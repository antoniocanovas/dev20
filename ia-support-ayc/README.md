# ia-support · Clientes AYC (n8n + API del ERP de AYC)

Chat IA en n8n que consulta clientes contra la API del ERP de AYC. Misma filosofía
que `ia-support-contactos/n8n/chat-ia-contactos.json` (Chat Trigger → AI Agent con
OpenRouter, memoria y herramientas), pero de momento solo lectura y una herramienta.

```
Chat (n8n) → Agente clientes ── consultar_clientes ──→ Consulta → API clientes → Normalizar
                                 (subflujo del mismo flujo)        │
                                                                   └─ GET 88.27.249.204:50880/api/clientes/consultarClientes
```

## La API

`GET http://88.27.249.204:50880/api/clientes/consultarClientes?dato=<texto>&subEmpresa=AYC`, cabecera `X-api-key`.
`dato` busca en nombre, CIF y código de cliente. Devuelve un array de
`{codigoCliente, nombreCliente, cif, direccion, codigoPostal, poblacion, provincia, nombreClienteFactura}`.

Campos opcionales (análisis de 45.911 clientes, 27/10/2026):

- `nombreClienteCadena`: solo viene si el cliente pertenece a una cadena (1.709, ~4 %); si no, **la clave no existe**.
  En 36 coincide con el propio nombre (es la central). Las más frecuentes: GRUPO UPPER (con variantes `(AYC)`, `(¡QUE!) *BAJA*`),
  CASH LEVANTE, EUROPAMUR, CUDAL.
- `nombreClienteFactura`: casi siempre presente, pero igual al nombre en el 94 %. Distinto en 2.502 (p. ej. las tiendas
  `+BK …` facturan a VICKY FOODS PRODUCTS SLU); falta en 35 (códigos 4350…).
- *Normalizar* los devuelve como `cadena` y `nombre_factura`, **vacíos si faltan o son iguales al nombre**, y el agente
  muestra "Cadena:" y "Factura a:" solo cuando no están vacíos, en la lista y en la ficha.
- Algunos nombres llevan `*BAJA*` en el texto; la API no tiene un campo de baja.

Lo que se ha visto al probarla (27/10/2026), y por qué el flujo hace lo que hace:

- **Distingue mayúsculas**: `cartagena` → 0 clientes, `CARTAGENA` → 201. El flujo pasa el dato a mayúsculas.
- **Sin límite**: `B30` devuelve 2.759 clientes (1,4 MB). Al modelo solo le llegan los 10 primeros, con `total` y `hay_mas`.
- **Campos rellenos de espacios** (columnas de ancho fijo): se recortan.
- **Errores intermitentes**: la primera llamada con `CARTAGENA` devolvió 500 `{"mensaje": "Error al consultar clientes.", "detalle": "Error interno."}` y la siguiente funcionó. El nodo reintenta 3 veces (1 s entre intentos).
- **Tildes y Ñ literales**: `NAM NAM` no encuentra `ÑAM ÑAM`. El agente prueba variantes si no hay resultados.
- **Un CIF, varios códigos**: `B30682488` tiene dos códigos (dos direcciones), así que se tratan como clientes distintos y se elige.
- Sin clave: 401 `API Key no válida o ausente.`

## El flujo

Archivo `n8n/chat-ia-clientes-ayc.json`, generado con `python3 n8n/build_workflow.py` (el código del
nodo *Normalizar* está en `n8n/normalizar.js`; tras cambiarlo hay que regenerar el JSON).

- **consultar_clientes** (*Call n8n Workflow Tool*): llama al mismo flujo por su id fijo `ChatIaClienAYC01` por la
  entrada *Consulta* (*Execute Workflow Trigger*, parámetro `dato`). Se hace así, y no con un *HTTP Request Tool*
  como en contactos, porque la respuesta cruda puede pesar más de 1 MB y hay que recortarla antes del modelo.
- **API clientes**: HTTP Request con la credencial *Header Auth* "API AYC (X-api-key)". La respuesta se lee como
  texto para que un array vacío no corte el subflujo.
- **Normalizar**: devuelve `{dato, total, requiere_eleccion, hay_mas, resultados[≤10]}` (coincidencias exactas de
  código o CIF primero) o `{error}`, igual que la búsqueda de contactos.
