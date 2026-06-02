# Cadra Checkpoint — Spec vs. Code, 2026-05-26

A line-by-line audit of the current codebase against the
[Cadra Platform PRD v0.4](Cadra_Platform_PRD_v0.4.docx) and the
[Cadra at NRS Specification v0.1](Cadra_at_NRS_Specification_v0.1.docx).

## TL;DR

Per PRD §13.1, **v0.1 = Foundation (Months 1–4)**. We are roughly **40% of the
way through v0.1**. The CRUD spine of the three domains and the API gateway
envelope are in. Everything that makes Cadra commercially viable per the PRD —
webhook delivery, identity federation, ingestion services, audit logging,
multi-tenancy — is **not started**. Two architectural drifts (Odoo 15 vs.
FastAPI/Postgres/Keycloak; single-tenant vs. schema-per-tenant) are known and
intentional, scheduled for the Cadra v0.2 cutover.

The current code is a **working NRS prototype on Odoo**, not yet
**Cadra v0.1**. That's fine if the plan is still "NRS keeps running on Odoo
until v0.2 cuts everyone over to the productised stack." But every endpoint
we build on Odoo now is throw-away if v0.2 means a new codebase — worth being
honest about.

---

## Where we are vs. the v0.1 exit criteria (PRD §13.1)

| v0.1 exit criterion | Status | Note |
|---|---|---|
| All core entities can be created, read, updated, deleted via API and admin UI | ✅ done | Odoo gives us the UI; 36 REST endpoints give us the API |
| User can authenticate, raise a request, see it processed, view history | ✅ done | But "history" is Odoo `mail.thread`, not the immutable audit log the spec wants |
| Email to configured inbox creates a service request that appears in the admin UI | ❌ not started | No IMAP/SMTP/Graph integration anywhere in the repo |
| Platform deployed to staging, 1000-concurrent-user load test passes | ⚠️ partial | Deploy-ready done (bootstrap + Caddy + CI); no load test yet |
| NRS data migrated to v0.1 staging and validated | ❌ not started | We're running fresh seeded data, not migrated NRS data |
| Multi-tenant platform infrastructure (schema-per-tenant, Keycloak) | ❌ skipped | Single-tenant Odoo; Keycloak deferred to v0.2 |
| Event log + webhook infrastructure | ❌ not started | No `events` table, no subscription model, no dispatcher |
| CSV import/export connector (proves connector framework) | ⚠️ partial | `/assets/export.csv` exists; no import, no other entities, no framework |
| Email ingestion service | ❌ not started | |
| Audit logging baseline | ⚠️ partial | Odoo `mail.thread` tracking is implicit — not immutable, not separate, not query-shaped for compliance |
| Observability baseline | ❌ not started | No OpenTelemetry, no Grafana/Loki/Tempo, no per-tenant dashboards |

---

## What's built well

These are solid and match the spec:

- **API gateway envelope** ([myservice_api/controllers/utils.py](../myservice_api/controllers/utils.py)) —
  `{data, meta}` / `{error}` shape matches PRD §10.7 exactly, including
  `request_id`, `timestamp`, `version`, cursor pagination with
  `next_cursor`/`previous_cursor`/`total_estimate`
- **JWT + scope auth** — clean separation of resource-scope strings
  (`assets:read`, `requests:write`), proper 401/403 distinction
- **36 endpoints with REST semantics** — verbs, status codes, path parameters
  all correct after the refactor
- **OpenAPI auto-generation** — spec is generated from the `@cadra_route`
  registry at runtime, so it never drifts from the code
- **Test suite** — 70 cases (67 pass, 3 xfail upstream bugs), response
  capture, negative-path coverage, idempotency proven
- **Deploy-ready** — `scripts/bootstrap.sh` brings a cold stack to "API live,
  creds saved" in one command, dev + prod compose, Let's Encrypt, CI

---

## Significant drifts (built ≠ spec)

These work, but deviate from the spec in ways that matter. Each is fixable;
some are intentional.

### 1. Idempotency header name

