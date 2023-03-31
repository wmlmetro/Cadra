from odoo.osv import expression
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinST,
    ReduceLoggingMixin,
)


class RequestServiceCase(ReduceLoggingMixin,
                         AccessRulesFixMixinST,
                         TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(RequestServiceCase, cls).setUpClass()
        cls.service_level_1 = cls.env.ref(
            'generic_service.generic_service_level_1')
        cls.service_level_2 = cls.env.ref(
            'generic_service.generic_service_level_2')
        cls.type_simple = cls.env.ref(
            'generic_request.request_type_simple')
        cls.stage_draft = cls.env.ref(
            'generic_request.request_stage_type_simple_draft')
        cls.stage_sent = cls.env.ref(
            'generic_request.request_stage_type_simple_sent')
        cls.request_partner = cls.env.ref('base.res_partner_2')
        cls.request_partner_fake = cls.env.ref('base.res_partner_3')
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.Request = cls.env['request.request']
        cls.request = cls.env.ref(
            "generic_request.request_request_type_sequence_demo_1")
        cls.request_reopen_1 = cls.env.ref(
            "generic_request.request_request_reopen_main_1")

        cls.request.stage_id = cls.env.ref(
            "generic_request.request_stage_type_sequence_sent")
        cls.new_reopen_1_route = cls.env.ref(
            'generic_request.'
            'request_stage_route_type_reopen_main_new_to_classified')

        cls.close_reopen_route = cls.env.ref(
            'generic_request.'
            'request_stage_route_type_sequence_sent_to_grant')
        cls.close_route = cls.env.ref(
            'generic_request.request_stage_route_type_sequence_sent_to_closed')
        cls.new_request_type = cls.env.ref(
            'generic_request.request_type_access')
        cls.new_request_category = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')
        cls.new_request_category_gen = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.new_request_type = cls.env.ref(
            'generic_request.request_type_access')
        cls.new_request_type_reop_no_categ = cls.env.ref(
            'generic_request.request_type_reopen_as_type_no_categ')
        cls.new_request_type_reop_categ_1 = cls.env.ref(
            'generic_request.request_type_reopen_as_type_categ_1')
        cls.new_request_type_reop_categ_2 = cls.env.ref(
            'generic_request.request_type_reopen_as_type_categ_2')

    def test_request_wizard_close_onchanges(self):
        self.assertEqual(self.request.stage_id.code, 'sent')
        request_close = self.env['request.wizard.close'].new({
            'request_id': self.request.id,
        })
        self.assertFalse(request_close.close_route_id)
        self.assertFalse(request_close.reopen)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_service_id)
        self.assertFalse(request_close.new_request_text)

        # Test onchange request_id
        request_close.onchange_request_id()
        self.assertEqual(request_close.close_route_id, self.close_reopen_route)
        self.assertTrue(request_close.reopen)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_service_id)
        self.assertFalse(request_close.new_request_text)

        # Test onchange request_id new request text
        request_close.onchange_request_id_new_request_text()
        self.assertEqual(request_close.close_route_id, self.close_reopen_route)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_service_id)
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

        # test onchange for close route
        res = request_close.onchange_update_domain_type_categ()
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_service_id)
        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids', '=', False),
             ('id', 'in', self.new_request_type.ids),
             ('service_ids', '=', False)]
        )
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

        # test onchange for new_request_service_id
        request_close.new_request_service_id = self.default_service
        res_serv = request_close.onchange_update_domain_type_categ()

        # Add request type to close route
        self.close_route.write({
            'reopen_as_type_ids': [(4, self.new_request_type.id)]})
        self.assertEqual(request_close.new_request_service_id,
                         self.default_service)
        self.assertEqual(
            res_serv.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.close_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)

        # test onchange for new_request_category_id
        request_close.new_request_category_id = self.new_request_category
        res_cat = request_close.onchange_update_domain_type_categ()
        self.assertEqual(request_close.new_request_service_id,
                         self.default_service)
        self.assertEqual(
            res_serv.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.close_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertEqual(request_close.new_request_category_id,
                         self.new_request_category)
        self.assertFalse(request_close.new_request_type_id)

        self.assertEqual(
            res_cat.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids.id', '=', self.new_request_category.id),
             ('id', 'in', self.close_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

    def test_request_wizard_close_onchanges_2(self):
        # pylint: disable=too-many-statements
        self.assertEqual(self.request_reopen_1.stage_id.code, 'new')

        request_close = self.env['request.wizard.close'].new({
            'request_id': self.request_reopen_1.id,
            'reopen_as': 'subrequest',
        })

        self.assertFalse(request_close.close_route_id)
        self.assertFalse(request_close.reopen)
        self.assertFalse(request_close.new_request_service_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_text)
        self.assertEqual(request_close.reopen_as, 'subrequest')

        # Test onchange request_id, need for add route to wizard
        request_close.onchange_request_id()
        self.assertEqual(
            request_close.close_route_id, self.new_reopen_1_route)

        self.assertTrue(self.request_reopen_1.request_text)
        # Test onchange request_id new request text
        request_close.onchange_request_id_new_request_text()
        self.assertEqual(request_close.close_route_id, self.new_reopen_1_route)
        self.assertFalse(request_close.new_request_service_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)
        self.assertEqual(request_close.new_request_text,
                         self.request_reopen_1.request_text)

        # test onchange for close route
        res = request_close.onchange_update_domain_type_categ()
        self.assertFalse(request_close.new_request_service_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)
        self.assertEqual(
            self.new_reopen_1_route.reopen_as_type_ids.ids,
            [
                self.new_request_type_reop_categ_1.id,
                self.new_request_type_reop_categ_2.id,
                self.new_request_type_reop_no_categ.id,
            ]
        )

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids', '=', False),
             ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', False)]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', False)]
        )

        # test onchange for default_service
        request_close.new_request_service_id = self.default_service
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_service_id, self.default_service)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids', '=', False),
             ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )

        # test onchange for new_request_category
        request_close.new_request_category_id = self.new_request_category
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_service_id, self.default_service)
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category)
        self.assertFalse(request_close.new_request_type_id)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids.id', '=', self.new_request_category.id),
             ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )

        # Add new request type new_request_type_reop_categ_2
        request_close.new_request_type_id = self.new_request_type_reop_categ_2

        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_service_id, self.default_service)
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category)
        self.assertEqual(
            request_close.new_request_type_id,
            self.new_request_type_reop_categ_2)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            ['&', '&',
             ('category_ids.id', '=', self.new_request_category.id),
             ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            ['&',
             ('request_type_ids.id', 'in',
              self.new_reopen_1_route.reopen_as_type_ids.ids),
             ('service_ids', '=', self.default_service.id)]
        )

        request_ids = self.env['request.request'].search([])
        # Close request
        request_close.action_close_request()

        new_request = self.env['request.request'].search([
            ('id', 'not in', request_ids.ids)])

        self.assertEqual(self.request_reopen_1.stage_id.code, 'classified')

        self.assertEqual(
            new_request.service_id,
            self.default_service)
        self.assertEqual(
            new_request.category_id,
            self.new_request_category)
        self.assertEqual(
            new_request.type_id,
            self.new_request_type_reop_categ_2)

    def test_service_access_rights(self):
        demo_user = self.env.ref('generic_request.user_demo_request')
        uenv = self.env(user=demo_user)

        # No services visible for request user
        self.assertFalse(uenv['generic.service'].search([]))

        # Subscribe demo user to service 'Default'
        self.default_service.message_subscribe(
            partner_ids=demo_user.partner_id.ids)

        # Check that now service 'Default' is visible for demo user
        self.assertIn(self.default_service, uenv['generic.service'].search([]))

    def test_request_onchange_service(self):

        # Category for simple type
        category_tech = self.env.ref(
            'generic_request.request_category_demo_technical_configuration')

        # Create new (empty) request
        request = self.Request.new({})
        self.assertFalse(request.stage_id)
        self.assertFalse(request.type_id)
        self.assertFalse(request.category_id)
        self.assertFalse(request.service_id)

        res = request._onchange_category_type()

        self.assertEqual(
            res['domain']['type_id'],
            expression.AND([
                [('category_ids', '=', False),
                 ('start_stage_id', '!=', False)],
                [('service_ids', '=', False)],
            ])
        )
        self.assertEqual(
            res['domain']['category_id'],
            expression.AND([
                [], [('service_ids', '=', False)],
            ])
        )

        # Set service 'Default for request
        request.service_id = self.default_service
        res = request._onchange_category_type()

        # Ensure that request type was cleared (it is not allowed for selected
        # service)
        self.assertEqual(request.service_id, self.default_service)
        self.assertFalse(request.category_id)
        self.assertFalse(request.type_id)

        request.category_id = category_tech
        res = request._onchange_category_type()
        self.assertEqual(request.service_id, self.default_service)
        self.assertFalse(request.type_id)
        self.assertEqual(request.category_id, category_tech)

        self.assertEqual(
            res['domain']['type_id'],
            expression.AND([
                [('category_ids', '=', category_tech.id),
                 ('start_stage_id', '!=', False)],
                [('service_ids', '=', self.default_service.id)],
            ])
        )
        self.assertEqual(
            res['domain']['category_id'],
            expression.AND([
                [],
                [('service_ids', '=', self.default_service.id)],
            ])
        )

    def test_request_service_change(self):
        rent_service = self.env.ref(
            'generic_service.generic_service_rent_notebook')
        self.type_simple.service_ids += rent_service

        request = self.Request.create({
            'type_id': self.type_simple.id,
            'service_id': self.default_service.id,
            'request_text': 'test',
        })
        self.assertEqual(request.can_change_service, True)
        self.assertNotIn(
            'service-changed',
            request.request_event_ids.mapped('event_code'))

        request.service_id = rent_service

        self.assertIn(
            'service-changed',
            request.request_event_ids.mapped('event_code'))
        self.assertEqual(
            request.request_event_ids.sorted()[0].event_code,
            'service-changed')
        self.assertEqual(
            request.request_event_ids.sorted()[0].old_service_id,
            self.default_service)
        self.assertEqual(
            request.request_event_ids.sorted()[0].new_service_id,
            rent_service)

    def test_request_no_service_level(self):

        # request
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        # ensure no service level
        self.assertFalse(request.service_level_id)

        # request with partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'partner_id': self.request_partner_fake.id,
            'request_text': 'test',
        })

        # ensure no service level
        self.assertFalse(request.service_level_id)

    def test_request_author_service_level(self):

        # set service level 1 for request author
        self.env.user.partner_id.service_level_id = self.service_level_1.id

        # request without partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)

        # request with partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'partner_id': self.request_partner_fake.id,
            'request_text': 'test',
        })

        # ensure no service level (partner no service level)
        self.assertFalse(request.service_level_id)

    def test_request_partner_service_level(self):

        # set service level 1 for request author
        self.env.user.partner_id.service_level_id = self.service_level_1.id

        # request without partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)

        # request with partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'partner_id': self.request_partner.id,
            'request_text': 'test',
        })

        # ensure partner service level
        self.assertEqual(request.service_level_id.id, self.service_level_2.id)

    def test_write_request_partner_service_level(self):
        # set service level 1 for request author
        self.env.user.partner_id.service_level_id = self.service_level_1.id

        # request without partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)

        # relate partner to request
        request.partner_id = self.request_partner.id

        # ensure partner service level
        self.assertEqual(request.service_level_id.id, self.service_level_2.id)

        # relate partner to request
        request.partner_id = False

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)

        # relate partner to request
        request.partner_id = self.request_partner_fake.id

        # ensure False service level
        self.assertFalse(request.service_level_id)

    def test_can_change_service(self):
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertEqual(request.can_change_service, True)

        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)
        self.assertEqual(request.can_change_service, False)

    def test_service_id_domain_new_record(self):
        request = self.Request.new({
            'request_text': 'test',
        })
        self.assertEqual(
            request.service_id_domain, "[]")

        request.type_id = self.type_simple
        self.assertEqual(
            request.service_id_domain, "[]")

    def test_service_id_domain_created_record(self):
        request = self.Request.create({
            'request_text': 'test',
            'type_id': self.type_simple.id,
        })
        self.assertEqual(
            request.service_id_domain,
            '[["request_type_ids", "=", %s]]' % self.type_simple.id)

        search_res = self.env['generic.service'].with_context(
            request_service_id_domain=request.service_id_domain,
        ).name_search()
        expected_res = self.env['generic.service'].search(
            [('request_type_ids', '=', self.type_simple.id)],
        )

        self.assertEqual(
            {s[0] for s in search_res},
            set(expected_res.ids))

    def test_request_service_level_changed_event_created(self):
        request = self.Request.create({
            'request_text': 'event service level changed test',
            'type_id': self.type_simple.id,
        })
        self.assertEqual(request.request_event_count, 1)
        self.assertEqual(request.request_event_ids.event_type_id.code,
                         'record-created')
        request.service_level_id = self.service_level_1.id
        self.assertSetEqual(
            set(request.request_event_ids.mapped('event_type_id.code')),
            {'record-created', 'service-level-changed'})
        self.assertEqual(request.request_event_count, 2)

    def test_request_service_level_changed_event_on_service_level_guess(self):
        # set service level 1 for request author
        self.env.user.partner_id.service_level_id = self.service_level_1.id

        # request without partner
        request = self.Request.create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)
        last_event = request.request_event_ids.filtered(
            lambda r: r.event_code == 'service-level-changed').sorted()[0]
        self.assertFalse(last_event.old_service_level_id)
        self.assertEqual(last_event.new_service_level_id, self.service_level_1)

        # relate partner to request
        request.partner_id = self.request_partner.id

        # ensure partner service level
        self.assertEqual(request.service_level_id.id, self.service_level_2.id)
        last_event = request.request_event_ids.filtered(
            lambda r: r.event_code == 'service-level-changed').sorted()[0]
        self.assertEqual(last_event.old_service_level_id, self.service_level_1)
        self.assertEqual(last_event.new_service_level_id, self.service_level_2)

        # relate partner to request
        request.partner_id = False

        # ensure author service level
        self.assertEqual(request.service_level_id.id, self.service_level_1.id)
        last_event = request.request_event_ids.filtered(
            lambda r: r.event_code == 'service-level-changed').sorted()[0]
        self.assertEqual(last_event.old_service_level_id, self.service_level_2)
        self.assertEqual(last_event.new_service_level_id, self.service_level_1)

        # relate partner to request
        request.partner_id = self.request_partner_fake.id

        # ensure False service level
        self.assertFalse(request.service_level_id)
        last_event = request.request_event_ids.filtered(
            lambda r: r.event_code == 'service-level-changed').sorted()[0]
        self.assertEqual(last_event.old_service_level_id, self.service_level_1)
        self.assertFalse(last_event.new_service_level_id)
