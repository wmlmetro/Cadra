from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
)


class TestRequestEvents(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestEvents, cls).setUpClass()
        cls.event_category_request_event = cls.env.ref(
            'generic_request.system_event_category_request_events')
        cls.event_category = cls.env.ref(
            'generic_request.system_event_category_request_sub_request_events')
        cls.event_category_parent = cls.env.ref(
            'generic_request.'
            'system_event_category_request_parent_request_events')
        cls.parent_request = cls.env.ref(
            'generic_request.request_request_type_simple_demo_1')
        cls.parent_stage1 = cls.env.ref(
            'generic_request.request_stage_type_simple_draft')
        cls.parent_stage2 = cls.env.ref(
            'generic_request.request_stage_type_simple_sent')
        cls.parent_stage3 = cls.env.ref(
            'generic_request.request_stage_type_simple_confirmed')
        cls.parent_route = cls.env.ref(
            'generic_request.request_stage_route_type_simple_draft_to_sent')
        cls.subrequest1 = cls.env.ref(
            'generic_request.request_request_type_access_demo_1')
        cls.subrequest2 = cls.env.ref(
            'generic_request.request_request_type_sequence_demo_1')
        cls.subrequest1_stage1 = cls.env.ref(
            'generic_request.request_stage_type_access_new')
        cls.subrequest1_stage12 = cls.env.ref(
            'generic_request.request_stage_type_access_sent')
        cls.subrequest1_stage2 = cls.env.ref(
            'generic_request.request_stage_type_access_granted')
        cls.subrequest2_stage1 = cls.env.ref(
            'generic_request.request_stage_type_sequence_new')
        cls.subrequest2_stage12 = cls.env.ref(
            'generic_request.request_stage_type_sequence_sent')
        cls.subrequest2_stage2 = cls.env.ref(
            'generic_request.request_stage_type_sequence_closed')

    def test_request_event(self):
        event = self.env['request.event'].search([
            ('request_id', '=', self.parent_request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 0)
        self.assertEqual(self.subrequest1.stage_id, self.subrequest1_stage1)
        self.assertEqual(self.subrequest2.stage_id, self.subrequest2_stage1)

        self.subrequest1.stage_id = self.subrequest1_stage12.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.parent_request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 1)
        self.assertEqual(self.subrequest1.stage_id, self.subrequest1_stage12)

        self.assertEqual(event[0].event_code, 'subrequest-stage-changed')
        self.assertEqual(event[0].subrequest_id, self.subrequest1)
        self.assertEqual(
            event[0].subrequest_old_stage_id, self.subrequest1_stage1)
        self.assertEqual(
            event[0].subrequest_new_stage_id, self.subrequest1_stage12)

        self.subrequest2.stage_id = self.subrequest2_stage12.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.parent_request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 2)
        self.assertEqual(self.subrequest2.stage_id, self.subrequest2_stage12)

        self.assertEqual(event[0].event_code, 'subrequest-stage-changed')
        self.assertEqual(event[0].subrequest_id, self.subrequest2)
        self.assertEqual(
            event[0].subrequest_old_stage_id, self.subrequest2_stage1)
        self.assertEqual(
            event[0].subrequest_new_stage_id, self.subrequest2_stage12)

        self.assertEqual(event[1].event_code, 'subrequest-stage-changed')
        self.assertEqual(event[1].subrequest_id, self.subrequest1)
        self.assertEqual(
            event[1].subrequest_old_stage_id, self.subrequest1_stage1)
        self.assertEqual(
            event[1].subrequest_new_stage_id, self.subrequest1_stage12)

        self.subrequest1.stage_id = self.subrequest1_stage2.id

        event = self.env['request.event'].search([
            ('request_id', '=', self.parent_request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 4)
        self.assertEqual(self.subrequest1.stage_id, self.subrequest1_stage2)

        self.assertEqual(event[0].event_code, 'subrequest-closed')
        self.assertEqual(event[0].subrequest_id, self.subrequest1)

        self.subrequest2.stage_id = self.subrequest2_stage2.id
        event = self.env['request.event'].search([
            ('request_id', '=', self.parent_request.id),
            ('event_type_id.event_category_id', '=', self.event_category.id)
        ])
        self.assertEqual(len(event), 7)
        self.assertEqual(self.subrequest2.stage_id, self.subrequest2_stage2)

        self.assertEqual(
            event[0].event_code, 'subrequest-all-subrequests-closed')

        self.assertEqual(event[1].event_code, 'subrequest-closed')
        self.assertEqual(event[1].subrequest_id, self.subrequest2)

        self.assertEqual(event[2].event_code, 'subrequest-stage-changed')
        self.assertEqual(event[2].subrequest_id, self.subrequest2)
        self.assertEqual(
            event[2].subrequest_old_stage_id, self.subrequest2_stage12)
        self.assertEqual(
            event[2].subrequest_new_stage_id, self.subrequest2_stage2)

        self.assertEqual(event[3].event_code, 'subrequest-closed')
        self.assertEqual(event[3].subrequest_id, self.subrequest1)

        self.assertEqual(event[4].event_code, 'subrequest-stage-changed')
        self.assertEqual(event[4].subrequest_id, self.subrequest1)
        self.assertEqual(
            event[4].subrequest_old_stage_id, self.subrequest1_stage12)
        self.assertEqual(
            event[4].subrequest_new_stage_id, self.subrequest1_stage2)

    def test_parent_request_event(self):
        self.assertEqual(self.parent_request.stage_id, self.parent_stage1)
        self.parent_request.stage_id = self.parent_stage2
        event = self.env['request.event'].search([
            ('request_id', '=', self.subrequest1.id),
            ('event_type_id.event_category_id', '=',
             self.event_category_parent.id)
        ])
        self.assertEqual(len(event), 1)
        self.assertEqual(event[0].event_code, 'parent-request-stage-changed')

        event = self.env['request.event'].search([
            ('request_id', '=', self.subrequest2.id),
            ('event_type_id.event_category_id', '=',
             self.event_category_parent.id)
        ])
        self.assertEqual(len(event), 1)
        self.assertEqual(event[0].event_code, 'parent-request-stage-changed')

        self.parent_request.stage_id = self.parent_stage3
        event = self.env['request.event'].search([
            ('request_id', '=', self.subrequest1.id),
            ('event_type_id.event_category_id', '=',
             self.event_category_parent.id)
        ])
        self.assertEqual(len(event), 3)
        self.assertEqual(event[0].event_code, 'parent-request-closed')
        self.assertEqual(event[1].event_code, 'parent-request-stage-changed')
        self.assertEqual(event[2].event_code, 'parent-request-stage-changed')

        event = self.env['request.event'].search([
            ('request_id', '=', self.subrequest2.id),
            ('event_type_id.event_category_id', '=',
             self.event_category_parent.id)
        ])
        self.assertEqual(len(event), 3)
        self.assertEqual(event[0].event_code, 'parent-request-closed')
        self.assertEqual(event[1].event_code, 'parent-request-stage-changed')
        self.assertEqual(event[2].event_code, 'parent-request-stage-changed')

        # change parent request
        wizard = self.env['request.wizard.set.parent'].with_context(
            active_model='request.request', active_ids=[self.subrequest1.id]
        ).create({})

        self.assertEqual(wizard.request_ids, self.subrequest1)
        self.assertEqual(wizard.parent_id.id, self.parent_request.id)
        wizard.parent_id = self.subrequest2
        wizard.do_set_parent()

        event = self.env['request.event'].search([
            ('request_id', '=', self.subrequest1.id),
            ('event_type_id.event_category_id', '=',
             self.event_category_parent.id)
        ])
        self.assertEqual(event[0].event_code, 'parent-request-changed')
