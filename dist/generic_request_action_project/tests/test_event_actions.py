from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin


class TestStageRouteActions(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestStageRouteActions, cls).setUpClass()
        cls.test_request_type = cls.env.ref(
            'generic_request_project.request_type_with_task')
        cls.test_route = cls.env.ref(
            'generic_request_project.'
            'request_stage_type_with_task_draft_to_new')
        cls.stage_draft = cls.env.ref(
            'generic_request_project.request_stage_type_with_task_draft')
        cls.stage_new = cls.env.ref(
            'generic_request_project.request_stage_type_with_task_new')
        cls.task_project_id = cls.env.ref(
            'generic_request_project.'
            'request_with_task_project_1')
        cls.task_stage_id = cls.env.ref('project.project_stage_0')
        cls.test_action = cls.env.ref(
            'generic_request_action_project.'
            'demo_create_project_task_action')
        cls.test_request = cls.env.ref(
            'generic_request_action_project.demo_request_with_task_3')
        cls.demo_user = cls.env.ref('base.user_demo')
        cls.test_project = cls.env.ref('project.project_project_1')
        cls.test_category = cls.env.ref(
            'generic_request.request_category_demo_technical')

    def test_stage_route_actions(self):
        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        # move along the route
        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertEqual(self.test_request.project_task_ids.stage_id,
                         self.test_action.task_stage_id)
        self.assertEqual(
            self.test_request.project_task_ids.name,
            "Task for request %s" % self.test_request.name,
        )

    def test_task_assign_user(self):
        self.test_action.task_assign_type = 'user'
        self.test_action.task_user_id = self.demo_user
        self.assertEqual(self.test_action.task_assign_type, 'user')
        self.assertEqual(self.test_action.task_user_id, self.demo_user)

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertEqual(
            self.test_request.project_task_ids.user_ids, self.demo_user)

    def test_task_assign_user_from_request(self):
        self.test_action.task_assign_type = 'request-user'
        self.test_request.user_id = self.demo_user

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertEqual(
            self.test_request.project_task_ids.user_ids, self.demo_user)

    def test_task_assign_user_from_request__no_user(self):
        self.test_action.task_assign_type = 'request-user'
        self.assertFalse(self.test_request.user_id)

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertFalse(self.test_request.project_task_ids.user_ids)

    def test_task_project_compute_type(self):
        self.test_request.category_id = self.test_category
        self.assertEqual(self.test_request.category_id, self.test_category)
        self.assertEqual(self.test_request.project_task_count, 2)

        task = self.env['project.task'].search([
            ('request_id', '=', self.test_request.id),
            ('name', '=', 'Project for this task selected by domain'),
        ])
        self.assertEqual(len(task), 1)
        self.assertEqual(task.project_id, self.test_project)

        task = self.env['project.task'].search([
            ('request_id', '=', self.test_request.id),
            ('name', '=',
             'Project for this task selected by python expression'),
        ])
        self.assertEqual(len(task), 1)
        self.assertEqual(task.project_id, self.test_project)

    def test_task_project_from_request__no_project(self):
        self.test_action.task_project_compute_type = 'request'
        self.assertFalse(self.test_request.project_id)

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertFalse(self.test_request.project_task_ids.project_id)

    def test_task_project_from_request__with_project(self):
        self.test_request.project_id = self.test_project
        self.test_action.task_project_compute_type = 'request'

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertEqual(
            self.test_request.project_task_ids.project_id, self.test_project)

    def test_task_use_same_deadline(self):
        self.test_action.task_use_request_deadline = True
        self.test_request.deadline_date = fields.Date.today()

        self.assertEqual(self.test_request.stage_id, self.stage_draft)
        self.assertEqual(len(self.test_request.project_task_ids), 0)

        self.test_request.stage_id = self.stage_new
        self.assertEqual(self.test_request.stage_id, self.stage_new)

        self.assertEqual(len(self.test_request.project_task_ids), 1)
        self.assertTrue(self.test_request.project_task_ids.date_deadline)
        self.assertEqual(
            self.test_request.project_task_ids.date_deadline,
            self.test_request.deadline_date)
