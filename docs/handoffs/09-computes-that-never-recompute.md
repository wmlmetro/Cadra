# Handoff 09 — Computes that never recompute

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #52. **Branch:** `fix/stale-computes` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
git checkout -b fix/stale-computes
```

### Needs the owner

- **Merging the PR** (standing).
- **One check I cannot do and you cannot either** — see R25.
- **Rotating the `test_client` secret** (standing, outward-facing credential).

---

## Report 08 is accepted, and two of its corrections are to me

**§"What the first scheduler tick actually did" is the section I asked for and it is better than the question deserved.** Staging it with `--max-cron-threads=0`, retiring the debts, *then* waking the scheduler — so the tick had a known start and nothing else moving — is the difference between a measurement and an anecdote. 192 jobs, eight databases, 3m38s. And explaining why 192 and 186 are different measures rather than reconciling them into one comfortable number is exactly the standard.

**Part B is the strongest evidence in the programme that the outbox is built right, and not for the reason either of us expected.** Four seconds, unattended, on two tenants. But the nine-minute `nrs19` case is the real find: a delivery **timed out and had actually landed**, the retry got `409 duplicate`, and handoff 06's ruling that a 409 is a delivery rather than a failure turned what would have been a spurious dead-letter into an `acknowledged`. That design was argued in the abstract months ago and was load-bearing live, on its first real timeout. Nobody planned that test.

**The telemetry cron is a find I would not have made and it is the most serious thing in the report.** A weekly POST to a third party carrying the database name, the installed application list, and the **company name, email and phone** — across these tenants, the Nigeria Revenue Service, Guaranty Trust Bank, Jaiz Bank Plc and the Lagos State Ministry of Health. Neutralising it in two layers before waking the scheduler, rather than discovering it in the log afterwards, is the whole value of having staged the tick. And correcting yourself on it twice — that it had already fired once on `nrs19`, and that your own config comment about failing silently was wrong — is worth more than getting it right first time.

**Deleting two hazardous crons before waking the scheduler rather than after** is the judgement call I would most want made this way.

### The two corrections to my framing, both accepted

**R24 · "Production incident" was wrong and "not one, not once" was too strong.** The k8s configmap has always omitted `db_name` and sets `dbfilter`, so the cluster's worker has been enumerating every tenant. The eight tenants that never ran a cron are the eight **local** ones. I wrote the handoff from `config/*.conf` without checking `k8s/`, and the headline overstated it. Correcting an Architect's framing in the report's first section, before the work, is right.

**R25 · The one thing nobody has confirmed, and it is now an owner action.** You could not reach the cluster (`kubectl` has no context) and neither can I. Until someone runs it, "the cluster is fine" is read from a manifest, not observed. **Owner: on a staging tenant, run `select cron_name, lastcall from ir_cron where cron_name ilike '%epreciat%';` — a `lastcall` inside the last 31 days settles it.** If it comes back empty or stale, this handoff changes shape and everything above it is a production incident after all.

### Rulings on your open questions

**R26 · The dashboard routes: `sudo()` and a 403. Your architecturally-correct option, not the conservative one you shipped.** Take it as its own change with its own tests.

The reasoning is rule 1 and rule 3 together. Those three routes are the only ones in the API that do not `sudo()`, so a permissions failure surfaces as `400 validation_failed` carrying **Odoo group names into the published envelope** — an error code that misdescribes the failure, and an internal detail leaking through a contract. That is worse than silent; it is misleading.

**On the session-semantics change you correctly refused to make unilaterally:** a Security Officer holding `dashboards:read` but no fleet group currently gets an error and would afterwards get data. **That is the correct behaviour and it is the point.** In this API the scope is the gate — that is rule 2's shape everywhere else — and an Odoo group silently acting as a second, undeclared gate is the defect, not the protection. Make the change, name it in the API changelog as a behaviour change, and keep the derived-groups mapping you shipped as the belt to that braces.

**R27 · Stop the telemetry in the cluster.** It has been going out weekly all along, and one POST carrying the Nigeria Revenue Service's company name, email and phone already left this machine on 6 September.

This is not a close call. Client identity for a national revenue service, two banks and a state ministry is not ours to disclose to a third party as a side effect of a default we never chose. Set `publisher_warranty_url` in the cluster ConfigMap and deactivate the cron per tenant, exactly as you did locally. **And it needs a deliberate roll** — you established that a `subPath`-mounted ConfigMap is excluded from update propagation and the only step that rolls `odoo-19` is `workflow_dispatch`-gated, so merging it is not applying it. Say in the report what the owner has to press.

The `digest` cron: deactivate per tenant on the same pass. Harmless today, real email the day anyone configures SMTP, and nobody has decided those 36 subscribers should get one.

**R28 · Yes, one handoff for the whole stale-stored-compute class — this one.** They share a single rule, which you wrote and I am adopting verbatim:

> *A stored compute whose body reads the clock but whose `@api.depends` contains nothing the clock changes needs a cron, and that cron's method must exist.*

**R29 · `is_verified` — the ruling you asked for before touching it.** It is published API surface, so this is mine. **It must expire**, on a per-category verification interval with a sane default. Two things make it safe to do now: it is true on **zero** assets today, so nothing flips; and the alternative is that the first time anyone uses the Verify button, the register acquires a field that says "verified" for ever and means "verified once, at an unknown time". A permanent true is not a weaker version of the control — it is the opposite of it.

Announce it as a behaviour change in the API changelog. Vendra does not read the field.

**R30 · Delete the repo-root `odoo.conf`.** It describes a stack that no longer exists, nothing reads it, and it is the single explicit exception in the new `db_name` guard. An exception carved for a dead file is a hole waiting for someone to put a live file in it.

**R31 · Build the in-registry cron test.** You named it yourself as the only guard that catches this defect in the form it actually took — a database row, not a source file — and the Odoo-native CI step you wired now exists to host it. Walk `ir.cron`, resolve every `state=code` call against the live model, fail on anything that does not resolve.

**Wiring the Odoo-native suites into CI was outside the handoff's scope and you were right to do it anyway.** 1,464 lines of tests that nothing ran, including `test_the_drain_cron_exists_and_trigger_resolves_it` — the single test in the repository that is the correct answer to this entire bug class, written in handoff 06, never once executed. Confirming that Odoo actually returns non-zero so the step gates rather than decorates is the part that makes it real.

**Not in this handoff:** the `_render_qweb_pdf` print funnel (finding 2) and the k8s no-trigger problem (finding 6). Both are real, both get handoff 10. The print funnel deserves one line here because the owner met it without knowing: he affixed a tag last night and noticed `printed_at` was `null`, and I told him it was a step nothing enforces. You found the actual cause — the ambiguity guard declines ~99.97% of calls on `nrs19`, so the print stamp has essentially never fired. His observation and your finding are the same defect from two ends.

---

## The work

**A · Stop the telemetry (R27).** Cluster ConfigMap, per-tenant cron deactivation, the digest cron alongside it, and a clear statement of what the owner must press for it to take effect. Small, and first, because it is the only item here with a third party on the other end.

**B · The stale stored computes (R28, R29).**

- **`sla_breached` first.** 215 of 215 requests on `jaizbankplc` have a deadline in the past and the field is true on none of them — a 100% miss backing a live menu, a filter and a kanban badge. Nothing in `tests/` mentions it.
- **`is_overdue`** — backs a live "Overdue PM" menu that returns empty for ever.
- **`is_verified`** — per R29, with the interval and the changelog entry.

Each needs a cron whose method exists, and a test that proves the field changes when the clock moves rather than when its inputs do. The two orphan crons you deleted were somebody's attempt at exactly this; write the methods this time.

**C · The guards (R30, R31).** Delete `odoo.conf`, drop its exception from the `db_name` guard, and build the in-registry cron test.

## Acceptance

- No telemetry POST can leave any environment, and the report says what the owner must press for the cluster half.
- `sla_breached` is true on the requests whose deadline has passed — quote the count on `jaizbankplc` before and after.
- Each of the three fields changes because time passed, proved by a test that moves the clock rather than the inputs.
- The in-registry cron test fails when a cron's method is renamed. **Prove it fails**, then fix it.
- Per-tenant fan-out shown with its verification table. Both suites green, quoted.

## Report

`docs/handoffs/09-REPORT.md`. In it:

1. **What `sla_breached` becoming true actually does to a live tenant** — how many requests light up, and whether anything downstream (a filter, a badge, a notification) behaves badly at that volume. This is the same class as waking eight schedulers at once, and you handled that one well.
2. **Whether any other published field is a stored compute that reads the clock.** `is_verified` is the one we know about because it is serialised; the question is whether it is the only one.
3. Your wall-clock accounting.
