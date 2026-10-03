# Handoff 46 — Report: everyone sees their own job

**Branch:** `fix/everyone-sees-their-own-job` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/46-evidence/` — `shots/` (every persona's landing page, full sidebar and an asset page, on `test19` and `jaizbankplc`, plus one or two typed hidden URLs each), `matrix-test19.json` / `matrix-jaizbankplc.json` (per persona, per sidebar item: drawn or not, and what the server answered), the seed / list / remove runs, the collision counts, the suites.

**Not in the handoff, and should have been — a "Needs the owner" block.** Three things in this handoff need the owner and nothing said so up front: the PR merge (the Builder cannot merge), the classification of `cadra19` / `nrs19` / `gtb19` (ruled on 2026-09-16, still not applied — the seed refuses an unclassified database, so those three have no personas), and the cluster (nothing here reaches it). They are in *Needs the owner* at the end.

## In plain words, first

**There are now six invented people on every local tenant that is allowed to hold them**, one for each job:

- Halima Danjuma, a store officer.
- Chukwudi Anyanwu, an asset manager.
- Nkechi Obiora, from the tag-issuing unit.
- Babatunde Olaniyan, a tagging officer.
- Zainab Garba, an internal auditor.
- Oluwaseun Ajayi, a systems administrator.

Sign in as any of them and you see that person's job. Their passwords are in one file per tenant on this machine, which is never committed.

**Nobody can mistake them for real staff, by three separate marks.**

- **The fixture label.** Each one is labelled a test fixture by the same rule that already labels everything the test suites create. Nothing types that label in; the system stamps it, and nothing can take it off.
- **The email domain.** Each address is on a domain that by internet rule can never belong to anybody.
- **An external id.** Each carries a tag only the seeding script uses.

**The demo also cannot write invented history onto a real register.** Anything one of these people does is labelled too: a move they ask for, an approval they give.

**None of them is an employee**, so none can hold an asset or appear on a staff list.

**The names were checked against the real staff before use.** The handoff's own example name, *Aisha Bello*, is four real employees on the NRS replica. The six names used match nobody on any of the nine local databases. The seed refuses to create anyone whose name a tenant's staff or contacts already carry.

**Three commands.**

- **seed** — puts them on. Running it twice changes nothing.
- **list** — says which accounts on a tenant are demo accounts.
- **remove** — takes them off. It shows what it would do first, and touches nothing it did not create. I planted a stranger on the demo domain and tampered with one persona's address: the remover refused both by name. Where a persona is named on a request or on an asset's history, it is switched off rather than deleted, because that record must keep the name.

**What each person sees.** Every menu item now carries the permission the server demands for it. I signed in as each person and, for every item:

- **An item they see**, the server answers.
- **An item they don't see**, the server refuses. I typed the address of every such item as that person.

That held for all 27 items, for all six people, on two tenants. Where they land after signing in:

- Five land on the asset register dashboard.
- The tag-issuing-unit officer alone lands on a page saying, in words, that their role opens nothing yet, and why.

Buttons inside pages follow the same rule now. A store officer opening an asset sees no Edit, Move or Verify. Typing a settings address shows that person the settings read-only.

**The finding the handoff hoped for: the roles do not fit the people.**

- **The store officer can't do a store officer's job.** She can look but cannot register an asset, request a move, or confirm one is there. The only role that can also approves other people's moves and changes the system's settings.
- **The tagging officer can confirm a label is on, but cannot print a new one or replace a faded one.**
- **Everyone who can see the asset dashboard also sees Fleet and Staff Bus.** One permission covers all of them.
- **The record of who was given which role is readable by every store officer.** The permission that lets them look up a staff member for custody also opens that record.

Those are for the Architect to decide. I have not invented a permission to paper over any of them.

**Two things found on the way.**

1. **The dashboard showed a refused person invented numbers.** That was 13,150 assets, from the sample data, to somebody the server had refused. It now shows a dash and the refusal.
2. **Registering an asset had been getting slower with every tag ever printed.** The system found the next tag number by counting through every number already used, one at a time, because it sorted *999* above *8305*. On the test tenant each new asset took about eleven seconds; now it takes a fifth of a second. The NRS replica (one tag prefix) and Jaiz (eight) were already paying this. Fixed, with a test that fails on the old code.

**Two things to know before a demo.**

1. Anything a persona creates is labelled a fixture for good — including a *real* person's account, if somebody onboards a colleague from a persona's session. Don't.
2. The permanent record of who was granted which role keeps the personas' grants after they are removed. That record is append-only on purpose.

## A · What was built

| | where |
|---|---|
| Seed, list, remove, and the wrapper that keeps passwords off the terminal | `scripts/seed_demo_personas.py`, `list_demo_personas.py`, `remove_demo_personas.py`, `demo_personas.sh` |
| An account that is a fixture is a test actor | `myservice_api/models/api_client.py` (`_is_test_credential_user`) |
| `is_test_fixture` on every user row (additive, 19.0.3.19.0) | `controllers/v1_users.py`, OpenAPI in `v1.py`, `docs/api/CHANGELOG.md` |
| The nav table with a scope on every item, `canOpen`, `landingPath` | `src/lib/navigation.ts` (moved out of `Sidebar.tsx`) |
| The front door: a stored session that cannot open `/` goes to its landing page | `src/App.tsx` (`Home`) |
| `/no-access`, in words | `src/pages/NoAccess.tsx` |
| In-page write controls hidden without their scope; write-only pages refuse; settings read-only | §C |
| No mock numbers to a signed-in person; the greeting and the avatar name the person | `pages/Dashboard.tsx`, `Sidebar.tsx` |
| A sign-in never inherits the previous account's scopes | `lib/auth.ts` (`storeToken`) |
| Access changes under *Audit*, opened to `identity:read` — the server's own scope | `navigation.ts`, `pages/admin/AccessChanges.tsx` |
| *Demo / test account* badge on the Users screen | `pages/admin/Users.tsx` |
| Tag numbering by arithmetic | `myservice_asset_register/models/asset_tag.py` |
| Guards | `tests/test_nav_scopes.py`, `tests/test_demo_personas_agree.py`, `myservice_api/tests/test_fixture_label_is_derived.py` (+2), `myservice_asset_register/tests/test_tag_number.py`, `e2e/tests/46-everyone-sees-their-own-job.spec.ts` |

## B · The personas

### Who, and why these combinations

| key | name | job title | roles | why |
|---|---|---|---|---|
| `storekeeper` | Halima Danjuma | Store Officer | Asset User | the handoff's storekeeper |
| `asset_manager` | Chukwudi Anyanwu | Asset Manager | Asset Manager | the approver every move needs |
| `tag_unit` | Nkechi Obiora | Tag-Issuing Unit Officer | Tag-Issuing Unit **alone** | one per role, as asked — kept as the evidence that this role alone opens nothing (§E.5) |
| `tagger` | Babatunde Olaniyan | Tagging Officer | Asset User + Tag-Issuing Unit | the tagger a person actually is (handoff 41's pairing) |
| `auditor` | Zainab Garba | Internal Auditor | Auditor | the handoff's auditor |
| `administrator` | Oluwaseun Ajayi | Systems Administrator | System Administrator + Asset Manager | the handoff's administrator; Asset Manager because the model's own approval check asks for it (`_may_decide`), and the wildcard scope alone is refused there |

Logins are `first.last@demo.example`; time zone `Africa/Lagos`; no `hr.employee`.

**For Vendra's paired handoff:** the same six names and the same domain were sent to the Vendra session running its handoff 46 (it was listed as busy), with the warning that the handoff's example name is four real NRS employees.

### Marked three ways — and the label is the repository's own

1. **`is_test_fixture`, derived.** The personas are created *by* `cadra_demo_personas`, an API credential flagged `is_test_credential`. It is archived at creation, has no secret and no scopes, and its user is archived too (`/auth/token` → 401, measured). `cadra.test.fixture.mixin` stamps each persona's partner exactly as it stamps anything a test credential creates. No third convention, no settable path.
2. **`demo.example`** — under RFC 2606's `.example`, which can never be delegated.
3. **`__cadra_demo__.persona_<key>`** — an `ir.model.data` namespace no module can own.

**What a persona does is labelled too.** `_is_test_credential_user` now also answers yes for an account whose partner is a fixture. Measured on `test19`:

- The Asset Manager persona asked for a move, with the administrator persona as approver: request 2111, `is_test_fixture = t`.
- The administrator persona approved it; the movement row it caused (14200) reads `source = test`.
- The Store Officer asking for the same move: 403.

### No collisions — per tenant, with counts (`46-evidence/collisions-before.txt`)

Measured before seeding. Name matches are every word of the name, case-insensitive, among employees / contacts; the personas' own partners are excluded.

| tenant | class | accounts | employees | employees with IR | on `@demo.example` | name matches |
|---|---|---|---|---|---|---|
| test19 | test | 213 | 110 | 107 | 2 (this handoff's, archived by the removal test) | 0 / 0 |
| boot44 | test | 36 | 6 | 5 | 0 | 0 / 0 |
| nrs | client | 5 | 1 | 0 | 0 | 0 / 0 |
| lasg | client | 12 | 60 | 60 | 0 | 0 / 0 |
| gtb | client | 12 | 60 | 0 | 0 | 0 / 0 |
| jaizbankplc | client | 19 | 61 | 61 | 0 | 0 / 0 |
| cadra19 | absent | 6 | 2 | 1 | 0 | 0 / 0 |
| nrs19 | absent | 11 | 11,386 | 0 (NRS's IR numbers are in `x_ir_number`, handoff 38) | 0 | 0 / 0 |
| gtb19 | absent | 12 | 61 | 1 | 0 | 0 / 0 |

- **IR numbers:** a persona has no employee, so it has no IR number to collide with.
- **Custody:** a custodian is an employee, so a persona can never hold an asset.
- **After seeding:** every `list` reports `linked to a demo persona: 0` and `carrying a persona's name: 0` on every tenant.

