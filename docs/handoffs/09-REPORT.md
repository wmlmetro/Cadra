# Handoff 09 — Report

**Branch:** `fix/stale-computes` → PR into `dev`. **Base:** `dev` at `1826817`.

**Both suites green.** Odoo-native: **119 tests, 0 failures, exit 0**. pytest API
suite: **250 passed, 27 skipped**. 42 files, +2,261 / −98, 15 new files, one
deleted.

**The headline result is one nobody had to make happen.** The `sla_breached`
cron installed on `jaizbankplc` at 23:15 and fired at **23:16:37**, unattended,
via the scheduler handoff 08 revived — flipping 215 requests that had been
sitting past their deadline unflagged. Nothing invoked it. The same happened on
all eight tenants within seconds of each upgrade. Handoff 08 proved the
scheduler runs; this is the first work that simply *assumed* it and was right.

---

## Needs the owner

1. **Merge the PR** (standing — the permission layer refuses `gh pr merge`).
2. **R27's cluster half does not apply on merge, and this is the one item with
   a third party on the other end.** Two separate actions, both manual:
   - **`publisher_warranty_url`**: the ConfigMap is mounted with `subPath`
     (`k8s/dev/41-odoo-19-deployment.yaml:70-74`), which Kubernetes excludes
     from ConfigMap update propagation, and the only step that rolls `odoo-19`
     is `workflow_dispatch`-gated (`deploy-dev.yml:216`). **Run `deploy-dev`
     manually with `roll_odoo` enabled.** Until that runs, the cluster keeps
     POSTing weekly.
   - **The cron rows**: **run the `upgrade-19` workflow** with
     `upgrade_modules = myservice_nrs_base` and `target_dbs` = *every* tenant.
     That is what carries the per-tenant deactivation.
3. **Run the `upgrade-19` workflow for EVERY tenant with `myservice_asset_register`
   — at or before the image roll, not after.** `nrs.asset.category.verification_interval_days`
   is a new stored column, and `_compute_verified` reads it on every
   `nrs.asset` create/write. That is **Vendra's write path, `POST /api/v1/assets`
   (INT-03)**. On an un-upgraded tenant it raises `UndefinedColumn` and the
   endpoint 500s. This is not theoretical — it happened here mid-handoff, with
   the Python landed and no database upgraded, and it 500'd every call to
   `GET /api/v1/assets` until the fan-out finished. One Odoo registry serves
   every tenant, so a tenant left behind breaks the moment the image rolls
   forward.

4. **R25 is still unanswered and I still cannot answer it.** `kubectl` has no
   context on this machine. Nobody has yet observed a cron running in the
   cluster. `select cron_name, lastcall from ir_cron where cron_name ilike
   '%epreciat%';` on a staging tenant.
5. **Rotate the `test_client` secret** (standing).

---

## R24 and R25 — accepted, and one of them got worse

R24 accepted. R25 unchanged: I could not reach the cluster and did not pretend
to. Everything below about the cluster is read from manifests, not observed.

That gap now matters more than it did. Agent-verified finding in
`myservice_asset_register/migrations/19.0.1.10.0/post-migrate.py`: **the
migration handoff 08 shipped would have deleted the crons this handoff
installs.** It deletes `cron_asset_pm_refresh_overdue` and
`cron_asset_refresh_verification` by xmlid, unconditionally, and Odoo runs
post-migrate *after* the module's data files load and runs **every** script
whose version is above the installed one. A database below `19.0.1.10.0`
upgraded straight to `19.0.1.11.0` would load the new cron records and then
have the old script delete them — silently restoring exactly the state handoff
08 found. All eight local tenants sit at `19.0.1.10.0` and are safe. **The
cluster's module version is unverified**, which is precisely the case this
guards. The script now skips the deletion when the method it names exists.

---

## A · The telemetry is stopped