- Spec (§7.4, §8.10): `Idempotency-Key`
- Code: `X-Idempotency-Key`
  ([utils.py:354](../myservice_api/controllers/utils.py#L354))
- **Impact**: low. Convention thing. Probably worth normalising before any
  external client integrates.

### 2. Asset lifecycle state machine (PRD §8.4)

- Spec: 10 states (`procured`, `received`, `tagged`, `deployed`,
  `in_maintenance`, `in_transit`, `idle`, `lost`, `retired`, `disposed`) with
  strict permitted-transition table
- Code: 5 states (`active`, `in_repair`, `disposed`, `transferred`,
  `missing`) in
  [myservice_asset_register/models/asset.py:77-83](../myservice_asset_register/models/asset.py#L77)
- No `/assets/{id}/transition` endpoint, no state machine enforcement, no
  transition events
- **Impact**: high. Lifecycle is the heart of the assets domain. The current
  model doesn't capture the procure→receive→tag→deploy flow that PO-driven
  creation (PRD §8.13) depends on. Cannot integrate with SAP MM without it.

### 3. Tag schema (PRD §8.3, NRS §3.2)

- Spec: `{ROOT}-{LOCATION_SEGMENT}-{CATEGORY}-{SEQUENCE}` →
  `NRS-HQ-F2-AC-0142`
- Code: `{ROOT}-{DOMAIN}-{SEQUENCE}` → `NRS-PLT-00001`
  ([asset_tag.py:150-187](../myservice_asset_register/models/asset_tag.py#L150))
- Location segment is missing; category collapsed to a domain enum
- **Impact**: medium. Spec calls this "the single most important field on
  the asset record" and says "long-term consequences." Tags are immutable
  once assigned, so we'd be migrating NRS into a non-spec format. Fix
  before NRS data load.

### 4. Auth stack (PRD §10.8)

- Spec: Keycloak realm-per-tenant, SAML 2.0 + OIDC + SCIM provisioning, role
  mapping from IdP groups
- Code: bespoke JWT HS256 with `api.client` model and client_credentials
  grant
- **Impact**: known and accepted for v0.1. Scheduled for v0.2 cutover.
  Worth noting that current client_credentials = machine-to-machine only;
  **no human-user auth path exists** — admin UI is Odoo's own auth,
  completely separate from the API. NRS spec §4 calls for SuccessFactors
  federation that we cannot deliver today.

### 5. Approval workflows (PRD §9.8, NRS §3.5)

- Spec: built-in approval engine (any-of-N, all-of-N, quorum, sequential) +
  external workflow callback as one option
- Code: external callback only
  ([myservice_workflow/controllers/callback.py](../myservice_workflow/controllers/callback.py)).
  No local approval engine. No `POST /requests/{id}/approve` endpoint.
- NRS §3.5 documents detailed approval chains (₦1M / ₦5M thresholds,
  multi-step approvers) we cannot configure today
- **Impact**: high. Disposal is gated by approval per spec, and we have no
  approval mechanism. Disposal endpoint also doesn't exist (see below).

---

## Missing v0.1 scope (significant gaps)

What the PRD says we should have by month 4, that we don't:

| Gap | Spec ref | Impact |
|---|---|---|
| **Webhook delivery infrastructure** | §10.6, NRS §8 | None of: event log, subscription model, HMAC signing, retry queue with exponential backoff, DLQ, at-least-once guarantees. NRS spec §8.3 lists 27 specific event types we should emit. We emit zero. |
| **Email ingestion** | §10.4, v0.1 scope | No IMAP / Graph / SMTP code. Cannot do the "email creates request" flow in v0.1 exit criteria. |
| **Audit log (immutable, queryable)** | §7.8, §8.14, §9.13 | We rely on `mail.thread` which is for messaging, not audit. Can be edited/deleted by admins. Doesn't capture source (API vs UI vs connector). Retention policy not configurable per tenant. |
| **`/documents` endpoint** | §10.9, §9.7 | No `POST /requests/{id}/attachments`. No pluggable storage. Attachments live in Odoo `ir.attachment` only. |
| **Faceted search endpoints** | §7.4, §8.10, §9.10 | No `POST /{resource}/search`. List-with-filters is the substitute; works for now. |
| **Bulk import/export** | §7.4, §8.10, §9.10 | No `POST /assets/bulk-import`, `POST /assets/bulk-move`, no equivalent for locations/requests. Only the assets CSV export. |
| **Location lifecycle** | §7.3 | No `lifecycle_state` field on locations (spec: `planned`/`active`/`under_renovation`/`decommissioned`/`archived`). Only Odoo's boolean `active`. No `POST /locations/{id}/transition`. |
| **`GET /locations/by-code/{code}`** | §7.4 | We don't have a `code` field at all; we use `name`. Need to add `code` and adjust the tag schema simultaneously. |
| **Resource cross-references** | §7.4, §8.10 | Missing: `GET /locations/{id}/assets`, `GET /locations/{id}/requests`, `GET /assets/{id}/movements`, `GET /assets/{id}/custodianship`, `GET /assets/{id}/maintenance`, `GET /assets/{id}/requests` |
| **Disposal endpoint + workflow** | §8.9, §8.10 | `POST /assets/{id}/dispose` doesn't exist. Spec says disposal must require approval and supporting documentation (refuses transition without it). |
| **Multi-tenancy** | §6.3, §11.3 | Single-tenant Odoo. No `tenant_id` on any row. Cross-tenant isolation impossible because there's no notion of a second tenant. |
| **Observability** | §10.10, §11.7 | No OpenTelemetry, no per-tenant integration dashboard, no replay tooling. Logs are Odoo's own. |

---

## Things we built that aren't in the v0.1 scope

Some things we built run ahead of the v0.1 plan — fine to keep but worth flagging:

- **`/api/v1/dashboard/*`, `/api/v1/security/*`, `/api/v1/fleet/*`,
  `/api/v1/fm/*`** — 9 dashboard GETs. PRD §13.3 puts "enhanced reporting
  and dashboards" in v0.3.
- **`/api/v1/barcode/*` + tag lookup** — barcode workflow. Spec mentions tag
  printing as part of v0.2 (NRS migration).
- **Fleet dashboard endpoint** — fleet is a v0.2 scope item per PRD §13.2.
- **`/api/v1/home/*`** — NRS-specific homepage form. Not in any release
  sequence; it's a holdover from the legacy myservice UI.

None of these are bad to have, but they're the "build what's in front of us"
pattern — solving the next visible thing rather than the next-most-important
per the spec. The integration fabric (the actual commercial value per
PRD §10) is not built, while we have dashboard endpoints.

---

## Recommendation: what to tackle next

Given the v0.2 cutover means a new stack anyway, two strategic options:

### Option A — Keep going on Odoo, target NRS production

What you actually need before NRS migration
([NRS §14](Cadra_at_NRS_Specification_v0.1.docx) sets out the migration plan):

1. **Webhook delivery** (PRD §10.6). It's the single biggest commercial gap
   and it's a self-contained piece of infrastructure. Build the event log
   table, subscription model, dispatcher worker, retry policy, HMAC signing.
   Even without subscribers, having the event log means we can replay
   history into v0.2.
2. **Real audit log**. New `cadra.audit.event` model — append-only, with
   actor, source (API/UI/connector), before/after JSON, indexed by entity.
   Replace the bits of `mail.thread` we lean on for compliance.
3. **Asset lifecycle alignment** with the spec's 10-state machine +
   `POST /assets/{id}/transition` + `POST /assets/{id}/dispose` with approval
   gate. This unlocks SAP MM later.
4. **Tag schema fix**: add `code` field on locations, change tag generator
   to `{ROOT}-{LOC_SEG}-{CAT}-{SEQ}`. **Do this before any production NRS
   data load**, because tags are immutable.

### Option B — Stop building features on Odoo, start v0.2

Spin up the FastAPI/Postgres/Keycloak skeleton per PRD §11. Migrate the API
surface we already have. Use the NRS-on-Odoo build as a working spec for the
v0.2 implementation. The pytest suite we have becomes the conformance suite
for v0.2.

### Read

**Option A** is the right call if NRS leadership wants to see something in
production this quarter, because v0.2 is months of foundation work before
any endpoint is reachable. **Option B** is the right call if the team is
willing to keep NRS on the legacy myservice for another 4-6 months while we
build the right thing.
