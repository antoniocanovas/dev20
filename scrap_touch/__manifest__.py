{
    'name': 'Scrap Touch',
    'version': '20.0.1.3.0',
    'summary': "Pantalla táctil para el reciclaje de vehículos: entrada para desguace",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'icon': '/scrap_touch/static/description/icon.png',
    'depends': ['purchase_stock', 'scrap_base'],
    'data': [
        'views/scrap_touch_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'scrap_touch/static/src/**/*',
        ],
        'web.assets_tests': [
            'scrap_touch/static/tests/tours/**/*',
        ],
    },
    'application': True,
}
