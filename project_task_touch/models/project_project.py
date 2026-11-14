from datetime import datetime, time

from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    touch_ok = fields.Boolean(
        string="Show in Deadlines",
        help="Its tasks are shown in Deadlines. A project created from a template marked so is marked too.",
    )
    # Odoo doesn't keep the template a project is created from
    touch_template_id = fields.Many2one(
        'project.project', string="Created from Template", copy=False, index='btree_not_null',
        domain=[('is_template', '=', True)], ondelete='set null',
    )

    def action_create_from_template(self, values=None, role_to_users_mapping=None):
        """ Also the deadlines of the tasks: Odoo doesn't copy them. Each one keeps the gap it has
        in the template from its start (or, without one, from its earliest deadline), from the
        start of the new project. Without planned dates in the template, the project ends with
        its last deadline. """
        template = self
        project = super().action_create_from_template(values=values, role_to_users_mapping=role_to_users_mapping)
        project.touch_template_id = template
        template._touch_copy_deadlines(project)
        return project

    def _touch_copy_deadlines(self, project):
        self.ensure_one()
        Task = self.env['project.task'].with_context(active_test=False)
        # The tasks of the template in the order Odoo copied them (see map_tasks), and their copies
        originals = Task.search([('project_id', '=', self.id), ('parent_id', '=', False)])
        copies = Task.search([('project_id', '=', project.id), ('parent_id', '=', False)]).sorted('id')
        if len(originals) != len(copies):
            return
        mapping, _dependencies = originals._create_task_mapping(copies)
        deadlines = {original.id: original.date_deadline for original in Task.browse(list(mapping)) if original.date_deadline}
        if deadlines:
            reference = (
                datetime.combine(self.date_start, time.min) if self.date_start
                else min(deadline.replace(hour=0, minute=0, second=0, microsecond=0) for deadline in deadlines.values())
            )
            start = datetime.combine(project.date_start or fields.Date.context_today(self), time.min)
            for task_id, deadline in deadlines.items():
                mapping[task_id].date_deadline = start + (deadline - reference)
        if project.date_start and not (self.date_start and self.date):
            # The planned dates are a range: both or none; until the last deadline
            last = max((copy.date_deadline.date() for copy in mapping.values() if copy.date_deadline), default=project.date_start)
            project.date = max(last, project.date_start)
