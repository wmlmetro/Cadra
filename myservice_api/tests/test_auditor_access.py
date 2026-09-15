"""The Auditor opens all five reports, and writes nothing. Proved by ACTING.

Handoff 23. Specification §3 names an `Auditor` / `audit_viewer` with
"read-only access to audit logs"; INT-10 §4.3 recorded that Cadra had no such
group at all, so the five §13.4 standard reports were reachable only by
somebody who could also change the register they were reporting on. The group
now exists (`myservice_api/security/api_groups.xml`) and
`utils.GROUP_SCOPES` maps it to six read scopes.

**Why this suite does not read permission rows.**

The sibling Frappe repository shipped a report whose own roles table named the
role that was supposed to open it, and the report was still unopenable —
because a second gate nobody had in mind (a permission on the underlying
doctype) refused before the report's own check ran. Every configuration test
written for it passed. The failure was found by a human clicking the link.

That is the whole argument for the shape of this file. Cadra has exactly the
same class of second gate and more of them: every `@cadra_route` runs
`require_jwt` BEFORE the handler, the handlers then run `sudo()` — mostly —
and anything that forgot the `sudo()` refuses with an `AccessError` that the
envelope turns into a 403 indistinguishable, to a naive reader, from a scope
refusal. A test that asserts `"assets:read" in GROUP_SCOPES[...]` cannot see
any of that. So:

  * `test_the_auditor_group_derives_exactly_the_read_scopes` and
    `test_the_auditor_group_holds_no_write_scope_in_the_scope_table` are the
    CONFIGURATION half. They are here to fail loudly when somebody edits the
    table, and **neither is evidence that a report opens.**
  * `test_an_auditor_can_open_every_one_of_the_five_standard_reports` is the
    test. It mints a real token through `POST /api/v1/auth/login` as a real
    user holding exactly this group, and does a real `GET` against all five
    URLs. It asserts **200**, never "not 403" — a 404 from a report whose
    fixture was never created passes "not 403" while proving nothing, which
    is why setUpClass builds an asset and a custody link rather than reaching
    for whatever the tenant happens to hold.

**Every refusal is paired with a read of the same resource.** A 403 on a
resource the caller cannot see either way is not a proof of least privilege —
it is consistent with an auditor who can reach nothing at all, which is the
failure mode this group was created to fix. Same doctrine as the Frappe
suite: prove the positive first, then prove the boundary around it.

Run it:

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098 \\
      --test-enable --test-tags /myservice_api --workers=0

**`--workers=0` is not optional.** `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port`, and `PreforkServer` has no
`httpd`; under the committed `workers = 2` every test in this class ERRORS in
setUpClass and the run still reports "0 failed". Check the denominator — an
`of 0 tests` line is a failed run wearing a pass.

Fixtures carry a `auditprobe<hex>` marker and the user's login starts with
`auditprobe.`, because this suite runs against live-shaped tenants and a
reader who has never heard of it must be able to tell its rows from real ones
on sight. Nothing here commits; HttpCase's rollback takes it all back.
"""
import json
import uuid
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


#: The scopes `myservice_api.group_auditor` is expected to grant, pinned here
#: rather than read out of GROUP_SCOPES. That is the point of the pin: a
#: seventh scope added to the table must FAIL a test and force somebody to
#: decide, not quietly widen an audit credential. If you are here because this
#: list disagrees with `utils.GROUP_SCOPES`, the question to answer is whether
#: an auditor should hold the new scope — not which copy to edit.
EXPECTED_AUDITOR_SCOPES = frozenset({
    "assets:read",
    "locations:read",
    "requests:read",
    "identity:read",
    "dashboards:read",
    "settings:read",
})

AUDITOR_GROUP_XMLID = "myservice_api.group_auditor"


