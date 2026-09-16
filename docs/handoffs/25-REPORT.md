# Report 25 — Where the tests are allowed to write

**Branch:** `fix/tests-know-where-they-are` · **Base:** `dev` (handoff 24 merged as PR #70 before this started).

**Needs the owner:** the PR merge, and **two scripts against `jaizbankplc`** — `scripts/mark_test_fixtures.py` (from handoff 24, verified NOT yet run) and the new `scripts/remove_test_residue.py`. The permission layer refuses a committing write to a client-derived tenant, which is the correct refusal and is why both are scripts rather than done things.

---

## 1 · What the guard refuses and what it lets through

**The mark is `cadra.database_class`, a system parameter in the target database, read with SQL.** Values `test` / `client` / `production`. Absent refuses. No bypass flag, no override variable.

Proved by pointing the suite at each class in turn. `test19` is the database under test because it is the one I can move between classes without touching anybody's data:

| The database says | HTTP suite | In-registry suite |
|---|---|---|
| *(no mark at all)* | **REFUSED** | **REFUSED** |
| `production` | **REFUSED** | **REFUSED** |
| `client` | **REFUSED** | **REFUSED** |
| `yes` — a value that is not a class | **REFUSED** | **REFUSED** |
| `  TEST ` — case and whitespace | **runs** (normalised) | **runs** |
| `test` | **runs** — 24/24 | **runs** — 0 failed of 516 |
| `test`, credential not flagged `is_test_credential` | **REFUSED** | n/a |

`jaizbankplc` is marked `client` and refuses; verified through the route rather than by running the suite at it, because the permission layer refused that command — correctly, and it is the same refusal this handoff automates:

```json
{"database": "jaizbankplc", "database_class": "client",
 "accepts_test_writes": false, "credential_is_test": true}
```

`nrs`, `lasg` and `gtb` are marked `client` too. **`cadra19`, `nrs19` and `gtb19` are deliberately left unmarked** — they refuse anyway, and marking a database `client` on a guess would put a false record in the one place the system now trusts.

**Whitespace and case are normalised on purpose** (`  TEST ` is accepted): a person who typed the word meant the word. A value that is not a class at all — `yes`, `true`, a typo — is treated exactly as absent, so a misspelling can never open a door a blank cannot.

**Both refusals are loud and name the remedy in full**, including the exact `odoo shell` command with the right database substituted in. Neither is a skip: report 23 §3's rule is that a skip is a guard that passes, and the in-registry refusal reports `0 failed, 36 error(s) of 0 tests` and exits non-zero — the collapsed denominator CLAUDE.md warns about, but carrying 36 errors rather than a silent green.

### Where each suite asks, and why it cannot ask earlier

**The HTTP suite: `creds` depends on the guard.** It was `token` at first, on the reasoning that every writing path reaches the API through `client` and `client` through `token`. **That was wrong and the verification pass found it:** four tests take `api_base` + `creds` and POST to `/auth/token` with bare `requests` — three in `test_auth.py`, one in `test_negative.py` — so `pytest tests/test_auth.py` against a client-derived register ran **green** with the guard never instantiated. Gating the credentials closes it by construction: there is no way to authenticate against this API without them, so there is no second door left to find. The raw reader is now `_creds_unchecked`, private to the guard, with a source guard stopping it becoming the next door.

It is deliberately **not** an `autouse` fixture — an autouse session fixture also fires for the static suites (`test_source_guards.py`, `test_deployment_profile.py`), which are documented to run with no instance up and which I broke exactly once by making it autouse. Gating authentication covers strictly more anyway: an unauthenticated test cannot write.

**The in-registry suite: `setUpClass` on a shared base, because there is no earlier point with an environment.** The obvious one-line answer is a `_register_hook` guard, and it does not work: Odoo runs a module's tests from inside `load_module_graph` (`odoo/modules/loading.py:279`), immediately after that module is upgraded and **long before `_register_hook` at STEP 9** (`loading.py:588`). A `_register_hook` guard runs after every test in the registry has already finished. The test loader imports `<module>.tests` at `odoo/tests/loader.py:61`, but at import time there is no cursor to ask with.

So all **39 first-party test classes across 13 modules** now derive from `CadraTransactionCase` / `CadraHttpCase`, and a source guard fails on any class that derives straight from a core base — matched on the AST, across all three spellings, **including a core base sitting second in a multiple-inheritance list**, which my first pass missed on two real classes in `test_callback_replay.py`.

### One acceptance criterion is NOT met literally, and here is exactly why

The handoff asks that the suite *"refuses before writing anything"*. **It refuses before writing anything to the register, and it does write one row before refusing.**

Classifying the database needs a bearer token, and `POST /auth/token` is not a read: `_session_payload` issues a refresh token, `myservice.api.refresh_token._issue` CREATEs it, and the request commits. So one refresh-token row lands in the target database before the refusal prints.

Closing it completely needs an unauthenticated classification route, and `cadra_route` has no public mode — auth is enforced in `cadra_endpoint` for every route in the API without exception. Adding one is a change to the central auth decorator, which is the "nine pre-envelope routes" backlog item's territory and not something to do in passing in a handoff about test safety. The row is operational, indistinguishable from any integration authenticating, and carries no fixture data.

**My conftest docstring said "minting a token is a read".** That sentence was false when I wrote it and the review caught it; it now says what actually happens. Flagged rather than quietly left, because a convenient sentence in a comment is how the last several of these started.

### The part worth reading: the guard leaked while I was proving it

**The first cut read the mark with `ir.config_parameter.get_param`, and during its own proof run it let 24 writing tests through against a database carrying no mark at all.**

`get_param` is `@ormcache`d **per worker**, and `config/odoo.19.conf` sets `workers = 2`. I deleted the parameter row, ran the suite, and got `24 passed`. Querying the route a moment later returned `database_class: "client"` — a value that had been set and then removed — while the worker the suite had hit was still answering `"test"`. Two workers, two stale answers, neither of them what the database held.

A guard served from a cache says yes about a state that has stopped being true, which is the entire failure class this handoff exists to close. `database_class()` now reads the row:

```python
env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (PARAM,))
```

`tests/test_source_guards.py::test_the_database_class_is_read_from_the_database_not_a_cache` fails if the cached reader returns, and its mutation proof exercises **the exact code that leaked** plus three cousins — including the case where the function reads neither the cache nor the row, which is the third way in. It is also written to distinguish prose from code: the first version of the guard flagged the docstring that explains why `get_param` is wrong.

That fact is now in `docs/ENVIRONMENT-FACTS.md` under its own heading, because it is not specific to this guard — anything a safety decision turns on must read the row.

### The credential that lies about itself

`is_test_credential` is what makes a fixture identifiable afterwards: it drives `nrs.asset.custody.source = 'test'`, which is why 330 custody rows self-label with nobody curating them. Handoff 23 minted `Handoff23 Approver` with a direct `create()` and the flag defaulted off — and its six approved disposals are the one class of artefact in `jaizbankplc` a reader cannot identify from the record itself.

Three things now close that, at three different depths:

1. **One fixture path.** `create_api_client()` **forces** the flag rather than defaulting it — a test has no legitimate reason to mint a credential that lies about itself. The seven direct `create()` call sites were rewritten onto it.
2. **A source guard** fails on any direct `create()` of `myservice.api.client` in a first-party test, matched on the AST so that `.sudo()` and `.with_context()` in the chain do not hide it. Its mutation proof is `test_approve_disposal_route.py:72` **as handoff 23 actually wrote it**.
3. **A session guard** refuses the whole HTTP run if the credential it authenticates with is unflagged.

A test that needs an *unflagged* credential to prove the flag's own behaviour toggles it on a record it already holds — which is what `test_custody_is_not_capped.py` already did, and the guard is written not to flag it.

---

## 2 · Whether CI needed an exemption

**No, and there is no CI branch anywhere in the guard.**

CI stamps the database it creates. `scripts/bootstrap.py` gained `ensure_database_class()`, and `.github/workflows/ci.yml` exports `CADRA_DATABASE_CLASS=test` before `bootstrap.sh` — so the statement "this is a test database" is *true* rather than waived.

**The trap in that, which is the reason it is not a one-liner: `scripts/bootstrap.sh` is also the production deploy path** (`README` §Deploy: `CADRA_PROFILE=prod scripts/bootstrap.sh`). Stamping `test` unconditionally inside bootstrap would have marked every client's live database as safe to write fixtures into — the exact inversion of the control this handoff builds. So the class is never inferred from anything but an explicit statement. All four branches measured against a real database:

| Environment | Result |
|---|---|
| `CADRA_DATABASE_CLASS=test` | `'test'` |
| `CADRA_PROFILE=prod`, no class named | `'production'` |
| neither — a developer's fresh tenant | `None`, nothing written, loud warning |
| `CADRA_DATABASE_CLASS=tset` | `ValueError: ... is not one of test, client, production` |

`production` on a prod profile is the one inference that cannot make the guard weaker. Everything else writes nothing and lets fail-closed do the work.

CI then **asserts the stamp landed** in its own step, so a missing mark reads as an unstamped database rather than as a broken guard.

### The suite now has somewhere legitimate to go

`test19` is marked `test`, carries a full credential pair at `docs/api/.creds.test19`, and its client is flagged `is_test_credential`. It is the documented target in `CLAUDE.md`, `tests/README.md` and `docs/ENVIRONMENT-FACTS.md`.

**Moving off a client's register exposed three hidden dependencies on that register, and all three were real defects:**

1. **`tests/test_locations.py` asked for `/api/v1/locations/1` outright**, in four tests. A row id is a fact about one database's insert order, not about the API. They now read a location off the register (`any_location`).
2. **`test_audit_logs.py` walked the access-report cursor at `limit=3` and asserted more than one page came back** — making the proof a function of how many users the tenant happened to have. At `limit=1` it proves the cursor on any register holding two accounts.
3. **`token_scopes()` was asked `"settings:read" not in scopes`, but `admin` is a wildcard in `require_jwt`** (`utils.py:236` says so in as many words). `test19`'s client holds `admin` and not `settings:read`, so the test took the 403 branch against a server correctly answering 200. Fixed in a new `token_grants()` helper rather than at the three call sites, because it is a class of error, not an instance.

All three are the lesson `token_scopes`' own docstring already carried, one level along: a per-tenant fact is not a fact about the API.

---

## 3 · What the removal script would do to `jaizbankplc`

`scripts/remove_test_residue.py`, **dry run by default** — `CADRA_APPLY=1` is the only way through, and a database marked `production` is refused before anything is read.

**The dry run MEASURES rather than predicts.** Every candidate is actually unlinked inside a savepoint which is then rolled back, so these are counts of deletions that really succeeded. That rule exists because the first version of this script did predict, from a model of the schema, **and the model was backwards** — see §6.

| | |
|---|---|
| fixture-named assets | **3,894 of 4,164** |
| → removable (trial-deleted, rolled back) | **3,779** |
| → refused by the rules | **115** |
| → refused by the database on a trial delete | 0 |
| fixture-named locations | **368 of 440** |
| → removable (trial-deleted, rolled back) | **255** |
| → refused by the rules | **17** |
| → **refused by the database on a trial delete** | **96** |

**Those 96 are the reason the trial delete earns its place.** They fail on `nrs_asset_transfer_from_location_id_fkey` — a foreign key from the transfer log that no reading of the model files predicted and that I would have reported as removable.

### What it refuses, and why none of it is negotiable

- **99 assets carrying a chain-of-custody row.** `nrs.asset.custody.asset_id` is `ondelete='restrict'` and `custody.unlink()` raises unconditionally, so the asset cannot be released at all while a link exists.
- **6 assets carrying an approved disposal** — `H23 disposal probe` (8396) and five `pytest-approval-*`. Deleting the record is not a reversal; it is the same fabrication one step on. The script points at `mark_test_fixtures.py` instead.
- **10 assets a service request points at**, and **17 locations** likewise. Neither `request.request.nrs_asset_id` nor `.generic_location_id` declares an `ondelete`, so the default `set null` applies: deleting the fixture would **succeed** and silently blank a real request's field. Report 24 measured 354 of 420 entries in the public homepage dropdown as fixtures, so a member of the public who chose one off it is not hypothetical.
- **352 custody rows `source: test` are never removed**, in any circumstance.

### Two things the script cannot identify, said out loud rather than counted as zero

**Service requests do not self-identify at all.** `request.request.name` is a sequence — `REQ-000692` — not a name the suite chooses, so a test-created request is indistinguishable from a real one by any rule this script could apply. There are 460 requests on `jaizbankplc` and report 24 counted roughly one created per session. **The script reports this in words and removes none of them.** It is the same defect class as the unflagged credential: a fixture that does not say it is one cannot be found later.

**The name patterns needed checking in both directions.** Odoo wraps a `like` value in `%…%`, so the first version's `('name', 'like', 'H23%')` was a substring match that would have claimed a real `PUMP-H23-4` as a fixture. Switching to `=like` fixed that — and simultaneously stopped matching **201 assets that genuinely are fixtures**, the `idem-asset-pytest-…` family the idempotency tests write with their own prefix in front. Both families are now declared, both anchored. Enumerating what was actually in the register found the second one; assuming would not have.

### Two things I checked rather than assumed

**`mark_test_fixtures.py` had not been run — and when the owner ran it, HALF of it silently did nothing.**

The handoff asked me to verify rather than assume, and this is what that was for. After the run, the six disposals were correctly disclosed and **the credential was still `is_test_credential = False`**. The script printed nothing at all about it — not a failure, not a "not found", nothing — so the output read as a clean run.

The cause: `Handoff23 Approver` is **archived** on `jaizbankplc`, and handoff 24's script searched for it with a plain `Client.search(...)`. Odoo's default `active_test` excludes archived records, so the search returned an empty recordset and the `for` loop never executed. Report 24 called both changes idempotent; one of them had never worked on this tenant and could not have.

Fixed here: the search takes `active_test=False` — an archived credential's artefacts are still artefacts, which is exactly why `nrs.asset.custody._is_test_credential_user` already searched that way — and the script now says so out loud when it finds no such client. Re-run and verified: `Handoff23 Approver` → `is_test_credential = True`, 6 of 6 disposals disclosed.

**This is the third instrument in two handoffs that reported success while doing nothing**, after report 23's unregistered test file and report 22's mutation proof asserting on a variable that never existed. The pattern is the same every time: a step that can find nothing and say nothing.

**A second correction from handoff 26, in §3 above.** The refusal bullet reads *"10 assets a service request points at, and 17 locations likewise"*. The 17 is right; the *"likewise"* is not. Measured on `jaizbankplc` on 2026-09-15, **zero** requests on that tenant set `generic_location_id` at all. All 17 locations are refused by the removal script's OTHER rule — they hold an asset the script will not remove. Which rule holds that asset, over exactly those 17 pairs in the script's own elif-chain order: **10 because a service request points at the ASSET, 5 because the asset carries an approved disposal, 2 because of a custody row** — disjoint, summing to 17. The script was right; the sentence describing it was wrong, which is the same shape as this report's own §6 lesson. (Handoff 26's FIRST attempt at this correction said all 17 were pinned by custody rows. That was also wrong, and was caught by its verification pass. Recorded because a correction nobody measured is how the original sentence got here.)

