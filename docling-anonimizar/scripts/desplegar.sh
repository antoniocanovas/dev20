#!/bin/sh
# Despliega docling-anonimizar en el servidor (Easypanel, proyecto ia-support).
#   scripts/desplegar.sh [api] [n8n]     (sin argumentos: todo)
# - api: copia el código al origen "Upload" del servicio anonimizador, construye la imagen y fuerza el servicio.
#        El servicio tiene que existir antes en Easypanel (ver README).
# - n8n: regenera el flujo, lo importa sobre el mismo id, lo publica y reinicia n8n y su runner
#        (la CLI no avisa al n8n en marcha; el reinicio corta unos segundos los demás flujos).
set -e
cd "$(dirname "$0")/.."
H=root@217.154.182.5; P=22022
QUE=${*:-api n8n}
for x in $QUE; do
  case $x in
    api)
      tar czf - --no-xattrs --exclude __pycache__ -C api . | ssh -p $P $H "set -e
        docker service inspect ia-support_anonimizador >/dev/null 2>&1 || { echo 'Falta crear el servicio anonimizador en Easypanel'; exit 1; }
        C=/etc/easypanel/projects/ia-support/anonimizador/code; mkdir -p \$C; tar xzf - -C \$C
        docker build -q -t easypanel/ia-support/anonimizador:latest \$C >/dev/null
        docker service update --force --quiet ia-support_anonimizador >/dev/null
        echo 'anonimizador desplegado'" ;;
    n8n)
      python3 n8n/build_workflow.py >/dev/null
      scp -q -P $P n8n/workflows/docling_anonimizar.json $H:/tmp/docling_anonimizar.json
      ssh -p $P $H 'set -e
        N=$(docker ps -q -f name=ia-support_n8n\\.)
        docker cp /tmp/docling_anonimizar.json $N:/tmp/wf.json
        docker exec $N n8n import:workflow --projectId=njbPRUnMI5G0izCw --input=/tmp/wf.json 2>&1 | grep -v "Error tracking" | tail -1
        docker exec $N n8n publish:workflow --id=DoclingAnonim001 2>&1 | grep -E "^Publishing" || true
        docker exec -u root $N rm -f /tmp/wf.json; rm -f /tmp/docling_anonimizar.json
        docker service update --force --quiet ia-support_n8n >/dev/null
        for i in $(seq 1 60); do
          docker service logs --since 90s ia-support_n8n 2>&1 | grep -q "Activated workflow \"Docling" && break; sleep 3
        done
        docker service logs --since 90s ia-support_n8n 2>&1 | grep -E "Activated workflow \"Docling|rror" | grep -v "Error tracking" | tail -4
        # El runner DESPUÉS de que n8n esté arriba: si se recrea antes, se queda conectado al broker
        # del n8n viejo ("Runner process exited on idle timeout" cada ~18 s) y los nodos Code fallan
        # con "Task request timed out". Pasó el 12/11 a mitad de una conversión.
        docker service update --force --quiet ia-support_n8n-runner >/dev/null
        echo "runner recreado"' ;;
  esac
done
