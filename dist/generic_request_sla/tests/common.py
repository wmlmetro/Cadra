import datetime
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.tools.misc import mute_logger
from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinST,
    ReduceLoggingMixin,
)
from odoo.addons.generic_request.tests.common import (
    RequestClassifierUtilsMixin)


class RequestSLACase(ReduceLoggingMixin,
                     AccessRulesFixMixinST,
                     RequestClassifierUtilsMixin,
                     TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(RequestSLACase, cls).setUpClass()
        cls.env.user.tz = 'UTC'

        cls.cron_update_state = cls.env.ref(
            'generic_request_sla.ir_cron_request_sla_update_state')

        # Request Type
        cls.sla_type = cls.env.ref(
            'generic_request_sla_log.request_type_sla')

        # Categories
        cls.request_category_general = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.request_category_support = cls.env.ref(
            'generic_request.request_category_demo_support')
        cls.request_category_technical = cls.env.ref(
            'generic_request.request_category_demo_technical')

        # Stages
        cls.stage_draft = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_draft')
        cls.stage_sent = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_sent')
        cls.stage_confirmed = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_confirmed')
        cls.stage_rejected = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_rejected')

        # SLA rules
        cls.sla_draft = cls.env.ref(
            'generic_request_sla.request_sla_rule_8h_in_draft')
        cls.sla_sent_unassigned = cls.env.ref(
            'generic_request_sla.request_sla_rule_2h_unassigned')
        cls.sla_sent_assigned = cls.env.ref(
            'generic_request_sla.request_sla_rule_4h_assigned')

        # SLA rule lines
        cls.sla_draft_support = cls.env.ref(
            'generic_request_sla.request_sla_rule_8h_in_draft_support')
        cls.sla_draft_technical = cls.env.ref(
            'generic_request_sla.request_sla_rule_8h_in_draft_technical')

        # Users
        cls.demo_user = cls.env.ref('base.user_demo')
        cls.request_user = cls.env.ref(
            'generic_request.user_demo_request')
        cls.request_manager = cls.env.ref(
            'generic_request.user_demo_request_manager')
        cls.request_manager_2 = cls.env.ref(
            'generic_request.user_demo_request_manager_2')

        cls.sla_type.message_subscribe(
            partner_ids=cls.request_user.partner_id.ids)

        # Calendar
        cls.sla_calendar = cls.env.ref(
            'generic_request_sla_log.example_sla_calendar')
        cls.sla_calendar.tz = 'UTC'

    def _enable_use_services_setting(self):
        (
            self.env.ref('base.group_user') +
            self.env.ref('base.group_portal') +
            self.env.ref('base.group_public')
        ).write({
            'implied_ids': [
                (4,
                 self.env.ref(
                     'generic_request.group_request_use_services').id),
            ]
        })

    def run(self, result=None):
        # Hide unnecessary log output
        with mute_logger('odoo.models.unlink',
                         'odoo.addons.mail.models.mail_mail'):
            return super(RequestSLACase, self).run(result=result)

    def _get_sla_control(self, request, rule):
        return request.sla_control_ids.filtered(
            lambda r: r.sla_rule_id == rule)

    def _get_sla_control_by_code(self, request, code):
        return request.get_sla_control_by_code(code)

    def _get_sla_control_field(self, request, sla_control_code, field_name):
        cl = self._get_sla_control_by_code(request, sla_control_code)
        return cl[field_name]

    def assertSLAControl(self, request, sla_control_code, field_name, value):
        """ Assert, that specified field of specified control line
            equals to value.

            Automatically converts datetime values before comparison
        """
        check_val = self._get_sla_control_field(
            request, sla_control_code, field_name)

        if isinstance(check_val, datetime.datetime) and isinstance(value, str):
            check_val = fields.Datetime.to_string(check_val)

        return self.assertEqual(check_val, value)
