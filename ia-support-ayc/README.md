# ia-support · Clientes AYC (n8n + API del ERP de AYC)

Chat con IA, hecho en n8n, para consultar los clientes del ERP de AYC y sus precios especiales, descuentos y surtido,
y para **dar de alta o modificar** líneas de esas tablas, siempre con confirmación. No borra nada.

## Cómo funciona (para usuarios)

### Qué se le puede preguntar

Se escribe en lenguaje normal, por ejemplo:

- "Busca Ñam Ñam", "B30682488", "el cliente 4300016289" o "clientes de Cartagena".
- "¿Qué precios especiales tiene el 4300016289?" o "¿Qué descuento tiene UPPER en las madalenas?"
- "¿Qué surtido tiene el 4300016289?", "¿Puedo venderle Poker de vainilla?" o "Muéstrame el surtido 390".

El chat recuerda la conversación: si muestra una lista, basta con contestar "el segundo".

### Clientes

- Se puede buscar por **parte del nombre, CIF o código**. Si hay varios, el chat los enumera y pide elegir uno; con
  uno solo, muestra su ficha.
- Un mismo CIF puede tener **varios códigos de cliente**, uno por tienda o dirección. Son clientes distintos.
- En la ficha aparecen, cuando existen:
  - **Cadena:** el grupo al que pertenece la tienda (p. ej. GRUPO UPPER).
  - **Factura a:** el cliente al que se le factura, si no es él mismo (p. ej. las tiendas +BK facturan a VICKY FOODS).
- Si hay muchos resultados, muestra los 10 primeros y propone afinar la búsqueda.

### Precios especiales y descuentos

- Cada cliente tiene asignada **una tabla de precios especiales y otra de descuentos**.
- Las tablas **se comparten**: el chat dice cuántos clientes tienen la misma. Cambiar una tabla afecta a todos ellos.
- Cada línea es un artículo con su precio (€) o su descuento (%), y las fechas desde y hasta.
- La tabla **999** significa "sin precios especiales" o "sin descuentos".
- Las líneas que **todavía no han empezado** aparecen como "a partir del dd/mm/aaaa".
- Un mismo artículo puede salir dos veces si tiene dos periodos distintos.

### Surtido

El surtido es la **lista cerrada** de lo que se le puede vender a un cliente: lo que no está en el surtido no se le
puede vender.

- **Asignación:** cada cliente tiene un surtido, que también se comparte entre clientes, igual que las tablas de
  precios.
- **Sin surtido asignado:** un cliente con la tabla 999, o sin tabla, no tiene surtido. Eso **no** significa que
  pueda comprar de todo.
- **Tipos de línea:**
  - **Artículo suelto:** ese artículo concreto.
  - **Marca completa:** todos los artículos de la marca (p. ej. DULCESOL).
  - **Grupo de una marca:** todos los artículos de ese grupo (p. ej. "GR ENVUELTO DSOL 1" de DULCESOL). El chat no
    sabe qué artículos hay dentro de una marca o un grupo; si se pregunta por uno que no está suelto, avisa de que
    puede entrar por el grupo pero no lo puede comprobar.
  - **Avisos:** marcas especiales del ERP, como "CLIENTE SOLO ENDOSOS", "FIN DE SERVICIO" o "SOLO ARTÍCULOS
    AUTORIZADOS".
- **Quién hace el endoso (cliente factura).** Cuando el comercial visita la tienda, decide quién hace la venta: AYC,
  Vicky Foods u otro subdistribuidor. Cada línea del surtido es de un **cliente factura**:
  - **Genérico (0000000001):** la línea vale sea quien sea el que factura.
  - **Un cliente factura concreto** (p. ej. VICKY FOODS, 4400000173): la línea solo vale cuando el endoso lo hace él.
    Vicky Foods tiene en los surtidos las marcas Dulcesol, Hermanos Juan, BePlus y Burger King.

  El chat muestra el surtido **en un apartado por cada cliente factura**. A "¿puedo venderle X?" contesta, por
  ejemplo, "Sí, pero solo cuando el endoso lo hace Vicky Foods".

  Este cliente factura **no es** el "Factura a" de la ficha del cliente.
- **Surtido de un cliente factura:** Vicky Foods no tiene surtido propio; sus líneas están dentro de los surtidos de
  los clientes. Si se pregunta por él, el chat pide el número de surtido y muestra solo sus líneas.
- **Surtidos grandes:** muestra los primeros 60 artículos y un resumen por marca, y propone filtrar por marca,
  artículo o cliente factura.

### Dar de alta o modificar (desde el 11/11/2026)

Por ejemplo: "Cambia el precio especial del artículo 129 del cliente 4300016289 a 1,35", "Pon el descuento del 0777 de la
tabla 14 al 15 %" o "Añade el artículo 9505 al surtido 242".

1. **Vista previa.** El chat busca la tabla del cliente y enseña lo que va a cambiar: alta o modificación, artículo,
   valor anterior y nuevo, y fechas. Si la tabla la comparten otros clientes, avisa de cuántos son, porque el cambio
   les afecta a todos.
2. **Confirmación.** No se guarda nada hasta que contestas "sí". Aunque le digas que lo guarde directamente, siempre
   pide la confirmación.
3. **Resultado.** Dice lo que ha quedado guardado, o el motivo por el que el ERP no lo ha aceptado. Cada cambio queda
   apuntado en el registro "Cambios ERP AYC", una Data Table de n8n.

Reglas:

- **Números:** los precios y descuentos se escriben con coma (1,25 o 6,5 %). Si un número es ambiguo, como "1.250",
  el chat pregunta.
- **Fechas:**
  - un alta empieza hoy y no tiene fecha de fin, salvo que se indique otra cosa;
  - al modificar una línea, se mantienen sus fechas;
  - no puede haber dos líneas del mismo artículo con fechas que se solapen;
  - para cambiar el precio a partir de una fecha hacen falta dos pasos: cerrar la línea actual el día anterior y dar
    de alta la nueva.
- **Surtido:** hay que decir si la línea es genérica o de un cliente factura concreto, como Vicky Foods. Si ya está
  claro, el chat lo deduce: por la línea que ya existe, por el cliente factura consultado o por la marca.
- **Tablas 999 y 998:** son las de "sin precios especiales", "sin descuentos" o "sin surtido" y las comparten miles
  de clientes. No se tocan.
- **Borrar:** no se borran líneas. Una línea se puede cerrar poniéndole fecha de fin.
- **Líneas creadas por el ERP:** de momento no se pueden modificar desde el chat; falta publicar un arreglo de la
  API. Las altas sí funcionan.

### Lo que todavía no hace

