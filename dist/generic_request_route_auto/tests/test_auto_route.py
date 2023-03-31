import logging
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinMT,
    ReduceLoggingMixin,
)

_logger = logging.getLogger(__name__)


class TestRouteActionsAuto(ReduceLoggingMixin,
                           AccessRulesFixMixinMT,
                           TransactionCase):

    def setUp(self):
        super(TestRouteActionsAuto, self).setUp()
        self.request_category = self.env.ref(
            'generic_request.request_category_demo_general')

        # Request type auto
        self.request_type_auto = self.env.ref(
            'generic_request_route_auto.request_type_auto')
        self.auto_stage_draft = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_draft')
        self.auto_stage_sent = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_sent')
        self.auto_stage_confirmed = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_confirmed')
        self.auto_stage_rejected = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_rejected')
        self.auto_route_send = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_draft_to_sent')
        self.auto_route_confirm = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_confirmed')
        self.auto_route_reject = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_rejected')

    def test_request_route_view_triggers(self):
        route = self.auto_route_confirm
        action = route.action_request_stage_route_trigger_actions()
        self.assertEqual(action['context']['default_route_id'], route.id)
        triggers = self.env[action['res_model']].search(action['domain'])
        self.assertEqual(triggers, route.trigger_ids)
        self.assertEqual(route.trigger_count, len(triggers))
