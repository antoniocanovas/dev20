from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    touch_activity_model_ids = fields.Many2many(
        'ir.model', 'res_company_touch_activity_model_rel', 'company_id', 'model_id',
        string="Models of the Deadline Activities",
        domain=[('transient', '=', False)],
        help="The activities created on the records of these models are shown in Deadlines by default.",
    )
