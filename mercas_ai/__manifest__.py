{
    "name": "Mercas AI",
    "version": "20.0.1.0.0",
    "summary": "Consola de chat con la IA (MCP Gateway) desde el propio backend de Odoo",
    "description": (
        "Consola de chat con la IA (MCP Gateway) desde el propio backend de Odoo: "
        "ventas, compras, facturacion, stock, existencias, cajas y lotes. "
        "Ver README.md para el detalle de la arquitectura."
    ),
    "author": "Antonio Cánovas",
    "license": "LGPL-3",
    "category": "Productivity/AI",
    "depends": [
        "odoo_mcp_manager",
        "chat_ai",
        "sale",
        "purchase",
        "account",
        "stock",
        "product_expiry",
    ],
    "data": [
        "data/ai_tool_sales_report.xml",
        "data/ai_tool_domain_reports.xml",
        "data/ai_resource_lines.xml",
        "views/res_config_settings_views.xml",
        "wizard/ai_chat_wizard_views.xml",
        "wizard/ai_domain_chat_wizard_views.xml",
        'security/ir.access.csv',
    ],
    "assets": {
        "web.assets_backend": [
            "mercas_ai/static/src/css/chat_fields.css",
            "mercas_ai/static/src/js/chat_fields.js",
            "mercas_ai/static/src/xml/chat_fields.xml",
        ],
        "web.assets_tests": [
            "mercas_ai/static/tests/tours/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
}