- **Consultar pedidos, facturas, albaranes o stock.**

## Descripción técnica

```
Chat (n8n) → Agente clientes ─┬ consultar_clientes ───────────┐
                              ├ consultar_precios_especiales ─┤
                              ├ consultar_descuentos ─────────┼→ Consulta (subflujo del mismo flujo, campo accion)
                              └ consultar_surtido ────────────┘    │
   clientes:                    API clientes → Normalizar          ├ GET …/api/clientes/consultarClientes
   preciosEspeciales/descuentos/surtidos:                          ├ GET …/api/{preciosEspeciales|descuentos|surtidos}/consultar
     API tabla → Tabla → API productos → ¿Surtido? →               └ GET …/api/{preciosEspeciales|descuentos|surtidos}/listarProductos
       Normalizar condiciones | Normalizar surtido
```

- **API:** `http://88.27.249.204:50880/api/…` (AcisaAPI, entorno de pruebas), con la cabecera `X-api-key` (credencial
  de n8n `AycApiKeyHeader1`) y `subEmpresa=AYC`. Hay dos tipos de llamada:
  - `clientes/consultarClientes?dato=` busca clientes. Distingue mayúsculas, así que el flujo envía el dato en mayúsculas.
  - `{preciosEspeciales|descuentos|surtidos}/consultar?codigoCliente=` devuelve la tabla asignada
    `{codigoTabla, descripcion, numeroClientes}`, y `…/listarProductos?codigoTabla=` devuelve sus líneas, sin las
    caducadas pero con las futuras.
- **Líneas de surtido:** traen `codigoMarca`, `codigoGrupo`, `codigoArticulo` y `clienteFactura`.
  - El tipo de línea se deduce de los campos rellenos: un artículo numérico es un artículo suelto; sin artículo, con
    marca y sin grupo, es una marca completa; con marca y grupo, es un grupo; un código no numérico es un aviso.
  - En `clienteFactura`, `0000000001` es el genérico.
- **Flujo:** `n8n/chat-ia-clientes-ayc.json` (id `ChatIaClienAYC01`). Se genera con `python3 n8n/build_workflow.py`,
  que copia en los nodos Code el contenido de `n8n/*.js`, siempre con `comun.js` delante:
  - `comun.js`: funciones comunes (`t`, `sp`, `iso`, `fallo`, `leerApi` para leer la respuesta de la API y sus
    errores, `buscador` para filtrar por palabras), las acciones (`TIPOS`) y los nombres de los clientes factura
    (`NOMBRES_CF`). Lo que se define aquí no se puede volver a declarar en los otros `.js`.
  - `normalizar.js`: deja como mucho 10 clientes y quita los espacios de relleno.
  - `tabla.js`: elige la tabla (la que da el usuario o la que devuelve `consultar`) y traduce los errores 404/400.
    Lo usan tanto las consultas como las altas y modificaciones.
  - `normalizar_condiciones.js`: precios y descuentos.
    - Separa las líneas de artículo (hasta 60, con el filtro `articulo`, que busca también en la marca y el grupo) de
      las de marca (`marcas`), grupo (`grupos`), familia (`familias`) y las generales, sin marca ni artículo
      (`generales`). Estas cuatro van siempre completas.
    - Las tablas 998 y 999 (clientes sin precios o descuentos) se devuelven vacías: la 998 de descuentos trae una
      línea general al 0 %.
  - `normalizar_surtido.js`: surtido.
    - Separa avisos, marcas, grupos y artículos y agrupa por cliente factura (`clientes_factura`).
    - Con la entrada `cliente_factura`, filtra las líneas de ese cliente factura.
    - Con `articulo`, filtra los artículos y devuelve hasta 60. Si no hay coincidencia exacta, devuelve hasta 10
      `parecidos`.
    - Los nombres de los clientes factura están en `NOMBRES_CF` (`comun.js`), porque la API no los da.
  - `numero_es.js` (`aNumero`): convierte "1,25", "1.250,50 €" o "6,5 %" en un número con punto. Es para las futuras
    peticiones de actualizar: la API guarda `"1,25"` como 125.
- **Herramientas:** las cuatro llaman al mismo flujo por la entrada *Consulta*, porque n8n solo admite un *Execute
  Workflow Trigger* por flujo. Las entradas son `accion`, `dato`, `codigo_cliente`, `codigo_tabla`, `articulo` y
  `cliente_factura`. Así la respuesta de la API se recorta antes de llegar al modelo; la de clientes puede pasar de 1 MB.
- **Agente:** usa OpenRouter `anthropic/claude-haiku-5.5` con temperatura 0,1 y una memoria de 20 mensajes. Las reglas
  de negocio están en `SYSTEM` (`build_workflow.py`).
- **Chat:** público, con Basic Auth (credencial `AlbIaBasicAuth01`, usuario `revision`), en
  `https://ia-support-n8n.kw2y1s.easypanel.host/webhook/6d2b7e41-58c3-4f0a-a9e2-4b1d9c0e7a31/chat`. No hay que usar
  `/signin?redirect=…`, que es el login de n8n. Si el navegador manda al login, abrir el chat en una ventana privada.
- **Detalles de la API que explican cómo está hecho el flujo:**
  - Los campos vienen con espacios de relleno.
  - Hay errores 500 intermitentes; los nodos HTTP de consulta hacen 2 intentos con 0,3 s entre ellos y 15 s de
    tiempo máximo. n8n repite también los 404, por eso se usan pocos intentos y poca espera (con 3 intentos y 1 s, un
    404 tardaba 2,6 s; ahora ~0,7 s). No se usa *Never Error*: con él tampoco se reintentarían los 500.
  - La respuesta se lee como texto para que un array vacío no corte el subflujo.
  - Muchas peticiones en paralelo hacen caer la API: hay que usar *Batching* de 1.
  - Hay más detalle en el anexo.
