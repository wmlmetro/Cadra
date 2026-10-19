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

3. **`group_changes_in_period` is a real count that is PRESENT at zero.**
   It was a structural zero until handoff 24 gave this system a forward
   record (`myservice.api.access.change`), and the half of that argument
   which was always the point survives: the key is in the payload whether or
   not it is zero, so a consumer counting access changes sees the absence
   rather than inferring it from a key that is not there.

   The half that had to go is the ZERO ITSELF. A grant made inside the
   period is now counted, so a test pinning `== 0` over a live period would
   be pinning the absence of the feature — and would pass or fail on
   whatever the tenant happened to hold, which is the defect this suite is
   scoped against everywhere else. So the zero is asserted over a period the
   record cannot reach, and the counting is asserted as a DELTA across a
   grant the test makes itself. `coverage` is what tells a
   zero-because-nothing-happened from a zero-because-the-record-does-not-
   reach-this-period.

4. **It writes nothing.** Fingerprinted by md5 over the tables it could
   plausibly touch, before and after, with the precommit callbacks run on
   both sides so a tracked write cannot hide behind "tracking rows are not
   written until commit". The access record itself is one of them, and it is
   the one that matters most: a report that appended to the record it
   reports on would be manufacturing its own evidence.

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
from odoo.tests import tagged

from odoo.addons.myservice_api.models.access_change import (
    ACCESS_EVENT_GRANTED,
    ACCESS_EVENT_REMOVED,
    SYSTEM_ACTOR,
)
from odoo.addons.myservice_api.models.audit_access import (
    ACCESS_COVERAGE_NONE,
    ACCESS_COVERAGE_PARTIAL,
    ACCESS_COVERAGE_RECORDED,
    ACCESS_EVENT_CREATED,
    ACCESS_EVENT_MODIFIED,
    _STRUCTURAL_LOGINS,
)
from odoo.addons.myservice_api.models.audit_configuration import (
    lagos_days_in_utc,
)
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

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

#: The four facts the forward record makes answerable, and only from the
#: instant it begins. `access_change_fidelity` moves them between
#: `recoverable` and `not_recoverable` by MEASUREMENT, so every test below
#: asserts the RULE — which list they are in, given `record_starts_at` — and
#: never the frozen list they happened to be in the day it was written.
RECORDED_FACTS = frozenset((
    'group_granted', 'group_removed', 'group_change_actor',
    'group_change_timestamp'))


