"""A missing credential must refuse, not admit.

`/myservice/workflow/callback` is `auth='public'`, `csrf=False`, and it is the
route that APPROVES and REJECTS requests. Its token guard used to read
`if config.callback_token:` — so on a tenant that had never set one, the guard
did not run and every caller was admitted. An absent credential is the one
case where "no check" and "check passed" are the same code path, which is why
these tests exist as `HttpCase` rather than as unit tests of a helper: the
question is what an UNAUTHENTICATED caller gets over real HTTP, and no
in-registry call can answer it.

The refusal is 503 with the same opaque body an unconfigured tenant already
gets, not 401 — the caller may have sent a perfectly good token and the fault
is ours — and the sentence naming `workflow.config.callback_token` goes to the
log at ERROR, where an operator can act on it and an unauthenticated caller
cannot read it.

The second half is the query parameter. `?token=` is accepted for ONE more
release, is still COMPARED (a wrong one is still a 401), and logs a WARNING
naming the caller every time it is the thing that supplied the credential, so
the deprecation has a visible end date rather than an assumed one.

Needs `--workers=0`: `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the committed `workers = 2` every test in the class errors
in setUpClass and the run reports "0 failed".

Run with:
    odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_workflow \\
         --stop-after-init --test-enable --test-tags /myservice_workflow \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase

CALLBACK_URL = "/myservice/workflow/callback"
TOKEN = "h17-callback-shared-secret"
# The controller logs under its own module name; assertLogs needs it exactly.
LOGGER = "odoo.addons.myservice_workflow.controllers.callback"


@tagged("post_install", "-at_install")
class TestCallbackAuth(CadraHttpCase):

    def setUp(self):
        super().setUp()
        Config = self.env["workflow.config"]
        # `get_active_config()` searches `active=True, purpose=workspace`
        # with `limit=1` and no explicit order, so an existing row would win
        # over ours on a tenant that already has one. Stand ours up alone.
        Config.search([("purpose", "=", "workspace"),
                       ("active", "=", True)]).write({"active": False})
        self.config = Config.create({
            "name": "handoff 17 callback auth probe",
            "purpose": "workspace",
            "adapter_type": "stub",
            "callback_enabled": True,
            "callback_token": TOKEN,
            # Deliberately no `approved_stage_id` and no `trigger_stage_ids`:
            # this file is about the door, not the stage mapping behind it,
            # and a trigger stage would make `create()` below dispatch
            # outbound as a side effect.
        })
        # An explicit, unique reference: the controller resolves the request
        # by `name`, and a sequence-generated one shared with any other row
        # would make the lookup the thing under test.
        self.req = self.env["request.request"].create({
            "name": "H17-CB-%s" % uuid.uuid4().hex[:8]})
        self.assertEqual(self.req.workflow_status, "not_sent")
        self.env.flush_all()

    # ── helpers ──────────────────────────────────────────────────────────

    def _post(self, header_token=None, query_token=None, outcome="approved"):
        url = CALLBACK_URL
        if query_token is not None:
            url = "%s?token=%s" % (CALLBACK_URL, query_token)
        headers = {"Content-Type": "application/json"}
        if header_token is not None:
            headers["X-Callback-Token"] = header_token
        return self.url_open(
            url,
            data=json.dumps({
                "reference": self.req.name,
                "workspace_ref": "WF-H17-0001",
                "outcome": outcome,
                "comment": "handoff 17 probe",
            }),
            headers=headers,
        )

    def _post_form(self, query_token=None, form_token=None, outcome="approved"):
        """The FORM-ENCODED path, which is the one that leaked.

        `type='http'` merges the query string and the form fields into
        `kwargs`, and the handler used to assign `data = kwargs` wholesale —
        so the credential arrived inside the payload dict and the INFO line
        that logs that dict wrote the tenant's live shared secret into our
        own log. Sending `application/json` never reaches that branch, which
        is why the JSON tests could not see it.
        """
        url = CALLBACK_URL
        if query_token is not None:
            url = "%s?token=%s" % (CALLBACK_URL, query_token)
        payload = {
            "reference": self.req.name,
            "workspace_ref": "WF-H17-FORM",
            "outcome": outcome,
            "comment": "handoff 17 form probe",
        }
        if form_token is not None:
            payload["token"] = form_token
        return self.url_open(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def _status_now(self):
        """The stored value, not whatever the test env cached before the
        request ran. The HTTP handler writes on its own cursor into the same
        transaction; without this the assertion reads a stale cache and
        passes for the wrong reason."""
        self.env.invalidate_all()
        return self.req.workflow_status

    # ── A1 — a missing token refuses ─────────────────────────────────────

    def test_a_tenant_with_no_callback_token_cannot_be_made_to_approve(self):
        """The regression this file exists for. No token configured used to
        mean no authentication at all on an approval endpoint."""
        self.config.callback_token = False
        self.env.flush_all()

        response = self._post()

        self.assertEqual(
            response.status_code, 503,
            "a tenant with no callback_token must refuse the callback")
        self.assertEqual(
            response.json(),
            {"error": "Workflow integration is not available"},
            "the body must not name our internal configuration to an "
            "unauthenticated caller")
        self.assertEqual(
            self._status_now(), "not_sent",
            "the request was APPROVED by an unauthenticated caller")

    def test_the_missing_token_refusal_is_logged_at_error_naming_the_field(self):
        """A tenant hitting this needs to find out from a log rather than
        from an approval nobody authorised — and the log line has to say
        which field to set, on which database."""
        self.config.callback_token = False
        self.env.flush_all()

        with self.assertLogs(LOGGER, level="ERROR") as captured:
            self._post()

        line = "\n".join(captured.output)
        self.assertIn("callback_token", line)
        self.assertIn(self.env.cr.dbname, line)
        self.assertIn("REFUSED", line)

    def test_a_missing_token_refuses_even_when_the_caller_supplies_one(self):
        """It is not "no token sent" that refuses, it is "no token
        configured". A caller holding a perfectly good secret from another
        tenant must not be admitted by a tenant that checks nothing."""
        self.config.callback_token = False
        self.env.flush_all()

        response = self._post(header_token=TOKEN)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self._status_now(), "not_sent")

    # ── the header, which is the supported channel ───────────────────────

    def test_a_correct_token_in_the_header_still_applies_the_outcome(self):
        response = self._post(header_token=TOKEN)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self._status_now(), "approved")

    def test_a_wrong_token_in_the_header_is_401(self):
        response = self._post(header_token=TOKEN + "-wrong")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Unauthorized"})
        self.assertEqual(self._status_now(), "not_sent")

    def test_no_token_at_all_is_401_when_one_is_configured(self):
        response = self._post()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self._status_now(), "not_sent")

    # ── A2 — the query parameter, deprecated but still compared ──────────

    def test_a_correct_token_in_the_query_string_still_works_and_warns(self):
        """One more release. It keeps working — breaking WorkSpace to fix a
        logging exposure would be its own outage — but every use is on the
        record, with the caller named, so the deprecation has an end date."""
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            response = self._post(query_token=TOKEN)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._status_now(), "approved")

        line = "\n".join(captured.output)
        self.assertIn("QUERY STRING", line)
        self.assertIn("deprecated", line.lower())
        self.assertIn("ip=", line)
        self.assertNotIn(TOKEN, line,
                         "the secret must never reach the log")

    def test_a_wrong_token_in_the_query_string_is_401(self):
        """Accepting the channel is not accepting the value."""
        response = self._post(query_token=TOKEN + "-wrong")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Unauthorized"})
        self.assertEqual(self._status_now(), "not_sent")

    # ── the credential must never reach OUR log either ───────────────────

    def test_the_secret_never_reaches_the_log_on_the_form_encoded_path(self):
        """The path that leaked, captured at the level that leaked.

        The earlier query-string test asserted `assertNotIn(TOKEN, ...)` and
        was green for two reasons that had nothing to do with the code being
        right: it posted `application/json`, so it never took the
        form-encoded branch where `data = kwargs`, and it captured at
        WARNING, so the INFO line carrying the payload was invisible to it.
        A test that cannot see the defect cannot witness the fix.

        This one takes the form branch AND captures at INFO, so the assertion
        is over the exact record that used to carry the secret.
        """
        with self.assertLogs(LOGGER, level="INFO") as captured:
            response = self._post_form(form_token=TOKEN)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._status_now(), "approved")

        line = "\n".join(captured.output)
        self.assertIn("Workflow callback received", line,
                      "the INFO payload line must still be emitted — this "
                      "test is worthless if the record it inspects is gone")
        self.assertNotIn(TOKEN, line,
                         "the tenant's live shared secret reached the Odoo "
                         "log. A credential is authentication, not payload; "
                         "it must be stripped before `data` is built.")
        self.assertNotIn("'token'", line)

    def test_the_secret_never_reaches_the_log_from_the_query_string_either(self):
        """Same defect, other channel. A query-string token also lands in
        `kwargs` on a `type='http'` route, so a form-encoded body with
        `?token=` in the URL carried it into the payload too."""
        with self.assertLogs(LOGGER, level="INFO") as captured:
            response = self._post_form(query_token=TOKEN)

        self.assertEqual(response.status_code, 200, response.text)
        line = "\n".join(captured.output)
        self.assertIn("Workflow callback received", line)
        self.assertNotIn(TOKEN, line)

    def test_a_form_field_token_is_named_as_a_form_field_not_as_a_query_string(self):
        """The deprecation log is a migration list, so it has to be right
        about which channel a caller is on. Reading `kwargs['token']` cannot
        distinguish a query parameter from a form field — both are merged —
        and calling a form field a QUERY STRING puts a caller on the
        access-log-exposure list who is not on it."""
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            self._post_form(form_token=TOKEN)

        line = "\n".join(captured.output)
        self.assertIn("FORM FIELD", line)
        self.assertNotIn("QUERY STRING", line)
        self.assertIn("ip=", line)

    def test_a_wrong_query_token_also_warns_that_the_channel_is_deprecated(self):
        """The warning fires when the query string is what SUPPLIED the
        credential, match or no match — a caller still using the old channel
        needs to appear in the log whether or not it also has the wrong
        secret."""
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            self._post(query_token=TOKEN + "-wrong")

        self.assertIn("QUERY STRING", "\n".join(captured.output))

    def test_the_header_wins_and_a_header_only_call_does_not_warn(self):
        """A caller that has already migrated must not appear in the
        deprecation log, or the log stops being a migration list."""
        with self.assertLogs(LOGGER, level="INFO") as captured:
            response = self._post(header_token=TOKEN)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("QUERY STRING", "\n".join(captured.output))

    # ── the comparison itself ────────────────────────────────────────────

    def test_the_token_comparison_is_constant_time_and_survives_non_ascii(self):
        """`hmac.compare_digest` raises TypeError on non-ASCII `str`, and
        `provided` is attacker-controlled text — so that would be a
        TypeError an unauthenticated caller could trigger at will."""
        from odoo.addons.myservice_workflow.controllers.callback import (
            WorkflowCallbackController)

        match = WorkflowCallbackController._token_matches
        self.assertTrue(match(TOKEN, TOKEN))
        self.assertFalse(match(TOKEN, TOKEN + "x"))
        self.assertFalse(match("", TOKEN))
        self.assertFalse(match(TOKEN, ""))
        self.assertFalse(match(None, TOKEN))
        self.assertFalse(match(TOKEN, None))
        self.assertTrue(match("ключ-ñ", "ключ-ñ"))
        self.assertFalse(match("ключ-ñ", "ключ-n"))
