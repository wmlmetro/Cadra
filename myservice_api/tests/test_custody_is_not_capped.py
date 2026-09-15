"""A chain of custody is complete, or it is evidence of nothing.

Handoff 15 B3. `include=custody` has always returned the whole chain, because
it does not paginate. `GET /assets/<id>/custody` went through `paginate()`
and therefore through `record_cap()`, so a capped credential asking the same
question the other way got a shorter answer — nine rows on the embed, two on
the route, and nothing in either response saying which was which.

The ruling went the way the model was built: the cap is lifted from BOTH
paths rather than applied to both. A chain is one asset's complete record,
bounded by how often that asset changed hands and not by how much data a
tenant holds — and **a truncated chain cannot be told from a complete one**,
which is the entire finding `nrs.asset.custody` exists to close.

Also here: handoff 15 B2. The suite that proves all of this writes permanent
links into whatever tenant it runs against, so those links say `test` on
their face.

HttpCase, because the cap is decided from validated JWT claims on `request`
and there is no honest way to fake that from a TransactionCase. Needs
`--workers=0` — see test_pagination_cap.py for why.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestCustodyIsNotCapped(CadraHttpCase):

    #: Small on purpose. The cap only has to BITE; building a hundred-link
    #: chain would prove the same thing and cost a hundred writes.
    CAP = 3
    LINKS = 6

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.myservice_api.controllers import utils
        cls.utils = utils

        marker = uuid.uuid4().hex[:8]

        Category = cls.env["nrs.asset.category"]
        category = Category.search([], limit=1) or Category.create(
            {"name": "Custody probe"})
        cls.asset = cls.env["nrs.asset"].create(
            {"name": "custody probe %s" % marker, "category_id": category.id})

        Employee = cls.env["hr.employee"]
        cls.employees = Employee.create([
            {"name": "custody probe A %s" % marker},
            {"name": "custody probe B %s" % marker},
        ])

        # Move the custodian back and forth. The recorder lives in
        # `nrs.asset.write`, not in the transfer route — handoff 14 — so an
        # ordinary ORM write is the honest way to build a chain.
        for i in range(cls.LINKS):
            cls.asset.write({"custodian_id": cls.employees[i % 2].id})

        cls.client_capped = cls.create_api_client({
            "name": "custody probe capped",
            "client_id": "custodyprobe_capped_%s" % marker,
            "scopes": "assets:read",
            "max_page_limit": cls.CAP,
            "total_record_cap": cls.CAP,
        })
        cls.client_test = cls.create_api_client({
            "name": "custody probe test credential",
            "client_id": "custodyprobe_test_%s" % marker,
            "scopes": "assets:read assets:write",
            "is_test_credential": True,
        })
        cls.secrets = {
            rec.client_id: rec.rotate_secret()
            for rec in (cls.client_capped, cls.client_test)
        }

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
        r = self.url_open(
            path, headers={"Authorization": "Bearer %s" % self._token(client)})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _other_custodian(self):
        """The probe employee the asset is NOT currently assigned to.

        Hard-coding one of the two is wrong: the transfer route refuses a
        move to the current custodian with a 400, and each test method starts
        from the class savepoint rather than from the previous test — so
        which of the pair is held depends only on how many writes setUpClass
        happened to make. A test that fails on that is testing the fixture.
        """
        held = self.asset.custodian_id
        return self.employees[1] if held == self.employees[0] else self.employees[0]

    def _whole_chain(self, client):
        """Walk the cursor. NOT a big `limit=` — `parse_limit` clamps that to
        the client's own page ceiling, so naming a large number silently
        hands back one page and calls it the chain."""
        links, cursor = [], None
        for _ in range(50):
            path = "/api/v1/assets/%d/custody?limit=%d" % (self.asset.id,
                                                           self.CAP)
            if cursor:
                path += "&cursor=%s" % cursor
            body = self._get(client, path)
            links.extend(body["data"])
            cursor = body["pagination"]["next_cursor"]
            if not cursor:
                break
        return links

    # ── the ruling ───────────────────────────────────────────────────

    def test_a_capped_credential_still_walks_the_whole_chain(self):
        """The cap bites on assets and does not bite here."""
        links = self._whole_chain(self.client_capped)
        self.assertEqual(
            len(links), self.LINKS,
            "a capped credential must reach every link. A chain cut off at "
            "the cap is indistinguishable from a chain that ended there, "
            "which is the defect this model was built to close.")

    def test_the_total_is_true_and_nothing_claims_truncation(self):
        body = self._get(
            self.client_capped,
            "/api/v1/assets/%d/custody?limit=1" % self.asset.id)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["pagination"]["total_estimate"], self.LINKS,
                         "total_estimate is a fact about the chain on every "
                         "path, capped or not")
        self.assertNotIn(
            "_warnings", body,
            "nothing was truncated, so nothing may say it was. A truncation "
            "warning on a complete answer is the same lie pointing the other "
            "way.")

    def test_the_route_and_the_embed_agree(self):
        """One question, one answer, whichever way it is asked.

        This is the asymmetry report 14 measured live: two rows back from the
        route and nine from the embed, with nothing saying which was which.
        """
        route = self._whole_chain(self.client_capped)
        embed = self._get(
            self.client_capped,
            "/api/v1/assets/%d?include=custody" % self.asset.id)
        self.assertEqual(
            len(route), len(embed["data"]["custody"]),
            "the embed and the route must return the same chain; a client "
            "that gets different answers from the two cannot trust either")

    def test_the_asset_list_is_still_capped(self):
        """The exemption is one resource, not a hole in the control.

        Without this, "lift the cap on custody" and "stop capping" pass
        identically, and the guard for a commercial control would be a test
        that never noticed it was gone.
        """
        self.assertEqual(self.utils.EXTERNAL_TOTAL_CAP, 100)
        self.assertEqual(self.client_capped.total_record_cap, self.CAP)
        body = self._get(self.client_capped, "/api/v1/assets?limit=2000")
        self.assertLessEqual(
            len(body["data"]), self.CAP,
            "the record cap must still bite on an ordinary list endpoint")

    # ── handoff 15 B2 ────────────────────────────────────────────────

    def test_a_link_written_by_a_test_credential_says_so(self):
        """`source: test`, decided from the credential and not from the call.

        The suite exercises the recorder against live-shaped tenants, the
        recorder is append-only, and the links it leaves are permanent. A
        reader who was never told this suite exists must still be able to
        see that they are artefacts — the same argument as
        `tracking_backfill`, one step on.
        """
        token = self._token(self.client_test)
        r = self.url_open(
            "/api/v1/assets/%d/transfer-custody" % self.asset.id,
            data=json.dumps({"to_custodian_id": self._other_custodian().id,
                             "reason": "test_custody_is_not_capped"}),
            headers={"Authorization": "Bearer %s" % token,
                     "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)

        links = self._whole_chain(self.client_capped)
        self.assertEqual(
            links[-1]["source"], "test",
            "a link written under a test credential must be labelled `test`, "
            "not `api_transfer`. The route it arrived by is the less "
            "important fact: the reader's first question is whether it "
            "happened at all.")

    def test_a_caller_cannot_label_its_own_link_a_test(self):
        """Because that would be a way to disguise a real transfer.

        The source is read off the credential. Nothing in the request body
        or headers may reach it — in the one model whose whole value is that
        its contents were not invented.
        """
        token = self._token(self.client_test)
        self.client_test.is_test_credential = False
        try:
            r = self.url_open(
                "/api/v1/assets/%d/transfer-custody" % self.asset.id,
                data=json.dumps({"to_custodian_id": self._other_custodian().id,
                                 "source": "test",
                                 "reason": "trying to label my own write"}),
                headers={"Authorization": "Bearer %s" % token,
                         "Content-Type": "application/json"})
            self.assertEqual(r.status_code, 200, r.text)
            links = self._whole_chain(self.client_capped)
            self.assertEqual(
                links[-1]["source"], "api_transfer",
                "`source` in the request body must be ignored entirely")
        finally:
            self.client_test.is_test_credential = True
