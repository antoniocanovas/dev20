#!/bin/sh
# Pruebas de la API de clientes de AYC (la clave se pasa por entorno, no está en el repositorio).
#   AYC_KEY=xxxx sh pruebas/pruebas_api.sh
: "${AYC_KEY:?Falta AYC_KEY}"
A=${A:-http://88.27.249.204:50880/api}
for d in CARTAGENA cartagena B30682488 4300017472 %C3%91AM%20%C3%91AM XYZNOEXISTE; do
  printf '%-20s ' "$d"
  curl -s -m 30 -o /tmp/ayc_$$.json -w '%{http_code} %{size_download}B  ' -H "X-api-key: $AYC_KEY" \
    "$A/clientes/consultarClientes?dato=$d&subEmpresa=AYC"
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d),'clientes' if isinstance(d,list) else d)" /tmp/ayc_$$.json
done
rm -f /tmp/ayc_$$.json