**Locally: zero active telemetry or digest crons on all eight tenants**, and the
upgrade log shows the mechanism working per database rather than being asserted:

```
INFO cadra19 ...ir_cron: deactivated scheduled action digest.ir_cron_digest_scheduler_action (Digest Emails)
INFO cadra19 ...ir_cron: already inactive, left alone: mail.ir_cron_module_update_notification
```

"already inactive" on the publisher cron is handoff 08's work being found
rather than redone — the method does not write to a cron that is already off,
so a repeat upgrade produces no write and no log line claiming work it did not
do.

Two layers, mirroring the local fix:

1. `publisher_warranty_url = http://localhost:1/publisher-warranty/` in
   `k8s/dev/10-configmap-odoo-19.yaml`. The durable half: it covers tenants that
   do not exist yet and holds whatever any `ir_cron` row says.
2. `myservice_nrs_base` deactivates both crons by xmlid, tolerating absence.
   Reached by **two** entry points because neither substitutes for the other —
   `post_init_hook` for a fresh tenant (an install runs no migration scripts)
   and `migrations/19.0.1.1.0/post-migrate.py` for existing ones (an upgrade
   runs no `post_init_hook`).

The digest cron rides along, per R27.

**Honest limitation, stated in the code rather than discovered later:** if
someone installs `digest` *after* this runs, the row comes back. For the
telemetry cron that is survivable because layer 1 is config, not data. For
digest there is no layer 1 — an upgrade of `myservice_nrs_base` is the remedy.

**Two corrections to my own report 08 while here.** `config/odoo.19.conf`
carried a comment saying the cluster decision "is the owner's, not this file's."
R27 made that decision; the comment now says what was decided and what it takes
to apply. And editing that file broke its bind mount exactly as `CLAUDE.md`
warns — `/etc/odoo/odoo.conf` vanished from the container until
`up -d --force-recreate odoo`. The warning is correct and I still walked into it.

---

## B · The stale stored computes — five, not three

The handoff named three. An AST audit of every stored compute in our modules
whose body reads the clock found **five**. That audit is also the answer to
report question 2, so it is written up there; the two extras are here because
they were fixed.

| Field | Module | Shape of the defect | Rows wrong before |
|---|---|---|---|
| `request.request.sla_breached` | `request_fields` | false on every request that was created inside its own SLA window — i.e. all of them | **303** estate-wide |
| `nrs.asset.is_verified` | `asset_register` | could only move false → true; "verified once, at an unknown time" | 0 (1 true, recent) |
| `nrs.asset.pm.is_overdue` | `asset_register` | backs an "Overdue PM" menu that is empty for ever | 0 (no PM rows exist) |
| `security.guard.on_duty` | `security` | **`@api.depends()` was EMPTY** — computed at creation, never again | 0 (no guards exist) |
| `fleet.vehicle.maintenance_status` | `fleet_maintenance` | a stored **Selection returning a wrong enum value**, not merely a false boolean | 0 (all `no_schedule`) |

### Live proof, per tenant, unattended

`lastcall` for the five refresh crons after the fan-out — every one ran by
itself, within seconds of its tenant's upgrade:

```
TENANT       reqs   past   FLAGGED  verif  lastcall of the 5 refresh crons
cadra19      80     80     80       0      22:56:01 22:56:02 22:56:02 22:56:02 22:55:27
nrs19        0      0      0        0      22:59:14 22:59:20 22:59:21 22:59:23 22:59:25
gtb19        8      8      8        0      23:02:13 23:02:47 23:03:04 23:03:05 23:03:05
test19       0      0      0        0      23:06:18 23:06:44 23:06:44 23:06:44 23:06:45
nrs          0      0      0        0      23:11:14 23:11:14 23:11:14 23:10:54 23:11:14
gtb          0      0      0        0      23:13:36 23:13:50 23:13:50 23:13:51 23:13:52
lasg         0      0      0        0      23:15:04 23:15:06 23:15:06 23:15:06 23:15:06
jaizbankplc  233    215    215      1      23:16:39 23:16:39 23:16:21 23:16:37 23:16:38
```

