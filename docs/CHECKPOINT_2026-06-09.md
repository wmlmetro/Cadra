# Cadra Checkpoint — 2026-06-09

Two-week delta from [CHECKPOINT_2026-05-26.md](CHECKPOINT_2026-05-26.md).

## TL;DR

Two weeks of work, ~33 commits, all of it **operability and demo-readiness**.
Staging is now actually demo-able: mail egress works on K8s despite the DO
SMTP block, Swagger renders against the live host, the sidebar/nav is
legible, the FM dashboard map shows real Nigerian coordinates instead of
Edinburgh, and the NRS asset register seeds cleanly with stable External
IDs. None of the four strategic v0.1 gaps from the last checkpoint
(**webhooks, audit log, asset lifecycle, tag schema**) was touched. Status
against PRD §13.1 v0.1 exit criteria is unchanged.

This is the right work *if* the goal is "demo NRS-on-Odoo to stakeholders
this quarter" — which it appears to be, given the new
[demo card](api/cadra_api_demo_card.md). It is not progress against the
PRD v0.1 plan. Both can be true. Worth being explicit about which one
we're optimising for.

---

## What shipped since 2026-05-26

### Mail egress on K8s (the headline)

DO Kubernetes clusters block outbound SMTP. Five commits stood up an
HTTPS bridge so `mail.mail.send()` works without SMTP at all:

- [`myservice_email_relay`](../myservice_email_relay/) — new module,
  overrides `ir.mail_server.connect()` to POST to a relay endpoint
- Zoho outgoing-mail server seeded from env on boot
- Dockerfile fix to actually `COPY` the module into the image
- DEBUG logging of secret length+prefix for diagnosis

Commits: `8581786`, `4cca035`, `d2b40fa`, `497475d`, `8299887`.

### Identity bulk import

- `POST /api/v1/identity/employees/bulk` — async employee import
  (commit `a67be73`)
- `openpyxl` added to the image so the module loads
  (commit `34caf14`)

### Seed pipeline

- NRS asset register loader with External-ID backfill (`630400d`)
- Bulk-create perf fix in backfill (`2ec463f`)
- `full-no-master+geo` profile; staging switched to it (`938b820`)
- Real lat/lng on the dashboard map markers (`fd39846`)

### Theme / nav / UI polish

- Sidebar text contrast (`46abb66`), navbar dropdown legibility (`932f5b2`)
- Theme version bump to force asset bundle regen (`4fa3189`)
- Dedupe "Facility Command Center", promote Locations to sidebar
  (`1f91957`, `3aaec01`, `a6b9a9c`)
- FM dashboard: drop Edinburgh default, allow internal scroll
  (`b8a050c`, `cb50965`)

### API hygiene

- OpenAPI request schema + example support on `@cadra_route` (`ebc7f95`)
- Auto-generated `client_id` + editable client views (`036f3f9`, `0d57103`)
- Clean error responses, Swagger query-param visibility (`e189ff0`)
- Live-host `servers` URL so Swagger "Try it" works behind ingress
  (commit `2796485`, this checkpoint)
- Demo card + rendered endpoint reference PDF (commit `320df73`)

### CI / ops

- Optional module-upgrade Job in `deploy-dev.yml` for manifest changes
  (`1c58c85`) — addresses the "Odoo manifest changes need upgrade"
  memory item

---

## v0.1 exit criteria — status unchanged

| Criterion | 2026-05-26 | 2026-06-09 |
|---|---|---|
| CRUD via API + admin UI | ✅ | ✅ |
| Auth → raise request → see history | ✅ | ✅ |
| Email → service request | ❌ | ❌ *(mail egress now works; ingress still not built)* |
| Staging deployed + 1000-user load test | ⚠️ | ⚠️ *(staging more demo-able; still no load test)* |
| NRS data migrated to staging | ❌ | ❌ *(seed loader exists; real NRS data not migrated)* |
| Multi-tenant infra (Keycloak, schema/tenant) | ❌ | ❌ |
| Event log + webhook delivery | ❌ | ❌ |
| CSV import/export connector | ⚠️ | ⚠️ |
| Email ingestion | ❌ | ❌ |
| Audit logging baseline | ⚠️ | ⚠️ |
| Observability baseline | ❌ | ❌ |

The four irreversibility/commercial-value items from the last checkpoint
are still where they were:

1. **Tag schema** still `{ROOT}-{DOMAIN}-{SEQUENCE}`, not the spec's
   `{ROOT}-{LOCATION_SEGMENT}-{CATEGORY}-{SEQUENCE}`. Tags are immutable
   once assigned; fixing this after a production NRS load is painful.
2. **Asset lifecycle** still 5 states, not the spec's 10. No
   `POST /assets/{id}/transition`, no `POST /assets/{id}/dispose`, no
   approval gate.
3. **Webhook delivery** — no event log, no subscription model, no
   dispatcher, no HMAC signing. NRS spec §8.3 names 27 event types we
   emit zero of.
4. **Audit log** — still leaning on `mail.thread` for compliance. No
   separate, immutable `cadra.audit.event` model.

---

## What this checkpoint is honest about

The 2026-05-26 checkpoint asked: **Option A** (keep building NRS on Odoo,
target near-term production) or **Option B** (stop and start v0.2 on
FastAPI/Postgres/Keycloak)?

The two weeks since have answered with action, not words: we're on
**Option A**, and within Option A we've prioritised "make the demo work
end-to-end" over "fix the items that will hurt most after NRS production
data lands." That's a defensible product call — a working demo unlocks
stakeholder buy-in that funds the rest — but it does mean the technical
debt clock is ticking on the tag schema in particular.

---

## Recommended next moves

In order of "irreversible if we don't do it before NRS data lands":

1. **Tag schema fix** — add `code` field on locations, rework the
   generator to `{ROOT}-{LOC_SEG}-{CAT}-{SEQ}`. Cannot be done cleanly
   after production data load. One focused PR.
2. **Asset lifecycle + disposal endpoint** — 10-state machine,
   `POST /assets/{id}/transition`, `POST /assets/{id}/dispose` with
   approval gate. Unblocks SAP MM integration later and is required
   before any disposal workflow can be configured for NRS.
3. **Webhook delivery skeleton** — event log table, subscription model,
   dispatcher worker, HMAC signing, retry/DLQ. Self-contained; can be
   built without disturbing existing endpoints. Even with zero
   subscribers, having the event log preserves history we can replay
   into v0.2.
4. **Real audit log** — `cadra.audit.event` model alongside (not
   replacing) `mail.thread`. Append-only, indexed by entity, captures
   source (API/UI/connector).

Items 1 and 2 are the irreversible ones. If forced to pick one for the
next sprint, it's **tag schema**.
