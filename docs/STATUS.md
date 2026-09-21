# Status — Cadra

What is built, with the evidence and the measurements behind each item. Moved out of `CLAUDE.md` by handoff 19; **the rows below are exactly as they stood there, unchanged.**

`CLAUDE.md` carries a one-line-per-item version of this table — what it is, whether it is built, and the handoff that built it. This file is where the detail lives.

**Ruled ≠ landed.** This file lists landed work only. A decision that has been made but not built lives in `docs/DECISIONS.md` tagged `[ruled]`.

| Work | Status |
|---|---|
| Vendra integration CR-01 Parts A + B | **built** (handoff 01) — provenance fields, filters, idempotency and enum correctness |
| Vendra integration CR-01 Part C — tag capture | **built** (handoff 03) — `label_state`, print stamping, `POST /assets/<id>/tag-affixed` under `tagging:write`, `is_tagged` on the serialiser |
| Login scopes (handoff 05) | **landed** (`b8b6f64`) — group→scope mapping, `group_tag_issuing_unit`, `settings:write`, re-derivation on refresh, migration `19.0.3.1.0` |
| Demo-contract corrections (handoff 05) | **landed** (`82da6ab`) — `data.tagging.label_id`, `print-url` 404 fixed, `barcode/lookup` 500 fixed, `tag_label_state` validated |
| Tag transport — INT-05 outbound (handoff 06) | **landed** (`c2b124a`, PR #49) — `asset.tag.affixed` on an `ir.cron`-drained outbox with capped exponential backoff, `event_id` idempotency, 4xx-is-permanent classification and a visible `dead` state. Proven live on `nrs19` against a receiver taken down and brought back. Contract for Vendra: `docs/integrations/INT-05-tag-affixed-callback.md` |
| Dead `_sql_constraints` (handoff 02) | **closed** — all 8 reachable sites ported and enforced in every tenant; `docs/constraint-audit.md` |
| The scheduler reaches every tenant (handoff 08) | **built** — `db_name` removed from both dev configs, exposure handed to `dbfilter`. An affix on `nrs19` delivered to Vendra unattended (queued 20:39:37 → acknowledged 20:48:50), and on `jaizbankplc` in 4 seconds. Two orphan crons scheduling methods that never existed deleted before the first tick. |
| API clients act as themselves (handoff 08) | **built** — every `myservice.api.client` gets its own `res.users`; `affixed_by` names the Tag-Issuing Unit instead of Administrator. Migration `19.0.3.2.0`, 10 clients re-homed, 387 token rows repointed across all eight tenants. (The 11th client lives in the 15-era `odoo` database, which a 19 worker cannot load; it serves no tenant.) |
| Computes that never recompute (handoff 09) | **built** — five stored computes whose bodies read the clock now have crons that exist. `sla_breached` went 0 → 215 on `jaizbankplc` unattended, one minute after the upgrade, via the scheduler handoff 08 revived; 303 requests estate-wide. Two of the five (`security.guard.on_duty`, `fleet.vehicle.maintenance_status`) were found by an AST audit, not by the handoff. |
| Publisher telemetry stopped (handoff 09) | **built, and now live in the cluster too** — `publisher_warranty_url` in the k8s ConfigMap plus per-tenant deactivation of the telemetry and digest crons. Zero active telemetry crons on all 8 local tenants; the cluster half landed via `upgrade-19` on 2026-09-08 06:54, which rolls the image forward at the end of its run, and `myservice_nrs_base` `19.0.1.1.0` logged "2 third-party scheduled action(s) deactivated" on staging, gtb, jaizbankplc and lasg. The cluster's `nrs` database loads 14 modules against 77 and has none of ours, so layer 1 — a server-wide config — is what covers it. |
| The envelope's `forbidden` and `not_found` were unreachable (handoff 09) | **built** — in Odoo 19 `AccessError`/`MissingError` subclass `UserError`, so the broad clause caught them first and two published error codes had never been returned through `cadra_route`. |
| The print funnel recorded 2 prints in 17,217 labels (handoff 10) | **built and live in the cluster** (`upgrade-19` run `34214199930`, image `dev-e7293b4`) — two independent causes. The `_render_qweb_pdf` hook refused to stamp whenever `res_ids` could be tag-label ids, and on `nrs19` 11,928 of 11,932 asset ids are; the id space is now settled at the boundary (`report_action` refuses a foreign recordset). **And Odoo 19's report route is `readonly=True`, so the cursor serving a print could not write at all** — the stamp now takes its own read/write cursor. Proved live through the readonly route on `cadra19`. Two callers were found to be rendering the WRONG asset, and the A4 sheet report had never rendered anything on any tenant. |
| A ConfigMap change that never takes effect is now LOUD (handoff 10) | **built and exercised** — `deploy-dev` and `deploy-19` end by comparing the running `odoo-19` pod against the ConfigMaps they just applied and failing the job on a difference. Not automatic: `odoo-19` is `Recreate` on an RWO filestore, so rolling on every push would interrupt every live tenant to pick up a comment. Its first firing on `dev` read the pod's `odoo.conf.template` and all five `odoo-bootstrap-19` keys and reported each one — which is how the telemetry row above was confirmed rather than assumed. |
| The rest of the numbers that are not true (handoff 13) | **built** — the four counts derived from a capped window are counted over the register: `sla_pct` and the four FM KPIs, the fleet state/fuel breakdowns, and `kpis.vendors`. Proved live on `jaizbankplc` at 661 open requests, where the old code answered 500. A shape guard over the whole first-party tree flags any `len()` or tally over a limited `search()`, with an inline `capped-count-ok:` waiver for the four honest ones. |
| Two structural zeros found while fixing them (handoff 13) | **built** — the FM `in_progress` KPI filtered on stage code `progress`, which no tenant has ever had, and `kpis.vendors` read `state_id` off a model with no such field, so the AttributeError went into a bare `except: pass` and the vendor list was empty on every tenant. Neither was windowed. Both were zero, always. |
| The chain of custody (handoff 14) | **built** — `nrs.asset.custody`, append-only on the model so `write` and `unlink` raise even under `sudo()`, `ondelete='restrict'` on the asset. Recorded in `nrs.asset.write`, NOT in the transfer route: `custodian_id` has five writers and a chain with a gap in it cannot be told from a period of no movement. Backfilled from the chatter tracking values on all eight tenants, counts matching. `GET /assets/<id>/custody` and `include=custody`, uncapped. INT-10 §2.3 closed. |
| Three unauthenticated HTML 500s (handoff 14) | **built** — `/auth/login`, `/auth/refresh` and `/auth/revoke` answered a raw Odoo error page to a non-string body. Same two-line type check that fixed `/auth/token` in handoff 12; `/auth/revoke` had no `try/except` at all while documenting that it always answers `200`. |
| The staleness window is bounded (handoff 14) | **built** — a `myservice.api.client` whose pagination limits differ from the default cannot be saved with `token_ttl_seconds` above 3600. The JWT claim stays unrevocable for its TTL; what changes is that the TTL can no longer be a day. |
| The callback that answers twice (handoff 18) | **built** — both callback routes now fire on the TRANSITION, so a byte-identical replay writes nothing: no dispatch-log row, no chatter post, no stage write, no `date_moved`, no `request.event` row. A replay carrying a DIFFERENT outcome after a recorded decision is refused `409`, logged at ERROR, and changes nothing. `workspace_ref` was measured and rejected as the dedup key: it is optional in both published contracts and set on **0 of 407** requests estate-wide. |
| The `/api/v1` twin caught up with the legacy route (handoff 18) | **built** — v1 always appended a fresh inbound row and never reconciled the outbound dispatch it was answering, so on a tenant using it an answered dispatch read `sent` for ever. Both routes now share one `_reconcile_callback`. Latent, not live: there is no outbound request-approval row on any of the eight tenants because `_send_to_workflow` has never run on one. |
| The v1 callback stopped publishing an internal menu path (handoff 18) | **built and proved live on `jaizbankplc`** — it answered `400 validation_failed` carrying *"Please configure one under Settings → WorkSpace Integration"* to an API caller on any tenant with no WorkSpace config, which is all eight. Now `503 server_misconfigured`, body *"Workflow integration is not available"*, configuration sentence to the log. Same answer handoff 15 gave the legacy route. |
| A stage change is a stage CHANGING (handoff 18) | **built** — `request.request.write` branched on `'stage_id' in vals`, so writing a request's current stage back over itself appended a `stage_changed` row to the request's own audit trail and reset `date_moved`. Found through the callback; it affects every caller. `myservice_request_core` had no tests at all and now has 8, run by CI. |
| A credential out of a published image layer (handoff 18) | **built** — `Dockerfile.nrs-import` baked `ODOO_ADMIN_PW=admin` and the entrypoint passed it straight to XML-RPC as the tenant's admin. The default is gone, the entrypoint refuses and names the Secret, the k8s Job reads `cadra-odoo/ODOO_ADMIN_PASSWORD`, and `nrs-import.yml` pre-checks the key. `e2e/config.ts` keeps its `admin`/`admin` default only while the origin is local. The credential guard grew three readers — Dockerfile, k8s manifest, JS/TS — and `_CREDENTIAL_RE` grew `pw`, which it had been missing: `ODOO_ADMIN_PW` matched nothing. |
| `request.jsonrequest` is gone (handoff 18) | **built** — it is an attribute of the JSON-RPC dispatcher and never of `request`, so the unauthenticated SAP employee webhook answered a 500 on exactly the branch whose intended answer is `Empty payload`. A source guard now refuses the attribute anywhere in first-party Python. |
| The five §13.4 audit reports (handoff 23) | **complete** — the access-change and configuration-change reports close the set. The access report's honest answer is that no record exists: `res_groups_users_rel` is `(gid, uid)` with no timestamp or actor, `group_ids` carries no tracking, `mail_tracking_value` holds **0 rows** on `res.users`/`res.groups` on all eight tenants and `ir_logging` **0 rows** on all eight. Nothing synthesised; `group_changes_in_period` is a structural zero in the payload. The configuration report's ceiling is **22 keys estate-wide** written after creation, **12 by a named human** — `jaizbankplc` 7/5, `cadra19` 7/5, `nrs19` 2/1, `test19` 2/1, the other four 1/0. Both boundaries re-measured per request. Credential values redacted by key name (two-tier rule, 27 keys verified); `myservice_api.jwt_secret` proved never to leave the database. |
| The `Auditor` group (handoff 23) | **built** — `myservice_api.group_auditor`, six read scopes, no write scope, implied by nothing. Specification §3's `audit_viewer`, which INT-10 §4.3 had recorded as absent; `Vendra Auditor` is a Frappe role and exists in the sibling repo only. **Proved by acting**: a user holding exactly this group logs in through `/auth/login` and opens all five reports (5×200), and the same token is refused on five writes. `settings:read` is new with it. Landed on all eight tenants. |
| A disposal approved over the API (handoff 23) | **built** — `POST /assets/<id>/approve-disposal` under `approvals:write`, the gap report 16 named, closed without making the approver writable. Proved live on `jaizbankplc`: a body asking for approver uid 2 was refused `400`, the next call recorded uid **287** — the caller's own client user — and a third answered `409`. `disposal_approved_by` stays off `_WRITABLE_FIELDS`. |
| The test suite knows where it is allowed to write (handoff 25) | **built** — both suites read `cadra.database_class` from the target database with SQL and refuse anything but `test`; **absent refuses**. No bypass flag. The first cut read it through `get_param`, which is `@ormcache`d per worker, and leaked **24 writing tests onto an unmarked database** during its own proof run. |
| A record says it is a fixture, by derivation (handoff 26) | **built** — `is_test_fixture` on **14 models**, stamped from the acting credential at creation by `cadra.test.fixture.mixin`. Overwritten rather than defaulted, refused by `write()` unconditionally, in no `_WRITABLE_FIELDS`, published on the asset, location and request envelopes and annotated in OpenAPI. **Not retroactive, and documented as such in the field help, the changelog and the OpenAPI annotation.** Verified: 8 of 8 local tenants at 14 columns each; 8 in-registry tests including the ABSENT case (a record created under an unflagged credential must NOT be labelled) and the archived-credential case. |
| A creatable model with no self-label fails the suite (handoff 26) | **built** — `test_every_model_a_first_party_path_creates_is_classified` enumerates every model any first-party path can create and fails unless it is labelled, labelled another way, or exempted **with a written reason**. The labelled set is PARSED out of `test_fixture.py`, not copied into the guard. Six mutation proofs cover the spellings that blinded the previous guard, including `Client = env[MODEL]` then `Client.create(...)` and `self._helper().create(...)`. |
| The silent-instrument sweep (handoff 26) | **24 sites found, 13 fixed.** The worst was in the newest file: `remove_test_residue.py` read its production refusal through the ormcached `get_param` — the exact call the handoff that wrote that script had just proved unsafe. Also fixed: `bootstrap.py` minting a DUPLICATE API client because the existing one was archived (2 sites), `bootstrap.sh` turning a FAILED psql measurement into a confident "fresh DB" and running `odoo -i` against a populated database, `audit_report_fingerprint.sh` proving "nothing was written" by measuring nothing, and `seed_asset_costs.py` gating on a database NAME allowlist that did not contain `jaizbankplc`. The remaining 11 are listed with file and line in `docs/GO-LIVE.md` §10.2. |
| The open-items register (handoff 26) | **built** — `docs/GO-LIVE.md` Part II, one entry per outstanding item, tagged `[open]` / `[verified]` / `[landed, keep it that way]`, each with its evidence and the report it came from. **`admin`/`admin` was verified accepted on all eight local tenants on 2026-09-15** — a statement about what bootstrap leaves behind, not about this laptop. |
| Odoo 19 migration | in flight, separate track |

---

## Corrections found while moving this table (handoff 19)

The rows above are unchanged, so these are recorded here rather than edited in.

- **The table stopped at handoff 14, and had gaps before it.** Handoffs **04, 07, 11, 15, 16 and 17** all landed and have reports in `docs/handoffs/`, and none of them ever got a row. `CLAUDE.md`'s condensed table now carries all six; their detail is in their reports.
- **The handoff 11 row credited the wrong handoff.** Report 11 §7.2 *measured* the pagination cap and said it was "worth its own handoff"; handoff 12 built it (`1b009e6`). Handoff 11's own deliverables were the retired screens, one CI concurrency group and the INT-10 audit read-access contract. Corrected in `CLAUDE.md`.
- **`| Odoo 19 migration | in flight, separate track |` is stale in one direction and true in another.** The local stack, CI (`.github/workflows/ci.yml` runs the 19 stack only) and the whole cluster (`k8s/dev/` has no Odoo 15 manifest; every `*.cadra.ng` ingress points at `odoo-19`) are all on Odoo 19. **But the `prod` compose profile is still Odoo 15** — `docker-compose.yml` builds `cadra-odoo:15.0-dev` from `FROM odoo:15.0`, `docker-compose.prod.yml` overrides the command and not the image, and `docs/DEPLOYMENT.md` does not mention 19 anywhere — so a client deployed by the documented route today gets 15. The branch `chore/retire-15-stack` is cited in `CLAUDE.md` as evidence the migration is in flight; `git log dev..chore/retire-15-stack` is **empty**, so that branch carries no work.

## Handoff 20 — the Odoo 19 migration, closed for deployment

Appended rather than edited into the correction above, the same discipline the
chain of custody enforces in code: a landed record says what was true when it
was written, and what changed goes underneath it.

**The third correction in the previous section is no longer true, and this is
what made it false.**

- **Every compose profile now resolves to Odoo 19.** `docker-compose.yml`
  builds `cadra-odoo:19.0-dev` from `Dockerfile.odoo.19.dev`, so an overlay
  inherits the right runtime instead of having to override it. Verified
  against the real resolver: `docker compose -f docker-compose.yml -f
  docker-compose.prod.yml config` reports `image: cadra-odoo:19.0-dev`.
- **The Odoo 15 stack is deleted**, not repointed: `docker-compose.dev.yml`,
  `config/odoo.dev.conf`, `Dockerfile.odoo.dev` and `Dockerfile.odoo.k8s`.
  `CADRA_PROFILE=dev` resolves to `docker-compose.19.yml`; `dev19` is kept as
  an alias. Nothing in the repository can build an Odoo 15 image any more, and
  a test asserts it.
- **`config/odoo.prod.conf` is ported to 19.** Two settings in it were silent
  no-ops rather than errors, which is why nothing caught them: `longpolling_port`
  is ignored by a 19 server (measured — it leaves `gevent_port` at its
  default), and the addons path carried the Odoo 15 vendor tree instead of
  `crnd-19`/`oca-19`, where **11 module names collide** and Odoo takes the
  first path entry that has one.
- **Two independent guards now assert which runtime a profile gets**, because
  none did and that is why it drifted:
  `tests/test_deployment_profile.py` (static, no docker required, 12 tests)
  and the `prod-compose-lint` job in CI (the real `docker compose config`).
- **`docs/DEPLOYMENT.md` is rewritten** and names the deployment shape it
  describes in its first paragraph. It contained no occurrence of "19"; it now
  also carries the one-registry / schema-before-code rule that
  `docs/ENVIRONMENT-FACTS.md` had asserted was already there and which was not.
- **The prod profile could never reach its own database**, and a verification
  pass found it. A compose `command:` replaces CMD and not ENTRYPOINT, so the
  Odoo image never injected `--db_user`/`--db_password`, and
  `config/odoo.prod.conf` deliberately commits neither. Measured:
  `fe_sendauth: no password supplied`. The start-up sequence now lives in
  `config/prod-entrypoint.sh` — a file, so a test can execute it — and the
  profile was brought up on a throwaway project to prove it connects.
- **`chore/retire-15-stack` is still empty** and this work did not go there. It
  landed on `fix/prod-profile-is-19`; that branch can be deleted.

**Measured on this run**, on `jaizbankplc`:

| Suite | Result |
|---|---|
| `pytest tests/` | 483 passed, 28 skipped, 0 failed |
| In-registry Odoo, CI's 11 modules | 0 failed, 0 error(s) **of 378 tests** |

The 28 skips are all named: 24 admin-scope, 2 Turnstile-not-configured, 1 no
SAP asset number on this tenant, 1 no active `workflow.config`. None comes
from a file this handoff changed.

---

## Handoff 26 — the last handoff

**Suites, in CI's order, against `test19`:**

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) | **840 passed, 9 skipped, 0 failed** |
| In-registry, CI's 11 modules | **0 failed, 0 error(s) of 524 tests** |

