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


## Handoff 34 — warranty

**What was built.** A warranty on an asset, captured the way it is quoted — a
duration and a start date, the expiry derived from them and a contradicting
expiry refused — with who honours it (a name) and the certificate number.
`data.warranty` publishes the answer and the working (`basis`), under the
writable names. Three filter states and an *expiring soon* window, on a Lagos
day; `warranty_status` on `/meta/enums`. Every later change is an append-only
`warranty_changed` event; a create writes none. The app has a Warranty section
on the asset form and page, a register filter that names its window, and four
dashboard tiles that each open exactly the rows they counted. **Accepted from
`myservice_api` 19.0.3.12.0** — Vendra's half is gated on that, and
`openapi.json` says it.

**How it was proved.** In-registry, CI's 11 modules on `test19`: 0 failed, 0
error(s) of 820. HTTP and browser results with their denominators are in
report 34 §6. Spec 34 acts list → asset → edit → asset → register filter →
dashboard tile → register in one session and reads the record back.

**Measured.** No warranty on any real tenant: 0 of 19,170 assets across the
seven non-test databases, every one *no warranty recorded*. A multi-asset
warranty write that would have told SAP of each disposal twice was found by
the verification pass and proved to fail first (`2 != 1`).

**Schema.** `myservice_asset_register` 19.0.1.18.0, `myservice_api`
19.0.3.12.0; four new columns on `nrs_asset`. All eight local databases
upgraded, one at a time, before the code was restarted onto them.

## 38 — Before the demo (2026-10-01)

**Built.** Two of the things said to NRS on 30 September, made true the day
before the 2 October demonstration, with the handoff's governing rule — do
not break the demo — deciding every shape below.

**A scanned serial number finds its asset.** `/barcode/lookup` and
`/tags/lookup` (and their `/api/v1` twins) resolve through ONE helper,
`_resolve_lookup`: tag number, then asset code, then serial number, each an
exact match. The serial is compared after stripping the query, case-
insensitively, with LIKE wildcards escaped; internal whitespace and leading
zeros stay significant. A serial on more than one asset is a 404 that says
how many (`details.ambiguous`, `details.matches`); every hit carries
`matched_by`, `tagged` and `serial_number`. The tag-number path is unchanged:
only an active tag resolves by number. The station's heading, placeholder
and result card say which field matched; its "no match" panel — never
reachable before, because a miss is a 404 the page caught as a generic
error — now renders.

**A faded tag is replaced by two people.** On `nrs.asset.tag.label`'s own
state machine, completed with handoff 35's conventions: `approver_id` named
at request; the decider from the token; self-approval refused in the model
(under `sudo()` too); a reason required to ask and to reject; nine stamp
fields refused by `write` without `cadra_tag_replacement`; a scrapped tag
cannot leave `scrapped`. Five routes in `myservice_api/controllers/v1_tags.py`
(`GET /tags/pending-replacements`, `GET /tags/<id>`, `POST …/request-
replacement`, `…/approve-replacement`, `…/reject-replacement`), the station's
*Replace tag* dialog, a *Replacement pending* panel with Approve / Reject,
and a *Pending replacements* card. `nrs.asset.change.request` was deliberately
not reused (`docs/DECISIONS.md`, 2026-10-01).

**How it was proved.** HTTP suite on `test19`: 1127 passed, 10 skipped (the
tenth is the new, named one: the API cannot create an untagged asset). In-
registry: `myservice_asset_register` 0 failed, 0 error(s) of 448;
`myservice_barcode_station` 0 of 20; `myservice_api` 0 of 287. Playwright
on `test19` with the service credential: 38 passed across specs 01, 10 and
38 — spec 38 scans tag, code, serial and serial-with-trailing-space and reads
the badge each time, then the service credential asks and `admin` approves
from the station in the SAME session; the old label is read back scrapped
with its reason and approver, the new one active and linked, the old number
a miss. Driven again by hand with screenshots and an API transcript (report
38 §E). In Postgres on `test19`: tag 28994 `NRS-GEN-5565` scrapped,
`replaced_by` 28997 `NRS-GEN-5568`, the old number existing exactly once.

