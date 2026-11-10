{
    'name': 'Scrap Base',
    'version': '20.0.1.3.0',
    'summary': "Base del reciclaje de vehículos: plantillas de desguace en los productos",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': ['purchase_stock', 'account', 'fleet', 'mrp'],
    'data': [
        'security/ir.access.csv',
        'data/scrap_base_data.xml',
        'views/product_template_views.xml',
        'views/purchase_order_views.xml',
        'views/res_company_views.xml',
    ],
}
