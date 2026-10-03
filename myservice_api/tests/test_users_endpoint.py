"""`GET /roles`, `GET /users`, `GET /users/<id>` — proved by acting, in the
registry, where the fixtures can be made to order. Handoff 41 §4B.

The HTTP suite (`tests/test_users.py`) proves the contract against whatever
accounts a tenant happens to have, and skips when one it needs is absent.
This suite MAKES them: an Asset Manager (direct one role, effective two), a
tagger holding only the Tag-Issuing Unit, an inactive Asset User, and an
API credential — then asserts the exact answers.

And it proves the handoff's own requirement, the one no HTTP test can
state: that the three routes WRITE NOTHING. The forward record of
membership changes (`myservice.api.access.change`, handoff 24) is counted
before and after, and so is the membership relation itself and the
implication relation — three counts that must not move across every route
and every filter this module publishes.

Run it:

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098 \\
      --test-enable --test-tags /myservice_api --workers=0

`--workers=0` is not optional (see `test_auditor_access.py`); read the
`of N tests` line, not the exit code.

Fixtures carry a `h41probe<hex>` marker; nothing here commits.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestUsersEndpoint(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils, v1_users
        cls.utils = utils
        cls.v1_users = v1_users

        cls.marker = "h41probe%s" % uuid.uuid4().hex[:8]

        # ── the credential the suite calls as ────────────────────────
        #
        # `admin` on the CLIENT RECORD: that is where an API credential's
        # token comes from, and `admin` is a wildcard in `require_jwt`. The
        # client's own `res.users` is an ordinary internal user —
        # `SCOPE_GROUPS` deliberately maps `admin` to no group — which is
        # exactly the fact its row below is expected to publish.
        cls.api_client = cls.create_api_client({
            "name": "%s admin" % cls.marker,
            "client_id": "%s_admin" % cls.marker,
            "scopes": "admin",
        })
        cls.secret = cls.api_client.rotate_secret()

        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

        # ── the people ───────────────────────────────────────────────
        #
        # `group_ids`: Odoo 19's name for the membership field. Every
        # profile is on 19 (`tests/test_deployment_profile.py` asserts it).
        Users = cls.env["res.users"].sudo().with_context(no_reset_password=True)
        ref = cls.env.ref
        internal = ref("base.group_user").id
        cls.manager = Users.create({
            "name": "%s manager" % cls.marker,
            "login": "%s.manager" % cls.marker,
            "group_ids": [(6, 0, [
                internal,
                ref("myservice_asset_register.group_asset_manager").id])],
        })
        cls.tagger = Users.create({
            "name": "%s tagger" % cls.marker,
            "login": "%s.tagger" % cls.marker,
            "group_ids": [(6, 0, [
                internal,
                ref("myservice_asset_register.group_tag_issuing_unit").id])],
        })
        cls.leaver = Users.create({
            "name": "%s leaver" % cls.marker,
            "login": "%s.leaver" % cls.marker,
            "active": False,
            "group_ids": [(6, 0, [
                internal,
                ref("myservice_asset_register.group_asset_user").id])],
        })

    # ── helpers ──────────────────────────────────────────────────────

    def _token(self):
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.api_client.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _get(self, path):
        return self.url_open(
            path, headers={"Authorization": "Bearer %s" % self._token()})

    def _ok(self, path):
        r = self._get(path)
        self.assertEqual(r.status_code, 200, "%s: %s" % (path, r.text))
        body = r.json()
        self.assertIn("data", body, body)
        return body

    def _row(self, user):
        return self._ok("/api/v1/users/%d" % user.id)["data"]

    @staticmethod
    def _keys(roles):
        return [r["key"] for r in roles]

    def _counts(self):
        """The three tables a writer of membership would move."""
        self.env.cr.execute("SELECT count(*) FROM res_groups_users_rel")
        membership = self.env.cr.fetchone()[0]
        self.env.cr.execute("SELECT count(*) FROM res_groups_implied_rel")
        implication = self.env.cr.fetchone()[0]
        record = self.env["myservice.api.access.change"].sudo().search_count([])
        return {"membership_rows": membership,
                "implication_rows": implication,
                "access_change_rows": record}

    # ── direct versus effective ──────────────────────────────────────

    def test_an_asset_manager_is_a_member_of_one_role_and_holds_three(self):
        """Handoff 41's trap, stated as an answer: direct `[asset_manager]`,
        effective `[asset_user, asset_officer, asset_manager]` (the Officer
        since handoff 47), in catalogue order."""
        row = self._row(self.manager)
        self.assertEqual(self._keys(row["roles_direct"]), ["asset_manager"])
        self.assertEqual(self._keys(row["roles_effective"]),
                         ["asset_user", "asset_officer", "asset_manager"])
        self.assertEqual(row["kind"], "person")
        self.assertEqual(row["scopes_source"], "roles")
        self.assertEqual(row["scopes"],
                         self.utils.scopes_for_user(self.manager.sudo()))
        # The implication the row reports is the one `/roles` reports —
        # the ladder User < Officer < Manager since handoff 47.
        roles = {r["key"]: r for r in self._ok("/api/v1/roles")["data"]}
        self.assertEqual(roles["asset_manager"]["implies"],
                         ["asset_user", "asset_officer"])
        self.assertEqual(roles["asset_officer"]["implies"], ["asset_user"])
        self.assertEqual(roles["asset_user"]["implies"], [])

    def test_a_tagger_holds_exactly_tagging_write_from_its_roles(self):
        row = self._row(self.tagger)
        self.assertEqual(self._keys(row["roles_direct"]), ["tag_issuing_unit"])
        self.assertEqual(self._keys(row["roles_effective"]), ["tag_issuing_unit"])
        self.assertEqual(row["scopes"], ["tagging:write"])
        self.assertEqual(row["scopes"],
                         self.utils.scopes_for_user(self.tagger.sudo()))
        self.assertEqual(row["scopes_source"], "roles")

    def test_an_inactive_account_is_listed_as_inactive_and_filtered(self):
        row = self._row(self.leaver)
        self.assertIs(row["active"], False)
        self.assertEqual(self._keys(row["roles_direct"]), ["asset_user"])
        self.assertEqual(self._keys(row["roles_effective"]), ["asset_user"])

        q = "q=%s" % self.marker

        def listed(extra):
            return {r["id"] for r in
                    self._ok("/api/v1/users?%s%s" % (q, extra))["data"]}

        self.assertIn(self.leaver.id, listed(""), "absent must mean both")
        self.assertIn(self.leaver.id, listed("&active=false"))
        self.assertNotIn(self.leaver.id, listed("&active=true"))
        self.assertIn(self.manager.id, listed("&active=true"))

    # ── the credential's own row ─────────────────────────────────────

    def test_the_calling_credential_is_an_api_credential_not_a_person(self):
        row = self._row(self.api_client.user_id)
        self.assertEqual(row["kind"], "api_credential")
        self.assertEqual(row["scopes_source"], "credential")
        self.assertEqual(row["scopes"], ["admin"])
        self.assertEqual(row["api_client"], {
            "id": self.api_client.id,
            "name": self.api_client.name,
            "client_id": self.api_client.client_id,
            "active": True,
            "is_test_credential": True,
        })
        # `admin` maps to no group (`SCOPE_GROUPS`), so this user is in no
        # role at all — and its token still carries everything. That is the
        # whole reason `scopes_source` exists.
        self.assertEqual(row["roles_direct"], [])
        self.assertEqual(row["roles_effective"], [])
        self.assertNotIn("admin", self.utils.scopes_for_user(
            self.api_client.user_id.sudo()))

    # ── the vocabulary ───────────────────────────────────────────────

    def test_roles_is_group_scopes_re_expressed(self):
        roles = self._ok("/api/v1/roles")["data"]
        expected = [(self.v1_users.role_key(xmlid), sorted(scopes))
                    for xmlid, scopes in self.utils.GROUP_SCOPES]
        self.assertEqual([(r["key"], r["scopes"]) for r in roles], expected)
        for role in roles:
            group = self.env.ref(role["xmlid"], raise_if_not_found=False)
            self.assertEqual(role["installed"], bool(group), role)
            if group and role["xmlid"] != "base.group_system":
                self.assertEqual(role["name"], group.sudo().name)
        by_key = {r["key"]: r for r in roles}
        self.assertEqual(by_key["system"]["name"], "System Administrator")

    # ── the filters, on fixtures made to order ───────────────────────

    def test_role_is_effective_and_role_direct_is_membership(self):
        q = "q=%s" % self.marker
        effective = {r["id"] for r in self._ok(
            "/api/v1/users?%s&role=asset_user" % q)["data"]}
        direct = {r["id"] for r in self._ok(
            "/api/v1/users?%s&role_direct=asset_user" % q)["data"]}
        self.assertIn(self.manager.id, effective,
                      "the manager HOLDS asset_user by implication")
        self.assertNotIn(self.manager.id, direct,
                         "the manager is not a MEMBER of asset_user")
        self.assertIn(self.leaver.id, effective)
        self.assertIn(self.leaver.id, direct)
        self.assertNotIn(self.tagger.id, effective)

        r = self._get("/api/v1/users?role=nonsense")
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(r.json()["error"]["code"], "invalid_request")
        self.assertEqual(r.json()["error"]["details"]["allowed_values"],
                         list(self.v1_users.ROLE_KEYS))

    def test_a_structural_login_is_404_and_detail_round_trips_the_list(self):
        r = self._get("/api/v1/users/1")
        self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(r.json()["error"]["code"], "not_found")
        listed = {r["id"]: r for r in self._ok(
            "/api/v1/users?q=%s" % self.marker)["data"]}
        self.assertEqual(listed[self.manager.id], self._row(self.manager))

    # ── the handoff's own requirement: nothing is written ────────────

    def test_the_three_routes_write_no_membership_and_no_record(self):
        """Counted, not assumed: the access record, the membership relation
        and the implication relation, before and after every route and
        every filter."""
        before = self._counts()
        paths = [
            "/api/v1/roles",
            "/api/v1/users",
            "/api/v1/users?role=asset_user",
            "/api/v1/users?role_direct=asset_manager",
            "/api/v1/users?active=false",
            "/api/v1/users?is_api_client=true",
            "/api/v1/users?q=%s" % self.marker,
            "/api/v1/users/%d" % self.manager.id,
            "/api/v1/users/%d" % self.api_client.user_id.id,
            "/api/v1/users/1",
            "/api/v1/users?role=nonsense",
        ]
        for path in paths:
            self._get(path)
        self.env.invalidate_all()
        after = self._counts()
        self.assertEqual(after, before,
                         "a READ moved a count it must not: %s -> %s"
                         % (before, after))
