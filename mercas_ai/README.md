# Mercas MCP Chat

Consolas de chat con IA integradas en el propio backend de Odoo, construidas sobre
`odoo_mcp_manager` (el MCP Gateway de Cybrosys). No requiere clientes externos (Claude
Desktop, curl, etc.) ni tener configurada una MCP API Key: todo se ejecuta por ORM dentro
del propio proceso de Odoo.

## Estado / continuidad (para retomar la sesión)

Todo lo descrito en este README está implementado y probado **por ORM** (`odoo-bin shell`,
simulando exactamente lo que hace cada botón). El comportamiento en navegador real (JS/CSS) no
siempre se ha podido verificar de primera mano en las sesiones de agente (sin ruta de red a
`localhost:8069` desde ese entorno) — confirmarlo visualmente sigue siendo responsabilidad del
usuario, pero un bug ya detectado y corregido así fue: el auto-scroll del historial
(`static/src/js/chat_fields.js`, widget `mercas_chat_history`) usaba
`useEffect((el) => {...}, () => [this.value, this.boxRef.el])` — Owl invoca el callback de
`useEffect` con las dependencias **por posición**, así que `el` recibía `this.value` (el string
HTML del historial), no `this.boxRef.el` (el nodo DOM); `el.scrollTop = el.scrollHeight` sobre
un string es un no-op silencioso, sin error en consola. Arreglado leyendo `this.boxRef.el` desde
el cierre en vez de por posición. Si aparece otro comportamiento raro de un widget Owl en este
módulo, sospechar primero de este mismo patrón (deps posicionales de `useEffect`) antes de asumir
un problema de timing/API de la build de Odoo 19.

El atajo de teclado (widget `mercas_chat_message`, mismo fichero) no usa este patrón (lee
`ev.target` directamente), así que no debería tener el mismo problema, pero sigue pendiente de
confirmación visual en navegador. Antes usaba Ctrl+Enter/Cmd+Enter; ahora Intro solo envía
directamente y Mayús+Intro inserta un salto de línea — revisar primero este archivo si hay dudas
sobre el atajo activo.

**Recordatorio operativo**: cada vez que se toque este módulo con Odoo ya arrancado, hay que
reiniciar el proceso para que los cambios se vean (ver "Limitaciones conocidas" más abajo) — es
la fuente más probable de "no veo el cambio" en la próxima sesión.

## Dependencias

| Módulo | Para qué |
|---|---|
| `odoo_mcp_manager` | Aporta `ai.provider`, `ai.model`, `ai.tool`, `ai.bot.conversation` y el motor de enrutado LLM (`LLMRouter`) que este módulo reutiliza. |
| `sale`, `purchase`, `account`, `stock` | Modelos sobre los que consultan las herramientas de informes (`sale.order`, `purchase.order`, `account.move`, `stock.move`). |
| `product_expiry` | Aporta `stock.lot.expiration_date`, usado por `stock_report` para mostrar la caducidad de cada lote (ver sección 2). |

## Qué instala

### 1. Fix: `ai.bot.channel.platform` sin la opción "Web Widget"

`odoo_mcp_manager` implementa el adaptador del canal Web (`_connect_web`, el controlador
`/bot/web`, las vistas), pero el campo `platform` de `ai.bot.channel` nunca incluye
`('web', 'Web Widget')` en su Selection — así que esa opción no aparece en el desplegable del
formulario de canales. `models/ai_bot_channel.py` lo corrige con un `selection_add`.

### 2. Cuatro herramientas de informe deterministas (`models/ai_tool.py`)

El problema que motivó este módulo: pedirle a la IA que sume importes a partir de un volcado
de registros (`search_records`) no funciona — ese tool ni siquiera expone campos financieros,
así que el modelo alucina totales. Estas herramientas hacen un `read_group` real en Odoo y
devuelven cifras exactas; la IA solo redacta la respuesta a partir de datos ya calculados.

