"""The access-change report states a boundary it measured, and writes nothing.

Handoff 23, specification §13.4's fourth standard report. The report in
`myservice_api/models/audit_access.py` makes an unusual claim for a report:
that the thing an auditor asked for **cannot be produced from this database
at all**. Group grants and removals leave no trace, so the report says so on
its own face instead of returning an empty table that reads like a quiet
quarter.

A claim of that shape is only worth what its evidence is worth, so these
tests are organised around the ways it could rot:

1. **The boundary is a measurement, not a sentence.** `res_groups_users_rel`
   having exactly two integer columns is the entire argument. If the table
   grows a `create_date` next year, the report is meant to notice and switch
   to `partial` rather than keep publishing a limitation that has stopped
   being true. So the test asserts the SCHEMA FACT — `{'gid', 'uid'}` — and
   not merely that `membership_audit_columns` came back empty. An empty list
   is also what a broken query returns.

2. **`partial` must be proved reachable.** It is the whole future-proofing
   mechanism and, on every deployment today, it is dead code. Dead code that
   nobody has ever executed is not future-proofing, it is a comment. All
   three of its disjuncts are driven directly here.

3. **`group_changes_in_period` is a STRUCTURAL zero.** It is in the payload
   so that a consumer counting access changes sees the absence rather than
   inferring it from a key that is not there. A key that vanishes when the
   count is zero is exactly the defect.

4. **It writes nothing.** Fingerprinted by md5 over the five tables it could
   plausibly touch, before and after, with the precommit callbacks run on
   both sides so a tracked write cannot hide behind "tracking rows are not
   written until commit".

**Every assertion about events and roster membership here is SCOPED to
records this test created.** `myservice_api/tests` runs in CI after
`pytest tests/`, which COMMITS fixtures of its own — users included, since a
provisioned API client is a `res.users`. An unscoped count would be an
assertion about whatever the tenant happened to hold, which is the same
defect the report exists to remove, turned on its own tests. See
`test_disposal_report.py::TestTheSapPositionIsStatedOnce` for the time this
was learned the hard way.

Run with:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --test-enable \\
      --test-tags /myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098

TransactionCase throughout, so `--workers=0` is not needed for this file —
but the HttpCase suites alongside it in this module do need it, so the run
above is given in the form that works for all of them.
"""
import uuid
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.myservice_api.models.audit_access import (
    ACCESS_COVERAGE_NONE,
    ACCESS_COVERAGE_PARTIAL,
    ACCESS_EVENT_CREATED,
    ACCESS_EVENT_MODIFIED,
    _STRUCTURAL_LOGINS,
)

#: Wide enough to hold anything a test dates deliberately. Tests that are
#: ABOUT a boundary name their own period instead of using this.
WIDE_FROM = date(2000, 1, 1)
WIDE_TO = date(2099, 12, 31)

#: A period that is certainly in the past and certainly holds nothing this
#: test did not put there.
DEAD_FROM = date(2001, 1, 1)
DEAD_TO = date(2001, 12, 31)

#: The columns whose presence on the membership table would turn `none` into
#: something better. Mirrors the set `access_change_fidelity` intersects on.
AUDIT_COLUMNS = {'create_date', 'create_uid', 'write_date', 'write_uid'}


class AccessReportCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Users = self.env["res.users"]
        self.marker = uuid.uuid4().hex[:10]

    # ── fixtures ────────────────────────────────────────────────────

    def _user(self, **vals):
        """A real, non-structural account this test owns.

        `login` carries the marker so every assertion below can be scoped to
        it, and says `audit-test` on its face so that a row left behind in a
        tenant by an aborted run is self-identifying rather than looking
        like somebody's account.
        """
        seq = len(getattr(self, "_made", []) or [])
        login = "audit-test-%s-%d@example.invalid" % (self.marker, seq)
        user = self.Users.create(dict(
            {"name": "Audit access test %s" % login, "login": login}, **vals))
        self._made = (getattr(self, "_made", []) or []) + [user]
        return user

    # ── plumbing ────────────────────────────────────────────────────

    def _flush_tracking(self):
        """Materialise the chatter tracking rows this transaction would write.

        Odoo 19 registers `_track_finalize` on `cr.precommit`, so tracking
        values reach `mail_tracking_value` at COMMIT and not at flush. A
        `TransactionCase` never commits, so a fingerprint taken without this
        would be blind to exactly the writes it is meant to catch. Odoo's own
        `MailCommon.flush_tracking` idiom.
        """
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.flush_all()

    def _backdate(self, records, column, moment):
        """Move an ORM-managed audit stamp, in SQL, because the ORM will not.

        `create_date` and `write_date` are set from `cr.now()`, which is
        cached for the whole transaction — so every record a TransactionCase
        creates carries the SAME stamp and no amount of ORM writing will
        separate them. Testing a period boundary or the two-second rule
        therefore has to go under the ORM. Flush first so the row exists;
        invalidate after so the cache does not keep serving the old value.
        """
        self.assertIn(column, ("create_date", "write_date"))
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE %s SET %s = %%s WHERE id IN %%s" % (records._table, column),
            (moment, tuple(records.ids)))
        self.env.invalidate_all()

    def _report(self, date_from=WIDE_FROM, date_to=WIDE_TO):
        return self.Users.access_change_report(date_from, date_to)

    def _events_for(self, report, user):
        """Only this test's events. Never the whole period."""
        return [e for e in report["events"] if e["user_id"] == user.id]

    def _roster_for(self, report, user):
        for row in report["roster"]:
            if row["user_id"] == user.id:
                return row
        return None


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheReportWritesNothing(AccessReportCase):
    """Fingerprinted, because "it looks like a read" is not evidence.

    The argument is the disposal report's and it holds harder here: this
    report walks every user in the tenant and touches `create_uid`,
    `write_uid`, a non-stored `full_name` compute on `res.groups` and a
    per-user search on `myservice.api.client`. Any one of those is a place a
    stored compute could be triggered into writing. A report that quietly
    repairs what it finds can never honestly report zero, and the run after
    the repair reports a cleanliness it manufactured itself.

    Five tables, because those are the five a read of this shape could
    plausibly disturb: the accounts, their group membership, the two chatter
    tables a tracked write would land in, and the parameter table the sibling
    report reads.
    """

    #: table -> the ORDER BY that makes `string_agg` deterministic.
    #: `res_groups_users_rel` has no `id` column — that absence is the
    #: report's central finding — so it is ordered on its own two columns.
    FINGERPRINTED = {
        "res_users": "t.id",
        "res_groups_users_rel": "t.gid, t.uid",
        "res_groups": "t.id",
        # The report searches this model to label a roster row as an
        # integration; a write on that path would otherwise be invisible.
        "myservice_api_client": "t.id",
        "mail_message": "t.id",
        "mail_tracking_value": "t.id",
        "ir_config_parameter": "t.id",
    }

    def _fingerprint(self):
        # Flush FIRST, on both sides, and run the precommit callbacks with
        # it. A stored compute left pending in `tocompute` is written by the
        # next flush, so fingerprinting without one would let a genuine write
        # hide behind "it was pending anyway" on the way in and manufacture a
        # phantom write on the way out.
        self._flush_tracking()
        self.env.invalidate_all()
        marks = {}
        for table, order in self.FINGERPRINTED.items():
            self.env.cr.execute(
                "SELECT count(*), md5(coalesce(string_agg(t::text, '|' "
                "ORDER BY %s), '')) FROM %s t" % (order, table))
            marks[table] = self.env.cr.fetchone()
        return marks

    def test_the_fingerprint_notices_a_write(self):
        """The NEGATIVE CONTROL, and without it the two tests below are
        decoration.

        A `FINGERPRINTED` dict naming tables that do not exist, or an
        `assertEqual` comparing two things neither of which moves, produces
        an identical before and after on every run and looks exactly like a
        proof that the report is read-only. Criterion 7 of the handoff asks
        for guards proved to fail before they pass; the CI series guard in
        this same branch got one and this did not, until the verification
        pass said so.

        So: mutate one row in each fingerprinted table the report could
        plausibly touch, and require the mark to move. If this test ever
        passes vacuously, the two below are worthless.
        """
        before = self._fingerprint()

        user = self._user()
        self._flush_tracking()
        after_user = self._fingerprint()
        self.assertNotEqual(
            before["res_users"], after_user["res_users"],
            "creating a user did not move the `res_users` fingerprint, so "
            "this fingerprint cannot detect a write and every read-only "
            "claim resting on it is unproven")

        # The field the model itself probes for, so this test is not the
        # place Odoo 19's `groups_id` -> `group_ids` rename gets pinned.
        groups_field = self.env["res.users"]._access_groups_field()
        user.write({groups_field: [(4, self.env.ref(
            "base.group_no_one").id)]})
        self._flush_tracking()
        after_group = self._fingerprint()
        self.assertNotEqual(
            after_user["res_groups_users_rel"],
            after_group["res_groups_users_rel"],
            "a group grant did not move the membership fingerprint")

        self.env["ir.config_parameter"].sudo().set_param(
            "cadra.fingerprint_probe_%s" % self.marker, "1")
        self._flush_tracking()
        self.assertNotEqual(
            after_group["ir_config_parameter"],
            self._fingerprint()["ir_config_parameter"],
            "a parameter write did not move the parameter fingerprint")

    def test_the_report_changes_nothing(self):
        created = self._user()
        modified = self._user()
        modified.write({"name": "Audit access test renamed %s" % self.marker})
        self._flush_tracking()

        before = self._fingerprint()
        report = self._report()
        after = self._fingerprint()

        self.assertTrue(
            self._events_for(report, created),
            "the fixture produced no event for the account this test "
            "created, so this test proved nothing about a report that ran "
            "over rows")
        self.assertEqual(
            before, after,
            "access_change_report modified the database. It is a report over "
            "the identity register: it must not stamp, backfill or repair "
            "anything it walks past. Compare the per-table md5s above to see "
            "which table moved.")

    def test_the_fidelity_block_changes_nothing(self):
        """Measured separately because it is the half that runs raw SQL.

        `access_change_fidelity` reaches past the ORM into
        `information_schema`, `mail_tracking_value` and `ir_logging`. Raw SQL
        is exactly where an accidental write would not look like one.
        """
        self._user()
        self._flush_tracking()

        before = self._fingerprint()
        fidelity = self.Users.access_change_fidelity()
        after = self._fingerprint()

        self.assertTrue(fidelity["notes"], "fidelity came back empty")
        self.assertEqual(
            before, after,
            "access_change_fidelity modified the database")

    def test_running_it_twice_gives_the_same_answer(self):
        """The same guarantee from the outside.

        A report that repaired on the first pass would come back cleaner on
        the second, and the diff between the two runs would BE the repair —
        visible here even if it landed in a table the fingerprint does not
        cover.
        """
        self._user()
        self._flush_tracking()

        first = self._report()
        second = self._report()
        self.assertEqual(
            first, second,
            "two consecutive runs of access_change_report disagreed, which "
            "means the first one changed something the second one read")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheBoundaryIsMeasured(AccessReportCase):
    """The finding, asserted as a schema fact rather than as an empty list.

    `membership_audit_columns == []` is necessary and nowhere near
    sufficient: a query against the wrong table name, a query returning no
    rows because `information_schema` was spelled wrong, and a membership
    table that genuinely carries no audit columns are three different worlds
    that produce the same empty list. Only one of them means what the report
    says it means.
    """

    def test_the_membership_table_is_two_integer_columns(self):
        """`res_groups_users_rel` is `(gid, uid)` and that is the whole table.

        This single fact is the load-bearing claim of the entire report: a
        grant writes a row that records neither WHEN it happened nor WHO made
        it, so no query against this database can produce a grant history.

        If this assertion ever fails, the report is not broken — the WORLD
        changed, and `audit_access.py` must be rewritten to read whatever
        the new columns hold instead of continuing to publish a limitation
        that has stopped being true.
        """
        columns = self.Users._access_membership_table_columns()
        self.assertEqual(
            columns, {"gid", "uid"},
            "res.users.group_ids' relation table no longer has exactly the "
            "two columns the access-change report's entire boundary rests "
            "on; it now has %s. If audit columns have appeared, the report "
            "must start READING them — `_access_change_coverage` will "
            "already flip to `partial`, but the events themselves are still "
            "derived from create/write stamps only and would understate "
            "what the database now holds." % sorted(columns))
        self.assertFalse(
            columns & AUDIT_COLUMNS,
            "the membership table has grown audit columns: %s"
            % sorted(columns & AUDIT_COLUMNS))

    def test_the_empty_audit_column_list_came_from_that_measurement(self):
        """`fidelity` publishes the derived answer; the test ties it to the
        measurement above so an empty list cannot come from a broken query."""
        fidelity = self.Users.access_change_fidelity()
        self.assertEqual(
            fidelity["membership_audit_columns"], [],
            "membership_audit_columns is non-empty, so the report is "
            "claiming a grant history exists while still not reading it")
        columns = self.Users._access_membership_table_columns()
        self.assertEqual(
            fidelity["membership_audit_columns"],
            sorted(columns & AUDIT_COLUMNS),
            "the published list is not the intersection of the measured "
            "columns with the audit columns, so it is not derived from the "
            "measurement it claims to be derived from")

    def test_the_note_names_the_table_and_its_columns(self):
        """A boundary an auditor cannot check is a boundary they have to take
        on trust, which is the thing INT-10 exists to argue against. The note
        names the relation and lists what it holds, so the reader can run the
        same query."""
        note = self.Users.access_change_fidelity()["notes"]["membership"]
        self.assertIn("res_groups_users_rel", note)
        self.assertIn("gid", note)
        self.assertIn("uid", note)
        self.assertIn("no timestamp and no actor", note)

    def test_the_groups_field_is_group_ids_and_carries_no_tracking(self):
        """Odoo 19 renamed `groups_id` to `group_ids`, and neither name is
        assumed — `_access_groups_field` probes `_fields`. The tracking half
        is the second of the four claims: with no `tracking=` there is no
        chatter history to roll back the way the register snapshot rolls back
        `custodian_id`."""
        self.assertEqual(
            self.Users._access_groups_field(), "group_ids",
            "the groups field is no longer `group_ids`; the report's probe "
            "found something else and every note below quotes the wrong name")
        fidelity = self.Users.access_change_fidelity()
        self.assertEqual(fidelity["groups_field"], "group_ids")
        self.assertIs(
            fidelity["groups_field_tracked"], False,
            "res.users.group_ids has acquired tracking=. The report will now "
            "report `partial`, which is correct, but it still does not READ "
            "mail.tracking.value — so it is understating what the database "
            "holds and audit_access.py owes the reader that history.")

    def test_the_tracking_and_logging_counts_are_integers_not_claims(self):
        """Both are COUNTED on every request. A limitation published as a
        constant is a limitation that goes stale silently, which is the whole
        argument for re-measuring."""
        fidelity = self.Users.access_change_fidelity()
        self.assertIsInstance(fidelity["tracking_rows"], int)
        self.assertIsInstance(fidelity["logging_rows"], int)
        self.assertGreaterEqual(fidelity["tracking_rows"], 0)
        self.assertGreaterEqual(fidelity["logging_rows"], 0)
        self.assertIn(
            str(fidelity["tracking_rows"]), fidelity["notes"]["tracking"],
            "the tracking note does not quote the number it measured, so a "
            "reader cannot tell a measurement from a boilerplate sentence")
        self.assertIn(str(fidelity["logging_rows"]),
                      fidelity["notes"]["logging"])


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheStructuralZero(AccessReportCase):
    """`group_changes_in_period` is 0 and it is PRESENT.

    A count that disappears when it is zero is how a consumer ends up
    inferring "the key is missing, so this report does not cover group
    changes" — or worse, not noticing at all. The zero is the statement.
    """

    def test_group_changes_in_period_is_present_and_zero(self):
        summary = self._report()["summary"]
        self.assertIn(
            "group_changes_in_period", summary,
            "the structural zero is missing from the summary. A consumer "
            "counting access changes now sees no key rather than a zero, and "
            "the absence of group-change reporting becomes something they "
            "have to infer.")
        self.assertEqual(summary["group_changes_in_period"], 0)
        self.assertIsInstance(summary["group_changes_in_period"], int)

    def test_it_stays_zero_when_the_period_is_full_of_events(self):
        """The zero is structural, not incidental. A period with real access
        events still reports no group changes, because there is nothing to
        report them FROM — not because the period was quiet."""
        self._user()
        self._user()
        self._flush_tracking()
        report = self._report()
        self.assertTrue(report["events"], "the fixture produced no events")
        self.assertEqual(report["summary"]["group_changes_in_period"], 0)

    def test_the_summary_carries_the_counts_a_consumer_branches_on(self):
        report = self._report()
        for key in ("accounts", "accounts_active", "events_in_period",
                    "group_changes_in_period", "coverage", "statement"):
            self.assertIn(key, report["summary"])
        self.assertEqual(report["summary"]["events_in_period"],
                         len(report["events"]))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheCoverageEnum(AccessReportCase):
    """All three branches, driven directly with synthetic inputs.

    Driven directly and not through the report on purpose. Two of the three
    branches are unreachable on any tenant that exists today — `partial`
    needs an access history nobody has, and the distinction between the two
    `none` wordings needs a period both empty and non-empty. Waiting for a
    deployment to exercise them is waiting forever, and `partial` is the
    entire future-proofing mechanism: if it has never executed, it is a
    comment rather than a feature.

    Branch on `coverage`, never on `statement` — so the enum is asserted
    first in every case and the wording second.
    """

    def _fidelity(self, **overrides):
        """The shape `_access_change_coverage` actually reads, and only that.

        Deliberately a hand-built dict rather than the real fidelity block: a
        tenant that grew one tracking row would otherwise flip these tests to
        `partial` and they would stop testing what they say they test.
        """
        return dict({
            "groups_field_tracked": False,
            "membership_audit_columns": [],
            "tracking_rows": 0,
        }, **overrides)

    def test_no_history_and_no_events_says_nothing_happened_either(self):
        """`none` with the quiet-period wording. The distinction this sentence
        carries is the one the disposal report's `empty` makes: the table
        below is empty AND the record could not have held anything anyway,
        and a reader must not be able to read one as the other."""
        coverage, statement = self.Users._access_change_coverage(
            [], self._fidelity())
        self.assertEqual(coverage, ACCESS_COVERAGE_NONE)
        self.assertIn(
            "no account was created", statement,
            "an empty period is being described with the wording written for "
            "a period that had events")
        self.assertIn("This report can speak for NO period", statement)

    def test_no_history_but_real_events_counts_them(self):
        """`none` with the other wording. The coverage verdict is unchanged —
        accounts created is not a grant history — but the sentence must not
        tell an auditor that nothing happened when two things did."""
        events = [{"event": ACCESS_EVENT_CREATED},
                  {"event": ACCESS_EVENT_MODIFIED}]
        coverage, statement = self.Users._access_change_coverage(
            events, self._fidelity())
        self.assertEqual(coverage, ACCESS_COVERAGE_NONE)
        self.assertIn(
            "2 event(s)", statement,
            "the statement does not count the events it is published above")
        self.assertNotIn("no account was created", statement)

    def test_tracking_on_the_groups_field_reaches_partial(self):
        """The day somebody adds `tracking=True`. First of three disjuncts."""
        coverage, statement = self.Users._access_change_coverage(
            [], self._fidelity(groups_field_tracked=True))
        self.assertEqual(
            coverage, ACCESS_COVERAGE_PARTIAL,
            "`partial` is unreachable, which makes the report's entire "
            "future-proofing story a comment rather than a mechanism")
        self.assertIn("grown an access history", statement)
        self.assertIn("NOT", statement)

    def test_audit_columns_on_the_membership_table_reach_partial(self):
        """Second disjunct: the schema itself grew the columns."""
        coverage, _statement = self.Users._access_change_coverage(
            [], self._fidelity(membership_audit_columns=["create_date"]))
        self.assertEqual(coverage, ACCESS_COVERAGE_PARTIAL)

    def test_tracking_rows_appearing_reach_partial(self):
        """Third disjunct: an audit module got installed and started writing.

        Driven with events present as well, because `partial` must win over
        both `none` wordings rather than being reachable only in the quiet
        case.
        """
        coverage, statement = self.Users._access_change_coverage(
            [{"event": ACCESS_EVENT_CREATED}],
            self._fidelity(tracking_rows=5))
        self.assertEqual(coverage, ACCESS_COVERAGE_PARTIAL)
        self.assertNotIn("1 event(s)", statement)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheEventsAreEvidenced(AccessReportCase):
    """What the report DOES say, scoped to accounts this test created.

    Every assertion filters on `user_id`. The tenant this runs against holds
    other accounts, `pytest tests/` commits more of them before this suite
    runs in CI, and an assertion over `len(report["events"])` would be an
    assertion about the fixture debris of a different suite.
    """

    def test_a_created_account_is_an_exact_event(self):
        user = self._user()
        self._flush_tracking()
        today = fields.Datetime.now().date()
        report = self._report(today - timedelta(days=1),
                              today + timedelta(days=1))

        events = self._events_for(report, user)
        created = [e for e in events if e["event"] == ACCESS_EVENT_CREATED]
        self.assertEqual(
            len(created), 1,
            "an account created inside the period produced %d create events"
            % len(created))
        event = created[0]
        self.assertEqual(
            event["precision"], "exact",
            "an account creation is the one access event whose timestamp and "
            "actor are its OWN rather than a last-write smear; publishing it "
            "as `last_write_only` would understate the only precise evidence "
            "this report has")
        self.assertEqual(event["login"], user.login)
        self.assertEqual(event["actor"]["id"], self.env.uid)
        self.assertEqual(event["evidence"],
                         "res_users.create_date / create_uid")
        self.assertEqual(event["at"], user.create_date)

    def test_that_same_account_is_absent_from_a_period_that_excludes_it(self):
        """The other half, and the half that catches a report that ignores
        its own arguments. A create event that appears in EVERY period is not
        filtered at all, and would pass the test above every time."""
        user = self._user()
        self._flush_tracking()
        report = self._report(DEAD_FROM, DEAD_TO)
        self.assertEqual(
            self._events_for(report, user), [],
            "an account created today appears as an event in a period ending "
            "in 2001, so access_change_report is not filtering on its period")

    def test_the_roster_carries_the_account_in_every_period(self):
        """The roster is PRESENT TENSE and is deliberately not period
        filtered — it answers "who has access now", the question an auditor
        asks immediately after the one about changes. It must therefore
        appear even in a period that holds none of its events."""
        user = self._user()
        self._flush_tracking()
        row = self._roster_for(self._report(DEAD_FROM, DEAD_TO), user)
        self.assertIsNotNone(
            row, "the roster dropped a live account because its create date "
                 "fell outside the requested period; the roster is current "
                 "state, not history")
        self.assertEqual(row["login"], user.login)
        self.assertTrue(row["active"])
        self.assertIs(row["is_api_client"], False)
        self.assertIsInstance(row["groups"], list)

    def test_an_untouched_account_reports_no_modification(self):
        """The two-second rule.

        Odoo stamps `create_date` and `write_date` in the same transaction —
        and in a TransactionCase `cr.now()` is cached, so they are identical
        to the microsecond. Without the tolerance every account in the
        database would report an `account_modified` event it never had, and
        the report's most-used number would be noise.
        """
        user = self._user()
        self._flush_tracking()
        today = fields.Datetime.now().date()
        report = self._report(today - timedelta(days=1),
                              today + timedelta(days=1))

        events = self._events_for(report, user)
        self.assertEqual(
            [e["event"] for e in events], [ACCESS_EVENT_CREATED],
            "an account that was created and never touched again reported "
            "%s. `write_date` equals `create_date` on a fresh row, so any "
            "`account_modified` here is the two-second tolerance failing and "
            "every account in the tenant is now reported as modified."
            % [e["event"] for e in events])

    def test_a_genuinely_later_write_is_a_last_write_only_event(self):
        """The tolerance must not swallow a real modification either.

        `create_date` is pushed an hour back in SQL — the ORM cannot separate
        the two stamps inside one transaction — so the row looks like an
        account created an hour ago and written since, which is what a real
        modification looks like.
        """
        user = self._user()
        self._flush_tracking()
        self._backdate(user, "create_date",
                       fields.Datetime.now() - timedelta(hours=1))

        today = fields.Datetime.now().date()
        report = self._report(today - timedelta(days=1),
                              today + timedelta(days=1))
        events = self._events_for(report, user)
        modified = [e for e in events if e["event"] == ACCESS_EVENT_MODIFIED]
        self.assertEqual(
            len(modified), 1,
            "an account written an hour after it was created produced no "
            "`account_modified` event, so the two-second tolerance is "
            "swallowing real modifications")
        self.assertEqual(
            modified[0]["precision"], "last_write_only",
            "a modification event must publish its own imprecision: one "
            "write stamp covers every change ever made to the row, so this "
            "is the MOST RECENT change and not a list of them")
        self.assertEqual(modified[0]["evidence"],
                         "res_users.write_date / write_uid")

    def test_the_model_sorts_by_time(self):
        """Chronological — but only out of the MODEL, and say so.

        This asserted chronological order under the title "a report an
        auditor reads top to bottom", which was a claim about the published
        report and was not true of it: `v1_audit.py` re-sorts by ascending
        account id before publishing, because the cursor walks ascending ids
        and a time-ordered list cannot be paged honestly with the cursor
        this API issues. `/reports/disposals` makes the same trade.

        So this test now says what it actually checks — the model's order —
        and `tests/test_audit_logs.py` asserts the API's, which is the one a
        consumer sees. A test whose title describes a different layer from
        its assertion is how a contract comes to have two answers.
        """
        self._user()
        self._user()
        self._flush_tracking()
        events = self._report()["events"]
        self.assertEqual(
            [e["at"] for e in events], sorted(e["at"] for e in events),
            "the model no longer returns events in chronological order")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestStructuralUsersAreExcluded(AccessReportCase):
    """Odoo's own plumbing accounts are not people and not integrations.

    Four rows of framework internals at the top of every answer is how a
    report teaches its reader to skim, and `__system__` appearing in a roster
    of "who has access" is a question nobody asked. The exclusion is asserted
    against accounts that genuinely EXIST, so the test cannot pass by the
    accident of them being absent from this tenant.
    """

    def test_the_system_account_exists_and_is_still_excluded(self):
        root = self.env.ref("base.user_root")
        self.assertEqual(
            root.login, "__system__",
            "base.user_root is no longer `__system__`, so `_STRUCTURAL_LOGINS` "
            "is filtering on a login that no longer exists and the ORM's own "
            "uid 1 is now in the roster")
        report = self._report()
        self.assertIsNone(
            self._roster_for(report, root),
            "uid 1 is in the access roster")
        self.assertEqual(self._events_for(report, root), [])

    def test_none_of_the_structural_logins_appears_anywhere(self):
        report = self._report()
        roster_logins = {r["login"] for r in report["roster"]}
        event_logins = {e["login"] for e in report["events"]}
        for login in ("__system__", "public", "portaltemplate"):
            self.assertNotIn(
                login, roster_logins,
                "`%s` is a framework account, not somebody with access, and "
                "it is in the roster" % login)
            self.assertNotIn(login, event_logins)
        # The constant is the contract; the three above are the ones §13.4
        # names. Assert the whole tuple so a fifth added later is covered.
        self.assertFalse(
            roster_logins & set(_STRUCTURAL_LOGINS),
            "structural accounts in the roster: %s"
            % sorted(roster_logins & set(_STRUCTURAL_LOGINS)))

    def test_the_exclusion_is_stated_in_the_fidelity_notes(self):
        """A filtered row that is not declared is a row the reader does not
        know was filtered, which is the same defect as a silently dropped
        field on a write."""
        note = self.Users.access_change_fidelity()["notes"]["structural_users"]
        for login in _STRUCTURAL_LOGINS:
            self.assertIn(login, note)

    def test_a_deactivated_account_is_still_reported(self):
        """`active_test` is off on purpose. A deactivated account that held
        access during the period is precisely what an auditor is asking
        about, and filtering it would turn "who had access" into "who has
        access", silently."""
        user = self._user()
        user.action_archive()
        self._flush_tracking()
        row = self._roster_for(self._report(), user)
        self.assertIsNotNone(
            row, "a deactivated account vanished from the roster; an account "
                 "that was switched off during the period is the one an "
                 "auditor most wants to see")
        self.assertIs(row["active"], False)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThePeriodBounds(AccessReportCase):
    """Both bounds inclusive, and the closing bound covers its whole day.

    A period given as two dates that silently drops everything after
    midnight on the closing date is the quietest possible way for a report to
    be wrong: it is right for most of the rows, and the ones it loses are the
    ones nobody counted.
    """

    #: Late enough on the closing day that a naive midnight bound loses it.
    LATE = datetime(2021, 6, 30, 23, 30, 0)

    def _user_at(self, moment):
        """An account whose create and write stamps both sit at `moment`.

        Both, so the two-second rule produces no `account_modified` event and
        the test is about the period bound and nothing else.
        """
        user = self._user()
        self._flush_tracking()
        self._backdate(user, "create_date", moment)
        self._backdate(user, "write_date", moment)
        return user

    def test_an_event_at_2330_on_the_closing_day_is_included(self):
        user = self._user_at(self.LATE)
        report = self._report(date(2021, 6, 1), date(2021, 6, 30))
        events = self._events_for(report, user)
        self.assertEqual(
            [e["event"] for e in events], [ACCESS_EVENT_CREATED],
            "an account created at 23:30 on the closing date of the period "
            "was dropped. The bound is documented as inclusive of the whole "
            "closing day; a midnight bound loses every event after 00:00:00 "
            "on the last day and loses them silently.")

    def test_an_event_on_the_opening_day_is_included(self):
        user = self._user_at(datetime(2021, 6, 1, 0, 0, 1))
        report = self._report(date(2021, 6, 1), date(2021, 6, 30))
        self.assertEqual(
            [e["event"] for e in self._events_for(report, user)],
            [ACCESS_EVENT_CREATED],
            "the opening bound is exclusive; it is documented as inclusive")

    def test_an_event_the_next_day_is_excluded(self):
        """The bound has to bite in the other direction too, or "inclusive of
        the whole closing day" is indistinguishable from "no upper bound"."""
        user = self._user_at(datetime(2021, 7, 1, 0, 30, 0))
        report = self._report(date(2021, 6, 1), date(2021, 6, 30))
        self.assertEqual(
            self._events_for(report, user), [],
            "an account created after midnight on the day AFTER the closing "
            "date is inside the period, so the upper bound is not bounding")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheStatementIsNotTranslated(AccessReportCase):
    """A published payload string does not move with the caller's language.

    `statement` is part of an API response an integration stores, diffs and
    reconciles against last quarter's run. Running it through `_()` would
    make the same period produce different bytes depending on who asked,
    which is the property a reconciliation cannot survive. The model says so
    in a comment; this is the test that makes the comment enforceable.

    What this can and cannot prove, said plainly: Odoo's `_()` returns a
    plain `str`, so no type check can distinguish a translated string from an
    untranslated one. What it CAN prove is that the bytes do not change with
    `lang`, and that the exact published wording is still the wording. On a
    tenant with no second language loaded the first half is weak; the second
    half is not, and together they catch the realistic regression, which is
    somebody wrapping these literals in `_()` and a translation catalogue
    arriving later.
    """

    def _fidelity(self):
        return {"groups_field_tracked": False,
                "membership_audit_columns": [], "tracking_rows": 0}

    def test_the_statement_is_a_plain_string(self):
        _coverage, statement = self.Users._access_change_coverage(
            [], self._fidelity())
        self.assertIs(
            type(statement), str,
            "the statement is not a plain `str` — a lazy translation object "
            "here would serialise differently, or not at all, depending on "
            "when the envelope is rendered")

    def test_the_statement_does_not_move_with_the_language(self):
        english = self.Users._access_change_coverage([], self._fidelity())
        other = self.env["res.users"].with_context(
            lang="fr_FR")._access_change_coverage([], self._fidelity())
        self.assertEqual(
            english, other,
            "the coverage statement changed with the acting user's language. "
            "It is a published API payload: a consumer cannot store, diff or "
            "reconcile a value that depends on who asked.")

    def test_the_published_wording_is_the_wording(self):
        """Pinned literally, because a translated string would first show up
        as a wording change and this is what makes that visible in a diff."""
        _c, empty = self.Users._access_change_coverage([], self._fidelity())
        self.assertIn(
            "Cadra holds no record of access changes, and no account was "
            "created or modified in this period either.", empty)
        _c, some = self.Users._access_change_coverage(
            [{"event": ACCESS_EVENT_CREATED}], self._fidelity())
        self.assertIn(
            "Cadra holds no record of group grants or removals", some)
        self.assertIn(
            "An `account_modified` row does not say which field changed.",
            some)

    def test_the_report_publishes_that_same_statement(self):
        """The statement a consumer receives is the one these tests pin, and
        not a second copy that drifted."""
        report = self._report()
        expected = self.Users._access_change_coverage(
            report["events"], report["fidelity"])
        self.assertEqual(report["summary"]["coverage"], expected[0])
        self.assertEqual(report["summary"]["statement"], expected[1])
