# ia-support · Contactos (n8n + API + Odoo 20)

Primera fase del asistente de surtidos: una API REST de contactos y de sus
tarifas que escribe por SQL directamente en las tablas de un Odoo 20
(`res_partner`, `product_pricelist`, `product_pricelist_item`) y que consulta
albaranes (`stock_picking`, `stock_move`), más un flujo de prueba y un chat IA
en el n8n existente. Entorno interno de pruebas: sin autenticación y sin HTTPS propio.

```
Proyecto ia-support (Easypanel, servidor 217.154.182.5)

  n8n (existente) --HTTP--> contactos-api:8000 --SQL--> surtidos-db:5432 (BD odoo) <-- odoo20:8069
  navegador ------------------------------------------------------------------------> odoo20 (dominio Easypanel)
```

## Servicios creados

| Servicio Easypanel | Host interno (red `easypanel-ia-support`) | Tipo / imagen | Exposición |
|---|---|---|---|
| `surtidos-db` | `ia-support_surtidos-db:5432` | PostgreSQL 16 (`postgres:16`), BD `odoo`, usuario `odoo` | Sin puerto público |
| `odoo20` | `ia-support_odoo20:8069` | App, imagen `odoo:20` | https://ia-support-odoo20.kw2y1s.easypanel.host |
| `contactos-api` | `ia-support_contactos-api:8000` | App, código subido a Easypanel (Upload) + build con `Dockerfile` | Sin dominio ni puerto público |

No se ha modificado ningún servicio existente de ia-support (`db`, `docling`, `n8n`, `n8n-db`, `n8n-runner`, `odoo`, `odoo-db`).

### Accesos

- **Odoo 20**: https://ia-support-odoo20.kw2y1s.easypanel.host, usuario `admin` / `admin`. BD `odoo` con el módulo Contactos y datos demo.
- **n8n**: https://ia-support-n8n.kw2y1s.easypanel.host. Flujo **"Prueba API contactos"**.
- **API (Swagger)**: solo red interna. Desde el portátil, con un túnel (ver más abajo): http://localhost:18000/docs.
- **Easypanel**: solo por túnel SSH (`~/sshn8n` reenvía el puerto 3000): http://localhost:3000.

### Variables de entorno (en Easypanel, no en el repositorio)

- `odoo20`: `HOST=ia-support_surtidos-db`, `USER=odoo`, `PASSWORD=<pg>`, `PORT=5432`, `ODOO_ADMIN_PASSWD=<contraseña maestra>`.
- `contactos-api`: `DB_HOST=ia-support_surtidos-db`, `DB_PORT=5432`, `DB_NAME=odoo`, `DB_USER=odoo`, `DB_PASSWORD=<pg>`. Opcional: `ODOO_LANG` (por defecto `es_ES`), idioma en que se leen y crean los nombres de tarifas y productos; si no hay traducción se usa el inglés.

La contraseña de Postgres es aleatoria (16 bytes en hexadecimal) y está en Easypanel → surtidos-db → Credenciales.

## Decisiones tomadas (no estaban en el encargo)

