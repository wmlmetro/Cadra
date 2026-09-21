# Handoff 30 — Before the fourth twin

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/asset-events`.

> Reports 28 and 29 are accepted in full, and two things in them are corrections of me that I want on the record before anything else.
>
> **I said I would quote 1,146 for the rest of this engagement, and you told me not to.** 1,145 of those rows were written by Administrator inside six seconds, one per asset, by a script re-mapping locations onto a hierarchy. Nobody moved anything. I would have said that number to NRS. **You found it only because I asked what a backfill would recover** — the question was about something else entirely — and the honest version of the finding is better than the loud one: the structural hole was real and proven by test, and the scale was a seeding artefact.
>
> **And §0 of report 29 is the worst of the five, because I ruled on it.** *"`require_jwt` discards scopes, so per-scope shaping is impossible here"* is false — the whole validated token is on the request and three places already read it. It came from a summary, was never checked against the function, reached report 27, and I wrote it into handoff 28 §D as *an architectural fact, not a to-do*. **I should have opened the function before ruling on a constraint about our own API.** My rule, applied to me.
>
> Third: `refetchOnMount: false` meant the headline fix did not hold in the flow a person actually takes, and your own harness could not see it because it loaded every page fresh. *Acting from a cold start proves only the cold start.* That sentence goes in `CLAUDE.md`.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/asset-events && git push -u origin feat/asset-events
```

Commit the instruction file first.

**Do not start until `dev` contains report 29's merge**, and say so if it does not.

---

## A · Stop before the fourth twin — this is the whole ruling

Report 28 §4 asks for append-only provenance fields. Report 29 Q2 asks where a *reason for missing* would live. Report 28 Q5 asks whether verifications want a record of their own. **Every one of those answers is yes, and every one of them is another copy of `nrs.asset.custody`.**

That would be four near-identical append-only tables — custody, movement, provenance, verification — each with its own instant, actor, source, reason, honesty rules, ACLs, history adapter and tests. **Two twins is a pattern. Four is a design somebody chose without noticing.**

**So: before you build the fourth, tell me whether they should be one.** One `nrs.asset.event` with a type, the common columns and a typed payload, or four tables, or two and two. I am not ruling it from here — you have read all of them and I have read none of the code. What I want in the report is the case, both ways, including the costs I cannot see: migrating two live models with rows already in them on eight tenants, whether a shared table makes the history simpler or the queries worse, and whether a single model weakens the per-type guarantees that are the whole point.

**Whatever you conclude, these three are ruled and get built:**

- **Verification as a record.** *"Show me every time this asset was checked and by whom"* is the custody question, and for a government register it may be the most-asked one — physical verification exercises are the thing an auditor turns up to watch. One overwritten column is not that.
- **A reason for *Mark missing*, as evidence rather than a note.** An asset that cannot be found may be a loss, and *why* is the first question. It has nowhere true to live today, which is why it must get a place rather than be squeezed into a free-text field that means something else.
- **`grn_reference`, `purchase_order_reference`, `sap_asset_number`.** Your argument is right: these are what an auditor reconciles against Vendra and SAP, they change rarely, and a change to one is exactly the event somebody would want to hide. The other three import fields stay tracked and stay noise.

**Not ruled, deliberately:** cost and `value`. Money carries depreciation with it and it is a separate decision.

**The design work comes first and the report leads with it.** If the answer is one model, say what it costs to bring custody and movement into it.

## B · What may be done to a disposed asset — a rule, not a grey button

Report 29 Q4. Today a disposed asset can be marked missing, which overwrites `disposed` and un-disposes it in the register, with a 200.

**The rule goes in the model, where every writer passes** — the same place the movement recorder went, for the same reason. Disabling buttons fixes one door and leaves the API, the importer and the shell open.

**Disposed is terminal.** Not missing, not moved, not a custody change. If an asset comes back from disposal that is a deliberate, recorded act and not a side effect of a PATCH. **Tell me what un-disposing should mean before you build it** — whether it is a reversal event, who may do it, and what the register says afterwards. If the honest answer is *nobody has ever needed this*, say that and refuse it outright.

**And missing is not terminal** — a missing asset that turns up is ordinary. Say in the report which transitions you allowed and why, as a table. That table is the specification.

## C · A rejected field must not fail in silence

Report 29 found `asset_tag` typed, saved, answered 200, and unchanged. You made the tag read-only in the UI, which fixes that field on that screen. **The hole is general:** `_warnings.rejected_fields` is read by nothing, so *any* field the API refuses fails exactly as silently, for every caller including Vendra.

**Close it as a class.** The app surfaces rejected fields; whether the API should answer 400 instead of 200-with-a-warning is a published-contract change and I want your recommendation rather than a change made in passing.

**Then `building_id`** (report 28 Q2): `PATCH {"building_id": …}` accepts a value and moves nothing, because the derivation is a form onchange the API never runs. **Take the three fields out of `_WRITABLE_FIELDS`.** Re-implementing an onchange inside `write` is a second copy of a rule, and this programme has now been bitten three times by two things that should agree and don't. Refusing is honest and it costs a caller nothing they are getting today — provided §C's first half lands first, or the refusal is as silent as the bug.

## D · Four smaller ones, all ruled

- **D1 · Publish the maintenance request reference** to holders of `requests:read` (report 29 Q1). It was withheld for a reason that turned out to be false, and per-scope shaping works.
- **D2 · `POST /assets/<id>/condemn`**, calling `action_condemn` the way `/verify` calls `action_verify` (report 29 Q5). It puts the disposal date on the server instead of the browser's clock, sets the condition in one place, and kills the one-hour-a-night bug at its source rather than in the front end.
- **D3 · Close custody's claimable `source`** (report 28 Q4). Four lines, already written for movements.
- **D4 · `sap_reconciliation_state = exception`** (report 29 Q3) — **measure before wiring.** How many rows carry it, on which tenants, and what put it there. If it is real, wire it as a review status; if nothing has ever carried it, it is a fifth dead status and we have just deleted three.

## E · Not for you

**Backfill: no** (report 28 Q1). Your measurement is the argument and I am not overriding it. Recorded as decided.

**GitHub billing is the owner's and I have escalated it.** Nothing you do about it. Keep running everything locally and keep quoting the `Ran … / OK` lines.

---

## Report

`docs/handoffs/30-REPORT.md`.

1. **§A's design case, first and at length.** One model or four, and what it costs either way.
2. The transition table from §B.
3. Your recommendation on 400-versus-warning for a rejected field.
4. What §D4 measured.
5. Wall-clock, and the correction share.