**The residue grew after report 24 measured it.** Report 24 counted 3,584 fixture assets of 4,056 on 2026-09-15; the same day, after that report's own verification runs, the register holds 4,164 assets. Measuring the problem did not slow it down, because nothing did until this handoff.

## 4 · C3's measurement, and what it decided

**Something writes it, so it is published.** `workflow_payment_ref` is written by the WorkSpace/Workflow approval callback at `myservice_workflow/models/request_request.py:319` and `:386`, and the request form tracks it (`request_request_views.xml:37`). It is not a dead column, so the ruling's other branch applies: a financial fact invisible to every role including the auditor belongs in the serializer.

It is now in `serialize_request` under a `workflow` block — **together with `workspace_ref`**, which sits on the same form and was invisible in exactly the same way. That second field is beyond what C3 named; I added it because it is the identical defect found while measuring the first.

**I attributed it to the wrong writer, in three places, and the review caught it.** `workspace_ref` is written by the **outbound send** path (`request_request.py:115`), not by the approval callback — and it is measured at **0 of 407** requests across every local tenant (`request_request.py:222` carries that measurement). Publishing it is still right; describing it as an approval-callback field was not, and a published key is permanent. The serializer comment, the changelog and the test docstring all now say which path writes which field and that a consumer should expect `null` from `workspace_ref`.

