"""A stage change is a stage CHANGING, not the word appearing in `vals`.

Handoff 18 item A, third effect. `request.request.write` branched on
`'stage_id' in vals`, so writing a request's current stage back over itself:

  - reset `date_moved` to now, and
  - appended a `stage_changed` row to `request.event`

— saying a move had happened when none had. `request.event` is the request's
own audit trail and the `/api/v1` serialiser publishes it, so this is not a
cosmetic count: it is a fabricated entry in the record an auditor reads.

The WorkSpace callback is how it was found — it wrote the configured approved
stage unconditionally on every replay, so a duplicate POST double-counted.
But the callback is only the caller that made it visible. Any caller writing
an unchanged stage has been fabricating events here for as long as this method
has existed, and the callback's own guard would leave every other one alone.

There were no tests in this module at all before this file. `-u
myservice_request_core` in CI's Odoo step is what runs it.
"""
import uuid

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStageWriteIsATransition(TransactionCase):

    def setUp(self):
        super().setUp()
        Stage = self.env["request.stage"]
        suffix = uuid.uuid4().hex[:6]
        self.first = Stage.create({"name": "H18 First %s" % suffix,
                                   "sequence": 10})
        self.second = Stage.create({"name": "H18 Second %s" % suffix,
                                    "sequence": 20})
        self.closing = Stage.create({"name": "H18 Closed %s" % suffix,
                                     "sequence": 30, "closed": True})
        self.req = self.env["request.request"].create({
            "name": "H18-SW-%s" % uuid.uuid4().hex[:8],
            "stage_id": self.first.id,
        })
        self.env.flush_all()
        # Without this every assertion below counts zero and passes for the
        # wrong reason: `_log_event` writes `event_type_id = etype.id or
        # False`, so on a tenant missing the seed row the filter matches
        # nothing whatever the code does.
        self.assertTrue(
            self.env["request.event.type"].search(
                [("code", "=", "stage_changed")], limit=1),
            "the stage_changed event type is missing — every count below "
            "would be zero and every assertion here vacuous")

    def _events(self, req=None):
        return self.env["request.event"].search_count(
            [("request_id", "=", (req or self.req).id),
             ("event_type_id.code", "=", "stage_changed")])

    # ── the defect ───────────────────────────────────────────────────────

    def test_writing_the_same_stage_logs_no_event_and_does_not_move_the_clock(self):
        events = self._events()
        moved = self.req.date_moved

        self.req.write({"stage_id": self.first.id})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertEqual(self._events(), events,
                         "a stage_changed event was logged for a stage that "
                         "did not change")
        self.assertEqual(self.req.date_moved, moved,
                         "date_moved was reset by a write that moved nothing")

    def test_a_real_move_still_logs_one_event_and_sets_date_moved(self):
        """The half that matters most: a guard that suppressed everything
        would pass the test above and silently stop recording stage moves
        altogether."""
        events = self._events()

        self.req.write({"stage_id": self.second.id})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertEqual(self._events(), events + 1)
        self.assertTrue(self.req.date_moved)
        self.assertEqual(self.req.stage_id, self.second)

    def test_moving_into_a_closing_stage_still_stamps_date_closed(self):
        self.req.write({"stage_id": self.closing.id})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertTrue(self.req.date_closed)

    def test_re_writing_a_closing_stage_does_not_restamp_date_closed(self):
        self.req.write({"stage_id": self.closing.id})
        self.env.flush_all()
        self.req.invalidate_recordset()
        closed_at = self.req.date_closed
        events = self._events()

        self.req.write({"stage_id": self.closing.id})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertEqual(self.req.date_closed, closed_at)
        self.assertEqual(self._events(), events)

    # ── the batch case, which is why `moved` is a recordset ──────────────

    def test_in_a_batch_write_only_the_records_that_moved_are_recorded(self):
        """The reason the moved subset is computed before `super()`.

        Afterwards every record compares equal to the new stage and there is
        nothing left to tell them apart — and merging `date_moved` into
        `vals`, which is what the old code did, would stamp it on the record
        that did not move as well as the one that did.
        """
        stayer = self.req
        mover = self.env["request.request"].create({
            "name": "H18-SW-%s" % uuid.uuid4().hex[:8],
            "stage_id": self.second.id,
        })
        self.env.flush_all()
        stayer_moved_at = stayer.date_moved
        stayer_events = self._events(stayer)
        mover_events = self._events(mover)

        (stayer | mover).write({"stage_id": self.first.id})
        self.env.flush_all()
        (stayer | mover).invalidate_recordset()

        self.assertEqual(self._events(stayer), stayer_events,
                         "the record that was already in this stage was "
                         "logged as having moved")
        self.assertEqual(stayer.date_moved, stayer_moved_at,
                         "the record that did not move had its date_moved "
                         "reset by the one that did")
        self.assertEqual(self._events(mover), mover_events + 1)
        self.assertTrue(mover.date_moved)

    # ── the edges ────────────────────────────────────────────────────────

    def test_clearing_the_stage_is_a_move(self):
        events = self._events()

        self.req.write({"stage_id": False})
        self.env.flush_all()

        self.assertEqual(self._events(), events + 1)

    def test_an_explicit_date_moved_in_vals_is_still_honoured(self):
        """`setdefault` semantics preserved: a caller that supplies its own
        `date_moved` — a migration replaying history, say — keeps it."""
        stamp = "2020-01-01 00:00:00"

        self.req.write({"stage_id": self.second.id, "date_moved": stamp})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertEqual(str(self.req.date_moved), stamp)

    def test_a_write_that_touches_no_stage_records_nothing(self):
        events = self._events()
        moved = self.req.date_moved

        self.req.write({"priority": "3"})
        self.env.flush_all()
        self.req.invalidate_recordset()

        self.assertEqual(self._events(), events)
        self.assertEqual(self.req.date_moved, moved)
