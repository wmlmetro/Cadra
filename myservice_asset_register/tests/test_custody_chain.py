"""The chain of custody, and the two guarantees it is worth nothing without.

    1. Every custodian change produces exactly one link, whoever made it.
    2. A link, once written, cannot be changed or removed by anybody.

Neither is enforced by an ACL. An ACL is configuration; these tests exercise
the model, which is code, and they exercise it under `sudo()` as well —
because a record whose whole value is that nobody can alter it has to refuse
the administrator too.

The first guarantee is the one the handoff did not scope. It said the
transfer-custody route was the only writer of `custodian_id`; it is not.
`custodian_id` is in the API's `_WRITABLE_FIELDS`, `nrs.asset.transfer`
writes it on completion, `myservice_identity` clears it on retrieval, and it
is an editable field on the Odoo form. So the recorder lives in
`nrs.asset.write`, where every one of those passes, and the tests below go
through the ORM rather than through the route for exactly that reason.

WHY THE GATED WRITES BELOW SAY `cadra_approval_exempt="test"`
-------------------------------------------------------------
Handoff 35 put a gate under every writer of `location_id` and
`custodian_id`: on a tenant that has not turned the rule off — and absent
means ON, so `test19` has not — a write that CHANGES either field raises
unless a second person approved it. These fixtures are not a person
deciding to move something, so each gated write declares itself with the
reason `approval_policy.EXEMPT_REASONS` reserves for exactly this.

**Per call, never once for the file or the class.** A module-level default
would be the bypass flag `database_class.py` argues against at length: it
becomes the way everything here is written by the end of the month, and
then a test that should have discovered the gate never meets it. Spelling
it at each site also means a grep for the constant finds every test that
is standing outside the rule. Writes that do NOT change the two fields are
left exactly as they were — a fixture that stops needing the declaration
is a fixture whose meaning has changed.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


#: A user who is NOT the one creating the transfer.
#:
#: Handoff 35 made `nrs.asset.transfer.action_complete` exempt from the
#: approval gate only when the document carries an approver, and
#: `action_approve`/`action_complete` refuse a transfer whose approver is its
#: own creator — otherwise the exemption would have been a way for one person
#: to move an asset alone, which is the hole the verification pass found. So a
#: test that wants a COMPLETABLE transfer needs two people, exactly as a real
#: one does. `self.env.uid` creates it; this approves it.
def _a_second_user(env):
    login = "cadra-transfer-approver"
    user = env["res.users"].sudo().search([("login", "=", login)], limit=1)
    if not user:
        user = env["res.users"].sudo().create({
            "name": "Cadra Transfer Approver", "login": login,
            "group_ids": [
                (4, env.ref("base.group_user").id),
                (4, env.ref("myservice_asset_register.group_asset_manager").id),
            ],
        })
    return user


class CustodyCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Custody = self.env["nrs.asset.custody"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Custody test category"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Custody Alice"})
        self.bob = Employee.create({"name": "Custody Bob"})
        self.carol = Employee.create({"name": "Custody Carol"})

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Custody test asset", "category_id": self.category.id},
            **vals))

    def _links(self, asset):
        return self.Custody.search([("asset_id", "=", asset.id)], order="id")


@tagged("post_install", "-at_install")
class TestAppendOnly(CustodyCase):

    def test_write_raises(self):
        asset = self._asset(custodian_id=self.alice.id)
        link = self._links(asset)
        self.assertEqual(len(link), 1)
        with self.assertRaises(UserError):
            link.write({"reason": "rewriting history"})

    def test_write_raises_under_sudo(self):
        """The guard is on the model, not on an access rule.

        `sudo()` bypasses every ACL and record rule in Odoo, so a guard
        expressed as configuration would be exactly as strong as the promise
        that nobody ever calls `sudo()` — and every API route in this
        codebase calls it on every request.
        """
        asset = self._asset(custodian_id=self.alice.id)
        with self.assertRaises(UserError):
            self._links(asset).sudo().write({"reason": "rewriting history"})

    def test_unlink_raises(self):
        asset = self._asset(custodian_id=self.alice.id)
        with self.assertRaises(UserError):
            self._links(asset).unlink()

    def test_unlink_raises_under_sudo(self):
        asset = self._asset(custodian_id=self.alice.id)
        with self.assertRaises(UserError):
            self._links(asset).sudo().unlink()

    def test_the_message_says_it_refuses_sudo(self):
        """An error that does not explain itself sends somebody looking for
        the ACL that is stopping them, and there is not one."""
        asset = self._asset(custodian_id=self.alice.id)
        with self.assertRaises(UserError) as caught:
            self._links(asset).sudo().unlink()
        self.assertIn("sudo", str(caught.exception).lower())

    def test_deleting_the_asset_cannot_erase_the_chain(self):
        """`ondelete='restrict'`. Cascading would let anybody able to delete
        an asset delete its history with it — the same defect this model
        exists to remove, one level up.

        The exception type is deliberately not pinned. The refusal comes
        from a foreign key, and whether that surfaces as psycopg2's
        `IntegrityError` or as an ORM error Odoo wrapped around it is a
        detail of the version we happen to be on. What must hold is that the
        delete is REFUSED — pinning the class would make this test fail on
        an upgrade that changed nothing about the guarantee.
        """
        from odoo.tools import mute_logger
        asset = self._asset(custodian_id=self.alice.id)
        self.env.flush_all()
        with self.assertRaises(Exception), \
                mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            asset.unlink()
            self.env.flush_all()


@tagged("post_install", "-at_install")
class TestEveryChangeIsRecorded(CustodyCase):

    def test_creation_with_a_custodian_opens_the_chain(self):
        """An asset created already assigned is the FIRST link, not a state
        that precedes the chain. The chatter tracking rows this replaces
        record creation the same way, so leaving it out would make the
        backfilled half and the live half disagree."""
        asset = self._asset(custodian_id=self.alice.id)
        links = self._links(asset)
        self.assertEqual(len(links), 1)
        self.assertFalse(links.from_custodian_id)
        self.assertEqual(links.to_custodian_id, self.alice)

    def test_creation_without_a_custodian_opens_nothing(self):
        self.assertEqual(len(self._links(self._asset())), 0)

    def test_one_change_is_exactly_one_link(self):
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(cadra_approval_exempt="test").write(
            {"custodian_id": self.bob.id})
        links = self._links(asset)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[-1].from_custodian_id, self.alice)
        self.assertEqual(links[-1].to_custodian_id, self.bob)

    def test_the_link_names_the_acting_user_not_the_custodian(self):
        """"Who moved it" is a different question from "who had it", and the
        two custodian columns cannot answer the first."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(cadra_approval_exempt="test").write(
            {"custodian_id": self.bob.id})
        link = self._links(asset)[-1]
        self.assertEqual(link.changed_by_id, self.env.user)
        self.assertEqual(link.changed_by_name, self.env.user.name)

    def test_a_write_that_does_not_move_custody_records_nothing(self):
        asset = self._asset(custodian_id=self.alice.id)
        asset.write({"name": "Renamed, not moved"})
        self.assertEqual(len(self._links(asset)), 1)

    def test_rewriting_the_same_custodian_records_nothing(self):
        """Saving a form is not a custody event. A link per save would fill
        the chain with movements that never happened."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.write({"custodian_id": self.alice.id})
        self.assertEqual(len(self._links(asset)), 1)

    def test_clearing_the_custodian_is_a_custody_event(self):
        """`myservice_identity.action_mark_retrieved` does exactly this when
        an employee leaves. An asset going from held to unheld is the single
        most audit-relevant movement there is."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(cadra_approval_exempt="test").write(
            {"custodian_id": False})
        link = self._links(asset)[-1]
        self.assertEqual(link.from_custodian_id, self.alice)
        self.assertFalse(link.to_custodian_id)

    def test_a_multi_record_write_records_each_asset_separately(self):
        """One `write()` over a recordset is N custody events, not one."""
        first = self._asset(custodian_id=self.alice.id)
        second = self._asset(custodian_id=self.bob.id)
        (first | second).with_context(cadra_approval_exempt="test").write(
            {"custodian_id": self.carol.id})
        self.assertEqual(self._links(first)[-1].from_custodian_id, self.alice)
        self.assertEqual(self._links(second)[-1].from_custodian_id, self.bob)
        self.assertEqual(len(self._links(first)), 2)
        self.assertEqual(len(self._links(second)), 2)

    def test_the_names_survive_the_employee_being_deleted(self):
        """Delete the employee and read the link again.

        `ondelete='set null'` empties `to_custodian_id`. Without the name
        snapshot an append-only row could therefore still be emptied of its
        content from OUTSIDE the model — the guarantee would hold on the row
        and fail on the join, which is the same thing to an auditor.
        """
        asset = self._asset(custodian_id=self.alice.id)
        link = self._links(asset)
        self.assertEqual(link.to_custodian_id, self.alice)
        self.assertEqual(link.to_custodian_name, "Custody Alice")

        self.alice.unlink()
        self.env.flush_all()
        link.invalidate_recordset()
        self.assertFalse(link.to_custodian_id,
                         "the link to a deleted employee should go null")
        self.assertEqual(link.to_custodian_name, "Custody Alice",
                         "the NAME must survive the employee record")


