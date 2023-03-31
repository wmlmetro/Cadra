import ast
from odoo.tests.common import TransactionCase


class TestRequestMailSource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(TestRequestMailSource, cls).setUpClass()
        cls.template1 = cls.env.ref(
            'generic_request_mail.demo_request_creation_template1')
        cls.template2 = cls.env.ref(
            'generic_request_mail.demo_request_creation_template2')
        cls.mail_source = cls.env.ref(
            'generic_request_mail.demo_request_mail_source')

    def test_request_mail_source(self):
        self.assertEqual(
            self.mail_source.request_creation_template_id, self.template1)
        mail_alias = self.env['mail.alias'].search(
            [('alias_name', '=', self.mail_source.alias_name)])
        self.assertEqual(len(mail_alias), 1)
        alias_defaults = dict(ast.literal_eval(mail_alias.alias_defaults))
        self.assertEqual(
            alias_defaults['type_id'], self.template1.request_type_id.id)
        self.assertEqual(
            alias_defaults['category_id'],
            self.template1.request_category_id.id)
        self.assertEqual(
            alias_defaults['request_text'], self.template1.request_text)

        self.mail_source.request_creation_template_id = self.template2
        self.assertEqual(
            self.mail_source.request_creation_template_id, self.template2)
        mail_alias = self.env['mail.alias'].search(
            [('alias_name', '=', self.mail_source.alias_name)])
        alias_defaults = dict(ast.literal_eval(mail_alias.alias_defaults))
        self.assertEqual(len(mail_alias), 1)
        self.assertEqual(
            alias_defaults['type_id'], self.template2.request_type_id.id)
        self.assertEqual(
            alias_defaults['category_id'],
            self.template2.request_category_id.id)
        self.assertEqual(
            alias_defaults['request_text'], self.template2.request_text)

    def test_mail_source_change_creation_template_val(self):
        ms = self.mail_source
        self.assertEqual(ms.request_creation_template_id, self.template1)
        self.assertNotEqual(
            self.template1.request_type_id, self.template2.request_type_id)

        alias_defaults = dict(ast.literal_eval(ms.alias_defaults))
        self.assertEqual(
            alias_defaults['type_id'], self.template1.request_type_id.id)

        # Change template 1 and see that mail-source updated too
        self.template1.request_type_id = self.template2.request_type_id

        alias_defaults = dict(ast.literal_eval(ms.alias_defaults))
        self.assertEqual(
            alias_defaults['type_id'], self.template2.request_type_id.id)
