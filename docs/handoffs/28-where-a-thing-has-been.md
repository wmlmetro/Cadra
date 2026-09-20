# Handoff 28 — Where a thing has been

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/location-record`.

> Report 27 is accepted in full, and §A is the best measurement this programme has produced on either side. One sentence in it is the whole handoff: *NRS watched an asset being moved from one location to another, and nothing the system wrote down about that move is protected from being edited or deleted afterwards.* **1,146 tracked location changes on `nrs19` and one transfer row** is the number I will be quoting for the rest of this engagement.
>
> **The row to keep is blocking finding 1**, and it is the same shape as the thing it was found in. You graded disposal approval `guarded_record` because the fields are absent from `_WRITABLE_FIELDS` — a fact about one door, read as a fact about the record. Both are ordinary inputs on the Odoo form. So an asset manager could rewrite who approved a disposal and the history would show the new name **graded as protected**. In the module written to stop the system overclaiming. You took the word from a research summary and never opened the model, and by then it had reached five documents. Your own closing line is the rule: *the one claim I did not check against the file was the one that was wrong.*
>
> And you found the ordering bug by opening the screen after thirty-two tests were green. I wrote that an ordering nobody tests will be wrong; it was wrong while tested, until somebody looked.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/location-record && git push -u origin feat/location-record
```

Commit the instruction file first, as `CLAUDE.md` says and as report 27 correctly did over my Step 0.

---

## A · Q1 and Q2 — yes. Location gets the custody treatment.

**Ruling: build the append-only location record, and build it in `nrs.asset.write` where every writer passes.**

Three reasons. **Where a thing is** is half of what an asset register is for, and the other half is already protected — a register that can prove who held a laptop and not where it was is not half an audit trail, it is an audit trail with a hole in the shape of the question people actually ask. **What exists today is worse than nothing in one specific way:** a transfer row looks like a record, and it is editable, deletable, cascade-deleted with the asset, carries a date rather than a time, and has no field for who moved it — so a reader who finds one trusts it. And **NRS asked for an approver on moves**, and §13.2 is right that an approval recorded on a row an asset manager can delete is not an approval record. This is the prerequisite for the thing they asked for in the room.

Yes, it is a stored model and a fan-out across every tenant. Custody was too, and nobody regrets custody.

**Q2 answers itself once §A is at the model layer: `PATCH` keeps accepting `location_id`.** Blocking the quiet door is the instinct that handoff 14 punished — I told you `custodian_id` had one writer and it had six, and recording at the asserted point would have produced a chain with invisible holes. Record underneath every writer instead, and the quiet door stops being quiet without anybody having to find it.

**And do not make `PATCH` write a `nrs.asset.transfer` row.** Those are two different things and conflating them is how the next reader gets confused: the new record is the *fact* that the asset moved; `nrs.asset.transfer` is a *process document* with draft/approved/done and an approver. A move is not always a transfer. Leave transfer alone, link to it where one exists.

**Carry the four honesty properties across unchanged** — they are already right in the history and must be right at the source: an actor the record does not have is null, a reconstruction says so, the record knows when it began, and nothing infers a person from a `create_uid` that means something else.

**On reaching back:** do not backfill from chatter in this handoff. Custody's 674 reconstructions were worth it and they are also why `nrs19` shows one link for 6,643 held assets — the honest picture. Tell me in the report what a location backfill would and would not recover, and I will rule on it separately rather than have it ride along with a model.

## B · Two small things the register should have been doing all along

**B1 · Q3 — yes. The Verify button records a verifier.** *"No record anywhere says a physical check was made"* is the single worst sentence in report 27 for a government asset register. A verification with a date and no person is a date. Point the button at the route that records one.

**B2 · Q4 — make the comment true.** Track the six provenance fields. A GRN reference, a PO reference, a vendor, a cost — these are exactly what an auditor traces back to Vendra and SAP, and today they are overwritten in place with nothing recorded anywhere. One line per field, no migration.

**Be plain in the report about what that buys:** tracking makes the change *visible*, graded `chatter`, which is deletable by the same people who can make it. That is better than invisible and it is not protection. If these deserve the §A treatment, say so and I will rule; do not quietly upgrade them.

## C · Three more screens that say things that are not so

The audit tab was the one NRS found. These are the ones report 27 found beside it, and they are the same defect.

**C1 · The *Legacy Data* tab prints *"Migrated from FIRS legacy system · March 2024"* on every asset**, hardcoded, including assets Vendra registered this month. That is a false provenance statement on a register screen, shown to a client, about assets whose real provenance we hold. Show what the record says, or show nothing.

**C2 · `RequestDetail.tsx` prints `"System"` for a message with no author.** The history got this right two weeks later — *No person recorded* — and this is the same claim in the other direction: naming an actor the record does not have.

**C3 · Evidence grades are hover-only.** The short label is always visible, so this is not urgent — but NRS are being shown this system on screens people touch, and a grade nobody can read is a grade that is not doing its job. Make the meaning reachable without a mouse.

## D · Accepted, and one thing registered

**The new exposures to `assets:read` are accepted** — (a) through (d) as you list them. The history's whole purpose is to answer *who did what*, `assets:read` is the scope for the asset, and none of it is a message body. Historical values of `disposal_reason` are the same class as its current value, which was already published. **Closing the maintenance-request reference yourself rather than asking was the right call**, and I would rather read that sentence than be asked.

**Register the limitation underneath it:** `require_jwt` checks scopes and discards them, so no route can see what its caller holds. That is why the boundary had to be closed by removing a field rather than by filtering, and it forecloses per-scope shaping anywhere in this API. It belongs in the register as an architectural fact, not as a to-do.

**And put the build trap in `ENVIRONMENT-FACTS.md`** — a plain `npm run build` takes `BASE_PATH=/` and silently breaks the locally served app under `/app/`. You measured it once in passing; that is exactly the kind of thing the next person loses an afternoon to.

---

## Report

`docs/handoffs/28-REPORT.md`.

1. **Every writer of `location_id` you found**, and which the record covers. Do not take my list as the list; there isn't one.
2. What a location backfill would and would not recover.
3. Whether the provenance fields want more than tracking.
4. Wall-clock, and the correction share.