| Tool | Modelo | Agrupa por | Suma | Extra |
|---|---|---|---|---|
| `sales_report` | `sale.order` | cliente (`customer`) y/o día | `amount_total` | |
| `purchase_report` | `purchase.order` | proveedor (`vendor`) y/o día | `amount_total` | |
| `invoice_report` | `account.move` (solo `state='posted'`) | cliente/proveedor y/o día | `amount_total` | `move_type`: `customer`/`vendor`/`all` |
| `stock_report` | `stock.move` (solo `state='done'`) | producto y/o día | `quantity` | `direction`: `in`/`out`/`internal`; `only_boxes`: solo productos con `is_box=True` (ver más abajo) |

**`stock_report` y el desglose por lote**: cuando `product` identifica exactamente uno o más
`product.product` concretos (nombre o referencia interna — ver "Limitaciones conocidas" sobre
`only_boxes`, que desactiva este desglose por ir dirigido a varios productos a la vez), la
herramienta añade una clave `lots` con las existencias actuales (`stock.quant`, ubicaciones
internas, cantidad > 0) agrupadas por `stock.lot`, ordenadas por caducidad más próxima primero
(FEFO): `lot` (nombre del lote), `supplier` (`stock.lot.partner_id`, de `mercas_base`),
`expiration` (`stock.lot.expiration_date`, de `product_expiry`) y `qty`. `_format_result` en
`domain_chat_mixin.py` lo añade como sección "Lotes en stock" tras el resumen de cantidades. Es
información de **existencias actuales**, no de los movimientos del rango de fechas consultado
(que es lo que agrega el resto de la tool) — por eso no depende de `date_from`/`date_to`.
Limitado a 15 lotes (`_stock_lots_detail(products, limit=15)`) para no disparar el tamaño de la
respuesta con productos con muchísimos lotes abiertos.

**Singular/plural en `product`**: el nombre se busca con `ilike` (substring), así que una
consulta en plural ("manzanas") no encontraría por sí sola productos guardados en singular
("MANZANA", "MANZANA ROJA"). `_singularize_es()` en `ai_tool.py` recorta la "s"/"es" final de
cada palabra del término antes del `ilike` sobre `product.name` (no sobre `default_code`, que no
pluraliza), para que la consulta encuentre también las variantes singulares y multi-palabra.

Parámetros comunes: `date_from` / `date_to` (`YYYY-MM-DD`), `group_by`. Estas herramientas
también quedan disponibles para el resto del ecosistema MCP (el chat general, el MCP Gateway
externo, Telegram/WhatsApp/Web) — no son exclusivas de la consola de este módulo.

**Permisos**: las cuatro tools consultan `sale.order`/`purchase.order`/`account.move`/
`stock.move`/`res.partner`/`product.product`/`stock.quant` vía `self._user_model(model_name)`
(heredado de `odoo_mcp_manager`: `self.env[model_name].with_user(self._effective_uid())`), nunca
con `.sudo()`. `_effective_uid()` resuelve al usuario real que pregunta — `mcp_user_id` del
contexto si viene de `chat_ai`/Discuss o de un cliente MCP autenticado con su propia API key, o
`self.env.uid` en cualquier otro caso (wizard incluido) — así que un usuario sin acceso de
lectura a alguno de esos modelos, o cuyas record rules multi-compañía no cubran los registros
consultados, recibe un `AccessError` real en vez de ver cifras a las que no debería llegar.

### 3. Una consola de chat en el menú **MCP Gateway**, restringida a su dominio de negocio

Toda la lógica (prompt de clasificación, reglas de negocio, extracción de parámetros,
formateo determinista) vive en un único sitio: `wizard/domain_chat_mixin.py`
(`MercasDomainChatMixin`, `models.AbstractModel`). Los dos wizards de abajo son
`_inherit = ['mercas.mcp.domain.chat.mixin']` — no llevan copia propia de esa lógica, solo
difieren en su `_conversation_prefix` (para no compartir historial) y en su vista/menú:

- **Chat IA** (`mercas.mcp.chat.wizard`, `ai_chat_wizard.py`) — **única consola visible por
  defecto**. `_conversation_prefix = 'backend'`. Conversación persistida en
  `ai.bot.conversation` (`platform='web'`, `platform_user_id='backend-<uid>'`).

