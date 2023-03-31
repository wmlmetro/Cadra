from odoo.addons.generic_request_action.tests.common import (
    RouteActionsTestCase)


class TestRouteActions(RouteActionsTestCase):
    def setUp(self):
        super(TestRouteActions, self).setUp()
        self.action_add = self.env(
            'generic_request_action_tag.'
            'request_event_action_add_tag_on_create')
        self.action_remove = self.env(
            'generic_request_action_tag.'
            'request_event_action_remove_tag_on_stage_changed')

    def test_action_tag(self):
        request = self.env['request.request'].with_user(
            self.demo_manager).create({
                'type_id': self.request_type.id,
                'category_id': self.request_category.id,
                'request_text': 'Test request',
            })
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertEqual(len(request.tag_ids), 2)

        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)
        self.assertEqual(len(request.tag_ids), 1)
