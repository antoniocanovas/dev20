from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    is_merca = fields.Boolean(
        string="Market Goods",
        default=True,
        help="Category of the goods of the market (fruit and vegetables): only "
             "its products are offered in the catalog of the counter screen "
             "(mercas_touch), in sales and purchases. The boxes are chosen "
             "apart, whatever their category.",
    )
