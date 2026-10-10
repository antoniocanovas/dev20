{
    'name': 'Meat Cutting',
    'version': '20.0.1.2.0',
    'summary': "Pantalla de despiece para tablet: pesar, etiquetar y desmontar canales en piezas",
    'author': 'Antonio Cánovas',
    'license': 'LGPL-3',
    'category': 'Supply Chain/Manufacturing',
    'icon': '/mrp/static/description/icon.png',
    'depends': ['mrp', 'product_expiry'],
    'data': [
        'data/ir_sequence_data.xml',
        'report/meat_cutting_line_reports.xml',
        'report/meat_cutting_line_templates.xml',
        'report/meat_box_label_templates.xml',
        'views/product_template_views.xml',
        'views/stock_crotal_views.xml',
        'views/meat_cutting_session_views.xml',
        'views/mrp_unbuild_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_package_views.xml',
        'wizard/meat_carcass_register_views.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'meat_cutting/static/src/**/*',
        ],
        'web.assets_tests': [
            'meat_cutting/static/tests/tours/**/*',
        ],
    },
    'application': True,
}
