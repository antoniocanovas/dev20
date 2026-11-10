from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _related_analytic_distribution(self):
        """ The lines of an invoice of a repair of a vehicle (already sold) go to its analytic
        account. """
        distribution = super()._related_analytic_distribution()
        if self.display_type == 'product':
            distribution = distribution | self.move_id.sudo().repair_order_id._scrap_analytic_distribution()
        return distribution