**Measured.** Serials: 0 collide with a tag number or an asset code on any of
the eight tenants; `nrs19` has 11,332 of 11,951 assets with a serial, 1,291
serial values on more than one asset (3,455 rows; `PROBOOK` ×94), 574 with a
space inside, 10 beginning `0`; 0 stored serials carry padding (of 11,704
with one). Tag replacements: 0 had ever happened on any tenant
(`replaces_id`/`replaced_by_id` empty everywhere). IR numbers (handoff §C,
NOT built): `nrs19` holds NRS's real ones in a studio column `x_ir_number` —
11,385 of 11,386 employees, all digits, 10,498 five long and 887 eight long,
none containing a letter `O`, no duplicates — while `ir_number`, the field
Cadra's API and app read, is empty on that tenant; on the other seven, 193 of
193 IR numbers are `LASG-IR-00001`/`JAIZ-IR-…` seeds or `PYTEST-…` fixtures.

**Schema.** `myservice_asset_register` 19.0.1.20.0 (four columns on
`nrs_asset_tag_label`: `approver_id`, `rejected_by`, `rejected_date`,
`decision_reason`), `myservice_api` 19.0.3.14.0. All eight local databases
upgraded one at a time.

## 40 — The camera in the dialog (2026-10-01)

**Built.** The camera as a second way into the confirm dialog's tag field —
and, because it fell out of the same state, its serial field — as a Type /
Camera toggle drawn like the station's own, so it reads as the same control
in a smaller place. The camera is `components/BarcodeScanner.tsx` exactly as
the station's lookup box uses it, mounted under whichever field asked for
it, one at a time (`cameraFor: "tag" | "serial" | null`); the component
needed no change to be mounted a second time — it holds no module state and
stops its own stream on detection and on unmount. Default Type, never
auto-selected on a small screen or anywhere else. Nothing on the server
changed; `git diff --stat` shows no Python, XML or manifest.

**The one rule that differs from the handheld.** A trigger pull on a
handheld is a deliberate act — the person aimed at THIS label — so its
trailing Enter submits, as it did in report 39. A camera is looking at the
room continuously and reads whatever passes the lens: the neighbouring
label, a box, another asset's tag. So **a camera detection fills the field
and does not submit**; the toggle flips back to Type and the cursor returns
to the field, and Confirm is one more tap or Enter. The reasoning is in the
file comment because it will look like an inconsistency to the next reader.
Switching the camera off by any route — the toggle, a detection, a submit —
returns focus to the field it was open for; a close or a submit with the
camera open unmounts the scanner, which stops the stream.

**Found by the spec's first run.** With the preview open the dialog is
taller than a 720px viewport and *Confirm* was scrolled out of sight inside
it — the handoff's third check, *the preview does not reposition the dialog*,
read literally, and the dialog had not moved; its footer had. The first fix,
a sticky footer, floated between *Fitted by* and the serial field in the
screenshot with the serial input visible beneath it; it is not kept and the
reason is not claimed. The dialog is now a flex column capped at the viewport — header and
footer fixed, the form scrolling between them — and the spec asserts the
dialog's box is inside the viewport and *Confirm* is in view with the camera
running.

