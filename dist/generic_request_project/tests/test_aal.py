import logging
from odoo.tests.common import TransactionCase
from odoo import fields

_logger = logging.getLogger(__name__)

try:
    from freezegun import freeze_time  # noqa
except ImportError:  # pragma: no cover
    _logger.warning("freezegun not installed. Tests will not work!")


class AnalyticLineTest(TransactionCase):

    def setUp(self):
        super(AnalyticLineTest, self).setUp()
        self.request_simple_type = self.env.ref(
            'generic_request.request_request_type_simple_demo_1')
        self.activity_coding = self.env.ref(
            'generic_request.request_timesheet_activity_coding')
        self.activity_call = self.env.ref(
            'generic_request.request_timesheet_activity_call')
        self.request = self.env['request.request'].create({
            'type_id': self.request_simple_type.id,
            'request_text': "Test",
        })
        self.test_project = self.env['project.project'].create({
            'name': 'test_project',
            'allow_timesheets': True,
        })
        self.test_project_2 = self.env['project.project'].create({
            'name': 'test_project_2',
            'allow_timesheets': True,
        })
        self.request_manager = self.env.ref(
            'generic_request.user_demo_request_manager')

        # Create env for request manager to trigger with it
        # wizard action 'Start Work' to set 'user_id' in timesheet properly
        # (backport compatibility for v.16)
        self.menv = self.env(user=self.request_manager)

        self.request_user = self.env.ref('generic_request.user_demo_request')
        self.partner = self.env.ref('base.res_partner_10')
        self.partner_2 = self.env.ref('base.res_partner_1')

    def test_create_aal(self):
        # pylint: disable=too-many-statements
        # Project is not defined
        self.assertFalse(self.request.timesheet_line_ids)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 0)

        with freeze_time('2021-08-03 09:44:00'):
            # Create request_timesheet_line manually ("add a line")
            self.env['request.timesheet.line'].with_user(
                self.request_manager).create({
                    'request_id': self.request.id,
                    'activity_id': self.activity_coding.id,
                    'amount': 3.0, })
            self.assertEqual(len(self.request.timesheet_line_ids), 1)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 0)

        with freeze_time('2021-08-04 09:44:00'):
            # Create by pressing Start Work button on request form
            self.request.with_env(self.menv).action_start_work()
            self.assertEqual(len(self.request.timesheet_line_ids), 2)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 0)

        with freeze_time('2021-08-04 11:14:00'):
            action = self.request.with_env(self.menv).action_stop_work()
            wizard = self.env[action['res_model']].with_context(
                **action['context']
            ).create({'activity_id': self.activity_call.id, })
            self.assertEqual(wizard.amount, 1.5)
            wizard.do_stop_work()
            self.assertEqual(len(self.request.timesheet_line_ids), 2)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 0)

            # Define project
            self.request.with_user(self.request_manager).write({
                'project_id': self.test_project.id,
            })
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        aal_1 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[1]
        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-03')
        self.assertEqual(aal_1.name, 'Coding')
        self.assertEqual(aal_1.unit_amount, 3.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        aal_2 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[0]
        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-04')
        self.assertEqual(aal_2.name, 'Call')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Create with defined analytic account
        with freeze_time('2021-08-05 10:04:00'):
            self.request.with_user(self.request_manager).action_start_work()
            self.assertEqual(len(self.request.timesheet_line_ids), 3)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 2)

        with freeze_time('2021-08-05 11:04:00'):
            action = self.request.with_user(
                self.request_manager
            ).action_stop_work()
            wizard = self.env[action['res_model']].with_context(
                **action['context']
            ).create({'activity_id': self.activity_coding.id, })
            self.assertEqual(wizard.amount, 1.0)
            wizard.do_stop_work()
            self.assertEqual(len(self.request.timesheet_line_ids), 3)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 3)

            aal_3 = self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])[0]
            self.assertEqual(fields.Date.to_string(aal_3.date), '2021-08-05')
            self.assertEqual(aal_3.name, 'Coding')
            self.assertEqual(aal_3.unit_amount, 1.0)
            self.assertEqual(aal_3.account_id.name, 'test_project')
            self.assertEqual(aal_3.amount, 0.00)
            self.assertEqual(
                aal_3.company_id.name, 'YourCompany')
            self.assertFalse(aal_3.partner_id)
            self.assertEqual(aal_3.user_id.name, 'Demo Request Manager')

        with freeze_time('2021-08-06 11:04:00'):
            # Create request_timesheet_line manually ("add a line")
            self.env['request.timesheet.line'].create({
                'user_id': self.request_manager.id,
                'request_id': self.request.id,
                'activity_id': self.activity_call.id,
                'amount': 3.5, })
            self.assertEqual(len(self.request.timesheet_line_ids), 4)
            self.assertEqual(len(self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])), 4)

            aal_4 = self.env['account.analytic.line'].search([(
                'request_id', '=', self.request.id)])[0]
            self.assertEqual(fields.Date.to_string(aal_4.date), '2021-08-06')
            self.assertEqual(aal_4.name, 'Call')
            self.assertEqual(aal_4.unit_amount, 3.5)
            self.assertEqual(aal_4.account_id.name, 'test_project')
            self.assertEqual(aal_4.amount, 0.00)
            self.assertEqual(
                aal_4.company_id.name, 'YourCompany')
            self.assertFalse(aal_4.partner_id)
            self.assertEqual(aal_4.user_id.name, 'Demo Request Manager')

    def test_update_aal(self):
        # pylint: disable=too-many-statements
        self.request.project_id = self.test_project
        self.env['request.timesheet.line'].with_user(
            self.request_manager).create({
                'request_id': self.request.id,
                'activity_id': self.activity_coding.id,
                'amount': 1.5,
                'date': '2021-08-03',
                'description': 'description coding 1', })
        self.env['request.timesheet.line'].with_user(
            self.request_manager).create({
                'request_id': self.request.id,
                'activity_id': self.activity_call.id,
                'amount': 1.0,
                'date': '2021-08-05',
                'description': 'description call 1', })

        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        # Change project_id
        self.request.project_id = self.test_project_2
        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        aal_1 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[0]
        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-05')
        self.assertEqual(aal_1.name, 'Call: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project_2')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        aal_2 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[1]
        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project_2')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Clear value of an project in request
        self.request.project_id = False
        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 0)

        # Define value of an project in request
        self.request.project_id = self.test_project
        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        # Define partner_id
        self.request.partner_id = self.partner
        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        aal_1 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[0]
        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-05')
        self.assertEqual(aal_1.name, 'Call: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertEqual(aal_1.partner_id.name, 'The Jackson Group')
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        aal_2 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[1]
        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertEqual(aal_2.partner_id.name, 'The Jackson Group')
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Change partner_id
        self.request.partner_id = self.partner_2
        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        aal_1 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[0]
        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-05')
        self.assertEqual(aal_1.name, 'Call: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertEqual(aal_1.partner_id.name, 'Wood Corner')
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        aal_2 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[1]
        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertEqual(aal_2.partner_id.name, 'Wood Corner')
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Clear value of partner_id
        self.request.partner_id = False

        self.assertEqual(len(self.request.timesheet_line_ids), 2)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 2)

        aal_1 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[0]
        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-05')
        self.assertEqual(aal_1.name, 'Call: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        aal_2 = self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])[1]
        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Change activity_name in request_timesheet_line
        rtl_1 = self.env['request.timesheet.line'].search(
            [('id', '=', aal_1.req_timesheet_line_id.id)])
        rtl_1.activity_id = self.activity_coding

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-05')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Change date in request_timesheet_line
        rtl_1 = self.env['request.timesheet.line'].search(
            [('id', '=', aal_1.req_timesheet_line_id.id)])
        rtl_1.date = '2021-08-25'

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-25')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request Manager')

        # Change user_id in request_timesheet_line
        rtl_2 = self.env['request.timesheet.line'].search(
            [('id', '=', aal_2.req_timesheet_line_id.id)])
        rtl_2.user_id = self.request_user

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-25')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: description coding 1')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request User')

        # Change description in request_timesheet_line
        rtl_2 = self.env['request.timesheet.line'].search(
            [('id', '=', aal_2.req_timesheet_line_id.id)])
        rtl_2.description = 'changed description'

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-25')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: changed description')
        self.assertEqual(aal_2.unit_amount, 1.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request User')

        # Change duration in request_timesheet_line
        rtl_2 = self.env['request.timesheet.line'].search(
            [('id', '=', aal_2.req_timesheet_line_id.id)])
        rtl_2.amount = 3.5

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-25')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')

        self.assertEqual(fields.Date.to_string(aal_2.date), '2021-08-03')
        self.assertEqual(aal_2.name, 'Coding: changed description')
        self.assertEqual(aal_2.unit_amount, 3.5)
        self.assertEqual(aal_2.account_id.name, 'test_project')
        self.assertEqual(aal_2.amount, 0.00)
        self.assertEqual(aal_2.company_id.name, 'YourCompany')
        self.assertFalse(aal_2.partner_id)
        self.assertEqual(aal_2.user_id.name, 'Demo Request User')

        # Delete a request_timesheet_line
        rtl_2.unlink()
        self.assertEqual(len(self.request.timesheet_line_ids), 1)
        self.assertEqual(len(self.env['account.analytic.line'].search([(
            'request_id', '=', self.request.id)])), 1)

        self.assertEqual(fields.Date.to_string(aal_1.date), '2021-08-25')
        self.assertEqual(aal_1.name, 'Coding: description call 1')
        self.assertEqual(aal_1.unit_amount, 1.0)
        self.assertEqual(aal_1.account_id.name, 'test_project')
        self.assertEqual(aal_1.amount, 0.00)
        self.assertEqual(aal_1.company_id.name, 'YourCompany')
        self.assertFalse(aal_1.partner_id)
        self.assertEqual(aal_1.user_id.name, 'Demo Request Manager')
