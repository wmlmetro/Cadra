"""INT-05 outbound delivery: queueing, backoff, dead-lettering.

The pytest suite in `tests/` talks HTTP to a live server and cannot reach
model internals, so the delivery guarantee — the part of this work that is
actually hard — is proven here, in-process, where a failing receiver can be
simulated exactly and a three-hour backoff does not take three hours.

Run with:
    odoo -d <db> -u myservice_workflow --test-enable \\
         --test-tags /myservice_workflow --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
import contextlib
import json
from unittest.mock import patch

from odoo import fields
from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tools import mute_logger
from odoo.tests import tagged

from odoo.addons.myservice_workflow.models.workflow_config import (
    WorkflowRestAdapter,
)
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


class FakeAdapter:
    """Stands in for a receiver. Returns whatever the test told it to."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def deliver(self, payload, event_id, request_ref=None):
        self.calls.append({'payload': payload, 'event_id': event_id,
                           'request_ref': request_ref})
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def ok_result(status=200, ref='VIM-2026-00001'):
    return {'ok': True, 'retryable': False, 'status': status,
            'body': json.dumps({'name': ref}), 'external_ref': ref,
            'acknowledged': True, 'error': None}


def fail_result(status=503, retryable=True):
    return {'ok': False, 'retryable': retryable, 'status': status,
            'body': 'upstream down', 'external_ref': None,
            'acknowledged': False, 'error': 'HTTP %s' % status}


