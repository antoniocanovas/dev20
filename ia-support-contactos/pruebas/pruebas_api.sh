#!/bin/sh
# Pruebas de punta a punta de la API de contactos.
# Uso en el servidor (red interna del proyecto, sin exponer la API):
#   docker run --rm -i --network easypanel-ia-support --entrypoint sh curlimages/curl:8.11.1 < pruebas_api.sh
# O desde el portátil con túnel SSH:  A=http://localhost:18000 sh pruebas_api.sh
A=${A:-http://ia-support_contactos-api:8000}
S=${S:-curl-$(date +%s)}
J='Content-Type: application/json'
r() { echo; echo "### $1 $2"; shift 2; curl -s -w '  [HTTP %{http_code}]' "$@"; echo; }
campo() { sed -E "s/.*\"$1\":([0-9]+).*/\1/"; }

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
r DELETE baja -X DELETE "$A/contactos/$ID?sesion=$S&usuario=pruebas"
r DELETE baja-repetida -X DELETE "$A/contactos/$ID"
r GET no-existe $A/contactos/999999
r GET log "$A/log?sesion=$S"
