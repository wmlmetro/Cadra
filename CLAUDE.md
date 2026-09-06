# CLAUDE.md — Cadra (myservicenrs)

Guidance for Claude Code and any developer working in this repository. Keep it current: update **Status** as work lands and **Decisions** whenever one is made.

## Working model — two Claude roles

This project is run by **two cooperating Claude sessions**, the same way its sibling `vendra_network` is:

1. **The Architect (Claude in Cowork/cloud)** — owns the plan, the cross-system specs, this file, and quality control. Writes build instructions, reviews finished work, and holds the integration picture across Cadra, Vendra and SAP. Does not run Odoo.
2. **The Builder (Claude Code in the IDE, this machine)** — executes build instructions: writes code, runs the stack, runs pytest, and handles git. **If you are Claude Code reading this in the IDE, you are the Builder.**

**Handoff protocol** (`docs/handoffs/`):
- The Architect writes numbered instruction files: `docs/handoffs/NN-<slug>.md` — context, steps, acceptance checks, what to report.
- The Builder executes the latest un-reported handoff and writes `docs/handoffs/NN-REPORT.md`: what was run, full test output (not a summary), decisions made and why, deviations from the instructions, open questions, commit hashes.
- **Deviating from a handoff is expected when the handoff is wrong.** Say so in the report with evidence; do not silently comply with a bad instruction, and do not silently improvise around it either.
- The Builder never edits the handoff instruction files or the specs; corrections flow through reports.
- After pushing, notify the Architect: `ListAgents` → `SendMessage` to **`claude-fc [01f312]`**, first line self-contained ("Handoff 01 complete — …"). If it is not listed, skip silently; the Architect polls the repo. The report and commits are the source of truth; the message is only a doorbell.

### Handoff authoring rules (Architect)

**A handoff must be executable end to end with nothing left for the owner to do by hand.** Every one:

1. **Opens with Step 0 — get to the right state.** Merge the previous work (branch or PR), run whatever migration, module upgrade or per-tenant fan-out that merge requires, verify it took, then create the new branch. Never assume the repo or the databases are already where the work needs them.
2. **Ends with the work landed** — committed, pushed, PR opened, report written, Architect notified. "Done" means in the remote, not in the working tree.
3. **Names anything that genuinely needs the owner** in a "Needs the owner" block at the top — **including the final PR merge: the Builder's permission layer refuses `gh pr merge`, so every handoff ending in a PR is owner-blocked at that step** — — a credential, a production deploy, an approval, a business decision. Explicit and up front, never discovered halfway through.

If a handoff cannot be completed without a manual step that is not in it, that is a defect in the handoff — say so in the report.

### Parallel execution (Builder)

Work a handoff with **multiple subagents in parallel** when its steps are independent.

- **Partition by file, never by concern.** Two agents must never edit the same file. Split along module/controller boundaries.
- **Serialize anything sharing state**: anything touching the database or the running stack (module upgrade, seeds, migrations), and all `git` operations, run one at a time in the main session.
- **Fan out freely on read-heavy work** — reading Odoo core for the right hook, tracing how an existing endpoint does something, checking a model's field definitions. This is where parallelism pays.
- **Finish with a fresh verification agent** (not an author) reviewing the diff against the handoff's acceptance criteria and the rules below. Its findings go in the report.
- Give each agent the full contract: this file, the relevant spec section, the exact files it owns, and what to return. Launch independent agents in one message; ~2–5 per handoff.

## What this is

**Cadra** — the asset and facilities register for the Nigeria Revenue Service (NRS), built on **Odoo 15** with a versioned REST layer (`/api/v1/*`) in `myservice_api` over the ITSM, asset register, security and FM modules. An Odoo 19 migration is in flight (`crnd-19/`, `oca-19/`, `docker-compose.19.yml`, `chore/retire-15-stack`); treat 15 as production until that lands.

**Canonical spec:** the PRD and NRS specification under `docs/` (`Cadra_Platform_PRD_v0.4.docx`, `Cadra_at_NRS_Specification_v0.1.docx`). When README and spec disagree, the spec wins.

## The ecosystem — why the API's shape matters beyond Cadra

Cadra is one of three systems in the NRS integration programme, defined by *"End-to-End Integration Flow — Cadra · Vendra · SAP"* (September 2026):

