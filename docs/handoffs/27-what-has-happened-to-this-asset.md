# Handoff 27 — What has happened to this asset

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/asset-history`.

> **The cycle reopens for a client-driven gap, not for more polish.** Handoff 26 closed the programme's own quality work and the register is the resume point for it. This is new, it came out of a live demonstration to NRS, and it is the one thing they asked for that the system does not do.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/asset-history && git push -u origin feat/asset-history
```

---

## What happened, and what I have already established

NRS were walked through an asset's whole life end to end — purchase order into Vendra, goods receipt, hand-off to Cadra, registration, tagging — and then on the asset itself: assigned to an employee, reassigned to another, moved between locations. They opened **Audit & Review** expecting to see that, step by step. It was blank.

**It is not broken. It was never built.** I read it before writing this. `Frontend/artifacts/nrs-asset-register/src/pages/AssetDetail.tsx:428` renders exactly three things: a status pill, a *Review Flags* list which is `is_verified ? [] : ["Not yet verified"]`, and a purple box that appears for one status value. **On a verified asset with an ordinary status that is one pill and empty space.** There is no history in it, and there never was.

**The data, on the other hand, is almost all there.** `GET /assets/<id>` already takes `include=custody` — the whole chain, oldest first, uncapped, and deliberately exempt from the external record cap because *"a chain of custody is complete or it is evidence of nothing"* — and `include=transfers` for location moves, and `GET /assets/<id>/custody` as the paginated form. Each custody link carries when, from whom, to whom, **who moved it**, why, and `source`.

**And the front end already has the door open.** `fetchAsset(id, includes?)` takes an includes argument. `AssetDetail.tsx` calls it as `fetchAsset(id ?? "")`. Nothing in `lib/adapters.ts` maps custody or transfers at all.

So: a chain of custody that survived a whole handoff to build, that refuses deletion by anyone including an administrator using sudo, that 674 rows were backfilled into — **and the screen an auditor opens does not ask for it.**

---

## A · Measure what actually has a record. Before building anything.

The tab must show *what has happened to this asset*. Before deciding what that list contains, establish what this system can honestly say, event by event. **This is the step that matters** — handoff 24 went looking for group-membership history and found six places it could have been recorded and zero rows in any of them. Assume nothing here.

For every event in an asset's life — registered from Vendra, tagged, verified, custodian changed, location moved, status changed, financial fields changed, disposal approved, anything else you find — say three things:

1. **Is there a record with a real timestamp and a real actor?**
2. **Can it be deleted or edited after the fact, and by whom?** A `mail.message` is not evidence; the custody chain is. Where the only record is chatter, say so — that is a finding, not a detail.
3. **Does it reach back?** Custody covers only changes since it existed, and the backfilled rows are reconstructions. An event type with no history before a date needs that date known.

**Report this before you report the feature.** If something NRS watched happen in the demo has no durable record, that is the most important sentence in the report and I want it in plain words.

## B · One ordered history, built server-side

**My ruling: the timeline is assembled by the API, not stitched together in the browser.**

Three reasons, and the third is the one that decides it. Ordering across several sources is the substance of the thing, and an ordering nobody tests is an ordering that will be wrong. The permission and record-cap rules are already settled server-side and would have to be re-reasoned client-side. And **INT-10 exists**: an external auditor asking *what happened to this asset* is the same question NRS asked in that room, and they should get the same answer from the API rather than only from our React app.

**Requirements, and they are all the same requirement in different places — the list must not imply more than the record supports:**

- **A reconstructed row says so on its face.** `source: tracking_backfill` must survive all the way to the screen. An auditor reading a reconstruction as a contemporaneous record is worse off than one reading nothing, and that sentence is already in the serializer's own docstring.
- **An actor the record does not have is blank, not inferred.** No falling back to "system" or to a created-by field that means something else.
- **Where the history begins is shown.** If the chain starts three months after the asset was registered, the list says so at the bottom rather than trailing off. This is the same rule the access report already follows.
- **An event type we cannot record at all is named in the response**, not silently absent. A gap a consumer cannot distinguish from "nothing happened" is the defect this whole programme is about.

Reuse what exists — `include=custody` and `include=transfers` are built, tested and correct. This is an ordering and a merge, not a new record.

## C · The tab shows it, and says what it cannot show

Render the list. Newest first unless you find a reason otherwise — say which you chose and why.

**And fix the failure mode that produced this handoff:** a tab called *Audit & Review* that has nothing to show must say *there is no recorded history for this asset* in words. **Empty space is how this got in front of a client.** That applies to the feature as a whole, not just the day it ships.

Keep the approval status and review flags that are there now; they belong on that tab. They are simply not what the name promises on their own.

## D · Not in this handoff

NRS also raised whether a location move should require an approver rather than happening on one person's say-so. **That is a process question for them and the owner, not a defect.** Do not build it, do not design it. Record it in `GO-LIVE.md` as a client request with the date and what was asked, and note what the current behaviour actually is — who can move an asset today, and what is recorded when they do — so whoever picks up that conversation starts from the facts.

---

## Report

`docs/handoffs/27-REPORT.md`.

1. **§A's table first** — every event type, whether it has a durable record, and what is missing. Plain words.
2. Whether anything NRS saw in the demonstration cannot be shown, and why.
3. What the timeline covers, where it begins, and what it says when it is empty.
4. Wall-clock, and the correction share.

Questions are welcome. This is a new thread, not the closed one.
