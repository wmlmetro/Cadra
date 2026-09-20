# Handoff 29 — Every control on the asset page

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`, **after handoff 28 has merged.** **Branch:** `fix/asset-page-controls`.

> **Wait for 28.** Its §C1 edits `AssetDetail.tsx` and so does this; branching before it merges buys a conflict in the one file both handoffs care about. If 28 is still open when you read this, say so and stop.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/asset-page-controls && git push -u origin fix/asset-page-controls
```

Commit the instruction file first.

---

## Why this exists

The owner tapped **Mark as missing** on a live screen and got the browser's own grey dialog — the one that says *"<hostname> says"*. That is what prompted this, and it is the smallest thing in the handoff.

**I read the code before writing this and the pill is wrong.** `lib/adapters.ts:194`:

```ts
function deriveStatus(a: ApiAsset): ApprovalStatus {
  if (a.state === "active" && !a.is_verified) return "Review — data quality";
  return "Cleared";
}
```

`markAssetMissing` sends `state: "missing"`. `condemnAsset` sends `state: "disposed"`. **Neither is `"active"`, so both fall through to `"Cleared"` — a green pill.** Mark an asset missing and the register tells you it is cleared. Condemn it and the register tells you it is cleared. The lifecycle state is sitting right there on the object as `lifecycleState` and the pill never reads it.

This is the defect class the Cadra side has now produced four times — 282 assets labelled *Good* and reachable by no filter, 225 requests shown under the wrong severity, a blank *Audit & Review* tab — and it is on the screen NRS were shown last week.

**And three of the five pill styles can never appear.** `StatusPill` defines *allottee not in nominal roll*, *VIN not verifiable* and *possible duplicate*; `deriveStatus` returns only two values. They are mock-era concepts the API does not model, and the *Audit & Review* tab branches on one of them.

---

## A · The pill tells the truth about the asset

Lifecycle and data-quality are two different facts and the pill currently shows one where the reader expects the other. **Decide the shape and say why in the report** — a second pill, or one pill that shows lifecycle when it is anything but active — but the requirement is fixed: **an asset that is missing, disposed or condemned must never render as cleared, anywhere it renders.**

Check the register list, the dashboard and any card or table that shows this, not only the detail page. The bug is in a shared function, so assume it is on every screen until you have looked at each.

**The three unreachable pill styles:** either the API can produce them and the mapping is missing, or it cannot and they are dead. Measure which, then delete or wire them. A style nobody can reach is a promise the screen cannot keep — and the *Audit & Review* tab is branching on one of them today, which means that branch is dead too.

## B · The browser's dialogs go

Two of them, and the app already has a proper dialog system — `AssetActionDialogs.tsx` builds Move, Transfer custody and Condemn properly, with a reason field and a real mutation. These two were simply never brought along:

- **`AssetDetail.tsx:209`** — bare `confirm()` for *Mark as missing*.
- **`pages/settings/AssetCategories.tsx:298`** — `window.confirm` for **deleting a category**, which is destructive and behind the browser's own dialog.

Use the app's dialogs. And while you are in there: *Mark as missing* records a state change with no reason field, where Move, Transfer and Condemn all take one. Say in the report whether it should — I suspect *why is this missing* is the first thing an auditor asks — but do not add it on my say-so; check what the API accepts first.

## C · The inventory — and it is proved by acting, not by reading

**Every control on the asset detail page**: what its label promises, what it calls, what changes in the database, and **what the person sees afterwards**. One row each, in the report.

- Verify · Mark as missing · Move · Transfer custody · Condemn · Generate tags · Raise a request · every tab, every link, every menu item you find. Do not work from my list; find them.
- For each: does the screen it leaves you on tell the truth? Does the list behind it update? Does the history now show it — 28 built that, and this is the first real test of whether it sees what the UI does?
- **A control that does nothing, or that reports success while nothing happened, is the finding.** So is one whose label describes something other than what it calls.

**Act on a marked test tenant and read the result from the database, not from the toast.** Report 27 had thirty-two green tests over a tab that showed an asset changing hands before it existed, and found it by opening the screen. That is the standard here: the report should say *I clicked it and this is the row that changed.*

Where you find something broken and small, fix it. Where it is large, **write it down and leave it** — I would rather have a complete inventory and three fixes than four fixes and a partial one.

## D · The same question one screen out

The register list and dashboard show the same assets through the same adapter. Check the pills, counts and filters there against what the detail page says about the same asset. **A count that includes a missing asset in a figure a person reads as working stock is the same defect with more consequence.**

---

## Report

`docs/handoffs/29-REPORT.md`.

1. **The inventory table** — every control, what it promises, what it does, what the user sees. This is the deliverable.
2. What the pill shows now, for each lifecycle state, on each screen.
3. Which of the three unreachable statuses were dead and which were missing wiring.
4. What you fixed and what you left, with the reason for each.
5. Wall-clock, and the correction share.