class AccessReportCase(CadraTransactionCase):

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

    def _group(self, name=None):
        """A group this test owns, which no account can already be in.

        A brand-new group rather than `base.group_no_one`: a grant only
        reaches the record when membership genuinely MOVES, so a test that
        granted a group the account already held would write nothing and
        would then prove the opposite of what it says.
        """
        seq = len(getattr(self, "_groups", []) or [])
        name = name or "Audit access test group %s-%d" % (self.marker, seq)
        group = self.env["res.groups"].create({"name": name})
        self._groups = (getattr(self, "_groups", []) or []) + [group]
        return group

    def _grant(self, user, group=None):
        """Change real membership — the ONLY way a row reaches the record.

        `myservice.api.access.change.create` refuses a hand-written row, so a
        test that needs the record to hold something has to cause the thing
        the record is about. That is the point of the model and it is the
        point of this helper.
        """
        group = group or self._group()
        user.write({self.Users._access_groups_field(): [(4, group.id)]})
        self._flush_tracking()
        return group

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

    Every table the report READS is fingerprinted, because a read is where
    an accidental write comes from: the accounts, their group membership, the
    two chatter tables a tracked write would land in, the parameter table the
    sibling report reads, the client table the roster labels from — and, since
    handoff 24, the access record itself. That last one is not one more table.
    The report now reads the append-only record of who was granted what, and a
    report that appended to it while reading it would be manufacturing the
    evidence it then cites; the model refuses a hand-written row, and this
    proves the report never finds a way to ask for one.
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
        # The forward access record (handoff 24). The report reads it for the
        # group-change events, for `record_starts_at` and for `record_rows`.
        # It is append-only and the report is a reader: a row appearing across
        # a read is the worst write this fingerprint could catch.
        "myservice_api_access_change": "t.id",
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

        The access record is driven the only way it can be — by changing real
        membership, since the model refuses a hand-written row — which is the
        same write that drives the membership fingerprint, so one grant proves
        both marks live.
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
        # The same grant, in the record that now reports it. Asserted here
        # rather than in a test of its own because a fingerprint over a table
        # that NOTHING in this test writes is exactly the vacuous proof this
        # negative control exists to rule out: `myservice_api_access_change`
        # would then compare equal on every run and the two read-only tests
        # below would be resting on a table they never proved they could see.
        self.assertNotEqual(
            after_user["myservice_api_access_change"],
            after_group["myservice_api_access_change"],
            "a group grant wrote no row to `myservice_api_access_change`, so "
            "either the recorder is not installed or this fingerprint cannot "
            "see the access record — and the read-only proofs below, which "
            "now cover the table the report reads its group changes FROM, "
            "are unproven")
        self.assertGreater(
            after_group["myservice_api_access_change"][0],
            after_user["myservice_api_access_change"][0],
            "the access record did not GROW across a grant; a moved md5 with "
            "an unchanged row count would mean a row was rewritten rather "
            "than appended, on a model that refuses both")

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

    def _assert_the_four_facts_follow_the_record(self, fidelity):
        """The rule, asserted in whatever state this tenant is actually in.

        `recoverable` and `not_recoverable` stopped being frozen lists in
        handoff 24: the four facts the forward record answers sit in one list
        or the other according to whether the record has BEGUN here. Pinning
        either list literally would make this test a statement about the
        tenant it last ran on — and would pass, wrongly, on a tenant that has
        never recorded anything simply because that is the older shape.
        """
        recoverable = set(fidelity["recoverable"])
        not_recoverable = set(fidelity["not_recoverable"])
        self.assertFalse(
            recoverable & not_recoverable,
            "a fact is published as both recoverable and not recoverable: %s"
            % sorted(recoverable & not_recoverable))
        if fidelity["record_starts_at"]:
            self.assertTrue(
                RECORDED_FACTS <= recoverable,
                "this tenant's access record has begun (%s) and these facts "
                "are still not published as recoverable: %s. The report is "
                "understating a record it holds."
                % (fidelity["record_starts_at"],
                   sorted(RECORDED_FACTS - recoverable)))
            self.assertFalse(
                RECORDED_FACTS & not_recoverable,
                "the record has begun and these facts are still named as NOT "
                "recoverable: %s"
                % sorted(RECORDED_FACTS & not_recoverable))
        else:
            self.assertTrue(
                RECORDED_FACTS <= not_recoverable,
                "this tenant holds no access-change rows, so nothing can be "
                "answered about grants — and these facts are published as "
                "recoverable anyway: %s. Claiming coverage the record does "
                "not have is the one failure mode this report exists to "
                "prevent." % sorted(RECORDED_FACTS - not_recoverable))
            self.assertFalse(RECORDED_FACTS & recoverable)

    def test_the_record_start_is_measured_and_published(self):
        """`record_starts_at` and `record_rows` are one measurement seen twice.

        `changed_at` is required on the model, so a tenant holding rows has an
        earliest one and a tenant holding none has no start. If those two ever
        disagree, one of them has stopped being measured — and the one that
        matters is `record_starts_at`, which is the instant the whole coverage
        verdict is computed against.
        """
        fidelity = self.Users.access_change_fidelity()
        for key in ("record_starts_at", "record_rows"):
            self.assertIn(
                key, fidelity,
                "`%s` is absent from the fidelity block; the report measured "
                "the boundary of its own record and did not publish it" % key)
        self.assertIsInstance(fidelity["record_rows"], int)
        self.assertGreaterEqual(fidelity["record_rows"], 0)
        self.assertEqual(
            fidelity["record_starts_at"] is None,
            fidelity["record_rows"] == 0,
            "`record_starts_at` is %r while `record_rows` is %d. A row cannot "
            "exist without a `changed_at` — the field is required — so these "
            "two cannot disagree unless one of them is a constant."
            % (fidelity["record_starts_at"], fidelity["record_rows"]))
        note = fidelity["notes"]["record_start"]
        self.assertTrue(note, "the record-start note is empty")
        if fidelity["record_starts_at"]:
            self.assertIn(
                str(fidelity["record_rows"]), note,
                "the record-start note does not quote the row count it "
                "measured, so a reader cannot tell a measurement from a "
                "boilerplate sentence")
            self.assertIn(str(fidelity["record_starts_at"]), note)
        else:
            self.assertIn(
                "NO access-change rows", note,
                "this tenant holds no access-change rows and the note does "
                "not say so; a reader is left to assume the record covers "
                "the period")

    def test_a_recorded_grant_moves_the_four_facts_into_recoverable(self):
        """Driven, because the branch that matters is the one no tenant has
        taken yet.

        The rule is asserted first in whatever state the tenant arrived in,
        then a real grant is made and it is asserted again on the other side
        of the boundary. Without the drive this test would only ever exercise
        the `not_recoverable` arm, which is the arm that was already true.
        """
        self._assert_the_four_facts_follow_the_record(
            self.Users.access_change_fidelity())

        user = self._user()
        self._grant(user)

        after = self.Users.access_change_fidelity()
        self.assertIsNotNone(
            after["record_starts_at"],
            "a grant was made in this transaction and the record still "
            "reports no start, so either the recorder did not fire or "
            "`record_starts_at` is not measuring the rows it claims to")
        self.assertGreaterEqual(after["record_rows"], 1)
        self._assert_the_four_facts_follow_the_record(after)
        self.assertTrue(
            RECORDED_FACTS <= set(after["recoverable"]),
            "the record has begun and the four facts it answers are not in "
            "`recoverable`: %s"
            % sorted(RECORDED_FACTS - set(after["recoverable"])))

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
class TestTheGroupChangeCount(AccessReportCase):
    """`group_changes_in_period` is a real count, and it is PRESENT at zero.

    It was a structural zero until handoff 24 put a forward record behind it.
    The half of that argument which was always the point survives unchanged:
    a count that disappears when it is zero is how a consumer ends up
    inferring "the key is missing, so this report does not cover group
    changes" — or worse, not noticing at all.

    The half that had to go is the zero itself, and these tests are the ones
    that had to change shape rather than be relaxed. `assertEqual(count, 0)`
    over a live period is no longer a statement about the design: it is a
    statement about whether anybody has been granted anything on this tenant,
    which this suite is scoped against asserting everywhere else. So:

    * the ZERO is asserted over a period the record cannot reach (2001), where
      it is structural again and for a reason that is now stated — the record
      did not exist then and no row can carry a `changed_at` inside it;
    * the COUNTING is asserted as a delta across a grant this test makes
      itself, which is exact regardless of what the tenant already held.

    A grant is made by moving real membership, never by writing a row: the
    model refuses a hand-written create, which is what makes the count
    evidence rather than a number somebody typed.
    """

    def test_the_key_is_present_and_zero_for_a_period_before_the_record(self):
        """The presence guarantee, over the one period where the zero is still
        structural. The record began, at the earliest, when handoff 24 shipped;
        a row dated 2001 cannot exist, because `changed_at` is stamped when the
        membership moves and nothing backdates it."""
        summary = self._report(DEAD_FROM, DEAD_TO)["summary"]
        self.assertIn(
            "group_changes_in_period", summary,
            "the count is missing from the summary. A consumer counting "
            "access changes now sees no key rather than a zero, and the "
            "absence of group changes in the period becomes something they "
            "have to infer.")
        self.assertEqual(
            summary["group_changes_in_period"], 0,
            "a period in 2001 reports group changes. No row can carry a "
            "`changed_at` before the record existed, so this is either the "
            "period filter not filtering or a count taken over the whole "
            "table.")
        self.assertIsInstance(summary["group_changes_in_period"], int)
        self.assertIn("implication_changes_in_period", summary)
        self.assertEqual(summary["implication_changes_in_period"], 0)
        # Handoff 45's count is present at zero for the same reason, and a
        # period in 2001 is before any deactivation could have been recorded.
        self.assertIn("account_state_changes_in_period", summary)
        self.assertEqual(summary["account_state_changes_in_period"], 0)
        self.assertEqual(summary["account_state_coverage"],
                         ACCESS_COVERAGE_NONE)

    def test_a_grant_moves_the_count_by_exactly_one(self):
        """The count is a measurement, asserted as a DELTA.

        One grant is one change. Measured either side of the grant rather
        than against a literal, because the tenant's own history is not this
        test's business and an absolute assertion would be a claim about it.
        """
        user = self._user()
        self._flush_tracking()
        before = self._report()["summary"]["group_changes_in_period"]

        self._grant(user)

        after = self._report()["summary"]["group_changes_in_period"]
        self.assertEqual(
            after, before + 1,
            "one group grant moved `group_changes_in_period` from %d to %d. "
            "It is now a real count over the forward record: one grant is "
            "exactly one change, and a delta of anything else means the "
            "report is either missing rows or double-counting them."
            % (before, after))

    def test_the_grant_is_an_event_with_exact_precision_and_its_evidence(self):
        """A recorded grant is the FIRST access event this report can publish
        with `precision: exact` and an actor that is not a create stamp. The
        evidence string names the row, so an auditor can go and read it."""
        user = self._user()
        self._flush_tracking()
        group = self._grant(user)
        label = group.full_name or group.name

        # Scoped to THIS group, not to every grant the account has. Creating
        # an account is itself recorded — `_default_groups()` puts it in
        # `base.group_user` — so a filter on the event type alone would count
        # the create's grants too and this assertion would be about how many
        # groups a new user lands in.
        granted = [e for e in self._events_for(self._report(), user)
                   if e["event"] == ACCESS_EVENT_GRANTED
                   and e["group"] == label]
        self.assertEqual(
            len(granted), 1,
            "a single grant of %r produced %d `granted` events"
            % (label, len(granted)))
        event = granted[0]
        self.assertEqual(
            event["precision"], "exact",
            "a recorded grant is the one access event whose timestamp and "
            "actor are its own; publishing it as `last_write_only` would "
            "throw away the only precise group evidence this report has")
        self.assertEqual(event["group"], label)
        self.assertIn(
            "myservice_api_access_change.id=", event["evidence"],
            "the event does not name the row it came from, so the reader "
            "cannot check it")
        self.assertIn("attributable", event)
        self.assertIsInstance(event["attributable"], bool)
        if not event["attributable"]:
            # An upgrade, a cron or the test runner acting as SUPERUSER. The
            # record says so rather than naming a person — asserted as the
            # RULE, not as a claim about who happens to run this suite.
            self.assertEqual(event["actor"]["name"], SYSTEM_ACTOR)
            self.assertIsNone(event["actor"]["id"])
        else:
            self.assertTrue(event["actor"]["id"])
            self.assertNotEqual(event["actor"]["name"], SYSTEM_ACTOR)

    def test_a_grant_today_is_absent_from_a_period_before_the_record(self):
        """The count and the events are both period-filtered, and the failure
        this catches is the one an auditor hits for the next twelve months: a
        report that answered a 2001 question with 2026 rows would be the exact
        opposite of the boundary this report is built to state."""
        user = self._user()
        self._flush_tracking()
        self._grant(user)

        self.assertGreater(
            self._report()["summary"]["group_changes_in_period"], 0,
            "the grant this test just made is not counted in a period that "
            "contains today, so the assertion below proves nothing")
        dead = self._report(DEAD_FROM, DEAD_TO)
        self.assertEqual(dead["summary"]["group_changes_in_period"], 0)
        self.assertEqual(
            [e for e in self._events_for(dead, user)
             if e["event"] in (ACCESS_EVENT_GRANTED, ACCESS_EVENT_REMOVED)],
            [],
            "a grant made today appears in a period ending in 2001")

    def test_a_removal_is_counted_as_well_as_a_grant(self):
        """A removal is the half that leaves NOTHING behind in the membership
        table — the row is deleted and the only evidence it ever existed is
        the forward record. If only grants were counted, the register would
        drift upwards forever and nobody could tell."""
        user = self._user()
        group = self._grant(user)
        before = self._report()["summary"]["group_changes_in_period"]

        user.write({self.Users._access_groups_field(): [(3, group.id)]})
        self._flush_tracking()

        report = self._report()
        self.assertEqual(
            report["summary"]["group_changes_in_period"], before + 1,
            "a removal did not move the count. The membership row is gone and "
            "the forward record is the only place it is written down.")
        label = group.full_name or group.name
        removed = [e for e in self._events_for(report, user)
                   if e["event"] == ACCESS_EVENT_REMOVED
                   and e["group"] == label]
        self.assertEqual(
            len(removed), 1,
            "a single removal of %r produced %d `removed` events"
            % (label, len(removed)))

    def test_an_implication_change_is_counted_separately(self):
        """What a group MEANS is not who is in it, and the two are not summed.

        On Odoo 19 `res.groups.all_implied_ids` is an unstored compute, so
        adding an implication moves effective access while writing zero rows
        to the membership table. It is counted in its own key and deliberately
        kept out of `events`, which the controller pages by user id and an
        implication names no user — folding it in would either drop it
        silently or break the page contract.
        """
        holder, implied = self._group(), self._group()
        before = self._report()["summary"]

        holder.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()

        after = self._report()["summary"]
        self.assertEqual(
            after["implication_changes_in_period"],
            before["implication_changes_in_period"] + 1,
            "an implication edge was added and "
            "`implication_changes_in_period` did not move. That change "
            "grants every member of one group the rights of another while "
            "writing no membership row, so a report that does not count it "
            "is blind to the access change that leaves the least trace.")
        self.assertEqual(
            after["group_changes_in_period"],
            before["group_changes_in_period"],
            "an implication change was counted as a group MEMBERSHIP change. "
            "They are different facts and a reader counting grants must never "
            "be silently handed an implication edge.")

    def test_the_summary_carries_the_counts_a_consumer_branches_on(self):
        report = self._report()
        for key in ("accounts", "accounts_active", "events_in_period",
                    "group_changes_in_period", "implication_changes_in_period",
                    "account_state_changes_in_period",
                    "account_state_changes_not_shown",
                    "account_state_coverage",
                    "coverage", "statement"):
            self.assertIn(key, report["summary"])
        self.assertEqual(report["summary"]["events_in_period"],
                         len(report["events"]))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheCoverageEnum(AccessReportCase):
    """Every branch, driven directly with synthetic inputs.

    Driven directly and not through the report on purpose. Most of these
    branches are unreachable on any tenant that exists today — the record has
    just started on all of them, `partial` from a grown history needs one
    nobody has, and the distinction between the two `none` wordings needs a
    period both empty and non-empty. Waiting for a deployment to exercise them
    is waiting forever.

    Handoff 24 added the three that matter most, because they are now the
    ones a real request takes: where the requested period sits relative to the
    instant this tenant's record BEGAN. `none` for a period that ended before
    it, `partial` for one that straddles it, `recorded` for one wholly inside
    it. The first is the answer an auditor will get for the next twelve
    months and it must stay `none` however much the record has since filled
    up — rows from after a period say nothing about the period.

    Branch on `coverage`, never on `statement` — so the enum is asserted
    first in every case and the wording second.
    """

    #: A record that began at a known instant, so the three period cases can
    #: be placed either side of it.
    RECORD_BEGAN = "2026-01-01 00:00:00"

    def _fidelity(self, **overrides):
        """The shape `_access_change_coverage` actually reads, and only that.

        Deliberately a hand-built dict rather than the real fidelity block: a
        tenant that grew one tracking row — or that has since recorded its
        first grant — would otherwise flip these tests to another branch and
        they would stop testing what they say they test.

        `record_starts_at` is stated as `None` rather than left out. The model
        reads it with `.get`, so an absent key and a null one behave alike
        today; spelling it means these tests say which world they are in
        instead of relying on that.
        """
        return dict({
            "groups_field_tracked": False,
            "membership_audit_columns": [],
            "tracking_rows": 0,
            "record_starts_at": None,
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

    # ── the three the forward record decides ────────────────────────

    def test_a_period_that_ended_before_the_record_began_is_still_none(self):
        """The answer an auditor gets for the next twelve months, and the one
        that must not drift.

        A record that now holds ten thousand rows says nothing about a quarter
        that closed before it began. If this ever answers `recorded` or
        `partial` because the record is healthy TODAY, the report is citing
        rows from outside the period as coverage of it — which is the precise
        overstatement the whole fidelity block exists to prevent.
        """
        coverage, statement = self.Users._access_change_coverage(
            [{"event": ACCESS_EVENT_CREATED}],
            self._fidelity(record_starts_at=self.RECORD_BEGAN),
            start=datetime(2025, 1, 1),
            end=datetime(2025, 12, 31, 23, 59, 59, 999999),
            group_changes=0)
        self.assertEqual(
            coverage, ACCESS_COVERAGE_NONE,
            "a period that ended before the access record began was answered "
            "%r. Nothing was being written down then and nothing can be "
            "reconstructed; any other answer claims coverage of a period the "
            "record does not reach." % coverage)
        self.assertIn(self.RECORD_BEGAN, statement)
        self.assertIn("AFTER the end of the period", statement)
        self.assertIn(
            "must not be read as", statement,
            "the statement does not warn that an empty table here is a "
            "statement about the record rather than about the estate")

    def test_a_period_straddling_the_record_start_is_a_partial_lower_bound(
            self):
        """Half the quarter is recorded and half of it never can be, and the
        count below is therefore a floor rather than a total. A consumer that
        read it as a total would reconcile against a number that is missing
        exactly the part nobody can produce."""
        coverage, statement = self.Users._access_change_coverage(
            [], self._fidelity(record_starts_at=self.RECORD_BEGAN),
            start=datetime(2025, 6, 1),
            end=datetime(2026, 6, 30, 23, 59, 59, 999999),
            group_changes=3)
        self.assertEqual(coverage, ACCESS_COVERAGE_PARTIAL)
        self.assertIn(self.RECORD_BEGAN, statement)
        self.assertIn(
            "LOWER BOUND", statement,
            "a straddling period publishes a count that is missing everything "
            "before the record began, and the statement does not say so")
        self.assertIn("3 group change(s)", statement)

    def test_a_period_wholly_inside_the_record_is_recorded(self):
        """`recorded` — the answer that did not exist before handoff 24, and
        the first time this report can say the table below is COMPLETE.

        Driven with `tracking_rows=5` as well, so it also proves the forward
        record wins over the grown-history disjunct. Those two arms disagree:
        `partial` would tell an auditor the report understates what the
        database holds, which is false once the record covers the period, and
        the one that is actually READ has to be the one that decides.
        """
        coverage, statement = self.Users._access_change_coverage(
            [], self._fidelity(record_starts_at=self.RECORD_BEGAN,
                               tracking_rows=5),
            start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 28, 23, 59, 59, 999999),
            group_changes=2)
        self.assertEqual(
            coverage, ACCESS_COVERAGE_RECORDED,
            "a period lying wholly after the record began was answered %r. "
            "`recorded` is the only value that says the group changes listed "
            "are every grant and removal in the period, and it is the whole "
            "point of having written the record." % coverage)
        self.assertIn("2 group change(s)", statement)
        self.assertIn(
            SYSTEM_ACTOR, statement,
            "the `recorded` statement does not warn that a change made by an "
            "upgrade, a cron or the command line is attributed to "
            "`%s` rather than to a person — which is the one caveat that "
            "survives a complete record" % SYSTEM_ACTOR)

    def test_the_record_decides_before_the_grown_history_disjuncts(self):
        """Stated as its own test because it is an ORDERING, and an ordering
        is the kind of thing a later edit reverses without noticing. Every one
        of the three `partial`-from-history disjuncts must lose to a record
        that covers the period."""
        for override in ({"groups_field_tracked": True},
                         {"membership_audit_columns": ["create_date"]},
                         {"tracking_rows": 12}):
            coverage, _statement = self.Users._access_change_coverage(
                [], self._fidelity(record_starts_at=self.RECORD_BEGAN,
                                   **override),
                start=datetime(2026, 2, 1),
                end=datetime(2026, 2, 28, 23, 59, 59, 999999))
            self.assertEqual(
                coverage, ACCESS_COVERAGE_RECORDED,
                "%s flipped a fully recorded period to %r. The forward record "
                "is the source this report actually READS; a hint that some "
                "other history exists must not downgrade a period the record "
                "covers." % (sorted(override), coverage))


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
        kinds = [e["event"] for e in events]
        # The `granted` rows a create writes are filtered out rather than
        # tolerated. `_default_groups()` puts every new account in
        # `base.group_user`, and since handoff 24 that is RECORDED — so a
        # brand-new account legitimately carries create-time grant events and
        # this list is no longer only the create. What must still be exactly
        # the create is everything that comes from the user row's own stamps,
        # which is what the two-second rule governs; the grant events are
        # asserted in their own right in `TestTheGroupChangeCount`.
        self.assertEqual(
            [k for k in kinds
             if k not in (ACCESS_EVENT_GRANTED, ACCESS_EVENT_REMOVED)],
            [ACCESS_EVENT_CREATED],
            "an account that was created and never touched again reported "
            "%s. `write_date` equals `create_date` on a fresh row, so any "
            "`account_modified` here is the two-second tolerance failing and "
            "every account in the tenant is now reported as modified."
            % kinds)

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

    Every moment below is the UTC instant the stamp is STORED as, and the
    days it is judged against are LAGOS days (handoff 65,
    `TestThePeriodIsALagosDay`): 23:30 Lagos is 22:30 UTC.
    """

    #: Late enough on the closing day that a naive midnight bound loses it —
    #: 23:30 LAGOS on 30 June. Until handoff 65 this was 23:30 UTC, which is
    #: 00:30 Lagos on 1 July and now, correctly, outside the period.
    LATE = datetime(2021, 6, 30, 22, 30, 0)

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
        # 00:00:01 LAGOS on 1 June — 23:00:01 UTC on 31 May, which the UTC
        # day this report used until handoff 65 left out.
        user = self._user_at(datetime(2021, 5, 31, 23, 0, 1))
        report = self._report(date(2021, 6, 1), date(2021, 6, 30))
        self.assertEqual(
            [e["event"] for e in self._events_for(report, user)],
            [ACCESS_EVENT_CREATED],
            "the opening bound is exclusive; it is documented as inclusive")

    def test_an_event_the_next_day_is_excluded(self):
        """The bound has to bite in the other direction too, or "inclusive of
        the whole closing day" is indistinguishable from "no upper bound"."""
        # 00:30 LAGOS on 1 July — 23:30 UTC on the closing date, which the
        # UTC day this report used until handoff 65 let in.
        user = self._user_at(datetime(2021, 6, 30, 23, 30, 0))
        report = self._report(date(2021, 6, 1), date(2021, 6, 30))
        self.assertEqual(
            self._events_for(report, user), [],
            "an account created after midnight on the day AFTER the closing "
            "date is inside the period, so the upper bound is not bounding")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThePeriodIsALagosDay(AccessReportCase):
    """A day in this report is a LAGOS day (handoff 65), as it has been on
    the configuration report since 63b and as every other date the register
    publishes is. It was a UTC day: from 00:00 to 01:00 Lagos a grant made a
    minute ago fell on yesterday's UTC date and was missing from today's
    report — and an auditor asking "who was given what on the 19th" was
    shown the hour from 01:00 on the 19th to 01:00 on the 20th.

    Both halves of the report are period-filtered and both are pinned: the
    account stamps (`create_date`/`write_date`) and the forward record's
    `changed_at`. The stamps come from Postgres (`cr.now()`), which no frozen
    clock in Python reaches, so each row is PLACED at the instant in SQL
    instead; the only clock this report compares is the stored stamp against
    the day's two edges. The same helper as 63b's — `lagos_days_in_utc` —
    so the two reports cannot disagree on where a day starts.
    """

    # 00:30 Lagos on 11 May 2031 is 23:30 UTC on the 10th. Days far from
    # any run's real clock: a fixture account is GRANTED its groups at the
    # real now, so a period containing today would see that grant too (the
    # first draft used 18–19 October 2026 and failed on the 19th).
    HALF_PAST_MIDNIGHT_LAGOS = datetime(2031, 5, 10, 23, 30)
    THE_19TH = date(2031, 5, 11)
    THE_18TH = date(2031, 5, 10)

    def _created_at(self, moment):
        """An account whose create and write stamps both sit at `moment`, so
        the two-second rule writes no `account_modified` and the test is
        about the period's edges alone."""
        user = self._user()
        self._flush_tracking()
        self._backdate(user, "create_date", moment)
        self._backdate(user, "write_date", moment)
        return user

    def _granted_at(self, moment):
        """A REAL grant (the record refuses a hand-written row), then its
        `changed_at` moved in raw SQL — the record is append-only and its
        `write` raises unconditionally, so SQL is the only way to place a
        row at an instant (CLAUDE.md: a fixture that needs a row in the past
        uses raw SQL and says so). The TransactionCase rolls it back."""
        user = self._user()
        self._flush_tracking()
        group = self._grant(user)
        rows = self.env["myservice.api.access.change"].sudo().search([
            ("user_id", "=", user.id), ("group_id", "=", group.id),
            ("event", "=", ACCESS_EVENT_GRANTED)])
        self.assertEqual(
            len(rows), 1,
            "the grant wrote %d record rows, not one; the placement below "
            "would be moving the wrong thing" % len(rows))
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE myservice_api_access_change SET changed_at = %s "
            "WHERE id = %s", (moment, rows.id))
        self.env.invalidate_all()
        return user, group.full_name or group.name

    def _grants(self, report, user, label):
        return [e for e in self._events_for(report, user)
                if e["event"] == ACCESS_EVENT_GRANTED and e["group"] == label]

    def test_an_account_created_at_half_past_midnight_is_in_that_lagos_day(
            self):
        user = self._created_at(self.HALF_PAST_MIDNIGHT_LAGOS)
        self.assertEqual(
            [e["event"] for e in self._events_for(
                self._report(self.THE_19TH, self.THE_19TH), user)],
            [ACCESS_EVENT_CREATED],
            "an account created at 00:30 Lagos on the 19th is missing from "
            "the report for the 19th — the period is being read as a UTC day")
        self.assertEqual(
            self._events_for(
                self._report(self.THE_18TH, self.THE_18TH), user), [],
            "an account created at 00:30 Lagos on the 19th is reported on "
            "the 18th, its UTC date")

    def test_a_recorded_grant_at_half_past_midnight_is_in_that_lagos_day(
            self):
        """The half of the report that answers §13.4's question — and the
        count beside it, which a summary-only reader trusts."""
        user, label = self._granted_at(self.HALF_PAST_MIDNIGHT_LAGOS)
        the_19th = self._report(self.THE_19TH, self.THE_19TH)
        self.assertEqual(
            len(self._grants(the_19th, user, label)), 1,
            "a grant recorded at 00:30 Lagos on the 19th is missing from the "
            "report for the 19th — `changed_at` is being bounded by UTC days")
        self.assertGreaterEqual(
            the_19th["summary"]["group_changes_in_period"], 1)
        self.assertEqual(
            self._grants(self._report(self.THE_18TH, self.THE_18TH),
                         user, label), [],
            "a grant recorded at 00:30 Lagos on the 19th is reported on the "
            "18th, its UTC date")

    def test_the_edges_are_lagos_midnight_and_its_last_microsecond(self):
        start, end = lagos_days_in_utc(self.THE_19TH, self.THE_19TH)
        self.assertEqual(start, datetime(2031, 5, 10, 23, 0))
        self.assertEqual(end, datetime(2031, 5, 11, 22, 59, 59, 999999))
        first = self._created_at(start)
        last = self._created_at(end)
        before = self._created_at(start - timedelta(microseconds=1))
        after = self._created_at(end + timedelta(microseconds=1))
        report = self._report(self.THE_19TH, self.THE_19TH)
        self.assertTrue(self._events_for(report, first),
                        "Lagos midnight itself is outside the day it opens")
        self.assertTrue(self._events_for(report, last),
                        "the day's last microsecond is outside it")
        self.assertEqual(self._events_for(report, before), [],
                         "the instant before Lagos midnight is inside the day")
        self.assertEqual(self._events_for(report, after), [],
                         "the instant after the day's last is inside it")


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
        # `record_starts_at: None` pins these to the no-record branch: the
        # wordings pinned below are that branch's, and a tenant that has begun
        # recording would otherwise be compared against a different sentence.
        return {"groups_field_tracked": False,
                "membership_audit_columns": [], "tracking_rows": 0,
                "record_starts_at": None}

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
        not a second copy that drifted.

        Recomputed from the SAME inputs the report used. `start`, `end` and
        `group_changes` became arguments in handoff 24, and they are not
        optional to this comparison: on a tenant that has begun recording,
        calling the helper without them answers `recorded` for a period the
        report itself called `partial`, and the test would be comparing the
        published statement against the answer to a different question — then
        failing, or worse, being "fixed" by loosening it.
        """
        report = self._report()
        # The report's own edges, Lagos days since handoff 65 — computed by
        # the same helper, so this compares like with like.
        start, end = lagos_days_in_utc(WIDE_FROM, WIDE_TO)
        expected = self.Users._access_change_coverage(
            report["events"], report["fidelity"], start=start, end=end,
            group_changes=report["summary"]["group_changes_in_period"])
        # Since handoff 45 the statement says the account-state half too —
        # recomputed from the same inputs, appended the way the report does.
        account_state = self.Users._access_account_state_coverage(
            report["fidelity"], start=start, end=end,
            changes=report["summary"]["account_state_changes_in_period"])
        self.assertEqual(report["summary"]["coverage"], expected[0])
        self.assertEqual(report["summary"]["account_state_coverage"], account_state[0])
        self.assertEqual(report["summary"]["statement"],
                         "%s %s" % (expected[1], account_state[1]))