**How it was proved.** `e2e/tests/40-the-camera-in-the-dialog.spec.ts`, on
`test19`, with a REAL decode and no physical camera: Playwright's Chromium
on this Mac has `BarcodeDetector` and `*.localhost` is a secure context, so
the spec launches Chromium with its fake capture device playing a file, and
before each *Start camera* writes into that file a JPEG of the label Cadra
would PRINT for the number — `code128Svg`, the label printer's own encoder,
imported from the app's source — which the platform decodes off the video
(`docs/ENVIRONMENT-FACTS.md` has the recipe and its one race). Four tests:
camera on with nothing in front of it — the dialog's full markup without the
expected number, the scan box empty, the page marked blurred, the dialog
inside the viewport and *Confirm* in view, one live track; the label — the
field filled, the dialog still open, no refusal, the row read back unchanged,
the toggle on Type, the field focused, the track `ended`; the serial the same
way into its own field; *Confirm* — the row `affixed` / `is_tagged` /
`affixed_by_name` / `affixed_by` = the token's user, and every stream ever
opened `ended`. The WRONG label through the camera — filled and not sent,
then on *Confirm* the server's sentence as written and the input kept, the
row untouched; then the right number typed and Enter — the keyboard-wedge
path — records. Camera off: auto-focus, a toggle on and off (started and not)
returns focus, `pressSequentially` + Enter records. Cancel with the camera
running: every track `ended`, the page unblurred, the dialog reopened on Type
with the field focused and nothing written. Five screenshots in
`docs/handoffs/40-evidence/`. In Postgres on `test19` (final run, 19:36 WAT):
tag 29563 `NRS-ACS-817` `affixed` 18:36:44 UTC by uid 2, `E2E Camera Tagger`
(asset 66029); 29564 `NRS-ACS-818` affixed 18:36:48 after the camera-read
`NRS-ACS-8189` was refused (asset 66030); 29565 `NRS-ACS-819` affixed by
Enter (66031); 29566 `NRS-ACS-820` still `issued` — the close test wrote
nothing (66032). Seven earlier runs during the build left the same shape on
29297–29367, plus one `issued` orphan (29321) from the helper race before it
was fixed. Suites, in CI's order: HTTP (`tests/`, test19) 1127 passed, 10
skipped in 1126.85s (0:18:46), exit 0, 0 lines matching `of 0 tests` or
`CRITICAL`; the whole Playwright suite on `test19` with the service
credential, retries off: 163 passed, 2 failed, 4 skipped of 169 (7.3m) — the
2 are the two depreciation specs that fail on `dev` as well (`docs/GO-LIVE.md`
§13.5 item 13), the 4 are the three building-less move specs and
`08-requests` *create a request end-to-end* (no `type_id` in seed data), all
pre-existing; specs 39 + 40 re-run after the verification pass's fixes: 7
passed of 7, 0 skipped. In-registry suites not run: `git diff --stat` shows
no Python, XML or manifest change.

**Measured.** `test19` labels at 19:37 WAT, after every run above: 405
`affixed`, 6,455 `issued` on an active tag, 32 `issued` on a pending one, 23
`scrapped` (of 6,915). Report 39 counted 360 `affixed` of 6,354 before its
run; the difference is this evening's suites, not a tagger. No
schema change.

**Not proved, and said so.** A physical camera and a printed label: there is
no device here, and the fake-device proof covers the decode and the wiring,
not a lens, a focus distance or a glare. **The first real use on a device
prompts for camera permission**, before the preview appears; the component
already names the two other refusals (not https, no detector — Safari and
Firefox) and typing stays available under all three. One observation, not
fixed because the station is on the do-not-touch list: if the station's own
camera is running when *Confirm affixed* is clicked, it keeps running behind
the blurred page.

## 39 — The tagger confirms (2026-10-01)

**Built.** The one control the tagging integration had no person for. `POST
/api/v1/assets/<id>/tag-affixed` has existed, tested, since handoff 03 and is
the only thing that makes an asset `is_tagged`; nothing in the React app or
the legacy station called it, so the only way it had ever been done was
Postman. The barcode station's card now carries *Confirm affixed* beside
*Print label* and *Replace tag*, shown for an active tag whose label is
neither `affixed` nor `scrapped`; once it is affixed the card shows the
record — when, and who fitted it — instead of a button.

**The dialog.** An empty field the tagger scans the physical label into, an
optional *Fitted by*, and an optional serial field offered only when the
record has a serial to check against (the route refuses a scanned serial it
cannot check, so for such a record the dialog says why instead of offering
the field). Enter from a handheld scanner submits. **The expected number is
never handed over**: no default, no placeholder, no suggestion — and, after
the first screenshots showed it legibly in the scan box behind the overlay,
the card's number line is replaced, the scan box is emptied (query restored
on close) and the page is blurred while the dialog is open. The one place it
appears is the server's wrong-tag refusal, shown verbatim because the
handoff forbids paraphrasing it; the verification pass named the tension
and it is open for the Architect (`docs/DECISIONS.md`, 2026-10-01).

**The refusals, in sentences.** The server's message as written through the
app's standard error panel, the inputs kept: *Scanned tag X does not match
the tag issued for this asset (Y). The label on the asset is not the one
Cadra issued for it.*; the serial mismatch; *This asset has no active tag to
confirm* while a replacement is pending; a 403 through the same panel. A
scrapped label in hand is refused as a mismatch naming the tag NOW issued —
the model's own scrapped sentence is unreachable through the route, which
resolves `active_tag_id` first (`docs/DECISIONS.md`, 2026-10-01). A repeat
confirmation is shown in the dialog as *Already confirmed on <date> by
<name>. Nothing was changed* — detected by reading the `tagging` block before
posting, not by a clock, because the server answers a repeat exactly as it
answers a first.

