{
    'name': 'Scrap Repair',
    'version': '20.0.1.0.0',
    'summary': "Reparación de los vehículos de compra/venta, con sus costes e ingresos en la cuenta analítica del vehículo",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': ['scrap_touch', 'repair'],
    'assets': {
        'web.assets_backend': [
            'scrap_repair/static/src/**/*',
        ],
        'web.assets_tests': [
            'scrap_repair/static/tests/tours/**/*',
        ],
    },
}
