#!/bin/sh
# subir.sh <foto> [query]  -> sube la foto a la ingesta con las credenciales del .env del servidor
E=${ENV_FILE:-/root/albaranes-ia/.env}
U=$(sed -n "s/^REVISION_USER=//p" $E); P=$(sed -n "s/^REVISION_PASSWORD=//p" $E)
curl -s -m 300 -u "$U:$P" -F "foto=@$1" "https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/ingesta?$2" -w "\nHTTP %{http_code} %{time_total}s\n"
