# Report 24 — The record starts now

**Branch:** `feat/access-record` · **Base:** `dev` (report 23's work was merged as PR #69 before this started, so §A's fallback branch was not needed).

**Needs the owner:** the PR merge, and **`scripts/mark_test_fixtures.py`** — see §3. The Builder's permission layer refused a committing write to a client-derived tenant, which is the correct refusal and is why that step is a script rather than a done thing.

---

## 1 · Every writer of group membership, and which ones the record covers

**The handoff's list was wrong in three places, and my own first pass was wrong in two more.** Both matter, so both are here.

### The three the handoff got wrong — all verified against Odoo 19 core, not assumed

**Group implication writes nothing.** `res.groups.all_implied_ids` is declared `compute='_compute_all_implied_ids'` with **no `store=True`**, and `res.users.all_group_ids` is computed from it at read time. On Odoo 15 the transitive closure was materialised into the membership table; on 19 it is not. So adding an implication grants every member of a group the rights of another group **while writing zero rows to `res_groups_users_rel`**. The handoff asked for "the implied rows an auditor will ask about" — there are none. There is only an implication edge, and it is recorded here as its own event because it moves what a group *means* rather than who is in it.

**`res.config.settings` group toggles are that case, not membership.** `_apply_group` / `_remove_group` write `implied_ids` on `res.groups` and never touch `res.users` at all.

**Reified group fields are gone.** No `sel_groups_*`, no `in_group_*`, no `_remove_reified_groups` anywhere in 19 core. The admin user form submits the real `group_ids` field as a single `(6, 0, ids)` command, so an ORM override *does* catch the UI — the concern as written no longer applies.

### The six writers, and whether a `res.users.write` override would have caught each

| # | Writer | Caught by a `write` override? | Covered now |
|---|---|---|---|
| 1 | `res.users.write` with `group_ids` — including the admin form | yes | yes |
| 2 | `res.users.create` — seed scripts, the API-client provisioner, `auth_signup`'s template `copy()`, and `_default_groups()` putting a user in a group the create never mentioned | **no** | yes |
| 3 | `res.groups.write` with `user_ids` — `scripts/bootstrap.py` and eight security XML files that re-apply on **every** module upgrade | **no** | yes |
| 4 | `res.groups.write` with `implied_ids` — and every settings toggle | **no** | yes |
| 5 | `res.users.unlink` — `ON DELETE CASCADE` erases every membership row | **no** | yes |
| 6 | `res.groups.create` populated in one shot, and `res.groups.unlink` | **no** | yes |

**A `res.users.write` override alone — which is what INT-10 §2.10b recommended — would have recorded one of six.** That recommendation is now marked superseded in INT-10 §2.10c with this table under it, so the next person to propose the cheap option meets the measurement rather than the conclusion.

### The part I got wrong, which is the part worth reading

**I wrote a docstring claiming the list was exhaustive at four, in the file that warns against exactly that, and a review found two more.** `myservice_security/security/security_groups.xml` declares `group_security_admin` with **both** `implied_ids` and `user_ids` on the record — so on a cold install the group arrives populated through `res.groups.create` and never passes through `write`. And `ON DELETE CASCADE` sits on *both* foreign keys of the relation, so deleting a group erases membership exactly as deleting a user does.

CLAUDE.md says a claim of exclusivity is a guess unless a search backs it. I searched the writers the handoff named and then asserted completeness over a set I had not re-searched after designing around it. The docstring now records that the list has been wrong twice and says to treat a seventh as likely rather than impossible.

**Not covered, and stated in the code rather than implied:** raw SQL against the relation table, and a direct `call_kw` from any client with RPC access. Both converge on the ORM m2m flush, so only a database trigger would catch them — and a trigger would still not see writer 4, which never touches that table.

### The three properties the handoff asked for

