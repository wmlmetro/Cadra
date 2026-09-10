"""The disposal report reports what is missing, and repairs none of it.

Handoff 16 §B2. INT-10 §2.9 measured what Cadra could say about a disposal
and the answer was a state, an untracked date and an untracked reason — no
authorising reference of any kind, no approver, no proceeds, no method, and
no period report. The fields are handoff 16's work; these tests are about the
report over them, and specifically about the three things a status check on
`disposal_report` would not see:

1. **A disposal with nothing behind it is the OUTPUT, not an exclusion.** The
   easy report to write is one that lists well-documented disposals, and it
   passes every test that asks "does a good row appear". So the tests here
   assert the opposite direction: a disposal with no reference, no approver
   and no method is IN the rows, with each absence named in `findings`. A
   report that filtered them would be a report of the paperwork rather than
   of the estate, and would show an auditor a clean sheet built out of the
   rows it dropped.

2. **`state = 'missing'` is not a disposal.** An asset that cannot be found
   has not been disposed of, and a report that conflated them would let a
   loss be written off as a disposal — the single most consequential wrong
   answer this report could give. Asserted against the report's own
   `extra_domain` argument, which is the only caller-supplied input it has.

3. **It writes nothing.** Fingerprinted with an md5 over the whole
   `nrs_asset` table plus the two mail tables, before and after, with a flush
   on both sides so a pending compute cannot hide a write on one side or
   fabricate one on the other. A report that quietly fixes what it finds can
   never honestly report zero, and the second run reports a cleanliness it
   created itself.

And one thing that is not about the report at all: **every value of
`disposal_method` maps onto SAP's two-word `disposal_type`.** A method added
later without a mapping would silently default to `disposal`, so a scrapping
would post to SAP as a disposal and nobody would find out from Cadra.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.myservice_asset_register.models.asset_disposal import (
    DEFAULT_SAP_DISPOSAL_TYPE,
    PROCEEDS_EXPECTED_METHODS,
    SAP_DISPOSAL_TYPE,
)

# A period wide enough to hold anything a test dates deliberately, and
# narrow enough that it is obviously a choice. Individual tests that are
# about the boundaries name their own.
WIDE_FROM = date(2000, 1, 1)
WIDE_TO = date(2099, 12, 31)


class DisposalCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Disposal test category"})
        self._sap_seq = 0

    def _flush_tracking(self):
        """Materialise the chatter tracking rows this transaction would write.

        Odoo 19 registers `_track_finalize` on `cr.precommit`
        (`addons/mail/models/mail_thread.py:534`), so tracking values are
        written at COMMIT and not at flush. A `TransactionCase` never
        commits — so a test that writes a tracked field and then reads
        `mail_tracking_value` finds nothing, and a fallback that depends on
        those rows passes or fails for reasons that have nothing to do with
        the code under test. This is Odoo's own `MailCommon.flush_tracking`
        idiom, and it belongs in any test that reads the tracking table.
        """
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.flush_all()

    def _sap_number(self):
        """Unique, because `nrs.asset` constrains SAP numbers to one asset."""
        self._sap_seq += 1
        return "DISPTEST%06d" % self._sap_seq

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Disposal test asset", "category_id": self.category.id},
            **vals))

    def _bare_disposal(self, **vals):
        """A disposal with nothing behind it — the common case on a live
        tenant, and the one the report exists to make visible."""
        return self._asset(**dict(
            {"state": "disposed", "disposal_date": date(2026, 3, 15)},
            **vals))

    def _documented_disposal(self, **vals):
        """A disposal that would pass an audit: every question answered."""
        asset = self._asset(**dict({
            "state": "disposed",
            "disposal_date": date(2026, 3, 15),
            "disposal_method": "sale",
            "disposal_reference": "BOS/2026/014",
            "disposal_reason": "Beyond economic repair; sold at board of survey.",
            "disposal_proceeds": 45000.0,
            "sap_asset_number": self._sap_number(),
        }, **vals))
        asset.write({
            "disposal_approved_by": self.env.uid,
            "disposal_approved_date": datetime(2026, 3, 10, 9, 0, 0),
        })
        return asset

    def _report(self, date_from=WIDE_FROM, date_to=WIDE_TO, extra_domain=None):
        return self.Asset.disposal_report(
            date_from, date_to, extra_domain=extra_domain)

    def _row_for(self, report, asset):
        for row in report["rows"] + report["unplaceable"]:
            if row["asset_id"] == asset.id:
                return row
        return None


@tagged("post_install", "-at_install")
class TestFindingsAreTheProduct(DisposalCase):

    def test_a_disposal_with_no_reference_appears_with_the_finding(self):
        """The acceptance criterion, stated as a test.

        Not filtered, not annotated in a warnings block somewhere off to the
        side: in `rows`, with `no_authorising_reference` in its own
        `findings` list, so a reader walking the schedule cannot miss it and
        a machine counting them does not have to parse prose.
        """
        asset = self._bare_disposal()
        row = self._row_for(self._report(), asset)
        self.assertIsNotNone(
            row, "a disposal with no authorising reference was filtered out "
                 "of the report — it is the finding, not an exclusion")
        self.assertIn("no_authorising_reference", row["findings"])
        self.assertIsNone(row["disposal_reference"])

    def test_the_bare_disposal_names_every_absence(self):
        """Four findings from one row, because an auditor's test has four
        parts and answering "it is incomplete" tells them nothing about
        which part to chase."""
        asset = self._bare_disposal()
        row = self._row_for(self._report(), asset)
        for finding in ("no_authorising_reference", "no_approver",
                        "no_disposal_method", "no_disposal_reason"):
            self.assertIn(finding, row["findings"])

    def test_a_missing_sap_number_is_not_a_per_row_finding(self):
        """The absence is real and it is NOT a finding (handoff 17 E1).

        It is absent from ~100% of rows on every tenant, and a finding that
        fires on every row is one a reader learns to skip — which costs
        `no_approver` and `no_authorising_reference`, sitting in the same
        column, the weight they were meant to carry. The FACT survives: the
        row still publishes `sap_asset_number: None`, and the period says so
        once in `summary.sap_coverage`.
        """
        asset = self._bare_disposal()
        row = self._row_for(self._report(), asset)
        self.assertNotIn("no_sap_asset_number", row["findings"])
        self.assertIsNone(
            row["sap_asset_number"],
            "the per-row FACT went with the per-row finding. Only the "
            "finding label was meant to go.")

    def test_a_documented_disposal_has_no_findings(self):
        """The other direction, and it is the one that makes the first
        meaningful: if every row carried findings the report would be
        measuring itself rather than the register."""
        asset = self._documented_disposal()
        row = self._row_for(self._report(), asset)
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["disposal_reference"], "BOS/2026/014")
        self.assertEqual(row["approved_by_id"], self.env.uid)

    def test_an_approver_with_no_date_is_its_own_finding(self):
        """Weaker than no approver, and different: somebody is named, but
        the disposal cannot be placed against the authority in time."""
        asset = self._documented_disposal()
        asset.disposal_approved_date = False
        row = self._row_for(self._report(), asset)
        self.assertIn("no_approval_date", row["findings"])
        self.assertNotIn("no_approver", row["findings"])

    def test_missing_proceeds_is_a_finding_only_where_money_was_expected(self):
        """A scrapping with no proceeds is ordinary. A SALE with no proceeds
        is a finding, and flagging both would bury the second in the first —
        which on a real estate is the larger population by far.
        """
        sold = self._documented_disposal(disposal_proceeds=0.0)
        scrapped = self._documented_disposal(
            disposal_method="scrapped", disposal_proceeds=0.0)
        report = self._report()
        self.assertIn("sale", PROCEEDS_EXPECTED_METHODS)
        self.assertIn("no_proceeds_recorded",
                      self._row_for(report, sold)["findings"])
        self.assertNotIn("no_proceeds_recorded",
                         self._row_for(report, scrapped)["findings"])

    def test_the_summary_counts_match_the_rows(self):
        """The summary is what an auditor reads instead of walking pages, so
        it has to be derived from the same rows rather than from a second
        query that can drift from them."""
        self._bare_disposal()
        self._bare_disposal()
        self._documented_disposal()
        report = self._report()
        summary = report["summary"]

        self.assertEqual(summary["total"], len(report["rows"]))
        self.assertEqual(summary["unplaceable"], len(report["unplaceable"]))
        self.assertEqual(
            summary["clean"],
            sum(1 for row in report["rows"] if not row["findings"]))
        for finding, count in summary["findings"].items():
            self.assertEqual(
                count,
                sum(1 for row in report["rows"]
                    if finding in row["findings"]),
                "summary count for %s disagrees with the rows" % finding)
        self.assertEqual(
            sum(summary["by_method"].values()), len(report["rows"]))

    def test_proceeds_are_totalled_per_currency_and_never_across_them(self):
        """Every tenant is single-currency today, which is exactly the
        condition under which a cross-currency sum looks correct for years.

        SCOPED to this test's own two assets, and the first version was not.
        `disposal_report` reports the REGISTER, so an absolute total is a
        claim about every disposal on the tenant — which passed locally
        because the tenant happened to hold none at that moment, and failed
        in CI, where `pytest tests/` runs BEFORE the in-registry suites and
        commits a disposal fixture carrying proceeds of its own. A
        `TransactionCase` rolls back its own rows and cannot roll back
        somebody else's.

        This is the same defect the whole handoff is about, turned on the
        tests: an assertion that is true because of what happened to be in
        the database, presented as an assertion about the code.
        """
        first = self._documented_disposal(disposal_proceeds=45000.0)
        second = self._documented_disposal(disposal_proceeds=5000.0)
        report = self._report(
            extra_domain=[("id", "in", [first.id, second.id])])
        proceeds = report["summary"]["proceeds_by_currency"]
        self.assertEqual(len(proceeds), 1)
        self.assertAlmostEqual(sum(proceeds.values()), 50000.0, places=2)


@tagged("post_install", "-at_install")
class TestTheSapPositionIsStatedOnce(DisposalCase):
    """`summary.sap_coverage` — handoff 17 E1.

    EVERY test here is SCOPED with `extra_domain`, and that is not tidiness.
    `disposal_report` reports the REGISTER, and in CI `pytest tests/` runs
    before this suite and COMMITS disposal fixtures of its own, none of them
    carrying a SAP number. An unscoped coverage assertion would be an
    assertion about whatever the database happened to hold — the same defect
    the whole report exists to remove, turned on its own tests. The proceeds
    test above learned this the hard way.
    """

    def _coverage(self, assets):
        report = self._report(
            extra_domain=[("id", "in", [a.id for a in assets])])
        return report["summary"]["sap_coverage"]

    def test_a_period_where_nothing_reached_sap_says_so_once(self):
        """The sentence the ruling asked for, and it is said ONCE for the
        period rather than 63 times down a findings column."""
        assets = [self._bare_disposal(), self._bare_disposal()]
        coverage = self._coverage(assets)
        self.assertEqual(coverage["coverage"], "none")
        self.assertEqual(coverage["total"], 2)
        self.assertEqual(coverage["with_sap_asset_number"], 0)
        self.assertEqual(coverage["without_sap_asset_number"], 2)
        self.assertIn("No disposal in this period carried a SAP asset "
                      "number", coverage["statement"])

    def test_a_period_where_some_reached_sap_never_says_none_did(self):
        """The case that makes the absolute sentence a lie.

        Three of five carrying a SAP number must not be rendered as *"No
        disposal in this period carried a SAP asset number"*. A renderer
        cannot get this wrong by accident because the verdict is not left to
        it: `coverage` is `partial` and the statement counts.
        """
        assets = [self._bare_disposal(), self._bare_disposal(),
                  self._documented_disposal(), self._documented_disposal(),
                  self._documented_disposal()]
        coverage = self._coverage(assets)
        self.assertEqual(coverage["coverage"], "partial")
        self.assertEqual(coverage["total"], 5)
        self.assertEqual(coverage["with_sap_asset_number"], 3)
        self.assertEqual(coverage["without_sap_asset_number"], 2)
        self.assertNotIn("No disposal in this period", coverage["statement"])
        self.assertIn("3 of 5", coverage["statement"])

    def test_a_period_where_all_reached_sap_says_that_instead(self):
        assets = [self._documented_disposal(), self._documented_disposal()]
        coverage = self._coverage(assets)
        self.assertEqual(coverage["coverage"], "complete")
        self.assertEqual(coverage["without_sap_asset_number"], 0)
        self.assertIn("Every disposal", coverage["statement"])

    def test_an_empty_period_is_not_the_same_statement_as_none_reached_sap(
            self):
        """Both counts are zero and the two mean different things.

        "No disposal in this period carried a SAP asset number" is true of
        the empty set and reads to a human as a finding about disposals that
        do not exist. `empty` keeps the two apart.
        """
        coverage = self._coverage([])
        self.assertEqual(coverage["coverage"], "empty")
        self.assertEqual(coverage["total"], 0)
        self.assertNotIn("SAP", coverage["statement"])

    def test_the_coverage_counts_add_up_to_the_rows_they_describe(self):
        """The failure this catches is a coverage block counted over a
        different population from `summary.total` — two numbers in one
        response that cannot both be about the same period."""
        assets = [self._bare_disposal(), self._documented_disposal(),
                  self._documented_disposal()]
        report = self._report(
            extra_domain=[("id", "in", [a.id for a in assets])])
        coverage = report["summary"]["sap_coverage"]
        self.assertEqual(coverage["total"], report["summary"]["total"])
        self.assertEqual(
            coverage["with_sap_asset_number"]
            + coverage["without_sap_asset_number"],
            len(report["rows"]))
        self.assertEqual(
            coverage["with_sap_asset_number"],
            sum(1 for row in report["rows"] if row["sap_asset_number"]))

    def test_no_row_carries_the_retired_finding(self):
        """The acceptance criterion, stated where it will fail loudly if
        anybody puts it back: `no_sap_asset_number` appears once as a
        statement, never per row."""
        assets = [self._bare_disposal(), self._documented_disposal()]
        report = self._report(
            extra_domain=[("id", "in", [a.id for a in assets])])
        for row in report["rows"] + report["unplaceable"]:
            self.assertNotIn("no_sap_asset_number", row["findings"])
        self.assertNotIn("no_sap_asset_number", report["summary"]["findings"])


@tagged("post_install", "-at_install")
class TestMissingIsNotADisposal(DisposalCase):

    def test_a_missing_asset_never_appears(self):
        """INT-10 §2.9 and the SAP requirements §4.3 both say it explicitly:
        an asset that cannot be found has not been disposed of. Conflating
        them would let a loss be written off as a disposal."""
        lost = self._asset(state="missing", disposal_date=date(2026, 3, 15))
        report = self._report()
        self.assertIsNone(self._row_for(report, lost))

    def test_extra_domain_cannot_pull_a_missing_asset_in(self):
        """`extra_domain` is the report's only caller-supplied input. A
        caller naming `missing` gets nothing rather than a loss dressed as a
        disposal — the domain narrows, it never widens."""
        lost = self._asset(state="missing", disposal_date=date(2026, 3, 15))
        report = self._report(extra_domain=[("state", "=", "missing")])
        self.assertIsNone(self._row_for(report, lost))
        self.assertEqual(report["rows"], [])

    def test_extra_domain_still_narrows(self):
        """The guard must not have turned the argument into a no-op: an
        `extra_domain` that excludes a row still excludes it."""
        kept = self._bare_disposal(name="Kept")
        dropped = self._bare_disposal(name="Dropped")
        report = self._report(extra_domain=[("id", "=", kept.id)])
        self.assertIsNotNone(self._row_for(report, kept))
        self.assertIsNone(self._row_for(report, dropped))


@tagged("post_install", "-at_install")
class TestThePeriod(DisposalCase):

    def test_both_boundaries_are_inclusive(self):
        """An auditor asks for a quarter by naming its first and last day.
        An exclusive upper bound silently loses everything disposed of on 31
        March, which is the busiest disposal date in a financial year."""
        first = self._bare_disposal(disposal_date=date(2026, 1, 1))
        last = self._bare_disposal(disposal_date=date(2026, 3, 31))
        report = self._report(date(2026, 1, 1), date(2026, 3, 31))
        self.assertIsNotNone(self._row_for(report, first))
        self.assertIsNotNone(self._row_for(report, last))

    def test_a_disposal_outside_the_period_is_not_in_it(self):
        before = self._bare_disposal(disposal_date=date(2025, 12, 31))
        after = self._bare_disposal(disposal_date=date(2026, 4, 1))
        report = self._report(date(2026, 1, 1), date(2026, 3, 31))
        self.assertIsNone(self._row_for(report, before))
        self.assertIsNone(self._row_for(report, after))

    def test_dates_may_be_given_as_strings(self):
        """An auditor's period arrives over an API or off a form; both hand
        it over as text."""
        asset = self._bare_disposal(disposal_date=date(2026, 3, 15))
        report = self._report("2026-01-01", "2026-03-31")
        self.assertIsNotNone(self._row_for(report, asset))
        self.assertEqual(report["period"]["date_from"], "2026-01-01")
        self.assertEqual(report["period"]["inclusive"], "both")

    def test_a_period_that_ends_before_it_starts_is_refused(self):
        """Silently returning nothing would read as "no disposals that
        quarter", which is an answer rather than an error."""
        with self.assertRaises(UserError):
            self._report(date(2026, 3, 31), date(2026, 1, 1))

    def test_a_missing_date_is_refused(self):
        with self.assertRaises(UserError):
            self._report(False, date(2026, 3, 31))


