from odoo.tests.common import TransactionCase


class TestToDoActions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestToDoActions, cls).setUpClass()

        cls.test_request_type = cls.env.ref(
            'generic_request_action.request_type_action')
        cls.test_request_category = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.todo_template_on_create = cls.env.ref(
            'generic_request_todo.generic_todo_template_crnd_deploy')
        cls.stage_sent = cls.env.ref(
            'generic_request_action.request_stage_type_action_sent')
        cls.stage_rejected = cls.env.ref(
            'generic_request_action.request_stage_type_action_rejected')

    def test_actions_todo(self):
        request = self.env['request.request'].create({
            'category_id': self.test_request_category.id,
            'type_id': self.test_request_type.id,
            'request_text': 'Test request todo'
        })

        # Check todoes created properly
        template_todo_line_list_names = \
            self.todo_template_on_create.todo_template_line_ids.mapped('name')
        request_todo_line_list_names = request.generic_todo_ids.mapped('name')
        self.assertEqual(len(request_todo_line_list_names), 4)
        self.assertTrue(all(request.generic_todo_ids.mapped('active')))
        self.assertListEqual(
            template_todo_line_list_names, request_todo_line_list_names)

        # Create todoes template and action for rewrite test
        rewrite_template = self.env['generic.todo.template'].create({
            'name': 'Test rewrite todo template'
        })
        self.env['generic.todo.template.line'].create([{
            'name': 'Test rewrite todo line1',
            'todo_template_id': rewrite_template.id,
            'todo_type_id': self.env.ref(
                'generic_todo.generic_todo_type_simple').id
        }, {
            'name': 'Test rewrite todo line2',
            'todo_template_id': rewrite_template.id,
            'todo_type_id': self.env.ref(
                'generic_todo.generic_todo_type_simple').id
        }])

        self.env['request.event.action'].create({
            'name': 'Action test rewrite todoes',
            'event_type_ids': [(4, self.env.ref(
                'generic_request.request_event_type_stage_changed').id)],
            'request_type_id': self.test_request_type.id,
            'act_type': 'generic-todo',
            'generic_todo_action': 'rewrite',
            'generic_todo_template_id': rewrite_template.id,
        })

        # Change request stage and check todoes created properly
        request.stage_id = self.stage_sent
        template_todo_line_list_names = \
            rewrite_template.todo_template_line_ids.mapped('name')
        request_todo_line_list_names = request.generic_todo_ids.mapped('name')
        self.assertEqual(len(request_todo_line_list_names), 2)
        self.assertTrue(all(request.generic_todo_ids.mapped('active')))
        self.assertListEqual(
            template_todo_line_list_names, request_todo_line_list_names)

        # Close request and check todoes are cleared (inactive)
        request.stage_id = self.stage_rejected
        self.assertFalse(any(request.generic_todo_ids.mapped('active')))
