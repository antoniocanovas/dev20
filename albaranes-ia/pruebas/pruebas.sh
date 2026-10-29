#!/bin/sh
# Batería de pruebas de extremo a extremo, en el servidor (lee usuario y contraseña de los
# webhooks del .env sin mostrarlos). Copia antes la carpeta pruebas/ al servidor:
#   scp -P 22022 -r pruebas root@217.154.182.5:/root/albaranes-ia/
#   ssh -p 22022 root@217.154.182.5 sh /root/albaranes-ia/pruebas/pruebas.sh
# No escribe en el ERP salvo las notas del historial de los albaranes propios (la rectificación
# está en DRY_RUN; los de terceros solo leen el ERP).
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
comprueba "tipo Modificado" "d['marca']=='modificado'" "$R"
F=$(unica $D/foto_operaciones_WH-OUT-00041.jpg)
R=$(sh $D/subir.sh $F | cuerpo)
comprueba "informe de operaciones: número por código de barras" "d['albaran']=='WH/OUT/00041' and d['origen_numero']=='codigo_barras'" "$R"
comprueba "detecta Gabinete 12 -> 9" "any(r['articulo'].endswith('Gabinete grande') and r['ia']==9 for r in d['tabla'])" "$R"
ID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
R=$(sh $D/subir.sh $F | cuerpo)
comprueba "misma foto otra vez: misma incidencia, sin duplicar" "d.get('duplicada') is True and d['incidencia_id']==$ID" "$R"
R=$(sh $D/subir.sh $(unica $D/foto_no_albaran.jpg) | cuerpo)
comprueba "foto que no es un albarán: error explicado" "d['estado']=='error' and d['marca']=='error' and d['incidencia_id']" "$R"
EID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")

echo "== Varias fotos por albarán"
P1=$(unica $D/foto_2paginas_WH-OUT-00040_p1.jpg); P2=$(unica $D/foto_2paginas_WH-OUT-00040_p2.jpg)
R=$(sh $D/subir.sh "$P1" "" "$P2" | cuerpo)
comprueba "2 fotos: un solo reconocimiento con 2 páginas" "d['albaran']=='WH/OUT/00040' and d['paginas']==2 and len(d['tabla'])==5" "$R"
comprueba "2 fotos: Gabinete 12 -> 10 (foto 1)" "any(r['articulo'].endswith('Gabinete grande') and r['ia']==10 for r in d['tabla'])" "$R"
comprueba "2 fotos: Cubo 8 sin cambio (foto 2)" "any(r['articulo'].endswith('pedal') and r['ia']==8 for r in d['tabla'])" "$R"
MID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
comprueba "2 fotos: cada línea con su foto" \
  "[l['pagina'] for l in d['decision']['lineas'] if l['producto'].endswith('pedal')]==[2] and [l['pagina'] for l in d['decision']['lineas'] if l['producto']=='Gabinete grande']==[1] and len(d['paginas'])==2" \
  "$(sh $D/pedir.sh albaranes/api/incidencia/$MID)"
R=$(sh $D/subir.sh "$P1" "" "$P2" | cuerpo)
comprueba "2 fotos otra vez: mismo reconocimiento" "d.get('duplicada') is True and d['incidencia_id']==$MID" "$R"
R=$(sh $D/subir.sh "$P2" "" "$P1" | cuerpo)
comprueba "2 fotos en otro orden: reconocimiento nuevo con aviso de previos" \
  "d['incidencia_id']!=$MID and any('ya se había reconocido' in a for a in d['avisos'])" "$R"

echo "== Albaranes de terceros (solo se lee el ERP)"
comprueba "ERP: WH/IN/00016 con precios del pedido de compra" "d['numero']=='WH/IN/00016' and d['compra']['numero']=='P00014' and d['lineas'][0]['precio']==780" \
  "$($API 'http://ia-support_albaranes-api:8000/erp/albaran?numero=WH/IN/00016')"
