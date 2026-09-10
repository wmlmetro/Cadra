# Report 19 — Make CLAUDE.md readable again

**Builder** · branch `docs/claude-md-diet` · base `dev` at `1203ac9`.
**Needs the owner: the PR merge** (`gh pr merge` is refused by the Builder's permission layer).

**Step 0 was the new rule working.** The instruction file arrived as an uncommitted working-tree file with no ref touched. I committed it on `dev` as `952bc76` and pushed, then branched. Nothing had to be replayed, nothing was orphaned, and there was no lock file. That is the whole cycle §A describes, exercised once before being written down.

---

## 1 · The four counts

| | Before (in `CLAUDE.md`) | After (in its new home) | Byte-identical |
|---|---|---|---|
| Decision ledger lines | **117** | **117** in `docs/DECISIONS.md` | yes, and in the original order |
| Status table rows | **19** | **19** in `docs/STATUS.md` | yes, and in the original order |

Verified by extracting the exact source ranges from `git show 952bc76:CLAUDE.md` and `diff`ing them against the new files — not by counting twice. Both diffs are empty.

**The ledger was 117 lines, not 95.** `## Decisions` held 95. The other **22 were filed under `## Status`**, between the table and the backlog: dated entries in ledger format, several carrying `[landed]` tags. They are ledger, so they went to `docs/DECISIONS.md`, kept in the order they appeared, under a one-line italic note saying where they had been. That is a deviation from a literal reading of §B, which describes `## Decisions` as the thing being moved. Leaving them behind would have left 22 rulings in a section that no longer has any.

## 2 · Line and word count

| | Lines | Words |
|---|---|---|
| Before | 370 | 12,809 |
| After | **178** | **3,495** |

Under the 180-line criterion. Every §C section is still inline; the six Architecture rules and the author-identity paragraph are byte-identical.

**Where the lines went.** 143 to `docs/DECISIONS.md`, 38 to `docs/STATUS.md`, 34 deleted with the `architect/next` mechanism, and the rest to reflowing. Several sections — the old git section, multi-tenancy, the stored-field rule — were hard-wrapped at about 70 columns while the rest of the file used one line per paragraph. Reflowing them to match cost nothing and recovered roughly 25 lines. Two near-identical `docker compose` fences became one, with the test flags described as flags to append.

## 3 · §D — what else went

- **The `architect/next` branch and the `git reset --hard` note**, as instructed. 34 lines describing a condition that can no longer occur.
- **An italic changelog line** at the head of `## Stack & environment`: *"Corrected against this machine on 2026-09-05 (handoff 01)… this section said 15 and every command in it was wrong."* A note about a repair five handoffs old. The repair is in the text.
- **"Odoo 15 remains the deployed production runtime; nothing on this machine runs it any more."** No longer true of the first half — see §4.
- **The `.env.example` / `odoo` paragraph**, from four sentences to one plus a pointer, **because the two files disagreed about the error.** `CLAUDE.md` said a `psycopg2` unix-socket error and *"Skipping database odoo as its base version is not 19.0.1.3"*; `docs/ENVIRONMENT-FACTS.md` says `operator does not exist: character varying ->> unknown` followed by `Failed to load registry`. Both cannot be the message. `CLAUDE.md` now says the error names nothing relevant and points at the other file for the text.
- **The skip count.** `CLAUDE.md` said "~24 admin-scoped tests skip"; `ENVIRONMENT-FACTS.md` says 27 and explains the second cause (pagination tests that skip when a tenant fits inside the record cap). `CLAUDE.md` now points instead of carrying a second, staler number.
- **One of two owner-preference bullets.** "Explain in plain English what happened first" and "Explain in plain language first, code second" are the same instruction; the second is now a clause of the first.
- **The three-row ecosystem table**, to three clauses of prose. Same content, four fewer lines.
- **The struck-through closed backlog item**, as instructed. The three open items are intact.

**One correction inside a section §B told me to keep.** The backlog cited `utils.py:830` as holding the query-parameter primitive. Line 830 is now `TRUNCATION_REASON`, from handoff 12's record-cap work; the primitive is `_selection_allowed_values` at line 1178. The backlog is kept precisely because a Builder could walk into that item this week, and it was pointing them at the wrong code. Now cited by name.

## 4 · §D — the contradictions, and yes it had drifted back

**It had.** `## What this is` still read *"built on **Odoo 15** … An Odoo 19 migration is in flight (`crnd-19/`, `oca-19/`, `docker-compose.19.yml`, `chore/retire-15-stack`); treat 15 as production until that lands"* — eleven lines above a `## Stack & environment` section that opened *"Runtime: Odoo 19.0"*, and a status row reading *"Odoo 19 migration | in flight, separate track"*. Report 01 corrected the stack section and left the opening paragraph alone.

Measured rather than assumed:

- **CI** runs the 19 stack only, and its own comment says the 15 stack can no longer build the 19-only `myservice_request_core`.
- **The cluster** has no Odoo 15 manifest at all. Every file in `k8s/dev/` is 19.
- **`chore/retire-15-stack`**, cited as evidence the migration is in flight, has **no commits of its own**: `git log dev..chore/retire-15-stack` is empty.

So the migration has landed on every runtime and what is left is retiring the 15 *files*. `CLAUDE.md` now says that, and `docs/STATUS.md` records the stale row as a correction rather than editing the moved row.

**A second factual error, wrong in both places it could matter: the stack is PostgreSQL 13, not 15.** `docker-compose.yml` pins `postgres:13`, the 19 overlay does not override it, `k8s/dev/30-postgres-statefulset.yaml` pins `postgres:13`, and the running container answers `PostgreSQL 13.23`. Corrected.

**The status table had stopped at handoff 14.** Handoffs **07, 11, 15, 16 and 17** all landed and have reports, and none ever got a row. The condensed table now carries all five, each summarised from that handoff's own report. This is the one place I added rather than moved, so it is the place to check me.

## 5 · Kept because I was unsure — the list you asked for

**Three near-duplicate pairs in the ledger.** Same ruling entered twice, in every case with the same landing commit. §B said verbatim, so all six lines moved. Correcting a `[landed]` entry is yours, not mine:

- *"Tag capture before tag transport"* and *"Tag capture is built before tag transport"*, both 2026-09-05.
- *"`/report/pdf/<...>` resolves its second segment against `report_name`, not the action xmlid"* and *"`print-url` built its path from the report action's xmlid, not its `report_name`"*, both `[landed 82da6ab]`.
- *"`/auth/login` no longer grants `["*"]`"* and *"`/auth/login` derives scopes from Odoo groups"*, both `[landed b8b6f64]`.

**A ledger entry that report 16 already withdrew, and I left standing.** The handoff 10 R46 entry says the Security Command Center and the barcode station's client action *"are DEAD on Odoo 19"* because they require `web.AbstractAction`, which does not exist there. `docs/ENVIRONMENT-FACTS.md` says the opposite — `myservice_nrs_base` ships a legacy shim, so those modules do load — and report 16 proved it in a real browser, mounting all four dashboards with zero console errors and explicitly withdrawing report 15 §6.1. **The ledger now carries a `[landed]` decision that is known to be false.** It needs a correcting entry from you; I would not write one over your ruling in a documentation handoff.

**`cadra19` is first in the fan-out loop and `ENVIRONMENT-FACTS.md` says its filestore is broken and unusable for anything browser-based.** The loop is command-line only, so it is not wrong. But `CLAUDE.md` lists `cadra19` among the local databases with no warning, and a Builder who picks the first name in the list for a browser check will lose time. A clause would fix it. I did not add one because I do not know whether the filestore has since been repaired.

**The `_sql_constraints` section still says to keep the legacy list behind an `_ODOO_MAJOR` guard "in our own modules only (the 15 stack still loads them)".** With the 15 stack retired on every runtime, the parenthetical is arguably obsolete and the guard arguably unnecessary. The guard is still *correct* and `tests/test_source_guards.py` enforces it, so removing the reasoning would leave a rule with no stated cause. Kept verbatim; it becomes a real question when `dist/` goes.

**The Architect's address, `claude-fc [01f312]`.** Kept. I have no way to confirm from here that it is current.

**`nrs19` is "the working tenant for integration and demo work"** in the ledger, while the Stack section sends every test command at `jaizbankplc`. Not a contradiction — `jaizbankplc` is the only tenant with a usable `CLIENT_ID`/`CLIENT_SECRET` pair, which I confirmed (`docs/api/.creds.jaizbankplc` and `.creds.nrs19` are the only two, and the `nrs19` one holds the demo's scoped clients). It reads like one to somebody new. Left alone.

## 6 · What was run

No Python changed, so per the handoff I ran the source guards only:

```
$ tests/.venv/bin/python -m pytest tests/test_source_guards.py -q
........................................................................ [ 66%]
....................................                                     [100%]
108 passed in 2.02s
```

**108 of 108.** Denominator quoted, per the rule; no `of 0 tests`, no `CRITICAL`, and the run left no tracked file dirty.

## Acceptance

| Criterion | Result |
|---|---|
| `CLAUDE.md` under 180 lines | 178 |
| Every §C section still inline | all 13 present; Architecture rules and author identity byte-identical |
| Both moves complete and byte-identical | 117/117 and 19/19, diffs empty |
| New git rule in, `architect/next` out | 0 occurrences of `architect/next` or `git reset --hard` |
| Step 0 was the new rule working | yes — `952bc76` |
| Backlog keeps open items, loses the closed one | 3 open, 0 struck-through |
| No Python changed · source guards green | 0 files · 108 of 108 |

## Open questions

1. **The withdrawn R46 ledger entry** (§5). It says two dashboards are dead on Odoo 19; report 16 proved they mount. Yours to correct.
2. **The three duplicate ledger pairs** (§5). Merge or leave?
3. **The five status rows I wrote** for handoffs 07, 11, 15, 16 and 17, summarised from their reports. Worth a glance.
4. **`cadra19`'s filestore** (§5) — still broken? If so `CLAUDE.md` should say so where it lists the tenant.