**How it was proved.** Built (`BASE_PATH=/app/ npm run build`, served by the
local proxy from `dist/public`) and driven on `test19` by
`e2e/tests/39-the-tagger-confirms.spec.ts`: the dialog's full markup asserted
not to contain the number at open, every field empty, the scan box empty
and the page marked blurred; the wrong number refused with the sentence intact and
the input kept, the row read back unchanged; the wrong serial refused; the
right label with the serial and a name recorded, and the row read back
`affixed` / `is_tagged` / `affixed_by_name` / `affixed_by` = the token's
user; two tabs confirm the same label and the second says *already
confirmed*, the row's `affixed_at` and `affixed_by_name` unchanged; the
service credential asks for a replacement and `admin` approves while the
tagger's card is open, and the old number is refused first as *no active tag*
and then as a mismatch naming the new number. Six screenshots in
`docs/handoffs/39-evidence/`. In Postgres on `test19`: tag 29249
`NRS-ACS-733` `affixed` at `2026-10-01 17:30:41` by uid 2, `E2E Tagger`; tag
29250 `FIRST Tagger`; tag 29251 `scrapped` and 29252 `issued` on the same
asset (two earlier runs, before the scan-box leak was covered and before the
verification pass's fixes, left the same shape on tags 29004–29007 and
29008–29011). Suites: HTTP (`tests/`, test19) 1127 passed, 10 skipped in 1016.65s (0:16:56); 0 lines matching `of 0 tests` or `CRITICAL`; Playwright on `test19` 41 passed (1.5m) — the 38 of report 38 plus spec 39's 3; 0 skipped in 39.
In-registry suites not run: `git diff --stat` shows no Python, XML or
manifest change.

**Measured.** `test19` labels by state before the run: 360 `affixed`, 5,968
`issued`, 16 `issued`+`pending`, 10 `scrapped`, 0 `printed` (of 6,354). The
station's five tiles count none of these states — they read 6,348 / 6,332 /
24 / 16 / 24 before and after the confirmation in the screenshots — so "the
counters follow" is query invalidation that changes nothing visible today.
No schema change.

## 41 — Who has what (2026-10-01)

**Built.** Read only, end to end, and the first of three on people. On the
server: three `res.groups.privilege` records so the register groups and the
Auditor reach the Odoo 19 user form (`asset_security.xml`, `api_groups.xml`);
`GET /api/v1/users`, `/users/<id>` and `/roles` (`controllers/v1_users.py`,
`myservice_api` 19.0.3.15.0); and the four `/barcode/*` wrappers delegating
under sudo (`_delegate_reads_as_superuser`, `v1.py`). In the app: an
*Administration* nav group holding *Users* (`/admin/users`, deep link
`/admin/users/:id`) and *Access changes* (`/admin/access-changes?user_id=`),
both admin-scoped, both with no control that changes anything. Nothing in
this handoff writes membership; the in-registry suite counts the access
record, the membership relation and the implication relation before and
after every route and filter and asserts none moved.

**The two defects, and what each really was.**

*The groups were invisible.* Not because `category_id` was unset — `res.groups`
has no `category_id` on 19. A group reaches the user form through a
`res.groups.privilege`, rendered as one SELECTION per privilege; a group with
no privilege is shown only under *Extra Rights* and only in developer mode.
11 of 11 first-party groups on `test19` had none. Two privileges, not one:
*Asset Register* (User / Manager, one choice) and *Tag Issuing* (the
Tag-Issuing Unit alone), because a privilege's groups are mutually exclusive
on the form and a human tagger holds Asset User AND Tag-Issuing Unit. The
Auditor got *Audit*. The seven other groups are `docs/GO-LIVE.md` §18.2.
Screenshot: `docs/handoffs/41-evidence/01-user-form-after-privileges.png`.

