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

    # ── handoff 13 B2 · the source IP, on failures ───────────────────

    def test_every_failure_line_carries_a_source_ip(self):
        """The field that separates "somebody typed the secret wrong" from
        "somebody is working through a list".

        Not a new category of data: it arrives on the same unauthenticated
        request as the client id already logged here, and `last_used_ip`
        records it on success. Until now the caller who SUCCEEDED was
        identified and the one who FAILED was anonymous, which is backwards.
        """
        for name, (cid, secret) in self._shapes().items():
            with self.subTest(cause=name):
                with self.assertLogs("cadra.auth", level="WARNING") as captured:
                    self._post(cid, secret)
                line = "\n".join(captured.output)
                self.assertIn("ip=", line)
                self.assertIn("ip_source=", line)

    def test_the_success_line_does_not_carry_one(self):
        """Failures only, per the ruling. The success path records the
        address on the client record instead."""
        with self.assertLogs("cadra.auth", level="INFO") as captured:
            self._post(self.live.client_id, self.live_secret)
        ok_lines = [line for line in captured.output if "outcome=ok" in line]
        self.assertTrue(ok_lines)
        for line in ok_lines:
            self.assertNotIn("ip=", line)

    def test_the_address_is_resolved_the_same_way_with_or_without_proxyfix(self):
        """Odoo 19 runs ProxyFix only when `X-Forwarded-Host` is also
        present (`odoo/http.py`, `Application.__call__`), and the dev
        stack's nginx does not send it — which is why `last_used_ip` reads
        the proxy container's address on every client row in every local
        tenant. So we do not depend on ProxyFix: the RIGHT-MOST
        `X-Forwarded-For` entry is the one our own nearest proxy appended,
        and everything to its left is caller-supplied and forgeable.
        """
        with self.assertLogs("cadra.auth", level="WARNING") as captured:
            self.url_open(
                "/api/v1/auth/token",
                data=json.dumps({"client_id": self.live.client_id,
                                 "client_secret": "wrong"}),
                headers={"Content-Type": "application/json",
                         "X-Forwarded-For": "10.9.9.9, 203.0.113.7"})
        line = "\n".join(captured.output)
        self.assertIn("ip=203.0.113.7", line,
                      "the right-most entry is the trusted one")
        self.assertNotIn("10.9.9.9", line,
                         "a caller-supplied left-hand entry must not be "
                         "logged as if we had observed it")
        self.assertIn("ip_source=xff+1", line,
                      "one further hop was declared, so the value is the "
                      "nearest proxy and not necessarily the caller")

    def test_an_infrastructure_address_says_that_it_is_one(self):
        """"A field that always reads the same is worse than no field."
        When the value is the ingress rather than the caller, the line says
        so rather than presenting `10.244.1.7` as an identification."""
        with self.assertLogs("cadra.auth", level="WARNING") as captured:
            self.url_open(
                "/api/v1/auth/token",
                data=json.dumps({"client_id": self.live.client_id,
                                 "client_secret": "wrong"}),
                headers={"Content-Type": "application/json",
                         "X-Forwarded-For": "10.244.1.7"})
        self.assertIn("ip_source=xff,infra", "\n".join(captured.output))

    def test_a_forged_address_cannot_append_a_field_to_the_log_line(self):
        """`X-Forwarded-For` is caller-supplied on an unauthenticated
        request, exactly like the client id — and `ip=` is the LAST field
        on the line, which is the shape a forger reaches for.

        A newline cannot get here (`requests`, and every compliant client,
        refuses to send one) but a SPACE is legal in a header value, so
        `1.2.3.4 outcome=ok` would otherwise write a second field under our
        own logger name. An IP field may contain an IP or nothing: the
        value is printed only after `ipaddress` has parsed it.
        """
        with self.assertLogs("cadra.auth", level="WARNING") as captured:
            self.url_open(
                "/api/v1/auth/token",
                data=json.dumps({"client_id": self.live.client_id,
                                 "client_secret": "wrong"}),
                headers={"Content-Type": "application/json",
                         "X-Forwarded-For": "1.2.3.4 outcome=ok"})
        line = "\n".join(captured.output)
        self.assertIn("ip=? ip_source=xff,unparsable", line)
        self.assertNotIn("outcome=ok", line,
                         "an unauthenticated caller must not be able to "
                         "write a field into our log")

    def test_a_non_address_in_the_header_is_reported_not_repeated(self):
        with self.assertLogs("cadra.auth", level="WARNING") as captured:
            self.url_open(
                "/api/v1/auth/token",
                data=json.dumps({"client_id": self.live.client_id,
                                 "client_secret": "wrong"}),
                headers={"Content-Type": "application/json",
                         "X-Forwarded-For": "unknown"})
        line = "\n".join(captured.output)
        self.assertIn("ip=?", line)
        self.assertNotIn("unknown", line)

    def test_the_success_path_records_the_caller_and_not_the_proxy(self):
        """`last_used_ip` is the only record of where a credential is used
        from. It was `request.httprequest.remote_addr`, which is the proxy
        wherever ProxyFix does not run."""
        self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.live.client_id,
                             "client_secret": self.live_secret}),
            headers={"Content-Type": "application/json",
                     "X-Forwarded-For": "198.51.100.22"})
        self.live.invalidate_recordset(["last_used_ip"])
        self.assertEqual(self.live.last_used_ip, "198.51.100.22")