R=$(sh $D/subir.sh $(unica $D/foto_proveedor_valorado_WH-IN-00016.jpg) "tipo=entrada" | cuerpo)
comprueba "entrada valorada: referencia escrita a mano -> WH/IN/00016" "d['tipo']=='entrada' and d['albaran']=='WH/IN/00016' and d['origen_numero']=='vision'" "$R"
comprueba "entrada: armario 6 -> 5 a mano" "any(r['articulo'].endswith('Gabinete grande') and r['erp']==6 and r['ia']==5 for r in d['tabla'])" "$R"
comprueba "entrada: caja a 14,50 en vez de 14 -> precio distinto" "any(r['articulo'].endswith('Caja de almacenamiento') and r['precio_doc']==14.5 and 'precio_distinto' in r['motivos'] for r in d['tabla'])" "$R"
comprueba "entrada: cubo a 10 con 5 % = 9,50 neto -> sin diferencia" "any(r['articulo'].endswith('pedal') and r['estado']=='verificado' for r in d['tabla'])" "$R"
comprueba "entrada: portes sin pareja, por revisar" "any('ortes' in e['articulo'] for e in d['extras']) and d['estado']=='pendiente_revision' and d['marca']=='modificado'" "$R"
TID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
R=$(sh $D/subir.sh $(unica $D/foto_proveedor_sin_referencia_WH-IN-00017.jpg) "tipo=entrada" | cuerpo)
comprueba "entrada sin referencia: pide escribir nuestro albarán" "d['albaran'] is None and any('escríbelo' in a for a in d['avisos']) and len(d['extras'])==2" "$R"
SID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
c=$(sh $D/pedir.sh albaranes/buscar/$SID -m 120 -X POST --data-urlencode "referencias=WH/IN/00017" -o /dev/null -w "%{http_code}")
comprueba "buscar en el ERP WH/IN/00017 a mano ($c): todo coincide" \
  "d['albaran_numero']=='WH/IN/00017' and d['origen_numero']=='manual' and d['referencias']=='WH/IN/00017' and all(l['estado']=='verificado' for l in d['decision']['lineas']) and not d['decision']['extras']" \
  "$(sh $D/pedir.sh albaranes/api/incidencia/$SID)"
c=$(sh $D/pedir.sh albaranes/buscar/$SID -m 120 -X POST --data-urlencode "referencias=WH/IN/00016, WH/IN/00017" -o /dev/null -w "%{http_code}")
comprueba "buscar dos referencias ($c): las líneas de WH/IN/00016 no están en su albarán" \
  "d['albaran_numero']=='WH/IN/00016, WH/IN/00017' and sum('no_en_documento' in l['motivos'] for l in d['decision']['lineas'])==4" \
  "$(sh $D/pedir.sh albaranes/api/incidencia/$SID)"
c=$(sh $D/pedir.sh albaranes/buscar/$SID -m 120 -X POST --data-urlencode "referencias=WH/IN/99999" -o /dev/null -w "%{http_code}")
comprueba "buscar una referencia que no existe ($c): se avisa" \
  "d['albaran_numero'] is None and any('99999' in a for a in d['decision']['avisos'])" "$(sh $D/pedir.sh albaranes/api/incidencia/$SID)"
R=$(sh $D/subir.sh $(unica $D/foto_proveedor_valorado_WH-IN-00016.jpg) "tipo=entrada&referencias=P00014" | cuerpo)
comprueba "entrada con el pedido P00014 indicado al subir -> WH/IN/00016" "d['albaran']=='WH/IN/00016' and d['origen_numero']=='manual'" "$R"
comprueba "ERP: EAN del producto (barcode) en las líneas de WH/IN/00016" \
  "{l['referencia']: l['ean'] for l in d['lineas']} == {'E-COM07': '8412345000072', 'E-COM08': None, 'E-COM10': '8412345000102', 'FURN_0002': None}" \
  "$($API 'http://ia-support_albaranes-api:8000/erp/albaran?numero=WH/IN/00016')"
R=$(sh $D/subir.sh $(unica $D/foto_proveedor_ean_WH-IN-00016.jpg) "tipo=entrada" | cuerpo)
NID=$(printf '%s' "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['incidencia_id'])")
R=$(sh $D/pedir.sh albaranes/api/incidencia/$NID)
comprueba "entrada con EAN: armario y cubo emparejados por EAN; caja y alfombrilla, por la IA" \
  "{l['referencia']: [x['emparejado_por'] for x in l['documento']] for l in d['decision']['lineas']} == {'E-COM07': ['ean'], 'E-COM08': ['ia'], 'E-COM10': ['ean'], 'FURN_0002': ['ia']}" "$R"
comprueba "entrada con EAN: cubo 10 -> 9 a mano; el resto coincide" \
  "{l['referencia']: (l['cantidad_doc'], l['estado']) for l in d['decision']['lineas']} == {'E-COM07': (6, 'verificado'), 'E-COM08': (30, 'verificado'), 'E-COM10': (9, 'pendiente_revision'), 'FURN_0002': (20, 'verificado')}" "$R"