**Both denominators checked, not the exit codes.** 840 against report 25's
811 is exactly the 29 pytest tests this handoff added (7 pattern-parity, 17
source-guard, 5 published-label); 524 against its 516 is exactly the 8
in-registry tests added. Neither run contains `of 0 tests` or a `CRITICAL`.
The 9 skips are report 25's 9, unchanged, from no file this handoff touched.

**The verification pass found thirteen defects in work already called
finished**, four of them serious enough to have failed this handoff on its
own subject — including a correction I wrote to report 25 that replaced one
false claim with another. All thirteen fixed; report 26 §9 lists them.

**Where the programme resumes from: `docs/GO-LIVE.md` Part II.** There is no
handoff 27. Contracted core scope was complete at handoff 23; what stands
between this system and a delivered one is four servers, a test SAP
environment, four answers from the NRS SAP team, a fixed-asset register
extract and some credential rotations — none of it code.

## Handoff 27 — what has happened to this asset (the cycle reopened by a client)

**What was built.** `GET /api/v1/assets/<id>/history` — one ordered history
of an asset, merged server-side (`nrs.asset.asset_history()`,
`myservice_api/models/asset_history.py`) from seven places a record is kept: the
registration stamp, the tag label's issue/print/affix stamps, the chain of
custody, transfer rows joined to the chatter row of the move they recorded,
every other tracked field change, the disposal approval, the integration
outbox, and maintenance requests. Rendered in the asset's *Audit & Review*
tab, below the approval status and review flags that were already there. No
stored field was added, so there was no migration and no tenant fan-out.

