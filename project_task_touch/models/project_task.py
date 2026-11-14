from odoo import api, fields, models

from .project_task_touch import CLOSED_STATES


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # On the screen of Deadlines (see project.task.touch), grouped by state, the columns of the
    # states asked for are shown even if empty, so that a task can be dragged to them;
    # elsewhere, only the states with tasks, as always
    state = fields.Selection(group_expand='_touch_group_expand_state')
    # Odoo doesn't keep when a task is closed: the closed ones, the last closed first
    touch_date_closed = fields.Datetime(
        string="Closed on", compute='_compute_touch_date_closed', store=True, copy=False,
    )

    @api.depends('state')
    def _compute_touch_date_closed(self):
        now = fields.Datetime.now()
        for task in self:
            # From done to cancelled (or back), it keeps the date it was closed
            task.touch_date_closed = (task.touch_date_closed or now) if task.state in CLOSED_STATES else False

    def _touch_group_expand_state(self, states, domain):
        return self.env.context.get('touch_states') or states
