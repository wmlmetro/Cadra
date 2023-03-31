from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
)


class TestWizardSetParent(ReduceLoggingMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(TestWizardSetParent, cls).setUpClass()
        cls.request1 = cls.env.ref(
            'generic_request.request_request_type_simple_demo_1')
        cls.request2 = cls.env.ref(
            'generic_request.demo_request_with_complex_priority')
        cls.request3 = cls.env.ref(
            'generic_request.request_request_type_sequence_printer_request')
        cls.subrequest1 = cls.env.ref(
            'generic_request.request_request_type_access_demo_1')
        cls.type_simple = cls.env.ref(
            'generic_request.request_type_simple')
        cls.general_category = cls.env.ref(
            'generic_request.request_category_demo_general')

    def test_wizard_set_parent(self):
        wizard = self.env['request.wizard.set.parent'].with_context(
            active_model='request.request', active_ids=[self.request1.id]
        ).create({})

        self.assertEqual(wizard.request_ids, self.request1)
        self.assertEqual(wizard.parent_id.id, False)
        wizard.parent_id = self.request2
        wizard.do_set_parent()
        self.assertEqual(self.request1.parent_id, self.request2)

        wizard = self.env['request.wizard.set.parent'].with_context(
            active_model='request.request', active_ids=[
                self.subrequest1.id, self.request2.id]
        ).create({})

        self.assertEqual(set(wizard.request_ids.ids), set([
            self.subrequest1.id, self.request2.id]))
        self.assertEqual(wizard.parent_id, self.request1)
        wizard.parent_id = self.request3
        wizard.do_set_parent()
        self.assertEqual(self.subrequest1.parent_id, self.request3)
        self.assertEqual(self.request2.parent_id, self.request3)

    def test_check_default_get(self):
        Request_env = self.env['request.request']
        ParentRequest = Request_env.create({
            'type_id': self.type_simple.id,
            'category_id': self.general_category.id,
            'request_text': 'Test request',
        })
        self.assertIsNone(
            ParentRequest._context.get('generic_request_parent_id'))
        child_context = {'generic_request_parent_id': ParentRequest.id}
        ChildRequest = Request_env.with_context(**child_context).create({
            'type_id': self.type_simple.id,
            'category_id': self.general_category.id,
            'request_text': 'Test request'
        })
        self.assertEqual(ChildRequest.parent_id.id, ParentRequest.id)
        self.assertIsNone(ChildRequest.env.context.get(
            'generic_request_parent_id'))