**What it measured first (§A), in one table.** "Can it be altered" means
through the application, by whom.

| Event | Record | Real time + actor? | Can it be altered afterwards? | Reaches back to |
|---|---|---|---|---|
| Custodian changed | `nrs.asset.custody` | yes / yes | **No — refused to everyone, sudo included** (Python; no DB trigger) | recorder live 2026-09-09; earlier links reconstructed from chatter and marked so |
| Registered | `create_date` / `create_uid` | yes / yes (the API client itself since handoff 08) | not editable; gone if the asset is deleted | always |
| Tag issued | label row's `create_date` | yes / yes | label row deletable by an asset manager | always |
| Tag printed / affixed | stamps on the label row | yes / yes | guarded by a context key a caller can set; only the LAST print is kept | handoff 03 / 10 |
| Disposal approved | two columns on the asset | yes / yes | not API-writable, **but both are inputs on the Odoo form**; a rewrite leaves a chatter line, which the history lists | handoff 23 |
| Sent to SAP / Tag unit | `workflow.dispatch.log` | yes / yes | no unlink ACL; delivery fields editable by workflow admin | handoff 06 / 07 |
| **Location moved** | `nrs.asset.transfer` **only via `POST /move` or a completed transfer**; otherwise chatter alone | date only on the row (instant = its `create_date`) / no mover on the row | **Yes — edit and delete by any asset manager, no trace; cascades away with the asset** | `nrs19`: 1,146 tracked moves, **1** transfer row |
| Status / condition changed | chatter only | yes / yes | **Yes — deletable by anyone who can edit the asset** | since the field was tracked |
| Verified | chatter only (one overwritten date on the asset) | yes / whoever saved the date | **Yes**; the app's Verify button records no verifier at all | — |
| Disposal executed | date on the asset | date / **no person** | tracked | handoff 16 |
| Cost, SAP field, GRN/PO reference changed | **nothing** | — | — | — |
| Maintenance performed | one overwritten date | date / no person | yes | — |

