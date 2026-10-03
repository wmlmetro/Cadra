"""An account switched off, and back on, is in the access record — handoff 45 §1.

The auditor's question is *"who removed this person's access, and when"*.
Until handoff 45 the access record (`myservice.api.access.change`) held group
grants and removals and the answer to that question sat in
`res_users.write_uid` / `write_date`, which the next write overwrites. These
tests prove the record now holds `deactivated` and `reactivated`, and that
the access-changes report publishes them.

**Driven WITHOUT the API on purpose.** The hook is on `res.users.write`, not on
`POST /users/<id>/deactivate`, because the flag has more than one writer: the
back office's *Archive* (`action_archive`, which assigns the field and so
calls `write`), a script, core's portal self-deletion. A test that went
through the route would prove the route; these prove the place every writer
converges. The route is driven over HTTP in
`tests/test_access_record_deactivation.py`.

Scoped the same way as `test_access_change_record.py`, whose fixtures this
file reuses: every assertion about rows is about rows above a watermark taken
in the test, never about the tenant's history.

Run with:
    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d test19 -u myservice_api --test-enable \\
      --test-tags /myservice_api --stop-after-init --workers=0 \\
      --http-port=8099 --gevent-port=8098
"""
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.myservice_api.models.access_change import (
    ACCESS_CHANGE_SKIP_KEY,
    ACCESS_EVENT_DEACTIVATED,
    ACCESS_EVENT_GRANTED,
    ACCESS_EVENT_REACTIVATED,
    ACCOUNT_STATE_EVENTS,
    SYSTEM_ACTOR,
)
from odoo.addons.myservice_api.models.audit_access import (
    ACCESS_COVERAGE_NONE,
    ACCESS_COVERAGE_PARTIAL,
    ACCESS_COVERAGE_RECORDED,
)

from .test_access_change_record import AccessChangeCase

#: The four facts the account-state half of the record answers, moved between
#: `recoverable` and `not_recoverable` by measurement of ITS OWN start.
ACCOUNT_STATE_FACTS = frozenset((
    'account_deactivated', 'account_reactivated',
    'account_state_change_actor', 'account_state_change_timestamp'))


