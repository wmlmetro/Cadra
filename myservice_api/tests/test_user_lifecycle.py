"""The person, and the door — in the registry. Handoff 43.

What the HTTP suite (`tests/test_user_lifecycle.py`) cannot reach from
outside, driven here with real tokens on a test database:

1. **The door is shut by the code, not by a row.** Both rows set to free
   sign-up, and `_get_signup_invitation_scope()` still answers `b2b`; an
   anonymous `GET /web/signup` is still a 404.
2. **A method we override is a name the framework owns.** Core's `create`
   and `action_reset_password` are read from source and must still end in
   `_action_reset_password`; the controller must still ask
   `_get_signup_invitation_scope`; `_get_signup_url` must still go through
   `_get_signup_url_for_action`. The relay's `_connect__` was carried onto
   19 dead for the life of the stack because nobody held this.
3. **The letter is the tenant's.** Captured on its way out: the brand the
   parameters say, the organisation's name, one sentence saying what it is,
   a link on the host the request came in on, no Odoo anywhere, no
   password; the plain-text part Odoo derives from it carries the link.
4. **Creating with roles is granting roles.** `system` is refused with the
   model's sentence and NO account is created, no letter sent.
5. **The record names the person who clicked.** The `user_create` rows
   carry the token's user as `changed_by_id`.
6. **Deactivation takes effect now.** A live token is refused on the next
   request, `/auth/login` refuses, and reactivation lets them back in.
7. **The label.** A person created under a test credential is a fixture
   on the partner behind them; one created by an administrator is not.
8. **Three refusals the verification pass found untested** (report 43 §F):
   the last system administrator who is a PERSON cannot be deactivated
   while a credential's user also holds the group; a deactivated nominee
   is refused on `/move`; an anonymous password reset ignores a forged
   `X-Forwarded-Host` and builds its link on core's base.
"""
import inspect
import json
import re
import uuid

from odoo import fields
from odoo.addons import auth_signup
from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase
from odoo.tests import tagged
from odoo.tools import html2plaintext

from odoo.addons.myservice_api.models import invitation as inv

ONLY_THESE = "Over the API only these roles can be granted or removed"
LOGO_SVG = ("data:image/svg+xml;base64,"
            "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIg"
            "aGVpZ2h0PSIxMCI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIiBmaWxsPSIjMTIz"
            "NDU2Ii8+PC9zdmc+")


