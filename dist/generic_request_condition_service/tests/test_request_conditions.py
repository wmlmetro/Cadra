from odoo.addons.generic_request_condition.tests import test_request_conditions


class TestRequestCondition(test_request_conditions.TestRequestConditions):
    @classmethod
    def setUpClass(cls):
        super(TestRequestCondition, cls).setUpClass()
        cls.request_service_demo = cls.env.ref(
            'generic_service.generic_service_rent_notebook')
        cls.request_service_demo_1 = cls.env.ref(
            'generic_service.generic_service_support_consulting')
        cls.type_demo = cls.env.ref(
            'generic_request_condition.request_type_conditional')

    def test_request_can_change_service_no_conditions(self):
        request = self.env['request.request'].create({
            'type_id': self.type_demo.id,
            'request_text': 'test',
            'service_id': self.request_service_demo.id
        })
        request.type_id.change_service_condition_ids = False
        self.assertEqual(request.stage_id, self.draft_stage)
        self.assertEqual(request.service_id, self.request_service_demo)
        self.assertTrue(request.can_change_service)

        # move request to sent stage
        request.stage_id = self.sent_stage

        # Check that changing service not allowed
        self.assertEqual(request.stage_id, self.sent_stage)
        self.assertEqual(request.service_id, self.request_service_demo)
        self.assertFalse(request.can_change_service)

    def test_request_can_change_service_with_conditions(self):
        request = self.env['request.request'].create({
            'type_id': self.type_demo.id,
            'request_text': 'test',
            'service_id': self.request_service_demo.id
        })
        self.assertEqual(request.stage_id, self.draft_stage)
        self.assertTrue(request.can_change_service)

        request.stage_id = self.sent_stage
        self.assertEqual(request.stage_id, self.sent_stage)
        self.assertTrue(request.can_change_service)

        request.request_text = 'confirm me'
        request.stage_id = self.confirmed_stage
        self.assertEqual(request.stage_id, self.confirmed_stage)
        self.assertFalse(request.can_change_service)

    def test_request_type_service_change(self):
        request = self.env['request.request'].create({
            'type_id': self.type_demo.id,
            'service_id': self.request_service_demo.id,
            'request_text': 'test',
        })

        # Change service
        request.write({'service_id': self.request_service_demo_1.id})
        last_event = request.request_event_ids.sorted()[0]
        self.assertEqual(last_event.event_code, 'service-changed')
        self.assertEqual(last_event.old_service_id, self.request_service_demo)
        self.assertEqual(
            last_event.new_service_id, self.request_service_demo_1)
