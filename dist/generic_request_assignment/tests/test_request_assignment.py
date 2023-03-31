import logging

from odoo import SUPERUSER_ID
from odoo.tools.misc import mute_logger
from odoo.tools.safe_eval import safe_eval

from .common import RequestAssignmentCase

_logger = logging.getLogger(__name__)


class TestRequestAssignment(RequestAssignmentCase):

    def test_010_simple_flow_assign_user(self):
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 6)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assign request to demo_user by user
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.demo_user)
        self.assertTrue(self.request_1.date_assigned)

    def test_015_simple_flow_assign_user_with_comment(self):
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 6)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assign request to demo_user by user
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
            'assign_comment': 'Test Assign Comment',
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.demo_user)
        self.assertTrue(self.request_1.date_assigned)
        self.assertTrue(self.env['mail.message'].search_count([
            ('model', '=', 'request.request'),
            ('res_id', '=', self.request_1.id),
            ('body', 'ilike', 'Test Assign Comment'),
        ]))

    def test_020_simple_flow_assign_user_by_eval(self):
        # Change policy rule eval sequence to 1
        self.policy_rule_eval.write({'sequence': 1})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 1)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assign request to user_admin by eval
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.user_admin)
        self.assertTrue(self.request_1.date_assigned)

    def test_030_simple_flow_assign_user_by_user_field(self):
        # Change policy rule user_field sequence to 1
        self.policy_user_field.write({'sequence': 1})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 6)
        self.assertEqual(self.policy_user_field.sequence, 1)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assign request to request_user by user_field
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.request_user)
        self.assertTrue(self.request_1.date_assigned)

    def test_040_simple_flow_assign_user_by_policy(self):
        # Change policy rule policy sequence to 1
        self.policy_rule_policy.write({'sequence': 1})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 6)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 1)
        # Assign request to demo0_user by policy
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.demo0_user)
        self.assertTrue(self.request_1.date_assigned)

    @mute_logger('odoo.sql_db')
    def test_050_simple_flow_assign_user_by_order_rule_eval_incorrect(self):
        # Change policy rule policy sequence to 1,
        #  assign_eval to {'user_id': 100} incorrect
        self.policy_rule_eval.write({
            'sequence': 1,
            'assign_eval': "{'user_id': 100}"})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 1)
        self.assertEqual(
            self.policy_rule_eval.assign_eval, "{'user_id': 100}")
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assignment
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        # worked rule 'assign_user' because this rule is incorrect
        self.assertEqual(self.request_1.user_id, self.demo_user)
        self.assertTrue(self.request_1.date_assigned)

    def test_060_simple_flow_assign_user_by_rule_eval_condition(self):
        # Change policy rule eval sequence to 1
        self.policy_rule_eval.write({
            'sequence': 1,
            'condition_ids': [(4, self.condition.id)]})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 1)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Assignment
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.user_admin)
        self.assertTrue(self.request_1.date_assigned)

    def test_070_simple_flow_assign_user_by_rule_eval_condition_failed(self):
        # Change policy rule eval sequence to 1
        self.policy_rule_eval.write({
            'sequence': 1,
            'condition_ids': [(4, self.condition.id)]})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 1)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Set response text to request
        self.request_1.write({'response_text': 'test'})
        self.assertEqual(self.request_1.response_text, '<p>test</p>')
        # Assignment
        AssignWizard = self.env['generic.wizard.assign']
        assign_wizard = AssignWizard.with_user(SUPERUSER_ID).with_context(
            default_assign_object_ids=self.request_1.ids,
        ).create({
            'assign_model_id': self.assign_model.id,
            'assign_type': 'policy',
            'assign_policy_id': self.example_policy.id,
        })
        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, self.demo_user)
        self.assertTrue(self.request_1.date_assigned)

    def test_080_simple_flow_assign_user_test_wizard(self):
        # Change policy rule eval sequence to 1
        self.policy_rule_eval.write({
            'sequence': 1,
            'condition_ids': [(4, self.condition.id)]})
        # Make sure policy rules order
        self.assertEqual(self.policy_rule_user.sequence, 5)
        self.assertEqual(self.policy_rule_eval.sequence, 1)
        self.assertEqual(self.policy_user_field.sequence, 7)
        self.assertEqual(self.policy_rule_policy.sequence, 8)
        # Set response text to request
        self.request_1.write({'response_text': 'test'})
        self.assertEqual(self.request_1.response_text, '<p>test</p>')
        # Create test wizard
        TestWizard = self.env['generic.assign.policy.test_assign_policy']
        wizard = TestWizard.create({
            'assign_policy_id': self.example_policy.id,
            'res_id': self.request_1.id,
        })
        wizard.run_test_get()

        self.assertEqual(
            safe_eval(wizard.result_get).get('user_id', False),
            self.demo_user.id)

        self.assertEqual(
            safe_eval(wizard.result_convert).get('user_id', False),
            self.demo_user.id)
