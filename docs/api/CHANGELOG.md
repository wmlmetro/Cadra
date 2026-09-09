# Cadra API — changelog

Changes to the published `/api/v1/*` surface, newest first.

This file did not exist before handoff 09. It was created because two rulings
in that handoff both said "announce it in the API changelog" and there was
nowhere to announce anything — which is itself the problem it now solves. The
API has had a live external consumer since INT-03 (Vendra), and until now the
only record of a behaviour change was a handoff report, which an integrator
does not read.

**What belongs here.** Anything a consumer could observe: a new field, a new
route, a changed enum value, a changed error code, a changed status code, a
change in *when* a field's value moves. Additive changes are safe and are
listed for completeness; the ones that can break a consumer are marked
**BREAKING** or **BEHAVIOUR CHANGE**.

**What does not.** Internal refactors, tests, performance, anything a
consumer cannot see. Rule 1 in `CLAUDE.md` is the test: if Vendra could
branch on it, it goes here.

---

## 2026-09-09 — handoff 15

### WIDENING · The chain of custody is exempt from the per-credential record cap

**Who is affected:** any client provisioned with a `total_record_cap` — the
external default is 100 records of any one resource across all cursor pages.
This is a widening, so it breaks nobody. It is listed because a client that
built around 100 links should be able to find out that it no longer is.

`GET /assets/<id>/custody` now returns the **whole** chain however the
credential is capped. `include=custody` always did, because it does not
paginate — so until today the same question had two answers, one of them
silently shorter, depending on which way you asked it.

The cap is not going anywhere else. A chain of custody is not a page of a
register: it is one asset's complete record, bounded by how often that asset
changed hands rather than by how much data a tenant holds, and **a truncated
chain cannot be told from a complete one** — which is the entire finding the
model was built to close. `total_estimate` is the true count on both paths,
as everywhere.

The per-page ceiling is unchanged. It bounds the cost of one `SELECT` and is
not the commercial control; a capped client walks the whole chain with the
cursor.

### ADDITIVE · `GET /dashboard/fleet-command` names a panel it could not build

**Who is affected:** anybody reading the fleet-command payload. The new key is
present only when something failed, so its absence carries no meaning and a
client that never looks is unaffected.

Three panels — vendor performance, compliance alerts and recent maintenance
logs — returned an empty list for any failure, with nothing anywhere saying
so. Two of the three had been empty on **every tenant since they were
written**, because they read fields that do not exist on Odoo's fleet models:
compliance counted an `insurance_expiration_date` that is in no version of
`fleet.vehicle`, and the maintenance log read a `service_id` off
`fleet.vehicle.log.services`, which has `service_type_id`. Both are fixed.

A panel that now fails is named:

```json
{ "data": { "...": "...", "_warnings": { "unavailable": ["vendors"] } } }
```

A key listed there means the value in this payload is a placeholder, not an
answer. `[]` and "I could not build this" were the same response until today.

### BEHAVIOUR CHANGE · `POST /integrations/sap/employee-sync` no longer reports rows it then destroyed

**Who is affected:** anybody sending more than one employee in a batch. The
response shape is unchanged; what changes is that it is now true.

The per-employee handler isolated a failed row by calling `rollback()`. A
rollback is not row-scoped — it discards everything since the last commit —
so one unmappable employee erased **every employee written before it in the
same request**, while the `results` array had already recorded them as
`"status": "success"`. A caller reconciling against that array believed it
had written rows that no longer existed, and nothing in the response said
otherwise.

Each employee is now applied inside its own savepoint. A failure undoes that
employee and nothing else, `status` is `error` for it and stays correct for
the rows before it, and `error_message` carries the exception type as well as
its text — several ORM and Postgres errors stringify to an empty string, so
some callers were shown nothing at all.

