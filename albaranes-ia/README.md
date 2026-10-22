# albaranes-ia: detección de albaranes modificados a mano

Prototipo para detectar los cambios que hace el comercial a mano sobre el albarán impreso (tacha la cantidad con una "/" y escribe otra, o la sobrescribe). Lee la foto del albarán firmado con un modelo de visión, la compara con el ERP y deja a Administración una pantalla para revisar la cantidad final de cada línea y aprobar o rechazar. Después rectifica el albarán y la factura en el ERP, por ahora en modo simulación (`DRY_RUN`).

En producción el ERP será AS400/DB2. Odoo 20 es solo el entorno de pruebas, y todo el acceso al ERP está aislado en `albaranes-api/erp/`.

## Entorno de pruebas (reconocimiento, 16/10/2026)

1. **Plataforma:** el servidor `217.154.182.5` (SSH por el puerto 22022) usa Easypanel sobre Docker Swarm, sin `docker compose`. Proyecto `ia-support`, red overlay `easypanel-ia-support`. Los servicios no publican puertos: se exponen por los dominios de Easypanel (Traefik).
2. **Odoo:** imagen `odoo:20`, versión `20.0-20260926`, en https://ia-support-odoo20.kw2y1s.easypanel.host y por dentro en `ia-support_odoo20:8069`. BD `odoo` en `ia-support_surtidos-db` (Postgres 16), con Ventas, Inventario y Contabilidad con datos demo. Filestore en el volumen `ia-support_odoo20_odoo20-data`.
3. **n8n:** versión 2.21.0, en https://ia-support-n8n.kw2y1s.easypanel.host, con BD propia (`ia-support_n8n-db`) y *task runners* externos (`ia-support_n8n-runner`).
4. **Comunicación:** n8n habla con los servicios por los hosts internos de la red de Easypanel. Ninguna API nueva está expuesta a Internet: solo los webhooks de n8n, con Basic Auth.
5. **APIs externas de Odoo 20:** responden JSON-2 (`/json/2/<modelo>/<método>`, con API key como Bearer), JSON-RPC y XML-RPC. Se usa **JSON-2**: las otras dos están obsoletas en Odoo 20. Lo he comprobado en el propio entorno.
6. **API key:** en Odoo 20 debe tener **ámbito `rpc`**, porque una sin ámbito da *Invalid apikey*. Para un usuario no administrador también es obligatoria la caducidad, que se ha puesto a 90 días.
7. **Usuario de integración:** `integracion.albaranes`, con permisos de Inventario (administrador), Ventas (administrador) y Facturación.
8. **Informe del albarán:** el *Albarán de entrega* (`stock.action_report_delivery`, plantilla `stock.report_deliveryslip`) **no lleva código de barras**. Solo imprime el `name` (`WH/OUT/00040`) en el título, con las columnas Producto, Pedido y Entregado.
9. **Código de barras:** el informe estándar *Operaciones de albarán* (`stock.action_report_picking`) sí lleva el `name` en Code128 (`report_stockpicking_operations.xml`). El sistema acepta los dos informes: si no hay código, el modelo lee el número impreso.
10. **Secretos:** están en `/root/albaranes-ia/.env` (permisos 600) y en las credenciales de n8n. Ninguno está en el código.

## Estado y cómo retomarlo (22/10/2026)

**Hecho:** las fases A–E están desplegadas y probadas en el entorno de pruebas (ver Pruebas). Después se ha ajustado la pantalla con el usuario (ver *Cambios del 22/10*). Todo lo de abajo está **desplegado** en el servidor.

**Datos que hay ahora en `albaranes_ia`:**

| # | Albarán | Estado | Tipo | Nota |
|---|---|---|---|---|
| 21 | WH/OUT/00040 | aprobada | Modificado | Segunda prueba real (22/10): Caja 24 → 20 y Cubo 8 → 7, aprobada sin tocar. Rectificación simulada |
| 14 | WH/OUT/00041 | aprobada | Modificado | De `pruebas.sh` |
| 4 | WH/OUT/00041 | aprobada | Modificado | De `pruebas.sh` |
| 16, 6 | — | error | Error | Fotos que no son albaranes (`foto_no_albaran.jpg`). Sirven para probar *Reintentar* / *Eliminar* |

