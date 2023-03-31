from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin


class RouteActionsTestCase(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(RouteActionsTestCase, cls).setUpClass()
        cls.request_type = cls.env.ref(
            'generic_request_action.request_type_action')
        cls.request_category = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.stage_draft = cls.env.ref(
            'generic_request_action.request_stage_type_action_draft')
        cls.stage_sent = cls.env.ref(
            'generic_request_action.request_stage_type_action_sent')
        cls.stage_rejected = cls.env.ref(
            'generic_request_action.request_stage_type_action_rejected')

        cls.route_send = cls.env.ref(
            'generic_request_action.'
            'request_stage_route_type_action_draft_to_sent')

        cls.action_set_response = cls.env.ref(
            'generic_request_action'
            '.request_stage_route_type_action_sent_to_rejected_set_response')

        cls.action_assign = cls.env.ref(
            'generic_request_action.'
            'request_stage_route_type_action_draft_to_sent_assign')
        cls.condition_do_assign = cls.env.ref(
            'generic_request_action.'
            'condition_request_text_is_do_assign')
        cls.condition_event_do_assign = cls.env.ref(
            'generic_request_action.'
            'condition_event_request_text_is_do_assign')

        # Demo users
        cls.demo_manager = cls.env.ref(
            'generic_request.user_demo_request_manager')
        cls.demo_manager_2 = cls.env.ref(
            'generic_request.user_demo_request_manager_2')

        # Demo request
        cls.demo_request = cls.env.ref(
            'generic_request_action.request_request_type_action_demo_1')
