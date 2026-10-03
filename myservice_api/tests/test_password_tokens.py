"""The first five minutes, from the inside — handoff 45 §2.

What the HTTP suite (`tests/test_password_tokens.py`) cannot reach without
waiting days or holding a session:

* a token past its expiry reads `expired`, not `invalid` — minted here with
  core's own `hash_sign` and an expiry in the past;
* a newer letter supersedes an older one: the invitation's token reads
  `cancelled` once a reset was requested;
* the letter's link is the APP's page (`/app/accept-invite?token=…`), with
  only the token in it;
* the back office: a signed-in non-administrator who opens `/odoo` is signed
  out of Odoo and sent to `/app/`; an administrator is not; an anonymous
  visitor is sent to `/app/`; a non-administrator signing in on `/web/login`
  leaves with no Odoo session; and the plumbing the app and the cluster rely
  on — `/web/login` (the probes), `/web/health`, `/report/barcode` (the QR on
  a printed label), `/web/assets` — answers as before.

Run it (`--workers=0` is not optional for an HttpCase; read `of N tests`):

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098 \\
      --test-enable --test-tags /myservice_api:TestPasswordTokens --workers=0
"""
import base64
import datetime
import json
import uuid

from odoo import tools
from odoo.tests import tagged

from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase
from odoo.addons.myservice_api.controllers.v1_signup import token_status
from odoo.addons.myservice_api.models.invitation import app_password_path