- **Altas y modificaciones:** herramientas `actualizar_precio_especial`, `actualizar_descuento` y `actualizar_surtido`
  (`accion=actualizar…`). Rama del subflujo:
  (`API tabla`) → `Tabla` → `¿Actualizar?` → `Preparar actualización` → `API líneas act` → `Plan actualización` →
  `¿Ejecutar?` → `API actualizar` → `Resultado actualización` → `Tabla registro` → `Registro` → `Respuesta actualización`.
  - **`preparar_actualizacion.js`**, que lleva delante `numero_es.js` (la tabla ya la ha decidido `Tabla`):
    - valida el producto, el valor (con `aNumero`), las fechas y el cliente factura;
    - toma la tabla del cliente o la indicada;
    - bloquea las tablas 999 y 998.
  - **`plan_actualizacion.js`:**
    - con las líneas actuales del producto, decide entre alta, modificación o sin cambios, y avisa de los solapes;
    - en surtidos elige el cliente factura: el de la línea existente, el indicado o el de la marca; si no lo sabe,
      pregunta;
    - devuelve una vista previa con `codigo_confirmacion`, un hash del cuerpo del POST. Solo ejecuta si recibe ese
      mismo código, así que el agente no puede saltarse la vista previa.
  - **`API actualizar`:** POST sin reintentos.
  - **Registro de cambios:** Data Table **"Cambios ERP AYC"**. El nodo `Tabla registro` la crea la primera vez, y en
    cada cambio se apuntan la fecha, el usuario (`revision`), la tabla, el producto, la operación, los valores, las
    fechas, el resultado y la petición. Si el registro falla, el cambio ya está hecho y se avisa. El módulo Data
    Table está desactivado en `n8n execute`, así que el registro solo funciona desde el chat real.
  - **El nodo `Sin ejecutar`** recoge la vista previa, las preguntas y los errores. El subflujo devuelve la salida
    del último nodo, y la rama "false" de un If no devolvería nada.

## Instalarlo en n8n

El flujo tiene id fijo `ChatIaClienAYC01` y ya apunta a las credenciales `API AYC (X-api-key)` (id `AycApiKeyHeader1`),
*OpenRouter account* (id `BAhp65TskxSwWt7J`, la del chat de contactos) y *Albaranes IA - Basic Auth*
(id `AlbIaBasicAuth01`, usuario `revision`) para entrar al chat publicado.

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

## Actualizar el flujo instalado

Servidor: `ssh -p 22022 root@217.154.182.5` (Easypanel, proyecto `ia-support`; contenedores `ia-support_n8n.1…` y
`ia-support_n8n-db.1…`). Pasos para subir una versión nueva:

```sh
python3 n8n/build_workflow.py                       # regenerar el JSON tras tocar el .py o los .js
ssh -p 22022 root@217.154.182.5 'C=$(docker ps -q -f name=ia-support_n8n.1); \
  docker exec $C n8n export:workflow --id=ChatIaClienAYC01 --output=/tmp/bk.json && \
  docker cp $C:/tmp/bk.json /root/backups/ChatIaClienAYC01_$(date +%Y%m%d_%H%M).json'      # copia antes
scp -P 22022 n8n/chat-ia-clientes-ayc.json root@217.154.182.5:/tmp/
ssh -p 22022 root@217.154.182.5 'C=$(docker ps -q -f name=ia-support_n8n.1); \
  docker cp /tmp/chat-ia-clientes-ayc.json $C:/tmp/w.json && docker exec $C n8n import:workflow --input=/tmp/w.json && \
  docker exec $C n8n publish:workflow --id=ChatIaClienAYC01 && docker exec -u root $C rm -f /tmp/w.json /tmp/bk.json'
```

`import:workflow` despublica el flujo y `publish:workflow` lo vuelve a publicar en la BD, así que las herramientas
(subflujo) funcionan al momento. **La URL del chat** no se registra hasta despublicar y volver a publicar desde la
interfaz, o reiniciar n8n.

## Probar con flujos temporales

La clave de la API está solo en la credencial de n8n (no en el repo ni en el portátil), así que las pruebas se hacen
en el servidor con un flujo temporal (`TmpSurtidoAYC01`) que se crea a partir de `n8n/chat-ia-clientes-ayc.json` y se
lanza con `n8n execute`. No toca el flujo publicado:

```sh
# Subflujo (sin modelo): Consulta pasa a ser un Code con estas entradas; las que faltan van vacías.
sh pruebas/n8n_tmp.sh subflujo '{"accion":"surtidos","codigo_cliente":"4300016289","articulo":"poker"}'
sh pruebas/n8n_tmp.sh subflujo '{"accion":"clientes","dato":"B30682488"}'
# Agente: un mensaje por ejecución (sin memoria entre una y otra). Sus herramientas llaman al flujo PUBLICADO,
# así que primero hay que instalar la versión a probar.
sh pruebas/n8n_tmp.sh agente '¿Puedo venderle Poker de vainilla al 4300016289?'
# Al terminar: borra el flujo temporal y sus ejecuciones de la BD de n8n (psql en ia-support_n8n-db).
sh pruebas/n8n_tmp.sh limpiar
```

(`pruebas/flujo_tmp.py` genera el flujo temporal y `pruebas/resultado_tmp.py` resume la ejecución: herramientas
llamadas y salida del último nodo.)

Cuidados:

- **Un caso cada vez.** Un nodo HTTP con muchos items lanza todas las peticiones en paralelo: al recorrer 300 tablas,
  la API de AYC empezó a dar timeout desde la 138. Si hace falta recorrer muchas, activar *Batching* (1 petición cada vez).
- `n8n execute` necesita `N8N_RUNNERS_MODE=internal` y `N8N_RUNNERS_BROKER_PORT=5699` (el script los pone): sin ellas
  choca con el broker de tareas del n8n en marcha.
- Para ver la respuesta cruda de un endpoint nuevo, lo más rápido es un flujo temporal *Manual → HTTP Request*
  (credencial `AycApiKeyHeader1`, respuesta como texto, `onError: continueRegularOutput`) → *Code* que resuma claves
  y tamaños, con el mismo `TMP_ID` para que `limpiar` lo borre.

## Añadir otra API (receta)

Lo que se hizo con precios especiales, descuentos y surtidos:

1. Ver la respuesta real (flujo temporal, apartado anterior): forma de `consultar` y de `listarProductos`, mensajes de
   404/400, tamaños y campos con relleno o raros. Apuntarlo en el *Anexo A*.
2. Si sigue el patrón *consultar por cliente → tabla → listarProductos*, basta con: añadir la `accion` (= nombre en la
   URL, `/api/<accion>/…`) a *¿Condiciones?*, darle nombre en `que` (`n8n/tabla.js`), crear la herramienta con
   `herramienta_condiciones(...)` y su conexión `ai_tool`. Si las líneas tienen otra forma, un Code propio detrás de
   *API productos* (como *¿Surtido?* → *Normalizar surtido*).
3. Explicar en `SYSTEM` (`build_workflow.py`) el concepto y cómo mostrarlo; regenerar.
4. Probar el subflujo con `subflujo` (casos buenos, vacíos, 404, sin datos), instalar y probar el agente con `agente`;
   apuntar los resultados en el *Anexo C*.

## Pendiente

- Marcas y grupos: la API no dice qué artículos hay dentro. Para contestar con seguridad "¿puedo venderle X?" haría
  falta una API de artículos o que `listarProductos` expanda las líneas.