**A deviation worth naming:** C3 said the field *"belongs in the serializer under `financial`"*. `serialize_request` has no `financial` block — that is the asset serializer's shape — so it shipped under `workflow`. The ruling's intent is met; its literal wording is not.

**C1** — ruled, and `systemDomain` had no backing field, so its row is gone. The value was always `nrs.asset.domain`; what was wrong was the name it arrived under. It is `fmDomain` now, rendered under its own label for **every** asset rather than only IT ones (the FM domain is a fact about all of them), with the model's label via `useEnumLabel("domain")` rather than the bare key. The mock carried network identifiers like `ABJ-HQ-MST-233`, which is what kept the page looking right in development while a live tenant showed `it`; it now carries FM domain values, so the two render the same shape. `tsc --noEmit` is clean.

**C2** — the handoff named `v1_settings.py:134`; **a search found three sites**, the FM-domain refusals on both the POST and PATCH category routes and the logo-prefix refusal on brand settings. All three publish both keys now, with `allowed` deprecated in `docs/api/CHANGELOG.md` and removed at the next major version.

**D — closed, and nothing is genuinely open.** Report 23 §3 settled it: the `odoo`-on-the-line requirement is gone, replaced by an allow-list of the two non-Odoo `<major>.0` shapes, anchored so that `ODOO_VERSION: '15.0'` cannot exempt itself by containing the word `version`. The mutation proof reads `tests/fixtures/retired-gitlab-ci.yml` — the deleted `.gitlab-ci.yml` byte for byte — and finds three real offenders where the old logic found none. Report 24 §8 was carrying a stale item. Closed in the ledger.