- **Consultas IA (debug)** (`mercas.mcp.domain.chat.wizard`, `ai_domain_chat_wizard.py`) —
  **no borrado**: mismo mixin, `_conversation_prefix = 'domain'`. Su menú
  (`mcp_gateway_menu_domain_chat`) lleva `groups="base.group_no_one"`, así que solo aparece con
  el modo desarrollador activo (Ajustes → Activar modo desarrollador, o `?debug=1` en la URL).
  Se mantiene únicamente para depurar/comparar contra `ai_chat_wizard.py` sin tener que revertir
  código; en uso normal ambos wizards se comportan igual, con historiales de conversación
  independientes.

Ambas consolas responden **solo** preguntas de ventas, compras, facturación y stock. Una única
llamada corta al LLM clasifica la pregunta en uno de esos 4 dominios (o `otro`) y extrae los
parámetros de filtrado; si el dominio es `otro`, responde el mensaje fijo *"Sólo puedo responder
preguntas de VENTAS, COMPRAS, FACTURACIÓN Y STOCK."* sin llamar a ninguna tool. Si el dominio es
válido, ejecuta la tool determinista correspondiente y formatea el resultado en Python — **sin**
una segunda llamada de "humanizar" al LLM, por eso los importes nunca los redacta/parafrasea la
IA (siempre exactos, salen de Odoo).

Históricamente hubo un tercer modo: `ai_chat_wizard.py` usaba `LLMRouter` (el mismo router
genérico del bot gateway) para elegir libremente entre *cualquier* tool (`ask_ai`,
`search_records`, `create_record`, `update_record`, `delete_record`, `analyze_records`), y
humanizaba el resultado con una segunda llamada al LLM. Se retiró porque `LLMRouter` solo pasa
al modelo la `description` de una línea de cada tool — nunca el `input_schema` — así que no
tenía forma de conocer parámetros como `only_boxes`, ni las reglas de negocio de `prompts.py`, y
el paso de "humanizar" arriesgaba a que el LLM alterase cifras ya exactas al parafrasearlas. Esa
capacidad genérica sigue existiendo en `odoo_mcp_manager` (la usan Telegram/WhatsApp/Web bot
gateway), simplemente ya no está expuesta en este menú.

