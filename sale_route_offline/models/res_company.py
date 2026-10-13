from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    route_order_count = fields.Integer(
        'Recent Orders per Customer', default=5,
        help="Number of recent orders of each customer loaded on the tablet.")
    route_payment_journal_ids = fields.Many2many(
        'account.journal', 'res_company_route_payment_journal_rel', 'company_id', 'journal_id',
        string='Route Payment Journals', domain="[('type', 'in', ('bank', 'cash'))]",
        help="Journals in which the salespeople register payments on the route. "
             "Empty means every bank and cash journal of the company.")

    def _get_route_payment_journals(self):
        self.ensure_one()
        return self.route_payment_journal_ids.filtered(lambda journal: journal.active) or self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self),
            ('type', 'in', ('bank', 'cash')),
        ])
