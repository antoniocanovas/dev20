{
    "name": "Mercas Demo",
    "version": "20.0.1.0.0",
    "summary": "Datos de demo/arranque para Mercas Base sobre un Odoo limpio",
    "author": "Antonio Cánovas",
    "license": "LGPL-3",
    "category": "Inventory",
    "depends": [
        "mercas_base",
    ],
    "data": [
        "data/product_category_demo.xml",
        "data/product_attribute_demo.xml",
        "data/res_company_demo.xml",
        "data/res_partner_demo.xml",
        "data/product_template_demo.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
}
