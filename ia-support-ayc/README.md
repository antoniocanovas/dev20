# ia-support · Clientes AYC (n8n + API del ERP de AYC)

Chat IA en n8n que consulta clientes, y sus precios especiales, descuentos y surtido, contra la API del ERP de AYC.
Misma filosofía que `ia-support-contactos/n8n/chat-ia-contactos.json` (Chat Trigger → AI Agent con
OpenRouter, memoria y herramientas), pero de momento solo lectura.

```
Chat (n8n) → Agente clientes ─┬ consultar_clientes ───────────┐
                              ├ consultar_precios_especiales ─┤
                              ├ consultar_descuentos ─────────┼→ Consulta (subflujo del mismo flujo, campo accion)
                              └ consultar_surtido ────────────┘    │
   clientes:                    API clientes → Normalizar          ├ GET …/api/clientes/consultarClientes
   preciosEspeciales/descuentos/surtidos:                          ├ GET …/api/{preciosEspeciales|descuentos|surtidos}/consultar
     API tabla cliente → Tabla → API productos → ¿Surtido? →       └ GET …/api/{preciosEspeciales|descuentos|surtidos}/listarProductos
       Normalizar condiciones | Normalizar surtido
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
- ⚠️ Al recorrer las tablas 1–300 con un solo nodo HTTP, n8n lanzó las 300 peticiones a la vez y desde la 138 todas dieron
  timeout. La API se recuperó enseguida. Si hay que volver a recorrerlas, hacerlo con *Batching* (1 petición cada vez).

Lo que se ha visto al probar la de clientes (27/10/2026), y por qué el flujo hace lo que hace:

- **Distingue mayúsculas**: `cartagena` → 0 clientes, `CARTAGENA` → 201. El flujo pasa el dato a mayúsculas.
- **Sin límite**: `B30` devuelve 2.759 clientes (1,4 MB). Al modelo solo le llegan los 10 primeros, con `total` y `hay_mas`.
- **Campos rellenos de espacios** (columnas de ancho fijo): se recortan.
- **Errores intermitentes**: la primera llamada con `CARTAGENA` devolvió 500 `{"mensaje": "Error al consultar clientes.", "detalle": "Error interno."}` y la siguiente funcionó. El nodo reintenta 3 veces (1 s entre intentos).
- **Tildes y Ñ literales**: `NAM NAM` no encuentra `ÑAM ÑAM`. El agente prueba variantes si no hay resultados.
- **Un CIF, varios códigos**: `B30682488` tiene dos códigos (dos direcciones), así que se tratan como clientes distintos y se elige.
- Sin clave: 401 `API Key no válida o ausente.`

## El flujo

Archivo `n8n/chat-ia-clientes-ayc.json`, generado con `python3 n8n/build_workflow.py` (el código de los nodos
*Normalizar*, *Tabla* y *Normalizar condiciones* está en `n8n/*.js`; tras cambiarlo hay que regenerar el JSON).

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
  respuesta a **Normalizar surtido** (`n8n/normalizar_surtido.js`), que devuelve `{tipo: "surtido", tabla, avisos,
  marcas, grupos, total_tabla, articulos_por_marca, total, hay_mas, productos[≤60], parecidos}`. `productos`:
  `articulo, descripcion, marca, grupo, desde, hasta` (vacío si es 2500) y `vigente`, ordenados por marca y
  descripción. `marcas` (marca completa) y `grupos` (grupo de una marca) llevan códigos, descripciones y fechas, y van
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
   404/400, tamaños y campos con relleno o raros. Apuntarlo en *La API*.
2. Si sigue el patrón *consultar por cliente → tabla → listarProductos*, basta con: añadir la `accion` (= nombre en la
   URL, `/api/<accion>/…`) a *¿Condiciones?*, darle nombre en `que` (`n8n/tabla.js`), crear la herramienta con
   `herramienta_condiciones(...)` y su conexión `ai_tool`. Si las líneas tienen otra forma, un Code propio detrás de
   *API productos* (como *¿Surtido?* → *Normalizar surtido*).
3. Explicar en `SYSTEM` (`build_workflow.py`) el concepto y cómo mostrarlo; regenerar.
4. Probar el subflujo con `subflujo` (casos buenos, vacíos, 404, sin datos), instalar y probar el agente con `agente`;
   apuntar los resultados en las tablas de abajo.

## Pendiente

- Probar el chat publicado (ya responde, con Basic Auth) con varias preguntas seguidas (memoria), p. ej. "dime el
  surtido de ÑAM ÑAM" → "el segundo".
- Marcas y grupos (09/11/2026): la API no dice qué artículos hay en una marca o un grupo. Para responder con
  seguridad "¿puedo venderle X?" cuando X no está suelto haría falta una API de artículos (marca y grupo de un
  artículo) o que `listarProductos` expanda las líneas. Consultarlo con AYC.
- Confirmar con AYC qué significan exactamente `SOLOENDOSO`, `FINDESERVI` y `CSACLIENTE` para la venta.
- Tablas de surtido de la 138 en adelante sin revisar (timeouts al recorrerlas; ver *Cuidados*).
- Revisar la tabla 14 de descuentos de UPPER, que ha pasado a venir vacía (dato del ERP, no del flujo).
- Surtidos grandes (246 artículos en la 242): el agente recibe 60 y propone filtrar. Si se usa mucho para listar
  completo, valorar subir el límite (`LIMITE` en `normalizar_surtido.js`).

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

## Pruebas de la API

Directas contra la API, desde una máquina que tenga la clave (no está en el repositorio):

```sh
AYC_KEY=<clave> sh pruebas/pruebas_api.sh
```

Sin la clave, usar `pruebas/n8n_tmp.sh` (ver *Probar con flujos temporales*).