- **`PORT=5432` en odoo20**: Easypanel inyecta `PORT=8069` y el entrypoint de la imagen de Odoo lo usa como puerto de la BD.
- **Comando de odoo20**: genera `/tmp/odoo.conf` al arrancar con `admin_passwd` (de la variable `ODOO_ADMIN_PASSWD`), `list_db = False`, `proxy_mode = True` y `http_interface = 0.0.0.0` (Odoo 20 escucha por defecto solo en 127.0.0.1). Después lanza `odoo -d odoo -i contacts --with-demo`; desde Odoo 19 los datos demo no se cargan si no se pide. El `-i contacts` se repite en cada arranque y es inocuo.
- **Build de la API**: Easypanel no despliega imágenes que solo existen en local (intenta hacer `pull`). Por eso el código de `api/` se sube como archivo `.tar.gz` (origen "Upload") y Easypanel lo construye con el `Dockerfile`. Para redesplegar: Easypanel → contactos-api → Origen → Upload → subir `api.tar.gz` → Deploy.
- **Tipos**: para escribir se aceptan `FACTURA`, `ALBARAN` y `CADENA`. Al leer, los contactos de Odoo que no encajan (p. ej. los hijos de Azure Interior, con `type = contact`) se devuelven con el tipo estándar de Odoo (`contact`, `other`).
- **Campos extra**: `telefono` → `phone` y `email` → `email`.
- **Código único**: solo entre contactos **activos**. Así el flujo de n8n se puede repetir (la baja final archiva el T001).
- **NIF**: NIF, NIE o CIF español con letra o dígito de control, prefijo `ES` opcional. Se guarda en mayúsculas, sin espacios ni guiones. Los hijos heredan el NIF de la cadena si no traen uno propio, como hace Odoo.
- **Reglas de CADENA**: una CADENA no puede tener `cadena_id`. `cadena_id` debe ser una empresa activa.
- **Deshacer**: un ALTA deshecho queda archivado (nunca DELETE), una BAJA deshecha se reactiva y una MODIF restaura la foto `antes`. Devuelve 409 si el contacto ha cambiado después del cambio o si ese cambio ya estaba deshecho. Un UNDO no se puede deshacer (400).
- **`create_uid` / `write_uid` = 1 y `company_id` = 1**, como pide el encargo (los contactos demo de Odoo tienen `company_id` vacío).
- **Recalculados por la API**: `complete_name`, `commercial_partner_id`, `commercial_company_name` (también en los hijos al renombrar una cadena), `email_normalized`, `lang`, `write_date` y `write_uid`. **No** se recalculan `phone_sanitized` ni el chatter: el historial está en `api.contactos_log`.
- **Columnas obligatorias de otros módulos**: con Facturación (la instala Ventas) `res_partner.autopost_bills` es obligatoria y el alta la rellena con el valor por defecto de Odoo (`ask`). Sin esto, el alta fallaba en cuanto se instalaba Ventas.

### Tarifas

- **Requisitos en Odoo**: módulo **Ventas** instalado y **Ajustes → Ventas → Tarifas** activado. Sin Ventas (o Productos), los endpoints de tarifas responden 503; con Ventas pero sin activar la opción, funcionan pero avisan (`tarifas_activadas: false`, `aviso`), porque Odoo no aplica tarifas en los pedidos.
- **Tarifa del cliente**: en Odoo 20 es `res_partner.specific_property_product_pricelist`, un jsonb por compañía (`{"1": id}`). Es un campo comercial: vive en la empresa (`commercial_partner_id`) y Odoo lo copia a todas sus direcciones. La API lo lee siempre de la empresa y, al asignar, lo escribe en la empresa y en todas sus direcciones. Al dar de alta una dirección o cambiarle la cadena, le copia la tarifa de la cadena, como Odoo.
- **Tarifa por defecto**: si la empresa no tiene tarifa asignada (o la asignada está archivada), se calcula como Odoo: la primera tarifa activa de la compañía con un grupo de países que incluya el país del cliente, si no la primera sin grupos de países, si no la de los parámetros `res.partner.property_product_pricelist[_1]`, si no la primera. La respuesta indica `origen`: `asignada`, `por_defecto` o `ninguna`.
- **Precios**: `POST /tarifas/{id}/precios` crea o cambia un **precio fijo** para un producto (plantilla) y una cantidad mínima, sin fechas. Si ya hay una regla de ese producto con esa cantidad mínima y sin fechas (sea de precio fijo, descuento o recargo), pasa a precio fijo con el precio nuevo. Repetir el mismo precio da 409. Las reglas de categoría, globales, con fechas o de variante se ven en el contenido, pero la API no las crea.
- **Duplicar**: copia la tarifa **que se aplica** al cliente (la asignada o la por defecto) con todas sus reglas, salvo las de productos archivados (como Odoo), y se la asigna. Nombre por defecto `"<tarifa> - <empresa>"`. La copia no lleva grupos de países y va al final de la secuencia, para que nunca pase a ser la tarifa por defecto de nadie.
- **Crear vacía**: `POST /tarifas` crea una tarifa sin precios (todos los productos van a su precio de venta), en la moneda de la compañía 1, y si se da `contacto_id` se la asigna a su empresa. Como las copias, va sin grupos de países y al final de la secuencia. No deja repetir el nombre de otra tarifa activa (409).
- **Tarifas compartidas**: un precio se pone en la tarifa, no en el cliente, así que afecta a todos los que la usan. Por eso cada tarifa devuelve `clientes_asignados` (empresas que la tienen asignada) y `es_tarifa_por_defecto`. La API no lo impide; el chat IA avisa y propone duplicar antes.
- **Deshacer**: `ASIGNAR` vuelve a la tarifa anterior (o a la por defecto). `CREAR` y `DUPLICAR` vuelven a la anterior (si se asignó a un cliente) y **archivan** la tarifa creada, si ninguna otra empresa la tiene asignada. Un precio puesto se quita, uno cambiado vuelve a su valor y uno quitado se vuelve a crear con el mismo id. Devuelve 409 si la tarifa del cliente o el precio han cambiado después.
- **Historial**: acciones de tarifa `ASIGNAR`, `CREAR` y `DUPLICAR`. Un `CREAR` sin cliente se guarda con `partner_id` vacío. `api.contactos_log` tiene dos columnas nuevas, `entidad` (`contacto`, `tarifa` o `precio`) y `objeto_id` (la tarifa creada o asignada, o la regla de precio). Se añaden solas al arrancar la API. En `tarifa`, `partner_id` es la empresa y `antes`/`despues` llevan `tarifa_id`. En `precio`, `antes`/`despues` llevan la fila completa de la regla.
- **No se hace**: no se borran tarifas (se archivan), no se toca el chatter de Odoo y no se recalculan precios en pedidos ya hechos.

