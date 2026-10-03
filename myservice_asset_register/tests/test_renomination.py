"""Ask someone else — re-pointing a pending request. Handoff 45, G.1(b).

WHAT THIS FILE IS FOR
---------------------
Handoff 43 measured a request left waiting on an approver whose account had
been deactivated, with nothing on the row saying so. The ruling: deactivation
is NEVER blocked, so the stranded request is fixed forward — a pending
request can be re-pointed at a different approver, as an act with a name and
a time on it. And: *the model's `write` refuses everything but `_transition`;
keep the refusal and add the one path, do not loosen the model.*

So the properties asserted here, in order:

    1. **Who may** — the requester and an administrator; not the approver
       currently asked, not a bystander. Refused in the model, so a refusal
       holds wherever it is asked from.
    2. **Who may be asked** — the same four tests a first nomination passes
       (active, eligible, not the requester) plus not the person already
       asked; and a reason. Every refusal writes NOTHING.
    3. **The act** — the append-only row says who, from whom, to whom, when
       and why; `approver_id` moves; the old approver's inbox empties and the
       new one's fills; the new approver can then decide it.
    4. **The one path** — `write` still refuses `approver_id` without the
       action, plainly and under `sudo()`.
    5. **The row is append-only through THE mixin** — edited, deleted or
       hand-written, it is refused in its own words, and the guard is the
       mixin's rather than a fifth copy.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init --workers=0
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_change_request import ChangeRequestCase

RENOMINATION = "nrs.asset.change.request.renomination"
_GUARD_METHODS = ("create", "write", "unlink", "_resolve_source")


class RenominationCase(ChangeRequestCase):

    def setUp(self):
        super().setUp()
        self.Renomination = self.env[RENOMINATION]
        # A second eligible approver to re-point at. `self.approver` is the
        # one the request is raised naming; `self.requester` raises it.
        self.instead = self._user("renomination-test-instead", manager=True)
        # An administrator who is NOT an asset manager and did not raise the
        # request: the person who fixes a request whose requester has left.
        self.admin = self._user("renomination-test-admin", manager=False)
        self.admin.write({self._groups_field(): [
            (4, self.env.ref("base.group_system").id)]})
        self.asset = self._asset(location_id=self.room.id)

    def _groups_field(self):
        Users = self.env["res.users"]
        return "group_ids" if "group_ids" in Users._fields else "groups_id"

    def _rows(self, req):
        return self.Renomination.search([("request_id", "=", req.id)],
                                        order="id")

    def _refused(self, req, who, new, reason="Away until next month"):
        """Assert the act is refused, and that it wrote NOTHING."""
        before = req.approver_id
        with self.assertRaises(UserError) as raised:
            req.with_user(who).action_renominate(new, reason)
        req.invalidate_recordset()
        self.assertEqual(req.approver_id, before,
                         "a refused re-nomination moved the approver")
        self.assertFalse(self._rows(req),
                         "a refused re-nomination left a row behind")
        return str(raised.exception)


# ═════════════════════════════════════════════════════════════════════
# 1 · Who may
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestWhoMayRenominate(RenominationCase):

    def test_the_requester_may(self):
        req = self._request(self.asset)
        self.assertTrue(req._may_renominate(self.requester))
        row = req.with_user(self.requester).action_renominate(
            self.instead, "Approver is on leave")
        self.assertEqual(req.approver_id, self.instead)
        self.assertEqual(row.renominated_by_id, self.requester)

    def test_an_administrator_may(self):
        """Not an asset manager, not the requester — and still may, because
        the requester may have left too, and somebody has to be able to
        unstick the queue. The write right is the model's rule, not an ACL's:
        this user holds no write access on the request model at all."""
        self.assertTrue(self.admin._is_admin())
        self.assertFalse(self.admin.has_group(self.CR.APPROVER_GROUP))
        req = self._request(self.asset)
        self.assertTrue(req._may_renominate(self.admin))
        row = req.with_user(self.admin).action_renominate(
            self.instead, "Requester and approver have both left")
        self.assertEqual(req.approver_id, self.instead)
        self.assertEqual(row.renominated_by_id, self.admin)

    def test_the_approver_currently_asked_may_not(self):
        """They can DECIDE it, which is the better act for somebody who wants
        it off their desk; handing it on is the requester's call."""
        req = self._request(self.asset)
        self.assertFalse(req._may_renominate(self.approver))
        message = self._refused(req, self.approver, self.instead)
        self.assertIn("who raised this request, or an administrator", message)

    def test_a_bystander_may_not(self):
        req = self._request(self.asset)
        self.assertFalse(req._may_renominate(self.bystander))
        message = self._refused(req, self.bystander, self.instead)
        self.assertIn("who raised this request", message)

    def test_another_eligible_approver_may_not(self):
        """Eligible to decide is not eligible to steer: one approver must not
        be able to take a request away from another."""
        req = self._request(self.asset)
        self.assertTrue(req._may_decide(self.instead))
        self.assertFalse(req._may_renominate(self.instead))
        self._refused(req, self.instead, self.instead)

    def test_nobody_may_once_it_is_decided(self):
        req = self._request(self.asset)
        req.with_user(self.requester).action_withdraw()
        self.assertFalse(req._may_renominate(self.requester))
        self.assertFalse(req._may_renominate(self.admin))
        message = self._refused(req, self.requester, self.instead)
        self.assertIn("already withdrawn", message)
        self.assertIn("A decision is taken once", message)


