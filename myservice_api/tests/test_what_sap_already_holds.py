"""What SAP already holds — handoff 59, in-registry.

The model's half of what `tests/test_what_sap_already_holds.py` drives over
HTTP: the `record_only` rows are in the ONE table, the tagging gates are
skipped without being fired, no label is ever minted for such a unit; the
SAP class is checked at both registration gates; placeholders are matched
on the normalised value; SAP asset numbers are unique once stripped and
upper-cased; the class-digit warning knows class 3500's numbers start `5`.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestWhatSapAlreadyHolds --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import uuid

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models import (
    asset_gates, serial_placeholders)
from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused, TRANSITIONS, sap_number_class_warning)

from .test_receipt_gates import CHECKLIST, EVIDENCE, GateCrew


@tagged('post_install', '-at_install')
class TestWhatSapAlreadyHolds(GateCrew, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_crew()
        self.land = self.env['nrs.asset.category'].create(
            {'name': 'Land (59 test)', 'code': 'L59',
             'identification_mode': 'record_only', 'sap_asset_class': '6000'})

    def _plot(self, **vals):
        base = {'name': 'Plot probe', 'category_id': self.land.id,
                'reference': 'PLOT-%s' % uuid.uuid4().hex[:8],
                'register_state': 'captured'}
        base.update(vals)
        return self.env['nrs.asset'].sudo().create(base)

    # ── §2 · record_only ─────────────────────────────────────────────

    def test_record_only_rows_are_in_the_one_table(self):
        """Not a second path: the rows that differ for a unit with no label
        are rows of `TRANSITIONS`, limited by `modes`."""
        record_only = [r for r in TRANSITIONS
                       if 'record_only' in r.get('modes', ('record_only',))]
        actions = {r['action'] for r in record_only}
        self.assertNotIn('request-tagging', actions)
        self.assertIn('register', actions)
        froms = {s for r in record_only if r['action'] == 'register'
                 for s in r['frm']}
        self.assertEqual(froms, {'reg_ready'})
        self.assertEqual(asset_gates.WAITING_ON['reg_ready'], 'maker')

    def test_five_gates_skip_tagging_and_mint_no_label(self):
        a = self._plot()
        self.assertEqual(a.identification_mode, 'record_only')
        self.assertFalse(a.active_tag_id)
        self.assertTrue(a.asset_code, 'the asset code is assigned at creation')
        self._fire(a, self.store, 'submit')
        self._fire(a, self.officer, 'verify',
                   payload={'checklist': CHECKLIST, 'attachments': EVIDENCE})
        self._fire(a, self.approver, 'approve')
        self.assertEqual(a.register_state, 'reg_ready')
        self.assertEqual(a._gates_block()['waiting_on'], 'maker')
        with self.assertRaises(GateRefused) as cm:
            self._fire(a, self.controller, 'request-tagging')
        self.assertEqual(cm.exception.kind, 'invalid_state')
        skip = a._gate_events().filtered(
            lambda e: e.gate_action == 'skip-tagging')
        self.assertEqual(len(skip), 1)
        self.assertFalse(skip.gate, 'skipped, not fired: no gate recorded')
        self.assertEqual(skip.reason,
                         'no label: Land (59 test) is identified by its '
                         'record')
        self.assertEqual((skip.from_value, skip.to_value),
                         ('vfm_approved', 'reg_ready'))
        self._fire(a, self.maker, 'register', payload={
            'sap_asset_code': '6' + '0' * 6 + '4159', 'cost': 5e6,
            'cost_centre': 'NRS-HQ-EST', 'capitalisation_date': '2026-10-12',
            'asset_class': self.land.id})
        self._fire(a, self.checker, 'approve-registration')
        self.assertEqual(a.register_state, 'registered')
        self.assertFalse(a.tag_ids, 'no label, ever')
        self.assertEqual(len(self._int06(a)), 1,
                         "SAP gets the master at the checker's approval, "
                         "label or none")
        self.assertEqual(
            len({e.actor_id for e in a._gate_events() if e.gate}), 5,
            'five people fired five gates')
        # Nothing after registration mints one either — the back-office
        # station's Generate is `_generate_tag`.
        with self.assertRaises(UserError):
            a._generate_tag(source='manual')
        self.assertFalse(a.tag_ids)

    def test_a_returned_record_only_registration_goes_back_to_reg_ready(self):
        a = self._plot()
        for user, action, kw in (
                (self.store, 'submit', {}),
                (self.officer, 'verify', {'payload': {
                    'checklist': CHECKLIST, 'attachments': EVIDENCE}}),
                (self.approver, 'approve', {}),
                (self.maker, 'register', {'payload': {
                    'sap_asset_code': 'ZQX%s' % uuid.uuid4().hex[:6],
                    'cost': 10.0, 'cost_centre': 'CC',
                    'capitalisation_date': '2026-10-12',
                    'asset_class': self.land.id}})):
            self._fire(a, user, action, **kw)
        self._fire(a, self.checker, 'return-registration', reason='Wrong CC')
        self.assertEqual(a.register_state, 'reg_ready')

    def test_a_serial_on_a_record_only_unit_is_refused_whoever_sends_it(self):
        with self.assertRaises(GateRefused) as cm:
            self._plot(serial_number='SN-123')
        self.assertEqual(cm.exception.details['field'], 'serial_number')
        with self.assertRaises(GateRefused) as cm:
            self._plot(reference=False)
        self.assertEqual(cm.exception.details['missing_fields'],
                         ['reference'])

    # ── §1 · the SAP class at both registration gates ────────────────

    def test_registration_needs_the_class_to_carry_a_sap_class(self):
        self.category.sap_asset_class = False
        a = self._to('tagged')
        payload = {'sap_asset_code': 'ZQY%s' % a.id, 'cost': 10.0,
                   'cost_centre': 'CC', 'capitalisation_date': '2026-10-12',
                   'asset_class': self.category.id}
        with self.assertRaises(GateRefused) as cm:
            self._fire(a, self.maker, 'register', payload=payload)
        self.assertEqual(str(cm.exception.args[0]), (
            'Gates Test Category has no SAP asset class, so SAP would reject '
            'this asset. An Asset Controller sets it under Settings → Asset '
            'Categories.'))
        self.assertEqual(a.register_state, 'tagged', 'nothing written')
        self.assertFalse(a.sap_asset_number)
        self.category.sap_asset_class = '3000'
        self._fire(a, self.maker, 'register', payload=payload)
        self.category.sap_asset_class = False
        with self.assertRaises(GateRefused):
            self._fire(a, self.checker, 'approve-registration')
        self.assertEqual(a.register_state, 'reg_submitted')

    def test_the_sap_class_is_four_digits_and_recorded(self):
        for bad in ('300', '30000', '3A00'):
            with self.assertRaises(ValidationError):
                self.category.sap_asset_class = bad
        self.category.sap_asset_class = ' 4000 '
        self.assertEqual(self.category.sap_asset_class, '4000')
        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_param(
                'cadra.class_sap_asset_class.%d' % self.category.id),
            '4000; class: Gates Test Category')
        self.category.sap_asset_class = ''
        self.assertFalse(self.category.sap_asset_class)

    # ── §3 · placeholders ────────────────────────────────────────────

    def test_placeholders_are_matched_on_the_normalised_value(self):
        is_ph = serial_placeholders.matcher(serial_placeholders.load(self.env))
        for value in ('XXXX', ' x ', '0', '0000', 'no   serial', 'n/a',
                      '4a12345fd', 'None'):
            self.assertTrue(is_ph(value), value)
        for value in ('', 'X1', '0A', 'N\\A', 'PYT59-0001', 'NONEX'):
            self.assertFalse(is_ph(value), value)

    def test_a_placeholder_is_refused_before_the_uniqueness_check(self):
        """Legacy `XXXX` on the register: a receipt of `XXXX` is refused as
        a placeholder, never as its duplicate; a real serial goes through."""
        self.env['nrs.asset'].sudo().create({
            'name': 'Legacy XXXX', 'category_id': self.category.id,
            'serial_number': 'XXXX'})
        self.assertEqual(self._candidate().register_state, 'captured',
                         'a real serial goes through')
        with self.assertRaises(GateRefused) as cm:
            self.env['nrs.asset'].sudo().create({
                'name': 'Gates probe', 'category_id': self.category.id,
                'serial_number': 'xxxx', 'make': 'Dell', 'model_name': 'L',
                'register_state': 'captured'})
        self.assertEqual(str(cm.exception.args[0]), (
            "'xxxx' is a placeholder, not a serial number. Capture the "
            "serial printed on the item."))
        self.assertTrue(cm.exception.details['placeholder'])

    # ── §4 · SAP asset numbers ───────────────────────────────────────

    def test_sap_numbers_are_unique_once_stripped_and_upper_cased(self):
        a = self.env['nrs.asset'].sudo().create(
            {'name': 'A', 'category_id': self.category.id})
        b = self.env['nrs.asset'].sudo().create(
            {'name': 'B', 'category_id': self.category.id})
        a.sap_asset_number = 'ZQZ59ICT0001'
        with self.assertRaises(ValidationError):
            b.sap_asset_number = ' zqz59ict0001 '

    def test_the_class_digit_warning(self):
        self.assertIsNone(sap_number_class_warning('3' + '1' * 10, '3000'))
        self.assertIsNone(sap_number_class_warning('ZQZ59ICT0001', '3000'))
        self.assertIsNone(sap_number_class_warning('3' + '1' * 10, None))
        self.assertEqual(
            sap_number_class_warning('2' + '1' * 10, '3000'),
            '2' + '1' * 10 + ' looks like a class 2000 number; this '
            'category maps to 3000.')
        # Class 3500's numbers start `5` in SAP's own export.
        self.assertIsNone(sap_number_class_warning('5' + '1' * 10, '3500'))
        self.assertEqual(
            sap_number_class_warning('5' + '1' * 10, '3000'),
            '5' + '1' * 10 + ' looks like a class 3500 number; this '
            'category maps to 3000.')
