# Handoff 70 · The administrator can finish it

**For:** the Builder. **From:** the Architect, 28 October 2026.
**Branch:** `feat/the-administrator-can-finish-it` off `dev` (after PR #134 is
merged; if it is not yet, branch off `fix/where-the-captures-went`).
**Budget:** under 2 hours. Report ≤ 150 lines, `70-REPORT.md`; `70-PROGRESS.md`.
**Progress weights:** the switch 15 · receipt gates 25 · audit capture and
review 25 · the overrides report 15 · front end 10 · tests, CI, report 10.

---

## 0 · What the owner asked for

An **administrator** (Odoo `base.group_system`, the `admin` scope) must be able
to take a unit **through every step on their own**:

- the **receipt gates** for a unit from procurement (IAD verify, IAD approve,
  request tagging, affix, Register Maker, Register Checker), and the SAP link's
  maker and checker (handoff 65), **whatever roles the officers hold**;
- the **audit**: capture in any open campaign and **accept or return any
  capture**, whoever is named as capturer or reviewer, **their own included**.

Nobody else gets this. Not an Asset Manager, not an Asset Controller, and
never a machine credential.

## 1 · What already works, and the one thing in the way (checked in the code)

An admin's token already holds every scope: `admin` is a wildcard
(`utils.require_jwt`, `asset_gates._gate_scopes`). So no scope check refuses
an admin. **What refuses them is segregation of duties**, in four places:

