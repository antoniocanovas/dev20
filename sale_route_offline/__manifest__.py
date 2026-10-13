{
    'name': 'Route Sales Offline',
    'version': '20.0.1.0.0',
    'summary': "Pantalla de preventa para tablet: clientes, deuda, pedidos y cobros sin conexión",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Sales/Sales',
    'icon': '/sale_route_offline/static/description/icon.png',
    'depends': ['sale', 'account'],
    'data': [
        'views/sale_route_offline_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_route_offline/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'sale_route_offline/static/tests/**/*.test.js',
        ],
    },
    'application': True,
}
