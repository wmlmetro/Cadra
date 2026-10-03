# Handoff 50 — The consequences

**Branch:** `fix/the-consequences`
**Report:** `docs/handoffs/50-REPORT.md`

> **Needs the owner, up front:** merging; the cluster; and `cadra19`, `nrs19` and `gtb19` are still unclassified, so three tenants still have no personas — six handoffs now.
>
> **Still unrun and still not this:** `33-the-whole-surface.md`.

---

## 0 · Report 49 accepted

Four screens over four routes that were never touched, both gates registered on each, and a 29-screenshot drive as the person the screens are for. Three things in it are worth more than the pages.

**You measured "empty" instead of assuming it.** The first empty-state run used 2020 and came back with 37 rows, because every local tenant's fixtures backdate disposals to exactly 2020-01-01. That is the denominator rule pointed at a date, and most people would have shipped the screen.

**You refused to invent a scope to hide the export**, and reported the consequence instead. That is the third time in three handoffs that the honest answer has been *here is the thing you now have to decide*, and it is why the role model is defensible.

**And the departed-custodians card re-measured before it was built** — 87 assets, 59 people, 0 flagged, out of 207 departed — with the held-assets denominator honestly reported as 6,644 against the earlier 6,646. A number we are about to put in front of NRS, checked rather than carried.

---

## 1 · Three rulings from your report

### Ruling 1 · The export gets its own permission. A store officer may not take a copy of the register.

Your §A finding: three of the four screens sit on `assets:read`, so every Asset User, Officer and Manager is answered — **including the whole-register export.**

Reading a page of the register and taking a copy of all of it are **different acts**, and `assets:read` currently means both. That is one name carrying two meanings, which is exactly what handoff 47 split twice for. The same logic applies here and I am applying it: **the export moves to its own permission, held by the Auditor and the Administrator.**

This is a split, not an invention — the same distinction 47 drew between the employee picker and the access record. Announce it BREAKING as 47's were, and say in the report who on each tenant loses the export.

### Ruling 2 · The app gets an error boundary. Today any render bug is a blank page with no words.

Your §E.2: a null book value threw in render and, with **no React error boundary anywhere in the tree**, the entire app unmounted to a blank white page. You fixed the null; the hole is still there.

A blank page with no words is the worst failure this product can produce — worse than an error, because the person cannot tell whether it is their network, their account, or us, and there is nothing to report. **Add a route-level boundary** that shows a sentence, says what the person can do, and keeps the shell so they can navigate away. Prove it by deliberately throwing inside a page.

### Ruling 3 · The attribution trailer stops being a memory problem.

Twice now — reports 37 and 49 — the Step-0 commit has carried the trailer the repository forbids, both caught after the push, both disclosed honestly. **That is a systemic failure, not carelessness:** the tool's default is applied before the rule is consulted, every time, by a different session.

A rule that depends on remembering is a rule that will be broken again. **Make it mechanical** — a commit-msg hook, a CI check, whatever is cheapest and cannot be forgotten — so a commit carrying it fails rather than ships. Past commits stay as the owner ruled.

---

## 2 · Two things 47 left behind

### 2.1 · The map hands the fleet to people 47 just took it from

`GO-LIVE.md` §25, found by 47's own verification pass: `GET /dashboard/map` stays on the register's scope because it backs the register dashboard — and its payload carries **one row per geocoded vehicle, with plate and driver**. So an Asset User refused `/fleet` reads the fleet through the map.

47 split `dashboards:read` precisely so that could not happen, and this is the hole in its own fix. It is a BREAKING serializer change and that is why it was left; it is also identified personal data about named drivers, so **it is not a leftover, it is the finishing of the job.**

Decide what the register dashboard actually needs from that payload and send only that. If the map genuinely needs the vehicle rows, then it is a fleet screen wearing a register scope and should move — say which, with the reason.

### 2.2 · Credentials provisioned under the old scopes

`GO-LIVE.md` §25's last item: a credential that held `identity:read` to read the access-changes report now needs `access:read`; one that held `dashboards:read` for the fleet, FM or security endpoints now needs `operations:read`; one that held `assets:write` to mint or replace labels now needs `tagging:write`.

**Per-tenant counts, then a decision.** If nobody is affected on any tenant, say so with the counts and we are done. If somebody is, the fix is a credential's scope row and a named decision, not a quiet widening.

---

## 3 · One thing to name rather than fix

Your §G: the whole browser suite has **two failures that are the §13.5 baseline pair, both depreciation specs, red on `dev` before this branch.**

Handoff 37 found and fixed a depreciation defect that was red for one hour a night. **Say whether these two are the same thing in browser form, a second instance of it, or unrelated** — and if the answer is that nobody knows, that is the answer and I want it. Two red browser tests living on `dev` is how the last pair started.

---

## 4 · Verification

- The export refused to a Store Officer and answered to the Auditor, driven as each, with the per-tenant counts of who lost it.
- The map payload, before and after, as an Asset User — the vehicle rows gone, the register dashboard still drawing.
- A deliberate throw inside a page, showing the boundary rather than a blank screen.
- A commit carrying the trailer, refused by whatever mechanism you build.
- The credential counts per tenant.
- The persona matrix re-run, since permissions move again here.
- Suites with denominators, and the standing sentence pass.

---

## 5 · What is left of handoff 33 — absorbed, so it stops being deferred

`33-the-whole-surface.md` is marked superseded and must not be run. Three of its four sections were executed by handoff 37; what remains is three items, and they live here because three items is not a handoff and keeping them listed as one is why they have been put off seven times.

**§B1 · The three write-only keys.** A key that can be written and never read back is a record nobody can check. Publish them. If any one of them should *not* be readable, say which and why — that is a finding, not a reason to skip it.

**§D1 · Widen the census.** Report 37 re-took it a third time and the number had moved again — 163, then 179, then 286 — so whatever this guard counts, it counts something that changes under us. Widen it as 33 asked, and **state the denominator and the date every time it is quoted**, which is the rule that caught the last two moves.

**§D3 · The words guard.** 33 wanted a guard over user-facing strings forbidding field names and backticks. Report 36 showed why it cannot be applied as written: the gated-write refusal deliberately prints a literal command, on the reasoning that an error naming a remedy the reader has to look up is worse than one naming none. **So the ruling 36 proposed stands: an API error and an audit-history sentence shown on a screen are different classes of string, and the guard cannot be drawn until they are separated.** Separate them, or record precisely why the census cannot be drawn — 33 itself offered that escape and it is still the honest answer if it is true.

**None of these three is urgent.** They are here so they get done rather than deferred an eighth time. If any of them turns out to be larger than it looks, stop at that one and say so — do not let it swallow §§1–4, which are the reason this handoff exists.