- Confirmar con AYC qué significan exactamente `SOLOENDOSO`, `FINDESERVI` y `CSACLIENTE` para la venta.
- Afinar el texto del agente: a veces dice "No tiene avisos" aunque las instrucciones le piden no mencionarlo.
- Surtidos grandes: valorar subir `LIMITE` en `normalizar_surtido.js` si se usa mucho para listar completo.

## Pruebas de la API

Directas contra la API, desde una máquina que tenga la clave (no está en el repositorio):

```sh
AYC_KEY=<clave> sh pruebas/pruebas_api.sh
```

Sin la clave, usar `pruebas/n8n_tmp.sh` (ver *Probar con flujos temporales*).

## Anexo A. Detalle de la API (hallazgos)


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

### Precios especiales y descuentos (29/10/2026)

Las dos APIs funcionan igual (misma cabecera y `subEmpresa=AYC`):

- `GET /api/{preciosEspeciales|descuentos}/consultar?codigoCliente=…` → la tabla asignada al cliente:
  `{codigoTabla, descripcion, numeroClientes}` (un objeto, no un array). Las tablas se comparten:
  `4300016289` (UPPER) → precios 14 `04PES UPPER-TIENDAS` y descuentos 14 `04CDP CAD 14 UPPER TIENDAS`, 216 clientes.
  La mayoría (~34.300) tienen la 999 `PES/CDP CLIENTE BLOQUEADO`, que está vacía: es "sin precios especiales/descuentos".
  Cliente inexistente: 404 `No hay datos comerciales (CLP) para el cliente y subempresa indicados.`;
  sin código: 400 `El parámetro 'codigoCliente' es obligatorio.`
- `GET /api/{preciosEspeciales|descuentos}/listarProductos?codigoTabla=…` → array de
  `{codigoArticulo, descripcion, precio|descuento, fechaDesde, fechaFin}` (fechas `dd/mm/aaaa`, código y descripción
  con relleno). Tabla inexistente (p. ej. la 12 del ejemplo): 404 `No se encontró la tarifa de precios / la tabla de
  descuentos con código 12.` Las tablas son pequeñas (máximo visto, 46 líneas en las tablas 1–60).
  No devuelve líneas caducadas pero **sí futuras** (descuentos 2: las 20 empiezan el 01/11/2026), y el mismo artículo
  puede venir dos veces con periodos distintos (precios 14, artículo 0290: desde 01/02/2024 y desde 29/10/2026).

### Surtidos (03/11/2026)

Un surtido es la lista **cerrada** de lo que se puede vender a un cliente: no se puede vender nada fuera de ella.
En el ERP las líneas se definen por producto, por marca (todos sus productos) o por marca-grupo. Hasta el 09/11/2026
la API solo devolvía `{codigoArticulo, descripcion, fechaDesde, fechaFin}` (las 14 tablas entre la 1 y la 137, 655
líneas); ahora devuelve también las líneas de marca y de grupo (ver abajo).

- `GET /api/surtidos/consultar?codigoCliente=…` → `{codigoTabla, descripcion, numeroClientes}`, como precios y
  descuentos: `4300016289` (UPPER) → 242 `UPPER CADENA 14 EDI`, 186 clientes. Los clientes con la 999 (p. ej.
  `4300017472`) dan 404 `No se encontró la tabla de surtido con código 999.`: **sin surtido asignado**. Cliente
  inexistente: 404 `No hay datos comerciales (CLP)…`.
- `GET /api/surtidos/listarProductos?codigoTabla=…` → array de artículos. Las tablas son más grandes que las de precios
  (242: 246 artículos, 34 KB; 1: 188; 105 y 106: 165). Tabla inexistente: 404 `No se encontró la tabla de surtido con código 12.`
- `fechaFin` casi siempre `31/12/2500` (sin fin) y falta en 3 líneas.
- Algunas líneas no son artículos, sino marcas del ERP: `SOLOENDOSO` *CLIENTE SOLO ENDOSOS*, `FINDESERVI` *FIN DE
  SERVICIO*, `CSACLIENTE` *CSA CLIENTE SOLO ART.AUTORIZADOS*. *Normalizar surtido* las devuelve aparte, en `avisos`.
- **Ampliada el 09/11/2026 con marcas y grupos.** Cada línea trae ahora además `codigoMarca`, `descripcionMarca`,
  `codigoGrupo`, `descripcionGrupo` (las descripciones faltan si su código va vacío). Hay cuatro clases de línea
  (recorrido de las tablas 1–140 y la 242):

  | Línea | Cómo se reconoce | Vistas |
  |---|---|---|
  | Artículo | `codigoArticulo` numérico; marca y grupo son los del artículo | 641 (+246 en la 242) |
  | Marca completa | sin artículo, con marca y sin grupo (sin `descripcion`) | 1: tabla 100, DULCESOL |
  | Grupo de una marca | sin artículo, con marca y grupo (sin `descripcion`) | 100, 126 y 242: DULCESOL GRANEA *GR ENVUELTO DSOL 1* y GRANEB *GR ENVUELTO DSOL 2* |
  | Marca del ERP | código no numérico, sin marca ni grupo | 14 (SOLOENDOSO, FINDESERVI, CSACLIENTE) |

  La API **no expande** las marcas ni los grupos en artículos: no se puede saber qué artículos entran por ellos.
  Antes de este cambio esas líneas no venían (la 242 tenía 246 líneas y ahora 248).
- **Cliente factura de cada línea (11/11/2026).** Cada línea trae `clienteFactura`: el subdistribuidor que hace el
  endoso, es decir, quien factura la venta. No es el "Factura a" de la ficha del cliente.
  - `0000000001` es el **genérico**: vale sea quien sea el que factura. No existe como cliente.
  - `4400000173` es VICKY FOODS PRODUCTS SLU: Dulcesol, Hermanos Juan, BePlus y BKING. Tiene líneas en las
    tablas 10, 100, 105, 106, 242 y 390.
  - `codigoCliente` va siempre vacío.
  - Un cliente factura no tiene surtido propio: `surtidos/consultar` con su código da 404, "El cliente no tiene
    tabla de surtido asignada".
  - *Normalizar surtido* agrupa por cliente factura (`clientes_factura`, y `cliente_factura` en cada marca, grupo
    y producto). Con la entrada `cliente_factura` solo devuelve las líneas de ese cliente factura.
  - El nombre sale de `NOMBRES_CF`, en `normalizar_surtido.js`, porque la API no lo da. Si aparece otro cliente
    factura, se muestra por su código; hay que añadirlo a ese mapa.
  - Al consultar el surtido de un cliente factura, el agente pide el número de tabla.
  - **Para las altas y modificaciones, cuando se hagan las herramientas de actualizar:** n8n enviará siempre
    `clienteFactura`.
    - Si el producto ya está en la tabla, el de su línea.
    - Si es un alta, el de las otras líneas de la misma marca en la tabla, y si no hay ninguna, `0000000001`.
    - Si se ha consultado un cliente factura, el suyo.
    - La API ya busca y guarda las líneas por ese campo.
