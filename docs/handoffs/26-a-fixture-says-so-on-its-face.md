# Handoff 26 — A fixture says so on its face

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/fixtures-say-so`.

> Report 25 stands in full, including the acceptance criterion it did not meet literally and explained instead. The guard is right and I am taking the deviation: one refresh-token row before the refusal is operational, indistinguishable from any integration authenticating, and closing it needs a public mode on `cadra_endpoint` — which is the pre-envelope-routes item's territory and not something to do in passing inside a handoff about test safety. **The finding I want kept is the ormcache leak.** A guard that read `get_param` let twenty-four writing tests through against a database carrying no mark, and answered `"test"` from one worker and `"client"` from another about a row that had been deleted. You found it by insisting on the *absent* case rather than the two that were obviously going to pass, and you put the fact in `ENVIRONMENT-FACTS.md` rather than in the guard. Anything a safety decision turns on reads the row.
>
> **One thing to reconcile first.** §3 says the owner ran `mark_test_fixtures.py`, that half of it silently did nothing, that you fixed it and re-ran it verified. §7 says neither script has been run. One of those is stale. Fix it in the report file, and note which — a report that contradicts itself about whether an instrument ran is the subject of §B.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/fixtures-say-so && git push -u origin fix/fixtures-say-so
```

If handoff 25's PR has not merged, branch from `fix/tests-know-where-they-are`, say so, and do not merge it yourself.

---

## A · Every record a test creates says so, by derivation, not by convention

**This is the ruling report 25 §3 asked for without asking for it.** Service requests do not self-identify at all: `request.request.name` is a sequence, so a test-created request is indistinguishable from a real one by any rule a cleanup script could apply. There are 460 of them on `jaizbankplc` and roughly one more per session. **The script reports this in words and removes none of them, which is correct and is also the end of the road** — those records can never be found again.

The name convention was never the mechanism. `is_test_credential` is, and the custody chain is honest because 330 rows **derive** their label from it with nobody curating anything. A prefix is a thing somebody remembers to type; a derivation is a thing that happens.

**So: anything created through a credential flagged `is_test_credential` carries that fact on the record**, the way custody already does. Requests first, because they are the measured hole and they are reachable from a public dropdown.

**Then close the class rather than the instance.** Enumerate every model the API can create, and fail when one of them has no self-label — the way the concurrency guard derives membership from behaviour rather than from a list. A model added next year with no marker should turn the suite red on the day it is added, not be discovered in a register two years later at 88%.

**Two things to get right.** A derived label must not be settable or clearable over the API, or it is a convention again with extra steps. And tell me what it costs on records that already exist: **it is not retroactive**, the same way the access record is not, and the honest answer is that everything created before it is unidentifiable forever.

## B · A step that can find nothing and say nothing

`mark_test_fixtures.py` searched for `Handoff23 Approver` with a plain `search()`, the credential is archived, Odoo's `active_test` excluded it, the recordset came back empty, the `for` loop never ran, and **the script printed nothing at all** — not a failure, not a "not found". The owner read a clean run. Report 24 had called it idempotent; on that tenant it had never worked and could not have.

**This is the third instrument in three handoffs that reported success while doing nothing**, after the test file that was written and never registered, and the mutation proof that asserted on a variable that never existed. The shape is identical every time and it is not a coincidence: **a step that operates on a named thing, finds no such thing, and treats zero as done.**

So make it a property rather than a third fix. Sweep `scripts/` and every maintenance path: a step that names a record and does not find it **fails loudly and names what it looked for**. Where a zero result is legitimate, it says so deliberately in the code rather than by omission. And `active_test=False` wherever the question is *"does this record exist"* rather than *"is this record in use"* — an archived artefact is still an artefact, which `nrs.asset.custody._is_test_credential_user` already knew.

## C · The three tenants nobody has classified

`cadra19`, `nrs19` and `gtb19` carry no class. They refuse, so nothing is unsafe — but *unknown* is a state somebody eventually resolves by guessing, and the guess that costs money is `test`.

**Measure, then propose; the owner marks.** For each: what is in it, whether it was restored from a client dump, whether anything outside this repository uses it. `nrs19` in particular is the register Vendra's own integration work measures against and it holds around twelve thousand assets — find out what those are before anybody types a word into that parameter.

**The rule when it is genuinely ambiguous is `client`.** A test database wrongly marked `client` costs somebody an afternoon. A client database wrongly marked `test` costs a register.

## D · The fixtures that cannot be removed are marked instead

99 assets hold a chain-of-custody row and `custody.unlink()` raises unconditionally, so they stay — and **they should stay.** Append-only is the property the whole custody chain is worth having for, and carving one exception for tidiness is how it stops meaning anything. Report 25 already made this call correctly once for the six disposals.

**Extend the marking rather than the removal.** They are identifiable today, which is more than the requests are; label them on their face so a reader of the register knows what they are looking at without consulting a script. Same for the 17 locations and 10 assets a real service request points at — those are refused because deleting them would silently blank a live request's field, which is the right refusal and a permanent state.

Report what is left unmarked after this, and whether anything in that set is reachable from the public homepage.

---

## E · The closing register — this is the last handoff

**Handoff 26 is the last one. There is no 27.** Contracted core scope was complete at handoff 23; the three since have been the quality of the record rather than its scope. They found real things — an endpoint standing open on every tenant, import loops erasing rows while reporting success, a client's register at 88% test fixtures — and they have now reached the point where the marginal finding costs more than it returns. What stands between this system and a delivered one is four servers, a test SAP environment, four answers from the NRS SAP team, a fixed-asset register extract and the credential rotations. None of it is code.

So the last thing this handoff builds is the place the programme resumes from. **`docs/GO-LIVE.md` gains an open-items register**, in the shape Vendra's `GO-LIVE.md` already uses: one entry per item, each tagged `[open]`, `[verified]` or `[landed, keep it that way]`, each carrying its evidence and the report it came from. Everything outstanding goes in it, and I mean everything:

- the two owner-run scripts, what each does, and what a run leaves behind;
- the service requests that can never be identified, with the count and the date it was taken;
- the three unclassified tenants, with your proposed class and its evidence beside each;
- the `admin` password on every tenant, the `ODOO_ADMIN_PASSWORD` Secret, and the two live-cutover credentials sitting unrotated in git history;
- the nine pre-envelope routes, the per-session artefact paths, `Finance Officer` / `finance_viewer`, and the retroactive access question (INT-10 §2.10b — NRS's decision, not a backlog item);
- anything in your own notes a reader would need and could not find on their own.

**Do not close the report with questions for me.** Anything you would have asked becomes an entry in the register with the options written out, so whoever picks this up — you in three months, or somebody else — reads a decision to make rather than a cliffhanger. And if something in §A–§D turns out to be wrong or bigger than it looked, **do not build around it**: put it in the register, say so in the report, and stop there.

---

## Report

`docs/handoffs/26-REPORT.md`. Short, and the last one. In it:

1. **What the enumeration in §A found** — every creatable model, and which had no self-label.
2. What the `scripts/` sweep found. I expect a fourth instance of §B's shape; tell me if there is not one.
3. Your proposed class for each of the three tenants, with the evidence.
4. **Whether the register is complete** — and the one thing you would put at the top of it if you could only hand over one.
5. Wall-clock, and the correction share.
