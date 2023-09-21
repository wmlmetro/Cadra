import logging

from odoo.addons.generic_request.tests.common import RequestCase

_logger = logging.getLogger(__name__)


class TestRequestMail(RequestCase):
    """Test request base
    """

    def test_unlink_with_activities(self):
        # Test that request unlink works, even if request has mail activities
        # 1. Create request
        # 2. Add mail activity
        # 3. Unlink request
        # 4. Ensure request unlinked ok.
        request = self.env['request.request'].create({
            'type_id': self.simple_type.id,
            'request_text': 'Test',
            'user_id': self.request_manager.id,
        })

        self.assertEqual(len(request.request_event_ids), 1)
        self.assertEqual(
            request.request_event_ids.sorted()[0].event_type_id,
            self.env.ref('generic_system_event.system_event_record_created'))

        res_model = self.env['ir.model']._get(request._name)
        activity = self.env['mail.activity'].create({
            'res_model_id': res_model.id,
            'res_id': request.id,
            'summary': 'Test Activity',
            'activity_type_id': self.env.ref(
                'mail.mail_activity_data_todo').id,
        })

        self.assertEqual(
            request.request_event_ids.sorted()[0].event_type_id,
            self.env.ref(
                'generic_system_event_mail_events.'
                'generic_system_event_type_mail_activity_new'))

        request.unlink()

        self.assertFalse(request.exists())
        self.assertFalse(activity.exists())
