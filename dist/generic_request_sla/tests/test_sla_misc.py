from odoo import exceptions
from .common import RequestSLACase


class TestRequestSLAMisc(RequestSLACase):

    def setUp(self):
        super(TestRequestSLAMisc, self).setUp()
        # if rule lines will be added to demo in next modules for
        # sla_draft_support rule,
        # we must reject it, because it can work on any rule line without
        # category and this tests will failed
        self.sla_draft.rule_line_ids.filtered(
            lambda rl: rl != self.sla_draft_support).unlink()

    def test_sla_rule_constraint(self):
        with self.assertRaises(exceptions.ValidationError):
            self.sla_draft.compute_time = 'calendar'

        self.sla_type.sla_calendar_id = self.sla_calendar

        self.sla_draft.compute_time = 'calendar'

    def test_sla_rule_line_constraint(self):
        with self.assertRaises(exceptions.ValidationError):
            self.sla_draft_support.compute_time = 'calendar'

        self.sla_type.sla_calendar_id = self.sla_calendar

        self.sla_draft_support.compute_time = 'calendar'