@tagged('post_install', '-at_install')
class TestOutboundTagEvents(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['workflow.dispatch.log']
        self.category = self.env['nrs.asset.category'].create({
            'name': 'INT-05 Test Category',
        })
        self.config = self.env['workflow.config'].create({
            'name': 'Vendra (test)',
            'purpose': 'asset_events',
            'adapter_type': 'stub',
            'event_enabled': True,
            'retry_max_attempts': 4,
            'retry_base_seconds': 60,
            'retry_cap_seconds': 600,
        })

    # ── helpers ───────────────────────────────────────────────────────

    def _asset(self, **overrides):
        vals = {
            'name': 'INT-05 Probe',
            'category_id': self.category.id,
            'serial_number': 'SN-INT05-001',
            'grn_reference': 'GRN-2026-00001',
            'purchase_order_reference': 'PO-2026-00417',
            'import_source': 'vendra',
            'import_ref': 'MAT-PRE-2026-00001',
        }
        vals.update(overrides)
        return self.env['nrs.asset'].create(vals)

    def _affix(self, asset, **kwargs):
        label = asset.active_tag_id
        self.assertTrue(label, 'asset should have an auto-generated tag')
        label._mark_affixed(label.name, **kwargs)
        return label

    def _events(self, asset):
        return self.Log.search([('asset_id', '=', asset.id),
                                ('event_type', '=', 'asset.tag.affixed')])

    # ── enqueue ───────────────────────────────────────────────────────

    def test_affix_queues_one_event_with_a_stable_id(self):
        asset = self._asset()
        self._affix(asset, affixed_by_name='J. Okafor')

        events = self._events(asset)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.status, 'pending')
        self.assertEqual(events.attempts, 0)
        self.assertTrue(events.event_id)
        self.assertEqual(events.config_id, self.config)
        # Snapshotted, so retuning the policy later cannot resurrect or kill
        # an event already in flight.
        self.assertEqual(events.max_attempts, 4)

        payload = json.loads(events.payload_sent)
        self.assertEqual(payload['event'], 'asset.tag.affixed')
        self.assertEqual(payload['event_id'], events.event_id,
                         'the body must carry the same key as the header')

    def test_payload_echoes_provenance_and_does_not_invent_a_print(self):
        asset = self._asset()
        label = self._affix(asset, affixed_by_name='J. Okafor')
        payload = json.loads(self._events(asset).payload_sent)

        self.assertEqual(payload['provenance']['grn_reference'], 'GRN-2026-00001')
        self.assertEqual(payload['provenance']['purchase_order_reference'],
                         'PO-2026-00417')
        self.assertEqual(payload['provenance']['import_source'], 'vendra')
        self.assertEqual(payload['asset']['serial_number'], 'SN-INT05-001')
        self.assertEqual(payload['tag']['number'], label.name)
        self.assertEqual(payload['tag']['label_id'], label.id)
        self.assertEqual(payload['tag']['label_state'], 'affixed')
        self.assertEqual(payload['tag']['affixed_by_name'], 'J. Okafor')
        # Never printed, so the event says so rather than inferring one.
        self.assertIsNone(payload['tag']['printed_at'])
        self.assertTrue(payload['tag']['affixed_at'].endswith('Z'),
                        'timestamps must carry an explicit offset')

    def test_repeat_confirmation_does_not_raise_a_second_event(self):
        asset = self._asset()
        label = asset.active_tag_id
        label._mark_affixed(label.name, affixed_by_name='J. Okafor')
        label._mark_affixed(label.name, affixed_by_name='Someone Else')

        self.assertEqual(len(self._events(asset)), 1,
                         'one physical act is one event')

    def test_no_target_at_all_means_no_event_and_no_failure(self):
        self.config.unlink()
        asset = self._asset()
        self._affix(asset)

        self.assertFalse(self._events(asset))
        # The capture still stands — transport being unconfigured must never
        # cost Cadra the record of what happened.
        self.assertEqual(asset.active_tag_id.label_state, 'affixed')
        self.assertTrue(asset.tag_label_state == 'affixed')

    def test_a_paused_target_queues_the_event_rather_than_discarding_it(self):
        """`event_enabled` is an off-switch for delivery, not a shredder.

        Discarding here would mean that switching the target back on silently
        loses every affix that happened while it was off, with nothing to
        notice or backfill from.
        """
        self.config.event_enabled = False
        asset = self._asset()
        self._affix(asset)

        event = self._events(asset)
        self.assertEqual(len(event), 1, 'the event must still be queued')
        self.assertEqual(event.status, 'pending')

        # ...and the drain leaves it alone until the switch goes back on.
        adapter = FakeAdapter(ok_result())
        with self._drain(adapter):
            self.Log._cron_drain_outbound_events()
        self.assertEqual(adapter.calls, [])
        self.assertEqual(event.attempts, 0)

        self.config.event_enabled = True
        with self._drain(adapter):
            self.Log._cron_drain_outbound_events()
        self.assertEqual(len(adapter.calls), 1, 'the backlog must drain')
        self.assertEqual(event.status, 'acknowledged')

    def test_a_mismatched_scan_neither_affixes_nor_queues(self):
        asset = self._asset()
        label = asset.active_tag_id
        with self.assertRaises(ValidationError):
            label._mark_affixed('NOT-THE-TAG')
        self.assertFalse(self._events(asset))

    # ── delivery outcomes ─────────────────────────────────────────────

    def _deliver(self, event, adapter):
        with patch.object(type(self.config), '_get_adapter',
                          return_value=adapter):
            return event._deliver_once()

    def _drain(self, adapter):
        """Run the drain against a fake receiver."""
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(
            type(self.config), '_get_adapter', return_value=adapter))
        return stack

    def test_successful_delivery_acknowledges_and_clears_the_queue(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)

        self.assertTrue(self._deliver(event, FakeAdapter(ok_result())))
        self.assertEqual(event.status, 'acknowledged')
        self.assertEqual(event.attempts, 1)
        self.assertFalse(event.next_attempt_at)
        self.assertEqual(event.external_ref, 'VIM-2026-00001')
        self.assertTrue(event.sent_at)

    def test_a_2xx_without_an_identity_is_sent_not_acknowledged(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        result = dict(ok_result(status=202), external_ref=None,
                      acknowledged=False, body='')

        self.assertTrue(self._deliver(event, FakeAdapter(result)))
        self.assertEqual(event.status, 'sent',
                         'a bare 202 is "received", not "acknowledged"')

    def test_a_retryable_failure_backs_off_and_stays_queued(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)

        self.assertFalse(self._deliver(event, FakeAdapter(fail_result(503))))
        self.assertEqual(event.status, 'error')
        self.assertEqual(event.attempts, 1)
        self.assertTrue(event.next_attempt_at > fields.Datetime.now())
        self.assertIn('HTTP 503', event.error_message)

    def test_backoff_doubles_and_is_capped(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)

        seen = []
        for attempt in range(1, 6):
            event._dispatch().write({'attempts': attempt})
            seen.append(event._backoff_seconds())
        # base 60, cap 600
        self.assertEqual(seen, [60, 120, 240, 480, 600])

    def test_a_permanent_rejection_dead_letters_on_the_first_attempt(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)

        self.assertFalse(self._deliver(
            event, FakeAdapter(fail_result(400, retryable=False))))
        self.assertEqual(event.status, 'dead')
        self.assertEqual(event.attempts, 1,
                         'a 400 does not become valid by being resent')
        self.assertFalse(event.next_attempt_at)

    def test_exhausting_the_budget_dead_letters_and_tells_a_human(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        adapter = FakeAdapter(fail_result(503))

        for _ in range(4):
            event._dispatch().write(
                {'next_attempt_at': fields.Datetime.now()})
            self._deliver(event, adapter)

        self.assertEqual(event.attempts, 4)
        self.assertEqual(event.status, 'dead')
        self.assertFalse(event.next_attempt_at)
        # Visible where the person who cares about this asset is looking.
        notes = self.env['mail.message'].search([
            ('model', '=', 'nrs.asset'), ('res_id', '=', asset.id),
        ])
        self.assertTrue(
            any('not delivered' in (m.body or '') for m in notes),
            'a dead letter must reach the asset chatter, not just the log')

    def test_the_event_id_is_identical_on_every_redelivery(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        adapter = FakeAdapter(fail_result(503), fail_result(503), ok_result())

        for _ in range(3):
            event._dispatch().write(
                {'next_attempt_at': fields.Datetime.now()})
            self._deliver(event, adapter)

        self.assertEqual(len(adapter.calls), 3)
        ids = {call['event_id'] for call in adapter.calls}
        self.assertEqual(len(ids), 1, 'a redelivery must reuse the event id')
        self.assertEqual(ids.pop(), event.event_id)
        self.assertEqual(event.status, 'acknowledged')
        self.assertEqual(event.attempts, 3)

    def test_the_backoff_is_honoured_by_the_worker_too(self):
        """A row can be reachable twice — its own trigger and a sweep."""
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        event._dispatch().write({'next_attempt_at': self.env[
            'workflow.dispatch.log']._next_attempt_datetime(600)})
        adapter = FakeAdapter(ok_result())

        self.assertFalse(self._deliver(event, adapter))
        self.assertEqual(adapter.calls, [],
                         'no attempt may be spent before the wait elapses')
        self.assertEqual(event.attempts, 0)

    # ── the drain ─────────────────────────────────────────────────────

    def test_the_drain_never_touches_a_request_approval_row(self):
        """The hazard in reusing this table as a queue.

        Request dispatches also sit at `pending` and `error`. A drain scoped
        merely by status would re-POST a human approval that nobody asked to
        resubmit.
        """
        legacy = self.Log.create({
            'direction': 'outbound',
            'status': 'error',
            'adapter_type': 'stub',
            'error_message': 'a failed approval dispatch from before INT-05',
        })
        # `next_attempt_at` must be DUE, or this test passes on that clause
        # alone and proves nothing about `event_type` — delete the event_type
        # filter from the domain and it would still be green.
        legacy._dispatch().write({'next_attempt_at': fields.Datetime.now()})
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)

        adapter = FakeAdapter(ok_result())
        with self._drain(adapter):
            self.Log._cron_drain_outbound_events()

        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0]['request_ref'], event.name)
        self.assertEqual(legacy.status, 'error',
                         'the approval row must be untouched')
        self.assertEqual(legacy.attempts, 0)

    def test_the_drain_skips_a_disabled_target_in_the_domain(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        self.config.event_enabled = False

        adapter = FakeAdapter(ok_result())
        with self._drain(adapter):
            self.Log._cron_drain_outbound_events()

        self.assertEqual(adapter.calls, [])
        self.assertEqual(event.status, 'pending')

    # ── human actions ─────────────────────────────────────────────────

    def test_retry_extends_the_budget_without_erasing_the_attempt_count(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        adapter = FakeAdapter(fail_result(503))
        for _ in range(4):
            event._dispatch().write(
                {'next_attempt_at': fields.Datetime.now()})
            self._deliver(event, adapter)
        self.assertEqual(event.status, 'dead')

        event.action_retry_now()

        self.assertEqual(event.status, 'pending')
        self.assertEqual(event.attempts, 4,
                         'the attempt count is evidence and must survive')
        self.assertEqual(event.max_attempts, 8)
        self.assertTrue(event.next_attempt_at)

    def test_a_delivered_event_cannot_be_resent_by_hand(self):
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        self._deliver(event, FakeAdapter(ok_result()))

        with self.assertRaises(UserError):
            event.action_retry_now()

    # ── adapter classification ────────────────────────────────────────

    def test_status_classification(self):
        """Which HTTP answers are worth trying again."""
        adapter = WorkflowRestAdapter(self.config)

        class R:
            def __init__(self, code, text='{}'):
                self.status_code = code
                self.text = text

            def json(self):
                return json.loads(self.text)

        cases = {
            500: True, 502: True, 503: True,     # the receiver is broken
            408: True, 425: True, 429: True,     # "wait", not "no"
            400: False, 401: False, 403: False,  # the request is wrong
            404: False, 422: False,
        }
        for code, retryable in cases.items():
            result = adapter._classify(R(code))
            self.assertFalse(result['ok'], code)
            self.assertEqual(result['retryable'], retryable,
                             'HTTP %s retryability' % code)

    def test_a_duplicate_is_a_delivery_not_a_failure(self):
        """409 means the receiver already has it — which is the goal."""
        adapter = WorkflowRestAdapter(self.config)

        class R:
            status_code = 409
            text = '{"name": "VIM-2026-00001"}'

            def json(self):
                return json.loads(self.text)

        result = adapter._classify(R())
        self.assertTrue(result['ok'])
        self.assertEqual(result['external_ref'], 'VIM-2026-00001')

    # ── configuration ─────────────────────────────────────────────────

    def test_an_unusable_event_target_is_refused_at_save_time(self):
        with self.assertRaises(ValidationError):
            self.env['workflow.config'].create({
                'name': 'Broken', 'purpose': 'asset_events',
                'adapter_type': 'rest',          # no base url, no endpoint
            })
        with self.assertRaises(ValidationError):
            self.env['workflow.config'].create({
                'name': 'By email?', 'purpose': 'asset_events',
                'adapter_type': 'email', 'email_to': 'x@example.com',
            })

    def test_the_approval_config_lookup_is_unaffected(self):
        approvals = self.env['workflow.config'].create({
            'name': 'NRS WorkSpace', 'purpose': 'workspace',
            'adapter_type': 'stub',
        })
        self.assertEqual(
            self.env['workflow.config'].get_active_config(), approvals,
            'the approval flow must not start resolving the event target')

    # ── the production wiring ─────────────────────────────────────────

    def test_the_drain_cron_exists_and_trigger_resolves_it(self):
        """The gap that hid a blocker.

        Every other test calls `_deliver_once` or `_cron_drain_outbound_events`
        by hand, so a typo in the cron xmlid would make `_trigger_drain` log a
        warning, return False, and leave the whole suite green while no event
        was ever delivered without waiting for the periodic sweep.
        """
        cron = self.env.ref('myservice_workflow.cron_workflow_outbound_events')
        self.assertTrue(cron.active)
        self.assertEqual(cron.ir_actions_server_id.code.strip(),
                         'model._cron_drain_outbound_events()')

        before = self.env['ir.cron.trigger'].search_count(
            [('cron_id', '=', cron.id)])
        self.assertTrue(self.Log._trigger_drain(),
                        '_trigger_drain must resolve the cron, not warn')
        self.assertEqual(
            self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)]),
            before + 1)

    def test_queueing_an_event_books_an_immediate_drain(self):
        cron = self.env.ref('myservice_workflow.cron_workflow_outbound_events')
        before = self.env['ir.cron.trigger'].search_count(
            [('cron_id', '=', cron.id)])
        asset = self._asset()
        self._affix(asset)
        self.assertGreater(
            self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)]),
            before, 'the affix must book a delivery run')

    def test_a_queued_row_is_eligible_for_the_very_next_drain(self):
        """No grace period may exclude the row its own trigger was booked for.

        An earlier version excluded rows younger than 20 seconds, which is
        every freshly queued row — so the triggered run found nothing, the
        trigger was consumed, and the first attempt waited for the periodic
        sweep.
        """
        asset = self._asset()
        self._affix(asset)
        adapter = FakeAdapter(ok_result())
        with self._drain(adapter):
            self.Log._cron_drain_outbound_events()
        self.assertEqual(len(adapter.calls), 1,
                         'the first attempt must happen on the triggered run')

    # ── the ORM guard ─────────────────────────────────────────────────

    def test_a_hand_crafted_event_row_is_refused(self):
        """A row carrying delivery fields is an instruction to POST.

        `readonly=True` is a web-client hint, not an ORM guard — so without
        this any internal user could forge an `asset.tag.affixed` and have
        Cadra sign it with the tenant's credentials, walking round the
        `tagging:write` separation entirely.
        """
        with self.assertRaises(ValidationError):
            self.Log.create({
                'direction': 'outbound',
                'status': 'pending',
                'event_type': 'asset.tag.affixed',
                'event_id': 'forged',
                'config_id': self.config.id,
                'payload_sent': '{"event": "asset.tag.affixed"}',
                'next_attempt_at': fields.Datetime.now(),
            })

        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        with self.assertRaises(ValidationError):
            event.write({'next_attempt_at': fields.Datetime.now()})
        with self.assertRaises(ValidationError):
            event.write({'attempts': 0})

    def test_an_ordinary_audit_row_is_still_writable(self):
        """The guard must not break `request.request._send_to_workflow`."""
        row = self.Log.create({
            'direction': 'outbound',
            'status': 'pending',
            'adapter_type': 'stub',
            'payload_sent': '{}',
        })
        row.write({'status': 'sent', 'workspace_ref': 'WF-1'})
        self.assertEqual(row.status, 'sent')

    # ── the constraint actually exists ────────────────────────────────

    def test_event_id_is_unique_in_the_database(self):
        """Handoff 02 was entirely about constraints that were declared and
        did not exist. Assert this one rather than trusting the declaration."""
        asset = self._asset()
        self._affix(asset)
        event = self._events(asset)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "INSERT INTO workflow_dispatch_log "
                    "(direction, status, event_id) VALUES (%s, %s, %s)",
                    ('outbound', 'pending', event.event_id))

    # ── the REST adapter's request, without a socket ──────────────────

    def test_the_rest_adapter_composes_url_headers_and_timeout(self):
        cfg = self.env['workflow.config'].create({
            'name': 'Vendra REST', 'purpose': 'asset_events',
            'adapter_type': 'rest',
            'rest_base_url': 'https://vendra.example/',
            'rest_endpoint_event': '/api/method/vendra_network.api.tag_event',
            'rest_auth_type': 'bearer', 'rest_api_key': 'secret-token',
            'rest_timeout': 30,
        })
        adapter = cfg._get_adapter()

        class R:
            status_code = 201
            text = '{"name": "VIM-1"}'

            def json(self):
                return json.loads(self.text)

        with patch('requests.post', return_value=R()) as post:
            result = adapter.deliver({'event': 'asset.tag.affixed'},
                                     'abc123', request_ref='WDL-2026-0001')

        url = post.call_args[0][0]
        headers = post.call_args[1]['headers']
        self.assertEqual(
            url,
            'https://vendra.example/api/method/vendra_network.api.tag_event')
        self.assertEqual(headers['X-Idempotency-Key'], 'abc123')
        self.assertEqual(headers['X-Event-Id'], 'abc123')
        self.assertEqual(headers['X-Request-Id'], 'WDL-2026-0001')
        self.assertEqual(headers['Authorization'], 'Bearer secret-token')
        # split (connect, read) budget
        self.assertEqual(post.call_args[1]['timeout'], (10, 30))
        self.assertTrue(result['ok'])
        self.assertEqual(result['external_ref'], 'VIM-1')

    def test_the_rest_adapter_reports_a_missing_endpoint_permanently(self):
        cfg = self.env['workflow.config'].create({
            'name': 'Stub then broken', 'purpose': 'asset_events',
            'adapter_type': 'stub',
        })
        cfg.invalidate_recordset()
        adapter = WorkflowRestAdapter(cfg)
        result = adapter.deliver({}, 'abc123')
        self.assertFalse(result['ok'])
        self.assertFalse(result['retryable'],
                         'a URL that does not exist is not a transient fault')