### The seed, twice, everywhere (`seed-every-tenant.txt`, `seed-after-fixes.txt`)

- **First run:** `test19`, `boot44`, `nrs`, `lasg`, `gtb` and `jaizbankplc` each created 6. On `test19` it was a re-seed after removal: 4 created, 2 reactivated.
- **Second run:** `created 0, updated 0, unchanged 6, passwords: none new` on every one.
- **Unclassified:** `cadra19`, `nrs19` and `gtb19` answered `REFUSED: this database's class is not set`, exit 1, nothing read or changed.
- **After the verification fixes:** run 1 archived each seeding user once; run 2 changed nothing.

### Listing on `nrs19` (`nrs19-copy-list.txt`)

`nrs19` is unclassified, so the seed refuses it, and classifying it is the owner's step (ruled 2026-09-16, `docs/GO-LIVE.md` §7). I did not apply it. To show the listing against 11,386 real employees, I copied `nrs19` into a throwaway database, `nrs19_h46copy`, classified **the copy** `client`, then seeded, listed and removed there, and dropped the copy afterwards. On the copy:

- **Demo personas:** 6 of 18 accounts, all three marks agreeing.
- **The rest:** 1 seeding credential and 9 real-looking accounts.
- **Employees:** 11,386, with 0 linked to a persona and 0 carrying a persona's name.

