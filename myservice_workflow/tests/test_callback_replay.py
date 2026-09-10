"""A callback that arrives twice is one decision, not two.

Handoff 18 item A. `/myservice/workflow/callback` and its `/api/v1` twin both
acted on the CALL rather than on the transition: a second byte-identical POST
answered `200 {"ok": true}` and did all three effects again —

  1. another `workflow.dispatch.log` row (the first callback had rewritten the
     `sent` row the replay was looking for, so the replay created a new one);
  2. another chatter post;
  3. another write of the configured `approved_stage_id` — **and this is the
     damaging one.** Where an approved stage is configured the stage was
     written unconditionally, so a replay arriving after a human had moved the
     request onward DRAGGED IT BACK. `request.request.write` then logged a
     `stage_changed` event and reset `date_moved` for a stage that had not
     changed: a double-count inside the request's own audit trail.

Handoff 06 settled the shape in the other direction — one physical act is one
event, and `_mark_affixed` fires on the TRANSITION. This is the same rule
pointed inbound, and these tests are what hold it there.

**Why not `workspace_ref`.** It is the natural dedup key and it is optional in
both published contracts. Measured across all eight local tenants before this
was written: `request.request.workspace_ref` is set on 0 of 407 requests, and
all 76 request-approval log rows carrying one carry the same pytest fixture
constant. `workflow_status` is written by every path that applies an outcome,
so that is what the dedup stands on.

Needs `--workers=0`: `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the committed `workers = 2` every test in the class errors
in setUpClass and the run reports "0 failed".

Run with:
    odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_workflow \\
         --stop-after-init --test-enable --test-tags /myservice_workflow \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import uuid

from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

CALLBACK_URL = "/myservice/workflow/callback"
TOKEN = "h18-callback-replay-secret"
LOGGER = "odoo.addons.myservice_workflow.controllers.callback"


class WorkflowCallbackFixture:
    """One tenant wired to a WorkSpace, one request, two stages."""

    def _stand_up_config(self, **overrides):
        Config = self.env["workflow.config"]
        # `get_active_config()` searches `active=True, purpose=workspace`
        # with `limit=1` and no explicit order, so an existing row on the
        # tenant would win over ours. Stand ours up alone.
        Config.search([("purpose", "=", "workspace"),
                       ("active", "=", True)]).write({"active": False})
        vals = {
            "name": "handoff 18 replay probe",
            "purpose": "workspace",
            "adapter_type": "stub",
            "callback_enabled": True,
            "callback_token": TOKEN,
        }
        vals.update(overrides)
        return Config.create(vals)

    def _stages(self):
        Stage = self.env["request.stage"]
        suffix = uuid.uuid4().hex[:6]
        return (
            Stage.create({"name": "H18 Open %s" % suffix, "sequence": 10}),
            Stage.create({"name": "H18 Approved %s" % suffix, "sequence": 20}),
            Stage.create({"name": "H18 Onward %s" % suffix, "sequence": 30}),
        )

    def _make_request(self, stage=None):
        # An explicit unique reference: the controller resolves the request by
        # `name`, and a sequence-generated one shared with another row would
        # make the lookup the thing under test.
        return self.env["request.request"].create({
            "name": "H18-CB-%s" % uuid.uuid4().hex[:8],
            "stage_id": stage.id if stage else False,
        })

    # ── what "wrote nothing" means, measured ─────────────────────────────

    def _settle(self):
        """Flush, and RUN THE PRECOMMIT CALLBACKS.

        `flush_all()` is not enough and the first run of these tests proved
        it. `stage_id` is `tracking=True`, and `mail.thread` materialises a
        tracking message from a precommit callback rather than at flush — so
        a manual stage move made inside the test posted its message LATER,
        during the next callback's request, and the footprint taken straight
        after the move under-counted by one. The assertion then read as "the
        replay posted a message" when what happened was that the test's own
        earlier write finally landed.

        This is `mail`'s own `flush_tracking()` helper, inlined because this
        class does not inherit `MailCommon`. Handoff 09's discipline, one
        mechanism further on: a value is not settled until it has been
        WRITTEN, and a stored compute and a tracking message settle at
        different moments.
        """
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _footprint(self, req):
        """Every trace an applied callback leaves, in one comparable dict.

        A replay assertion that checks only the status would pass on code
        that reposts chatter and appends a log row on every duplicate — which
        is most of what the defect actually was. So the whole footprint is
        captured, and the test compares the whole thing.
        """
        self._settle()
        self.env.invalidate_all()
        return {
            "workflow_status": req.workflow_status,
            "stage_id": req.stage_id.id,
            "date_moved": req.date_moved,
            "dispatch_rows": self.env["workflow.dispatch.log"].sudo()
                             .search_count([("request_id", "=", req.id)]),
            "events": self.env["request.event"].sudo()
                      .search_count([("request_id", "=", req.id)]),
            "messages": self.env["mail.message"].sudo().search_count([
                ("model", "=", "request.request"), ("res_id", "=", req.id)]),
        }


@tagged("post_install", "-at_install")
class TestCallbackReplayHttp(HttpCase, WorkflowCallbackFixture):
    """The published route, over real HTTP, twice."""

    def setUp(self):
        super().setUp()
        self.open_stage, self.approved_stage, self.onward_stage = self._stages()
        self.config = self._stand_up_config(
            approved_stage_id=self.approved_stage.id)
        self.req = self._make_request(self.open_stage)
        self._settle()

    def _post(self, outcome="approved", workspace_ref="WF-H18-0001",
              comment="handoff 18 replay probe"):
        return self._post_with(outcome=outcome, workspace_ref=workspace_ref,
                               comment=comment)

    def _post_with(self, outcome="approved", workspace_ref="WF-H18-0001",
                   comment="handoff 18 replay probe", payment_ref=None):
        """The same POST, with the optional fields spellable.

        Both are `nullable` in the published schema, so a caller sending the
        outcome first and a reference later is within contract — which is
        exactly the case the replay check has to be honest about.
        """
        payload = {
            "reference": self.req.name,
            "workspace_ref": workspace_ref,
            "outcome": outcome,
        }
        if comment is not None:
            payload["comment"] = comment
        if payment_ref is not None:
            payload["payment_ref"] = payment_ref
        return self.url_open(
            CALLBACK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json",
                     "X-Callback-Token": TOKEN},
        )

    # ── the acceptance criterion, whole ──────────────────────────────────

    def test_a_byte_identical_replay_writes_nothing_and_answers_success(self):
        first = self._post()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["replayed"])

        after_first = self._footprint(self.req)
        self.assertEqual(after_first["workflow_status"], "approved")
        self.assertEqual(after_first["stage_id"], self.approved_stage.id,
                         "the configured approved stage must be applied once")

        second = self._post()

        self.assertEqual(second.status_code, 200, second.text)
        body = second.json()
        self.assertTrue(body["ok"], "a replay of a request we honoured is a "
                                    "success, not a failure")
        self.assertTrue(body["replayed"])
        self.assertEqual(self._footprint(self.req), after_first,
                         "a replay wrote something: no dispatch row, no "
                         "chatter post, no stage write, no date_moved and no "
                         "request.event row may change")

    def test_a_replay_does_not_drag_a_request_back_from_where_a_human_moved_it(self):
        """The damaging effect, isolated.

        This is the case the fix exists for and the one an operator would
        actually meet: approve, someone moves the request onward, WorkSpace
        redelivers. The old code wrote `approved_stage_id` unconditionally,
        so the replay undid a human's work and logged a `stage_changed`
        event saying the request had moved when it had been moved BACK.
        """
        self.assertEqual(self._post().status_code, 200)
        self.req.write({"stage_id": self.onward_stage.id})
        moved_on = self._footprint(self.req)

        response = self._post()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._footprint(self.req), moved_on)
        self.env.invalidate_all()
        self.assertEqual(
            self.req.stage_id, self.onward_stage,
            "the replay dragged the request back to the approved stage")

    def test_a_replay_is_reported_at_info_naming_the_request_and_the_outcome(self):
        self.assertEqual(self._post().status_code, 200)

        with self.assertLogs(LOGGER, level="INFO") as captured:
            self._post()

        line = "\n".join(captured.output)
        self.assertIn("replay ignored", line)
        self.assertIn(self.req.name, line)

    # ── a replay writes nothing, and says what it therefore discarded ────

    def test_a_repeat_carrying_a_late_payment_ref_is_not_swallowed_in_silence(self):
        """The hole a verification pass found in the first version.

        The disposition compares `workflow_status` and nothing else, so a
        SECOND `approved` carrying a `payment_ref` the first did not have was
        discarded and answered `200` — and `payment_ref` is optional in both
        published schemas, so a workflow engine that sends the approval when
        it is granted and the payment reference when it clears is doing
        nothing wrong. Rule 3: silent degradation is a defect even at 200.

        It still writes nothing. What changed is that it no longer does so
        quietly.
        """
        self.assertEqual(self._post(outcome="approved").status_code, 200)
        after_first = self._footprint(self.req)
        self.env.invalidate_all()
        self.assertFalse(self.req.workflow_payment_ref)

        with self.assertLogs(LOGGER, level="WARNING") as captured:
            response = self._post_with(outcome="approved",
                                       payment_ref="PAY-2026-04412")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["replayed"])
        self.assertIn("payment_ref", body["discarded_fields"])
        self.assertEqual(self._footprint(self.req), after_first,
                         "a replay must still write nothing")

        line = "\n".join(captured.output)
        self.assertIn("payment_ref", line)
        self.assertIn("discarded", line)

    def test_a_repeat_carrying_nothing_new_does_not_cry_wolf(self):
        """The other half, and the one the first version got wrong.

        An ordinary redelivery carries the SAME comment, and the first
        version flagged a comment whenever one was supplied — so the common
        case warned and `test_a_replay_is_reported_at_info…` failed on the
        run meant to prove the feature. A guard that fires on every
        redelivery is a guard somebody turns off. The comparison is now
        against `workflow.dispatch.log.workflow_comment`, which holds the
        text verbatim, rather than against the chatter body, which wraps it
        in markup.
        """
        self.assertEqual(self._post(comment="same words").status_code, 200)

        response = self._post(comment="same words")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["replayed"])
        self.assertNotIn("discarded_fields", body,
                         "an identical redelivery reported a discard")

        # and the no-comment case, which is the same claim one field fewer
        no_comment = self._post_with(outcome="approved", comment=None)
        self.assertNotIn("discarded_fields", no_comment.json())

    def test_a_second_query_carrying_a_new_question_says_the_question_was_dropped(self):
        """`queried` → `queried` is a replay, which means a genuinely NEW
        question is discarded — the comment text is the only thing that
        distinguishes a new question from a redelivery of the old one. That
        is a consequence of the rule the handoff asked for, and it is
        reported rather than hidden. Report 18 raises it for a ruling."""
        self.assertEqual(self._post(outcome="queried",
                                    comment="which cost centre?").status_code,
                         200)
        queried = self._footprint(self.req)

        response = self._post(outcome="queried", comment="and which vendor?")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("comment", response.json()["discarded_fields"])
        self.assertEqual(self._footprint(self.req), queried)

    # ── a replay that would CHANGE the outcome is a different animal ─────

    def test_a_contradicting_outcome_is_refused_with_409_and_changes_nothing(self):
        """Refused, not absorbed, and the report says why.

        Applying it would overwrite a recorded decision on the say-so of a
        message that may be a stale redelivery arriving out of order — and
        nothing in the payload can tell a genuine reversal from one. The
        refusal names both outcomes so the caller knows exactly what we
        hold; a real reversal is a human decision and now needs one.
        """
        self.assertEqual(self._post(outcome="approved").status_code, 200)
        approved = self._footprint(self.req)

        response = self._post(outcome="rejected")

        self.assertEqual(response.status_code, 409, response.text)
        body = response.json()
        self.assertEqual(body["current_outcome"], "approved")
        self.assertEqual(body["attempted_outcome"], "rejected")
        self.assertEqual(self._footprint(self.req), approved,
                         "a refused callback must not have written anything")

    def test_a_contradiction_is_logged_at_error_because_somebody_has_to_look(self):
        self.assertEqual(self._post(outcome="approved").status_code, 200)

        with self.assertLogs(LOGGER, level="ERROR") as captured:
            self._post(outcome="rejected")

        line = "\n".join(captured.output)
        self.assertIn("CONFLICT", line)
        self.assertIn(self.req.name, line)
        self.assertIn("approved", line)
        self.assertIn("rejected", line)

    def test_queried_after_a_decision_is_a_contradiction_too(self):
        """`queried` is the mildest case and gets the same treatment.

        It writes no stage, so the damage is smaller — but it moves
        `workflow_status` off `approved`, which erases the recorded decision
        just as completely. Same rule, same refusal.
        """
        self.assertEqual(self._post(outcome="approved").status_code, 200)
        approved = self._footprint(self.req)

        response = self._post(outcome="queried", comment="one more thing")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self._footprint(self.req), approved)

    def test_a_replayed_query_writes_nothing_either(self):
        self.assertEqual(self._post(outcome="queried",
                                    comment="please clarify").status_code, 200)
        queried = self._footprint(self.req)
        self.assertEqual(queried["workflow_status"], "queried")

        response = self._post(outcome="queried", comment="please clarify")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["replayed"])
        self.assertEqual(self._footprint(self.req), queried)

    # ── and the progressions that must keep working ──────────────────────

    def test_a_decision_after_a_query_is_a_progression_and_applies(self):
        """`queried` is not a decision, so a decision after one is not a
        contradiction. A dedup that swallowed this would be worse than the
        defect it replaced — WorkSpace asks a question, gets an answer,
        approves, and Cadra never records the approval."""
        self.assertEqual(self._post(outcome="queried",
                                    comment="clarify please").status_code, 200)

        response = self._post(outcome="approved")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["replayed"])
        self.env.invalidate_all()
        self.assertEqual(self.req.workflow_status, "approved")
        self.assertEqual(self.req.stage_id, self.approved_stage)

    def test_a_re_sent_request_can_be_decided_again(self):
        """Replay suppression bites only where nothing new was asked.

        `_send_to_workflow` sets `workflow_status` back to `pending`, so a
        second dispatch is a second question and its answer is a second
        transition. Without this the fix would turn one approval per request
        into one approval per lifetime.
        """
        self.assertEqual(self._post(outcome="approved").status_code, 200)

        self.req.write({"workflow_status": "pending"})   # what a re-send does
        before = self._footprint(self.req)

        response = self._post(outcome="rejected")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["replayed"])
        after = self._footprint(self.req)
        self.assertEqual(after["workflow_status"], "rejected")
        self.assertGreater(after["messages"], before["messages"],
                           "a genuine second decision must still be recorded")


@tagged("post_install", "-at_install")
class TestCallbackDisposition(TransactionCase, WorkflowCallbackFixture):
    """The decision itself, and the log row both controllers now share.

    These are ORM tests rather than HTTP ones on purpose: `/api/v1`'s twin
    needs a JWT and a scope to reach over HTTP, and what has to be identical
    between the two routes is the MODEL METHOD each of them calls. Testing
    that directly is the only way to assert the twins agree without standing
    up two clients.
    """

    def setUp(self):
        super().setUp()
        self.config = self._stand_up_config()
        self.req = self._make_request()

    def test_the_disposition_table(self):
        Req = self.req
        cases = [
            ("not_sent", "approved", Req.CALLBACK_APPLY),
            ("not_sent", "queried", Req.CALLBACK_APPLY),
            ("pending", "approved", Req.CALLBACK_APPLY),
            ("pending", "rejected", Req.CALLBACK_APPLY),
            ("pending", "queried", Req.CALLBACK_APPLY),
            ("queried", "approved", Req.CALLBACK_APPLY),
            ("queried", "rejected", Req.CALLBACK_APPLY),
            ("queried", "queried", Req.CALLBACK_REPLAY),
            ("approved", "approved", Req.CALLBACK_REPLAY),
            ("rejected", "rejected", Req.CALLBACK_REPLAY),
            ("approved", "rejected", Req.CALLBACK_CONFLICT),
            ("rejected", "approved", Req.CALLBACK_CONFLICT),
            ("approved", "queried", Req.CALLBACK_CONFLICT),
            ("rejected", "queried", Req.CALLBACK_CONFLICT),
        ]
        for current, outcome, expected in cases:
            self.req.workflow_status = current
            self.assertEqual(
                self.req._workflow_callback_disposition(outcome), expected,
                "%s + %s should be %s" % (current, outcome, expected))

    # ── B1: the v1 twin never reconciled the outbound dispatch ───────────

    def test_a_callback_reconciles_the_outbound_dispatch_it_answers(self):
        """The legacy behaviour, now shared, and it is the right one.

        The `/api/v1` twin always appended a fresh inbound row and never
        touched the dispatch it was answering, so on a tenant using v1 an
        answered dispatch read `sent` for ever and "which dispatches are
        still unanswered" could not be asked. There is no outbound
        request-approval row on any of the eight local tenants today —
        `_send_to_workflow` has never run on any of them — so this was
        latent, not live. It stops being latent the first time a tenant
        sends one.
        """
        Log = self.env["workflow.dispatch.log"].sudo()
        sent = Log.create({
            "request_id": self.req.id,
            "direction": "outbound",
            "status": "sent",
            "workspace_ref": "WF-OUT-1",
        })

        reconciled = Log._reconcile_callback(
            self.req, "approved", "WF-OUT-1", {"outcome": "approved"})

        self.assertEqual(reconciled, sent,
                         "the callback must answer the dispatch it is a "
                         "reply to, not append a row beside it")
        self.assertEqual(
            Log.search_count([("request_id", "=", self.req.id)]), 1)

    def test_with_no_outbound_dispatch_an_inbound_row_is_appended(self):
        Log = self.env["workflow.dispatch.log"].sudo()

        row = Log._reconcile_callback(
            self.req, "queried", "WF-IN-1", {"outcome": "queried"})

        self.assertEqual(row.direction, "inbound")
        self.assertEqual(row.status, "queried")
        self.assertEqual(row.workspace_ref, "WF-IN-1")
        self.assertEqual(json.loads(row.response_received),
                         {"outcome": "queried"})

    def test_an_asset_event_is_never_mistaken_for_an_approval_dispatch(self):
        """Asset lifecycle events (INT-05) live in this table and also pass
        through `sent`. One of those is not an answer to an approval request
        and must never be rewritten by a callback about one — handoff 06's
        ruling that the drain is scoped by `event_type` and not by status,
        applied to the reader on the other side."""
        Log = self.env["workflow.dispatch.log"].sudo()
        event = Log.with_context(cadra_event_dispatch=True).create({
            "request_id": self.req.id,
            "direction": "outbound",
            "status": "sent",
            "event_type": "asset.tag.affixed",
            "event_id": uuid.uuid4().hex,
        })

        row = Log._reconcile_callback(
            self.req, "approved", "WF-X", {"outcome": "approved"})

        self.assertNotEqual(row, event)
        self.assertEqual(row.direction, "inbound")
        self.assertEqual(event.status, "sent",
                         "an asset event was rewritten by a request callback")

    # ── the stage write is a transition too ──────────────────────────────

    def test_writing_the_stage_a_request_already_holds_is_not_a_move(self):
        stage = self.env["request.stage"].create({"name": "H18 Same"})
        self.req.write({"stage_id": stage.id})
        before = self._footprint(self.req)

        self.req._set_workflow_stage(stage)

        self.assertEqual(self._footprint(self.req), before)