# ═════════════════════════════════════════════════════════════════════
# 2 · Who may be asked, and why
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestWhoMayBeAsked(RenominationCase):

    def test_a_deactivated_person_cannot_be_asked(self):
        """Re-pointing a request AT somebody who cannot sign in would
        recreate the defect this act exists to fix."""
        req = self._request(self.asset)
        self.instead.active = False
        message = self._refused(req, self.requester, self.instead)
        self.assertIn("cannot be asked: their account is deactivated",
                      message)

    def test_somebody_who_could_not_have_made_the_change_cannot_be_asked(
            self):
        req = self._request(self.asset)
        message = self._refused(req, self.requester, self.bystander)
        self.assertIn("could have made the change themselves", message)

    def test_the_requester_cannot_be_asked(self):
        """By the administrator, since the requester asking themselves is
        refused on who-may first."""
        req = self._request(self.asset)
        message = self._refused(req, self.admin, self.requester)
        self.assertIn("person who raised it", message)

    def test_the_person_already_asked_cannot_be_asked_again(self):
        req = self._request(self.asset)
        message = self._refused(req, self.requester, self.approver)
        self.assertIn("already the person being asked", message)

    def test_an_administrator_may_be_asked(self):
        """The same eligibility `_resolve_approver` applies at request time:
        an administrator could have made the change themselves."""
        req = self._request(self.asset)
        req.with_user(self.requester).action_renominate(
            self.admin, "Only the administrator is in this week")
        self.assertEqual(req.approver_id, self.admin)

    def test_a_reason_is_required(self):
        req = self._request(self.asset)
        for blank in ("", "   ", None):
            with self.subTest(reason=blank):
                message = self._refused(req, self.requester, self.instead,
                                        reason=blank)
                self.assertIn("Say why you are asking somebody else",
                              message)

    def test_nobody_named_is_refused(self):
        req = self._request(self.asset)
        message = self._refused(req, self.requester,
                                self.env["res.users"])
        self.assertIn("Name the person", message)

    def test_an_id_is_accepted_as_well_as_a_record(self):
        req = self._request(self.asset)
        req.with_user(self.requester).action_renominate(
            self.instead.id, "By id")
        self.assertEqual(req.approver_id, self.instead)


