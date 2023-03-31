from .common import RequestSLACase


class TestRequestSLARule(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLARule, cls).setUpClass()

        # Add Simple Request Type
        cls.simple_type = cls.env.ref(
            'generic_request.request_type_simple')
        cls.default_rule_type = cls.env.ref(
            'generic_request_sla.request_sla_rule_type_default')

    def test_sla_rule_sequence(self):
        SLA_Rule = self.env['request.sla.rule']

        self.assertEqual(len(self.simple_type.sla_rule_ids), 0)

        # Create first rule for Simple Request type
        sla_rule_1 = SLA_Rule.sudo().create({
            'name': 'SLA rule 1',
            'code': 'sla-rule-1',
            'sla_rule_type_id': self.default_rule_type.id,
            'request_type_id': self.simple_type.id,
            'warn_time': 1.0,
            'limit_time': 2.0,
        })

        self.assertEqual(len(self.simple_type.sla_rule_ids), 1)
        # The Sequence value must be the default 5
        self.assertEqual(sla_rule_1.sequence, 5)

        sla_rule_2 = SLA_Rule.new({
            'name': 'SLA rule 2',
            'code': 'sla-rule-2',
            'sla_rule_type_id': self.default_rule_type.id,
            'request_type_id': self.simple_type.id,
            'warn_time': 1.0,
            'limit_time': 2.0,
        })
        sla_rule_2.onchange_set_default_sequence()
        self.assertEqual(sla_rule_2.sequence, 6)

        self.simple_type.sla_rule_ids += sla_rule_2
        self.assertEqual(len(self.simple_type.sla_rule_ids), 2)

        sla_rule_3 = SLA_Rule.new({
            'name': 'SLA rule 3',
            'code': 'sla-rule-3',
            'sla_rule_type_id': self.default_rule_type.id,
            'request_type_id': self.simple_type.id,
            'warn_time': 1.0,
            'limit_time': 2.0,
        })
        sla_rule_3.onchange_set_default_sequence()
        self.assertEqual(sla_rule_3.sequence, 7)

        self.simple_type.sla_rule_ids += sla_rule_3
        self.assertEqual(len(self.simple_type.sla_rule_ids), 3)
