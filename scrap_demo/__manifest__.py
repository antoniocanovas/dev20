{
    'name': 'Scrap Demo',
    'version': '20.0.1.2.0',
    'summary': "Datos de ejemplo del reciclaje de vehículos: plantillas, vehículos, compras, plazos, marcas, oportunidades y expedientes",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': ['scrap_touch', 'scrap_crm', 'scrap_repair', 'project_task_touch'],
    'data': [
        'data/scrap_demo_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
