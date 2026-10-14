{
    'name': 'Mercas Keys',
    'version': '20.0.2.0.0',
    'category': 'Technical',
    'license': 'AGPL-3',
    'summary': 'Pantalla unificada F1-F5 y navegación rápida para mercas',
    'author': 'Serincloud',
    'website': 'https://ingenieriacloud.com',
    'depends': ['web', 'sale', 'purchase', 'account'],
    'data': [
        'views/mercas_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mercas_keys/static/src/js/list_renderer_patch.js',
            'mercas_keys/static/src/js/mercas_modes.js',
            'mercas_keys/static/src/js/mercas_hotkey_service.js',
            'mercas_keys/static/src/js/mercas_topbar.js',
            'mercas_keys/static/src/js/mercas_unified_screen.js',
            'mercas_keys/static/src/xml/mercas_unified_screen.xml',
            'mercas_keys/static/src/css/mercas_unified_screen.css',
        ],
        'web.assets_tests': [
            'mercas_keys/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
