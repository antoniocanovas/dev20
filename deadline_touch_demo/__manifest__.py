{
    'name': 'Vencimientos: datos de ejemplo',
    'version': '20.0.1.0.0',
    'summary': "Plantillas de proyecto y proyectos de ejemplo para la pantalla de Vencimientos",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Services/Project',
    'depends': ['deadline_touch'],
    'data': [
        'data/deadline_touch_demo_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