- **Borrados el 22/10, a petición del usuario:** #1, #13 y #17 (WH/OUT/00040), para volver a subirlo. Las rectificaciones eran simulaciones (o estaba rechazado), así que Odoo no se tocó.
  - Copia: `/root/albaranes-ia/backup_incidencias_WH-OUT-00040_202610220939.csv`.
  - Sus notas siguen en el historial del picking 49 de Odoo (`mail_message` 1169, 1197 y 1202). No se han borrado porque no hace falta para volver a subirlo.
- **La primera prueba real (#17, 16/10)** leyó lo mismo que la #21. Su plan `DRY_RUN` era una devolución de 4 Cajas y 1 Cubo, validarla y crear un abono en borrador desde S00026 (la factura INV/2026/00010 ya está publicada).

**Pendiente de decisión del usuario (no hacer sin confirmación):**
- **Rectificar de verdad:** `DRY_RUN=false` en Easypanel → albaranes-api → Entorno, y relanzar `/erp/rectificar` con un reconocimiento aprobado (ahora sería la #21, que sustituye a la #17).
- **Commit:** `albaranes-ia/` sigue sin trackear en git. Si se borra, solo queda lo desplegado en el servidor.
- **Notas antiguas de Odoo:** borrar o no las tres notas del picking 49 que mencionan la "incidencia" #1, #13 y #17.

**Sin probar en el navegador** (sí con curl, en el servidor, salvo lo que se indica):
- *Exportar a hoja de cálculo* y los dos *Imprimir*: son solo del navegador y no tienen prueba por curl.
- *Reintentar* y *Eliminar*: las rutas están probadas con un POST de formulario con Basic Auth, que es lo que envía la página.

**Ideas comentadas y no hechas:**
- Separar el estado "Por revisar" entre *cambiado a mano* y *dudoso pero igual* (baja confianza, tachón ilegible, número que no coincide). Ahora los dos son `pendiente_revision`.
- Cerrar automáticamente los `verificado` (aprobarlos no cambia nada en el ERP).
- Exportación con una fila por línea (artículo, ERP, IA, final), o `.xlsx` con formato en vez de CSV.
- Cambiar "incidencia" por "reconocimiento" también por dentro (tabla, rutas de la API, nodos de n8n). Requiere migrar la base y tocar los flujos, sin cambio visible.
- Que el aviso de "ya reconocido antes" obligue a revisar (ahora solo informa).

**Cambios del 22/10** (detalle en *Pantallas*):
- **Terminología:** en pantalla, en las notas de Odoo y en los mensajes de la API se dice **reconocimiento**. Por dentro sigue siendo `incidencia` (tabla, rutas `/incidencias`, `incidencia_id`, nodos de n8n).
- **Aviso de reconocimientos previos:** si se sube otra foto de un albarán que ya tiene reconocimientos, se avisa. Lo hace el nodo "Reconocimientos previos" con `GET /incidencias?albaran=…&excluir=…`.
- **Tipo Original / Modificado / Error:** campo `marca` calculado por la API. Sustituye a los filtros "Modificados", "Verificados" y "Con error".
- **Un solo botón Aprobar**, que aplica la columna *Final*. Se quitó "Corregir y aprobar".
- **Reintentar y Eliminar** para los reconocimientos con error.
- **Lista:** filtro por fechas, exportación CSV e impresión. Revisión: impresión.
- La tabla de revisión se ordena por la posición en la foto (`bbox[1]`) y ya no pone las dudosas primero (del 16/10).

**Incidencias conocidas:**
- **DNS con Cloudflare WARP:** en el Mac del usuario, WARP (DNS `127.0.2.2`) devuelve `SERVFAIL` para `*.kw2y1s.easypanel.host`, y los DNS públicos sí lo resuelven. Para comprobar el servidor sin depender de WARP:
  ```sh
  curl --resolve ia-support-n8n.kw2y1s.easypanel.host:443:217.154.182.5 …
  ```
- **`API_TOKEN` sin definir:** la API no está expuesta a Internet. En producción hay que ponerlo.
- **Un solo usuario Basic Auth (`revision`):** el campo "usuario" de la revisión es texto libre. En producción, un proxy con SSO (Cloudflare Access, Authelia…).

**Producción:** necesita n8n, albaranes-api, Postgres para los reconocimientos, la clave del modelo y HTTPS. `barcode-ocr` es opcional. En lugar de Odoo, un adaptador AS400 en `erp/`, cuya parte delicada es rectificar con los programas del ERP. Además:
- retención de fotos (RGPD);
- recortar las ejecuciones de n8n;
- alertas de error;
- usuarios nominales.

**Ampliaciones estudiadas:**
- [`albaranes_nagarmur.md`](albaranes_nagarmur.md): prompt para retomar el albarán del cliente con sus códigos, la tabla de equivalencias y el aprendizaje.
- [`IDEAS.md`](IDEAS.md): otros documentos a los que aplicar la metodología, e IA local (Docling + Ollama) frente a Claude.

## Arquitectura

```
 móvil / escáner                       n8n (webhooks con Basic Auth)
 ─────────────── POST foto ──► "Albaranes IA - Ingesta"
                                 1 guardar foto ───────────────► albaranes-api  /incidencias      (idempotente por SHA-256)
                                 2 código de barras ───────────► barcode-ocr    /decode
                                   └ si no hay: número por IA ─► albaranes-api  /vision/peticion ─► OpenRouter (credencial n8n)
                                 3 albarán y líneas ───────────► albaranes-api  /erp/albaran ─────► Odoo 20 JSON-2
                                   └ reconocimientos previos ──► albaranes-api  /incidencias?albaran=…&excluir=…
                                 4 lectura línea a línea ──────► OpenRouter / Anthropic (JSON Schema estricto)
                                 5 reglas (nodo Decidir) → verificado | pendiente_revision, marca original | modificado
                                 6 guardar resultado + nota en el historial del albarán
 Administración ◄── pantalla ── "Albaranes IA - Revisión"   (todas bajo /webhook/albaranes/)
                                 GET  revision?estado=&desde=&hasta=   lista
                                 GET  revision/{id}                    pantalla HTML
                                 GET  api/incidencia/{id}              JSON + imagen
                                 POST api/incidencia/{id}/resolver     aprobar | corregir | rechazar
                                      └ rectificar ────────────► albaranes-api /erp/rectificar (DRY_RUN)
                                 POST reintentar/{id}   foto original ─► ingesta (127.0.0.1:5678) con reprocesar=true
                                 POST eliminar/{id}     ───────────────► albaranes-api DELETE /incidencias/{id} (solo en error)
```

Los webhooks con parámetros comparten `webhookId` "albaranes". Dos rutas con el mismo método y el mismo número de segmentos chocarían. Por eso *reintentar* y *eliminar* son rutas de 2 segmentos y no `api/incidencia/{id}/…`.

| Servicio (Easypanel) | Host interno | Qué hace |
|---|---|---|
| `barcode-ocr` | `ia-support_barcode-ocr:8000` | FastAPI + zxing-cpp + OpenCV. `POST /decode` devuelve el código o `null` |
| `albaranes-api` | `ia-support_albaranes-api:8000` | Reconocimientos (tabla `incidencia`) en su propia BD, preparación e interpretación de la lectura por IA, y **capa ERP** |
| n8n | `ia-support_n8n` | Orquesta los flujos y sirve los webhooks y las páginas HTML |
| BD `albaranes_ia` | `ia-support_surtidos-db` | Reconocimientos (tabla `incidencia`): foto, lectura, decisión, revisión y rectificación. Base de datos y rol propios, no la del ERP |

### Capa ERP sustituible

`albaranes-api/erp/base.py` define el contrato: `obtener_albaran`, `obtener_albaran_por_id`, `anadir_nota`, `planificar_rectificacion` y `aplicar_rectificacion`, con los diccionarios normalizados documentados en el fichero. `erp/odoo_json2.py` es la implementación para Odoo. Para AS400/DB2 basta con escribir otro adaptador con la misma interfaz y elegirlo con `ERP_BACKEND`. Ni n8n, ni la pantalla, ni las reglas conocen modelos de Odoo.

### Lectura con IA

- `albaranes-api` prepara la petición: prompt, JSON Schema estricto, imagen reducida a 1568 px y modelo de `VISION_MODEL`.
- n8n la envía con su credencial (*Openrouter Header Auth account*), así que la clave no sale de n8n.
- `albaranes-api` interpreta la respuesta.

Respuesta por línea: `articulo, impreso, tachado, manuscrito, cantidad_final, confianza, dudoso, motivo, bbox`, con `bbox` normalizado de 0 a 1. Se le pasan como contexto las líneas del ERP (`move_id`, referencia, producto, pedido y entregado) para que asocie cada fila.

Para usar la API de Anthropic directamente:
1. Pon `VISION_PROVIDER=anthropic` y `VISION_MODEL=claude-sonnet-5-5`.
2. En los nodos "IA: …" del flujo, cambia la credencial por una *Header Auth* con `x-api-key`.

La petición ya incluye la cabecera `anthropic-version`. También existe `POST /vision/leer`, que llama directamente desde el servicio si este tiene `ANTHROPIC_API_KEY` u `OPENROUTER_API_KEY`.

### Reglas de decisión (nodo "Decidir" del flujo de ingesta)

Una línea queda **verificada** solo si se cumplen todas estas condiciones:
- la cantidad leída coincide con la del ERP;
- la confianza es ≥ `CONFIANZA_UMBRAL` (0,85);
- no está marcada como dudosa y no tiene tachones.

En cualquier otro caso pasa a **pendiente_revision**, con su motivo:

| Motivo | Cuándo |
|---|---|
| `modificada` | La cantidad leída es distinta de la del ERP |
| `tachon_ilegible` | Hay un tachón sin número legible |
| `baja_confianza` | Confianza por debajo del umbral |
| `dudosa` | El modelo marca la lectura como dudosa |
| `variacion_sospechosa` | El cambio supera el 50 % (`VARIACION_SOSPECHOSA`) |
| `supera_pedido` | La cantidad leída es mayor que la pedida |
| `no_leida` | No se ha leído la línea |
| `tachado_sin_cambio` | Está tachado pero la cantidad es la misma |

El albarán entero queda verificado solo si lo están todas sus líneas y además:
- no hay líneas escritas a mano que no estén en el ERP;
- el número leído coincide con el del ERP;
- la foto no es de mala calidad.

### Idempotencia

- **Misma foto:** la identifica el SHA-256 del fichero. Si se sube otra vez, devuelve el mismo reconocimiento (`duplicada: true`, unos 0,2 s) sin volver a llamar a la IA ni escribir otra nota. Con `reprocesar=true` se vuelve a leer, salvo que ya esté resuelto. Si estaba a medias (`recibida`/`procesando`), se procesa aunque sea duplicada.
- **Otra foto del mismo albarán:** tiene otra huella, así que es un reconocimiento nuevo. Se lee con la IA, se escribe otra nota y lleva el aviso *"Este albarán ya se había reconocido antes: #N del dd/mm/aaaa (estado)"*. El aviso no cambia el estado.
- **Resolver:** solo se puede una vez; un segundo intento da 409.
- **Rectificar:** comprueba antes que el albarán no haya cambiado en el ERP desde la lectura (409 si ha cambiado).

## E. Rectificación en Odoo 20

Opciones estudiadas para un albarán ya validado, todas estándar y sin módulos propios:
- **Editar las cantidades hechas:** no es posible en un albarán validado, porque los movimientos están cerrados.
- **Devolución:** `stock.picking.action_return`. En Odoo 20 ya no hay asistente: se crea un albarán de devolución en borrador con las líneas. Al validarlo, Odoo descuenta lo entregado en el pedido de venta (`to_refund`).
- **Abono:** asistente estándar de factura del pedido (`sale.advance.payment.inv`, método *según lo entregado*). Si lo facturado supera lo entregado, genera la factura rectificativa (abono) por la diferencia.

Qué hace el adaptador, que es lo más simple y soportado:

| Situación | Qué hace |
|---|---|
| Albarán **sin validar** | Pone las cantidades hechas finales y valida sin pedido pendiente (sin *backorder*) |
| Validado, **menos** cantidad | Devolución estándar solo de la diferencia, y se valida |
| Validado, **más** cantidad | Sube la cantidad de la línea del pedido. Odoo crea un albarán con la diferencia, que se valida |
| Producto que se factura **por pedido** | Además ajusta la cantidad pedida, para que salga en el abono |
| Pedido con **factura publicada** | Crea en **borrador** el abono o la factura complementaria desde el pedido, para que Administración lo revise y publique |

Con `DRY_RUN=false` también añade una nota en el historial del albarán con la foto adjunta (`ir.attachment`).

- **Con `DRY_RUN=true`** (por defecto) solo guarda el plan en `rectificacion`. Aparece en la pantalla y en la respuesta del resolver, sin escribir nada en el ERP.
- **Para activarlo:** `DRY_RUN=false` en Easypanel → albaranes-api → Entorno → Implementar.

**Probado de verdad el 16/10/2026** (`pruebas/prueba_rectificacion.py`, sobre albaranes desechables):
- **WH/OUT/00042, validado y facturado:** se pasa de 12 a 10, de 5 a 7 y de 3 a 2 (por pedido). El resultado es la devolución WH/IN/00010, el albarán complementario WH/OUT/00044 y un abono en borrador de 501,98 (+2 gabinetes, +1 alfombrilla, −2 sillas). El pedido queda entregado y facturado 10/7/24/2/8.
- **WH/OUT/00043, sin validar:** se valida con 11.

## Uso

### Imprimir un albarán de prueba

En Odoo 20 (https://ia-support-odoo20.kw2y1s.easypanel.host, usuario `admin`), Inventario → Entregas:
- **WH/OUT/00040** (pedido S00026, cliente *Supermercados Prueba IA*): 5 líneas, validado y facturado (INV/2026/00010). Es el caso típico de albarán firmado.
- **WH/OUT/00041** (S00027): 4 líneas, preparado sin validar.

Imprime con **Imprimir → Albarán de entrega**, que sale en español y sin código de barras. Si quieres probar también el código de barras, usa **Imprimir → Operaciones de albarán**. Haz los tachones y cambios a mano, saca una foto y súbela.

### Subir la foto

- **Formulario** (también desde el móvil, con la cámara): https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/subir. Al terminar muestra la tabla ERP / IA y el enlace a la revisión.
- **curl:**
  ```sh
  curl -u revision:<contraseña> -F foto=@albaran.jpg https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/ingesta
  ```
  Añade `?reprocesar=true` para volver a leer la misma foto.
- **Usuario:** `revision`. La contraseña está en el servidor:
  ```sh
  ssh -p 22022 root@217.154.182.5 grep REVISION_PASSWORD /root/albaranes-ia/.env
  ```
  Se puede cambiar en n8n → Credenciales → *Albaranes IA - Basic Auth*.

### Pantallas

Las páginas están en `web/` y se incrustan en los nodos Code al generar los flujos. Para cambiarlas: editar `web/*.html` y luego `scripts/desplegar.sh n8n`.

| Página | Ruta (bajo `/webhook/albaranes/`) | Fichero |
|---|---|---|
| Subir foto | `subir` | `web/subir.html` |
| Resultado (subida, foto repetida, revisión guardada, reintentar, eliminar) | — | `web/resultado.html` |
| Lista | `revision` | `web/lista.html` |
| Revisión de un reconocimiento | `revision/{id}` | `web/revision.html` |

**Estado y tipo.** Cada reconocimiento muestra dos etiquetas:

| Estado interno (`estado`) | Etiqueta | Filtro |
|---|---|---|
| `pendiente_revision`, `verificado`, `error` | Por revisar | **Por revisar** (por defecto) |
| `aprobada`, `corregida`, `rectificada` | Aprobada / Corregida / Rectificada en el ERP | **Resueltos** |
| `rechazada` | Rechazada | **Rechazados** |
| `recibida`, `procesando` | Recibida / Procesando | solo en **Todos** |

- **Tipo (`marca`, lo calcula la API en `_marca`):**
  - **Error**, si `estado = error`;
  - si está resuelto, **Modificado** cuando alguna cantidad final es distinta de la del ERP, y **Original** si no;
  - si no, lo que detectó la IA: **Modificado** cuando alguna cantidad leída es distinta o hay líneas a mano que no están en el ERP. El nodo Decidir lo guarda en `decision.marca`; en reconocimientos antiguos se recalcula.
- **Rechazado:** conserva lo que detectó la IA.
- **Dónde se ve el tipo:** en la columna *Tipo* de la lista, en la cabecera de la revisión, en el resultado y en la nota de Odoo (*"**Modificado**, por revisar"* / *"**Original**, coincide con el ERP"*).

**Lista** (https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/revision):
- **Filtros de estado:** Por revisar, Resueltos, Rechazados y Todos.
- **Recibidos desde / hasta:** fecha de recepción en hora de Madrid; `hasta` incluye el día. Se combina con el estado: los enlaces conservan las fechas y el formulario conserva el estado. Una fecha no válida da *"Fecha no válida: usa AAAA-MM-DD"*.
- **Exportar a hoja de cálculo:** CSV de la vista en curso, hecho en el navegador, de hasta 500 filas (`limite=500` en el nodo "Listar incidencias"). Lleva `;`, BOM UTF-8 y CRLF para Excel en español. Columnas:
  - reconocimiento, albarán, cliente, estado y tipo;
  - líneas, líneas a revisar y cambios aprobados;
  - recibido, revisado por, fecha de revisión, comentario y error.
  - Nombre del fichero: `albaranes_<filtro>_<desde>_<hasta>.csv`.
- **Imprimir:** `window.print()`. Lleva un título con el filtro, las fechas, el número de albaranes y la hora; oculta cabecera, filtros y botones, y fuerza colores claros aunque esté en modo oscuro.

**Revisión:**
- **Foto:** a la izquierda, con zoom (rueda o pellizco), arrastre y giro. Al tocar una fila salta a su `bbox`.
- **Tabla:** a la derecha, en el mismo orden que en la foto (de arriba abajo; las que no se ven en ella, al final). Las líneas que hay que revisar van resaltadas. La columna *Final* viene con lo que leyó la IA y es editable.
- **Aprobar:** aplica siempre la columna *Final*. Se envía `accion=aprobar` si no se ha tocado ninguna casilla y `accion=corregir` si se ha cambiado alguna, para que quede constancia (`aprobada` / `corregida`). Se desactiva si alguna casilla *Final* está vacía.
- **Rechazar:** pide confirmación con un segundo clic. No toca el ERP.
- **Con error** (en lugar de los dos anteriores):
  - **Reintentar** → `POST reintentar/{id}`. n8n coge la foto original de la API y la pasa por el flujo de ingesta (`http://127.0.0.1:5678/webhook/albaranes/ingesta?html=1`, con la credencial Basic Auth y `reprocesar=true`). Es el mismo reconocimiento.
  - **Eliminar** → `POST eliminar/{id}`, que pide confirmación. Borra el reconocimiento con su foto. La API (`DELETE /incidencias/{id}`) solo lo permite en `error` y da 409 en el resto.
- **Imprimir:** página 1 con los datos (cabecera, avisos, tabla con la cantidad final en negrita y resolución); página 2 con la foto completa, sin el visor. Oculta los botones y la zona de aprobar.

**Restricción de las páginas:** n8n las sirve con `Content-Security-Policy: sandbox allow-downloads allow-forms allow-modals allow-popups allow-scripts …`, **sin `allow-same-origin`** (comprobado el 22/10). Consecuencias:
- el origen es opaco, así que `fetch` a los webhooks **no envía la Basic Auth**. Toda acción va por **formulario normal** (`#form` en `revision.html`), y los datos van incrustados en la página (`__DATOS__`);
- descargar (CSV con Blob) e imprimir sí están permitidos (`allow-downloads`, `allow-modals`);
- `localStorage` puede fallar: está envuelto en `try/catch`. Solo recuerda el nombre de "Revisado por".

### Chuleta para el servidor

```sh
ssh -p 22022 root@217.154.182.5
# Reconocimientos (BD albaranes_ia; el usuario de Postgres está en $POSTGRES_USER del contenedor)
docker exec $(docker ps -q -f name=ia-support_surtidos-db | head -1) sh -c \
  'psql -U $POSTGRES_USER -d albaranes_ia -c "select id, creada, estado, albaran_numero, nombre_fichero from incidencia order by id"'
# Llamar a los webhooks con las credenciales del .env (pedir.sh lee /root/albaranes-ia/.env: ejecutar en el servidor)
sh /root/albaranes-ia/pruebas/pedir.sh "albaranes/api/incidencia/21"
# La API por dentro (sin API_TOKEN), desde el contenedor de n8n
docker exec $(docker ps -q -f name=ia-support_n8n | head -1) wget -qO- "http://ia-support_albaranes-api:8000/incidencias?limite=20"
```

- **Antes de borrar reconocimientos:** guardar una copia con `\copy (select * from incidencia where …) to stdout with csv header` en `/root/albaranes-ia/`. Las notas de Odoo están en `mail_message` (`model='stock.picking'`, `res_id` = id del albarán) de la BD `odoo`.
- **Ejecuciones de n8n:** para depurar un flujo, mirar en n8n → Ejecuciones el nodo que falló. Los errores de la ingesta se guardan también en el campo `error` del reconocimiento (`"<nodo>: <mensaje>"`).

## Variables

Todas están en `.env.example`. Las no secretas están también en Easypanel → albaranes-api → Entorno. Los secretos (`ODOO_API_KEY`, `STORE_DSN` y las claves) están en `/root/albaranes-ia/.env`, montado en el contenedor como `/run/config/albaranes-ia.env`.

## Arrancar y desplegar

Los servicios ya están creados en Easypanel: `barcode-ocr` y `albaranes-api`, con origen *Upload* y build por `Dockerfile`.

```sh
scripts/desplegar.sh            # todo
scripts/desplegar.sh api        # solo albaranes-api
scripts/desplegar.sh ocr        # solo barcode-ocr
scripts/desplegar.sh n8n        # regenera n8n/workflows/*.json, los importa, los publica y reinicia n8n
```

- **Código:** se copia al origen de Easypanel (`/etc/easypanel/projects/ia-support/<servicio>/code`), así que un *Implementar* desde Easypanel construye lo mismo.
- **Flujos:** se generan con `n8n/build_workflows.py` a partir de las plantillas de `web/`. **No se editan a mano** los JSON de `n8n/workflows/`.
- **Reinicio de n8n:** es necesario porque la CLI no avisa al n8n en marcha. Corta unos segundos los demás flujos, y el chat de contactos pierde la memoria de las conversaciones abiertas.

### Montarlo desde cero

1. Ejecuta los datos de prueba. Crea el usuario de integración con su API key, el cliente y los pedidos de prueba, y deja la clave en `/tmp/albaranes_ia_apikey` del contenedor; pásala al `.env`. Haz un `pg_dump` antes.
   ```sh
   odoo shell -d odoo --no-http < scripts/datos_prueba.py
   ```
2. Crea el rol y la base de datos `albaranes_ia` en Postgres. La tabla la crea la API al arrancar.
3. Crea los servicios en Easypanel:
   - en `albaranes-api`, el montaje de enlace de `/root/albaranes-ia/.env` en `/run/config/albaranes-ia.env` y el entorno no secreto;
   - después, `scripts/desplegar.sh`.
4. En n8n, crea la credencial *Albaranes IA - Basic Auth* (id `AlbIaBasicAuth01`). La de OpenRouter ya existía.

## Pruebas

```sh
scp -P 22022 -r pruebas root@217.154.182.5:/root/albaranes-ia/
ssh -p 22022 root@217.154.182.5 sh /root/albaranes-ia/pruebas/pruebas.sh   # extremo a extremo
```

Resultado del 16/10/2026: 15 correctas y 0 fallos. Comprueba:
- salud de los servicios, `DRY_RUN` activo y lectura del ERP por JSON-2;
- 401 sin credenciales;
- número por visión y por código de barras, y detección de `12 → 10` y `12 → 9`;
- foto repetida sin duplicar, y foto que no es un albarán;
- lista, pantalla y API del reconocimiento;
- aprobar con rectificación simulada, y doble resolución rechazada.

**Ampliado el 22/10 y aún sin ejecutar entero.** Las comprobaciones nuevas se probaron una a una con curl:
- tipo `modificado` y `error`;
- fecha no válida en la lista;
- eliminar un aprobado da 409;
- reintentar el de error (mismo id, evento `reprocesar`) y eliminarlo después (404).

Cada ejecución crea reconocimientos nuevos de WH/OUT/00040 y 00041, con su nota en Odoo, y hace unas tres llamadas a la IA. El de error lo borra al final.

Otros ficheros de `pruebas/`:
- **`generar_foto_prueba.py`:** fotos sintéticas a partir del PDF del albarán, con tachones `barra:N`, `encima:N` y `garabato`, perspectiva, giro y sombra. Necesita pymupdf.
- **`prueba_rectificacion.py`:** rectificación real sobre WH/OUT/00042 y 00043. Se crean con:
  ```sh
  RECTIFICACION=1 odoo shell ... < scripts/datos_prueba.py
  ```
- **`subir.sh` y `pedir.sh`:** llamadas a los webhooks con las credenciales del `.env`, sin mostrarlas.

### Lectura de las fotos sintéticas (claude-sonnet-5.5, unos 13 s y 0,02 $ por albarán)

| Albarán | Cambio a mano | La IA lee | Resultado |
|---|---|---|---|
| WH/OUT/00040 | Gabinete 12 tachado con "/" y 10 al lado | 10 (93 %) | Revisión: modificada |
| | Caja 24 rayado, con 20 escrito encima, entre dos filas | Asigna el 20 a la fila de arriba (80 %) y deja la Caja como tachón ilegible | Revisión: dudosa, variación grande |
| | Alfombrilla 3 con un garabato | Ilegible (30 %) | Revisión: tachón ilegible |
| | Cubo 8 sin tocar | 8 (95 %) | Verificada |
| WH/OUT/00041 (operaciones) | Gabinete 12 → 9; Alfombrilla 3 con 5 encima | 9 (90 %) y 5 (70 %) | Revisión. El número sale del código de barras |

## Limitaciones y siguientes pasos

- **Cajas (`bbox`):** son aproximadas. Con fotos muy inclinadas pueden desplazarse una fila, pero sirven para llevar la vista a la zona.
- **Números entre filas:** si se escribe un número entre dos filas, el caso es ambiguo de verdad. El modelo lo marca como dudoso y lo decide la persona que revisa.
- **Una foto por albarán:** no se tratan los albaranes de varias páginas.
- **Datos guardados en n8n:** el flujo guarda las ejecuciones correctas, útil para depurar, y n8n guarda con ellas las cabeceras del webhook, incluida la de Basic Auth. En producción conviene `saveDataSuccessExecution: none` o un token por cabecera que se rote.
- **Caducidad de la API key:** la de Odoo caduca el 14/01/2027.
- **Producción (AS400/DB2):**
  - escribir el adaptador `erp/db2.py`;
  - decidir cómo se rectifica allí (albarán de abono o regularización);
  - imprimir el código de barras en su albarán, porque en el de Odoo no viene.
