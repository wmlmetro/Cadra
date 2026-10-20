# Handoff 68 — A second provider

**Branch:** `feat/a-second-provider`
**Report:** `docs/handoffs/68-REPORT.md` (~120 lines)
**Runs after:** 67, merged. Branch from `dev`, after pulling.
**Time budget:** 2 hours. Follow `CLAUDE.md`'s *Speed* and *Progress*
rules.

---

## 0 · Report 67 is accepted, and why this handoff exists

The Barcode Station captures, the mobile team's four gaps are closed, and a
regional office has a checklist. All three award lots are served on
Cadra's side.

**The owner, 20 October:** the Anthropic account is stuck on the provider's
verification, and he has an **OpenAI** API key ready. Add OpenAI as a
second provider, beside Anthropic, chosen per tenant on *Settings →
Identify from photo*. Report 64 built the adapter for exactly this. **No
other behaviour changes.**

## 1 · The OpenAI provider

- **`OpenAIProvider`** in `myservice_api/controllers/ai_provider.py`,
  beside `AnthropicProvider`, implementing the same `identify(req)` and
  answering the same `ProviderAnswer`.
- **Use the official `openai` Python SDK**, pinned, and imported only when
  used, as `anthropic` is. Add it to both Dockerfiles: **the image must be
  rebuilt**, as in 64.
- **Read OpenAI's current documentation** for the model and the API rather
  than assuming them:
  - image input;
  - **structured output against our JSON schema** (strict schema mode, if
    the chosen API offers it);
  - the system or developer prompt;
  - timeouts and error types.

  Say which API you used and why.
- **The same prompt and schema as Anthropic** (prompt version 67.1, the
  categories, the twenty SAP descriptions per class, `size_band`, the
  text-read kinds). **If OpenAI's strict schema mode can't express a
  construct in ours**, adapt the schema in one place for both providers, or
  keep a provider-specific transformation of the same schema. Never a
  second, divergent prompt.
- **The same safety:**
  - the photo's metadata (EXIF, GPS) is stripped before sending (64);
  - the timeout from settings;
  - every refusal in words;
  - a malformed answer is discarded and counted;
  - every call is recorded in `nrs.ai.suggestion`, with `provider =
    openai` and the model id.
- **Error mapping**, in the same words as Anthropic's: a bad key, no
  permission or quota, rate-limited, timeout, server error, refused by the
  model.
- **Cost:** the live-check script's price table gains OpenAI's per-token
  prices. Take them from OpenAI's pricing page, and mark them for the owner
  to confirm, as 65 did.

## 2 · The key: the owner's, in the environment

- **A separate variable:** `CADRA_OPENAI_API_KEY`. `CADRA_AI_API_KEY` stays
  Anthropic's, so both can be present and switching provider never means
  swapping a secret.
- Add it to the `cadra-odoo` secret's optional keys in
  `k8s/dev/41-odoo-19-deployment.yaml`.
- `scripts/set_ai_key.sh` takes the provider: `set_ai_key.sh openai`
  prompts with no echo and writes the local `.env`.
- *Settings* shows **whether a key is present for each provider**: present
  or absent, never the value.
- **The owner places the key. You never see it, ask for it or print it.**
  Every test uses the fake provider. The live check is the owner's.

## 3 · Settings and the live check

- **The provider list on *Settings → Identify from photo*:** Anthropic,
  OpenAI, and Fake (the Fake option only on a test tenant, as now).
- **The model field** follows the provider: a sensible default per
  provider, taken from that provider's current documentation, which the
  owner can change.
- **Switching provider** is a configuration-record event, as every setting
  is.
- **`ai_live_check.py --models`** accepts `provider:model` pairs, e.g.
  `--models openai:<model>,anthropic:claude-opus-5-5`, so one folder of
  photos compares providers in one table.
- **The acceptance dashboard (67)** already breaks down by model. Make sure
  `provider` is in that breakdown too.

## 4 · What must not change

- Anthropic's provider, byte for byte, apart from any shared-schema change
  §1 requires (say what changed, if anything).
- The route, the audit trail, the fields, and the rule that no suggestion
  writes a field by itself.
- `GO-LIVE` §33.1: NRS's written acceptance is needed before production
  photos go to **any** outside provider. Update the line to name both.

## 5 · Verification

1. Unit tests for the OpenAI provider against a **faked SDK client**:
   - a good answer;
   - each error mapping;
   - a malformed answer counted;
   - EXIF stripped before the call.
2. The settings route: provider switch recorded; key presence per provider;
   Fake refused on a non-test tenant.
3. Targeted HTTP and browser specs (64's and 67's identify paths) on the
   fake; one final local run; CI cited.

## 6 · For the owner, after the merge

1. Rebuild the image (`deploy-dev`), then `upgrade-19` if any module
   version changed.
2. Put the OpenAI key in the `cadra-odoo` secret as
   `CADRA_OPENAI_API_KEY` and restart Odoo. Locally:
   `scripts/set_ai_key.sh openai`.
3. On `test19` or `staging`: *Settings → Identify from photo* → provider
   **OpenAI** → on.
4. Run `ai_live_check.py` over your photo folder, with OpenAI (and
   Anthropic once its verification clears). Paste the table into the
   report's addendum.
