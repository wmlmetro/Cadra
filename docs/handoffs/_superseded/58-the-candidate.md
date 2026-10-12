# Handoff 58 — The candidate

**Branch:** `feat/the-candidate`
**Report:** `docs/handoffs/58-REPORT.md`
**Runs after:** handoff 57 (the overnight MVP) is merged and the demo it was built for has happened — this handoff replaces 57's scaffolding with the real model. Handoff 53 may run before or after
this; handoff 55 is **on hold** (see `docs/ADDENDUM-A-EVALUATION.md` §7).
Branch from `dev`.

**Read first:** `docs/reference/addendum-a-verification-gated-receipt.md`
(the specification, by section and AD-number) and
`docs/ADDENDUM-A-EVALUATION.md` (what it keeps, what it replaces, the
owner's rulings in §7). This handoff is **Phase A of six**. It builds the
spine every later phase hangs on, and it changes nothing a tenant sees until
that tenant is switched on.

---

## 0 · What this is

NRS has ruled that a received unit is not an asset. It is an **asset
candidate** that passes four gates — Store, Internal Audit, tagging,
registration — and becomes a register asset only when a Register Checker
approves. Today INT-03 creates an `nrs.asset` the moment Vendra posts a
receipt. That stops, for tenants that opt in.

Phase A builds: the candidate model and its state machine; the roles and
the two segregation rules; the append-only record of every transition; the
route Vendra will call instead of `POST /assets`; a read-only screen; and a
per-tenant switch. **No gate's screen is built here** — IAD's review, the
tagging request, the maker-checker — those are Phases B to D. Phase A is
the thing they act on.

The rulings that bind this handoff (evaluation §7):

- **Serialised items keep "no serial, no receipt."** Items without a
  manufacturer serial follow Section 12: Tag-ID and Pool modes.
- **SAP owns depreciation.** Candidates are invisible to the depreciation
  module; nothing here touches it.
- **The label carries the asset code**, reserved at tagging request (Phase C).
  Phase A reserves nothing; it only makes room.
- **The candidate is a separate model**, not a flag on `nrs.asset`.

---

## 1 · The model

`nrs.asset.candidate`, in `myservice_asset_register`, with these fields —
the addendum's `AssetCandidate` (§6) plus what the ingest needs:

- `name` — the candidate's own number, its own sequence (`NRS-CND-000001`).
  **Not** an asset code; the code comes in Phase C.
- `grn_number`, `po_number`, `po_line_no`, `vendra_unit_ref` (the
  `Vendra Receipt Serial` row name, so the two halves can always be joined).
- `identification_mode` — Selection `serial` / `tag_id` / `pool`, copied from
  the category at creation (§2).
- `serial_no` — nullable; **required when mode is `serial`**, refused when it
  is not (a serial on a pool line is a data error, not extra information).
- `make`, `model`, `class_attributes` (JSON, per class — §2), `photo_ids`
  (attachments), `condition_on_arrival`, `received_by_name`, `received_at`.
- `category_id` → `nrs.asset.category`; `sap_material_code`.
- `state` — the Section 3 machine, exactly these values and no others:
  `expected`, `notified`, `received`, `captured`, `vfm_pending`,
  `vfm_verified`, `vfm_approved`, `vfm_query`, `vfm_rejected`,
  `tag_requested`, `tag_issued`, `tagged`, `reg_submitted`, `registered`,
  `issued`. Phase A **creates candidates at `captured`** (Vendra posts a
  receipt that already carries the attributes — ruling §7/4.1) and offers
  one transition: `captured → vfm_pending` (*submit to IAD*). Every other
  transition is declared in the machine, guarded, and **refused with the
  sentence "not built yet: Phase <letter>"** so the table exists once and
  nobody re-derives it in Phase B.
- `version` — integer; a change to captured data makes a new version and
  an event, never an overwrite (§6 rules).
- `asset_id` → `nrs.asset`, nullable, set only at `registered` (Phase D).
  Phase A: always empty, and a test pins that.

Rules on the model:

- `serial_no`, where present, is unique across **all non-rejected
  candidates and all `nrs.asset`** — one SQL-level check, one sentence
  naming the existing record (AD-09).
- The machine is a table `(from, to, action, scope, gate)` in one place.
  Every transition goes through one method that checks the row exists, the
  caller's scope, and §3's segregation rule; writes the event; moves the
  state. There is no second path.
- **Append-only mixin** on the candidate event model (§4): reuse
  `nrs.asset.append.only.mixin` as the asset event does.

## 2 · Identification mode on the class

`nrs.asset.category` gains `identification_mode` (Selection
`serial`/`tag_id`/`pool`, default `serial`) and `class_attributes_schema`
(JSON: the mandatory capture fields per class, AD-08/AD-32 — for `serial`
the default schema is `make`, `model`; for `tag_id` it is description,
make or brand, model or catalogue reference, colour, material, dimensions).
Seeded defaults per D11: vehicles and electronics `serial`; furniture
`tag_id`; **nothing defaults to `pool`** — the owner has skipped the
threshold decision (D10) and a pool line is a deliberate choice an Asset
Controller makes. Changing a class's mode affects only new candidates
(AD-31); pin it.

Expose both on `GET /api/v1/asset-categories` (Vendra reads them — its
Phase A needs the mode at the receipt). Additive; CHANGELOG.

## 3 · Roles and the two segregation rules

New groups, with published names in `PUBLISHED_ROLE_NAMES` and rows in
`GROUP_SCOPES` (the SPA scope map and `SCOPE_WORDS` must follow — the 52
guard will insist):

| Group | Published name | Scopes added |
|---|---|---|
| `group_iad_vfm_officer` | IAD Value-for-Money Officer | `candidates:read`, `vfm:verify` |
| `group_iad_vfm_approver` | IAD Value-for-Money Approver | `candidates:read`, `vfm:approve` |
| `group_asset_controller` | Asset Controller | `candidates:read`, `tagging:request`, `settings:classes` |
| `group_register_maker` | Register Maker | `candidates:read`, `register:make` |
| `group_register_checker` | Register Checker | `candidates:read`, `register:check` |

Existing roles: **Asset User** (the storekeeper) gains `candidates:read`
and `candidates:write` (capture, submit); **Auditor** gains
`candidates:read`. Nobody else changes.

**Rule 1 — no user fires two gates on one record** (§4 enforcement 1). The
gates are: receipt, VfM verify, VfM approve, tag request, tagging, register
make, register check. Implement it in the transition method: before firing
gate *g* for user *u* on candidate *c*, if any event on *c* records *u*
firing a *different* gate, refuse — and the refusal **names the earlier
action, its date, and the user**, never "permission denied" (enforcement 4).
In Phase A only two gates can fire (receipt via ingest, submit), so the rule
is proved by test with a fixture that stamps earlier gates directly.

**Rule 2 — the role-exclusion table** (§4 enforcement 2). A new model
`nrs.role.exclusion` (`group_a`, `group_b`, `active`, `reason`), seeded with
the defaults: Store (Asset User/Officer) with any IAD, Tagging or Register
role; Register Maker with Register Checker. Enforced **where grants happen**:
`access_guard.py` already refuses `base.*` grants and self-grants over the
API; add the exclusion check beside them, in the model, under every writer,
with the refusal naming both roles and the exclusion's reason. The Users
page shows the refusal verbatim. Editable by `settings:write` holders on the
existing Settings surface; every change goes to the configuration record.

**Delegation** (enforcement 3) is **not** Phase A — named here as deferred.

## 4 · The record

`nrs.asset.candidate.event` — the addendum's `AuditEvent` for candidates:
`candidate_id`, `from_state`, `to_state`, `action`, `gate`, `user_id`,
`role_key`, `occurred_at`, `reason`, `before`/`after` (JSON, for edited
fields), `evidence_ids`, `client` (`web`/`api`/`scanner`). Append-only,
`ondelete='restrict'` on the candidate for the asset event's reason. A
candidate's history route returns them in order, each with a sentence, the
way `asset_history.py` renders asset events — **reuse that renderer's
shape**, do not invent a second grammar.

## 5 · The route Vendra calls — A2

`POST /api/v1/candidates/ingest`, scope `ingestion:write` (the INT-03
credential already holds it). Body: one GRN line, with either a list of
units (Serial / Tag-ID: one candidate each) or a quantity per location
(Pool: one candidate per location). Idempotent on
`(grn_number, po_line_no, vendra_unit_ref)` — a second delivery returns the
same candidate ids and creates nothing (§9 Idempotency). Refusals:
serial missing on a `serial`-mode class; serial present on a `pool` line;
unknown category; a serial already on record — each a 4xx naming the line.

**The existing `POST /api/v1/assets` is untouched.** Which route Vendra
calls is Vendra's decision, driven by the switch in §7.

## 6 · The screen

Two read-only pages in the SPA, visible to anyone holding `candidates:read`:
a **Candidates** list (state, mode, PO, GRN, serial or quantity, age in
state) with a *waiting on* filter that, in Phase A, knows only *Store*
(captured) and *IAD* (vfm_pending); and a **candidate page** with its
fields, its photos, and its history. One action: **Submit to IAD**, for
Asset User, on a `captured` candidate. Nothing else is clickable. Sidebar
entry under Asset Register, behind the §7 switch, so a tenant that has not
opted in never sees it. Role-scoped like every other item (handoff 46).

## 7 · The switch

`cadra.receipt.gated` — an `ir.config_parameter` per tenant, the same
pattern as the sidebar switches (handoff 48), shown on the Settings page
with the sentence: *When on, receipts from Vendra become candidates that
pass Internal Audit, tagging and registration before they are assets. When
off, receipts create assets directly, as before.* Default **off** on every
tenant. Exposed on `GET /api/v1/settings` so Vendra can read it (Vendra's
Phase A reads it to decide which route to call). A change is a
configuration-record event.

**When off, nothing in this handoff is reachable from the UI**, and
`POST /assets` behaves exactly as before — the full suite on a flag-off
tenant is the proof. When on, `POST /assets` from the INT-03 credential is
**refused** with a sentence pointing at `/candidates/ingest`, so a
mis-configured Vendra cannot quietly create assets around the gates.

## 8 · What must not change

- `nrs.asset`, its tags, its history, its routes. Zero diff outside the
  additive category fields.
- The depreciation module. Candidates do not exist to it.
- Any existing scope's meaning. New scopes only.
- Client tenants: the switch is off everywhere; the fan-out installs the
  models and nothing else moves.

## 9 · Verification

1. Full suite, in-registry with denominators, browser suite — on a
   **flag-off** tenant first, proving nothing changed; then on `test19`
   with the flag on.
2. The machine: a test per declared transition — the one that works, and
   every other refused with *not built yet: Phase <letter>*; the
   denominator printed (15 states, N transitions).
3. Rule 1 proved with a stamped fixture: the same user refused at a second
   gate, the refusal naming the first. Rule 2 proved on the Users page and
   over the API: the default exclusions refused with both role names; an
   exclusion toggled off lets the grant through; the change in the
   configuration record.
4. `/candidates/ingest` driven over HTTP: Serial line of five → five
   candidates at `captured`; the same body again → the same five ids,
   nothing new; a line without serials on a `serial` class → refused
   naming the line; a `tag_id` line without serials → accepted; a `pool`
   line with a serial → refused.
5. Submit to IAD as Halima: state moves, event written with her name and
   the gate; the Candidates list's *waiting on IAD* shows it; as Zainab
   (Auditor) the page is readable and the button is absent.
6. Flag on: `POST /assets` with the INT-03 credential refused with the
   pointer sentence. Flag off: accepted as before.
7. Scope-map guard, endpoint-index guard, census — all green with the new
   denominators printed.
8. Fan-out to all tenants; zero error lines; the switch off on every one,
   printed.

And the standing sentence check.

## 10 · The question for the report

**What in the addendum's state table did you have to interpret?** Every
row where the guard, the role or the trigger was ambiguous enough that you
chose — list the choice and what the alternative would have been. Phase B
is written from that list.
