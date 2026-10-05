"""A store officer may not take a copy of the register.

Handoff 50, ruling 1. Reading a page of the register and taking a copy of
all of it are different acts: `GET /api/v1/assets/export` and
`GET /api/v1/assets/export.csv` moved off `assets:read` and onto their own
scope, `export:read` (BREAKING, announced) — granted through exactly one
group, the Auditor's, and covered by the `admin` wildcard as every scope is.
This file is the acting proof, driven through real tokens minted by
`POST /auth/token` against credentials holding exactly the scopes named:
the register scope still reads a page and no longer exports, `export:read`
exports with or without `assets:read` beside it, and the refusal names the
scope it wanted in both the sentence and `details.required_scopes`.

These are HttpCase tests because the gate is decided from the validated JWT
claims on `request`. They need `--workers=0`: `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the committed `workers = 2` every test in the class ERRORS
in setUpClass and the run reports "0 failed". Check the denominator.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestExportScope(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils
        cls.utils = utils

        # One real asset, so the exports have at least a row to carry and a
        # 200 here is a register answering rather than an empty-path fluke.
        cls.marker = "exportprobe%s" % uuid.uuid4().hex[:10]
        Category = cls.env["nrs.asset.category"]
        category = Category.search([], limit=1) or Category.create(
            {"name": "Export probe"})
        cls.asset = cls.env["nrs.asset"].create(
            {"name": "%s 001" % cls.marker, "category_id": category.id})

        # Three credentials, each holding exactly what its name says. No
        # `admin` anywhere — the wildcard would green every assertion at
        # once and prove nothing about the gate under test.
        cls.client_reader = cls.create_api_client({
            "name": "export probe reader",
            "client_id": "exportprobe_reader",
            "scopes": "assets:read"})
        cls.client_both = cls.create_api_client({
            "name": "export probe reader+export",
            "client_id": "exportprobe_both",
            "scopes": "assets:read export:read"})
        cls.client_export_only = cls.create_api_client({
            "name": "export probe export only",
            "client_id": "exportprobe_export_only",
            "scopes": "export:read"})
        cls.secrets = {}
        for rec in (cls.client_reader, cls.client_both,
                    cls.client_export_only):
            cls.secrets[rec.client_id] = rec.rotate_secret()

        # A tenant with no `myservice_api.jwt_secret` answers 500
        # server_misconfigured on /auth/token — same reasoning as
        # test_pagination_cap.py, and no commit anywhere in here.
        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

    # ── helpers ──────────────────────────────────────────────────────

    def _token(self, client):
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": client.client_id,
                             "client_secret": self.secrets[client.client_id]}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _get(self, client, path):
        return self.url_open(
            path, headers={"Authorization": "Bearer %s" % self._token(client)})

    # ── the refusal: the register scope no longer exports ───────────

    def test_a_register_reader_is_refused_both_export_routes(self):
        """`assets:read` alone gets 403 on the JSON and the CSV export.

        The JSON route's refusal is the PRD envelope and must name
        `export:read` in `details.required_scopes` — the machine-readable
        half Vendra and the app branch on. The CSV route is pre-envelope on
        success (a file, not JSON) but its refusals go through the same
        `require_jwt` envelope — the shape its own 401 test in
        tests/test_assets_csv.py already pins — so the same assertions hold.
        """
        for path in ("/api/v1/assets/export", "/api/v1/assets/export.csv"):
            with self.subTest(path=path):
                r = self._get(self.client_reader, path)
                self.assertEqual(
                    r.status_code, 403,
                    "a credential holding only `assets:read` exported the "
                    "register through %s — handoff 50 ruling 1 is undone: "
                    "%s" % (path, r.text))
                error = r.json().get("error") or {}
                self.assertEqual(
                    error.get("code"), self.utils.ERR_FORBIDDEN,
                    "a scope refusal must report `forbidden`, not %r"
                    % error.get("code"))
                self.assertIn(
                    "export:read", error.get("message", ""),
                    "the refusal must NAME the missing scope; got %r"
                    % error.get("message"))
                self.assertIn(
                    "export:read",
                    error.get("details", {}).get("required_scopes", []),
                    "`details.required_scopes` must name `export:read`")

    def test_the_refused_reader_still_reads_a_page(self):
        """The pairing that makes the 403 above mean something: the same
        credential reads a page of the register at 200, so the refusal is
        the split biting and not a credential that can reach nothing."""
        r = self._get(self.client_reader, "/api/v1/assets?limit=1")
        self.assertEqual(
            r.status_code, 200,
            "`assets:read` must still read a page — the split moved the "
            "EXPORT, not the register: %s" % r.text)

    # ── the grant: export:read opens both routes ─────────────────────

    def test_a_reader_who_also_holds_export_read_exports(self):
        r = self._get(self.client_both, "/api/v1/assets/export")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()["data"]
        self.assertIn("assets", body)
        self.assertIn("total", body,
                      "`total` is the register, not the response — the "
                      "handoff 12/13 truth-telling must survive the move")

        r = self._get(self.client_both, "/api/v1/assets/export.csv")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("text/csv", r.headers.get("Content-Type", ""))

    def test_export_read_alone_is_sufficient(self):
        """The gate is the scope, not a group and not a second scope: a
        credential holding `export:read` and nothing else exports both
        shapes. If this fails while the test above passes, the route is
        quietly requiring `assets:read` TOO, which turns the published
        contract (`x-cadra-scopes: [export:read]`) into a lie."""
        for path in ("/api/v1/assets/export", "/api/v1/assets/export.csv"):
            with self.subTest(path=path):
                r = self._get(self.client_export_only, path)
                self.assertEqual(
                    r.status_code, 200,
                    "`export:read` alone must open %s; got HTTP %s: %s"
                    % (path, r.status_code, r.text[:300]))