The same fix applies to the file-upload path
(`POST /integrations/employees/import`, read back with
`GET /integrations/employees/import/<job_id>`), where a batch is 200 rows
between commits. That job's `error_samples` also returned `[]` when its own
stored error list could not be read — "no errors" for a job full of them —
and now returns an entry saying the detail is unreadable.

### NEW ENUM VALUE · `source: "test"` on a custody link

**Who is affected:** anybody reading `source` off a custody link. Additive —
a new value in an existing enum. If you branch on `source`, treat an
unrecognised value as "not a live change of custodian" rather than failing.

Cadra's own API test suite runs against live-shaped tenants and moves an
asset's custodian on purpose, because a test that does not exercise the
recorder proves nothing about whether the chain is written at all. The
recorder is append-only, so those links are **permanent**.

`source: "test"` is how you can tell. It is decided server-side from the
credential that made the change and never from anything a caller sends —
a header saying "this one is a test" would let anybody disguise a real change
of custodian as an artefact, in the one model whose whole value is that its
contents were not invented.

Same argument as `tracking_backfill`, one step further on: a reader of the
chain must be able to see what a link is without being told the artefacts
exist.

---

## 2026-09-09 — handoff 14

### NEW · The chain of custody is readable — `GET /assets/<id>/custody`

**Who is affected:** anybody asking who has held an asset. Nothing existing
changes shape.

Cadra now keeps an append-only record of every change of custodian, on a new
`nrs.asset.custody` model. Until this release the chain lived in Odoo's
chatter tracking values: no route exposed it, and a user with the right
groups could delete it. The PRD requires a record that *"cannot be edited
retrospectively, only appended"*, and a chain of custody that can be deleted
is not a chain of custody.

Two ways to read it:

```
GET /api/v1/assets/<id>/custody          # paginated, oldest first
GET /api/v1/assets/<id>?include=custody  # the whole chain, embedded
```

Both need `assets:read`. **There is no write endpoint and there will not
be** — a link is a side effect of a custodian change, never a payload, and a
route that accepted one would be a way to write history directly.

A link carries: `changed_at`, `from_custodian` / `to_custodian` (plus the
names **as recorded**, which survive the employee record being deleted),
`changed_by` — the acting user, which is a different question from who held
it — `reason`, and `source`.

**Read `source` before you draw a conclusion from a chain.** It is one of
`api_transfer`, `api_write`, `transfer`, `direct` or `tracking_backfill`.
`tracking_backfill` marks a link **reconstructed** from the chatter tracking
values that predate this model. The reconstruction is faithful — those rows
carry the actor and the timestamp — but it begins where `custodian_id` became
a tracked field, not where the register does. **A chain is therefore sparser
than the asset's own age, and that is the honest picture rather than a
defect.** An auditor told where the record begins can work with it; one who
discovers the gap later cannot trust any of it, including the complete part.

`include=custody` is deliberately **not** capped. The embedded `transfers`
list takes the last 20; "the last twenty custodians" is precisely the answer
an auditor cannot use, because a truncated chain cannot be told from a
complete one. The paginated route is there for a chain long enough to want
paging, and reports a true `total_estimate` like every other list endpoint.

> **Deployment note — schema before code, on every tenant.** This release
> adds a stored model (`nrs.asset.custody`), so `myservice_asset_register`
> must be upgraded on **every** tenant database *before* the image rolls
> forward. One Odoo registry serves them all: on a tenant that has not been
> upgraded, `nrs.asset.write({'custodian_id': ...})` reaches a table that
> does not exist and answers `500` with the transaction aborted — and that
> includes `POST /assets` carrying a custodian, which is on Vendra's INT-03
> path. The `upgrade-19` fan-out runs per database and must complete first.

### ADDITIVE · `custody_id` on the transfer-custody response

`POST /assets/<id>/transfer-custody` now returns
`data.custody_change.custody_id` — the append-only link that call produced.
Existing fields are unchanged.

### FIXED · Three auth routes answered HTML to a malformed body

