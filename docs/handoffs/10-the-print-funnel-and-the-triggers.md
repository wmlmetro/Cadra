# Handoff 10 — The print funnel, and changes that never take effect

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after the handoff 09 PR. **Branch:** `fix/print-funnel` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
git checkout -b fix/print-funnel
```

### Needs the owner — and the ordering matters more than usual

1. **Merging the PR** (standing).
2. **`upgrade-19` for EVERY tenant carrying `myservice_asset_register`, at or before the image roll.** Report 09 is explicit: `verification_interval_days` is a new stored column read by `_compute_verified` on every `nrs.asset` create and write — which is **Vendra's INT-03 write path**. An un-upgraded tenant raises `UndefinedColumn` and the endpoint 500s. This is not theoretical; it happened mid-handoff and 500'd every call until the fan-out finished.
3. **The telemetry's cluster half, two separate manual actions** — `deploy-dev` with `roll_odoo` enabled for `publisher_warranty_url`, and `upgrade-19` with `myservice_nrs_base` across every tenant for the cron rows. Until both run, the cluster keeps POSTing weekly.

Items 2 and 3 are in `docs/GO-LIVE.md` on the Vendra side as well, because a deployment order that breaks another system's write path is not a Cadra-only fact.

---

## Report 09 is accepted

**The headline is the best sentence in either repository this week: work that simply assumed the scheduler and was right.** The `sla_breached` cron installed at 23:15 and fired at 23:16:37, unattended, flipping 215 requests that had sat past their deadline unflagged — on infrastructure handoff 08 revived two days earlier. That is what a fixed foundation looks like from the outside.

**The migration finding is the one that would have undone the previous handoff.** `post-migrate.py` deleting `cron_asset_pm_refresh_overdue` and `cron_asset_refresh_verification` by xmlid, unconditionally, on every database below that version — so a tenant upgrading straight through would load the new crons and then have the old script delete them, silently restoring the exact state handoff 08 was written to fix. All eight local tenants happen to be safe; **the cluster's version is unverified**, which is precisely the case the guard is for.

**And the `UserError` MRO finding is bigger than the dashboards it came from.** `AccessError`, `MissingError` and `ValidationError` all subclass `UserError`, and the wrapper caught `UserError` first — so `forbidden` (403) and `not_found` (404) have been **unreachable for the entire life of the envelope, on every route.** Vendra branches on `error.code`; an authorisation failure reporting itself as `validation_failed` tells an integrator to fix a payload when the answer is to fix a credential. Guarding it with an AST test that reads handler *order* rather than grepping for names is the right shape. **I have put an audit of the Vendra side into its handoff 15** — those two codes start arriving there for the first time, and nothing on our side has ever seen them.

**Creating `docs/api/CHANGELOG.md` was outside the handoff and correct.** Two rulings said to announce a change in a changelog that did not exist. An integrator does not read handoff reports.

### Rulings on your open questions

**R43 · Q1 — keep correctness, then measure it.** You kept the dotted `@api.depends` so shortening a category's window bites immediately, and flagged the trade rather than taking it. Right call. **Now put a test at the real scale** — 10,259 assets is the largest category on `nrs19` — and record the wall time. If it fits comfortably inside the proxy timeout, the trade is settled and documented. If it does not, that is the moment it becomes a queued job with a `202`, and not before: moving it pre-emptively would trade a correctness guarantee for a latency problem nobody has measured.

**R44 · Q2 — sanctioned.** `on_duty` and `maintenance_status` are the same class, both published, both latent. R29's reasoning is that being true on zero rows is exactly what makes a published field safe to correct now, and you applied it rather than waiting to be told.

**R45 · Q3 — fix it.** `_compute_next_due` rewriting `next_due_date` to today, every day, for any schedule with no `last_done_date`, is a stored compute dirtying rows on every tick — and it makes those schedules permanently `is_overdue = False`, which is the bug you just spent a handoff fixing, in a different costume. Small, and it belongs with the rest of the class.

**R46 · Q4 — fix it.** `security_tabs.js` doing a `search_read` on fields that do not exist on the model is an RPC that raises every time that tab is opened. Out of the previous handoff's rule, in scope now.

**R47 · Q5 — show both.** "Breached" hiding "Urgent" loses information exactly when the record most needs it: a breached *and* urgent request is not less urgent for having breached. Two badges.

---

## The work

**A · The print funnel — and the owner has already met it.** Report 08 finding 2: the `_render_qweb_pdf` hook returns early whenever the ids could be label ids, and handoff 03's own ruling established that tag ids collide with asset ids. On `nrs19` **11,927 of 11,931 asset ids are also valid label ids** — 99.97%. So the guard written for a rare edge case fires on the normal one, both callers are declined, and the register holds 11,879 labels at `issued` and exactly **one** at `printed`.

The owner tagged five assets by hand last week and noticed `printed_at` was `null`. I told him it was a step nothing enforces. He was looking at this.

The test named for the guarantee asserts `printed_at is None` **twice** — both assertions negative — and nothing in the repo requests `/report/pdf/` at all. So the fix needs a test that actually renders.

**Disambiguate rather than decline.** The two id spaces collide by construction, so the guard cannot resolve them by value; it needs the caller to say which it means. Whatever shape you choose, the property to hold is that a print through either real caller stamps, and an ambiguous call from somewhere else is refused loudly rather than silently.

**B · Changes that never take effect (report 08 finding 6).** A `subPath`-mounted ConfigMap is excluded from Kubernetes' update propagation, the ConfigMap is applied on every push to `dev`, and the only step that rolls `odoo-19` is `workflow_dispatch`-gated — so a config fix can be merged, applied, and silently not take effect. That is this programme's signature defect one layer up, and it is the reason item 3 above needs a human to press something. Make it either automatic or loud; a deploy that reports success having changed nothing is the worst of the three options.

**C · The small ones** (R45, R46, R47), and the R43 scale test.

## Acceptance

- A label printed through each real caller records `printed_at` and who printed it, proved by a test that renders the report rather than asserting it did not.
- An ambiguous print call is refused with a message naming the ambiguity.
- A ConfigMap change either rolls automatically or fails visibly. State which you chose.
- The R43 scale test names its wall time.
- Per-tenant fan-out with its verification table. Both suites green, quoted.

## Report

`docs/handoffs/10-REPORT.md`. In it:

1. **How you disambiguated the two id spaces**, and whether anything else in the repo relies on them colliding.
2. **The R43 number.**
3. Wall-clock.