@tagged("post_install", "-at_install")
class TestUserLifecycle(CadraHttpCase, MockEmail):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marker = "h43probe%s" % uuid.uuid4().hex[:8]
        ref = cls.env.ref
        cls.g_user = ref("base.group_user")
        cls.g_system = ref("base.group_system")
        cls.g_asset_user = ref("myservice_asset_register.group_asset_user")

        # An administrator PERSON, with a password, so the token is a login
        # token whose `uid` is a person the record can name.
        Users = cls.env["res.users"].sudo().with_context(no_reset_password=True)
        cls.admin_password = uuid.uuid4().hex
        cls.admin = Users.create({
            "name": "%s admin" % cls.marker,
            "login": "%s.admin" % cls.marker,
            "email": "%s.admin@example.invalid" % cls.marker,
            "password": cls.admin_password,
            "group_ids": [(6, 0, [cls.g_user.id, cls.g_system.id])],
        })
        # A test CREDENTIAL with `admin`, for the label test.
        cls.api_client = cls.create_api_client({
            "name": "%s cred" % cls.marker,
            "client_id": "%s_cred" % cls.marker,
            "scopes": "admin",
        })
        cls.secret = cls.api_client.rotate_secret()

        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)
        if ICP.get_param("myservice_api.turnstile_secret"):
            ICP.set_param("myservice_api.turnstile_secret", "")

    # ── helpers ──────────────────────────────────────────────────────

    def _login(self, login, password):
        return self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": login, "password": password}),
            headers={"Content-Type": "application/json"})

    def _admin_token(self):
        r = self._login(self.admin.login, self.admin_password)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _cred_token(self):
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.api_client.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _post(self, token, path, body=None):
        return self.url_open(
            path, method="POST", data=json.dumps(body if body is not None else {}),
            headers={"Authorization": "Bearer %s" % token,
                     "Content-Type": "application/json"})

    def _get(self, token, path):
        return self.url_open(path, headers={"Authorization": "Bearer %s" % token})

    def _email(self, tag):
        return "%s.%s@example.invalid" % (self.marker, tag)

    @staticmethod
    def _prose(html):
        """The letter with every URL removed — what the "no Odoo anywhere"
        assertion is about. The sign-up link carries `db=<database>`, and
        CI's database is called `odoo` (`.env.example`), which is how the
        first CI run after the merge matched the word in a URL and failed
        a letter that says nothing about Odoo (report 43 §E)."""
        return re.sub(r"https?://[^\s\"'<]+", "", html)

    def _sent(self):
        """The mails the gateway mock saw that STILL EXIST. In test mode a
        write route is served first on a read-only cursor and retried on a
        read/write one (`docs/ENVIRONMENT-FACTS.md`), so the mock records a
        `mail.mail` the rollback then removes beside the one that stayed."""
        return self._new_mails.exists()

    # ── 1. the door ──────────────────────────────────────────────────

    def test_i_the_door_is_shut_whatever_the_rows_say(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("auth_signup.invitation_scope", "b2c")
        self.env["website"].sudo().search([]).write({"auth_signup_uninvited": "b2c"})
        self.assertEqual(self.env["res.users"]._get_signup_invitation_scope(), inv.SIGNUP_SCOPE)
        self.assertEqual(inv.SIGNUP_SCOPE, "b2b")
        r = self.url_open("/web/signup")
        self.assertEqual(r.status_code, 404,
                         "free sign-up answered %s with both rows set to b2c" % r.status_code)
        # and our override is the one the registry resolves to, not website's
        resolved = type(self.env["res.users"])._get_signup_invitation_scope
        self.assertTrue(resolved.__module__.startswith("odoo.addons.myservice_api"),
                        resolved.__module__)

    # ── 2. the names the framework owns ──────────────────────────────

    def test_ii_core_still_calls_what_we_override(self):
        users_src = inspect.getsource(auth_signup.models.res_users)
        self.assertIn("_action_reset_password(signup_type='signup')", users_src,
                      "auth_signup's `create` no longer sends through "
                      "`_action_reset_password`; our letter override is dead")
        self.assertIn("def action_reset_password", users_src)
        self.assertRegex(users_src, r"return self\._action_reset_password\(signup_type=\"reset\"\)")
        partner_src = inspect.getsource(auth_signup.models.res_partner)
        self.assertIn("self.sudo()._get_signup_url_for_action()", partner_src,
                      "`_get_signup_url` no longer goes through "
                      "`_get_signup_url_for_action`; the host override is dead")
        controller_src = inspect.getsource(auth_signup.controllers.main)
        self.assertIn("_get_signup_invitation_scope() == 'b2c'", controller_src,
                      "the controller no longer asks `_get_signup_invitation_scope`")
        Users = type(self.env["res.users"])
        self.assertTrue(Users._action_reset_password.__module__.startswith(
            "odoo.addons.myservice_api"), Users._action_reset_password.__module__)

    # ── 3. the letter ────────────────────────────────────────────────

    def test_iii_the_letter_is_the_tenants_and_the_link_is_on_this_host(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cadra.brand_short_name", "Probe Bank")
        ICP.set_param("cadra.brand_primary", "#123456")
        ICP.set_param("cadra.brand_primary_dark", "#0A2A4A")
        ICP.set_param("cadra.brand_logo", LOGO_SVG)
        company = self.env["res.company"].sudo().search([], limit=1)
        company.name = "Probe Bank Plc"
        # web.base.url deliberately WRONG, to prove the link does not come from it
        ICP.set_param("web.base.url", "http://somewhere-else.invalid")

        token = self._admin_token()
        email = self._email("letter")
        with self.mock_mail_gateway():
            r = self._post(token, "/api/v1/users",
                           {"name": "%s Letter" % self.marker, "email": email,
                            "roles": ["asset_user"]})
        self.assertEqual(r.status_code, 201, r.text)
        row = r.json()["data"]
        self.assertEqual(row["login"], email.lower())
        self.assertEqual([x["key"] for x in row["roles_direct"]], ["asset_user"])
        self.assertEqual(row["invitation"]["state"], "outstanding", row["invitation"])
        self.assertEqual(row["invitation"]["sends"], 1)
        self.assertEqual(row["invitation"]["sent_by"]["name"], self.admin.name)
        self.assertIsNotNone(row["invitation"]["expires_at"])

        mails = self._sent().filtered(lambda m: m.email_to == email)
        self.assertEqual(len(mails), 1, "one letter, to the person")
        mail = mails[0]
        body = mail.body_html
        self.assertIn("Probe Bank Plc", mail.subject)
        self.assertIn("You have been given access to the Probe Bank Plc asset register", body)
        self.assertIn("#123456", body, "the brand colour is the tenant's")
        self.assertIn(self.base_url() + "/api/v1/brand/logo", body, "the logo is a URL, not a data: URI")
        self.assertNotIn("data:image", body)
        self.assertNotRegex(self._prose(body), re.compile(r"odoo", re.I), "no Odoo anywhere in the letter")
        self.assertNotRegex(body, re.compile(r"password:\s*\S", re.I), "no secret in the body")
        links = re.findall(r'href="([^"]+/web/signup\?[^"]+)"', body)
        self.assertTrue(links, "the letter carries the sign-up link")
        for link in links:
            self.assertTrue(link.startswith(self.base_url() + "/web/signup?"),
                            "link %r is not on the request host %r" % (link, self.base_url()))
            self.assertNotIn("somewhere-else.invalid", link)
            self.assertIn("token=", link)
            self.assertIn("redirect=%2Fapp%2F", link)
        text = html2plaintext(body)
        self.assertIn("You have been given access", text)
        self.assertIn("/web/signup?", text, "the plain-text part carries the link on its own")

        # the logo route serves the image the letter points at
        r = self.url_open("/api/v1/brand/logo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", r.content)

    def test_iii_b_no_logo_means_a_wordmark_not_a_broken_image(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cadra.brand_logo", "")
        ICP.set_param("cadra.brand_short_name", "Wordmark Co")
        self.env["res.company"].sudo().search([], limit=1).name = "My Company"
        token = self._admin_token()
        email = self._email("wordmark")
        with self.mock_mail_gateway():
            r = self._post(token, "/api/v1/users",
                           {"name": "%s Wordmark" % self.marker, "email": email})
        self.assertEqual(r.status_code, 201, r.text)
        body = self._sent().filtered(lambda m: m.email_to == email).body_html
        self.assertNotIn("<img", body)
        self.assertIn("Wordmark Co", body, "a generic company name falls back to the brand short name")
        self.assertNotIn("My Company", body)
        self.assertEqual(self.url_open("/api/v1/brand/logo").status_code, 404)

    def test_iii_c_the_reset_letter_is_ours_too(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cadra.brand_short_name", "Probe Bank")
        self.env["res.company"].sudo().search([], limit=1).name = "Probe Bank Plc"
        with self.mock_mail_gateway():
            self.admin.with_context(create_user=False).action_reset_password()
        mail = self._sent().filtered(lambda m: m.email_to == self.admin.email)
        self.assertEqual(len(mail), 1)
        self.assertIn("reset your password", mail.subject)
        self.assertIn("A password reset was requested", mail.body_html)
        self.assertNotRegex(self._prose(mail.body_html), re.compile(r"odoo", re.I))
        self.assertIn("/web/reset_password?", mail.body_html)
        # a reset stamps no invitation
        self.assertFalse(self.admin.cadra_invitation_sent_at)

    # ── 4. creating with roles is granting roles ─────────────────────

    def test_iv_system_on_create_is_refused_and_nothing_is_created(self):
        token = self._admin_token()
        email = self._email("system")
        before = self.env["myservice.api.access.change"].sudo().search_count([])
        with self.mock_mail_gateway():
            r = self._post(token, "/api/v1/users",
                           {"name": "%s Sys" % self.marker, "email": email,
                            "roles": ["asset_user", "system"]})
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(r.json()["error"]["code"], "forbidden")
        self.assertIn(ONLY_THESE, r.json()["error"]["message"])
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        self.assertFalse(Users.search([("login", "=", email)]), "the account was created anyway")
        self.assertFalse(self._sent().filtered(lambda m: m.email_to == email), "a letter went out")
        self.assertEqual(self.env["myservice.api.access.change"].sudo().search_count([]), before,
                         "a refused create left access-record rows")

    # ── 5. the record ────────────────────────────────────────────────

    def test_v_the_record_names_the_person_who_clicked(self):
        token = self._admin_token()
        email = self._email("record")
        with self.mock_mail_gateway():
            r = self._post(token, "/api/v1/users",
                           {"name": "%s Rec" % self.marker, "email": email,
                            "roles": ["asset_user"], "send_invitation": False})
        self.assertEqual(r.status_code, 201, r.text)
        uid = r.json()["data"]["id"]
        rows = self.env["myservice.api.access.change"].sudo().search([("user_id", "=", uid)])
        self.assertTrue(rows, "a create wrote no access-record row")
        self.assertEqual(set(rows.mapped("source")), {"user_create"})
        self.assertEqual(set(rows.mapped("event")), {"granted"})
        self.assertIn(self.g_asset_user.id, rows.mapped("group_id").ids)
        self.assertEqual(set(rows.mapped("changed_by_id").ids), {self.admin.id},
                         "the actor is the token's user, not the route's")
        self.assertTrue(all(rows.mapped("attributable")))
        self.assertEqual(r.json()["data"]["invitation"]["state"], "never")

    # ── 6. deactivation, now ─────────────────────────────────────────

    def test_vi_deactivation_shuts_the_door_now_and_reactivation_opens_it(self):
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        pw = uuid.uuid4().hex
        person = Users.create({
            "name": "%s leaver" % self.marker, "login": "%s.leaver" % self.marker,
            "email": self._email("leaver"), "password": pw,
            "group_ids": [(6, 0, [self.g_user.id, self.g_system.id])],
        })
        live = self._login(person.login, pw).json()["data"]["access_token"]
        self.assertEqual(self._get(live, "/api/v1/auth/whoami").status_code, 200)

        admin = self._admin_token()
        r = self._post(admin, "/api/v1/users/%d/deactivate" % person.id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["data"]["active"])
        person.invalidate_recordset()
        self.assertFalse(person.active)

        r = self._get(live, "/api/v1/auth/whoami")
        self.assertEqual(r.status_code, 401, "a live token kept working after deactivation")
        self.assertEqual(r.json()["error"]["message"], "Account is disabled")
        r = self._login(person.login, pw)
        self.assertEqual(r.status_code, 401, r.text)

        r = self._post(admin, "/api/v1/users/%d/deactivate" % person.id)
        self.assertEqual(r.status_code, 409, "deactivating twice should be said, not swallowed")

        r = self._post(admin, "/api/v1/users/%d/reactivate" % person.id)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["data"]["active"])
        r = self._login(person.login, pw)
        self.assertEqual(r.status_code, 200, "reactivated, and still cannot sign in: %s" % r.text)

    def test_vi_b_self_and_credential_refused_in_words(self):
        admin = self._admin_token()
        r = self._post(admin, "/api/v1/users/%d/deactivate" % self.admin.id)
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("You cannot deactivate your own account", r.json()["error"]["message"])
        self.admin.invalidate_recordset()
        self.assertTrue(self.admin.active)
        cred_user = self.api_client.user_id
        r = self._post(admin, "/api/v1/users/%d/deactivate" % cred_user.id)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn(self.api_client.client_id, r.json()["error"]["message"])
        r = self._post(admin, "/api/v1/users/%d/invite" % cred_user.id)
        self.assertEqual(r.status_code, 400, r.text)

    def test_vi_c_invitation_is_cancelled_by_deactivation_and_a_signed_in_person_is_not_invited(self):
        admin = self._admin_token()
        email = self._email("cancel")
        with self.mock_mail_gateway():
            r = self._post(admin, "/api/v1/users",
                           {"name": "%s Cancel" % self.marker, "email": email})
            self.assertEqual(r.status_code, 201, r.text)
            uid = r.json()["data"]["id"]
            self.assertEqual(r.json()["data"]["invitation"]["state"], "outstanding")
            r = self._post(admin, "/api/v1/users/%d/invite" % uid)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["data"]["invitation"]["sends"], 2)
        self.assertEqual(len(self._sent().filtered(lambda m: m.email_to == email)), 2)
        r = self._post(admin, "/api/v1/users/%d/deactivate" % uid)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["invitation"]["state"], "cancelled",
                         "deactivation voids the token (auth_signup's write) and the row should say so")
        r = self._post(admin, "/api/v1/users/%d/invite" % uid)
        self.assertEqual(r.status_code, 409, "an invitation to a deactivated person")
        self._post(admin, "/api/v1/users/%d/reactivate" % uid)
        # somebody who has signed in is not "invited". `login_date` is
        # related to the newest `res.users.log` row on 19, so a write to it
        # is a no-op; the honest way to have signed in is to sign in.
        user = self.env["res.users"].sudo().browse(uid)
        pw = uuid.uuid4().hex
        user.write({"password": pw})
        self.assertEqual(self._login(user.login, pw).status_code, 200)
        user.invalidate_recordset()
        self.assertTrue(user.login_date)
        r = self._post(admin, "/api/v1/users/%d/invite" % uid)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("has signed in already", r.json()["error"]["message"])

    # ── 7. the label ─────────────────────────────────────────────────

    def test_vii_a_person_created_under_a_test_credential_is_a_fixture_on_their_partner(self):
        cred = self._cred_token()
        admin = self._admin_token()
        with self.mock_mail_gateway():
            r1 = self._post(cred, "/api/v1/users",
                            {"name": "%s Fixture" % self.marker,
                             "email": self._email("fixture"), "send_invitation": False})
            r2 = self._post(admin, "/api/v1/users",
                            {"name": "%s Real" % self.marker,
                             "email": self._email("real"), "send_invitation": False})
        self.assertEqual((r1.status_code, r2.status_code), (201, 201), (r1.text, r2.text))
        Users = self.env["res.users"].sudo()
        fixture = Users.browse(r1.json()["data"]["id"])
        real = Users.browse(r2.json()["data"]["id"])
        self.assertTrue(fixture.partner_id.is_test_fixture, "created by a test credential, unlabelled")
        self.assertTrue(fixture.is_test_fixture, "the label is readable on the user through _inherits")
        self.assertFalse(real.partner_id.is_test_fixture, "created by a person, labelled a fixture")

    # ── the body gate ────────────────────────────────────────────────

    def test_viii_a_stray_key_or_a_bad_value_writes_nothing(self):
        admin = self._admin_token()
        email = self._email("stray")
        with self.mock_mail_gateway():
            r = self._post(admin, "/api/v1/users",
                           {"name": "x", "email": email, "password": "hunter2"})
            self.assertEqual(r.status_code, 400, r.text)
            self.assertEqual(r.json()["error"]["details"]["rejected_fields"], ["password"])
            r = self._post(admin, "/api/v1/users", {"name": "x", "email": "not-an-address"})
            self.assertEqual(r.status_code, 400, r.text)
            self.assertEqual(r.json()["error"]["details"]["field"], "email")
            r = self._post(admin, "/api/v1/users/%d/deactivate" % self.admin.id, {"reason": "left"})
            self.assertEqual(r.status_code, 400, r.text)
            self.assertEqual(r.json()["error"]["details"]["rejected_fields"], ["reason"])
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        self.assertFalse(Users.search([("login", "in", [email, "not-an-address"])]))
        self.assertFalse(self._sent())

    # ── 8. the refusals the verification pass found untested ─────────

    def test_ix_the_last_human_administrator_cannot_be_deactivated_whatever_the_credentials_hold(self):
        """Bootstrap puts every admin-scoped credential's user in
        `base.group_system` too (report 42 §F.2). Counting them, the last
        PERSON could be deactivated and the tenant left to a credential
        that cannot open the back office."""
        system = self.env.ref("base.group_system")
        Clients = self.env["myservice.api.client"].sudo().with_context(active_test=False)
        credential_user_ids = set(Clients.search([]).mapped("user_id").ids)
        # bootstrap grants the group to every admin-scoped credential's user
        # (report 42 §F.2); `create_api_client` does not, so do what bootstrap
        # does — no request is bound here, so the guard does not judge it
        self.api_client.user_id.sudo().write({"group_ids": [(4, self.g_system.id)]})
        system.invalidate_recordset()
        humans = system.user_ids.filtered(lambda u: u.id not in credential_user_ids)
        self.assertIn(self.admin, humans)
        self.assertIn(self.api_client.user_id, system.user_ids)
        self.assertNotIn(self.api_client.user_id, humans)
        # everybody human but our admin steps aside, inside the transaction
        (humans - self.admin).write({"active": False})
        token = self._cred_token()
        r = self._post(token, "/api/v1/users/%d/deactivate" % self.admin.id)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("last active system administrator", r.json()["error"]["message"])
        self.assertEqual(r.json()["error"]["details"]["active_administrators"], 1)
        self.admin.invalidate_recordset()
        self.assertTrue(self.admin.active)
        # and with a second human administrator back, the same call is allowed
        self.env["res.users"].sudo().with_context(no_reset_password=True).create({
            "name": "%s second admin" % self.marker, "login": "%s.second" % self.marker,
            "group_ids": [(6, 0, [self.g_user.id, self.g_system.id])]})
        r = self._post(token, "/api/v1/users/%d/deactivate" % self.admin.id)
        self.assertEqual(r.status_code, 200, r.text)

    def test_x_a_deactivated_nominee_is_refused_on_move(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cadra.approval.required", "True")
        g_manager = self.env.ref("myservice_asset_register.group_asset_manager")
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        leaver = Users.create({
            "name": "%s leaver-manager" % self.marker, "login": "%s.leaver.mgr" % self.marker,
            "group_ids": [(6, 0, [self.g_user.id, g_manager.id])]})
        leaver.write({"active": False})
        locations = self.env["generic.location"].sudo().search([], limit=2)
        if len(locations) < 2:
            self.skipTest("this database has %d location(s); a move needs two" % len(locations))
        category = self.env["nrs.asset.category"].sudo().search([], limit=1)
        if not category:
            self.skipTest("this database has no asset category; an asset needs one")
        asset = self.env["nrs.asset"].sudo().create({
            "name": "%s mover" % self.marker, "category_id": category.id,
            "location_id": locations[0].id})
        token = self._admin_token()
        r = self._post(token, "/api/v1/assets/%d/move" % asset.id,
                       {"to_location_id": locations[1].id, "approver_id": leaver.id,
                        "reason": "probe"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("cannot be asked: their account is deactivated", r.json()["error"]["message"])
        self.assertEqual(r.json()["error"]["details"]["approver_id"], leaver.id)
        self.assertFalse(self.env["nrs.asset.change.request"].sudo().search(
            [("asset_id", "=", asset.id)]), "a request was raised on a refused nomination")

    def test_xi_an_anonymous_reset_does_not_take_its_host_from_the_request(self):
        """`/web/reset_password` is public. Under `proxy_mode` the request
        host is whatever `X-Forwarded-Host` says, and a proxy that does not
        overwrite it passes the client's value through — so an anonymous
        caller must never choose the host a victim's link points at."""
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("web.base.url", "http://the-real-tenant.invalid")
        self.admin.company_id.sudo().email = False
        page = self.url_open("/web/reset_password")
        self.assertEqual(page.status_code, 200)
        m = re.search(r'csrf_token:\s*"([^"]+)"', page.text) or \
            re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        self.assertTrue(m, "no csrf token on the reset page")
        with self.mock_mail_gateway():
            r = self.url_open("/web/reset_password", data={
                "csrf_token": m.group(1), "login": self.admin.login},
                headers={"X-Forwarded-Host": "attacker.invalid",
                         "X-Forwarded-Proto": "https"})
        self.assertEqual(r.status_code, 200, r.text[:300])
        mail = self._sent().filtered(lambda m_: m_.email_to == self.admin.email)
        self.assertEqual(len(mail), 1, "no reset letter went out")
        links = re.findall(r'href="([^"]+/web/reset_password\?[^"]+)"', mail.body_html)
        self.assertTrue(links)
        for link in links:
            self.assertNotIn("attacker.invalid", link)
            self.assertTrue(link.startswith("http://the-real-tenant.invalid/"), link)
        # the From is the recipient's own address when the company has none,
        # as core's reset path did — never the public user
        self.assertIn(self.admin.email, mail.email_from)
