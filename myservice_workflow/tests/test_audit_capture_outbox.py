"""Handoff 66 §8.6: an audit capture registered from SAP's record sends
nothing to SAP — proved in the outbox, against a REAL SAP target on this
tenant (`adapter_type = stub`), the way handoff 65 proved the link.

The control is the same target queueing a master for a plain asset whose
label is affixed, so "nothing queued" for the audit's asset is the audit's
doing (the asset carries SAP's number), not an absent configuration. A
found-not-in-SAP item registered as new is the other side: it waits on the
Register Maker and nothing is queued until the Checker's approval.

Also here, because they are the model's rules and not the route's: the
ledger (R2a) — every new asset's code is a row, a block's codes are drawn
under the sequence and voided on return — and the reviewer is never the
capturer, even in a campaign built by hand round the team check.
"""
import io
import uuid
from datetime import datetime, timezone

from PIL import Image

from odoo.tests import tagged

from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused,
)
from odoo.addons.myservice_asset_register.models.audit_capture import (
    AUDIT_WRITE_KEY,
)
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_workflow.models.sap_asset_events import (
    EVENT_ASSET_MASTER_CREATE,
)


def _png(seed):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (seed % 256, 40, 90)).save(buf, 'PNG')
    return buf.getvalue()


@tagged('post_install', '-at_install')
class TestTheAuditSendsNothing(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['workflow.dispatch.log']
        self.env['workflow.config'].search([
            ('purpose', 'in', ('asset_events', 'sap_assets')),
        ]).write({'active': False})
        self.env['workflow.config'].create({
            'name': 'SAP (test, handoff 66)', 'purpose': 'sap_assets',
            'adapter_type': 'stub', 'event_enabled': True,
            'sap_company_code': 'NRS1', 'retry_max_attempts': 3,
            'retry_base_seconds': 60, 'retry_cap_seconds': 600,
        })
        self.category = self.env['nrs.asset.category'].create(
            {'name': 'Audit Outbox Category', 'code': 'A66',
             'sap_asset_class': '2000'})
        Users = self.env['res.users'].sudo()
        group = self.env.ref('base.group_user')

        def person(login):
            return Users.create({'name': login, 'login': login,
                                 'group_ids': [(4, group.id)]})
        self.capturer = person('audit-capturer-66')
        self.reviewer = person('audit-reviewer-66')
        self.controller = person('audit-controller-66')
        self.room = self.env['generic.location'].create(
            {'name': 'Audit room 66'})
        self.device = self.env['nrs.audit.device'].with_user(
            self.controller).sudo()._register_device('Phone 66',
                                                     self.capturer)
        self.block = self.env['nrs.audit.code.block'].with_user(
            self.controller).sudo()._issue_block(self.device, 3)
        self.campaign = self.env['nrs.audit.campaign'].with_user(
            self.controller).sudo()._open_campaign(
                'Audit 66', [{'location_id': self.room.id,
                              'office_code': 'A66'}],
                self.capturer, self.reviewer)

    def _record(self, number, tag):
        return self.env['nrs.sap.asset'].sudo().with_context(
            cadra_sap_mirror_import=True).create({
                'sap_key': '%s|0' % number, 'company_code': 'NRS1',
                'asset_number': number, 'asset_number_norm': number,
                'sub_number_norm': '0', 'asset_class': '2000',
                'description': 'OFFICE CHAIR', 'old_tag': tag,
                'old_tag_norm': tag, 'office_code': 'A66',
                'office_source': 'tag', 'serial_kind': 'none',
                'in_latest_export': True})

    def _masters(self, asset):
        return self.Log.search([('asset_id', '=', asset.id),
                                ('event_type', '=',
                                 EVENT_ASSET_MASTER_CREATE)])

    def _capture(self, outcome, seed, **extra):
        photo, _created = self.env['nrs.audit.photo'].with_user(
            self.capturer).sudo()._upload(_png(seed))
        body = {'capture_id': str(uuid.uuid4()),
                'campaign_id': self.campaign.id,
                'location_id': self.room.id, 'outcome': outcome,
                'photo_ids': [photo.id],
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'fields': {'condition': 'good',
                           'category_id': self.category.id,
                           'name': 'Chair %d' % seed}}
        body.update(extra)
        cap, created = self.env['nrs.audit.capture'].with_user(
            self.capturer).sudo()._receive(body, self.device)
        self.assertTrue(created)
        return cap

    def _codes(self):
        return self.block.code_ids.sorted('code').mapped('code')

    def test_registered_from_sap_queues_no_master(self):
        plain = self.env['nrs.asset'].create({
            'name': 'Unaudited chair', 'category_id': self.category.id})
        label = plain.active_tag_id
        label._mark_affixed(label.name)
        self.assertEqual(len(self._masters(plain)), 1,
                         'the stub target is live: an affix queues a master')

        rec = self._record('20000066001', 'FIRS/A66/0001')
        code = self._codes()[0]
        cap = self._capture('in_sap', 1, sap_record_id=rec.id, code=code,
                            scanned_label=code)
        cap.with_user(self.reviewer).sudo()._accept()
        asset = cap.result_asset_id
        self.assertEqual(asset.asset_code, code)
        self.assertEqual(asset.register_state, 'registered')
        self.assertEqual(asset.sap_asset_number, '20000066001')
        self.assertEqual(asset.sap_code_source, 'audit_from_sap_mirror')
        self.assertEqual(asset.active_tag_id.name, code)
        self.assertEqual(asset.active_tag_id.label_state, 'affixed')
        self.assertEqual(asset.active_tag_id.affixed_by, self.capturer)
        self.assertFalse(self._masters(asset), 'SAP has the master')
        self.assertFalse(self.Log.search([('asset_id', '=', asset.id)]),
                         'nothing at all is queued for it')
        self.assertEqual(asset.sap_posting_state, 'none')
        ledger = self.env['nrs.asset.code'].search([('code', '=', code)])
        self.assertEqual((ledger.state, ledger.asset_id), ('active', asset))
        event = asset.event_ids.filtered(
            lambda e: e.event_type == 'audit_capture')
        self.assertEqual(len(event), 1)
        self.assertIn('receipt gates do not apply', event.reason)
        self.assertEqual(event.actor_id, self.reviewer)

    def test_found_not_in_sap_waits_on_the_maker_and_queues_nothing(self):
        code = self._codes()[1]
        cap = self._capture('in_neither', 2, code=code, scanned_label=code)
        cap.with_user(self.reviewer).sudo()._accept()
        self.assertEqual(cap.exception_state, 'open')
        ledger = self.env['nrs.asset.code'].search([('code', '=', code)])
        self.assertEqual(ledger.state, 'in_review')
        asset = cap.with_user(self.controller).sudo()._register_new()
        self.assertEqual(asset.register_state, 'tagged')
        self.assertEqual(asset.asset_code, code)
        self.assertEqual(ledger.state, 'in_review',
                         'active only at registration (R2a)')
        self.assertFalse(self._masters(asset))

    def test_the_reviewer_is_never_the_capturer(self):
        # Built by hand round `_open_campaign`'s team check: the model's
        # rule on the act holds on its own.
        both = self.env['nrs.audit.campaign'].sudo().with_context(
            **{AUDIT_WRITE_KEY: True}).create({
                'name': 'Hand-built 66',
                'scope_ids': [(0, 0, {'location_id': self.room.id})],
                'capturer_ids': [(6, 0, self.capturer.ids)],
                'reviewer_ids': [(6, 0, self.capturer.ids)]})
        self.campaign = both
        cap = self._capture('on_register', 3, asset_id=self.env[
            'nrs.asset'].create({'name': 'Desk 66',
                                 'category_id': self.category.id,
                                 'location_id': self.room.id}).id)
        with self.assertRaises(GateRefused) as caught:
            cap.with_user(self.capturer).sudo()._accept()
        self.assertEqual(caught.exception.kind, 'segregation_of_duties')
        self.assertIn('a different person must review it',
                      str(caught.exception.args[0]))

    def test_the_ledger_and_the_block(self):
        asset = self.env['nrs.asset'].create({
            'name': 'Ledger desk', 'category_id': self.category.id})
        row = self.env['nrs.asset.code'].search(
            [('code', '=', asset.asset_code)])
        self.assertEqual((row.state, row.source, row.asset_id),
                         ('active', 'asset', asset))
        codes = self._codes()
        self.assertEqual(len(codes), 3)
        self.assertEqual(set(self.block.code_ids.mapped('state')),
                         {'reserved'})
        # No asset already holds a block code: drawn from the one sequence.
        self.assertFalse(self.env['nrs.asset'].with_context(
            cadra_candidates=True).search([('asset_code', 'in', codes)]))
        voided = self.block.with_user(self.controller).sudo()._return_block(
            'test')
        self.assertEqual(voided, 3)
        self.assertEqual(set(self.block.code_ids.mapped('state')), {'void'})
        with self.assertRaises(GateRefused):
            self.block.with_user(self.controller).sudo()._return_block()