**In plain words:** of everything NRS watched in the demonstration, the
change of custodian is the only step with a record nobody can alter. The
location move they watched is recorded on a row an asset manager can edit or
delete. The history shows both — and grades them differently on their face.

**Suites, in CI's order, against `test19`:**

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) | **861 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 561 tests** |
| Playwright, the four Audit & Review specs | **4 passed** |
| Front end `tsc --noEmit` / `vite build` | clean / built |

**Both denominators reconcile.** 869 collected = report 26's 849 + 10 added
by PRs #74/#75 and the guard fix merged since + the 10 in
`tests/test_asset_history.py`. 561 = 524 + the 4 in PR #74's
`test_asset_default_order.py` + the 33 in
`myservice_api/tests/test_asset_history.py`. Neither run contains `of 0
tests` or a `CRITICAL`. **The skips went from 9 to 8 during the handoff** —
its own Playwright spec verified a `test19` asset, which gave the
`is_verified` partition test the data it had been skipping for want of. The
tenant changed; the suite did not. `docs/ENVIRONMENT-FACTS.md` has it.

**One test was proved to fail first.**
`test_nothing_sorts_before_the_registration_it_followed` was run with the
fix disabled and failed with `'custody_changed' != 'registered'` — the
defect exactly as it had appeared on the screen — before it was trusted.