- **Números en las altas y modificaciones (11/11/2026).** La API no se toca: si recibe un precio o un descuento
  como texto con coma (`"1,25"`), lo guarda como 125. Se resuelve en n8n con `aNumero` (`n8n/numero_es.js`), que
  irá en el nodo que prepare la petición de actualizar.
  - Convierte el formato español a número con punto: `1,25` → 1.25, `1.250,50 €` → 1250.5, `6,5 %` → 6.5.
  - También acepta `1.25` y `,5`.
  - `1.250` es ambiguo y se pregunta al usuario.
  - El texto que no es un número da error.
  - Probado en local con 22 casos.
- ⚠️ Al recorrer las tablas 1–300 con un solo nodo HTTP, n8n lanzó las 300 peticiones a la vez y desde la 138 todas dieron
  timeout. La API se recuperó enseguida. Si hay que volver a recorrerlas, hacerlo con *Batching* (1 petición cada vez).

Lo que se ha visto al probar la de clientes (27/10/2026), y por qué el flujo hace lo que hace:

- **Distingue mayúsculas**: `cartagena` → 0 clientes, `CARTAGENA` → 201. El flujo pasa el dato a mayúsculas.
- **Sin límite**: `B30` devuelve 2.759 clientes (1,4 MB). Al modelo solo le llegan los 10 primeros, con `total` y `hay_mas`.
- **Campos rellenos de espacios** (columnas de ancho fijo): se recortan.
- **Errores intermitentes**: la primera llamada con `CARTAGENA` devolvió 500 `{"mensaje": "Error al consultar clientes.", "detalle": "Error interno."}` y la siguiente funcionó. El nodo hace 2 intentos (0,3 s entre ellos).
- **Tildes y Ñ literales**: `NAM NAM` no encuentra `ÑAM ÑAM`. El agente prueba variantes si no hay resultados.
- **Un CIF, varios códigos**: `B30682488` tiene dos códigos (dos direcciones), así que se tratan como clientes distintos y se elige.
- Sin clave: 401 `API Key no válida o ausente.`


## Anexo B. Detalle del flujo (nodo a nodo)


Archivo `n8n/chat-ia-clientes-ayc.json`, generado con `python3 n8n/build_workflow.py` (el código de los nodos
de los nodos Code está en `n8n/*.js`, con `comun.js` delante; tras cambiarlo hay que regenerar el JSON).

- **consultar_clientes** (*Call n8n Workflow Tool*): llama al mismo flujo por su id fijo `ChatIaClienAYC01` por la
  entrada *Consulta* (*Execute Workflow Trigger*, parámetro `dato`). Se hace así, y no con un *HTTP Request Tool*
  como en contactos, porque la respuesta cruda puede pesar más de 1 MB y hay que recortarla antes del modelo.
- **API clientes**: HTTP Request con la credencial *Header Auth* "API AYC (X-api-key)". La respuesta se lee como
  texto para que un array vacío no corte el subflujo.
- **Normalizar**: devuelve `{dato, total, requiere_eleccion, hay_mas, resultados[≤10]}` (coincidencias exactas de
  código o CIF primero) o `{error}`, igual que la búsqueda de contactos.
- **consultar_precios_especiales** y **consultar_descuentos**: llaman a la misma entrada *Consulta* con
  `accion` fija y `codigo_cliente`, `codigo_tabla` (solo si el usuario da la tabla; entonces se salta *consultar*) y
  `articulo` (filtra por código o palabras de la descripción, sin distinguir tildes). n8n solo arranca un
  *Execute Workflow Trigger* por flujo, por eso todas comparten *Consulta* y el nodo *¿Condiciones?* separa los caminos.
- **Tabla** (`n8n/tabla.js`) y **Normalizar condiciones** (`n8n/normalizar_condiciones.js`): devuelven
  `{tipo, tabla{codigo, descripcion, num_clientes}, total_tabla, total, hay_mas, productos[≤60]}` con
  `articulo, descripcion, precio|descuento, desde, hasta, vigente` (`vigente=false`: aún no ha empezado), o `{error}`
  con el mensaje de la API (404/400) si lo hay.
- **consultar_surtido**: como las dos anteriores, con `accion=surtidos`. Tras *API productos*, *¿Surtido?* manda la
  respuesta a **Normalizar surtido** (`n8n/normalizar_surtido.js`), que devuelve `{tipo: "surtido", tabla, cliente_factura,
  avisos, clientes_factura, marcas, grupos, total_tabla, total, hay_mas, productos[≤60], parecidos}`. `productos`:
  `articulo, descripcion, marca, grupo, cliente_factura, desde, hasta` (vacío si es 2500) y `vigente`, ordenados por
  cliente factura (el genérico al final), marca y descripción. `clientes_factura`: por cada uno, código, nombre,
  número de marcas, grupos y artículos y `articulos_por_marca`. `marcas` (marca completa) y `grupos` (grupo de una marca) llevan códigos, descripciones y fechas, y van
  siempre enteros aunque se filtre por artículo. `total_tabla` cuenta solo artículos sueltos.
- Filtro `articulo` (surtidos, precios y descuentos): ignora palabras vacías (de, del, la, con…), así que "poker de
  vainilla" busca POKER y VAINILLA. En surtidos busca también en la marca y el grupo del artículo ("dulcesol" encuentra
  los artículos que la descripción abrevia DSOL). En surtidos, si con todas las palabras no sale nada, `parecidos` devuelve hasta 10
  artículos con más palabras en común, para que el agente pregunte en vez de decir que no.
- **Agente clientes**: si hay varios, lista numerada (nombre, código, CIF, población) y deja elegir; con uno, la ficha.
  Para precios o descuentos por nombre o CIF, busca antes el cliente; muestra la tabla y los artículos con precio
  (€) o descuento (%) y "hasta", marca las líneas futuras y, si la tabla está vacía, lo dice con su descripción.
  Para el surtido muestra la tabla, los avisos (si hay), las marcas completas y los grupos (si hay) y los artículos
  agrupados por marca, con el grupo entre paréntesis; si son más de 60, el recuento por marca. A "¿puedo venderle X?"
  responde sí con el código si X está suelto o si su marca está completa; si su marca solo tiene grupos, dice que
  puede entrar por ellos pero que no puede comprobar el grupo; si solo hay parecidos, los enseña y pregunta; con la
  999 dice que no tiene surtido asignado.
  Si piden algo que no sea consultar, dice que de momento no puede.