**`jaizbankplc` `sla_breached`: 215 of 215 → 215 of 215.** Before, measured at
the start of this session: 233 requests, 233 with a deadline, **215 past it,
0 flagged, all 215 open**. After: **215 flagged.** The acceptance line asked for
before and after; the interesting part is that the "after" was produced by the
scheduler, not by me.

And the per-tenant cron/telemetry verification table:

```
TENANT        sla  verif ovrdu on_duty maint  TELEM_ACTIVE  column_exists
cadra19       1    1     1     1       1      0             1
nrs19         1    1     1     1       1      0             1
gtb19         1    1     1     1       1      0             1
test19        1    1     1     1       1      0             1
nrs           1    1     1     1       1      0             1
gtb           1    1     1     1       1      0             1
lasg          1    1     1     1       1      0             1
jaizbankplc   1    1     1     1       1      0             1
```

### One pattern for all five, and why it is not the obvious one

Two agents independently arrived at different mechanisms. The stronger one was
adopted for all five:

```python
batch.fetch(['is_verified'])                  # 1
self.env.add_to_compute(field, batch)         # 2
self.env.flush_all()                          # 3
if not in_test:
    self.env.cr.commit()                      # 4
```

1. **Prefetch, or the sweep rewrites everything.** A recompute writes only when
   the value differs from **cache**, and `_filter_not_equal` treats *absent from
   cache* as different. Without this, the daily pass UPDATEs every row it looks
   at and — since `_write_multi` stamps `write_uid`/`write_date` even on the
   compute-flush path — relabels every one of them as last modified by OdooBot
   to say that nothing changed.
2. **Mark the FIELD, not a dependency of it.** The obvious spelling,
   `batch.modified(['last_verified_date'])`, works today and routes through the
   dependency graph — the graph that by definition does not contain the clock.
   It becomes a silent no-op the day someone edits `@api.depends`, which is the
   exact class of bug the cron exists to compensate for.
3. **Flush per batch or the batching is decorative** — every id would otherwise
   sit pending until the transaction's own commit, which is the one thing the
   batches exist to avoid.
4. Commit per batch, never under test, as the depreciation cron does.

### `is_verified` (R29)

Per-category window (`nrs.asset.category.verification_interval_days`) → tenant
parameter (`cadra.assets.verification_interval_days`) → 365 days.
`@api.depends` gained the category path so tightening a category bites
immediately rather than at the next tick.

**A correction to R29: it is true on one asset, not zero.** Measured across all
eight databases — 17,123 assets, exactly one `is_verified`, on `jaizbankplc`,
the only asset in the estate with a `last_verified_date` at all, and recent
enough not to move under any of these windows. So the ruling's conclusion holds
and nothing flips; the count was off by one and the one is the owner's own
verification.

The new column is a stored field, so it went out as a multi-tenant migration.
It also announced itself the documented way: with the Python landed and no
database upgraded, `GET /api/v1/assets` returned **500 on every call** —
`column nrs_asset_category.verification_interval_days does not exist`. That is
`CLAUDE.md`'s rule reproducing itself exactly, mid-handoff.

### `is_overdue` — preventive, not corrective

The handoff says it "backs a live 'Overdue PM' menu that returns empty for
ever". True, and the menu is empty for a second reason the handoff did not
know: **there are zero `nrs.asset.pm` rows on every tenant.** There is no
before/after count to quote because there is nothing to correct. The first
tenant to create a PM schedule would have hit it.

---

## C · The guards

**`odoo.conf` deleted, and the exception with it (R30).** Verified nothing reads
it: `install.sh` writes `/etc/odoo/odoo.conf` from its own heredoc, every
container mounts something under `config/`, and the file has not been touched
since the initial commit. The `db_name` guard now has **no exceptions**, and the
self-test that used to assert the file was waved through now asserts it is
caught. A new guard asserts the file stays gone — because an exception matched
on a filename cannot tell a dead file from a live one that later takes its name.

