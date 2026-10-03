"""The grant, and the refusal — driven over HTTP, and through every door.

Handoff 42 §2, §3 and §6. `models/access_guard.py` makes two promises that
are only worth what their evidence is worth:

1. **`base.group_system` — and every group that is not one of the four
   Cadra roles — cannot be granted or removed over the API**, by anybody:
   not by an `admin`-scoped credential on its own user (the exposure report
   41 §G named), not on somebody else's.
2. **Nobody grants themselves a role.** A person removing one of their own
   is allowed; adding one is refused in the model's own sentence.

And the three things that must stay true around them: Odoo's own
last-administrator guard still fires; a write with NO request bound — the
shell, a migration, a seed — is not guarded at all; and a refusal writes
NOTHING, the access record included, which is counted before and after
every refused call rather than assumed from the exception.

**Driven through `POST /users/<id>/roles` with real tokens**, minted by the
real routes — one for an API credential (`/auth/token`) and one for a
person (`/auth/login`) — because the refusal lives on the model and the
point of the handoff is that the HTTP caller reads the model's sentence as
a `403`. The doors the route never opens (`res.groups.create` / `unlink`,
`implied_ids`, `res.users.unlink`, and membership from the group side) are
driven in the ORM with a minimal fake request pushed onto
`odoo.http._request_stack`, carrying only `jwt_claims` — which is exactly
and only what the guard reads — and then the same calls with the stack
empty, to show the guard is silent outside the API.

Run it:

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098 \\
      --test-enable --test-tags /myservice_api --workers=0

`--workers=0` is not optional (see `test_auditor_access.py`); read the
`of N tests` line, not the exit code. Fixtures carry a `h42probe<hex>`
marker; nothing here commits.
"""
import json
import uuid

from odoo.exceptions import AccessError, ValidationError
from odoo.http import _request_stack
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase

from odoo.addons.myservice_api.models.access_guard import API_GRANTABLE_XMLIDS

ONLY_THESE = "Over the API only these roles can be granted or removed"
NOBODY_THEMSELVES = "Nobody grants themselves a role"


class _FakeApiRequest:
    """The least a request can be and still be an API caller to the guard:
    an object that is truthy and carries `jwt_claims` — and an `env`,
    because the refusal's `_()` asks `odoo.http.request.env.lang` for the
    language (`tools/translate.py:542`) and the first run of this file
    died there with `AttributeError: '_FakeApiRequest' object has no
    attribute 'env'` on every one of the five tests that bind it: the
    guard had already raised, and it was the SENTENCE that could not be
    built. Nothing else reads anything else."""

    def __init__(self, uid, env):
        self.jwt_claims = {"uid": uid, "scopes": ["admin"]}
        self.env = env
        # `res.users.create` reaches `website.get_current_website`, which
        # asks `request.session.get('force_website_id')` when a request is
        # bound. An empty mapping answers it the way a real session without
        # that key does.
        self.session = {}


