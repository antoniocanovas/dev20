# Chat AI

Añade un usuario/partner "Asistente IA" con el que cualquier usuario interno autorizado puede
chatear directamente desde Discuss, igual que con OdooBot — de hecho está calcado del propio
`mail_bot` de Odoo (`odoo/addons/mail_bot/models/discuss_channel.py` y `mail_bot.py`), solo que
con nuestro propio bot en vez de `base.partner_root` y con la respuesta delegada a un modelo
sobreescribible por otros módulos en vez de las respuestas enlatadas de OdooBot.

## Estado / continuidad (para retomar la sesión)

Instalado y probado por ORM (`odoo-bin shell`, contra la base `mercas`) el 2026-08-01:

- **Bug real encontrado y corregido durante la primera instalación**: `models/ai_bot_conversation.py`
  extendía `platform` con `ondelete={"discuss": "set default"}`, copiado del patrón de
  `mercas_ai/models/ai_bot_channel.py`. Pero el campo base `platform` en
  `ai.bot.conversation` (a diferencia de `ai.bot.channel`) es `required=True` **sin** `default` —
  `'set default'` exige que el campo base tenga uno, si no revienta la carga del registro entero
  (`AssertionError` en `odoo/orm/fields_selection.py`). Corregido a `ondelete={"discuss":
  "cascade"}` (si se llega a desinstalar el módulo, se borran las conversaciones huérfanas en vez
  de dejarlas con un valor de `platform` indefinido).
- **Verificado por ORM** (usuarios y canales de prueba creados y luego revertidos con
  `env.cr.rollback()`, nada quedó persistido):
  - El usuario del bot no puede autenticarse (`_check_credentials` lanza `AccessDenied` pase lo
    que pase).
  - `base.user_admin` pertenece a `chat_ai.group_ai_chat_user` (seed de
    `security/chat_ai_security.xml` confirmado en base real).
  - Un usuario sin el grupo recibe el mensaje fijo de "servicio no habilitado" — sin crear
    `ai.bot.conversation` ni llamar al LLM.
  - Un usuario con el grupo pero sin acceso a Ventas, al ejecutar `sales_report`, recibe un
    `AccessError` real de Odoo (bloqueado por las ACL de `sale.order`) en vez de ver cifras —
    confirma que el fix de permisos de `mercas_ai` (`_user_model()` en vez de `.sudo()`)
    funciona de extremo a extremo.
  - El mismo tool como `base.user_admin` sí devuelve datos reales.
  - Confirmado directamente contra el código fuente de Odoo 19
    (`odoo/orm/environments.py:81`): `.sudo()` solo cambia `env.su`, nunca `env.uid` — por eso
    `_effective_uid()` resuelve siempre al usuario real aunque la tool se busque con `.sudo()`.

- **No verificado todavía**: el flujo conversacional completo con un proveedor de IA real
  (`_classify` vía `ai.provider.chat()`) — depende de tener Ollama (u otro proveedor) arriba y
  puede tardar 20-60s en el primer arranque del modelo (ver README de `muk_mercas_ai`). Las pruebas
  de permisos de arriba llaman a `ai.tool.execute()` directamente, sin pasar por el LLM, así que
  no dependen de ello.

- **Pendiente de quien retome la sesión**: el proceso de Odoo que sirve el navegador (el que
  gestiona el usuario, no este agente) seguía corriendo con el registro antiguo tras esta
  instalación — instalar/actualizar módulos con el proceso ya arrancado no se refleja en caliente
  en este entorno (mismo problema ya documentado en el README de `mercas_ai`). Hace falta
  reiniciarlo a mano para poder probar el chat con la IA en Discuss desde el navegador.

## Dependencias

| Módulo | Para qué |
|---|---|
| `odoo_mcp_manager` | Aporta `ai.tool`/`ai.provider` (el `chat.ai.responder` por defecto llama a `ask_ai`) y `ai.bot.conversation`, reutilizado aquí para persistir el historial de cada canal de Discuss. |
| `mail` | `discuss.channel`, el hook `_message_post_after_hook`. |

