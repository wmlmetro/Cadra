# Handoff 48 — Report: what this tenant has

**Branch:** `fix/what-this-tenant-has` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/48-evidence/`:

- `shots/` — the Sidebar screen before and after, the sidebar as the Store Officer, and a hidden address typed, on `test19` and `boot44`.
- `matrix-test19.json` / `matrix-boot44.json` — what was drawn, what was typed and what came back, the refusals, the rows in Postgres and the report rows.
- The suites, the module upgrade on every database, and the static guards failing first.

## In plain words, first

**An administrator can now decide which menu items their organisation sees.** There is a new screen, *Settings → Sidebar*, with a switch for every item in the left-hand menu and one for each group of items. Fleet means nothing to a tenant with no vehicles, so that tenant can switch Fleet off and nobody there sees it again.

**Two questions now decide whether somebody sees a menu item, and both must be yes:**

1. **Does this organisation use it?** That is the new switch, set per tenant by an administrator.
2. **Does this person's role open it?** That is handoff 46's rule, unchanged.

Switching Fleet on does not show it to a store officer whose role cannot open it. A store officer whose role does open Fleet does not see it on a tenant that has switched it off.

**This is not a security control, and the screen says so before anything else.** Switching an item off only stops it being drawn. Anybody whose role allows it can still type the page's address, and the data still comes back. I proved that on purpose:

- On `test19`, I switched *Employees* off. Typing its address returned the staff list, as the administrator and as the Store Officer.
- On `boot44`, I switched *All Assets* off. Typing its address returned 200 assets to each of them.

The first line of the screen reads *"This changes what is shown, not what is permitted."* What a person may do is decided by their role. If a tenant must never have a module, that module has to be uninstalled; a switch is not the place to do it. A test fails if anything on the server other than this screen's own route ever reads these switches.

**Everything is on by default.**

- **No tenant lost anything the day this shipped.** Before the first switch, 0 of 9 local databases had a single setting.
- **A menu item added in future appears automatically.** It does not sit hidden until somebody notices it.

**Groups work like a main switch on a wall.**

- **Off:** switching *Fleet & Transport* off hides everything in it, but leaves each item's own switch exactly where it was.
- **Back on:** switching the group back on brings back exactly what was showing before.
- **On the screen:** an item hidden only because its group is off says so.

**You cannot lock yourself out.** The Sidebar screen is where these switches are changed. So neither that screen nor the *Settings* group it sits in can be switched off.

- The server refuses either change and writes nothing, even when other switches are in the same save. I compared the stored settings before and after: they were identical.
- The screen shows those two switches greyed out with a padlock.
- If somebody forces the setting into the database by another route, it is ignored.
- Everything else can be switched off, *Users* and the whole *Administration* group included. Each can be switched back on from the Sidebar screen, which is always there.

**Every change is on the record.** Each switch is its own entry in the configuration-change report the auditors already have. Signed in as the Auditor persona, I read the report and it named the administrator who flipped each switch.

**What I think should not be in the sidebar at all** (the question in the handoff's §3):

1. **Staff Bus and Identity (clearance) are not real.** Neither reads anything from the server. Both show sample data built into the app. Because everything defaults to on, every new client is shown two screens of invented content. They should come out of the menu until there is something real behind them.
2. **Fleet has no real vehicles anywhere.** The real NRS register holds 0 vehicles. On every other local database, every vehicle came from one bulk load on one day. No client has ever put a vehicle into Cadra. Whether fleet is part of this product at all is a question for NRS.
3. **IT Assets Command is just a filtered list.** It is the register showing one category: 69 of 11,951 assets on the NRS register, and 0 on five of the eight local databases.
4. **The front-door dashboard reports something it does not check.** It still shows a hardcoded *"All systems operational"* badge. Either it measures something or it goes.
5. **SAP Sync is real but empty.** All 11,386 NRS staff are at *never synced*. It earns its place when the SAP feed goes live.

**One defect found by the review and fixed.**

- **What happened:** a malformed save, such as `"groups": false` sent beside a valid switch, was quietly ignored. The valid part was saved, with no error.
- **Now:** it is refused, with a test.

## A · What was built

| | where |
|---|---|
| `GET /api/v1/settings/sidebar` (any signed-in caller), `PATCH` (`admin`) | `myservice_api/controllers/v1_sidebar.py` (new), `myservice_api` 19.0.3.20.0 |
| A stable `key` on every nav item and group, and the new *Sidebar* item | `src/lib/navigation.ts` |
| The two-axis filter: `drawnGroups`, `tenantShows`; landing that prefers a shown page | `src/lib/navigation.ts`, `src/hooks/use-tenant-sidebar.ts` (new), `pages/Login.tsx`, `pages/SetPassword.tsx` |
| The screen | `src/pages/settings/Sidebar.tsx` (new), routed at `/settings/sidebar` |
| The sidebar reads the switches | `src/components/layout/Sidebar.tsx` (`data-nav-key` on every item) |
| Guards | `tests/test_sidebar_catalog.py` (static, new), `tests/test_sidebar_settings.py` (HTTP, new), `tests/test_nav_scopes.py` (parse widened for `key:`), `e2e/tests/48-what-this-tenant-has.spec.ts` (new), the 46 spec's probe table (+ `/settings/sidebar`) |
| Docs | endpoint reference §13, `CHANGELOG.md`, `DECISIONS.md`, `STATUS.md`, `GO-LIVE.md` §24, `CLAUDE.md` |

### The four things the handoff said to get right

**1. The identifier.**
- **What it is:** a literal `key` declared once on each item and group in `lib/navigation.ts`, and again in `SIDEBAR_GROUPS` on the server. It is not the label, the path or the scope.
- **Why it is stable:** a label is reworded, a path re-routed and a scope re-ruled, and handoff 47 is about to re-rule several. A key derived from any of those would switch a tenant's hidden item back on the day it changed. This key changes only when somebody edits the key itself.
- **The guard** (`test_sidebar_catalog.py`) holds three things:
  - the two tables are identical in keys, grouping and order;
  - every key ever published stays in the table or moves to `SIDEBAR_RETIRED`, and a retired key is never reused;
  - since the verification pass, every live key must be listed as published, so a key added later is protected too.
- **Path lost** because a route move would silently un-hide the item.
- **Label lost** because two items are both called *Depreciation*.

**2. Default on.** Absent means on.
- **Only the exact word `off` hides anything.** An unrecognised value leaves the item on.
- **The app hides only what the server lists.** If the server cannot be read, nothing is hidden. That covers a frontend rolled out ahead of its backend, where the route answers 404.
- **Untouched tenants, measured:** on `boot44` before the spec ran, 0 sidebar rows of 25 configuration parameters, 0 of 38 switches configured, nothing hidden. On `test19`, 0 rows of 27.

**3. Groups.**
- **The rule:** a group is a master switch. An item is shown when its own switch and its group's are both on.
- **Why this rule:** the alternative, where an item switched on overrides its group, gives you a group switch that sometimes does nothing. Nobody can predict that from the screen.
- **Where it is proved:** both directions, in `test_a_group_is_a_master_switch` and `test_an_item_off_under_a_group_off_stays_off_when_the_group_returns`.

**4. The configuration-change report, not the access record.**
- **Storage:** one `ir.config_parameter` row per switch (`cadra.sidebar.item.<key>` / `.group.<key>` = `on`/`off`).
- **Why one row per switch:** the report can only name who LAST wrote a row. With all switches in one row, a second administrator would be reported as the author of the first one's changes.
- **Never deleted:** switching back on writes `on` rather than deleting the row, because a deleted parameter leaves no tombstone in that report.
- **No empty changes:** switching on something nobody ever switched off writes nothing.
- **Redaction:** none of the 38 keys trips the report's credential redaction (checked against its three patterns, 0 of 38).

### The trap: the lockout, and where I drew the boundary

- **What is guarded:** exactly what draws the switches' own screen, which is the item `sidebar_settings` and its group `settings`.
  - The PATCH refuses either going off, 400, before anything is written.
  - The GET reports both as locked and on whatever a row says, so a row put there by the back office or a shell hides nothing.
  - The guard ties the lock to the item whose path IS `/settings/sidebar`, so moving the screen moves the lock.
- **Proved, not assumed:**
  - **Refused at the API** with the administrator's own token, three bodies. The third body carries a legitimate switch beside the locked one, and the rows in Postgres were byte-identical before and after.
  - **Disabled on the screen.**
  - **Over HTTP:** four refused bodies, each followed by a read showing nothing changed, plus switching the two locked switches ON, which is accepted and changes nothing.
- **The adjacent cases:**
  - **A group containing Settings** is the Settings group, and it is locked.
  - **The only route to the administration screens:** Users and the Administration group CAN be switched off. Users then opens only by its address until it is switched back on from the Sidebar screen, which is always drawn.
  - **The boundary I chose:** guard what is needed to undo any switch, and nothing more.
- **Not guarded, and not this handoff's to guard:** an administrator removing their own `admin` role. That is the role model's business; handoff 42 refuses self-grants, not self-removal.

## B · Verification

### The handoff's list, item by item

| asked | where proved | result |
|---|---|---|
| Setting changed and effect seen, administrator then persona, two tenants, different items off | spec tests 1 and 2 | `test19`: the *Fleet & Transport* group + *Employees* off. `boot44`: *All Assets*, *Maintenance Readiness*, *Asset Categories* off. The administrator's sidebar lost them at once, without a reload; the Store Officer signed in and never saw them |
| A disabled item's URL typed, data still returned | spec tests 1 and 2, `test_a_hidden_item_still_answers` | `test19` /hr/employees → `GET /api/v1/identity/employees` 200, 122 rows; `boot44` /assets/list → `GET /api/v1/assets` 200, 200 rows — each as the administrator AND as the Store Officer, none 403; the spec now fails on a 200 with no rows. Over HTTP: *All Assets* off, `GET /assets` returns the same ids before and after |
| Both axes | spec test 2 | Switched on for the tenant but the role does not open it: *Users*, *Sidebar* and *+ New Asset* are not in `hidden_items` and are not drawn for the Store Officer. Opened by the role but switched off for the tenant: the plan's items are not drawn. Both on: drawn |
| Lockout refused | spec test 1, HTTP suite | 400 ×3 in the browser session, rows unchanged; 4 refused bodies over HTTP, each read back unchanged |
| Configuration-change report shows who changed what | spec test 3 (as the Auditor), HTTP | Every switch the plan touched has a row, `current_value: off`, `last_written_by: Oluwaseun Ajayi` (the administrator persona). The HTTP test checks the suite's own user |
| Default-on on a never-touched tenant | spec test 0 | `boot44` and `test19`: 0 rows, 0 of 38 switches configured, nothing hidden. 0 rows on 9 of 9 local databases before the first switch |
| Suites with denominators, standing sentence pass | below | |

**In one session, as the flow is used.** The administrator persona did all of this without signing out:
1. signed in;
2. opened *Sidebar* from the sidebar;
3. saw the sentence and the two padlocks;
4. flipped the switches and saved;
5. watched the sidebar lose the items;
6. walked to the asset dashboard and back, and found the state held;
7. typed a hidden address and got data;
8. was refused the lockout;
9. had the rows read in Postgres.

### The fresh verification pass

An agent that wrote none of this reviewed the diff against the handoff and the rules. Its findings and what was done:

1. **On `test19` the typed-address proof was an empty 200.** `test19` holds 0 vehicles, so typing `/fleet` showed only that nothing was refused, not that data came back.
   - **Fixed:** `test19`'s plan now hides *Employees*, and the spec requires at least one row back on both tenants. `boot44` already returned 200 assets.
2. **Defect: `"groups": false` beside a valid `items` was dropped with a 200.** The valid switch was written. The cause was `body.get(kind) or {}`, which broke Architecture rule 3.
   - **Fixed:** `None` means absent, and any other non-object is refused.
   - **Tests added:** four cases (`false`, `[]`, `""`, `0`).
3. **The `test19` evidence was older than the final wording.** Re-run after the fixes; the matrices in `48-evidence/` are from the final code.
4. **The no-reuse guard protected only today's keys.**
   - **Fixed:** a live key not listed as published fails the test.
   - **Proved to fail first:** `label_printer` was added to both tables and not listed.
5. **Sign-in by invitation or reset did not prefer a shown page.** The sign-in page did.
   - **Fixed:** both now read the switches with the new token before the session is stored (`login(…, beforeStore)`). The `/` front door still redirects on scopes only; that is unchanged and recorded.
   - **And a regression of my own, caught by the handoff 46 spec:** my first version of the tenant-aware landing read the switches AFTER storing the session. Storing it swaps the sign-in page for the app at `/`, so for the length of one request the app rendered the command centre and fired its four reads before moving on. The Tag-Issuing Unit, whom `/` redirects, visited `/no-access` twice. The 46 spec's record of every URL passed through failed on it: *"tag_unit passed through /no-access on the way to /no-access: /app/ → /app/no-access → /app/no-access"* (`playwright-46-test19-before-fix.txt`). Now the switches are read with the new token before it is stored, and the navigation happens in the same tick.
   - **Timestamp format:** the endpoint reference's `changed_at` example now shows the API's real format.
   - **OpenAPI:** the spec publishes `security: []` on routes with `scopes=[]`. That is pre-existing, also true of `/meta/enums`, and not changed here.
6. **Any token reads which administrator changed the sidebar**, and the browser cache keeps it.
   - **Accepted and recorded** in `DECISIONS.md`. A payload whose shape changes with the caller's scope would make `changed_by: null` mean two things.
7. **The HTTP tests' cleanup forced switches on rather than restoring them.**
   - **Fixed:** it puts back the prior state and asserts it did.

**What the pass checked and found TRUE:**
- **Lockout:** no path through the API hides the Sidebar screen — odd casing, a back-office row and combined bodies were all tried.
- **Ordering:** every refusal comes before any write.
- **Presentation only:** only the sidebar, the sign-in pages and the screen read the switches.
- **Agreement:** the group rule is the same in the server and the UI.
- **Ownership:** `write_uid` names the caller under `sudo()`.
- **Redaction:** 0 of 38 keys are redacted.

### Suites

| suite | where | result | denominator | file |
|---|---|---|---|---|
| HTTP (`pytest tests/`), CI's order: first | `test19` | **1,273 passed, 9 skipped, 0 failed**, 6 min 9 s; no `of 0 tests` | 1,282 | `pytest-test19.txt` |
| — the same, before the verification fixes | `test19` | 1,269 passed, 9 skipped, 0 failed | 1,278 | `pytest-test19-before-verification-fixes.txt` |
| in-registry, CI's module list, `--workers=0` | `test19` | **0 failed, 0 error(s) of 1,059 tests**; no `CRITICAL`; no `of 0 tests`. The first run said **1 failed of 1,059**: `test_every_route_that_takes_a_body_is_classified` (handoff 32's guard) — the new PATCH was not in `_BODY_ROUTES`. Classified (`None`, it writes parameters, not fields) and re-run | | `inregistry-test19.txt` |
| browser, `48-what-this-tenant-has` | `test19` | **4 passed** | 4 | `playwright-48-test19.txt` |
| browser, same spec | `boot44` | **4 passed** | 4 | `playwright-48-boot44.txt` |
| browser, `46-everyone-sees-their-own-job` (unchanged behaviour, + `/settings/sidebar`) | `test19` | **7 passed**. The first run, on my first landing code, failed 1 (tag_unit through `/no-access` twice) — §B finding 5; `playwright-46-test19-before-fix.txt` | 7 | `playwright-46-test19.txt` |
| static guards | — | `test_sidebar_catalog.py` + `test_nav_scopes.py` 10 passed; each catalog guard mutated to fail first (`static-guards-fail-first.txt`) | 10 | — |
| SPA typecheck | — | `tsc --noEmit` clean | — | — |
| module upgrade, `myservice_api` 19.0.3.20.0 | 9 databases | 9 of 9 at `19.0.3.20.0`, 0 `CRITICAL` | 9 | `upgrade-fanout.txt` |

**The skip count is 9, the same as handoff 46**, and the categories are the same:
- Turnstile ×2;
- partition data absent ×3;
- no `workflow.config`;
- no SAP asset number;
- `is_tagged`;
- the untagged-serial skip.

**Standing sentence pass.** Every zero here carries its denominator:
- *0 sidebar rows*: on 9 of 9 databases, and of 25 / 27 parameters on `boot44` / `test19`;
- *0 configured*: of 38 switches;
- *0 redacted*: of 38 keys;
- *0 vehicles*: on `nrs19`, of 11,951 assets;
- *never synced*: 11,386 of 11,386 employees.

## C · What I think has no business in this product for most tenants (§3)

With all 28 items in one list, each needing a default, this is the clearest view of what the sidebar has accumulated. Measured per tenant, on 8 local databases:

| screen | what is behind it | verdict |
|---|---|---|
| **Staff Bus** | Nothing: it renders built-in sample data (`MockDataBanner`) and asks the server nothing | **Remove from the sidebar** until a model exists. Default on means every new client is shown invented data |
| **Identity (clearance)** | Nothing: `listIdentityRecords` returns `mockIdentityRecords` | **Remove**, same reason |
| **Fleet Command, Fleet, Fleet Roster, Maintenance Readiness** | `fleet.vehicle`, a real model. But **`nrs19`, the real NRS register, holds 0**, and on every other tenant every vehicle came from one superuser load on one day: `cadra19` and `nrs` 1,609 each; `gtb19`, `gtb`, `lasg` and `jaizbankplc` 30 each; `test19` 0 | **The textbook tenant switch today**, and a question for NRS before it is one for engineering: is fleet in scope for any client? |
| **IT Assets Command** | The register filtered to `domain = it`: 69 of 11,951 on `nrs19`, 13 of 1,335 on `cadra19`, 1 of 4,164 on `jaizbankplc`, 0 on the other five | A saved filter on *All Assets*, not a product line |
| **Facility Command Center** (`/`) | Cross-domain, and still a hardcoded *All systems operational* pill | An instrument reporting what it does not measure: **fix or drop the pill** |
| **SAP Sync** | Real, but `nrs19` has 11,386 of 11,386 employees at `never` | Keep; it earns its place when the SAP employee feed is live |

Also already off the sidebar, though still served by address: FM Operations, Security Operations, and the whole Service Desk group. They are not in the switch table, because a switch for an item nobody draws would be a promise.

## D · Deviations and things to know

- **`boot44` is the second tenant, not `jaizbankplc`.**
  - **Why:** the spec writes configuration rows, which are left behind as `on`, never deleted, by design. `jaizbankplc` is a replica of a live client's register. `boot44` is a `test`-class database with personas.
  - **Default-on on the client replicas was measured by row count only:** 0 `cadra.sidebar.%` rows on `jaizbankplc`, `lasg`, `gtb` and `nrs`, and nothing written to any of them.
- **The switches are visible to everybody signed in** (§B, finding 6).
- **Other people's sidebars catch up within five minutes or on reload.** The sidebar re-reads every five minutes; the administrator's own changes at once.
- **On the cluster a push rolls only the frontend.** Until the `cadra-upgrade` Job loads `myservice_api` 19.0.3.20.0, the route answers 404:
  - the sidebar then hides nothing;
  - the Sidebar screen shows the error.
- **`test19` and `boot44` now carry these rows**, all `on`, written by the administrator persona and the suite's credential. That is what the design leaves behind, and it is what the configuration report shows.

## Needs the owner

1. **Merge the PR.** The Builder's permission layer refuses `gh pr merge`.
2. **The cluster.** Run the `cadra-upgrade` Job (all tenants) after merging, or the route answers 404 there and the switches do nothing (the app stays as it was).
3. **Still outstanding from 46:** `cadra19`, `nrs19` and `gtb19` are unclassified, so they have no personas.
4. **§C is for the Architect and NRS**, not engineering: whether Staff Bus and Identity leave the product, and whether fleet is in scope for any client.

## Commits

__COMMITS__