@tagged("post_install", "-at_install")
class TestPasswordTokens(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marker = "h45probe%s" % uuid.uuid4().hex[:8]
        Users = cls.env["res.users"].sudo().with_context(no_reset_password=True)
        cls.password = uuid.uuid4().hex
        cls.officer = Users.create({
            "name": "%s officer" % cls.marker,
            "login": "%s.officer@example.invalid" % cls.marker,
            "email": "%s.officer@example.invalid" % cls.marker,
            "password": cls.password,
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("myservice_asset_register.group_asset_user").id])],
        })
        cls.admin_password = uuid.uuid4().hex
        cls.sysadmin = Users.create({
            "name": "%s admin" % cls.marker,
            "login": "%s.admin@example.invalid" % cls.marker,
            "password": cls.admin_password,
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("base.group_system").id])],
        })

    def _status(self, token):
        return token_status(self.env, token)["state"]

    # ── the token's states ─────────────────────────────────────────────

    def test_a_token_past_its_expiry_is_expired_not_invalid(self):
        partner = self.officer.partner_id.sudo()
        partner.signup_prepare(signup_type="signup")
        payload = [partner.id, partner.user_ids.ids, partner._get_login_date(),
                   "signup"]
        live = tools.hash_sign(self.env(su=True), "signup", payload,
                               expiration_hours=1)
        self.assertEqual(self._status(live), "outstanding")
        dead = tools.hash_sign(self.env(su=True), "signup", payload,
                               expiration=datetime.datetime.now()
                               - datetime.timedelta(hours=1))
        self.assertEqual(self._status(dead), "expired")
        # Same payload, signature broken: never valid.
        raw = bytearray(base64.urlsafe_b64decode(dead + "==="))
        raw[12] ^= 0xFF
        forged = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
        self.assertEqual(self._status(forged), "invalid")

    def test_a_newer_letter_cancels_the_older_one(self):
        partner = self.officer.partner_id.sudo()
        partner.signup_prepare(signup_type="signup")
        invite = partner._generate_signup_token()
        self.assertEqual(self._status(invite), "outstanding")
        partner.signup_prepare(signup_type="reset")
        reset = partner._generate_signup_token()
        self.assertEqual(self._status(invite), "cancelled")
        status = token_status(self.env, reset)
        self.assertEqual((status["state"], status["kind"]), ("outstanding", "reset"))

    def test_a_deactivated_account_cancels_its_link(self):
        partner = self.officer.partner_id.sudo()
        partner.signup_prepare(signup_type="signup")
        token = partner._generate_signup_token()
        self.officer.sudo().write({"active": False})
        try:
            self.assertEqual(self._status(token), "cancelled")
        finally:
            self.officer.sudo().write({"active": True})

    def test_the_letter_links_to_the_app_with_only_the_token(self):
        self.assertEqual(
            app_password_path("/web/signup?db=x&signup_email=a%40b&token=T0k-_1&redirect=%2Fapp%2F"),
            "/app/accept-invite?token=T0k-_1")
        self.assertEqual(app_password_path("/web/reset_password?db=x&token=abc"),
                         "/app/reset-password?token=abc")
        self.assertEqual(app_password_path("/web/login?db=x"), "/web/login?db=x")
        self.officer.partner_id.sudo().signup_prepare(signup_type="signup")
        url = self.officer.partner_id.sudo()._get_signup_url_for_action(
            url="/app/")[self.officer.partner_id.id]
        self.assertIn("/app/accept-invite?token=", url)
        self.assertNotIn("/web/", url)
        self.assertNotIn("signup_email", url)

    # ── the back office ────────────────────────────────────────────────

    def _get(self, path):
        return self.url_open(path, allow_redirects=False)

    def _location(self, r):
        return r.headers.get("Location", "")

    def test_an_anonymous_visitor_to_the_back_office_is_sent_to_the_app(self):
        for path in ("/odoo", "/web", "/odoo/action-base.action_res_users"):
            r = self._get(path)
            self.assertIn(r.status_code, (301, 302, 303), path)
            self.assertTrue(self._location(r).endswith("/app/"), (path, self._location(r)))

    def test_a_non_administrator_is_signed_out_of_odoo_and_sent_to_the_app(self):
        self.authenticate(self.officer.login, self.password)
        for path in ("/odoo", "/odoo/action-base.action_res_users", "/web"):
            self.authenticate(self.officer.login, self.password)
            r = self._get(path)
            self.assertTrue(self._location(r).endswith("/app/"), (path, r.status_code))
        # The session is gone: a JSON-RPC call with that cookie is anonymous.
        r = self.url_open("/web/session/get_session_info", data=json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"})
        self.assertFalse((r.json().get("result") or {}).get("uid"), r.text[:300])

    def test_an_administrator_keeps_the_back_office(self):
        self.authenticate(self.sysadmin.login, self.admin_password)
        r = self._get("/odoo")
        self.assertEqual(r.status_code, 200, self._location(r))
        self.assertIn("webclient", r.text[:20000].lower())

    def test_a_non_administrator_signing_in_on_odoos_page_leaves_with_no_session(self):
        page = self.url_open("/web/login")
        self.assertEqual(page.status_code, 200)
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        r = self.url_open("/web/login", data={
            "login": self.officer.login, "password": self.password,
            "csrf_token": csrf}, allow_redirects=False)
        self.assertTrue(self._location(r).endswith("/app/"), (r.status_code, self._location(r)))
        r = self.url_open("/web/session/get_session_info", data=json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"})
        self.assertFalse((r.json().get("result") or {}).get("uid"), r.text[:300])

    def _rpc(self, path, params=None):
        return self.url_open(path, data=json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": params or {}}),
            headers={"Content-Type": "application/json"})

    def test_a_non_administrator_holds_no_usable_odoo_session_by_any_door(self):
        """The verification pass's three doors: JSON-RPC sign-in, the ORM
        over RPC with that cookie, and an `auth='user'` page (`/my`)."""
        r = self._rpc("/web/session/authenticate", {
            "db": self.env.cr.dbname, "login": self.officer.login,
            "password": self.password})
        self.assertEqual((r.json().get("result") or {}).get("uid"), self.officer.id,
                         "the sign-in itself still answers — the session is "
                         "what is refused")
        r = self._rpc("/web/dataset/call_kw", {
            "model": "res.users", "method": "search_count", "args": [[]],
            "kwargs": {}})
        self.assertIn("error", r.json(), r.text[:300])
        self.assertIn("Session", str(r.json()["error"]), r.text[:300])
        info = self._rpc("/web/session/get_session_info").json().get("result") or {}
        self.assertFalse(info.get("uid"), "the session survived the refusal")
        # An http `auth='user'` page: sent to the app, not to Odoo's login.
        self.authenticate(self.officer.login, self.password)
        r = self._get("/my")
        self.assertTrue(self._location(r).endswith("/app/"), (r.status_code, self._location(r)))
        # And the back-office station's own JSON route, as a tagger would.
        self.authenticate(self.officer.login, self.password)
        r = self._rpc("/barcode/recent_tags")
        self.assertIn("error", r.json(), r.text[:300])

    def test_an_administrators_session_still_reaches_everything(self):
        self.authenticate(self.sysadmin.login, self.admin_password)
        r = self._rpc("/web/dataset/call_kw", {
            "model": "res.users", "method": "search_count", "args": [[]],
            "kwargs": {}})
        self.assertIsInstance(r.json().get("result"), int, r.text[:300])

    def test_posting_to_the_old_letter_pages_reaches_no_odoo_form(self):
        """`POST /web/reset_password` answered Odoo's page with "No account
        found for this login" (verification pass) — the same-answer rule,
        undone by a form nobody was meant to see."""
        page = self.url_open("/web/login")
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        r = self.url_open("/web/reset_password", data={
            "login": "nobody-%s@example.invalid" % self.marker,
            "csrf_token": csrf}, allow_redirects=False)
        self.assertTrue(self._location(r).endswith("/app/forgot-password"),
                        (r.status_code, r.text[:200]))
        r = self.url_open("/web/signup", data={"token": "abc", "csrf_token": csrf},
                          allow_redirects=False)
        self.assertTrue(self._location(r).endswith("/app/accept-invite?token=abc"),
                        (r.status_code, r.text[:200]))

    def test_the_plumbing_is_untouched(self):
        self.assertEqual(self._get("/web/login").status_code, 200)
        self.assertEqual(self._get("/web/health").status_code, 200)
        r = self._get("/report/barcode?barcode_type=QR&value=NRS-TEST-1&width=120&height=120")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers.get("Content-Type", "").startswith("image/"), r.headers)
