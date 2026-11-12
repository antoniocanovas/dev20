from datetime import datetime, time

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import html2plaintext

# Records shown on the screen, of each option
LIMIT = 300
# The columns of the tasks: their open states, in this order
TASK_STATES = ('01_in_progress', '02_changes_requested', '03_approved', '04_waiting_normal')
CLOSED_STATES = ('1_done', '1_canceled')
# The columns of the activities
ACTIVITY_STATES = ('overdue', 'today', 'planned')


def is_record_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ProjectTaskTouch(models.AbstractModel):
    """ Files (Expedientes), on a touch screen as the one of CAT (scrap_touch):

    * Tasks: the open tasks of the projects marked to be shown (touch_ok), in the kanban of the
      tasks grouped by state, filtered by the template the project was created from and by project;
    * Activities: the activities marked to be shown (touch_ok), true by default on the models
      chosen in the company, in columns by their state (overdue, today, planned).

    A single search box looks up the name of the task, of its project and of the people
    assigned, its customer and its tags (for the activities: summary, type, document and person
    assigned).
    """
    _name = 'project.task.touch'
    _description = "Files Touch Screen"

    # ------------------------------------------------------------------
    # Screen
    # ------------------------------------------------------------------

    @api.model
    def get_screen_data(self):
        """ The templates and projects to filter with, the columns and the rights of the user. """
        Project = self.env['project.project']
        templates = Project.search([('is_template', '=', True), ('touch_ok', '=', True)], order='name, id')
        projects = Project.search(self._get_project_domain(), order='name, id')
        task_states = dict(self.env['project.task']._fields['state']._description_selection(self.env))
        activity_states = dict(self.env['mail.activity']._fields['state']._description_selection(self.env))
        return {
            'templates': [{'id': template.id, 'name': template.name} for template in templates],
            'projects': [{
                'id': project.id,
                'name': project.name,
                'template_id': project.touch_template_id.id,
            } for project in projects],
            'task_states': [{'key': state, 'name': task_states[state]} for state in TASK_STATES + CLOSED_STATES],
            'activity_states': [{'key': state, 'name': activity_states[state]} for state in ACTIVITY_STATES],
            'can_create_task': self.env['project.task'].has_access('create'),
            'can_create_project': Project.has_access('create') and bool(templates),
            'kanban_view_id': self.env.ref('project_task_touch.project_task_view_kanban_touch').id,
            'list_view_id': self.env.ref('project_task_touch.project_task_view_list_touch').id,
        }

    def _get_project_domain(self):
        return [('touch_ok', '=', True), ('is_template', '=', False)]

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @api.model
    def get_tasks(self, query='', template_id=False, project_id=False, closed=False):
        """ The domain of the tasks, open or closed, for the kanban of the screen, the states to
        show as its columns, and how many tasks and activities there are.

        :param template_id: id of a template, 'none' for the projects not created from one or
            False for all of them
        """
        states = CLOSED_STATES if closed else TASK_STATES
        domain = self._get_task_domain(query, template_id, project_id) & Domain('state', 'in', states)
        return {
            'domain': list(domain),
            'states': list(states),
            'counts': self._get_counts(query, template_id, project_id),
        }

    def _get_task_domain(self, query, template_id, project_id):
        if template_id not in (False, 'none') and not is_record_id(template_id):
            raise ValidationError(self.env._("Invalid template."))
        if project_id and not is_record_id(project_id):
            raise ValidationError(self.env._("Invalid project."))
        domain = Domain([(f'project_id.{name}', operator, value) for name, operator, value in self._get_project_domain()])
        if template_id == 'none':
            domain &= Domain('project_id.touch_template_id', '=', False)
        elif template_id:
            domain &= Domain('project_id.touch_template_id', '=', template_id)
        if project_id:
            domain &= Domain('project_id', '=', project_id)
        if query := (query or '').strip():
            domain &= Domain.OR([
                Domain('name', 'ilike', query),
                Domain('project_id.name', 'ilike', query),
                Domain('user_ids.name', 'ilike', query),
                Domain('partner_id', 'ilike', query),
                Domain('tag_ids.name', 'ilike', query),
            ])
        return domain

    @api.model
    def create_task(self, project_id, name, date=False):
        """ A new task of a project marked to be shown, with its deadline on `date`. """
        if not is_record_id(project_id):
            raise ValidationError(self.env._("Invalid project."))
        project = self.env['project.project'].search(
            Domain(self._get_project_domain()) & Domain('id', '=', project_id))
        if not project:
            raise UserError(self.env._("The project is not shown in Files."))
        name = (name or '').strip()
        if not name:
            raise UserError(self.env._("Write the name of the task."))
        task = self.env['project.task'].create({
            'project_id': project.id,
            'name': name,
            'date_deadline': self._to_deadline(date),
        })
        return {'id': task.id, 'name': task.name}

    @api.model
    def get_subtasks(self, task_id):
        """ The open subtasks of a task of a file, to close them from the list of the screen. """
        task = self._browse_file_task(task_id)
        subtasks = task.child_ids.filtered(lambda subtask: subtask.state not in CLOSED_STATES)
        return [{
            'id': subtask.id,
            'name': subtask.name,
            'state': subtask.state,
            'users': ', '.join(subtask.user_ids.mapped('name')),
        } for subtask in subtasks.sorted(lambda subtask: (subtask.sequence, subtask.id))]

    @api.model
    def create_subtask(self, task_id, name):
        """ A new subtask, as the ones added on the kanban: of its project, with its people. """
        task = self._browse_file_task(task_id)
        name = (name or '').strip()
        if not name:
            raise UserError(self.env._("Write the name of the subtask."))
        sequences = task.child_ids.mapped('sequence')
        subtask = self.env['project.task'].create({
            'name': name,
            'parent_id': task.id,
            'project_id': task.project_id.id,
            'user_ids': task.user_ids.ids,
            'sequence': (max(sequences) if sequences else 0) + 1,
        })
        return {'id': subtask.id, 'name': subtask.name}

    def _browse_file_task(self, task_id):
        if not is_record_id(task_id):
            raise ValidationError(self.env._("Invalid task."))
        task = self.env['project.task'].browse(task_id).exists()
        if not task or not task.project_id.touch_ok:
            raise UserError(self.env._("The task is not of a file."))
        return task

    def _to_deadline(self, date):
        """ The deadline of a task (a datetime) on a day: at noon of the user, so that it is on
        that day in any time zone near. """
        if not date:
            return False
        day = fields.Date.to_date(date)
        tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        local = tz.localize(datetime.combine(day, time(12)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Files: projects created from a template
    # ------------------------------------------------------------------

    @api.model
    def create_project(self, template_id, name, date=False):
        """ A new file: a project created from a template marked to be shown, starting on `date`.

        :return: the new project, as in get_screen_data
        """
        if not is_record_id(template_id):
            raise ValidationError(self.env._("Invalid template."))
        template = self.env['project.project'].search(
            [('id', '=', template_id), ('is_template', '=', True), ('touch_ok', '=', True)])
        if not template:
            raise UserError(self.env._("The template is not shown in Files."))
        name = (name or '').strip()
        if not name:
            raise UserError(self.env._("Write the name of the file."))
        values = {'name': name}
        if date:
            # Its end and the deadlines of its tasks, from it (see project.project)
            values['date_start'] = fields.Date.to_date(date)
        project = template.action_create_from_template(values)
        project.touch_ok = True
        return {'id': project.id, 'name': project.name, 'template_id': template.id}

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    @api.model
    def get_activities(self, query='', template_id=False, project_id=False, closed=False):
        """ The activities marked to be shown, with how many tasks and activities there are.

        :param closed: the ones done instead (archived by Odoo with their date and feedback),
            the last done first
        """
        domain = self._get_activity_domain(query)
        if closed:
            activities = self.env['mail.activity'].search(
                domain & Domain('active', '=', False) & Domain('date_done', '!=', False),
                limit=LIMIT, order='date_done desc, id desc')
        else:
            activities = self.env['mail.activity'].search(domain, limit=LIMIT, order='date_deadline asc, id asc')
        return {
            'activities': [self._get_activity_data(activity) for activity in activities],
            'counts': self._get_counts(query, template_id, project_id),
        }

    def _get_activity_domain(self, query):
        domain = Domain('touch_ok', '=', True)
        if query := (query or '').strip():
            domain &= Domain.OR([
                Domain('summary', 'ilike', query),
                Domain('res_name', 'ilike', query),
                Domain('activity_type_id.name', 'ilike', query),
                Domain('user_id.name', 'ilike', query),
            ])
        return domain

    def _get_activity_data(self, activity):
        return {
            'id': activity.id,
            'summary': activity.summary or '',
            'type': activity.activity_type_id.name or '',
            'icon': activity.icon or '',
            'res_model': activity.res_model,
            'res_id': activity.res_id,
            'res_name': activity.res_name or '',
            # The users without access to the models (not administrators) see their name too
            'model': activity.res_model_id.sudo().name or '',
            'user': activity.user_id.name or '',
            'date_deadline': fields.Date.to_string(activity.date_deadline),
            'state': activity.state,
            'note': html2plaintext(activity.note or '').strip(),
            'date_done': fields.Date.to_string(activity.date_done),
            'feedback': activity.feedback or '',
        }

    # ------------------------------------------------------------------

    def _get_counts(self, query, template_id, project_id):
        domain = self._get_task_domain(query, template_id, project_id)
        return {
            'tasks': self.env['project.task'].search_count(domain & Domain('state', 'in', TASK_STATES)),
            'activities': self.env['mail.activity'].search_count(self._get_activity_domain(query)),
        }
