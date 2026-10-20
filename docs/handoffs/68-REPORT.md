# Handoff 68 — report: a second provider

**Branch:** `feat/a-second-provider` · **Commits:** `d39a343` (instruction), `4c493e9` (the work), `98bb4dc` (the CI guard and the verification pass's fixes), the report commit · **CI: green, both switch states, on the PR's head `8322441`** — run [39427956631](https://github.com/wmlmetro/Cadra/actions/runs/39427956631) (the earlier `5550ad7` runs passed both legs and were then cancelled by the newer push, so they read "cancelled"); the first run, [39423684468](https://github.com/wmlmetro/Cadra/actions/runs/39423684468), failed on one guard (deviation 6), and 39425747939 was superseded

## Needs the owner

1. **Merge the PR** (the Builder's permission layer refuses `gh pr merge`).
2. **Rebuild the image** — `deploy-dev` does it on the merge push. **No module version changed**, so `upgrade-19` is not needed for the schema; the new Python reaches the cluster on the next rollout of `odoo-19`, as every Python change does.
3. **The OpenAI key goes in the GitHub repository secret `CADRA_OPENAI_API_KEY`**, not into the `cadra-odoo` secret by hand (deviation 1). `deploy-dev` copies it into `cadra-odoo` on every push; a value patched in by hand is wiped by the next push. Then a rollout of `odoo-19`. Locally: `scripts/set_ai_key.sh openai`, then `up -d --force-recreate odoo`.
4. On `test19` or `staging`: *Settings → Identify from photo* → provider **OpenAI (GPT)** → on. The screen says whether each provider's key is present.
5. Run the live check over your photos — for example `--models openai:gpt-6.1-sol,openai:gpt-6-luna` now, and add `anthropic:claude-opus-5-5` once Anthropic clears verification — and paste the tables into this report's addendum.
6. **Confirm OpenAI's prices** in both tables (`ai_provider.PRICES_PER_MTOK`, `scripts/ai_live_check.py`) against OpenAI's pricing page.
7. **NRS's written acceptance must name OpenAI too** before production photos go to it (`GO-LIVE` §33.1, updated). An acceptance that names only Anthropic does not cover OpenAI.

## In plain words

Cadra can now send a photo to OpenAI instead of Anthropic to ask what the item is, and each tenant chooses which on its settings screen. Nothing else about the feature changed. Both companies get the same instructions and must answer in the same shape. The answer is checked the same way, every call is recorded the same way, and nothing is written to an asset unless a person saves it. Each company has its own key, held by the server and never by a database. Both keys can be in place at once, so switching company never means touching a secret, and the screen says which keys are there without ever showing one. The Anthropic code was not touched.

The new browser test caught one real bug on the settings screen, which was older than this handoff. After a page reload, the model box could show the previous company's model under the new company's name. It is fixed.

## What was built

- **`OpenAIProvider`** (`ai_provider.py`), beside `AnthropicProvider`, the same `identify(req)` → `ProviderAnswer`. **OpenAI's Responses API**, through the official SDK `openai==3.26.1`, imported only when used. I chose the Responses API over Chat Completions because OpenAI's current documentation (read through Context7 on 20 Oct) builds on it. The system prompt goes in `instructions`, the strict JSON schema in `text.format` (`strict: true`), and every current model is served there.
  - The image is sent as a base64 data URL at `detail: high`, the documented choice for high-fidelity reading.
  - `store: false`: the Responses API keeps a response for later retrieval by default, and Cadra never fetches one back.
  - `reasoning.effort` is the tenant's setting; `low`, `medium` and `high` are OpenAI's words too.
  - `max_output_tokens` is 8,192, not Anthropic's 4,096, because OpenAI counts reasoning tokens inside it. An answer cut short is malformed, and is counted.
  - The SDK's retries are off and the tenant's timeout is the whole budget, as for Anthropic.
- **One prompt, one schema.** The shared schema already meets strict mode's two rules (every object closed, every property required), so it goes to OpenAI **unchanged**. There is no transformation and no second schema. `strict_schema_problems()` plus a unit test fail the day an edit breaks either rule.
- **Errors, in Anthropic's sentences** (401 names `CADRA_OPENAI_API_KEY`; 403, 404 model, 429 rate, other status, connection, the SDK's base error), plus one OpenAI-only case: **`429 insufficient_quota` → "no quota left"**, because waiting does not cure it. The timeout is caught *before* the connection error: in the SDK it is a subclass of it. A refusal part, or `incomplete: content_filter`, is a refusal; `failed` is an error.
- **Usage**: OpenAI's `input_tokens` includes cached and cache-written tokens; Anthropic's does not. Cadra records uncached input separately for both, so one `cost_usd` serves both. A dated snapshot id (`gpt-6.1-sol-2026-09-29`) is priced as its model.
- **Keys**: `CADRA_OPENAI_API_KEY`, separate from `CADRA_AI_API_KEY` (still Anthropic's), in compose, `.env.example`, the k8s deployment (optional key) and **`deploy-dev`'s secret sync**. `set_ai_key.sh openai` prompts with no echo and writes `.env` (tried on a scratch `.env` with dummy values only).
- **Settings**: providers Anthropic, OpenAI, and the stand-in (offered only on a `test` database). `keys` and `provider_options` give each key's presence, never the value. **Each provider keeps its own model** (Anthropic's stays `cadra.ai.model`; OpenAI's is `cadra.ai.model.openai`, default `gpt-6.1-sol`), so a switch never overwrites the other provider's model. A switch is a configuration row. Turning on a provider without its key is refused, naming its variable.
- **Live check**: `--models openai:gpt-6.1-sol,anthropic:claude-opus-5-5` runs one table per provider:model. Afterwards it puts back each provider's model and the tenant's provider. OpenAI's prices are in its table, marked for the owner to confirm.
- **Acceptance dashboard**: `by_provider` is added, each `by_model` row names its provider, and the screen draws both.
- **The settings form re-syncs** whenever the server's values change. This is the fix for spec 68's finding.
- `GO-LIVE` §33.1–33.2, `DEPLOYMENT`, the endpoint reference, CHANGELOG, DECISIONS, STATUS and CLAUDE.md are updated.

## The numbers

| What | Result |
|---|---|
| `tests/test_openai_provider.py` (faked SDK) | **24 of 24** — a good answer, the request sent, 9 error mappings, timeout order, refusal, content filter, failed, 4 malformed answers discarded, EXIF absent from what the SDK received, the schema strict-valid |
| The **real** SDK in the rebuilt image, in-process transport, no network | the wire body: `strict: true`, `store: false`, `detail: high`, 7 keys; 401 / 429 quota / 429 rate / 404 / 400 / 500 → Cadra's sentences; a refusal; usage 5000−3000 cached → 2000 (`68-evidence/real-sdk-drive.txt`) |
| In-registry `TestAiProvidersSettings` + `TestAiSuggestion` (`test19f`) | **0 failed, 0 errors of 24 tests**; after the fixes, with `TestPublishedNamesResolve`, **0 of 38** |
| `tests/test_what_the_photo_says.py` + `test_source_guards.py` + the unit file | first run 267 of 268 — a 500 from my own refusal-hint format string (four `%s`, three values), fixed; then the photo file 26 of 26 |
| Browser 67 + 68 on `test19f` | **2 of 2** (68: list → switch → reload → back, read from the API at each step) |
| Browser 64 on `test19f` | 3 of 4 — *Photos tab* fails on tenant data, not this change (deviation 3) |
| Full pytest, gates off, fresh `test19f` (on `4c493e9`) | **1,567 passed, 10 skipped, 0 failed of 1,577**, 9 m 59 s |
| After the verification fixes: the unit, photo and source-guard files; spec 68 | 268 of 268; 1 of 1 |
| CI run 1 (`4c493e9`), both switch states | pytest **1,561 passed, 16 skipped** each; modules **1 failed of 1,314** each — `test_every_guarded_read_is_classified` (deviation 6) |
| CI run 39427956631 on `8322441` (the fix + this report), both switch states | pytest **1,561 passed, 16 skipped** each; modules **0 failed, 0 errors of 1,314** each |

## Deviations and questions

1. **The key's road on the cluster.** §2 and §6.2 say to put the key "in the `cadra-odoo` secret". `deploy-dev` regenerates that whole secret on every push (CLAUDE.md, handoff 65), so a key patched in by hand would be wiped by the next push. I added `CADRA_OPENAI_API_KEY` to `deploy-dev`'s sync. **The owner sets the GitHub secret instead.**
2. **The stand-in's model.** It used to show Anthropic's model (`claude-opus-5-5`) because there was one model parameter. It now has its own (`cadra-fake-1`), so a failed stand-in call records `cadra-fake-1`. This only affects test records.
3. **Spec 64's *Photos tab* is red on `test19f`, and was before this change** (report 67 ran spec 64 on `test19`, which now has its gates on, so the spec skips there). It expects *"1 accepted"*; on `test19f` it reads *"3 accepted, 2 ignored."* No class on either tenant has "chair" in its name (0 of 20, 0 of 180), so the stand-in suggests the first class by id. On `test19f` that is the same class the spec gives its asset, and handoff 65's *already held → accepted* rule counts it, and the condition, as accepted. The code that does this counting is untouched here. The spec should count the fields the asset already held; I did not change it in this handoff.
4. **`providers` now omits the stand-in on a non-test tenant.** The handoff said "as now", but before this change the list always included it (only the PATCH refused it). It is marked as a behaviour change in CHANGELOG.
5. **The verification pass** (a fresh agent, read-only over the diff) found no blocking defect and seven findings. I fixed five:
   - one OpenAI model split into two rows on the dashboard: failures record the alias, answers the dated snapshot. A snapshot now counts with its model, and there is a test for it;
   - `by_provider` was missing from the acceptance route's schema and the endpoint reference;
   - `set_ai_key.sh OpenAI` (capitalised) wrote Anthropic's key; the argument is now case-insensitive;
   - the stand-in's key sentence read wrongly;
   - the live check now marks a provider "touched" before its PATCH, so a timed-out PATCH is still restored.

   Left as it is: changing the provider throws away unsaved timeout and cap edits, because the form re-syncs to the server. Measured and left: OpenAI's strict mode allows about 1,000 enum values; the largest register here has 180 classes, which is 360 values.
6. **CI's first run failed on a guard I should have run.** The published-names guard classifies every `getattr(x, "name", default)` in a controller. The OpenAI provider reads its SDK's response objects that way, which made 15 unclassified reads. They are now classified as "not a record". I changed `myservice_api` but ran only my own two classes of it, not the module's guard: the same miss handoff 67 made.
7. **Fan-out:** none needed. No module version, field or data file changed; the container was recreated on the new image.

## Where the time went

- Step 0 and reading: 13:11–13:15.
- Build: 13:15–13:28 (the image 3 min of it).
- Targeted tests and fixes: 13:28–13:38.
- Final suite (10 min), verification pass (5 min) in parallel, and report: 13:38–13:53.
- CI run 1 failed at 13:50 and the guard was fixed by 13:53; CI was green on both legs by 14:07.
