{
    'name': 'Scrap GAIA',
    'version': '20.0.1.0.0',
    'summary': "GAIA: peso de lo vendido y reciclado por material (férreo, plástico...) en los albaranes de salida y en informes por periodo",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': ['scrap_base', 'sale_stock'],
    'data': [
        'security/ir.access.csv',
        'data/scrap_material_data.xml',
        'report/report_deliveryslip.xml',
        'report/scrap_gaia_report.xml',
        'views/scrap_material_views.xml',
        'views/product_template_views.xml',
        'views/stock_picking_views.xml',
        'views/scrap_gaia_report_views.xml',
    ],
}
