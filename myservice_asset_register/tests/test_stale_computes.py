"""Stored computes that read the clock, and the crons that push them.

The rule these tests exist to enforce:

    A stored compute whose body reads the clock but whose `@api.depends`
    contains nothing the clock changes needs a cron, and that cron's method
    must exist.

`nrs.asset.is_verified` and `nrs.asset.pm.is_overdue` are both that shape. What
changes them is the calendar, and the calendar is not an ORM dependency — so
nothing in the database changes on the day a verification lapses or a PM falls
due, and the stored value stays at whatever it was when the row was last
written. `is_verified` said "verified" for ever; `is_overdue` said "not
overdue" for ever, backing an "Overdue PM Schedules" menu whose entire domain
is `[('is_overdue','=',True)]`.

So every test here moves the CLOCK and never the record. A test that had to
write to the row to make the flag change would be testing the compute and
missing the bug — which is how this survived into production. Records are
created under a freeze too, so no assertion depends on what today's real date
happens to be; a test that passes only until next year is not a regression net.

Two `ir.cron` rows for these methods once existed in `nrs19` and
`jaizbankplc` with no methods behind them (see migration 19.0.1.10.0); they
came from an unmerged branch and were deleted. TestTheCronsAreWiredUp is the
half that stops the reverse happening — methods with nothing proving they are
reached.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from datetime import date, timedelta

from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

# One verification, and three vantage points on it. Every date below is a
# literal so the arithmetic is checkable by eye:
#   VERIFIED_ON + 365 days = 2027-03-01
VERIFIED_ON = date(2026, 3, 1)
SOON_AFTER = "2026-04-01"        # 31 days on: inside every window here
HALF_A_YEAR = "2026-09-01"       # 184 days on: past 90, inside 365
LONG_AFTER = "2027-06-01"        # 457 days on: past 365


@tagged("post_install", "-at_install")
class TestVerificationExpires(CadraTransactionCase):
    """nrs.asset.is_verified — published API surface: it is serialised by
    GET /api/v1/assets and accepted as an `is_verified=` filter. It must
    expire, on a per-category window with a tenant-wide default.
    """

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Category = self.env["nrs.asset.category"]
        self.Param = self.env["ir.config_parameter"].sudo()
        # States no window of its own, so its assets fall through to the
        # tenant parameter and then to the 365-day default.
        self.plain_category = self.Category.create(
            {"name": "H09 Plain Category", "code": "H09PLAIN"})

    def _category(self, name, days):
        return self.Category.create({
            "name": name,
            "code": name.replace(" ", "")[:12],
            "verification_interval_days": days,
        })

    def _verified_asset(self, category=None):
        """An asset whose verification is recorded on VERIFIED_ON.

        The caller creates it inside a freeze, so the stored flag starts out
        as of that day rather than as of whenever the suite happens to run.
        """
        asset = self.Asset.create({
            "name": "H09 Verified Asset",
            "category_id": (category or self.plain_category).id,
            "last_verified_date": VERIFIED_ON,
        })
        # Flush before returning, under the caller's clock. This is not
        # incidental: a stored compute is not stale until it has actually been
        # WRITTEN. Left pending in `env.transaction.tocompute`, it is computed
        # on the first access or on the flush that `search()` performs — which,
        # inside a later `freeze_time`, happens under the NEW clock and quietly
        # produces the right answer for the wrong reason. Materialising the
        # column here is what makes the row behave like one written days ago,
        # which is the only thing these tests are about.
        asset.flush_recordset()
        return asset

    # ── The regression this file exists for ──────────────────────────────────

    def test_a_verification_lapses_when_the_window_passes_and_the_cron_runs(self):
        """The whole bug in one test. An asset verified a month ago is
        verified; fifteen months later it is not — and not one field on the
        asset was written in between. Before the cron existed the flag was
        computed once, on the day of the verification, and stayed true for the
        life of the register.
        """
        with freeze_time(SOON_AFTER):
            asset = self._verified_asset()
            asset.invalidate_recordset()
            self.assertTrue(
                asset.is_verified,
                "A month after a verification the asset is still verified.")

        with freeze_time(LONG_AFTER):
            self.Asset._cron_refresh_verification()
            asset.invalidate_recordset()
            self.assertFalse(
                asset.is_verified,
                "Fifteen months on the 365-day window has lapsed, and the "
                "cron must have written the flag back to the row.")

    def test_without_the_cron_the_flag_stays_stale_forever(self):
        """The negative half, and the reason the cron may not be deleted.

        This pins the defect itself: the clock moves, nothing recomputes, and
        the stored column still claims the asset is verified. Anyone who
        removes cron_asset_refresh_verification will find this test still
        passing and the one above failing, which names exactly what they broke.
        """
        with freeze_time(SOON_AFTER):
            asset = self._verified_asset()

        with freeze_time("2030-01-01"):
            asset.invalidate_recordset()
            self.assertTrue(
                asset.is_verified,
                "Four years on and nothing has recomputed, so the stored value "
                "is the one written in 2026. This is the bug, not the fix.")

    # ── The per-category window ──────────────────────────────────────────────

    def test_a_category_window_overrides_the_tenant_default(self):
        """A fire extinguisher is not verified on the same cycle as a filing
        cabinet. On one day, with one verification date, a 90-day category has
        lapsed and the 365-day default has not — which is the only thing that
        makes the per-category setting worth having.
        """
        quarterly = self._category("H09 Quarterly", 90)

        with freeze_time(SOON_AFTER):
            quarterly_asset = self._verified_asset(category=quarterly)
            annual_asset = self._verified_asset()
            (quarterly_asset | annual_asset).invalidate_recordset()
            self.assertTrue(quarterly_asset.is_verified)
            self.assertTrue(annual_asset.is_verified)

        with freeze_time(HALF_A_YEAR):
            self.Asset._cron_refresh_verification()
            (quarterly_asset | annual_asset).invalidate_recordset()
            self.assertFalse(
                quarterly_asset.is_verified,
                "Six months on, a 90-day window has long since lapsed.")
            self.assertTrue(
                annual_asset.is_verified,
                "Same day, same verification date — the 365-day default has "
                "not lapsed, so the two must disagree.")

    def test_shortening_a_category_window_bites_immediately(self):
        """`category_id.verification_interval_days` is in `@api.depends`, so a
        manager who tightens a category does not wait a day for the cron. That
        one IS an ORM dependency and it must fire.
        """
        category = self._category("H09 Tightening", 365)

        with freeze_time(HALF_A_YEAR):
            asset = self._verified_asset(category=category)
            asset.invalidate_recordset()
            self.assertTrue(asset.is_verified)

            category.verification_interval_days = 30
            self.assertFalse(
                asset.is_verified,
                "Tightening the category to 30 days lapses a verification made "
                "six months ago, with no cron run in between.")

    # ── The tenant-wide fallback ─────────────────────────────────────────────

    def test_the_tenant_parameter_applies_where_the_category_states_nothing(self):
        """A tenant that counts its estate quarterly sets the parameter once
        rather than editing every category.
        """
        with freeze_time(SOON_AFTER):
            asset = self._verified_asset()
            asset.invalidate_recordset()
            self.assertTrue(asset.is_verified)

        self.Param.set_param("cadra.assets.verification_interval_days", "90")

        with freeze_time(HALF_A_YEAR):
            self.Asset._cron_refresh_verification()
            asset.invalidate_recordset()
            self.assertFalse(
                asset.is_verified,
                "The tenant window is now 90 days and six months have passed; "
                "under the 365-day default this asset would still be verified.")

    def test_a_category_window_wins_over_the_tenant_parameter(self):
        """Most specific wins. Otherwise the per-category setting would be
        advisory, which is the sort of setting that gets typed in and quietly
        ignored.
        """
        self.Param.set_param("cadra.assets.verification_interval_days", "30")
        generous = self._category("H09 Generous", 365)

        with freeze_time(SOON_AFTER):
            asset = self._verified_asset(category=generous)

        with freeze_time(HALF_A_YEAR):
            self.Asset._cron_refresh_verification()
            asset.invalidate_recordset()
            self.assertTrue(
                asset.is_verified,
                "The category says 365 days, so the 30-day tenant default must "
                "not shorten it.")

    def test_a_garbage_tenant_parameter_falls_back_to_the_documented_default(self):
        """`ir.config_parameter` is free text and someone will type into it. A
        non-numeric or non-positive value must not produce a cutoff of today —
        which would read as "every asset in the register is unverified" — or
        raise inside a compute that runs on every write.
        """
        for bad in ("not a number", "", "-5", "0", "12.5"):
            self.Param.set_param("cadra.assets.verification_interval_days", bad)
            self.assertEqual(
                self.Asset._verification_interval_days(), 365,
                "%r is not a window; fall back to 365 rather than inventing "
                "one." % bad)

    def test_an_asset_that_was_never_verified_is_never_flagged_verified(self):
        """The cron only touches rows carrying a last_verified_date, so this is
        also the assertion that it cannot flip a never-verified asset to true.
        """
        with freeze_time(SOON_AFTER):
            asset = self.Asset.create({
                "name": "H09 Never Verified",
                "category_id": self.plain_category.id,
            })

        with freeze_time(LONG_AFTER):
            self.Asset._cron_refresh_verification()
            asset.invalidate_recordset()
            self.assertFalse(asset.is_verified)


@tagged("post_install", "-at_install")
class TestOverdueRefreshes(CadraTransactionCase):
    """nrs.asset.pm.is_overdue — the same shape, backing a live menu whose
    entire domain is `[('is_overdue','=',True)]`.
    """

    # Serviced on VERIFIED_ON's day on a 90-day cycle, so: due 2026-05-30.
    LAST_DONE = date(2026, 3, 1)
    NEXT_DUE = date(2026, 5, 30)
    BEFORE_DUE = "2026-04-01"
    AFTER_DUE = "2026-07-01"

    def setUp(self):
        super().setUp()
        self.PM = self.env["nrs.asset.pm"]
        category = self.env["nrs.asset.category"].create(
            {"name": "H09 PM Category", "code": "H09PM"})
        self.asset = self.env["nrs.asset"].create(
            {"name": "H09 PM Asset", "category_id": category.id})

    def _schedule(self):
        schedule = self.PM.create({
            "name": "H09 Quarterly Service",
            "asset_id": self.asset.id,
            "interval_days": 90,
            "last_done_date": self.LAST_DONE,
        })
        # Flush before returning, under the caller's clock. This is not
        # incidental: a stored compute is not stale until it has actually been
        # WRITTEN. Left pending in `env.transaction.tocompute`, it is computed
        # on the first access or on the flush that `search()` performs — which,
        # inside a later `freeze_time`, happens under the NEW clock and quietly
        # produces the right answer for the wrong reason. Materialising the
        # column here is what makes the row behave like one written days ago,
        # which is the only thing these tests are about.
        schedule.flush_recordset()
        return schedule

    def test_a_schedule_falls_overdue_when_its_due_date_passes_and_the_cron_runs(self):
        """Serviced 1 March on a 90-day cycle: due 30 May, not overdue in
        April, overdue in July — and the schedule itself is never touched.
        """
        with freeze_time(self.BEFORE_DUE):
            schedule = self._schedule()
            self.assertEqual(schedule.next_due_date, self.NEXT_DUE)
            schedule.invalidate_recordset()
            self.assertFalse(
                schedule.is_overdue,
                "Two months before the due date nothing is overdue.")

        with freeze_time(self.AFTER_DUE):
            self.PM._cron_refresh_overdue()
            schedule.invalidate_recordset()
            self.assertTrue(
                schedule.is_overdue,
                "A month past the due date the flag must be true in the row, "
                "or the Overdue PM Schedules menu stays empty.")

    def test_without_the_cron_an_overdue_schedule_never_flags(self):
        """The defect itself, pinned. Every PM row on every tenant carried
        is_overdue = False for this reason.
        """
        with freeze_time(self.BEFORE_DUE):
            schedule = self._schedule()

        with freeze_time("2030-01-01"):
            schedule.invalidate_recordset()
            self.assertFalse(
                schedule.is_overdue,
                "Nearly four years past due and the stored flag still says no. "
                "This is the bug, not the fix.")

    def test_the_overdue_menu_domain_finds_the_schedule_after_the_cron(self):
        """The menu searches, and a search reads the column rather than the
        cache. This fails if the cron leaves the recompute pending instead of
        flushing it — which `modified()` on its own does.
        """
        with freeze_time(self.BEFORE_DUE):
            schedule = self._schedule()

        with freeze_time(self.AFTER_DUE):
            self.PM._cron_refresh_overdue()
            self.assertIn(
                schedule, self.PM.search([("is_overdue", "=", True)]),
                "Overdue PM Schedules uses exactly this domain.")

    # ── R45: the never-serviced schedule ─────────────────────────────────────

    # `create_date` is written by POSTGRES, not by Python — Odoo puts
    # `now() at time zone 'UTC'` in the INSERT — so `freeze_time` cannot move
    # it, and these three tests cannot use the literal-date idiom the rest of
    # this file is built on. That is worth knowing rather than working around
    # quietly: this file's whole discipline is "create the record under a
    # freeze too, so no assertion depends on what today happens to be", and an
    # anchor on `create_date` silently opts out of it. The first version of
    # these tests asserted a frozen date against a database-clock one and
    # failed on the run that was meant to prove them. So they derive their
    # expectation from the record's OWN `create_date` and freeze relative to
    # it — the arithmetic is still checkable, just not by eye against a
    # literal.

    def _never_serviced(self, name, interval=90):
        schedule = self.PM.create({
            "name": name,
            "asset_id": self.asset.id,
            "interval_days": interval,
        })
        schedule.flush_recordset()
        return schedule

    def test_a_never_serviced_schedule_is_due_one_interval_after_it_was_set_up(self):
        """`next_due_date = today` is not a due date, it is the absence of one.

        A schedule with an interval and no `last_done_date` used to be re-dated
        to today on every recompute, so it was permanently `is_overdue = False`
        and the daily cron rewrote the row every tick to say nothing had
        changed — the stale-clock defect of handoff 09 dressed as its fix. It
        now anchors on `create_date`.
        """
        schedule = self._never_serviced("H10 Never Serviced")
        self.assertEqual(
            schedule.next_due_date,
            schedule.create_date.date() + timedelta(days=90),
            "90 days after the day it was set up")
        schedule.invalidate_recordset()
        self.assertFalse(
            schedule.is_overdue,
            "and not overdue on the day it was created, whatever day that is")

    def test_a_never_serviced_schedules_due_date_does_not_move_with_the_clock(self):
        """The regression in one assertion: the date it was given on the day it
        was created is the date it still has months later — and it can finally
        fall overdue, which was impossible while the due date chased the clock.
        """
        schedule = self._never_serviced("H10 Fixed Point")
        due = schedule.next_due_date

        # A day past the due date, whenever that is. The freeze is relative to
        # the record's own anchor for the reason given above.
        with freeze_time(due + timedelta(days=1)):
            self.PM._cron_refresh_overdue()
            schedule.invalidate_recordset()
            self.assertEqual(schedule.next_due_date, due,
                             "the cron re-evaluates the flag, not the anchor")
            self.assertTrue(
                schedule.is_overdue,
                "and a never-serviced schedule CAN now fall overdue, which "
                "was impossible while the due date chased the clock")

    def test_the_cron_leaves_a_settled_schedule_alone(self):
        """`next_due_date = today` also meant a daily UPDATE on every such row.
        A refresh that rewrites rows it did not change is a refresh nobody can
        read a write_date off.
        """
        schedule = self._never_serviced("H10 Settled")
        before = schedule.write_date

        self.PM._cron_refresh_overdue()
        schedule.invalidate_recordset()
        self.assertEqual(schedule.write_date, before,
                         "nothing changed, so nothing was written")

    def test_marking_a_pm_done_clears_the_overdue_flag(self):
        """The other direction. last_done_date IS an ORM dependency, so this
        has always worked; it is here so a future change to the cron cannot
        break it unnoticed.
        """
        with freeze_time(self.BEFORE_DUE):
            schedule = self._schedule()

        with freeze_time(self.AFTER_DUE):
            self.PM._cron_refresh_overdue()
            schedule.invalidate_recordset()
            self.assertTrue(schedule.is_overdue)

            schedule.last_done_date = date(2026, 6, 25)
            self.assertFalse(
                schedule.is_overdue,
                "Serviced six days ago on a 90-day cycle: not overdue.")


@tagged("post_install", "-at_install")
class TestTheCronsAreWiredUp(CadraTransactionCase):
    """A method nothing calls is the same defect as a cron with no method,
    pointed the other way. Rows for both of these once existed in two tenant
    databases with no code behind them; these assert the pairing in the
    direction a source file can be checked.
    """

    def test_both_refresh_crons_exist_and_name_a_method_that_exists(self):
        expected = {
            "myservice_asset_register.cron_asset_refresh_verification":
                ("nrs.asset", "_cron_refresh_verification"),
            "myservice_asset_register.cron_asset_pm_refresh_overdue":
                ("nrs.asset.pm", "_cron_refresh_overdue"),
        }
        for xmlid, (model_name, method) in expected.items():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            self.assertTrue(cron, "%s is missing from the registry." % xmlid)
            self.assertEqual(cron.model_id.model, model_name)
            self.assertEqual(cron.state, "code")
            self.assertIn(method, cron.code)
            self.assertTrue(
                hasattr(self.env[model_name], method),
                "%s schedules %s.%s(), which does not exist."
                % (xmlid, model_name, method))