The real `nrs19`, listed read-only, shows 11 accounts and 0 personas.

### Removal (`test19-remove-dryrun.txt`, `test19-remove-apply.txt`, `after-fixes-cycle.txt`, `boot44-remover-refuses.txt`)

| where | dry run | apply | accounts |
|---|---|---|---|
| `test19` | delete 4, archive 2 (a move request names them) | deleted 4, archived 2; all six sign-ins → 401 | 217 → 213 |
| `nrs19_h46copy` | delete 6 + the seeding credential | deleted 6 | 18 → 11 — the original's 11 |
| `boot44` (after fixes) | — | deleted 6 + credential, then re-seeded from scratch | 43 → 36 → 43 |

- **Refusals, by planting:** I gave `boot44` a stranger on `@demo.example` and moved one persona's login off the domain.
  - The remover refused the persona by name and left the stranger untouched.
  - The listing flagged both as *MARKS DISAGREE*.
  - The seed refused to "repair" the tampered persona.
  - Both plants were undone.
- **After the verification fix (R4):** the `test19` dry run archives the administrator persona because it is *named as the actor on 1 movement row*. Before the fix it would have been deleted and that row's actor blanked.

## C · Each role sees its own job

### The rule

**Every item declares the scope the SERVER requires for what the page is for.**

- A read page declares its read scope.
- A page whose purpose is a change declares the write scope.
- The three Settings screens declare `settings:write`, because their reads are served under `assets:read` for other screens. The thing withheld is the change.

**Hidden must mean refused.** The spec proves it per persona, per item: drawn ⇒ the page's reads are answered; hidden ⇒ every probe is 403. The URL of every hidden item is typed as the person, and what the page asked and was told is kept.

### What each persona is drawn and where it lands (signed in, both tenants identical)