`POST /auth/login`, `POST /auth/refresh` and `POST /auth/revoke` returned a
raw Odoo HTML 500 page — not a Cadra envelope — when an unauthenticated
caller sent a non-string where a string was expected. They now answer
`400 invalid_request` in the envelope, as `POST /auth/token` has since
handoff 12. `POST /auth/revoke` in particular documents that it always
answers `200 {"revoked": true}`, which was not true under a malformed body.

### ADMINISTRATIVE · A non-default record cap forces a one-hour token

`myservice.api.client` refuses to save a `token_ttl_seconds` above 3600 when
`max_page_limit` or `total_record_cap` differs from the default. The cap is
stamped into the access JWT and a JWT is unrevocable for its lifetime, so a
long-lived token is a raised limit that outlives the decision to lower it
again. Every client on every tenant is already at 3600, so nothing changes
today.

---

## 2026-09-08 — handoff 12

### BEHAVIOUR CHANGE · `pagination.total_estimate` now reports the TRUE count

**Who is affected:** every consumer of a list endpoint holding a token issued
by `POST /auth/token`. That is Vendra, and it will be Audit.

`total_estimate` used to report the size of the capped window, not the size of
the register. A credential limited to the first 100 records asked
`jaizbankplc` for its assets, received 100 rows, `next_cursor: null`, and
`total_estimate: 100` — while the tenant held 2,363. Nothing about that
response looked wrong.

It is now a `search_count` on the caller's own unclamped domain, on every
path. The rows a capped credential receives have **not** changed; only the
number describing them has.

**What this means for a consumer that already trusts `total_estimate`:** it
may now be much larger than the number of rows you can actually page through.
That is the honest picture. Compare it against what you received and branch on
the new `_warnings.truncated` block below rather than on `next_cursor: null`,
which cannot distinguish "that is everything" from "that is all you get".

Affected routes: `GET /assets`, `/locations`, `/locations/<id>/descendants`,
`/identity/employees`, `/identity/employees/<id>/assets`, `/requests`,
`/fleet`.

### NEW · `_warnings.truncated` on any response the record cap bit

A top-level envelope key, additive, present only when records were withheld:

```json
{"data": [...], "meta": {...}, "pagination": {...},
 "_warnings": {"truncated": {
   "cap": 100, "total": 2363,
   "reason": "This credential is limited to the first 100 records of any query. Filter the query, or contact WestMetro to raise the limit."}}}
```

It is a sibling of `data`, not a key inside it, because a list endpoint's
`data` is an array — unlike `data._warnings.rejected_fields` on the write
endpoints, which is unchanged.

**It describes the query, not the page.** Asking for 5 rows of a 2,410-asset
register warns on page one, because the wall at record 100 is already certain.
Telling you at the end of a twenty-page walk what you needed before you started
would be the same defect in a new place.

### NEW · `X-Cadra-Truncated` response header and a trailing comment on `export.csv`

`GET /assets/export.csv` bypasses the envelope, so a truncated file now
carries `X-Cadra-Truncated: 100/2363` and a final row beginning `# TRUNCATED:`.
A CSV that is silently a twentieth of the register is the artefact that gets
saved, emailed and cited.

### NEW · `total` on `GET /assets/export`

The JSON export's `count` was `len()` of a capped search, so a route calling
itself "export all assets" answered `count: 100` on a 2,363-asset tenant.
`count` still means "rows in this response"; the new `total` is the register.

### BEHAVIOUR CHANGE · the cap is per-client, not per-audience

It used to be decided by the `aud` claim, which only `POST /auth/login`
stamps — so the rule in force was "browsers are trusted, programs are not",
and the partner cap was pointed at Vendra, which holds a machine credential.
It is now decided by two fields on the client record (`total_record_cap`,
`max_page_limit`), stamped into the access token at mint time.

