# Handoff 03 — Tag capture: making "is this asset tagged?" answerable

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` (both PRs merged). **Branch:** `feat/tag-capture` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
# per-tenant upgrade for anything the previous merge added, all eight databases,
# then the verification table from report 02 §Step 0. Paste it into your report.
git checkout -b feat/tag-capture
```

### Needs the owner

- **Merging the PR at the end.** Report 02 established that `gh pr merge` is refused by your permission layer. Push the branch, open the PR, and say so in the report — the owner merges. I have added this to `CLAUDE.md` so no future handoff assumes otherwise.
- **The staging/production deploy of PRs #44 and #45 still needs the per-tenant loop** you documented. That has not happened yet and it is the one way those merges break production.

---

## Report 02 is accepted, and I was wrong about the scope

I escalated "44 files in `dist/` — unassessed" as the headline of that handoff. **`dist/` is not on the Odoo 19 addons path at all.** Its constraints run on the 15 stack where `_sql_constraints` still works, and they are correct as they stand. I counted `grep` hits and inferred a hazard without checking whether the code was reachable — which is precisely the mistake I asked you to avoid when I said a fake that agrees with a wrong assumption is worse than no test.

Three corrections I have taken into `CLAUDE.md`:

- **`dist/` is out of reach** — three independent proofs, the decisive one being that the two vendored trees are mutually exclusive by Odoo version.
- **The "305 warnings" were not a measure of anything.** They count registry loads over eleven days, not affected objects. `305 = 33×9 + 8`, and the clusters drop from multiples of 9 to 8 exactly when handoff 01's fix landed. The real figure was 8 constraints × 7 databases = 56 missing instances. I used a number rhetorically without asking what it counted.
- **The real remainder was ours.** The six `crnd-19/` constraints are not vendor debt — they are the three modules we hand-ported from `dist/` 15.0, carrying the dead syntax across. Checking the CRND public repo directly rather than trusting the fetch script's note was the right instinct.

**The best work here is V1 — the guard had seven ways past it, including a version check the wrong way round.** A guard that reports green while the bug it names is live is the original failure wearing the costume of a test. Catching that in your own deliverable, and then pinning nine parametrised evasion cases so the next person to touch the AST walk finds out immediately, is the highest-value thing in either project so far.

**V5 deserves separate mention.** `cache=False` meant the body-recovery net could never catch anything, so an intermittent 400 hit `/auth/token` — the first call any integration makes. You and the reviewer both initially wrote it off as transient. Refusing to let a failure be attributed to your own recent change is a discipline worth keeping.

### Rulings on your seven questions

1. **Yes, the two rulings were yours to implement.** A decision recorded in `CLAUDE.md` but absent from the code is worse than no decision. You flagged it rather than hid it; that is the correct shape.
2. **Guard scope — agreed, and it is Part A here.** A source test is wrong for vendored trees; the startup/CI assertion on the warning count is right. It does not exist yet, so today the only protection is someone reading a log. Build it.
3. **`dist/` — no. It dies with the 15 stack.** Agreed; recorded so nobody reopens it.
4. **`nrs19`'s missing `jwt_secret` — yes, and it is Part A.** It is the migration target holding 11,878 assets and `/auth/login` 500s on it. A cutover rehearsal that cannot authenticate is not a rehearsal.
5. **`asset_code` `NOT NULL` — yes, Part A.** INT-06/07's dual-code reconciliation is a named control point in the signed-off spec; "one asset per *non-null* code" is a weaker guarantee than that control assumes. Your audit shows zero nulls in every tenant, so the migration is safe today and will not be later.
6. **The nine pre-envelope routes — yes, but not now.** Real and worth doing: `/auth/token` sitting outside the envelope means the first endpoint every integration touches is the one that behaves differently. It is a refactor of the auth surface, so it goes in the backlog and gets its own handoff after INT-03 is live. Backlogged in `CLAUDE.md` alongside V4.
7. **Yes, fixing `get_params()` was right.** One word, an intermittent 400 on a published contract, on the first call of every integration. I would rather you fix that class of thing and tell me than leave it because of a scope line.

---

## Part A — carry-overs (small, independent, good parallel fan-out)

1. **`asset_code` `NOT NULL`** with the unique constraint, so the guarantee INT-06/07 leans on is real. Verify zero nulls per tenant first (your audit says zero; re-check, data moves), and fan out.
2. **Startup/CI assertion on the dead-constraint warning**, covering the vendored trees a source test cannot: after a restart, `_sql_constraints` warnings must be zero. Make it fail loudly somewhere a human will see it, not just in a log.
3. **`jwt_secret` on `nrs19` and `test19`**, so `/auth/login` works on the migration target. If setting it is a per-tenant provisioning step, document it as one — a fresh tenant hitting the same wall is the real defect.

## Part B — tag capture (the substance)

Report 01 Part C established the finding: **Cadra records neither printing nor affixing.** `action_print_tag()` writes nothing, `tag_date` is the creation date wearing a misleading name, and `nrs.asset.tag.label.state` is a replacement lifecycle reading `active` from creation. There is nothing to expose, and no API change can fix that — which is why we are building capture before transport.

The Integration Flow makes this a control point: Cadra generates the identity, an **independent** Tag-Issuing Unit prints and affixes, and the serial-to-tag match is recorded at the point of tagging. The separation is deliberate — the person creating the record and the person issuing the tag are different people. Whatever you build must preserve that; a `label_state` an operator can set to `affixed` from a desk is not evidence of anything.

Build your own proposal from report 01 §Part C:

1. **`label_state` on `nrs.asset.tag.label`** — `issued | printed | affixed | scrapped` — distinct from the replacement `state`, which keeps its meaning. **Not** on `nrs.asset.state`; that is published API surface with a consumer now.
2. **A print-issued event** — `action_print_tag` / `action_batch_print_tags` stamp the timestamp and the issuing user. Cheap; the hooks are already the single funnel.
3. **An affixed event with an inbound confirmation** — `POST /api/v1/assets/<id>/tag-affixed` carrying tag number, who affixed it and when, scoped to a new `tagging:write`. `myservice_barcode_station` is the natural place for the scan that raises it.
4. **Expose the honest state** on the asset serialiser and as a filter, so Vendra can see it — but only once it means something. Until an affix is recorded, it must not read as tagged.

**Do not build the outbound callback yet.** Your delivery/retry finding — `workflow.dispatch.log` records attempts but nothing retries, so a callback fired while Vendra redeploys is lost and faithfully logged as lost — is exactly why transport gets its own handoff with a proper `ir.cron`, backoff, `event_id` idempotency and a dead-letter state. Capture first.

## Acceptance

- A tag can be printed, and Cadra can tell you it was, by whom, when.
- A tag can be confirmed affixed through the API under its own scope, and only then does the asset read as tagged.
- An asset that has never been tagged reads as such — the false-completeness trap does not reappear in the new field.
- `asset_code` is `NOT NULL` and unique in all eight databases; `/auth/login` works on `nrs19`.
- Full suite green, quoted verbatim; per-tenant loop shown; state which layers you tested at.

## Report

`docs/handoffs/03-REPORT.md`, same standard. Push, open the PR, name the merge as owner-blocked, notify the Architect.
