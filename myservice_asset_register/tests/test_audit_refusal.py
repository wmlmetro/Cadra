"""Handoff 69 §5 C2, in-registry — a refused capture sync, kept.

The HTTP suite (`tests/test_where_the_captures_went.py`) proves the row is
written for a real refusal and outlives the request's rollback, on a real
server. This pins the model's own rules, which no route can reach:

* nobody creates a row but the recorder, and nobody changes one;
* a row is deleted only by the retention job, and only past 90 days;
* the recorder keeps the identifying keys as sent and links an id only when
  it names a record — never the photos, the fields or the GPS;
* a failure to record never raises.

Run with:
    odoo -d test19 -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register:TestCaptureRefusal \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
import datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..models import audit_refusal

ANSWER = {"code": "invalid_state", "message": "The label scanned is not the "
          "code used.", "request_id": "req-69",
          "details": {"http_status": 409, "reason": "label_mismatch"}}


@tagged('post_install', '-at_install')
class TestCaptureRefusal(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Refusal = self.env['nrs.audit.capture.refusal']

    def _record(self, body=None, header='DEV-NOWHERE', answer=ANSWER):
        before = self.Refusal.search([], order='id desc', limit=1).id
        self.Refusal._record(body or {}, header, answer)
        return self.Refusal.search([('id', '>', before or 0)])

    def test_the_recorder_keeps_what_identifies_the_attempt(self):
        campaign = self.env['nrs.audit.campaign'].search([], limit=1)
        row = self._record({
            'capture_id': 'ABCDEF01-2345-6789-ABCD-EF0123456789',
            'campaign_id': campaign.id or 999999999,
            'location_id': 999999999, 'outcome': 'in_neither',
            'code': ' NRS-AST-1 ', 'photo_ids': [1], 'gps': {'latitude': 9},
            'fields': {'name': 'a chair'}})
        self.assertEqual(len(row), 1)
        self.assertEqual(row.capture_uuid,
                         'abcdef01-2345-6789-abcd-ef0123456789')
        self.assertEqual(row.campaign_id, campaign)
        self.assertFalse(row.location_id, 'an id that names nothing is '
                                          'not linked')
        self.assertFalse(row.device_id)
        self.assertEqual(row.device_code, 'DEV-NOWHERE')
        self.assertEqual((row.code, row.outcome), ('NRS-AST-1', 'in_neither'))
        self.assertEqual((row.http_status, row.error_code, row.reason,
                          row.message, row.request_id),
                         (409, 'invalid_state', 'label_mismatch',
                          ANSWER['message'], 'req-69'))
        self.assertEqual(row.user_id, self.env.user)
        stored = row.read()[0]
        for key in ('photo_ids', 'gps', 'fields', 'confirmed_json'):
            self.assertNotIn(key, stored)

    def test_an_as_sent_value_is_cut_and_a_bad_body_still_records(self):
        row = self._record({'capture_id': 'x' * 900, 'campaign_id': True,
                            'code': ['a list']}, header=None, answer=None)
        self.assertEqual(len(row), 1)
        self.assertEqual(len(row.capture_uuid), 200)
        self.assertFalse(row.campaign_id or row.code or row.device_code)
        self.assertEqual(row.http_status, 0)

    def test_nobody_creates_or_changes_a_row_by_hand(self):
        with self.assertRaises(UserError):
            self.Refusal.create({'refused_at': datetime.datetime.now(),
                                 'http_status': 400})
        row = self._record()
        with self.assertRaises(UserError):
            row.write({'message': 'something else'})
        with self.assertRaises(UserError):
            row.unlink()
        with self.assertRaises(UserError):
            row.with_context(
                **{audit_refusal._PURGE_KEY: True}).unlink()

    def test_the_retention_job_removes_only_what_is_past_90_days(self):
        # Two different refusals (the same one twice is one row, 69b).
        old = self._record()
        new = self._record(answer={**ANSWER, 'message': 'Another.'})
        past = datetime.datetime.now() - datetime.timedelta(
            days=audit_refusal.RETENTION_DAYS + 1)
        # The model refuses to change a row, so the fixture backdates by SQL.
        self.env.cr.execute("UPDATE nrs_audit_capture_refusal SET "
                            "refused_at = %s WHERE id = %s", (past, old.id))
        self.Refusal.invalidate_model(['refused_at'])
        self.assertGreaterEqual(self.Refusal._cron_purge_old(), 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_a_repeat_adds_to_its_row_and_sync_in_flight_is_none(self):
        body = {'capture_id': '0d4b1c4d-0000-4000-8000-000000000069'}
        first = self._record(body)
        again = self._record(body)
        self.assertFalse(again, 'a repeat writes no new row')
        self.assertEqual(first.count, 2)
        other = self._record(body, answer={**ANSWER, 'message': 'Another.'})
        self.assertEqual(len(other), 1)
        self.assertNotEqual(other, first)
        # A day later the same refusal starts a row of its own.
        self.env.cr.execute("UPDATE nrs_audit_capture_refusal SET "
                            "refused_at = refused_at - interval '25 hours' "
                            "WHERE id = %s", (first.id,))
        self.Refusal.invalidate_model(['refused_at'])
        self.assertEqual(len(self._record(body)), 1)
        # The only write a row takes is that one.
        with self.assertRaises(UserError):
            first.with_context(**{audit_refusal._REPEAT_KEY: True}).write(
                {'message': 'changed'})
        # Not a refusal: the same capture landing in another request.
        self.assertFalse(self._record(body, answer={
            **ANSWER, 'code': 'sync_in_flight'}))

    def test_a_failure_to_record_never_raises(self):
        with patch.object(type(self.Refusal), '_values',
                          side_effect=RuntimeError('boom')), \
                mute_logger(audit_refusal.__name__):
            self.Refusal._record({}, None, ANSWER)
