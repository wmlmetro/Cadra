from odoo.addons.generic_request.tests.common import RequestCase


class RequestAssignmentCase(RequestCase):

    @classmethod
    def setUpClass(cls):
        super(RequestAssignmentCase, cls).setUpClass()
        cls.assign_model = cls.env.ref(
            'generic_request_assignment.request_assign_policy_model')
        cls.example_policy = cls.env.ref(
            'generic_request_assignment.request_example_assign_policy')
        cls.policy_rule_user = cls.env.ref(
            'generic_request_assignment.request_rule_assign_user_demo')
        cls.policy_rule_eval = cls.env.ref(
            'generic_request_assignment.request_rule_assign_eval')
        cls.policy_user_field = cls.env.ref(
            'generic_request_assignment.request_rule_assign_user_field')
        cls.policy_rule_policy = cls.env.ref(
            'generic_request_assignment.request_rule_assign_policy')
        cls.request_1.write({'stage_id': cls.stage_sent.id})
        cls.user_admin = cls.env.ref("base.user_root")
        cls.demo0_user = cls.env.ref("base.demo_user0")
        cls.condition = cls.env.ref(
            "generic_request_condition."
            "condition_request_have_no_response_text")
