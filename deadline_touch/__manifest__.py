{
    'name': 'Vencimientos',
    'version': '20.0.1.0.0',
    'summary': "Pantalla táctil de vencimientos: tareas de proyectos y actividades",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Services/Project',
    'icon': '/deadline_touch/static/description/icon.png',
    'depends': ['project'],
    'data': [
        'views/res_company_views.xml',
        'views/project_project_views.xml',
        'views/mail_activity_views.xml',
        'wizard/mail_activity_schedule_views.xml',
        'views/deadline_touch_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'deadline_touch/static/src/**/*',
        ],
        'web.assets_tests': [
            'deadline_touch/static/tests/tours/**/*',
        ],
    },
    'application': True,
    'pre_init_hook': 'pre_init_hook',
}
