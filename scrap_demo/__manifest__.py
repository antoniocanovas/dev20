{
    'name': 'Scrap Demo',
    'version': '20.0.1.1.0',
    'summary': "Datos de ejemplo del reciclaje de vehículos: plantillas, vehículos, compras, plazos, marcas y oportunidades",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': ['scrap_touch', 'scrap_crm', 'scrap_repair'],
    'data': [
        'data/scrap_demo_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