@tagged("post_install", "-at_install")
class TestADisposalWithNoDate(DisposalCase):

    def test_the_date_falls_back_to_the_tracked_state_change(self):
        """`action_condemn` wrote no date for the whole life of the product,
        so an undated disposal is the common case rather than the edge one.
        The tracked `state` transition is the only evidence in the database
        of when it happened, and a row placed by it says so in
        `date_source` — an auditor reconciling a period total has to know
        whether the date placing a row in that period was recorded at the
        time or worked out afterwards.
        """
        asset = self._asset()
        # Flush BETWEEN the create and the write. `mail_thread.create`
        # registers `_track_discard` on `cr.precommit`, which nulls the
        # initial values for this record until the precommit runs — so a
        # write issued after a create and before that point records NO
        # tracking row at all, and the fallback under test has nothing to
        # find. Creating and then changing in one uninterrupted block is the
        # natural way to write this test and it silently tests nothing.
        self._flush_tracking()
        asset.write({"state": "disposed"})
        self._flush_tracking()
        self.assertFalse(asset.disposal_date)

        # UTC, because `mail_message.date` is UTC and a test run in the hour
        # after local midnight would otherwise compare two different days.
        today = fields.Datetime.now().date()
        report = self._report(today - timedelta(days=1),
                              today + timedelta(days=1))
        row = self._row_for(report, asset)
        self.assertIsNotNone(
            row, "an undated disposal fell out of the period report — the "
                 "silent hole this report exists to close")
        self.assertEqual(row["date_source"], "state_transition")
        self.assertIn("no_disposal_date", row["findings"])
        self.assertEqual(row["disposal_date"], today.isoformat())

    def test_a_disposal_with_no_evidence_at_all_is_unplaceable_not_absent(self):
        """A tenant seeded by direct SQL produces no tracking rows, so some
        disposals have no date and no way to recover one. Dropping them makes
        them invisible in EVERY period; putting them in one double-counts
        them in the next. They are returned in full, in their own key, with
        their own count, in every report.
        """
        asset = self.Asset.with_context(tracking_disable=True).create({
            "name": "Seeded disposal",
            "category_id": self.category.id,
            "state": "disposed",
        })
        report = self._report(date(2026, 1, 1), date(2026, 3, 31))
        ids = [row["asset_id"] for row in report["unplaceable"]]
        self.assertIn(asset.id, ids)
        self.assertNotIn(asset.id, [row["asset_id"] for row in report["rows"]])
        self.assertEqual(report["summary"]["unplaceable"],
                         len(report["unplaceable"]))

        row = self._row_for(report, asset)
        self.assertEqual(row["date_source"], "none")
        self.assertIsNone(row["disposal_date"])
        self.assertIn("no_disposal_date", row["findings"])

        # And it is in the NEXT period's report too, because it belongs to
        # no period. Invisible everywhere is the failure being avoided.
        later = self._report(date(2026, 4, 1), date(2026, 6, 30))
        self.assertIn(asset.id,
                      [row["asset_id"] for row in later["unplaceable"]])

    def test_a_reconstructed_date_says_so(self):
        """The migration recovers a date from the tracked state change and
        marks the row. Without the marker a recovered date is
        indistinguishable from a recorded one, which is exactly what
        `nrs.asset.custody.source = 'tracking_backfill'` exists to prevent.
        """
        asset = self._bare_disposal()
        asset.disposal_date_reconstructed = True
        row = self._row_for(self._report(), asset)
        self.assertEqual(row["date_source"], "reconstructed")
        self.assertIn("disposal_date_reconstructed", row["findings"])


