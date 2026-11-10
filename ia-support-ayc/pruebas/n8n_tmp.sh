#!/bin/sh
# Pruebas del flujo con un flujo temporal en el n8n del servidor (no toca el publicado; la clave de la API no sale
# del servidor: se usa la credencial de n8n).
#   sh pruebas/n8n_tmp.sh subflujo '{"accion":"surtidos","codigo_cliente":"4300016289","articulo":"poker"}'
#   sh pruebas/n8n_tmp.sh agente '¿Puedo venderle Poker de vainilla al 4300016289?'
#   sh pruebas/n8n_tmp.sh limpiar      # borra el flujo temporal y sus ejecuciones (al terminar)
# Las pruebas de agente usan el flujo PUBLICADO: instalar antes la versión nueva (ver README).
# Lanzar los casos de uno en uno: muchas peticiones a la vez tumban la API de AYC.
set -e
SSH="ssh -p 22022 root@217.154.182.5"
TMP_ID=${TMP_ID:-TmpSurtidoAYC01}; export TMP_ID
D=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT

if [ "$1" = limpiar ]; then
  $SSH "P=\$(docker ps -q -f name=ia-support_n8n-db); docker exec \$P sh -c \"psql -U \\\$POSTGRES_USER -d \\\${POSTGRES_DB:-\\\$POSTGRES_USER} \
    -c \\\"delete from execution_entity where \\\\\\\"workflowId\\\\\\\"='$TMP_ID';\\\" -c \\\"delete from workflow_entity where id='$TMP_ID';\\\"\"; \
    docker exec -u root \$(docker ps -q -f name=ia-support_n8n.1) rm -f /tmp/t.json; rm -f /tmp/tmp_pruebas.json"
  exit
fi
case "$1" in subflujo) E=$(python3 -c "import json,sys;d=dict.fromkeys(['accion','dato','codigo_cliente','codigo_tabla','articulo'],'');d.update(json.loads(sys.argv[1]));print(json.dumps(d,ensure_ascii=False))" "$2");; agente) E=$2;; *) echo "uso: $0 subflujo|agente|limpiar ..."; exit 1;; esac
python3 "$D/flujo_tmp.py" "$1" "$E" "$W/t.json"
scp -q -P 22022 "$W/t.json" root@217.154.182.5:/tmp/tmp_pruebas.json
$SSH 'C=$(docker ps -q -f name=ia-support_n8n.1); docker cp /tmp/tmp_pruebas.json $C:/tmp/t.json && docker exec $C n8n import:workflow --input=/tmp/t.json >/dev/null 2>&1
  docker exec -e N8N_RUNNERS_MODE=internal -e N8N_RUNNERS_BROKER_PORT=5699 $C n8n execute --id='"$TMP_ID"' --rawOutput 2>&1' > "$W/out.txt" || true
python3 "$D/resultado_tmp.py" "$W/out.txt"
