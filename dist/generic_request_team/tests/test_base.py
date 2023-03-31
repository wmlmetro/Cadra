import logging
from odoo import exceptions
from odoo.addons.generic_request.tests.common import RequestCase
from odoo.tests.common import tagged

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestGenericRequestTeamBase(RequestCase):

    @classmethod
    def setUpClass(cls):
        super(TestGenericRequestTeamBase, cls).setUpClass()
        cls.team_user_1 = cls.env.ref('generic_team.team_res_users_user1')
        cls.team_user_2 = cls.env.ref('generic_team.team_res_users_user2')
        cls.team_user_3 = cls.env.ref('generic_team.team_res_users_user3')
        cls.team_user_4 = cls.env.ref('generic_team.team_res_users_user4')

        cls.team_1 = cls.env.ref('generic_team.generic_team_team1')
        cls.team_2 = cls.env.ref('generic_team.generic_team_team2')
        cls.team_3 = cls.env.ref('generic_team.generic_team_team3')

    def test_10_assign_user(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to request manager
        manager = self.request_manager

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.sudo().create({
            'request_ids': [(6, 0, self.request_1.ids)],
        })

        # In this module (genenic_request_team), we have disabled the current
        # user as default in values if paraneter user_id not set
        self.assertFalse(assign_wizard.user_id)
        self.assertFalse(assign_wizard.team_id)

        assign_wizard.write({
            'user_id': manager.id,
        })
        self.assertEqual(assign_wizard.user_id, manager)

        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, manager)
        self.assertTrue(self.request_1.date_assigned)

        # Undo assign request
        manager = self.request_manager
        self.request_1.with_user(manager).write({'user_id': False})
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.date_assigned)

    def test_20_assign_user_with_comment(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)

        # Assign request to request manager
        manager = self.request_manager

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.with_user(manager).create({
            'request_ids': [(6, 0, self.request_1.ids)],
            'comment': 'Test Comment',
        })

        # In this module (genenic_request_team), we have disabled the current
        # user as default in values if paraneter user_id not set
        self.assertFalse(assign_wizard.user_id)
        self.assertFalse(assign_wizard.team_id)

        assign_wizard.write({
            'user_id': manager.id,
        })
        self.assertEqual(assign_wizard.user_id, manager)

        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, manager)
        self.assertTrue(self.request_1.date_assigned)
        self.assertTrue(self.env['mail.message'].search_count([
            ('model', '=', 'request.request'),
            ('res_id', '=', self.request_1.id),
            ('body', 'ilike', 'Test Comment'),
        ]))

    def test_30_assign_team(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to team
        team = self.team_1

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.sudo().create({
            'team_id': team.id,
            'request_ids': [(6, 0, self.request_1.ids)],
        })

        self.assertFalse(assign_wizard.user_id)
        self.assertEqual(assign_wizard.team_id, team)

        assign_wizard.do_assign()
        self.assertFalse(self.request_1.user_id)
        self.assertEqual(self.request_1.team_id, team)
        self.assertTrue(self.request_1.date_assigned)

        # Undo assign request
        manager = self.request_manager
        self.request_1.with_user(manager).write({'team_id': False})
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)
        self.assertFalse(self.request_1.date_assigned)

    def test_40_assign_team_with_comment(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to team
        team = self.team_1

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.sudo().create({
            'team_id': team.id,
            'request_ids': [(6, 0, self.request_1.ids)],
            'comment': 'Test Comment',
        })

        self.assertFalse(assign_wizard.user_id)
        self.assertEqual(assign_wizard.team_id, team)

        assign_wizard.do_assign()
        self.assertFalse(self.request_1.user_id)
        self.assertEqual(self.request_1.team_id, team)
        self.assertTrue(self.request_1.date_assigned)
        self.assertTrue(self.env['mail.message'].search_count([
            ('model', '=', 'request.request'),
            ('res_id', '=', self.request_1.id),
            ('body', 'ilike', 'Test Comment'),
        ]))

        # Undo assign request
        manager = self.request_manager
        self.request_1.with_user(manager).write({'team_id': False})
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)
        self.assertFalse(self.request_1.date_assigned)

    def test_50_assign_team_and_team_member_with_comment(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to team and team member
        team = self.team_1
        member = self.team_user_3

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.sudo().create({
            'team_id': team.id,
            'user_id': member.id,
            'request_ids': [(6, 0, self.request_1.ids)],
            'comment': 'Test Comment',
        })

        self.assertEqual(assign_wizard.user_id, member)
        self.assertEqual(assign_wizard.team_id, team)

        assign_wizard.do_assign()
        self.assertEqual(self.request_1.user_id, member)
        self.assertEqual(self.request_1.team_id, team)
        self.assertTrue(self.request_1.date_assigned)
        self.assertTrue(self.env['mail.message'].search_count([
            ('model', '=', 'request.request'),
            ('res_id', '=', self.request_1.id),
            ('body', 'ilike', 'Test Comment'),
        ]))

        # Undo assign request
        manager = self.request_manager
        self.request_1.with_user(manager).write({
            'team_id': False,
            'user_id': False,
        })
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)
        self.assertFalse(self.request_1.date_assigned)

    def test_60_assign_team_and_not_team_member_raise(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to team
        team = self.team_1
        not_member = self.team_user_2

        AssignWizard = self.env['request.wizard.assign']
        with self.assertRaises(exceptions.ValidationError):
            AssignWizard.sudo().create({
                'team_id': team.id,
                'user_id': not_member.id,
                'request_ids': [(6, 0, self.request_1.ids)],
            })

    def test_70_request_create_simple_with_team(self):
        Request = self.env['request.request']

        team = self.team_1

        request = Request.create({
            'type_id': self.simple_type.id,
            'category_id': self.general_category.id,
            'request_text': 'Request Text',
            'team_id': team.id,
        })

        self.assertTrue(request.name.startswith('Req-'))
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertFalse(request.user_id)
        self.assertEqual(request.team_id, team)
        self.assertTrue(request.date_assigned)

    def test_80_request_create_simple_with_team_and_team_member(self):
        Request = self.env['request.request']

        team = self.team_1
        member = self.team_user_3

        request = Request.create({
            'type_id': self.simple_type.id,
            'category_id': self.general_category.id,
            'request_text': 'Request Text',
            'team_id': team.id,
            'user_id': member.id,
        })

        self.assertTrue(request.name.startswith('Req-'))
        self.assertEqual(request.stage_id, self.stage_draft)
        self.assertEqual(request.user_id, member)
        self.assertEqual(request.team_id, team)
        self.assertTrue(request.date_assigned)

    def test_90_request_create_simple_with_team_and_not_team_member(self):
        Request = self.env['request.request']

        team = self.team_1
        not_member = self.team_user_2

        with self.assertRaises(exceptions.ValidationError):
            Request.create({
                'type_id': self.simple_type.id,
                'category_id': self.general_category.id,
                'request_text': 'Request Text',
                'team_id': team.id,
                'user_id': not_member.id,
            })

    def test_100_request_with_team_and_not_team_member(self):
        self.assertEqual(self.request_1.stage_id, self.stage_draft)

        # Make request sent
        self.request_1.write({'stage_id': self.stage_sent.id})
        self.assertEqual(self.request_1.stage_id, self.stage_sent)
        self.assertFalse(self.request_1.date_assigned)
        self.assertFalse(self.request_1.user_id)
        self.assertFalse(self.request_1.team_id)

        # Assign request to team
        team = self.team_1

        AssignWizard = self.env['request.wizard.assign']
        assign_wizard = AssignWizard.sudo().create({
            'team_id': team.id,
            'request_ids': [(6, 0, self.request_1.ids)],
        })

        self.assertFalse(assign_wizard.user_id)
        self.assertEqual(assign_wizard.team_id, team)

        assign_wizard.do_assign()
        self.assertFalse(self.request_1.user_id)
        self.assertEqual(self.request_1.team_id, team)
        self.assertTrue(self.request_1.date_assigned)

        # Assign request to request manager and he is not a member of the team
        manager = self.request_manager

        self.assertNotIn(manager,
                         team.leader_id + team.task_manager_id + team.user_ids)
        # If no user specified for wizard, current user will be automaticaly
        # selected, but clear team_id value when user is not member assigned
        # team
        self.request_1.with_user(manager).action_request_assign_to_me()
        self.assertEqual(self.request_1.user_id, manager)
        self.assertTrue(self.request_1.date_assigned)
        self.assertFalse(self.request_1.team_id)
