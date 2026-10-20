# albaranes-ia: detección de albaranes modificados a mano

Prototipo para detectar los cambios que hace el comercial a mano sobre el albarán impreso (tacha la cantidad con una "/" y escribe otra, o la sobrescribe). Lee la foto del albarán firmado con un modelo de visión, la compara con el ERP y deja a Administración una pantalla para aprobar o corregir. Después rectifica el albarán y la factura en el ERP, por ahora en modo simulación (`DRY_RUN`).

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

## Estado y cómo retomarlo (20/10/2026)

**Hecho:** las fases A–E están desplegadas y probadas en el entorno de pruebas (ver Pruebas). Primera prueba real del usuario, el 16/10:
- **Foto:** `IMG_5412.HEIC`, incidencia **#17**, WH/OUT/00040 identificado por visión.
- **Lectura:** acertó los dos cambios a mano: Caja 24 → 20 (92 %) y Cubo 8 → 7 (85 %, dudosa). Las otras 3 líneas, verificadas.
- **Resolución:** **aprobada** (sin nombre de usuario).
- **Plan `DRY_RUN`:** devolución de 4 Cajas y 1 Cubo, validarla y crear un abono en borrador desde S00026. La factura INV/2026/00010 ya está publicada.

**Pendiente de decisión del usuario:**
- **Rectificar de verdad la #17:** `DRY_RUN=false` en Easypanel y relanzar `/erp/rectificar` con su plan. **No hacerlo sin confirmación.**
- **Commit:** `albaranes-ia/` sigue sin trackear en git. Si se borra, solo queda lo desplegado en el servidor.

**Cambios posteriores a las pruebas:**
- La tabla de revisión se ordena por la posición en la foto (`bbox[1]`) y ya no pone las dudosas primero.

**Incidencias conocidas:**
- **DNS con Cloudflare WARP:** en el Mac del usuario, WARP (DNS `127.0.2.2`) devuelve `SERVFAIL` para `*.kw2y1s.easypanel.host`, y los DNS públicos sí lo resuelven. Para comprobar el servidor sin depender de WARP:
  ```sh
  curl --resolve ia-support-n8n.kw2y1s.easypanel.host:443:217.154.182.5 …
  ```
- **`API_TOKEN` sin definir:** la API no está expuesta a Internet. En producción hay que ponerlo.
- **Un solo usuario Basic Auth (`revision`):** el campo "usuario" de la revisión es texto libre. En producción, un proxy con SSO (Cloudflare Access, Authelia…).

**Producción:** necesita n8n, albaranes-api, Postgres para las incidencias, la clave del modelo y HTTPS. `barcode-ocr` es opcional. En lugar de Odoo, un adaptador AS400 en `erp/`, cuya parte delicada es rectificar con los programas del ERP. Además:
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
                                 4 lectura línea a línea ──────► OpenRouter / Anthropic (JSON Schema estricto)
                                 5 reglas (nodo Decidir) → verificado | pendiente_revision
                                 6 guardar resultado + nota en el historial del albarán
 Administración ◄── pantalla ── "Albaranes IA - Revisión"
                                 GET  /albaranes/revision            lista
                                 GET  /albaranes/revision/{id}       pantalla HTML
                                 GET  /albaranes/api/incidencia/{id} JSON + imagen
                                 POST /albaranes/api/incidencia/{id}/resolver  aprobar | corregir | rechazar
                                      └ rectificar ────────────► albaranes-api /erp/rectificar (DRY_RUN)
```

| Servicio (Easypanel) | Host interno | Qué hace |
|---|---|---|
| `barcode-ocr` | `ia-support_barcode-ocr:8000` | FastAPI + zxing-cpp + OpenCV. `POST /decode` devuelve el código o `null` |
| `albaranes-api` | `ia-support_albaranes-api:8000` | Incidencias en su propia BD, preparación e interpretación de la lectura por IA, y **capa ERP** |
| n8n | `ia-support_n8n` | Orquesta los flujos y sirve los webhooks y las páginas HTML |
| BD `albaranes_ia` | `ia-support_surtidos-db` | Incidencias: foto, lectura, decisión, revisión y rectificación. Base de datos y rol propios, no la del ERP |

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

- **Misma foto:** la identifica el SHA-256 del fichero. Si se sube otra vez, devuelve la misma incidencia (`duplicada: true`, unos 0,2 s) sin volver a llamar a la IA ni escribir otra nota. Con `reprocesar=true` se vuelve a leer, salvo que ya esté resuelta.
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

### Revisar

https://ia-support-n8n.kw2y1s.easypanel.host/webhook/albaranes/revision. La pantalla:
- **Foto:** a la izquierda, con zoom (rueda o pellizco), arrastre y giro. Al tocar una fila salta a su `bbox`.
- **Tabla:** a la derecha, en el mismo orden que en la foto (de arriba abajo; las que no se ven en ella, al final). Las líneas que hay que revisar van resaltadas.
- **Botones:** *Aprobar* usa las cantidades de la IA, *Corregir y aprobar* las que hayas escrito, y *Rechazar* (pide confirmación) no toca el ERP.

n8n sirve el HTML con `Content-Security-Policy: sandbox` (sin `allow-same-origin`). Por eso la página lleva los datos incrustados y envía un formulario normal en vez de usar `fetch`.

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
- lista, pantalla y API de incidencia;
- aprobar con rectificación simulada, y doble resolución rechazada.

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
