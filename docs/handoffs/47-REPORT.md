# Handoff 47 — Report: a role is a job

**Branch:** `fix/a-role-is-a-job` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/47-evidence/` — `matrix-test19.json` / `matrix-jaizbankplc.json` (the after-matrix, same spec as 46's; every typed URL's probe log is in the matrix), `shots/` (each persona's landing, sidebar and two typed hidden URLs per tenant — pruned to 46's precedent), `group-counts.txt` and `cred-scopes.txt` (the §2 counts, raw), the suites, the upgrade fan-out.

## In plain words, first

**Four permissions problems the last two reports measured are now fixed, and the fix is that each permission means one thing.**

1. **A new role exists: the Asset Officer.** Until today there was nothing between *can look at the register* and *runs the register*. A store officer could see her stock but not register an item, ask for a move, or record that she had checked something — and the only role that could do those things could also approve other people's moves, change the branding, the depreciation rules and the SAP integration. The Asset Officer is her job: register, request a move, verify. Not approve, not configure, not import. Administrators can grant it from the Users screen like any other role.

2. **The record of "who was given which role" now belongs to the people whose job it is.** It used to ride on the same permission as the employee picker, so every store officer could read it and the Auditor — whose job it is — could not find it. It now has its own permission, held by the Auditor and by administrators.

3. **Reading the asset dashboard no longer shows you the fleet.** One permission used to cover the register's figures AND every fleet, staff bus, facilities and security screen. They are now two. A store officer or an auditor sees the register's numbers and nothing about vehicles; a security officer sees the security dashboards and not the register's numbers.

4. **The tag unit can now do the tag unit's job.** Printing a label and replacing a faded one needed the *edit assets* permission — which the Tag-Issuing Unit deliberately does not have, and every Asset Manager did. So the unit could confirm a label was on but not print one, and the people who create asset records could print labels. Both are now the other way around: printing and replacing is the tagging permission; approving a replacement still needs a second person. **An Asset Manager can no longer print labels** — that is the ruling's intent, and the counts below say who that touches.

**Two screens of invented content left the menu.** Staff Bus and Identity (clearance) showed sample data built into the app to every new client. They are out of the sidebar (the pages still answer if you type their address, and the code stays). **NRS is owed a real clearance screen** — they asked for it by name — and that is recorded as owed, not dropped. The **"All systems operational" badge is deleted**: it was hardcoded and measured nothing.

**Nothing here reaches the cluster until the owner runs the upgrade Job,** and the role changes landed on every local tenant, so the persona matrix was re-run afterwards, as the handoff ordered.

## A · What was built

| | where |
|---|---|
| Two new scopes, `access:read` and `operations:read`; the Officer's and Auditor's grants; the Officer group in `SCOPE_GROUPS[assets:write]` | `myservice_api/controllers/utils.py` (19.0.3.21.0) |
| Access-changes report on `access:read` | `controllers/v1_audit.py` |
| Nine operational routes on `operations:read` | `controllers/v1.py` (fleet-command, 4× security, fleet/dashboard, fm/dashboard), `controllers/v1_fleet.py` (`/fleet`, `/fleet/<id>`) |
| Tag mint + replacement request on `tagging:write` | `controllers/v1.py` (`/barcode/generate`), `controllers/v1_tags.py` |
| `group_asset_officer` — ladder User < Officer < Manager, privilege, comments | `myservice_asset_register/security/asset_security.xml` (19.0.1.22.0) |
| Officer grantable over the API (the named fifth entry) | `myservice_api/models/access_guard.py` |
| Nav scopes: fleet screens → `operations:read`, Access changes → `access:read`; Staff Bus + Identity items removed | `src/lib/navigation.ts` |
| Keys retired, never reused | `controllers/v1_sidebar.py` (`SIDEBAR_RETIRED`) |
| Station Generate / Replace on `tagging:write` | `src/pages/BarcodeStation.tsx` |
| The pill deleted | `src/pages/Dashboard.tsx` |
| Scope words for the two new scopes; AccessChanges gate on `access:read` | `src/pages/admin/Users.tsx`, `src/pages/admin/AccessChanges.tsx`, `src/hooks/use-scopes.ts` |
| Contract pins (openapi + `/roles`) | `tests/test_role_is_a_job.py` (new) |
| The rulings driven as the people, in-registry | `myservice_api/tests/test_asset_officer_role.py` (new) |
| Static guards for the splits and the ladder | `tests/test_login_scopes.py` (§47 block) |
| Docs | `docs/api/CHANGELOG.md` (BREAKING entry), endpoint reference, demo guide, `INT-10-audit-access.md`, `DECISIONS.md`, `STATUS.md`, `GO-LIVE.md` §25, `CLAUDE.md` |

**What a ruling did NOT get:** no new scope was invented for ruling 3 — the Officer composes `assets:write` onto Asset User's reads, exactly as instructed. Rulings 1's two splits each DID mint a scope string, which is what "split" means; both are announced as BREAKING.

**The `operations:read` name.** Not `fleet:read`, because the security and FM dashboards take it too and a security screen on a fleet scope is the one-name-two-meanings defect again. One collision was accepted knowingly: the sidebar has a GROUP key `operations` (the Locations screens, handoff 48). A switch key is not a scope and the two tables say so at both declaration sites; recorded in `DECISIONS.md`.

## B · Who is affected, per tenant (§2)

Group members are DIRECT memberships (implication writes no rows on 19 — handoff 24). Raw rows in `47-evidence/group-counts.txt`.

| tenant | Asset User | Asset Manager | Auditor | TIU | Identity Mgr | Security Off | Bus User |
|---|---|---|---|---|---|---|---|
| cadra19 | 2 (1 active) | 2 (2) | 0 | 0 | 1 (1) | 2 (2) | 0 |
| nrs19 | 4 (3) | 5 (4) | 0 | 3 (2) | 1 (1) | 1 (1) | 0 |
| gtb19 | 1 (1) | 2 (2) | 0 | 0 | 1 (1) | 1 (1) | 0 |
| test19 | 136 (6) | 61 (8) | 1 (1) | 26 (6) | 1 (1) | 1 (1) | 0 |
| nrs | 3 (3) | 4 (4) | 1 (1) | 2 (2) | 1 (1) | 1 (1) | 0 |
| lasg | 3 (3) | 4 (4) | 1 (1) | 2 (2) | 1 (1) | 1 (1) | 0 |
| gtb | 3 (3) | 4 (4) | 1 (1) | 2 (2) | 1 (1) | 1 (1) | 0 |
| jaizbankplc | 5 (4) | 5 (5) | 2 (1) | 3 (3) | 1 (1) | 1 (1) | 0 |
| boot44 | 17 (4) | 15 (5) | 2 (2) | 15 (4) | 1 (1) | 1 (1) | 0 |

**What each split does to each of them:**

- **Asset Users and Auditors lose the fleet screens** (`dashboards:read` no longer opens them) **and Asset Users lose the access record** (`identity:read` no longer opens it). Nobody among them uses either: the real NRS register holds **0 vehicles of 11,951 assets**, every vehicle on every other tenant arrived in one bulk load (report 48 §C), and the access record being readable by store officers was finding §E.2, not a workflow.
- **Asset Managers lose tag minting and replacement** (`assets:write` no longer opens them). Who that is: the active managers counted above, per tenant — 2 / 4 / 2 / 8 / 4 / 4 / 4 / 5 / 5. What they keep: everything else they had, `assets:write` now arriving via the implied Officer. **If a real manager at a client is also the person who prints labels, that person needs the Tag-Issuing Unit role added** — one grant on the Users screen, and the handoff's own ruling says the pairing is the design.
- **Auditors gain `access:read`** — the report they could not find is now theirs; no auditor loses anything.
- **Security Officers and Bus Users swap `dashboards:read` for `operations:read`:** they keep every screen that is their job and lose the asset register's figures. Active holders: 2 on `cadra19`, 1 on each of the other seven; 0 bus users anywhere.

**API credentials** (`47-evidence/cred-scopes.txt`; the `admin` wildcard covers every split, so admin-scoped credentials are untouched):

- **Affected, non-admin, active:** `test_client` on `gtb19`, `nrs`, `lasg`, `gtb` (identity:read + dashboards:read + assets:write, no tagging) — each loses the access report, the nine operational routes, and tag mint/replace; `jaizbankplc`'s `test_client` the same except it holds `tagging:write`, so it keeps the tag routes. All five are **our own suite credentials on tenants the suite refuses anyway** (`client`-class databases), not integrations.
- **`vendra` on `nrs19` and `boot44`** holds `assets:write` and not `tagging:write`: it loses `/barcode/generate` and `/tags/<id>/request-replacement`, **neither of which INT-03 calls** — Vendra registers assets and `POST /assets` mints the tag server-side. No Vendra flow changes; the CHANGELOG entry says so to them directly.
- **`tag_issuing_unit` on `nrs19` and `boot44` GAINS** mint and replace — the unit's credential can now do the unit's whole job, which is ruling 2 verbatim.
- Nobody's credential row was edited: the counts say who the OWNER must touch if a non-admin credential is ever pointed at a moved route (`GO-LIVE.md` §25, owner item).

## C · The rulings, driven

**In-registry, as three real people** (`myservice_api/tests/test_asset_officer_role.py`, real `/auth/login` tokens, 6 tests):

- **The officer registers** (`POST /assets` → 201), **asks for a move** (`/move` with the manager as approver → 200, `pending_approval: true`), **verifies** (`/verify` → 200, `last_verified_by` = the officer).
- **The officer is refused, at the scope gate, naming the scope:** branding and depreciation settings (`settings:write`), the employee import (`integrations:write`), somebody else's approval and a disposal approval (`approvals:write`), the tag printer (`tagging:write`), creating a location (`locations:write`) — 7 doors, 7× 403.
- **The officer cannot be the approver:** a move naming the officer as `approver_id` is 400 — `APPROVER_GROUP` is still the Asset Manager, so the role composes nothing of handoff 35's two-person rule away.
- **The tagger mints and requests replacement on `tagging:write`** — label minted, moved to `pending` with the manager named.
- **The manager is refused both tag routes** — the BREAKING half, measured: 403 naming `tagging:write`.
- **The officer is refused the access record** (403 naming `access:read`) **and the fleet dashboard** (403 naming `operations:read`) **and still reads the register's figures** (`/dashboard/kpis` → 200).

**At the contract** (`tests/test_role_is_a_job.py`, 6 tests): the nine operational routes declare `[operations:read]` and the three register-figure routes `[dashboards:read]`; the two tag routes declare `[tagging:write]` and the two decisions `[approvals:write]`; `/roles` publishes `asset_officer` — grantable, delta exactly `["assets:write"]`, implying `asset_user`, implied by `asset_manager`. The access report's pin moved in its own suite (`test_audit_logs.py` → `["access:read"]`).

**In the browser, as the six personas** — §D.

## D · The matrix, after, against 46's

The 46 spec re-ran unchanged in its logic (drawn ⇒ answered, hidden ⇒ every
probe 403, every hidden URL typed as the person) on the same two tenants.
**Both tenants answer identically.** The before-matrix is 46's
(`46-evidence/matrix-*.json`), taken before handoff 48, which is why the
administrator "gains" the Sidebar item — that is 48's, not this handoff's.
The item count moved 27 → 26: handoff 48 added Sidebar (+1), this handoff
removed Staff Bus and Identity (−2).

| persona | drawn, before → after | lost | gained | lands |
|---|---|---|---|---|
| Store Officer | 20 → 13 | the 4 fleet screens, Access changes, + the 2 removed items | — | `/assets` |
| Tagging Officer | 20 → 13 | same seven | — | `/assets` |
| Tag-Issuing Unit alone | 0 → 0 | — | — | `/no-access` (ruling 4: the pairing stands) |
| Asset Manager | 26 → 19 | same seven | — | `/assets` |
| Internal Auditor | 20 → 14 | the 4 fleet screens + the 2 removed items — **keeps Access changes** | — | `/assets` |
| Systems Administrator | 27 → 26 | the 2 removed items | Sidebar (48's) | `/assets` |

**Every hidden item was typed as the person and every probe behind it
answered 403** — the spec fails otherwise, and it passed 7/7 on both
tenants, first run. The rows that tell the rulings' story:

- **Access changes**: hidden from the Store Officer and probed 403
  (`access:read`); still drawn to the Auditor and answered 200. Before, it
  was drawn to both and the Auditor's §E.2 complaint stood.
- **The tagger's job probes** moved `POST /barcode/generate 403 → 400` and
  `POST /tags/0/request-replacement 403 → 404`: the scope gate OPENED (the
  400/404 are the probe body and id 0 — nothing written), where before the
  unit's own job refused it.
- **The Store Officer's job probes are unchanged** (`POST /assets`, `/move`,
  `/verify` → 403): the personas keep their 46 roles on purpose, so the
  before/after compares the scope moves and nothing else. The role that
  fixes her job is the Asset Officer, driven in §C; **whether the demo's
  storekeeper persona should be re-seeded as an Asset Officer is the
  Architect's call** — it is a one-line change to the seed and it would
  make the demo show a storekeeper doing a storekeeper's job.

## E · Found on the way / deviations

**The fresh verification pass** (an agent that wrote none of it, reviewing
the diff against the handoff and `CLAUDE.md`) found one risk worth the
Architect's eyes, one rationale the rulings had silently falsified, and
three stale comments. All fixed or recorded in the same branch
(`fix:` commit); what it checked and found TRUE is at the end.

1. **`GET /dashboard/map` hands the identified fleet roster to
   `dashboards:read` holders.** The route stays on the register's scope
   because it backs the register dashboard's map — but its payload carries
   one row per geocoded VEHICLE, plate and driver included. So an Asset
   User refused `/fleet` still reads the fleet through the map. My own
   comment claimed the kept routes "identify nothing"; that was false for
   this one and is corrected. Splitting the payload is a BREAKING
   serializer change and a question about what the register map is for —
   **recorded `[open]` for the Architect in `GO-LIVE.md` §25**, per the
   standing rule not to invent a fix for a role-model finding.
2. **Ruling 2 falsified the who-may-approve rationale for tags, and nothing
   said so.** Every approval refusal read *"an approver must be somebody
   who could have made the change themselves."* For moves that is still
   true (a Manager implies the Officer). For a TAG replacement it is now
   deliberately false: the requester (the unit, `tagging:write`) and the
   decider (management, `approvals:write`) are disjoint pools — a stronger
   separation. The tag flow's refusals now say *"must hold the Asset
   Manager role"*, and `APPROVER_GROUP`'s docstring records both halves.
3. **Three stale comments** the diff created: the station scope's words on
   the Users screen ("Confirm a label is affixed" → it now mints and
   replaces too), `use-scopes.ts`'s "the unit's ONE write" (three now), and
   a changelog sentence naming a staff-bus *route* that does not exist (the
   Staff Bus screen was mock; only the scope's screen family includes it).
4. **A risk for the owner, not fixed here:** an `assets:write` credential's
   user currently holds `group_asset_manager` (the old `SCOPE_GROUPS`
   mapping) and is therefore nameable as an approver. On its next scope
   edit it becomes an Officer and ineligible — any pending request naming
   it would strand, the handoff-43 shape. No credential is named approver
   on any local tenant today (approvals are personas' and people's), but
   it belongs on the owner's checklist with §B's counts.

**Checked TRUE by the pass** (its full report is in the session, summarised):
the ruling-1 route inventory is complete both ways (the nine moved, the
three kept, no access/role data under `identity:read` anywhere); ruling 2
has no missed mint/replace door (the back-office station route is
administrators-only by handoff 45's session guard); the Officer has no
reachable door to approving, configuring, importing or tagging — no ACL
rows, not `APPROVER_GROUP`, every refusal driven; nothing silently widened
(every grant added is a ruled one, every other change is a named
narrowing); the retired sidebar keys are refused by the PATCH, held by the
catalog guard, and the routes stay served; the changelog's factual claims
match the code (including "POST /assets still mints server-side" —
`_generate_tag(source='auto')` in `nrs.asset.create`); no commit carries
any AI attribution; and none of the new tests can pass vacuously.

**Deviations from the handoff: none.** The six personas keep their 46
roles (the handoff's §2 compares "their permissions moving underneath
them", which re-roling would have muddied); the question of re-seeding the
storekeeper persona as an Asset Officer for the demo is raised in §D for
the Architect rather than decided here.

## F · What the pill would need to be real

The deleted badge claimed "all systems operational" to every viewer of the front door. A true version needs a server-side health answer the page can read with the viewer's own token — at minimum: the registry answered (which the page's other reads already prove), the scheduler's last heartbeat (`ir.cron` last-run ages), and the INT-05/INT-09 outboxes not backed up (pending-row age). None of that exists as a route today; it would be a new `GET /api/v1/meta/health` with a scope decision of its own, and the day before a demo was the wrong day to invent one. Until somebody builds that, no badge.

## G · Suites, with denominators

CI's order: the HTTP suite first, then the in-registry suites. Evidence
files beside this report.

| suite | where | result | denominator | file |
|---|---|---|---|---|
| HTTP (`pytest tests/`) | `test19` | **1,283 passed, 9 skipped, 0 failed**, 7 min 46 s; no `of 0 tests` | 1,292 | `pytest-test19.txt` |
| in-registry, CI's module list, `--workers=0` | `test19` | **0 failed, 0 error(s) of 1,066 tests**; 0 `CRITICAL`. The FIRST run said **2 failed of 1,066**: two pins asserting a manager's effective roles are exactly `[asset_user, asset_manager]` — the ladder correctly extends them; both pins moved with the ruling and the full list re-ran clean | 1,066 | `inregistry-test19.txt` |
| — after the verification fixes (message changes): tag replacement + officer classes | `test19` | **0 failed, 0 error(s) of 23 tests** | 23 | — |
| browser, `46-…` (the matrix) | `test19` | **7 passed**, first run | 7 | `playwright-46-test19.txt` |
| browser, same spec | `jaizbankplc` | **7 passed**, first run | 7 | `playwright-46-jaizbankplc.txt` |
| browser, `48-…` (the switches, with `staff_bus` retired) | `test19` / `boot44` | **4 passed** each | 4 + 4 | `playwright-48-*.txt` |
| browser, `01-navigation` (nav items edited; the two routes still serve by address) | `test19` | **31 passed** | 31 | `playwright-01-test19.txt` |
| static guards | — | `test_login_scopes` (incl. the four §47 guards) + `test_nav_scopes` + `test_sidebar_catalog`: **21 passed** | 21 | — |
| targeted HTTP re-run after the verification fixes (tags, contract pins, login scopes) | `test19` | **64 passed** | 64 | — |
| SPA typecheck + build | — | `tsc --noEmit` clean; `BASE_PATH=/app/` build rebuilt and served | — | — |
| module upgrade, `myservice_api` 19.0.3.21.0 + `myservice_asset_register` 19.0.1.22.0 | 9 databases | 9 of 9 `Modules loaded.`, 0 `CRITICAL` | 9 | `upgrade-fanout.txt` |

**The skip count is 9 of 1,292, the same nine categories as handoffs 46 and
48** — nothing this handoff touched adds or removes a skip.

**Standing sentence pass.** Every zero above carries its denominator. The
§B zeros: *0 bus users* — of the 9 local databases' membership tables; *0
vehicles* — of 11,951 assets on `nrs19` (report 48's measurement, which §B
leans on); *0 name/credential rows edited* — of the 21 credentials listed
in `cred-scopes.txt`.

## Needs the owner

1. **Merge the PR** — the Builder's permission layer refuses `gh pr merge`.
2. **The cluster:** nothing here reaches it. After merging, run the `cadra-upgrade` Job (all tenants) — both modules changed, so until it runs the cluster keeps the old scopes and the old sidebar.
3. **Credentials, when it matters:** no credential row was edited. If a non-admin credential is ever meant to read the access report, the operational dashboards, or mint/replace tags, add `access:read` / `operations:read` / `tagging:write` to its row (§B lists exactly who holds what today).
4. **A manager who really does print labels** at a client needs the Tag-Issuing Unit role added to their account — a Users-screen grant, and the pairing is the documented design.
5. **Still outstanding from 46:** `cadra19`, `nrs19`, `gtb19` are unclassified (ruled 2026-09-16, not applied), so they still have no personas.

## Commits

<!-- COMMITS -->
