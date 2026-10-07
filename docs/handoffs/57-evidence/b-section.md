# Report 57 — Stream B (the app)

## What was built

- **Candidates** (`/candidates`, Asset Register group, `candidates:read`): received units not yet on the
  register — unit, state, mode (*Serial*, always, tonight), PO, GRN, serial, time in state, waiting on,
  and the person's own actions. One list, one *waiting on* filter, opened on the signed-in person's own
  gate as derived from their scopes (`register:check` → Register Checker, `register:make` → Register
  Maker, `vfm:approve` → IAD approver, `vfm:verify` → IAD officer, `tagging:request` → Asset Controller,
  `tagging:write` → Tagging, `assets:write` → Store; an administrator opens on *Anybody*).
  `?waiting_on=<gate>` forces a filter. Says so when `receipt_gated` is off.
- **Gate buttons** (`components/GateActions.tsx`) on the candidate row and the asset page: a button for
  every entry of `gates.available` with `can_fire: true`, and for one the no-two-gates rule refuses,
  the server's sentence instead of a button. Dialogs: verify (four fixed checks + evidence picker,
  refused without both), register (SAP code, cost, cost centre, capitalisation date, asset class
  pre-set to the unit's own), reason for query / reject / return, answer for resubmit — each says
  what is still missing before it will send.
- **The banner** on a candidate's asset page: *Not on the register — this is a received unit still
  passing its gates*, its state, who it waits on, since when; at *Tag issued*, a link to the Barcode
  Station. On a candidate the register's own controls (Edit, Move, Verify, Condemn…) and the
  Cleared/In Review/Disposed strip are not drawn, and *Asset Tag* reads the server's tag
  (*Not issued yet*) — the adapter's fallback to the asset code made an unlabelled unit look labelled.
- **The register hides candidates on the client** by sending no `register_state` — the server's default
  is registered-only; the Candidates page reads `/candidates`.
- **Scopes**: the six new ones in `SCOPE` and `SCOPE_WORDS`, with words (`test_scope_maps.py` green).
- Nav entry and route for Stream C's *Receipt gates* settings page (`settings:write`).

## Drive — spec 57 on `test19`, switch ON

`(cd e2e && E2E_ORIGIN=http://test19.localhost:8069 E2E_SHOTS=… npx playwright test 57-)`

**10 passed, 0 failed, 0 skipped — of 10** (1.0 min; three green runs in total, the first at 2.1 min).
Each person signs in through the real sign-in page:

| # | Person (persona key) | Where | Result |
|---|---|---|---|
| 0 | Store Officer (`storekeeper`) — API, as INT-03 | `POST /assets` | `captured`, `tagging.label_id` null, register count unchanged, not in `GET /assets?q=` |
| 1 | Store Officer | Candidates (opens on *Store*) → Submit | `vfm_pending` |
| 2 | IAD officer (`iad_officer`) | Candidates (opens on *IAD officer*) → Verify: button disabled until four checks AND evidence | `vfm_verified` |
| 3 | IAD approver (`iad_approver`) | Candidates (*IAD approver*) → Approve | `vfm_approved` |
| 4 | Asset Controller (`asset_controller`) | Candidates (*Asset Controller*) → Request tagging | `tag_issued`, label minted now |
| 5 | Tagger (`tagger`) — own token | `POST /assets/<id>/tag-affixed` (the existing route) | `tagged` |
| 6 | Register Maker (`register_maker`) | Candidates (*Register Maker*) → Submit to register; dialog refuses without the SAP code | `reg_submitted` |
| 7 | Register Checker (`register_checker`) | Asset page → banner *waiting on Register Checker* → Approve registration | `registered`, banner gone, **register count +1**, unit in `GET /assets?q=` |

The register count (`GET /assets` total) was read after every step: unchanged through step 6, +1 at step 7.

Refusals, each asserted as the server's answer:

- **Same person at two gates**: the administrator submits a second unit, then verifies it →
  `409 conflict`, `details.reason = segregation_of_duties`, *"You received this unit on 7 Oct; a
  different person must verify it."* — never "permission denied". On that person's asset page: no
  Verify / Approve button, the two sentences in their place (shot 13).
- **Approve without verify**: IAD approver on a `vfm_pending` unit → `409 invalid_state`.
- **Register without the SAP code**: maker's token → `400 validation_failed`, message names the SAP code;
  the dialog shows *Still needed: the SAP asset code* and will not send.
- **Approve a registration nobody submitted**: checker on a `tagged` unit → `409 invalid_state`.

Screenshots: `57-evidence/b-test19/`, numbered `NN-<persona>-<action>-dialog` and
`-now-<register_state>`.

## Deviations, and where the handoff is wrong

1. **"Approve registration without SAP code" cannot be driven.** `register` refuses an empty code, so
   nothing reaches `reg_submitted` without one. Spec 57 proves the two refusals around it instead
   (register without the code; approve-registration from `tagged`). Said, not implied.
2. **§3's example is wrong about Chukwudi.** He keeps his job (Asset Manager, `assets:write`), so his
   Candidates page opens on *Store*. The IAD approver persona is Kelechi Ihenacho; the demo script uses her.
3. **The affix step is driven through the tagger's own token on the existing route**, not the station's
   dialog — that dialog is unchanged and proved by specs 39/40; what is new is that its success moves the gate.
4. **No idempotency key on gate POSTs**: the routes do not declare one, and a key the server ignores is a
   defect by this repo's rule.
5. B edited two lines in Stream C's area at C's request (nav entry + route for *Receipt gates*), both in
   files B owns.

## Verification pass (a fresh agent, not an author)

Typecheck clean. Findings fixed: a gate dialog could crash, or vanish with its refusal, when a 409's
refresh dropped the action (availability now captured at open; refresh on close); the ignored
idempotency key; register controls drawn on a candidate; spec 57's 400 checked only the status.
Passed to A and fixed there: `candidates`/`receipt_gate` missing from `PUBLISHED_ITEMS`. Recorded, not
fixed: *Back to Asset Register* on a candidate leads to a list it is not on.

## For the full-suite run with the switch ON

With `cadra.receipt.gated` on, `POST /assets` makes an unlabelled candidate that the register hides —
any older spec or test that creates an asset and then lists it, or expects a label at creation
(39/40/51's affix and replacement flows), behaves differently. Red there is the switch, not a defect;
A is categorising.

## Concurrency, for the record

Three streams shared one `test19`. The first spec 57 run skipped 10/10, correctly: a pytest run on the
suite credential had switched gating off at 20:50:01 between C turning it on and B starting. The
skip is the spec's own guard, by design; the runs above were in an agreed quiet window.