## Handoff 28 — where a thing has been

**What was built.** `nrs.asset.movement` — an append-only record of every
change of an asset's location, written by `nrs.asset.write` and
`nrs.asset.create` underneath every writer, with the same guards as the chain
of custody. The asset history reads it, so a move made from now on is graded
`append_only`. Also: `POST /assets/<id>/verify`, which records who verified;
tracking on the six provenance fields and on the verifier, with the instant
it began stamped per database; and three screens that stopped saying what the record does not.
**A stored model, so a fan-out:** migration `19.0.1.15.0` on all eight local
tenants, one at a time, each verified by reading its own database (version,
table, six tracked fields, its own stamp).

**Every writer of `nrs.asset.location_id`, and whether the record sees it.**
Searched for, not taken from the handoff.

| Writer | Through the ORM? | Recorded? | `source` |
|---|---|---|---|
| `POST /api/v1/assets` | `create` | yes | `api_write` |
| `PATCH /api/v1/assets/<id>` — the quiet door, left open | `write` | yes | `api_write` |
| `POST /api/v1/assets/<id>/move` | `write` | yes, linked to its transfer | `api_move` |
| `nrs.asset.transfer.action_complete` | `write` | yes, linked to its transfer | `transfer` |
| The bulk importer, new and update lines | `create` / `write` | yes | `direct` |
| `load()` — `scripts/seed_nrs_assets.py`, ~11.9k rows | `create` / `write` | yes | `direct` |
| The seed scripts (`nrs_hq_seed`, gtb, jaiz, lasg, `seeds/nrs_asset_seed`) | `create` | yes | `direct` |
| Odoo **Duplicate** | `copy` → `create` | yes, the twin's own opening row — *but Duplicate itself fails today on the tag rule, see GO-LIVE §13.4* | `direct` |
| A shell or XML-RPC `write` | `write` | yes | `direct` |
| **The Odoo form** | — | **it was never a writer.** Readonly with no `force_save`, so the client discarded it on save. Now saved, and recorded. | `direct` |
| **Deleting a location** (`ON DELETE SET NULL`, cascading from a parent) | **no — the database does it** | yes, via `generic.location.unlink`, before the delete | `location_deleted` |
| Any API credential flagged as a test credential | as above | yes | `test` |
| Raw SQL · `_write()` · a database restore | no | **NO.** None exists in first-party code today; nothing in Python can stop one. The guarantee has no trigger under it. | — |

