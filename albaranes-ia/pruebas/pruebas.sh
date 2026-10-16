#!/bin/sh
# Batería de pruebas de extremo a extremo, en el servidor (lee usuario y contraseña de los
# webhooks del .env sin mostrarlos). Copia antes la carpeta pruebas/ al servidor:
#   scp -P 22022 -r pruebas root@217.154.182.5:/root/albaranes-ia/
#   ssh -p 22022 root@217.154.182.5 sh /root/albaranes-ia/pruebas/pruebas.sh
# No escribe en el ERP salvo las notas del historial (la rectificación está en DRY_RUN).
D=$(dirname "$0")
API="docker run --rm --network easypanel-ia-support curlimages/curl:8.11.1 -s"
ok=0; ko=0
comprueba() {  # $1 descripción, $2 condición (expresión python sobre d = JSON de respuesta), $3 JSON
  if printf '%s' "$3" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if ($2) else 1)" 2>/dev/null; then
    ok=$((ok+1)); echo "OK   $1"; else ko=$((ko+1)); echo "FALLO $1: $(printf '%s' "$3" | head -c 300)"; fi
}
cuerpo() { sed '$d'; }  # quita la última línea (HTTP ...) que añade subir.sh
# Copia única de una foto (bytes al final del JPEG): cada ejecución crea incidencias nuevas
unica() { f=/tmp/prueba-$(date +%s%N)-$(basename "$1"); cp "$1" "$f"; date +%s%N >> "$f"; echo "$f"; }

echo "== Servicios"
comprueba "albaranes-api /health" "d['ok']" "$($API http://ia-support_albaranes-api:8000/health)"
comprueba "barcode-ocr /health" "d['ok']" "$($API http://ia-support_barcode-ocr:8000/health)"
comprueba "DRY_RUN activo" "d['dry_run'] is True" "$($API http://ia-support_albaranes-api:8000/config)"
comprueba "ERP: WH/OUT/00040 por JSON-2" "d['numero']=='WH/OUT/00040' and len(d['lineas'])==5" \
  "$($API 'http://ia-support_albaranes-api:8000/erp/albaran?numero=WH/OUT/00040')"

echo "== Seguridad"
c=$(curl -s -o /dev/null -w "%{http_code}" https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/revision)
[ "$c" = 401 ] && { ok=$((ok+1)); echo "OK   webhooks sin credenciales -> 401"; } || { ko=$((ko+1)); echo "FALLO sin credenciales: $c"; }

echo "== Ingesta"
R=$(sh $D/subir.sh $(unica $D/foto_entregado_WH-OUT-00040.jpg) | cuerpo)
comprueba "albarán sin código: número por visión" "d['albaran']=='WH/OUT/00040' and d['origen_numero']=='vision'" "$R"
comprueba "detecta Gabinete 12 -> 10" "any(r['articulo'].endswith('Gabinete grande') and r['ia']==10 for r in d['tabla'])" "$R"
comprueba "queda pendiente de revisión" "d['estado']=='pendiente_revision'" "$R"
F=$(unica $D/foto_operaciones_WH-OUT-00041.jpg)
R=$(sh $D/subir.sh $F | cuerpo)
comprueba "informe de operaciones: número por código de barras" "d['albaran']=='WH/OUT/00041' and d['origen_numero']=='codigo_barras'" "$R"
comprueba "detecta Gabinete 12 -> 9" "any(r['articulo'].endswith('Gabinete grande') and r['ia']==9 for r in d['tabla'])" "$R"
ID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
R=$(sh $D/subir.sh $F | cuerpo)
comprueba "misma foto otra vez: misma incidencia, sin duplicar" "d.get('duplicada') is True and d['incidencia_id']==$ID" "$R"
R=$(sh $D/subir.sh $(unica $D/foto_no_albaran.jpg) | cuerpo)
comprueba "foto que no es un albarán: error explicado" "d['estado']=='error' and d['incidencia_id']" "$R"

echo "== Revisión"
c=$(sh $D/pedir.sh albaranes/revision -o /dev/null -w "%{http_code}"); [ "$c" = 200 ] && echo "OK   GET /albaranes/revision 200" || { ko=$((ko+1)); echo "FALLO lista $c"; }
c=$(sh $D/pedir.sh albaranes/revision/$ID -o /dev/null -w "%{http_code}"); [ "$c" = 200 ] && echo "OK   GET /albaranes/revision/$ID 200" || { ko=$((ko+1)); echo "FALLO pantalla $c"; }
comprueba "API incidencia con imagen" "d['id']==$ID and d['imagen'].startswith('data:image/jpeg')" "$(sh $D/pedir.sh albaranes/api/incidencia/$ID)"
R=$(sh $D/pedir.sh albaranes/api/incidencia/$ID/resolver -X POST -H 'Content-Type: application/json' -d '{"accion":"aprobar","usuario":"pruebas.sh"}')
comprueba "aprobar -> rectificación simulada (DRY_RUN)" "d['ok'] and d['estado']=='aprobada' and d['rectificacion']['dry_run'] and d['rectificacion']['caso']=='albaran_sin_validar'" "$R"
R=$(sh $D/pedir.sh albaranes/api/incidencia/$ID/resolver -X POST -H 'Content-Type: application/json' -d '{"accion":"aprobar"}')
comprueba "resolver dos veces -> rechazado" "not d['ok'] and 'no se puede resolver' in d['error']" "$R"

rm -f /tmp/prueba-*
echo "== Resultado: $ok correctas, $ko fallos"
[ $ko = 0 ]