**The in-registry cron guard (R31), proven to fail.** Renaming the *method*
behind a real cron while leaving its XML alone:

```
FAIL: TestScheduledActions.test_every_scheduled_action_in_this_database_resolves
  - Cadra: refresh SLA breach flags (id=27, xmlid=myservice_request_fields.cron_request_sla_breached):
    model request.request has no attribute '_cron_refresh_sla_breached'
    (called as model._cron_refresh_sla_breached())
ODOO EXIT CODE = 1
```

Named the cron, its xmlid, its model and the missing method — and **Odoo exited
1**, which independently re-confirms report 08's claim that the CI step gates
rather than decorates. Restored: exit 0.

Design notes worth keeping: it uses `ast.parse` and never `eval` (running a cron
body to see whether it resolves would POST events to Vendra and write to eight
tenants); it steps through chained calls so `model.sudo()._foo()` resolves
rather than being written off; it counts what it resolved and asserts that count
is non-zero, so it cannot pass by checking nothing; and it checks **inactive**
crons too, because Odoo's own scheduler deactivates a cron after repeated
failure — `active=False` is where a broken cron *lands*, not proof it is
harmless.

**CI** now runs the Odoo-native suites for five more modules.

---

## R26, and a bigger thing behind it

**The three `myservice.dashboard` routes `sudo()`.** Session-token semantics
change as ruled — a Security Officer with `dashboards:read` but no fleet group
used to get an error and now gets data — and it is in the changelog as a
behaviour change. `SCOPE_GROUPS` keeps deriving the groups from the scope as the
belt to those braces.

**But the 400 was not the dashboards' fault, and fixing only them would have
left the real defect in place.** In Odoo 19:

```
AccessError.__mro__     -> AccessError, UserError, Exception
MissingError.__mro__    -> MissingError, UserError, Exception
ValidationError.__mro__ -> ValidationError, UserError, Exception
```

All three subclass `UserError`. `cadra_route` caught `(UserError,
ValidationError)` **first**, so the `AccessError` and `MissingError` clauses
below it were dead code — for every route, not just the dashboards. **Two
published error codes, `forbidden` (403) and `not_found` (404), were unreachable
through that path for the entire life of the envelope.** Vendra branches on
`error.code`; an authorisation failure reporting itself as `validation_failed`
tells an integrator to fix their payload when the answer is to fix their
credentials.

Handlers reordered specific-first. Guarded by an AST test that reads the
**order** of handlers rather than grepping for names, proven to fail by
reverting the order:

```
E  myservice_api/controllers/utils.py:1081  `except AccessError` is unreachable — `UserError` was already caught on line 1073
E  myservice_api/controllers/utils.py:1084  `except MissingError` is unreachable — `UserError` was already caught on line 1073
```

**`docs/api/CHANGELOG.md` did not exist.** Two rulings said to announce a change
in it. For an API with a live external consumer since INT-03, the only record of
a behaviour change was a handoff report, which an integrator does not read. It
now exists, with the rule that anything Vendra could branch on belongs in it,
seeded with the three behaviour changes above.

---

## Deviations, and one piece of scope I added

1. **Two extra fields fixed** (`on_duty`, `maintenance_status`). R28 says "the
   whole stale-stored-compute class — this one," and these are that class. Both
   are latent (zero rows wrong today) and both are published. I applied R29's
   own reasoning: being true on zero rows is precisely what makes a published
   field safe to correct, *before* anyone relies on the wrong behaviour. **If
   you disagree, this is the piece to push back on** — it is two extra modules
   of review surface for zero present defect.