---

## 5 · Suites, in CI's order

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) — `test19` | **811 passed, 9 skipped, 0 failed** |
| In-registry, CI's 11 modules, `test19` | **0 failed, 0 error(s) of 516 tests** |
| `tests/test_source_guards.py` standalone, no instance | **186 passed** |

**516 is report 24's denominator exactly**, so the guard costs no in-registry coverage.

**811 passed / 9 skipped, against report 24's 772 / 32.** The difference is the tenant, not the code: `test19`'s client holds `admin`, so **the 21 admin-scope skips are gone and those tests actually run**. The 9 remaining are 2 Turnstile-not-configured, 4 partition-data-absent (`is_verified`, `is_staff_bus`, `has_sap_code`, `closed`), 1 no active `workflow.config`, 1 no asset carrying a SAP asset number, and the documented `is_tagged` case. None is admin-scoped and none comes from a file this handoff touched.

---

## 6 · Wall-clock, and the correction share

**Roughly 4h30m**, most of it serialised against a stack that cannot take two registry loads at once.

**Correction share: about 55%, and it is the highest it has been for the right reason.** Two parallel investigation agents died on a session rate limit before returning anything, so the whole investigation ran in the main session. The one agent that did run was the **fresh verification pass at the end, and it found fifteen defects in work I had already called finished** — four of them serious enough that the handoff would have failed its own acceptance criteria.

