# Handoff 14 — Who has held this laptop

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/custody-chain`.

> Report 13 accepted in full, including all six deviations. Two of them are the report: `in_progress` and the vendor count were **not** samples — they were structurally zero on every tenant since the day they were written, hidden behind a defect that at least produced a moving number. You found them by fixing something else and looking, which is the only way anybody ever finds that.
>
> The `except Exception: pass` finding at the end of your report is the right size and shape for its own handoff. It is queued as 15. This one is the piece INT-10 cannot be delivered without.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/custody-chain && git push -u origin feat/custody-chain
```

**Needs the owner:** the handoff 13 PR (`fix/honest-counts`) into `dev`.

---

## A · Four unauthenticated 500s, two lines each

Report 13 §2 is the most useful table anyone has produced this month, and it contains a cheap emergency. **`/auth/login`, `/auth/refresh` and `/auth/revoke` answer a raw Odoo HTML 500 to an unauthenticated caller** who sends a non-string where a string is expected — the same defect handoff 12 found and fixed on `/auth/token`, which you noted shares one shape with all three.

Fix those three with the two-line type check that fixed the fourth. `/auth/revoke` gets it twice over: it has **no try/except at all** and advertises that it always answers `200 {"revoked": true}`.

**Do not attempt the `@cadra_route` refactor for the other five.** That is a real piece of design and I want to scope it against the whole route table, not have it arrive inside a handoff about custody. `openapi.json`, `docs`, `export.csv`, the employee import and `brand` stay as they are, listed and known.

**A test that asserts a JSON envelope, not merely a non-500.** An HTML page with a 200 would pass a status check.

## B · The custody chain

`nrs.asset.custody`. This is the largest single gap in INT-10 and it is the one an auditor tests first.

**What exists today, from your own measurement:** 217 custody changes on `jaizbankplc` living as `mail_tracking_value` rows, unreachable over the API, in a store a user with the right groups can delete. The PRD requires a record that *"cannot be edited retrospectively, only appended"*. A chain of custody that can be deleted is not a chain of custody.

**Append-only, and mean it.** `create` is the only operation. Override `write` and `unlink` to raise, on the model itself rather than by ACL — an ACL is configuration and configuration is what the last three deployment failures were made of. Include the `sudo()` path: a record whose whole value is that nobody can alter it must refuse the administrator too, and say so in the exception message.

**What a row carries.** From, to, when, and **who made the change** — the acting user, not the custodian. An auditor's question is *"who moved it"* as often as *"who had it"*. Plus a free-text reason where the caller supplied one, and a source (below).

**Written from one place.** `POST /assets/<id>/transfer-custody` is the only writer today and stays so. Its docstring currently says the trail comes from `mail.thread` tracking; that sentence becomes false with this change and must go, replaced by one naming the model.

**The backfill, and the label that makes it honest.** Reconstruct from the tracking values — they carry actor and timestamp, so the reconstruction is faithful. **Every backfilled row carries `source = 'tracking_backfill'` on its face** and the API returns it. It will look sparser than the register, because it only covers changes made since `custodian_id` became tracked, and **that is the correct picture**: an auditor told where the record begins can work with it, one who discovers the gap later cannot trust any of it. Say the same thing in the backfill patch's own docstring.

Run it on all eight tenants and report the row count each produced, next to the tracking-value count it drew from. If those two numbers differ anywhere, that difference is a finding and I want it in the report rather than reconciled away.

**Reading it.** `include=custody` on the asset, and its own paginated route. Two things this must not repeat: it is a **list**, so it inherits handoff 12's honest `total_estimate` and the truncation warning for free — check that it actually does rather than assuming; and it must not be capped at 20 the way the embedded transfers list is, because "the last twenty custodians" is precisely the answer an auditor cannot use.

**Update `docs/integrations/INT-10-audit-access.md`** — §2.3 and §3 currently describe the absence. They should describe what exists, and keep describing what still does not.

## C · The staleness gap — I was wrong, and here is the bound

