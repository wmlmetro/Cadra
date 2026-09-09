"""Reducing a client's cap does not wait for its refresh window to expire.

Handoff 13 B1. `/auth/refresh` already re-reads the limits off the client
record (handoff 12), so a raised cap bites on the next refresh. What was
left open is the other direction, and it is the one that matters: a cap is
REDUCED because somebody decided this credential should see less — a
partner in dispute, an integration behaving badly — and a family that goes
on rotating for a 30-day sliding window is how "we restricted them" turns
into "we will have restricted them, eventually".

Widening fails safe. Narrowing does not. So the write revokes.
"""
import json
import uuid

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestLimitChangeRevokesFamilies(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Client = cls.env["myservice.api.client"]
        cls.client_rec = Client.create({
            "name": "limit probe", "client_id": "limitprobe",
            "scopes": "assets:read", "total_record_cap": 500})
        cls.secret = cls.client_rec.rotate_secret()

        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)

    def _mint(self):
        response = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.client_rec.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["refresh_token"]

    def _refresh(self, raw):
        return self.url_open(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": raw}),
            headers={"Content-Type": "application/json"})

    def test_a_reduced_cap_kills_the_family_immediately(self):
        refresh_token = self._mint()
        self.assertEqual(self._refresh(refresh_token).status_code, 200,
                         "the family works before the change; otherwise the "
                         "assertion below proves nothing")

        refresh_token = self._mint()
        self.client_rec.write({"total_record_cap": 50})

        self.assertEqual(
            self._refresh(refresh_token).status_code, 401,
            "the cap was reduced; the family that would keep re-minting "
            "under the old ceiling for thirty days must be gone")

    def test_a_widened_cap_revokes_too(self):
        """Widening fails safe, so it need not — but a rule with an
        exception is a rule somebody has to remember. The cost is one
        re-authentication on an administrative action."""
        refresh_token = self._mint()
        self.client_rec.write({"total_record_cap": -1})
        self.assertEqual(self._refresh(refresh_token).status_code, 401)

    def test_the_revocation_reason_is_recorded(self):
        self._mint()
        self.client_rec.write({"max_page_limit": 25})
        tokens = self.env["myservice.api.refresh_token"].search(
            [("client_id", "=", self.client_rec.id), ("revoked", "=", True)])
        self.assertIn("limits_changed", tokens.mapped("revoked_reason"))

    def test_writing_the_same_value_revokes_nothing(self):
        """Saving the form is not an administrative decision. A no-op write
        that logged everybody out would make the guard something people
        route around."""
        refresh_token = self._mint()
        self.client_rec.write({
            "total_record_cap": self.client_rec.total_record_cap,
            "max_page_limit": self.client_rec.max_page_limit,
        })
        self.assertEqual(self._refresh(refresh_token).status_code, 200)

    def test_an_unrelated_write_revokes_nothing(self):
        refresh_token = self._mint()
        self.client_rec.write({"name": "limit probe renamed"})
        self.assertEqual(self._refresh(refresh_token).status_code, 200)

    def test_another_clients_family_is_untouched(self):
        other = self.env["myservice.api.client"].create({
            "name": "limit probe bystander", "client_id": "limitprobe_other",
            "scopes": "assets:read"})
        other_secret = other.rotate_secret()
        response = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": other.client_id,
                             "client_secret": other_secret}),
            headers={"Content-Type": "application/json"})
        other_refresh = response.json()["data"]["refresh_token"]

        self.client_rec.write({"total_record_cap": 10})

        self.assertEqual(self._refresh(other_refresh).status_code, 200,
                         "revocation is per client; a shared blast radius "
                         "would make the control unusable")

    def test_the_new_cap_is_in_force_on_the_next_token(self):
        """The point of the revocation is the ceiling, not the 401."""
        from odoo.addons.myservice_api.controllers import utils

        self.client_rec.write({"total_record_cap": 7})
        response = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.client_rec.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        token = response.json()["data"]["access_token"]
        claims = utils.jwt_decode(
            token, self.env["ir.config_parameter"].sudo().get_param(
                "myservice_api.jwt_secret"))
        self.assertEqual(claims[utils.CLAIM_TOTAL_RECORD_CAP], 7)
