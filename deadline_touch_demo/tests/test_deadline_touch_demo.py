from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDeadlineTouchDemo(TransactionCase):

    def test_demo(self):
        """ The templates of the demo and the projects made of them. """
        Project = self.env['project.project'].with_context(active_test=False)
        templates = Project.search([('is_template', '=', True), ('touch_ok', '=', True)])
        self.assertEqual(set(templates.mapped('name')) & {
            'Salida de residuos', 'Onboarding de empleado', 'Gestión AEAT mensual', 'Formación de taller'},
            {'Salida de residuos', 'Onboarding de empleado', 'Gestión AEAT mensual', 'Formación de taller'})
        self.assertTrue(all(templates.filtered(lambda t: t.name == 'Gestión AEAT mensual').mapped('date')), "With planned dates")
        self.assertTrue(all(templates.task_ids.filtered(lambda task: not task.parent_id).mapped('date_deadline')),
                        "With deadlines, moved to the files made of them")
        files = Project.search([('touch_template_id', 'in', templates.ids)])
        self.assertTrue(all(files.mapped('date')), "With an end, from the template")
        self.assertTrue(all(files.mapped('touch_ok')))
        self.assertGreaterEqual(len(files), 6)
        today = fields.Date.context_today(files)

        # Waste: one task each month; the last one done, this one created by its recurrence
        waste = files.filtered(lambda file: file.name == 'Salida de residuos')
        pickups = waste.task_ids.filtered(lambda task: not task.parent_id).sorted('date_deadline')
        self.assertEqual(len(pickups), 2)
        self.assertEqual(pickups.mapped('state'), ['1_done', '01_in_progress'])
        self.assertTrue(all(pickups.mapped('recurring_task')))
        self.assertEqual(pickups[1].date_deadline.month, today.month, "The one of this month")
        self.assertEqual(len(pickups[1].child_ids), 4, "With its subtasks")

        # Onboarding: the presentation waits for the training in risks, still open
        juan = files.filtered(lambda file: file.name == 'Onboarding Juan Pérez (mecánico)')
        tasks = {task.name: task for task in juan.task_ids}
        self.assertEqual(tasks['Contrato y alta en la Seguridad Social'].state, '1_done')
        self.assertEqual(tasks['Formación inicial en prevención de riesgos'].state, '01_in_progress')
        self.assertEqual(tasks['Presentación al equipo y acompañamiento la primera semana'].state, '04_waiting_normal')
        self.assertTrue(tasks['Formación inicial en prevención de riesgos'].date_deadline.date() < today, "Late")

        # AEAT: the month before the last one presented, the last one under way
        aeat = files.filtered(lambda file: file.name.startswith('AEAT')).sorted('date_start')
        self.assertEqual(len(aeat), 2)
        self.assertTrue(all(state == '1_done' for state in aeat[0].task_ids.mapped('state')))
        self.assertIn('04_waiting_normal', aeat[1].task_ids.mapped('state'), "The submission waits for the 303")

        # Training: courses with their steps as subtasks
        training = files.filtered(lambda file: file.name.startswith('Formación de taller'))
        vfu = training.task_ids.filtered(lambda task: task.name.startswith('Descontaminación'))
        self.assertEqual(sorted(vfu.child_ids.mapped('state')), ['01_in_progress', '1_done', '1_done'])
