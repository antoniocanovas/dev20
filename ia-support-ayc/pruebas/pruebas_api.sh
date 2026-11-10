#!/bin/sh
# Pruebas de la API de AYC (clientes, precios especiales, descuentos y surtidos) (la clave se pasa por entorno, no está en el repositorio).
#   AYC_KEY=xxxx sh pruebas/pruebas_api.sh
: "${AYC_KEY:?Falta AYC_KEY}"
A=${A:-http://88.27.249.204:50880/api}
for d in CARTAGENA cartagena B30682488 4300017472 %C3%91AM%20%C3%91AM XYZNOEXISTE; do
  printf '%-20s ' "$d"
  curl -s -m 30 -o /tmp/ayc_$$.json -w '%{http_code} %{size_download}B  ' -H "X-api-key: $AYC_KEY" \
    "$A/clientes/consultarClientes?dato=$d&subEmpresa=AYC"
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d),'clientes' if isinstance(d,list) else d)" /tmp/ayc_$$.json
done
for r in preciosEspeciales descuentos; do
  for q in consultar?codigoCliente=4300016289 consultar?codigoCliente=4300017472 listarProductos?codigoTabla=14 \
           listarProductos?codigoTabla=12; do
    printf '%-50s ' "$r/$q"
    curl -s -m 30 -o /tmp/ayc_$$.json -w '%{http_code} %{size_download}B  ' -H "X-api-key: $AYC_KEY" "$A/$r/$q&subEmpresa=AYC"
    python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d),'líneas' if isinstance(d,list) else d)" /tmp/ayc_$$.json
  done
done
# Surtidos: muestra el formato de las respuestas (claves y primeras líneas). T=<surtido> para listar otro.
T=${T:-}
printf '%-50s ' "surtidos/consultar 4300016289"
curl -s -m 30 -o /tmp/ayc_$$.json -w '%{http_code} %{size_download}B\n' -H "X-api-key: $AYC_KEY" \
  "$A/surtidos/consultar?codigoCliente=4300016289&subEmpresa=AYC"
head -c 600 /tmp/ayc_$$.json; echo
[ -z "$T" ] && T=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));d=d[0] if isinstance(d,list) and d else d;print(str(d.get('codigoTabla',d.get('codigoSurtido',''))).strip())" /tmp/ayc_$$.json 2>/dev/null)
for c in 4300017472 9999999999; do
  printf '%-50s ' "surtidos/consultar $c"
  curl -s -m 30 -w '  %{http_code}\n' -H "X-api-key: $AYC_KEY" "$A/surtidos/consultar?codigoCliente=$c&subEmpresa=AYC"
done
if [ -n "$T" ]; then
  printf '%-50s ' "surtidos/listarProductos $T"
  curl -s -m 30 -o /tmp/ayc_$$.json -w '%{http_code} %{size_download}B  ' -H "X-api-key: $AYC_KEY" \
    "$A/surtidos/listarProductos?codigoTabla=$T&subEmpresa=AYC"
  python3 -c "
import json,sys,collections
d=json.load(open(sys.argv[1]))
if not isinstance(d,list): print(d); sys.exit()
print(len(d),'líneas'); print('claves:',collections.Counter(k for x in d for k in x))
for x in d[:5]: print(' ',x)" /tmp/ayc_$$.json
fi
rm -f /tmp/ayc_$$.json