### Albaranes (solo consulta)

- **Requisitos en Odoo**: **Inventario** instalado (con Ventas, Odoo instala también `sale_stock`, que enlaza el albarán con su pedido). Sin él, los endpoints de albaranes responden 503.
- **Qué es cada cosa**: un albarán es un `stock_picking` y sus líneas son los `stock_move`. Las cantidades por lote salen de `stock_move_line`. `cantidad` es la pedida y `cantidad_hecha` la preparada o entregada.
- **Tipos**: `ENTREGA` (salida a cliente), `RECEPCION` (entrada de proveedor) e `INTERNO`, según el tipo de operación. Otros tipos de Odoo salen con su código.
- **Estados**: `BORRADOR`, `ESPERANDO_OTRA_OPERACION`, `ESPERANDO`, `PREPARADO`, `HECHO` y `CANCELADO`. Para filtrar se usa además `PENDIENTE` (ni hecho ni cancelado), y `ESPERANDO` incluye los que esperan otra operación.
- **Contacto**: si es una empresa, incluye los albaranes de todas sus direcciones; si es una dirección, solo los suyos (y los de sus contactos).
- **Fecha del albarán**: la de realización si está hecho, si no la prevista, en UTC. `hasta` incluye ese día.
- **Totales de líneas**: `GET /lineas-albaran` suma por tipo, producto y unidad (las entregas y las recepciones no se mezclan) todas las líneas no canceladas que cumplen el filtro, aunque solo muestre las primeras `limite`.
- Solo de la compañía 1. La API no crea, modifica ni valida albaranes.
- **Parámetros vacíos**: en todos los `GET`, un parámetro vacío (`?tipo=&desde=`) equivale a no enviarlo. Así las herramientas del chat pueden dejar filtros sin rellenar.

## API

FastAPI + psycopg 3. Al arrancar espera a que exista `res_partner` y crea el esquema `api` (tabla `api.contactos_log`). Las consultas son siempre parametrizadas. Los errores salen como `{"error": "..."}` con códigos 400, 404, 409 o 422, nunca con trazas.