@tagged("post_install", "-at_install")
class TestAccessGuard(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marker = "h42probe%s" % uuid.uuid4().hex[:8]
        ref = cls.env.ref
        cls.g_user = ref("base.group_user")
        cls.g_system = ref("base.group_system")
        cls.g_asset_user = ref("myservice_asset_register.group_asset_user")
        cls.g_asset_manager = ref("myservice_asset_register.group_asset_manager")
        cls.g_tagger = ref("myservice_asset_register.group_tag_issuing_unit")
        cls.g_auditor = ref("myservice_api.group_auditor")

        # ── the credential: `admin` on the CLIENT RECORD, an ordinary
        #    internal user underneath (`SCOPE_GROUPS` maps `admin` to no
        #    group). That is the exposure: a token that can do everything,
        #    on a user that is deliberately not an administrator.
        cls.api_client = cls.create_api_client({
            "name": "%s admin" % cls.marker,
            "client_id": "%s_admin" % cls.marker,
            "scopes": "admin",
        })
        cls.secret = cls.api_client.rotate_secret()
        cls.cred_user = cls.api_client.user_id

        # ── the people ───────────────────────────────────────────────
        Users = cls.env["res.users"].sudo().with_context(no_reset_password=True)
        cls.person_password = uuid.uuid4().hex
        cls.person = Users.create({
            "name": "%s person" % cls.marker,
            "login": "%s.person" % cls.marker,
            "password": cls.person_password,
            "group_ids": [(6, 0, [cls.g_user.id, cls.g_system.id,
                                  cls.g_asset_manager.id])],
        })
        cls.other = Users.create({
            "name": "%s other" % cls.marker,
            "login": "%s.other" % cls.marker,
            "group_ids": [(6, 0, [cls.g_user.id, cls.g_asset_user.id])],
        })
        cls.third = Users.create({
            "name": "%s third" % cls.marker,
            "login": "%s.third" % cls.marker,
            "group_ids": [(6, 0, [cls.g_user.id])],
        })

        # ── the tenant's own configuration (as test_auditor_access.py) ──
        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)
        if ICP.get_param("myservice_api.turnstile_secret"):
            ICP.set_param("myservice_api.turnstile_secret", "")

    # ── helpers ──────────────────────────────────────────────────────

    def _cred_token(self):
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.api_client.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _person_token(self):
        r = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": self.person.login,
                             "password": self.person_password}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200,
                         "the person could not log in: %s" % r.text)
        return r.json()["data"]["access_token"]

    def _set_roles(self, token, user, roles, dry_run=None):
        body = {"roles": roles}
        if dry_run is not None:
            body["dry_run"] = dry_run
        return self.url_open(
            "/api/v1/users/%d/roles" % user.id, method="POST",
            data=json.dumps(body),
            headers={"Authorization": "Bearer %s" % token,
                     "Content-Type": "application/json"})

    def _groups(self, user):
        self.env.invalidate_all()
        return set(user.sudo().group_ids.ids)

    def _record(self):
        return self.env["myservice.api.access.change"].sudo()

    def _count(self):
        self.env.flush_all()
        return self._record().search_count([])

    def _watermark(self):
        self.env.flush_all()
        last = self._record().search([], order="id desc", limit=1)
        return last.id or 0

    def _rows_since(self, mark, domain=None):
        self.env.flush_all()
        return self._record().search(
            [("id", ">", mark)] + list(domain or []), order="id")

    def _assert_refused(self, r, sentence, user, groups_before, count_before):
        self.assertEqual(r.status_code, 403, r.text)
        body = r.json()
        self.assertEqual(body["error"]["code"], "forbidden", body)
        self.assertIn(sentence, body["error"]["message"], body)
        self.assertNotIn("data", body, "a refusal carrying a record")
        self.assertEqual(self._groups(user), groups_before,
                         "a refused change moved the membership")
        self.assertEqual(self._count(), count_before,
                         "a refused change wrote into the access record")

    @staticmethod
    def _keys(roles):
        return [r["key"] for r in roles]

    # ── ruling 1: system is not grantable, by anybody ────────────────

    def test_i_the_credential_cannot_make_its_own_user_an_administrator(self):
        """Report 41 §G's exposure, refused — and refused with ruling 1's
        sentence, not ruling 2's, because a group outside the four is judged
        before whose account it is."""
        before, count = self._groups(self.cred_user), self._count()
        self.assertNotIn(self.g_system.id, before)
        r = self._set_roles(self._cred_token(), self.cred_user, ["system"])
        self._assert_refused(r, ONLY_THESE, self.cred_user, before, count)
        # Named by the PUBLISHED alias, the one `/roles` says (handoff 44
        # §3). Until 44 this asserted the group's `full_name` — on 19 *Role
        # / Administrator* — so the suite pinned the two names it should
        # have been catching.
        message = r.json()["error"]["message"]
        self.assertIn("'System Administrator' is not one of them", message)
        own = self.g_system.sudo().full_name or self.g_system.sudo().name
        self.assertNotEqual(own, "System Administrator",
                            "Odoo now calls it what we do; this test no "
                            "longer distinguishes the two names")
        self.assertNotIn(own, message,
                         "the refusal says Odoo's name for the group")

    def test_i_the_record_names_the_group_as_the_api_does(self):
        """The access-change snapshot and the access report's roster use the
        same alias, so the record an auditor reads, the refusal and `/users`
        say one name. Driven through the recorder by a back-office grant
        (no request, so the guard is silent and the row is written)."""
        Change = self._record()
        mark = self._watermark()
        self.third.sudo().write({"group_ids": [(4, self.g_system.id)]})
        self.env.flush_all()
        rows = Change.search([("id", ">", mark),
                              ("user_id", "=", self.third.id)])
        self.assertEqual(rows.mapped("group_name"), ["System Administrator"],
                         "1 back-office grant, %d rows" % len(rows))
        # Every other group keeps the name the record already used.
        g_user = self.env.ref("base.group_user")
        self.assertEqual(Change._group_label(g_user),
                         g_user.sudo().full_name or g_user.sudo().name)

    def test_ii_the_credential_cannot_make_anybody_else_one_either(self):
        before, count = self._groups(self.other), self._count()
        r = self._set_roles(self._cred_token(), self.other, ["system"])
        self._assert_refused(r, ONLY_THESE, self.other, before, count)

    # ── ruling 2: nobody grants themselves a role ────────────────────

    def test_iii_a_person_cannot_add_a_role_to_their_own_account(self):
        """The person holds `system` + Asset Manager; asking for those plus
        Auditor adds exactly one grantable group to their own account."""
        before, count = self._groups(self.person), self._count()
        r = self._set_roles(self._person_token(), self.person,
                            ["system", "asset_manager", "auditor"])
        self._assert_refused(r, NOBODY_THEMSELVES, self.person, before, count)
        self.assertIn(self.person.login, r.json()["error"]["message"])

    def test_iv_a_person_may_remove_their_own_role(self):
        """A downgrade is allowed, and the preview of what it costs is
        honest: without Asset Manager the implied Asset User goes too."""
        r = self._set_roles(self._person_token(), self.person, ["system"])
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertIs(data["applied"], True)
        self.assertEqual(data["revoked"], ["asset_manager"])
        self.assertEqual(data["granted"], [])
        self.assertNotIn("asset_manager", self._keys(data["after"]["roles_direct"]))
        self.assertNotIn("asset_user",
                         self._keys(data["after"]["roles_effective"]))
        self.assertIn("asset_user",
                      self._keys(data["before"]["roles_effective"]))
        self.assertNotIn(self.g_asset_manager.id, self._groups(self.person))
        self.assertIn(self.g_system.id, self._groups(self.person))

    # ── a grant that is allowed, and the record it leaves ────────────

    def test_v_a_grant_is_recorded_with_the_credential_as_the_actor(self):
        """Handoff 42 §4: no second audit. The recorder's hook writes the
        row; what is checked is that the actor is the token's user — the
        credential's own `res.users` — and not Administrator, although the
        route ran under `sudo()`."""
        mark = self._watermark()
        r = self._set_roles(self._cred_token(), self.third, ["tag_issuing_unit"])
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertIs(data["applied"], True)
        self.assertEqual(data["granted"], ["tag_issuing_unit"])
        self.assertEqual(data["revoked"], [])
        self.assertEqual(self._keys(data["user"]["roles_direct"]),
                         ["tag_issuing_unit"])
        self.assertIn(self.g_tagger.id, self._groups(self.third))

        rows = self._rows_since(mark, [("user_id", "=", self.third.id)])
        self.assertEqual(len(rows), 1,
                         "one grant produced %d row(s)" % len(rows))
        row = rows[0]
        self.assertEqual(row.event, "granted")
        self.assertEqual(row.group_id, self.g_tagger)
        self.assertEqual(row.source, "user_write")
        self.assertIs(row.attributable, True)
        self.assertEqual(row.changed_by_id, self.cred_user)
        self.assertEqual(row.actor, self.cred_user.name)
        self.assertEqual(row.changed_by_login, self.cred_user.login)

    # ── dry run: the preview is the write, rolled back ───────────────

    def test_vi_a_dry_run_previews_implication_and_writes_nothing(self):
        before, count = self._groups(self.third), self._count()
        r = self._set_roles(self._cred_token(), self.third, ["asset_manager"],
                            dry_run=True)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertIs(data["applied"], False)
        self.assertEqual(data["granted"], ["asset_manager"])
        self.assertEqual(self._keys(data["after"]["roles_direct"]),
                         ["asset_manager"])
        # Implication, computed by Odoo and not by the route.
        self.assertEqual(self._keys(data["after"]["roles_effective"]),
                         ["asset_user", "asset_manager"])
        self.assertEqual(
            [x["via"] for x in data["after"]["roles_effective"]],
            [["Asset Manager"], []])
        self.assertEqual(self._groups(self.third), before,
                         "a dry run moved the membership")
        self.assertEqual(self._count(), count,
                         "a dry run wrote into the access record")

    def test_vi_a_dry_run_of_a_refused_change_is_refused(self):
        before, count = self._groups(self.other), self._count()
        r = self._set_roles(self._cred_token(), self.other, ["system"],
                            dry_run=True)
        self._assert_refused(r, ONLY_THESE, self.other, before, count)

    # ── outside the API: silent, and Odoo's own guard still fires ────

    def test_vii_without_a_request_the_guard_is_silent(self):
        """The shell, a migration, a seed: `base.group_system` can be
        granted, as `scripts/bootstrap.py` must be able to."""
        self.assertFalse(_request_stack.top, "a request is bound in the "
                         "test thread; this test proves the OTHER case")
        self.other.sudo().write({"group_ids": [(4, self.g_system.id)]})
        self.assertIn(self.g_system.id, self._groups(self.other))

    def test_vii_the_last_administrator_guard_still_fires(self):
        admins = self.env["res.users"].sudo().with_context(
            active_test=False).search([("group_ids", "in", [self.g_system.id])])
        self.assertTrue(admins, "0 of the tenant's users hold base.group_system")
        with self.assertRaises(ValidationError):
            admins.write({"group_ids": [(3, self.g_system.id)]})
            self.env.flush_all()

    # ── the doors the route never opens, driven in the ORM ───────────

    def _as_api_caller(self, uid):
        """Push a minimal API request; the caller pops it in `finally`."""
        _request_stack.push(_FakeApiRequest(uid, self.env))

    def test_viii_groups_cannot_be_created_or_deleted_over_the_api(self):
        Groups = self.env["res.groups"].sudo()
        victim = Groups.create({"name": "%s group" % self.marker})
        count = self._count()
        self._as_api_caller(self.cred_user.id)
        try:
            with self.assertRaises(AccessError):
                Groups.create({"name": "%s api group" % self.marker})
            with self.assertRaises(AccessError):
                victim.unlink()
        finally:
            _request_stack.pop()
        self.assertEqual(self._count(), count)
        self.assertTrue(victim.exists())
        # The same calls with no request bound succeed (the test's own
        # rollback takes them back).
        self.assertFalse(_request_stack.top)
        Groups.create({"name": "%s shell group" % self.marker})
        victim.unlink()
        self.assertFalse(victim.exists())

    def test_viii_an_implication_cannot_be_changed_over_the_api(self):
        count = self._count()
        self._as_api_caller(self.cred_user.id)
        try:
            with self.assertRaises(AccessError) as cm:
                self.g_auditor.sudo().write(
                    {"implied_ids": [(4, self.g_asset_user.id)]})
            self.assertIn("What a group means cannot be changed over the API",
                          str(cm.exception))
            # `implied_by_ids` is the same edge from the other end.
            with self.assertRaises(AccessError):
                self.g_asset_user.sudo().write(
                    {"implied_by_ids": [(4, self.g_auditor.id)]})
        finally:
            _request_stack.pop()
        self.assertEqual(self._count(), count)
        self.env.invalidate_all()
        self.assertNotIn(self.g_asset_user.id, self.g_auditor.implied_ids.ids)
        # Unguarded without a request: the recorder writes its implication
        # row and the edge appears.
        mark = self._watermark()
        self.g_auditor.sudo().write({"implied_ids": [(4, self.g_asset_user.id)]})
        self.assertIn(self.g_asset_user.id, self.g_auditor.implied_ids.ids)
        self.assertEqual(
            self._rows_since(mark, [("event", "=", "implied_added")]).mapped(
                "group_id"), self.g_auditor)

    def test_viii_an_account_cannot_be_deleted_over_the_api(self):
        count = self._count()
        self._as_api_caller(self.cred_user.id)
        try:
            with self.assertRaises(AccessError) as cm:
                self.third.sudo().unlink()
        finally:
            _request_stack.pop()
        self.assertIn("An account cannot be deleted over the API",
                      str(cm.exception))
        self.assertTrue(self.third.exists())
        self.assertEqual(self._count(), count)
        with self.env.cr.savepoint():
            self.third.sudo().unlink()
            self.assertFalse(self.third.exists())

    def test_viii_the_group_side_is_judged_by_the_same_two_rules(self):
        """`res.groups.write({'user_ids': …})` is the same change from the
        other side (`access_change.py`, case 3) and meets the same guard:
        a self-grant refused, `base.group_system` refused, a grant of a
        Cadra role to somebody else allowed."""
        count = self._count()
        as_person = self.env["res.groups"].with_user(self.person).sudo()
        self._as_api_caller(self.person.id)
        try:
            with self.assertRaises(AccessError) as cm:
                as_person.browse(self.g_auditor.id).write(
                    {"user_ids": [(4, self.person.id)]})
            self.assertIn(NOBODY_THEMSELVES, str(cm.exception))
            with self.assertRaises(AccessError) as cm:
                as_person.browse(self.g_system.id).write(
                    {"user_ids": [(4, self.third.id)]})
            self.assertIn(ONLY_THESE, str(cm.exception))
            self.assertEqual(self._count(), count,
                             "a refused group-side change wrote a row")
            mark = self._watermark()
            as_person.browse(self.g_auditor.id).write(
                {"user_ids": [(4, self.third.id)]})
        finally:
            _request_stack.pop()
        self.assertIn(self.g_auditor.id, self._groups(self.third))
        rows = self._rows_since(mark, [("user_id", "=", self.third.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.source, "group_write")
        self.assertEqual(rows.changed_by_id, self.person)

    def test_viii_a_create_over_the_api_may_land_only_in_the_four(self):
        """Handoff 43 will create people over the API; the guard is ready
        for it: the default groups and the four pass, `base.group_system`
        does not, and a refused create leaves no account behind."""
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        count = self._count()
        login = "%s.created" % self.marker
        self._as_api_caller(self.cred_user.id)
        try:
            with self.assertRaises(AccessError) as cm:
                Users.create({
                    "name": "%s created admin" % self.marker,
                    "login": login,
                    "group_ids": [(6, 0, [self.g_user.id, self.g_system.id])],
                })
            self.assertIn(ONLY_THESE, str(cm.exception))
            self.assertFalse(Users.with_context(active_test=False).search(
                [("login", "=", login)]), "a refused create left an account")
            self.assertEqual(self._count(), count)
            created = Users.create({
                "name": "%s created tagger" % self.marker,
                "login": login,
                "group_ids": [(6, 0, [self.g_user.id, self.g_tagger.id])],
            })
        finally:
            _request_stack.pop()
        self.assertIn(self.g_tagger.id, self._groups(created))

    # ── the vocabulary says which four ───────────────────────────────

    def test_roles_marks_exactly_the_grantable_four(self):
        r = self.url_open("/api/v1/roles",
                          headers={"Authorization": "Bearer %s" % self._cred_token()})
        self.assertEqual(r.status_code, 200, r.text)
        roles = r.json()["data"]
        grantable = {x["xmlid"] for x in roles if x["grantable"] is True}
        self.assertEqual(grantable, set(API_GRANTABLE_XMLIDS))
        by_key = {x["key"]: x for x in roles}
        self.assertIs(by_key["system"]["grantable"], False)
        self.assertEqual(len(grantable), 4)