2. **`verification_interval_days` exposed on the settings API.** Its sibling
   `pm_interval_days` — same kind of setting, same screen — already is, so a
   per-category cadence settable only in the Odoo back office would make the
   Settings screen quietly incomplete. Additive; allow-list, serialiser, OpenAPI
   schemas and a test moved together, per rule 2.
3. **`migrations/19.0.1.10.0/post-migrate.py` edited** — §R25 above.
4. **`security.guard`'s compute split**, beyond the cron: `on_duty` (stored) and
   `active_duty_id` (not stored) shared one compute, so **reading the non-stored
   field wrote the stored column** — and in Odoo 19 `read()`/`search_read()` are
   `@api.readonly` and run on a readonly cursor. Separately,
   `_compute_duty_count` was declared `@api.depends('duty_count')`: a field
   depending on itself.
5. **The handoff's migration signature hint was wrong.** It suggested
   `migrate(env, version)`; Odoo 19 enforces `(cr, version)` via
   `VALID_MIGRATE_PARAMS` and raises `TypeError` otherwise. Every existing
   migration in the repo already uses `(cr, version)`.
6. **`docs/api/CHANGELOG.md` created** rather than appended to — it did not exist.

---

## Report question 1 — what `sla_breached` becoming true does to a live tenant

**303 requests light up estate-wide** (215 `jaizbankplc`, 80 `cadra19`, 8
`gtb19`). **Nothing fires. Nothing is notified.** Verified rather than reasoned:

- **It is not published.** `sla_breached` appears in exactly three files: the
  model and two view files. `myservice_api` never mentions `sla`; the SPA never
  mentions it. It is not on the request serialiser, so **Vendra and every other
  consumer see nothing** — this is not an API change.
- **No automation.** `base_automation` is *uninstalled* on all eight tenants.
  Zero `ir.act_server`, zero `ir.rule` and zero `ir.filters` reference the field;
  no mail template mentions an SLA breach. I queried for these rather than
  inferring from source.
- **No chatter, and one that would have mattered.** The field has no
  `tracking=True`, and more decisively the recompute reaches the database via
  `_flush` → `_write_multi`, so `BaseModel.write()` never runs: no `mail.thread`
  tracking, no `request.event` row, and **`myservice_workflow`'s `write()` stage
  hook `_check_workflow_auto_trigger` does not fire** — so 303 flipping rows
  cannot dispatch anything to the NRS WorkSpace. There is a test pinning that.

What does change, all in the Odoo backend:

1. The **"Overdue" menu** goes from permanently empty to 215 / 57 / 8 rows. A
   few hundred rows in a list view is nothing.
2. **The FM Triage Inbox on `jaizbankplc` turns entirely red** — `decoration-danger`
   on 215 of 233 rows. That is honest, and it destroys the decoration's contrast
   value on day one. Worth the owner seeing it coming rather than reporting it
   as a rendering bug.
3. A red **"SLA Breached — Escalate immediately"** banner on essentially every
   open request on that tenant.
4. **The kanban "Breached" badge suppresses the "Urgent" badge** — they are a
   `t-if`/`t-elif` chain. Cosmetic, but it is a visible regression in what the
   kanban communicates, caused by correcting the field.

**One audit side effect, and it is avoidable but not avoided for these 303.**
`_write_multi` stamps `write_uid`/`write_date` even on the compute-flush path,
so the first tick relabelled 303 requests as last modified by OdooBot. For rows
that genuinely changed that is unavoidable. The `fetch()` in the shared cron
pattern is what stops it recurring daily for rows that *don't* change — which is
the difference between a one-time stamp and 17,123 assets being rewritten every
night for ever.

## Report question 2 — is any other published field a clock-reading stored compute?

**Yes. Two, and both are published.** I answered this with an AST pass over
every stored compute in our modules, matching bodies that call `today()`,
`now()`, `context_today()` — rather than by grepping, which would have found the
three already known and stopped.