class AccountStateCase(AccessChangeCase):

    def _state_rows_since(self, mark, user=None):
        domain = [("event", "in", list(ACCOUNT_STATE_EVENTS))]
        if user is not None:
            domain.append(("user_id", "=", user.id))
        return self._rows_since(mark, domain)

    def _today_period(self):
        today = fields.Datetime.now().date()
        return today - timedelta(days=1), today + timedelta(days=1)

    def _empty_account_state_rows(self):
        """Only the account-state half, in SQL, because the model refuses
        `unlink()`. A TransactionCase rolls it back."""
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM %s WHERE event IN %%s" % self.Change._table,
            (tuple(ACCOUNT_STATE_EVENTS),))
        self.env.invalidate_all()


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestADeactivationIsOneRow(AccountStateCase):
    """The back office's Archive and Unarchive — no API anywhere."""

    def test_archive_from_the_back_office_writes_one_deactivated_row(self):
        actor = self._actor()
        person = self._user()
        mark = self._watermark()

        person.with_user(actor).action_archive()
        self._flush_tracking()

        rows = self._state_rows_since(mark)
        self.assertEqual(
            len(rows), 1,
            "archiving one account wrote %d account-state row(s) (of %d rows "
            "written in all). One deactivation is one event."
            % (len(rows), len(self._rows_since(mark))))
        self.assertEqual(rows.event, ACCESS_EVENT_DEACTIVATED)
        self.assertEqual(rows.user_id, person)
        self.assertEqual(rows.user_login, person.login)
        self.assertEqual(rows.source, "user_active")
        self.assertFalse(rows.group_id, "a deactivation names no group")
        self.assertFalse(rows.group_name)
        self.assertFalse(rows.implied_group_id)
        self.assertEqual(
            rows.changed_by_id, actor,
            "the row does not name the account that pressed Archive — the "
            "whole point of the event is WHO removed the access")
        self.assertEqual(rows.changed_by_login, actor.login)
        self.assertTrue(rows.attributable)
        self.assertEqual(rows.actor, actor.name)

    def test_unarchive_writes_one_reactivated_row(self):
        actor = self._actor()
        person = self._user()
        person.with_user(actor).action_archive()
        self._flush_tracking()
        mark = self._watermark()

        person.with_user(actor).action_unarchive()
        self._flush_tracking()

        rows = self._state_rows_since(mark)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.event, ACCESS_EVENT_REACTIVATED)
        self.assertEqual(rows.user_id, person)
        self.assertEqual(rows.changed_by_id, actor)
        self.assertFalse(rows.group_id)

    def test_a_plain_write_of_the_flag_is_recorded_the_same_way(self):
        """A script's `write({'active': False})` is the same door."""
        actor = self._actor()
        person = self._user()
        mark = self._watermark()
        person.with_user(actor).write({"active": False})
        person.with_user(actor).write({"active": True})
        self._flush_tracking()
        self.assertEqual(
            self._state_rows_since(mark, person).mapped("event"),
            [ACCESS_EVENT_DEACTIVATED, ACCESS_EVENT_REACTIVATED])

    def test_a_shell_or_upgrade_is_the_system_not_a_person(self):
        """The test env is SUPERUSER — what a shell, a cron and an upgrade
        arrive as. The row says `__system__` and flags itself."""
        person = self._user()
        mark = self._watermark()
        self.assertEqual(self.env.uid, 1)
        person.write({"active": False})
        self._flush_tracking()
        row = self._state_rows_since(mark, person)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.actor, SYSTEM_ACTOR)
        self.assertFalse(row.attributable)
        self.assertFalse(row.changed_by_id)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestWhatIsNotADeactivation(AccountStateCase):

    def test_a_write_that_does_not_move_the_flag_writes_nothing(self):
        actor = self._actor()
        live = self._user()
        gone = self._user()
        gone.with_user(actor).action_archive()
        self._flush_tracking()
        mark = self._watermark()

        # False -> False, True -> True, and Archive on an archived account.
        gone.with_user(actor).write({"active": False})
        live.with_user(actor).write({"active": True})
        gone.with_user(actor).action_archive()
        self._flush_tracking()

        self.assertFalse(
            self._rows_since(mark),
            "a write that did not move `active` produced %d row(s): %s. A "
            "no-op is not a deactivation, and an app that re-sends the flag "
            "on every save would fill the record with them."
            % (len(self._rows_since(mark)),
               self._rows_since(mark).mapped("event")))

    def test_a_batch_records_only_the_accounts_that_moved(self):
        actor = self._actor()
        live = self._user()
        gone = self._user()
        gone.with_user(actor).action_archive()
        self._flush_tracking()
        mark = self._watermark()

        (live | gone).with_user(actor).write({"active": False})
        self._flush_tracking()

        rows = self._state_rows_since(mark)
        self.assertEqual(
            rows.mapped("user_id"), live,
            "of the 2 accounts in the write, only the 1 that was active was "
            "deactivated; the record named %s" % rows.mapped("user_login"))

    def test_an_account_created_inactive_is_not_a_deactivation(self):
        mark = self._watermark()
        person = self._user(active=False)
        self._flush_tracking()
        self.assertFalse(person.active)
        self.assertFalse(
            self._state_rows_since(mark, person),
            "creating an account inactive wrote a `deactivated` row; nobody's "
            "access was taken away")
        # Its groups are still recorded, as for any create.
        self.assertTrue(self._rows_since(
            mark, [("user_id", "=", person.id),
                   ("event", "=", ACCESS_EVENT_GRANTED)]))

    def test_the_skip_key_suppresses_it_like_every_other_row(self):
        person = self._user()
        mark = self._watermark()
        person.with_context(**{ACCESS_CHANGE_SKIP_KEY: True}).write(
            {"active": False})
        self._flush_tracking()
        self.assertFalse(self._state_rows_since(mark, person))

    def test_a_groups_change_in_the_same_write_records_both(self):
        actor = self._actor()
        person = self._user()
        group = self._group()
        mark = self._watermark()
        person.with_user(actor).write({
            "active": False, self.groups_field: [(4, group.id)]})
        self._flush_tracking()
        events = sorted(self._rows_since(
            mark, [("user_id", "=", person.id)]).mapped("event"))
        self.assertEqual(events, sorted([ACCESS_EVENT_GRANTED,
                                         ACCESS_EVENT_DEACTIVATED]))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheRowIsAppendOnly(AccountStateCase):

    def test_a_deactivation_row_cannot_be_edited_or_deleted(self):
        person = self._user()
        mark = self._watermark()
        person.write({"active": False})
        self._flush_tracking()
        row = self._state_rows_since(mark, person)
        self.assertEqual(len(row), 1)
        with self.assertRaises(UserError):
            row.sudo().write({"event": ACCESS_EVENT_REACTIVATED})
        with self.assertRaises(UserError):
            row.sudo().unlink()
        with self.assertRaises(UserError):
            self.Change.sudo().create({
                "event": ACCESS_EVENT_DEACTIVATED, "user_id": person.id,
                "actor": "somebody", "attributable": True})


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheReportPublishesThem(AccountStateCase):

    def test_both_events_are_in_the_report_with_actor_and_no_group(self):
        actor = self._actor()
        person = self._user()
        self._flush_tracking()
        person.with_user(actor).action_archive()
        person.with_user(actor).action_unarchive()
        self._flush_tracking()

        report = self.Users.access_change_report(*self._today_period())
        mine = [e for e in report["events"]
                if e["user_id"] == person.id
                and e["event"] in ACCOUNT_STATE_EVENTS]
        self.assertEqual(
            [e["event"] for e in mine],
            [ACCESS_EVENT_DEACTIVATED, ACCESS_EVENT_REACTIVATED],
            "the report did not publish the deactivation and reactivation "
            "this test made (it published %d events in all)"
            % len(report["events"]))
        for e in mine:
            self.assertEqual(e["precision"], "exact")
            self.assertIn("group", e)
            self.assertIsNone(e["group"])
            self.assertIs(e["attributable"], True)
            self.assertEqual(e["actor"], {"id": actor.id, "name": actor.name})
            self.assertEqual(e["login"], person.login)
            self.assertTrue(e["evidence"].startswith(
                "myservice_api_access_change.id="))
        self.assertEqual(report["summary"]["events_in_period"],
                         len(report["events"]))

    def test_the_counter_moves_and_the_other_two_do_not(self):
        person = self._user()
        self._flush_tracking()
        period = self._today_period()
        before = self.Users.access_change_report(*period)["summary"]

        person.write({"active": False})
        self._flush_tracking()
        after = self.Users.access_change_report(*period)["summary"]

        self.assertEqual(
            after["account_state_changes_in_period"],
            before["account_state_changes_in_period"] + 1,
            "one deactivation moved the account-state count from %d to %d"
            % (before["account_state_changes_in_period"],
               after["account_state_changes_in_period"]))
        self.assertEqual(
            after["group_changes_in_period"],
            before["group_changes_in_period"],
            "a deactivation was counted as a group change")
        self.assertEqual(
            after["implication_changes_in_period"],
            before["implication_changes_in_period"],
            "a deactivation was counted as an implication change")
        self.assertEqual(after["account_state_changes_not_shown"],
                         before["account_state_changes_not_shown"])

    def test_the_account_state_boundary_is_its_own_and_measured(self):
        self._empty_account_state_rows()
        fidelity = self.Users.access_change_fidelity()
        self.assertIsNone(fidelity["account_state_record_starts_at"])
        self.assertEqual(fidelity["account_state_record_rows"], 0)
        self.assertTrue(ACCOUNT_STATE_FACTS <= set(fidelity["not_recoverable"]))
        self.assertFalse(ACCOUNT_STATE_FACTS & set(fidelity["recoverable"]))
        self.assertIn("NO deactivation or reactivation rows",
                      fidelity["notes"]["account_state"])
        summary = self.Users.access_change_report(*self._today_period())[
            "summary"]
        self.assertEqual(summary["account_state_coverage"],
                         ACCESS_COVERAGE_NONE)

        person = self._user()
        person.write({"active": False})
        self._flush_tracking()
        live = self.Users.access_change_fidelity()
        self.assertIsNotNone(live["account_state_record_starts_at"])
        self.assertEqual(live["account_state_record_rows"], 1)
        self.assertTrue(ACCOUNT_STATE_FACTS <= set(live["recoverable"]))
        self.assertFalse(ACCOUNT_STATE_FACTS & set(live["not_recoverable"]))

    def test_the_three_coverage_answers(self):
        began = "2026-01-01 00:00:00"
        fidelity = {"account_state_record_starts_at": began}
        cov = self.Users._access_account_state_coverage

        coverage, sentence = cov(
            fidelity, start=datetime(2025, 1, 1),
            end=datetime(2025, 12, 31, 23, 59, 59))
        self.assertEqual(coverage, ACCESS_COVERAGE_NONE)
        self.assertIn(began, sentence)

        coverage, sentence = cov(
            fidelity, start=datetime(2025, 6, 1),
            end=datetime(2026, 6, 30), changes=3)
        self.assertEqual(coverage, ACCESS_COVERAGE_PARTIAL)
        self.assertIn("LOWER BOUND", sentence)
        self.assertIn("the 3 below", sentence)

        coverage, sentence = cov(
            fidelity, start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 28), changes=2)
        self.assertEqual(coverage, ACCESS_COVERAGE_RECORDED)
        self.assertIn("— 2 —", sentence)

        coverage, _sentence = cov({"account_state_record_starts_at": None})
        self.assertEqual(coverage, ACCESS_COVERAGE_NONE)

    def test_the_statement_carries_the_account_state_sentence(self):
        person = self._user()
        person.write({"active": False})
        self._flush_tracking()
        statement = self.Users.access_change_report(*self._today_period())[
            "summary"]["statement"]
        self.assertIn("deactivation", statement.lower())