*The refusal.* Driven, as a person holding ONLY the Tag-Issuing Unit
(`h41_tagger`, token scope `tagging:write`): on the station, every read
refused at the SCOPE gate — `/tags/pending-replacements`,
`/barcode/untagged`, `/barcode/recent-tags`, `/barcode/kpis` on load,
`/barcode/lookup` on scan, each `403 forbidden: Missing required scope(s):
assets:read`; no scan card, no *Confirm affixed*. No access rule grants a
scope, so the `ir.model.access` row the handoff weighed would have changed
none of it. With Asset User beside it (`h41_tagger_paired`) the station
loads and the scan resolves — and ONE read still refused: `/barcode/recent-tags`
→ `403 forbidden: You are not allowed to access 'Location' (generic.location)
records…`. Four barcode wrappers read as the token's user where every other
route reads under sudo; the owner's sentence (*'Asset Barcode Tag'*) is the
same defect for a user holding `assets:read` through a group with no rule on
the tag model. Fixed in one helper. After it: 0 refusals for the paired
tagger across login, station, lookup, dialog, register and asset page
(`41-evidence/drive-after-fix.json`: 40 API calls, 0 of them 403, the only
two non-2xx being the pre-login 401 probes every session makes; before the
fix the same drive had 2 of 41 at 403).

**The read API, and the trap it was written around.** `roles_direct` is
`group_ids` ∩ vocabulary, `roles_effective` is `all_group_ids` ∩ vocabulary
— on `test19`, `h41_manager` reads direct `[asset_manager]`, effective
`[asset_user, asset_manager]`; `admin` reads direct `[system, asset_manager]`,
effective `[system, asset_user, asset_manager, security_officer]`, the last
arriving through Security Administrator, a group outside the vocabulary — so an
effective role can come from a group the row does not name. The vocabulary
and the scopes per role are `GROUP_SCOPES` re-expressed (`/roles`), and the
HTTP suite recomputes every person's `scopes` from `/roles` × `roles_effective`.
`?role=` filters on `all_group_ids`, which is searchable on 19
(`_search_all_group_ids` → `group_ids.all_implied_ids`); proved live:
`?role=asset_user` returns `h41_manager`, `?role_direct=asset_user` does not.
An API credential's `scopes` are the credential's own (`scopes_source:
"credential"`).

**The screen leads with direct.** What somebody granted is what handoff 42
will act on; the implied roles are rendered beside them as lighter, dashed
pills marked *implied*, and the scopes block is derived from the effective
set in plain words. The role filter is on EFFECTIVE membership (*Can act
as*) and the page says so under the table.

**The access-changes link.** The report existed as a route and nowhere in
the app; `/admin/access-changes` renders it for a period (auto-walking the
cursor, because the report pages by account id and a filtered person may be
on any page) and filters client-side by `user_id`. No new data.

**Proved.** Playwright `e2e/tests/41-who-has-what.spec.ts`: 6 of 6 on
`test19`, including the absence proof (every button on both pages fails the
change-word regex; the only inputs are one search and two dates). The spec's
first run skipped its inactive-filter test on a tenant that HAS an inactive
account — it read an empty table mid-refetch as "none" — and its second run
counted zero events for a person with two, in the gap between request and
render; both races fixed in the spec, neither in the page.

**Found, for 42 and 43** (`docs/GO-LIVE.md` §18.2): nothing in Cadra refuses
a privilege escalation over the API — Odoo core guards only the disjoint
user-type groups and the last administrator, and every v1 route is sudo;
mail is configured on 0 of 8 local tenants; `auth_signup` is installed on
8 of 8.

## 42 — The grant, and the refusal (2026-10-02)

**Built, in the order the handoff set.** First the line that cannot be
crossed, in the model: `myservice_api/models/access_guard.py`, two
`_inherit` classes under every writer of membership the recorder
enumerated. Over the API — and only over the API — a membership change may
touch nothing but the four grantable groups (Asset User, Asset Manager,
Tag-Issuing Unit, Auditor; one constant, read by the guard and by
`GET /roles` as `grantable`); a caller may remove their own roles and may
not add one; groups cannot be created, deleted or re-meant; an account
cannot be deleted. A person created over the API may hold what Odoo gives
every new internal user (`_default_groups()`) plus the four, so handoff 43
can create people without loosening it. Then the write: `POST
/api/v1/users/<id>/roles` (`myservice_api` 19.0.3.16.0), and the *Change
roles* section on the Users page.