| Método y ruta | Función |
|---|---|
| `GET /health` | `{"ok": true}` (503 si la BD no responde) |
| `GET /contactos?q=&incluir_bajas=false` | Busca por NIF, código o nombre (ILIKE, también sobre "Cadena, Contacto"). Máx. 10. Devuelve `total`, `requiere_eleccion` y `resultados` |
| `GET /contactos/{id}` | Ficha (incluye archivados) |
| `POST /contactos` | Alta → 201 con la ficha + `log_id` |
| `PATCH /contactos/{id}` | Modifica solo los campos enviados (`codigo`, `nif`, `nombre`, `tipo`, `cadena_id`, `telefono`, `email`, `activo`) |
| `DELETE /contactos/{id}?sesion=&usuario=` | Baja lógica (`active = false`) |
| `POST /log/{log_id}/undo` | Deshace el cambio. Body opcional `{"sesion","usuario"}` |
| `GET /log?sesion=&limite=50` | Historial, más recientes primero (contactos, tarifas y precios; con `entidad` y `objeto_id`) |
| `GET /contactos/{id}/tarifa` | Tarifa que se aplica al contacto: `origen` (`asignada`, `por_defecto`, `ninguna`), empresa donde vive y datos de la tarifa (`num_precios`, `clientes_asignados`, `es_tarifa_por_defecto`) |
| `PUT /contactos/{id}/tarifa` | Asigna una tarifa existente a la empresa del contacto y a sus direcciones. Body `{"tarifa_id": 3}`; `null` vuelve a la tarifa por defecto |
| `POST /contactos/{id}/tarifa/duplicar` | Duplica la tarifa del cliente con sus precios y le asigna la copia → 201. Body opcional `{"nombre"}` |
| `POST /tarifas` | Crea una tarifa vacía → 201. Body `{"nombre", "contacto_id"}`; con `contacto_id` se la asigna a su empresa |
| `GET /tarifas?q=&incluir_archivadas=false` | Busca tarifas por nombre (vacío = todas, máx. 20) |
| `GET /tarifas/{id}?q=&limite=100` | Contenido: cabecera y precios (producto, código, tipo `PRECIO_FIJO`/`DESCUENTO`/`RECARGO`, precio o %, cantidad mínima, fechas, precio de venta de referencia). `q` filtra por producto, código o categoría |
| `POST /tarifas/{id}/precios` | Pone (201) o cambia (200) el precio fijo de un producto. Body `{"producto_id", "precio", "cantidad_minima": 0}` |
| `DELETE /tarifas/{id}/precios/{precio_id}?sesion=&usuario=` | Quita un precio de la tarifa |
| `GET /albaranes?q=&contacto_id=&producto_id=&tipo=&estado=&desde=&hasta=&limite=20` | Busca albaranes, los más recientes primero (máx. 100): número, tipo, estado, contacto, origen, pedido de venta, fechas, ubicaciones y número de líneas. `q` busca en el número, el origen y el pedido |
| `GET /albaranes/{id}` | Albarán con sus líneas: producto, código, cantidad pedida y hecha, unidad, estado y lotes |
| `GET /lineas-albaran?producto_id=&contacto_id=&tipo=&estado=&desde=&hasta=&limite=50` | Líneas de un producto y/o de un contacto en varios albaranes (hace falta uno de los dos), con su albarán y los totales |
| `GET /productos?q=` | Busca productos por nombre, referencia o código de barras (máx. 10), con su precio de venta |

`POST`, `PUT` y `PATCH` aceptan `sesion` y `usuario` en el body; `DELETE`, en la query. Cada escritura registra su fila de log en la misma transacción y devuelve `log_id`.

### Probar la API

**Desde el servidor** (contenedor efímero en la red interna):

```sh
ssh -p 22022 root@217.154.182.5
docker run --rm -i --network easypanel-ia-support --entrypoint sh curlimages/curl:8.11.1 < pruebas_api.sh   # batería completa
```

**Desde el portátil con túnel SSH.** El host no llega a la red overlay, así que se levanta un reenviador temporal publicado solo en 127.0.0.1 del servidor:

```sh
# 1) en el servidor: reenviador temporal (no expone nada a Internet)
ssh -p 22022 root@217.154.182.5 'docker run -d --rm --name contactos-api-tunel --network easypanel-ia-support \
  -p 127.0.0.1:18000:8000 alpine/socat:1.8.0.1 tcp-listen:8000,fork,reuseaddr tcp:ia-support_contactos-api:8000'
# 2) en el portátil: túnel y pruebas
ssh -p 22022 -N -L 18000:127.0.0.1:18000 root@217.154.182.5 &
A=http://localhost:18000 sh pruebas/pruebas_api.sh      # o abrir http://localhost:18000/docs
# 3) al terminar
ssh -p 22022 root@217.154.182.5 'docker stop contactos-api-tunel'
```

