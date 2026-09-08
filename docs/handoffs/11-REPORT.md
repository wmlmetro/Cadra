# Handoff 11 — Report

**Builder:** Claude Code (IDE) · **Branch:** `fix/retire-dead-screens` → PR into `dev`
**Wall-clock:** 1h 05m (15:32–16:37 WAT, 2026-09-08), of which ~9 minutes was the eight-tenant upgrade fan-out and ~6 minutes the two test suites.

---

## 1. The audit question Cadra currently cannot answer

**"Who has held this laptop?"**

The specification calls it *"custodianship chain for any asset (full history)"* and the PRD calls it *"the full sequence of custodianship records… immutable; it cannot be edited retrospectively, only appended… an audit-grade record suitable for legal and compliance purposes."*

It is not that Cadra fails to record custody changes. **It records them somewhere no auditor can read, in a store that does not carry the guarantee the PRD demands.** Measured on the live databases:

| Tenant | custodian changes as `mail_tracking_value` rows | `nrs.asset.transfer` rows carrying a custodian change |
|---|---|---|
| `jaizbankplc` | **217** | **0** |
| `nrs19` | 1 | 1 |

`POST /assets/<id>/transfer-custody` deliberately creates no history row — its docstring says the trail comes from `mail.thread` tracking plus a `message_post`. `nrs.asset.transfer` cannot hold a pure custody change at all: `from_location_id` and `to_location_id` are both `required` and a constraint forbids from == to. And **no API route exposes an asset's `message_ids` or tracking values** — `include=` on assets accepts only `transfers`, `pm` and `children`, and the embedded transfers list is capped at the last 20.

So the chain exists as 217 chatter rows, is invisible over the API, and lives in `mail.message`, which a user with the right groups can delete. **A chain of custody that can be deleted is not a chain of custody.**

That is the answer to the question asked. There is a second finding that is arguably more urgent, because it degrades every other answer:

**A machine credential sees 100 assets and is told that is the whole register.** Proven live against `jaizbankplc` (2,316 assets) on a client-credentials token asking for `limit=2000`:

```json
"pagination": { "next_cursor": null, "previous_cursor": null, "total_estimate": 100 }
```

100 rows. No next cursor. `total_estimate: 100`. `export.csv` returns 101 lines. The cap keys off the `aud` claim, which only `POST /auth/login` stamps — so every SPA session is uncapped and **every integration credential, which is what an auditor holds, is capped**. This fails rule 3: it silently degrades and returns 200. Every "yes" in the INT-10 document is subject to it.

Both are written up in `docs/integrations/INT-10-audit-access.md` §2.3 and §2.11, with the fixes as questions 5 and 6 in its §7.

---

## 2. Deviation: R54 is wrong about the barcode station, and names the wrong fleet module

**The handoff asked me to retire the Security Command Center and "the barcode station's backend client action". The barcode station renders. I did not retire it.**

R54's premise — that these are `odoo.define` modules requiring `web.AbstractAction` and `web.rpc`, "neither of which exists on Odoo 19" — is true of Odoo core and not true of this codebase. `myservice_nrs_base/static/src/js/legacy_compat.js` re-provides `web.core`, `web.rpc`, `web.ajax`, `web.session` and `web.AbstractAction` as OWL-backed shims, and it is bundled. **Five legacy dashboards render on 19 through exactly that path.** Verified in a real browser, logged into `jaizbankplc`, before any change:

| Client action | Result |
|---|---|
| `myservice_barcode_station.action_barcode_station` | mounted, 47,135 bytes of DOM, "2316 TOTAL ASSETS / 2316 ACTIVE TAGS", **zero console errors** |
| `myservice_asset_register.action_asset_dashboard` | mounted, 23,972 bytes, zero errors |
| `myservice_fm_dashboard.action_fm_dashboard` | mounted, 45,090 bytes, "249 open requests", zero errors |
| `myservice_staff_bus.action_bus_dashboard` | mounted, 5,875 bytes, zero errors |
| `myservice_dashboard.action_myservice_dashboard` | mounted, 18,867 bytes, zero errors |

The barcode station is also the *narrowest* consumer of the shim of the six — no `_.escape`, no `qweb.render`, no `$.when`, no `web.Widget`. Every route it calls (`/barcode/{kpis,recent_tags,lookup,print_url}`) exists in `myservice_barcode_station/controllers/main.py`; all 41 DOM ids it reaches for resolve against its template; `myservice_barcode_station → myservice_asset_register → myservice_nrs_base` guarantees the shim. Commit `2cdac30` ported it in the same commit as the other five and its message says *"all 5 client-action dashboards render"* — and there are exactly five `ir.actions.client` records, of which the barcode station is one.

