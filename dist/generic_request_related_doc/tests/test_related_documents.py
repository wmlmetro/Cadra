from odoo.tests import common
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin


class RequestRelatedDocCase(ReduceLoggingMixin, common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(RequestRelatedDocCase, cls).setUpClass()

        cls.rel_doc = cls.env.ref(
            'generic_request_related_doc.'
            'request_request_type_sale_problem_demo_1_related_document_1')
        cls.rel_doc_type = cls.env.ref(
            'generic_request_related_doc.related_document_type__res_partner')
        cls.rel_doc_object = cls.env.ref(
            'base.res_partner_1')

    def test_rel_doc_name_get(self):
        self.assertEqual(
            self.rel_doc.doc_model, self.rel_doc_object._name)
        self.assertEqual(
            self.rel_doc.doc_id, self.rel_doc_object.id)
        self.assertEqual(
            self.rel_doc.display_name,
            self.rel_doc_object.display_name)

    def test_rel_doc_open_object_action(self):
        action = self.rel_doc.action_open_document_object()
        self.assertEqual(
            action['type'], 'ir.actions.act_window')
        self.assertEqual(
            action['res_model'], self.rel_doc_object._name)
        self.assertEqual(
            action['res_id'], self.rel_doc_object.id)

    def test_create_same_doc_type(self):
        new_doc_type = self.env['request.related.document.type'].create({
            'model_id': self.rel_doc_type.model_id.id,
            'name': 'Test',
        })
        self.assertEqual(
            new_doc_type.id, self.rel_doc_type.id)

    def test_context_action(self):
        self.assertFalse(self.rel_doc_type.request_action_id)
        self.assertFalse(self.rel_doc_type.request_action_name)
        self.assertFalse(self.rel_doc_type.request_action_toggle)

        # toggle (enable) request action button
        self.rel_doc_type.request_action_toggle = True

        self.assertTrue(self.rel_doc_type.request_action_id)
        self.assertTrue(self.rel_doc_type.request_action_name)
        self.assertTrue(self.rel_doc_type.request_action_toggle)

        # toggle (disable) request action button
        self.rel_doc_type.request_action_toggle = False

        action = self.rel_doc_type.request_action_id

        self.assertFalse(self.rel_doc_type.request_action_id)
        self.assertFalse(self.rel_doc_type.request_action_name)
        self.assertFalse(self.rel_doc_type.request_action_toggle)

        self.assertFalse(action.exists())
