# Handoff 02 — The silently-dropped database constraints

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #44 merges. **Branch:** `fix/restore-sql-constraints` → PR into `dev`.
**Origin:** report 01, "Findings outside this handoff's scope" — escalated, and it is bigger than you found.

## Report 01 is accepted

This is the strongest first handoff either project has had. Three things stand out.

**Reproducing the idempotency race before changing anything** — four concurrent requests, one key, two assets, four 201s, no error — turned a theoretical CR item into a demonstrated defect, and then proved the fix with the same probe. That is the standard.

**Finding the cause under the symptom.** My CR-3 item 4 asked you to move `idempotency_store()` inside a try/except for a `UniqueViolation`. You established that the violation could never fire because the constraint does not exist, so my instruction would have been a no-op that looked like a fix. That is the second time a Builder has caught me specifying a fix for a mis-diagnosed cause, and both times the report said so plainly instead of quietly complying.

**V1 — the multi-tenant migration.** You caught yourself: the suite was green because you had upgraded the one database it runs against, while six others were serving broken asset endpoints. One registry, many tenants, a stored column — I had not thought about it, the handoff said nothing about it, and it is the one way that PR could have taken production down. Putting the per-tenant loop into CLAUDE.md as a standing rule is exactly right.

Also correct: fixing the 500→400 for *all* coercions rather than only Selection, treating a 500 as an integration hazard because it tells the caller to retry a permanently-bad request, and declining V4 as an API-wide contract decision rather than smuggling it in. The `test_concurrent_same_key` honesty — "~20% false-negative, documented in its docstring" — is worth more than a test that claims certainty it does not have.

### Rulings on your open questions

1. **Nested `data.provenance` — keep it.** It matches the existing grouping and adds one envelope key rather than six. I will tell Vendra to read `data.provenance.grn_reference`.
2. **Yes, add `vendra` to `import_source`.** The enum already names integration partners (`sap`, `redhubb`), the field's entire purpose is naming the source, and `other` + a ref throws away the signal. Additive, so safe.
3. **Broadening `q` — accepted**, with your reasoning: an auditor pastes a GRN into the search box before finding a named filter. Note it in the API docs as intended behaviour so nobody "fixes" it later.
4. **Yes — that is this handoff, and it is wider than you found.**
5. **Part C: capture first, transport second — agreed, and it is handoff 03.** Your finding is the important one: `label_state` as it exists today would reproduce the same false-completeness bug in a new field, so exposing it was never the cheap option. Vendra will keep showing `Registered` and claim nothing further.

**Also decided:** on non-idempotent routes, validate the header's *length* everywhere (cheap, and a caller sending a 200-character key deserves to know), but do **not** reject the header itself — callers spraying it harmlessly should not start failing. Document which routes actually honour idempotency. V4 (unvalidated query-parameter enums) gets its own handoff once this and Part C land.

---

## The problem, restated with the real blast radius

Odoo 19 removed `_sql_constraints`. `orm/model_classes.py:162` logs a warning and **creates nothing**. You found three occurrences. There are more:

| Where | Files | Status |
|---|---|---|
| `myservice_api/models/api_idempotency.py` | 1 | **fixed** in PR #44 |
| `myservice_asset_register/models/asset.py` | 1 — `unique(asset_code)` | **live hole** |
| `myservice_staff_bus/models/bus_route.py` | 1 — `unique(code)` | **live hole** |
| **`dist/` — vendored CRND/OCA addons** | **44 files** | **unassessed** |

The 305 warnings in the container log are the measure of it. Every uniqueness and check constraint declared the old way, anywhere in the installed codebase, is currently absent from every Odoo 19 database. `dist/` is vendored third-party code nobody has been thinking about, and it is installed and holding real data.

**Why `asset_code` is the urgent one.** The September Integration Flow makes dual-code reconciliation a named control point: *"an asset is complete only when both the Cadra Asset Code and the SAP asset code are linked on the register."* INT-06/07 assumes one asset per code. Without the constraint, two assets can share a code, and the reconciliation silently matches the wrong one. Zero duplicates exist today, so this is a hole rather than an incident — which is the good time to close it.

## The work

**Step 1 · Audit before fixing.** Enumerate every `_sql_constraints` in installed code — ours and `dist/` — and for each: what it guarantees, whether it exists in the database today (check every tenant, the way you did for the idempotency table), and whether the data currently violates it. Land this as `docs/constraint-audit.md`. **The audit is the deliverable even if some fixes wait** — an unenforced constraint you know about is manageable; one you do not is not.

**Step 2 · Fix ours.** `asset_code` and `bus.route.code`, using the dual-spelling pattern you already established in `api_idempotency.py` so the Odoo 15 production stack is unaffected.

**The hard part is pre-existing duplicates, and it is not the same problem as the cache table.** There you could delete the loser of a stale race; here rows are real assets someone may have scanned, moved or maintained. If any tenant holds duplicate `asset_code` values, **do not deduplicate them silently** — report them per tenant with enough context to decide, and let the constraint wait behind that decision. Adding a constraint that quietly drops asset records would be a far worse defect than the missing constraint.

**Step 3 · Assess `dist/`.** Do not fix 44 vendored files blind. Classify by risk — which guard identity or uniqueness that our code or the API depends on, versus which are cosmetic — and recommend. Patching vendored addons has a maintenance cost at the next upgrade, so the recommendation matters as much as the finding.

**Step 4 · Stop it happening again.** A test, a lint rule or a startup check that fails loudly when `_sql_constraints` is declared on Odoo ≥19 in our own modules. Silent removal of a data-integrity guarantee is exactly the class of failure that should never again be discovered by accident.

## Acceptance

- `docs/constraint-audit.md` exists and covers every occurrence in installed code, with per-tenant existence and per-tenant violation counts.
- `asset_code` and `bus.route.code` uniqueness enforced in every local database, or explicitly blocked on a duplicate-data decision with the duplicates listed.
- The guard from step 4 fails on a deliberately reintroduced `_sql_constraints`.
- Full pytest suite green, quoted verbatim. Per-tenant upgrade loop run and its output shown — that rule is yours and this is its first real outing.

## Report

`docs/handoffs/02-REPORT.md`, same standard. Notify the Architect when done.

**One judgement call is explicitly yours:** if the audit shows the `dist/` situation is large or hazardous, stop at the audit plus our two constraints, report, and I will scope the rest. Finding out how deep it goes is worth more than fixing half of it.
