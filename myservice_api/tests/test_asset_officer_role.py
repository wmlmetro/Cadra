# -*- coding: utf-8 -*-
"""Handoff 47, driven as the people — the Asset Officer, and the tagger.

Three accounts, each holding exactly one job's groups, each signing in
through the real `/auth/login` and driving the real routes with the token
it was given:

* **the officer** (`group_asset_officer`) — ruling 3. Registers an asset,
  asks for a move, records a verification; is refused the settings, the
  imports, somebody else's approval, a disposal approval, and the tag
  printer. The role between reading the register and running it, proved in
  both directions.
* **the tagger** (Asset User + Tag-Issuing Unit, handoff 41's pairing) —
  ruling 2. Prints a label and asks for its replacement on `tagging:write`,
  the unit's own scope.
* **the manager** (`group_asset_manager`) — the other side of ruling 2,
  which is BREAKING: the group that creates asset records can no longer
  mint or replace a label. `assets:write` stopped opening those routes.

Same conventions as `test_auditor_access.py`: real tokens from the real
login route, never hand-built; nothing here commits — the class rollback
takes every write back.

**`--workers=0` is not optional** — see that file's docstring.
"""
import json
import uuid

from odoo import fields  # noqa: F401  (parity with the sibling suite)
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase

OFFICER_GROUP = "myservice_asset_register.group_asset_officer"
USER_GROUP = "myservice_asset_register.group_asset_user"
MANAGER_GROUP = "myservice_asset_register.group_asset_manager"
TIU_GROUP = "myservice_asset_register.group_tag_issuing_unit"