1. **A change nobody can attribute says so.** `uid 1` is an upgrade, a cron or the CLI: the row carries `actor = '__system__'`, `attributable = false`, no `changed_by_id`. A real person's change carries their name *and* their login, so the actor survives account deletion as well as the subject does.
2. **The record knows when it begins, per tenant, by measurement.** `fidelity.record_starts_at` is read from the earliest row held, at request time — `null` until the first change is recorded, and never a migration date.
3. **It is a record, not a mechanism.** No hook refuses or alters a write. Deleting the recorder file would leave every access decision in this system exactly as it is.

---

## 2 · The start instant per tenant, and what surprised me

**All eight tenants: `record_starts_at = null`, 0 rows.**

| Tenant | Rows | Starts at |
|---|---|---|
| `cadra19` `nrs19` `gtb19` `test19` `nrs` `lasg` `gtb` `jaizbankplc` | 0 | *(not yet begun)* |

That is the honest state and the report says so in words rather than implying it: *"This tenant holds NO access-change rows, so the record has not begun here and no period can be answered for group grants or removals. The recorder is installed and will write the first row the next time membership changes."*

**What surprised me — and it is the good kind.** I expected the fan-out itself to fill the record with noise. Eight security XML files re-apply `user_ids` links on **every** module upgrade, and two full fan-outs across eight tenants each ran those. **They produced zero rows.**

That is the diffing design paying off. The hooks snapshot real membership before and after and compare; a `Command.link` on a row that already exists changes nothing, so it records nothing. Had the hooks parsed `vals` instead — the obvious implementation — every tenant would now carry a few dozen fabricated `granted` rows attributed to `__system__`, on an append-only model, permanently, from the upgrade that installed it.

Both fan-outs: 8 of 8 tenants, `Modules loaded`, **0 CRITICAL, 0 ERROR**. The second was required because the review added a column (`changed_by_login`).

### Proved by acting, not by reading

All three coverage states, on `test19` under rollback:

| Requested period | `coverage` | Group changes |
|---|---|---|
| Ends **before** the record began | `none` | 0 — *"…begins at 2026-06-15, which is AFTER the end of the period you asked about"* |
| **Straddles** the start | `partial` | 1 — published as a **lower bound** |
| **Wholly inside** | `recorded` | 1 — complete |

The first is the one the handoff called out as the auditor's question for the next twelve months. It has its own test class.

**I deliberately did not exercise the record against `jaizbankplc`** beyond a read. Writing membership changes there to demonstrate the feature would have added permanent append-only rows to a client-derived register — which is the defect §3 exists to report.

---

## 3 · What a test run writes, and where

**This is the finding, and the Architect was right to ask for it first.**

The HTTP suite writes into **`jaizbankplc`**, a replica of a live client's register, because `CADRA_API_BASE` is the only thing choosing the target and the only tenant carrying a full `CLIENT_ID`/`CLIENT_SECRET` pair is that one. `.creds.nrs19` holds two scoped clients and fails the fixture's own check.

**There is no guard of any kind** — no allowlist, no refusal, no confirmation, no dry run. The suite reads one environment variable and writes wherever it points. Its only refusal is the opposite control: it declines to *guess* which credential to use, which protects the suite from a 401, not a tenant from the suite.

**And it has no teardown, by documented policy** (`tests/README.md`: *"leave them in the dev DB"*) — and could not have one: the API publishes exactly one `DELETE` route, for asset categories. There is none for assets, locations, requests, custody links or disposals.

Measured 2026-09-15, after ~154 sessions accumulating since 2026-08-26:

| | |
|---|---|
| assets named `pytest-*` | **3,584 of 4,056 (88%)** |
| chain-of-custody rows on fixture assets | **413 of 569 (73%)** |
| entries in the **public homepage** location dropdown | **354 of 420 (84%)** |
| fabricated approved disposals in the auditor-facing report | **6** (report 23 disclosed 1) |

**What it is not.** Nothing ever reached the production host — every captured response in `docs/api/test-responses/` names `jaizbankplc.localhost:8069`. No *real* asset carries a fabricated approval or custody link. CI is unaffected: it builds its own throwaway `odoo` database on a runner that is discarded.