# ═════════════════════════════════════════════════════════════════════
# 3 · The act, and what it leaves behind
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheAct(RenominationCase):

    def test_the_row_says_who_from_whom_to_whom_when_and_why(self):
        req = self._request(self.asset)
        row = req.with_user(self.requester).action_renominate(
            self.instead, "  Approver has left the service  ")
        self.assertEqual(len(row), 1)
        self.assertEqual(row.request_id, req)
        self.assertEqual(row.from_approver_id, self.approver)
        self.assertEqual(row.from_approver_name, self.approver.display_name)
        self.assertEqual(row.to_approver_id, self.instead)
        self.assertEqual(row.to_approver_name, self.instead.display_name)
        self.assertEqual(row.renominated_by_id, self.requester)
        self.assertEqual(row.renominated_by_name,
                         self.requester.display_name)
        self.assertTrue(row.renominated_at)
        self.assertEqual(row.reason, "Approver has left the service",
                         "the reason is stored stripped")
        self.assertEqual(req.renomination_ids, row)

    def test_each_re_pointing_is_its_own_row_oldest_first(self):
        req = self._request(self.asset)
        first = req.with_user(self.requester).action_renominate(
            self.instead, "First")
        second = req.with_user(self.requester).action_renominate(
            self.approver, "Back again")
        self.assertEqual(req.renomination_ids, first | second)
        self.assertEqual(self._rows(req).ids, [first.id, second.id])
        self.assertEqual(second.from_approver_id, self.instead)
        self.assertEqual(second.to_approver_id, self.approver)
        self.assertEqual(req.approver_id, self.approver)

    def test_the_stranded_request_is_unstuck(self):
        """The whole of G.1 in one test. The approver is deactivated with the
        request pending — and that is NOT refused, because deactivation is
        never blocked. The request then says, on its face, that it is waiting
        on somebody who cannot sign in; it is re-pointed; and the new
        approver decides it."""
        req = self._request(self.asset)
        self.approver.active = False      # never blocked
        req.invalidate_recordset()
        self.assertEqual(req.state, "pending")
        self.assertFalse(req.approver_id.active,
                         "the request should name an approver who cannot "
                         "sign in — that is the fact G.1(a) publishes")
        req.with_user(self.requester).action_renominate(
            self.instead, "The approver's account is deactivated")
        self.assertEqual(req.approver_id, self.instead)
        req.with_user(self.instead).action_approve()
        self.assertEqual(req.state, "approved")
        self.assertEqual(self.asset.location_id, self.elsewhere)

    def test_renominating_moves_nothing_about_the_asset(self):
        moves_before = len(self._moves(self.asset))
        req = self._request(self.asset)
        req.with_user(self.requester).action_renominate(
            self.instead, "Asking somebody else")
        self.assertEqual(self.asset.location_id, self.room)
        self.assertEqual(len(self._moves(self.asset)), moves_before)
        self.assertEqual(req.state, "pending")

    def test_the_inbox_moves_with_it(self):
        """The doorbell follows the nomination: the old approver's activity is
        cleared and the new approver gets one. Asserted on the users, not on
        the count, so a failed schedule cannot pass as a cleared one."""
        req = self._request(self.asset)
        self.assertEqual(req.sudo().activity_ids.user_id, self.approver,
                         "precondition: the request rang the first doorbell")
        req.with_user(self.requester).action_renominate(
            self.instead, "Asking somebody else")
        self.assertEqual(req.sudo().activity_ids.user_id, self.instead)

    def test_the_new_approver_finds_it_waiting_on_them(self):
        req = self._request(self.asset)
        req.with_user(self.requester).action_renominate(
            self.instead, "Asking somebody else")
        self.assertIn(req, self.CR.pending_for(self.instead))
        self.assertNotIn(req, self.CR.pending_for(self.approver))

    def test_a_label_claimed_through_the_context_is_direct(self):
        """`test` is a statement about the evidence and is derived from the
        credential, never claimed — the mixin's rule, on a fourth model."""
        req = self._request(self.asset)
        row = req.with_user(self.requester).with_context(
            cadra_renomination_source="test",
        ).action_renominate(self.instead, "Claiming a label")
        self.assertEqual(row.source, "direct")

    def test_the_api_declares_its_source(self):
        req = self._request(self.asset)
        row = req.with_user(self.requester).with_context(
            cadra_renomination_source="api_renominate",
        ).action_renominate(self.instead, "Over the API")
        # `test` when the acting user is a test credential's user —
        # `myservice_api` relabels; these users are not, so it is the
        # declared source.
        self.assertEqual(row.source, "api_renominate")