**How the guard tells our API from the system.** `bool(request)` and
`request.jwt_claims` — set by `require_jwt` on every `@cadra_route` and by
nothing else. The back office, XML-RPC, `odoo shell` (bootstrap), migrations,
hooks, security XML on install and upgrade, `auth_signup`'s template copy
and cron all lack it and are untouched. No context key, deliberately; the
markers that were considered and rejected are in `docs/DECISIONS.md`.
Diff-then-raise after `super()`, like the recorder, because `vals` cannot be
parsed honestly; the `AccessError` rolls the transaction back, recorder
rows included — the id gaps in `test19`'s access record (17133 → 17137 →
17140) are the refused writes' rows being rolled back after the sequence
had moved.

**Driven, verbatim** (`docs/handoffs/42-evidence/drive-refusals.txt`): the
suite credential, its user first stripped of `base.group_system` through
the back office so it is what report 41 claimed it was, asking for `system`
on its own user → `403 forbidden: Over the API only these roles can be
granted or removed: … 'Role / Administrator' is not one of them…`; the same
on `h41_manager` → the same sentence; the administrator adding Auditor to
their own account → `403 forbidden: Nobody grants themselves a role. admin
asked to add Auditor to their own account; another administrator has to do
that. Removing your own roles is allowed.`; the administrator removing their
own Asset Manager → 200, applied, effective loses Asset User; asking for it
back → refused; a dry run of a grant to `h41_manager` → 200, `applied:
false`, nothing written; the back office putting both groups back → two
rows, actor `Administrator`, `changed_by_login admin`, attributable. The
access record moved on exactly the allowed writes and on none of the
refused ones (9 → 10 → 10 → 10 → 10 → 11 → 11 → 13).

**Found by the drive, and corrected.** `scripts/bootstrap.py:509` grants
`base.group_system` to the user of every credential holding the `admin`
scope, so report 41's §G sentence — *the credential's user is deliberately
NOT a system administrator* — was false on every bootstrapped tenant; on
`test19` the suite credential's user held `Role / Administrator`. The
guard closes the escalation regardless (the group is not grantable over
the API whether or not the caller already holds it), and the drive proves
it on a credential that does not. The first draft of the route subtracted
the whole vocabulary before applying the desired set, so any change from
the screen on a row holding a non-grantable role (every administrator's
own) tried to remove `base.group_system` and was refused for that rather
than for what was asked; the route now replaces only the grantable four.

**The screen.** One section, hidden for a credential (*A credential's roles
follow its scopes and are not changed here.*): one checkbox per grantable
role, implication notes (*Asset Manager also confers Asset User*), Preview
(a dry run: *Will grant / Will revoke*, roles held and *Can act as* before →
after), Apply enabled only on a preview whose boxes have not changed since,
every refusal in the server's sentence. Screenshots in `42-evidence/`.

**Proved.** Playwright 41 (6, the absence proof rewritten to exempt exactly
the one section) + 42 (4: a grant through the screen read back from the
report with the admin session's own name as actor, then reverted the same
way; the self-grant refusal in words with Apply dark; one checkbox per
grantable role and none for `system`; the credential sentence) — 10 of 10.
The spec's first run found its own grant "missing": `Date.parse` on the
report's zoneless UTC `at` reads local time, an hour early in Lagos — the
bug report 39 fixed in the app, now fixed in the spec. Suites with
denominators in the report.

**And §5:** the seven remaining first-party groups have privileges —
Security (Officer / Manager / Administrator, one choice), Staff Bus (User /
Manager), WorkSpace Integration (its own category), Identity (the register's
category). 11 of 11.

**Measured ahead of 43.** Anonymous `GET /web/signup` → 404 on all four
cluster hosts; `/web/login` and `/web/reset_password` → 200. The door is
shut; why is 43's to say.

## 43 — The person, and the door (2026-10-02)

**Branch `fix/the-person-and-the-door` · `myservice_api` 19.0.3.17.1 · report `docs/handoffs/43-REPORT.md`, evidence `docs/handoffs/43-evidence/`.**

The last of three on people. NRS can now onboard their own: an
administrator creates a person with the roles they start with, the person
receives a letter from their own organisation with a link, sets a password,
and signs in holding exactly those roles; the first letter went to spam, so
there is a second; somebody leaves, and their access is taken away without
deleting anything.

### §0 · The door — measured, explained, shut by code

- Anonymous `GET /web/signup` → **404 on 4 of 4 cluster hosts**
  (`staging.app`, `jaizbankplc`, `lasg`, `gtb.cadra.ng`) and **8 of 8 local
  tenants**; `/web/login` and `/web/reset_password` → 200 on all. The login
  page carries no "Don't have an account?" link anywhere.
