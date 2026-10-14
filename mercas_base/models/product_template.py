from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_box = fields.Boolean(
        string="Is Box/Container",
        help="Marks this product as a box or container: used to detect box "
             "return/delivery orders and to exclude it from label printing "
             "and from the box count at locations.",
    )
    box_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Box",
        help="Container product used when selling this product.",
        domain=[("is_box", "=", True)],
    )

    def _mercas_any_box_product_exists(self):
        return bool(self.env["product.template"].search_count(
            [("is_box", "=", True)], limit=1
        ))