Not a writer, though it looks like one: `PATCH {"building_id": …}` — it
changes the building and leaves `location_id` where it was (GO-LIVE §13.4).

**The recorder is the innermost link** of both override chains
(`test_fixture` → `sap_asset_events` → `asset_depreciation` → `asset_sap` →
`asset.py`), so every module above it has finished with `vals` before it
reads them, and it compares the stored value before and after `super()`.

**Suites, in CI's order, against `test19`:**

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) | **872 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 614 tests** |
| Playwright, `06-asset-actions.spec.ts` | **10 passed, 3 skipped** — the three MOVE specs need two *building* locations, which `test19` lacks; the move path was driven by hand instead |
| Front end `tsc --noEmit` / `BASE_PATH=/app/ vite build` | clean / built |

**Both denominators reconcile.** 880 collected = handoff 27's 869 + 11 new. 614 = 561 + 53 new. Neither run contains `of 0 tests` or a `CRITICAL`; the 8 skips are handoff 27's 8.

**GitHub CI has not run this.** Every workflow on `wmlmetro` has been refused
by GitHub since 2026-09-18 14:13 UTC — *"recent account payments have failed
or your spending limit needs to be increased"* — with zero steps executed. A
red X on this handoff's PR means *never started*, not *failed*. The results
above are local, on this machine, and are not a substitute for CI.