- **Chat**: chat alojado y público, protegido con *Basic Auth* (credencial *Albaranes IA - Basic Auth*, usuario
  `revision`). Se entra directamente por
  `https://ia-support-n8n.kw2y1s.easypanel.host/webhook/6d2b7e41-58c3-4f0a-a9e2-4b1d9c0e7a31/chat` y el navegador
  pide usuario y contraseña. No usar la dirección `/signin?redirect=…`: es el login de n8n y pide el correo de un
  usuario de n8n (*"Must be a valid email"*). Antes el chat usaba `n8nUserAuth` (solo usuarios de n8n); se cambió el
  06/11/2026. Si el navegador sigue mandando al login, es la página antigua en caché: abrirla en ventana privada.
- Modelo, temperatura y memoria como en contactos (OpenRouter `anthropic/claude-haiku-5.5`, 0,1; últimos 20 mensajes).


## Anexo C. Historial de instalaciones y pruebas


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

Precios especiales y descuentos (29/10/2026): subflujo probado con copias temporales del flujo (ya borradas) en las
que *Consulta* era un Code con las entradas fijas:

| accion, entradas | Resultado |
|---|---|
| clientes, `dato=4300017472` | 1, ÑAM ÑAM (sin cambios) |
| preciosEspeciales, cliente `4300016289` | tabla 14 `04PES UPPER-TIENDAS` (216 clientes), 34 productos |
| descuentos, cliente `4300016289` | tabla 14 `04CDP CAD 14 UPPER TIENDAS`, 8 productos |
| preciosEspeciales, cliente `4300017472` | tabla 999 `PES CLIENTE BLOQUEADO`, 0 productos |
| descuentos, `codigo_tabla=2` | 20 productos, todos `vigente=false` (desde 01/11/2026) |
| preciosEspeciales, cliente `4300016289`, `articulo=madalenas` | 3 de 34 |
| descuentos, cliente `9999999999` | error "No hay datos comerciales (CLP)…" |
| preciosEspeciales, sin cliente ni tabla | error "Falta el código de cliente…" |
| descuentos, `codigo_tabla=12` | error "No se encontró la tabla de descuentos con código 12." |

Agente (copias temporales con los mensajes fijos y las herramientas apuntando al flujo ya publicado; borradas):

| Usuario | Agente |
|---|---|
| precios especiales del cliente 4300016289 | Tabla 14 (216 clientes) y los 34 artículos con precio y "hasta"; avisa del 0290 repetido con dos periodos |
| busca el cliente ÑAM ÑAM → el primero, ¿qué descuentos tiene? | Lista de 2 y elige; después "no tiene descuentos", tabla 999 CDP CLIENTE BLOQUEADO |
| ¿qué descuento tiene UPPER en las madalenas? el cliente es 4300016289 | Filtra `articulo=madalenas`: 0777 15,4 % y 10240 20,1 % |
| descuentos de la tabla 2 | 20 artículos, todos "a partir del 01/11/2026" |

Instalado en el servidor el 29/10/2026 (copia anterior en `/root/backups/ChatIaClienAYC01_20261029_1719.json`).

Surtidos (03/11/2026): mismo método, hoy en `pruebas/n8n_tmp.sh` (copias `TmpSurtidoAYC01`, ya borradas con sus ejecuciones).

| accion, entradas | Resultado |
|---|---|
| surtidos, cliente `4300016289` | tabla 242 `UPPER CADENA 14 EDI` (186 clientes), 246 artículos, 60 devueltos, `hay_mas` |
| surtidos, cliente `4300016289`, `articulo=poker` | 5 de 246 |
| surtidos, cliente `4300017472` | error "No se encontró la tabla de surtido con código 999." |
| surtidos, cliente `9999999999` | error "No hay datos comerciales (CLP)…" |
| surtidos, `codigo_tabla=10` / `126` | 44 artículos y aviso SOLOENDOSO / 3 artículos y aviso CSACLIENTE |
| surtidos, `codigo_tabla=12` | error "No se encontró la tabla de surtido con código 12." |
| descuentos, cliente `4300016289` | tabla 14, ahora **vacía** (el 29/10 tenía 8 líneas y 216 clientes; hoy 187): cambio del ERP |
| clientes, `dato=4300017472` | 1, ÑAM ÑAM (sin cambios) |

| Usuario | Agente |
|---|---|
| ¿Qué surtido tiene el cliente 4300016289? | Ficha, surtido 242 y los primeros artículos; propone filtrar por marca |
| ¿Puedo venderle Poker de vainilla al 4300016289? | Sí: 0129 POKER 4X45G VAINILLA y 1022 POKER 5X45G VAINILLA (antes del arreglo del filtro decía que no) |
| ¿… algodón de azúcar de limón? | No está; ofrece los dos de fresa (16583, 16584) |
| Dime el surtido de ÑAM ÑAM | Lista de 2 y pide elegir |
| Surtido del cliente 4300017472 | No tiene surtido asignado; no supone que pueda comprar de todo |
| ¿Qué artículos tiene el surtido 126? | 3 Poker y el aviso "solo artículos autorizados" |

Instalado y publicado por CLI el 03/11/2026 (copia anterior en `/root/backups/ChatIaClienAYC01_20261103_1202.json`).

Marcas y grupos (09/11/2026): subflujo y agente con `pruebas/n8n_tmp.sh` (flujo temporal ya borrado).

| accion, entradas | Resultado |
|---|---|
| surtidos, `codigo_tabla=100` | aviso SOLOENDOSO, marca completa DULCESOL, grupos GRANEA y GRANEB de DULCESOL, 1 artículo |
| surtidos, `codigo_tabla=126` | aviso CSACLIENTE, grupos GRANEA y GRANEB, 3 artículos LAGO |
| surtidos, cliente `4300016289`, `articulo=poker` | tabla 242, grupos GRANEA y GRANEB, 246 artículos de 27 marcas, 5 Poker (como antes) |