### curl de cada endpoint

```sh
A=http://ia-support_contactos-api:8000      # o http://localhost:18000 con túnel
J='Content-Type: application/json'

curl $A/health
curl "$A/contactos?q=azure"
curl "$A/contactos?q=T001&incluir_bajas=true"
curl $A/contactos/16
curl -X POST $A/contactos -H "$J" -d '{"codigo":"T001","nombre":"Contacto Prueba n8n","tipo":"FACTURA","sesion":"abc123","usuario":"antonio"}'
curl -X POST $A/contactos -H "$J" -d '{"codigo":"T010","nombre":"Tienda Centro","tipo":"ALBARAN","cadena_id":16,"nif":"ESB12345674"}'
curl -X PATCH $A/contactos/45 -H "$J" -d '{"telefono":"600111222","sesion":"abc123"}'
curl -X PATCH $A/contactos/45 -H "$J" -d '{"tipo":"OTRO"}'                # → 422
curl -X DELETE "$A/contactos/45?sesion=abc123&usuario=antonio"
curl -X POST $A/log/2/undo -H "$J" -d '{"sesion":"abc123"}'
curl "$A/log?sesion=abc123"

# Tarifas
curl $A/contactos/16/tarifa
curl "$A/tarifas/3?q=desk"
curl "$A/tarifas?q=mayor"
curl "$A/productos?q=desk%20pad"
curl -X POST $A/contactos/16/tarifa/duplicar -H "$J" -d '{"nombre":"Azure especial","sesion":"abc123"}'
curl -X POST $A/tarifas -H "$J" -d '{"nombre":"Tarifa Azure 2027","contacto_id":16,"sesion":"abc123"}'
curl -X POST $A/tarifas/6/precios -H "$J" -d '{"producto_id":32,"precio":0.99,"sesion":"abc123"}'
curl -X POST $A/tarifas/6/precios -H "$J" -d '{"producto_id":32,"precio":0.89,"cantidad_minima":10}'
curl -X DELETE "$A/tarifas/6/precios/7?sesion=abc123"
curl -X PUT $A/contactos/16/tarifa -H "$J" -d '{"tarifa_id":3,"sesion":"abc123"}'
curl -X PUT $A/contactos/16/tarifa -H "$J" -d '{"tarifa_id":null}'     # vuelve a la tarifa por defecto

# Albaranes
curl "$A/albaranes?contacto_id=16&tipo=ENTREGA&estado=PENDIENTE"
curl "$A/albaranes?q=S00026"
curl $A/albaranes/49
curl "$A/lineas-albaran?producto_id=32&contacto_id=16&tipo=ENTREGA&estado=HECHO&desde=2026-10-01&hasta=2026-10-31"
```

## Flujo de prueba en n8n

