from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    route_order_count = fields.Integer(related='company_id.route_order_count', readonly=False)
    route_payment_journal_ids = fields.Many2many(related='company_id.route_payment_journal_ids', readonly=False)
