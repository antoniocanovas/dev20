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

    mercas_no_expiration = fields.Boolean(
        string="No Expiry Date",
        help="Its lots don't expire: they aren't listed as lots without an "
             "expiry date on the counter screen.",
    )

    def _mercas_any_box_product_exists(self):
        return bool(self.env["product.template"].search_count(
            [("is_box", "=", True)], limit=1
        ))


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _mercas_is_weighed(self, uom):
        """Whether `uom` is a unit of weight: the quantity of the product in
        it is its net weight."""
        weight_uom = self.env["product.template"]._get_weight_uom_id_from_ir_config_parameter()
        return bool(uom) and uom._has_common_reference(weight_uom)

    def _mercas_net_weight(self, qty, uom):
        """Net weight of `qty` `uom` of the product, in the weight unit of the
        products: converted when `uom` is a unit of weight, or with the weight
        of the product otherwise."""
        self.ensure_one()
        if not uom:
            return 0.0
        weight_uom = self.env["product.template"]._get_weight_uom_id_from_ir_config_parameter()
        if self._mercas_is_weighed(uom):
            return uom._compute_quantity(qty, weight_uom, round=False)
        return uom._compute_quantity(qty, self.uom_id, round=False) * self.weight
