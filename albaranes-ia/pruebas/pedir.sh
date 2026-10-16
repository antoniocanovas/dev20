#!/bin/sh
# pedir.sh <ruta> [opciones curl...]: petición autenticada a los webhooks de albaranes-ia
E=${ENV_FILE:-/root/albaranes-ia/.env}
U=$(sed -n "s/^REVISION_USER=//p" $E); P=$(sed -n "s/^REVISION_PASSWORD=//p" $E)
R=$1; shift
curl -s -m 120 -u "$U:$P" "$@" "https://ia-support-n8n.kw2y1s.easypanel.host/webhook/$R"
