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
