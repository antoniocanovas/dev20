# Expedientes (`project_task_touch`)

Aplicación **Expedientes** con la experiencia táctil de `scrap_touch`. Junta las tareas de proyectos y las actividades. Depende solo de `project`. Versión 20.0.1.0.0. Los datos de ejemplo (plantillas y expedientes) están en `scrap_demo` (`demo_files.py`).

## Parametrización

- **Proyecto y plantilla** (`project.project`, pestaña *Ajustes*): *Mostrar en Expedientes* (`touch_ok`).
  - En Odoo 20 no existe `project.template`: una plantilla es un proyecto con `is_template`, así que un mismo campo sirve para las dos cosas.
  - Un proyecto creado desde una plantilla marcada sale marcado: el campo se copia.
- **Plantilla de origen** (`touch_template_id`): Odoo no guarda de qué plantilla sale un proyecto. Este módulo la apunta en `action_create_from_template`, que es lo que usa el filtro de plantilla. Los proyectos anteriores al módulo no la tienen y se ven en *Sin plantilla*.
- **Actividad** (`mail.activity`, formulario emergente): *Mostrar en Expedientes* (`touch_ok`).
- **Compañía** (pestaña *Expedientes*): *Modelos de las actividades de expedientes*, por ejemplo `hr.employee`. Las actividades nuevas de esos modelos salen con `touch_ok` marcado, y se puede desmarcar a mano.

## Pantalla (`/odoo/expedientes`)

- **Tareas / Actividades**: dos botones grandes con su contador.
  - **Tareas**: la **kanban estándar de tareas** incrustada (vista `project_task_view_kanban_touch`, primaria y heredada de `project.view_task_kanban`), agrupada por estado.
    - Columnas: En curso, Cambios solicitados, Aprobada y En espera. Con el botón *Cerradas* (el mismo que en Actividades), Hecha y Cancelada.
    - Las columnas vacías también salen, para poder arrastrar tareas a ellas. Esto lo hace `group_expand` de `state` con `touch_states` en el contexto, y solo en esta pantalla.
    - Fechas límite con el widget estándar `relative_date`: en rojo y negrita si están vencidas, en amarillo y negrita si son de hoy (kanban y lista). En las tarjetas de Actividades, la fecha con los mismos colores.
    - Orden en cada columna: primero la fecha límite más cercana (las que no tienen van al final) y después la prioridad más alta.
    - Etiquetas, subtareas (contador y lista desplegable, ocultas como tareas sueltas), actividades, prioridad, estado y drag & drop son los del estándar.
    - Al cambiar el estado desde la tarjeta, la tarea pasa a su columna en el momento (`js_class` `project_task_touch_kanban`, que recarga la kanban tras guardar).
    - No hay creación rápida en las columnas: se usa *Nueva tarea*. La tarea se abre en un diálogo.
    - Botones **Kanban / Lista**, como el selector de vistas de Odoo. La lista es la estándar de tareas (`project_task_view_list_touch`, heredada de `project.view_task_tree2`), sin agrupar, con el mismo orden, filtros y buscador, y con la columna *Fecha límite* visible por defecto. La vista elegida se recuerda en cada dispositivo (`localStorage`).
    - **Subtareas en la lista**: junto al nombre, un botón con las cerradas/total (o **+** si no tiene) abre bajo la fila sus subtareas abiertas: ✓ para cerrarlas, un desplegable para cambiar su estado y un cuadro para añadir otra (con su proyecto y sus personas), como el contador de subtareas de la kanban. Widget `project_task_touch_name_subtasks` y métodos `get_subtasks` / `create_subtask`.
    - **Dependencias**: salen todas las tareas; las que dependen de otras abiertas están *En espera* (reloj de arena) y Odoo las pasa solas a *En curso* al cerrar aquellas.
  - **Actividades**: las marcadas, en columnas Vencidas / Hoy / Planificadas. La tarjeta abre el documento.
    - El botón *Hecho* abre el popover estándar del chatter (`ActivityMarkAsDone`): pide el resumen y ofrece *Hecho*, *Hecho y programar la siguiente* (asistente estándar `mail.activity.schedule`) o *Descartar*.
    - Con *Cerradas*: las hechas (Odoo 20 las archiva con su fecha y su resumen), en una columna, de la más reciente a la más antigua.
