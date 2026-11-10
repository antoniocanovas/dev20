from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.depends('order_id.repair_order_ids')
    def _compute_analytic_distribution(self):
        """ The sales of a repair of a vehicle (already sold) go to its analytic account. """
        super()._compute_analytic_distribution()
        for line in self.filtered(lambda line: not line.display_type):
            distribution = line.order_id.sudo().repair_order_ids._scrap_analytic_distribution()
            if distribution:
                line.analytic_distribution = distribution
