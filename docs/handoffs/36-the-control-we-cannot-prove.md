# Handoff 36 — The control we cannot prove

**Branch:** `fix/the-control-we-cannot-prove`
**Report:** `docs/handoffs/36-REPORT.md`
**Small.** This is not a feature handoff. It closes the gap between a control existing and a control being provable, and I expect it to be short.

---

## 0 · Where this came from

Not from me reading the source. From Vendra's report 43, which walked the approval flow you built in handoff 35 as far as it could reach and then stopped, for a reason that is about this repository:

> Approving or rejecting needs the `approvals:write` scope **and** a second identity. `nrs19`'s credentials are `vendra` (`assets:read assets:write`) and `tag_issuing_unit` (`tagging:write`); **neither can approve anything.** Driven: `POST /approvals/1/approve` with the `vendra` token answers `403 Missing required scope(s): approvals:write`.

So on the tenant we demo from, the half of the control that *raises* a request is proved — the request appears, the asset does not move, the raiser gets `can_decide: false`, self-nomination is refused, a second pending request is refused with a `409` naming the first. **The half that decides is unreachable.** *"Two people, and never the same one twice"* is the control the stakeholder asked for, and we cannot demonstrate it on `nrs19`.

It also found a second thing in the way:

> `GET /api/v1/locations` returns an empty list, so there is nowhere to move an asset to.

A move needs somewhere to move to. `nrs19` has no locations at all, which means the *move* approval — as opposed to the custody approval — has never been exercised against this tenant by anybody.

**Both of these are environment gaps, not code defects.** I am treating them as a handoff anyway, for one reason: an unprovable control is indistinguishable from a broken one, and we are about to put this in front of NRS.

---

## 1 · What to do

### A · Make the decision half reachable on `nrs19`

One identity that can approve. Whatever the cheapest honest shape is — a credential carrying `approvals:write`, an Odoo login in `group_asset_manager`, or both if the API and the UI need different things.

**Three things I care about more than the mechanism:**

1. **It must be a genuinely separate person from `vendra`.** The whole control is that the same identity cannot do both halves. A credential that can raise *and* decide proves nothing and would be worse than what we have, because it would look like a pass.
2. **No secret value passes through chat, a document or a ticket.** Generate it on the machine — `openssl rand -hex 32` — and record in the report only *what exists and what scope it holds*, never the value. Same rule as every credential in this programme.
3. **Say whether this is seed data or a one-off.** If a fresh tenant installs with no identity that can approve anything, then approvals are off-by-default-by-accident on every tenant NRS ever creates, and that is a different and larger finding. **Check, and say which it is.** Report 35's own deployment ruling turned approvals on for every tenant including live clients — if none of those tenants has an approver either, I need to know today.

### B · Give `nrs19` somewhere to move an asset to

Enough locations to drive a move, and no more. Two or three, named like NRS would name them rather than `Test Location 1` — a move between two places whose names mean nothing proves the mechanism and teaches nobody.

Then **drive the move approval end to end** and put the transcript in the report: raised by one identity, decided by the other, the asset's location changing only on approval, and the asset history carrying `location_moved` with who did each half. Vendra's report 43 graded that history at two events deep because `location_moved` was unreachable; I want it four.

### C · The gap report 43 flagged inside the history

> an approved change records **the approver** as the actor and the requester appears nowhere in the history.

That is a real defect and it is small. The history is the artefact an auditor reads, and on an approved move it currently answers *who approved this* while losing *who asked for it* — which is exactly half of the two-person control it is supposed to evidence. **Fix it so both identities are in the record**, and say in the report how you decided which one is the "actor" rather than guessing at my preference.

---

## 2 · While you are in there

`nrs19` still holds handoff 41's probe asset (`12008`, `NRS-AST-047642`) and report 43's seven walk assets (`12009`–`12015`, one tagged `NRS-PC-063`) plus pending change request `CR/2026/0001`. **Leave them.** They are evidence, they are named in two reports, and a demo tenant that looks used is more honest than one that looks new. If any of them would confuse a demo, say which and why and I will rule.

---

## 3 · Verification

- The transcripts for A and B, driven, both identities visible.
- **The negative case, driven:** the raiser attempting to decide their own request, refused.
- For C, the history of an approved move showing both people, with the grading unchanged in kind.
- Whether a fresh tenant has an approver (§1A.3), answered with a measurement rather than a reading.
- The suite, with times.
- And the standing pass: **read every sentence you wrote in this handoff's code, comments and docs and check each against something you measured.** Vendra's verification pass found four false sentences in report 42's work, three of them inside the docstring of the instrument built to stop false statements. It is the most valuable habit either side of this programme has.

---

## 4 · Still waiting, and not superseded

`docs/handoffs/33-the-whole-surface.md` has never been run — there is no `33-REPORT.md`. Warranty (34) and approvals (35) overtook it because the owner had urgent items. **Do not run it as part of this handoff.** Read it once and tell me in the report whether 34 and 35 have made any of it moot, so I can either retire it or put it back in the queue honestly. Two handoffs have landed on the surfaces it describes; I would rather know than assume.
