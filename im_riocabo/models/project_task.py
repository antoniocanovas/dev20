from markupsafe import Markup

from odoo import api, models
from odoo.tools.misc import format_date


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._im_riocabo_notify_assignees({task: task.user_ids for task in tasks})
        return tasks

    def write(self, vals):
        old_users = {task: task.user_ids for task in self} if 'user_ids' in vals else None
        res = super().write(vals)
        if old_users is not None:
            self._im_riocabo_notify_assignees({task: task.user_ids - old_users[task] for task in self})
        return res

    def _im_riocabo_notify_assignees(self, users_per_task):
        Channel = self.env['discuss.channel']
        if not Channel._im_riocabo_should_notify():
            return
        for task, users in users_per_task.items():
            for user in users:
                if user == self.env.user:
                    continue
                Channel._im_riocabo_notify(user, task.with_context(lang=user.lang)._im_riocabo_chat_body())

    def _im_riocabo_chat_body(self):
        self.ensure_one()
        _ = self.env._
        lines = [_("New task assigned to you: %s", self._get_html_link_with_href())]
        if self.project_id:
            lines.append(_("Project: %s", self.project_id.display_name))
        if self.partner_id:
            lines.append(_("Customer: %s", self.partner_id.display_name))
        if self.date_deadline:
            lines.append(_("Deadline: %s", format_date(self.env, self.date_deadline)))
        return Markup("<br/>").join(lines)