| persona | lands on | items drawn of 27 | hidden |
|---|---|---|---|
| Store Officer | `/assets` | 20 | + New Asset, + New Location, Bulk Import, the three Settings, Users |
| Tagging Officer | `/assets` | 20 | same seven |
| Internal Auditor | `/assets` | 20 | same seven |
| Asset Manager | `/assets` | 26 | Users |
| Systems Administrator | `/assets` | 27 | — |
| Tag-Issuing Unit alone | `/no-access` | 0 | all 27; typing `/` is sent to `/no-access` |

- **Every hidden read** answered 403 to the person.
- **Every hidden write probe** answered 403: `POST /assets`, `/locations`, `/asset-categories`, `/integrations/employees/import`, `PATCH /settings/branding`, `/settings/depreciation`.
- **Every drawn item's probes** answered 200, 400 or 404, never 403.
- **The write probes cannot write.** Each sends `{"h46_probe": true}` or id 0, so a holder is told *"Nothing was written"* or 404 (measured as admin first).
- `matrix-*.json` has every row.

### In-page controls (the sweep)

Hidden without their scope:

| page | controls | scope |
|---|---|---|
| Asset register dashboard, list | New Asset | `assets:write` |
| Asset page | the whole action bar: Edit, Move, Transfer, Verify, Mark found / missing, Condemn | `assets:write` |
| Barcode station | Generate, Replace tag | `assets:write` |
| Barcode station | Approve / Reject replacement | `approvals:write` |
| Barcode station | *Confirm affixed* | `tagging:write` only — the tagger keeps it |
| Locations | New / Edit, and the coverage report's *Add coordinates* | `locations:write` |
| Service-desk pages | write controls | `requests:write` |
| SAP Sync | *Bulk import* | `integrations:write` |

- **Whole-page refusals:** the asset, location and request forms and the bulk import render a *needs the X scope* panel.
- **Settings pages:** read-only with a one-line note.
- **The spec asserts it on an asset page and on Branding:**
  - Action bar drawn ⇔ `assets:write`: true for two personas, false for three.
  - Read-only note ⇔ no `settings:write`: true for three, false for two.
  - It waits on the workflow strip every reader is drawn, so a blank page fails.

### Screens no role maps onto — for the toggles handoff

| screen | why it has no role |
|---|---|
| Fleet Command, Fleet, Fleet Roster, Maintenance Readiness | on `dashboards:read`, the scope the asset dashboard needs |
| FM Operations, Security Operations (still off the sidebar) | same scope |
| Staff Bus | same scope, and it reads no API at all (mock) |
| Identity (clearance) | reads no API (mock); nothing for a server to refuse |
| Facility Command Center | cross-domain; still carries a hardcoded *All systems operational* pill |

## D · The landing screen

- **The owner's rule:** the asset register dashboard. `landingPath` tries `/assets`, `/assets/list`, `/locations`, `/hr/employees`, `/dashboards/fleet` against the nav table's own scopes, and falls back to `/no-access`.
- **Measured by signing in:**
  - five personas → `/assets`;
  - the Tag-Issuing Unit alone → `/no-access`, with *"The Tag-Issuing Unit role lets you confirm a label on an asset, but finding the asset needs Asset User as well."*
- **The spec records every URL the browser passes through.** That is how the first front-door redirect was caught going through `/no-access` on the way to `/assets` (§G).
- **For the Architect:** the tagger lands on `/assets` by the owner's rule, though the barcode station is their job. It is a one-line change.

## E · The roles do not fit the people — the evidence

Measured as the person (`matrix-*.json`, `job` rows).

1. **Asset User cannot change the register.**
   - **What she can't do:** the Store Officer gets 403 on `POST /assets`, `/assets/<id>/move` and `/verify`.
   - **The only role that can:** Asset Manager. It also grants `approvals:write`, `settings:write`, `integrations:write`, `locations:write` and `ingestion:write`.
   - **So:** a storekeeper able to register stock can also approve other people's moves and change the branding, the depreciation rules and the SAP integration.
   - **The gap:** there is no role between *reading the register* and *running it*.
2. **`identity:read` is two things.**
   - **Why Asset User has it:** for the employee picker a custodian needs.
   - **What else it opens:** `/reports/access-changes`, the record of who granted whom which role.
   - **So:** every Asset User can read the access record. The Auditor, whose job that is, had been unable to find it — the app showed it to administrators only. It is now drawn to whoever the server answers.
