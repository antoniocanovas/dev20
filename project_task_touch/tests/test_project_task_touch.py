from datetime import date, datetime

from freezegun import freeze_time

from odoo import fields
from odoo.addons.project_task_touch.hooks import fill_touch_date_closed
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProjectTaskTouch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project']
        cls.template = Project.create({'name': 'Touch Template', 'touch_ok': True})
        cls.template._toggle_template_mode(True)
        cls.env['project.task'].create({'name': 'Touch Template Step', 'project_id': cls.template.id})
        cls.other_template = Project.create({'name': 'Touch Hidden Template'})
        cls.other_template._toggle_template_mode(True)
        cls.project = Project.create({'name': 'Touch Project', 'touch_ok': True})
        cls.hidden = Project.create({'name': 'Touch Hidden Project'})
        cls.user = new_test_user(cls.env, login='touch_user', name='Touch Assignee',
                                 groups='project.group_project_manager')
        Task = cls.env['project.task']
        cls.task = Task.create({
            'name': 'Touch Task', 'project_id': cls.project.id, 'user_ids': [cls.user.id],
            'partner_id': cls.env['res.partner'].create({'name': 'Touch Customer'}).id,
            'tag_ids': [fields.Command.create({'name': 'Touch Urgent Tag'})],
        })
        cls.hidden_task = Task.create({'name': 'Touch Hidden Task', 'project_id': cls.hidden.id})
        cls.Touch = cls.env['project.task.touch']

    def _tasks(self, *args, **kwargs):
        """ The tasks shown in the kanban of the screen. """
        return self.env['project.task'].search(self.Touch.get_tasks(*args, **kwargs)['domain'])

    def test_screen_data(self):
        data = self.Touch.get_screen_data()
        self.assertIn(self.template.id, [template['id'] for template in data['templates']])
        self.assertNotIn(self.other_template.id, [template['id'] for template in data['templates']])
        project_ids = [project['id'] for project in data['projects']]
        self.assertIn(self.project.id, project_ids)
        self.assertNotIn(self.hidden.id, project_ids)
        self.assertNotIn(self.template.id, project_ids, "A template isn't a file")
        self.assertEqual([state['key'] for state in data['task_states']][:4],
                         ['01_in_progress', '02_changes_requested', '03_approved', '04_waiting_normal'])

    def test_tasks_of_files_only(self):
        names = self._tasks().mapped('name')
        self.assertIn('Touch Task', names)
        self.assertNotIn('Touch Hidden Task', names)
        self.assertNotIn('Touch Template Step', names, "The tasks of the templates aren't shown")

    def test_search(self):
        for query in ('touch task', 'TOUCH PROJECT', 'Assignee', 'touch customer', 'urgent tag'):
            names = self._tasks(query).mapped('name')
            self.assertEqual(names, ['Touch Task'], query)
        self.assertFalse(self._tasks('nothing like this'))

    def test_create_project_from_template(self):
        project = self.Touch.create_project(self.template.id, 'Touch File 1', '2026-11-11')
        record = self.env['project.project'].browse(project['id'])
        self.assertTrue(record.touch_ok)
        self.assertFalse(record.is_template)
        self.assertEqual(record.touch_template_id, self.template)
        self.assertEqual(record.date_start, date(2026, 11, 11))
        self.assertEqual(record.task_ids.mapped('name'), ['Touch Template Step'])
        # Filtered by its template, then by itself
        self.assertEqual(self._tasks('', self.template.id).project_id, record)
        self.assertEqual(self.Touch.get_tasks('', self.template.id, record.id)['counts']['tasks'], 1)
        # The projects not created from a template
        names = self._tasks('', 'none').mapped('name')
        self.assertIn('Touch Task', names)
        self.assertNotIn('Touch Template Step', names)
        with self.assertRaises(UserError):
            self.Touch.create_project(self.other_template.id, 'Not shown', False)

    def test_deadlines_from_template(self):
        """ The deadlines of the template, with the same gap from the start of the new file. """
        Project, Task = self.env['project.project'], self.env['project.task']
        dated = Project.create({'name': 'Touch Dated', 'touch_ok': True, 'date_start': '2026-01-01', 'date': '2026-01-31'})
        dated._toggle_template_mode(True)
        step = Task.create({'name': 'Touch Step', 'project_id': dated.id, 'date_deadline': '2026-01-20 10:00:00'})
        Task.create({'name': 'Touch Sub Step', 'project_id': dated.id, 'parent_id': step.id, 'date_deadline': '2026-01-05 09:00:00'})
        Task.create({'name': 'Touch No Deadline', 'project_id': dated.id})
        file = Project.browse(self.Touch.create_project(dated.id, 'Touch Dated File', '2026-03-01')['id'])
        tasks = {task.name: task for task in file.task_ids}
        self.assertEqual(str(tasks['Touch Step'].date_deadline), '2026-03-20 10:00:00')
        self.assertEqual(str(tasks['Touch Sub Step'].date_deadline), '2026-03-05 09:00:00')
        self.assertFalse(tasks['Touch No Deadline'].date_deadline)
        self.assertEqual((str(file.date_start), str(file.date)), ('2026-03-01', '2026-03-31'), "As long as the template")
        self.assertEqual(str(step.date_deadline), '2026-01-20 10:00:00', "The template unchanged")

        # Without planned dates: from its earliest deadline, and the file ends with the last one
        undated = Project.create({'name': 'Touch Undated', 'touch_ok': True})
        undated._toggle_template_mode(True)
        Task.create({'name': 'Touch First', 'project_id': undated.id, 'date_deadline': '2026-01-10 12:00:00'})
        Task.create({'name': 'Touch Second', 'project_id': undated.id, 'date_deadline': '2026-01-15 12:00:00'})
        file = Project.browse(self.Touch.create_project(undated.id, 'Touch Undated File', '2026-05-01')['id'])
        self.assertEqual(sorted(str(deadline) for deadline in file.task_ids.mapped('date_deadline')),
                         ['2026-05-01 12:00:00', '2026-05-06 12:00:00'])
        self.assertEqual((str(file.date_start), str(file.date)), ('2026-05-01', '2026-05-06'))

    def test_create_task_and_state(self):
        task = self.Touch.create_task(self.project.id, 'Touch New Task', '2026-12-01')
        record = self.env['project.task'].browse(task['id'])
        self.assertEqual(record.project_id, self.project)
        self.assertEqual(record.date_deadline.date(), date(2026, 12, 1))
        record.state = '1_done'
        self.assertNotIn(record, self._tasks())
        self.assertIn(record, self._tasks(closed=True))
        with self.assertRaises(UserError):
            self.Touch.create_task(self.hidden.id, 'Not shown', False)

    def test_subtasks(self):
        """ Closed and added from the list, as on the kanban. """
        sub = self.env['project.task'].create({'name': 'Touch Sub', 'parent_id': self.task.id, 'project_id': self.project.id})
        self.assertEqual([data['name'] for data in self.Touch.get_subtasks(self.task.id)], ['Touch Sub'])
        sub.state = '1_done'
        self.assertFalse(self.Touch.get_subtasks(self.task.id), "Only the open ones")
        data = self.Touch.create_subtask(self.task.id, 'Touch Sub 2')
        new = self.env['project.task'].browse(data['id'])
        self.assertEqual((new.parent_id, new.project_id, new.user_ids), (self.task, self.project, self.user))
        with self.assertRaises(UserError):
            self.Touch.create_subtask(self.hidden_task.id, 'Not shown')

    def test_empty_state_columns(self):
        """ Grouped by state, the columns asked for, even if empty; elsewhere, as always. """
        Task = self.env['project.task']
        domain = [('project_id', '=', self.project.id)]
        groups = Task.with_context(read_group_expand=True).web_read_group(domain, ['state'])['groups']
        self.assertEqual([group['state'] for group in groups], ['01_in_progress'])
        states = self.Touch.get_tasks()['states']
        groups = Task.with_context(read_group_expand=True, touch_states=states).web_read_group(domain, ['state'])['groups']
        self.assertEqual([group['state'] for group in groups], states)

    def test_activities(self):
        partner_model = self.env['ir.model']._get('res.partner')
        self.env.company.touch_activity_model_ids = partner_model
        partner = self.env['res.partner'].create({'name': 'Touch Partner'})
        activity = partner.activity_schedule(summary='Touch Call', user_id=self.user.id)
        self.assertTrue(activity.touch_ok, "True by default on the models of the company")
        other = self.task.activity_schedule(summary='Touch Not Shown')
        self.assertFalse(other.touch_ok)
        other.touch_ok = True
        result = self.Touch.get_activities()
        summaries = [data['summary'] for data in result['activities']]
        self.assertIn('Touch Call', summaries)
        self.assertIn('Touch Not Shown', summaries, "Marked by hand")
        self.assertEqual([data['summary'] for data in self.Touch.get_activities('Touch Partner')['activities']], ['Touch Call'])
        self.assertEqual([data['summary'] for data in self.Touch.get_activities('assignee')['activities']], ['Touch Call'])
        # By type, with the count of the button too
        call_type = self.env['mail.activity.type'].create({'name': 'Touch Phone Type'})
        activity.activity_type_id = call_type
        self.assertIn({'id': call_type.id, 'name': 'Touch Phone Type'}, self.Touch.get_activities()['activity_types'])
        by_type = self.Touch.get_activities(activity_type_id=call_type.id)
        self.assertEqual([data['summary'] for data in by_type['activities']], ['Touch Call'])
        self.assertEqual(by_type['counts']['activities'], 1)
        self.assertEqual(self.Touch.get_tasks(activity_type_id=call_type.id)['counts']['activities'], 1)
        activity.action_feedback(feedback='Touch Feedback')
        self.assertFalse(activity.active)
        self.assertNotIn('Touch Call', [data['summary'] for data in self.Touch.get_activities()['activities']])
        # Among the closed ones, with its feedback
        closed = self.Touch.get_activities(closed=True)['activities']
        self.assertEqual([(data['summary'], data['feedback']) for data in closed], [('Touch Call', 'Touch Feedback')])
        self.assertTrue(closed[0]['date_done'])
        self.assertEqual([data['summary'] for data in self.Touch.get_activities(closed=True, activity_type_id=call_type.id)['activities']], ['Touch Call'])
        self.assertIn(call_type.id, [data['id'] for data in self.Touch.get_activities()['activity_types']], "Still among the types: done")

    def test_closed_tasks_last_closed_first(self):
        """ The closed tasks, the last closed first, as the screen orders them. """
        Task = self.env['project.task']
        first, second = Task.create([{'name': f'Touch Closed {n}', 'project_id': self.project.id} for n in (1, 2)])
        with freeze_time('2026-11-10 10:00:00'):
            second.state = '1_done'
            self.env.flush_all()
        with freeze_time('2026-11-10 11:00:00'):
            first.state = '1_canceled'
            self.env.flush_all()
        self.assertEqual(first.touch_date_closed, datetime(2026, 11, 10, 11))
        closed = Task.search(self.Touch.get_tasks(closed=True)['domain'], order='touch_date_closed desc, id desc')
        self.assertEqual(closed[:2], first + second, "The last closed first, though created before")
        with freeze_time('2026-11-12 09:00:00'):
            second.state = '1_canceled'
            self.env.flush_all()
        self.assertEqual(second.touch_date_closed, datetime(2026, 11, 10, 10), "Still closed: its date kept")
        second.state = '01_in_progress'
        self.assertFalse(second.touch_date_closed, "Open again")
        # The ones closed before the install, from the date they ended
        first.date_end = datetime(2026, 1, 5, 8)
        self.env.flush_all()
        self.env.cr.execute("UPDATE project_task SET touch_date_closed = NULL WHERE id = %s", [first.id])
        fill_touch_date_closed(self.env.cr)
        first.invalidate_recordset(['touch_date_closed'])
        self.assertEqual(first.touch_date_closed, datetime(2026, 1, 5, 8))

    def test_closed_activities_last_done_first(self):
        """ Done on the same day (a date without time): the last done first, though created before. """
        self.env.company.touch_activity_model_ids = self.env['ir.model']._get('res.partner')
        partner = self.env['res.partner'].create({'name': 'Touch Partner'})
        older = partner.activity_schedule(summary='Touch Older')
        newer = partner.activity_schedule(summary='Touch Newer')
        newer.action_feedback(feedback='First done')
        self.env.flush_all()
        # Each one done in its own request in real life: the first done, earlier
        self.env.cr.execute("UPDATE mail_activity SET write_date = write_date - interval '1 hour' WHERE id = %s", [newer.id])
        self.env.invalidate_all()
        older.action_feedback(feedback='Last done')
        closed = self.Touch.get_activities(closed=True)['activities']
        self.assertEqual([data['summary'] for data in closed][:2], ['Touch Older', 'Touch Newer'])