- **Why**, which report 42 owed: `auth_signup.invitation_scope = b2c` on 8
  of 8 — and never read. The `website` module overrides
  `res.users._get_signup_invitation_scope` with its own per-site field,
  `website.auth_signup_uninvited`, default `b2b`
  (`website/models/res_users.py:66-68`, `website.py:213-216`); the Settings
  toggle edits THAT field. So one click in *Settings › Customer Account*
  would have opened free sign-up on any tenant.
- **What a self-made account would have held:** on 19 `_create_user_from_template`
  copies `base.template_portal_user_id` — the `portaltemplate` user,
  `base.group_portal`, `share = True`. A share user: invisible to
  `/api/v1/users`, holding no scope, refused by handoff 42's guard on an
  API create. (`base.default_user`, which report 41 named, does not exist
  on 19.)
- **Does one exist:** no partner holds an outstanding sign-up token on any
  of the 8 tenants — 0 of 1,221 / 11,397 / 73 / 146 / 1,219 / 72 / 72 / 80
  on `cadra19` / `nrs19` / `gtb19` / `test19` / `nrs` / `lasg` / `gtb` /
  `jaizbankplc` (`test19`'s one is this handoff's fixture) — and 0 of
  6 / 11 / 12 / 52 / 5 / 12 / 12 / 19 users are share users beyond `public`
  and `portaltemplate`; and the
  `website` row — the thing that shuts the door — was created the same day
  as each database (`test19` 08-04, `nrs19` 08-06, `jaizbankplc`/`lasg`/`gtb`
  08-18, all equal to the first `res_users.create_date`). The door was
  never open on any of them.
- **Ruling landed:** `_get_signup_invitation_scope` returns `b2b` as a
  constant (`myservice_api/models/invitation.py`); the migration set the
  parameter (1 row changed on each of the 8 tenants) and the website field
  (0 rows on each; it already said `b2b`) so the Settings screen tells the
  truth, and switched off Odoo's *unregistered users* reminder cron (it
  mailed the inviter Odoo's letter five days after an unredeemed
  invitation). A fresh install gets the same from a `post_init_hook`. In-registry
  test: both rows forced to `b2c`, the method still answers `b2b`, the route
  still 404s.

### §1 · What was built

- **`POST /api/v1/users`** — name, email (also the login), the direct roles
  to start with, `send_invitation` (default true). A plain `res.users.create`
  with `_default_groups()` ∪ the roles, judged by handoff 42's guard on the
  model: `["asset_user", "system"]` → `403 forbidden` in the model's
  sentence, **no account created, no letter sent, no access-record row**.
  The create and the letter share one savepoint: a letter that cannot be
  sent → `500 server_misconfigured` naming the cause, nothing written.
  `409 conflict` on an address already held, naming the account and whether
  it is active. Idempotent.
- **`POST /users/<id>/invite`, `/deactivate`, `/reactivate`** — no body key
  accepted. Refusals in words: a credential's user (400), a deactivated
  person invited (409), somebody who has already signed in (409), your own
  account (403), the last active system administrator who is a person (409
  — the credentials' users hold the group too and do not count), already in
  that state (409).
- **`invitation` on every user row**: `never` / `outstanding` / `expired` /
  `redeemed` / `cancelled`, `sent_at`, `sent_by`, `sends`, `expires_at` —
  from three stored stamps on `res.users` written under EVERY path that
  sends a letter (API, user form, a create with an email), and the partner's
  live token.
- **The letters are the tenant's** (`res.users._action_reset_password`
  overridden, the one method the user form, `res.users.create`,
  `/web/reset_password` and the API all end in): the brand from
  `cadra.brand_*`, the organisation's name from `res.company`, one sentence
  saying what it is, the link in full under the button, the validity, no
  Odoo anywhere, no secret. The link is on the HOST THE REQUEST CAME IN ON
  (`res.partner._get_signup_url_for_action` overridden; core used
  `web.base.url`, which every administrator login rewrites and which lacked
  its port on 8 of 8 local tenants). A tenant with a brand logo gets it as
  an image URL (`GET /api/v1/brand/logo`, new, public); one without gets a
  wordmark in the brand colour. The From falls back as core's reset does:
  the company's address, the sender's, the recipient's own. An anonymous
  `/web/reset_password` keeps core's base URL (a forged `X-Forwarded-Host`
  cannot choose where a victim's link points); only an authenticated caller
  gets the request's host.
