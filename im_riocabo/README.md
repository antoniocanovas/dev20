# IM Riocabo (v20)

Avisos por **chat directo** (Conversaciones) cuando se asigna trabajo a alguien.
Riocabo quiere gestionarlo todo desde el chat; los avisos estándar de Odoo
(bandeja de entrada o correo) se mantienen además de estos.

## Qué hace

| Cuándo | A quién | Mensaje |
|---|---|---|
| Se crea una tarea | Cada persona asignada, salvo quien la crea | "Nueva tarea asignada: <enlace>" + proyecto, cliente, fecha límite |
| Se añaden personas a una tarea (`user_ids`) | Solo las personas nuevas | Igual que el anterior |
| Se crea una actividad para otra persona | La persona responsable (`user_id`) | "Nueva actividad asignada en <Modelo> <enlace>" + tipo, resumen, fecha de vencimiento |

- El chat es entre **quien asigna** y **quien recibe**. Si asigna el sistema (cron,
  alta de usuario), el remitente es OdooBot.
- El texto sale en el **idioma de quien recibe** (`i18n/es.po`).
- Nunca se avisa a uno mismo, ni a usuarios portal o archivados.
- Solo avisa si quien hace la acción es usuario interno.
- Desactivar avisos (importaciones, scripts): contexto `im_riocabo_no_notify=True`.
- Si el aviso falla, se registra un `WARNING` en el log y la tarea o actividad se
  crea igualmente (savepoint, sin `cr.commit()`).

## Estructura

- `models/discuss_channel.py`: `_im_riocabo_should_notify()` y `_im_riocabo_notify(user, body)`.
  Usa `discuss.channel._get_or_create_chat()` (API v18+).
- `models/project_task.py`: `create` / `write` (solo si cambia `user_ids`) y el texto del mensaje.
- `models/mail_activity.py`: `create` y el texto del mensaje.

## Historia

Viene de `addons-riocabo/im_riocabo` (v17, autor Punt Sistemes). Al migrar a v20
se rehízo entero porque el original:

- usaba `discuss.channel.channel_get`, que **no existe en v20** (al crear tareas o
  actividades habría dado error);
- enviaba el mensaje a un chat **de quien crea consigo mismo**, no a la persona asignada;
- comparaba `res_model_id.name` (descripción) con nombres técnicos, así que el tipo
  de documento salía siempre vacío;
- hacía `cr.commit()` dentro de `create` y no admitía creación múltiple.

## Estado

- 2026-11-04: v20.0.1.0.0 instalado en la base local `cat20`.
- Probado en una base desechable: casos de crear tarea, añadir asignados,
  cambio sin asignación, actividad para otra persona, actividad propia y
  `im_riocabo_no_notify`. Todos correctos, incluido el idioma (es / en).
- Pendiente: que Riocabo lo valide con usuarios reales.

## Ideas si piden más

- Avisar también al **reasignar** una actividad (`write` de `user_id`).
- Avisar al cambiar de etapa una tarea o al acercarse la fecha límite.
- Si resultan demasiados avisos, desactivar los correos estándar desde las
  preferencias de cada usuario (Notificación: "Gestionar en Odoo").