## Qué instala

### 1. El usuario del bot (`data/chat_ai_bot_data.xml`)

Un `res.users` real (no solo un `res.partner`) llamado "Asistente IA", `login=chat_ai_bot`. Es un
`res.users` de verdad (no un simple partner) porque Discuss necesita un usuario interno
(`share=False`) para que aparezca como contacto normal. Solo pertenece a `base.group_user` — no
tiene ni necesita ningún grupo de acceso a datos, porque **nunca ejecuta nada él mismo**: cada
consulta a una `ai.tool` se ejecuta con los permisos reales del humano que pregunta (ver más
abajo), nunca con los del bot.

**El login está bloqueado en dos capas independientes:**
1. No se le asigna contraseña en el XML.
2. `models/res_users.py::ResUsers._check_credentials` intercepta explícitamente ese `user_id` y
   lanza `AccessDenied` siempre, sin excepción. Esto es deliberado y no es redundante: confiar
   solo en "no tiene contraseña" es fragil — un flujo de reset de contraseña o un admin
   despistado podría dársela más adelante. El bloqueo duro en `_check_credentials` cierra la
   puerta pase lo que pase.

### 2. El grupo "Conversaciones IA" (`security/chat_ai_security.xml`)

`chat_ai.group_ai_chat_user` — quien no pertenezca a él recibe siempre el mensaje fijo *"No
tienes habilitado este servicio, habla con tu administrador"* en vez de una respuesta real, y no
se gasta ninguna llamada al LLM en generarla.

- `base.user_admin` se añade a este grupo explícitamente.
- Además, el grupo `odoo_mcp_manager.group_mcp_consent_approver` (quien puede aprobar tools
  sensibles) pasa a implicar este grupo (`implied_ids`) — quien puede aprobar acciones sensibles
  de la IA también puede hablar con ella, sin tener que mantener las dos listas de usuarios a
  mano. No se toca el fichero de `odoo_mcp_manager`: se extiende su grupo desde un `<record>` con
  el mismo id completo (`odoo_mcp_manager.group_mcp_consent_approver`) en nuestro propio XML.
- Ambos registros van en `noupdate="0"` a propósito (igual que hace `odoo_mcp_manager` con ese
  mismo grupo): así el alta de `base.user_admin` se resincroniza en cada actualización del
  módulo y no se pierde si alguien lo quita por error.

### 3. El enganche con Discuss (`models/discuss_channel.py`, `models/chat_ai_bot.py`)

Mismo punto exacto que usa el propio Odoo para OdooBot:
`discuss_channel._message_post_after_hook(message, msg_vals)`. Tras cada mensaje posteado en
cualquier canal, `chat.ai.bot._apply_logic()`:

1. Ignora el mensaje si el autor ya es el propio bot (evita un bucle infinito al postear su
   respuesta) o si no es un `message_type='comment'` normal.
2. Ignora cualquier canal que no sea un chat 1:1 (`channel_type == 'chat'`) donde el bot sea
   miembro — nunca responde en canales de grupo ni públicos, aunque alguien lo añada allí.
3. Comprueba el grupo `chat_ai.group_ai_chat_user` del autor real del mensaje (`self.env.user`,
   que en este punto es quien de verdad envió el mensaje desde su propia sesión — no hay sudo de
   por medio). Si no pertenece, responde el mensaje fijo de "servicio no habilitado" sin más.
4. Si pertenece, delega en `chat.ai.responder._get_reply(text, history)` (ver siguiente punto) y
   persiste el intercambio en `ai.bot.conversation` (`platform='discuss'`,
   `platform_user_id=<id del canal>` — un historial independiente por canal/usuario, igual que ya
   ocurre para telegram/whatsapp/web).

