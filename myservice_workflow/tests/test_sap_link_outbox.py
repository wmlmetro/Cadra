"""Handoff 65 §1: a SAP link sends nothing to SAP — proved in the outbox.

A link writes SAP's own asset number onto a register asset; the asset
master already exists in SAP, so `asset.master.create` must not be queued.
Proved against a REAL SAP target on this tenant (`adapter_type = stub`): the
same target does queue a master for an unlinked asset whose label is
affixed, so "nothing queued" for the linked one is the link's doing, not an
absent configuration.
"""
from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_workflow.models.sap_asset_events import (
    EVENT_ASSET_MASTER_CREATE,
)


@tagged('post_install', '-at_install')
class TestTheLinkSendsNothing(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['workflow.dispatch.log']
        self.env['workflow.config'].search([
            ('purpose', 'in', ('asset_events', 'sap_assets')),
        ]).write({'active': False})
        self.env['workflow.config'].create({
            'name': 'SAP (test, handoff 65)', 'purpose': 'sap_assets',
            'adapter_type': 'stub', 'event_enabled': True,
            'sap_company_code': 'NRS1', 'retry_max_attempts': 3,
            'retry_base_seconds': 60, 'retry_cap_seconds': 600,
        })
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'Link Outbox Category', 'code': 'L65'})
        Users = self.env['res.users'].sudo()
        group = self.env.ref('base.group_user')
        self.maker = Users.create({'name': 'Link Maker 65',
                                   'login': 'link-maker-65',
                                   'group_ids': [(4, group.id)]})
        self.checker = Users.create({'name': 'Link Checker 65',
                                     'login': 'link-checker-65',
                                     'group_ids': [(4, group.id)]})

    def _record(self, number, tag):
        return self.env['nrs.sap.asset'].sudo().with_context(
            cadra_sap_mirror_import=True).create({
                'sap_key': '%s|0' % number, 'company_code': 'NRS1',
                'asset_number': number, 'asset_number_norm': number,
                'sub_number_norm': '0', 'asset_class': '3000',
                'description': 'LAPTOP', 'old_tag': tag, 'old_tag_norm': tag,
                'office_code': 'L65', 'office_source': 'tag',
                'serial_kind': 'none'})

    def _masters(self, asset):
        return self.Log.search([('asset_id', '=', asset.id),
                                ('event_type', '=',
                                 EVENT_ASSET_MASTER_CREATE)])

    def test_approving_a_link_queues_no_master(self):
        tag = 'FIRS/L65/0001'
        rec = self._record('30000065001', tag)
        asset = self.env['nrs.asset'].create({
            'name': 'Linked laptop', 'category_id': self.category.id,
            'legacy_asset_code': tag})
        # The control: the same target queues a master for a plain asset
        # whose label is affixed.
        plain = self.env['nrs.asset'].create({
            'name': 'Unlinked laptop', 'category_id': self.category.id})
        label = plain.active_tag_id
        label._mark_affixed(label.name)
        self.assertEqual(len(self._masters(plain)), 1,
                         'the stub target is live: an affix queues a master')

        link = asset.with_user(self.maker)._sap_link_propose(
            scopes=['register:make'])
        self.assertEqual(link.sap_record_id, rec)
        link.with_user(self.checker)._decide(True, scopes=['register:check'])
        self.assertEqual(asset.sap_asset_number, '30000065001')
        self.assertEqual(asset.sap_code_source, 'linked_from_sap_mirror')
        self.assertEqual(asset.sap_company_code, 'NRS1')
        self.assertFalse(self._masters(asset), 'a link sends no master')
        self.assertFalse(self.Log.search([('asset_id', '=', asset.id)]),
                         'a link queues nothing at all for SAP')
        self.assertEqual(asset.sap_posting_state, 'none')
        # And affixing its label afterwards does not either: SAP already
        # holds the master the number names.
        label = asset.active_tag_id
        label._mark_affixed(label.name)
        self.assertFalse(self._masters(asset))

    def test_the_proposer_cannot_approve(self):
        tag = 'FIRS/L65/0002'
        self._record('30000065002', tag)
        asset = self.env['nrs.asset'].create({
            'name': 'Own link', 'category_id': self.category.id,
            'legacy_asset_code': tag})
        both = ['register:make', 'register:check']
        link = asset.with_user(self.maker)._sap_link_propose(scopes=both)
        from odoo.addons.myservice_asset_register.models.asset_gates import (
            GateRefused)
        with self.assertRaises(GateRefused) as caught:
            link.with_user(self.maker)._decide(True, scopes=both)
        self.assertEqual(caught.exception.kind, 'segregation_of_duties')
        self.assertFalse(asset.sap_asset_number)

    def test_a_link_row_is_never_deleted_or_edited(self):
        tag = 'FIRS/L65/0003'
        self._record('30000065003', tag)
        asset = self.env['nrs.asset'].create({
            'name': 'Kept link', 'category_id': self.category.id,
            'legacy_asset_code': tag})
        link = asset.with_user(self.maker)._sap_link_propose(
            scopes=['register:make'])
        from odoo.exceptions import UserError, ValidationError
        with self.assertRaises(UserError):
            link.sudo().unlink()
        with self.assertRaises(UserError):
            link.sudo().write({'state': 'approved'})
        # Only the approval may say two people linked it.
        with self.assertRaises(ValidationError):
            asset.sudo().write({'sap_asset_number': '30000065003',
                                'sap_code_source': 'linked_from_sap_mirror'})

    def test_a_link_waits_for_a_master_already_in_flight(self):
        """Verification pass, finding 2: an affix on an asset with no number
        queues a master; linking SAP's number on top would send SAP a second
        one. Refused, in words, at the proposal."""
        tag = 'FIRS/L65/0004'
        self._record('30000065004', tag)
        asset = self.env['nrs.asset'].create({
            'name': 'Affixed first', 'category_id': self.category.id,
            'legacy_asset_code': tag})
        label = asset.active_tag_id
        label._mark_affixed(label.name)
        self.assertEqual(asset.sap_posting_state, 'queued')
        from odoo.addons.myservice_asset_register.models.asset_gates import (
            GateRefused)
        with self.assertRaises(GateRefused) as caught:
            asset.with_user(self.maker)._sap_link_propose(
                scopes=['register:make'])
        self.assertEqual(caught.exception.kind, 'invalid_state')
        self.assertIn('two masters', str(caught.exception.args[0]))
        self.assertFalse(self.env['nrs.sap.link'].sudo().search(
            [('asset_id', '=', asset.id)]))


