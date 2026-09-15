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
