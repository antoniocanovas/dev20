{
    'name': 'Mercas Touch',
    'version': '20.0.1.0.0',
    'summary': "Pantalla táctil de mostrador para mercas: venta con lotes, recepción, cajas, lotes y cobros",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'icon': '/mercas_touch/static/description/icon.png',
    'depends': ['mercas_base', 'barcodes'],
    'data': [
        'views/mercas_touch_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mercas_touch/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'mercas_touch/static/tests/**/*.test.js',
        ],
        'web.assets_tests': [
            'mercas_touch/static/tests/tours/**/*',
        ],
    },
    'application': True,
}
