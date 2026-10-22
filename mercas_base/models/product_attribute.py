from odoo import fields, models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    mercas_role = fields.Selection(
        selection=[
            ("quality", "Quality"),
            ("size", "Size"),
        ],
        string="Merca Role",
        help=(
            "What the attribute tells of the goods, for the sales report, the lot "
            "and the settlement. An attribute that creates variants classifies "
            "goods bought already classified; one that never creates variants "
            "classifies each sale of goods bought in bulk. Values of both kinds "
            "with the same name are added up together."
        ),
    )