**The repo already has the right pattern and it works.** `myservice.api.client.is_test_credential` drives `nrs.asset.custody.source = 'test'`, and the custody chain is honest because of it — **330 of its rows self-label**. The hole is that the `Handoff23 Approver` credential was created with the flag *off*, so the six approvals it authorised are the one class of artefact a reader cannot identify from the record itself.

### Asset 8396

**Disposal approval is not reversible, and that is deliberate.** There is no `action_unapprove_disposal`, a second approval is a published 409, the approver fields are read-only over the API, and the button hides itself once an approver exists. It is correctable only by a human on the Odoo form, where `disposal_approved_by` is tracked — which is the design `asset_disposal.py` argues for: *"a genuine correction is made on the form and leaves a trail; a button that quietly replaces one name with another does not."*

So it is **marked, not un-approved.** Fabricating a reversal would be the same defect as the fabricated approval, one step on.

**`scripts/mark_test_fixtures.py` is owner-run.** It sets the credential flag and appends a disclosure to each fabricated disposal's reason so the auditor-facing report shows them for what they are. I could not run it: the permission layer refused a committing write to a client-derived tenant. **That refusal is correct** and I did not work around it. The script is idempotent.

**Recommended, not built:** a guard refusing to run the suite against a tenant not marked as a test tenant. I did not add one because CI runs with no `CADRA_API_BASE` at all and falls through to its own database, so a guard written carelessly breaks CI — and the handoff called this section secondary to the measurement. It needs a ruling on what marks a tenant safe.

---

## 4 · §D — a sentence, not a group

**`finance_viewer` is `group_auditor` under another name.** The deliverable is a line in INT-10 §4.3, and it is written.

"Asset financial data" resolves to four blocks of the asset serializer — `financial` (including the whole `depreciation` sub-block), `sap`, `disposal`, `provenance` — plus `GET /reports/depreciation` and `GET /settings/depreciation`. Every one is reached by `assets:read`, `dashboards:read` or `settings:read`, and `group_auditor` grants all three.

**The reason it cannot be anything else is structural, and I verified all three legs myself:**

- `grep -rn "groups=" --include="*.py"` across every first-party module returns **nothing**. No field is gated.
- `serialize_asset` has the signature `def serialize_asset(a, *, include=())` — **no scope argument**. `include` is an additive embed selector the *caller* chooses, and the four financial blocks are emitted unconditionally.
- Every route runs `.sudo()`, so an Odoo group cannot subtract from a scope.

The finest cut the platform can make is **route × scope**, and financial fields are not a route — they are nested blocks riding on `assets:read`, which is indivisible. A `finance_viewer` built honestly today would be `group_auditor` minus `locations:read`, `requests:read` and `identity:read` — **a narrower auditor, not a finance role**, since not one of those three is financial.

Two things flagged rather than closed: specification §3.4/§3.5 cast Finance as a disposal **approver** (`approvals:write`, the opposite of this row, and handoff 23 built that route); and `workflow_payment_ref` is stored and serialised by nothing, so a Finance Officer tracing a payment reference over the API cannot — nor can an auditor.

---

## 5 · §C — the decision log

**Ten corrections across seven entries**, each keeping the original claim visible as withdrawn.

| Entry | Verdict |
|---|---|
| Security Command Center / barcode station "DEAD on Odoo 19" | **Withdrawn.** Report 16 mounted the barcode station in a real Chromium at 47,362 bytes, 0 console errors. The *mechanism* is false for both: `legacy_compat.js` re-provides `AbstractAction` and `rpc` as OWL shims. The security screens are retired — but by commit `17aba57`, four months earlier. |
| `has_coordinates` partition | **Withdrawn.** Coordinates are NULL, never `0.0`, so `false` answered 0 where 250 of 380 sites are unmapped — and the test cited as proof was capped at one page and never ran on `/assets`. |
| External record cap (×2) | **Reason corrected.** "Commercial control"/"partner paywall" is shared-cluster reasoning on a single-tenant product; the ruling stands, the justification is now rate limiting. |
| `request.jsonrequest` guard | **Reason corrected.** It cited "the 15 stack is still the `prod` compose profile" — handoff 20 deleted that stack. The same stale sentence was live in `tests/test_source_guards.py` and is fixed there too. |
| `dist/` constraints "are correct" (×2) | **Reason corrected.** Unreached now, not correct; conclusion unchanged. |
| Two `[ruled — not built]` tags | **Annotated** with where the work actually landed. |
| `.gitlab-ci.yml` guard | **Annotated** — the deletion landed, but "a guard now covers CI configuration" was untrue until handoff 23 repaired it. |