| Usuario | Agente |
|---|---|
| ¿Qué surtido tiene el cliente 4300016289? | Surtido 242, los 2 grupos de DULCESOL, 60 artículos agrupados por marca con el grupo, y lo que falta por marca |
| Muéstrame el surtido 100 | Aviso, "Marca completa: DULCESOL", los 2 grupos y el artículo 9505 |
| ¿Puedo venderle Poker de vainilla al 4300016289? | Sí: 0129 y 1022 (LAGO) |
| ¿Puedo venderle palmeritas Dulcesol al 4300016289? | No están sueltas; pueden entrar por los grupos GR ENVUELTO DSOL 1/2, pero no lo puede comprobar; ofrece las palmeritas AYC |

Instalado y publicado por CLI el 09/11/2026 (copia anterior en `/root/backups/ChatIaClienAYC01_20261109_1034.json`).


Cliente factura en surtidos (11/11/2026): subflujo y agente con `pruebas/n8n_tmp.sh` (flujo temporal ya borrado).

| accion, entradas | Resultado |
|---|---|
| surtidos, cliente `4300016289` | tabla 242 (210 clientes): Vicky Foods con 2 grupos y 119 artículos; genérico con 123 |
| surtidos, `codigo_tabla=242`, `cliente_factura=4400000173` | solo Vicky Foods; `lineas_de_otros` 123 |
| surtidos, `codigo_tabla=390` | aviso SOLOENDOSO; Vicky Foods con 5 BKING; genérico con 1 DULCESOL |
| surtidos, cliente `4400000173` | error "El cliente no tiene tabla de surtido asignada." |

| Usuario | Agente |
|---|---|
| ¿Qué surtido tiene el cliente 4300016289? | Surtido 242 en dos apartados (Vicky Foods y genérico), con el recuento por marca |
| ¿Puedo venderle Poker de vainilla al 4300016289? | Sí: 4 artículos genéricos (valen para cualquiera) |
| ¿Puedo venderle productos Hermanos Juan al 4300016289? | Sí, pero solo si el endoso lo hace Vicky Foods; 20 artículos |
| ¿Qué surtido tiene Vicky Foods 4400000173? | No tiene surtido propio; pide el número de surtido |
| Líneas de Vicky Foods en el surtido 390 | Aviso, 5 artículos BKING y "2 líneas más de otros clientes factura" |

Instalado y publicado por CLI el 11/11/2026 (copia anterior en `/root/backups/ChatIaClienAYC01_20261111_0850.json`).

Altas y modificaciones (11/11/2026): subflujo y agente con `pruebas/n8n_tmp.sh` (flujo temporal ya borrado). Todo
en la tabla 14 de pruebas, con la línea de prueba `0129`, que creó la API.

| accion, entradas | Resultado |
|---|---|
| precios, cliente `4300016289`, `14403`, `5,80` | error: línea creada por el ERP (`API_MODIFICA_LINEAS_ERP = false`) |
| precios, cliente `4300016289`, `129`, `1,30` | vista previa: modificación de 1,25 € a 1,30 €, tabla compartida por 211 clientes |
| … con un código de confirmación erróneo | vista previa otra vez, con el aviso de que el código no corresponde |
| … con el código correcto | guardado (1 modificación); el registro falla por el módulo desactivado en la CLI |
| descuentos, tabla 14, `0129`, `6,5 %` | sin cambios |
| precios, tabla 14, `129`, `1,40`, desde 01/12/2026 | pregunta: se solapa con la línea actual, hay que cerrarla antes |
| precios, tabla `999` | error: no se modifica |
| descuentos, valor `1.250` | error: es ambiguo |
| surtidos, tabla 242, artículo nuevo | pregunta: con qué cliente factura |

| Usuario | Agente |
|---|---|
| Cambia el precio especial del artículo 129 del cliente 4300016289 a 1,35 | Vista previa (1,30 € → 1,35 €, tabla compartida por 211 clientes) y pide confirmación con el código |
| (vista previa anterior) Sí, confirmo el cambio | Llama con el código y confirma: guardado, de 1,30 € a 1,35 € |
| Pon el descuento del 129 de la tabla 14 al 7 % y guárdalo directamente | No lo guarda: enseña la vista previa y pide confirmación |
| Cambia el precio del artículo 14403 del cliente 4300016289 a 5,80 | Explica que la línea es del ERP y que falta el arreglo de la API |

Instalado y publicado por CLI el 11/11/2026 a las 12:02 (copia anterior en
`/root/backups/ChatIaClienAYC01_20261111_1202.json`). Las líneas de prueba de la tabla 14 han quedado así: precio
del `0129` a 1,35 € y descuento del `0129` a 6,6 %, los dos desde el 11/11/2026.

Líneas creadas por el ERP (11/11/2026, tras publicar el técnico `cambios_api_20261111.patch` y poner
`API_MODIFICA_LINEAS_ERP = true`):

| accion, entradas | Resultado |
|---|---|
| precios, tabla 14, `14403` (consulta) | 1 línea, 5,75 € del 01/02/2024 al 31/12/2026 |
| precios, tabla 14, `14403`, `5,80` | vista previa: modificación de 5,75 € a 5,80 €, mismas fechas |
| … con el código correcto | guardado (0 altas, 1 modificación) |
| precios, tabla 14, `14403` (consulta) | **1 línea**, 5,80 €, mismas fechas; la tabla sigue con 27 líneas (sin duplicado) |

| Usuario | Agente |
|---|---|
| Cambia el precio especial del artículo 14403 del cliente 4300016289 a 5,85 | Vista previa (5,80 € → 5,85 €, fechas conservadas, tabla compartida por 211 clientes) y pide confirmación; no se confirmó |

Instalado y publicado por CLI el 11/11/2026 a las 15:36 (copia anterior en
`/root/backups/ChatIaClienAYC01_20261111_1536.json`). El 14403 de la tabla 14 de pruebas ha quedado a 5,80 €
(antes 5,75 €).

Revisión de velocidad y duplicidades (11/11/2026, sin cambios para el agente):
- Reintentos: 2 intentos con 0,3 s de espera (antes 3 con 1 s) y 15 s de tiempo máximo (antes 30 s). Un 404 pasa de
  2,6 s a ~0,7 s (medido en el nodo *API tabla* con el cliente `4400000173`).
- Una sola rama para decidir la tabla (*¿Buscar tabla?* → *API tabla* → *Tabla*) para consultar y actualizar: se
  quitan *¿Buscar tabla act?* y *API tabla act* (35 nodos).
- `comun.js` con las funciones que estaban copiadas en 6 ficheros, y `NOMBRES_CF` en un solo sitio.
- Fuera la comprobación de `API_MODIFICA_LINEAS_ERP` (la API ya modifica las líneas del ERP).
- Regresión con el subflujo (flujo temporal ya borrado): clientes `B30682488` y `cartagena`; precios del 14403;
  descuentos de la tabla 14; surtido "poker vainilla", 242 con Vicky Foods y 390; vista previa del 14403 a 5,85;
  sin cambios a 5,80; solape del 129; tabla 999; valor `1.250`; alta en surtido sin cliente factura; sin cliente ni
  tabla; 404 de cliente sin surtido y de tabla inexistente. Todos dan lo mismo que antes.

