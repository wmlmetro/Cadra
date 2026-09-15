"""`is_test_fixture` is derived from the credential, and cannot be talked out of.

Handoff 26 §A. The chain of custody is honest because 330 of its rows DERIVE
`source = 'test'` from `myservice.api.client.is_test_credential` — nobody
curates it, nobody remembers to type it. Everything else leaned on a name
prefix, which is a convention, and `request.request` never had one at all:
its name is a sequence, so the 460 requests on `jaizbankplc` can never be
told from real ones. `cadra.test.fixture.mixin` makes the derivation general.

What is proved here is the three properties that make it a derivation rather
than a convention with extra steps:

  1. a record created under a flagged credential's user carries the label;
  2. a record created under an UNFLAGGED user does NOT — the absent case,
     which is the one report 25's ormcache leak was found by insisting on,
     and the one that is obviously going to pass right up until it doesn't;
  3. the value cannot be set on the way in, or cleared afterwards, by
     anybody — including a superuser with an `odoo shell`.

TransactionCase rather than HttpCase: the derivation reads `self.env.uid`,
and `with_user()` addresses that directly. Going over HTTP would prove the
same thing through three more layers, each of which could be why it passed.
"""
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestFixtureLabelIsDerived(CadraTransactionCase):

    #: One per model family the mixin covers that this case can create
    #: cheaply. Not all fourteen — the mixin is one `create` override, so a
    #: model proves the WIRING, and the wiring is what a new model gets
    #: wrong. `tests/test_source_guards.py` proves the coverage.
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flagged = cls.create_api_client({
            "name": "fixture-label probe (flagged)",
            "scopes": "assets:read",
        })
        # Deliberately NOT via `create_api_client`, which forces the flag on:
        # this one has to lie the way a real integration's credential is
        # honest. Minted through the helper and then turned off on a record
        # we already hold — the pattern `test_custody_is_not_capped.py`
        # established, and the one the source guard is written not to flag.
        cls.unflagged = cls.create_api_client({
            "name": "fixture-label probe (unflagged)",
            "scopes": "assets:read",
        })
        cls.unflagged.write({"is_test_credential": False})

        Category = cls.env["nrs.asset.category"]
        cls.category = Category.search([], limit=1) or Category.create(
            {"name": "fixture-label probe"})

    def _asset_as(self, user, name):
        return self.env["nrs.asset"].with_user(user).sudo().create({
            "name": name,
            "category_id": self.category.id,
        })

    def test_a_record_created_under_a_test_credential_says_so(self):
        asset = self._asset_as(self.flagged.user_id, "probe flagged")
        self.assertTrue(
            asset.is_test_fixture,
            "an asset created under a credential flagged `is_test_credential` "
            "carries no `is_test_fixture` — the derivation is not wired, and "
            "every fixture this suite writes is unidentifiable again")

    def test_a_record_created_under_a_real_credential_does_not(self):
        """The absent case, asserted first-class rather than assumed.

        Report 25's guard leaked because its proof exercised the two
        outcomes that were obviously going to pass and never the third. A
        label that is TRUE for everything is not a label.
        """
        asset = self._asset_as(self.unflagged.user_id, "probe unflagged")
        self.assertFalse(
            asset.is_test_fixture,
            "an asset created under an UNFLAGGED credential is labelled a "
            "test fixture. A label that says yes about every record says "
            "nothing about any of them.")

    def test_the_caller_cannot_declare_itself_real(self):
        """Sending `False` from an unflagged-looking payload changes nothing.

        `create` OVERWRITES rather than defaults, for the reason
        `_resolve_source` records: a field the caller sends would let anybody
        disguise a fixture as register data in the one place whose whole
        value is that its contents were not invented.
        """
        asset = self.env["nrs.asset"].with_user(
            self.flagged.user_id).sudo().create({
                "name": "probe lying payload",
                "category_id": self.category.id,
                "is_test_fixture": False,
            })
        self.assertTrue(
            asset.is_test_fixture,
            "a payload claiming `is_test_fixture: False` was honoured — the "
            "label is declarable, which makes it a convention again")

    def test_the_caller_cannot_slander_a_real_record(self):
        """And the other direction, which is the one nobody tests."""
        asset = self.env["nrs.asset"].with_user(
            self.unflagged.user_id).sudo().create({
                "name": "probe slander payload",
                "category_id": self.category.id,
                "is_test_fixture": True,
            })
        self.assertFalse(
            asset.is_test_fixture,
            "a payload claiming `is_test_fixture: True` was honoured on a "
            "record created by a real credential — anybody can mark a "
            "genuine asset as an artefact")

    def test_the_label_cannot_be_cleared_afterwards(self):
        """Append-only, for the reason the custody chain is.

        Unconditional: there is no superuser branch, because a superuser
        branch is what an `odoo shell` one-liner uses.
        """
        asset = self._asset_as(self.flagged.user_id, "probe clear")
        self.assertTrue(asset.is_test_fixture)
        with self.assertRaises(UserError):
            asset.write({"is_test_fixture": False})
        with self.assertRaises(UserError):
            asset.sudo().write({"is_test_fixture": False})
        asset.invalidate_recordset()
        self.assertTrue(
            asset.is_test_fixture,
            "the label came off despite the refusal")

    def test_writing_the_value_it_already_holds_is_not_an_error(self):
        """A form save round-trips every field; it is not an attempt to lie."""
        asset = self._asset_as(self.flagged.user_id, "probe idempotent write")
        asset.write({"is_test_fixture": True, "name": "probe renamed"})
        self.assertEqual(asset.name, "probe renamed")
        self.assertTrue(asset.is_test_fixture)

    def test_the_label_reaches_a_model_that_is_not_an_asset(self):
        """One non-asset model, because the mixin is what is under test.

        `request.request` specifically: it is the measured hole, and the one
        model whose name can never identify it.
        """
        request_type = self.env["request.type"].search([], limit=1)
        if not request_type:
            self.skipTest("no request.type on this database")
        record = self.env["request.request"].with_user(
            self.flagged.user_id).sudo().create({
                "type_id": request_type.id,
                "request_text": "fixture-label probe",
            })
        self.assertTrue(
            record.is_test_fixture,
            "a service request created under a test credential carries no "
            "label — the 460 unidentifiable requests on jaizbankplc are "
            "still being added to")

    def test_an_archived_credential_still_labels_its_output(self):
        """`active_test=False`, and it is the whole of report 25's §3.

        `Handoff23 Approver` is archived on `jaizbankplc`, and a plain
        `search()` is what made `mark_test_fixtures.py` report a clean run
        while doing nothing. An archived credential's artefacts are still
        artefacts.
        """
        self.flagged.write({"active": False})
        asset = self._asset_as(self.flagged.user_id, "probe archived")
        self.assertTrue(
            asset.is_test_fixture,
            "archiving the credential made its output stop self-labelling — "
            "the lookup is filtering on `active` somewhere")