- **`require_jwt` refuses a deactivated account's live token** — until now
  only `/auth/login` and `/auth/refresh` looked at `active`, so a person
  deactivated at 09:00 kept the app until their token expired.
- **An archived nominee is refused on `/move`, `/transfer-custody` and tag
  replacement** (`_resolve_approver`): the picker hid them, the gate did not.
- **The Users page**: *Create person* (dialog: name, email, one checkbox
  per GRANTABLE role, "send the invitation now"), a *Sign-in* section on the
  detail panel with the invitation in words, *Re-send invitation*,
  *Deactivate* / *Reactivate* with a confirm dialog; every refusal verbatim
  in a red panel (`04-self-deactivate-refused.png`: *forbidden: You cannot
  deactivate your own account. Another administrator has to.*). A
  credential's panel says sign-in is managed with the credential. No
  password is typed anywhere; nothing is deleted.

### §1b · The letter, received

Proved on `test19` with a real SMTP catcher (Mailpit, `docs/ENVIRONMENT-FACTS.md`):

- **NRS brand** — company named *Nigeria Revenue Service*, no logo
  parameter → red band with the wordmark; From *Nigeria Revenue Service
  <facilities@nrs.gov.ng>*; subject *Nigeria Revenue Service asset register
  — your access*; link `http://test19.localhost:8069/web/signup?…token=…&redirect=%2Fapp%2F`;
  0 `<img>`, 0 `data:` URIs, 0 occurrences of "odoo". HTML view and TEXT
  view (what an HTML-stripping client shows) in `05-nrs-letter-inbox-*.png`;
  the text part carries the sentence and the link on its own.
- **Jaiz brand** — the same tenant's brand switched to `cadra_brand_jaiz`'s
  parameters and the company renamed *Jaiz Bank Plc*: From *Jaiz Bank Plc
  <customercare@jaizbankplc.com>*, blue `#004080` band, the Jaiz SVG as
  `<img src="…/api/v1/brand/logo">`, 0 occurrences of "NRS" or "Nigeria
  Revenue" (`06-jaiz-letter-inbox-html.png`). Brand restored afterwards.
- The screenshots are of a second NRS letter, sent after the verification
  pass to a mixed-case address: the sign-in name is printed as stored,
  lower-cased, because Odoo's login match is exact (report 43 §F.6).
- **Redeemed:** the link opened (Odoo's sign-up page, pre-filled), a
  password set, `POST /api/v1/auth/login` with it → 200 with the scopes of
  the two roles given (`assets:read … tagging:write`), `whoami` the new
  person, the row `redeemed`.
- **Not done here, by necessity:** a real inbox on the CLUSTER. Delivery
  there is through the HTTPS relay, which the Builder cannot exercise from
  this machine; it is the owner's step after the PR is merged and
  `upgrade-19` has rolled (report 43, *Needs the owner*).

### §2 · Measured, not built

- **A pending request stranded on a deactivated approver.** `test19`,
  request 1426: raised naming `h41_manager`, `h41_manager` deactivated; the
  queue row publishes `approver: {id, name}` and nothing about `active`,
  `/approvals/approvers?q=h41` → `[]`, the requester cannot decide it
  (self-approval refused), and only another eligible person could — the
  `admin` person rejected it. The request cannot be re-nominated: the model
  refuses every write but a transition. Nominating the deactivated person
  in the first place is now refused (`h41_leaver`: *"cannot be asked: their
  account is deactivated"*). What the queue should say, and whether a
  pending request may be re-nominated or deactivation refused while the
  person is a nominee, is `docs/GO-LIVE.md` §20.2 for the Architect.
- **Custody and deactivation.** Nothing first-party reacts to a user's
  `active`; the *Identity (clearance)* screen is 20 hard-coded mock rows
  with no route behind it; the real routine is SAP-status-driven and
  back-office only. On the real register custody is not tied to accounts:
  `nrs19` links 1 of 11,386 employees to a user; 87 of its 6,646 custodied
  assets are held by one of 207 archived employees, 0 flagged. `test19`:
  1 of 88 employees has a user. §20.2.

### Verification

See report 43 §E for the denominators of every suite run (HTTP suite,
in-registry `myservice_api`, Playwright 41–43) and the fan-out.