| System | Repo | Role |
|---|---|---|
| **Vendra** | `Frappe/apps/vendra_network` (Frappe/ERPNext) | Digital goods receipt, GRN, classification, inventory |
| **Cadra (this)** | `wmlmetro/Cadra` (Odoo) | Asset register, identity, tagging, custody, lifecycle |
| **SAP** | NRS-owned | ERP: POs, financial postings, SAP asset codes, payment |

**Interfaces Cadra owns:** INT-03 (Vendra → Cadra, asset-classified receipt hand-off — *inbound to our API*), INT-04/05 (Cadra ↔ Tag-Issuing Unit), INT-06/07 (Cadra ↔ SAP asset master and dual-code reconciliation), INT-09 (lifecycle events → SAP).

**Practical consequence:** `POST /api/v1/assets` is no longer only a UI-adjacent endpoint — it is a contract another system builds against. Changes to `_WRITABLE_FIELDS`, the response envelope, the `condition`/`state` enums, or idempotency behaviour are **breaking changes for Vendra**. Treat them as versioned API changes, and say so in the report when you touch them.

## Stack & environment

*Corrected against this machine on 2026-09-05 (handoff 01). The local stack is **Odoo 19**, not 15 — this section said 15 and every command in it was wrong.*

- **Runtime: Odoo 19.0** (`cadra-odoo:19.0-dev`, built from `Dockerfile.odoo.19.dev`) · PostgreSQL 15 · Docker Compose · nginx (dev) / Caddy (prod). Odoo 15 remains the deployed production runtime; nothing on this machine runs it any more.
- **Bring-up needs BOTH compose files** — the base alone gives the wrong `odoo.conf` and no proxy:
  ```
  docker compose -f docker-compose.yml -f docker-compose.19.yml up -d
  ```
