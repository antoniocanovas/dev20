from odoo import models


class RepairServiceLine(models.Model):
    _inherit = 'repair.service.line'

    def _scrap_create_analytic_cost(self):
        """ The cost of the services of a repair of a vehicle (its cost price), in the analytic
        account of the vehicle, as the one of its parts. """
        Account = self.env['account.analytic.account'].sudo()
        Line = self.env['account.analytic.line'].sudo()
        for line in self:
            distribution = line.repair_id._scrap_analytic_distribution()
            product = line.product_id
            if not distribution or not product:
                continue
            quantity = line.uom_id._compute_quantity(line.quantity, product.uom_id)
            cost = quantity * product.with_company(line.repair_id.company_id).standard_price
            if not cost:
                continue
            values = Account._perform_analytic_distribution(distribution, -cost, quantity, Line, line)
            if values:
                Line.create(values)

    def _prepare_analytic_line_values(self, account_field_values, amount, unit_amount):
        self.ensure_one()
        return {
            'name': f"{self.repair_id.name} - {self.product_id.display_name}",
            'amount': amount,
            **account_field_values,
            'unit_amount': unit_amount,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_id.uom_id.id,
            'company_id': self.repair_id.company_id.id,
            'ref': self.repair_id.name,
            'category': 'other',
        }
