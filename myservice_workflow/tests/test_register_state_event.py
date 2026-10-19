"""`asset.register_state.changed` — handoff 62, in-registry.

The contract is `docs/integrations/INT-05b-register-state.md`. What is proved
here, where the outbox can be read row by row:

- a labelled unit Vendra sent raises SEVEN events through its seven gates, a
  `record_only` unit FIVE — one per act, for the state the act left;
- the payload is Vendra's table and nothing more: no person, `reason` on a
  query, a rejection and a return only, `sap_asset_code` on `registered` only;
- `state_since` strictly increases per unit, the same-second moves included;
- a unit Vendra did not send, and a unit received with the gates off, raise
  nothing; a move that rolls back takes its event with it;
- a target with no register-state endpoint queues nothing;
- the event goes to its own endpoint with the outbox's headers, and
  `asset.tag.affixed` is routed and called exactly as before.

The walk is `myservice_api`'s `GateCrew` — the one in-registry answer to
"how do you walk a unit" — imported as a module so its test classes are not
collected here a second time.

Run with:
    odoo -d test19 -u myservice_workflow --test-enable \\
         --test-tags /myservice_workflow:TestRegisterStateEvent \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import logging
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.myservice_api.tests import test_receipt_gates as gates
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_workflow.models.register_state_event import (
    EVENT_REGISTER_STATE)

#: Vendra report 56 §4 — every event carries these, and only these plus the
#: two conditional keys.
ALWAYS = {'event_id', 'asset_id', 'asset_code', 'grn_reference',
          'register_state', 'waiting_on', 'state_since'}

_logger = logging.getLogger(__name__)

ENDPOINT = '/api/method/vendra_network.api.cadra.register_state_event'


@tagged('post_install', '-at_install')
class TestRegisterStateEvent(gates.GateCrew, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_crew()   # switches the tenant's own targets off
        self.Log = self.env['workflow.dispatch.log']
        self.vendra = self.env['workflow.config'].create({
            'name': 'Vendra (62 test)', 'purpose': 'asset_events',
            'adapter_type': 'rest', 'rest_base_url': 'http://vendra.test',
            'rest_endpoint_event': '/api/method/vendra_network.api.cadra.'
                                   'tag_event',
            'rest_endpoint_register_state': ENDPOINT,
            'rest_auth_type': 'bearer', 'rest_api_key': 'k',
            'event_enabled': True})
        self.land = self.env['nrs.asset.category'].create(
            {'name': 'Land (62 test)', 'code': 'L62',
             'identification_mode': 'record_only', 'sap_asset_class': '6000'})

    # ── helpers ───────────────────────────────────────────────────────

    def _from_vendra(self, **vals):
        """A unit as INT-03 sends it: Vendra's source and receipt."""
        base = {'name': 'INT-03 probe', 'category_id': self.category.id,
                'serial_number': 'SN-62-%s' % uuid.uuid4().hex[:10],
                'make': 'Dell', 'model_name': 'Latitude 7430',
                'import_source': 'vendra', 'grn_reference': 'MAT-PRE-62',
                'register_state': 'captured'}
        base.update(vals)
        return self.env['nrs.asset'].sudo().create(base)

    def _plot(self):
        return self._from_vendra(
            category_id=self.land.id, serial_number=False, make=False,
            model_name=False,
            record_reference='PLOT-%s' % uuid.uuid4().hex[:8])

    def _events(self, asset):
        rows = self.Log.search([('event_type', '=', EVENT_REGISTER_STATE),
                                ('asset_id', '=', asset.id)], order='id')
        return rows, [json.loads(r.payload_sent) for r in rows]

    def _register_payload(self, asset, category):
        return {'sap_asset_code': 'SAP62%s' % uuid.uuid4().hex[:6].upper(),
                'cost': 5e6, 'cost_centre': 'NRS-HQ-62',
                'capitalisation_date': '2026-10-15',
                'asset_class': category.id}

    # ── seven gates, seven events ─────────────────────────────────────

    def test_a_labelled_unit_raises_one_event_per_act(self):
        a = self._to('registered', self._from_vendra())
        rows, bodies = self._events(a)
        self.assertEqual(
            [b['register_state'] for b in bodies],
            ['vfm_pending', 'vfm_verified', 'vfm_approved', 'tag_issued',
             'tagged', 'reg_submitted', 'registered'],
            'seven acts, seven events — `tag_requested` is passed through '
            'inside `request-tagging` and never sent')
        self.assertEqual(
            [b['waiting_on'] for b in bodies],
            ['iad', 'iad_approver', 'controller', 'tagging', 'maker',
             'checker', None])
        for body in bodies:
            extra = set(body) - ALWAYS
            self.assertTrue(ALWAYS <= set(body), body)
            self.assertEqual(
                extra, {'sap_asset_code'}
                if body['register_state'] == 'registered' else set(), body)
            self.assertEqual(body['asset_id'], a.id)
            self.assertEqual(body['asset_code'], a.asset_code)
            self.assertEqual(body['grn_reference'], 'MAT-PRE-62')
        self.assertEqual(bodies[-1]['sap_asset_code'], a.sap_asset_number)
        self.assertTrue(bodies[-1]['sap_asset_code'])
        # Every row is a queued INT-05 row: the same target, its own id.
        self.assertEqual(set(rows.mapped('config_id')), {self.vendra})
        self.assertEqual(set(rows.mapped('status')), {'pending'})
        self.assertEqual(len(set(rows.mapped('event_id'))), 7)
        for row, body in zip(rows, bodies):
            self.assertEqual(body['event_id'], row.event_id)

    def test_no_person_travels(self):
        a = self._to('registered', self._from_vendra())
        _rows, bodies = self._events(a)
        text = json.dumps(bodies)
        for person in (self.store, self.officer, self.approver,
                       self.controller, self.tagger, self.maker,
                       self.checker):
            for value in (person.name, person.login, person.email):
                self.assertNotIn(value, text)
        for body in bodies:
            for key in body:
                self.assertFalse(
                    any(w in key for w in ('user', 'actor', 'by', 'name',
                                           'email', 'person')),
                    'a key naming a person: %s' % key)

    def test_state_since_is_cadras_column_and_strictly_increases(self):
        a = self._to('registered', self._from_vendra())
        _rows, bodies = self._events(a)
        stamps = [b['state_since'] for b in bodies]
        self.assertEqual(stamps, sorted(set(stamps)),
                         'strictly increasing, no two equal')
        self.assertEqual(
            stamps[-1], fields.Datetime.to_string(
                a.register_state_since).replace(' ', 'T') + 'Z')

    def test_a_move_in_the_same_second_carries_a_later_value(self):
        a = self._from_vendra()
        ahead = fields.Datetime.now() + timedelta(seconds=30)
        a.sudo().write({'register_state_since': ahead})
        self._fire(a, self.store, 'submit')
        self.assertEqual(a.register_state_since, ahead + timedelta(seconds=1))
        # Inside one act: `request-tagging` moves twice in one call.
        a = self._to('vfm_approved', self._from_vendra())
        before = a.register_state_since
        self._fire(a, self.controller, 'request-tagging')
        moves = a._gate_events().filtered(
            lambda e: e.gate_action in ('request-tagging', 'issue-tag'))
        self.assertEqual(len(moves), 2)
        self.assertGreater(a.register_state_since, before)

    # ── record_only: five gates, five events, reg_ready among them ────

    def test_a_record_only_unit_raises_five_and_reg_ready(self):
        a = self._plot()
        self._fire(a, self.store, 'submit')
        self._fire(a, self.officer, 'verify', payload={
            'checklist': gates.CHECKLIST, 'attachments': gates.EVIDENCE})
        self._fire(a, self.approver, 'approve')
        self.assertEqual(a.register_state, 'reg_ready')
        self._fire(a, self.maker, 'register',
                   payload=self._register_payload(a, self.land))
        self._fire(a, self.checker, 'approve-registration')
        _rows, bodies = self._events(a)
        self.assertEqual(
            [(b['register_state'], b['waiting_on']) for b in bodies],
            [('vfm_pending', 'iad'), ('vfm_verified', 'iad_approver'),
             ('reg_ready', 'maker'), ('reg_submitted', 'checker'),
             ('registered', None)],
            '`vfm_approved` is passed through inside the approval and never '
            'sent; the skip lands the unit at `reg_ready`')
        self.assertNotIn('reason', bodies[2],
                         "the skip's sentence is the system's, not IAD's")

    # ── the words: query, reject, return ──────────────────────────────

    def test_a_query_carries_iads_question_and_resubmit_none(self):
        a = self._to('vfm_pending', self._from_vendra())
        self._fire(a, self.officer, 'query',
                   reason='  Which invoice covers this unit?  ')
        self._fire(a, self.store, 'resubmit', reason='Invoice INV-77.')
        _rows, bodies = self._events(a)
        query, resubmit = bodies[-2], bodies[-1]
        self.assertEqual(
            (query['register_state'], query['waiting_on'], query['reason']),
            ('vfm_query', 'store', 'Which invoice covers this unit?'))
        self.assertEqual((resubmit['register_state'], resubmit['waiting_on']),
                         ('captured', 'store'))
        self.assertNotIn('reason', resubmit)

    def test_a_rejection_carries_iads_reason(self):
        a = self._to('vfm_verified', self._from_vendra())
        self._fire(a, self.approver, 'reject',
                   reason='Not the model on the order.')
        _rows, bodies = self._events(a)
        self.assertEqual(bodies[-1], {
            'event_id': bodies[-1]['event_id'], 'asset_id': a.id,
            'asset_code': a.asset_code, 'grn_reference': 'MAT-PRE-62',
            'register_state': 'vfm_rejected', 'waiting_on': None,
            'state_since': bodies[-1]['state_since'],
            'reason': 'Not the model on the order.'})

    def test_a_return_carries_the_checkers_reason(self):
        a = self._to('reg_submitted', self._from_vendra())
        self._fire(a, self.checker, 'return-registration',
                   reason='Wrong cost centre.')
        _rows, bodies = self._events(a)
        self.assertEqual(
            (bodies[-1]['register_state'], bodies[-1]['waiting_on'],
             bodies[-1]['reason']), ('tagged', 'maker', 'Wrong cost centre.'))

    # ── when nothing is raised ────────────────────────────────────────

    def test_a_unit_vendra_did_not_send_raises_nothing(self):
        ours = self._to('registered', self._from_vendra(
            import_source='myservice'))
        no_receipt = self._to('registered', self._from_vendra(
            grn_reference='  '))
        for a in (ours, no_receipt):
            self.assertEqual(a.register_state, 'registered')
            self.assertFalse(self._events(a)[0])

    def test_gates_off_a_unit_received_and_affixed_raises_nothing(self):
        a = self.env['nrs.asset'].sudo().create({
            'name': 'Gates-off receipt', 'category_id': self.category.id,
            'serial_number': 'SN-62-OFF-%s' % uuid.uuid4().hex[:8],
            'import_source': 'vendra', 'grn_reference': 'MAT-PRE-62'})
        self.assertEqual(a.register_state, 'registered')
        label = a.active_tag_id
        self.assertTrue(label, 'gates off, a label is issued at creation')
        label.with_user(self.tagger).sudo()._mark_affixed(label.name)
        self.assertEqual(label.label_state, 'affixed')
        self.assertFalse(self._events(a)[0])
        affixed = self.Log.search([('event_type', '=', 'asset.tag.affixed'),
                                   ('asset_id', '=', a.id)])
        self.assertEqual(len(affixed), 1, 'INT-05 unchanged beside it')

    def test_a_move_that_rolls_back_takes_its_event(self):
        a = self._from_vendra()
        with self.assertRaises(RuntimeError):
            with self.env.cr.savepoint():
                self._fire(a, self.store, 'submit')
                self.assertEqual(len(self._events(a)[0]), 1)
                raise RuntimeError('the batch refused this unit')
        a.invalidate_recordset()
        self.assertEqual(a.register_state, 'captured')
        self.assertFalse(self._events(a)[0])

    def test_a_target_with_no_register_state_endpoint_queues_nothing(self):
        self.vendra.rest_endpoint_register_state = False
        a = self._to('vfm_pending', self._from_vendra())
        self.assertEqual(a.register_state, 'vfm_pending')
        self.assertFalse(self._events(a)[0])

    def test_no_target_queues_nothing(self):
        self.vendra.active = False
        a = self._to('vfm_pending', self._from_vendra())
        self.assertFalse(self._events(a)[0])

    def test_a_paused_target_still_queues(self):
        self.vendra.event_enabled = False
        a = self._to('vfm_pending', self._from_vendra())
        self.assertEqual(len(self._events(a)[0]), 1)

    # ── the wire ──────────────────────────────────────────────────────

    def _response(self, status=202, body=None):
        r = MagicMock()
        r.status_code = status
        r.text = json.dumps(body or {'message': {'status': 'accepted'}})
        r.json.return_value = body or {'message': {'status': 'accepted'}}
        return r

    def test_it_goes_to_its_own_endpoint_with_the_outbox_headers(self):
        a = self._to('vfm_pending', self._from_vendra())
        row = self._events(a)[0]
        with patch('requests.post', return_value=self._response()) as post:
            self.assertTrue(row._deliver_once())
        url = post.call_args.args[0]
        kw = post.call_args.kwargs
        self.assertEqual(url, 'http://vendra.test' + ENDPOINT)
        self.assertEqual(kw['json'], json.loads(row.payload_sent))
        self.assertNotIn('event', kw['json'],
                         'the body is the table; the endpoint names the event')
        self.assertEqual(kw['headers']['X-Idempotency-Key'], row.event_id)
        self.assertEqual(kw['headers']['X-Event-Id'], row.event_id)
        self.assertEqual(kw['headers']['X-Request-Id'], row.name)
        self.assertEqual(kw['headers']['Authorization'], 'Bearer k')
        self.assertEqual(row.status, 'sent')

    def test_tag_affixed_is_routed_and_called_exactly_as_before(self):
        a = self._to('tag_issued', self._from_vendra())
        a.active_tag_id.with_user(self.tagger).sudo()._mark_affixed(
            a.asset_code)
        tag_row = self.Log.search([('event_type', '=', 'asset.tag.affixed'),
                                   ('asset_id', '=', a.id)])
        self.assertEqual(len(tag_row), 1)
        self.assertEqual(json.loads(tag_row.payload_sent)['event'],
                         'asset.tag.affixed')
        calls = []

        class OldShape:
            """An adapter with the three-argument `deliver` every adapter
            had before 62: a tag event must still be callable on it."""

            def deliver(self, payload, event_id, request_ref=None):
                calls.append(payload['event'])
                return {'ok': True, 'retryable': False, 'status': 202,
                        'body': '', 'external_ref': None,
                        'acknowledged': False, 'error': None}

        with patch.object(type(self.vendra), '_get_adapter',
                          lambda cfg: OldShape()):
            self.assertTrue(tag_row._deliver_once())
        self.assertEqual(calls, ['asset.tag.affixed'])
        with patch('requests.post', return_value=self._response()) as post:
            tag_row._dispatch().write({'status': 'pending',
                                       'next_attempt_at': fields.Datetime.now()})
            tag_row._deliver_once()
        self.assertTrue(post.call_args.args[0].endswith(
            'vendra_network.api.cadra.tag_event'))

    def test_dead_letters_are_retried_together_keeping_their_ids(self):
        a = self._to('vfm_approved', self._from_vendra())
        rows = self._events(a)[0]
        with patch('requests.post',
                   return_value=self._response(400, {'error': 'no'})):
            for row in rows:
                row._deliver_once()
        self.assertEqual(set(rows.mapped('status')), {'dead'})
        ids = rows.mapped('event_id')
        rows.action_retry_now()
        self.assertEqual(set(rows.mapped('status')), {'pending'})
        self.assertEqual(rows.mapped('event_id'), ids)
        # The re-send's budget is the attempts made plus the TARGET's own —
        # 32 since handoff 63, ruling 8 (was 8).
        self.assertEqual(set(rows.mapped('max_attempts')),
                         {1 + self.vendra.retry_max_attempts})
        self.assertEqual(self.vendra.retry_max_attempts, 32)

    def test_a_dead_letter_says_the_state_stands(self):
        a = self._to('vfm_pending', self._from_vendra())
        row = self._events(a)[0]
        with patch('requests.post',
                   return_value=self._response(400, {'error': 'no'})):
            row._deliver_once()
        self.assertEqual(row.status, 'dead')
        note = a.message_ids.filtered(
            lambda m: 'Integration event not delivered' in (m.body or ''))
        self.assertTrue(note)
        self.assertIn('register state in Cadra is unaffected', note[0].body)
        self.assertNotIn('tag record', note[0].body)


