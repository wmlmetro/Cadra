"""Nobody moves an asset alone — the model's half of it. Handoff 35.

WHAT THIS FILE IS FOR, AND WHY IT IS NOT THE HTTP SUITE
-------------------------------------------------------
`tests/` exercises `POST /assets/<id>/move`, `POST
/assets/<id>/transfer-custody` and the four `/approvals` routes over HTTP.
Those tests prove the DOOR. They cannot see the rule, because the rule is not
at the door: handoff 35 §A enumerated twelve production writers of
`location_id` and thirteen of `custodian_id`, and the gate is on
`nrs.asset._write_recorded`, underneath all of them. Everything asserted here
goes through the ORM for that reason — a plain `write()`, a `sudo()`, a
context flag, a raw index violation — which is where a route-level test would
find nothing at all.

The properties, in the order they appear:

    1. **The switch** — absent, blank, misspelt and `off`, and that it is
       read from the ROW rather than through `get_param`'s ormcache.
    2. **The gate** under a plain write, and what legitimately passes it.
    3. **Nothing is written on request.** The worst thing this handoff could
       have done is write an append-only record for a move that had not
       happened, so it is asserted directly.
    4. **Self-approval**, refused under `sudo()` and as the superuser.
    5. **One pending request per asset**, which is a partial unique index and
       therefore a raw `psycopg2` violation rather than a `UserError`.
    6. **A request cannot be edited or deleted**, decided or not.
    7. **Approval applies the change**, and what it leaves behind: the
       movement or custody row, its `approval` label, the real approver, and
       the transfer document where there is one to make.
    8. **The premise** — approving into a world that has changed.
    9. **The clearance cannot be forged**, which is the whole reason
       `APPROVAL_KEY` carries an id rather than `True`.
    10. **Rejection needs a reason; withdrawal is the requester's.**

THE SWITCH IS ABSENT ON `test19`, AND THAT IS THE POINT
--------------------------------------------------------
Handoff 35 §C asked for the absent case to be proved by making it absent
rather than reasoned about, because handoff 25's ormcache leak was found
exactly that way. So `setUp` DELETES the parameter row: absent is what
`test19` is in anyway, but a test resting on a row nobody has written rests
on something outside itself, and it would start failing the day an
administrator set the switch — which is exactly the day it must not. Every
test below that does not say otherwise therefore runs under *approval
required*, which is why the fixtures that are NOT about approval declare
`cadra_approval_exempt="test"`, per call, the way the five sibling files in
this directory now do.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init --workers=0
"""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.approval_policy import (
    APPROVAL_KEY,
    EXEMPT_KEY,
    EXEMPT_REASONS,
    OFF,
    ON,
    PARAM,
    REQUIRED_WHEN_UNSET,
    approval_required,
    approval_setting,
)

MODEL = "nrs.asset.change.request"
MANAGER_GROUP = "myservice_asset_register.group_asset_manager"

#: The declaration every fixture write that is not itself under test makes.
#: Spelt at each site rather than hidden in a helper, for the reason
#: `EXEMPT_REASONS` gives: a bypass nobody can see in a grep becomes the way
#: everything is written.
AS_A_FIXTURE = {EXEMPT_KEY: "test"}


class ChangeRequestCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.CR = self.env[MODEL]
        self.Movement = self.env["nrs.asset.movement"]
        self.Custody = self.env["nrs.asset.custody"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Approval test category"})
        Location = self.env["generic.location"]
        self.room = Location.create({"name": "Approval test room"})
        self.elsewhere = Location.create({"name": "Approval test elsewhere"})
        self.third = Location.create({"name": "Approval test third place"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Approval Alice"})
        self.bob = Employee.create({"name": "Approval Bob"})
        self.carol = Employee.create({"name": "Approval Carol"})
        self.requester = self._user("approval-test-requester", manager=True)
        self.approver = self._user("approval-test-approver", manager=True)
        self.bystander = self._user("approval-test-bystander", manager=False)
        # §C, applied to the whole file: the baseline is ABSENT, made absent
        # here rather than assumed of the tenant. It is what `test19` is in
        # anyway, but a test that depends on a row nobody has written is a
        # test that passes for a reason outside itself — and it would start
        # failing the day an administrator set the switch, which is exactly
        # the day it must not. Every assertion below that does not say
        # otherwise therefore runs under *approval required*.
        self._set_switch(None)

    # ── fixtures ─────────────────────────────────────────────────────

    def _user(self, login, manager=True, hr=True):
        """A user of this register.

        `hr` grants `hr.group_hr_user`, and it is here for a reason that has
        NOTHING to do with approvals: `nrs.asset.custody._record` reads the
        employee's `name` in the ACTING user's environment, before its own
        `sudo()`, and `hr.employee._check_private_fields` refuses an
        employee row to anybody outside the HR groups. So an Asset Manager
        approving a CUSTODY change from the Odoo button gets an `AccessError`
        about `sap_user_id` and `ir_number` — fields nothing here asked for.
        See `TestDefectsFoundWhileWritingThisFile` at the foot of the file;
        the flag exists so every other test in between is about approvals
        rather than about that.
        """
        Users = self.env["res.users"]
        # Odoo 19 renamed `res.users.groups_id` to `group_ids`. Resolved
        # rather than written as a literal, exactly as `test_asset_event.py`
        # and four other places in this repository do.
        field = "group_ids" if "group_ids" in Users._fields else "groups_id"
        groups = [self.env.ref("base.group_user").id]
        if manager:
            groups.append(self.env.ref(MANAGER_GROUP).id)
        if hr:
            hr_group = self.env.ref("hr.group_hr_user",
                                    raise_if_not_found=False)
            if hr_group:
                groups.append(hr_group.id)
        return Users.create({
            "name": login,
            "login": login,
            # `message_post` refuses an author with no address, and both the
            # activity and the decision notification post one.
            "email": "%s@example.com" % login,
            field: [(6, 0, groups)],
        })

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Approval test asset", "category_id": self.category.id},
            **vals))

    def _request(self, asset, change_type="location", user=None, **vals):
        """A pending request, raised BY `user` (default: the requester).

        Always `with_user`, never the superuser: `create` stamps
        `requested_by_id` from `self.env.uid`, and a request raised by uid 1
        would make every self-approval assertion below vacuous.
        """
        values = {
            "asset_id": asset.id,
            "change_type": change_type,
            "approver_id": (vals.pop("approver", None) or self.approver).id,
        }
        if change_type == "location":
            values.setdefault("to_location_id", self.elsewhere.id)
        else:
            values.setdefault("to_custodian_id", self.bob.id)
        values.update(vals)
        return self.CR.with_user(user or self.requester).create(values)

    # ── the switch, written the way an administrator writes it ───────

    def _set_switch(self, value):
        """Set or clear the parameter ROW, deliberately not via `set_param`.

        `set_param` clears the ormcache on its way through, which is the one
        thing that must NOT happen in a test whose subject is what the module
        reads when the row changes underneath a cache. Raw SQL is also what
        an administrator running the printed command ends up doing, and it
        rolls back with the test transaction.
        """
        self.env.cr.execute(
            "DELETE FROM ir_config_parameter WHERE key = %s", (PARAM,))
        if value is not None:
            self.env.cr.execute(
                "INSERT INTO ir_config_parameter (key, value) "
                "VALUES (%s, %s)", (PARAM, value))

    def _moves(self, asset):
        return self.Movement.search([("asset_id", "=", asset.id)], order="id")

    def _links(self, asset):
        return self.Custody.search([("asset_id", "=", asset.id)], order="id")


# ═════════════════════════════════════════════════════════════════════
# 1 · The switch
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheSwitch(ChangeRequestCase):
    """Absent means on, and the value is read from the row every time.

    Handoff 35 §C: *prove it by making it absent.* Both halves matter — the
    DIRECTION (a value that is neither on nor off asks for a second person)
    and the READING (a control served from a per-worker cache is a control
    that can stop applying with no symptom, which is what handoff 25 watched
    happen to `database_class`).
    """

    def test_absent_means_required(self):
        self._set_switch(None)
        self.assertIsNone(approval_setting(self.env))
        self.assertTrue(approval_required(self.env))
        self.assertTrue(REQUIRED_WHEN_UNSET)

    def test_off_means_not_required(self):
        self._set_switch(OFF)
        self.assertEqual(approval_setting(self.env), OFF)
        self.assertFalse(approval_required(self.env))

    def test_on_means_required(self):
        self._set_switch(ON)
        self.assertEqual(approval_setting(self.env), ON)
        self.assertTrue(approval_required(self.env))

    def test_a_value_that_is_neither_is_required(self):
        """A typo must not open a door that a blank cannot. `off` is the only
        way to be off, and every near miss at it is on."""
        for value in ("maybe", "", "   ", "of", "no", "false", "0",
                      "disabled", "off;", "OFF ON"):
            with self.subTest(value=value):
                self._set_switch(value)
                self.assertIsNone(
                    approval_setting(self.env),
                    "%r was recognised as a setting" % value)
                self.assertTrue(approval_required(self.env),
                                "%r switched the rule off" % value)

    def test_case_and_surrounding_space_are_forgiven(self):
        """`"ON "` and `"Off"` are somebody typing, not somebody missing.
        Forgiving them is safe in a way that guessing at `"no"` is not,
        because they are the same WORD."""
        for value, expected in ((" ON ", ON), ("On", ON), ("OFF", OFF),
                                (" off\n", OFF)):
            with self.subTest(value=value):
                self._set_switch(value)
                self.assertEqual(approval_setting(self.env), expected)
        self._set_switch(" off ")
        self.assertFalse(approval_required(self.env))

    def test_the_row_is_read_and_not_get_param(self):
        """Deterministic, rather than a race against a cache.

        If `approval_required` went through `ir.config_parameter.get_param`
        — which is `@ormcache`d per worker — this raises. Handoff 25's leak
        cannot be reproduced on demand in one process, so the property is
        asserted at its cause instead of at its symptom.
        """
        Param = type(self.env["ir.config_parameter"])
        with patch.object(Param, "get_param",
                          side_effect=AssertionError(
                              "the approval switch was read through the "
                              "ormcache")):
            self.assertTrue(approval_required(self.env))

    def test_a_row_deleted_under_a_warm_cache_is_seen_at_once(self):
        """The handoff-25 shape, end to end.

        `set_param` populates the ormcache with `off`; the row is then
        removed the way a `DELETE` removes it, with nothing told to
        invalidate anything. A reader going through the cache would still
        say `off` — no second person needed — for as long as that worker
        lived. This one says *required*, immediately.
        """
        self.env["ir.config_parameter"].sudo().set_param(PARAM, OFF)
        self.assertFalse(approval_required(self.env))
        self.env.cr.execute(
            "DELETE FROM ir_config_parameter WHERE key = %s", (PARAM,))
        self.assertTrue(approval_required(self.env),
                        "a deleted switch went on answering `off`")

    def test_the_setting_tells_absent_from_deliberately_off(self):
        """Two facts a screen needs to tell apart and `required` alone
        cannot: *nobody has ever set this* and *somebody turned it off.*"""
        self._set_switch(None)
        self.assertIsNone(approval_setting(self.env))
        self._set_switch(OFF)
        self.assertEqual(approval_setting(self.env), OFF)
        self.assertFalse(approval_required(self.env))
        # Same behaviour from the register's point of view, different fact.
        self._set_switch("nonsense")
        self.assertIsNone(approval_setting(self.env))
        self.assertTrue(approval_required(self.env))

    def test_the_model_says_the_same_thing_as_the_module(self):
        """`approval_is_required()` is what the API and the app read. One
        statement of the rule, or there are two rules."""
        for value in (None, OFF, ON, "maybe"):
            with self.subTest(value=value):
                self._set_switch(value)
                self.assertEqual(self.CR.approval_is_required(),
                                 approval_required(self.env))

    def test_the_refusal_prints_the_command_that_turns_it_off(self):
        command = self.CR.set_switch_command()
        self.assertIn(PARAM, command)
        self.assertIn(self.env.cr.dbname, command)
        self.assertIn("set_param", command)


# ═════════════════════════════════════════════════════════════════════
# 2 · The gate, under every writer
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheGate(ChangeRequestCase):
    """A plain `write()` — no route, no button, no context.

    This is the door a route-level test cannot see, and the one report 28
    found six of when handoff 14 had named one.
    """

    def test_a_plain_write_of_location_is_refused(self):
        asset = self._asset(location_id=self.room.id)
        with self.assertRaises(UserError) as raised:
            asset.write({"location_id": self.elsewhere.id})
        self.assertIn("approve", str(raised.exception))
        self.assertEqual(asset.location_id, self.room, "nothing was written")

    def test_a_plain_write_of_custodian_is_refused(self):
        asset = self._asset(custodian_id=self.alice.id)
        with self.assertRaises(UserError):
            asset.write({"custodian_id": self.bob.id})
        self.assertEqual(asset.custodian_id, self.alice)

    def test_sudo_does_not_get_round_it(self):
        asset = self._asset(location_id=self.room.id)
        with self.assertRaises(UserError):
            asset.sudo().write({"location_id": self.elsewhere.id})

    def test_the_refusal_names_the_asset_the_destination_and_the_remedy(self):
        asset = self._asset(location_id=self.room.id)
        with self.assertRaises(UserError) as raised:
            asset.write({"location_id": self.elsewhere.id})
        message = str(raised.exception)
        self.assertIn(asset.display_name, message)
        self.assertIn("Approval test elsewhere", message)
        self.assertIn("/move", message)
        self.assertIn(PARAM, message,
                      "an error naming a remedy the reader has to look up is "
                      "worse than one naming none")

    def test_naming_the_location_without_changing_it_is_allowed(self):
        """The app's edit form re-sends every field on every save. Refusing
        the mere PRESENCE of the key would make saving a note impossible —
        the trap `CLAUDE.md` names."""
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        asset.write({"location_id": self.room.id,
                     "custodian_id": self.alice.id,
                     "name": "Renamed, not moved"})
        self.assertEqual(asset.name, "Renamed, not moved")
        self.assertEqual(len(self._moves(asset)), 1, "no move was recorded")
        self.assertEqual(len(self._links(asset)), 1)

    def test_an_empty_field_named_as_empty_is_not_a_change(self):
        asset = self._asset()
        asset.write({"location_id": False, "custodian_id": False,
                     "name": "Still nowhere"})
        self.assertEqual(asset.name, "Still nowhere")

    def test_a_write_naming_neither_field_is_not_gated(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"state": "in_repair", "condition": "fair"})
        self.assertEqual(asset.state, "in_repair")

    def test_clearing_a_location_is_not_gated(self):
        """**Ruled, and the two directions are not symmetrical.**

        Taking an asset off a location hands it to nobody — the same argument
        the `clearance` exemption makes in words. The alternative was a dead
        end rather than a control: the refusal named `POST …/move`, and that
        route requires `to_location_id`, so clearing a location became
        impossible through the API having worked for the register's whole
        life. A refusal naming a remedy that cannot work is worse than one
        naming none.
        """
        asset = self._asset(location_id=self.room.id)
        asset.write({"location_id": False})
        self.assertFalse(asset.location_id)
        self.assertEqual(self._moves(asset)[-1].from_location_id, self.room,
                         "not gated, but still RECORDED")

    def test_clearing_a_custodian_is_not_gated(self):
        asset = self._asset(custodian_id=self.alice.id)
        asset.write({"custodian_id": False})
        self.assertFalse(asset.custodian_id)
        self.assertEqual(self._links(asset)[-1].from_custodian_id, self.alice)

    def test_placing_an_asset_that_is_nowhere_is_gated(self):
        """The OTHER direction, and why clearing buys a caller nothing.

        Going from nowhere to somewhere is a grant and is gated, so dropping
        an asset and then placing it is two writes that get you exactly what
        one would: the second one is refused. A first placement at CREATE is
        a different thing again — see the class below."""
        asset = self._asset()
        with self.assertRaises(UserError):
            asset.write({"location_id": self.room.id})

    def test_handing_an_unheld_asset_to_somebody_is_gated(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            asset.write({"custodian_id": self.alice.id})

    def test_dropping_and_regranting_is_not_a_way_round(self):
        """Both halves in one test, because the two rules only make sense
        together and a reader landing on either alone would misread it."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.write({"custodian_id": False})
        self.assertFalse(asset.custodian_id)
        with self.assertRaises(UserError):
            asset.write({"custodian_id": self.bob.id})
        self.assertFalse(asset.custodian_id)

    def test_a_multi_record_write_is_refused_whole(self):
        """`_assert_change_is_approved` runs before `super().write()`, so one
        unapproved record in the set takes the whole write with it — and the
        asset that WOULD have been allowed is not left half-moved."""
        stays = self._asset(location_id=self.elsewhere.id)
        moves = self._asset(location_id=self.room.id)
        with self.assertRaises(UserError):
            (stays | moves).write({"location_id": self.elsewhere.id})
        self.assertEqual(moves.location_id, self.room)

    def test_the_gate_is_silent_when_the_switch_is_off(self):
        self._set_switch(OFF)
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        asset.write({"location_id": self.elsewhere.id,
                     "custodian_id": self.bob.id})
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertEqual(asset.custodian_id, self.bob)


@tagged("post_install", "-at_install")
class TestWhatIsOutsideTheRule(ChangeRequestCase):
    """`create`, and the five declared exemptions. §A's table, as tests."""

    def test_create_is_never_gated(self):
        """A registration is not a move. This is the door INT-03 from Vendra
        comes through, and gating it would dead-letter every receipt."""
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(asset.custodian_id, self.alice)

    def test_create_still_opens_the_two_append_only_records(self):
        """The gate did not cost the birth records that handoff 28 built."""
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        self.assertEqual(len(self._moves(asset)), 1)
        self.assertEqual(self._moves(asset).to_location_id, self.room)
        self.assertEqual(len(self._links(asset)), 1)
        self.assertEqual(self._links(asset).to_custodian_id, self.alice)

    def test_a_declared_exemption_passes(self):
        asset = self._asset(location_id=self.room.id)
        asset.with_context(**{EXEMPT_KEY: "seed"}).write(
            {"location_id": self.elsewhere.id})
        self.assertEqual(asset.location_id, self.elsewhere)

    def test_every_published_reason_passes(self):
        """Read off `EXEMPT_REASONS` rather than listed here, so a reason
        added on the day it is added is exercised on the day it is added."""
        for reason in EXEMPT_REASONS:
            with self.subTest(reason=reason):
                asset = self._asset(location_id=self.room.id)
                asset.with_context(**{EXEMPT_KEY: reason}).write(
                    {"location_id": self.elsewhere.id})
                self.assertEqual(asset.location_id, self.elsewhere)

    def test_an_unrecognised_exemption_is_no_exemption_at_all(self):
        """`approval_policy`'s rule applied to the other end: a typo must not
        open a door that a blank cannot. `True` is on the list because a bare
        boolean is what a caller reaches for, and it must not work."""
        for claimed in ("seeding", "Seed", "SEED", "tests", "", True, 1,
                        "import ", "because I said so"):
            with self.subTest(claimed=claimed):
                asset = self._asset(location_id=self.room.id)
                with self.assertRaises(UserError):
                    asset.with_context(**{EXEMPT_KEY: claimed}).write(
                        {"location_id": self.elsewhere.id})
                self.assertEqual(asset.location_id, self.room)

    def test_the_exemption_is_spelt_the_same_everywhere(self):
        """The three seed scripts, the importer, the clearance routine and
        `nrs.asset.transfer.action_complete` all write this key. If the
        constant moved, they would go on writing the old string and be
        refused in production with nothing failing here."""
        self.assertEqual(EXEMPT_KEY, "cadra_approval_exempt")
        for reason in ("import", "seed", "clearance", "migration",
                       "transfer", "test"):
            self.assertIn(reason, EXEMPT_REASONS)

    def test_an_approved_transfer_completes(self):
        """`action_complete` declares `transfer` — but only when the document
        carries an approver, which is the transfer's OWN second person:
        `draft → approved → done`, with an Approve button restricted to
        `group_asset_manager` that stamps `approved_by`. A document that has
        been through that has had its second person, and asking for another
        would be asking twice for the same decision."""
        asset = self._asset(location_id=self.room.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
            "reason": "office move",
        })
        transfer.action_approve()
        self.assertTrue(transfer.approved_by)
        transfer.action_complete()
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertEqual(self._moves(asset)[-1].source, "transfer")

    def test_an_unapproved_transfer_does_not_complete(self):
        """**The hole the condition closes, proved to fail first.**

        `action_complete` has no state precondition in the model — the button
        is only shown on an `approved` transfer, but the method can be called
        on a `draft` one from a shell or a server action. Exempting the
        SOURCE wholesale would therefore have made *create a transfer and
        complete it* the way round the whole feature. If the `if
        r.approved_by` condition is ever removed, this test is what says so.
        """
        asset = self._asset(location_id=self.room.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
        })
        self.assertEqual(transfer.state, "draft")
        self.assertFalse(transfer.approved_by)
        with self.assertRaises(UserError):
            transfer.action_complete()
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(transfer.state, "draft", "and the document with it")


