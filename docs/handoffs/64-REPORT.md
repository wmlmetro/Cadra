# Report — Handoff 64: what the photo says

Branch `feat/what-the-photo-says`, from `dev` at `2a462df` (Step 0's docs
commit on top of 63b's merge). Module versions: `myservice_api`
19.0.3.35.0, `myservice_asset_register` 19.0.1.32.0 (two new tables, one new
column on `nrs.asset.event`), `myservice_workflow` Python only.

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
2. **The deploy, including an image rebuild.** The Odoo image now carries
   the `anthropic` SDK (both Dockerfiles), so `deploy-dev` / `deploy-19`
   must build the image, then `upgrade-19` for the two modules on every
   tenant. The switch stays **off** everywhere until you turn it on.
3. **NRS's written acceptance** that photos go to Anthropic, before any
   production photo is sent (R7 + R11, GO-LIVE §33.1).
4. **The key**, which is yours and which I did not place:
   `scripts/set_ai_key.sh test19` locally (prompts, nothing echoed), or the
   `CADRA_AI_API_KEY` key of the `cadra-odoo` secret on the cluster (the
   bootstrap job mirrors it). Then *Settings → Identify from photo → on*,
   provider `anthropic`, on that tenant only.
5. **The live check (§5.5)**: photograph 30–50 office items, name them
   `chair-01.jpg` …, add `labels.json`, and run
   `tests/.venv/bin/python scripts/ai_live_check.py --base http://test19.localhost:8069 --folder <folder>`.
   Its docstring has the whole recipe. Paste the TOTALS block below as the
   addendum.
6. **NRS's class mapping** (report 59's proposal). Until classes carry a SAP
   class, the prompt has no SAP wording to copy (GO-LIVE §33.4): on `nrs19`
   1 of 22 classes carries one.

## In plain words

You can now photograph an item and Cadra suggests what it is: which class
it belongs to, a description in SAP's style, the colour, the material and the
condition. It also reads any text on the item, such as a brand, a model
number, a serial plate or an old FIRS tag, and lists the SAP records it might
be. The phone never talks to the AI company. Cadra's own server does, so the
key stays with us, the provider can be changed without touching the app, and
every question asked is written down. Nothing the AI says is saved unless a
person accepts it. On the web app's *New asset* form the suggestions are
filled in and highlighted, and the form will not save until each one has been
accepted, dismissed or retyped. When it saves, Cadra records which fields
were kept and which were changed, and the asset's history says so in one
line. The same works from any photo already on an asset, side by side with
the current values. It is switched off everywhere. Turning it on needs your
key and NRS's agreement, because the photos leave our servers.

Separately, **Test Connection** on Vendra's target always said *failed*
(`HTTP 401`), even when delivery worked. It now tests the two addresses Cadra
actually sends to, and says in words which one works.

## What was built

- **§1 — the adapter** (`myservice_api/controllers/ai_provider.py`).
  - **The interface:** image + prompt + schema in; validated JSON, model,
    latency and tokens out.
  - **Two implementations:**
    - `fake`: deterministic, offline, answers from the file name; every test
      uses it, and it answers only on a database marked `test`;
    - Anthropic's Messages API through the official SDK, pinned at 1.14.0 and
      imported only when used. Structured outputs, the system prompt cached,
      server-side refusal fallback.
  - **The settings**, all `cadra.*`: the switch (default off), the provider,
    the model (default `claude-opus-5-5`), the timeout (20 s), the daily cap
    (500), the effort (`low`).
  - **The key** goes the Turnstile secret's way (`myservice_api.ai_api_key`):
    bootstrap, one way, or `scripts/set_ai_key.sh`. No route reads or accepts
    it.
  - **What is sent:** the photo with its metadata stripped, the tenant's
    classes, and each mapped SAP class's twenty commonest descriptions.
