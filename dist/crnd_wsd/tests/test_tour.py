import logging

from odoo import exceptions, tools
from odoo.tests.common import tagged
from .phantom_common import TestPhantomTour

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestWebsiteServiceDesk(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDesk, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')

    def test_tour_request_base(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)
        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_base',
            login=self.user_demo.login)

    def test_tour_request_actions_ok(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        self.env.ref(
            'crnd_wsd.request_stage_route_type_generic_sent_to_closed'
        ).write({
            'website_published': True,
            'require_response': True,
        })

        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_actions_ok',
            login=self.user_demo.login)

    def test_tour_request_actions_redirect(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        self.env.ref(
            'crnd_wsd.request_stage_route_type_generic_sent_to_closed'
        ).write({
            'website_published': True,
            'require_response': False,
            'website_extra_action': 'redirect_to_my',
        })

        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_actions_redirect',
            login=self.user_demo.login)

    def test_tour_request_actions_not_allowed(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        req_send = self.env.ref(
            'crnd_wsd.request_stage_route_type_generic_draft_to_sent')
        req_send.allowed_user_ids = self.env.ref('base.user_root')

        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_actions_not_allowed',
            login=self.user_demo.login)

    @tools.mute_logger('odoo.addons.crnd_wsd.controllers.main')
    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # Patch create method
        def monkey_create(self, vals):
            # pylint: disable=translation-required
            if vals.get('request_text', '') == '<p>create_user_error</p>':
                raise exceptions.UserError('Test user_error')
            if vals.get('request_text', '') == '<p>create_error</p>':
                raise Exception('Test exception')
            return monkey_create.origin(self, vals)

        self.env['request.request']._patch_method('create', monkey_create)

        self._disable_use_services_setting()

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new',
            login=self.user_demo.login)

        # Revert patched method
        self.env['request.request']._revert_method('create')

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test generic request (modified)</h1>'))
        channel_website = self.env.ref(
            'generic_request.request_channel_website')
        self.assertEqual(new_requests.channel_id, channel_website)

    def test_tour_request_new_default_text(self):
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'default_request_text': 'Default text',
        })

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_default_text',
            login=self.user_demo.login)

        # Check channel 'Website' is assigned to the request
        channel_website = self.env.ref(
            'generic_request.request_channel_website')
        self.assertEqual(request.channel_id, channel_website)

    def test_tour_public_user(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'restrict'

        self._disable_use_services_setting()

        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_public_user')

    def test_tour_public_user_redirect(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'redirect'

        self._disable_use_services_setting()

        self._test_phantom_tour(
            '/', 'crnd_wsd_tour_request_public_user_redirect')

    def test_tour_public_user_create_request_to_congrat_page(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        default_website = self.env.ref('website.default_website')
        self.assertEqual(
            default_website.request_redirect_after_created_on_website,
            'congrats_page'
        )

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_public_user_create_req_to_congrat')

        self.assertEqual(len(request), 1)
        self.assertFalse(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertEqual(request.author_name, 'John Doe')
        self.assertEqual(request.email_from, 'john@doe.net')
        self.assertEqual(request.created_by_id, self.env.ref('base.user_root'))

    def test_tour_public_user_create_request_to_request_page(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        default_website = self.env.ref('website.default_website')
        self.assertEqual(
            default_website.request_redirect_after_created_on_website,
            'congrats_page'
        )
        # Change settings for redirect
        default_website.write({
            'request_redirect_after_created_on_website': 'req_page'
        })
        self.assertEqual(
            default_website.request_redirect_after_created_on_website,
            'req_page'
        )

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_public_user_create_req_to_request')

        self.assertEqual(len(request), 1)
        self.assertFalse(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertEqual(request.author_name, 'John Doe')
        self.assertEqual(request.email_from, 'john@doe.net')
        self.assertEqual(request.created_by_id, self.env.ref('base.user_root'))

    def test_tour_public_user_create_request_create_contact(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        company = self.env.user.company_id
        company.request_mail_create_author_contact_from_email = True

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_public_user_create_req_to_congrat')

        self.assertEqual(len(request), 1)
        self.assertTrue(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertFalse(request.author_name)
        self.assertFalse(request.email_from)
        self.assertEqual(request.author_id.name, 'John Doe')
        self.assertEqual(request.author_id.email, 'john@doe.net')
        self.assertEqual(request.created_by_id, self.env.ref('base.user_root'))

    def test_tour_create_request_default_option_no_phone(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        self.env.user.company_id.request_wsd_public_use_author_phone = (
            'no-phone')

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_author_no_phone')
        self.assertFalse(request.author_phone)
        self.assertEqual(request.email_from, 'test_author@email.com')

    def test_tour_create_request_phone_required(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        self.env.user.company_id.request_wsd_public_use_author_phone = (
            'required-phone')

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_author_phone_required')
        self.assertTrue(request)
        self.assertEqual(request.email_from, 'test_author@email.com')
        self.assertEqual(request.author_phone, '123456789')

    def test_tour_create_request_phone_optional_no_phone(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        self.env.user.company_id.request_wsd_public_use_author_phone = (
            'optional-phone')

        self._disable_use_services_setting()

        request_without_phone = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_author_no_phone')
        self.assertTrue(request_without_phone)
        self.assertFalse(request_without_phone.author_phone)
        self.assertEqual(request_without_phone.email_from,
                         'test_author@email.com')

    def test_tour_create_request_phone_optional_with_phone(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        self.env.user.company_id.request_wsd_public_use_author_phone = (
            'optional-phone')

        self._disable_use_services_setting()

        request_with_phone = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_tour_request_author_phone_required')
        self.assertEqual(request_with_phone.email_from,
                         'test_author@email.com')
        self.assertEqual(request_with_phone.author_phone, '123456789')

    def test_tour_request_channel_website_archived(self):
        channel_other = self.env.ref('generic_request.request_channel_other')

        # Archive channel website
        channel_website = self.env.ref(
            'generic_request.request_channel_website')
        channel_website.sudo().active = False
        channel_website.invalidate_cache()

        # Create Website request
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'default_request_text': 'Default text',
        })

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_default_text',
            login=self.user_demo.login)

        # Check that default channel assigned to the request
        self.assertEqual(request.channel_id, channel_other)

    def test_tour_request_channel_website_deleted(self):
        channel_other = self.env.ref('generic_request.request_channel_other')

        # Delete channel website
        self.env.ref(
            'generic_request.request_channel_website').sudo().unlink()

        # Create Website request
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'default_request_text': 'Default text',
        })

        self._disable_use_services_setting()

        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_default_text',
            login=self.user_demo.login)

        # Check that default channel assigned to the request
        self.assertEqual(request.channel_id, channel_other)

    def test_tour_request_new_priority_start(self):
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'complex_priority': False,
            'selection_priority_view': 'star',
        })

        self._disable_use_services_setting()

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_star',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertEqual(new_requests.priority, '3')

    def test_tour_request_new_priority_complex_start(self):
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'complex_priority': True,
            'selection_priority_view': 'star',
        })

        self._disable_use_services_setting()

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_complex_star',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertEqual(new_requests.impact, '2')
        self.assertEqual(new_requests.urgency, '1')

    def test_tour_request_new_priority_selection(self):
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'complex_priority': False,
            'selection_priority_view': 'selection',
        })

        self._disable_use_services_setting()

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_selection',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertEqual(new_requests.priority, '4')

    def test_tour_request_new_priority_complex_selection(self):
        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'complex_priority': True,
            'selection_priority_view': 'selection',
        })

        self._disable_use_services_setting()

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_complex_selection',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertEqual(new_requests.impact, '1')
        self.assertEqual(new_requests.urgency, '3')

    def test_tour_crnd_wsd_subrequest(self):
        self._disable_use_services_setting()

        self._test_phantom_tour(
            '/', 'tour_crnd_wsd_subrequest',
            login=self.user_demo.login)

    def test_tour_crnd_wsd_subrequest_additional(self):
        self._disable_use_services_setting()

        self._test_phantom_tour(
            '/', 'tour_crnd_wsd_subrequest_additional',
            login=self.user_demo.login)

    def test_tour_request_new_service(self):
        self._enable_use_services_setting()
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # TODO: refactor demo data to avoid using non-demo data
        # show on website notebook rent service
        self.env.ref('crnd_service_desk.request_type_incident').write({
            'website_published': True,
            'service_ids': [(4, self.env.ref(
                'generic_service.generic_service_default').id)],
            'category_ids': [(4, self.env.ref(
                'crnd_wsd.'
                'request_category_demo_website_support').id)],
        })
        self.env.ref('generic_service.generic_service_rent_notebook').write({
            'request_type_ids': [
                (4, self.env.ref(
                    'crnd_service_desk.request_type_incident').id),
            ],
            'category_ids': [
                (4, self.env.ref(
                    'crnd_wsd.'
                    'request_category_demo_website_support').id),
            ],
            'website_published': True,
        })

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tour_request_new_with_service',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test incident request</h1>'))
        self.assertEqual(
            new_requests.service_id,
            self.env.ref('generic_service.generic_service_default'))