@tagged('post_install', '-at_install')
class TestTheLinkRechecksAndFlags(TestTheLinkSendsNothing):
    """Handoff 66: two of report 65's left items.

    * A `serial_unique` proposal is re-checked for rivals at approval, the
      twin of the `old_tag_unique` re-check (verification pass, finding 9).
    * The serializer's duplicate flag is read once per page, not once per
      asset — and a flag written after a page was read still shows.

    Inherits the outbox class's setUp (category, maker, checker, the stub
    target) and its `_record` helper.
    """

    def _serial_record(self, number, serial):
        return self.env['nrs.sap.asset'].sudo().with_context(
            cadra_sap_mirror_import=True).create({
                'sap_key': '%s|0' % number, 'company_code': 'NRS1',
                'asset_number': number, 'asset_number_norm': number,
                'sub_number_norm': '0', 'asset_class': '3000',
                'description': 'LAPTOP', 'serial_number': serial,
                'serial_norm': serial, 'serial_kind': 'real'})

    def test_a_serial_proposal_is_refused_once_a_rival_appears(self):
        from odoo.addons.myservice_asset_register.models.asset_gates import (
            GateRefused)
        serial = 'SN66-RIVAL-%d' % self.category.id
        rec = self._serial_record('30000066001', serial)
        asset = self.env['nrs.asset'].create({
            'name': 'Serial-linked laptop', 'category_id': self.category.id,
            'serial_number': serial.lower()})
        link = asset.with_user(self.maker)._sap_link_propose(
            scopes=['register:make'])
        self.assertEqual(link.sap_record_id, rec)
        self.assertEqual(link.reason_code, 'serial_unique')
        self.assertEqual(asset._rivals_by_serial(rec), [])
        # A second Cadra asset arrives carrying the same serial, spelled
        # differently (case and spacing), before the checker decides.
        rival = self.env['nrs.asset'].create({
            'name': 'Second laptop, same serial',
            'category_id': self.category.id,
            'serial_number': '  %s ' % serial})
        self.assertEqual(asset._rivals_by_serial(rec), [rival.id])
        with self.assertRaises(GateRefused) as caught:
            link.with_user(self.checker)._decide(
                True, scopes=['register:check'])
        exc = caught.exception
        self.assertEqual(exc.kind, 'invalid_state')
        self.assertIn('1 other Cadra asset', str(exc.args[0]))
        self.assertTrue(exc.details['contested'])
        self.assertEqual(exc.details['asset_ids'], [rival.id])
        self.assertFalse(asset.sap_asset_number, 'nothing was written')

    def test_a_rival_whose_tag_is_in_sap_is_not_a_serial_rival(self):
        """The matcher tries a serial only when no active record carries
        the asset's old tag; such an asset points elsewhere."""
        serial = 'SN66-TAGGED-%d' % self.category.id
        rec = self._serial_record('30000066002', serial)
        asset = self.env['nrs.asset'].create({
            'name': 'Serial laptop', 'category_id': self.category.id,
            'serial_number': serial})
        tag = 'FIRS/L66/0001'
        self._record('30000066003', tag)
        self.env['nrs.asset'].create({
            'name': 'Tagged laptop, same serial',
            'category_id': self.category.id, 'serial_number': serial,
            'legacy_asset_code': tag})
        self.assertEqual(asset._rivals_by_serial(rec), [])

    def _flagged_page(self, n):
        Event = self.env['nrs.asset.event']
        from odoo.addons.myservice_asset_register.models.asset_event import (
            EVENT_SAP_DUPLICATE_FLAGGED)
        assets = self.env['nrs.asset'].create([
            {'name': 'Flag page %d' % i, 'category_id': self.category.id}
            for i in range(n)])
        for a in assets[::2]:
            Event._record(a, EVENT_SAP_DUPLICATE_FLAGGED,
                          to_value='300000660%02d' % a.id, notes='seen')
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['nrs.asset'].browse(assets.ids)

    def _read_flags(self, page):
        before = self.env.cr.sql_log_count
        got = {a.id: (a._sap_duplicate_flag().to_value or None,
                      a._sap_duplicate_flag().notes or None)
               for a in page}
        return got, self.env.cr.sql_log_count - before

    def test_the_flag_is_read_once_per_page(self):
        small, q_small = self._read_flags(self._flagged_page(2))
        large, q_large = self._read_flags(self._flagged_page(12))
        self.assertEqual(q_small, q_large,
                         'one query per page, whatever its size')
        # Same answer as the per-asset reading it replaces.
        page = self.env['nrs.asset'].browse(list(large))
        each = {a.id: a._sap_duplicate_flags().get(a.id) for a in page}
        self.assertEqual(large, {
            aid: ((ev.to_value or None, ev.notes or None) if ev
                  else (None, None)) for aid, ev in each.items()})
        self.assertEqual(sum(1 for v in large.values() if v[0]), 6)

    def test_a_flag_written_after_a_page_was_read_shows(self):
        tag = 'FIRS/L66/0002'
        rec = self._record('30000066004', tag)
        assets = self.env['nrs.asset'].create([
            {'name': 'Contested %d' % i, 'category_id': self.category.id,
             'legacy_asset_code': tag} for i in range(2)])
        page = self.env['nrs.asset'].browse(assets.ids)
        self.assertFalse(any(a._sap_duplicate_flag() for a in page))
        self.env['nrs.asset']._sap_flag_duplicate(
            rec, 'two laptops, one SAP record', scopes=['register:make'],
            targets={'claims': {rec.id: assets.ids}})
        self.assertEqual(
            [a._sap_duplicate_flag().to_value for a in page],
            ['30000066004'] * 2)
