# Handoff 57 — The gates, tonight

**Branch:** `feat/the-gates-tonight`
**Report:** `docs/handoffs/57-REPORT.md` — short; the drive matters more
than the prose tonight.
**Deadline:** deployed to the demo tenant with the switch on **by 07:00
Lagos, 8 October.** Branch from `dev`.

**Read first:** `docs/ADDENDUM-A-EVALUATION.md` §1 (one paragraph) and §7
(the rulings). The addendum itself is `docs/reference/addendum-a-
verification-gated-receipt.md`; tonight you need its **Section 3** state
table and **Section 4** roles, nothing else.

---

## 0 · What tonight is, and what it is not — read this twice

NRS has said a received unit is not an asset until Internal Audit has sighted
it, a tag is on it, and a maker-checker pair has registered it. **By tomorrow
morning the owner must show that chain working end to end on one laptop.**

The correct build is handoff 58 (a separate candidate model) and takes a
week. Tonight is **scaffolding**: the gate machine goes on the existing
`nrs.asset` record as a new field, and an asset that has not passed the
gates is hidden from the register. This is exactly the design the
Architect ruled against for the real build (evaluation §4.6) — and it is
chosen tonight **because** it reuses every proven path unchanged: INT-03
still creates the record, the label still prints, the affix dialog still
checks serial and label, the history still renders, SAP still gets the
master. Nothing is rewired; one field and six actions are added.

Say that in a comment at the top of the new code, dated, naming 58 as the
replacement. **Do not make it pretty. Make it true.**

### What is in

One tenant (the demo tenant — the owner names it), one laptop, this chain:

> receipt → *captured* → IAD verifies → IAD approves → Asset Controller
> requests tagging → label printed → affixed (existing) → Register Maker
> submits with SAP codes and cost → Register Checker approves →
> **the asset is in the register and SAP gets the master.**

Plus: a Candidates page, the no-two-gates rule, five new roles with
personas, and the register hiding candidates.

### What is out — do not start any of it

Delivery schedule, vendor notice, Tag-ID and Pool modes, notifications and
SLA clocks, evidence pack, material-master sync, GRN reversal to Vendra,
SAP asset-code request (the maker **types** it), the role-exclusion table,
delegation, per-role queues (one list with a filter), versioning of edits,
bulk actions, dashboards. **Vendra: nothing changes tonight.** INT-03
creates the asset exactly as it does now.

---

## 1 · Three workstreams, three agents, no shared files

Run them in parallel. The file boundaries below are the contract; an agent
that needs a file outside its boundary stops and says so rather than
editing it.

| Stream | Owns | Must not touch |
|---|---|---|
| **A · Server** | `myservice_asset_register/models/asset.py` (additive), new `models/asset_gates.py`, `myservice_api/controllers/v1_gates.py` (new), `controllers/utils.py` (scopes/groups rows only), `security/*.xml` (new groups), `models/asset_history.py` (new event labels), manifests, tests | the SPA, the persona scripts |
| **B · App** | `Frontend/…/src/pages/Candidates.tsx` (new), `src/components/GateActions.tsx` (new), `src/lib/dataProvider.ts` (additive functions + one default filter), `src/lib/navigation.ts` (one entry), `src/hooks/use-scopes.ts` and `pages/admin/Users.tsx` `SCOPE_WORDS` (the new scopes — the 52 guard will insist), e2e spec 57 | every server file |
| **C · Personas, flag, deploy** | `scripts/seed_demo_personas.py` (five new personas), the §7 settings switch, the demo script `docs/handoffs/57-DEMO-SCRIPT.md`, fan-out and deploy at the end | everything else |

**Hour 0, before anything else: Stream A publishes the route contract** —
the six routes' paths, bodies and responses as OpenAPI stubs (even if they
all return 501 for the first hour) — so Stream B builds against the real
shape from the start. The two meet at hour ~4 for the first end-to-end
drive.

---

## 2 · Stream A — the server

### 2a · One field, one table, one method

`nrs.asset.register_state`, Selection, exactly these values:
`captured`, `vfm_pending`, `vfm_verified`, `vfm_approved`, `vfm_query`,
`vfm_rejected`, `tag_requested`, `tag_issued`, `tagged`, `reg_submitted`,
`registered`. Default **`registered`** for every existing row (a migration
sets it, so nothing already on any tenant becomes a candidate overnight).

