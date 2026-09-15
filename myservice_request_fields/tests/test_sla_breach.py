"""`sla_breached` changes because time passed, not because a field was written.

`sla_breached` is a stored compute whose body reads the clock and whose
`@api.depends` names only `sla_deadline`. Nothing in the database changes on
the minute a request runs out of time, so the ORM has no reason to re-run the
compute and the stored value keeps whatever it was when the record was last
written — false, for every request created inside its own SLA window, which is
every request. On `jaizbankplc` that was 215 of 215 requests past their
deadline and the field true on none of them, backing a live "SLA Breached"
menu, a search filter, a list decoration and a kanban badge.

These tests move the CLOCK rather than the inputs, because moving the inputs
proves the compute works and says nothing about whether it is ever re-run. The
"still false after the clock moved" assertion is deliberately an assertion
about the bug: it is what stops someone deleting the cron on the strength of
the `@api.depends` line.

Run with:
    odoo -d <db> -u myservice_request_fields --test-enable \\
         --test-tags /myservice_request_fields --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
from datetime import timedelta

from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestSlaBreachRefresh(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Request = self.env["request.request"]

    def _request(self, **vals):
        base = {"name": "New", "sla_tier": "low"}  # low == a 24-hour deadline
        base.update(vals)
        rec = self.Request.create(base)
        # Flush before returning, under the caller's clock. This is not
        # incidental: a stored compute is not stale until it has actually been
        # WRITTEN. Left pending in `env.transaction.tocompute`, it is computed
        # on the first access or on the flush that `search()` performs — which,
        # inside a later `freeze_time`, happens under the NEW clock and quietly
        # produces the right answer for the wrong reason. Materialising the
        # column here is what makes the row behave like one written days ago,
        # which is the only thing these tests are about.
        rec.flush_recordset()
        return rec

    def _stored(self, rec):
        """Read the column, not the ORM cache.

        Reading `rec.sla_breached` after the cron would return the right answer
        even if the flush never happened, because a field marked to recompute
        is computed on access. Only the column proves the cron wrote anything.
        """
        rec.flush_recordset()
        self.env.cr.execute(
            "SELECT sla_breached FROM request_request WHERE id = %s", (rec.id,))
        return self.env.cr.fetchone()[0]

    # ── the regression this file exists for ──────────────────────────────────

    def test_a_request_breaches_when_the_clock_passes_its_deadline(self):
        rec = self._request()
        deadline = rec.sla_deadline
        self.assertTrue(deadline, "a tiered request must get a deadline")
        self.assertFalse(rec.sla_breached, "a fresh request is inside its SLA")
        self.assertFalse(self._stored(rec))

        with freeze_time(deadline + timedelta(minutes=1)):
            # Nothing has been written to the record; only the clock moved.
            rec.invalidate_recordset(["sla_breached"])
            self.assertFalse(
                rec.sla_breached,
                "THE BUG: the stored value does not move on its own. If this "
                "ever starts failing, the ORM has gained a way to recompute a "
                "clock-driven field and the cron below may be reconsidered — "
                "until then it is the only thing that flips this field.")
            self.assertFalse(self._stored(rec))

            self.Request._cron_refresh_sla_breached()

            self.assertTrue(rec.sla_breached, "the cron must flip the field")
            self.assertTrue(self._stored(rec), "and must write the column")

        self.assertEqual(rec.sla_deadline, deadline,
                         "the input must be untouched — the clock did this")

    def test_the_refresh_writes_no_message_and_fires_no_stage_hook(self):
        """The recompute flush bypasses `write()`.

        Stored computes reach the database through `_flush` -> `_write_multi`,
        not through `BaseModel.write`, so none of the `request.request` write
        overrides run: no mail tracking, no `request.event` row, no workflow
        auto-trigger. At 303 rows across the estate flipping on the first tick
        that is the difference between a silent correction and 303 chatter
        messages on three tenants.
        """
        rec = self._request()
        deadline = rec.sla_deadline
        messages = self.env["mail.message"].search_count(
            [("model", "=", "request.request"), ("res_id", "=", rec.id)])
        events = self.env["request.event"].search_count(
            [("request_id", "=", rec.id)])

        with freeze_time(deadline + timedelta(minutes=1)):
            self.Request._cron_refresh_sla_breached()
            self.assertTrue(rec.sla_breached)

        self.assertEqual(
            self.env["mail.message"].search_count(
                [("model", "=", "request.request"), ("res_id", "=", rec.id)]),
            messages, "the refresh must not post to the chatter")
        self.assertEqual(
            self.env["request.event"].search_count(
                [("request_id", "=", rec.id)]),
            events, "the refresh must not log a request event")
        if "workflow_status" in rec._fields:
            # myservice_workflow is not a dependency of this module, but where
            # it is installed its stage hook must stay asleep.
            self.assertEqual(rec.workflow_status, "not_sent",
                             "the refresh must not trip the workflow trigger")

    # ── the edges ────────────────────────────────────────────────────────────

    def test_a_request_with_no_deadline_is_never_flagged(self):
        """No tier means no deadline means no promise to breach. A cron that
        flagged these would invent breaches of an SLA nobody agreed to."""
        rec = self._request(sla_tier=False)
        self.assertFalse(rec.sla_deadline)
        self.assertFalse(rec.sla_breached)

        with freeze_time("2099-01-01 00:00:00"):
            self.Request._cron_refresh_sla_breached()

        self.assertFalse(rec.sla_breached)
        self.assertFalse(self._stored(rec))

    def test_a_second_run_changes_nothing(self):
        """The domain excludes rows already flagged, so the steady-state cost
        is the requests still inside their window — not the whole history."""
        rec = self._request()

        with freeze_time(rec.sla_deadline + timedelta(minutes=1)):
            first = self.Request._cron_refresh_sla_breached()
            self.assertGreaterEqual(first, 1)
            self.assertTrue(rec.sla_breached)

            second = self.Request._cron_refresh_sla_breached()
            self.assertEqual(
                second, 0,
                "a row already flagged must not be visited again")
            self.assertTrue(self._stored(rec))

    def test_a_request_still_inside_its_window_is_left_alone(self):
        rec = self._request()

        with freeze_time(rec.sla_deadline - timedelta(hours=1)):
            self.Request._cron_refresh_sla_breached()

        self.assertFalse(rec.sla_breached,
                         "the cron must not flag a request that has time left")
        self.assertFalse(self._stored(rec))

    # ── the production wiring ────────────────────────────────────────────────

    def test_the_refresh_cron_exists_and_names_a_method_that_exists(self):
        """Every test above calls the method by hand, which proves the refresh
        works and says nothing about whether anything ever calls it. That is
        the exact gap that left `sla_breached` false on 100% of breached
        requests while the compute itself was correct.
        """
        cron = self.env.ref("myservice_request_fields.cron_request_sla_breached")
        action = cron.ir_actions_server_id

        self.assertTrue(cron.active, "the cron must ship active")
        self.assertEqual(action.state, "code")
        self.assertEqual(action.code.strip(),
                         "model._cron_refresh_sla_breached()")
        self.assertEqual(action.model_id.model, "request.request")
        self.assertTrue(
            hasattr(self.Request, "_cron_refresh_sla_breached"),
            "the scheduled method must exist on the model the cron names")
        self.assertIn(
            cron.interval_type, ("minutes", "hours"),
            "the tightest SLA tier is 30 minutes; a daily or slower sweep "
            "would leave a critical breach unflagged for many times the SLA "
            "it is policing")
