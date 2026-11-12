from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # On the screen of Files (see project.task.touch), grouped by state, the columns of the
    # states asked for are shown even if empty, so that a task can be dragged to them;
    # elsewhere, only the states with tasks, as always
    state = fields.Selection(group_expand='_touch_group_expand_state')

    def _touch_group_expand_state(self, states, domain):
        return self.env.context.get('touch_states') or states