- **§2 — the route and the record.**
  - `POST /api/v1/ai/identify`: `photo_id`, or `file` + `source`.
  - Every refusal is in words. Every provider call writes an append-only
    `nrs.ai.suggestion`, failed and discarded ones included, and every call
    counts against the cap.
  - **A photo for an asset not yet saved** is held 24 h in
    `nrs.ai.pending.photo` (61's rules untouched) and claimed by the save.
  - **The save names the suggestion:** `ai_suggestion: {id, ignored}` on
    `POST`/`PATCH /assets`. It writes an `ai_suggestion_applied` event with
    each field accepted, changed (from → to) or ignored, and a history line
    of type `details_suggested`.
  - Endpoint reference §17, changelog, mobile map §8.
- **§3 — the web app.**
  - *Add asset*: filled, marked, Save held until each field is settled,
    *Don't use this suggestion*.
  - *Photos tab → Identify…*: Now / Suggested, *Use this* per field.
  - *Settings → Identify from photo*: the switch, the provider, the model,
    the cap and today's count, whether a key is placed.
- **§3b — Test Connection.** For an `asset_events` target it POSTs to each
  configured endpoint, with the delivery's own auth, a body that has no event
  id. The answer is one sentence per endpoint. Other targets keep the ping.
- **§5.5 — `scripts/ai_live_check.py`**, written and dry-run on the
  stand-in; the real run is the owner's.

## The numbers

| | Result |
|---|---|
| `tests/test_what_the_photo_says.py`, `test19f` | 22 of 22 (every field, the SAP candidates for a reader and the count for the Store Officer, each refusal, malformed counted, the cap, 4 accepted / 1 changed + history line, only the asker saves) |
| In-registry: `TestAiSuggestion`, `TestConnectionProbe`, history, photos | 0 failed, 0 errors of 59 |
| Spec 64 (browser), `test19f` | 4 of 4 |
| Touched specs 18 / 46 / 48 / 61 | 18+46+48: 15 passed, 5 skipped; 61: green (the crash-free run) |
| Test Connection, `test19`'s real Vendra target | old `/ping` → `HTTP 401 AuthenticationError`; probe → *Tag events: reachable, token accepted. Register-state events: reachable, token accepted.* |
| Final local pytest, gates off, fresh `test19f` (`1d6368d`) | **1,511 passed, 10 skipped of 1,521, 0 failed, 9 m 31 s** — the skips are 63b's ten (`64-evidence/final-pytest-gates-off-test19f.txt`) |
| CI on `1d6368d`, run [39232743936](https://github.com/wmlmetro/Cadra/actions/runs/39232743936) | **green** — gates off and gates on each: pytest 1,505 passed, 16 skipped of 1,521 (2 m 25 s / 3 m 32 s); in-registry **0 failed, 0 errors of 1,286 tests** (63b: 1,268); each leg ~13 min. Earlier runs: 39227272945 and 39230245701 each 2 failed of 1,519/1,520 — the history pins named in deviation 11 |
| Cost (§6), `claude-opus-5-5`, estimated | ~$0.024 a photo; the register $3,880; an HQ audit (57,059 HQ-coded records) $1,370 — `64-evidence/cost-of-an-office.md` |

## §6 · What would it cost to identify a whole office?

About **2½ US cents a photo**. The image is ~2,560 tokens at the web app's
1,600 px, the cached system prompt ~2,200, the answer ~600 tokens out; about
half the cost is the answer. NRS's register is 161,647 active assets, so
**one photo each is about $3,880**, and the 80,370 furniture about $1,930.
**An HQ audit**: 57,059 of 161,647 active SAP records (35.3 %) carry an old
tag with one of 74 `HQ…` office codes (37,831 have no office at all). That is
about **$1,370**. What reduces it:

- **Identifying only when the person asks, which is how it is built.** Items
  whose old tag the matcher reads directly need no photo read. If one in
  three needs one, HQ is about $460.
- **Smaller images:** 1,024 px is about $0.018 a photo (−25 %).
- **Keeping effort `low`.**
- **The Batch API** for photos identified at sync (not built).
- **The model**, your choice: Sonnet 5.5 would halve it and Haiku 5.5 would
  be about 40× cheaper, neither measured. The live check is how to decide.

The default cap bounds a tenant's day at about $12.

## Deviations and questions

1. **An SAP candidate fills nothing.** §3 says "pick an SAP candidate to fill
   the SAP number, if the person may". No asset route writes
   `sap_asset_number`; only the Register Maker's gate and SAP do, and
   `v1_assets` says why. So nobody on the form "may": the candidates are
   shown with their reasons, for reference. Linking is 65.
2. **The key does live on the configuration record.** §1 asks for the key
   never to appear "on the configuration record", and also asks for the
   Turnstile road. That road IS an `ir_config_parameter` row, readable by a
   back-office system administrator; the configuration-change report redacts
   it by name (`api_?key`). If "configuration record" meant that table, the
   alternative is an environment variable read by the server, never stored.
   **Question for the Architect.**
3. **The cap is counted, not reserved.** Calls made at the same instant as
   the last allowed one can each pass. Holding a lock across a 20-second
   call would queue the tenant (DECISIONS).
4. **Only the person who asked saves a suggestion** (found by the
   verification pass). A different person saving it is refused `403
   not_yours`: one name per confirmation.
5. **Also built: a Settings page.** "The count shown on Settings" needed a
   screen, so there is a new sidebar key, `ai_identify` (36 items).
6. **Found, not changed:** `TestPublishedNamesResolve`'s bare-override check
   is order-dependent. It fails when run alone, because nothing has built the
   routing map yet; it is not this change (DECISIONS).
7. **Found: SAP's Test Connection has the same false-failure shape.** INT-06
   publishes no `/ping`. Unmeasured, left as the handoff says.
8. **Environment:** Postgres crash-restarted once during a browser run
   (memory, `docs/ENVIRONMENT-FACTS.md`); the specs it hit were rerun. A
   restart I made mid-run spoiled one earlier run (502s); also rerun. While
   the backend went in I upgraded every local tenant, not only `test19` and
   `nrs19`: each took ~11 s, and the new event column would otherwise have
   broken them on restart. `boot44` was two API versions behind.
9. **The verification pass** (fresh agent, read-only) found:
   - an SDK error outside my except-chain escaping as a 500 that rolled
     back the call's record;
   - the "no classes" refusal leaving a held photo behind;
   - **a phone JPEG's EXIF GPS going to the provider** (now stripped at the
     byte level; the stored photo is untouched);
   - *Don't use this suggestion* leaving accepted AI values unaudited;
   - anyone being able to apply another person's suggestion;
   - an expired hold being claimable until the cron ran;
   - the key script splicing the database name into a shell string.

   All fixed, the strip and the asker rule with tests. Left as nits: a
   Photos-tab field shown "Same" is recorded *ignored*; no test pins the
   cap's Lagos midnight.
10. **Found by the live-check dry run:** the settings PATCH answered with the
    values from before its own write (a raw-SQL read before the ORM flush).
    Fixed, with a test proved to fail first.
11. **CI caught two of mine, twice:** the HTTP suite's own list of recorded
    history kinds (`tests/test_asset_events_api.py::_RECORDED_TYPES`) — first
    the list, then the two tests that read it as "the suite writes one of
    each". Fixed in `4e11165` and `1d6368d`; I had run the in-registry pin
    and not the HTTP one.

## Where the time went

Wall clock 09:34 → ~11:05 Lagos, about 1½ h of the 4½ h budgeted at Step 0
(no split was needed). Phases overlap; the long runs went in the
background.

- build (Step 0 docs, adapter, route, record, save hook, history, §3b, web
  app, settings page, live-check script, docs): 09:34–10:23, with each
  part's own tests run as it landed;
- tests: touched browser specs 10:23–10:45 (two runs spoiled — my mid-run
  restart, then a Postgres crash — and rerun), final pytest 10:48–10:58;
- verification pass: 10:24–10:31, its fixes and their re-proof 10:31–10:47;
- report: 10:48–11:05.

## Addendum — the owner's live check

*(to be pasted from `scripts/ai_live_check.py`'s TOTALS)*