- **Agente clientes**: si hay varios, lista numerada (nombre, código, CIF, población) y deja elegir; con uno, la ficha.
  Si piden algo que no sea consultar clientes, dice que de momento solo consulta.
- Modelo, temperatura y memoria como en contactos (OpenRouter `anthropic/claude-haiku-5.5`, 0,1; últimos 20 mensajes).

## Instalarlo en n8n

El flujo tiene id fijo `ChatIaClienAYC01` y ya apunta a las credenciales `API AYC (X-api-key)` (id `AycApiKeyHeader1`)
y *OpenRouter account* (id `BAhp65TskxSwWt7J`, la del chat de contactos).

```sh
# credencial (cred.json fuera del repositorio):
# [{"id":"AycApiKeyHeader1","name":"API AYC (X-api-key)","type":"httpHeaderAuth","data":{"name":"X-api-key","value":"<clave>"}}]
C=$(docker ps -q -f name=ia-support_n8n.1)
docker cp cred.json $C:/tmp/ && docker exec $C n8n import:credentials --input=/tmp/cred.json && docker exec $C rm /tmp/cred.json
docker cp chat-ia-clientes-ayc.json $C:/tmp/w.json && docker exec $C n8n import:workflow --input=/tmp/w.json
```

Después, abrir el flujo **Chat IA clientes AYC** en n8n → **Publish**, y probar desde el panel Chat:
"busca Ñam Ñam", "B30682488", "4300017472", "clientes de Cartagena".

**Tiene que estar publicado** también para que funcione la herramienta: en n8n 2.x un subflujo sin publicar da
*"Workflow is not active and cannot be executed"*. `n8n publish:workflow --id=ChatIaClienAYC01` lo publica en la BD,
pero el n8n en marcha no registra la URL del chat hasta reiniciarlo, o hasta despublicar y volver a publicar desde la interfaz.

## Instalación y prueba en el servidor (27/10/2026)

- Importados la credencial `AycApiKeyHeader1` y el flujo `ChatIaClienAYC01` (nuevo; los de contactos tienen el mismo
  hash de exportación y el mismo `updatedAt` del 16/10/2026 antes y después). Publicado con la CLI.
- Prueba con un flujo temporal (ya borrado) lanzado con
  `docker exec -e N8N_RUNNERS_MODE=internal -e N8N_RUNNERS_BROKER_PORT=5699 <n8n> n8n execute --id=...`
  (sin esas variables choca con el broker de tareas del n8n en marcha, puerto 5679):

| Subflujo, `dato` | Resultado |
|---|---|
| `cartagena` | 201 clientes (en mayúsculas), 10 devueltos, `hay_mas` |
| `B30682488` | 2 (ÑAM ÑAM, Molino de Marfagones y Canteras) |
| `4300017472` | 1 |
| `XYZNOEXISTE` | 0 |
| `B30` | 2.759, 10 devueltos |
| vacío | error "Falta el dato a buscar" |

| Usuario | Agente |
|---|---|
| busca los clientes con CIF b30682488 | Lista numerada de los 2 ÑAM ÑAM con código y dirección, y pide elegir |
| el segundo, ¿en qué dirección está? | Ficha del 4300028500 (C/ Fuente, Nº3, 30394 Canteras, Murcia) sin volver a buscar |
| ¿y cuántos clientes hay en cartagena? dame solo los primeros | 201 en total, los 10 primeros y propone acotar |

Tras añadir cadena y factura (mismo día, mismo método):

| Usuario | Agente |
|---|---|
| busca el cliente 4300016289 | Ficha de AGRUBUEN ¡UPPER 810! con "Cadena: GRUPO UPPER" y "Factura a: GRUPO UPPER" |
| busca el CIF B30710875 | Lista de 3; cada uno con su cadena, y "Factura a" solo en el que factura a otro |
| busca +BK AGUILAS | Ficha con "Factura a: VICKY FOODS PRODUCTS SLU" y sin cadena |

El servidor de n8n tiene que llegar a `88.27.249.204:50880` (desde el portátil responde en menos de 1 s).

## Pruebas de la API

```sh
AYC_KEY=<clave> sh pruebas/pruebas_api.sh
```
