# Close-out — the Architect's acceptance of report 26, and the last three rulings

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `docs/close-out`.

**Report 26 is accepted in full and the Cadra handoff cycle is closed.** This file exists because the rulings below belong in the repository rather than in a chat window, and because the register should not carry three open questions that already have answers. It is documentation only — no code, no tests, no fan-out. Commit it, fold §1–§3 into `docs/GO-LIVE.md` where each belongs, open the PR, and stop.

---

The finding I want on the record is not the mixin. It is `scripts/remove_test_residue.py` reading its production refusal through an ormcache — **the one guard between `CADRA_APPLY=1` and a real client's register, using the exact call the handoff that wrote the script had just proved unsafe, three directories from the docstring explaining why.** Nobody re-read the new file against the rule the same handoff had written down. That, and the fact that you caught your own correction to report 25 introducing a fresh false claim about the seventeen locations, are the two things worth carrying out of this programme. The lesson you ended on is right and it is the only one that has held all the way through: *the thing that works is not care; it is somebody who did not write it reading it against the database.*

Fourteen models carried no self-label and one carried one. Twenty-four silent instruments where I expected a fourth. Both numbers are larger than I would have guessed and both were found by enumerating rather than by reasoning.

## 1 · The three tenants — ruled. Mark all three.

- **`nrs19` → `client`.** Agreed without reservation. A real NRS staff extract naming serving officials, and the register another organisation measures against.
- **`cadra19` → `client`.** Agreed, and your second opinion is here: provenance decides it. Assets derived from a named architect's drawings, a named consultancy's completion schedule and a dated FIRS HQ furniture inventory, describing a real 19-floor building, are client-derived content whatever the tenant is used for. Your closing argument is the one that settles it — **`test19` already exists, is marked, and has a credential pair; a second test tenant is a thing to make, not a thing to reclassify.**
- **`gtb19` → `test`.** Agreed. This is the one place I am not applying *"when ambiguous, client"*, because it is not ambiguous: every category of content is traced to a source and none is client-supplied — synthetic employees, seed-script equipment, and locations from a JSON file that marks every row as public OpenStreetMap data.

**Mark all three rather than leaving the safe one unmarked.** Unmarked refuses, so nothing is unsafe either way — but a database whose class is recorded only in a report is the shape of thing this whole programme has been fixing. The parameter is where the decision lives. **Carry your caution about the two GitHub workflows with the `gtb19` mark**: that is a different database on the cluster, and classifying the local one says nothing about it.

## 2 · `with_user(SUPERUSER_ID)` on quick-submit (§7, GO-LIVE §11.1) — ruled, so it is not left as a question

You were right not to change it inside a handoff about labelling, and right that it is a pre-existing audit-trail defect the labelling exposed. **The ruling: split the two paths rather than choosing one behaviour for both.**

On the authenticated route, `.sudo()` is correct — it elevates privileges and keeps the actor, which is the whole difference between the two calls and the reason the actor is being lost. On the public twin there is no actor to keep, so `with_user(SUPERUSER_ID)` stays exactly as it is and the public path does not change at all. That is the one option of the three that fixes the defect without touching unauthenticated behaviour.

Record it in §11.1 as a ruling with that reasoning, not as an open question. Whoever picks it up implements it; nobody needs to re-decide it.

## 3 · The status of the two burnt cutover credentials — carried

Your fourth correction matters outside this repository and I am acting on it. *"Two unrotated credentials in git history"* has been in my own status reporting for weeks and it was wrong in the direction that lets something sit: neither key is set on any tenant and both routes have refused since handoff 17.

What is actually true is that **Redhubs' asset-register export and SAP's inbound employee sync have been answering `Unauthorized` since then, and two external parties are waiting on values somebody has to generate and hand over.** Keep §8.3 phrased the way you have it. I am taking it to NRS as a switched-off integration awaiting a credential rather than as a security item, because those need different people.

## 4 · What is accepted as it stands, and not to be reopened

- **§10.2's eleven remaining silent-instrument sites.** A deliberate stopping point, recorded with file and line. Correct call.
- **§12's three judged-and-left findings.** Correct call, and the reasoning is written down.
- **The 115 assets and 17 locations marked rather than removed.** Append-only is the property the custody chain is worth having.
- **The 460 unidentifiable service requests.** Permanent, stated as permanent, with the date the count was taken. There is no fix and inventing one would be worse.
- **Your two honest limits on the register** — what was known before handoff 19 and never written down, and §10.2 — stand as written. A register that names its own edges is usable; one that claims completeness is not.

## 5 · What this branch does

1. Commit this file.
2. Fold §1, §2 and §3 into `docs/GO-LIVE.md` where each already has a section, so the register carries the decisions rather than the questions.
3. Set the three parameters if you can do it without a committing write to a client-derived tenant; if the permission layer refuses, leave it as an owner line with the exact command, the way you have correctly done twice before.
4. Nothing else. No new tests, no fan-out, no further enumeration.

**No report is needed.** If anything in §1–§3 turns out to be wrong when you go to write it down, put it in the register and say so in the PR description.

---

Contracted core scope was complete at handoff 23. Handoffs 24, 25 and 26 found an access record that never existed, a test suite writing into a copy of a client's register, and fourteen models that could not say what they were — and then the register that makes all of it findable by somebody who was not here. That is a good place to stop, and this is where it stops.
