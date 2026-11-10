{
    'name': 'IM Riocabo',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Avisos por chat directo al asignar tareas y actividades',
    'description': u"""
Envía un mensaje por chat directo (Conversaciones) a la persona asignada:

* al crear una tarea o añadir personas asignadas a una tarea;
* al crear una actividad asignada a otra persona.

El mensaje lo envía quien hace la asignación, en el idioma de quien lo recibe,
con enlace al documento. No se avisa a uno mismo. Los avisos estándar de Odoo
(bandeja de entrada o correo) se mantienen.

Para crear registros sin avisos (importaciones, scripts) usar el contexto
``im_riocabo_no_notify=True``.
""",
    'author': 'Serincloud',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'project',
    ],
    'data': [],
    'installable': True,
}