Ambas consolas recuerdan la conversación del usuario entre visitas al menú (botón "Nueva
conversación" para archivarla y empezar de cero) y usan siempre el proveedor de IA activo de
mayor prioridad configurado en **MCP Gateway → Providers**.

### 4. Instrucciones de negocio en dos capas

En **Ajustes → MCP Gateway → Chat IA** hay dos campos que se inyectan en el prompt de
clasificación (`_CLASSIFY_PROMPT`, definido una sola vez en `wizard/domain_chat_mixin.py`):

- **Instrucciones generales (fijas)** — de solo lectura en el UI, vienen de
  `prompts.py::BASE_BUSINESS_INSTRUCTIONS` (no editable desde Ajustes; para cambiarlas hay que
  tocar ese fichero y actualizar el módulo). Contenido actual:
  - Ceñir la respuesta exclusivamente al producto/cliente/proveedor que se pregunta, sin
    mezclar cifras de otros.
  - "Cajas" o "envases" no son un nombre de producto: se traducen al parámetro
    `only_boxes: true` del dominio `stock` (filtra `product_id.is_box = True`, campo de
    `mercas_base`), dejando `product` vacío salvo que además se nombre un producto concreto.
- **Instrucciones personalizadas** — campo de texto libre editable, guardado en
  `ir.config_parameter` (`mercas_mcp_chat.custom_instructions`) vía `get_values`/`set_values`
  en `models/res_config_settings.py`. Se añade al prompt en cada consulta.

  ⚠️ Los campos de settings que se persisten como `ir.config_parameter` con el atajo
  `config_parameter="..."` **solo admiten** boolean/integer/float/char/selection/many2one/
  datetime — un `fields.Text` con ese atajo revienta `res.config.settings` en cuanto alguien
  abre Ajustes (`Exception: Field ... must have type ...`). Por eso este campo usa
  `get_values`/`set_values` manuales en vez del atajo. Si se añade algún campo de texto largo
  más a settings en este módulo, seguir el mismo patrón.

### 5. Widgets de chat (`static/src/js/chat_fields.js`)

Dos widgets de campo (Owl) usados en ambas vistas de wizard:

- `mercas_chat_history` (en `history_display`, tipo Html): envuelve el contenido en un
  `<div class="o_mercas_chat_history">` con scroll propio (`max-height: 60vh`) y lo desplaza
  al fondo en cada montaje/actualización (`useEffect` sobre `el.scrollTop = el.scrollHeight`).
- `mercas_chat_message` (en `message`, extiende el `TextField` estándar): añade un listener de
  `keydown` que, con Intro (sin Mayús, y no durante composición IME), guarda el valor en el
  registro (`record.update(...)`) y hace click en el botón con clase `o_mercas_chat_send` (el
  "Enviar" de cada formulario) — de ahí que ambos botones "Enviar" lleven esa clase además de
  `btn-primary`. Mayús+Intro no se intercepta, así que sigue insertando un salto de línea normal
  del `textarea`. El mismo `useEffect` que engancha el `keydown` también hace `el.focus()` (y
  coloca el cursor al final del texto) cada vez que el `textarea` se monta — como `action_send`
  recarga el formulario entero (`ir.actions.act_window`), sin esto el foco se perdía tras cada
  envío y había que volver a hacer click en el campo para seguir preguntando.

Ambas vistas de formulario (`ai_chat_wizard_views.xml`, `ai_domain_chat_wizard_views.xml`)
deliberadamente no usan `<sheet>`: desde Odoo 16.3, un `<form>` sin `<sheet>` recibe
automáticamente la clase `o_form_nosheet` (`form_compiler.js`), que ocupa todo el ancho
disponible en vez del `max-width` centrado que aplica `.o_form_sheet_bg`
(`form_controller.scss`). Es el mecanismo soportado por el framework, no un CSS a mano — si se
le vuelve a añadir `<sheet>`, el chat volverá a quedarse estrecho.

Como "todo el ancho disponible" quedaba demasiado ancho en monitores grandes (el historial y el
input se estiraban de punta a punta), todo el contenido de cada formulario va envuelto en un
`<div class="o_mercas_chat_container">` (`chat_fields.css`): `max-width: 700px` y
`margin-right: auto` — limita el ancho sin centrar (a diferencia de `.o_form_sheet_bg`, que
centra con `margin: auto` en ambos lados), así el chat queda pegado a la izquierda dejando hueco
libre a la derecha en vez de ocupar toda la pantalla. Bajado de 900px a 700px tras comprobar en
vivo (`javascript_tool`, `getBoundingClientRect`) que ninguna burbuja real superaba ~650px de
ancho — con 900px la fila de mensaje (que sí ocupa el 100% del contenedor) se veía
desproporcionadamente más ancha que las burbujas de encima.

El campo `message` y los botones "Enviar"/"Nueva conversación" ya no van en un `<group>` propio
debajo del mensaje: están en un único `<div class="o_mercas_chat_row">` (flex, `align-items:
flex-end`) junto con `<div class="o_mercas_chat_actions">` (los dos botones en fila, uno junto al
otro — `flex-direction: row`), de modo que ambos quedan al final de la misma línea que el campo
de mensaje, anclados a su parte inferior.

**Por qué el `textarea` necesitaba CSS explícito para ocupar todo el ancho de la fila**:
`.o_field_widget` (y el `<textarea class="o_input">` que envuelve) traen `display: inline-block`
por defecto en el core de Odoo (`fields.scss`) — dentro de un `<group>` normal eso no se nota
porque el grid del group ya les da un ancho de celda, pero en nuestro `<div class="o_mercas_chat_row">`
(flex a mano, sin `<group>`) un elemento `inline-block` no se estira solo: el `.o_field_widget`
crecía como *flex item* (`flex: 1 1 auto`) pero el `<textarea>` de dentro se quedaba a su ancho
intrínseco (~20 columnas), así que la fila se veía ocupando solo ~2/3 del contenedor. Arreglado
forzando `display: block; width: 100%` en cascada: `.o_field_widget` → su `<div>` interno → el
`<textarea>` (`chat_fields.css`).

**Ancho de las burbujas del historial**: cada mensaje en `_render_history`
(`domain_chat_mixin.py`) es un `<div style="display:inline-block;max-width:...">` con estilos
inline (no CSS de archivo, para no depender del bundle de assets en el HTML que se guarda en
`history_display`). Estaba en `max-width:75%` del contenedor ya limitado a 900px
(`o_mercas_chat_container`), lo que dejaba las burbujas visualmente estrechas (~50% del ancho de
pantalla en monitores grandes) con mucho hueco vacío a su lado. Subido a `max-width:92%` — en la
práctica el tope real casi nunca se llega a aplicar: las burbujas se ajustan a su contenido
(`display:inline-block`) y ninguna respuesta real observada supera ~650px, muy por debajo del
92% de 700px. El 92% solo actúa como límite de seguridad ante una respuesta excepcionalmente
larga en una sola línea sin saltos.

## Limitaciones conocidas

- **`stock_report` sin filtro de producto ni `only_boxes`**: si no se especifica ninguno de
  los dos, la cantidad total se suma entre productos que pueden tener unidades de medida
  distintas (unidades, kg, litros…) y no se muestra ninguna UdM en el resumen. Es una
  simplificación deliberada para mantener la tool ligera.
- **`invoice_report` y ambigüedad cliente/proveedor**: si la pregunta no dice si son facturas
  emitidas o recibidas, se traen ambas mezcladas (`move_type='all'`). El clasificador intenta
  inferirlo, pero en preguntas ambiguas puede no acertar.
- **Tras instalar o actualizar el módulo, si Odoo ya estaba en marcha, hace falta reiniciar el
  proceso.** El mecanismo estándar de Odoo para que un proceso vivo recargue su registro tras
  cambios hechos desde otro proceso (`orm_signaling_registry`) no se ha mostrado fiable en este
  entorno de desarrollo — el proceso en marcha puede seguir sirviendo el registro antiguo
  (`KeyError` / 404 en el modelo, o una vista/campo desactualizado) pese a que la base de datos
  ya tiene el módulo actualizado. Reiniciar el proceso de Odoo lo soluciona siempre; hasta ahora
  no se ha encontrado una vía fiable de forzarlo en caliente en este entorno.
- La primera pregunta tras un rato de inactividad de Ollama tarda notablemente más (~20-60 s):
  es el tiempo que tarda Ollama en recargar el modelo en memoria, no algo controlable desde
  este módulo.
- El comportamiento de los widgets JS (auto-scroll, atajo de teclado) no se ha verificado en
  un navegador real — ver sección "Estado / continuidad" arriba.

## Ampliar a un nuevo dominio

1. Añadir una tool determinista nueva en `models/ai_tool.py` (`_execute_builtin` + método
   `_builtin_<nombre>`), siguiendo el patrón de `_read_group_amount` si es un total monetario.
2. Registrar el `ai.tool` correspondiente en un XML de datos (ver
   `data/ai_tool_domain_reports.xml`).
3. En `wizard/domain_chat_mixin.py`: añadir la clave a `_DOMAIN_TOOL`, describir el dominio en
   `_CLASSIFY_PROMPT`, y añadir el caso en `_build_tool_params` / `_format_result`. Es el único
   sitio a tocar — tanto `ai_chat_wizard.py` (consola visible) como
   `ai_domain_chat_wizard.py` (gemelo debug-only) heredan de este mixin (`_inherit =
   ['mercas.mcp.domain.chat.mixin']`) sin llevar copia propia de la lógica, así que no hay nada
   que sincronizar entre ambos.
4. Si el dominio necesita su propio glosario de negocio, añadirlo a
   `prompts.py::BASE_BUSINESS_INSTRUCTIONS`, que ya usa el mixin en vez de tocar
   `_CLASSIFY_PROMPT` directamente.

No hace falta tocar `odoo_mcp_manager`.