@tagged("post_install", "-at_install")
class TestTheReportWritesNothing(DisposalCase):
    """Fingerprinted, because "it looks like a read" is not evidence.

    Report 19 in the Vendra repository made the argument and it holds here: a
    report that quietly repairs what it finds can never honestly report zero,
    and the run after the repair reports a cleanliness the report itself
    manufactured.
    """

    def _fingerprint(self):
        # Flush FIRST, on both sides, and run the precommit callbacks with
        # it. A stored compute left pending in `tocompute` is written by the
        # next flush, so fingerprinting without one would let a genuine write
        # hide behind "it was pending anyway" on the way in and manufacture a
        # phantom write on the way out — handoff 09's lesson, applied to a
        # fingerprint instead of to a freeze. The precommit run is the same
        # argument for tracking: a tracked write does not reach
        # `mail_tracking_value` until commit, so without it a report that
        # wrote a tracked field would fingerprint as having written nothing.
        self._flush_tracking()
        self.env.invalidate_all()
        marks = []
        for table in ("nrs_asset", "mail_message", "mail_tracking_value"):
            self.env.cr.execute(
                "SELECT count(*), md5(coalesce(string_agg(t::text, '|' "
                "ORDER BY t.id), '')) FROM %s t" % table)
            marks.append(self.env.cr.fetchone())
        return marks

    def test_the_report_changes_nothing(self):
        self._bare_disposal()
        self._documented_disposal()
        undated = self._asset()
        undated.write({"state": "disposed"})
        self._flush_tracking()

        before = self._fingerprint()
        report = self.Asset.disposal_report(WIDE_FROM, WIDE_TO)
        after = self._fingerprint()

        self.assertTrue(report["rows"], "the fixture produced no rows, so "
                                        "this test proved nothing")
        self.assertEqual(
            before, after,
            "disposal_report modified the database. It is a report: it must "
            "not repair, backfill or stamp anything it finds.")

    def test_running_it_twice_gives_the_same_answer(self):
        """The other half of the same guarantee, from the outside. A report
        that repaired on the first pass would come back cleaner on the
        second, and the diff would be the repair."""
        self._bare_disposal()
        undated = self._asset()
        undated.write({"state": "disposed"})

        self._flush_tracking()
        first = self.Asset.disposal_report(WIDE_FROM, WIDE_TO)
        second = self.Asset.disposal_report(WIDE_FROM, WIDE_TO)
        self.assertEqual(first, second)


