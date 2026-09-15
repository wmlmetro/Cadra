"""The forward record of who was granted what, and the boundary it publishes.

Handoff 24. `myservice_api/models/access_change.py` makes two claims that are
only worth what their evidence is worth, and this file is the evidence:

1. **Every way membership can move is recorded, and nothing else is.** The
   relation is writable from four structurally different directions and only
   one of them is `res.users.write`. Handoff 14 was told the transfer route
   was the only writer of `custodian_id` and an exhaustive search found six;
   the same mistake here would produce an append-only record with invisible
   holes, which is worse than no record because it reads as complete. So all
   four doors are driven — user write, user create, group write on members,
   group write on implications — plus the unlink that a cascade would
   otherwise erase, and the no-op re-link that must write nothing.

2. **The record says where it STOPS.** A record that begins on the day it was
   installed cannot answer for the period before it, and the one thing it
   must never do is answer that period with an empty table. A period ending
   before the first recorded row is `none` however much the record now holds,
   because rows from after the period say nothing about the period. That is
   the assertion this whole file exists to protect.

The append-only half is `nrs.asset.custody`'s argument in a second place, and
it is tested the same way: `write` and `unlink` are exercised under `sudo()`
as well as without it, because a record whose entire value is that nobody can
alter it has to refuse the administrator too — and every API route in this
codebase calls `sudo()` on every request.

**Every assertion here is SCOPED to rows this test caused.** `myservice_api`'s
in-registry suites run in CI after `pytest tests/`, which COMMITS fixtures of
its own — API clients are `res.users`, so they land in this very record. An
unscoped count would be an assertion about whatever the tenant happened to
hold, which is the defect the record exists to remove turned on its own
tests. Two scopes are used: a watermark (the highest row id before the action
under test, so everything above it is this test's) and, wherever the row
carries one, the id of a user or group this test created.

Two classes go further and EMPTY the table in SQL before measuring. That is
deliberate and it is safe: a `TransactionCase` never commits, so the delete is
rolled back with everything else. It is also the only honest way to observe
what a tenant holding no rows publishes — `record_starts_at` is `None` exactly
once in a tenant's life and no test can wait for it.

Run with:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --test-enable \\
      --test-tags /myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098

TransactionCase throughout, so this file does not itself need `--workers=0` —
but the HttpCase suites alongside it in this module do, so the run above is
given in the form that works for all of them.
"""
import uuid
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.myservice_api.models.access_change import (
    ACCESS_EVENT_GRANTED,
    ACCESS_EVENT_IMPLIED_ADDED,
    ACCESS_EVENT_IMPLIED_REMOVED,
    ACCESS_EVENT_REMOVED,
    SYSTEM_ACTOR,
)
from odoo.addons.myservice_api.models.audit_access import (
    ACCESS_COVERAGE_NONE,
    ACCESS_COVERAGE_PARTIAL,
    ACCESS_COVERAGE_RECORDED,
)

#: The two membership events, as opposed to the two implication events. The
#: report counts them in separate keys and several tests below assert that the
#: separation holds, so the split is named once here.
MEMBERSHIP_EVENTS = (ACCESS_EVENT_GRANTED, ACCESS_EVENT_REMOVED)

#: A fixed instant for the record to begin at, in the past and nowhere near a
#: period any other test names. The boundary tests are ABOUT this instant, so
#: it is pinned rather than derived from the clock.
RECORD_BEGINS = datetime(2024, 3, 15, 9, 30, 0)


class AccessChangeCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Users = self.env["res.users"]
        self.Groups = self.env["res.groups"]
        self.Change = self.env["myservice.api.access.change"]
        self.marker = uuid.uuid4().hex[:10]
        self._users = []
        self._groups = []
        # Resolved, never assumed. Odoo 19 renamed the user side from
        # `groups_id` to `group_ids` and the group side from `users` to
        # `user_ids`. `_access_groups_field` is `audit_access.py`'s probe and
        # `_access_users_field_name` is the recorder's — deliberately the
        # report's probe on the user side, so this file is not asserting the
        # recorder against its own answer.
        self.groups_field = self.Users._access_groups_field()
        self.users_field = self.Groups._access_users_field_name()

    # ── fixtures ────────────────────────────────────────────────────

    def _user(self, **vals):
        """A real account this test owns.

        `no_reset_password` because a created user otherwise triggers the
        signup mail path, which is a mail-server question and not an access
        question. The login carries the marker so every assertion can be
        scoped to it, and says `access-record` on its face so a row left
        behind by an aborted run is self-identifying rather than looking like
        somebody's account.
        """
        seq = len(self._users)
        login = "access-record-%s-%d@example.invalid" % (self.marker, seq)
        user = self.Users.sudo().with_context(no_reset_password=True).create(
            dict({"name": "Access record test %s" % login, "login": login},
                 **vals))
        self._users.append(user)
        return user

    def _group(self, label="A"):
        """A group this test owns, implying nothing and implied by nothing.

        Its own group rather than a core one, so that "exactly one row" is a
        statement about the hook and not about whatever `base.group_user`
        happens to imply on this tenant.
        """
        group = self.Groups.sudo().create(
            {"name": "Access record test group %s %s" % (label, self.marker)})
        self._groups.append(group)
        return group

    def _actor(self):
        """An account that can change another account's groups.

        `base.group_system` because writing `group_ids` on somebody else needs
        `base.group_erp_manager`, which it implies. `base.group_user` as well
        because Odoo 19 requires exactly one user-type group.
        """
        return self._user(**{self.groups_field: [(6, 0, [
            self.env.ref("base.group_user").id,
            self.env.ref("base.group_system").id,
        ])]})

    # ── plumbing ────────────────────────────────────────────────────

    def _flush_tracking(self):
        """Materialise everything this transaction would write at COMMIT.

        Odoo 19 registers `_track_finalize` on `cr.precommit`, so tracked
        writes reach the database at commit and not at flush, and a
        `TransactionCase` never commits. Odoo's own `MailCommon.flush_tracking`
        idiom, used here for the same reason `test_audit_access_report.py`
        uses it: a measurement taken without it is blind to exactly the writes
        it is meant to see.
        """
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.flush_all()

    def _watermark(self):
        """The highest row id right now.

        Everything above it was written by whatever the test does next. This
        is the scope, and it is what keeps an assertion about "exactly one
        row" from being an assertion about the tenant's whole history.
        """
        self.env.flush_all()
        last = self.Change.sudo().search([], order="id desc", limit=1)
        return last.id or 0

    def _rows_since(self, mark, domain=None):
        """This test's rows, in the order they were written."""
        self.env.flush_all()
        return self.Change.sudo().search(
            [("id", ">", mark)] + list(domain or []), order="id")

    def _membership_table(self):
        """The relation table behind the groups field, resolved not spelled.

        `res_groups_users_rel` is the answer on every deployment today and it
        is deliberately not written here — the report's whole boundary rests
        on measuring this rather than asserting it.
        """
        return self.Users._fields[self.groups_field].relation

    def _membership_row_count(self):
        """Rows in the membership relation. Flushed FIRST, which is the whole
        point: an unflushed count would report "nothing was written" about a
        write still sitting in the ORM's pending m2m operations."""
        self.env.flush_all()
        self.env.cr.execute("SELECT count(*) FROM %s" % self._membership_table())
        return self.env.cr.fetchone()[0]

    # ── controlling the record itself ───────────────────────────────

    def _empty_the_record(self):
        """Leave this tenant holding no access-change rows at all.

        Raw SQL because the model refuses `unlink()` — by design, and the
        append-only tests below prove it. Safe because a `TransactionCase`
        rolls back: nothing here survives the test. It is the only way to
        observe what a tenant publishes before its first row, which happens
        exactly once in a tenant's life.
        """
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM %s" % self.Change._table)
        self.env.invalidate_all()

    def _backdate_all_rows(self, moment):
        """Move every row's `changed_at`, in SQL, because the ORM will not.

        The model refuses `write()`, so there is no ORM route to a controlled
        timestamp — and `fields.Datetime.now()` inside one transaction cannot
        separate two rows by a period boundary anyway. Invalidate after, so
        the cache does not keep serving the old stamp.
        """
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE %s SET changed_at = %%s" % self.Change._table, (moment,))
        self.env.invalidate_all()

    def _record_begins_at(self, moment):
        """Leave the tenant's access record holding only rows at `moment`.

        Returns the user and group it used, both still live, so a caller can
        make a LATER change and have it land inside a period it names.
        """
        self._empty_the_record()
        user = self._user()
        group = self._group()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        self._backdate_all_rows(moment)
        return user, group


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestAGrantFromTheUserSideIsOneRow(AccessChangeCase):
    """`res.users.write` with the groups field — the obvious door.

    It is the one the admin user form actually uses: Odoo 19 deleted the
    reified `sel_groups_*` pseudo-fields, so the web client collapses its
    sub-widgets into a single command on the real field before the RPC. One
    grant is one row: a hook that wrote two would double-count every period,
    and one that wrote none would make the form the quietest hole in the
    record.
    """

    def test_granting_a_group_through_res_users_write_writes_exactly_one_row(self):
        user = self._user()
        group = self._group()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(
            len(rows), 1,
            "one group grant produced %d row(s). A grant is one event; more "
            "than one double-counts every period the report answers and fewer "
            "than one is a hole in an append-only record."
            % len(rows))
        self.assertEqual(rows.event, ACCESS_EVENT_GRANTED)
        self.assertEqual(
            rows.source, "user_write",
            "the row does not say it came from the user record, so a reader "
            "cannot tell a form edit from a seed script")

    def test_the_row_names_the_user_and_the_group_it_moved(self):
        user = self._user()
        group = self._group()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        row = self._rows_since(mark, [("user_id", "=", user.id)])

        self.assertEqual(row.user_id, user)
        self.assertEqual(row.group_id, group)
        self.assertFalse(
            row.implied_group_id,
            "a membership row named a second group; `implied_group_id` is for "
            "implication edges only and a reader counting grants would now be "
            "handed one")

    def test_the_row_snapshots_the_identity_as_it_read_at_the_time(self):
        """The same argument as the custody chain's `*_name` columns.

        `user_id` and `group_id` are `ondelete='set null'`, so without the
        snapshot an append-only row could still be emptied of its content from
        OUTSIDE the model — the guarantee would hold on the row and fail on
        the join, which is the same thing to an auditor.
        """
        user = self._user()
        group = self._group()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        row = self._rows_since(mark, [("user_id", "=", user.id)])

        self.assertEqual(row.user_login, user.login)
        self.assertEqual(row.user_name, user.name)
        self.assertTrue(
            row.group_name,
            "the group snapshot is blank, so a row whose group is later "
            "deleted names nothing at all")
        self.assertIn(
            group.name, row.group_name,
            "the group snapshot does not contain the group's own name; "
            "`_group_label` falls back to `name` when `full_name` is empty "
            "and one of the two has stopped working")

    def test_a_write_that_does_not_mention_groups_writes_nothing(self):
        """`res.users.write` is on the path of every login (`login_date`) and
        every preference change. A row per write would fill the record with
        events that are not access events, and the hook is guarded on the
        groups key precisely so that it does not pay for two snapshots on
        that path either."""
        user = self._user()
        mark = self._watermark()

        user.write({"name": "Access record renamed %s" % self.marker})
        self._flush_tracking()

        self.assertEqual(
            len(self._rows_since(mark, [("user_id", "=", user.id)])), 0,
            "renaming a user wrote an access-change row")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestAGrantFromTheGroupSideIsRecordedToo(AccessChangeCase):
    """`res.groups.write` with the members field — the door that is easy to miss.

    It is the SAME change made from the other side and it never passes through
    `res.users.write`; the two converge only in the generic m2m flush.
    `scripts/bootstrap.py` writes this way, and so do the security XML files
    that re-apply on every module upgrade. Without this hook every one of them
    would be invisible, and the record would be complete in exactly the cases
    somebody used the web form.
    """

    def test_the_group_side_field_is_user_ids_on_odoo_19(self):
        """Pinned with a message, not assumed. If the probe stops finding the
        field it returns `None` and the group-side snapshot silently becomes
        an empty frozenset — which records nothing and fails nothing."""
        self.assertEqual(
            self.users_field, "user_ids",
            "res.groups' members field is no longer `user_ids`; the recorder "
            "probes ('user_ids', 'users') and found %r, so every group-side "
            "change is now either unrecorded or recorded against the wrong "
            "relation" % (self.users_field,))

    def test_adding_a_member_through_res_groups_write_writes_exactly_one_row(self):
        user = self._user()
        group = self._group()
        mark = self._watermark()

        group.write({self.users_field: [(4, user.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("group_id", "=", group.id)])
        self.assertEqual(
            len(rows), 1,
            "adding a member from the group side produced %d row(s)"
            % len(rows))
        self.assertEqual(rows.event, ACCESS_EVENT_GRANTED)
        self.assertEqual(
            rows.source, "group_write",
            "the row does not say the change was made from the group record. "
            "That is the half of the record `res.users.write` cannot see, and "
            "labelling it `user_write` would hide which door was used.")
        self.assertEqual(rows.user_id, user)
        self.assertEqual(rows.group_id, group)

    def test_removing_a_member_through_res_groups_write_is_a_removal(self):
        user = self._user()
        group = self._group()
        group.write({self.users_field: [(4, user.id)]})
        self._flush_tracking()
        mark = self._watermark()

        group.write({self.users_field: [(3, user.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("group_id", "=", group.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.event, ACCESS_EVENT_REMOVED)
        self.assertEqual(rows.source, "group_write")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestCreatingAnAccountIsRecorded(AccessChangeCase):
    """`res.users.create` — and the case that proves the hooks diff.

    Every seed script, `auth_signup`'s `_create_user_from_template` and the
    API client provisioner land on `create` and never on `write`. The subtle
    half is that a create carrying NO group key at all still lands the user in
    a group, because `_default_groups()` supplies one. A hook that parsed
    `vals` would see nothing and record nothing, and every account ever
    provisioned would enter the estate with access nobody wrote down.
    """

    def test_a_create_that_mentions_no_groups_still_records_the_default_membership(self):
        mark = self._watermark()
        user = self._user()
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertTrue(
            rows,
            "a user created with no groups key recorded nothing, but the "
            "account is a member of %s. The hook is reading `vals` instead of "
            "diffing the real membership, and `_default_groups()` is now "
            "invisible." % user[self.groups_field].mapped("name"))
        self.assertEqual(set(rows.mapped("event")), {ACCESS_EVENT_GRANTED})
        self.assertEqual(
            set(rows.mapped("source")), {"user_create"},
            "a create is labelled as something other than `user_create`")

    def test_the_recorded_groups_are_the_membership_the_create_actually_produced(self):
        """Asserted against the real membership rather than against
        `base.group_user` by name. What must hold is that the record and the
        relation agree; which group the default happens to be is Odoo's
        business and pinning it here would make this test fail on a tenant
        that configured `base.default_user_group`."""
        mark = self._watermark()
        user = self._user()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(
            set(rows.mapped("group_id").ids), set(user[self.groups_field].ids),
            "the rows written at create do not match the membership the "
            "create produced")

    def test_a_create_that_names_a_group_records_that_group_too(self):
        group = self._group()
        mark = self._watermark()
        user = self._user(**{self.groups_field: [
            (4, self.env.ref("base.group_user").id), (4, group.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertIn(
            group.id, rows.mapped("group_id").ids,
            "a group named explicitly in the create was not recorded")
        self.assertEqual(
            set(rows.mapped("group_id").ids), set(user[self.groups_field].ids))
        self.assertEqual(set(rows.mapped("source")), {"user_create"})


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestARemovalIsRecorded(AccessChangeCase):
    """A removal is the event an auditor asks about, and the one the schema
    destroys. `res_groups_users_rel` deletes the only evidence the grant ever
    happened, so a record that logged grants and not removals would show an
    estate whose access only ever grew."""

    def test_removing_a_group_writes_exactly_one_removal_row(self):
        user = self._user()
        group = self._group()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        mark = self._watermark()

        user.write({self.groups_field: [(3, group.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(
            len(rows), 1,
            "one removal produced %d row(s)" % len(rows))
        self.assertEqual(rows.event, ACCESS_EVENT_REMOVED)
        self.assertEqual(rows.source, "user_write")
        self.assertEqual(rows.group_id, group)
        self.assertNotIn(group.id, user[self.groups_field].ids)

    def test_a_grant_and_a_removal_in_one_write_are_two_rows_sharing_one_instant(self):
        """One write can add three groups and remove two, and that is ONE
        event in time. `_record_many` writes them in a single `create` with a
        single stamp, which is what keeps the chronological order meaningful
        and the write cost proportional to what moved."""
        user = self._user()
        held = self._group("held")
        wanted = self._group("wanted")
        user.write({self.groups_field: [(4, held.id)]})
        self._flush_tracking()
        mark = self._watermark()

        user.write({self.groups_field: [(3, held.id), (4, wanted.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {(r.event, r.group_id.id) for r in rows},
            {(ACCESS_EVENT_GRANTED, wanted.id),
             (ACCESS_EVENT_REMOVED, held.id)})
        self.assertEqual(
            len(set(rows.mapped("changed_at"))), 1,
            "two halves of one write were stamped at different instants, so "
            "the record now reads as two events")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestAnImplicationIsRecordedAndMovesNoMembership(AccessChangeCase):
    """The case the membership table cannot see at all, on Odoo 19.

    `res.groups.all_implied_ids` is declared `compute=` with no `store=True`,
    and `res.users.all_group_ids` is computed at read time from it. So adding
    an implication grants every member of a group the rights of another group
    while writing ZERO rows to the membership relation. There are no "implied
    rows" for an auditor to ask about — only an edge.

    That makes it an effective-access change that a membership record would
    miss completely, and it is why `res.config.settings` group toggles are
    this case rather than the membership one: `_apply_group` writes
    `implied_ids` and never touches `res.users` at all.

    Both facts are asserted together. The row alone would not prove the
    implication changed anything, and the untouched relation alone would not
    prove it was recorded; it is the pair that says the record closes a hole
    the relation physically cannot.
    """

    def _group_with_a_member(self, label):
        """A group that HAS somebody in it.

        Load-bearing: on an empty group there would be nobody for an
        implication to propagate to, so "no membership rows were written"
        would be true for a reason that has nothing to do with Odoo 19.
        """
        group = self._group(label)
        user = self._user()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        return group, user

    def test_adding_an_implication_writes_one_implied_added_row(self):
        implier, _member = self._group_with_a_member("implier")
        implied = self._group("implied")
        mark = self._watermark()

        implier.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("group_id", "=", implier.id)])
        self.assertEqual(
            len(rows), 1,
            "adding an implication produced %d row(s)" % len(rows))
        self.assertEqual(rows.event, ACCESS_EVENT_IMPLIED_ADDED)
        self.assertEqual(
            rows.source, "group_implied",
            "an implication change is labelled as membership. A reader "
            "counting grants would be handed an edge that moved what a group "
            "MEANS rather than who is in it.")

    def test_adding_an_implication_writes_no_membership_rows_at_all(self):
        """The Odoo 19 fact, measured in SQL rather than quoted.

        If this ever fails the world changed, not the code: the transitive
        closure has gone back to being materialised, `all_implied_ids` is
        stored again, and the membership events now double-count every
        implication. `access_change.py`'s case 4 would have to be rewritten.
        """
        implier, member = self._group_with_a_member("implier")
        implied = self._group("implied")
        before_rows = self._membership_row_count()
        before_member = set(member[self.groups_field].ids)
        mark = self._watermark()

        implier.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()

        self.assertEqual(
            self._membership_row_count(), before_rows,
            "adding an implication wrote rows to `%s`. On Odoo 19 the closure "
            "is an UNSTORED compute and an implication must write none — if "
            "it now does, the implication is ALSO arriving as membership "
            "events and every such change is counted twice."
            % self._membership_table())
        member.invalidate_recordset()
        self.assertEqual(
            set(member[self.groups_field].ids), before_member,
            "the member's direct membership moved when only an implication "
            "was added")
        self.assertEqual(
            len(self._rows_since(mark, [("user_id", "=", member.id)])), 0,
            "an implication produced a per-user membership row, so the two "
            "kinds of event are no longer distinguishable in the record")
        self.assertEqual(
            len(self._rows_since(mark, [("group_id", "=", implier.id)])), 1,
            "the implication was not recorded, so an effective-access change "
            "that writes nothing to the membership table is now invisible in "
            "BOTH places")

    def test_removing_an_implication_writes_one_implied_removed_row(self):
        implier, _member = self._group_with_a_member("implier")
        implied = self._group("implied")
        implier.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()
        before_rows = self._membership_row_count()
        mark = self._watermark()

        implier.write({"implied_ids": [(3, implied.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("group_id", "=", implier.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.event, ACCESS_EVENT_IMPLIED_REMOVED)
        self.assertEqual(rows.source, "group_implied")
        self.assertEqual(
            self._membership_row_count(), before_rows,
            "removing an implication moved the membership relation")

    def test_an_implication_row_names_two_groups_and_no_user(self):
        """It is about a pair of groups and names no user, and that absence is
        the contract: `access_change_report` cannot page an event with no user
        id, so it counts these separately rather than inventing one."""
        implier, _member = self._group_with_a_member("implier")
        implied = self._group("implied")
        mark = self._watermark()

        implier.write({"implied_ids": [(4, implied.id)]})
        row = self._rows_since(mark, [("group_id", "=", implier.id)])

        self.assertEqual(row.group_id, implier)
        self.assertEqual(row.implied_group_id, implied)
        self.assertFalse(
            row.user_id,
            "an implication row names a user; it is not a membership change "
            "and attaching one would make it page as though it were")
        self.assertFalse(row.user_login)
        self.assertIn(implied.name, row.implied_group_name or "")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheActorIsNamedHonestly(AccessChangeCase):
    """Who made the change, and the refusal to invent somebody.

    Report 23 measured 100% of the ACL stamps in this estate as `uid 1`. A
    record that renders those as "the system administrator granted this" is
    worse than no record: it invents a person, and an invented person is what
    ends up in a finding. An upgrade, a cron and the command line all arrive
    as SUPERUSER, and the row says so — `__system__`, `attributable = False`,
    `changed_by_id` null. The three are written together and must never
    diverge, because a consumer that trusted `actor` and ignored
    `attributable` would read `__system__` as a username.
    """

    def test_a_change_made_as_superuser_is_recorded_as_the_system_actor(self):
        """A `TransactionCase` runs as uid 1, so this is the default path and
        also the one every module upgrade takes."""
        user = self._user()
        group = self._group()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        row = self._rows_since(mark, [("user_id", "=", user.id)])

        self.assertEqual(
            row.actor, SYSTEM_ACTOR,
            "a change made as SUPERUSER was attributed to %r" % row.actor)
        self.assertIs(
            row.attributable, False,
            "a SUPERUSER change is flagged attributable, so a report will "
            "print a name beside a change no person made")
        self.assertFalse(
            row.changed_by_id,
            "`changed_by_id` points at a user for a change that cannot "
            "honestly be attributed to one")

    def test_the_system_actor_is_never_a_persons_name(self):
        """`uid 1` has a display name. Writing it would be an invention, and
        it is the specific invention this constant exists to prevent."""
        root = self.env.ref("base.user_root")
        user = self._user()
        group = self._group()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        row = self._rows_since(mark, [("user_id", "=", user.id)])

        self.assertNotEqual(
            row.actor, root.name,
            "the record names uid 1's display name (%r) as the actor" % root.name)
        self.assertEqual(row.actor, SYSTEM_ACTOR)

    def test_a_change_made_by_a_real_user_names_that_user_and_is_attributable(self):
        actor = self._actor()
        user = self._user()
        group = self._group()
        self._flush_tracking()
        mark = self._watermark()

        user.with_user(actor).write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()

        row = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(
            len(row), 1,
            "a grant made by a real user produced %d row(s)" % len(row))
        self.assertEqual(
            row.changed_by_id, actor,
            "the row does not point at the user who made the change")
        self.assertEqual(
            row.actor, actor.name,
            "the actor snapshot is %r rather than the acting user's name; "
            "without it a deleted account leaves a change nobody can be "
            "attached to" % row.actor)
        self.assertIs(
            row.attributable, True,
            "a change made by a named person is flagged unattributable, which "
            "understates the record in the one direction nobody checks")

    def test_the_two_actors_are_distinguishable_in_one_period(self):
        """Both kinds in one record, because the flag is only useful if a
        reader can separate them without reading `actor` as a username."""
        actor = self._actor()
        user = self._user()
        first = self._group("first")
        second = self._group("second")
        self._flush_tracking()
        mark = self._watermark()

        user.write({self.groups_field: [(4, first.id)]})
        user.with_user(actor).write({self.groups_field: [(4, second.id)]})
        self._flush_tracking()

        rows = self._rows_since(mark, [("user_id", "=", user.id)])
        self.assertEqual(len(rows), 2)
        by_group = {r.group_id.id: r for r in rows}
        self.assertIs(by_group[first.id].attributable, False)
        self.assertIs(by_group[second.id].attributable, True)
        self.assertEqual(by_group[first.id].actor, SYSTEM_ACTOR)
        self.assertEqual(by_group[second.id].actor, actor.name)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheRecordIsAppendOnly(AccessChangeCase):
    """`write` and `unlink` raise, and they raise under `sudo()` too.

    The argument is `nrs.asset.custody`'s and it holds harder here, because
    the thing being protected is the evidence of who was given access. An ACL
    is configuration: one `1,1,1,1` line in the CSV and an internal user could
    `call_kw` a backdated row naming an arbitrary actor into a record that
    then cannot be corrected, because this model refuses correction by design.

    So the guard is on the model, and it is exercised under `sudo()` — which
    bypasses every ACL and record rule in Odoo, and which every API route in
    this codebase calls on every request.
    """

    def _a_row(self):
        user = self._user()
        group = self._group()
        mark = self._watermark()
        user.write({self.groups_field: [(4, group.id)]})
        return self._rows_since(mark, [("user_id", "=", user.id)])

    def test_write_raises(self):
        with self.assertRaises(UserError):
            self._a_row().write({"actor": "somebody else"})

    def test_write_raises_under_sudo(self):
        with self.assertRaises(UserError):
            self._a_row().sudo().write({"actor": "somebody else"})

    def test_unlink_raises(self):
        with self.assertRaises(UserError):
            self._a_row().unlink()

    def test_unlink_raises_under_sudo(self):
        with self.assertRaises(UserError):
            self._a_row().sudo().unlink()

    def test_the_message_says_it_refuses_sudo(self):
        """An error that does not explain itself sends somebody looking for
        the ACL that is stopping them, and there is not one."""
        with self.assertRaises(UserError) as caught:
            self._a_row().sudo().unlink()
        self.assertIn(
            "sudo", str(caught.exception).lower(),
            "the refusal does not mention sudo, so the reader is left to "
            "hunt for an access rule that does not exist")

    def test_a_hand_written_row_is_refused(self):
        """`create` is guarded too, so that the record says what happened
        rather than what somebody typed. Without it an append-only model is
        a place to plant a row nobody can remove."""
        with self.assertRaises(UserError):
            self.Change.create({
                "event": ACCESS_EVENT_GRANTED,
                "actor": "invented",
                "attributable": True,
                "changed_at": "2020-01-01 00:00:00",
            })

    def test_a_hand_written_row_is_refused_under_sudo(self):
        with self.assertRaises(UserError):
            self.Change.sudo().create({
                "event": ACCESS_EVENT_REMOVED,
                "actor": "invented",
                "source": "user_write",
            })

    def test_a_real_membership_change_still_writes_one(self):
        """The guard must not have closed the only door that should be open."""
        self.assertEqual(len(self._a_row()), 1)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestDeletingAUserDoesNotEndTheRecordMidSentence(AccessChangeCase):
    """A cascade erases every membership row a deleted user had.

    `res_groups_users_rel` has `ON DELETE CASCADE` on both foreign keys, so
    without a hook an auditor would see the grants and never the fact that the
    account and all its access went away. The removals are recorded BEFORE
    `super().unlink()` runs, and the identity snapshots are taken while the
    user still exists — which is what makes a deleted account's history still
    legible afterwards.
    """

    def _deleted_user(self):
        user = self._user()
        group = self._group()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        login, name = user.login, user.name
        held = set(user[self.groups_field].ids)
        mark = self._watermark()
        user.unlink()
        # `flush_all` rather than `_flush_tracking` here: the account is gone,
        # and running the precommit callbacks over a deleted record is a
        # question about `mail` rather than about this record. Invalidate,
        # because the foreign key was set null by POSTGRES on delete and the
        # ORM cache is still holding the id it had a moment ago.
        self.env.flush_all()
        self.env.invalidate_all()
        # Scoped on the login SNAPSHOT, which is the only handle left: the
        # foreign key went null with the account.
        rows = self._rows_since(mark, [("user_login", "=", login)])
        return rows, login, name, held, group

    def test_deleting_a_user_records_the_removals_before_the_cascade_erases_them(self):
        rows, _login, _name, held, group = self._deleted_user()

        self.assertTrue(
            rows,
            "deleting a user recorded nothing. The cascade has already erased "
            "the membership rows, so this history is now unrecoverable.")
        self.assertEqual(set(rows.mapped("event")), {ACCESS_EVENT_REMOVED})
        self.assertEqual(
            set(rows.mapped("source")), {"user_unlink"},
            "a deletion is labelled as an ordinary write, so a reader cannot "
            "tell an account being closed from a group being taken away")
        self.assertEqual(
            set(rows.mapped("group_id").ids), held,
            "the rows do not cover every group the account held at deletion")
        self.assertIn(group.id, rows.mapped("group_id").ids)

    def test_the_login_and_name_snapshots_survive_the_account(self):
        rows, login, name, _held, _group = self._deleted_user()
        self.assertEqual(set(rows.mapped("user_login")), {login})
        self.assertEqual(
            set(rows.mapped("user_name")), {name},
            "the name snapshot did not survive the account, so a deleted "
            "user's access history now names nobody")

    def test_the_user_link_goes_null_but_the_row_does_not(self):
        """`ondelete='set null'` rather than cascade, deliberately: deleting a
        user must not erase the record of what they were given. The null is
        the expected outcome and the snapshot is what carries the meaning."""
        rows, _login, _name, _held, _group = self._deleted_user()
        self.assertFalse(
            any(rows.mapped("user_id")),
            "the rows still point at a user record that no longer exists")
        self.assertTrue(
            all(rows.mapped("actor")),
            "a row lost its actor when the account went")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestAChangeThatChangesNothingWritesNothing(AccessChangeCase):
    """The reason the hooks diff instead of reading `vals`.

    Eight security XML files re-apply group links on EVERY module upgrade
    rather than only on install, and `(6, 0, ids)` does not say what it
    replaced. A hook that trusted the command list would write a grant every
    time any of them ran, and after a year the record would be mostly upgrade
    noise with the real events buried in it — which is how an append-only
    record becomes unreadable without anything ever being wrong.
    """

    def test_relinking_a_group_the_user_already_holds_writes_no_row(self):
        user = self._user()
        group = self._group()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        mark = self._watermark()

        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()

        self.assertEqual(
            len(self._rows_since(mark, [("user_id", "=", user.id)])), 0,
            "re-linking a group the user already holds wrote a grant. Every "
            "module upgrade re-applies these links, so the record will fill "
            "with grants that never happened.")

    def test_relinking_a_member_from_the_group_side_writes_no_row(self):
        user = self._user()
        group = self._group()
        group.write({self.users_field: [(4, user.id)]})
        self._flush_tracking()
        mark = self._watermark()

        group.write({self.users_field: [(4, user.id)]})
        self._flush_tracking()

        self.assertEqual(
            len(self._rows_since(mark, [("group_id", "=", group.id)])), 0,
            "re-linking an existing member from the group side wrote a grant")

    def test_rewriting_the_same_membership_wholesale_writes_no_row(self):
        """`(6, 0, ids)` with the ids it already has. This is what saving a
        user form without touching the groups widget produces, and it is the
        single most common write on the model."""
        user = self._user()
        group = self._group()
        user.write({self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        unchanged = user[self.groups_field].ids
        mark = self._watermark()

        user.write({self.groups_field: [(6, 0, unchanged)]})
        self._flush_tracking()

        self.assertEqual(
            len(self._rows_since(mark, [("user_id", "=", user.id)])), 0,
            "a wholesale rewrite of the membership it already had wrote "
            "%d row(s); saving a user form is not an access event"
            % len(self._rows_since(mark, [("user_id", "=", user.id)])))

    def test_an_implication_rewritten_unchanged_writes_no_row(self):
        implier = self._group("implier")
        implied = self._group("implied")
        implier.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()
        mark = self._watermark()

        implier.write({"implied_ids": [(6, 0, implier.implied_ids.ids)]})
        self._flush_tracking()

        self.assertEqual(
            len(self._rows_since(mark, [("group_id", "=", implier.id)])), 0,
            "rewriting an unchanged implication set wrote an edge event")


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThePeriodBeforeTheRecordCannotBeAnswered(AccessChangeCase):
    """The assertion this whole file exists to protect.

    A forward record begins when it begins. For the next twelve months the
    period an auditor asks about will mostly fall BEFORE that instant, and the
    one thing the report must never do is answer it with an empty table — an
    empty table reads as "no access changed", and what is true is "nothing was
    being recorded". The distinction is the entire point of INT-10.

    So `coverage` must stay `none` for such a period however much the record
    now holds: rows from after the period say nothing about the period. The
    other two branches are asserted alongside it, because a `none` that is
    returned unconditionally would pass the first test forever.

    Each test owns the whole table: `_record_begins_at` empties it and puts
    this test's rows at one pinned instant, so the answers are a function of
    the boundary logic and not of what the tenant happened to hold. The delete
    rolls back with the test.
    """

    #: Periods named relative to `RECORD_BEGINS` (2024-03-15 09:30).
    BEFORE = (date(2023, 1, 1), date(2023, 12, 31))
    STRADDLING = (date(2024, 1, 1), date(2024, 12, 31))

    def test_a_period_ending_before_the_record_began_answers_none(self):
        self._record_begins_at(RECORD_BEGINS)

        summary = self.Users.access_change_report(*self.BEFORE)["summary"]

        self.assertEqual(
            summary["coverage"], ACCESS_COVERAGE_NONE,
            "a period that ended before the access record began was answered "
            "%r. The record holds rows, but every one of them is from after "
            "the period; claiming any coverage of it asserts that somebody "
            "was writing things down when nobody was."
            % summary["coverage"])
        self.assertEqual(
            summary["group_changes_in_period"], 0,
            "rows from outside the period were counted into it")

    def test_the_statement_says_the_record_begins_after_the_period(self):
        """The enum tells a renderer what to do; the sentence tells a person
        why the table is empty. A reader who sees only the empty table reads
        it as a quiet quarter, which is the misreading the whole report is
        built to prevent."""
        self._record_begins_at(RECORD_BEGINS)

        statement = self.Users.access_change_report(*self.BEFORE)["summary"][
            "statement"]

        self.assertIn("AFTER the end of the period", statement)
        self.assertIn(
            str(RECORD_BEGINS), statement,
            "the statement does not quote the instant it measured, so a "
            "reader cannot tell a measurement from a boilerplate sentence")
        self.assertIn("must not be read as", statement)

    def test_no_group_change_event_is_published_for_that_period(self):
        """The count and the table have to agree. A `none` verdict above a
        list that still carried grants would be the worst of both."""
        self._record_begins_at(RECORD_BEGINS)

        report = self.Users.access_change_report(*self.BEFORE)
        leaked = [e for e in report["events"]
                  if e["event"] in MEMBERSHIP_EVENTS]

        self.assertEqual(
            leaked, [],
            "group-change events from outside the period were published into "
            "it: %s" % leaked)

    def test_a_period_straddling_the_start_answers_partial(self):
        """Part of the period is covered and part of it never can be, and the
        honest answer says which — plus that the rows shown are a LOWER
        BOUND."""
        self._record_begins_at(RECORD_BEGINS)

        summary = self.Users.access_change_report(*self.STRADDLING)["summary"]

        self.assertEqual(
            summary["coverage"], ACCESS_COVERAGE_PARTIAL,
            "a period that begins before the record and ends after it was "
            "answered %r" % summary["coverage"])
        self.assertIn("part-way through the period", summary["statement"])
        self.assertIn("LOWER BOUND", summary["statement"])

    def test_a_period_wholly_after_the_start_answers_recorded(self):
        """`recorded` is the branch that did not exist before the record did.
        It is the only one that entitles a reader to treat an empty table as
        "nothing happened", so it must be reachable AND must not be reached
        one day too early."""
        user, group = self._record_begins_at(RECORD_BEGINS)
        # A second change, after the pinned instant and inside the period.
        user.write({self.groups_field: [(3, group.id)]})
        self._flush_tracking()

        today = fields.Datetime.now().date()
        summary = self.Users.access_change_report(
            date(2024, 3, 16), today)["summary"]

        self.assertEqual(
            summary["coverage"], ACCESS_COVERAGE_RECORDED,
            "a period beginning after the record did was answered %r; the "
            "branch the forward record was built for is unreachable"
            % summary["coverage"])
        self.assertEqual(
            summary["group_changes_in_period"], 1,
            "the one change made inside the period was not counted")
        self.assertIn(
            SYSTEM_ACTOR, summary["statement"],
            "the `recorded` statement does not warn that an upgrade, a cron "
            "or the command line is attributed to the system actor rather "
            "than to a person")

    def test_the_recorded_change_is_published_as_an_exact_event(self):
        """The row reaches the table a consumer pages, with its own timestamp
        and its own actor — not a last-write smear off `res_users`."""
        user, group = self._record_begins_at(RECORD_BEGINS)
        user.write({self.groups_field: [(3, group.id)]})
        self._flush_tracking()

        today = fields.Datetime.now().date()
        report = self.Users.access_change_report(date(2024, 3, 16), today)
        mine = [e for e in report["events"]
                if e["user_id"] == user.id and e["event"] in MEMBERSHIP_EVENTS]

        self.assertEqual(len(mine), 1, "the recorded removal is not in the "
                                       "published events")
        self.assertEqual(mine[0]["event"], ACCESS_EVENT_REMOVED)
        self.assertEqual(mine[0]["precision"], "exact")
        self.assertIs(mine[0]["attributable"], False)
        self.assertEqual(mine[0]["actor"]["name"], SYSTEM_ACTOR)
        self.assertIn(group.name, mine[0]["group"] or "")
        self.assertIn("myservice_api_access_change", mine[0]["evidence"])


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheRecordStartIsMeasuredAndTheCountIsReal(AccessChangeCase):
    """Two numbers that used to be constants and now have to be measured.

    `record_starts_at` is deliberately NOT the migration date: a tenant
    upgraded and then left alone has a record that begins when something first
    happened on it, and claiming the upgrade instant would assert coverage of
    a period in which nothing was being written down. And
    `group_changes_in_period` was a STRUCTURAL zero — a hardcoded 0 published
    so a consumer saw the absence rather than inferring it. It is now a count,
    and a count that is still hardcoded looks exactly the same on a quiet
    tenant.

    These tests own the whole table for the same reason as the class above.
    """

    def test_record_starts_at_is_the_earliest_row_and_not_a_constant(self):
        user, _group = self._record_begins_at(RECORD_BEGINS)
        # A later change, which must NOT move the start.
        user.write({self.groups_field: [(4, self._group("later").id)]})
        self._flush_tracking()

        earliest = self.Change.sudo().search(
            [], order="changed_at, id", limit=1)
        fidelity = self.Users.access_change_fidelity()

        self.assertEqual(
            self.Change.record_starts_at(), earliest.changed_at,
            "`record_starts_at` is not the earliest row this tenant holds")
        self.assertEqual(
            fidelity["record_starts_at"], str(RECORD_BEGINS),
            "the published start is %r rather than the instant of the "
            "earliest row; a later change moved it, or it is a constant"
            % fidelity["record_starts_at"])
        self.assertGreaterEqual(fidelity["record_rows"], 2)

    def test_record_starts_at_is_none_when_the_tenant_holds_no_rows(self):
        """The state every tenant is in until its first membership change.

        The honest answer is `None` and an honest `none` coverage — NOT a
        claim that the record begins today. A tenant that has the recorder
        installed and has recorded nothing has a record that has not begun.
        """
        self._empty_the_record()

        fidelity = self.Users.access_change_fidelity()
        self.assertIsNone(
            self.Change.record_starts_at(),
            "`record_starts_at` invented a start for a tenant holding no rows")
        self.assertIsNone(fidelity["record_starts_at"])
        self.assertEqual(fidelity["record_rows"], 0)
        self.assertIn(
            "holds NO access-change rows", fidelity["notes"]["record_start"],
            "the note does not say the record has not begun here")

        summary = self.Users.access_change_report(
            date(2023, 1, 1), date(2023, 12, 31))["summary"]
        self.assertEqual(
            summary["coverage"], ACCESS_COVERAGE_NONE,
            "a tenant with no access record claimed coverage of a period")

    def test_the_four_recorded_facts_move_by_measurement_not_by_deployment(self):
        """`group_granted` is answerable because rows EXIST, not because the
        code shipped. A tenant that has the recorder and has recorded nothing
        must still list it as not recoverable — otherwise the fidelity block
        promises a history the tenant does not have, on the strength of a
        deploy."""
        recorded_facts = {"group_granted", "group_removed",
                          "group_change_actor", "group_change_timestamp"}

        self._empty_the_record()
        empty = self.Users.access_change_fidelity()
        self.assertFalse(
            recorded_facts & set(empty["recoverable"]),
            "a tenant holding no access-change rows claims %s are "
            "recoverable" % sorted(recorded_facts & set(empty["recoverable"])))
        self.assertTrue(recorded_facts <= set(empty["not_recoverable"]))

        self._record_begins_at(RECORD_BEGINS)
        live = self.Users.access_change_fidelity()
        self.assertTrue(
            recorded_facts <= set(live["recoverable"]),
            "a tenant whose record has begun still lists %s as not "
            "recoverable" % sorted(recorded_facts - set(live["recoverable"])))
        self.assertFalse(recorded_facts & set(live["not_recoverable"]))

    def test_group_changes_in_period_counts_the_rows_it_found(self):
        """Not the old hardcoded zero.

        The table holds only this test's rows, so the expected count is exact
        rather than a floor — a `>= 1` here would pass on a tenant with one
        stray row and on a count that had silently stopped incrementing.
        """
        self._empty_the_record()
        user = self._user()
        first = self._group("first")
        second = self._group("second")
        user.write({self.groups_field: [(4, first.id), (4, second.id)]})
        user.write({self.groups_field: [(3, first.id)]})
        self._flush_tracking()

        expected = self.Change.sudo().search_count(
            [("event", "in", list(MEMBERSHIP_EVENTS))])
        today = fields.Datetime.now().date()
        summary = self.Users.access_change_report(
            today - timedelta(days=1), today + timedelta(days=1))["summary"]

        self.assertGreaterEqual(
            expected, 4,
            "the fixture wrote %d membership rows; it should have written the "
            "create default, two grants and one removal, so this test is no "
            "longer exercising what it says" % expected)
        self.assertEqual(
            summary["group_changes_in_period"], expected,
            "`group_changes_in_period` is %d where the record holds %d "
            "membership rows in the period. It is no longer the structural "
            "zero and it must be a count."
            % (summary["group_changes_in_period"], expected))

    def test_implication_changes_are_counted_separately_from_membership(self):
        """They are a different fact — what a group MEANS, not who is in it —
        and they name no user, so they cannot be paged into the events list.
        Folding them into `group_changes_in_period` would inflate the number
        an auditor reads as "grants and removals"."""
        self._empty_the_record()
        implier = self._group("implier")
        implied = self._group("implied")
        user = self._user()
        user.write({self.groups_field: [(4, implier.id)]})
        self._flush_tracking()

        today = fields.Datetime.now().date()
        period = (today - timedelta(days=1), today + timedelta(days=1))
        before = self.Users.access_change_report(*period)["summary"]

        implier.write({"implied_ids": [(4, implied.id)]})
        self._flush_tracking()
        after = self.Users.access_change_report(*period)["summary"]

        self.assertEqual(
            after["implication_changes_in_period"],
            before["implication_changes_in_period"] + 1,
            "an implication change was not counted")
        self.assertEqual(
            after["group_changes_in_period"],
            before["group_changes_in_period"],
            "an implication change was counted as a membership change, so "
            "the number an auditor reads as grants and removals now includes "
            "edges that moved nobody")