**Retiring it would have removed a working screen from a live tenant on a false premise.**

Where the mis-generalisation came from is traceable: report 10 line 358 says barcode_station.js *"depends on the same two dead modules, so the client action fails to load on 19 as well."* That sentence generalises from `myservice_security` to the barcode station, and the generalisation does not survive the one fact that decides it — **the security files are in no asset bundle and the barcode station's are.**

### What I retired instead

**a) The security screens: the entry points were already gone, four months ago.** Commit `17aba57` (2026-04-08, *"replace broken JS client actions with standard act_window views"*) converted every `ir.actions.client` in `myservice_security` to an `act_window` and re-pointed the menus. The Security menus work today and open ordinary list views. Nothing in the repo references the three tags except the two JS files that register them, and reading the live actions registry in a logged-in session returns `false` for all three.

So R54's action was already done and only the note was missing. What remained was **521 lines of CSS shipping to every backend page in every app to style markup that is never rendered** — `security.css` (296 lines, only `.ms-soc-*`, consumed only by the retired `security_dashboard.xml`) and `security_tabs.css` (225 lines, 30 selectors all `.nrs-*`, consumed only by `security_tabs.xml`). Both dropped from the bundle.

**b) `security_navbar.css` was deliberately KEPT, and this is the one thing in Part A that needs an Architect ruling.** Despite its name and its own header comment (*"Target: `.o_menu_sections` (top nav tabs when Security & Safety is active)"*) it scopes to nothing — every selector is a core web-client class (`.o_main_navbar`, `.o_menu_sections`, `.o_menu_systray`, `.dropdown-menu`), so it restyles the top navbar of **every backend screen in every app for every user**. Where `myservice_theme_v5` also sets a property it wins (it appends after), but `security_navbar.css` alone supplies the uppercase/condensed/letter-spaced nav labels, the red active-tab underline, and the dark `.o_menu_sections .dropdown-menu` treatment. Removing it is a visible global change — arguably a *fix*, since a dark dropdown under a white navbar is a bug — but it is a design decision, not a retirement, and it needs a screenshot pass. **A file named for a retired module that styles the whole product is worth a ruling on its own.**

**c) The genuinely dead client action is in `myservice_fleet_maintenance`, not the barcode station.** `fleet_dashboard.js` **was** bundled, so it was downloaded, parsed and registered `myservice_fleet_dashboard` into the actions registry on every backend page load in every app — and that string appears exactly once in the entire repository, at the registration itself. No `ir.actions.client` record carries it. Both menuitems in `views/menu.xml` are `active="0"`. Confirmed live: the tag was in the registry before the change and nothing reached it.

It carries a second, latent defect: `myservice_fleet_maintenance` is the one module of the six whose `depends` does not reach `myservice_nrs_base`, which provides the shim its `require('web.AbstractAction')` needs. It only ever loaded because `myservice_dashboard` happens to drag `nrs_base` in.

Its three asset entries are gone; the source stays.

**Proof after the change**, same browser probe on `jaizbankplc` after the eight-tenant upgrade and a restart:

```
barcode_station: true    nrs_asset_dashboard: true    myservice_dashboard: true
myservice_fm_dashboard: true    bus_dashboard: true
myservice_fleet_dashboard: FALSE
nrs_security_command_center: false   nrs_case_management: false
myservice_security_dashboard: false
```

All five live dashboards re-render with byte-identical DOM sizes (47,135 / 23,972 / 45,090 / 5,875 / 18,867) and zero console errors. The retired tag is gone from the registry.

