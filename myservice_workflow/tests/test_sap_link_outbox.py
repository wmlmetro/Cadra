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
