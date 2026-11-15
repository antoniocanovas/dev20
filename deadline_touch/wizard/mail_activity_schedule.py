from odoo import api, fields, models


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    # The dialog of the chatter to schedule an activity: checked by default on the models
    # chosen in the company, as the activity, and it can be changed by hand
    touch_ok = fields.Boolean(
        string="Show in Deadlines", compute='_compute_touch_ok', store=True, readonly=False, precompute=True,
    )

    @api.depends('res_model_id')
    def _compute_touch_ok(self):
        models = self.env.company.touch_activity_model_ids
        for scheduler in self:
            scheduler.touch_ok = scheduler.res_model_id in models

    def _action_schedule_activities(self):
        activities = super()._action_schedule_activities()
        activities.touch_ok = self.touch_ok
        return activities
