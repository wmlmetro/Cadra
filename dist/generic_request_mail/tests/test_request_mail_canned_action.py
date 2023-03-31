import logging

from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin

_logger = logging.getLogger(__name__)


class TestRequestMailCanned(ReduceLoggingMixin, TransactionCase):

    def test_request_mail_canned_action(self):
        # create tests shortcodes
        MailShortcode = self.env['mail.shortcode']

        shc1 = MailShortcode.create({
            'source': 't1',
            'substitution': 'It is first shortcode for tests.',
        })

        shc2 = MailShortcode.create({
            'source': 't2',
            'substitution': 'It is second shortcode for tests.',
        })

        # get request_mail_shortcode action
        action = self.env.ref(
            'generic_request_mail.request_canned_response_action')
        result = action.read()[0]

        # ensure mail.shortcode model and domain
        self.assertEqual(result.get('res_model'), 'mail.shortcode')
        self.assertEqual(result.get('domain'), "[]")

        # search shortcodes
        shortcodes = MailShortcode.search([])

        # ensure new shortcodes
        self.assertIn(shc1.id, shortcodes.ids)
        self.assertIn(shc2.id, shortcodes.ids)
