#!/bin/sh
# Pruebas de punta a punta de la API de contactos, tarifas y albaranes.
# Uso en el servidor (red interna del proyecto, sin exponer la API):
#   docker run --rm -i --network easypanel-ia-support --entrypoint sh curlimages/curl:8.11.1 < pruebas_api.sh
# O desde el portátil con túnel SSH:  A=http://localhost:18000 sh pruebas_api.sh
A=${A:-http://ia-support_contactos-api:8000}
S=${S:-curl-$(date +%s)}
J='Content-Type: application/json'
r() { echo; echo "### $1 $2"; shift 2; curl -s -w '  [HTTP %{http_code}]' "$@"; echo; }
campo() { sed -E "s/.*\"$1\":([0-9]+).*/\1/"; }
primero() { grep -oE "\"$1\":[0-9]+" | head -1 | cut -d: -f2; }   # primera aparición del campo

r GET health $A/health
r GET buscar-azure "$A/contactos?q=azure"
ALTA=$(curl -s -X POST $A/contactos -H "$J" -d "{\"codigo\":\"T001\",\"nombre\":\"Contacto Prueba n8n\",\"tipo\":\"FACTURA\",\"sesion\":\"$S\",\"usuario\":\"pruebas\"}")
echo; echo "### POST alta"; echo "$ALTA"
ID=$(echo "$ALTA" | sed -E 's/^\{"id":([0-9]+).*/\1/')
r POST alta-duplicada -X POST $A/contactos -H "$J" -d '{"codigo":"T001","nombre":"Otro","tipo":"ALBARAN"}'
r POST nif-invalido -X POST $A/contactos -H "$J" -d '{"codigo":"T002","nombre":"X","tipo":"FACTURA","nif":"12345678A"}'
PATCH=$(curl -s -X PATCH $A/contactos/$ID -H "$J" -d "{\"telefono\":\"600111222\",\"sesion\":\"$S\"}")
echo; echo "### PATCH telefono"; echo "$PATCH"
LOG=$(echo "$PATCH" | campo log_id)
r GET ficha-tras-patch $A/contactos/$ID
r POST undo -X POST $A/log/$LOG/undo
r POST undo-repetido -X POST $A/log/$LOG/undo
r PATCH tipo-invalido -X PATCH $A/contactos/$ID -H "$J" -d '{"tipo":"OTRO"}'
r PATCH sin-campos -X PATCH $A/contactos/$ID -H "$J" -d '{}'

# --- Tarifas (necesitan Ventas instalado en Odoo) ---
r GET tarifa-cliente $A/contactos/$ID/tarifa
DUP=$(curl -s -X POST $A/contactos/$ID/tarifa/duplicar -H "$J" -d "{\"sesion\":\"$S\",\"usuario\":\"pruebas\"}")
echo; echo "### POST duplicar-tarifa"; echo "$DUP"
TARIFA=$(echo "$DUP" | sed -E 's/.*"tarifa":\{"id":([0-9]+).*/\1/')
LOG_DUP=$(echo "$DUP" | campo log_id)
PROD=$(curl -s "$A/productos?q=Desk%20Pad" | primero id)
r GET productos "$A/productos?q=Desk%20Pad"
PRECIO=$(curl -s -X POST $A/tarifas/$TARIFA/precios -H "$J" -d "{\"producto_id\":$PROD,\"precio\":1.5,\"sesion\":\"$S\",\"usuario\":\"pruebas\"}")
echo; echo "### POST precio-nuevo"; echo "$PRECIO"
REGLA=$(echo "$PRECIO" | primero precio_id)
CAMBIO=$(curl -s -X POST $A/tarifas/$TARIFA/precios -H "$J" -d "{\"producto_id\":$PROD,\"precio\":1.75,\"sesion\":\"$S\"}")
echo; echo "### POST precio-cambiado"; echo "$CAMBIO"
r POST precio-repetido -X POST $A/tarifas/$TARIFA/precios -H "$J" -d "{\"producto_id\":$PROD,\"precio\":1.75}"
r POST precio-negativo -X POST $A/tarifas/$TARIFA/precios -H "$J" -d "{\"producto_id\":$PROD,\"precio\":-1}"
r POST undo-precio-cambiado -X POST $A/log/$(echo "$CAMBIO" | campo log_id)/undo
r GET contenido-tarifa "$A/tarifas/$TARIFA?q=desk"
QUITA=$(curl -s -X DELETE "$A/tarifas/$TARIFA/precios/$REGLA?sesion=$S&usuario=pruebas")
echo; echo "### DELETE quitar-precio"; echo "$QUITA"
r POST undo-quitar-precio -X POST $A/log/$(echo "$QUITA" | campo log_id)/undo
r GET tarifas "$A/tarifas"
r PUT asignar-misma -X PUT $A/contactos/$ID/tarifa -H "$J" -d "{\"tarifa_id\":$TARIFA}"
r POST undo-duplicar -X POST $A/log/$LOG_DUP/undo
r GET tarifa-tras-undo $A/contactos/$ID/tarifa
NUEVA=$(curl -s -X POST $A/tarifas -H "$J" -d "{\"nombre\":\"Tarifa $S\",\"contacto_id\":$ID,\"sesion\":\"$S\",\"usuario\":\"pruebas\"}")
echo; echo "### POST crear-tarifa-vacia"; echo "$NUEVA"
r POST crear-tarifa-repetida -X POST $A/tarifas -H "$J" -d "{\"nombre\":\"tarifa $S\"}"
r POST crear-tarifa-sin-nombre -X POST $A/tarifas -H "$J" -d '{"nombre":"  "}'
r POST undo-crear-tarifa -X POST $A/log/$(echo "$NUEVA" | campo log_id)/undo
SUELTA=$(curl -s -X POST $A/tarifas -H "$J" -d "{\"nombre\":\"Suelta $S\",\"sesion\":\"$S\"}")
echo; echo "### POST crear-tarifa-sin-cliente"; echo "$SUELTA"
r POST undo-crear-sin-cliente -X POST $A/log/$(echo "$SUELTA" | campo log_id)/undo
r DELETE baja -X DELETE "$A/contactos/$ID?sesion=$S&usuario=pruebas"
r DELETE baja-repetida -X DELETE "$A/contactos/$ID"
r GET no-existe $A/contactos/999999

# --- Albaranes, solo consulta (necesitan Inventario instalado en Odoo) ---
r GET albaranes-entrega "$A/albaranes?tipo=ENTREGA&limite=3"
ALB=$(curl -s "$A/albaranes?tipo=ENTREGA&limite=1" | primero id)
r GET ficha-albaran $A/albaranes/$ALB
r GET albaranes-azure-pendientes "$A/albaranes?contacto_id=$(curl -s "$A/contactos?q=azure%20interior" | primero id)&estado=PENDIENTE&limite=3"
r GET lineas-producto "$A/lineas-albaran?producto_id=$PROD&limite=3"
r GET albaran-estado-invalido "$A/albaranes?estado=OTRO"
r GET lineas-sin-filtro "$A/lineas-albaran"
r GET albaran-no-existe $A/albaranes/999999
r GET log "$A/log?sesion=$S"