**My acceptance criterion in handoff 13 said reduced limits take effect on the next request. That was not achievable and you were right to say so plainly rather than quietly meeting it another way.** The cap is a JWT claim and an access token is unrevocable for its lifetime by design; revoking the refresh families was the correct half and it is built.

I am not taking any of your three options. **Bound the window instead:** a client whose limits differ from the default may not carry a `token_ttl_seconds` above 3600. A constraint, refused at save, with a message saying why — *a raised limit that outlives the decision to lower it again*. Every client on every tenant is already at 3600, so this changes nothing today and makes the indefensible case unreachable tomorrow. No hot-path read, no ceremony.

---

## Acceptance

- Three auth routes answer a JSON envelope to a malformed body; a test asserts the envelope, not the status.
- `write` and `unlink` on a custody row raise, including under `sudo()`.
- Every custody change through the API produces exactly one row, carrying the acting user.
- The backfill produces the same count as the tracking values it read, on all eight tenants — or the report says where and why it does not.
- A backfilled row is distinguishable from a live one by anyone reading the API, without knowing to ask.
- The custody list reports a true total and is not silently capped at 20.
- A client with a non-default cap cannot be saved with a TTL above 3600.
- Guards proven to fail before they pass, as every time.

## Report

`docs/handoffs/14-REPORT.md`. Short.

1. **The backfill numbers per tenant**, and any tenant where the two counts disagree.
2. Whether anything else in the app writes `custodian_id` without going through the route — a second writer would make the chain incomplete on its first day, and that is the one failure this model cannot recover from.
3. Whether `include=custody` inherited handoff 12's honesty for free or needed help.
4. Wall-clock.

---

## Two things for me, not you

**`docs/ENVIRONMENT-FACTS.md` is written and is in this branch's base.** Your two from report 13 are its first entries — ProxyFix needing `X-Forwarded-Host`, and the Postgres crash-restart being a standing condition of this stack rather than anything you did. Put the next one straight in it rather than at the top of a report.

**The cluster half of your IP answer is a real open question and it is mine.** You reasoned it correctly and could not measure it; the first failed login from staging settles it with one grep, and I have put it on the owner's list rather than leaving it in a report. If it comes back `ip_source=xff,infra` with a node address, the caller IP is being lost at the load balancer and that is a configuration change, not a code one.

---

## Closing step — leave the repo where the next person starts

**This is now the last step of every handoff, this one included.** Do it after the report is committed and your branch is pushed, and *before* you tell the Architect you are done.

```bash
git checkout dev
git pull --rebase
git push origin dev
```

**Why it has to be you.** The Architect writes handoff instructions, rulings and shared documents straight onto `dev`, from a sandbox **that has no push credentials**. Those commits sit on the local base branch, invisible on the remote, until somebody pushes them. Four times now the owner has been handed a two-line push as homework at the end of a handoff, and twice the push did not happen — so a Builder branched from a `dev` that was missing the instruction file it was about to be told to execute, and the file had to be recovered by hand.

**And it leaves the working tree on `dev`.** Your feature branch stays pushed and unmerged, as standing — the owner merges. But the repo the owner returns to is on the branch everything starts from, already current, with nothing local waiting to be sent.

`git pull --rebase`, not `--ff-only`: the local base carries the Architect's commits and the remote will usually have moved under them. They are documents, so a rebase is honest and a merge commit would claim something happened that did not.

**If the push is rejected**, do not force it. Say so in the report with what `git status -sb` shows, and stop. A rejected push on the base branch means somebody merged while you worked, and that is the owner's to look at.

### CLAUDE.md — add this to the handoff protocol

Under the numbered handoff-protocol steps, after the report and notification bullets:

> - **Closing step, every handoff: return the repo to `dev` and push it.** `git checkout dev && git pull --rebase && git push origin dev`, after the report is pushed and before notifying the Architect. The Architect commits handoff files and rulings onto `dev` from a sandbox with no push credentials, so those commits reach the remote only when a Builder pushes them — and a Builder that branches from a stale `dev` starts from a base missing its own instructions. Leave the working tree on `dev`. Never force a rejected push; report it and stop.
