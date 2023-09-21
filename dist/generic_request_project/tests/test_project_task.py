from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin
from odoo.addons.generic_system_event.tests.common import (
    GenericSystemTestUtils,
)


class TestRequestProject(ReduceLoggingMixin,
                         GenericSystemTestUtils,
                         TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestProject, cls).setUpClass()
        cls.event_category = cls.env.ref(
            'generic_request_project.'
            'system_event_category_request_project_task_events')
        cls.request = cls.env.ref(
            'generic_request_project.demo_request_with_task')
        cls.task_1 = cls.env.ref(
            'generic_request_project.request_with_task_task_1')
        cls.task_2 = cls.env.ref(
            'generic_request_project.request_with_task_task_2')
        cls.task_stage_0 = cls.env.ref('project.project_stage_0')
        cls.task_stage_1 = cls.env.ref('project.project_stage_1')
        cls.task_stage_2 = cls.env.ref('project.project_stage_2')
        cls.stage_changed = cls.env.ref(
            'generic_request_project.request_event_type_task_stage_changed')
        cls.project = cls.env.ref(
            'generic_request_project.request_with_task_project_1')

    def test_create_task_from_request(self):
        request = self.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        action = request.action_show_related_tasks()

        task = self.env[action['res_model']].with_context(
            **action['context']).create({})
        self.assertEqual(request.project_task_count, 1)
        self.assertIn(task, request.project_task_ids)
        self.assertEqual(task.name, 'Request %s' % request.name)
        self.assertEqual(task.description, request.request_text)
        self.assertIn(self.env.user, task.user_ids,)
        self.assertFalse(task.project_id)

    def test_create_task_from_request_2(self):
        request = self.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        action = request.action_create_task()
        self.assertEqual(action['view_mode'], 'form')

        task = self.env[action['res_model']].with_context(
            **action['context']).create({})
        self.assertEqual(request.project_task_count, 1)
        self.assertIn(task, request.project_task_ids)
        self.assertEqual(task.name, 'Request %s' % request.name)
        self.assertEqual(task.description, request.request_text)
        self.assertIn(self.env.user, task.user_ids)
        self.assertFalse(task.project_id)

    def test_create_task_from_request_project(self):
        request = self.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        request.project_id = self.project
        action = request.action_show_related_tasks()

        task = self.env[action['res_model']].with_context(
            **action['context']).create({})
        self.assertEqual(request.project_task_count, 1)
        self.assertIn(task, request.project_task_ids)
        self.assertEqual(task.name, 'Request %s' % request.name)
        self.assertEqual(task.description, request.request_text)
        self.assertIn(self.env.user, task.user_ids)
        self.assertEqual(task.project_id, self.project)

    def test_create_task_from_request_project_2(self):
        request = self.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        request.project_id = self.project
        action = request.action_create_task()
        self.assertEqual(action['view_mode'], 'form')

        task = self.env[action['res_model']].with_context(
            **action['context']).create({})
        self.assertEqual(request.project_task_count, 1)
        self.assertIn(task, request.project_task_ids)
        self.assertEqual(task.name, 'Request %s' % request.name)
        self.assertEqual(task.description, request.request_text)
        self.assertIn(self.env.user, task.user_ids)
        self.assertEqual(task.project_id, self.project)

    def test_create_task_from_assigned_request(self):
        request = self.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        request.user_id = self.env.ref('generic_request.user_demo_request')
        action = request.action_show_related_tasks()

        task = self.env[action['res_model']].with_context(
            **action['context']).create({})
        self.assertEqual(request.project_task_count, 1)
        self.assertIn(task, request.project_task_ids)
        self.assertEqual(task.name, 'Request %s' % request.name)
        self.assertEqual(task.description, request.request_text)
        self.assertIn(request.user_id, task.user_ids)

    def test_task_events(self):
        self.assertEqual(self.task_1.stage_id, self.task_stage_0)
        self.assertEqual(self.task_2.stage_id, self.task_stage_0)
        event = self.env['request.event'].search([
            ('request_id', '=', self.request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 0)

        self.task_1.stage_id = self.task_stage_1.id
        self.assertEqual(self.task_1.stage_id, self.task_stage_1)

        event = self.env['request.event'].search([
            ('event_type_id.event_category_id', '=', self.event_category.id),
            ('request_id', '=', self.request.id)
        ])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.event_code, 'task-stage-changed')
        self.assertEqual(event.task_old_stage_id, self.task_stage_0)
        self.assertEqual(event.task_new_stage_id, self.task_stage_1)

        self.task_2.stage_id = self.task_stage_1.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id),
        ], order='event_date, id')
        self.assertEqual(len(event), 2)
        self.assertEqual(event[0].task_id.id, self.task_1.id)
        self.assertEqual(event[0].task_old_stage_id, self.task_stage_0)
        self.assertEqual(event[0].task_new_stage_id, self.task_stage_1)
        self.assertEqual(event[1].task_id.id, self.task_2.id)
        self.assertEqual(event[1].task_old_stage_id, self.task_stage_0)
        self.assertEqual(event[1].task_new_stage_id, self.task_stage_1)

        self.task_1.stage_id = self.task_stage_2.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id),
        ])

        self.assertEqual(event[0].event_code, 'task-closed')
        self.assertEqual(event[0].task_id, self.task_1)
        self.assertEqual(event[0].task_old_stage_id, self.task_stage_1)
        self.assertEqual(event[0].task_new_stage_id, self.task_stage_2)
        self.assertEqual(event[1].event_code, 'task-stage-changed')
        self.assertEqual(event[1].task_id, self.task_1)
        self.assertEqual(event[2].event_code, 'task-stage-changed')
        self.assertEqual(event[2].task_id, self.task_2)
        self.assertEqual(event[3].event_code, 'task-stage-changed')
        self.assertEqual(event[3].task_id, self.task_1)

        self.task_2.stage_id = self.task_stage_2.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id),
        ])

        self.assertEqual(event[0].event_code, 'task-all-tasks-closed')
        self.assertEqual(event[1].event_code, 'task-closed')
        self.assertEqual(event[1].task_id, self.task_2)
        self.assertEqual(event[2].event_code, 'task-stage-changed')
        self.assertEqual(event[2].task_id, self.task_2)
        self.assertEqual(event[3].event_code, 'task-closed')
        self.assertEqual(event[3].task_id, self.task_1)
        self.assertEqual(event[4].event_code, 'task-stage-changed')
        self.assertEqual(event[4].task_id, self.task_1)
        self.assertEqual(event[5].event_code, 'task-stage-changed')
        self.assertEqual(event[5].task_id, self.task_2)
        self.assertEqual(event[6].event_code, 'task-stage-changed')
        self.assertEqual(event[6].task_id, self.task_1)

    def test_project_changed(self):
        self.assertFalse(self.request.project_id)

        self.request.project_id = self.project
        last_event = self.request.request_event_ids.sorted()[0]
        self.assertEqual(
            last_event.event_code, 'project-changed')
        self.assertFalse(last_event.old_project_id)
        self.assertEqual(last_event.new_project_id, self.project)

        self.request.project_id = False
        last_event = self.request.request_event_ids.sorted()[0]
        self.assertEqual(
            last_event.event_code, 'project-changed')
        self.assertEqual(last_event.old_project_id, self.project)
        self.assertFalse(last_event.new_project_id)

    def test_project_request_access_rights(self):
        # Test that user who have no access to request can change stage on
        # project task
        user = self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Demo project user',
            'login': 'demo-project-request-user',
            'email': 'demo-project-request-user@example.com',
            'groups_id': [
                (6, 0, [self.env.ref('project.group_project_user').id])],
        })
        # Change stage of task
        self.task_1.with_user(user).stage_id = self.task_stage_1

        self.assertEqual(
            self._get_last_event(self.request).event_code,
            'task-stage-changed')
        self.assertEqual(
            self._get_last_event(self.request).user_id, user)
