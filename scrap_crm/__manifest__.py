{
    'name': 'SCRAP CRM',
    'version': '20.0.1.1.0',
    'category': '',
    'description': u"""
SCRAP demand integration from CRM
""",
    'author': 'Serincloud',
    'license': 'LGPL-3',
    'depends': [
        'crm',
        'project',
        # La marca de las oportunidades es la de Flota, la misma que la de los vehículos y sus
        # piezas (scrap_base), que así se encuentran desde la oportunidad
        'scrap_base',
        # The screen of what is available, from the opportunity, as the touch screen of CAT
        'scrap_touch',
        # The photos of the products (product.image), shown on that screen, as on the shop
        'website_sale',
    ],
    'data': [
        'security/ir.access.csv',
        'views/crm_lead_views.xml',
        'views/crm_stage_views.xml',
        'views/project_task_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'scrap_crm/static/src/**/*',
        ],
        'web.assets_tests': [
            'scrap_crm/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
