"""Four causes, one body, four log lines.

Handoff 12 B. `POST /auth/token` answers `401 Invalid client credentials` to
a wrong secret, an unknown client, an archived client, and a client id in
the wrong case — `=` on a Postgres varchar is case-sensitive, so `Vendra`
and `vendra` are different clients. An hour was lost on staging to the
fourth of those.

The body deliberately does NOT change: naming which half of the pair is
wrong turns this endpoint into a client-id enumeration oracle. What changed
is that the `request_id` the response already carries is now lookup-able,
because the cause is written to the `cadra.auth` logger against it.

Needs `--workers=0`; see the note in test_pagination_cap.py.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestAuthFailureCauses(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Client = cls.env["myservice.api.client"]
        cls.live = Client.create({
            "name": "auth probe live", "client_id": "authprobe_live",
            "scopes": "assets:read"})
        cls.live_secret = cls.live.rotate_secret()
        cls.archived = Client.create({
            "name": "auth probe archived", "client_id": "authprobe_archived",
            "scopes": "assets:read"})
        cls.archived_secret = cls.archived.rotate_secret()
        cls.archived.active = False

        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

    def _post(self, client_id, client_secret):
        return self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": client_id,
                             "client_secret": client_secret}),
            headers={"Content-Type": "application/json"})

    def _shapes(self):
        return {
            "bad_secret": (self.live.client_id, "not-the-secret"),
            "no_such_client": ("authprobe_does_not_exist", "irrelevant"),
            "inactive": (self.archived.client_id, self.archived_secret),
            "case_mismatch": (self.live.client_id.upper(), self.live_secret),
        }

    def test_all_four_causes_answer_401(self):
        for name, (cid, secret) in self._shapes().items():
            with self.subTest(cause=name):
                r = self._post(cid, secret)
                self.assertEqual(r.status_code, 401)
                self.assertEqual(r.json()["error"]["code"], "unauthorized")

    def test_the_four_bodies_are_byte_identical_apart_from_the_request_id(self):
        """The only thing that may differ between them is the correlation
        id — which is the point: it is what makes the log lookup-able."""
        bodies = {}
        for name, (cid, secret) in self._shapes().items():
            body = self._post(cid, secret).json()
            body["error"]["details"].pop("http_status", None)
            body["error"].pop("request_id", None)
            bodies[name] = json.dumps(body, sort_keys=True)

        distinct = set(bodies.values())
        self.assertEqual(
            len(distinct), 1,
            "the four failure causes must be indistinguishable to the "
            "caller, or /auth/token becomes a client-id enumeration "
            "oracle. Got:\n" + "\n".join(
                "  %s -> %s" % (k, v) for k, v in sorted(bodies.items())))

    def test_each_cause_writes_its_own_named_log_line(self):
        expected = {
            "bad_secret": "outcome=bad_secret",
            "no_such_client": "outcome=no_such_client",
            "inactive": "outcome=inactive",
            "case_mismatch": "outcome=case_mismatch",
        }
        for name, (cid, secret) in self._shapes().items():
            with self.subTest(cause=name):
                with self.assertLogs("cadra.auth", level="WARNING") as captured:
                    self._post(cid, secret)
                line = "\n".join(captured.output)
                self.assertIn(expected[name], line)
                self.assertIn("request_id=", line)
                self.assertNotIn(self.live_secret, line,
                                 "the secret must never reach the log")
                if name == "case_mismatch":
                    self.assertIn("matched=%s" % self.live.client_id, line)

    def test_a_successful_mint_is_logged_too(self):
        """A log that records only failures cannot answer 'did this
        credential ever work'."""
        with self.assertLogs("cadra.auth", level="INFO") as captured:
            r = self._post(self.live.client_id, self.live_secret)
        self.assertEqual(r.status_code, 200)
        line = "\n".join(captured.output)
        self.assertIn("outcome=ok", line)
        self.assertIn("client_id=%s" % self.live.client_id, line)
        self.assertNotIn(self.live_secret, line)

    def test_a_client_id_cannot_forge_a_log_line(self):
        """The client id is caller-supplied text going into a log line. A
        newline in it would let an unauthenticated caller write whatever it
        liked under our own logger name."""
        from odoo.addons.myservice_api.controllers.utils import log_safe

        self.assertNotIn("\n", log_safe("vendra\noutcome=ok"))
        self.assertEqual(log_safe(None), "-")
        self.assertEqual(log_safe(""), "-")
        self.assertTrue(log_safe("x" * 500).endswith("...(truncated)"))
        self.assertLess(len(log_safe("x" * 500)), 200)

    def test_a_forged_client_id_does_not_reach_the_log_raw(self):
        with self.assertLogs("cadra.auth", level="WARNING") as captured:
            self._post("forged\noutcome=ok client_id=vendra", "x")
        for record in captured.records:
            self.assertNotIn("\n", record.getMessage())

    def test_a_client_id_that_is_not_a_string_still_answers_401(self):
        """`client_id` reaches the ORM as a domain value. A JSON object or
        a number there raises inside the diagnostic; the diagnostic runs in
        a savepoint precisely so the caller still gets its 401 rather than
        a 500 caused by us trying to explain the 401."""
        for weird in ({"$ne": None}, 12345, ["vendra"], True):
            with self.subTest(client_id=weird):
                r = self.url_open(
                    "/api/v1/auth/token",
                    data=json.dumps({"client_id": weird,
                                     "client_secret": "irrelevant"}),
                    headers={"Content-Type": "application/json"})
                self.assertIn(
                    r.status_code, (400, 401),
                    "a non-string client_id must be refused, not 500: %s"
                    % r.text[:300])
                self.assertIn(r.json()["error"]["code"],
                              ("unauthorized", "invalid_request"))