# ═════════════════════════════════════════════════════════════════════
# 4 · The one path — `write` is not loosened
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestWriteIsStillShut(RenominationCase):

    def test_approver_id_is_not_writable_without_the_action(self):
        req = self._request(self.asset)
        with self.assertRaises(UserError) as raised:
            req.with_user(self.requester).write(
                {"approver_id": self.instead.id})
        self.assertIn("approve it, reject it, or withdraw it",
                      str(raised.exception))
        self.assertEqual(req.approver_id, self.approver)

    def test_nor_under_sudo(self):
        req = self._request(self.asset)
        with self.assertRaises(UserError):
            req.sudo().write({"approver_id": self.instead.id})
        self.assertEqual(req.approver_id, self.approver)
        self.assertFalse(self._rows(req))

    def test_a_decided_request_cannot_be_renominated_even_by_an_admin(self):
        req = self._request(self.asset)
        req.with_user(self.approver).action_reject(decision_reason="No")
        message = self._refused(req, self.admin, self.instead)
        self.assertIn("already rejected", message)


# ═════════════════════════════════════════════════════════════════════
# 5 · The row is append-only, through THE mixin
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheRowIsAppendOnly(RenominationCase):

    def _one_row(self):
        req = self._request(self.asset)
        return req.with_user(self.requester).action_renominate(
            self.instead, "One row")

    def test_an_edit_is_refused_under_sudo_in_its_own_words(self):
        row = self._one_row()
        with self.assertRaises(UserError) as raised:
            row.sudo().write({"reason": "rewritten"})
        self.assertIn("re-pointed to is append-only", str(raised.exception))
        self.assertIn("sudo", str(raised.exception))
        self.assertEqual(row.reason, "One row")

    def test_a_delete_is_refused_under_sudo_in_its_own_words(self):
        row = self._one_row()
        with self.assertRaises(UserError) as raised:
            row.sudo().unlink()
        self.assertIn("re-pointed to is append-only", str(raised.exception))
        self.assertTrue(row.exists())

    def test_a_hand_written_row_is_refused(self):
        req = self._request(self.asset)
        with self.assertRaises(UserError) as raised:
            self.Renomination.sudo().create({
                "request_id": req.id,
                "from_approver_id": self.approver.id,
                "to_approver_id": self.instead.id,
                "renominated_by_id": self.requester.id,
                "reason": "Typed in",
            })
        self.assertIn("cannot be created directly", str(raised.exception))
        self.assertFalse(self._rows(req))

    def test_another_models_flag_does_not_open_this_one(self):
        req = self._request(self.asset)
        others = {"cadra_custody_append": True,
                  "cadra_movement_append": True,
                  "cadra_event_append": True}
        with self.assertRaises(UserError):
            self.Renomination.sudo().with_context(**others).create({
                "request_id": req.id,
                "from_approver_id": self.approver.id,
                "to_approver_id": self.instead.id,
                "renominated_by_id": self.requester.id,
                "reason": "Typed in",
            })

    def test_the_guard_is_the_mixins_and_not_a_copy(self):
        """The fourth append-only record inherits the mixin; it does not copy
        it (`CLAUDE.md`). Asked off the MRO, as `test_append_only_mixin`
        asks it of the other three."""
        module = ("odoo.addons.myservice_asset_register.models."
                  "asset_change_request_renomination")
        mro = type(self.env[RENOMINATION]).__mro__
        own = [klass for klass in mro if klass.__module__ == module]
        self.assertEqual(len(own), 1)
        for method in _GUARD_METHODS:
            with self.subTest(method=method):
                self.assertNotIn(method, vars(own[0]))
                first = next(klass for klass in mro if method in vars(klass))
                self.assertTrue(
                    first.__module__.endswith(".models.append_only"),
                    "%s resolves to %s" % (method, first.__module__))

    def test_the_request_cannot_be_deleted_from_under_it(self):
        row = self._one_row()
        with self.assertRaises(UserError):
            row.request_id.sudo().unlink()
        self.assertTrue(row.exists())
