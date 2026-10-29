#!/bin/sh
# subir.sh <foto> [query] [más fotos…]  -> sube las fotos (páginas de un albarán, en orden) a la
# ingesta con las credenciales del .env del servidor
E=${ENV_FILE:-/root/albaranes-ia/.env}
U=$(sed -n "s/^REVISION_USER=//p" $E); P=$(sed -n "s/^REVISION_PASSWORD=//p" $E)
F=$1; Q=$2; shift; [ $# -gt 0 ] && shift
set -- -F "foto=@$F" $(for x in "$@"; do printf -- '-F foto=@%s ' "$x"; done)
curl -s -m 300 -u "$U:$P" "$@" "https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/ingesta?$Q" -w "\nHTTP %{http_code} %{time_total}s\n"
