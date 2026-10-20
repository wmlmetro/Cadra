"""Two providers on *Settings → Identify from photo* — handoff 68 §5.2.

Driven through the real route with a real token, in-registry, because one
of the three things to prove needs a database that is NOT marked `test` —
which the HTTP suite refuses to touch. The database's class is patched to
`client` for the request (`v1_ai.database_class`, the name the route
reads); nothing is committed.

1. the stand-in provider is refused on a non-test tenant, and not offered;
2. whether the server holds each provider's key, never the key — from the
   SERVER's environment, patched here with invented values;
3. switching provider is a write of `cadra.ai.provider` (the configuration
   record's row, as every setting is), each provider keeps its own model,
   and turning on a provider whose key is absent is refused naming ITS
   variable.

Needs `--workers=0` (HttpCase).
"""
import json
import os
import uuid
from unittest import mock

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase
from odoo.addons.myservice_api.controllers import ai_provider as ai

AI = "/api/v1/settings/ai-identify"
NO_KEYS = {"CADRA_AI_API_KEY": "", "CADRA_OPENAI_API_KEY": ""}


@tagged("post_install", "-at_install")
class TestAiProvidersSettings(CadraHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client_rec = cls.create_api_client({
            "name": "ai providers probe",
            "client_id": "aiproviders_%s" % uuid.uuid4().hex[:8],
            "scopes": "settings:read settings:write"})
        cls.secret = cls.client_rec.rotate_secret()
        ICP = cls.env["ir.config_parameter"].sudo()
        if not ICP.get_param("myservice_api.jwt_secret"):
            ICP.set_param("myservice_api.jwt_secret", uuid.uuid4().hex)
        # A known starting point: off, on Anthropic, no model chosen.
        for key in (ai.PARAM_ENABLED, ai.PARAM_PROVIDER,
                    ai.model_param(ai.PROVIDER_ANTHROPIC),
                    ai.model_param(ai.PROVIDER_OPENAI)):
            ICP.search([("key", "=", key)]).unlink()

    def _token(self):
        r = self.url_open(
            "/api/v1/auth/token",
            data=json.dumps({"client_id": self.client_rec.client_id,
                             "client_secret": self.secret}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["access_token"]

    def _call(self, method, body=None, db_class="client", env=None):
        headers = {"Authorization": "Bearer %s" % self._token(),
                   "Content-Type": "application/json"}
        with mock.patch(
                "odoo.addons.myservice_api.controllers.v1_ai.database_class",
                return_value=db_class), \
                mock.patch.dict(os.environ, env or NO_KEYS):
            if method == "GET":
                return self.url_open(AI, headers=headers)
            return self.url_open(AI, data=json.dumps(body or {}),
                                 headers=headers, method="PATCH")

    def _param(self, key):
        self.env.invalidate_all()
        self.env.cr.execute("SELECT value FROM ir_config_parameter "
                            "WHERE key = %s", (key,))
        row = self.env.cr.fetchone()
        return row and row[0]

    # 1 ────────────────────────────────────────────────────────────────

    def test_the_stand_in_is_refused_and_not_offered_on_a_client_tenant(self):
        r = self._call("PATCH", {"provider": "fake"})
        self.assertEqual(r.status_code, 400, r.text)
        err = r.json()["error"]
        self.assertEqual(err["details"]["reason"], "not_a_test_database")
        self.assertIn("only on a database marked `test`", err["message"])
        self.assertNotEqual(self._param(ai.PARAM_PROVIDER), "fake")
        data = self._call("GET").json()["data"]
        self.assertEqual(data["providers"], ["anthropic", "openai"])
        self.assertEqual([o["value"] for o in data["provider_options"]],
                         ["anthropic", "openai"])
        # On a test database it is offered, last.
        test = self._call("GET", db_class="test").json()["data"]
        self.assertEqual(test["providers"], ["anthropic", "openai", "fake"])

    # 2 ────────────────────────────────────────────────────────────────

    def test_each_providers_key_presence_and_never_the_key(self):
        env = {"CADRA_AI_API_KEY": "", "CADRA_OPENAI_API_KEY":
               "invented-openai-value-68"}
        r = self._call("GET", env=env)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertNotIn("invented-openai-value-68", r.text)
        self.assertEqual(data["keys"], {
            "anthropic": {"placed": False, "variable": "CADRA_AI_API_KEY",
                          "command": "scripts/set_ai_key.sh"},
            "openai": {"placed": True, "variable": "CADRA_OPENAI_API_KEY",
                       "command": "scripts/set_ai_key.sh openai"}})
        opts = {o["value"]: o for o in data["provider_options"]}
        self.assertEqual((opts["anthropic"]["key_placed"],
                          opts["openai"]["key_placed"]), (False, True))
        self.assertEqual(opts["openai"]["default_model"], "gpt-6.1-sol")
        self.assertEqual(opts["openai"]["label"], "OpenAI (GPT)")
        # `key_placed` is the CONFIGURED provider's — Anthropic's, here.
        self.assertEqual((data["provider"], data["key_placed"],
                          data["key_variable"]),
                         ("anthropic", False, "CADRA_AI_API_KEY"))

    # 3 ────────────────────────────────────────────────────────────────

    def test_a_switch_is_recorded_and_each_provider_keeps_its_model(self):
        r = self._call("PATCH", {"provider": "anthropic",
                                 "model": "claude-sonnet-5-5"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self._call("PATCH", {"provider": "openai"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        # The provider is a configuration row, as every setting is; the
        # model shown follows it, from OpenAI's own default.
        self.assertEqual(self._param(ai.PARAM_PROVIDER), "openai")
        self.assertEqual((data["provider"], data["model"],
                          data["default_model"]),
                         ("openai", "gpt-6.1-sol", "gpt-6.1-sol"))
        self.assertEqual(data["notice"], "Photograph the item, not people. "
                         "The photo is sent to OpenAI (GPT) to read it.")
        # A model sent with no provider is the CONFIGURED provider's.
        r = self._call("PATCH", {"model": "gpt-6-luna"})
        self.assertEqual(r.json()["data"]["model"], "gpt-6-luna")
        self.assertEqual(self._param("cadra.ai.model.openai"), "gpt-6-luna")
        # Anthropic's choice was not touched by any of it.
        self.assertEqual(self._param("cadra.ai.model"), "claude-sonnet-5-5")
        back = self._call("PATCH", {"provider": "anthropic"}).json()["data"]
        self.assertEqual(back["model"], "claude-sonnet-5-5")
        opts = {o["value"]: o["model"] for o in back["provider_options"]}
        self.assertEqual(opts, {"anthropic": "claude-sonnet-5-5",
                                "openai": "gpt-6-luna"})
        # The configuration-change report reads the row the switch wrote.
        today = self.env["ir.config_parameter"].sudo()\
            .configuration_change_report
        from odoo.addons.myservice_asset_register.models.ai_suggestion import (
            lagos_today)
        day = lagos_today()
        keys = {row["key"] for row in today(day, day)["rows"]}
        self.assertIn(ai.PARAM_PROVIDER, keys)
        self.assertIn("cadra.ai.model.openai", keys)

    def test_turning_on_a_provider_without_its_key_names_its_variable(self):
        env = {"CADRA_AI_API_KEY": "invented-anthropic-value",
               "CADRA_OPENAI_API_KEY": ""}
        r = self._call("PATCH", {"provider": "openai", "enabled": True},
                       env=env)
        self.assertEqual(r.status_code, 400, r.text)
        err = r.json()["error"]
        self.assertEqual(err["details"]["reason"], "provider_not_ready")
        self.assertIn("CADRA_OPENAI_API_KEY", err["message"])
        self.assertIn("set_ai_key.sh openai", err["message"])
        self.assertNotIn("invented-anthropic-value", r.text)
        self.assertNotEqual(self._param(ai.PARAM_ENABLED), "true")
        # Anthropic's key IS held: switching on there goes through, and
        # switching to OpenAI while on is refused — the key that matters is
        # the provider's being switched TO.
        ok = self._call("PATCH", {"provider": "anthropic", "enabled": True},
                        env=env)
        self.assertEqual(ok.status_code, 200, ok.text)
        refused = self._call("PATCH", {"provider": "openai"}, env=env)
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertIn("CADRA_OPENAI_API_KEY",
                      refused.json()["error"]["message"])
        self.assertEqual(self._param(ai.PARAM_PROVIDER), "anthropic")