@tagged("post_install", "-at_install")
class TestApprovingADisposal(DisposalCase):

    def test_the_approver_is_who_pressed_the_button(self):
        """Not a name typed into a field. Since handoff 08 an API client acts
        as its own `res.users`, so an approval made through an integration
        names that integration rather than `Administrator`."""
        asset = self._bare_disposal()
        asset.action_approve_disposal()
        self.assertEqual(asset.disposal_approved_by.id, self.env.uid)
        self.assertTrue(asset.disposal_approved_date)
        self.assertNotIn("no_approver",
                         self._row_for(self._report(), asset)["findings"])

    def test_it_posts_to_the_chatter(self):
        asset = self._bare_disposal()
        before = len(asset.message_ids)
        asset.action_approve_disposal()
        self.assertGreater(len(asset.message_ids), before)

    def test_it_refuses_an_asset_that_is_not_disposed(self):
        """An approval recorded against an asset still on the register is an
        approval of nothing."""
        asset = self._asset()
        with self.assertRaises(UserError):
            asset.action_approve_disposal()

    def test_it_refuses_to_overwrite_an_existing_approval(self):
        """Silently replacing an approver erases the only record of who
        authorised the disposal. A genuine correction is made on the form,
        where the field is tracked and the change leaves a trail."""
        asset = self._bare_disposal()
        asset.action_approve_disposal()
        with self.assertRaises(UserError):
            asset.action_approve_disposal()

    def test_condemning_records_a_date(self):
        """`action_condemn` wrote a condition and a state and nothing else,
        so every disposal made through the Odoo button arrived undated."""
        asset = self._asset()
        asset.action_condemn()
        self.assertEqual(asset.state, "disposed")
        self.assertTrue(asset.disposal_date)
        self.assertFalse(
            asset.disposal_approved_by,
            "condemning an asset is not authorising its disposal — recording "
            "the person who pressed the button as the approving authority "
            "would manufacture the evidence an auditor is asking for")