The machine is **one table** `(from, to, action, scope, gate)` in
`asset_gates.py` and **one method** `_fire_gate(action, reason=None,
payload=None)` that: checks the row exists for the current state; checks
the caller holds the scope; applies the no-two-gates rule (§2c); writes an
`nrs.asset.event` with a new type `gate_fired` carrying
`from`/`to`/`gate`/`action`/`reason`; moves the state. No other code path
changes `register_state` — pin it with a test that writes the field
directly and is refused.

Transitions tonight (gate in brackets):

| From | To | Action | Scope | Fired by |
|---|---|---|---|---|
| captured | vfm_pending | submit | `assets:write` [receipt/submit] | Store |
| vfm_pending | vfm_verified | verify | `vfm:verify` [verify] | IAD Officer — checklist JSON required, ≥1 evidence attachment required |
| vfm_verified | vfm_approved | approve | `vfm:approve` [approve] | IAD Approver — **must not be the verifier** |
| vfm_pending, vfm_verified | vfm_query | query | `vfm:verify` or `vfm:approve` | reason required |
| vfm_query | captured | resubmit | `assets:write` | Store, response required |
| vfm_pending, vfm_verified | vfm_rejected | reject | `vfm:approve` | reason required; terminal tonight |
| vfm_approved | tag_requested | request_tagging | `tagging:request` [tag request] | Asset Controller |
| tag_requested | tag_issued | *(system)* | — | fires inside request_tagging: the existing tag label is minted here (today it is minted at creation — **move the mint**; the label's number is the asset code, ruling §7/4.3 — if that is more than an hour, keep today's number and say so) |
| tag_issued | tagged | *(system)* | — | fires from the **existing** `_mark_affixed` success path |
| tagged | reg_submitted | register | `register:make` [make] | Register Maker — body: `sap_asset_code` (typed), `cost`, `cost_centre`, `capitalisation_date`, `asset_class` confirm |
| reg_submitted | registered | approve_registration | `register:check` [check] | Register Checker — **must not be the maker**; `sap_asset_code` present |
| reg_submitted | tagged | return_registration | `register:check` | reason required |

Rows for `expected`/`notified`/`issued` are **not** in the table tonight.

### 2b · Where INT-03 and INT-06 move

- `POST /api/v1/assets` (INT-03): when the §7 switch is **on**, the record
  is created with `register_state = captured` and **no tag label is
  minted**. Switch off: today's behaviour, byte for byte.
- **INT-06 (asset master to SAP)** fires on `registered`, not on affix, when
  the switch is on. Find the hook that fires it today, add the condition,
  and prove by driving that affixing a candidate sends **nothing** and the
  checker's approval sends the master.
- **Depreciation**: SAP owns it (ruling). Nothing here touches the module.

### 2c · The no-two-gates rule

Before firing gate *g* for user *u* on asset *a*: if any `gate_fired` event
on *a* has `user_id = u` and a **different** gate, refuse — the sentence
names the earlier action, its date and the user: *"You received this unit
on 7 Oct; a different person must verify it."* Never "permission denied".
The two maker-checker and officer-approver refusals fall out of this rule
for free; a test proves all three.

### 2d · The register hides candidates

Every list and count route over `nrs.asset` gains a default domain
`register_state = 'registered'`, overridable with `?register_state=any` or
`=<value>`. **One place** — whatever shared helper builds the asset domain
— not per route. The dashboard strip, the register list, the auditor's
reports, the export, the map: all registered-only by default. Print in the
report the list of routes that gained the filter and the one or two that
deliberately did not (the asset-by-id route must still return a candidate
to whoever may see it).

### 2e · Roles and scopes

Five groups in `security/asset_security.xml`, published names, `GROUP_SCOPES`
rows, `SCOPE_GROUPS` derivation — IAD Value-for-Money Officer
(`candidates:read`, `vfm:verify`), IAD Value-for-Money Approver
(`candidates:read`, `vfm:approve`), Asset Controller (`candidates:read`,
`tagging:request`), Register Maker (`candidates:read`, `register:make`),
Register Checker (`candidates:read`, `register:check`). Asset User and
Auditor gain `candidates:read`. `candidates:read` is what lets a role see
`?register_state=any`.

### 2f · Routes

