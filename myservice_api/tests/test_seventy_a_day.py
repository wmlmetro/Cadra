"""Seventy a day — handoff 60, in-registry.

What the HTTP suite (`tests/test_seventy_a_day.py`) cannot reach cheaply:
the table `waiting on me` is read from, pinned against the gate table; the
per-person domain judged as each of the seven people; a batch's stored
evidence linked rather than copied; the timestamp the Candidates list is
sorted by; and a new asset's identification mode with the gates off.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestSeventyADay --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import json

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models import asset_gates as G

from .test_receipt_gates import CHECKLIST, EVIDENCE, GateCrew


@tagged('post_install', '-at_install')
class TestSeventyADay(GateCrew, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_crew()

    def _mine(self, user):
        Asset = self.env['nrs.asset'].with_user(user).sudo()
        return Asset.search(Asset._waiting_on_me_domain())

    # ── the table `waiting on me` reads ──────────────────────────────

    def test_waiting_act_matches_the_table(self):
        """Every state somebody waits in has its act, and each act is the
        gate table's own — same gate, same scopes. `affix` is the system
        transition the station fires; `tag_requested` is never waited in
        (request-tagging issues the label in the same act)."""
        waited = {s for s, who in G.WAITING_ON.items() if who}
        self.assertEqual(set(G.WAITING_ACT), waited - {'tag_requested'})
        for state, (action, gate, scopes) in G.WAITING_ACT.items():
            if action == 'affix':
                row = next(r for r in G.SYSTEM_TRANSITIONS
                           if r['action'] == 'affix')
                self.assertIn(state, row['frm'])
                self.assertEqual(row['gate'], gate)
                self.assertEqual(scopes, (G.S_TAGGING_WRITE,))
                continue
            rows = [r for r in G.TRANSITIONS
                    if r['action'] == action and state in r['frm']]
            self.assertTrue(rows, (state, action))
            for row in rows:
                self.assertEqual(row.get('gate') or row.get('acts_as'), gate)
                self.assertEqual(tuple(row['scopes']), scopes)

    # ── the per-person domain, as each person ───────────────────────

    def test_each_person_waits_on_their_own_gate_and_not_on_a_barred_unit(
            self):
        a, b = self._candidate(), self._candidate()
        self.assertIn(a, self._mine(self.store))
        self.assertNotIn(a, self._mine(self.officer))
        self._fire(a, self.store, 'submit')
        self._fire(b, self.store, 'submit')
        self.assertNotIn(a, self._mine(self.store))
        self.assertIn(a, self._mine(self.officer))
        self.assertNotIn(a, self._mine(self.approver))
        self._fire(a, self.officer, 'verify',
                   payload={'checklist': CHECKLIST, 'attachments': EVIDENCE})
        self.assertIn(a, self._mine(self.approver))
        self.assertNotIn(a, self._mine(self.officer))
        # A person holding two gate scopes (the exclusion table allows no
        # such person to be GRANTED them, so it is switched off here, as
        # test_receipt_gates does) is barred by the no-two-gates rule: the
        # officer-approver verified `a`, so `a` does not wait on them; `b`
        # it never touched, so `b` does.
        self.env.ref(
            'myservice_api.role_exclusion_iad_officer_approver'
        ).sudo().active = False
        R = 'myservice_asset_register.'
        both = self.env['res.users'].sudo().create({
            'name': 'g60-both', 'login': 'g60-both',
            'group_ids': [(4, self.env.ref(R + 'group_iad_vfm_officer').id),
                          (4, self.env.ref(R + 'group_iad_vfm_approver').id)]})
        self._fire(b, both, 'verify',
                   payload={'checklist': CHECKLIST, 'attachments': EVIDENCE})
        mine = self._mine(both)
        self.assertIn(a, mine, 'it may approve what somebody else verified')
        self.assertNotIn(b, mine, 'it verified b, so may not approve it')
        found = b._two_gates_refusal(G.GATE_APPROVE, user=both)
        self.assertTrue(found and found[0].startswith('You verified this unit'))

    def test_nobody_with_no_gate_scope_waits_on_anything(self):
        person = self.env['res.users'].sudo().create(
            {'name': 'g60-none', 'login': 'g60-none'})
        self._candidate()
        self.assertFalse(self._mine(person))

    # ── a batch's evidence: stored once, linked from each event ─────

    def test_stored_evidence_is_linked_not_copied(self):
        a = self._to('vfm_pending')
        b = self._to('vfm_pending')
        units = a | b
        files = units._validate_gate_evidence(CHECKLIST, EVIDENCE)
        stored = units._store_gate_evidence(files)
        self.assertEqual(len(stored), 1)
        Attachment = self.env['ir.attachment'].sudo()
        before = Attachment.search_count([])
        for unit in units:
            self._fire(unit, self.officer, 'verify', payload={
                'checklist': CHECKLIST,
                '_stored_attachment_ids': stored.ids})
        self.assertEqual(Attachment.search_count([]), before, 'no copies')
        for unit in units:
            [found] = unit._gate_evidence()
            self.assertEqual(found['files'], stored)
            self.assertEqual(found['checklist'], CHECKLIST)
            ev = found['event']
            self.assertEqual(json.loads(ev.notes)['attachment_ids'],
                             stored.ids)
            self.assertEqual(ev.actor_id, self.officer)

    def test_the_checks_are_the_single_routes_own(self):
        with self.assertRaises(G.GateRefused) as cm:
            self.env['nrs.asset']._validate_gate_evidence(
                dict(CHECKLIST, price=False), EVIDENCE)
        self.assertEqual(cm.exception.args[0], (
            'Verification needs all four checks confirmed — quantity, '
            'specification, condition and price.'))

    # ── when a unit entered its state ───────────────────────────────

    def test_register_state_since_moves_with_the_state(self):
        a = self._candidate()
        self.assertTrue(a.register_state_since)
        self.env.cr.execute(
            "UPDATE nrs_asset SET register_state_since = "
            "register_state_since - interval '3 days' WHERE id = %s",
            (a.id,))
        a.invalidate_recordset()
        old = a.register_state_since
        self._fire(a, self.store, 'submit')
        self.assertGreater(a.register_state_since, old)

    # ── §1.2: the class's mode, whatever the switch says ────────────

    def test_a_gates_off_asset_carries_its_class_mode(self):
        Asset = self.env['nrs.asset'].sudo()
        chair_class = self.env['nrs.asset.category'].create(
            {'name': 'G60 Chairs', 'code': 'G60C',
             'identification_mode': 'tag_id'})
        land = self.env['nrs.asset.category'].create(
            {'name': 'G60 Land', 'code': 'G60L',
             'identification_mode': 'record_only'})
        plain = self.env['nrs.asset.category'].create(
            {'name': 'G60 Plain', 'code': 'G60P'})
        chair = Asset.create({'name': 'Chair', 'category_id': chair_class.id})
        self.assertEqual(chair.register_state, 'registered')
        self.assertEqual(chair.identification_mode, 'tag_id')
        self.assertTrue(chair.active_tag_id, 'a chair is labelled')
        self.assertEqual(Asset.create({'name': 'Box', 'category_id':
                                       plain.id}).identification_mode,
                         'serial')
        plot = Asset.create({'name': 'Plot', 'category_id': land.id})
        self.assertEqual(plot.identification_mode, 'record_only')
        self.assertFalse(plot.active_tag_id,
                         'no label for a unit identified by its record')
        # ...so nothing is ever affixed, and its master goes out at creation
        # instead (with the gates off it would otherwise go out on affix).
        self.assertEqual(len(self._int06(plot)), 1)
        self.assertFalse(self._int06(chair), 'a chair waits for its label')
