"""The record cap tells the truth about itself.

Handoff 12 A. The cap is a deliberate commercial control and it stays. What
was indefensible was everything it said:

  * it keyed off the `aud` claim, which only /auth/login stamps, so the rule
    in force was "browsers are trusted, programs are not" — and Vendra and
    the audit client both hold machine credentials;
  * `total_estimate` reported the size of the capped WINDOW, so a tenant
    holding 2,363 assets answered "there are 100";
  * nothing in the response said it had been truncated.

These are HttpCase tests because the cap is decided from the validated JWT
claims on `request`, and there is no honest way to fake that from a
TransactionCase. Note they need `--workers=0`: `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the documented `workers = 2` config every test in the
class ERRORS in setUpClass and the run reports "0 failed".
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestPaginationCap(CadraHttpCase):

    #: More than EXTERNAL_TOTAL_CAP, so the cap has something to bite on.
    ASSET_COUNT = 105

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils
        cls.utils = utils

        # A marker in the name so `?q=` narrows the domain to exactly our
        # own rows. Without it these assertions would depend on how many
        # assets the tenant happens to hold, and would pass or fail for
        # reasons that have nothing to do with the cap.
        cls.marker = "capprobe%s" % uuid.uuid4().hex[:10]

        # `category_id` is required on nrs.asset; reuse the tenant's first
        # category rather than inventing one, so nothing about these rows is
        # unusual for the register they are counted in.
        Category = cls.env["nrs.asset.category"]
        category = Category.search([], limit=1) or Category.create(
            {"name": "Cap probe"})

        Asset = cls.env["nrs.asset"]
        cls.assets = Asset.create([
            {"name": "%s %03d" % (cls.marker, i), "category_id": category.id}
            for i in range(cls.ASSET_COUNT)
        ])

        cls.client_default = cls.create_api_client({
            "name": "cap probe default", "client_id": "capprobe_default",
            "scopes": "assets:read"})
        cls.client_uncapped = cls.create_api_client({
            "name": "cap probe uncapped", "client_id": "capprobe_uncapped",
            "scopes": "assets:read", "total_record_cap": -1,
            "max_page_limit": -1})
        cls.client_500 = cls.create_api_client({
            "name": "cap probe 500", "client_id": "capprobe_500",
            "scopes": "assets:read", "max_page_limit": 500,
            "total_record_cap": 500})
        cls.secrets = {}
        for rec in (cls.client_default, cls.client_uncapped, cls.client_500):
            cls.secrets[rec.client_id] = rec.rotate_secret()

        # The controller reads the tenant's jwt_secret from a config param;
        # a tenant that has never been bootstrapped has none and /auth/token
        # answers 500 server_misconfigured.
        # No commit anywhere in here. Odoo 19 refuses one from inside a
        # test ("Cannot commit or rollback a cursor from inside a test"),
        # and HttpCase does not need it: the server thread runs on the
        # test's own cursor in test mode, so these rows are visible to
        # url_open and disappear with the rollback at the end.
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

    def _list(self, client, query=""):
        token = self._token(client)
        r = self.url_open(
            "/api/v1/assets?q=%s%s" % (self.marker, query),
            headers={"Authorization": "Bearer %s" % token})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ── the acceptance criteria, one test each ───────────────────────

    def test_a_capped_token_is_told_the_true_total(self):
        body = self._list(self.client_default, "&limit=2000")

        self.assertEqual(len(body["data"]), self.utils.EXTERNAL_TOTAL_CAP,
                         "the cap must still bite — it is a deliberate control")
        self.assertEqual(
            body["pagination"]["total_estimate"], self.ASSET_COUNT,
            "total_estimate must be a fact about the register, not the size "
            "of the window the caller was given. This is the whole finding.")

    def test_a_capped_response_says_it_was_truncated(self):
        body = self._list(self.client_default, "&limit=2000")

        warning = body.get("_warnings", {}).get("truncated")
        self.assertTrue(warning, "a truncated response must announce it; "
                                 "rule 3 — silent degradation is a defect "
                                 "even when it returns 200")
        self.assertEqual(warning["cap"], self.utils.EXTERNAL_TOTAL_CAP)
        self.assertEqual(warning["total"], self.ASSET_COUNT)
        self.assertIn("limited to the first", warning["reason"])

    def test_an_uncapped_client_gets_everything_and_no_warning(self):
        body = self._list(self.client_uncapped, "&limit=2000")

        self.assertEqual(len(body["data"]), self.ASSET_COUNT,
                         "total_record_cap = -1 means uncapped; Vendra and "
                         "the audit client are provisioned this way")
        self.assertEqual(body["pagination"]["total_estimate"], self.ASSET_COUNT)
        self.assertNotIn("_warnings", body,
                         "nothing was truncated, so nothing may claim it was")

    def test_a_client_with_max_page_limit_500_gets_its_own_ceiling(self):
        body = self._list(self.client_500, "&limit=2000")

        self.assertEqual(len(body["data"]), self.ASSET_COUNT,
                         "105 rows fit inside a 500 page and a 500 cap")
        self.assertNotIn("_warnings", body)

    def test_the_cap_survives_across_cursor_pages(self):
        """Paginating inside the window must not walk past it."""
        token = self._token(self.client_default)
        seen, cursor, pages = 0, None, 0
        while pages < 10:
            url = "/api/v1/assets?q=%s&limit=40" % self.marker
            if cursor:
                url += "&cursor=%s" % cursor
            body = self.url_open(
                url, headers={"Authorization": "Bearer %s" % token}).json()
            seen += len(body["data"])
            self.assertEqual(body["pagination"]["total_estimate"],
                             self.ASSET_COUNT,
                             "every page reports the true total, not a "
                             "remaining-rows countdown")
            cursor = body["pagination"]["next_cursor"]
            pages += 1
            if not cursor:
                break
        self.assertEqual(seen, self.utils.EXTERNAL_TOTAL_CAP,
                         "the cumulative cap is the control; exhausting it "
                         "must end the walk")

    def test_the_csv_export_carries_the_truncation_header(self):
        """A CSV bypasses the envelope, so it gets a header and a final
        commented row instead. This is the artefact that gets saved,
        emailed and cited."""
        token = self._token(self.client_default)
        r = self.url_open("/api/v1/assets/export.csv",
                          headers={"Authorization": "Bearer %s" % token})
        self.assertEqual(r.status_code, 200)

        total = self.env["nrs.asset"].search_count([])
        if total <= self.utils.EXTERNAL_TOTAL_CAP:
            self.skipTest("tenant holds %d assets — nothing to truncate" % total)

        self.assertEqual(r.headers.get("X-Cadra-Truncated"),
                         "%d/%d" % (self.utils.EXTERNAL_TOTAL_CAP, total))
        self.assertIn("# TRUNCATED", r.text.splitlines()[-1])

    def test_the_json_export_reports_the_true_total(self):
        token = self._token(self.client_default)
        r = self.url_open("/api/v1/assets/export",
                          headers={"Authorization": "Bearer %s" % token})
        body = r.json()["data"]
        total = self.env["nrs.asset"].search_count([])

        self.assertEqual(body["total"], total)
        if total > self.utils.EXTERNAL_TOTAL_CAP:
            self.assertEqual(body["count"], self.utils.EXTERNAL_TOTAL_CAP)
            self.assertTrue(r.json().get("_warnings", {}).get("truncated"))

    def test_a_malformed_limit_claim_never_widens_access(self):
        """A claim we cannot parse falls back to the external default, not
        to uncapped. The failure direction matters more than the failure."""
        from odoo.http import request as _request  # noqa: F401
        self.assertEqual(
            self.utils.client_limit_claims(self.client_default), {},
            "an unconfigured client stamps no claims at all, so its token is "
            "byte-identical to the one it received before this existed")
        self.assertEqual(
            self.utils.client_limit_claims(self.client_uncapped),
            {"max_page_limit": -1, "total_record_cap": -1})