@tagged('post_install', '-at_install')
class TestADayWithoutVendra(gates.GateCrew, CadraTransactionCase):
    """Report 62 §5: Vendra down for a day, measured against the real retry
    ladder — the real drain, the real backoff, the target's default policy —
    on a simulated clock. Since handoff 63 (ruling 8) the default is 32
    attempts, 60 s doubling to a 3,600 s cap: 26 h 3 min of trying, where
    report 62 measured the old 8 (2 h 3 min) dead-lettering a whole day.

    Seventy units a day (handoff 60) at seven events each is 490 events,
    raised evenly over a working day, 08:00–17:00 Lagos. Vendra is down
    from `down` to `up`; while it is down every attempt fails the way a
    stopped receiver fails (a refused connection: retryable). The drain
    runs every time anything is due, as `_trigger` makes it in production.
    Measured, not computed: the counts are the outbox's.
    """

    DAY_EVENTS = 490

    def setUp(self):
        super().setUp()
        self._setup_crew()
        self.Log = self.env['workflow.dispatch.log']
        self.vendra = self.env['workflow.config'].create({
            'name': 'Vendra (62 outage)', 'purpose': 'asset_events',
            'adapter_type': 'rest', 'rest_base_url': 'http://vendra.test',
            'rest_endpoint_event': '/tag', 'rest_endpoint_register_state': '/rs',
            'rest_auth_type': 'bearer', 'rest_api_key': 'k',
            'event_enabled': True})
        # Default policy, as every target is created (handoff 63).
        self.assertEqual((self.vendra.retry_max_attempts,
                          self.vendra.retry_base_seconds,
                          self.vendra.retry_cap_seconds), (32, 60, 3600))
        self.unit = self.env['nrs.asset'].sudo().create({
            'name': 'Outage probe', 'category_id': self.category.id,
            'serial_number': 'SN-62-OUT-%s' % uuid.uuid4().hex[:8],
            'make': 'Dell', 'model_name': 'Latitude 7430',
            'import_source': 'vendra', 'grn_reference': 'MAT-PRE-62-OUT',
            'register_state': 'captured'})

    #: 32 attempts: waits of 1, 2, 4, 8, 16 and 32 minutes, then 25 hours.
    BUDGET_SECONDS = 3780 + 25 * 3600

    def _run(self, start, down, up, horizon, events=None):
        """Raise the day's events from `start`, drain until `horizon`.
        Returns the rows and, per row id, the simulated instant it was
        raised (`create_date` is the database's own clock, not this one)."""
        events = events or self.DAY_EVENTS
        clock = [start]
        step = timedelta(hours=9) / events
        pending = [start + step * i for i in range(events)]
        raised = {}

        class Receiver:
            def deliver(self, payload, event_id, request_ref=None,
                        event_type=None):
                if down <= clock[0] < up:
                    return {'ok': False, 'retryable': True, 'status': None,
                            'body': '', 'external_ref': None,
                            'acknowledged': False,
                            'error': 'ConnectionError: [Errno 111] '
                                     'Connection refused'}
                return {'ok': True, 'retryable': False, 'status': 202,
                        'body': '', 'external_ref': None,
                        'acknowledged': False, 'error': None}

        rows = self.Log.browse()
        with patch.object(fields.Datetime, 'now',
                          staticmethod(lambda *a: clock[0])), \
                patch.object(type(self.vendra), '_get_adapter',
                             lambda cfg: Receiver()), \
                patch.object(type(self.Log), '_trigger_drain',
                             lambda *a, **k: True):
            while True:
                due = self.Log.search(
                    [('id', 'in', rows.ids),
                     ('status', 'in', ('pending', 'error')),
                     ('next_attempt_at', '!=', False)],
                    order='next_attempt_at', limit=1)
                nxt = pending[:1] + ([due.next_attempt_at] if due else [])
                if not nxt or min(nxt) > horizon:
                    break
                clock[0] = min(nxt)
                while pending and pending[0] <= clock[0]:
                    pending.pop(0)
                    row = self.unit._queue_register_state_event('submit')
                    raised[row.id] = clock[0]
                    rows |= row
                self.Log._cron_drain_outbound_events(limit=500)
        return rows, raised

    def _utc(self, day, hhmm):
        # Lagos is UTC+1, all year.
        h, m = hhmm
        return fields.Datetime.to_datetime('2026-10-%02d 00:00:00' % day) + \
            timedelta(hours=h - 1, minutes=m)

    def test_down_for_the_whole_working_day(self):
        """Down 07:00 Lagos to 07:00 the next day: the whole day's events
        are raised while it is down, the first of them 23 hours before it
        returns. Report 62 measured every one dead-lettered under the old
        eight attempts; under 32 none is — every one arrives, the latest
        within the hour cap of Vendra's return."""
        down, up = self._utc(16, (7, 0)), self._utc(17, (7, 0))
        rows, raised = self._run(start=self._utc(16, (8, 0)), down=down,
                                 up=up, horizon=self._utc(18, (12, 0)))
        statuses = {s: len(rows.filtered(lambda r: r.status == s))
                    for s in set(rows.mapped('status'))}
        delays = [(r.sent_at - up).total_seconds() for r in rows]
        _logger.info('63 ruling 8, down 07:00-07:00: %s of %d, latest %d s '
                     'after Vendra returned', statuses, len(rows),
                     max(delays))
        self.assertEqual(len(rows), self.DAY_EVENTS)
        self.assertEqual(statuses, {'sent': self.DAY_EVENTS})
        self.assertTrue(all(0 <= d <= 3600 for d in delays))

    def test_down_longer_than_the_budget(self):
        """Down for two days: every event raised on the first day is
        dead-lettered after exactly 32 attempts spanning 26 h 3 min — the
        budget ends, it does not stretch. (49 events, not 490: the ladder
        is per event, and the span is the claim.)"""
        rows, raised = self._run(start=self._utc(16, (8, 0)),
                                 down=self._utc(16, (7, 0)),
                                 up=self._utc(18, (12, 0)),
                                 horizon=self._utc(18, (12, 0)), events=49)
        self.assertEqual(set(rows.mapped('status')), {'dead'})
        self.assertEqual(set(rows.mapped('attempts')), {32})
        spans = {(r.last_attempt_at - raised[r.id]).total_seconds()
                 for r in rows}
        self.assertEqual(spans, {float(self.BUDGET_SECONDS)},
                         '32 attempts span 26 h 3 min: waits of 1, 2, 4, 8, '
                         '16 and 32 minutes, then 25 of an hour')

    def test_back_at_noon(self):
        """Down overnight, back at 12:00 Lagos; the morning's events raised
        while it was down. Under the old eight attempts (report 62) the
        events raised more than 2 h 3 min before noon died; under 32 none
        does: raised before noon, delivered within the hour cap of it;
        raised after, on time."""
        up = self._utc(17, (12, 0))
        rows, raised = self._run(start=self._utc(17, (8, 0)),
                                 down=self._utc(16, (17, 0)), up=up,
                                 horizon=self._utc(18, (12, 0)))
        dead = rows.filtered(lambda r: r.status == 'dead')
        late = rows.filtered(lambda r: r.status == 'sent'
                             and raised[r.id] < up)
        on_time = rows.filtered(lambda r: r.status == 'sent'
                                and raised[r.id] >= up)
        delays = [(r.sent_at - up).total_seconds() for r in late]
        _logger.info('63 ruling 8, back at noon: %d dead, %d late (latest %d '
                     's after noon), %d on time, of %d', len(dead), len(late),
                     max(delays or [0]), len(on_time), len(rows))
        self.assertFalse(dead)
        self.assertEqual(len(late) + len(on_time), self.DAY_EVENTS)
        self.assertTrue(late)
        self.assertLessEqual(max(delays), 3600)
