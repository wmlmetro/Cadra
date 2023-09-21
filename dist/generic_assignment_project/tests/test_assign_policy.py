from odoo.tests.common import TransactionCase, Form, tagged


@tagged("-at_install", "post_install")
class TestAssignPolicy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.project = self.env.ref('project.project_project_1')
        self.task = self.env.ref('project.project_task_1')
        self.task_policy = self.env.ref(
            'generic_assignment_project.'
            'assign_project_manager_to_project_task_policy')
        self.demo_user = self.env.ref('base.user_demo')

    def test_assign_policy(self):
        self.task.user_ids = False
        self.assertFalse(self.task.user_ids)
        self.assertEqual(self.task.project_id.user_id, self.demo_user)

        wizard_model = self.env['generic.wizard.assign'].with_context(
            default_assign_model='project.task',
            default_assign_object_ids=self.task.ids,
        )
        with Form(wizard_model) as wizard:
            wizard.assign_type = 'policy'
            wizard.assign_policy_id = self.task_policy
            wizard.save().do_assign()

        self.task.invalidate_cache()
        self.assertEqual(self.task.user_ids, self.demo_user)
