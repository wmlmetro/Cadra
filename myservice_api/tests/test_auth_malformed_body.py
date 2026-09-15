"""A malformed body reaches the auth surface as JSON, never as an HTML 500.

Handoff 14 Part A. `/auth/login`, `/auth/refresh` and `/auth/revoke` are
three of the nine routes that predate `@cadra_route`, so nothing under them
turns an exception into the PRD envelope. Every one of them took a value
straight out of an UNAUTHENTICATED JSON body and used it as a string:

  * `login`  -> `.strip()` on the line it is read
  * `password` -> Odoo's password verifier
  * `turnstile_token` -> posted to Cloudflare as form data
  * `refresh_token` -> `hashlib.sha256(raw.encode("utf-8"))`

A JSON object, a number or a list in any of them raised before a single
check ran, and the caller got a werkzeug HTML page with no `request_id` and
no error code. Handoff 12 found and fixed exactly this on `/auth/token`.

These tests assert the ENVELOPE, not the status. An HTML page served with a
200 would pass a status check and tell us nothing — so every assertion here
goes through `_envelope()`, which insists the response parses as JSON and
carries the PRD shape (`error.code` / `error.message` / `error.request_id`
on the failure side, `data` + `meta` on the success side).

Needs `--workers=0`; see the note in test_pagination_cap.py.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


# Values a JSON body can legally carry where our code expects a string. Each
# one is a shape a real integration sends by accident (a number for an id, a
# list from a form library) or on purpose (`{"$ne": null}`, the first thing
# anybody types at an endpoint to see whether it interpolates).
NON_STRINGS = ({"$ne": None}, 12345, ["vendra"], 3.5, True)


@tagged("post_install", "-at_install")
class TestAuthMalformedBody(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `/auth/refresh` reads the tenant's signing key before it looks at
        # the token, so on a tenant that was never provisioned every case
        # here would answer `server_misconfigured` and the file would prove
        # nothing. Installing a module is not provisioning a tenant — the
        # standing ruling; the same guard as test_auth_failure_causes.
        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

    def _post(self, path, body):
        return self.url_open(
            path, data=json.dumps(body),
            headers={"Content-Type": "application/json"})

    def _envelope(self, response, where):
        """Return the parsed envelope, or fail saying what came back instead.

        The whole point of the fix is the SHAPE of the answer, so this is
        deliberately stricter than "not a 500": it refuses an HTML body, it
        refuses a bare JSON value, and it refuses a dict that is neither
        half of the PRD envelope.
        """
        ctype = (response.headers.get("Content-Type") or "").lower()
        self.assertIn(
            "application/json", ctype,
            "%s answered Content-Type %r — an HTML error page is exactly "
            "what this route must no longer produce. First 300 bytes:\n%s"
            % (where, ctype, response.text[:300]))
        try:
            body = response.json()
        except ValueError:
            self.fail("%s did not return JSON. First 300 bytes:\n%s"
                      % (where, response.text[:300]))
        self.assertIsInstance(body, dict, "%s: envelope is not an object" % where)
        self.assertTrue(
            ("error" in body) != ("data" in body),
            "%s: the envelope carries exactly one of `error` / `data`, got "
            "keys %s" % (where, sorted(body)))
        if "error" in body:
            error = body["error"]
            self.assertIsInstance(error, dict, "%s: `error` is not an object" % where)
            for key in ("code", "message", "request_id"):
                self.assertIn(key, error, "%s: envelope has no error.%s" % (where, key))
            self.assertIn("http_status", error.get("details") or {},
                          "%s: envelope has no error.details.http_status" % where)
        else:
            self.assertIn("meta", body, "%s: success envelope has no `meta`" % where)
            self.assertIn("request_id", body["meta"])
        return body

    # ── the defect itself: the answer must be an envelope ────────────

    def test_no_auth_route_answers_html_to_a_non_string(self):
        """The regression this file exists for. Every field on every one of
        the three routes, against every non-string a JSON body can hold."""
        cases = [
            ("/api/v1/auth/login", "login"),
            ("/api/v1/auth/login", "username"),
            ("/api/v1/auth/login", "password"),
            ("/api/v1/auth/login", "turnstile_token"),
            ("/api/v1/auth/refresh", "refresh_token"),
            ("/api/v1/auth/revoke", "refresh_token"),
        ]
        for path, field in cases:
            for weird in NON_STRINGS:
                with self.subTest(path=path, field=field, value=weird):
                    body = {"login": "someone@example.com",
                            "password": "irrelevant"} if "login" in path else {}
                    body[field] = weird
                    r = self._post(path, body)
                    self._envelope(r, "%s with %s=%r" % (path, field, weird))
                    self.assertNotEqual(
                        r.status_code, 500,
                        "%s 500'd on %s=%r" % (path, field, weird))

    # ── and the answer it gives ──────────────────────────────────────

    def test_a_non_string_is_refused_as_invalid_request(self):
        """`invalid_request` — not a new code, and not `validation_failed`:
        the body could not be read as a request at all."""
        cases = [
            ("/api/v1/auth/login", {"login": {"$ne": None}, "password": "x"}),
            ("/api/v1/auth/login", {"username": 12345, "password": "x"}),
            ("/api/v1/auth/login", {"login": "x", "password": ["y"]}),
            ("/api/v1/auth/login",
             {"login": "x", "password": "y", "turnstile_token": {"a": 1}}),
            ("/api/v1/auth/refresh", {"refresh_token": {"$ne": None}}),
            ("/api/v1/auth/refresh", {"refresh_token": 12345}),
            ("/api/v1/auth/revoke", {"refresh_token": {"$ne": None}}),
            ("/api/v1/auth/revoke", {"refresh_token": ["a"]}),
        ]
        for path, payload in cases:
            with self.subTest(path=path, payload=payload):
                r = self._post(path, payload)
                envelope = self._envelope(r, "%s %r" % (path, payload))
                self.assertEqual(r.status_code, 400)
                self.assertEqual(envelope["error"]["code"], "invalid_request")
                self.assertEqual(
                    envelope["error"]["details"]["http_status"], 400)

    def test_the_username_alias_is_type_checked_like_login(self):
        """`login` falls back to `username`, so the alias is a second door
        into the same `.strip()` and has to be shut with it."""
        r = self._post("/api/v1/auth/login",
                       {"username": {"$ne": None}, "password": "x"})
        envelope = self._envelope(r, "/auth/login via username")
        self.assertEqual(envelope["error"]["code"], "invalid_request")

    # ── nothing well-formed changed ──────────────────────────────────

    def test_revoke_still_answers_200_revoked_true(self):
        """The documented contract: any well-formed body gets
        `200 {"revoked": true}`, whether or not the token ever existed —
        the response must not reveal that."""
        for token in ("a-token-that-was-never-issued", "x" * 200):
            with self.subTest(token=token[:20]):
                r = self._post("/api/v1/auth/revoke", {"refresh_token": token})
                envelope = self._envelope(r, "/auth/revoke well-formed")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(envelope["data"], {"revoked": True})

    def test_a_missing_field_still_reads_as_missing_not_as_mistyped(self):
        """An absent field is not a non-string. The type check must not
        swallow the `is required` message an integrator is reading."""
        expected = {
            "/api/v1/auth/login": "required",
            "/api/v1/auth/refresh": "required",
            "/api/v1/auth/revoke": "required",
        }
        for path, word in expected.items():
            with self.subTest(path=path):
                r = self._post(path, {})
                envelope = self._envelope(r, "%s with an empty body" % path)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(envelope["error"]["code"], "invalid_request")
                self.assertIn(word, envelope["error"]["message"])

    def test_bad_credentials_still_answer_401_through_the_envelope(self):
        """The type check sits in front of authentication; it must not have
        moved a wrong password from 401 onto 400."""
        r = self._post("/api/v1/auth/login",
                       {"login": "nobody@example.invalid", "password": "wrong"})
        envelope = self._envelope(r, "/auth/login with bad credentials")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(envelope["error"]["code"], "unauthorized")

    def test_an_unknown_refresh_token_still_answers_401(self):
        r = self._post("/api/v1/auth/refresh",
                       {"refresh_token": "not-a-token-we-ever-issued"})
        envelope = self._envelope(r, "/auth/refresh with an unknown token")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(envelope["error"]["code"], "unauthorized")
