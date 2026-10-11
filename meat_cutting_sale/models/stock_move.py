from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_meat_ordered_presentation(self):
        presentations = self.sale_line_id.product_no_variant_attribute_value_ids.product_attribute_value_id
        return ', '.join(presentations.mapped('name')) or super()._get_meat_ordered_presentation()
