# Handoff 23 — The last two reports

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/audit-logs`.

> Report 22 accepted in full. **Your one-sentence verdict on the fresh pass is the most valuable thing either repository has produced about its own practice:** *the pass found nothing wrong with the mechanism and a good deal wrong with the evidence that the mechanism works. Four of the nine findings are tests or guards that pass without testing anything.*
>
> **The partition assertion never ran on `/assets`** — capped at one page, so the only real check was gated behind *"only test endpoints smaller than fifty rows"*, silently. **Both `active` parameters' `false` branch had no regression net at all** — the branch report 21 itself called the worse of the two failures. **And the CI-series guard did not fire when the real file was restored**, because its mutation proof wrote a variable name that had never existed.
>
> **`?has_coordinates=false` answering zero where 250 of 380 sites are unmapped** is the best single find. An unset coordinate is SQL NULL and never `0.0`, and Odoo renders `!= 0.0` as *(x != 0 OR x IS NULL)* — so the question *which sites has nobody mapped* returned none of them.
>
> And **282 assets were labelled "Good" on screen, excluded from the Good filter, and reachable by no filter at all.** That is the front-end family's real cost, measured.

## Step 0

Commit the instruction file on `dev`, push, branch. **Needs the owner:** merge handoff 22's PR.

---

## A · The guard that does not fire

**Report 22 finding 3, reported and not fixed.** `test_deployment_profile.py:315` skips any line without `odoo` in it, and the pin it exists to catch — `SERIES_BRANCH: '15.0'` — has no `odoo` on that line. Its mutation proof passed only because it wrote `ODOO_SERIES_BRANCH`, a variable that never existed.

**Fix it, and fix the proof.** The mutation must restore **the real file**, byte for byte, from git history. A guard proved against a fixture it invented is the shape your own pass just spent nine findings on.

## B · The last two audit reports

`Cadra_at_NRS_Specification_v0.1.docx` §13.4 names five standard audit reports. The snapshot, the custody chain and disposals are built. **These are the last two, and they finish contracted core scope in this repository.**

**B1 · Access changes for any user, per period.** Who was granted or removed from what, when, and by whom. Your INT-10 document records that Cadra has no access log at all — so the honest first question is what the data supports. Odoo tracks group membership changes through `mail.tracking_value` on `res.users` where the fields are tracked, and not otherwise.

**Say what is answerable before building the answer.** If the history is partial, the report says which period it can speak for and which it cannot — the same boundary the snapshot publishes at `data.fidelity`, and for the same reason: an auditor told where the record begins can work with it, one who discovers the gap later cannot trust any of it.

**B2 · Configuration change log — who changed what setting, when.** `ir.config_parameter`, the settings singletons, and anything that changes what the system does without changing its code. The same honesty rule applies, and I expect it to bite harder here: most of these are almost certainly untracked today.

**Both read-only**, both with a statement above the table, both proved to write nothing by fingerprint — the shape all five of your reports now share. And both must be openable by `Vendra Auditor`, **proved by acting rather than by reading permission rows**, which is the gate that had made two earlier reports unopenable by the role that named them.

**If the honest answer to either is "the data does not support this", that is the deliverable** — written into `docs/integrations/INT-10-audit-access.md` as a gap with what it would take to close it. Do not synthesise a history we do not have. You have refused to fabricate provenance three times unprompted; this is the fourth and the largest.

## C · The disposal-approval route — my ruling, and it was owed

Report 16 named it: `action_approve_disposal` is Odoo-form only, because the approver is deliberately not writable over the API — a client able to PATCH the approver could create a disposal and name any user as its authority in the same request, turning a finding into a clean row with nobody having authorised anything. That control is right and it stays.

**Build the route, gated on `approvals:write`, and the approver is the authenticated user — never a field in the payload.**

That is the whole ruling and it preserves what the control protects. The route records **who called it**, derived from the credential, not who the caller says approved. The field stays out of `_WRITABLE_FIELDS`; nothing about PATCH changes. And `approvals:write` gates nothing asset-related today, so granting it to a client is a deliberate act somebody has to perform rather than something a broad credential already carries.

**A test that a client without the scope is refused**, and one that the recorded approver is the caller and not anything the body asked for.

---

## Acceptance

- The series guard fires on the real file restored from history.
- Both reports exist, read-only, proved by fingerprint, with a statement that says in words when they find nothing.
- Each publishes the boundary of what it can answer, on its face.
- `Vendra Auditor` can open both, proved by acting.
- A disposal approval over the API records the caller; a client without `approvals:write` is refused.
- Guards proven to fail before they pass. Denominators quoted. Suites in CI's order. Fan-out if any column moves.

## Report

`docs/handoffs/23-REPORT.md`. Short.

1. **What each report can and cannot answer**, as two lists. That is the deliverable more than the code is.
2. How many settings changes are recoverable at all. I expect a small number and would rather have it than not.
3. Wall-clock and the correction share.

---

## What this finishes, and one thing for me

**With this handoff, contracted core scope is complete in both repositories.** Five audit reports, the chain of custody, the dual-code control, the tagging segregation, the capture control, six SAP interfaces built and waiting on a real SAP, and the deployment path corrected.

What remains after it is not engineering: four servers, a test SAP environment, four answers in the interface pack, a fixed-asset register extract, and the credential rotations. Every one of those sits with NRS or with the owner.

**The three corrections in `docs/DECISIONS.md` are still mine and I have now owed them for six handoffs.** The withdrawn R46 entry, the duplicate pairs staying as they are, and the INT-10 §16 citation. They go in with the `cadra-vendra-interface.md` edit your report 21 §3 earned, and I am not promising them a seventh time — I am doing them alongside this handoff rather than after it.