### What the verification pass caught that I had missed

| | Found | Why it mattered |
|---|---|---|
| 1 | **`CADRA_DATABASE_CLASS` never reached the container.** `docker compose run` forwards only what the `environment:` block names, and neither that var nor `CADRA_PROFILE` was in it. | `ensure_database_class()` was **dead code on every real path**, and CI's new assertion step would have gone red on the first run. My "all four branches measured" table was measured through `exec -e`, which is not the path CI or a deploy uses. |
| 2 | **`CADRA_DATABASE_CLASS=test` outranked `CADRA_PROFILE=prod`** and silently downgraded an existing `production` mark. | `bootstrap.sh` does `set -a; . ./.env`, and a `.env` gets copied onto servers. A developer's `test` marking could have stamped a client's live database. The exact inversion the whole handoff exists to prevent. |
| 3 | **Gating `token` was not enough** — four tests authenticate through `creds` + bare `requests`. | `pytest tests/test_auth.py` against `jaizbankplc` ran **green**, guard never instantiated. My claim "there is no way to authenticate around it" was false. |
| 4 | **The removal script's cascade model was backwards.** Custody is `ondelete='restrict'` and refuses `unlink` outright; I had written that Odoo "will happily cascade" it. | `CADRA_APPLY=1` would have raised on the first asset and aborted mid-loop, and 3,815 "removable" was a number from an instrument that never attempted the operation it predicted. |
| 5 | Odoo's `like` is a substring match; `H23%` would have matched `PUMP-H23-4`. | A real asset classified as a fixture and deleted. |
| 6 | The credential guard **could not see `Client = env[MODEL]` then `Client.create(...)`** — verbatim the spelling this handoff had just removed from four files. | The guard written to stop the hole reopening was blind to it. |
| 7 | The base-class mutation proof's "core base sitting second" case put the core base **first**, so it passed for the wrong reason. | Report 22's failure mode exactly, in the guard written to avoid it. |
| 8 | `meta/database` identified the caller as "first client on this user", archived included. | Two clients on one user → reports the flagged one while the suite authenticates as the unflagged one. `Handoff23 Approver` with extra steps. |
| 9 | `common.py` claimed `super().setUpClass()` was "enforced by test_source_guards.py". **Nothing enforced it.** | A docstring asserting a protection the repo did not have. |
| 10 | The unflagged-credential remedy printed `search([])` — flag **every** credential, archived included. | A false self-label in the one mechanism this handoff defends. |
| 11 | `workspace_ref` attributed to the approval callback in three places; it is written by the outbound send path and is 0 of 407. | A published key is permanent. |