Seven hits. Three are the handoff's. One (`nrs.asset.pm.next_due_date`) shares a
compute with `is_overdue` and is covered by the same cron. One
(`nrs.employee.import.job.display_name`) reads the clock but depends on
`create_date` and is a label on an import job — no action. The remaining two are
real and were fixed:

- **`fleet.vehicle.maintenance_status`** — serialised as
  `data.maintenance_status` at `v1_fleet.py:77` and driving the fleet dashboard's
  OK / Due Soon / Overdue counts. Stored Selection reading `date.today()`; a
  vehicle whose service date passes stays `ok` for ever. **Worse than
  `is_overdue`**: it returns a *wrong enum value*, not merely a false boolean.
- **`security.guard.on_duty`** — counted by
  `myservice_security/controllers/main.py:25` behind `GET /api/v1/security/kpis`.
  Stored, and `@api.depends()` was **empty**: computed once at creation, when no
  roster exists, and never recomputed — not when a roster was added, not when
  one was cancelled, not when the day turned over. The purest instance of the
  bug in the codebase, and two defects rather than one.

Both are currently harmless — zero guards, zero roster rows, and every vehicle
`no_schedule` across all eight tenants — and both are now on the same pattern as
the other three.

**The generalisable answer to the question you asked: `is_verified` was not the
only one, and it was not the worst one.** The reason it was the one we knew about
is that it is serialised under a name that reads like a claim. `on_duty` is
serialised as a *count*, and a count of zero looks like an answer.

## Report question 3 — wall-clock

| | |
|---|---|
| Read the handoff, trace the code, measure the baseline | ~25 min |
| Build, four agents in parallel (telemetry+guard, asset_register, request_fields, security+fleet) | ~30 min wall, ~2h of agent time |
| Main session in parallel: guards, `odoo.conf`, R26, the exception reorder, changelog, CI | overlapped |
| **Per-tenant fan-out, first pass (8 tenants × 3 modules)** | **28 min** — the single longest item |
| Per-tenant fan-out, second pass | 8 min |
| Odoo-native suites (×3: fail, fix, re-prove) | ~12 min |
| pytest API suite (×2) | ~10 min |
| Docs, CLAUDE.md, report, verification pass | ~30 min |
| **Total** | **~2h 20m wall** |

**The fan-out is the bottleneck and it is not test time.** 28 minutes for the
first pass, of which `cadra19` alone took 5 minutes — and the work is eight
sequential full registry loads, not eight migrations. The three test runs that
actually found bugs took 12 minutes between them. If this cadence continues,
parallelising the fan-out across tenants is worth more than anything else here.

**Three tests failed on their first real run**, and that is the most useful
thing that happened. All three were "the flag stays stale without the cron"
negatives, and all three failed for one reason: **a stored compute is not stale
until it has been written.** Left pending in `env.transaction.tocompute`, it is
evaluated on first access — or on the flush that `search()` performs — which
inside a later `freeze_time` happens under the *new* clock and produces the
right answer for the wrong reason. Every fixture now flushes under the clock it
was created with. Written differently, those three would have shipped green and
proved nothing, which is the same failure mode as handoff 08's
"a test that invokes the thing under test cannot see that nothing else invokes
it" — one layer down.

---

## The verification pass

A fresh agent that wrote none of the code reviewed the diff against the
handoff's acceptance criteria and `CLAUDE.md`. **No blockers.** It confirmed the
recompute mechanism against Odoo 19 core rather than against the comments —
including that `Field.write` calls `_filter_not_equal` *before*
`_update_cache(dirty=True)`, which is what makes the `fetch()` prefetch actually
prevent unchanged rows being rewritten — and confirmed attribution is clean,
that exactly one new stored column exists, that nothing in the repo relied on an
`AccessError` arriving as 400, and that the three dashboard routes really were
the only non-`sudo()` ones.

**Seven findings fixed in response:**