Todo el bloque está envuelto en un `try/except` amplio en `discuss_channel.py`: un fallo aquí
nunca debe poder romper el posteo normal de un mensaje en cualquier otro canal de Discuss del
resto de la instalación.

**Punto de seguridad clave**: la respuesta se genera en el mismo proceso/transacción que el
propio `message_post` del usuario — nunca a través del gateway HTTP `/mcp_gateway` con la API key
compartida (esa API key colapsa a todo el mundo en una única identidad). Como consecuencia, si la
tool que acaba resolviendo la pregunta usa `ai.tool.execute()` sin más (el flujo genérico de
`odoo_mcp_manager`, ya no vía `.sudo()` tras su actualización — ver `models/ai_tool.py`
`_user_model()`/`_effective_uid()` en ese módulo), se ejecuta con los permisos ACL/record rules
reales del usuario humano que preguntó, no con superusuario ni con el usuario del bot.

### 4. `chat.ai.responder` — el punto de extensión para la lógica de negocio

`models/chat_ai_responder.py` define un `models.AbstractModel` con un único método,
`_get_reply(text, history)`, y una implementación por defecto: un passthrough sencillo a la tool
genérica `ask_ai` de `odoo_mcp_manager`, sin ninguna restricción de dominio. `chat_ai` no asume
qué módulo de negocio (si alguno) está instalado.

Los módulos de negocio deben hacer `_inherit = 'chat.ai.responder'` y sobreescribir
`_get_reply` con su propia clasificación/tools — ver `mercas_ai/models/chat_ai_responder.py`,
que enruta hacia sus 4 tools de informes (`sales_report`/`purchase_report`/`invoice_report`/
`stock_report`) reutilizando `mercas.mcp.domain.chat.mixin._classify`/`_build_tool_params`/
`_run_report` en vez del `LLMRouter` genérico — mismo motivo por el que `mercas_ai` ya lo
evita en su propia consola (ver el README de ese módulo, sección 3): `LLMRouter` no ve el
`input_schema` de cada tool, así que no sabría rellenar `customer`/`date_from`/`group_by`.

### 5. Onboarding proactivo (`models/res_users.py::_on_webclient_bootstrap`)

Para que un usuario autorizado no tenga que adivinar que el bot existe ni buscarlo a mano en
"Nuevo mensaje" de Discuss, se engancha el mismo hook que usa OdooBot para su propio onboarding
(`res.users._on_webclient_bootstrap`, `mail_bot/models/res_users.py::_init_odoobot`): la primera
vez que un usuario del grupo carga el cliente web, se crea (o reutiliza) el chat 1:1 con el bot
vía `discuss.channel._get_or_create_chat()` y se postea un mensaje de bienvenida — el canal
aparece solo en su barra lateral de Discuss, sin acción manual. Un campo `chat_ai_greeted`
evita repetir el saludo en cada carga de página. Todo el método va envuelto en `try/except`: un
fallo aquí no debe poder romper la carga del cliente web para nadie.

## Limitaciones conocidas / decisiones deliberadas

- La respuesta se genera **de forma síncrona**, dentro del mismo `message_post` que la dispara —
  igual que OdooBot. Para un LLM esto añade unos segundos de latencia a la petición de envío del
  mensaje del usuario; es una limitación conocida y aceptada por simplicidad (evita gestionar un
  cursor/hilo en segundo plano). Si en el futuro la latencia percibida es un problema, migrar a
  un hilo en segundo plano como ya hace `odoo_mcp_manager` para el adaptador de Discord
  (`controllers/bot_gateway_controller.py`, respuesta diferida tipo 5) es el patrón a seguir.
- Este módulo no incluye ninguna lógica de negocio propia — instalarlo solo (sin `mercas_ai`
  u otro módulo que sobreescriba `chat.ai.responder`) deja el bot respondiendo con un `ask_ai`
  genérico, sin acceso a ningún dato de Odoo.