**Default is unchanged** (`0` = today's 100 on both), so an existing client
sees no difference. **The `vendra` client is uncapped by data migration on
every tenant** — as will be the audit client when INT-10 names one. Raising a
limit takes effect on the client's next token or refresh, i.e. within its TTL
(1 hour by default), not at the end of the 30-day refresh window.

### NO CHANGE · `POST /auth/token` still answers one 401 for every cause

Deliberately. Wrong secret, unknown client, archived client and a client id in
the wrong case (`Vendra` vs `vendra` — Postgres `=` is case-sensitive) are one
body, because distinguishing them is a client-id enumeration oracle. The cause
is now written server-side against the `request_id` the response already
carries; quote that id to WestMetro and the answer is one grep away. See
`docs/api/reading-an-auth-failure.md`.

---

## 2026-09-08 — handoff 10

### BEHAVIOUR CHANGE · `data.tagging.printed_at` / `printed_by` / `label_state` start moving

**Who is affected:** any consumer reading the `tagging` block, and anyone
filtering on `tag_label_state`.

`label_state` moves `issued → printed` from exactly one place —
`ir.actions.report._render_qweb_pdf`, the single funnel every print path goes
through. That hook declined to record anything whenever `res_ids` could be tag
label ids, and tag label ids and asset ids collide by construction: on the NRS
register **11,928 of 11,932 asset ids are also valid label ids**, 99.97%. So
the guard written for a rare edge case fired on the normal one. Every real
print was declined and the register held 11,879 labels at `issued` and exactly
one at `printed`.

The ids are now unambiguous — a report's `res_ids` are ids of the report's own
declared model, enforced where the caller hands them over — so:

| Field | Before | After |
|---|---|---|
| `data.tagging.printed_at` | `null` for effectively every asset | the datetime the label was rendered |
| `data.tagging.printed_by` | `null` | who issued the print instruction |
| `data.tagging.label_state` | `issued` until an affix skipped straight to `affixed` | `issued → printed → affixed` |
| `?tag_label_state=printed` | matched one row estate-wide | matches labels that have actually been printed |

**Nothing about the shape changes** — same keys, same types, same enum values.
What changes is that two of them stop being permanently null and one of them
starts visiting a state it was already documented to have. A consumer treating
`printed_at != null` as "a label exists on paper" gets the answer it always
expected; a consumer that had learned to ignore `printed` as a state that
never occurs should stop.

`is_tagged` is **unchanged**: it is still true only after an affix
confirmation whose scanned tag number matched the issued one. Printing is not
tagging.

### BEHAVIOUR CHANGE · `data.pm[].next_due_date` for a schedule that has never been serviced

**Who is affected:** any consumer reading the `pm` block on
`GET /api/v1/assets/{id}`.

A `nrs.asset.pm` row with an interval and no `last_done_date` reported
`next_due_date = today` — every day. That is not a due date, it is the absence
of one: it moved forward with the clock, so such a schedule could never be
overdue and the daily refresh rewrote the row on every tick. It now reports
`create_date + interval_days`, a fixed point, and can fall overdue like any
other.

Latent when shipped: there are zero `nrs.asset.pm` rows on any tenant, so no
consumer has ever seen the old value.

---

## 2026-09-07 — handoff 09

### BEHAVIOUR CHANGE · `error.code` — `forbidden` and `not_found` are reachable again

**Who is affected:** any consumer branching on `error.code` or on
`error.details.http_status`.

In Odoo 19 `AccessError`, `MissingError` and `ValidationError` are all
subclasses of `UserError`. The `cadra_route` handler chain caught `UserError`
first, so the `AccessError` and `MissingError` clauses beneath it were dead
code. Every Odoo-level access refusal answered `400 validation_failed` and
every missing record answered `400 validation_failed`. Two published error
codes were unreachable through that path for the whole life of the envelope.

The handlers are now ordered specific-first:

| Cause | Before | After |
|---|---|---|
| Odoo access refusal | `400 validation_failed` | `403 forbidden` |
| Record does not exist | `400 validation_failed` | `404 not_found` |
| Constraint / `UserError` | `400 validation_failed` | unchanged |

Routes that raise their own explicit `err(ERR_NOT_FOUND, …)` — which is most
of them — are unaffected; they never reached this path.

This corrects the envelope toward what the PRD §10.7 error table always said.
A consumer that pattern-matched on `validation_failed` to mean "any failure"
will now see the two more specific codes.

Guarded by `tests/test_source_guards.py::test_a_user_error_handler_never_shadows_a_more_specific_one`.

### BEHAVIOUR CHANGE · `GET /dashboard/{kpis,map,fleet-command}` — the scope is the gate

**Who is affected:** session tokens (`POST /auth/login`) holding
`dashboards:read`. API client tokens are unaffected in practice.

These three were the only routes in the API that did not `sudo()`. They read
`fleet.vehicle` and `generic.location` directly, so a caller holding
`dashboards:read` without the corresponding Odoo groups got an access refusal
carrying an Odoo group name — *"You are not allowed to access 'Vehicle'"* —
into the published envelope.

They now `sudo()` like every other route. Consequences:

- A caller **without** `dashboards:read` gets `403 forbidden` naming the
  scope, from the token gate, as on every other route.
- A caller **with** `dashboards:read` gets data. Previously a Security Officer
  holding the scope but no fleet group got an error; they now get the payload.
  That is the intended change: in this API the declared scope is the gate, and
  an Odoo group acting as a second, undeclared gate behind it is the defect,
  not the protection.
- No Odoo group name can reach a consumer through these routes any more.

The scope→group mapping in `utils.SCOPE_GROUPS` is retained as defence in
depth, not as the control.

Guarded by `tests/test_source_guards.py::test_the_dashboard_routes_sudo`.

### BEHAVIOUR CHANGE · `is_verified` on `nrs.asset` now expires

**Who is affected:** consumers reading `data.is_verified` or filtering with
`GET /assets?is_verified=`. Vendra does not read this field.

`is_verified` is a stored compute measured against today's date, but nothing
in the database changes on the day a verification lapses and nothing pushed a
recompute. It could therefore only ever move from `false` to `true` — an asset
verified once was reported verified for ever, and the field meant "verified
at some unknown point in the past", not "verified".

A daily cron now re-evaluates it, so the field can move `true → false` without
any write to the asset. The window is per-category
(`nrs.asset.category.verification_interval_days`), falling back to the tenant
parameter `cadra.assets.verification_interval_days`, falling back to 365 days.

**Nothing flips on any current tenant.** Measured across all eight local
databases: 17,123 assets, and `is_verified` is true on exactly **one** — a
single asset on `jaizbankplc`, the only one in the estate carrying a
`last_verified_date` at all, and recent enough to stay true under any of these
windows. (The ruling that prompted this said "true on zero assets"; it is one,
and that one does not move.) So this changes no value any consumer has ever
seen. It changes what the field will mean the first time anyone uses the
Verify button in earnest.

A permanent `true` is not a weaker version of this control. It is the
opposite of one.

### Additive · `verification_interval_days` on the asset-category settings API

Per-category verification window, in days. `0` or unset means "use the tenant
default" (`cadra.assets.verification_interval_days`, itself defaulting to 365).

- Serialised on `GET /settings/categories` and `GET /settings/categories/{id}`
  as `data.verification_interval_days` (integer, `null` when unset).
- Writable on `POST /settings/categories` and `PATCH /settings/categories/{id}`
  under `settings:write`, alongside its sibling `pm_interval_days`.
- Present in the OpenAPI request schemas for both write routes.

Additive and safe: a consumer that does not send it is unaffected, and a
consumer that does not read it sees no change. It is on the API rather than
back-office-only because `pm_interval_days` — the same kind of setting, the
same screen — already is, and a per-category cadence that can only be set in
Odoo would make the Settings screen quietly incomplete.