3. **`dashboards:read` is two things.**
   - **What it covers:** the asset dashboard's KPIs and every Fleet, Staff Bus, FM and Security screen.
   - **So:** every Asset User and Auditor is drawn Fleet Command, Fleet, Staff Bus, Fleet Roster and Maintenance Readiness.
4. **The tagger cannot issue or replace a tag.**
   - **What works:** Asset User + Tag-Issuing Unit confirms a label (`tag-affixed`).
   - **What doesn't:** `POST /barcode/generate` and `/tags/<id>/request-replacement` → 403. Both need `assets:write`.
   - **So:** the unit's own scope covers one step of its job.
5. **The Tag-Issuing Unit alone opens nothing.** `GET /barcode/lookup` and `/barcode/untagged` → 403 (handoff 41's finding, now on screen in words).
6. **The Auditor has reports with no screen.** These answer 200 to the auditor over the API, and the app has no page for any of them:
   - `/reports/configuration-changes`
   - `/reports/disposals`
   - `/reports/asset-register`
   - `/assets/export`

None of these is fixed here. Each is a decision about the role model, and the handoff said not to invent a scope.

## F · Found on the way

1. **The dashboard showed refused people mock numbers** — 13,150 assets and the sample category chart, because one refused read in `fetchTotals` sent all three tiles to the mock. Now "—" and the refusal.
2. **A sign-in could inherit the previous account's scopes.** `storeToken` wrote the scope only when non-empty. Now always written or removed.
3. **The sidebar chip said "admin scope" for an account with none, the avatar read "A" for everybody, and the dashboard greeted everybody as "Admin".** All three now name the person.
4. **Tag numbering walked every issued number past 999.**
   - **Cause:** a text sort; full account in `docs/DECISIONS.md`.
   - **Before:** ~11 s per `POST /assets` on `test19` — the HTTP suite reached 17 % in an hour.
   - **After:** 0.2–0.3 s.
   - **Real tenants:** one `nrs19` prefix and eight `jaizbankplc` prefixes are past 999.
   - **Test:** `test_tag_number.py`, failing first on the old code: *"410 not less than 120: creating one asset spent 410 queries…"* (`tag-number-fail-first.txt`).
5. **A local `.env.local` compiles an expired token into this machine's bundle.** A fresh local browser is "signed in" with no scopes until the first 401 (`docs/ENVIRONMENT-FACTS.md`). Left alone: it is the owner's file.
6. **Three write routes have no screen:** `approve-disposal`, `home/quick-submit`, `integrations/sap/employee-sync`.

## G · Verification

**The fresh verification pass** (an agent that wrote none of it) checked every claim above and found one defect and five risks.

**D1 — the spec's in-page check could pass on a blank page.**
- **Cause:** it waited on a button inside the gated bar and swallowed the timeout.
- **Fixed:** it now waits on the workflow strip every reader is drawn, with no catch.

**R2 — the remover deleted any claimed account on its external id alone.**
- **Fixed:** it now takes only the seeding credential's own user, by login, and refuses an unrecognised name.

**R4 — deleting a persona blanked the actor on asset history.**
- **Fixed:** such a persona is now archived.

**R5 — the landing rule ran only at sign-in.**
- **Fixed:** `/` now redirects a stored session that cannot open it.
- **What fixing it uncovered:** the first version sent every fresh local browser to `/no-access` before sign-in. The phantom session described in §F.5 has no scopes, and the redirect judged it.
- **How it was caught:** the spec's new record of every URL passed through.
- **Now:** the redirect acts only on a session the app stored; the sign-in trace reads `/app/ → /app/assets`.

**N6 — the name check was one contiguous substring.**
- **Fixed:** every word of the name, in any order.

**N8 — the seeding user was left active.**
- **Fixed:** archived.

**N5 — three static checks could pass on nothing.**
- **Fixed:** all three tightened, each proved to fail on a mutation.

**N1 — malformed report probes.**
- **Fixed:** the disposals probe was missing `from`, and the asset-register probe was added. Both answer the auditor 200.

**N2 — two asset-page notices pointed at buttons a reader no longer has.**
- **Fixed:** now said only to someone who has them.

**N4 — the cluster runbook named the wrapper.**
- **Fixed:** the wording now says the wrapper is local-only.

**Recorded, not changed — for the Architect:**
- **R1:** an account a persona creates is a fixture for good.
- **R3:** the access record keeps the personas' grants. It is append-only by design; the `@demo.example` login on each row says what it was.

**Checked TRUE by the pass:**
- **Passwords:** all 36 persona passwords grepped across the tree, 0 hits outside `docs/api/.personas.*` (gitignored, mode 600).
- **Seeding credential:** inert on every tenant.
- **Employees:** 0 linked to a persona.
- **Nav scopes:** all 27 items agree with the server on mount.
- **Write controls:** every one gated by its route's scope, with Confirm affixed on `tagging:write` alone.
- **Docs:** the counts in STATUS and DECISIONS match the evidence.

**Suites** (denominators; full output in `46-evidence/`)

| suite | where | result | denominator | file |
|---|---|---|---|---|
| HTTP (`pytest tests/`), CI's order: first | `test19` | **1,244 passed, 9 skipped, 0 failed**, 6 min 14 s; exit 0; no `of 0 tests` | 1,253 | `pytest-test19.txt` |
| in-registry, CI's module list, `--workers=0` | `test19` | **0 failed, 0 error(s) of 1,059 tests**; no `CRITICAL` | 1,059 | `inregistry-test19.txt` |
| browser, `46-everyone-sees-their-own-job` | `test19` | **7 passed** | 7 | `playwright-46-test19.txt` |
| browser, same spec | `jaizbankplc` | **7 passed**, 0 rows written (asset, change-request and parameter counts in the window: 0 / 0 / 0) | 7 | `playwright-46-jaizbankplc.txt` |
| static guards | — | `test_nav_scopes.py` + `test_demo_personas_agree.py` 14 passed, each mutated to fail first | 14 | — |
| `test_tag_number.py` | `test19` | old code **1 failed of 3** (410 queries) → new code **0 failed of 3** | 3 | `tag-number-fail-first.txt` |
| SPA typecheck | — | `tsc --noEmit` clean | — | — |

**The first full HTTP run failed 1 of 1,253:** `test_every_user_row_carries_every_key`. I added `is_test_fixture` to the user row and not to the suite's key set. The contract test did its job. Fixed in the same branch, with a new test that the label is a boolean on every row and true on every `@demo.example` person.

**The skip count moved 10 → 9, and the tenant changed, not the suite.** `test_user_lifecycle.py`'s *the user behind another credential* refusal needed a second API credential. The inert seeding credential is one, so it now runs (refusals only; it passed). `CLAUDE.md` is updated.

**Run time 37 min → 6 min.** That is the tag fix. An earlier run of the same suite on the old code was stopped at 17 % after an hour; that run is not counted.

**Standing sentence pass.** Every count in this report and in the doc entries carries its denominator. The *zero* claims are *0 of N*:

- *0 name matches* — on 9 of 9 databases.
- *0 employees linked* — of 110 / 6 / 1 / 60 / 60 / 61 employees on the six seeded tenants, and of 11,386 on the `nrs19` copy.
- *0 hits for any password* — 36 passwords.

## Needs the owner

1. **Merge the PR** (the Builder's permission layer refuses `gh pr merge`).
2. **Classify `cadra19`, `nrs19`, `gtb19`** with `docs/GO-LIVE.md` §7's three commands — ruled 2026-09-16 and still not applied — then `scripts/demo_personas.sh <db> seed` on each. Until then they have no personas.
3. **The cluster:** nothing here reaches it; §23.2 says how to run the three scripts there, and the passwords have to be lifted from the output by hand.
4. **At go-live:** `scripts/demo_personas.sh <db> remove`, read the dry run, then `--apply`, on every client tenant.
5. **Never onboard a real person from a persona's session** — they would be labelled a fixture for good (§G, R1).

## Commits

- `6ada631` docs: handoff 46 — everyone sees their own job
- `50f4708` feat(api): an account that is a fixture is a test actor; is_test_fixture on every user row
- `0906c1f` fix(assets): the next tag number by arithmetic, not by walking every issued number
- `23b4338` feat(scripts): demo personas — seeded, listed and removed, marked three ways
- `2b8d802` feat(app): each role sees its own job
- `5642ad4` docs: handoff 46 — decisions, status, go-live register, environment facts
- `ffc16c4` test: the user row's key set carries is_test_fixture; the label is a boolean and true on every demo persona
- `825b212` docs: report 46 — everyone sees their own job
- the commit that adds this list

**PR:** https://github.com/wmlmetro/Cadra/pull/104 (into `dev`).
