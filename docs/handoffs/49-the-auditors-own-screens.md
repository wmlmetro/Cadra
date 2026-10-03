# Handoff 49 — The auditor's own screens

**Branch:** `fix/the-auditors-own-screens`
**Report:** `docs/handoffs/49-REPORT.md`

> **Needs the owner, up front:** merging; the cluster upgrade; and `cadra19`, `nrs19` and `gtb19` are still unclassified, so they still have no personas — five handoffs now.
>
> **Also unrun in this repository:** `33-the-whole-surface.md`. Report 37 §5 says its remainder returns as a re-queue. **That is not this handoff.** Do not start it.

---

## 0 · Report 37 accepted — and two things in it outrank the handoff

**The old SAP door was never a door.** Driving it beside the new one showed it cannot create or update a single employee on the Odoo 19 stack, because the employment-record table wants a *who changed this* stamp and that route runs with nobody to stamp it. **And it reports every one of those failures under a top-level `"success": true`.** We spent three handoffs arguing about how to secure a lock on an empty room. Retiring it was right for a far stronger reason than the census.

**And the two red tests were red for one hour a night.** The register stamps a disposal with the Lagos day and the depreciation module measured *today* in UTC, so between 23:00 and 24:00 UTC a freshly disposed asset read *fully depreciated*. Every green run before was genuinely green. Report 36 happened to drive at 22:49. Your own sentence is the one I will be quoting: *a test that is red one hour a night and green twenty-three is worse than a red test — it converts "the suite passed" from a fact into a statement about when you ran it.*

**That is the third Lagos-versus-UTC defect in this programme** (handoffs 29, 30, now this). It is a pattern, not a coincidence, and freezing the clock inside the bad hour is the right shape of fix. If you ever see a date compared without an explicit zone in this codebase again, treat it as a defect on sight.

The disclosed commit trailer is noted and the owner has chosen to leave it. Keep the rule from here.

---

## 1 · What this builds

**Zainab Garba is an auditor whose screens do not exist.** Four things the server already answers to her, with no page in the app:

- `GET /api/v1/reports/configuration-changes`
- `GET /api/v1/reports/disposals`
- `GET /api/v1/reports/asset-register`
- `GET /api/v1/assets/export`

The access-changes report got its screen in handoff 41 and its own permission in 47. These four are the rest of her job.

**This is a front-end handoff.** If you find yourself changing a route to make a page work, stop and say why — these have been answered to auditors for weeks, and a change to them is a change to a published contract.

---

## 2 · Three rules, and the first is not negotiable

**An empty report says it is empty. It never shows invented data.**

Handoff 47 removed two screens from this product for exactly that reason — they rendered sample data built into the app, to every client, about their own organisation. **Building a new screen that falls back to a mock when a tenant has no rows would repeat that mistake a week later.** No mock import, no placeholder rows, no illustrative chart. If a tenant has no disposals, the page says so in a sentence.

**Both gates apply, as they now do everywhere.** A new nav item needs its scope (handoff 47) and its sidebar switch (handoff 48). Default on. Register the switch keys properly — `v1_sidebar.py` already keeps retired keys so they are never reused.

**Drive it as the auditor, not as an administrator.** Every screen in this handoff exists for one persona. Sign in as Zainab, reach each page, and type the URL of each as a persona who should not have it. That is how report 46 found three real gaps and how 37 found that the door was broken.

---

## 3 · The export is a different shape

`/assets/export` is a download, not a table. Decide and state: what the button does, what the file is called, what a large tenant does — `nrs19` holds 11,951 assets — and what the person sees while it is being produced. A silent click that may or may not have worked is the worst outcome available here.

---

## 4 · One thing to add, because it is already true and nobody can see it

Report 45 measured, and report 43 before it, that **87 of 6,646 held assets on the NRS register belong to 59 people who have left** — none flagged for retrieval, and SAP still calls all 59 active.

That is precisely what an auditor's disposals-and-register screens exist to surface, and right now the only way to know it is to read one of our reports. **If one of these four pages can answer it without inventing a new endpoint, make it answerable** — a filter, a column, a count. If it cannot, say which route would need to change and leave it; I would rather have the sentence than a rushed endpoint.

---

## 5 · Verification

- All four screens, as Zainab, on two tenants, screenshotted.
- Each of them on a tenant where the underlying data is **empty**, showing the empty state rather than anything invented.
- Each URL typed by a persona who should not have it, refused by the server.
- The export driven end to end on `nrs19`'s volume, with the timing said.
- The sidebar switches for the new items, on and off.
- Suites with denominators, and the standing sentence pass.

---

## 6 · And then the clearance screen

NRS asked for offboarding by name and we removed the mock in 47 having recorded that we owe them a real one. The mechanism exists — `retrieval_flag`, `action_flag_retrieval`, `action_mark_retrieved` in `myservice_identity` — and has **no API route at all**, so it is reachable only from the back office.

**That is the next handoff, not this one**, and it is waiting on one answer from NRS: what clearance means to them in practice. Report 43 §G.2 found custody is held by *employee records* rather than accounts — 1 of 11,386 employees on their register has a login — so their offboarding question was never about switching off a user, and I want that confirmed with them before we build the screen that implies it is.

**If while you are in these four screens you learn something that bears on that**, put it in the report. You will be closer to the data than I am.