@tagged("post_install", "-at_install")
class TestTheSourceIsTruthful(CustodyCase):

    def test_an_undeclared_write_is_direct(self):
        asset = self._asset(custodian_id=self.alice.id)
        self.assertEqual(self._links(asset).source, "direct")

    def test_a_declared_source_is_carried(self):
        asset = self._asset()
        asset.with_context(
            cadra_custody_source="api_transfer",
            cadra_custody_reason="Previous custodian left",
            cadra_approval_exempt="test",
        ).write({"custodian_id": self.alice.id})
        link = self._links(asset)[-1]
        self.assertEqual(link.source, "api_transfer")
        self.assertEqual(link.reason, "Previous custodian left")

    def test_a_caller_cannot_file_a_custody_change_under_test(self):
        """The context is caller-controlled over `call_kw`. `test` says the
        link is an ARTEFACT, and until handoff 30 anybody able to change a
        custodian could claim it and file a real change of custody as one.
        Movement closed this when it was written; this model, which it was
        copied from, did not — two copies of one rule, disagreeing for a
        month. `test` is derived from the credential, never claimed."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(cadra_custody_source="test",
                           cadra_approval_exempt="test").write(
            {"custodian_id": self.bob.id})
        link = self._links(asset)[-1]
        self.assertEqual(link.to_custodian_id, self.bob)
        self.assertEqual(link.source, "direct")

    def test_a_caller_cannot_file_a_custody_change_as_a_reconstruction(self):
        """`tracking_backfill` says the link was rebuilt from the message
        log after the fact. Claimed on a live change it would mark a
        contemporaneous record as a reconstruction — and `myservice_api`
        exempts that label from the test-credential relabel, so it would
        also have been a way to keep `test` OFF a fixture."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(cadra_custody_source="tracking_backfill",
                           cadra_approval_exempt="test").write(
            {"custodian_id": self.bob.id})
        self.assertEqual(self._links(asset)[-1].source, "direct")

    def test_a_source_nobody_defined_is_direct(self):
        asset = self._asset()
        asset.with_context(cadra_custody_source="the_board_said_so",
                           cadra_approval_exempt="test").write(
            {"custodian_id": self.alice.id})
        self.assertEqual(self._links(asset)[-1].source, "direct")

    def test_first_party_code_can_still_pass_a_reconstruction_explicitly(self):
        """Closing the context must not have closed the one honest door: a
        backfill passes the label to `_record` as an argument, which an RPC
        caller cannot reach — `_record` is private to `call_kw`."""
        asset = self._asset()
        link = self.Custody._record(
            asset, self.env["hr.employee"], self.alice,
            source="tracking_backfill")
        self.assertEqual(link.source, "tracking_backfill")

    def test_a_completed_transfer_is_labelled_transfer(self):
        Location = self.env["generic.location"]
        origin = Location.create({"name": "Custody test origin"})
        destination = Location.create({"name": "Custody test destination"})
        asset = self._asset(custodian_id=self.alice.id,
                            location_id=origin.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": origin.id,
            "to_location_id": destination.id,
            "from_custodian_id": self.alice.id,
            "to_custodian_id": self.bob.id,
            "reason": "Office move",
            # An APPROVED transfer, because since handoff 35
            # `action_complete` declares `cadra_approval_exempt='transfer'`
            # only when `approved_by` is set — an unapproved one meets the
            # gate like any other write. Given an approver rather than a
            # test exemption, so this exercises the production path.
            "approved_by": _a_second_user(self.env).id,
        })
        transfer.action_complete()
        link = self._links(asset)[-1]
        self.assertEqual(link.source, "transfer")
        self.assertEqual(link.to_custodian_id, self.bob)
        self.assertEqual(link.reason, "Office move")


@tagged("post_install", "-at_install")
class TestLinksCannotBeHandWritten(CustodyCase):
    """`create` is guarded on the model too, not only by `ir.model.access`.

    An ACL is configuration. One `1,1,1,1` line in the CSV and an internal
    user could `call_kw` a backdated link naming an arbitrary actor into a
    record that then cannot be corrected, because this model refuses
    correction by design.
    """

    def test_a_hand_written_link_is_refused(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Custody.create({
                "asset_id": asset.id,
                "to_custodian_id": self.alice.id,
                "source": "api_transfer",
                "changed_at": "2020-01-01 00:00:00",
            })

    def test_a_hand_written_link_is_refused_under_sudo(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Custody.sudo().create({
                "asset_id": asset.id,
                "to_custodian_id": self.alice.id,
                "source": "tracking_backfill",
            })

    def test_a_real_custodian_change_still_writes_one(self):
        """The guard must not have closed the only door that should be open."""
        asset = self._asset(custodian_id=self.alice.id)
        self.assertEqual(len(self._links(asset)), 1)
