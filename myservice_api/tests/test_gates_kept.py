"""The gates, kept — handoff 58, in-registry.

What only the registry can show, or shows more cheaply than HTTP:

* **P4** — SAP's INT-06 answer never silently replaces the number the
  Register Maker typed: equal, the label becomes *confirmed by SAP*;
  different, the entered one stays, SAP's is kept beside it, and the unit is
  a dual-code exception naming both numbers, the maker and the checker.
* **P5** — a candidate takes no custodian, no move, no transfer and no
  disposal, through any writer; a request against it is refused when RAISED.
* **Section 12** — the class decides what a gated receipt must carry; the
  unit keeps the mode it arrived with (AD-31); empty serials never collide.
* **Rule 2** — every seeded exclusion refuses the grant that would create
  its pair; an existing pair is not revoked; switched off, the grant goes
  through; every change is on the configuration record.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestGatesKept --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import uuid

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused,
)

from .test_receipt_gates import GateCrew

R = 'myservice_asset_register.'


@tagged('post_install', '-at_install')
class TestGatesKept(GateCrew, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_crew()
        self.furniture = self.env['nrs.asset.category'].create(
            {'name': 'Kept Test Furniture', 'code': 'K58',
             'identification_mode': 'tag_id'})
        self.location = self.env['generic.location'].sudo().search(
            [], limit=1)
        self.employee = self.env['hr.employee'].sudo().create(
            {'name': 'Kept Test Custodian'})

    def _register(self, a):
        """`_to` stops at the maker; the checker approves."""
        self._to('reg_submitted', a)
        self._fire(a, self.checker, 'approve-registration')
        self.assertEqual(a.register_state, 'registered')
        return a

    def _receive(self, **vals):
        base = {'name': 'Kept probe', 'category_id': self.category.id,
                'serial_number': 'SN-K58-%s' % uuid.uuid4().hex[:10],
                'make': 'Dell', 'model_name': 'Latitude',
                'register_state': 'captured'}
        base.update(vals)
        return self.env['nrs.asset'].sudo().create(base)

    def _chair(self, **vals):
        base = {'name': 'Executive chair', 'category_id': self.furniture.id,
                'make': 'Ergo', 'model_name': 'EC-200', 'colour': 'Black',
                'material': 'Leather', 'dimensions': '60x60x120 cm',
                'register_state': 'captured'}
        base.update(vals)
        return self.env['nrs.asset'].sudo().create(base)

    # ── P4: SAP's number and the maker's ────────────────────────────

    def test_sap_returning_the_same_number_confirms_it_and_nothing_else(self):
        a = self._receive()
        self._register(a)
        entered = a.sap_asset_number
        a._set_sap_master({'sap_asset_number': ' %s ' % entered.lower(),
                           'company_code': 'NRS1'})
        self.assertEqual(a.sap_asset_number, entered)
        self.assertEqual(a.sap_code_source, 'confirmed')
        self.assertFalse(a.sap_returned_asset_number)
        self.assertEqual(a.sap_reconciliation_state, 'reconciled')
        self.assertIsNone(a._sap_discrepancy())

    def test_sap_returning_a_different_number_keeps_the_makers_and_raises(
            self):
        a = self._receive()
        self._register(a)
        entered = a.sap_asset_number
        a._set_sap_master({'sap_asset_number': 'SAP-OTHER-1',
                           'company_code': 'NRS1'})
        self.assertEqual(a.sap_asset_number, entered,
                         "the maker's number is never replaced silently")
        self.assertEqual(a.sap_returned_asset_number, 'SAP-OTHER-1')
        self.assertEqual(a.sap_code_source, 'manual')
        self.assertEqual(a.sap_reconciliation_state, 'exception')
        block = a._sap_discrepancy()
        self.assertEqual(block['maker_number'], entered)
        self.assertEqual(block['sap_number'], 'SAP-OTHER-1')
        self.assertEqual(block['maker']['id'], self.maker.id)
        self.assertEqual(block['checker']['id'], self.checker.id)
        self.assertTrue(block['raised_at'])
        listed = self.env['nrs.asset'].sudo().search(
            [('sap_reconciliation_state', '=', 'exception'),
             ('id', '=', a.id)])
        self.assertEqual(listed, a, 'on the reconciliation surface')

    def test_a_discrepancy_closes_when_the_number_is_corrected_to_saps(self):
        """The way out (verification pass: there was none). Correcting the
        entered number to SAP's makes it the maker's entry confirmed by
        SAP's own answer; any other correction leaves the exception."""
        a = self._register(self._receive())
        a._set_sap_master({'sap_asset_number': 'SAP-CLOSE-1',
                           'company_code': 'NRS1'})
        self.assertEqual(a.sap_reconciliation_state, 'exception')
        a.sudo().write({'sap_asset_number': 'SAP-SOMETHING-ELSE'})
        self.assertEqual(a.sap_reconciliation_state, 'exception')
        a.sudo().write({'sap_asset_number': 'sap-close-1'})
        self.assertFalse(a.sap_returned_asset_number)
        self.assertEqual(a.sap_code_source, 'confirmed')
        self.assertEqual(a.sap_reconciliation_state, 'reconciled')

    def test_nobody_but_the_integration_writes_what_sap_returned(self):
        a = self._receive()
        for vals in ({'sap_returned_asset_number': 'X'},
                     {'sap_code_source': 'confirmed'}):
            with self.assertRaises(Exception):
                with self.env.cr.savepoint():
                    a.write(vals)

    # ── P5: a candidate is not on the register ───────────────────────

    def test_a_candidate_takes_no_custodian_move_or_disposal(self):
        a = self._receive()
        cases = (({'custodian_id': self.employee.id},
                  'a custodian can be assigned once it is registered.'),
                 ({'location_id': self.location.id},
                  'it can be moved once it is registered.'),
                 ({'state': 'disposed'},
                  'it can be disposed of once it is registered.'))
        for vals, tail in cases:
            with self.assertRaises(GateRefused) as caught:
                a.sudo().with_context(cadra_approval_exempt='test').write(vals)
            self.assertEqual(caught.exception.kind, 'not_on_the_register')
            message = str(caught.exception.args[0])
            self.assertTrue(message.startswith(
                'This unit is not on the register yet (waiting on Store); '),
                message)
            self.assertTrue(message.endswith(tail), message)
        # Clearing takes nothing onto it; naming the same value is no change.
        a.sudo().write({'custodian_id': False, 'location_id': False})

    def test_the_sentence_names_whom_the_unit_waits_on(self):
        a = self._to('vfm_verified')
        with self.assertRaises(GateRefused) as caught:
            a.sudo().write({'custodian_id': self.employee.id})
        self.assertIn('(waiting on IAD approval)',
                      str(caught.exception.args[0]))

    def test_a_receipt_arriving_with_a_custodian_is_refused(self):
        with self.assertRaises(GateRefused) as caught:
            self._receive(custodian_id=self.employee.id)
        self.assertEqual(caught.exception.kind, 'not_on_the_register')

    def test_a_request_or_transfer_against_a_candidate_is_refused_when_raised(
            self):
        a = self._receive()
        with self.assertRaises(GateRefused):
            self.env['nrs.asset.change.request'].sudo().create({
                'asset_id': a.id, 'change_type': 'location',
                'to_location_id': self.location.id,
                'approver_id': self.checker.id, 'reason': 'x'})
        with self.assertRaises(GateRefused) as caught:
            self.env['nrs.asset.transfer'].sudo().create({
                'asset_id': a.id, 'to_location_id': self.location.id})
        self.assertTrue(str(caught.exception.args[0]).endswith(
            'it can be transferred once it is registered.'))

    def test_a_registered_asset_is_untouched_by_the_rule(self):
        a = self._register(self._receive())
        a.sudo().with_context(cadra_approval_exempt='test').write(
            {'custodian_id': self.employee.id})
        self.assertEqual(a.custodian_id, self.employee)

    # ── Section 12 ────────────────────────────────────────────────────

    def test_a_tag_id_unit_arrives_without_a_serial_and_walks_the_chain(self):
        chair = self._chair()
        self.assertEqual(chair.identification_mode, 'tag_id')
        self.assertFalse(chair.serial_number)
        self._to('tag_issued', chair)
        chair.active_tag_id.with_user(self.tagger).sudo().with_context(
            cadra_affix_check='label_and_attributes')._mark_affixed(
            chair.asset_code)
        self.assertEqual(chair.register_state, 'tagged')
        affix = self.env['nrs.asset.event'].search([
            ('asset_id', '=', chair.id), ('gate_action', '=', 'affix')])
        self.assertIn('"check": "label_and_attributes"', affix.notes)
        self._register(chair)

    def test_a_tag_id_unit_missing_its_colour_is_refused_naming_it(self):
        with self.assertRaises(GateRefused) as caught:
            self._chair(colour=False)
        self.assertEqual(caught.exception.details['missing_fields'],
                         ['colour'])
        self.assertIn('colour', str(caught.exception.args[0]))

    def test_a_serial_unit_without_a_serial_is_refused(self):
        with self.assertRaises(GateRefused) as caught:
            self._receive(serial_number=False)
        self.assertTrue(str(caught.exception.args[0]).endswith(
            '0 of 1 serial numbers captured. Capture one serial number per '
            'accepted unit.'))

    def test_a_pool_unit_is_refused_with_the_phase_e_sentence(self):
        self.furniture.identification_mode = 'pool'
        with self.assertRaises(GateRefused) as caught:
            self._chair()
        self.assertEqual(str(caught.exception.args[0]),
                         'Pool identification is not built yet (Addendum A '
                         'Phase E).')

    def test_a_change_of_mode_affects_new_receipts_only(self):
        chair = self._chair()
        self.furniture.identification_mode = 'serial'
        self.assertEqual(chair.identification_mode, 'tag_id',
                         'a unit keeps the mode it arrived with (AD-31)')
        with self.assertRaises(GateRefused):
            self._chair()  # a NEW chair now needs a serial
        param = self.env['ir.config_parameter'].sudo().get_param(
            'cadra.class_identification.%d' % self.furniture.id)
        self.assertTrue(param.startswith('serial; mandatory: make, '
                                         'model_name'), param)

    def test_empty_serials_never_collide_and_a_real_one_does(self):
        self._chair()
        self._chair()  # two chairs, no serial between them: no collision
        first = self._receive(serial_number='SN-K58-DUP')
        with self.assertRaises(GateRefused) as caught:
            self._receive(serial_number='  sn-k58-dup ')
        self.assertIn(first.asset_code, str(caught.exception.args[0]))

    def test_nothing_is_asked_of_a_receipt_with_the_switch_off(self):
        # A create without `register_state` is the switch-off path.
        a = self.env['nrs.asset'].sudo().create(
            {'name': 'Legacy-shaped', 'category_id': self.furniture.id})
        self.assertEqual(a.register_state, 'registered')
        self.assertFalse(a.identification_mode)

    # ── Rule 2: the exclusion table ──────────────────────────────────

    def _person(self, login, *xmlids):
        groups = [(4, self.env.ref('base.group_user').id)]
        groups += [(4, self.env.ref(x).id) for x in xmlids]
        return self.env['res.users'].sudo().create({
            'name': login, 'login': login, 'email': '%s@k58.example' % login,
            'group_ids': groups})

    def test_every_seeded_exclusion_refuses_the_grant(self):
        seeded = self.env['nrs.role.exclusion'].search([])
        self.assertEqual(len(seeded), 8, 'the addendum defaults')
        for i, exclusion in enumerate(seeded):
            user = self._person('k58-x%d' % i, )
            user.sudo().write({'group_ids': [(4, exclusion.group_a.id)]})
            with self.assertRaises(AccessError) as caught:
                with self.env.cr.savepoint():
                    user.sudo().write(
                        {'group_ids': [(4, exclusion.group_b.id)]})
            self.assertIn('cannot be held by one person',
                          str(caught.exception))

    def test_a_manager_is_refused_an_iad_role_through_implication(self):
        manager = self._person('k58-mgr', R + 'group_asset_manager')
        with self.assertRaises(AccessError):
            manager.sudo().write({'group_ids': [
                (4, self.env.ref(R + 'group_iad_vfm_officer').id)]})

    def test_an_existing_pair_is_not_revoked_and_unrelated_grants_pass(self):
        x = self.env.ref('myservice_api.role_exclusion_maker_checker')
        x.active = False
        both = self._person('k58-both', R + 'group_register_maker',
                            R + 'group_register_checker')
        x.active = True
        both.sudo().write({'group_ids': [
            (4, self.env.ref('myservice_api.group_auditor').id)]})
        self.assertTrue(both.has_group(R + 'group_register_checker'))
        holders = x._holders()[x.id]
        self.assertIn(both, holders)

    def test_switched_off_the_grant_goes_through_and_is_recorded(self):
        x = self.env.ref('myservice_api.role_exclusion_maker_checker')
        x.active = False
        param = self.env['ir.config_parameter'].sudo().get_param(
            'cadra.role_exclusion.%d' % x.id)
        self.assertTrue(param.startswith('off; '), param)
        maker = self._person('k58-maker', R + 'group_register_maker')
        maker.sudo().write({'group_ids': [
            (4, self.env.ref(R + 'group_register_checker').id)]})
        self.assertTrue(maker.has_group(R + 'group_register_checker'))

    def test_the_group_side_is_judged_too(self):
        maker = self._person('k58-gside', R + 'group_register_maker')
        with self.assertRaises(AccessError):
            self.env.ref(R + 'group_register_checker').sudo().write(
                {'user_ids': [(4, maker.id)]})

    def test_a_new_credential_with_excluded_scopes_is_provisioned(self):
        """`_provision_client_user` creates the user BEFORE the client that
        names it, so the user is not yet linked when rule 2 judges it — a
        fresh database's bootstrap (every scope at once) failed on exactly
        this (verification pass). No `user_id`: the provisioning path."""
        client = self.create_api_client({
            'name': 'k58 provisioned',
            'client_id': 'k58p-%s' % uuid.uuid4().hex[:8],
            'scopes': 'assets:write tagging:write register:make '
                      'register:check vfm:verify vfm:approve'})
        self.assertTrue(client.user_id.has_group(R + 'group_register_checker'))
        self.assertTrue(client.user_id.has_group(R + 'group_register_maker'))

    def test_an_api_credentials_user_is_outside_rule_2(self):
        client_user = self._person('k58-cred')
        self.create_api_client({
            'name': 'k58 credential', 'user_id': client_user.id,
            'client_id': 'k58-%s' % uuid.uuid4().hex[:8],
            'scopes': 'register:make register:check'})
        client_user.sudo().write({'group_ids': [
            (4, self.env.ref(R + 'group_register_maker').id),
            (4, self.env.ref(R + 'group_register_checker').id)]})
        self.assertTrue(client_user.has_group(R + 'group_register_checker'))
