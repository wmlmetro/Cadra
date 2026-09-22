# Handoff 34 — Warranty

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/warranty`.

> **New scope, from a stakeholder at last week's demonstration**, and it spans both repositories. *How do we capture warranty on assets?* The honest answer today is that we do not — but we very nearly do, and that is the first thing to know.
>
> **`nrs.asset.warranty_expiry` already exists**, it is already in `_WRITABLE_FIELDS`, already published by `serialize_asset` and the OpenAPI schema, and the app's asset form already has a *Warranty expiry* input. **And it is zero of 1,335 on `cadra19` and zero of 4,164 on `jaizbankplc`** — report 32's own sweep found it among the columns nobody has ever filled in. A field, a form input and a published key, and no value has ever reached any of them.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/warranty && git push -u origin feat/warranty
```

Commit the instruction file first. **This goes before handoff 33 if 33 has not started** — 33 widens a guard and can wait; this is client scope with a date on it. If 33 is already running, finish and merge it first.

---

## The shape, decided with the owner

- **Captured at goods receipt in Vendra, per receipt line, applying to every unit on that line.**
- **A duration, not a date** — the storekeeper enters *24 months* and the expiry is computed, because that is how a warranty is quoted and a computed date cannot be mistyped.
- **Three facts, not one:** how long, **who honours it**, and **the certificate or document reference**. *"It is under warranty"* is useless to the person holding a broken laptop if nobody can say who to call and what to quote.
- **Cadra stores it, shows it, and answers *what is under warranty and what expires soon*.**

---

## A · Read this before writing a line — the deployment order is load-bearing

**Since handoff 31, a field Cadra does not accept is a `400`.** That was the right ruling and it makes this sequence dangerous:

> **If Vendra starts sending warranty fields to a Cadra that has not been upgraded, every INT-03 asset hand-off fails with a 400.**

Not degrade. Fail. Every unit received in Vendra would dead-letter instead of registering.

**So Cadra accepts the fields before Vendra sends them, and there is no version of this where that order reverses.** Your half is additive — new published keys, new accepted keys, nothing renamed, nothing refused that used to be allowed — so a Cadra carrying them is harmless to the Vendra that is live today.

**Say in your report, plainly and near the top, which Cadra version accepts the new keys.** The Vendra handoff is gated on that sentence. The precedent for the gate already exists on their side — `provenance_fields_enabled()` was written for exactly this situation — and your report is what lets it open.

## B · The fields

`warranty_expiry` stays exactly as it is: same name, same type, same published key. Around it:

- **Who honours it** — the warrantor, as a name recorded at the time. **Not a link to a partner record.** Cadra holds no vendor records for assets arriving from Vendra, and the custody chain's own rule is the precedent: the name as it stood when the record was made, so a record deleted or renamed later cannot empty the row.
- **The reference** — certificate or document number, free text, as given.
- **The basis of the expiry: the start date and the duration.** This one is mine and I want the reasoning kept. **A derived date published without its derivation is the defect this programme has spent a month on.** A bare *"expires 12 March 2028"* cannot be checked, argued with, or corrected when somebody finds the certificate says thirty-six months. *"24 months from 12 March 2026"* can. Publish the answer and the working.

**Everything is optional.** Most assets in the register have no warranty and never will. An asset without one is the ordinary case, not a gap, and nothing should imply otherwise.

**Whether a change to any of these is recorded as an event is yours to decide.** A warranty is a contractual fact somebody could have an interest in altering, and you built that model and know what it costs. Decide, and say why.

## C · What it must never do

**A warranty has nothing to do with whether an asset is in service.** An expired warranty is not a condition, not a lifecycle state, not a review status, and it must not touch a pill, a filter default, or any count a person reads as working stock. We have fixed that confusion twice — *Good · Cleared* on a disposed asset, and 282 assets reachable by no filter. **It is a fact about a contract, not about the asset.**

## D · *What is under warranty, and what expires soon*

They asked how we capture it; **what they will ask for next is the list.**

- Filter the register by *under warranty* / *expired* / *no warranty recorded*. **Three states, not two** — *no warranty recorded* is the honest third, it will be almost every asset for a long time, and folding it into *expired* would be the system asserting something it does not know.
- An *expiring soon* view, with the window named on the screen rather than implied.

**Two things we have already been bitten by:**

1. **Today is a Lagos day.** *Expires this month* against a UTC date is wrong for an hour every night — report 29 found precisely that in the register snapshot. Use the definition the snapshot uses.
2. **A count that is not its filter is this repository's most repeated defect.** Whatever a tile says, clicking it returns those rows.

---

## Report

`docs/handoffs/34-REPORT.md`.

1. **Which Cadra version accepts the new keys.** One sentence, prominent — Vendra is gated on it.
2. Whether a warranty change is recorded as an event, and why.
3. What the three filter states return on real data — *zero of how many*, per tenant.
4. Wall-clock, and the correction share.

---

## Not in this handoff

**No backfill.** Nothing in this estate has ever recorded a warranty and no receipt carries one to recover it from. Every existing asset reads *no warranty recorded*, truthfully, until somebody enters one.

**And one for me:** whether SAP's purchase order carries warranty terms we should receive on INT-01 rather than type at receipt. A question for their team; it blocks none of this.
