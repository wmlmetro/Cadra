"""The receipt gates — handoff 57 (SCAFFOLDING, replaced by handoff 58).

In-registry, because the chain needs SEVEN different people: the no-two-gates
rule refuses one person firing two gates on a unit, so a single API
credential cannot walk it. Each person here holds exactly the role the
addendum gives them, and their scopes are derived from their groups by the
same table a login uses (`scopes_for_user`) — nothing is handed a scope it
would not get by signing in.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestReceiptGates --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import base64
import json
import uuid

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused,
)

EVIDENCE = [{"name": "sighting.txt", "mimetype": "text/plain",
             "data": base64.b64encode(b"sighted on the loading bay").decode()}]
CHECKLIST = {"quantity": True, "specification": True, "condition": True,
             "price": True}


@tagged('post_install', '-at_install')
class TestReceiptGates(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.env['workflow.config'].search([
            ('purpose', 'in', ('asset_events', 'sap_assets')),
        ]).write({'active': False})
        self.sap = self.env['workflow.config'].create({
            'name': 'SAP (gates test)', 'purpose': 'sap_assets',
            'adapter_type': 'stub', 'event_enabled': True,
            'sap_company_code': 'NRS1'})
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'Gates Test Category', 'code': 'G57'})

        def person(login, *xmlids):
            groups = [(4, self.env.ref('base.group_user').id)]
            groups += [(4, self.env.ref(x).id) for x in xmlids]
            return self.env['res.users'].sudo().create({
                'name': login.replace('-', ' ').title(), 'login': login,
                'email': '%s@gates.example' % login, 'group_ids': groups})

        R = 'myservice_asset_register.'
        self.store = person('g57-store', R + 'group_asset_officer')
        self.officer = person('g57-officer', R + 'group_iad_vfm_officer')
        self.approver = person('g57-approver', R + 'group_iad_vfm_approver')
        self.controller = person('g57-controller', R + 'group_asset_controller')
        self.tagger = person('g57-tagger', R + 'group_asset_user',
                             R + 'group_tag_issuing_unit')
        self.maker = person('g57-maker', R + 'group_register_maker')
        self.checker = person('g57-checker', R + 'group_register_checker')

    # ── helpers ───────────────────────────────────────────────────────

    def _candidate(self):
        return self.env['nrs.asset'].sudo().create({
            'name': 'Gates probe', 'category_id': self.category.id,
            'serial_number': 'SN-G57-%s' % uuid.uuid4().hex[:10],
            'grn_reference': 'GRN-57', 'register_state': 'captured'})

    def _fire(self, asset, user, action, **kw):
        # As the routes do: the person's uid, under sudo.
        return asset.with_user(user).sudo()._fire_gate(action, **kw)

    def _to(self, state, asset=None):
        """Walk a candidate to `state`, one person per gate, from wherever
        it stands."""
        a = asset or self._candidate()
        register = {
            'sap_asset_code': 'SAP-%s' % a.id, 'cost': 1850000.0,
            'cost_centre': 'NRS-HQ-IT', 'capitalisation_date': '2026-10-08',
            'asset_class': self.category.id}
        steps = {
            'captured': (self.store, 'submit', {}),
            'vfm_pending': (self.officer, 'verify',
                            {'payload': {'checklist': CHECKLIST,
                                         'attachments': EVIDENCE}}),
            'vfm_verified': (self.approver, 'approve', {}),
            'vfm_approved': (self.controller, 'request-tagging', {}),
            'tagged': (self.maker, 'register', {'payload': register}),
        }
        while a.register_state != state:
            here = a.register_state
            if here == 'tag_issued':
                a.active_tag_id.with_user(self.tagger).sudo()._mark_affixed(
                    a.asset_code)
            else:
                user, action, kw = steps[here]
                self._fire(a, user, action, **kw)
            self.assertNotEqual(a.register_state, here)
        return a

    def _int06(self, asset):
        return self.env['workflow.dispatch.log'].search([
            ('asset_id', '=', asset.id),
            ('event_type', '=', 'asset.master.create')])

    # ── the chain ─────────────────────────────────────────────────────

    def test_the_whole_chain_and_sap_hears_only_at_the_end(self):
        a = self._candidate()
        self.assertFalse(a.active_tag_id,
                         'a captured receipt must not have a label minted')
        self._to('tagged', a)
        label = a.active_tag_id
        self.assertEqual(label.name, a.asset_code,
                         'the label carries the asset code (ruling 4.3)')
        self.assertEqual(label.label_state, 'affixed')
        self.assertFalse(self._int06(a),
                         'affixing a CANDIDATE must send SAP nothing')
        self._to('reg_submitted', a)
        self.assertFalse(self._int06(a))
        self._fire(a, self.checker, 'approve-registration')
        self.assertEqual(a.register_state, 'registered')
        sent = self._int06(a)
        self.assertEqual(len(sent), 1,
                         "the checker's approval sends the master, once")
        payload = json.loads(sent.payload_sent)
        cap = payload['asset']['capitalisation']
        self.assertEqual(cap['amount'], 1850000.0)
        self.assertEqual(cap['cost_centre'], 'NRS-HQ-IT')
        self.assertEqual(cap['proposed_capitalisation_date'], '2026-10-08')
        self.assertEqual(a.sap_code_source, 'manual')

        events = self.env['nrs.asset.event'].search([
            ('asset_id', '=', a.id), ('event_type', '=', 'gate_fired')],
            order='id')
        self.assertEqual(
            [(e.from_value, e.to_value, e.gate) for e in events],
            [('captured', 'vfm_pending', 'receipt'),
             ('vfm_pending', 'vfm_verified', 'verify'),
             ('vfm_verified', 'vfm_approved', 'approve'),
             ('vfm_approved', 'tag_requested', 'tag_request'),
             ('tag_requested', 'tag_issued', False),
             ('tag_issued', 'tagged', 'tagging'),
             ('tagged', 'reg_submitted', 'make'),
             ('reg_submitted', 'registered', 'check')])
        self.assertEqual(
            [e.actor_id for e in events],
            [self.store, self.officer, self.approver, self.controller,
             self.controller, self.tagger, self.maker, self.checker])
        verify = json.loads(events[1].notes)
        self.assertEqual(verify['checklist'], CHECKLIST)
        self.assertEqual(len(verify['attachment_ids']), 1)

    def test_a_registered_asset_is_untouched_by_affix_rules(self):
        """Switch off / every pre-57 record: a label is minted at creation
        and affixing it asks SAP to capitalise, exactly as before."""
        a = self.env['nrs.asset'].sudo().create(
            {'name': 'Legacy probe', 'category_id': self.category.id})
        self.assertEqual(a.register_state, 'registered')
        self.assertTrue(a.active_tag_id)
        a.active_tag_id._mark_affixed(a.active_tag_id.name)
        self.assertEqual(len(self._int06(a)), 1)

    # ── the no-two-gates rule ─────────────────────────────────────────

    def test_one_person_two_gates_is_refused_naming_the_earlier_act(self):
        both = self.env['res.users'].sudo().create({
            'name': 'G57 Both', 'login': 'g57-both', 'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_asset_officer').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_iad_vfm_officer').id)]})
        a = self._candidate()
        self._fire(a, both, 'submit')
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, both, 'verify', payload={
                'checklist': CHECKLIST, 'attachments': EVIDENCE})
        self.assertEqual(caught.exception.kind, 'segregation_of_duties')
        message = str(caught.exception.args[0])
        self.assertRegex(
            message, r'^You received this unit on \d{1,2} \w{3}; a different '
                     r'person must verify it\.$')
        self.assertEqual(a.register_state, 'vfm_pending')
        self.assertEqual(caught.exception.details['earlier']['user_name'],
                         'G57 Both')

    def test_the_approver_must_not_be_the_verifier(self):
        iad = self.env['res.users'].sudo().create({
            'name': 'G57 Iad', 'login': 'g57-iad', 'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_iad_vfm_officer').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_iad_vfm_approver').id)]})
        a = self._candidate()
        self._fire(a, self.store, 'submit')
        self._fire(a, iad, 'verify',
                   payload={'checklist': CHECKLIST, 'attachments': EVIDENCE})
        block = a.with_user(iad)._gates_block()
        approve = [x for x in block['available'] if x['action'] == 'approve']
        self.assertEqual(len(approve), 1)
        self.assertFalse(approve[0]['can_fire'])
        self.assertIn('a different person must approve it',
                      approve[0]['refusal'])
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, iad, 'approve')
        self.assertIn('You verified this unit on', str(caught.exception))

    def test_the_checker_must_not_be_the_maker(self):
        pair = self.env['res.users'].sudo().create({
            'name': 'G57 Pair', 'login': 'g57-pair', 'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_register_maker').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_register_checker').id)]})
        a = self._to('tagged')
        self._fire(a, pair, 'register', payload={
            'sap_asset_code': 'SAP-PAIR-%s' % a.id, 'cost': 10.0,
            'cost_centre': 'CC', 'capitalisation_date': '2026-10-08',
            'asset_class': self.category.id})
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, pair, 'approve-registration')
        self.assertIn('You submitted this unit for registration on',
                      str(caught.exception))
        self.assertIn('a different person must approve its registration',
                      str(caught.exception))
        self.assertEqual(a.register_state, 'reg_submitted')
        self.assertFalse(self._int06(a))

    # ── the other refusals ────────────────────────────────────────────

    def test_approve_without_verify_is_a_wrong_state(self):
        a = self._to('vfm_pending')
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, self.approver, 'approve')
        self.assertEqual(caught.exception.kind, 'invalid_state')

    def test_a_gate_needs_its_scope(self):
        a = self._to('vfm_pending')
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, self.store, 'verify', payload={
                'checklist': CHECKLIST, 'attachments': EVIDENCE})
        self.assertEqual(caught.exception.kind, 'forbidden')
        self.assertIn('vfm:verify', str(caught.exception))

    def test_verify_needs_the_checklist_and_evidence(self):
        a = self._to('vfm_pending')
        for payload in ({'attachments': EVIDENCE},
                        {'checklist': dict(CHECKLIST, price=False),
                         'attachments': EVIDENCE},
                        {'checklist': CHECKLIST},
                        {'checklist': CHECKLIST, 'attachments': []}):
            with self.assertRaises(GateRefused) as caught:
                self._fire(a, self.officer, 'verify', payload=payload)
            self.assertEqual(caught.exception.kind, 'validation_failed')
        self.assertEqual(a.register_state, 'vfm_pending')

    def test_query_and_resubmit_and_reject_need_words(self):
        a = self._to('vfm_pending')
        with self.assertRaises(GateRefused):
            self._fire(a, self.officer, 'query', reason='  ')
        self._fire(a, self.officer, 'query', reason='Wrong model delivered')
        self.assertEqual(a.register_state, 'vfm_query')
        with self.assertRaises(GateRefused):
            self._fire(a, self.store, 'resubmit')
        self._fire(a, self.store, 'resubmit', reason='Supplier swapped it')
        self.assertEqual(a.register_state, 'captured')
        b = self._to('vfm_verified')
        self._fire(b, self.approver, 'reject', reason='Overpriced')
        self.assertEqual(b.register_state, 'vfm_rejected')

    def test_approve_registration_needs_the_sap_code(self):
        a = self._to('reg_submitted')
        a.sudo().write({'sap_asset_number': False})
        with self.assertRaises(GateRefused) as caught:
            self._fire(a, self.checker, 'approve-registration')
        self.assertEqual(caught.exception.kind, 'validation_failed')
        self.assertIn('SAP asset code', str(caught.exception))

    def test_return_registration_goes_back_to_the_maker(self):
        a = self._to('reg_submitted')
        self._fire(a, self.checker, 'return-registration',
                   reason='Cost centre is wrong')
        self.assertEqual(a.register_state, 'tagged')
        self.assertEqual(a.active_tag_id.label_state, 'affixed',
                         'the tag and the code are kept')

    def test_a_candidate_is_tagged_only_once_its_tag_is_issued(self):
        a = self._to('vfm_approved')
        self.assertFalse(a.active_tag_id)
        other = self._to('tag_issued')
        with self.assertRaises(ValidationError):
            other.active_tag_id.with_user(self.officer).sudo()._mark_affixed(
                other.asset_code)  # the officer verified it: two gates

    # ── the field is moved by nothing else ───────────────────────────

    def test_writing_register_state_directly_is_refused(self):
        a = self._candidate()
        with self.assertRaises(UserError):
            a.write({'register_state': 'registered'})
        with self.assertRaises(UserError):
            a.sudo().write({'register_state': 'vfm_approved'})
        self.assertEqual(a.register_state, 'captured')
        with self.assertRaises(UserError):
            self.env['nrs.asset'].sudo().create(
                {'name': 'x', 'register_state': 'tagged'})

    # ── the register hides candidates ────────────────────────────────

    def test_a_candidate_is_hidden_from_searches_and_found_by_id(self):
        Asset = self.env['nrs.asset'].sudo()
        a = self._candidate()
        self.assertFalse(Asset.search_count([('id', '=', a.id)]))
        self.assertEqual(
            Asset.with_context(cadra_candidates=True).search_count(
                [('id', '=', a.id)]), 1)
        self.assertEqual(Asset.search_count(
            [('id', '=', a.id), ('register_state', '!=', 'registered')]), 1)
        self.assertTrue(Asset.browse(a.id).exists())
        before = Asset.search_count([])
        self._fire(self._to('reg_submitted', a), self.checker,
                   'approve-registration')
        self.assertEqual(Asset.search_count([]), before + 1,
                         'the register count moves when the checker approves')

    # ── found by the verification pass ────────────────────────────────

    def test_a_repeat_affix_on_a_tagged_candidate_is_idempotent(self):
        """Handoff 39's contract: a second confirmation does not rewrite the
        first and is not an error — a candidate keeps it."""
        a = self._to('tagged')
        label = a.active_tag_id
        when = label.affixed_date
        label.with_user(self.tagger).sudo()._mark_affixed(a.asset_code)
        self.assertEqual(label.affixed_date, when)
        self.assertEqual(a.register_state, 'tagged')

    def test_replacing_a_tagged_candidates_label_mints_its_successor(self):
        a = self._to('tagged')
        old = a.active_tag_id
        manager = self.env['res.users'].sudo().create({
            'name': 'G57 Manager', 'login': 'g57-manager', 'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref(
                    'myservice_asset_register.group_asset_manager').id)]})
        old.with_user(self.tagger).sudo().action_request_replacement(
            reason='damaged', approver=manager)
        new = old.with_user(manager).sudo().action_approve_replacement()
        self.assertTrue(new, 'an approved replacement must mint a successor')
        self.assertEqual(old.state, 'scrapped')
        self.assertNotEqual(new.name, old.name)
