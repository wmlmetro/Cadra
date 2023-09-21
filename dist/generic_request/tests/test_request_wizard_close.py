from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin, FindNew
from odoo.addons.generic_mixin.tests.common import deactivate_records_for_model


class TestRequestReopenAs(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestReopenAs, cls).setUpClass()

        # Requests
        cls.Request = cls.env['request.request']
        cls.request = cls.env.ref(
            "generic_request.request_request_type_sequence_demo_1")
        cls.request_reopen_1 = cls.env.ref(
            "generic_request.request_request_reopen_main_1")
        cls.request_resp_attachment = cls.env.ref(
            'generic_request.request_request_type_simple_demo_1')
        cls.request = cls.env.ref(
            "generic_request.request_request_type_sequence_demo_1")

        # Stages
        cls.request.stage_id = cls.env.ref(
            "generic_request.request_stage_type_sequence_sent")
        cls.request.stage_id = cls.env.ref(
            "generic_request.request_stage_type_sequence_sent")
        cls.stage_confirmed = cls.env.ref(
            'generic_request.request_stage_type_simple_confirmed')
        cls.stage_draft = cls.env.ref(
            'generic_request.request_stage_type_simple_draft')
        cls.stage_sent = cls.env.ref(
            'generic_request.request_stage_type_simple_sent')

        # Routes
        cls.close_reopen_route = cls.env.ref(
            'generic_request.'
            'request_stage_route_type_sequence_sent_to_grant')
        cls.close_route = cls.env.ref(
            'generic_request.request_stage_route_type_sequence_sent_to_closed')
        cls.new_reopen_1_route = cls.env.ref(
            'generic_request.'
            'request_stage_route_type_reopen_main_new_to_classified')

        # Categories
        cls.new_request_category = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')
        cls.new_request_category_gen = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.new_request_category = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')

        # Types
        cls.new_request_type = cls.env.ref(
            'generic_request.request_type_access')
        cls.new_request_type_reop_no_categ = cls.env.ref(
            'generic_request.request_type_reopen_as_type_no_categ')
        cls.new_request_type_reop_categ_1 = cls.env.ref(
            'generic_request.request_type_reopen_as_type_categ_1')
        cls.new_request_type_reop_categ_2 = cls.env.ref(
            'generic_request.request_type_reopen_as_type_categ_2')
        cls.new_request_type = cls.env.ref(
            'generic_request.request_type_access')

        # Services
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')

        # Attachments
        cls.response_attachment1 = cls.env.ref(
            'generic_request.request_response_attachment_demo1')
        cls.response_attachment2 = cls.env.ref(
            'generic_request.request_response_attachment_demo2')

    def test_request_wizard_close_onchanges(self):
        deactivate_records_for_model(self.env, 'request.classifier')
        self.assertEqual(self.request.stage_id.code, 'sent')
        request_close = self.env['request.wizard.close'].new({
            'request_id': self.request.id,
        })
        self.assertFalse(request_close.close_route_id)
        self.assertFalse(request_close.reopen)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_text)

        # Test onchange request_id
        request_close.onchange_request_id()
        self.assertEqual(request_close.close_route_id, self.close_reopen_route)
        self.assertTrue(request_close.reopen)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_text)

        # Test onchange request_id new request text
        request_close.onchange_request_id_new_request_text()
        self.assertEqual(request_close.close_route_id, self.close_reopen_route)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

        # test onchange for close route
        res = request_close.onchange_update_domain_type_categ()
        self.assertFalse(request_close.new_request_category_id)
        self.assertFalse(request_close.new_request_type_id)
        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids', '=', False),
                ('id', 'in', self.close_reopen_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.close_reopen_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

        # Remove Default Service from category
        self.assertIn(
            self.default_service, self.new_request_category.service_ids)

        # Remove link category with service
        self.env['request.classifier'].search([
            ('service_id', '=', self.default_service.id),
            ('category_id', '=', self.new_request_category.id),
        ]).write({'active': False})
        self.env['request.classifier'].flush()
        self.assertEqual(request_close.close_route_id, self.close_reopen_route)
        self.assertNotIn(
            self.default_service, self.new_request_category.service_ids)

        # test onchange for new_request_category_id
        request_close.new_request_category_id = self.new_request_category
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_category_id, self.new_request_category)
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(self.close_route.reopen_as_type_ids.ids)

        # Add request type to close route
        self.close_route.write({
            'reopen_as_type_ids': [(4, self.new_request_type.id)]})

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids.id', '=', self.new_request_category.id),
                ('id', 'in', self.close_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False)
            ])
        self.assertEqual(request_close.new_request_text,
                         self.request.request_text)

    def test_request_wizard_close_onchanges_2(self):
        # pylint: disable=too-many-statements
        deactivate_records_for_model(self.env, 'request.classifier')
        self.assertEqual(self.request_reopen_1.stage_id.code, 'new')

        request_close = self.env['request.wizard.close'].new({
            'request_id': self.request_reopen_1.id,
            'reopen_as': 'subrequest',
        })

        self.assertFalse(request_close.close_route_id)
        self.assertFalse(request_close.reopen)
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
        self.assertFalse(request_close.new_request_type_id)
        self.assertFalse(request_close.new_request_category_id)
        self.assertEqual(request_close.new_request_text,
                         self.request_reopen_1.request_text)

        # test onchange for close route
        res = request_close.onchange_update_domain_type_categ()
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
            [
                '&', '&',
                ('category_ids', '=', False),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        # test onchange for new_request_type_reop_no_categ
        request_close.new_request_type_id = self.new_request_type_reop_no_categ
        res = request_close.onchange_update_domain_type_categ()
        self.assertFalse(request_close.new_request_category_id)
        self.assertEqual(
            request_close.new_request_type_id,
            self.new_request_type_reop_no_categ)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids', '=', False),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        self.assertEqual(request_close.request_id, self.request_reopen_1)
        self.assertEqual(
            request_close.new_request_text, self.request_reopen_1.request_text)
        # Remove Default Service from category
        self.assertIn(
            self.default_service, self.new_request_category.service_ids)

        # Remove link category with service
        self.env['request.classifier'].search([
            ('service_id', '=', self.default_service.id),
            ('category_id', '=', self.new_request_category.id),
        ]).write({'active': False})
        self.env['request.classifier'].flush()
        self.assertNotIn(
            self.default_service, self.new_request_category.service_ids)

        # test onchange for new_request_category
        request_close.new_request_category_id = self.new_request_category
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category)
        self.assertFalse(request_close.new_request_type_id)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids.id', '=', self.new_request_category.id),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]

        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        # Add new request type new_request_type_reop_categ_2
        request_close.new_request_type_id = self.new_request_type_reop_categ_2
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category)
        self.assertEqual(
            request_close.new_request_type_id,
            self.new_request_type_reop_categ_2)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids.id', '=', self.new_request_category.id),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        # test onchange for new_request_category_gen
        request_close.new_request_category_id = self.new_request_category_gen
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category_gen)
        self.assertFalse(request_close.new_request_type_id)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids.id', '=', self.new_request_category_gen.id),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        # Add new request type new_request_type_reop_categ_1
        request_close.new_request_type_id = self.new_request_type_reop_categ_1
        res = request_close.onchange_update_domain_type_categ()
        self.assertEqual(
            request_close.new_request_category_id,
            self.new_request_category_gen)
        self.assertEqual(
            request_close.new_request_type_id,
            self.new_request_type_reop_categ_1)

        self.assertEqual(
            res.get('domain', {}).get('new_request_type_id', []),
            [
                '&', '&',
                ('category_ids.id', '=', self.new_request_category_gen.id),
                ('id', 'in', self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )
        self.assertEqual(
            res.get('domain', {}).get('new_request_category_id', []),
            [
                '&',
                ('request_type_ids.id', 'in',
                    self.new_reopen_1_route.reopen_as_type_ids.ids),
                ('service_ids', '=', False),
            ]
        )

        request_ids = self.env['request.request'].search([])
        # Close request
        request_close.action_close_request()

        new_request = self.env['request.request'].search([
            ('id', 'not in', request_ids.ids)])

        self.assertEqual(self.request_reopen_1.stage_id.code, 'classified')

        self.assertEqual(
            new_request.category_id,
            self.new_request_category_gen)
        self.assertEqual(
            new_request.type_id,
            self.new_request_type_reop_categ_1)

    def test_request_wizard_close_and_reopen(self):
        # Check stage of the request.
        self.assertEqual(self.request.stage_id.code, 'sent')

        # Ensure request have no subrequests
        self.assertFalse(self.request.child_ids)

        # Create wizard for closing the request.
        request_close = self.env['request.wizard.close'].create({
            'request_id': self.request.id,
            'close_route_id': self.close_reopen_route.id,
            'new_request_type_id': self.new_request_type.id,
            'new_request_category_id': self.new_request_category.id,
            'new_request_text': 'test'
        })

        # Closes the request and create new request as child of current request
        close_res = request_close.action_close_request()
        new_request = self.env[close_res['res_model']].browse(
            close_res['res_id'])
        self.assertEqual(new_request.parent_id, self.request)

        self.assertEqual(self.request.stage_id.code, 'grant')
        self.assertTrue(self.request.child_ids)

        # Ensure there is only one subrequest created
        self.request.child_ids.ensure_one()

        subrequest = self.request.child_ids
        self.assertEqual(new_request, subrequest)

        # Test if subrequest created right
        self.assertEqual(subrequest.stage_id.code, 'new')
        self.assertEqual(subrequest.request_text, '<p>test</p>')
        self.assertEqual(subrequest.type_id, self.new_request_type)
        self.assertEqual(subrequest.category_id, self.new_request_category)
        self.assertEqual(subrequest.author_id, self.request.author_id)
        self.assertEqual(subrequest.partner_id, self.request.partner_id)
        self.assertEqual(subrequest.created_by_id, self.env.user)

    def test_request_wizard_close_and_reopen_service(self):
        # Check stage of the request and service
        self.assertEqual(self.request.stage_id.code, 'sent')
        self.assertFalse(self.request.service_id)

        # Create wizard for closing the request.
        request_close = self.env['request.wizard.close'].create({
            'request_id': self.request.id,
            'close_route_id': self.close_reopen_route.id,
            'new_request_type_id': self.new_request_type.id,
            'new_request_category_id': self.new_request_category.id,
            'new_request_service_id': self.default_service.id,
            'new_request_text': 'test'
        })

        # Closes the request
        request_ids = self.Request.search([])
        request_close.action_close_request()
        new_request = self.Request.search([('id', 'not in', request_ids.ids)])

        self.assertEqual(self.request.stage_id.code, 'grant')
        self.assertEqual(new_request.service_id, self.default_service)

    def test_request_wizard_close_no_reopen(self):
        # Check stage of the request.
        self.assertEqual(self.request.stage_id.code, 'sent')

        # Ensure request have no subrequests
        self.assertFalse(self.request.child_ids)

        # Create wizard for closing the request.
        request_close = self.env['request.wizard.close'].create({
            'request_id': self.request.id,
            'close_route_id': self.close_route.id,
            'response_text': 'test-reponse',
        })

        # Closes the request and create new request as child of current request
        request_close.action_close_request()

        self.assertEqual(self.request.stage_id.code, 'closed')
        self.assertFalse(self.request.child_ids)

    def test_wizard_close_attachments(self):
        # Prepare request for closing
        self.assertEqual(
            self.request_resp_attachment.stage_id, self.stage_draft)
        self.request_resp_attachment.write({'stage_id': self.stage_sent.id})
        self.assertTrue(self.request_resp_attachment.can_be_closed)

        # Create wizard for closing the request, link attachment to it
        close_route = self.env['request.stage.route'].sudo().search([
            ('request_type_id', '=', self.request_resp_attachment.type_id.id),
            ('stage_from_id', '=', self.request_resp_attachment.stage_id.id),
            ('stage_to_id', '=', self.stage_confirmed.id),
        ])
        wizard_close = self.env['request.wizard.close'].create({
            'request_id': self.request_resp_attachment.id,
            'close_route_id': close_route.id,
            'response_text': 'test-response-attachments',
            'attachment_ids': [(4, self.response_attachment1.id),
                               (4, self.response_attachment2.id)],
        })
        self.assertEqual(len(wizard_close.attachment_ids), 2)
        self.assertIn(self.response_attachment1, wizard_close.attachment_ids)
        self.assertIn(self.response_attachment2, wizard_close.attachment_ids)

        # Close request
        with FindNew(self.env, 'mail.mail') as nr:
            wizard_close.action_close_request()
        self.assertEqual(
            self.request_resp_attachment.stage_id.code, 'confirmed')

        # Check mail created and has the same attachments as request response
        # attachments
        response_mail = nr['mail.mail'].search(
            [('subject', 'ilike', 'Your request %s has been closed!' %
              self.request_resp_attachment.name)])
        mail_attachments = response_mail.attachment_ids
        self.assertEqual(len(mail_attachments), 2)
        mail_attachment_datas = sorted(
            mail_attachments.mapped('datas'))
        wizard_attachment_datas = sorted(
            wizard_close.attachment_ids.mapped('datas'))
        self.assertListEqual(mail_attachment_datas, wizard_attachment_datas)
