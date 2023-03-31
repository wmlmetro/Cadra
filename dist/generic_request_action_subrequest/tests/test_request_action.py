from odoo import fields
from odoo.addons.generic_request_action.tests.common import (
    RouteActionsTestCase
)


class TestRouteActionsSubrequest(RouteActionsTestCase):

    @classmethod
    def setUpClass(cls):
        super(TestRouteActionsSubrequest, cls).setUpClass()

        # Subrequest creation template
        cls.request_creation_template = cls.env.ref(
            "generic_request_action_subrequest."
            "demo_request_creation_template_for_action")

        # Subrequest type
        cls.request_type_seq = cls.env.ref(
            'generic_request.request_type_sequence')
        cls.request_type_seq_st_new = cls.env.ref(
            'generic_request.request_stage_type_sequence_new')
        cls.request_type_seq_st_sent = cls.env.ref(
            'generic_request.request_stage_type_sequence_sent')
        cls.request_type_seq_rt = cls.env.ref(
            'generic_request.request_stage_route_type_sequence_new_to_sent')

        # Action subrequest
        cls.act_subrequest = cls.env['request.event.action'].create({
            'name': 'Subrequest',
            'event_type_ids': [
                (4, cls.env.ref(
                    'generic_request.request_event_type_stage_changed').id)],
            'request_type_id': cls.request_type.id,
            'route_id': cls.route_send.id,
            'act_type': 'subrequest',
            'subrequest_template_id': cls.request_creation_template.id,
            'subrequest_text': 'Subrequest for {{ request.name }}',
        })

    def test_10_route_action_subrequest_simple(self):
        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        # Set deadline for request
        request.deadline_date = fields.Date.today()

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        subrequest = request.child_ids
        self.assertEqual(subrequest.type_id, self.request_type_seq)
        self.assertEqual(subrequest.stage_id,
                         self.request_type_seq_st_new)
        self.assertFalse(subrequest.user_id)
        self.assertEqual(
            subrequest.request_text,
            '<p>Subrequest for %s</p>' % request.name)
        self.assertEqual(subrequest.author_id, self.env.user.partner_id)

        # Root user has no parent company, so partner_id have to be False
        self.assertFalse(subrequest.partner_id)

        # Subrequest has no deadline
        self.assertFalse(subrequest.deadline_date)

    def test_20_route_action_subrequest_same_author(self):
        # Copy author of parent request
        self.act_subrequest.subrequest_same_author = True

        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        subrequest = request.child_ids
        self.assertEqual(subrequest.type_id, self.request_type_seq)
        self.assertEqual(subrequest.stage_id, self.request_type_seq_st_new)
        self.assertFalse(subrequest.user_id)
        self.assertEqual(
            subrequest.request_text,
            '<p>Subrequest for %s</p>' % request.name)
        self.assertEqual(
            subrequest.author_id, self.env.ref('base.res_partner_address_2'))
        self.assertEqual(
            subrequest.partner_id, self.env.ref('base.res_partner_1'))

    def test_30_route_action_subrequest_trigger_route(self):
        # Modify action to automaticaly trigger subrequest route
        self.act_subrequest.subrequest_trigger_route_id = (
            self.request_type_seq_rt)

        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        self.assertEqual(request.child_ids.type_id, self.request_type_seq)
        self.assertEqual(request.child_ids.stage_id,
                         self.request_type_seq_st_sent)
        self.assertFalse(request.child_ids.user_id)
        self.assertEqual(
            request.child_ids.request_text,
            '<p>Subrequest for %s</p>' % request.name)

    def test_40_route_action_subrequest_same_deadline(self):
        # Copy author of parent request
        self.act_subrequest.subrequest_same_deadline = True

        request = self.demo_request
        request.deadline_date = fields.Date.today()
        self.assertEqual(request.stage_id, self.stage_draft)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        subrequest = request.child_ids
        self.assertTrue(subrequest.deadline_date)
        self.assertEqual(subrequest.deadline_date, request.deadline_date)

    def test_50_route_action_subrequest_same_priority(self):
        # Copy author of parent request
        self.act_subrequest.write({
            'subrequest_transfer_field_ids': [(6, 0, [
                self.env['ir.model.fields']._get(
                    'request.request', 'priority'
                ).id,
            ])],
        })

        request = self.demo_request
        self.assertEqual(request.priority, '3')

        request.priority = '5'
        self.assertEqual(request.stage_id, self.stage_draft)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Check that subrequest created
        self.assertEqual(request.child_count, 1)
        subrequest = request.child_ids
        self.assertEqual(subrequest.priority, '5')