| # | Rule | Where |
|---|---|---|
| S1 | the no-two-gates rule: one person may not fire two gates on one unit (the SAP link's maker/checker counts as gates) | `asset_gates._two_gates_refusal` / `_assert_two_gates`; `_gates_block` computes `can_fire` from it |
| S2 | a capturer must be named on the campaign | `audit_capture.py`, capture create, *"You are not a capturer on campaign …"* |
| S3 | nobody reviews their own capture | `_assert_reviewable`, `segregation_of_duties` |
| S4 | a reviewer must be named on the campaign | `_assert_reviewable`, *"You are not a reviewer on campaign …"* |

Lift these four for an administrator, **when the tenant has switched it on**,
and record every time it mattered. Nothing else changes.

## 2 · Rulings

1. **A tenant switch, off by default.** `cadra.admin_override`
   (`ir.config_parameter`), **off on every tenant**, including after upgrade.
   The owner turns it on per tenant. Reason: NRS's Addendum A §4 and the PRD
   require two people at each control, so on NRS's production tenant this stays
   off until NRS accepts in writing that administrators may act alone (the
   same as R7, the hosting ruling). Add it to `docs/GO-LIVE.md` as an
   acceptance item.
2. **Only a person, only an administrator.** Override applies when the acting
   `res.users` is in `base.group_system` **and** the switch is on. A token from
   `/auth/token` (a machine credential: Vendra's, the SAP sync's) never
   overrides, even if its user were in the group.
3. **No reason is asked.** The owner wants it quick. Instead **every act that
   needed the override is flagged and listed** (§5). An act an admin does that
   breaks no rule (they are simply the first person at that gate) is not an
   override and is not flagged.
4. **Everything else still holds:** a unit must be in the right state for the
   act; the affix still checks the scanned tag; a capture still needs a device
   bound to the person, a code reserved to them, the scanned label equal to the
   code, a room inside an open campaign, the five-day window. The override
   lifts **who** may act, never **what** is true.
5. **Vendra is unchanged.** The INT-05b events carry the actor as today; no new
   field is sent.

## 3 · The switch (15)

- `GET /api/v1/settings` → `admin_override: {"enabled": bool}` (every signed-in
  caller, so the front end can draw).
- `PATCH /api/v1/settings/admin-override` `{"enabled": true|false}`: the
  `admin` scope **only** (not `settings:write`). Recorded in Configuration
  changes like every setting.
- On **Settings › Receipt gates**, a second section for an admin:
  **"Administrators may act at every step"**, a switch, and one sentence under
  it: *"An administrator can then fire every receipt gate and review every
  audit capture alone, their own included. Each such act is listed under
  Audit › Administrator overrides. Leave it off where two people must sign."*
- One helper, `admin_overrides(env, user, token_kind)` → bool, used by every
  site below. Put it where both `asset_gates.py` and `audit_capture.py` can
  import it.

## 4 · Where the override applies

**Receipt gates and the SAP link (S1), 25.**
- `_two_gates_refusal(gate, user)`: when the helper is true, return no refusal.
- `_fire_gate`: when the act would have been refused by S1 and went ahead by
  the override, the gate event records `admin_override: true` and
  `override_of`: the sentence S1 would have answered (*"You verified on 20
  Oct; a different person must approve."*). Store both on `nrs.asset.event`
  (two new columns), not in free text.
- `_gates_block`: `can_fire: true` for an admin under the override, plus
  `"as_admin": true` on that action, so the page can label it.
- The Candidates list and its badge count what the admin may now act on.
- The SAP link's maker/checker: the same, through the same helper.

**Audit (S2–S4), 25.**
- Capture create: skip S2 for an admin under the override. The device and
  code rules stay (rule 4), so an admin capturing needs a device bound to
  them and a block, issued on Devices and codes as for anyone.
- `_assert_reviewable`: skip S3 and S4 for an admin under the override.
- Record on the capture: `reviewed_as_admin: true` and `override_of`: which
  rule(s) were lifted (`own_capture`, `not_a_reviewer`; for a capture,
  `not_a_capturer`). Published on the capture read.
- `POST /audit/captures/accept` (the batch): the same, per capture.
- `GET /audit/campaigns` is unchanged; the **front end** lists every open
  campaign for an admin under the override (§6).

## 5 · Audit › Administrator overrides (15)

- `GET /api/v1/reports/admin-overrides?since=&until=&kind=gate|audit`
  (`settings:read`, so the **Auditor** reads it too; and `admin`). Newest
  first, cursor-paged. Each row: when (Lagos time), who, the kind, the act
  (`verify`, `approve`, `register`, `accept capture`…), the asset (code) or
  capture (id, campaign, room), and `override_of` in words.
- A page under the sidebar's **Audit** group, **Administrator overrides**
  (`settings:read`), with a date filter and a CSV download. When the switch is
  on, a line at the top says so and since when; when off, *"Off on this
  tenant; the list shows any acts from when it was on."*
- A gate's history line on the asset reads *"Approved by A. Admin, as
  administrator (they verified on 20 Oct)."*

## 6 · Front end (10)

- The gate buttons on Candidates and the asset's gate panel: when an action
  carries `as_admin: true`, the button reads **"Approve (as administrator)"**
  (its verb, then the words).
- **Audit review**: an admin under the override sees **every open campaign**
  in the dropdown, not only those naming them, and on their own capture the
  Accept button reads **"Accept (as administrator)"**.
- **Audit capture** and the Barcode Station's Capture mode: every open campaign
  for an admin under the override.
- With the switch off, nothing on any page changes.

## 7 · Tests, CI, report (10)

- HTTP, switch **on**, one admin user, gates on: the admin takes one unit from
  IAD verify to registered alone; each gate after the first records
  `admin_override: true` with its `override_of`; the list shows them.
- The same with the switch **off**: the second gate is refused
  `segregation_of_duties`, as today.
- A non-admin Asset Manager with the switch on: still refused.
- A machine credential in `base.group_system` (create one in the test): still
  refused.
- Audit, switch on: the admin captures in a campaign that does not name them
  (with their own device and block), then accepts that same capture; both
  flagged. Switch off: both refused as today.
- Only `admin` can PATCH the switch; `settings:write` alone gets `403`.
- Browser: an admin switches it on, approves a candidate through two gates with
  the "(as administrator)" buttons, and finds both on Administrator overrides.
- CI gates on and off. If GitHub Actions is still not starting, run the suite
  locally and say so; do not wait (rule 9).
- `docs/DECISIONS.md`: the ruling and why it is off by default. `GO-LIVE.md`:
  the NRS acceptance item. Endpoint reference §11.8 (the setting), §14 (the
  gates), §19.7 (review), and the new report.

## 8 · Not in this handoff

- No change to the asset **move and disposal approvals** (§11) or the tag
  replacement approval. The owner did not ask for them. Check whether a system
  administrator can already approve each; say which in the report, change none.
- No change to role exclusions (an admin still cannot be granted Capturer and
  Reviewer together; they don't need to be).
- Nothing in Vendra.