R=$(sh $D/subir.sh $(unica $D/foto_cliente_entrega_WH-OUT-00040.jpg) "tipo=entrega" | cuerpo)
comprueba "entrega: '00040' escrito a mano -> WH/OUT/00040" "d['tipo']=='entrega' and d['albaran']=='WH/OUT/00040'" "$R"
comprueba "entrega: el cliente recibe 10 armarios de 12" "any(r['articulo'].endswith('Gabinete grande') and r['erp']==12 and r['ia']==10 and 'cantidad_distinta' in r['motivos'] for r in d['tabla'])" "$R"
comprueba "entrega: el resto coincide (sus códigos emparejados por descripción)" "sum(r['estado']=='verificado' for r in d['tabla'])==4 and not d['extras']" "$R"
R=$(sh $D/pedir.sh albaranes/api/incidencia/$TID/resolver -X POST -H 'Content-Type: application/json' -d '{"accion":"aprobar","usuario":"pruebas.sh"}')
comprueba "aprobar uno de terceros: se guarda sin rectificar" "d['ok'] and d['estado']=='aprobada' and d['rectificacion'] is None" "$R"
comprueba "la API no rectifica los de terceros" "'terceros' in d['detail']" \
  "$($API -X POST -H 'Content-Type: application/json' -d "{\"incidencia_id\": $TID}" http://ia-support_albaranes-api:8000/erp/rectificar)"

echo "== Revisión"
c=$(sh $D/pedir.sh albaranes/revision -o /dev/null -w "%{http_code}"); [ "$c" = 200 ] && echo "OK   GET /albaranes/revision 200" || { ko=$((ko+1)); echo "FALLO lista $c"; }
c=$(sh $D/pedir.sh albaranes/revision/$ID -o /dev/null -w "%{http_code}"); [ "$c" = 200 ] && echo "OK   GET /albaranes/revision/$ID 200" || { ko=$((ko+1)); echo "FALLO pantalla $c"; }
comprueba "API incidencia con imagen" "d['id']==$ID and d['paginas'][0]['imagen'].startswith('data:image/jpeg')" "$(sh $D/pedir.sh albaranes/api/incidencia/$ID)"
R=$(sh $D/pedir.sh albaranes/api/incidencia/$ID/resolver -X POST -H 'Content-Type: application/json' -d '{"accion":"aprobar","usuario":"pruebas.sh"}')
comprueba "aprobar -> rectificación simulada (DRY_RUN)" "d['ok'] and d['estado']=='aprobada' and d['rectificacion']['dry_run'] and d['rectificacion']['caso']=='albaran_sin_validar'" "$R"
R=$(sh $D/pedir.sh albaranes/api/incidencia/$ID/resolver -X POST -H 'Content-Type: application/json' -d '{"accion":"aprobar"}')
comprueba "resolver dos veces -> rechazado" "not d['ok'] and 'no se puede resolver' in d['error']" "$R"
sh $D/pedir.sh "albaranes/revision?estado=&desde=2026-13-01" | grep -q "Fecha no válida" \
  && { ok=$((ok+1)); echo "OK   lista: fecha no válida explicada"; } || { ko=$((ko+1)); echo "FALLO lista con fecha no válida"; }
c=$(sh $D/pedir.sh albaranes/eliminar/$ID -X POST -d accion= -o /dev/null -w "%{http_code}")
[ "$c" = 409 ] && { ok=$((ok+1)); echo "OK   eliminar uno aprobado -> 409"; } || { ko=$((ko+1)); echo "FALLO eliminar aprobado: $c"; }

echo "== Reconocimientos con error"
c=$(sh $D/pedir.sh albaranes/reintentar/$EID -m 300 -X POST -d accion= -o /dev/null -w "%{http_code}")
comprueba "reintentar: mismo reconocimiento, vuelve a procesarse ($c)" \
  "d['id']==$EID and d['estado']=='error' and any(e['evento']=='reprocesar' for e in d['eventos'])" "$(sh $D/pedir.sh albaranes/api/incidencia/$EID)"
c=$(sh $D/pedir.sh albaranes/eliminar/$EID -X POST -d accion= -o /dev/null -w "%{http_code}")
c2=$(sh $D/pedir.sh albaranes/api/incidencia/$EID -o /dev/null -w "%{http_code}")
[ "$c" = 200 ] && [ "$c2" = 404 ] && { ok=$((ok+1)); echo "OK   eliminar el de error -> ya no existe"; } || { ko=$((ko+1)); echo "FALLO eliminar error: $c / $c2"; }

rm -f /tmp/prueba-*
echo "== Resultado: $ok correctas, $ko fallos"
[ $ko = 0 ]