- **Filtros** (en Tareas): primero la plantilla (con la opción *Sin plantilla*) y después el proyecto de esa plantilla. Se aplican al momento, como en *Disponibles* de `scrap_crm`: `get_tasks` devuelve el dominio y la pantalla se lo pasa a la kanban.
- **Buscador**: busca en la tarea, el proyecto, el cliente (`partner_id`), las etiquetas y la persona asignada. En Actividades busca en el resumen, el tipo, el documento y la persona asignada.
- **Nueva tarea**: se elige el proyecto (o se usa el filtrado) y después el nombre y la fecha límite.
- **Nuevo expediente**: se elige la plantilla (o se usa la filtrada) y después el nombre y la fecha de inicio. Crea el proyecto con `action_create_from_template`, con sus tareas, y lo deja filtrado.
- **Fechas límite desde la plantilla** (también al crear desde Proyecto): Odoo no copia la fecha límite de las tareas. Este módulo la pone en cada tarea y subtarea con el mismo desfase que tiene en la plantilla desde su fecha de inicio (o, si no la tiene, desde su fecha límite más temprana), contado desde el inicio del expediente. Si la plantilla no tiene fechas planificadas, el expediente termina con su última fecha límite; si las tiene, dura lo mismo que ella (lo hace Odoo). `project.project._touch_copy_deadlines`.

## Tests

```
cd /Users/acanovas/pycharmprojects/20odoo
PYTHONPATH=<scratchpad>/pylib /Users/acanovas/pycharmprojects/venv312/bin/python odoo-bin \
  -c /Users/acanovas/pycharmprojects/conf/odoo20com.conf -d <bd_prueba> -i project_task_touch \
  --test-tags /project_task_touch --stop-after-init --http-port 8079 --gevent-port 8084
```

2026-11-12: 12 tests, 0 fallos (11 de modelo y 1 recorrido táctil: orden, subtareas en la lista, arrastre, cambio de estado en la tarjeta, búsqueda mientras se escribe y actividades). Con `-i scrap_demo --test-tags /scrap_crm,/scrap_demo,/project_task_touch`: 20 tests, 0 fallos.

Capturas en móvil y tableta: un script con Chrome sin interfaz por el protocolo DevTools (iniciar sesión con `requests` en `/web/session/authenticate`, pasar la cookie, `Emulation.setDeviceMetricsOverride`, `Page.captureScreenshot`). El Chrome del usuario no se deja redimensionar y Odoo no se deja meter en un iframe. Tras cambiar SCSS/JS hay que reiniciar el servidor: guarda el paquete de estilos en memoria.

## Estado en cat20 (2026-11-12)

- Instalado y actualizado con todo lo anterior (`scrap_crm` 20.0.1.2.0, `scrap_demo` 20.0.1.2.0). El usuario arranca el servidor desde PyCharm.
- Datos: proyecto *Peticiones de piezas (demo)* marcado y con fechas límite puestas a mano; las cuatro plantillas de `scrap_demo` y sus expedientes, creados con `create_files` desde `odoo-bin shell` (el hook solo corre al instalar) y con fechas de inicio y fin y fechas límite; el usuario creó *Gerardo Muñoz* (plantilla *Formación de taller*), completado con las fechas de su plantilla.
- Copias en `/Users/acanovas/pycharmprojects/backups/cat20_2026111*_*.dump`; la última, `cat20_20261112_1113_antes_fechas_plantillas.dump`.
- Pendiente: que el usuario reinicie el servidor para que los expedientes nuevos reciban las fechas de su plantilla (código Python nuevo), y que lo pruebe creando uno.

## Pendiente o por decidir

- **Ofrecido y sin respuesta:** un botón *Solo realizables* junto a *Cerradas* para ocultar las tareas *En espera* (que dependen de otras abiertas).
- En Actividades no se aplican los filtros de plantilla y proyecto, porque las actividades pueden ser de cualquier modelo. Actividades solo tiene columnas (no lista); ofrecido añadir lista, sin respuesta.
- En un móvil (pantalla pequeña) la kanban estándar no permite arrastrar. En tableta y PC sí.
- No hay actividades marcadas en cat20: falta elegir modelos en la compañía (pestaña *Expedientes*) o marcar la actividad.
- Errata en la configuración de PyCharm del usuario: `-u ... crap_touch ...` en lugar de `scrap_touch`.

## Fecha límite y `scrap_crm`

Hasta `scrap_crm` 20.0.1.2.0, su campo `datetime_deadline` (de v17) sustituía en el formulario de la tarea a la *Fecha límite* estándar sin copiarse a `date_deadline`, y lo escrito no llegaba a la kanban ni a la lista. Desde esa versión el formulario usa la estándar y la migración pasó los datos (2026-11-11).

## Pantallas pequeñas (2026-11-12)

Revisado en un móvil (390 px) y en una tableta (820 px) con Chrome sin interfaz: ninguna pantalla hace scroll lateral.
- En el móvil, *Nueva tarea* y *Nuevo expediente* son solo iconos, la plantilla y el proyecto comparten fila y las columnas de Actividades van una debajo de otra.
- En la lista, *Título* tiene al menos 240 px y el botón de subtareas no se corta nunca: se recorta el nombre. La regla CSS es más específica que la de la lista de Odoo, que pone los campos en línea.
- La kanban en el móvil es la estándar: una columna por pantalla, que se pasa deslizando, y sin arrastrar (Odoo no lo permite en pantallas pequeñas). Para cambiar de estado, el selector de la tarjeta.