Under `/api/v1/assets/<id>/gates/`: `submit`, `verify`, `approve`, `query`,
`resubmit`, `reject`, `request-tagging`, `register`, `approve-registration`,
`return-registration` — one POST each, each calling `_fire_gate`. Plus
`GET /api/v1/candidates` = the asset list with `register_state != registered`
and a `waiting_on` filter (`store`, `iad`, `controller`, `tagging`, `maker`,
`checker`) computed from the state. All in the census and the endpoint
index — the 52 guards will insist, which is good.

---

## 3 · Stream B — the app

- **Candidates page** (`/candidates`, sidebar under Asset Register, visible
  to `candidates:read`): the list, with state, mode (always *Serial*
  tonight), PO, GRN, serial, age in state, and the *waiting on* filter.
  Default filter: the signed-in person's own gate, derived from their roles
  — so Chukwudi's Candidates page opens on *waiting on IAD approver*.
- **Gate actions** on the asset page and on the candidate row: exactly the
  buttons the signed-in person's scope earns for the record's state, and
  **none that the server would refuse** — `can_fire` per action comes from
  the server (the serialiser adds `gates.available: [...]`, computed with the
  no-two-gates rule applied to the caller). The verify dialog: a checklist
  of four fixed items (quantity, specification, condition, price) and an
  attachment picker; refused without both. Reasons are required where the
  table says so and the dialog says so before the server does.
- **The register hides candidates** on the client too: the asset list and
  the strip use the default; the Candidates page passes
  `register_state=any`. A candidate's asset page shows a banner naming its
  state and the gate it is waiting on, so nobody mistakes it for a register
  asset.
- The scope map and `SCOPE_WORDS` gain the five scopes, with words.
- **Spec 57**: the whole chain as the personas, every refusal (same person
  at two gates, approve without verify, approve registration without SAP
  code), and the register count unchanged until the checker approves.

---

## 4 · Stream C — personas, switch, deploy

- **Five personas** on the demo tenant via the seed, demo-flagged like the
  six that exist, names checked at zero hits against the roll:
  IAD Officer, IAD Approver, Asset Controller, Register Maker, Register
  Checker. Chukwudi (Asset Manager) and Babatunde (tagger) keep their jobs.
  Record the logins the way 46 did — never in the repo.
- **The switch** `cadra.receipt.gated` (`ir.config_parameter`, pattern of
  handoff 48), on the Settings page with its sentence, exposed on
  `GET /api/v1/settings`, default off, **on for the demo tenant only** at
  deploy. A change is a configuration-record event.
- **`docs/handoffs/57-DEMO-SCRIPT.md`**: the chain as a numbered run sheet
  — who is signed in (Chrome profile), which page, which button, what the
  screen says. Eight people now; the owner has four profiles and will need
  the other four made before the room. Say so at the top.
- **Deploy**: fan-out to all tenants (the migration sets `registered` on
  every existing row — print the count per tenant), switch on for the demo
  tenant, the demo chain driven once **on the deployed tenant** with
  screenshots. That drive is the report.

---

## 5 · Order of the night

| Hour | A | B | C |
|---|---|---|---|
| 0–1 | field, migration, machine table, OpenAPI stubs **published** | reads the stubs; Candidates page skeleton against them | personas seeded on `test19`; switch built |
| 1–4 | transitions, rule, events, INT-03/INT-06 conditions, register filter | gate actions, dialogs, banner, scope words | demo script drafted |
| ~4 | **first end-to-end drive on `test19`, all three present** | | |
| 4–6 | fixes from the drive; tests; census/index guards green | spec 57; fixes | script corrected against what the screens actually say |
| 6–7 | full suite + in-registry | browser suite | fan-out, switch on demo tenant, deployed drive, screenshots |
| 7 | PR, merge (owner), deploy (owner) | | |

If at hour 4 the chain does not run end to end, **cut from the far end**:
drop return-registration, then query/resubmit, then the checklist
attachment requirement — never the no-two-gates rule and never the
register filter, because those two are the point.

---

## 6 · Verification — the minimum that still proves it

1. Full suite, in-registry with denominators, browser suite, on `test19`
   with the switch on; the full suite once more with it off.
2. Spec 57 green.
3. The deployed drive: screenshots of each gate as its persona, the
   register count before and after the checker's approval, the SAP master
   message appearing in the outbox only after approval.
4. The route list that gained the register filter, printed.
5. The sentence check — including the scaffolding comment, which must say
   plainly what this is.

## 7 · What the owner does tonight

- Names the demo tenant.
- Makes four more Chrome profiles before the room.
- Merges and deploys when the PR is green — the Builder cannot.