All eleven are fixed, each with a test or a proof where one applies. The base matcher also gained aliased imports, `*WithUserDemo`, and `rglob` for test subdirectories; the removal script gained the second fixture family and the trial-delete measurement.

### The two findings that were mine, from proving rather than writing

- **The guard read through an ormcache and leaked 24 writing tests** onto an unmarked database. Found only by insisting on the *absent* case rather than the two that were obviously going to pass.
- **The mechanical rewrite put the guarded import inside seven parenthesised multi-line imports**, because the insertion point came from a `startswith("from odoo")` line scan. A regex found the class bases; only the AST could place the import.

**The lesson, and it is the same one report 24 ended on.** I wrote "there is no way to authenticate around it" and "Odoo will happily cascade" — two confident sentences about systems I had not checked, in a handoff whose entire subject is a control that was trusted without being checked. The guard itself is sound. Everything that was wrong was a claim ABOUT it, and every one of those was caught by somebody reading it who had not written it.

## 7 · Open, and not mine to close

- **`scripts/mark_test_fixtures.py` and `scripts/remove_test_residue.py` are both owner-run** against `jaizbankplc`. **CORRECTED by handoff 26 — this section was stale and contradicted §3 of this same report.** `mark_test_fixtures.py` HAS been run there: §3 describes the owner running it, half of it silently doing nothing, the fix, and a verified re-run, and the database agrees — checked on 2026-09-15, `Handoff23 Approver.is_test_credential = t` and all six disposals carry the disclosure. §3 is the accurate section. Only `remove_test_residue.py` has never been run. Its dry run is in §3; run it dry first, read the refusals, then `CADRA_APPLY=1`. (A report that contradicts itself about whether an instrument ran is the subject of handoff 26 §B; it is corrected here rather than left for a reader to arbitrate.)
- **`cadra19`, `nrs19` and `gtb19` carry no class.** They refuse, which is safe, but nobody has decided what they are. **Measured and proposed in handoff 26 §C** — `nrs19` → `client` (a real NRS staff extract, 11,386 employees, Vendra's integration tenant), `cadra19` → `client` (seeded from real NRS contractor documents), `gtb19` → `test` (synthetic assets, public OSM branch coordinates, already carrying fixtures; the live GTB tenant is `gtb`). The evidence for each is in `docs/GO-LIVE.md` §7. The owner marks; nothing marks itself.
- **The 67 fixture assets with non-self-labelling custody rows** are unremovable by this script by design. If NRS wants them gone, that is a decision about append-only history, not a scripting problem.
- **`docs/api/.creds.test19` is gitignored**, like every creds file. Anyone else running the suite locally provisions and marks their own tenant; the refusal prints the command.
- **The nine pre-envelope routes** and **per-session test artefact paths** remain in the backlog, untouched here.
