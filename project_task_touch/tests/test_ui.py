from freezegun import freeze_time

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProjectTaskTouchUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project']
        cls.template = Project.create({'name': 'Tour Template', 'touch_ok': True})
        cls.template._toggle_template_mode(True)
        cls.env['project.task'].create({'name': 'Tour Template Step', 'project_id': cls.template.id})
        cls.project = Project.create({'name': 'Tour Project', 'touch_ok': True})
        existing = cls.env['project.task'].create({'name': 'Tour Existing Task', 'project_id': cls.project.id})
        # The nearest deadline first, then the highest priority
        Task = cls.env['project.task']
        Task.create({'name': 'Tour Later Task', 'project_id': cls.project.id, 'date_deadline': '2030-02-01 12:00:00'})
        Task.create({'name': 'Tour Sooner Task', 'project_id': cls.project.id, 'date_deadline': '2030-01-01 12:00:00'})
        Task.create({'name': 'Tour Urgent Task', 'project_id': cls.project.id, 'priority': '1'})
        other = Project.create({'name': 'Tour Other', 'touch_ok': True})
        cls.env['project.task'].create({'name': 'Tour Other Task', 'project_id': other.id})
        cls.env['project.task'].create({'name': 'Tour Subtask', 'project_id': cls.project.id, 'parent_id': existing.id})
        # Closed: the last closed first, though created before
        last_closed, first_closed = Task.create([
            {'name': 'Tour Last Closed', 'project_id': cls.project.id},
            {'name': 'Tour First Closed', 'project_id': cls.project.id},
        ])
        for task, moment in ((first_closed, '2026-11-01 10:00:00'), (last_closed, '2026-11-02 10:00:00')):
            with freeze_time(moment):
                task.state = '1_done'
                cls.env.flush_all()
        cls.activity = existing.activity_schedule(summary='Tour Call')
        cls.activity.touch_ok = True
        new_test_user(cls.env, login='touch_tour', name='Touch Tour', groups='project.group_project_manager')

    def test_files(self):
        self.start_tour('/odoo/expedientes', 'project_task_touch_tour', login='touch_tour')
        project = self.env['project.project'].search([('name', '=', 'Tour File')])
        self.assertEqual(project.touch_template_id, self.template)
        self.assertTrue(project.touch_ok)
        task = self.env['project.task'].search([('name', '=', 'Tour New Task')])
        self.assertEqual(task.project_id, project)
        subtasks = self.env['project.task'].search([('name', 'like', 'Tour Subtask')], order='id')
        self.assertEqual([(subtask.name, subtask.state) for subtask in subtasks],
                         [('Tour Subtask', '1_done'), ('Tour Subtask 2', '01_in_progress')])
        self.assertEqual(subtasks[1].parent_id.name, 'Tour Existing Task')
        self.assertFalse(self.activity.active)
        self.assertEqual(self.activity.feedback, 'Tour feedback')
        self.assertEqual(task.state, '04_waiting_normal', "Approved on its card, then dragged to Waiting")