- **Tenancy is host-based.** `http://localhost:8069` answers *"No database is selected"*; reach a database as `http://<db>.localhost:8069`. Local databases: `cadra19`, `nrs19`, `gtb19`, `test19` (19-era) and `nrs`, `gtb`, `lasg`, `jaizbankplc` (15-era replicas now served by the 19 container).
- **Tests need a database with a `docs/api/.creds.<db>` file.** Today that is only `jaizbankplc` (`nrs19` has one, but it holds the demo's two scoped clients, not a `CLIENT_ID`/`CLIENT_SECRET` pair). The shared `docs/api/.creds` was deleted in handoff 05:
  ```
  CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
  ```
  The venv is `tests/.venv` (Python 3.13) — the repo's own Python, not the container's. `docs/api/smoke_test.py` is the 30-second liveness check. Note the suite's token has no `admin` scope, so ~24 admin-scoped tests skip; that is expected, not a failure.
- **Module upgrade** after model/view/manifest changes — the running container already binds port 8069, so an in-container upgrade must be given free ports:
  ```
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d <db> -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
  ```
  Then `docker compose … restart odoo` — Python changes are bind-mounted but not hot-reloaded.

### Odoo 19 gotcha: `_sql_constraints` is dead

Odoo 19 removed it. `odoo/orm/model_classes.py:162` logs *"Model attribute '_sql_constraints' is no longer supported, please define models.Constraint on the model"* and **creates no constraint** — a uniqueness guarantee declared the old way silently stops existing. **8 declaration sites** were affected — 2 first-party plus 6 in `crnd-19/` — and all are now ported; `docs/constraint-audit.md` is the standing record. Use `models.Constraint("UNIQUE (a, b)", "message")` on 19, keeping the legacy list behind an `_ODOO_MAJOR` guard in our own modules only (the 15 stack still loads them). `dist/` is the Odoo 15 vendor tree and is **not** on the 19 addons path — its `_sql_constraints` are correct as they stand; `crnd-19/`/`oca-19/` are 19-only and need no guard. `tests/test_source_guards.py` fails on any unguarded reintroduction in our modules.

### Adding a stored field is a multi-tenant migration, not a code change

One Odoo process serves every database from one registry, so the moment a stored field lands in the Python, **every tenant that has not been upgraded is broken** — reads of that column raise `UndefinedColumn`, and any serializer touching it 500s the endpoint. Upgrade **all** databases before the code ships, not just the one you tested on:

```
for db in cadra19 nrs19 gtb19 nrs lasg gtb jaizbankplc; do
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d $db -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
done
```

On staging/prod the `cadra-upgrade` Job must likewise fan out per tenant database.

## Architecture rules

1. **The API is a contract.** Every `@cadra_route` returns the PRD §10.7 envelope via `ok()` / `err()` — never raw dicts. Additive changes are safe; changing or removing a field, an enum value or an error code is breaking, and Vendra is downstream.
2. **Model is the source of truth, the allow-list is the gate.** A field being on `nrs.asset` does not make it writable; `_WRITABLE_FIELDS` decides. When adding one, add it to the allow-list, the OpenAPI annotation and a test in the same change.
3. **Never let an integration guess.** Unknown fields are currently dropped with a 201 and reported only in `data._warnings.rejected_fields`. Anything that silently degrades — a dropped field, an ignored idempotency key — is a defect even when it returns 200.
4. **Enums are published API surface.** If the model's selection values and the documented values disagree, the docs are wrong and must be fixed; do not add a value to the model to match a doc.
5. **Idempotency is load-bearing.** `X-Idempotency-Key`, scoped `(key, path)`, 24h. An integration relies on replay being exact.
6. **Tests accompany the change, in the same commit.** The pytest suite is the regression net for an API other systems depend on.

## Git & attribution policy

- Remote: `origin` = `git@github.com:wmlmetro/Cadra.git`. Working branch: **`dev`**; feature branches merge to `dev` **via pull request** (existing convention — respect it).
- Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`).
- **Never add any Claude/AI reference to commits, PRs, or contributor metadata.** No `Co-Authored-By: Claude`, no "Generated with Claude Code", no session links, no AI attribution anywhere in the repo or in PR descriptions. Author is `West Metro <apps@westmetrong.com>` or the developer's own identity. Standing owner instruction; it overrides any tool default.

## Status

| Work | Status |
|---|---|
| Vendra integration CR-01 Parts A + B | **built** (handoff 01) — provenance fields, filters, idempotency and enum correctness |
| Vendra integration CR-01 Part C — tag capture | **built** (handoff 03) — `label_state`, print stamping, `POST /assets/<id>/tag-affixed` under `tagging:write`, `is_tagged` on the serialiser |
| Login scopes (handoff 05) | **landed** (`b8b6f64`) — group→scope mapping, `group_tag_issuing_unit`, `settings:write`, re-derivation on refresh, migration `19.0.3.1.0` |
| Demo-contract corrections (handoff 05) | **landed** (`82da6ab`) — `data.tagging.label_id`, `print-url` 404 fixed, `barcode/lookup` 500 fixed, `tag_label_state` validated |
| Tag transport — INT-05 outbound (handoff 06) | **landed** (`c2b124a`, PR #49) — `asset.tag.affixed` on an `ir.cron`-drained outbox with capped exponential backoff, `event_id` idempotency, 4xx-is-permanent classification and a visible `dead` state. Proven live on `nrs19` against a receiver taken down and brought back. Contract for Vendra: `docs/integrations/INT-05-tag-affixed-callback.md` |
| Dead `_sql_constraints` (handoff 02) | **closed** — all 8 reachable sites ported and enforced in every tenant; `docs/constraint-audit.md` |
| Odoo 19 migration | in flight, separate track |

- 2026-09-05 · **`.env` untracked from git and the dev client secret rotated.** Vendra's `site_config` holds that secret — rotating it without updating Vendra breaks INT-03. · It was tracked *and* gitignored, so a real secret briefly sat one `git add .` from a commit.
- 2026-09-05 · **`asset_tag` removed from `_WRITABLE_FIELDS`.** Breaking, announced; Vendra (the only live consumer) does not write it. · A client could PATCH `tag` until it no longer matched the physical label, defeating the affix control.
- 2026-09-05 · **Empty scopes means no permissions, not wildcard.** · A client created without scopes receiving everything is privilege escalation waiting for a typo — the opposite of the Tag-Issuing Unit separation.
- 2026-09-05 · **`data.tag` deprecated by annotation, not removed.** · Breaking a published field to fix a naming problem is not a trade worth making with a live consumer.
- 2026-09-05 · **The affix endpoint verifies `serial_number` when supplied.** · The spec asks for the serial-to-tag match; checking one side is half a control.

- 2026-09-05 · **`nrs19` is the working tenant for integration and demo work**, replacing `cadra19`. · The 19-era database with the real dataset (~11,878 assets) and the migration target; its `jwt_secret` and API client were provisioned in handoff 03. Vendra's `Host` header, category ids and client credentials are all per-tenant — none of them carry over from `cadra19`.

- 2026-09-05 · `[landed b8b6f64]` **`/auth/login` no longer grants `["*"]`** — scopes derive from the user's Odoo groups (`utils.GROUP_SCOPES` / `scopes_for_user`), `tagging:write` comes from the new `group_tag_issuing_unit` alone, and a user with no Cadra group gets an empty scope list. · Handoff 04 Q1; handoff 05.
- 2026-09-05 · `[landed]` **`ensure_vendra_client()` stays.** The demo's asset-creating half needs a credential that is *not* `test_client` — an admin wildcard that passes `tagging:write` without holding it would make the demo prove nothing. · The separation is the control; same argument as ruling 6 applied to the other side.
- 2026-09-05 · `[landed f7bf682]` **The shared `docs/api/.creds` is deleted.** Only 2 of 8 tenants had a `.creds.<db>`, so the ruling's literal precondition was never met — deleted on the evidence that no reader can reach it instead (both readers fall back only on the no-tenant branch, which cannot authenticate against a host-routed stack). · Handoff 05 Part C.
- 2026-09-05 · `[landed]` **`nrs19` client split**: `vendra` (assets:read/write, deliberately no `tagging:write`) and `tag_issuing_unit` (`tagging:write` only). Proven live in both directions with 403s. · An asset-creating credential that can also confirm its own tag defeats the control.

- 2026-09-06 · `[landed b8b6f64]` **`admin` is a wildcard, so `settings:write` exists.** Six tenant-configuration write routes moved off `admin`. Granting an Asset Manager `admin` to keep the SPA's Settings screens would have handed them `tagging:write` — the hole reopened in the name of not breaking the UI. · Handoff 05 Part A.
- 2026-09-06 · `[landed b8b6f64]` **Session refresh RE-DERIVES scopes from groups; client refresh replays the client record's.** `verify_and_rotate` used to replay the stored string either way, so removing someone from the Tag-Issuing Unit left them holding `tagging:write` for up to the 30-day sliding window. · A group change must bite within the hour, not the month.
- 2026-09-06 · `[landed b8b6f64]` **An internal user with no Cadra group gets NO scopes.** Every list endpoint runs `sudo()`, so a scope is the only gate between a logged-in account and the register; a "read scopes only" default would hand the asset base to anyone with an Odoo password. · Handoff 05.
- 2026-09-06 · `[landed 82da6ab]` **A tag label id is not an asset id and the spaces collide** — 22 assets on `nrs19` have an asset id that is a valid label id for a *different* asset. `print-url` takes a label id and returns a URL containing an asset id; feeding the wrong one returns `200` and renders the wrong machine's label. `data.tagging.label_id` exists so an integrator never has to guess. · Handoff 05 Part B.
- 2026-09-06 · `[landed 82da6ab]` **`/report/pdf/<...>` resolves its second segment against `ir.actions.report.report_name`, not the action xmlid.** `print-url` emitted the xmlid and 404'd; the one published route from an asset to a printable label had never rendered anything. · Handoff 05.
- 2026-09-06 · `[landed 82da6ab]` **`dict(field.selection)` is wrong for a *related* Selection** — `.selection` is a callable there, so it raises `TypeError`. Use `fields_get`. This 500'd `/barcode/lookup` for every asset it found, and broke the barcode station's own scan box, not just the API. · Handoff 05.
- 2026-09-06 · `[landed 82da6ab]` **A query-enum validator must never disable itself on failure**, and `"null"` is not a "no filter" sentinel where the filter is an enum — treating it as one returned the whole register. · Handoff 05 verification pass; `utils._selection_allowed_values` returns `None` on error and rolls the cursor back, so it must not be used on a read path.
- 2026-09-06 · **Odoo caches group membership** (`res.users._get_group_ids` is `@ormcache`d). A group change made from a separate `odoo shell` process does not reliably invalidate a running HTTP worker; changes made through the running server (UI or XML-RPC) do. Stock Odoo behaviour — but it will make anyone testing the scope mapping from a shell think it is broken. · Handoff 05.

- 2026-09-06 · `[landed b8b6f64]` **`/auth/login` derives scopes from Odoo groups**, and a new **`settings:write`** scope carries the six tenant-config routes. · `admin` is itself a wildcard in `require_jwt`, so mapping Asset Manager to `admin` would have moved the hole rather than closed it. Additive, non-breaking; ships a data migration because refresh tokens replay stored scopes for 30 days.
- 2026-09-06 · `[ruled]` **`tagging:write` stays inside the `admin` wildcard.** "Absolute below system-administrator" is the accepted posture; document it where the scope is defined so it reads as a decision, not an oversight.
- 2026-09-06 · `[landed 82da6ab]` **`print-url` built its path from the report action's xmlid, not its `report_name`** — it resolved to nothing and returned the website's 404 page as a 26KB HTML body. The one published route from an asset to a printable label had never rendered anything. · Read `report_name` off the action record so a rename cannot reintroduce it.
- 2026-09-06 · `[ruled]` **Fix the `phase1_*` seed users' roles** — empty scopes by accident must not look like empty scopes by design.

## Backlog — agreed, not yet scheduled

- **The nine pre-envelope routes adopt `@cadra_route`** (`/auth/*`, `/openapi.json`, `/docs`, `/assets/export.csv`, `/integrations/employees/import`, `/brand`). They validate nothing and sit outside the standard envelope — and `/auth/token` is the first endpoint every integration touches. Refactor of the auth surface; after INT-03 is live.
- **Query-parameter validation, API-wide (report 01 V4).** Scoped in report 05: **~26 sites across 5 files** — 13 enum params (`200 []`), **5 boolean params that silently drop the filter and return the UNFILTERED list**, and 8 int params that `except: pass`. The booleans are the dangerous half and should go first: an empty list reads as "no matches", a full list reads as an answer. `utils.py:830` already holds the primitive. Handoff 05 did the tagging filters only.
- **Per-session test artefact paths.** Two concurrent pytest sessions clobber each other's report and captures. Cosmetic.
- ~~**`docs/api/.creds` is one file for eight tenants.**~~ **Closed by handoff 05** (`f7bf682`) — the shared file is deleted and both readers now resolve `.creds.<db>` or nothing.

## Decisions

> **Ruled ≠ landed.** A line here records what was *decided*, not what exists in the code. Tag each one **`[ruled]`** when the Architect makes it, and change it to **`[landed <commit>]`** only when a Builder report confirms it shipped. The Architect may write `[ruled]`; only a report moves a line to `[landed]`. The Status table above lists **landed** work only.
>
> This convention exists because handoff 04 found four decisions recorded here as done that had never been implemented — including one the list contradicted itself on. A decision written down and not built is worse than one not yet made, because the next handoff builds on it.


- 2026-09-05 · Architect/Builder split adopted for this repo, mirroring `vendra_network`. · One person owns two codebases in one programme; the handoff trail is how the integration stays coherent across both.
- 2026-09-05 · **Serialised provenance is a nested `data.provenance` block**, not six top-level keys. · Matches the existing grouping; one new envelope key instead of six for a contract Vendra is building against.
- 2026-09-05 · **`vendra` added to the `import_source` enum.** · The enum already names integration partners; `other` + a ref throws away the signal the field exists to carry.
- 2026-09-05 · **`q` also matches `grn_reference` and `purchase_order_reference`.** Intended behaviour — an auditor pastes a GRN into search before finding a named filter. Do not "fix" it.
- 2026-09-05 · **Idempotency header length is validated on all routes; the header is not rejected on non-idempotent ones.** · A caller sending an over-long key deserves an error; a caller harmlessly spraying the header should not start failing. Document which routes honour it.
- 2026-09-05 · **Tag capture before tag transport.** Cadra records neither printing nor affixing, and `nrs.asset.tag.label.state` is a replacement lifecycle that reads `active` from creation — exposing it would reproduce the false-completeness bug in a new field. Vendra shows `Registered` and claims nothing further until capture exists. · Handoff 01 Part C.
- 2026-09-05 · **`dist/` is Odoo 15 only and its `_sql_constraints` are correct** — it is not on the 19 addons path, so the "44 unassessed vendored files" were never a hole. `crnd-19/`/`oca-19/` are 19-only and need no version guard. · Handoff 02 audit.
- 2026-09-05 · **The six `crnd-19/` holes were our own porting bug**, not vendor debt — `generic_resource`/`generic_location`/`generic_team` are hand-ported by us and are not fetched by `scripts/fetch-crnd-19.sh`, so patching them carries no upstream-clobber cost. · Handoff 02.
- 2026-09-05 · **`models.Constraint` on an AbstractModel does propagate to concrete inheritors** on Odoo 19 (verified on `generic.resource.mixin` → `generic_resource_simple`). · Handoff 02.
- 2026-09-05 · **`dist/` is not on the Odoo 19 addons path and is out of scope permanently.** Its constraints are correct for the 15 stack and die with it. · Three independent proofs in `docs/constraint-audit.md`; the trees are mutually exclusive by Odoo version.
- 2026-09-05 · **`asset_code` becomes `NOT NULL`** alongside its unique constraint. · INT-06/07 dual-code reconciliation is a named control point; "one asset per *non-null* code" is weaker than it assumes.
- 2026-09-05 · **Vendored trees are guarded by a startup assertion on the warning count, not by the source test.** · A source test cannot cover code an upstream refresh may reintroduce.
- 2026-09-05 · **Tag capture is built before tag transport.** Cadra records neither printing nor affixing; the Tag-Issuing Unit's independence must survive into whatever records it. · Handoff 01 Part C, handoff 03.
- 2026-09-05 · **`label_state` lives on `nrs.asset.tag.label`, is readonly, and moves only through `_mark_printed` / `_mark_affixed`.** `is_tagged` is true only after an affix confirmation whose scanned tag number matched the issued one. · A status an operator can set from a desk is evidence of nothing; the serial-to-tag match IS the control.
- 2026-09-05 · **The print funnel is `ir.actions.report._render_qweb_pdf`, not the action methods.** The label wizard, the barcode station's raw `/report/pdf/` URL and Odoo's own Print-menu binding all bypass `action_print_tag`. · Handoff 03; stamping only the action methods would have under-recorded printing badly.
- 2026-09-05 · **Tag ids collide with asset ids, and the four tag reports all declare `model = nrs.asset`** — so anything resolving a report's `res_ids` must not assume which. Two callers pass tag ids in. · Handoff 03 V1: a hook that guessed wrong fabricated print records on unrelated assets. Under-record rather than fabricate.
- 2026-09-05 · **`readonly=True` is a web-client hint, not an ORM guard.** Fields that record an observed event are protected by a `write()` override keyed on a context flag the recording method sets. · Handoff 03 V1; `group_asset_manager` can write over XML-RPC.
- 2026-09-05 · **`active_tag_id` excludes a tag pending replacement; `physical_tag_id` does not.** The physical question must use the latter — requesting a replacement does not peel the label off the asset. · Handoff 03 V3.
- 2026-09-05 · **Unknown API scopes are rejected on save** (`myservice.api.client`), and an empty scopes field remains a wildcard. · A typo used to mint a token and produce a 403 indistinguishable from a real permission decision.
- 2026-09-05 · **Installing modules is not provisioning a tenant.** `-i`/`-u` never run `scripts/bootstrap.py`, so a tenant created the documented way gets no `jwt_secret` and no API client. · How `nrs19`/`test19` ended up unable to authenticate; `k8s/dev/MULTI-TENANT.md` now says so.
- 2026-09-05 · **`_sql_constraints` is dead on Odoo 19** — declared constraints silently do not exist. Ours use the dual-spelling pattern in `api_idempotency.py`; a guard must fail loudly on any new use. · 2 live holes in our modules + 44 files in `dist/`; handoff 02. **Corrected by the handoff 02 audit:** the `dist/` files are not reachable by Odoo 19 and were never holes; the real remainder was 6 sites in `crnd-19/`. All 8 are now fixed.

- 2026-09-06 · `[landed c2b124a]` **The affix endpoint queues the event; it does not POST it.** Delivering inline would announce an affix before its transaction committed — a rollback would leave Vendra holding `Tagged` for an asset Cadra does not think is tagged — and would make the Tag-Issuing Unit's confirmation latency a function of whether Vendra is up. `ir.cron._trigger()` books the drain inside the same transaction, so delivery follows the commit by seconds without being part of it. · Handoff 06 B2.
- 2026-09-06 · `[landed c2b124a]` **Any 4xx except 408/425/429 dead-letters on the first attempt.** A request does not become valid by being sent eight more times; burning the budget only delays the moment a human sees the problem. 5xx, 429 and network errors back off. Mirrors Vendra's own classifier pointing the other way. · Handoff 06.
- 2026-09-06 · `[landed c2b124a]` **A `409` from the receiver is a delivery, not a failure.** It is the receiver saying it already has this `event_id` — which is the outcome the idempotency key exists to produce. Treating it as an error would dead-letter events that landed perfectly. · Handoff 06.
- 2026-09-06 · `[landed c2b124a]` **The drain is scoped by `event_type`, not by status.** Request-approval dispatches also sit at `pending`/`error` in this table, and a queue scoped merely by status would re-POST a human approval nobody asked to resubmit. The handoff said "drain `pending` and `error`"; taken literally that is a defect. · Handoff 06; covered by `test_the_drain_never_touches_a_request_approval_row`.
- 2026-09-06 · `[landed c2b124a]` **A repeat affix confirmation raises no second event.** `_mark_affixed` already refuses to rewrite the original record, so the event fires on the state TRANSITION. One physical act is one event. · Handoff 06 B4.
- 2026-09-06 · `[landed c2b124a]` **A tenant with no `asset_events` config emits nothing, and says so at INFO.** That is the correct state for seven of eight tenants. Queueing events that can only dead-letter would turn "no Vendra here" into a permanent alarm. · Handoff 06 B3.
- 2026-09-06 · `[landed c2b124a]` **`max_attempts` is snapshotted onto the row at enqueue.** Retuning the retry policy must not retroactively resurrect events already dead or kill events still in flight. · Handoff 06; same reasoning as Vendra's outbox.
- 2026-09-06 · `[landed c2b124a]` **A manual retry extends the budget rather than resetting `attempts`.** The attempt count is the evidence of how hard the receiver was down; zeroing it erases the only record of that. · Handoff 06.
- 2026-09-06 · **No `ir.cron` fires on the local dev stack.** `config/odoo.19.conf` sets `db_name = odoo`, which pins Odoo's cron worker to that one (empty) database — the log reads *"Skipping database odoo as its base version is not 19.0.1.3"* once a minute and no tenant cron has ever run here. Production is unaffected: `k8s/dev/10-configmap-odoo-19.yaml` deliberately sets **no** `db_name`, so the worker enumerates every tenant. This is not new and is not caused by INT-05 — but it means the depreciation, PM and token-GC crons are equally dormant locally, and anything cron-driven must be proven with a throwaway worker container (`--database=<db>` and no `db_name`). · Handoff 06 live proof.
- 2026-09-06 · `[landed c2b124a]` **A `workflow.dispatch.log` row carrying delivery fields is a SEND INSTRUCTION, and is guarded like one.** `create`/`write` reject `event_type`, `config_id`, `next_attempt_at` and the rest unless the queue's own `cadra_event_dispatch` context flag is set. Without it any internal user — including handoff 05's deliberately scope-less `h05_nobody` — could hand-craft a row over `call_kw` and have Cadra POST a forged `asset.tag.affixed` to Vendra signed with the tenant's credentials, walking round the `tagging:write` separation entirely. The ACL cannot carry this: `_send_to_workflow` writes its audit row as the acting user, so `perm_create` has to stay. · Handoff 06 verification; the same ruling as "`readonly=True` is a web-client hint, not an ORM guard", applied to a new model.
- 2026-09-06 · `[landed c2b124a]` **No grace period may exclude the row whose own `_trigger` booked the run.** A 20-second "don't race the triggered delivery" clause excluded every freshly queued row, and Odoo consumes the trigger before running the action — so the wake-up was spent on an empty pass and every FIRST delivery waited for the 5-minute sweep. The race it guarded against cannot happen: Odoo holds `FOR NO KEY UPDATE SKIP LOCKED` on the `ir.cron` row for the whole action, serialising drains cluster-wide. That guarantee holds only while the cron is the sole entry point — an API route or server action over the queue would need its own row-level lock. · Handoff 06 verification; delivery went from 12 minutes to 11 seconds.
- 2026-09-06 · `[landed c2b124a]` **`event_enabled` pauses delivery; it does not discard events.** Dropping events raised while the switch is off means turning it back on silently loses every affix in between, with nothing to notice or backfill from. The enqueue path queues regardless; the drain excludes disabled targets in its own domain. · Handoff 06 verification; rule 3 — something that silently degrades is a defect even when it returns 200.
- 2026-09-06 · `[landed c2b124a]` **A status label must be true for every row that can carry it.** `error` was relabelled "Failed — Will Retry", which is a false promise on a request-approval dispatch — those are one-shot and are never retried. Labels stay neutral; the `Retrying` and `Dead Letters` filters carry the queue semantics instead. · Handoff 06 verification.
