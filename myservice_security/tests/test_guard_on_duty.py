"""security.guard.on_duty — the roster half and the clock half.

on_duty is stored, and two separate things stopped it ever being recomputed:
its @api.depends was empty, so a roster row appearing or being cancelled
changed nothing; and its body reads today's date, so even a correct depends
would leave it true the morning after the shift.

Both halves are proven here, and the clock half is proven by moving the clock
and running the cron with NO write to the guard or to the roster — because a
test that pokes an input proves the dependency graph works, which was never
the thing in doubt.

on_duty is published API surface: the security dashboard and
GET /api/v1/security/kpis both count it with search_count, which reads the
stored column — so every assertion below checks the column, not just the ORM
cache.

Run with:
    odoo -d <db> -u myservice_security --test-enable \\
         --test-tags /myservice_security --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
from datetime import date

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestGuardOnDuty(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Guard = self.env["security.guard"]
        self.Roster = self.env["security.duty.roster"]
        self.location = self.env["generic.location"].create({"name": "Gate House"})

    def _guard(self, name):
        partner = self.env["res.partner"].create({"name": name})
        return self.Guard.create({
            "name": name,
            "badge_number": "BDG-%s" % partner.id,
            "partner_id": partner.id,
        })

    def _roster(self, guard, on_date, status="active"):
        return self.Roster.create({
            "guard_id": guard.id,
            "location_id": self.location.id,
            "date": on_date,
            "shift": "morning",
            "status": status,
        })

    def _on_duty_in_the_column(self, guard):
        """What the dashboard's search_count would see, not what the cache holds."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT on_duty FROM security_guard WHERE id = %s", (guard.id,))
        return self.env.cr.fetchone()[0]

    # ── the roster half: nothing to do with the clock ────────────────────────

    def test_a_roster_row_for_today_puts_the_guard_on_duty_with_no_cron(self):
        """The empty @api.depends meant on_duty was computed once, at creation,
        when the guard could not possibly have a roster — and never again. A
        guard posted to a gate today must read as on duty the moment the roster
        row says so, without waiting for any scheduled job."""
        guard = self._guard("Depends Half")
        self.assertFalse(guard.on_duty)
        self.assertFalse(self._on_duty_in_the_column(guard))

        self._roster(guard, fields.Date.today())

        self.assertTrue(guard.on_duty)
        self.assertTrue(self._on_duty_in_the_column(guard))

    def test_ending_the_shift_takes_the_guard_off_duty_with_no_cron(self):
        """The same defect in the other direction, and the more dangerous one:
        a guard who has gone home still counted as on station."""
        guard = self._guard("Checked Out")
        roster = self._roster(guard, fields.Date.today())
        self.assertTrue(self._on_duty_in_the_column(guard))

        roster.action_check_out()

        self.assertFalse(guard.on_duty)
        self.assertFalse(self._on_duty_in_the_column(guard))

    def test_a_roster_for_another_day_does_not_put_the_guard_on_duty(self):
        """on_duty means on station now, not rostered at some point."""
        guard = self._guard("Tomorrow")
        self._roster(guard, fields.Date.add(fields.Date.today(), days=1))
        self.assertFalse(self._on_duty_in_the_column(guard))

    # ── the clock half: the reason there is a cron ───────────────────────────

    def test_on_duty_stays_true_after_the_shift_date_passes_until_the_cron_runs(self):
        """The whole bug in one test.

        Nothing is written between the two blocks below — only the date
        changes. Without the cron the guard is still on duty the next morning,
        for ever, because no dependency can fire for the calendar turning over.
        The middle assertion pins the stale value deliberately: if someone
        deletes the cron, this test must fail rather than quietly pass.
        """
        with freeze_time("2026-03-02"):
            guard = self._guard("Clock Half")
            self._roster(guard, date(2026, 3, 2))
            self.assertTrue(self._on_duty_in_the_column(guard))

        with freeze_time("2026-03-03"):
            self.assertTrue(
                self._on_duty_in_the_column(guard),
                "the stored column cannot correct itself — that is the defect")

            self.Guard._cron_refresh_on_duty()

            self.assertFalse(guard.on_duty)
            self.assertFalse(
                self._on_duty_in_the_column(guard),
                "the cron must take yesterday's shift off the dashboard")

    def test_the_cron_puts_a_guard_on_duty_when_the_rostered_day_arrives(self):
        """The same silence in the other direction: a shift rostered in advance
        must start counting on the day it starts, not on the day someone
        happens to edit the row."""
        with freeze_time("2026-03-02"):
            guard = self._guard("Rostered Ahead")
            self._roster(guard, date(2026, 3, 3))
            self.assertFalse(self._on_duty_in_the_column(guard))

        with freeze_time("2026-03-03"):
            self.assertFalse(self._on_duty_in_the_column(guard))
            self.Guard._cron_refresh_on_duty()
            self.assertTrue(self._on_duty_in_the_column(guard))

    # ── the production wiring ────────────────────────────────────────────────

    def test_the_refresh_cron_exists_and_resolves_to_the_method(self):
        """A cron whose method does not exist is the defect handoff 08 found in
        two live tenants. Asserting the xmlid, the model and the call string
        together is what makes a rename fail here rather than at 00:05."""
        cron = self.env.ref("myservice_security.cron_security_refresh_on_duty")
        self.assertTrue(cron.active)
        self.assertEqual(cron.model_id.model, "security.guard")
        self.assertEqual(cron.ir_actions_server_id.code.strip(),
                         "model._cron_refresh_on_duty()")
        self.assertTrue(hasattr(self.Guard, "_cron_refresh_on_duty"))
