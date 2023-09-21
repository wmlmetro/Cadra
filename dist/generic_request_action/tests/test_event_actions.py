# pylint:disable=too-many-lines
from datetime import date

from odoo import exceptions
from odoo.addons.generic_mixin.tests.common import FindNew
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RouteActionsTestCase


class TestRouteActions(RouteActionsTestCase):

    def test_10_route_actions_basic(self):
        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        })

        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actions were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Reject request
        request.stage_id = self.stage_rejected
        self.assertEqual(request.stage_id, self.stage_rejected)

        # Test that server action executed
        expected = ('<p>Your request was rejected by %s</p>'
                    '' % self.demo_manager.name)
        self.assertEqual(request.response_text, expected)

    def test_20_route_actions_sudo(self):
        # Create request as demo_manager
        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        })

        # Send request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Set action to be ran as superuser
        self.action_set_response.act_sudo = True

        # Reject request
        request.stage_id = self.stage_rejected
        self.assertEqual(request.stage_id, self.stage_rejected)

        # Test that server action executed
        expected = ('<p>Your request was rejected by %s</p>'
                    '' % self.demo_manager.name)
        self.assertEqual(request.response_text, expected)

    def test_30_route_actions_sudo_user(self):
        # Create request as demo_manager
        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        })

        # Send request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Set action to be ran as user Manager 2
        self.action_set_response.act_sudo = True
        self.action_set_response.act_sudo_user_id = self.demo_manager_2

        # Reject request
        request.stage_id = self.stage_rejected
        self.assertEqual(request.stage_id, self.stage_rejected)

        # Test that server action executed
        expected = ('<p>Your request was rejected by %s</p>'
                    '' % self.demo_manager_2.name)
        self.assertEqual(request.response_text, expected)

    def test_40_mail_activity(self):
        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        mail_activity = self.env['mail.activity'].search(
            [('res_id', '=', request.id),
             ('res_model', '=', 'request.request'),
             ('summary', '=', 'Get more info related to %s' % request.name)])
        self.assertEqual(len(mail_activity), 1)
        self.assertEqual(mail_activity.res_id, request.id)
        self.assertEqual(
            mail_activity.summary,
            "Get more info related to %s" % request.name)
        self.assertEqual(
            mail_activity.note,
            """<p>Ask client to provide more info for request """
            """<a href="%s">%s</a></p>""" % (
                request.get_mail_url(),
                request.name,
            )
        )

    def test_45_kanban_state(self):
        self.env['request.event.action'].create({
            'name': 'Set kanban_state to ready on stage change',
            'event_type_ids': [(6, 0, [self.env.ref(
                'generic_request.request_event_type_stage_changed').id])],
            'act_type': 'kanban_state',
            'kanban_state': 'done',
        })
        self.assertEqual(self.demo_request.kanban_state, 'normal')

        self.demo_request.stage_id = self.stage_sent

        self.assertEqual(self.demo_request.kanban_state, 'done')

    def test_50_related_act_windows(self):
        act_data = self.request_type.action_show_request_actions()
        actions = self.env[act_data['res_model']].search(act_data['domain'])
        self.assertEqual(actions._name, 'request.event.action')
        self.assertGreater(len(actions), 1)

        act_data = self.route_send.action_show_request_actions()
        actions = self.env[act_data['res_model']].search(act_data['domain'])
        self.assertEqual(actions._name, 'request.event.action')
        self.assertGreater(len(actions), 1)

    def test_60_helper_model_field(self):
        self.assertEqual(
            self.action_set_response.helper_request_model_id,
            self.env.ref('generic_request.model_request_request'))

    def test_70_constraint_event_type_ids(self):
        with self.assertRaises(exceptions.ValidationError):
            self.action_set_response.write({
                'event_type_ids': [(5, 0)],
            })

    def test_action_assign_type_field(self):

        self.demo_request.user_id = self.demo_manager_2

        mail_activity = self.env['mail.activity'].search(
            [('res_id', '=', self.demo_request.id),
             ('res_model', '=', 'request.request'),
             ('summary', '=', 'Please, process request %s'
              % self.demo_request.name)])

        self.assertEqual(len(mail_activity), 1)
        self.assertEqual(mail_activity.user_id, self.demo_manager_2)

    def test_route_actions_no_condition(self):
        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actins were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

    def test_route_actions_condition_not_pass(self):
        # Add condition to assign action
        self.action_assign.condition_ids |= self.condition_do_assign

        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actins were executed
        self.assertFalse(request.user_id)
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

    def test_route_actions_condition_pass(self):
        # Add condition to assign action
        self.action_assign.condition_ids |= self.condition_do_assign

        request = self.demo_request
        request.request_text = '<p>do assign</p>'  # this text make action run
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actions were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

    def test_route_actions_event_condition_not_pass(self):
        # Add condition to assign action
        self.action_assign.event_condition_ids |= (
            self.condition_event_do_assign)

        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actins were executed
        self.assertFalse(request.user_id)
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

    def test_route_actions_event_condition_pass(self):
        # Add condition to assign action
        self.action_assign.event_condition_ids |= (
            self.condition_event_do_assign)

        request = self.demo_request
        request.request_text = '<p>do assign</p>'  # this text make action run
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actions were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

    def test_route_actions_event_condition_pass_without_unsubscribe(self):
        # Add condition to assign action
        self.action_assign.event_condition_ids |= (
            self.condition_event_do_assign)

        request = self.demo_request
        request.request_text = '<p>do assign</p>'  # this text make action run

        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        user_demo = self.env.ref('base.user_demo')
        request.write({
            'user_id': user_demo.id,
        })

        self.assertIn(
            user_demo.partner_id,
            [f.partner_id for f in request.message_follower_ids],
        )

        self.assertFalse(self.action_assign.unsubscribe_prev_assignee)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actions were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)
        # User Demo not removed from followers
        self.assertIn(
            user_demo.partner_id,
            [f.partner_id for f in request.message_follower_ids],
        )

    def test_route_actions_event_condition_pass_unsubscribe(self):
        # Add condition to assign action
        self.action_assign.event_condition_ids |= (
            self.condition_event_do_assign)

        request = self.demo_request
        request.request_text = '<p>do assign</p>'  # this text make action run

        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertNotIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)

        user_demo = self.env.ref('base.user_demo')
        request.write({
            'user_id': user_demo.id,
        })

        self.assertIn(
            user_demo.partner_id,
            [f.partner_id for f in request.message_follower_ids],
        )

        self.assertFalse(self.action_assign.unsubscribe_prev_assignee)
        self.action_assign.write({
            'unsubscribe_prev_assignee': True,
        })
        self.assertTrue(self.action_assign.unsubscribe_prev_assignee)

        # Run a route by changing state of request
        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        # Test that actions were executed
        self.assertEqual(
            request.user_id,
            self.env.ref('generic_request.user_demo_request'))
        self.assertIn(
            self.env.ref('base.res_partner_2'),
            request.message_partner_ids)
        # User Demo removed from followers
        self.assertNotIn(
            user_demo.partner_id,
            [f.partner_id for f in request.message_follower_ids],
        )

    def test_action_validate(self):
        self.env['request.event.action'].create({
            'name': 'Validate Request',
            'event_type_ids': [(6, 0, [self.env.ref(
                'generic_system_event.system_event_record_created').id])],
            'act_type': 'validate',
            'validate_condition_ids': [
                (6, 0, [
                    self.env.ref(
                        'generic_request_action.'
                        'condition_request_text_is_valid'
                    ).id,
                ]),
            ],
            'validate_error_msg': 'Request is not valida because 42',
        })

        with self.assertRaisesRegex(
                exceptions.ValidationError,
                'Request is not valida because 42'):
            self.env['request.request'].with_user(self.demo_manager).create({
                'type_id': self.request_type.id,
                'category_id': self.request_category.id,
                'request_text': 'Test request',
            })

        # No exception raise if request text is 'valid'
        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'valid',
        })
        self.assertTrue(request)

    def test_action_validate_event(self):
        self.env['request.event.action'].create({
            'name': 'Validate Request Event',
            'event_type_ids': [(6, 0, [self.env.ref(
                'generic_request.request_event_type_changed').id])],
            'act_type': 'validate',
            'validate_event_condition_ids': [
                (6, 0, [
                    self.env.ref(
                        'generic_request_action.'
                        'condition_request_event_new_text_is_valid'
                    ).id,
                ]),
            ],
            'validate_error_msg': 'Request is not valida because 42',
        })

        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        })

        # Ensure valid request text passes condition
        request.write({'request_text': 'valid'})

        # But invalid request text throws validation error
        with self.assertRaisesRegex(
                exceptions.ValidationError,
                'Request is not valida because 42'):
            request.write({'request_text': 'Some invalid text'})

    def test_action_send_email_with_response_attachments(self):

        # link attachment to demo request
        self.request_attachment.write({
            'res_model': 'request.request',
            'res_id': self.demo_request.id,
        })

        # create mail template to send via action and link attachment to it
        mail_template = self.env['mail.template'].create({
            'name': 'Request closed',
            'model_id': self.env.ref(
                'generic_request.model_request_request').id,
            'body_html': 'The request was closed',
            'attachment_ids': [(4, self.template_attachment.id)],
        })

        # Check template attachment was added properly to mail template
        self.assertIn(self.template_attachment, mail_template.attachment_ids)
        self.assertEqual(len(mail_template.attachment_ids), 1)

        # Check request attachment was added properly to demo request
        self.assertIn(self.request_attachment,
                      self.demo_request.attachment_ids)
        self.assertEqual(len(self.demo_request.attachment_ids), 1)

        # Create action to send mail template on request close event
        self.env['request.event.action'].create({
            'name': 'Send mail when request closed',
            'event_type_ids': [(6, 0, [self.env.ref(
                'generic_request.request_event_type_closed').id])],
            'act_type': 'send_email',
            'send_email_template_id': mail_template.id,
            'send_response_attachments': True
        })

        # Prepare request for closing
        self.assertEqual(self.demo_request.stage_id.code, 'draft')
        self.demo_request.stage_id = self.stage_sent
        self.assertEqual(self.demo_request.stage_id.code, 'sent')

        # Create wizard for closing the request, link attachment to it
        wizard_close = self.env['request.wizard.close'].create({
            'request_id': self.demo_request.id,
            'close_route_id': self.route_confirmed.id,
            'response_text': 'test-reponse-attachments',
            'attachment_ids': [(4, self.response_attachment.id)],
        })
        self.assertIn(self.response_attachment, wizard_close.attachment_ids)

        # Close request
        with FindNew(self.env, 'mail.mail') as nr:
            wizard_close.action_close_request()
        self.assertEqual(self.demo_request.stage_id.code, 'confirmed')

        # Check mail created
        action_mail = nr['mail.mail'].filtered(
            lambda x: x.body == '<p>%s</p>' % mail_template.body_html)

        # Check response attachment was properly added
        self.assertEqual(len(self.demo_request.attachment_ids), 2)
        self.assertEqual(len(self.demo_request.response_attachment_ids), 1)
        self.assertIn(self.request_attachment.datas,
                      self.demo_request.attachment_ids.mapped('datas'))
        self.assertIn(
            self.response_attachment.datas,
            self.demo_request.response_attachment_ids.mapped('datas'))
        self.assertIn(
            self.response_attachment.datas,
            self.demo_request.attachment_ids.mapped('datas'))

        # Check mail has response attachment and mail template attachment
        self.assertEqual(len(action_mail.attachment_ids), 2)
        self.assertIn(self.response_attachment.datas,
                      action_mail.attachment_ids.mapped('datas'))
        self.assertIn(self.template_attachment.datas,
                      action_mail.attachment_ids.mapped('datas'))

        # Check template attachments didn't change
        self.assertEqual(len(mail_template.attachment_ids), 1)
        self.assertIn(self.template_attachment, mail_template.attachment_ids)

    def test_action_change_deadline__increase_calendar_days_1(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_type': 'calendar_days',
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': 1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 21))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 22))

    def test_action_change_deadline__increase_calendar_days_2(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_type': 'calendar_days',
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': 2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 22))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 24))

    def test_action_change_deadline__decrease_calendar_days_1(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_type': 'calendar_days',
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': -1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-23'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 23))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 22))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 21))

    def test_action_change_deadline__decrease_calendar_days_2(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_type': 'calendar_days',
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': -2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-23'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 23))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 21))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 19))

    def test_action_change_deadline_increase__by_working_days_1(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': 1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 23))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 24))

    def test_action_change_deadline_increase__by_working_days_2(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': 2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 24))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 26))

    def test_action_change_deadline_decrease__by_working_days_1(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': -1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-30'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 30))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 27))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 26))

    def test_action_change_deadline_decrease__by_working_days_2(self):
        self.action_auto_change_deadline.write({
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_reassigned').id)],
            'change_deadline_from_field_date': self.env.ref(
                'generic_request.field_request_request__deadline_date').id,
            'change_deadline_value': -2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)

        self.demo_request_deadline.deadline_date = '2020-03-30'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 30))

        with freeze_time('2020-03-10'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 26))

        with freeze_time('2020-03-12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager_2.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 24))

    def test_action_change_deadline_increase__by_working_days_1_datetime(self):
        self.action_auto_change_deadline.write({
            'change_deadline_value': 1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)
        self.assertFalse(self.demo_request_deadline.date_assigned)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-6 13:33:12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 9))

    def test_action_change_deadline_increase__by_working_days_2_datetime(self):
        self.action_auto_change_deadline.write({
            'change_deadline_value': 2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)
        self.assertFalse(self.demo_request_deadline.date_assigned)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-06 13:33:12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 10))

    def test_action_change_deadline_decrease__by_working_days_1_datetime(self):
        self.action_auto_change_deadline.write({
            'change_deadline_value': -1,
        })

        self.assertFalse(self.demo_request_deadline.user_id)
        self.assertFalse(self.demo_request_deadline.date_assigned)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-09 13:33:12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 6))

    def test_action_change_deadline_decrease__by_working_days_2_datetime(self):
        self.action_auto_change_deadline.write({
            'change_deadline_value': -2,
        })

        self.assertFalse(self.demo_request_deadline.user_id)
        self.assertFalse(self.demo_request_deadline.date_assigned)

        self.demo_request_deadline.deadline_date = '2020-03-20'

        self.assertEqual(
            self.demo_request_deadline.deadline_date, date(2020, 3, 20))

        with freeze_time('2020-03-09 13:33:12'):
            self.demo_request_deadline.invalidate_cache()

            self.demo_request_deadline.write({
                'user_id': self.demo_manager.id,
            })
            self.assertEqual(
                self.demo_request_deadline.deadline_date, date(2020, 3, 5))

    def test_action_tag(self):
        request = self.env['request.request'].with_user(
            self.demo_manager
        ).create({
            'type_id': self.request_type.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        })
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertEqual(len(request.tag_ids), 2)

        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)
        self.assertEqual(len(request.tag_ids), 1)
