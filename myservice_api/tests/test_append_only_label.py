"""One relabel, three records. Handoff 31 §A.

A row written under a TEST credential says `source = 'test'`, on the chain
of custody, the movement record and the event record alike. The suite
exercises the recorders against real assets, the records are append-only, so
those rows are permanent in whichever tenant it ran against — and what makes
that acceptable is that a reader can tell them from history without being
told the suite exists.

Until handoff 31 that was THREE overrides in this module, one per model,
"supposed to be the same rule and not the same code": custody's went through
a forwarder and spared `tracking_backfill` with one spelling of the test,
movement's inlined the lookup and spared it with another, and the event
record's spared nothing. Each was correct. It is one now, on
`nrs.asset.append.only.mixin` (`models/append_only.py`), and what is
asserted here is what three per-model tests could not: that the ONE reaches
all three, by acting, in a single write.

It reaches them only because each model inherits the mixin in a module BELOW
this one — a fact about how the registry was assembled, which is why it is
checked by writing rows rather than by reading classes.
`tests/test_source_guards.py` holds the same chain with no server.

Run with:
    odoo -d <db> -u myservice_api --test-enable \\
         --test-tags /myservice_api --stop-after-init
"""
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

_MODELS = ("nrs.asset.custody", "nrs.asset.movement", "nrs.asset.event")

# What a route declares on the three context keys before it writes.
_DECLARED = {
    "cadra_custody_source": "api_write",
    "cadra_movement_source": "api_write",
    "cadra_event_source": "api_write",
}


@tagged("post_install", "-at_install")
class TestOneRelabelReachesAllThree(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Label test category"})
        Location = self.env["generic.location"]
        self.room = Location.create({"name": "Label test room"})
        self.elsewhere = Location.create({"name": "Label test elsewhere"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Label Alice"})
        self.bob = Employee.create({"name": "Label Bob"})
        # Minted as `test_asset_history.py` mints its own: the shared base
        # class flags every credential a test creates `is_test_credential`,
        # and an API client acts as its own `res.users` (handoff 08).
        self.credential = self.create_api_client({
            "name": "label probe test credential",
            "client_id": "labelprobe_%s" % uuid.uuid4().hex[:8],
            "scopes": "assets:read assets:write",
        })
        self.assertTrue(self.credential.is_test_credential)
        self.assertTrue(self.credential.user_id)

    def _asset(self):
        return self.env["nrs.asset"].create({
            "name": "Label test asset", "category_id": self.category.id,
            "custodian_id": self.alice.id, "location_id": self.room.id})

    def _last(self, model, asset):
        return self.env[model].search(
            [("asset_id", "=", asset.id)], order="id")[-1]

    def _one_write_that_causes_all_three(self, asset):
        """Custody moves, the asset moves, and its status changes — one
        `write`, with the source a route would declare on every key."""
        asset.with_context(**_DECLARED).write({
            "custodian_id": self.bob.id,
            "location_id": self.elsewhere.id,
            "state": "missing"})

    def test_a_write_under_a_test_credential_says_test_on_all_three(self):
        asset = self._asset()
        # What a route does: the credential's own user, with sudo.
        self._one_write_that_causes_all_three(
            asset.with_user(self.credential.user_id).sudo())
        for model in _MODELS:
            with self.subTest(model=model):
                self.assertEqual(
                    self._last(model, asset).source, "test",
                    "%s was written under a test credential and does not "
                    "say so. The row is permanent; nobody can relabel it "
                    "afterwards." % model)

    def test_the_same_write_by_anybody_else_keeps_what_the_route_declared(
            self):
        """The half that matters. A label that reads `test` for everything
        says nothing about anything — so the identical write, made as the
        ordinary user, must carry the declared source on all three."""
        asset = self._asset()
        self._one_write_that_causes_all_three(asset)
        for model in _MODELS:
            with self.subTest(model=model):
                self.assertEqual(self._last(model, asset).source,
                                 "api_write")

    def test_the_label_names_the_credentials_user_as_the_actor(self):
        """Relabelling the SOURCE must not blur WHO: the row still names
        the credential's own user, which is how a reader finds which suite
        wrote it."""
        asset = self._asset()
        user = self.credential.user_id
        self._one_write_that_causes_all_three(asset.with_user(user).sudo())
        self.assertEqual(
            self._last("nrs.asset.custody", asset).changed_by_id, user)
        self.assertEqual(
            self._last("nrs.asset.movement", asset).moved_by_id, user)
        self.assertEqual(
            self._last("nrs.asset.event", asset).actor_id, user)

    def test_a_declared_reconstruction_is_not_relabelled(self):
        """`tracking_backfill` says the row was REBUILT from the message
        log. That is the more important thing to say about it, whoever was
        acting when it was written — a backfill run under a test credential
        that came out as `test` would hide that a row is a reconstruction
        behind the claim that it is an artefact.

        Custody's and movement's overrides each had this exception, spelt
        two ways; the event record's had none. Written as rows on the two
        records that publish the value, and asked of `_resolve_source` on
        all three, because the rule is the mixin's whether or not a model
        has a use for the label yet.
        """
        asset = self._asset()
        user = self.credential.user_id
        nobody = self.env["hr.employee"]
        nowhere = self.env["generic.location"]

        link = self.env["nrs.asset.custody"].with_user(user).sudo()._record(
            asset, nobody, self.alice, source="tracking_backfill",
            reason="rebuilt from tracking")
        self.assertEqual(link.source, "tracking_backfill")

        move = self.env["nrs.asset.movement"].with_user(user).sudo()._record(
            asset, nowhere, self.room, source="tracking_backfill",
            reason="rebuilt from tracking")
        self.assertEqual(move.source, "tracking_backfill")

        for model in _MODELS:
            with self.subTest(model=model):
                Model = self.env[model].with_user(user).sudo()
                self.assertEqual(
                    Model._resolve_source("tracking_backfill", user),
                    "tracking_backfill")
                # …and the exemption is for a reconstruction ONLY. An
                # ordinary declared source under the same credential is
                # still relabelled, or the test above passed by accident.
                declared = Model._context_sources[0]
                self.assertEqual(Model._resolve_source(declared, user),
                                 "test")

    def test_the_derivation_is_the_clients_and_nobody_forwards_to_it(self):
        """`nrs.asset.custody._is_test_credential_user` was a forwarder kept
        "because scripts and the docs cite it"; a search found that nothing
        did, and it went with the override that used it. One statement of
        what a test credential is — on `myservice.api.client`."""
        Client = self.env["myservice.api.client"]
        self.assertTrue(
            Client._is_test_credential_user(self.credential.user_id.id))
        self.assertFalse(Client._is_test_credential_user(self.env.uid))
        for model in _MODELS:
            with self.subTest(model=model):
                self.assertFalse(
                    hasattr(self.env[model], "_is_test_credential_user"))
