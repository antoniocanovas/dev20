from odoo import models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def _mercas_apply_inventory(self, qty, location=None):
        """ The touch screens open elsewhere show the new stock of the lot counted. """
        diff = super()._mercas_apply_inventory(qty, location)
        if diff:
            self.env['mercas.touch']._notify_lots_changed(self.product_id)
        return diff
