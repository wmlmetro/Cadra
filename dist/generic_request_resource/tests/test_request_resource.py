from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinST,
    ReduceLoggingMixin,
)


class RequestResourceCase(ReduceLoggingMixin,
                          AccessRulesFixMixinST,
                          TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(RequestResourceCase, cls).setUpClass()
        cls.type_simple = cls.env.ref(
            'generic_request.request_type_simple')
        cls.Request = cls.env['request.request']

    def test_request_resource_changed_event_created(self):
        request = self.Request.create({
            'request_text': 'event resource changed test',
            'type_id': self.type_simple.id,
        })
        self.assertEqual(request.request_event_count, 1)
        self.assertEqual(request.request_event_ids.event_type_id.code,
                         'record-created')
        request.resource_id = 1
        self.assertSetEqual(
            set(request.request_event_ids.mapped('event_type_id.code')),
            {'record-created', 'resource-changed'})
        self.assertEqual(request.request_event_count, 2)
