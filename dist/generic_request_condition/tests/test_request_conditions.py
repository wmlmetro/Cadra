import logging

from odoo import exceptions
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin

_logger = logging.getLogger(__name__)


class TestRequestConditions(ReduceLoggingMixin, TransactionCase):
    """Test request Simple Flow
    """

    @classmethod
    def setUpClass(cls):
        super(TestRequestConditions, cls).setUpClass()
        cls.request = cls.env.ref(
            "generic_request_condition.request_conditional_demo_1")
        cls.draft_stage = cls.env.ref(
            "generic_request_condition.request_stage_type_conditional_draft")
        cls.sent_stage = cls.env.ref(
            "generic_request_condition.request_stage_type_conditional_sent")
        cls.confirmed_stage = cls.env.ref(
            "generic_request_condition."
            "request_stage_type_conditional_confirmed")

        cls.request_manager = cls.env.ref(
            'generic_request.user_demo_request_manager')
        cls.request_categ_demo = cls.env.ref(
            'generic_request.request_category_demo')
        cls.request_categ_demo_general = cls.env.ref(
            'generic_request.request_category_demo_general')
        cls.request_categ_demo_technical = cls.env.ref(
            'generic_request.request_category_demo_technical')

        cls.group_change_author_xmlid = (
            'generic_request.group_request_user_can_change_author')
        cls.group_change_author = cls.env.ref(cls.group_change_author_xmlid)

        cls.install_os_categ = cls.env.ref(
            'generic_request_condition.request_category_demo_install_os')
        cls.set_up_workplace_categ = cls.env.ref(
            'generic_request_condition.request_category_demo_setup_workplace')

        cls.install_os_condition = cls.env.ref(
            'generic_request_condition.install_os')
        cls.set_up_workplace_condition = cls.env.ref(
            'generic_request_condition.setup_workplace')

    def test_request_move_conditions_raise(self):
        self.assertEqual(self.request.stage_id, self.draft_stage)

        self.request.stage_id = self.sent_stage

        self.assertEqual(self.request.stage_id, self.sent_stage)

        # Ensure that confirmed stage raises error
        with self.assertRaises(exceptions.AccessError):
            self.request.stage_id = self.confirmed_stage

    def test_request_move_conditions_no_raise(self):
        self.request.stage_id = self.sent_stage
        self.assertEqual(self.request.stage_id, self.sent_stage)

        # Fix request text
        self.request.request_text = 'confirm me'

        self.assertEqual(self.request.request_text, '<p>confirm me</p>')

        # Try to move request ot confirmed stage
        self.request.stage_id = self.confirmed_stage

        # Ensure that request is confirmed
        self.assertEqual(self.request.stage_id, self.confirmed_stage)

    def test_request_can_change_request_text_no_conditions(self):
        self.request.type_id.change_request_text_condition_ids = False
        self.assertTrue(
            self.request.with_user(
                self.request_manager).can_change_request_text)

    def test_request_can_change_request_text(self):
        self.assertFalse(
            self.request.with_user(
                self.request_manager).can_change_request_text)

        self.request.created_by_id = self.request_manager
        self.request.refresh()

        self.assertTrue(
            self.request.with_user(
                self.request_manager).can_change_request_text)

    def test_request_can_change_assignee_no_conditions(self):
        self.request.type_id.change_assignee_condition_ids = False

        # Request is no assigned
        self.assertTrue(
            self.request.with_user(self.request_manager).can_change_assignee)

        self.request.user_id = self.request_manager
        self.request.refresh()

        # Request is assigned
        self.assertTrue(
            self.request.can_change_assignee)

    def test_request_can_change_assignee(self):
        # Request is not assigned, so current user (admin) can change assignee
        self.assertTrue(
            self.request.can_change_assignee)

        # Change assigneed request manager
        self.request.user_id = self.request_manager
        self.request.refresh()

        # Now only assignee can reassign request to someone else
        self.assertFalse(
            self.request.can_change_assignee)

        mrequest = self.request.with_user(self.request_manager)
        mrequest.refresh()
        self.assertTrue(mrequest.can_change_assignee)

    def test_request_assign_raise_by_condition(self):
        self.assertTrue(
            self.request.with_user(self.request_manager).can_change_assignee)
        self.assertFalse(self.request.user_id)

        self.request.stage_id = self.sent_stage
        self.request.user_id = self.request_manager
        self.assertEqual(self.request.user_id, self.request_manager)

        # Try to assing request that already assigned
        with self.assertRaises(exceptions.UserError):
            self.request.action_request_assign()

    def test_request_assign_closed_allow_conditions(self):
        # Test that closed request could be assigned to somebody if it is
        # allowed by conditions
        self.request.type_id.change_assignee_condition_ids = self.env.ref(
            'generic_request_condition.condition_request_is_closed')
        self.assertFalse(self.request.can_change_assignee)

        self.request.stage_id = self.sent_stage
        self.request.refresh()
        self.assertFalse(self.request.can_change_assignee)

        with self.assertRaises(exceptions.UserError):
            self.request.ensure_can_assign()

        self.request.request_text = 'confirm me'
        self.request.stage_id = self.confirmed_stage
        self.request.refresh()
        self.assertTrue(self.request.can_change_assignee)
        self.request.ensure_can_assign()

        assign_wizard = self.env['request.wizard.assign'].create({
            'request_ids': [(6, 0, self.request.ids)],
            'user_id': self.request_manager.id,
        })
        self.assertEqual(assign_wizard.user_id, self.request_manager)

        assign_wizard.do_assign()

        self.assertEqual(self.request.user_id, self.request_manager)

    def test_request_can_change_category_no_conditions(self):
        self.request.type_id.change_category_condition_ids = False
        self.assertEqual(self.request.stage_id, self.draft_stage)
        self.assertEqual(self.request.category_id, self.request_categ_demo)
        self.assertTrue(self.request.can_change_category)

        # move request to sent stage
        self.request.stage_id = self.sent_stage

        # Check that changing category not allowed
        self.assertEqual(self.request.stage_id, self.sent_stage)
        self.assertEqual(self.request.category_id, self.request_categ_demo)
        self.assertFalse(self.request.can_change_category)

    def test_request_can_change_category_with_conditions(self):
        self.assertEqual(self.request.stage_id, self.draft_stage)
        self.assertTrue(self.request.can_change_category)

        self.request.stage_id = self.sent_stage
        self.assertEqual(self.request.stage_id, self.sent_stage)
        self.assertTrue(self.request.can_change_category)

        self.request.request_text = 'confirm me'
        self.request.stage_id = self.confirmed_stage
        self.assertEqual(self.request.stage_id, self.confirmed_stage)
        self.assertFalse(self.request.can_change_category)

    def test_request_can_change_deadline_no_conditions(self):
        self.request.type_id.change_deadline_condition_ids = False
        self.assertEqual(self.request.stage_id, self.draft_stage)
        self.assertTrue(self.request.can_change_deadline)

        # move request to sent stage
        self.request.stage_id = self.sent_stage

        # Check that changing deadline is allowed
        self.assertEqual(self.request.stage_id, self.sent_stage)
        self.assertTrue(self.request.can_change_deadline)

        # move request to confirmed stage
        self.request.request_text = 'confirm me'
        self.request.stage_id = self.confirmed_stage

        # Check that changing deadline is not allowed
        self.assertEqual(self.request.stage_id, self.confirmed_stage)
        self.assertFalse(self.request.can_change_deadline)

    def test_request_can_change_deadline_with_conditions(self):
        self.assertFalse(self.request.can_change_deadline)
        self.request.request_text = 'confirm me'
        self.request.invalidate_cache()
        self.assertTrue(self.request.can_change_deadline)

    def test_request_can_change_author_no_conditions(self):
        self.request.type_id.change_author_condition_ids = False
        self.assertEqual(self.request.stage_id, self.draft_stage)

        self.assertFalse(
            self.env.user.has_group(self.group_change_author_xmlid))
        self.assertFalse(self.request.can_change_author)

        self.env.user.groups_id += self.group_change_author
        self.assertTrue(
            self.env.user.has_group(self.group_change_author_xmlid))
        self.assertTrue(self.request.can_change_author)

        # move request to sent stage
        self.request.stage_id = self.sent_stage

        # Check that changing author is not allowed
        self.assertEqual(self.request.stage_id, self.sent_stage)
        self.assertFalse(self.request.can_change_author)

        # move request to confirmed stage
        self.request.request_text = 'confirm me'
        self.request.stage_id = self.confirmed_stage

        # Check that changing author is not allowed
        self.assertEqual(self.request.stage_id, self.confirmed_stage)
        self.assertFalse(self.request.can_change_author)

    def test_request_can_change_author(self):
        self.assertEqual(self.request.stage_id, self.draft_stage)
        self.assertFalse(self.request.can_change_author)

        self.request.request_text = 'change author'

        self.assertFalse(
            self.env.user.has_group(self.group_change_author_xmlid))
        self.assertFalse(self.request.can_change_author)

        self.env.user.groups_id += self.group_change_author
        self.assertTrue(
            self.env.user.has_group(self.group_change_author_xmlid))
        self.assertTrue(self.request.can_change_author)

        self.request.request_text = 'Test'
        self.request.stage_id = self.sent_stage
        self.assertEqual(self.request.stage_id, self.sent_stage)
        self.assertFalse(self.request.can_change_author)

        self.request.request_text = 'confirm me'
        self.request.stage_id = self.confirmed_stage
        self.assertEqual(self.request.stage_id, self.confirmed_stage)
        self.assertTrue(self.request.closed)
        self.assertFalse(self.request.can_change_author)

        self.request.request_text = 'change author'
        self.assertTrue(self.request.can_change_author)

    def test_condition_operator(self):
        Route = self.env['request.stage.route']

        # create request type with categories
        request_type = self.env['request.type'].create({
            'name': 'Workplace',
            'code': 'workplace',
            'category_ids': [(4, self.install_os_categ.id),
                             (4, self.set_up_workplace_categ.id)]
        })

        # create default stages and routes
        request_type.action_create_default_stage_and_routes()

        # create stage
        stage_process = self.env['request.stage'].create({
            'name': 'Process',
            'code': 'process',
            'request_type_id': request_type.id
        })

        # create request
        request = self.env['request.request'].create({
            'category_id': self.install_os_categ.id,
            'type_id': request_type.id,
            'request_text': 'Install OS'
        })

        # create route with conditions and operator 'AND' between
        draft_process_route = self.env['request.stage.route'].create({
            'name': 'Draft_Process',
            'stage_from_id': request.stage_id.id,
            'stage_to_id': stage_process.id,
            'request_type_id': request_type.id,
            'condition_ids': [(4, self.install_os_condition.id),
                              (4, self.set_up_workplace_condition.id)],
            'condition_operator': 'and'
        })

        # check that we cant route
        with self.assertRaises(exceptions.AccessError):
            Route.ensure_route(request, stage_process.id)

        # change conditions operator to 'OR'
        draft_process_route.condition_operator = 'or'

        # check that we already be able to route
        self.assertEqual(Route.ensure_route(request, stage_process.id),
                         draft_process_route)
