# Handoff 08 — Nothing scheduled has ever run

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #51. **Branch:** `fix/scheduler-all-tenants` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
git checkout -b fix/scheduler-all-tenants
```

### Needs the owner

- **Merging the PR** (standing).
- Nothing else. **This handoff is the highest-priority work in either repository** — read the next section before planning it.

---

## What the owner found, driving the chain by hand

He affixed a tag on `nrs19` through the API. Cadra recorded it, raised `asset.tag.affixed`, and wrote it to the Dispatch Log — where it sat at **`pending`** and never moved. Vendra showed `0 tagged`. Nothing errored. Nothing was logged as wrong. Nothing was lost. Draining the queue by hand delivered it in seconds and the unit read `Tagged`.

`config/odoo.19.conf:7` sets **`db_name = odoo`**, and Odoo's scheduler only serves the database named there. `config/odoo.dev.conf:7` says the same.

**So no `ir.cron` has ever run on any tenant except `odoo`.** Not one, not once. That includes all eight production-shaped tenants.

### This is much larger than the tag callback

The INT-05 delivery cron is how it was found; it is not the worst of it. Every scheduled job this product ships has been dormant on every tenant:

| Cron | What its never running means |
|---|---|
| `Cadra: deliver outbound asset events (INT-05)` | Every integration event queues and stays queued. **How we found this.** |
| `NRS Asset Depreciation — Recompute book values` | **Book values have never been recomputed on any tenant.** For an asset register sold to a revenue service, this is the one with an auditor attached. |
| `Cadra API: purge expired / revoked refresh tokens` | Expired and revoked tokens are never cleaned up. A security item, and it compounds with handoff 06's wildcard-scope work. |
| `NRS Asset PM — Auto-create service requests` | Preventive maintenance is never raised. |
| `Fleet: Check Preventive Maintenance Due` | Same, for fleet. |
| `NRS — Push asset data to Redhubs` | Never pushed. |

**Confirm that list before acting on it.** I read it out of the `data/*.xml` files under the `myservice_*` addons, which are the ones on the addons path. I have deliberately excluded everything under `dist/` — that path is *not* on the addons path in this stack, and I have over-escalated a `dist/` finding once before in this programme. Check whether any `dist/` module is actually installed on a live tenant before adding it to the list or leaving it off.

**In the report, say what each dormant cron has cost.** Not "it did not run" — what state is now wrong because it did not, and whether that state needs a backfill. Depreciation is the one I expect to need one.

### Why nothing caught it

Every test in this repository that exercises delivery calls `_cron_drain_outbound_events()` **directly**. That is a legitimate way to test the logic and it is why report 06's retry, backoff and dead-letter proofs are real. But calling the function proves the function works; it says nothing about whether anything calls it. Report 06 proved delivery *works*. It could not prove delivery *happens*.

That gap is the lesson of this handoff and it generalises: **a test that invokes the thing under test cannot see that nothing else invokes it.** Look for the same shape elsewhere while you are in here.

---

## Part A — the fix

`docker-compose.19.yml` already passes `--db-filter=${ODOO_DBFILTER:-}`, so the mechanism exists and is unused.

Remove `db_name` from the Odoo 19 config and select the database by host filter instead, so the scheduler covers every database while host-based routing keeps working. `config/odoo.dev.conf` carries the same line and gets the same treatment; check `config/odoo.prod.conf` and `odoo.conf` and say in the report what each of them is for and whether it is live anywhere — `odoo.conf` names a different database entirely (`myservice`) and I do not know what uses it.

**Two things to get right**, because this is a change every tenant feels at once:

- **`--max-cron-threads` is currently 1.** One thread now has eight databases to work through instead of one. Say in the report whether that is sufficient and what you based the answer on; do not simply raise it because more sounds safer.
- **Waking eight dormant schedulers at once means every overdue job fires at once.** Depreciation across 11,878 assets on `nrs19` alone, plus whatever the other seven hold, plus every queued integration event. Work out what the first tick actually does before you cause it, and if it needs staging, stage it deliberately and say so.

## Part B — prove it unattended

**This is the acceptance criterion that matters and it is the only one I will not accept an argument about.**

On `nrs19`, affix a tag through the API and then **do nothing**. No shell, no manual drain, no calling the cron function. Wait for the scheduler.

The event must deliver on its own and Vendra must show the unit as `Tagged`. Quote the timestamps: when the event was queued, when it was delivered. The gap between them is the proof.

Then do the same on a second tenant, because "it works on the one we always use" is what we believed yesterday.

## Part C — every API client acts as Administrator

The owner's second finding, from the same session. Confirming a tag records:

```
"affixed_by":      { "id": 2, "name": "Administrator" },
"affixed_by_name": "S. Abolarin"
```

The operative's name is free text; the system's record of *who acted* says Administrator, and will for every tag affixed by any client for ever.

**The control is intact; the audit trail is not.** Scope separation genuinely holds — Vendra is refused `tagging:write` and cannot certify an asset it created. But the entire point of that separation is to answer *who confirmed this label*, and today the answer is the one answer that means nothing.

Give each API client its own Odoo user, named for the client, holding only the groups its scopes require. Existing records cannot be corrected and should not be pretended about — say in the report how many rows carry the useless value.

## Part D — the debts

The `h05_*` test users on `nrs19` and the `phase1_*` seed users. They were left deliberately so transcripts reproduce; the transcripts are written and these must not reach staging. Rotating the `test_client` secret stays with the owner — it is an outward-facing credential.

## Acceptance

- **A tag affixed on `nrs19` reaches Vendra with nobody watching**, and again on a second tenant. Timestamps quoted.
- Every cron in the confirmed list is shown running on a non-`odoo` tenant.
- The report says what each dormant cron cost and which need a backfill.
- A tag confirmation records the Tag-Issuing Unit's own user, not Administrator.
- The eight-tenant fan-out is shown, with its verification table.
- Full suite green, quoted verbatim.

## Report

`docs/handoffs/08-REPORT.md`. In it:

1. **What the first scheduler tick actually did** on a tenant that had never had one — how many jobs fired, how long it took, and whether anything needed staging. This is the number I most want, because it is what a production cutover will do too.
2. **Whether depreciation needs a backfill**, and what that looks like.
3. **Anywhere else the same shape appears** — a guarantee proven by a test that calls the thing itself, with nothing proving anything else calls it. That question found this one.

Push, open the PR, name the merge as owner-blocked, notify the Architect.
