from odoo import api, fields, models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    # True by default on the models chosen in the company (see res.company)
    touch_ok = fields.Boolean(
        string="Show in Files", compute='_compute_touch_ok', store=True, readonly=False, precompute=True,
        index='btree_not_null',
    )

    @api.depends('res_model_id')
    def _compute_touch_ok(self):
        models = self.env.company.touch_activity_model_ids
        for activity in self:
            activity.touch_ok = activity.res_model_id in models
