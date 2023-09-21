from odoo.addons.generic_request_action.tests.common import (
    RouteActionsTestCase
)


class TestRouteActionsSubrequest(RouteActionsTestCase):

    @classmethod
    def setUpClass(cls):
        super(TestRouteActionsSubrequest, cls).setUpClass()

        # Subrequest type
        cls.request_type_seq = cls.env.ref(
            'generic_request.request_type_sequence')
        cls.request_type_seq_st_new = cls.env.ref(
            'generic_request.request_stage_type_sequence_new')

        # Subrequest creation template
        cls.request_creation_template = cls.env.ref(
            "generic_request_action."
            "demo_request_creation_template_for_action")

        # Action subrequest
        cls.assign_policy = cls.env.ref(
            'generic_request_assignment.request_example_assign_policy')
        cls.act_subrequest = cls.env['request.event.action'].create({
            'name': 'Subrequest',
            'event_type_ids': [
                (4, cls.env.ref(
                    'generic_request.request_event_type_stage_changed').id)],
            'request_type_id': cls.request_type.id,
            'route_id': cls.route_send.id,
            'act_type': 'subrequest',
            'subrequest_template_id': cls.request_creation_template.id,
            'subrequest_text': 'Subrequest',
            'subrequest_assign_policy_id': cls.assign_policy.id,
        })

    def test_10_route_action_subrequest_assign(self):
        self.env.ref('base.demo_user0').groups_id += self.env.ref(
            'generic_request.group_request_user_implicit')
        # Create request
        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        self.assertEqual(request.child_ids.type_id, self.request_type_seq)
        self.assertEqual(request.child_ids.stage_id,
                         self.request_type_seq_st_new)
        self.assertEqual(
            request.child_ids.user_id, self.env.ref('base.user_demo'))
        self.assertEqual(request.child_ids.request_text, '<p>Subrequest</p>')