| Usuario | Agente |
|---|---|
| ¿Qué surtido tiene Vicky Foods 4400000173? | No tiene surtido propio; pide el número de surtido |
| Pon el descuento del artículo 0129 del cliente 4300016289 al 7,5 % | Vista previa (7,2 % → 7,5 %, tabla 14 compartida por 211 clientes); no se confirmó |

Instalado y publicado por CLI el 11/11/2026 a las 15:56 (copia anterior en
`/root/backups/ChatIaClienAYC01_20261111_1556.json`). El descuento del `0129` en la tabla 14 estaba al 7,2 %, del
11/11/2026 al 31/12/2026: lo cambió el usuario desde el chat real a las 13:12 (registro en la Data Table).

Líneas de marca, grupo y generales en precios y descuentos (11/11/2026). Recorridas las tablas 1–80 con un flujo
temporal: en precios (14, 16, 27, 37, 43, 51) solo hay artículos. En descuentos, la 14 tiene una línea **general**
(6 %, sin marca, grupo, prefamilia, familia ni artículo) y la 55 una marca (CARRETILLA 14 %) y 3 grupos (DULCESOL
GRANEA y GRANEB 14,65 %, FINI BS100G 15,5 %). No hay líneas de familia sin artículo. La 998 de descuentos tiene una línea
general al 0 %. Las líneas de artículo traen la marca y el grupo del artículo.

| accion, entradas | Resultado |
|---|---|
| descuentos, tabla 14 | `generales` 6 % sin fin; 1 artículo (0129, LAGO, 7,2 % hasta 31/12/2026) |
| descuentos, tabla 55 | 1 marca, 3 grupos, 1 artículo |
| descuentos, tabla 55, `dulcesol` | marcas y grupos completos, 0 artículos |
| precios, cliente `4300016289`, `poker` | 0129 con marca LAGO, `hasta` vacío (sin fin) |
| descuentos, cliente `4400000173` | tabla 998 vacía (sin la línea general al 0 %) |

Regla del ERP (dicha por el usuario el 11/11/2026): se aplica la línea general, salvo que haya otra específica de
artículo, grupo o marca. Supuesto, sin confirmar: entre las específicas manda la más concreta (artículo > grupo >
marca). Está en `SYSTEM`, paso 8.

| Usuario | Agente |
|---|---|
| ¿Qué descuentos tiene la tabla 55? | Marca CARRETILLA, 3 grupos y el artículo 0777; añade "no hay generales ni familias" (sobra) |
| ¿Qué descuento tiene el artículo 0129 del cliente 4300016289? | 7,2 % propio, "no la general del 6 %" |
| ¿Qué descuento tiene el artículo 14403 del cliente 4300016289? | Sin línea propia: se aplica la general, 6 % |
| En la tabla de descuentos 55, ¿qué descuento tiene un artículo de Dulcesol? | 14,65 % si es de GR ENVUELTO DSOL 1 o 2; si no, ninguno. Ofrece comprobar el grupo con el código (no puede, sin línea propia) |

Instalado y publicado por CLI el 11/11/2026 a las 16:20 (copia anterior en
`/root/backups/ChatIaClienAYC01_20261111_1620.json`).

Ajustes del 11/11/2026, 16:24 (copias en `/root/backups/ChatIaClienAYC01_20261111_1623.json` y `…_1624.json`):
- `SYSTEM`, paso 8: no decir nada de las clases de línea vacías. Probado: en la tabla 55 ya no dice "no hay generales
  ni familias".
- `normalizar_condiciones.js`: si el filtro no encuentra artículos y hay marcas, grupos o familias, añade una `nota`.
  Dice que la API no da el grupo de un artículo sin línea propia. Probado dos veces con "artículo de Dulcesol en la
  55": una vez pregunta si sabe el grupo; la otra pide el código "para comprobarlo". Con el código se puede ver si
  el artículo tiene línea propia, pero no su grupo.

Surtidos, altas y modificaciones reales (11/11/2026, tabla 390 `+BK`, 48 clientes, base de pruebas). Es la primera
escritura en CSA con la API: transacción y journal correctos. Tras cada paso, `listarProductos` devuelve una sola
línea del artículo.

| accion, entradas | Resultado |
|---|---|
| surtidos, tabla 390, `0129`, sin cliente factura | pregunta: con qué cliente factura |
| … con `0000000001` (vista previa y confirmación) | guardado, 1 alta: 0129 genérico, LAGO, desde 11/11/2026 sin fin; la tabla pasa de 6 a 7 líneas |
| tabla 390, `0129`, fecha fin 31/12/2026 | guardado, 1 modificación; una sola línea |
| tabla 390, `17243` (línea del ERP, Vicky Foods), fecha fin 31/12/2027 | vista previa con el cliente factura de la línea (Vicky Foods); guardado, 1 modificación, una sola línea, conserva el desde 10/04/2024 |
| tabla 390, `17243`, fecha fin 31/12/2500 | guardado: vuelve a quedar sin fin |
| tabla 390, marca `LAGO` (solo vista previa) | alta de marca completa, genérico (no hay otras líneas de LAGO) |

Queda en la tabla 390 de pruebas la línea `0129` genérico, del 11/11/2026 al 31/12/2026 (no se pueden borrar líneas).

Chat real y memoria (11/11/2026):
- El usuario volvió a publicar el chat desde la interfaz. La URL responde 401 (pide Basic Auth), así que está
  registrada.
- La Data Table "Cambios ERP AYC" (id `qTs0fyTgac8A9YXw`; en la BD de n8n, la tabla
  `"data_table_user_qTs0fyTgac8A9YXw"`) tiene los dos cambios que hizo el usuario desde el chat a las 13:12: el
  descuento del 0129 de la tabla 14, de 6,6 % a 7,2 %, y después su fecha fin a 31/12/2026. Usuario `revision`,
  resultado `ok`.
- Memoria: tres mensajes en la misma ejecución y sesión (flujo temporal con el *Code* "Mensaje" devolviendo 3
  items). "Busca el cliente 4300016289" → ficha. "¿Qué descuentos tiene?" → usa el mismo cliente sin volver a
  buscarlo: general 6 % y el 0129 al 7,2 %. "¿Y qué surtido tiene de Hermanos Juan?" → surtido 242, 20 artículos,
  solo con endoso de Vicky Foods.
