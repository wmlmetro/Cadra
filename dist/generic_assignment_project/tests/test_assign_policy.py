from odoo.tests.common import TransactionCase


class TestAssignPolicy(TransactionCase):

    def setUp(self):
        self.project = self.env.ref('project.project_project_data')
        self.task = self.env.ref('project.project_task_data_1')
        self.task_policy = self.env.ref(
            'assign_project_manager_to_project_task_policy')

    def test_assign_policy(self):

        self.task.user_id = False
        self.assertEqual(self.task.user_id, False)
        wizard = self.env['generic.wizard.assign']
        wizard.assign_policy_id.do_assign(self.task_policy)
        self.assertEqual(self.task.user_ids, self.project.user_id)