## Handoff 29 — every control on the asset page

**What was built.** A front-end handoff. The asset's status pill told the
truth about data quality and nothing about lifecycle, so a missing or
disposed asset rendered as a green *Cleared* on every screen that used the
shared adapter. One status slot now shows the lifecycle state when it is
anything but active (`AssetStatusPills`, `LifecyclePill`), and `deriveStatus`
returns *Not in service* for it, so filters and grouping follow. The three
mock-era statuses were measured dead and deleted. The browser's two
`confirm()` dialogs are app dialogs. Condemn sets the condition as well as the
state. Counts that folded missing and disposed assets into stock were fixed
where the front end could and relabelled where it could not. A dead
notifications bell, a hard-coded user name and four dead tabs were removed.
The persisted query cache was versioned so a browser cannot outlive the fix.
One back-end fix rode along: the register snapshot's *today* is a Lagos day.

**How it was proved.** By acting: a harness clicks the real control as a
signed-in person on `test19`, and reads the asset's rows from Postgres before
and after. Report 29 §1 is the table.

| Control | The row | The screen, before | after |
|---|---|---|---|
| Mark missing | `state active → missing` | green *Cleared*, behind the browser's own dialog | red *Missing*, app dialog |
| Condemn | `state → disposed`; **now also `condition → decommissioned`** | *Good · Cleared* | *Decommissioned · Disposed* |
| Edit, with a typed asset tag | name saved, **tag unchanged**, 200 | no message | tag read-only, with the reason |
| Move · Transfer custody · Verify | movement / custody / verifier rows written | correct | correct — handoff 28's record sees what the UI does |