**Nothing beyond these.** `Vendra Auditor` never entered the ledger — the only mention is report 23's own correction. No standing "only writer" claim survives uncorrected. Entries `:205`–`:228` hold.

**One thing I had to fix in my own work:** my corrections cited DECISIONS.md *line numbers*, and inserting them moved every line below. All cross-references are now dates and claims. A decision log whose corrections rot is the instrument this handoff is about.

Also corrected: the stale structural-zero claim in the route docstring, INT-10 §2.10 and `docs/api/CHANGELOG.md`. `docs/DECISIONS.md:194` is handoff 23's own entry and was true when written; the handoff 24 entries supersede it.

---

## 6 · Suites, in CI's order

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) | **772 passed, 32 skipped, 0 failed** |
| In-registry, CI's 11 modules, `jaizbankplc` | **0 failed, 0 error(s) of 516 tests** |
| `myservice_api` alone, `test19` | **0 failed, 0 error(s) of 190 tests** |

**The `myservice_api` denominator moved 126 → 190.** That is the check, not the exit code: report 23 found a test file that was written, never registered, and reported "0 failed" while running nothing. 46 new tests in `test_access_change_record.py` plus the rewritten group-change and coverage classes account for it.

All 32 skips are named and none is from a file this handoff touched: 21 admin-scope, 3 partition-data-absent, 2 Turnstile-not-configured, 1 no SAP asset number, 1 no active `workflow.config`, plus the documented `is_tagged` case.

**One thing that looks like a failure and is not.** The in-registry run logs `ERROR: cannot execute INSERT in a read-only transaction` nineteen times. They are Odoo 19's own readonly-first cursor policy — the next line is always *"retrying with a read/write cursor"*, and the request then returns 200. They come from `myservice_api_refresh_token` and `mail_message` inserts in handoff 23's `HttpCase`, not from this work, and the denominator is 516 rather than 0.

---

## 7 · Wall-clock and the correction share

**Roughly 2h10m.** Five parallel read-only investigations up front (~8 min wall, run concurrently) — the writer enumeration, the custody/report blueprint, the DECISIONS sweep, the `finance_viewer` question and the test-residue trace — then the build serialised against a stack that cannot take two registry loads at once.

**Correction share: about 35%.** Two full eight-tenant fan-outs rather than one, because the review added a column. Two writers found after I had claimed the list was complete. Ten decision-log corrections, then a second pass over those to replace the line numbers my own edits had invalidated. The status table needed fixing because I inserted handoff 24 in the wrong place and duplicated handoff 23's row.

**The most valuable 20 minutes was the writer enumeration before any code.** It changed the design three times before a line was written — and the fourth change, the two writers it did not catch, came from a review afterwards. The lesson is not that the search was wrong; it is that I stopped searching once I had a design and then wrote "exhaustive" over it.

---

## 8 · Open, and not mine to close

- **`scripts/mark_test_fixtures.py` needs the owner.** Permission layer refuses a committing write to a client-derived tenant.
- **No guard stops the suite writing into a tenant with real data.** Needs a ruling on what marks a tenant safe; a careless guard breaks CI.
- **The reconstruction of pre-record grants** is unchanged and still NRS's decision (INT-10 §2.10b). What changed is that the unrecoverable period stopped growing.
- **`workflow_payment_ref` is serialised by nothing** — invisible to every role including the auditor.
- **The CI-series guard ruling** from report 22 is still open; untouched here.
