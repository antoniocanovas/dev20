{
    'name': 'Vencimientos',
    'version': '20.0.1.0.0',
    'summary': "Pantalla táctil de vencimientos: tareas de proyectos y actividades",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Services/Project',
    'icon': '/project_task_touch/static/description/icon.png',
    'depends': ['project'],
    'data': [
        'views/res_company_views.xml',
        'views/project_project_views.xml',
        'views/mail_activity_views.xml',
        'views/project_task_touch_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'project_task_touch/static/src/**/*',
        ],
        'web.assets_tests': [
            'project_task_touch/static/tests/tours/**/*',
        ],
    },
    'application': True,
}
