from odoo import models


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    def _scrap_analytic_distribution(self):
        """ The analytic account of the vehicle repaired: its parts, its services and, when it
        is sold, its sales go to it. """
        account = self[:1].product_id.product_tmpl_id.sudo().scrap_analytic_account_id
        return {str(account.id): 100} if account else {}

    def action_repair_done(self):
        result = super().action_repair_done()
        self._scrap_create_parts_analytic_cost()
        self.repair_service_line_ids._scrap_create_analytic_cost()
        return result

    def _scrap_create_parts_analytic_cost(self):
        """ The parts of a repair of a vehicle, at their value, in the analytic account of the
        vehicle: a part added is a cost, a part removed into the stock a recovery. They are made
        here, and not by the stock moves, which only make them for some operation types (as
        project_stock_account does). """
        Account = self.env['account.analytic.account'].sudo()
        Line = self.env['account.analytic.line'].sudo()
        for repair in self:
            distribution = repair._scrap_analytic_distribution()
            if not distribution:
                continue
            for move in repair.move_ids.sudo().filtered(lambda move: move.state == 'done' and move.value):
                values = Account._perform_analytic_distribution(
                    distribution, move.value, move._get_valued_qty(), move.analytic_account_line_ids, move)
                if values:
                    move.analytic_account_line_ids += Line.create(values)