@tagged("post_install", "-at_install")
class TestAssetOfficerRole(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils
        cls.utils = utils

        cls.marker = "officerprobe%s" % uuid.uuid4().hex[:8]

        Users = cls.env["res.users"].sudo().with_context(
            no_reset_password=True)
        cls.groups_field = ("group_ids" if "group_ids" in Users._fields
                            else "groups_id")

        def mk(label, xmlids):
            password = uuid.uuid4().hex
            user = Users.create({
                "name": "%s %s" % (label, cls.marker),
                "login": "%s.%s@example.invalid" % (label, cls.marker),
                "password": password,
                cls.groups_field: [(6, 0, [
                    cls.env.ref("base.group_user").id,
                ] + [cls.env.ref(x).id for x in xmlids])],
            })
            return user, password

        cls.officer, cls.officer_password = mk("officer", [OFFICER_GROUP])
        cls.tagger, cls.tagger_password = mk("tagger", [USER_GROUP, TIU_GROUP])
        cls.manager, cls.manager_password = mk("manager", [MANAGER_GROUP])

        Category = cls.env["nrs.asset.category"].sudo()
        cls.category = Category.search([], limit=1) or Category.create(
            {"name": "Officer probe"})
        cls.location = cls.env["generic.location"].sudo().create(
            {"name": "officer probe room %s" % cls.marker})
        # Created NOWHERE and untagged, through the ORM: the subject for the
        # tagger's mint and the officer's move/verify.
        cls.asset = cls.env["nrs.asset"].sudo().create({
            "name": "officer probe asset %s" % cls.marker,
            "category_id": cls.category.id,
        })

        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)
        if ICP.get_param("myservice_api.turnstile_secret"):
            ICP.set_param("myservice_api.turnstile_secret", "")

    # ── helpers (the sibling suite's, verbatim in shape) ─────────────

    def _login_token(self, user, password):
        r = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": user.login, "password": password}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200,
                         "%s could not even log in: %s" % (user.login, r.text))
        return r.json()["data"]["access_token"]

    def _send(self, token, method, path, body=None):
        return self.url_open(
            path, method=method,
            data=json.dumps(body if body is not None else {}),
            headers={"Authorization": "Bearer %s" % token,
                     "Content-Type": "application/json"})

    def _get(self, token, path):
        # No body: `url_open` upgrades any request carrying data to a write.
        return self.url_open(
            path, headers={"Authorization": "Bearer %s" % token})

    def _assert_403_names(self, response, scope, what):
        self.assertEqual(
            response.status_code, 403,
            "%s answered %s, not the 403 the role model promises: %s"
            % (what, response.status_code, response.text[:300]))
        self.assertIn(scope, response.text,
                      "%s's refusal does not name `%s`" % (what, scope))

    # ── ruling 3 · the officer's job works ───────────────────────────

    def test_the_officer_token_carries_the_users_reads_plus_assets_write(self):
        officer_scopes = set(self.utils.scopes_for_user(self.officer))
        user_scopes = {s for _x, ss in self.utils.GROUP_SCOPES
                       for s in ss
                       if _x == USER_GROUP}
        self.assertEqual(
            officer_scopes, user_scopes | {"assets:write"},
            "the officer's effective scopes are %s" % sorted(officer_scopes))

    def test_the_officer_registers_moves_and_verifies(self):
        token = self._login_token(self.officer, self.officer_password)

        r = self._send(token, "POST", "/api/v1/assets", {
            "name": "officer registered %s" % self.marker,
            "category_id": self.category.id,
        })
        self.assertEqual(r.status_code, 201,
                         "the officer cannot register an asset — the role's "
                         "first job: %s" % r.text[:300])

        r = self._send(token, "POST",
                       "/api/v1/assets/%d/move" % self.asset.id, {
                           "to_location_id": self.location.id,
                           "approver_id": self.manager.id,
                           "reason": "officer probe move",
                       })
        self.assertEqual(r.status_code, 200,
                         "the officer cannot ask for a move: %s" % r.text[:300])
        self.assertTrue(r.json()["data"].get("pending_approval"),
                        "the move did not raise a request — approval is "
                        "required on every tenant here (handoff 35)")

        r = self._send(token, "POST",
                       "/api/v1/assets/%d/verify" % self.asset.id,
                       {"notes": "officer probe sighting"})
        self.assertEqual(r.status_code, 200,
                         "the officer cannot record a verification: %s"
                         % r.text[:300])
        self.assertEqual(self.asset.last_verified_by.id, self.officer.id,
                         "the verification does not name the officer")

    def test_the_officer_is_refused_running_the_register(self):
        """Settings, imports, other people's approvals, disposals, the tag
        printer — each refused AT THE SCOPE GATE, naming the scope."""
        token = self._login_token(self.officer, self.officer_password)
        for method, path, body, scope in [
            ("PATCH", "/api/v1/settings/branding", {"brand_name": "x"},
             "settings:write"),
            ("PATCH", "/api/v1/settings/depreciation", {}, "settings:write"),
            ("POST", "/api/v1/integrations/employees/import", {},
             "integrations:write"),
            ("POST", "/api/v1/approvals/0/approve", {}, "approvals:write"),
            ("POST", "/api/v1/assets/%d/approve-disposal" % self.asset.id,
             {}, "approvals:write"),
            ("POST", "/api/v1/barcode/generate",
             {"asset_ids": [self.asset.id]}, "tagging:write"),
            ("POST", "/api/v1/locations", {"name": "officer probe"},
             "locations:write"),
        ]:
            self._assert_403_names(
                self._send(token, method, path, body), scope,
                "%s %s as the officer" % (method, path))

    def test_the_officer_cannot_be_the_approver(self):
        """Holding the officer role does not make somebody a second person:
        `APPROVER_GROUP` is the Asset Manager, and a request naming the
        officer as approver is refused by the model."""
        token = self._login_token(self.officer, self.officer_password)
        r = self._send(token, "POST",
                       "/api/v1/assets/%d/move" % self.asset.id, {
                           "to_location_id": self.location.id,
                           "approver_id": self.officer.id,
                           "reason": "officer probe self-approver",
                       })
        self.assertEqual(r.status_code, 400,
                         "naming an officer as approver answered %s: %s"
                         % (r.status_code, r.text[:300]))

    # ── ruling 2 · minting and replacing a tag is tagging ────────────

    def test_the_tagger_mints_and_requests_replacement_on_its_own_scope(self):
        token = self._login_token(self.tagger, self.tagger_password)

        r = self._send(token, "POST", "/api/v1/barcode/generate",
                       {"asset_ids": [self.asset.id]})
        self.assertEqual(r.status_code, 200,
                         "the tagger cannot mint a label — ruling 2 is not "
                         "landed: %s" % r.text[:300])
        tag = self.env["nrs.asset.tag.label"].sudo().search(
            [("asset_id", "=", self.asset.id), ("state", "=", "active")],
            limit=1)
        self.assertTrue(tag, "the mint answered 200 and no active label "
                             "exists on the asset")

        r = self._send(token, "POST",
                       "/api/v1/tags/%d/request-replacement" % tag.id, {
                           "reason": "damaged",
                           "notes": "officer probe: faded label",
                           "approver_id": self.manager.id,
                       })
        self.assertEqual(r.status_code, 200,
                         "the tagger cannot ask for a replacement: %s"
                         % r.text[:300])
        self.assertEqual(tag.state, "pending",
                         "the label did not move to pending")

    def test_the_manager_no_longer_mints_or_replaces(self):
        """The BREAKING half of ruling 2, measured: `assets:write` stopped
        opening the tag routes. The group that creates asset records is no
        longer the group that mints their labels."""
        token = self._login_token(self.manager, self.manager_password)
        self._assert_403_names(
            self._send(token, "POST", "/api/v1/barcode/generate",
                       {"asset_ids": [self.asset.id]}),
            "tagging:write", "POST /barcode/generate as the manager")
        self._assert_403_names(
            self._send(token, "POST", "/api/v1/tags/0/request-replacement",
                       {"reason": "damaged", "approver_id": self.officer.id}),
            "tagging:write", "POST /tags/0/request-replacement as the manager")

    # ── ruling 1 · the two splits, as the people ─────────────────────

    def test_the_officer_is_refused_the_access_record_and_the_fleet(self):
        token = self._login_token(self.officer, self.officer_password)
        self._assert_403_names(
            self._get(token,
                      "/api/v1/reports/access-changes"
                      "?from=2026-01-01&to=2026-01-02"),
            "access:read", "the access record as the officer")
        self._assert_403_names(
            self._get(token, "/api/v1/fleet/dashboard"),
            "operations:read", "the fleet dashboard as the officer")
        # The register's own figures still answer — the split took the
        # fleet away, not the dashboard.
        r = self._get(token, "/api/v1/dashboard/kpis")
        self.assertEqual(r.status_code, 200,
                         "the officer lost the asset dashboard's figures: %s"
                         % r.text[:300])
