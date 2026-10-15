"""A replacement keeps its number — handoff 61 §1, ruling R3, in the registry.

Until handoff 61 `nrs.asset.tag.label.action_approve_replacement` scrapped
the label and called `nrs.asset._generate_tag`, minting a NEW number — and on
a unit that came through the receipt gates, whose label carries the ASSET
CODE (ruling 4.3), the gated override passed it to the location-prefix
generator, so the replacement was no longer the code (findings §5.6). Since
61 the approval voids the PRINT and reprints the label under the SAME number:
one row per physical print, `reprint_count` telling them apart, the void
(`voided_date`, `void_reason`) stamped on the print it voids.

Every test is one sentence of that, proved on the rows: gates off (a
location-prefix label) and gates on (the asset code), the affix check on a
reprint that has not been printed, the PDF funnel's print letting it
through, the scrapped refusal naming the void, a number already active on a
second asset refused, the new stamps unforgeable, and the approver rule of
handoff 38 unchanged.

The receipt-gate walk is `GateCrew`'s (`test_receipt_gates.py`): seven
people, because the no-two-gates rule refuses one person firing two gates.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestReprintSameCode --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models.asset_event import (
    EVENT_AFFIX_REFUSED,
)
from odoo.addons.myservice_asset_register.models.asset_tag import _lagos_date

from .test_receipt_gates import GateCrew

R = 'myservice_asset_register.'


@tagged('post_install', '-at_install')
class TestReprintSameCode(GateCrew, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_crew()
        self.manager = self.env['res.users'].sudo().create({
            'name': 'R61 Manager', 'login': 'r61-manager',
            'email': 'r61-manager@reprint.example',
            'group_ids': [(4, self.env.ref('base.group_user').id),
                          (4, self.env.ref(R + 'group_asset_manager').id)]})

    # ── helpers ───────────────────────────────────────────────────────

    def _plain_asset(self):
        """Gates OFF shape: created on the register, its first print minted
        at creation by the location-prefix generator."""
        a = self.env['nrs.asset'].sudo().create({
            'name': 'Reprint probe', 'category_id': self.category.id})
        self.assertTrue(a.active_tag_id, 'an asset is born with a label')
        return a

    def _replace(self, label, reason='damaged'):
        label.with_user(self.tagger).sudo().action_request_replacement(
            reason=reason, notes='faded past reading', approver=self.manager)
        return label.with_user(self.manager).sudo() \
            .action_approve_replacement(decision_reason='sighted')

    def _refusals(self, asset):
        return self.env['nrs.asset.event'].sudo().search(
            [('asset_id', '=', asset.id),
             ('event_type', '=', EVENT_AFFIX_REFUSED)], order='id')

    def _assert_reprint_of(self, old, new, number):
        self.assertEqual(len(new), 1)
        self.assertEqual(old.name, number)
        self.assertEqual(new.name, number, 'the number must not change')
        self.assertNotEqual(new, old, 'one row per physical print')
        self.assertEqual((old.state, old.label_state), ('scrapped', 'scrapped'))
        self.assertEqual((new.state, new.label_state), ('active', 'issued'))
        self.assertEqual(old.reprint_count, 0)
        self.assertEqual(new.reprint_count, 1)
        self.assertEqual(new.replaces_id, old)
        self.assertEqual(old.replaced_by_id, new)
        self.assertTrue(old.voided_date)
        self.assertEqual(old.void_reason, 'damaged')
        self.assertFalse(new.voided_date)
        self.assertEqual(new.source, old.source,
                         "a reprint keeps its number's provenance")
        asset = new.asset_id
        self.assertEqual(asset.active_tag_id, new)
        self.assertEqual(asset.active_tag_number, number)
        self.assertEqual(asset.asset_tag, number)
        self.assertEqual(set(asset.tag_ids.mapped('name')), {number},
                         'nothing else was minted for this asset')
        self.assertEqual(self.env['nrs.asset.tag.label'].sudo().search_count(
            [('name', '=', number), ('state', '=', 'active')]), 1,
            'one active label per number')

    # ── the number stays ──────────────────────────────────────────────

    def test_a_location_prefix_label_is_reprinted_under_its_number(self):
        a = self._plain_asset()
        old = a.active_tag_id
        number = old.name
        self.assertNotEqual(number, a.asset_code,
                            'gates off, the first print is a prefix number')
        new = self._replace(old)
        self._assert_reprint_of(old, new, number)
        self.assertEqual(old.approved_by, self.manager)
        self.assertEqual(old.requested_by, self.tagger)

    def test_a_registered_gated_units_code_is_reprinted_as_the_code(self):
        a = self._to('registered')
        old = a.active_tag_id
        self.assertEqual(old.name, a.asset_code, 'ruling 4.3')
        self.assertEqual(old.label_state, 'affixed')
        new = self._replace(old)
        self._assert_reprint_of(old, new, a.asset_code)
        self.assertEqual(a.register_state, 'registered')

    def test_a_tagged_candidates_code_is_reprinted_as_the_code(self):
        """The case `test_receipt_gates` found in handoff 57 — a candidate
        whose label is already issued — now reprinted, not re-minted under
        a location prefix (findings §5.6)."""
        a = self._to('tagged')
        old = a.active_tag_id
        new = self._replace(old)
        self._assert_reprint_of(old, new, a.asset_code)
        self.assertEqual(a.register_state, 'tagged')

    def test_a_second_replacement_is_reprint_two(self):
        a = self._plain_asset()
        first = a.active_tag_id
        second = self._replace(first)
        third = self._replace(second, reason='lost')
        self.assertEqual(third.name, first.name)
        self.assertEqual(third.reprint_count, 2)
        self.assertEqual(third.replaces_id, second)
        self.assertEqual(second.void_reason, 'lost')
        self.assertEqual(first.void_reason, 'damaged')
        self.assertEqual(a.tag_ids.filtered(lambda t: t.state == 'active'),
                         third)

    # ── the affix check ───────────────────────────────────────────────

    def test_the_voided_print_is_refused_until_the_reprint_is_printed(self):
        a = self._plain_asset()
        old = a.active_tag_id
        new = self._replace(old)
        # Bare try/except, not assertRaises: assertRaises is a savepoint and
        # would unwind the recorder's same-cursor test-mode write (the 51
        # test's reason).
        try:
            new.with_user(self.tagger).sudo()._mark_affixed(new.name)
            self.fail('a reprint confirmed before it was printed')
        except ValidationError as caught:
            message = str(caught)
        self.assertEqual(message, (
            'Tag %s is reprint 1 and has not been printed yet, so the label '
            'being scanned can only be the original print, voided on %s '
            '(Damaged / Unreadable). Print reprint 1, then confirm it.'
        ) % (new.name, _lagos_date(old.voided_date)))
        refusals = self._refusals(a)
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals.reason, 'voided_print')
        self.assertEqual(refusals.to_value, new.name)
        self.assertEqual(new.label_state, 'issued')

        # Printed — the stamp the funnel and the station both make — and the
        # same number now confirms.
        new._mark_printed()
        self.assertEqual(new.label_state, 'printed')
        new.with_user(self.tagger).sudo()._mark_affixed(new.name)
        self.assertEqual(new.label_state, 'affixed')
        self.assertEqual(a.tag_label_state, 'affixed')
        self.assertEqual(len(self._refusals(a)), 1,
                         'a successful affix records no refusal')

    def test_a_wrong_number_on_a_reprint_is_still_a_number_mismatch(self):
        a = self._plain_asset()
        new = self._replace(a.active_tag_id)
        try:
            new.with_user(self.tagger).sudo()._mark_affixed('NOT-THIS-ONE')
            self.fail('a wrong number was accepted')
        except ValidationError as caught:
            self.assertIn('does not match the tag issued', str(caught))
        self.assertEqual(self._refusals(a).reason, 'number_mismatch')

    def test_the_pdf_funnel_prints_the_reprint_not_the_voided_print(self):
        a = self._plain_asset()
        old = a.active_tag_id
        new = self._replace(old)
        report = self.env.ref(R + 'action_report_asset_tag')
        self.env['ir.actions.report']._mark_printed_for([a.id], report)
        self.assertEqual(new.label_state, 'printed')
        self.assertEqual(old.label_state, 'scrapped',
                         'a voided print is not walked back to printed')
        new.with_user(self.tagger).sudo()._mark_affixed(new.name)
        self.assertEqual(new.label_state, 'affixed')

    def test_a_first_print_needs_no_recorded_print_as_before(self):
        a = self._plain_asset()
        label = a.active_tag_id
        self.assertEqual(label.label_state, 'issued')
        label.with_user(self.tagger).sudo()._mark_affixed(label.name)
        self.assertEqual(label.label_state, 'affixed')

    def test_the_voided_print_presented_directly_names_its_void(self):
        a = self._plain_asset()
        old = a.active_tag_id
        new = self._replace(old)
        try:
            old.with_user(self.tagger).sudo()._mark_affixed(old.name)
            self.fail('a voided print was confirmed')
        except ValidationError as caught:
            message = str(caught)
        self.assertEqual(message, (
            'Tag %s has been scrapped: the original print was voided on %s '
            '(Damaged / Unreadable) and cannot be confirmed as affixed. The '
            'label in service is reprint 1, under the same number.'
        ) % (old.name, _lagos_date(old.voided_date)))
        self.assertEqual(self._refusals(a).reason, 'scrapped')
        self.assertEqual(new.label_state, 'issued')

    def test_a_label_scrapped_before_handoff_61_says_its_scrap_date(self):
        """A row scrapped before 61 has no void stamp; the sentence uses its
        scrap date and reason rather than inventing a void."""
        a = self._plain_asset()
        label = a.active_tag_id
        label.write({'replacement_reason': 'stolen'})
        label.with_context(cadra_tag_capture=True).write(
            {'state': 'scrapped', 'label_state': 'scrapped',
             'scrapped_date': '2026-01-02'})
        try:
            label._mark_affixed(label.name)
            self.fail('a scrapped label was confirmed')
        except ValidationError as caught:
            self.assertEqual(str(caught), (
                'Tag %s has been scrapped: the original print was voided on '
                '2026-01-02 (Stolen) and cannot be confirmed as affixed.'
            ) % label.name)

    # ── what the approval refuses, and what nobody can forge ──────────

    def test_a_number_already_active_on_a_second_asset_is_not_reprinted(self):
        """84 numbers are active on two assets each across three local
        tenants (2026-10-15), written by paths that went round the Python
        constraint. Reprinting one would print the other asset's label. The
        duplicate is made with raw SQL because `_check_unique_active`
        refuses it through the ORM — which is how the real ones exist."""
        a, b = self._plain_asset(), self._plain_asset()
        old = a.active_tag_id
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE nrs_asset_tag_label SET name = %s WHERE id = %s",
            (old.name, b.active_tag_id.id))
        self.env.invalidate_all()
        old.with_user(self.tagger).sudo().action_request_replacement(
            reason='damaged', approver=self.manager)
        with self.assertRaisesRegex(UserError, 'also active on'):
            old.with_user(self.manager).sudo().action_approve_replacement()
        self.assertEqual(old.state, 'pending')
        self.assertFalse(old.voided_date)
        self.assertFalse(old.replaced_by_id)

    def test_the_print_stamps_cannot_be_written_or_created(self):
        a = self._plain_asset()
        label = a.active_tag_id
        for field, value in (('reprint_count', 3),
                             ('voided_date', '2026-01-01 00:00:00'),
                             ('void_reason', 'lost')):
            with self.assertRaisesRegex(ValidationError, 'cannot be set',
                                        msg=field):
                label.sudo().write({field: value})
        for field, value in (('reprint_count', 3), ('replaces_id', label.id),
                             ('void_reason', 'lost')):
            with self.assertRaisesRegex(ValidationError, 'Print fields',
                                        msg=field):
                self.env['nrs.asset.tag.label'].sudo().create({
                    'name': 'R61-FORGED-%s' % field, 'asset_id': a.id,
                    'state': 'scrapped', field: value})

    def test_the_requester_still_cannot_approve(self):
        a = self._plain_asset()
        label = a.active_tag_id
        label.with_user(self.tagger).sudo().action_request_replacement(
            reason='damaged', approver=self.manager)
        with self.assertRaisesRegex(UserError, 'cannot decide it'):
            label.with_user(self.tagger).sudo().action_approve_replacement()
        self.assertEqual(label.state, 'pending')
        self.assertEqual(len(a.tag_ids), 1, 'nothing reprinted')