@tagged("post_install", "-at_install")
class TestTheSapMapping(DisposalCase):
    """SAP takes two words for a disposal instruction and Cadra records eight
    routes. A route added later without a mapping would silently fall through
    to `disposal`, so a scrapping would post to SAP as a disposal with
    nothing in Cadra to reconcile against."""

    def _selection_values(self):
        return [
            key for key, _label in
            self.Asset._fields["disposal_method"].selection
        ]

    def test_every_method_maps(self):
        for value in self._selection_values():
            self.assertIn(
                value, SAP_DISPOSAL_TYPE,
                "disposal_method %r has no SAP disposal_type mapping — it "
                "would be sent to SAP as the default" % value)

    def test_every_mapping_is_a_word_sap_accepts(self):
        """The SAP requirements document §4.2 defines `disposal_type` as
        `disposal` or `retirement`. Anything else is a payload SAP rejects,
        discovered on a live retirement."""
        for value in SAP_DISPOSAL_TYPE.values():
            self.assertIn(value, ("disposal", "retirement"))

    def test_the_default_is_what_sap_has_always_received(self):
        """Adding the field must not change a single event already in
        flight: an asset with no recorded method sends the literal the
        payload hard-coded before it existed."""
        self.assertEqual(DEFAULT_SAP_DISPOSAL_TYPE, "disposal")
        self.assertEqual(
            SAP_DISPOSAL_TYPE.get(False, DEFAULT_SAP_DISPOSAL_TYPE),
            "disposal")

    def test_the_report_publishes_the_sap_type(self):
        asset = self._documented_disposal(disposal_method="scrapped")
        row = self._row_for(self._report(), asset)
        self.assertEqual(row["sap_disposal_type"], "retirement")