*(In the sequential probe the bus dashboard's URL failed to resolve on one pass; re-probed in isolation it mounts at 5,875 bytes with zero errors. Navigation timing, not a regression — recorded because a green line that was amber once is worth saying out loud.)*

### Two things that must not be tidied up later

- **`myservice_security/static/lib/leaflet/` must not be deleted.** `fleet_dashboard.js:227,230` hard-codes `/myservice_security/static/lib/leaflet/leaflet.{css,js}` — a cross-module URL dependency nothing declares. `myservice_dashboard` and `myservice_staff_bus` each vendor their own copy.
- **`tests/test_security_tabs_fields.py` cannot be deleted without deleting the JS**, and vice versa: it opens `security_tabs.js` as a text file in `setUp`. It sits at exactly `MIN_CALLS = 5` against the 5 calls in the file, so it is a real tripwire. Its value now is archival integrity — it guarantees the retired code stays portable as the registry drifts. Left in place; the note says why.

---

## 3. Deviation: R55 named three workflows; there are four

`tenant-cutover-19.yml` does `kubectl rollout restart deployment/odoo-19` followed by `rollout status`. That is the same hazard R55 names — a deploy whose ConfigMap guard reads the running pod while something else replaces it under them — so it joined the group. Four workflows now share `concurrency: cadra-cluster-deploy`, all `cancel-in-progress: false`.

Deliberately **not** in the group: `db-query`, `audit-tenant`, `set-tenant-company` and `debug-job` all `kubectl exec` into `odoo-19` to read a tenant. Queueing a 20-second query behind a 40-minute deploy would be a worse workflow, not a safer one.

---

## 4. Guards added

Three new source guards in `tests/test_source_guards.py`, each proven to go red before being accepted.

**`test_every_workflow_that_rolls_odoo_19_shares_one_concurrency_group`** — derives membership from what a workflow *does* to `odoo-19` (`kubectl scale` / `rollout restart` / `rollout status` on `deployment/odoo-19`), never from a hand-kept list of names, so a fifth cluster-touching workflow that quietly gets its own group fails. Detects exactly the four. Proven: reverting `upgrade-19` to its own group turns it red, naming the file.

**`test_every_bundled_client_action_has_an_action_record`** and **`test_every_client_action_record_has_a_bundled_registration`** — a two-way join between `core.action_registry.add('<tag>', …)` in **bundled** JS and `<field name="tag">` on `ir.actions.client` records. The two halves of a client action live in different files and nothing joined them up; the security modules had the record-missing half and the fleet module had the JS-orphaned half, which is the same defect from opposite ends. **Bundled-ness is the hinge** — a guard that grepped the JS tree would fail on exactly the files we deliberately retired. Proven: putting `fleet_dashboard.js` back in the manifest turns it red with the tag and the file.

**`test_the_retired_screens_stay_retired`** — parametrised over the four retired tags, asserting the retirement itself rather than only the consistency the join checks.

---

## 5. INT-10 — `docs/integrations/INT-10-audit-access.md`

Written in the INT-06-07-09 shape: metadata header, `## 1. The shape of it`, the unnumbered live-OpenAPI section, numbered sections with `###` subsections, a measured-facts table, and a continuously numbered "what we need to proceed" list ending with the contact line. All four required sections answered as §2 (the questions), §3 (what is missing and what keeps each field honest), §4 (access and segregation), §5 (what Vendra must supply).

**A blocking finding sits at §0: "INT-10" appears nowhere in this repository, and the *End-to-End Integration Flow* document is not in it either.** It is referenced twice as an external source and never quoted; `CLAUDE.md` lists Cadra's interfaces as INT-03, INT-04/05, INT-06/07 and INT-09, with no INT-10. So §2's eleven questions are a **reconstruction** from `Cadra_at_NRS_Specification_v0.1.docx` §13.4 (which names five standard audit reports and is the closest thing to a requirement list), §13.3, §3's roles table, §7.6, §8.6 and §15, plus PRD §5.11, §8.14 and line 619. Request 1 in §7 is "send us the September flow's INT-10 section", and the document is built to survive being corrected by it.

Of §13.4's five named reports, **Cadra has none as an API surface today.** Point-in-time exists only for depreciation; the custodianship chain does not exist as a model; disposal has no documentation refs and no period report; access changes and configuration changes have no log at all.

Everything numeric in the document was measured today, not carried forward:

| Tenant | Assets | With a cost | PO ref | GRN ref | SAP number | Serial | Affixed |
|---|---|---|---|---|---|---|---|
| `nrs19` | 11,942 | **56 (0.5%)** | 59 | 60 | 2 | 11,323 | 54 |
| `jaizbankplc` | 2,316 | 274 | 143 | 543 | 0 | 102 | 305 |
| `cadra19` | 1,335 | 1,329 | 0 | 13 | 0 | 13 | 0 |
| `nrs` / `gtb19` / `gtb` / `lasg` | 1,272 / 156 / 150 / 150 | all | 0 | 0 | 0 | 0 | 0 |

**On the migration target, 99.5% of assets carry no cost at all.** No API change fixes that. §7 question 13 puts it to NRS as a decision rather than leaving it to be discovered: either the costs are loaded, or INT-10 goes live knowing it cannot answer the money question for the estate. Cadra will not synthesise a value it does not have.

The section that most repays reading is §3.2, "fields that nothing keeps honest". The pattern it names: **everything Cadra generates is guarded properly — `asset_code` is `NOT NULL` + `UNIQUE` + not writable over the API, `asset_tag` was removed from `_WRITABLE_FIELDS`, the six tag-capture fields raise on any write outside the capture context. Everything Cadra receives from another system — the GRN reference, the PO reference, the serial number, the department, every financial field, every `sap_*` field — is guarded by nothing and tracked by nothing.** For an interface whose purpose is tracing an asset back to what was paid for it, that is the wrong way round. §7 question 7 asks which of those should become tracked.

Also recorded there, because an auditor will otherwise find it as a finding: **`printed` is only trustworthy from 2026-09-08 forward** (handoff 10), while `affixed` is trustworthy throughout.

---

## 6. Verification

**pytest** — `CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q`

```
258 passed, 27 skipped in 176.99s (0:02:56)
```

Baseline before any change was `252 passed, 27 skipped in 174.61s`; the 6 new passes are the guards in §4. The 27 skips are the admin-scoped tests the suite's token cannot reach, as documented.

**In-registry Odoo tests** — the CI command, with one correction. CI runs it against the database in `.env.example`, which is `odoo` — and on this machine `odoo` is the 15-era leftover a 19 worker cannot load (`ERROR: operator does not exist: character varying ->> unknown`, then `Failed to load registry`). Run against `test19` instead:

```
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo -c /etc/odoo/odoo.conf -d test19 \
    -u myservice_workflow,myservice_asset_depreciation,myservice_nrs_base,myservice_asset_register,\
myservice_request_fields,myservice_security,myservice_fleet_maintenance,myservice_barcode_station \
    --test-enable --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098

133 post-tests in 225.56s, 9645 queries
0 failed, 0 error(s) of 133 tests when loading database 'test19'
exit code: 0
```

(CI's own run is 72 tests because it starts from a fresh `odoo` database; `test19` carries the post-install set as well.)

**Per-tenant fan-out** — both modules upgraded on all eight tenants (`cadra19`, `nrs19`, `gtb19`, `test19`, `nrs`, `lasg`, `gtb`, `jaizbankplc`). Every run reached `Modules loaded.` with 77 modules (78 on `test19`) and no errors. The one `WARNING`/`View error context` line in each run is a pre-existing accessibility warning on `security_access_log_views.xml:4` about an `alert-*` class needing an `alert` role — present before this change and unrelated to it.

Strictly, neither manifest touches a model, so no schema fan-out was required. The upgrade was needed anyway: an asset-bundle change does not take effect on restart.

**Live proof** — the browser probe in §2, before and after.

---

## 7. Open questions for the Architect

1. **`security_navbar.css`** (§2b). It is named for a retired module and styles the entire product. Retire it and accept a visible global navbar change, keep it and rename/relocate it into a theme module where its scope is honest, or leave it exactly as is? Ruling wanted; I made no change.
2. **The pagination cap** (§1, INT-10 §2.11). This is a live defect against rule 3, not just an INT-10 gap — Vendra holds a machine credential too, and any list endpoint it reads is capped at 100 with `total_estimate` claiming completeness. Recommendation in INT-10 §7 question 5: keep the cap, move it off the `aud` claim onto a per-client setting, always report the true `total_estimate`, and always emit a `next_cursor` while rows remain. Worth its own handoff ahead of INT-10.
3. **The custody chain** (§1). An append-only `nrs.asset.custody` model is the largest single INT-10 gap. Do we backfill the 217 existing tracking rows? They carry actor and timestamp so the backfill is faithful — but the result will be visibly sparser than the register, because it only covers changes made since `custodian_id` became tracked. That is honest and will still look like a gap to an auditor.
4. **`do_notify` is not in the shim.** Only the barcode station calls it (`barcode_station.js:204`), on "Request replacement": the RPC succeeds and the record is written, then the `.then()` throws, so the list never refreshes. It reads as "nothing happened" while the write landed. Three lines in `legacy_compat.js`. Out of scope for R54 — recorded in `docs/retired-screens.md`, which is where someone will look.
5. **The `.env.example` database is `odoo`** (§6). CI creates it fresh so CI is fine, but the command CLAUDE.md documents cannot be run verbatim on a developer machine, and the failure it produces (`psycopg2` complaining about an operator) does not say why. Worth a line in CLAUDE.md or a CI-only marker.

## 8. Commits

- `fix: retire the screens that cannot render, and prove the ones that can` — the two manifests, `docs/retired-screens.md`, the three guards.
- `ci: one concurrency group for every workflow that rolls odoo-19` — the four workflows.
- `docs: INT-10 — Cadra's half of continuous audit read access`

PR into `dev`. **Owner-blocked at the merge**, as standing.