# ═════════════════════════════════════════════════════════════════════
# 3 · Nothing is written on request
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestNothingIsWrittenOnRequest(ChangeRequestCase):
    """§B's first non-negotiable, asserted rather than assumed.

    *A movement row or a custody link written when somebody ASKS would be a
    permanent record of a move that had not happened and might never happen.
    That is the worst thing this handoff could do* — and the two models it
    would corrupt are the two the programme spent handoffs 14 and 28
    building, both of which refuse correction by design.
    """

    def test_raising_a_move_request_moves_nothing(self):
        asset = self._asset(location_id=self.room.id)
        before = len(self._moves(asset))
        req = self._request(asset, "location")
        self.assertEqual(req.state, "pending")
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(len(self._moves(asset)), before)

    def test_raising_a_custody_request_hands_nothing_over(self):
        asset = self._asset(custodian_id=self.alice.id)
        before = len(self._links(asset))
        req = self._request(asset, "custody")
        self.assertEqual(req.state, "pending")
        self.assertEqual(asset.custodian_id, self.alice)
        self.assertEqual(len(self._links(asset)), before)

    def test_raising_a_request_makes_no_transfer_document(self):
        """The transfer is the RESULT of an approval, not the request."""
        asset = self._asset(location_id=self.room.id)
        self._request(asset, "location")
        self.assertFalse(self.env["nrs.asset.transfer"].search(
            [("asset_id", "=", asset.id)]))

    def test_the_request_records_what_the_asset_was_when_asked(self):
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        req = self._request(asset, "location")
        self.assertEqual(req.from_location_id, self.room)
        self.assertEqual(req.from_location_name, self.room.display_name)
        self.assertEqual(req.from_state, asset.state)
        self.assertEqual(req.to_location_name, self.elsewhere.display_name)

    def test_the_premise_is_read_from_the_asset_not_from_the_caller(self):
        """A premise the requester can write is a premise they can choose,
        and the whole use of these columns is to catch what they believed."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location",
                            from_location_id=self.third.id,
                            from_location_name="Somewhere it never was")
        self.assertEqual(req.from_location_id, self.room)
        self.assertEqual(req.from_location_name, self.room.display_name)

    def test_the_requester_is_the_acting_user_not_the_payload(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location",
                            requested_by_id=self.approver.id)
        self.assertEqual(req.requested_by_id, self.requester)
        self.assertEqual(req.requested_by_name, self.requester.display_name)

    def test_the_decided_columns_cannot_be_set_at_creation(self):
        """`create` pops all seven of them. A request that arrives already
        carrying a decider is the forgery this model exists to prevent."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location",
                            approved_by_id=self.approver.id,
                            approved_by_name="Somebody Senior",
                            transfer_reference="TRF/2026/9999")
        self.assertFalse(req.approved_by_id)
        self.assertFalse(req.approved_by_name)
        self.assertFalse(req.decided_at)
        self.assertFalse(req.transfer_reference)
        self.assertFalse(req.movement_id)
        self.assertFalse(req.custody_id)
        self.assertFalse(req.transfer_id)

    def test_a_request_gets_a_reference_of_its_own(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertTrue(req.name)
        self.assertNotEqual(req.name, "New")


# ═════════════════════════════════════════════════════════════════════
# 4 · Self-approval
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestSelfApproval(ChangeRequestCase):
    """Refused in the MODEL, not hidden in the app.

    A hidden button is a door closed on one screen — report 30 found a
    disposed asset could be un-disposed through a route nobody had looked at.
    So this is asked of `action_approve` directly, under `sudo()` and as the
    superuser, which is where a screen-level rule has nothing to say.
    """

    def test_the_requester_cannot_approve_their_own(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError) as raised:
            req.with_user(self.requester).action_approve()
        self.assertIn("second person", str(raised.exception))
        self.assertEqual(req.state, "pending")
        self.assertEqual(asset.location_id, self.room)

    def test_the_refusal_is_not_an_access_right(self):
        """The requester holds `group_asset_manager` and may write this model
        — an ACL would let them through. The refusal is the model's, about
        who the request BELONGS to, and it is asked of `action_approve`
        rather than of a button."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.requester).check_access("write")
        with self.assertRaises(UserError):
            req.with_user(self.requester).action_approve()
        self.assertEqual(req.state, "pending")

    def test_the_superuser_cannot_approve_its_own_request(self):
        """The suite runs as the superuser, so a request raised here belongs
        to uid 1 — and uid 1 approving it is self-approval however omnipotent
        it is elsewhere. `_may_decide` lets a system administrator decide
        anybody ELSE's; this is the line above that one."""
        asset = self._asset(location_id=self.room.id)
        req = self.CR.create({
            "asset_id": asset.id, "change_type": "location",
            "to_location_id": self.elsewhere.id,
            "approver_id": self.approver.id})
        self.assertEqual(req.requested_by_id, self.env.user)
        with self.assertRaises(UserError):
            req.action_approve()
        with self.assertRaises(UserError):
            req.sudo().action_approve()
        self.assertEqual(req.state, "pending")

    def test_nominating_yourself_is_refused_at_request_time(self):
        """A ValidationError, and a different moment from the one above: the
        dialog can say so before anything is raised."""
        asset = self._asset(location_id=self.room.id)
        with self.assertRaises(ValidationError):
            self._request(asset, "location", approver=self.requester)

    def test_the_requester_is_never_in_their_own_approver_list(self):
        candidates = self.CR.eligible_approvers(exclude_user=self.requester)
        self.assertNotIn(self.requester, candidates)
        self.assertIn(self.approver, candidates,
                      "an eligible approver should be offered")

    def test_somebody_who_could_not_have_made_the_change_cannot_approve(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertFalse(req._may_decide(self.bystander))
        with self.assertRaises(UserError) as raised:
            req.with_user(self.bystander).action_approve()
        self.assertIn("could have made the change themselves",
                      str(raised.exception))

    def test_anybody_eligible_may_decide_whoever_was_nominated(self):
        """The nomination is what puts it in a queue. It confers nothing and
        withholds nothing — which is why `approver_id` being caller-supplied
        is safe."""
        other = self._user("approval-test-other-manager", manager=True)
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertTrue(req._may_decide(other))
        req.with_user(other).action_approve()
        self.assertEqual(req.state, "approved")
        self.assertEqual(req.approver_id, self.approver, "the nominee")
        self.assertEqual(req.approved_by_id, other, "who actually clicked")


# ═════════════════════════════════════════════════════════════════════
# 5 · One pending request per asset
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestOnePendingRequestPerAsset(ChangeRequestCase):
    """§D's first question, answered by a PARTIAL unique index.

    `models.Constraint` cannot express it — Odoo 19's replacement for
    `_sql_constraints` builds table constraints and a partial index is not
    one — so it is created in `init()`, and it raises a raw `psycopg2`
    violation that aborts the transaction rather than a `UserError`. Every
    assertion below is therefore inside a savepoint.
    """

    def test_the_index_exists_and_is_partial(self):
        self.env.cr.execute(
            "SELECT indexdef FROM pg_indexes "
            " WHERE indexname = 'nrs_asset_change_request_one_pending_per_asset'")
        row = self.env.cr.fetchone()
        self.assertTrue(row, "the one-pending-per-asset index is not there")
        self.assertIn("UNIQUE", row[0].upper())
        self.assertIn("pending", row[0],
                      "a non-partial index would forbid an asset a SECOND "
                      "request for the rest of its life")

    def test_a_second_pending_request_is_refused_by_the_database(self):
        asset = self._asset(location_id=self.room.id)
        self._request(asset, "location")
        self.env.flush_all()
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), \
                self.env.cr.savepoint():
            self._request(asset, "custody")
            self.env.flush_all()

    def test_a_withdrawn_request_frees_the_asset(self):
        asset = self._asset(location_id=self.room.id)
        first = self._request(asset, "location")
        first.with_user(self.requester).action_withdraw()
        self.env.flush_all()
        second = self._request(asset, "location",
                               to_location_id=self.third.id)
        self.assertEqual(second.state, "pending")
        self.assertEqual(first.state, "withdrawn")

    def test_a_decided_request_does_not_block_the_next_one(self):
        asset = self._asset(location_id=self.room.id)
        first = self._request(asset, "location")
        first.with_user(self.approver).action_approve()
        self.env.flush_all()
        second = self._request(asset, "location",
                               to_location_id=self.third.id)
        self.assertEqual(second.state, "pending")

    def test_another_asset_is_not_blocked(self):
        one = self._asset(location_id=self.room.id)
        two = self._asset(location_id=self.room.id)
        self._request(one, "location")
        self.env.flush_all()
        self.assertEqual(self._request(two, "location").state, "pending")

    def test_pending_for_asset_finds_the_one_in_the_way(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertEqual(self.CR.pending_for_asset(asset), req)

    def test_pending_for_is_what_is_waiting_on_that_person(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertIn(req, self.CR.pending_for(self.approver))
        self.assertNotIn(req, self.CR.pending_for(self.requester))


# ═════════════════════════════════════════════════════════════════════
# 6 · A request cannot be edited, and can never be deleted
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestARequestIsNotEdited(ChangeRequestCase):
    """Not the append-only mixin — a state machine, and the difference is
    deliberate. A request legitimately moves from `pending` to one of three
    terminal states, so it needs a door rather than a wall. What it takes
    from the mixin is the SHAPE: the transitions set a context flag on
    themselves and `write` refuses without it, so the machine is enforced by
    the model and not by who holds which group."""

    def test_a_pending_request_cannot_be_edited(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError) as raised:
            req.write({"to_location_id": self.third.id})
        self.assertIn("approve it, reject it, or withdraw it",
                      str(raised.exception))
        self.assertEqual(req.to_location_id, self.elsewhere)

    def test_a_pending_request_cannot_be_edited_with_sudo(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError):
            req.sudo().write({"reason": "rewritten afterwards"})

    def test_a_decided_request_is_frozen(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        with self.assertRaises(UserError) as raised:
            req.write({"decision_reason": "actually, no"})
        self.assertIn("already been decided", str(raised.exception))

    def test_a_decided_request_is_frozen_under_sudo_too(self):
        """What it recorded is who authorised a change to a government asset
        register. A decision that can be edited afterwards authorises
        nothing."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_reject(
            decision_reason="not this month")
        with self.assertRaises(UserError):
            req.sudo().write({"approved_by_id": self.requester.id})
        self.assertEqual(req.approved_by_id, self.approver)

    def test_a_decided_request_cannot_be_reopened(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_reject(decision_reason="no")
        for action in ("action_approve", "action_reject", "action_withdraw"):
            with self.subTest(action=action):
                with self.assertRaises(UserError) as raised:
                    getattr(req.with_user(self.approver), action)(
                        decision_reason="second thoughts")
                self.assertIn("A decision is taken once",
                              str(raised.exception))

    def test_a_request_can_never_be_deleted(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError) as raised:
            req.unlink()
        self.assertIn("Withdraw", str(raised.exception))

    def test_a_request_cannot_be_deleted_with_sudo(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        with self.assertRaises(UserError):
            req.sudo().unlink()

    def test_the_asset_cannot_be_deleted_under_a_request(self):
        """`restrict`, like the three append-only models and unlike
        `nrs.asset.transfer`, which cascades: a record of who authorised what
        must not be deletable by deleting its subject."""
        asset = self._asset()
        self._request(asset, "custody")
        self.env.flush_all()
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), \
                self.env.cr.savepoint():
            asset.unlink()
            self.env.flush_all()

    def test_the_new_model_does_not_adopt_the_append_only_mixin(self):
        """Asserted here as well as in `test_append_only_mixin.py`, whose
        `_MODELS` registry is the list of the three that DO. A request is not
        a fourth append-only record and must not be counted as one."""
        guard = type(self.env["nrs.asset.append.only.mixin"])
        self.assertFalse(issubclass(type(self.CR), guard))


# ═════════════════════════════════════════════════════════════════════
# 7 · Approval applies the change
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestApprovalAppliesTheChange(ChangeRequestCase):

    def test_a_move_approval_moves_the_asset(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        self.assertEqual(req.state, "approved")
        self.assertEqual(asset.location_id, self.elsewhere)

    def test_the_movement_row_says_it_was_an_approval(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location", reason="Room being repainted")
        req.with_user(self.approver).action_approve()
        move = self._moves(asset)[-1]
        self.assertEqual(move.source, "approval",
                         "a move a second person agreed to must not read as "
                         "an anonymous direct edit")
        self.assertEqual(move.from_location_id, self.room)
        self.assertEqual(move.to_location_id, self.elsewhere)
        self.assertEqual(move.reason, "Room being repainted")
        self.assertEqual(move.moved_by_id, self.approver,
                         "the row names whoever made the change happen")
        self.assertEqual(req.movement_id, move)

    def test_the_custody_link_says_it_was_an_approval(self):
        asset = self._asset(custodian_id=self.alice.id)
        req = self._request(asset, "custody", reason="Alice is on leave")
        req.with_user(self.approver).action_approve()
        link = self._links(asset)[-1]
        self.assertEqual(link.source, "approval")
        self.assertEqual(link.from_custodian_id, self.alice)
        self.assertEqual(link.to_custodian_id, self.bob)
        self.assertEqual(link.reason, "Alice is on leave")
        self.assertEqual(link.changed_by_id, self.approver)
        self.assertEqual(req.custody_id, link)
        self.assertFalse(req.movement_id)

    def test_a_custody_approval_makes_no_transfer_document(self):
        """`nrs.asset.transfer` requires both locations, so a pure custody
        change cannot be recorded in it at all."""
        asset = self._asset(custodian_id=self.alice.id)
        req = self._request(asset, "custody")
        req.with_user(self.approver).action_approve()
        self.assertFalse(req.transfer_id)
        self.assertFalse(self.env["nrs.asset.transfer"].search(
            [("asset_id", "=", asset.id)]))

    def test_a_move_from_somewhere_makes_a_transfer_with_a_real_approver(self):
        """`approved_by` has been null on 264 of the 265 transfer rows on
        this machine, because `/move` created them already `done`. From here
        it is the person who actually clicked."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        transfer = req.transfer_id
        self.assertTrue(transfer, "an asset that HAS a location is "
                                  "transferred, not placed")
        self.assertEqual(transfer.approved_by, self.approver)
        self.assertTrue(transfer.approved_date)
        self.assertEqual(transfer.state, "done")
        self.assertEqual(transfer.from_location_id, self.room)
        self.assertEqual(transfer.to_location_id, self.elsewhere)
        self.assertEqual(req.transfer_reference, transfer.name)
        self.assertEqual(self._moves(asset)[-1].transfer_id, transfer)

    def test_a_move_from_nowhere_makes_no_transfer(self):
        """Both of that model's location columns are required and a
        constraint forbids them being equal, so an asset that is NOWHERE
        cannot be the subject of one. It is PLACED, not transferred — 46% of
        `jaizbankplc`'s register had no location when it was measured."""
        asset = self._asset()
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertFalse(req.transfer_id)
        self.assertFalse(req.transfer_reference)
        self.assertTrue(req.movement_id, "the MOVE is the fact; the transfer "
                                         "is paperwork")

    def test_who_was_asked_and_who_clicked_are_two_different_columns(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        self.assertEqual(req.approver_id, self.approver)
        self.assertEqual(req.approved_by_id, self.approver)
        self.assertEqual(req.approved_by_name, self.approver.display_name)
        self.assertTrue(req.decided_at)
        self.assertNotEqual(self.CR._fields["approver_id"],
                            self.CR._fields["approved_by_id"])

    def test_a_decision_reason_is_recorded(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve(
            decision_reason="Checked with the store — fine.")
        self.assertEqual(req.decision_reason,
                         "Checked with the store — fine.")

    def test_approving_writes_exactly_one_record(self):
        """Not two. The recorder runs underneath `action_approve`'s write
        like it does under every other writer — the approval does not record
        anything itself."""
        asset = self._asset(location_id=self.room.id)
        before = len(self._moves(asset))
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        self.assertEqual(len(self._moves(asset)), before + 1)


# ═════════════════════════════════════════════════════════════════════
# 8 · The premise
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestThePremise(ChangeRequestCase):
    """§D: *a request whose premise no longer holds must not be approvable in
    silence.* An approval means *"yes, move it FROM A to B"*, and the
    difference from *"yes, move it to B"* is everything once somebody else
    has moved it to C."""

    def test_the_asset_moving_underneath_breaks_it(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        asset.with_context(**AS_A_FIXTURE).write(
            {"location_id": self.third.id})
        self.assertFalse(req.premise_holds)
        self.assertIn("Approval test third place", req.premise_broken_reason)
        with self.assertRaises(UserError) as raised:
            req.with_user(self.approver).action_approve()
        self.assertIn("no longer be approved", str(raised.exception))
        self.assertIn("Approval test third place", str(raised.exception))
        self.assertEqual(asset.location_id, self.third, "nothing happened")
        self.assertEqual(req.state, "pending")

    def test_the_custodian_changing_underneath_breaks_it(self):
        asset = self._asset(custodian_id=self.alice.id)
        req = self._request(asset, "custody")
        asset.with_context(**AS_A_FIXTURE).write(
            {"custodian_id": self.carol.id})
        self.assertFalse(req.premise_holds)
        self.assertIn("Approval Carol", req.premise_broken_reason)
        with self.assertRaises(UserError):
            req.with_user(self.approver).action_approve()

    def test_somebody_else_getting_there_first_breaks_it(self):
        """The asset is already where the request asks it to be. Approving
        would write a move with nothing in it — and the reason given is that
        it is no longer WHERE IT WAS, which is the check that runs first."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        asset.with_context(**AS_A_FIXTURE).write(
            {"location_id": self.elsewhere.id})
        self.assertFalse(req.premise_holds)
        self.assertIn("Approval test elsewhere", req.premise_broken_reason)
        with self.assertRaises(UserError):
            req.with_user(self.approver).action_approve()

    def test_a_request_to_move_it_where_it_already_is_is_never_approvable(
            self):
        """`_premise_check`'s *already at* branch, which is reachable only
        from the MODEL: `POST /assets/<id>/move` refuses `to == current` at
        the door, so this is what happens when a request is raised any other
        way. It can be created and it can never be approved — which is a
        request that can only ever be withdrawn."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location", to_location_id=self.room.id)
        self.assertFalse(req.premise_holds)
        self.assertIn("already at", req.premise_broken_reason)
        with self.assertRaises(UserError):
            req.with_user(self.approver).action_approve()

    def test_a_request_to_hand_it_to_whoever_holds_it_is_the_same(self):
        asset = self._asset(custodian_id=self.alice.id)
        req = self._request(asset, "custody", to_custodian_id=self.alice.id)
        self.assertFalse(req.premise_holds)
        self.assertIn("already holds", req.premise_broken_reason)

    def test_a_disposed_asset_breaks_it_before_the_model_does(self):
        """`_assert_disposed_is_terminal` would raise anyway — but AFTER the
        approver had clicked, with the model's words about a write they did
        not know they were making. This says what actually changed."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        asset.write({"state": "disposed"})
        self.assertFalse(req.premise_holds)
        self.assertIn("disposed", req.premise_broken_reason)
        with self.assertRaises(UserError) as raised:
            req.with_user(self.approver).action_approve()
        self.assertIn("disposed", str(raised.exception))

    def test_a_status_change_underneath_breaks_it(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        asset.write({"state": "in_repair"})
        self.assertFalse(req.premise_holds)
        self.assertIn("in_repair", req.premise_broken_reason)

    def test_the_destination_cannot_be_deleted_under_a_request(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location", to_location_id=self.third.id)
        self.assertTrue(req.premise_holds)
        # `to_location_id` is `restrict`, so the request itself protects the
        # destination — which is the answer, and better than the one the
        # handoff imagined. Proved rather than asserted from the field
        # definition: `restrict` on a m2o is easy to write and easy to read
        # past.
        self.env.flush_all()
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), \
                self.env.cr.savepoint():
            self.third.unlink()
            self.env.flush_all()

    def test_an_untouched_request_still_holds(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        self.assertTrue(req.premise_holds)
        self.assertFalse(req.premise_broken_reason)

    def test_a_decided_request_is_not_rejudged(self):
        """Its premise held at the moment it was decided. Re-judging it
        against today's asset would make the history of a closed record
        change under the reader."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_approve()
        asset.with_context(**AS_A_FIXTURE).write(
            {"location_id": self.third.id})
        req.invalidate_recordset()
        self.assertTrue(req.premise_holds)
        self.assertFalse(req.premise_broken_reason)


# ═════════════════════════════════════════════════════════════════════
# 9 · The clearance cannot be forged
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheClearanceCannotBeForged(ChangeRequestCase):
    """`APPROVAL_KEY` carries an id and not `True`, and the id is CHECKED.

    A bare boolean in the context would mean *approval required* could be
    switched off by anybody who had read the source. This is the same forgery
    path `nrs.asset.movement._record` closed for `transfer_id`, in the same
    words: *a transfer belonging to another asset, or one that names a
    different destination, would let somebody borrow an approval for a move
    it never covered.*
    """

    def _forged(self, asset, vals, **context):
        with self.assertRaises(UserError):
            asset.with_context(**context).write(vals)

    def test_an_id_that_is_not_a_request_clears_nothing(self):
        asset = self._asset(location_id=self.room.id)
        self._forged(asset, {"location_id": self.elsewhere.id},
                     **{APPROVAL_KEY: 99999999})

    def test_a_request_for_a_different_asset_clears_nothing(self):
        mine = self._asset(location_id=self.room.id)
        yours = self._asset(location_id=self.room.id)
        borrowed = self._request(yours, "location")
        self._forged(mine, {"location_id": self.elsewhere.id},
                     **{APPROVAL_KEY: borrowed.id})
        self.assertEqual(mine.location_id, self.room)

    def test_a_request_for_a_different_destination_clears_nothing(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")   # asks for `elsewhere`
        self._forged(asset, {"location_id": self.third.id},
                     **{APPROVAL_KEY: req.id})
        self.assertEqual(asset.location_id, self.room)

    def test_a_custody_request_does_not_clear_a_move(self):
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        req = self._request(asset, "custody")
        self._forged(asset, {"location_id": self.elsewhere.id},
                     **{APPROVAL_KEY: req.id})

    def test_a_withdrawn_request_clears_nothing(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.requester).action_withdraw()
        self._forged(asset, {"location_id": self.elsewhere.id},
                     **{APPROVAL_KEY: req.id})

    def test_a_rejected_request_clears_nothing(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.approver).action_reject(decision_reason="no")
        self._forged(asset, {"location_id": self.elsewhere.id},
                     **{APPROVAL_KEY: req.id})

    def test_the_genuine_request_for_this_change_does_clear_it(self):
        """The positive control. Without it every assertion above would pass
        on a gate that refused everything."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        asset.with_context(**{APPROVAL_KEY: req.id}).write(
            {"location_id": self.elsewhere.id})
        self.assertEqual(asset.location_id, self.elsewhere)


# ═════════════════════════════════════════════════════════════════════
# 10 · Rejection and withdrawal
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestRejectionAndWithdrawal(ChangeRequestCase):

    def test_a_rejection_without_a_reason_is_refused(self):
        """A rejection with nothing to act on leaves the requester to simply
        ask again — the shape of control that produces noise and no
        information. `/condemn`, `/mark-missing` and `/mark-found` require
        one for the same argument."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        for empty in (None, "", "   "):
            with self.subTest(reason=empty):
                with self.assertRaises(UserError) as raised:
                    req.with_user(self.approver).action_reject(
                        decision_reason=empty)
                self.assertIn("Say why", str(raised.exception))
        self.assertEqual(req.state, "pending")

    def test_a_rejection_with_a_reason_closes_it_and_moves_nothing(self):
        asset = self._asset(location_id=self.room.id)
        before = len(self._moves(asset))
        req = self._request(asset, "location")
        req.with_user(self.approver).action_reject(
            decision_reason="That room is being repurposed.")
        self.assertEqual(req.state, "rejected")
        self.assertEqual(req.approved_by_id, self.approver)
        self.assertEqual(req.decision_reason,
                         "That room is being repurposed.")
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(len(self._moves(asset)), before)

    def test_the_requester_cannot_reject_their_own(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError):
            req.with_user(self.requester).action_reject(
                decision_reason="changed my mind")

    def test_the_requester_may_withdraw_without_a_reason(self):
        """A requester withdrawing their own request owes nobody one; an
        approver rejecting one does. That is why these are two acts."""
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.requester).action_withdraw()
        self.assertEqual(req.state, "withdrawn")
        self.assertEqual(req.approved_by_id, self.requester,
                         "whoever closed it, which here is the requester")
        self.assertFalse(req.decision_reason)
        self.assertEqual(asset.location_id, self.room)

    def test_nobody_else_may_withdraw_it(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        with self.assertRaises(UserError) as raised:
            req.with_user(self.approver).action_withdraw()
        self.assertIn("Reject it instead", str(raised.exception))
        self.assertEqual(req.state, "pending")

    def test_a_withdrawal_reason_is_kept_when_one_is_given(self):
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        req.with_user(self.requester).action_withdraw(
            decision_reason="Asked the wrong person.")
        self.assertEqual(req.decision_reason, "Asked the wrong person.")


# ═════════════════════════════════════════════════════════════════════
# 11 · Four defects this file found and cannot fix
# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheBypassThatWasFound(ChangeRequestCase):
    """The four defects this file found, now FIXED and held shut.

    Every test here was written the other way round first. Each asserted the
    WRONG behaviour — the thing that actually happened — because each was
    found by writing a test that asserted the right behaviour and watching it
    fail. They were pinned that way so that whoever changed the code next
    would read them, and so that each would FAIL the day its defect was
    fixed.

    They all failed. The defects were fixed in the same handoff, and these
    are their inverses: what the code does now, and what it must keep doing.

    **The one that mattered** is `test_a_pending_request_does_not_clear_the
    _gate`. Together with a forgeable `state`, an Asset Manager could move any
    asset alone in two `call_kw` calls — raise a request properly, then write
    `location_id` directly with `cadra_approval_id` naming their own PENDING
    request. The gate found a request for the right asset and the right
    destination and waved it through. The REST API was never a way in;
    the Odoo web client was, which is the argument of this whole handoff
    turned back on itself.
    """

    def test_a_request_cannot_be_created_already_approved(self):
        """`create` FORCES `state = pending`; it does not default it.

        It used to call `vals.setdefault('state', STATE_PENDING)`, so a
        caller-supplied `state` survived and a request could exist in
        `approved` with no decider, no date and nothing having happened. The
        seven decided COLUMNS were popped even then — see
        `test_the_decided_columns_cannot_be_set_at_creation` — and `state`
        was the eighth thing that needed it.
        """
        asset = self._asset(location_id=self.room.id)
        born = self._request(asset, "location", state="approved")
        self.assertEqual(
            born.state, "pending",
            "a request is born pending whatever the caller asked for")
        self.assertFalse(born.approved_by_id)
        self.assertFalse(born.decided_at)

    def test_a_pending_request_does_not_clear_the_gate(self):
        """**THE BYPASS.** A pending request clears nothing.

        `_approval_clears` used to accept `pending` as well as `approved`,
        because `action_approve` wrote the asset BEFORE stamping its own
        decision, so at the moment of the write the row still said pending.
        That made the request's own id a skeleton key: raise one properly,
        then write the field directly with `cadra_approval_id` set to it.

        The fix was to reverse the order — `action_approve` stamps first, in
        the same transaction, so a refusal in the write rolls the stamp back
        — which let the clearance demand `approved` WITH a decider, the one
        thing only `action_approve` can produce.
        """
        asset = self._asset(location_id=self.room.id)
        pending = self._request(asset, "location")
        self.assertEqual(pending.state, "pending")
        with self.assertRaises(UserError):
            asset.with_context(**{APPROVAL_KEY: pending.id}).write(
                {"location_id": self.elsewhere.id})
        asset.invalidate_recordset()
        self.assertEqual(asset.location_id, self.room,
                         "the asset must not have moved")

    def test_an_approved_request_with_no_decider_does_not_clear_the_gate(self):
        """Belt and braces: the DECIDER is checked, not just the state.

        The state is a Selection that a future migration, a data fix or some
        `_write_recorded` elsewhere could set. `approved_by_id` is the fact
        that matters, and it is written by exactly one method. Checked
        separately so that neither alone is enough.
        """
        asset = self._asset(location_id=self.room.id)
        req = self._request(asset, "location")
        # Straight past the model's own guards, which is the point: even a
        # row doctored in the database does not clear the gate.
        self.env.cr.execute(
            "UPDATE nrs_asset_change_request SET state = 'approved' "
            "WHERE id = %s", (req.id,))
        req.invalidate_recordset()
        self.assertEqual(req.state, "approved")
        self.assertFalse(req.approved_by_id)
        with self.assertRaises(UserError):
            asset.with_context(**{APPROVAL_KEY: req.id}).write(
                {"location_id": self.elsewhere.id})

    def test_a_custody_approval_does_not_need_hr_read_access(self):
        """An Asset Manager who is not an HR user can approve a custody change.

        `nrs.asset.custody._record` used to build `from_custodian.name` and
        `to_custodian.name` in the ACTING user's environment and only then
        call `self.sudo().create(...)`. `hr.employee._check_private_fields`
        refuses the record to anybody outside `hr.group_hr_user`, and reading
        one field prefetches the whole row, so the refusal named `ir_number`,
        `sap_user_id`, `is_test_fixture` and eleven other fields nothing had
        asked for.

        **Pre-existing**, and the same thing happened on the ordinary Odoo
        asset form. The REST API never met it because `_browse_or_404`
        browses `sudo()`. What this handoff added was a second Odoo-side door
        onto it — the Approve button — so the Asset Manager the feature
        exists for could not use it from the backend.
        """
        manager = self._user("approval-test-no-hr", manager=True, hr=False)
        asset = self._asset(custodian_id=self.alice.id)
        req = self._request(asset, "custody", approver=manager)
        req.with_user(manager).action_approve()
        asset.invalidate_recordset()
        self.assertEqual(asset.custodian_id, self.bob)
        self.assertEqual(req.state, "approved")

    def test_a_clearance_id_that_is_not_an_id_is_refused_not_crashed(self):
        """`True` gets a clean refusal, not a `TypeError`.

        `_approval_clears` used to start `if not request_id: return False`,
        which let `True` through to `browse(True)` and a bare
        `TypeError: 'bool' object is not iterable` — an unhandled exception
        where every other bad clearance got a `UserError`. `True` is the
        first value somebody probing this reaches for, precisely because the
        design is that the key carries an id.

        `bool` is a subclass of `int`, so it is refused by name.
        """
        asset = self._asset(location_id=self.room.id)
        for bogus in (True, False, "7", 0, -1, None, [1], 1.5):
            with self.subTest(clearance=bogus):
                with self.assertRaises(UserError):
                    asset.with_context(**{APPROVAL_KEY: bogus}).write(
                        {"location_id": self.elsewhere.id})
        asset.invalidate_recordset()
        self.assertEqual(asset.location_id, self.room)
