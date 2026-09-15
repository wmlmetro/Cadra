"""A disposal approved over the API records the CALLER. Proved by acting.

Handoff 23 §C, and this file exists because the first version of that work
shipped without it. Every other test of `POST /assets/<id>/approve-disposal`
asserted a **403** — the pytest suite's credential does not hold
`approvals:write`, and neither does the Auditor — so the route's whole reason
for existing had no executed coverage at all: not the 200 path, not the
approver actually written, not the 400 that refuses a body naming an
approver, not the 409 on a second call. The verification pass found it, and
"a client without the scope is refused" is only half of the acceptance
criterion it was standing in for.

**The claim under test is narrow and it is not the model's.**
`nrs.asset.action_approve_disposal` writes `self.env.uid`, and
`myservice_asset_register/tests/test_disposal_report.py` already covers that
through the ORM. What is new — and what nothing covered — is that the uid
SURVIVES THE CONTROLLER: `_browse_or_404` hands back a `sudo()` recordset,
and the route's docstring claims Odoo 19's `sudo()` does not change
`env.uid`, so the record still names the client rather than `Administrator`.
That is a claim about the request path, and only a request can prove it.

So this suite mints a real client-credentials token for a real
`myservice.api.client` carrying `approvals:write`, POSTs, and then reads the
approver back **through the ORM rather than through the response** — the
response is the thing under test and cannot also be the evidence for itself.

Run it:

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\
      odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \\
      --http-port=8099 --gevent-port=8098 \\
      --test-enable --test-tags /myservice_api --workers=0

**`--workers=0` is not optional** — `HttpCase.setUpClass` reads
`odoo.service.server.server.httpd.server_port` and `PreforkServer` has no
`httpd`, so under the committed `workers = 2` every test here errors in
setUpClass and the run still reports "0 failed". Quote the denominator.

Fixtures carry an `apprprobe<hex>` marker. Nothing commits; HttpCase rolls
back.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestApproveDisposalRoute(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.marker = "apprprobe%s" % uuid.uuid4().hex[:8]

        ICP = cls.env["ir.config_parameter"].sudo()
        # Same reason as `test_auditor_access`: a tenant with no signing
        # secret answers 500 on every auth route, and the failure would read
        # as a fault in this route rather than in the tenant.
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

        # ── the credential ───────────────────────────────────────────
        #
        # `assets:read approvals:write` and nothing else. Deliberately NOT
        # `assets:write`: the point of the scope is that approving is not
        # something a broad asset credential can already do, and a client
        # holding both would prove the route works for somebody who could
        # have PATCHed the record anyway.
        cls.secret = uuid.uuid4().hex
        cls.client_rec = cls.create_api_client({
            "name": "Approver probe %s" % cls.marker,
            "client_id": cls.marker,
            "scopes": "assets:read approvals:write",
        })
        cls.client_rec.set_client_secret(cls.secret)

        Category = cls.env["nrs.asset.category"].sudo()
        cls.category = Category.search([], limit=1) or Category.create(
            {"name": "Approval probe category %s" % cls.marker})

    # ── helpers ─────────────────────────────────────────────────────

    def _token(self):
        """A real client-credentials token from the real route."""
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.client_rec.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(
            r.status_code, 200,
            "the approver client could not mint a token, so nothing below "
            "this line means anything: %s" % r.text)
        return r.json()["data"]["access_token"]

    def _disposed_asset(self):
        """An asset in `disposed` with no approval on it yet."""
        asset = self.env["nrs.asset"].sudo().create({
            "name": "Approval probe %s %s" % (self.marker,
                                              uuid.uuid4().hex[:6]),
            "category_id": self.category.id,
        })
        asset.write({"state": "disposed"})
        self.assertFalse(
            asset.disposal_approved_by,
            "the fixture arrived already approved, so every assertion below "
            "would pass without the route doing anything")
        return asset

    def _approve(self, token, asset, body=None):
        return self.url_open(
            "/api/v1/assets/%d/approve-disposal" % asset.id,
            method="POST",
            data=json.dumps(body if body is not None else {}),
            headers={"Authorization": "Bearer %s" % token,
                     "Content-Type": "application/json"})

    # ── the test the acceptance criterion actually asks for ─────────

    def test_the_recorded_approver_is_the_caller(self):
        """*"A disposal approval over the API records the caller."*

        Read back through the ORM, not out of the response body. The
        response is what is under test; using it as the evidence for itself
        would pass just as happily if the route echoed the caller while
        writing something else.
        """
        token = self._token()
        asset = self._disposed_asset()

        r = self._approve(token, asset)
        self.assertEqual(r.status_code, 200, r.text)

        asset.invalidate_recordset()
        self.assertEqual(
            asset.disposal_approved_by, self.client_rec.user_id,
            "the disposal names %s; the call was made by %s. `sudo()` in "
            "`_browse_or_404` must not change `env.uid`, or every approval "
            "in the register names whoever the framework felt like."
            % (asset.disposal_approved_by.name or "nobody",
               self.client_rec.user_id.name))
        self.assertNotEqual(
            asset.disposal_approved_by, self.env.ref("base.user_admin"),
            "the approval names Administrator, which is the exact defect "
            "handoff 08 fixed and this route must not reintroduce")
        self.assertTrue(asset.disposal_approved_date,
                        "an approver was recorded with no approval date")

        body = r.json()["data"]
        self.assertEqual(body["disposal"]["approved_by"]["id"],
                         self.client_rec.user_id.id,
                         "the response disagrees with the database")

    def test_a_body_naming_an_approver_is_refused_and_writes_nothing(self):
        """*"...and not anything the body asked for."*

        Refused, not ignored. Dropping the field would answer 200 to a
        caller that believes it appointed somebody, and the approver in the
        register would then disagree with the approver in that caller's own
        logs — with nothing anywhere saying so.

        The second half of this test is the part that matters: after the
        refusal the asset must still be approvable, which is what proves the
        refused call wrote nothing.
        """
        token = self._token()
        admin = self.env.ref("base.user_admin")

        for field in ("disposal_approved_by", "approved_by", "approver",
                      "user_id", "disposal_approved_date"):
            with self.subTest(field=field):
                asset = self._disposed_asset()
                r = self._approve(token, asset, {field: admin.id})
                self.assertEqual(r.status_code, 400, r.text)
                error = r.json()["error"]
                self.assertEqual(error["code"], "invalid_request")
                self.assertIn(field, error["details"]["rejected_fields"])

                asset.invalidate_recordset()
                self.assertFalse(
                    asset.disposal_approved_by,
                    "the refused call wrote an approver anyway")

                # And the refusal left the record approvable, which is the
                # only way to be sure nothing was half-written.
                self.assertEqual(
                    self._approve(token, asset).status_code, 200)
                asset.invalidate_recordset()
                self.assertEqual(asset.disposal_approved_by,
                                 self.client_rec.user_id)

    def test_a_second_approval_is_a_409_naming_who_holds_the_first(self):
        """An approval is a one-time act, so a second caller is TOLD.

        A quiet second success would let a later approver overwrite the
        record of who actually authorised the disposal — which is the one
        fact the disposal report exists to carry.
        """
        token = self._token()
        asset = self._disposed_asset()
        self.assertEqual(self._approve(token, asset).status_code, 200)

        asset.invalidate_recordset()
        first_approver = asset.disposal_approved_by
        first_date = asset.disposal_approved_date

        r = self._approve(token, asset)
        self.assertEqual(r.status_code, 409, r.text)
        error = r.json()["error"]
        self.assertEqual(error["code"], "conflict")
        self.assertIn(first_approver.name, error["message"],
                      "the 409 does not say who holds the approval")
        self.assertEqual(error["details"]["approved_by"]["id"],
                         first_approver.id)

        asset.invalidate_recordset()
        self.assertEqual(asset.disposal_approved_by, first_approver)
        self.assertEqual(asset.disposal_approved_date, first_date,
                         "the refused second approval moved the date")

    def test_an_asset_that_is_not_disposed_of_cannot_be_approved(self):
        """An approval against an asset still on the register authorises
        nothing, and the model says so in its own words."""
        token = self._token()
        asset = self.env["nrs.asset"].sudo().create({
            "name": "Approval probe live %s" % self.marker,
            "category_id": self.category.id,
        })
        self.assertEqual(asset.state, "active")

        r = self._approve(token, asset)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(r.json()["error"]["code"], "validation_failed")

        asset.invalidate_recordset()
        self.assertFalse(asset.disposal_approved_by)

    def test_an_unknown_key_is_reported_rather_than_silently_dropped(self):
        """Not every unrecognised key is refused — only the ones that claim
        an approver. The rest follow the contract PATCH already publishes:
        reported in `_warnings.rejected_fields`, because a key this route
        does not read is a caller misunderstanding and it is told so."""
        token = self._token()
        asset = self._disposed_asset()

        r = self._approve(token, asset, {"colour": "blue"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(
            "colour",
            r.json()["data"]["_warnings"]["rejected_fields"],
            "an unread key was accepted in silence")

    def test_a_client_without_the_scope_is_refused(self):
        """The second half of the criterion, proved with a REAL credential
        rather than from the published contract.

        `tests/test_audit_logs.py` asserts this too, using the suite's own
        token. This one narrows a client deliberately, so the refusal is
        attributable to the scope rather than to whatever that tenant's
        credential happened to hold.
        """
        narrowed = self.create_api_client({
            "name": "Narrow probe %s" % self.marker,
            "client_id": "%s-narrow" % self.marker,
            "scopes": "assets:read assets:write",
        })
        secret = uuid.uuid4().hex
        narrowed.set_client_secret(secret)

        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": narrowed.client_id,
                             "client_secret": secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()["data"]["access_token"]

        asset = self._disposed_asset()
        # It can READ the asset — so the refusal below is the scope and not
        # an invisible record. Same pairing doctrine as the auditor suite.
        self.assertEqual(
            self.url_open("/api/v1/assets/%d" % asset.id,
                          headers={"Authorization": "Bearer %s" % token}
                          ).status_code, 200)

        r = self._approve(token, asset)
        self.assertEqual(r.status_code, 403, r.text)
        error = r.json()["error"]
        self.assertEqual(error["code"], "forbidden")
        self.assertIn("approvals:write", error["details"]["required_scopes"])

        asset.invalidate_recordset()
        self.assertFalse(
            asset.disposal_approved_by,
            "a client without the scope approved a disposal anyway")
