"""Every number on the FM dashboard is counted over the whole register.

Handoff 13 A1/A2. Four of the five KPIs were `len()` over the newest 500
open requests, standing beside `resolved_today`, which was a real
`search_count`. And `sla_pct` — a RATIO whose numerator and denominator
both came from inside that window — is published at
`GET /api/v1/fm/dashboard` wearing the name of a compliance figure.

These tests seed PAST the old 500-row window on purpose. Below it the fix
is invisible: a windowed count and a true count agree exactly when nothing
was withheld, which is why this defect survived four handoffs of people
reading the file.

`HttpCase`, because the controller reads `request.env` — and so it needs
`--workers=0`: `setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the committed `workers = 2` every test here errors in
setUpClass and the run cheerfully reports "0 failed".
"""
import json
from datetime import date, timedelta

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestFmDashboardCounts(CadraHttpCase):

    #: Past the 500-row window the KPIs used to be taken from. 300 of them
    #: are in one category and 220 in another, so the per-category SLA rows
    #: also straddle it.
    ALPHA_OPEN = 300
    ALPHA_OVERDUE = 150
    BETA_OPEN = 220

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["request.category"]
        cls.alpha = Category.create({"name": "H13 Alpha"})
        cls.beta = Category.create({"name": "H13 Beta"})

        stale = date.today() - timedelta(days=5)
        Request = cls.env["request.request"]
        # The default stage is an open one, so `closed` computes False.
        cls.alpha_requests = Request.create([
            {"name": "H13-A-%04d" % i,
             "category_id": cls.alpha.id,
             "priority": "3" if i < 40 else "1",
             "deadline_date": stale if i < cls.ALPHA_OVERDUE else False}
            for i in range(cls.ALPHA_OPEN)
        ])
        cls.beta_requests = Request.create([
            {"name": "H13-B-%04d" % i, "category_id": cls.beta.id}
            for i in range(cls.BETA_OPEN)
        ])
        cls.env.flush_all()

        cls.open_domain = [("closed", "=", False)]
        cls.overdue_domain = cls.open_domain + [
            ("deadline_date", "!=", False),
            ("deadline_date", "<", date.today()),
        ]

    def _payload(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/myservice/fm_dashboard/data",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertNotIn("error", body, body)
        return body["result"]

    # ── the KPIs ─────────────────────────────────────────────────────

    def test_the_seed_is_actually_past_the_old_window(self):
        """If this fails the rest of the file proves nothing.

        A windowed count and a true count are identical below the window.
        These assertions are only meaningful above it.
        """
        total_open = self.env["request.request"].search_count(self.open_domain)
        self.assertGreater(
            total_open, 500,
            "the old code took the newest 500 open requests; a register "
            "smaller than that cannot show the difference")

    def test_every_kpi_is_the_register_not_the_window(self):
        Request = self.env["request.request"]
        kpis = self._payload()["kpis"]

        self.assertEqual(kpis["open"], Request.search_count(self.open_domain))
        self.assertEqual(kpis["overdue"],
                         Request.search_count(self.overdue_domain))
        self.assertEqual(
            kpis["escalated"],
            Request.search_count(self.open_domain + [("priority", "=", "3")]))
        self.assertEqual(
            kpis["in_progress"],
            Request.search_count(
                self.open_domain + [("stage_id.code", "=", "in_progress")]))

        self.assertGreater(
            kpis["open"], 500,
            "this is the assertion the old code failed: it answered 500")

    def test_the_kpis_no_longer_disagree_with_each_other(self):
        """`resolved_today` was a real count and the four beside it were not.

        One payload, five numbers, one of them honest — and the honest one
        made the others look measured. The relationship that has to hold is
        that every subset is no larger than the whole.
        """
        kpis = self._payload()["kpis"]
        for part in ("overdue", "escalated", "in_progress"):
            self.assertLessEqual(
                kpis[part], kpis["open"],
                "%s counts a subset of the open requests; it cannot exceed "
                "them unless the two were measured differently" % part)

    # ── sla_pct ──────────────────────────────────────────────────────

    def test_sla_pct_is_a_ratio_of_two_true_counts(self):
        rows = {row["domain"]: row for row in self._payload()["sla_data"]}

        self.assertIn("H13 Alpha", rows)
        alpha = rows["H13 Alpha"]
        self.assertEqual(alpha["open"], self.ALPHA_OPEN)
        self.assertEqual(alpha["overdue"], self.ALPHA_OVERDUE)
        # 150 of 300 — the figure an NRS manager would read off this table.
        self.assertEqual(alpha["sla_pct"], 50)

        beta = rows["H13 Beta"]
        self.assertEqual(beta["open"], self.BETA_OPEN)
        self.assertEqual(beta["overdue"], 0)
        self.assertEqual(beta["sla_pct"], 100)

    def test_the_sla_table_sums_to_the_headline_beside_it(self):
        """The breakdown and the KPI are one response. Anyone who adds up
        the column and gets a different number concludes, reasonably, that
        the register is wrong."""
        payload = self._payload()
        self.assertEqual(
            sum(row["open"] for row in payload["sla_data"]),
            payload["kpis"]["open"])
        self.assertEqual(
            sum(row["overdue"] for row in payload["sla_data"]),
            payload["kpis"]["overdue"])
        self.assertEqual(
            sum(row["escalated"] for row in payload["sla_data"]),
            payload["kpis"]["escalated"])

    def test_the_workload_column_totals_the_open_requests(self):
        """Team workload was a tally over the same 500-row window."""
        payload = self._payload()
        self.assertEqual(
            sum(row["count"] for row in payload["team_workload"]),
            payload["kpis"]["open"],
            "these seeded rows are all unassigned, so the whole open count "
            "lands in one bucket and the top-10 truncation cannot hide it")

    # ── the lists are allowed to be windows; they are lists ──────────

    def test_the_lists_stay_lists_and_the_counts_stay_counts(self):
        payload = self._payload()
        self.assertLessEqual(len(payload["recent_requests"]), 30)
        self.assertLessEqual(len(payload["overdue_list"]), 50)
        self.assertGreater(payload["kpis"]["overdue"],
                           len(payload["overdue_list"]),
                           "the seed puts more overdue requests in the "
                           "register than the list shows — which is the "
                           "point: the LIST is a sample, the COUNT is not")

    def test_in_progress_counts_the_stage_that_actually_exists(self):
        """It filtered on stage code `progress`. No tenant has ever had one.

        cadra19, nrs19, gtb19, test19 and jaizbankplc all ship
        `new, triage, in_progress, resolved, closed`, and the string
        `'progress'` appears nowhere else in the repo — so this KPI was not
        merely windowed, it was structurally zero on every tenant, forever,
        sitting next to four numbers that moved.
        """
        Stage = self.env["request.stage"]
        self.assertFalse(
            Stage.search([("code", "=", "progress")]),
            "a stage with code 'progress' now exists; the old filter was "
            "right and this test is what is wrong")

        in_progress = Stage.search([("code", "=", "in_progress")], limit=1)
        self.assertTrue(in_progress, "no in_progress stage on this tenant")
        self.alpha_requests[:7].write({"stage_id": in_progress.id})
        self.env.flush_all()

        self.assertEqual(self._payload()["kpis"]["in_progress"],
                         self.env["request.request"].search_count(
                             self.open_domain
                             + [("stage_id.code", "=", "in_progress")]))
        self.assertGreaterEqual(self._payload()["kpis"]["in_progress"], 7)