**Measured (§D):** `nrs19` reported *Verified: 1*, and that asset is the
missing one. `jaizbankplc`: 140 disposed assets, all rendered *Cleared*. After
the fix the asset dashboard's strip adds up for the first time — `test19`:
1,105 active + 0 under repair + 6 missing + 144 condemned = 1,255 on register,
each figure matched to SQL.

**Retracted here:** handoff 28's "architectural fact" that `require_jwt`
discards scopes. It sets `request.jwt_claims`. GO-LIVE §14.1.

**Suites, in CI's order, against `test19`:**

| Suite | Result |
|---|---|
| `pytest tests/` | **873 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 615 tests** |
| Playwright, the whole suite | **121 passed, 2 failed, 4 skipped** — both failures reproduce against `dev`'s front end (GO-LIVE §13.5.13) |
| Front end `tsc --noEmit` / `BASE_PATH=/app/ vite build` | clean / built |

**GitHub CI has still not run** — refused for billing since 2026-09-18, on
handoffs 27, 28 and this one. Left to find: GO-LIVE §13.5, eleven entries.

## Handoff 30 — before the fourth twin

**What was built.** Three more things get a record nobody can alter — every
verification, every change of status with its reason, and a change to the GRN
reference, the purchase order reference or the SAP asset number — as ONE
model, `nrs.asset.event`, rather than three more copies of custody. Custody
and movement were left where they are; the case both ways is report 30 §1.
The append-only guard is written once, as a mixin. Disposal is terminal, in
the model, for every writer. `POST /assets/<id>/mark-missing` and
`POST /assets/<id>/condemn` exist, each requiring a reason. `building_id`,
`floor_id` and `room_id` are no longer writable over the API. The app shows
`_warnings` for every write. A maintenance request's reference is published
in the asset history to a holder of `requests:read`. `sap_reconciliation_state
= exception` is a review status in the app.

**How it was proved.** Acted by hand against `test19` before any test
existed, and the rows read from Postgres: after four refused calls on a
disposed asset, 0 transfers, 0 movements, 0 custody links. Then:

| Suite | Result |
|---|---|
| HTTP, `test19` | 942 passed, 8 skipped — 60 of them the new file |
| in-registry, CI's 11 modules | 0 failed, 0 error(s) **of 733** (615 + 88 + 4 + 19, + 7 for the verification pass) |
| static guards | 228 passed — 1 failed before the guard was taught the new model |
| browser, `test19` | 131 passed, 4 skipped, 2 failed — the two GO-LIVE §13.5.13 already records |

**Measured.**

- **Nobody has ever un-disposed a real asset.** One transition out of
  `disposed` exists across all eight databases: `NRS-AST-047641`, an `E2E-…`
  fixture, 19:37 on 20 September — handoff 29's own probe.
- **`exception`: 34 on `nrs19`, 184 on `test19`, 593 on `jaizbankplc`, and
  every one of the 811 is a demo or a test fixture.** The *"34 real cases"*
  quoted since handoff 07 are 29 of handoff 04's demo assets and five
  handoff-05/06 probes. The control is live
  and its opening balance is zero.
- **Before this handoff's tests ran, no asset anywhere was `in_repair` or
  `transferred`, and nothing in the code writes `transferred`.**
- **Custody 1,341 rows, movement 420**, across eight databases, measured
  before the suites ran — the size of the migration that was NOT done.
- **Every API credential's user has no timezone**, so `context_today` is UTC
  for them: `/condemn` as specified would have dated the first hour of every
  Lagos day to the day before.

**Found because rejected fields became visible:** a category's depreciation
method could never be changed from the Depreciation settings screen. The API
publishes `method` and accepts `depreciation_method`; the screen echoed the
first, the API dropped it with a 200, and the screen said *"policy saved"*.

**Schema.** `myservice_asset_register` 19.0.1.16.0, `myservice_api`
19.0.3.10.0, one new table, no new column on an existing one. All eight local
databases upgraded, one at a time, before the code was restarted onto them.

