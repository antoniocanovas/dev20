# Vencimientos: datos de ejemplo (`deadline_touch_demo`)

Datos de ejemplo para probar la pantalla de Vencimientos (`deadline_touch`). Depende solo de ella. Se cargan al instalar (hook `post_init_hook`), con las fechas relativas al día de instalación. Pensado para bases de prueba, no de producción.

## Datos

Tres etapas (*Por hacer*, *En curso* y *Hecho*) y cuatro plantillas marcadas para Vencimientos, con fechas de inicio y fin (desde el 1 de enero) y fechas límite en sus tareas. Los proyectos creados con ellas toman de la plantilla su fin y sus fechas límite, movidas a su inicio (`deadline_touch`):

- *Salida de residuos*: una tarea con 4 subtareas que se repite cada mes; la del mes pasado hecha y la de este mes creada por la recurrencia.
- *Onboarding de empleado*: 7 tareas con dependencias. *Onboarding Juan Pérez (mecánico)* en su segunda semana (una vencida, otras esperando) y *Onboarding Laura Martín (administración)*, que empieza hoy.
- *Gestión AEAT mensual*: revisar facturas, conciliar bancos, modelos 303, 111 y 115, presentar y archivar, con dependencias y hasta el día 20 del mes siguiente. El mes anterior al pasado, presentado; el pasado, en curso.
- *Formación de taller*: cursos (PRL, descontaminación de VFU, carretilla, híbridos y eléctricos, corte) con las subtareas *Inscripción / Asistencia / Certificado entregado* y una evaluación final que depende de todos. *Formación de taller · Juan Pérez* con el PRL hecho y el resto en marcha.

Si ya existe alguna plantilla con esos nombres, el hook no crea nada, para no duplicarlas. Para crearlas a mano en una base ya instalada: `from odoo.addons.deadline_touch_demo.hooks import create_demo; create_demo(env)` desde `odoo-bin shell`.

## Tests

Con los de `deadline_touch` (ver su README): `-i deadline_touch_demo --test-tags /deadline_touch,/deadline_touch_demo`.
