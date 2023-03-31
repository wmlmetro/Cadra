from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin


class TestWizardLogWork(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestWizardLogWork, cls).setUpClass()
        cls.request = cls.env.ref(
            'generic_request_project.demo_request_with_complex_task')
        cls.task = cls.env.ref(
            'generic_request_project.project_task_development')
        cls.timesheet_line = cls.env.ref(
            'generic_request_project.working_hours_task_development')

    def test_log_work_wizard(self):
        self.assertEqual(len(self.task.timesheet_ids), 1)
        self.assertEqual(self.task.timesheet_ids, self.timesheet_line)
        self.assertEqual(self.timesheet_line.unit_amount, 1)

        act = self.request.action_request_work_log()

        self.env[act['res_model']].with_context(
            **act['context']
        ).create({
            'task_id': self.task.id,
            'timesheet_ids': [
                (1, self.timesheet_line.id, {'unit_amount': 2}),
            ],
        })
        self.assertEqual(self.timesheet_line.unit_amount, 2)

        self.env[act['res_model']].with_context(
            **act['context']
        ).create({
            'task_id': self.task.id,
            'timesheet_ids': [
                (1, self.timesheet_line.id, {'unit_amount': 3}),
                (0, 0, {
                    'employee_id': self.timesheet_line.employee_id.id,
                    'name': 'Test',
                    'project_id': self.task.project_id.id,
                    'unit_amount': 1,
                    'user_id': self.env.user.id,
                }),
            ],
        })
        self.assertEqual(self.timesheet_line.unit_amount, 3)
        self.assertEqual(len(self.task.timesheet_ids), 2)
        self.assertEqual(
            (self.task.timesheet_ids - self.timesheet_line).unit_amount,
            1)
