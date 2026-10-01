"""A faded tag is replaced by two people, and the old number never returns.

Handoff 38. NRS, 30 September: *"you notice an air conditioner tag is weak
… you can reprint a tag for that particular asset."* The model already
scrapped the old label, minted a new number and kept the chain; what it
did not do was record WHY, name who was asked, refuse the requester
deciding their own request, or stop anybody editing the stamps afterwards.
Each test below is one of those sentences, and each is proved on the row.

The requester and the approver are two users of this register, because the
model refuses one person being both halves — under `sudo()` as well, which
`test_a_requester_cannot_approve_their_own_request_even_sudo` drives.
"""
import uuid

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

MANAGER_GROUP = 'myservice_asset_register.group_asset_manager'


@tagged('post_install', '-at_install')
class TestTagReplacement(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'Tag replacement test category', 'code': 'TRP'})
        self.requester = self._user('tag-replace-requester', manager=True)
        self.approver = self._user('tag-replace-approver', manager=True)
        self.bystander = self._user('tag-replace-bystander', manager=False)

    def _user(self, login, manager=True):
        Users = self.env['res.users']
        field = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'
        groups = [self.env.ref('base.group_user').id]
        if manager:
            groups.append(self.env.ref(MANAGER_GROUP).id)
        login = '%s-%s' % (login, uuid.uuid4().hex[:8])
        return Users.create({
            'name': login, 'login': login,
            # `message_post` with `partner_ids` needs an author with an
            # address, and every transition posts one.
            'email': '%s@example.com' % login,
            field: [(6, 0, groups)],
        })

    def _asset(self):
        asset = self.env['nrs.asset'].create(
            {'name': 'Tag replacement test asset',
             'category_id': self.category.id})
        self.assertTrue(asset.active_tag_id, 'an asset is born with a tag')
        return asset

    def _as(self, user, tag):
        return tag.with_user(user)

    def _request(self, tag, reason='damaged', notes=None, approver=None):
        return self._as(self.requester, tag).action_request_replacement(
            reason=reason, notes=notes,
            approver=self.approver if approver is None else approver)

    # ── the request ──────────────────────────────────────────────────

    def test_a_request_records_why_who_asked_and_who_was_asked(self):
        tag = self._asset().active_tag_id
        self._request(tag, reason='damaged', notes='faded in the sun')
        self.assertEqual(tag.state, 'pending')
        self.assertEqual(tag.replacement_reason, 'damaged')
        self.assertEqual(tag.replacement_notes, 'faded in the sun')
        self.assertEqual(tag.requested_by, self.requester)
        self.assertTrue(tag.requested_date)
        self.assertEqual(tag.approver_id, self.approver)
        self.assertFalse(tag.approved_by)
        self.assertFalse(tag.rejected_by)

    def test_a_request_without_a_reason_is_refused(self):
        tag = self._asset().active_tag_id
        with self.assertRaisesRegex(UserError, 'reason is required'):
            self._request(tag, reason=None)
        with self.assertRaisesRegex(UserError, 'reason is required'):
            self._request(tag, reason='because')
        self.assertEqual(tag.state, 'active')

    def test_a_request_naming_nobody_is_refused(self):
        tag = self._asset().active_tag_id
        with self.assertRaisesRegex(UserError, 'Name who you are asking'):
            self._as(self.requester, tag).action_request_replacement(
                reason='damaged', approver=self.env['res.users'])
        self.assertEqual(tag.state, 'active')

    def test_a_request_naming_yourself_is_refused(self):
        tag = self._asset().active_tag_id
        with self.assertRaisesRegex(UserError, 'cannot ask yourself'):
            self._request(tag, approver=self.requester)

    def test_a_request_naming_someone_ineligible_is_refused(self):
        tag = self._asset().active_tag_id
        with self.assertRaisesRegex(UserError, 'cannot approve'):
            self._request(tag, approver=self.bystander)

    def test_the_odoo_form_path_reads_the_fields_typed_on_the_record(self):
        """The form button calls with no arguments; the reason and the
        approver come off the record, which the form lets the requester
        type before pressing it."""
        tag = self._asset().active_tag_id
        tag.write({'replacement_reason': 'lost',
                   'approver_id': self.approver.id})
        self._as(self.requester, tag).action_request_replacement()
        self.assertEqual(tag.state, 'pending')
        self.assertEqual(tag.replacement_reason, 'lost')
        self.assertEqual(tag.approver_id, self.approver)

    def test_only_an_active_tag_can_be_requested(self):
        tag = self._asset().active_tag_id
        self._request(tag)
        with self.assertRaisesRegex(UserError, 'only an active tag'):
            self._request(tag)

    # ── the decision ─────────────────────────────────────────────────

    def test_approval_scraps_mints_links_and_stamps(self):
        asset = self._asset()
        old = asset.active_tag_id
        old_number = old.name
        self._request(old, reason='damaged')
        new = self._as(self.approver, old).action_approve_replacement(
            decision_reason='seen it, agreed')
        self.assertEqual(len(new), 1)
        self.assertEqual(old.state, 'scrapped')
        self.assertEqual(old.label_state, 'scrapped')
        self.assertTrue(old.scrapped_date)
        self.assertEqual(old.approved_by, self.approver)
        self.assertTrue(old.approved_date)
        self.assertEqual(old.decision_reason, 'seen it, agreed')
        self.assertEqual(old.replacement_reason, 'damaged',
                         'the reason survives the decision')
        self.assertEqual(old.replaced_by_id, new)
        self.assertEqual(new.replaces_id, old)
        self.assertEqual(new.state, 'active')
        self.assertEqual(new.asset_id, asset)
        self.assertEqual(asset.active_tag_id, new)
        self.assertEqual(asset.asset_tag, new.name)
        self.assertNotEqual(new.name, old_number)

    def test_the_old_number_is_never_reissued(self):
        """Two replacements in a row on one asset: three numbers, all
        different, and the scrapped ones never come back. `_generate_tag`
        searches every tag on the prefix, scrapped included."""
        asset = self._asset()
        first = asset.active_tag_id
        self._request(first)
        second = self._as(self.approver, first).action_approve_replacement()
        self._request(second)
        third = self._as(self.approver, second).action_approve_replacement()
        numbers = [first.name, second.name, third.name]
        self.assertEqual(len(set(numbers)), 3, numbers)
        self.assertEqual(
            self.env['nrs.asset.tag.label'].search_count(
                [('name', '=', first.name)]), 1,
            'the scrapped number exists exactly once, on the scrapped row')
        # And a fresh mint on this asset still avoids both scrapped numbers.
        minted = asset._generate_tag(source='manual')
        self.assertNotIn(minted.name, numbers[:2])

    def test_a_decision_needs_a_pending_request(self):
        tag = self._asset().active_tag_id
        with self.assertRaisesRegex(UserError, 'not awaiting'):
            self._as(self.approver, tag).action_approve_replacement()
        with self.assertRaisesRegex(UserError, 'not awaiting'):
            self._as(self.approver, tag).action_reject_replacement(
                decision_reason='no')
        self.assertEqual(tag.state, 'active')

    def test_a_requester_cannot_approve_their_own_request_even_sudo(self):
        tag = self._asset().active_tag_id
        self._request(tag)
        with self.assertRaisesRegex(UserError, 'cannot decide it'):
            self._as(self.requester, tag).action_approve_replacement()
        with self.assertRaisesRegex(UserError, 'cannot decide it'):
            self._as(self.requester, tag).sudo().action_approve_replacement()
        self.assertEqual(tag.state, 'pending')

    def test_a_bystander_cannot_decide(self):
        tag = self._asset().active_tag_id
        self._request(tag)
        with self.assertRaisesRegex(UserError, 'cannot decide a tag'):
            self._as(self.bystander, tag).sudo().action_approve_replacement()

    def test_anyone_eligible_may_decide_not_only_the_one_asked(self):
        """`approver_id` is whose queue it sits in, not the only authority —
        the same two-column rule as `nrs.asset.change.request`."""
        other = self._user('tag-replace-other-manager', manager=True)
        tag = self._asset().active_tag_id
        self._request(tag, approver=self.approver)
        new = self._as(other, tag).action_approve_replacement()
        self.assertEqual(tag.approved_by, other)
        self.assertEqual(tag.approver_id, self.approver,
                         'who was asked is kept beside who clicked')
        self.assertTrue(new)

    def test_rejection_needs_a_reason_and_records_who_said_no(self):
        tag = self._asset().active_tag_id
        self._request(tag)
        with self.assertRaisesRegex(UserError, 'reason is required'):
            self._as(self.approver, tag).action_reject_replacement()
        self.assertEqual(tag.state, 'pending')
        self._as(self.approver, tag).action_reject_replacement(
            decision_reason='label is fine, clean it')
        self.assertEqual(tag.state, 'active')
        self.assertEqual(tag.rejected_by, self.approver)
        self.assertTrue(tag.rejected_date)
        self.assertEqual(tag.decision_reason, 'label is fine, clean it')
        self.assertFalse(tag.replaced_by_id)
        # A later request is a new slot: the old decision's stamps go.
        self._request(tag, reason='stolen')
        self.assertFalse(tag.rejected_by)
        self.assertFalse(tag.decision_reason)
        self.assertEqual(tag.replacement_reason, 'stolen')

    # ── the stamps nobody can edit ───────────────────────────────────

    def test_the_stamps_cannot_be_written_directly(self):
        tag = self._asset().active_tag_id
        for field, value in (('requested_by', self.requester.id),
                             ('approved_by', self.approver.id),
                             ('approved_date', '2026-01-01 00:00:00'),
                             ('rejected_by', self.approver.id),
                             ('decision_reason', 'forged'),
                             ('replaced_by_id', tag.id),
                             ('replaces_id', tag.id)):
            with self.assertRaisesRegex(ValidationError, 'cannot be set',
                                        msg=field):
                tag.sudo().write({field: value})

    def test_a_scrapped_tag_stays_scrapped(self):
        tag = self._asset().active_tag_id
        self._request(tag)
        self._as(self.approver, tag).action_approve_replacement()
        with self.assertRaisesRegex(ValidationError, 'stays scrapped'):
            tag.sudo().write({'state': 'active'})
        with self.assertRaisesRegex(UserError, 'only an active tag'):
            self._request(tag)
        self.assertEqual(tag.state, 'scrapped')