1. **The SLA cron was the one of the five that silently skipped archived rows.**
   `request.request` has an `active` flag, so the bare `search()` hid them —
   while the same changeset argues the opposite case explicitly in `asset_pm.py`
   and `fleet_vehicle.py`. Three crons guarded it and the fourth, where the same
   reasoning applies, did not. Latent (zero archived requests on every tenant),
   fixed anyway.
2. **`is_verified` read the clock through the *reader's* timezone.**
   `fields.Date.context_today(self)` resolves `env.user.tz`; the other four
   computes use server-local. Nigeria is UTC+1, so between 23:00 and 00:00 UTC a
   Lagos user's write computed a cutoff a day ahead of the cron's — and the
   stored column could flip and un-flip depending on who last triggered it. A
   stored field's value must not depend on who is reading. Now
   `fields.Date.today()`, matching what `action_verify` writes.
3. **`next_due_date` dropped from the overdue cron's explicit push list** — it
   comes off the same compute and `compute_value` un-marks every field in
   `pool.field_computed`, so naming it added nothing.
4. **CI now names `myservice_security` and `myservice_fleet_maintenance`.** They
   were running only by transitive cascade through `button_upgrade()`. That is
   coverage you cannot see, and it evaporates the day either dependency changes
   — which is the same shape as the defect that made this CI step necessary.
5. **`cron_asset_pm_refresh_overdue` given `priority=1`**, so it precedes
   `cron_asset_pm`, which decides what to raise a request for by reading
   `next_due_date`. The fleet pair already did this; the asset pair did not.
6. **The handler-shadowing guard now matches dotted exception names** —
   `except odoo.exceptions.UserError:` would have escaped it entirely.
7. **The 19.0.1.10.0 migration says in the file that its deletion branch can no
   longer fire**, and why it must stay anyway.

**Not fixed, deliberately** — see Open questions 1 and 2 below, plus: none of the
five crons call Odoo 19's `ir.cron._commit_progress`, so a run killed by
`limit_time_real_cron` is recorded as a failure rather than `PARTIALLY_DONE` and
is not rescheduled to finish. The raw `cr.commit()` is safe — the job lock is
held on a separate cursor — so this is a resumability gap, not a correctness
one, and `_cron_refresh_verification` on `nrs19` would walk 11,878 assets in one
non-resumable pass. Worth a follow-up.

## Open questions

1. **Writing a category's `verification_interval_days` recomputes every asset in
   that category, synchronously, inside an HTTP request.** That is the price of
   the `@api.depends('category_id.verification_interval_days')` that makes
   "shortening a category's window bites immediately" true — and the field is
   writable over `PATCH /api/v1/settings/categories/{id}` under `settings:write`.
   Measured largest category: **10,259 assets on `nrs19`**, 1,778 on
   `jaizbankplc`. The flush path bypasses `write()` overrides so there is no
   chatter storm, and a bulk UPDATE of that size is seconds rather than minutes
   — but it is a published route behind a proxy timeout with no test at that
   scale. The alternative is dropping the dotted depends, which makes a category
   change bite within a day instead of immediately. **I kept correctness and am
   flagging the trade rather than taking it.**

2. **Was fixing `on_duty` and `maintenance_status` in scope?** I argued yes from
   R28 and R29. It is the one place I widened the handoff.
3. **`_compute_next_due` rewrites `next_due_date` to today, every day**, for any
   schedule with `interval_days` and no `last_done_date` — such a schedule is
   permanently `is_overdue = False`. Pre-existing and untouched; it means the
   overdue cron will dirty those rows on every tick. Needs a ruling if PM
   schedules are ever created in volume.
4. **`myservice_security/static/src/js/security_tabs.js:181`** does a
   `search_read` on `security.guard` for `shift_start` / `shift_end`, neither of
   which exists on the model. That RPC raises. Outside this handoff's rule;
   flagged, not fixed.
5. **The kanban badge chain** (question 1, item 4) — "Breached" now hides
   "Urgent". A product call, not a defect.
