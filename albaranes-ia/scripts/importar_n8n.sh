#!/bin/sh
# importar_n8n.sh (se ejecuta en el servidor): importa y publica los flujos de /tmp/wf/*.json en n8n y lo reinicia
set -e
N=$(docker ps -q -f name=ia-support_n8n\\.)
for f in /tmp/wf/*.json; do
  docker cp $f $N:/tmp/wf.json; docker exec $N n8n import:workflow --input=/tmp/wf.json 2>&1 | grep -v "Error tracking" | tail -1
  id=$(python3 -c "import json,sys;d=json.load(open('$f'));print(d['id'])")
  docker exec $N n8n publish:workflow --id=$id 2>&1 | grep -E "^Publishing" || true
done
docker exec -u root $N rm -f /tmp/wf.json; rm -rf /tmp/wf
docker service update --force --quiet ia-support_n8n >/dev/null
for i in $(seq 1 60); do
  docker service logs --since 90s ia-support_n8n 2>&1 | grep -q 'Activated workflow "Albaranes IA - Revisión"' && break; sleep 3
done
docker service logs --since 90s ia-support_n8n 2>&1 | grep -E "Activated workflow \"Albaranes|rror" | grep -v "Error tracking" | tail -4
