#!/bin/sh
# Despliega albaranes-ia en el servidor de pruebas (Easypanel, proyecto ia-support).
#   scripts/desplegar.sh [api] [ocr] [n8n]     (sin argumentos: todo)
# - api/ocr: copia el código al origen "Upload" de Easypanel, construye la imagen y fuerza el servicio.
# - n8n: regenera los flujos, los importa sobre los mismos ids, los publica y reinicia n8n
#   (la CLI no avisa al n8n en marcha; el reinicio corta unos segundos los demás flujos).
set -e
cd "$(dirname "$0")/.."
H=root@217.154.182.5; P=22022
QUE=${*:-api ocr n8n}
codigo() {  # $1 carpeta local, $2 servicio
  tar czf - --no-xattrs --exclude __pycache__ -C "$1" . | ssh -p $P $H "set -e
    C=/etc/easypanel/projects/ia-support/$2/code; mkdir -p \$C; tar xzf - -C \$C
    docker build -q -t easypanel/ia-support/$2:latest \$C >/dev/null
    docker service update --force --quiet ia-support_$2 >/dev/null
    echo \"$2 desplegado\""
}
for x in $QUE; do
  case $x in
    api) codigo albaranes-api albaranes-api ;;
    ocr) codigo barcode-ocr barcode-ocr ;;
    n8n)
      python3 n8n/build_workflows.py
      ssh -p $P $H 'rm -rf /tmp/wf; mkdir -p /tmp/wf'
      scp -q -P $P n8n/workflows/*.json $H:/tmp/wf/
      scp -q -P $P scripts/importar_n8n.sh $H:/tmp/importar_n8n.sh
      ssh -p $P $H 'sh /tmp/importar_n8n.sh; rm -f /tmp/importar_n8n.sh' ;;
  esac
done