@tagged("post_install", "-at_install")
class TestAuditorAccess(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils
        cls.utils = utils

        cls.marker = "auditprobe%s" % uuid.uuid4().hex[:8]

        cls.auditor_group = cls.env.ref(AUDITOR_GROUP_XMLID)

        # ── the account ───────────────────────────────────────────────
        #
        # `base.group_user` because an auditor is an internal user and Odoo
        # 19 requires exactly one of user/portal/public; `group_auditor`
        # because that is the thing under test. NOTHING ELSE — the whole
        # claim being proved is that this group alone opens the five
        # reports, and an account that had picked up Asset User on the way
        # in would prove that two groups together do.
        #
        # Odoo 19 renamed `res.users.groups_id` to `group_ids`. Both are
        # accepted here the way `myservice.api.client._provision_client_user`
        # accepts both, so this file does not become the one place a version
        # is pinned.
        Users = cls.env["res.users"].sudo().with_context(
            no_reset_password=True)
        cls.groups_field = ("group_ids" if "group_ids" in Users._fields
                            else "groups_id")
        cls.auditor_password = uuid.uuid4().hex
        cls.auditor_user = Users.create({
            "name": "Auditor probe %s" % cls.marker,
            "login": "auditprobe.%s@example.invalid" % cls.marker,
            "password": cls.auditor_password,
            cls.groups_field: [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.auditor_group.id,
            ])],
        })

        # ── the fixtures the five reports need ───────────────────────
        #
        # One real asset, so `/assets/<id>/custody` resolves to a record
        # instead of answering 404. A 404 is the trap this fixture exists to
        # avoid: it is not 403, it is not 500, and a test that only checked
        # "the auditor was not refused" would go green on a URL that never
        # reached the report at all.
        Category = cls.env["nrs.asset.category"].sudo()
        category = Category.search([], limit=1) or Category.create(
            {"name": "Auditor probe"})
        cls.asset = cls.env["nrs.asset"].sudo().create({
            "name": "auditor probe asset %s" % cls.marker,
            "category_id": category.id,
        })

        # A custody link, so the chain has something in it. The recorder
        # lives in `nrs.asset.write` (handoff 14), so an ordinary ORM write
        # is the honest way to make one.
        cls.employee = cls.env["hr.employee"].sudo().create(
            {"name": "auditor probe custodian %s" % cls.marker})
        cls.asset.write({"custodian_id": cls.employee.id})

        # ── the tenant's own configuration ───────────────────────────
        #
        # A tenant with no `myservice_api.jwt_secret` answers 500
        # `server_misconfigured` on /auth/login, exactly as it does on
        # /auth/token — same reasoning as test_pagination_cap.py.
        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

        # Cloudflare Turnstile guards /auth/login and is a no-op only while
        # `myservice_api.turnstile_secret` is empty. On a tenant that HAS a
        # site configured, every login in this suite would be refused for a
        # challenge token no test can produce — the suite would report a
        # failure about auditors that was really a failure about Cloudflare.
        # Cleared for the duration; the class rollback puts it back, and
        # nothing here commits.
        cls.turnstile_secret_was = ICP.get_param(
            "myservice_api.turnstile_secret")
        if cls.turnstile_secret_was:
            ICP.set_param("myservice_api.turnstile_secret", "")

        # Periods for the three period-scoped reports. `from`/`to` are both
        # INCLUSIVE and `to` must not precede `from`; `as_of` must not be in
        # the future. Today is deliberately the upper bound on all four, so
        # the fixtures created a moment ago are inside every window.
        today = fields.Date.today()
        cls.period_from = (today - timedelta(days=365)).isoformat()
        cls.period_to = today.isoformat()
        cls.as_of = today.isoformat()

    # ── helpers ──────────────────────────────────────────────────────

    def _login_token(self):
        """A REAL session token for the auditor, minted by the real route.

        Not a hand-built JWT. The scopes on this token are whatever
        `/auth/login` decided to put there, which is the only version of the
        question that matters — a token assembled in the test would prove
        that `require_jwt` respects scopes, not that an auditor gets them.
        """
        r = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": self.auditor_user.login,
                             "password": self.auditor_password}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(
            r.status_code, 200,
            "the auditor could not even log in, so nothing below this line "
            "means anything: %s" % r.text)
        return r.json()["data"]["access_token"]

    def _auth(self, token):
        return {"Authorization": "Bearer %s" % token}

    def _get(self, token, path):
        return self.url_open(path, headers=self._auth(token))

    def _send(self, token, method, path, body=None):
        headers = dict(self._auth(token))
        headers["Content-Type"] = "application/json"
        return self.url_open(
            path, method=method,
            data=json.dumps(body if body is not None else {}),
            headers=headers)

    def _report_urls(self):
        """The five standard reports of specification §13.4, by URL.

        Keyed by the name the specification uses, so a subTest failure names
        the REPORT rather than a path fragment.
        """
        return [
            ("asset register snapshot",
             "/api/v1/reports/asset-register?as_of=%s" % self.as_of),
            ("custodianship chain",
             "/api/v1/assets/%d/custody" % self.asset.id),
            ("disposal report",
             "/api/v1/reports/disposals?from=%s&to=%s"
             % (self.period_from, self.period_to)),
            ("access changes",
             "/api/v1/reports/access-changes?from=%s&to=%s"
             % (self.period_from, self.period_to)),
            ("configuration changes",
             "/api/v1/reports/configuration-changes?from=%s&to=%s"
             % (self.period_from, self.period_to)),
        ]

    # ── 1. the configuration half, and it is only half ───────────────

    def test_the_auditor_group_derives_exactly_the_read_scopes(self):
        """`scopes_for_user` gives an auditor the six reads and nothing else.

        **This test is NOT sufficient on its own and must never be treated as
        the acceptance criterion.** It reads the group→scope table through
        the function that consumes it, which is one gate out of at least
        three: `require_jwt` also has to accept the token, and each handler
        has to reach its data without tripping an ir.model.access rule. The
        Frappe failure this suite is modelled on passed a test exactly this
        strong. `test_an_auditor_can_open_every_one_of_the_five_standard_reports`
        is the evidence; this one localises the fault when that one breaks.
        """
        derived = set(self.utils.scopes_for_user(self.auditor_user))

        self.assertEqual(
            derived, set(EXPECTED_AUDITOR_SCOPES),
            "a user holding base.group_user + group_auditor and nothing else "
            "must derive exactly the six read scopes the five reports need")

        writes = sorted(s for s in derived if s.endswith(":write"))
        self.assertEqual(
            writes, [],
            "an auditor holding a write scope is not independent of what "
            "they are auditing; found %s" % writes)
        self.assertNotIn(
            self.utils.SCOPE_ADMIN, derived,
            "`admin` is a wildcard in require_jwt — it would defeat every "
            "other assertion in this file at once")

    # ── 2. THE test: five reports, opened ────────────────────────────

    def test_an_auditor_can_open_every_one_of_the_five_standard_reports(self):
        """All five §13.4 reports answer 200 to a token with only this group.

        This is the handoff's acceptance criterion and the reason the file
        exists. It ACTS: a real user, a real `/auth/login`, a real bearer
        token, five real `GET`s against fixtures this suite created so every
        URL resolves to something.

        **200, not "not 403".** The looser assertion passes on a 404 from an
        asset id that was never created and on a 500 from a handler that
        forgot its `sudo()` — the two failures most likely to be sitting
        behind a scope check that looks correct. A 404 in particular is the
        Frappe failure's exact shape: the gate opened, and there was nothing
        on the other side.

        `subTest` per report, so a run that finds one broken report names it
        and still checks the other four. An auditor told "the reports work"
        when four of five do is being told something false.
        """
        token = self._login_token()

        for name, url in self._report_urls():
            with self.subTest(report=name, url=url):
                r = self._get(token, url)
                self.assertEqual(
                    r.status_code, 200,
                    "an auditor must be able to open the %s report; got HTTP "
                    "%s: %s" % (name, r.status_code, r.text))

                body = r.json()
                self.assertNotIn(
                    "error", body,
                    "the %s report answered 200 carrying an error envelope, "
                    "which is a refusal a client reading the status code "
                    "would never see" % name)
                self.assertIn(
                    "data", body,
                    "every @cadra_route answers the PRD §10.7 envelope — "
                    "rule 1 — and the %s report did not" % name)
                self.assertIsNotNone(
                    body["data"],
                    "the %s report returned `data: null`; an empty report is "
                    "a legitimate answer and `null` is not one of its "
                    "shapes" % name)

    # ── 3. every write refused, and every refusal paired with a read ──

    def test_an_auditor_is_refused_every_write(self):
        """Five write paths, five 403s, each naming the scope it wanted.

        **Each refusal is paired with a successful READ of the same
        resource.** A 403 proves least privilege only if the caller can see
        the thing they were refused permission to change: an auditor who gets
        403 on `POST /assets` and 403 on `GET /assets` has not been given a
        careful boundary, they have been given nothing, and the reports above
        would be failing too. Pairing is what tells those two apart, and it
        is the doctrine carried over from the Frappe suite.

        The bodies are well formed on purpose. A malformed body would also be
        refused — with a 400 — and a test that cannot tell 400 from 403 is
        asserting that the request was bad rather than that the caller was
        unauthorised. `require_jwt` runs before any body parsing inside
        `cadra_endpoint`, so these are refused for the only reason under
        test.

        `tag-affixed` wants `tagging:write` and `approve-disposal` wants
        `approvals:write`, neither of which is an "assets" scope — they are
        here because a read-only claim that only checks the obvious write
        scope is not a read-only claim.
        """
        token = self._login_token()

        # Read first. If any of these is not 200 the refusals below are
        # meaningless, and saying so here is more useful than five confusing
        # passes.
        r = self._get(token, "/api/v1/assets/%d" % self.asset.id)
        self.assertEqual(
            r.status_code, 200,
            "the auditor cannot READ the asset, so a 403 on writing it "
            "proves nothing about least privilege: %s" % r.text)
        r = self._get(token, "/api/v1/locations?limit=1")
        self.assertEqual(
            r.status_code, 200,
            "the auditor cannot READ locations, so a 403 on creating one "
            "proves nothing about least privilege: %s" % r.text)

        attempts = [
            ("create an asset", "POST", "/api/v1/assets",
             {"name": "%s must not exist" % self.marker}, "assets:write"),
            ("edit an asset", "PATCH", "/api/v1/assets/%d" % self.asset.id,
             {"notes": "%s must not be written" % self.marker},
             "assets:write"),
            ("approve a disposal", "POST",
             "/api/v1/assets/%d/approve-disposal" % self.asset.id,
             {}, "approvals:write"),
            ("confirm a tag affixed", "POST",
             "/api/v1/assets/%d/tag-affixed" % self.asset.id,
             {"tag_number": "%s-TAG" % self.marker}, "tagging:write"),
            ("create a location", "POST", "/api/v1/locations",
             {"name": "%s must not exist" % self.marker}, "locations:write"),
        ]

        for label, method, path, body, scope in attempts:
            with self.subTest(attempt=label, scope=scope):
                r = self._send(token, method, path, body)
                self.assertEqual(
                    r.status_code, 403,
                    "an auditor must not be able to %s; got HTTP %s: %s"
                    % (label, r.status_code, r.text))

                envelope = r.json()
                self.assertIn(
                    "error", envelope,
                    "a 403 must carry the PRD error envelope, not a bare "
                    "body — Vendra branches on `error.code`")
                error = envelope["error"]
                self.assertEqual(
                    error["code"], self.utils.ERR_FORBIDDEN,
                    "an authorisation failure must report `forbidden`. "
                    "`validation_failed` here tells an integrator to fix "
                    "their payload when the answer is to fix their "
                    "credentials — the exact defect handoff 09 closed.")
                self.assertIn(
                    scope, error["message"],
                    "the refusal must NAME the missing scope; `%s` is not in "
                    "%r" % (scope, error["message"]))
                self.assertIn(
                    scope, error.get("details", {}).get("required_scopes", []),
                    "`details.required_scopes` is the machine-readable half "
                    "of the same fact and must name `%s` too" % scope)

        # Nothing got through. Read back through the ORM rather than the API,
        # so a write that happened but is invisible to a read-scoped token
        # would still be caught.
        self.asset.invalidate_recordset()
        self.assertFalse(
            self.asset.notes,
            "the PATCH was refused with a 403 and the field changed anyway")
        self.assertEqual(
            self.env["nrs.asset"].sudo().search_count(
                [("name", "ilike", self.marker), ("id", "!=", self.asset.id)]),
            0,
            "a refused POST /assets must leave no record behind")
        self.assertEqual(
            self.env["generic.location"].sudo().search_count(
                [("name", "ilike", self.marker)]),
            0,
            "a refused POST /locations must leave no record behind")

    # ── 4. the sweep over the table itself ───────────────────────────

    def test_the_auditor_group_holds_no_write_scope_in_the_scope_table(self):
        """`GROUP_SCOPES`'s auditor entry is pinned, so widening it fails here.

        The acting tests above check the writes they know to try. This one
        catches the scope granted in a future edit that nobody wrote a test
        for — `ingestion:write` added "so the auditor can import the roll",
        say — by pinning the whole entry rather than probing it. Adding a
        scope to an audit credential should cost a deliberate decision and a
        line in `docs/DECISIONS.md`; a test that fails is how the decision
        gets asked for.
        """
        entries = [scopes for xmlid, scopes in self.utils.GROUP_SCOPES
                   if xmlid == AUDITOR_GROUP_XMLID]
        self.assertEqual(
            len(entries), 1,
            "`%s` must appear exactly once in GROUP_SCOPES; a second entry is "
            "a union nobody reading the first one would expect"
            % AUDITOR_GROUP_XMLID)

        granted = set(entries[0])
        self.assertEqual(
            granted, set(EXPECTED_AUDITOR_SCOPES),
            "the auditor's scope grant changed. Every scope here ends up in "
            "an audit credential's token; if the change is deliberate, "
            "update EXPECTED_AUDITOR_SCOPES in the same commit and say why "
            "in docs/DECISIONS.md.")

        self.assertEqual(
            sorted(s for s in granted if not s.endswith(":read")), [],
            "every scope an auditor holds must be a `:read`. A read-only "
            "group is the ONLY thing making the login token unable to write "
            "— every route runs sudo(), so the Odoo group is not the gate "
            "and cannot be.")
        self.assertTrue(
            granted <= self.utils.ALL_SCOPES,
            "a scope no route declares is a scope that grants nothing and "
            "reads as though it grants something: %s"
            % sorted(granted - self.utils.ALL_SCOPES))

    # ── 5. independence, enforced rather than commented ──────────────

    def test_the_auditor_group_is_implied_by_nothing_and_implies_nothing(self):
        """The XML says "do not tidy this into the hierarchy". This enforces it.

        An auditor who is also an Asset Manager is not independent of what
        they are auditing, and an Asset Manager who silently picks up the
        auditor's `settings:read` has been handed a scope nobody granted
        them. `implied_ids` in either direction would do one of those two
        things, and the choice is a one-line `eval="[(4, ref(...))]"` that
        looks like housekeeping in a diff.

        Both directions are checked because they fail differently:
        `implied_ids` leaks the auditor's scopes OUT to whoever holds this
        group, `implied_by_ids` leaks them IN to every member of the implying
        group. The second is the dangerous one and the easier one to add by
        accident, since it is written in the OTHER module's file.
        """
        group = self.auditor_group

        self.assertFalse(
            group.implied_ids,
            "group_auditor must imply nothing; it implies %s"
            % group.implied_ids.mapped("name"))

        # `implied_by_ids` is the reverse of the same m2m table on Odoo 19.
        # Searched rather than read where the field is absent, so this test
        # states the fact rather than the field.
        if "implied_by_ids" in group._fields:
            implied_by = group.implied_by_ids
        else:
            implied_by = self.env["res.groups"].sudo().search(
                [("implied_ids", "in", group.id)])
        self.assertFalse(
            implied_by,
            "nothing may imply group_auditor — %s does, which silently hands "
            "its members the auditor's read scopes"
            % implied_by.mapped("name"))

        # The transitive closures, for the case where the direct edge is
        # clean and a two-hop path is not. `all_implied_ids` is REFLEXIVE in
        # Odoo 19 — it contains the group itself — so the group is subtracted
        # before the assertion rather than expected to be absent.
        if "all_implied_ids" in group._fields:
            self.assertFalse(
                group.all_implied_ids - group,
                "group_auditor transitively implies %s"
                % (group.all_implied_ids - group).mapped("name"))
        if "all_implied_by_ids" in group._fields:
            self.assertFalse(
                group.all_implied_by_ids - group,
                "group_auditor is transitively implied by %s"
                % (group.all_implied_by_ids - group).mapped("name"))