Archivo: `n8n/flujo-prueba-contactos.json`, importado en n8n como **"Prueba API contactos"** (https://ia-support-n8n.kw2y1s.easypanel.host/workflow/EJw0EPoA3D3s4QzS). Nodos en cadena (todos HTTP Request sin credenciales y sin nodos comunitarios):

`Manual Trigger → Set (sesion = test-<ms>) → Buscar (GET ?q=azure) → Buscar T001 previo → Archivar T001 previo → Alta (POST T001) → Modificar (PATCH teléfono) → Deshacer (POST /log/{log_id}/undo) → Ver tarifa cliente → Duplicar tarifa → Buscar producto (Desk Pad) → Poner precio (1,50) → Cambiar precio (1,75) → Deshacer precio → Ver contenido tarifa → Deshacer duplicar → Crear tarifa vacía → Deshacer crear tarifa → Baja (DELETE) → Ver log (GET /log?sesion=) → Buscar albaranes (últimas 3 entregas) → Ver albarán (el primero)`

Los pasos de tarifas necesitan Ventas instalado, con los datos demo (el producto *Desk Pad*).

**Limpieza previa**: si una ejecución anterior se quedó a medias (por ejemplo, al lanzar solo el nodo Alta con *Execute step*), queda un T001 activo y el siguiente alta daría 409 por código duplicado. Los nodos "Buscar T001 previo" y "Archivar T001 previo" lo archivan antes del alta. Si no hay ninguno, la API responde 404; el nodo tiene *On Error → Continue*, así que sigue en verde y muestra el 404 en su salida.

**Cómo lanzarlo**: abrir el flujo → **Execute workflow**. Todos los nodos deben quedar en verde; al pulsar cada uno se ve su respuesta. El último ("Ver log") muestra los 11 cambios de la sesión: ALTA, MODIF (revertido) y UNDO del contacto; DUPLICAR de la tarifa (revertido); ALTA y MODIF (revertido) del precio y su UNDO; UNDO de la tarifa; CREAR de la tarifa vacía (revertido) y su UNDO, y BAJA del contacto (más una BAJA previa si la limpieza archivó un T001).

**Qué mirar en Odoo**: Contactos → Filtros → **Archivados** (o quitar el filtro por defecto) → buscar por *Referencia* `T001`.
- Después del flujo, el contacto "Contacto Prueba n8n" aparece **archivado**, sin teléfono (el deshacer lo dejó vacío), y el tipo de dirección es Factura.
- Para ver cada paso por separado, ejecuta los nodos uno a uno ("Execute step") y refresca la ficha en Odoo: tras **Alta** aparece activo, tras **Modificar** muestra el teléfono 600111222, tras **Deshacer** lo pierde y tras **Baja** queda archivado.
- **Tarifa**: ejecutando hasta **Ver contenido tarifa**, en Ventas → Productos → Tarifas aparece *"Default - Contacto Prueba n8n"* con el Desk Pad a 1,50, y la ficha del contacto (pestaña Ventas y compras) la tiene asignada. Tras **Deshacer duplicar**, el contacto vuelve a la tarifa por defecto y la copia queda archivada (filtro *Archivadas* en Tarifas).
- Cada ejecución crea un T001 nuevo, porque el anterior ya está archivado. Para ver los pasos uno a uno, lanza también antes los dos nodos de limpieza.

## Chat IA (lenguaje natural)

Archivo: `n8n/chat-ia-contactos.json`, importado en n8n como **"Chat IA contactos"** (https://ia-support-n8n.kw2y1s.easypanel.host/workflow/op8niOnmjKQMQ3Nr).

```
Chat (Chat Trigger) → Agente contactos (AI Agent)
                        ├─ OpenRouter (anthropic/claude-haiku-5.5, temperatura 0,1; credencial "OpenRouter account")
                        ├─ Memoria (Simple Memory, últimos 20 mensajes por conversación)
                        └─ Herramientas HTTP → contactos-api:
                           buscar_contactos · ficha_contacto · alta_contacto · modificar_contacto
                           baja_contacto · deshacer_cambio · historial_sesion
                           tarifa_cliente · contenido_tarifa · buscar_tarifas · buscar_productos
                           crear_tarifa · duplicar_tarifa · asignar_tarifa · poner_precio · quitar_precio
                           buscar_albaranes · ficha_albaran · lineas_albaran
```

- **Cómo usarlo**: abre el flujo y usa el panel **Chat** de abajo, o entra en la URL del chat: https://ia-support-n8n.kw2y1s.easypanel.host/webhook/81c5b9ef-bcae-409c-b294-be99feab1920/chat (publicado el 16/10/2026). Esa URL exige iniciar sesión en n8n (*n8n User Auth*), porque el asistente escribe en el ERP.
- **Tras reimportar**: `n8n import:workflow` deja el flujo despublicado. Hay que volver a publicarlo (botón **Publish**, o `n8n publish:workflow --id=op8niOnmjKQMQ3Nr` y reiniciar el servicio `ia-support_n8n`, porque la CLI no avisa al n8n en marcha). El reinicio corta unos segundos los flujos de Helpdesk.
- **Sesión**: el `sessionId` del chat se manda como `sesion` a la API. Cada conversación tiene su propio historial en `api.contactos_log` (con `usuario = chat`), y "deshaz lo último" solo afecta a esa conversación.
- **Tarifas**: se le puede preguntar "¿qué tarifa tiene Azure?", "¿a cuánto tiene el Desk Pad?", "ponle el Desk Pad a 1,50 a partir de 10 unidades", "hazle una tarifa propia", "crea una tarifa vacía Ferias 2027 para Azure" o "ponle la tarifa Mayoristas". Si no está claro si quiere una tarifa vacía o una copia de la que tiene, lo pregunta. Antes de cambiar precios mira si la tarifa es la por defecto o la usan otros clientes; si es así lo avisa y propone duplicarla primero. Al confirmar recuerda que la tarifa es de toda la cadena.
- **Albaranes**: solo consulta. "¿Qué albaranes tiene pendientes Azure?", "enséñame el último albarán de Gemini", "¿cuánto Desk Pad le hemos entregado a Azure este mes?". "Albarán" sin más se entiende como entrega a cliente. Las instrucciones del agente son una expresión de n8n que incluye la fecha de hoy (`$now`), para que pueda convertir "este mes" o "la semana pasada" en fechas.
- **Reglas del agente** (en las instrucciones del nodo): siempre busca antes de actuar. Si hay varios candidatos, da una lista numerada y deja elegir. **Pide confirmación explícita antes de cada escritura (contactos, tarifas, precios o deshacer)**, y una confirmación vale para una sola operación. Explica los errores de la API en lenguaje natural. No inventa ids. Fuera de contactos, tarifas y consulta de albaranes no actúa. Iteraciones máximas del agente: 15 (las preguntas de tarifas encadenan más herramientas).
- **Modelo**: se cambia en el nodo OpenRouter. Haiku 5.5 cuesta unos 0,10 $ por millón de tokens de entrada y 0,50 $ de salida; cada mensaje consume entre 6.000 y 9.000 tokens.
- **Memoria**: la Simple Memory vive en el proceso de n8n y se pierde si n8n se reinicia. Para que sea persistente habría que usar *Postgres Chat Memory* con su propia BD.

Conversación de prueba real de contactos (15/10/2026), con todos los pasos verificados en la BD (las tarifas se añadieron después):

| Usuario | Asistente |
|---|---|
| busca Azure | Lista numerada de 4 contactos y pide elegir |
| Da de alta una dirección de entrega llamada Tienda Azure Murcia, código ALB-AZ01, teléfono 968111222, dentro de la cadena Azure Interior | Resume (ALBARAN en la cadena Azure Interior) y pide confirmación; no escribe hasta el "sí" |
| sí | Crea el id 54 "Azure Interior, Tienda Azure Murcia" con el NIF heredado de la cadena |
| cámbiale el teléfono a 600999888 → adelante | Teléfono cambiado |
| deshaz lo último → sí | Teléfono restaurado a 968111222 |
| ponle el NIF 12345678A | Avisa de que la letra no es válida (sería Z) y ofrece opciones; un "sí" ambiguo no lo toma como confirmación |
| la 2 → sí, confirmo | La API lo rechaza (422) y lo explica sin cambiar nada |
| cambia su código a TC01 → sí | La API devuelve 409: "TC01 ya lo usa otro contacto"; no cambia nada |
| da de baja esa tienda → sí / deshaz la baja → sí | La archiva y luego la reactiva |
| ¿cuántos pedidos tiene Azure este mes? | Responde que en esta fase solo gestiona contactos |

Prueba de albaranes y tarifas en el servidor (16/10/2026), con un flujo temporal que pasa las preguntas al mismo agente (ya borrado):

| Usuario | Asistente |
|---|---|
| ¿Qué entregas tiene pendientes Azure Interior? | Lista numerada de los 5 contactos Azure y propone la empresa (id 16) para incluir todas sus direcciones |
| De la primera de esas entregas, dime qué productos lleva | No hay albaranes de Azure en ningún estado (correcto: en los datos demo no tiene) y ofrece mirar otras direcciones |
| ¿Cuántas unidades del producto más entregado hemos entregado este año? | Busca entregas hechas en 2026 (no hay ninguna en demo), explica que `lineas_albaran` necesita un producto o un cliente y pide uno |
| ¿Qué tarifa tiene Azure Interior y qué precio tiene algún producto? | Tarifa VIP (USD), solo de este cliente: Acoustic Bloc Screens a 150 USD frente a 295 |

## Operación

```sh
ssh -p 22022 root@217.154.182.5        # o ~/sshn8n (abre además el túnel de Easypanel en :3000)

docker service ls --filter name=ia-support_                       # estado
docker service logs -f --tail 100 ia-support_contactos-api        # logs de la API
docker service logs -f --tail 100 ia-support_odoo20               # logs de Odoo
docker service logs -f --tail 100 ia-support_surtidos-db          # logs de Postgres
docker exec -it $(docker ps -q -f name=ia-support_surtidos-db) psql -U odoo -d odoo   # consola SQL
#   select * from api.contactos_log order by id desc limit 20;
```

Los logs también están en Easypanel → ia-support → servicio → Logs.

### Backup

Backup puntual hecho antes de la entrega: `/root/backups/surtidos-odoo-20261015-1504.dump` (2 MB, formato custom de pg_dump). Para repetirlo:

```sh
mkdir -p /root/backups
docker exec $(docker ps -q -f name=ia-support_surtidos-db) pg_dump -U odoo -Fc odoo > /root/backups/surtidos-odoo-$(date +%Y%m%d-%H%M).dump
# restaurar en una BD vacía: pg_restore -U odoo -d <bd> --no-owner fichero.dump
```

El filestore de Odoo está en el volumen `odoo20-data` (`/var/lib/odoo`). Con solo Contactos apenas tiene contenido.

## Activar las tarifas en el servidor

**Hecho el 15/10/2026**, con backup previo en `/root/backups/surtidos-odoo-20261015-1557-pre-tarifas.dump`. Al instalar Ventas con demo, Odoo registró un error al cargar los datos demo de contabilidad de la segunda compañía (*My US Company*, sin plan contable); los módulos quedaron instalados y el siguiente arranque carga sin errores. El Odoo en marcha recargó los módulos solo, sin reiniciarlo. La API se redesplegó copiando `main.py` a `/etc/easypanel/projects/ia-support/contactos-api/code/`, con `docker build -t easypanel/ia-support/contactos-api:latest` sobre esa carpeta y `docker service update --force ia-support_contactos-api` (un *Deploy* desde Easypanel usa la misma carpeta). Los flujos se importaron con `n8n import:workflow` sobre sus mismos ids, conservando la credencial de OpenRouter.

**Albaranes (16/10/2026)**: backup en `/root/backups/surtidos-odoo-20261016-0955-pre-inventario.dump`, instalados `stock` y `sale_stock` con datos demo (sin errores, 48 albaranes demo) con `odoo -i stock,sale_stock --stop-after-init` dentro del contenedor de odoo20. El servidor en marcha recargó los módulos solo. API y flujos redesplegados igual que antes.

La v1.1 de la API (tarifas) necesita, una sola vez:

1. **Backup** de la BD (ver arriba).
2. **Instalar Ventas** en `odoo20`: Aplicaciones → *Ventas* → Activar (o añadir `sale` al `-i contacts` del comando del servicio). Con los datos demo de la BD trae productos como *Desk Pad*.
3. **Activar las tarifas**: Ajustes → Ventas → *Tarifas* → Guardar. Odoo crea la tarifa *Default* de la compañía.
4. **Redesplegar la API**: subir el nuevo `api.tar.gz` (Easypanel → contactos-api → Origen → Upload → Deploy). Al arrancar añade las columnas `entidad` y `objeto_id` a `api.contactos_log`.
5. **Reimportar los flujos** de `n8n/` sobre los existentes (o pegar los nodos nuevos) y volver a elegir la credencial *OpenRouter account* en el nodo OpenRouter del chat. Después, publicar el chat (ver *Tras reimportar*).
6. Lanzar `pruebas_api.sh` y el flujo **"Prueba API contactos"**.

## Estructura

```
api/            Código de la API (main.py, nif.py, Dockerfile, requirements.txt)
n8n/            flujo-prueba-contactos.json · chat-ia-contactos.json (agente IA)
pruebas/        pruebas_api.sh (batería curl de punta a punta: contactos, tarifas y albaranes)
```
