# Handoff 44 — Report: the credential that is already root

**Branch:** `fix/the-credential-that-is-already-root` · **Base:** `dev` at `3f4a4a7` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/44-evidence/` — the drive script and its four transcripts, the three full HTTP-suite runs, the in-registry run, the strip script's dry run and apply on `test19`, and the fresh tenant's install, bootstrap and credential groups.

## In plain words, first

The test credential that `bootstrap.py` sets up on every tenant was being made a full Odoo system administrator — the role that can run any code on the server. I took that role away from it on the test tenant and drove everything the credential is used for.

**Nothing broke.** Every request the credential makes got the same answer with the role as without it. That covers creating an asset as Vendra would, replaying it, confirming a label, the employee sync, the reconciliation reads, all nine dashboards, the five audit reports, users, roles and approvals. The whole HTTP suite run as the stripped credential was *better* than with the role. Two tests had been skipping themselves for months because the credential was root, so they could not prove what they were written to prove. They now run and pass: nobody can withdraw somebody else's move request, and the credential cannot make itself an administrator.

The one thing the credential lost is something it should never have had: withdrawing a request somebody else raised, which Odoo allows any system administrator. The role was never doing any work. We had been handing out root for nothing.

**What changed.**

- **Two places were handing the role out, not one.** Report 42 found `bootstrap.py`. Searching every first-party writer before building on that, as `CLAUDE.md` requires, found a second: the database migration that gave each credential its own user on 7 September granted the role to any credential holding the `admin` scope. That is exactly why the three credentials that hold it are the three that had `admin` that day. Both have stopped, and a source guard now fails if either comes back. The migration mattered beyond history: a 15-era client database cut over to 19 would have run it again and minted root.
- A database built from nothing with the new script has no credential holding it. On that fresh database, Vendra creates an asset and the Tag-Issuing Unit confirms its label, and the record names each of them correctly.
- The credentials already holding the role keep it until somebody decides otherwise, because bootstrap is also how a client's server is deployed. Removing it there silently would change live systems with nobody deciding to. There is now a script for that decision: it only shows what it would do unless told to act, and it puts the change on the access record.
- Locally, 3 of 12 credentials held the role, and all three were this same test credential. I removed it on `test19` only. **Neither Vendra's nor the Tag-Issuing Unit's credential held it on any tenant** — the "credentials that matter most" were never root.
- What an API credential is entitled to is now written down for the first time.

**One name.** The refusal used to call the role *Role / Administrator* while the rest of the API called it *System Administrator*. One table in the model now names it, and every place that says the name reads from that table, including the access record from today on. A guard fails if anybody starts a second table.

**Staging.** The user-management screens from handoffs 41–43 are live on all four cluster hosts. Measured, not assumed.

## A · The strip-and-drive (§1)

**What I stripped.** `test19`'s `cadra_client_test_client` is the user behind `test_client`. That credential holds every scope, `admin` included. I removed `base.group_system` with the owner script this handoff adds (§C), in two runs, dry run first:

```
database: test19 · dry run
1 API client(s) on this database
  ~ test_client              cadra_client_test_client           scopes: admin approvals:write assets:read …
1 of 1 client users hold base.group_system directly; 1 would be removed, 0 refused.

database: test19 · APPLY
  ✓ test_client              cadra_client_test_client           scopes: admin approvals:write assets:read …
1 of 1 client users hold base.group_system directly; 1 removed, 0 refused.
```

Before and after, read from Postgres:

| | group held directly | last access-change id |
|---|---|---|
| before the dry run | `t` | 18546 |
| after the apply | `f` | 18548 |

The record row is:

```
18548 | removed | Smoke Test (API client) | System Administrator | __system__ | f | user_write
```

Id 18547 is missing because the dry run's row was rolled back. The gap is the proof it ran. `strip-test19-dryrun.txt`, `strip-test19-apply.txt`.

**The targeted drive.** `drive_credentials.py` authenticates each credential the tenant has and calls every leg the handoff names:

- **Receipt hand-off (INT-03):** an idempotent `POST /assets` and its replay, a read, and the reconciliation filter.
- **Label confirmation (INT-05):** `POST /assets/<id>/tag-affixed`.
- **Employee sync:** `POST /integrations/sap/employee-sync`. The suite's own test of this accepts a 500, so the drive checks the status itself.
- **Diagnostics and dashboards:** `/meta/diagnostics` and all nine dashboard and station reads.
- **Administration:** users, roles, the approvals queue and approvers, and the three settings reads.
- **Reports:** all five audit reports, employees, locations and requests.

It flags any 5xx and any 400/403 whose sentence names an Odoo access refusal. I ran it with the group held and again without it:

```
with    (drive-test19-with-group.txt):    37 calls, 0 flagged
without (drive-test19-without-group.txt): 37 calls, 0 flagged
diff of the status columns, ids and timestamps masked: identical
```

**The whole HTTP suite as the credential**, the same tenant before and after:

| run | passed | failed | skipped | of |
|---|---|---|---|---|
| with the group (`pytest-test19-baseline-with-group.txt`) | 1,176 | 2 | 12 | 1,190 |
| without the group, plus this handoff's code (`pytest-test19-without-group.txt`) | 1,181 | 0 | 10 | 1,191 |

The run without the group has one more test: the source guard this handoff adds (§D).

**The two baseline failures are not the group.** Both are in `tests/test_audit_logs.py` and both are `test19` outgrowing a test. The access-changes report pages accounts 50 at a time, and `test19` now holds 61 accounts in the report (72 internal users, of 74), most of them from handoff 43's fixtures.

- One test compared the whole period's `events_in_period` (198) with one page's events (170).
- The other gave a one-row-per-page cursor walk a fixed budget of 60 pages.

The report was right both times. Both tests now walk every page (§D). They passed **26 of 26** while the group was still held, before the strip, so the fix is independent of it.

**The two skips that disappeared are the finding:**

- `tests/test_approvals.py:695` — *"both users this suite can authenticate as are Odoo administrators, who may withdraw anybody's request by design."* It now runs: `test_somebody_elses_request_cannot_be_withdrawn` PASSED.
- `tests/test_user_roles.py:193` — *"the suite's credential user already holds `system` directly (1 of 1); nothing to escalate to."* It now runs: `test_the_credential_cannot_make_its_own_user_an_administrator` PASSED.

The targeted re-run of both files gave 48 passed of 48, 0 skipped.

**The list the handoff asked for:**

1. **Withdrawing a change request somebody else raised.** The route allows a non-requester only when `_is_admin()` is true (`v1_approvals.py`, the `withdraw` handler). That is `base.group_erp_manager`, which `base.group_system` implies.

   That is the entire list, and it is a loss in the right direction: it is a power of an Odoo administrator, not anything the credential's scopes promise.

   Deciding approvals is **not** lost. `approvals:write` maps to Asset Manager in `SCOPE_GROUPS`, and Asset Manager is `APPROVER_GROUP`. So `_may_decide` still says yes through `has_group`, and being nominated still passes `_resolve_approver`. The suite's approve and reject tests pass as the stripped credential.

**What I did not drive, and why it cannot depend on the group:**

- **Crons.** 0 of 31 crons on `test19` and 0 of 31 on `nrs19` run as a credential user. Every first-party cron is `base.user_root`.
- **The tag-transport outbox and the SAP outbound legs** are dispatched by those crons.
- **`bootstrap.py` itself** runs in `odoo shell` as the superuser. It is not the credential.

So "works for ten minutes and fails on the monthly job" has no job to fail on.

## B · `bootstrap.py` changed (§2), and a tenant built from nothing

`ensure_test_client` no longer grants the group. The comment that stood there gave the reason as *"the dashboard routes are the few that do NOT sudo()"*. They have since handoff 09 (`utils.SCOPE_GROUPS`'s own comment), and the drive confirms it. The new comment says what replaced the grant and where the procedure is.

**A fresh tenant, `boot44`, built the way `bootstrap.sh` builds one.** `bootstrap.sh` itself cannot target a second database without editing `.env`, because it sources `POSTGRES_DB=odoo` from it. So I ran its two steps by hand, with the live Odoo stopped so only one registry was in memory:

- **Install** (`boot44-install.txt`): `-i` with `bootstrap.sh`'s default module list. 0 `ERROR` or `CRITICAL` lines, 75 modules installed, 17 of 19 first-party. The two not installed are not in that list.
- **Bootstrap** (`boot44-bootstrap.txt`): `scripts/bootstrap.py` in `odoo shell` with `CADRA_DATABASE_CLASS=test`. It created `test_client`, `tag_issuing_unit` and `vendra`, ran the core seeds, and marked the database `test`.
- **Groups** (`boot44-credential-groups.txt`): **0 of 3** credential users hold `base.group_system`. Each holds exactly what `groups_for_scopes` gives it:

  | credential | groups |
  |---|---|
  | `vendra` | *Role / User, Asset User, Asset Manager* |
  | `tag_issuing_unit` | *Role / User, Tag-Issuing Unit* |
  | `test_client` | `base.group_user` plus the nine its scopes map to |

- **The drive with all three credentials** (`drive-boot44.txt`): 0 calls flagged.
  - Vendra's create answered 201, and its replay returned the same asset with the same status.
  - The Tag-Issuing Unit's affix answered 200.
  - Read back from Postgres:

    ```
     asset | asset_created_by    | tag         | state  | affixed_by                    | affixed_by_name
         1 | cadra_client_vendra | NRS-ACS-001 | active | cadra_client_tag_issuing_unit | H44 Drive
    ```

    The two counterparties are told apart in the record. That is the reason they are separate credentials.
- **The whole HTTP suite on `boot44`** (`pytest-boot44.txt`): **1,168 passed, 0 failed, 23 skipped, of 1,191**, in 3 minutes. Every skip is data a new database does not have:
  - handoff 41's named people: 11
  - partitions with no rows: 4
  - no SAP numbers, no `workflow.config`, one page of requests
  - Turnstile not configured: 2
  - the untagged-serial and `is_tagged` skips that every tenant shows

  None of them concerns the group.

**What happens to the credentials that already hold it (§2), measured locally:**

| tenant | credentials | holding `base.group_system` directly |
|---|---|---|
| `cadra19` | 1 | `test_client` |
| `nrs19` | 4 | `test_client` (not `tag_issuing_unit`, `vendra`, `nrs_approver`) |
| `gtb19` | 1 | none |
| `test19` | 1 | `test_client` — **removed by this handoff** |
| `nrs` | 1 | none |
| `lasg` | 1 | none |
| `gtb` | 1 | none |
| `jaizbankplc` | 2 | none (`test_client`, archived `h23_approver`) |

That is **3 of 12**, now 2, and every holder is the smoke credential on a tenant where it held `admin`. All eight smoke-credential users were created on 2026-09-07 by the `19.0.3.2.0` migration, which granted the group to any client holding `admin` or `*`. The five tenants whose `test_client` had a narrower scope string (no `admin`) never got it, and have not been through a bootstrap since — which would also have granted it, unconditionally. **I found the migration grant by searching every first-party writer of `base.group_system`, not from the handoff** (§B½).

**Is removing it safe now?** On the evidence above, yes. **Order:** `cadra19`, then `nrs19` locally; on the cluster, `staging` first, then each client tenant. **The command** is in `scripts/strip_credential_system_group.py`'s header: dry run, read it, then `CADRA_APPLY=1`. **What an operator would see if it went wrong:** a `403` or `400` on a call made with that credential, whose message names an Odoo model or group. The way back is to re-add the group from *Settings › Users* on `cadra_client_<client_id>`, then report the route.

**Not run on the cluster, and not measured there.** I tried to read the cluster's credential table through the read-only `db-query` workflow and my permission layer refused it as a production read. The query is under *Needs the owner*. **I changed no live tenant.**

## B½ · The second grant site, found by search

The handoff and report 42 named one grant: `bootstrap.py`. Before building on that, I searched every first-party mention of `base.group_system` — Python, XML, CSV, YAML and shell, excluding `dist/`, `crnd-19/` and `oca-19/`. That found `myservice_api/migrations/19.0.3.2.0/post-migrate.py:69`:

```python
if "admin" in scopes or "*" in scopes:
    user.write({groups_field: [(4, system_group.id)]})
```

It carried the same stale reason: *"the few controller reads that do not sudo() would otherwise start failing"*. **Removed.** A migration that has run does not run again on that database, so this changes nothing already measured. But a database upgraded across `19.0.3.2.0` in future — a 15-era client cut over to 19 — would have run it and handed its `admin` credential root again.

`tests/test_source_guards.py::test_no_provisioning_path_grants_a_credential_system_administrator` fails on a `(4, …)` membership write naming the system group in `bootstrap.py` or in any first-party migration. I proved it fails first by stashing both files: it failed naming `scripts/bootstrap.py:510` and `myservice_api/migrations/19.0.3.2.0/post-migrate.py:69`. With the edits restored, all 218 source guards passed.

**The same search found four models that only system administrators may read:**

- `nrs.sap.sync.log`, `nrs.sap.import.wizard` and `nrs.employee.import.job` (`myservice_identity/security/ir.model.access.csv`);
- `myservice_api`'s own client, idempotency, refresh-token and access-change models.

Each is a place where a non-root credential *could* fail if a route forgot `sudo()`. I drove the one the first drive had not called, the employee **xlsx import** (`drive-test19-employee-import.txt`), as the stripped credential:

- `POST /api/v1/integrations/employees/import` answered `202`.
- `GET …/import/1` answered `200`, `state: completed`, 1 row of 1 processed, 1 created, 0 errors.

The route `sudo()`s, and its background thread opens its own environment as the superuser (`employee_import_job.py:208`). The idempotent replay in every drive exercises the idempotency model, and every token exercises the refresh-token model. Both work.

**A corollary worth knowing.** `_provision_client_user` writes a client user's groups with `(6, 0, …)` on every scope change. So the next time `ALL_SCOPES` gains a scope, the next bootstrap will silently strip the group everywhere anyway. That is the reason to run the script first: the removal then happens on the record, with a log, by somebody's decision.

**What an API credential is entitled to** is now `docs/DECISIONS.md` 2026-10-02, and rule 7 in `CLAUDE.md`'s architecture rules:

- its power is its scopes, read from the token;
- its user holds exactly `groups_for_scopes(scopes)`, and never `base.group_system`, `admin` included;
- a credential needing more needs a scope and a `SCOPE_GROUPS` row, in a commit.

## C · The owner's script

`scripts/strip_credential_system_group.py` is an `odoo shell` script in the shape of `remove_test_residue.py`:

- **Dry run by default.** Every removal is actually performed inside a savepoint and rolled back, so a refusal from Odoo (the last-administrator check, for instance) shows up in the dry run, not in the apply.
- **What it touches:** only users behind a `myservice.api.client`, archived clients included, and only their *direct* membership. A credential that holds the group through another group is named and left alone.
- **No database-class refusal.** Removing root from a credential is as right on a client's database as on a test one.
- **Recorded.** The change goes on the access-change record like any other membership change.
- **Signals the running server** after the commit, so workers drop their cached copy of the groups without a restart (§G).
- **Names and leaves alone** a credential still running as a person, a direct `base.group_erp_manager` row, and — as a note — a credential holding `admin` without `approvals:write`, which loses deciding approvals.

Proved on `test19` (§A).

## D · One name per role (§3)

- **`myservice_api/models/role_names.py`** holds `PUBLISHED_ROLE_NAMES` (`base.group_system` → *System Administrator*) and `role_alias(group)`. Every place that names a group consults it first:
  - `v1_users.py`, for `/users`, `/users/<id>` and `/roles` (its old controller-local table is gone);
  - `access_guard.py`, all four refusal sentences;
  - `access_change._group_label`, the record's `group_name` snapshot;
  - `audit_access.py`, the roster's membership list, which now uses `_group_label` so a roster row and the recorded change beside it name a group identically.

  Every other group keeps the name each place already used.
- **The OpenAPI description** said Odoo calls the group *Settings*. That was true on 15. On 19 it is *Role / Administrator*. Corrected.
- **Shown live on `test19`** (`naming-live.txt`):
  - The refusal: `403 forbidden: Over the API only these roles can be granted or removed: Asset User, Asset Manager, Tag-Issuing Unit, Auditor. 'System Administrator' is not one of them. …`
  - `/roles` says `System Administrator`.
  - `openapi.json` says *"published as 'System Administrator' — Odoo 19's own name for it is 'Role / Administrator'…"*.
- **The record says it too:** the strip's row (§A) reads `group_name = System Administrator`.
- **Tests:**
  - `test_access_guard.py::test_i_the_credential_cannot_make_its_own_user_an_administrator` now asserts the published name *and* that Odoo's own name is absent. Before this it asserted `full_name`, so the suite was pinning the two-name defect it should have caught.
  - `test_i_the_record_names_the_group_as_the_api_does` drives a back-office grant through the recorder and reads the row.
  - `tests/test_source_guards.py::test_a_role_alias_is_chosen_in_one_place` fails on any second `"base.group_*": "…"` mapping in first-party code. I proved it fails first by planting one in `v1_users.py`: it failed naming `myservice_api/controllers/v1_users.py:1058`, then passed with the plant removed.
- **Old rows keep *Role / Administrator*.** The record is append-only, and a snapshot is a snapshot.

## E · The guard from 42, unchanged

- **In-registry `myservice_api` on `test19`, after the change:** `0 failed, 0 error(s) of 326 tests`, run with `--workers=0` (`odoo-myservice_api-test19.filtered.txt` — each test's start line and the result line; the raw log is not committed, it carries fixture token hashes in `bad query` lines). That includes every `test_access_guard` case: all six doors, the self-grant, the self-removal and the silent back office. The run logs 360 `cannot execute INSERT in a read-only transaction` lines and 0 `CRITICAL`. That pattern is `docs/ENVIRONMENT-FACTS.md` §*In-registry runs log …*, and it is not a failure.
- **Over HTTP:** `tests/test_user_roles.py` and `tests/test_access_guard`'s HTTP twin are inside the 1,181.

## F · Whether 41 and 42 are live on staging (§5)

They are, and so is 43. I probed each host anonymously (`staging.app.cadra.ng`, `jaizbankplc.cadra.ng`, `lasg.cadra.ng`, `gtb.cadra.ng`):

- **The new routes:** `GET /api/v1/roles`, `GET /api/v1/users`, and `POST /api/v1/users/1/roles`, `/invite` and `/deactivate`. Every one answered `401 application/json` — `{"error": {"code": "unauthorized", "message": "Missing bearer token", …}}`.
- **The control:** `POST /api/v1/doesnotexist44` and `/api/v1/users/1/nosuchaction` answered `404 text/html` (Odoo's page) on the same hosts.

So the routes exist in the code those hosts are running. `upgrade-19` ran successfully five times on 2026-10-02. Report 42's worry about the cached image does not describe today. It remains true that a run on `dev-latest` *can* reuse a cached image, and pinning the image is still the safer instruction.

## G · Verification pass

A fresh agent, not an author, reviewed the diff against the handoff and `CLAUDE.md`'s rules. Its findings and what I did with each:

**Confirmed, and fixed:**

1. **"3 of 13" was 3 of 12.** My own table adds up to 12, and so does its SQL over all eight tenants, archived rows included. Corrected in every place I had written it.
2. **The migration's grant.** It found the second grant site independently of my search. It was already fixed by then (§B½).
3. **The strip script never told the running server.** `odoo shell` does not signal cache invalidation on exit, so every worker would have kept its cached copy of the credential's groups — still treating it as root — until a restart. On a quiet client tenant that could be indefinitely.
   - **The fix:** the script now calls `env.registry.signal_changes()` after the commit.
   - **The proof** (`strip-boot44-signal.txt`): I granted the group on `boot44` through a shell, as the old script would have, and the shared cache sequence did not move. Then I stripped it with the new script. The sequence moved 32 → 33, and Odoo logged *"Caches invalidated, signaling through the database: ['default', 'stable']"*.
   - **The `test19` drive is still valid.** It ran after a restart issued in the same command as the drive (§A), and the HTTP suite's withdraw-403 independently shows the server no longer treated the credential as root.
4. **The drive script's docstring promised a move/withdraw leg it does not have.** The claim is removed. Deciding and withdrawing are proved by `tests/test_approvals.py`, which has the second person they need. The docs that said "every leg" now say what the drive actually called, and that Vendra's and the Tag-Issuing Unit's legs ran on `boot44`, because `test19` has neither credential.
5. **The script did not enforce "never a person".** It now skips, and names, any credential whose user is not a `cadra_client_*` user — `base.user_admin` on a database the migration has not reached, or a hand-linked human.

**Plausible, and acted on:**

- **A credential holding `admin` alone would also lose deciding approvals.** The model asks `_may_decide` for Asset Manager, and `SCOPE_GROUPS` gives `admin` no group. Every smoke credential measured locally also holds `approvals:write`, so none is affected. The script now prints a note for any credential it strips that holds `admin` without `approvals:write`, and the bootstrap comment and `DECISIONS.md` say so.
- **A direct `base.group_erp_manager` row is the same power by another door** (it is what `_is_admin()` reads). The script now names any such row and leaves it alone. 0 of 12 local credentials hold one.
- **My rename had changed the refusal's naming of every other group**, from `full_name` to `name`. Restored: only the alias changes; the offending group otherwise reads `full_name`, as before.
- **The `CLAUDE.md` skip breakdown did not add up.** Rewritten from the stripped run's actual ten skips.
- **The extra test, explained.** 1,190 → 1,191 is `test_a_role_alias_is_chosen_in_one_place`, added after the baseline began. The provisioning guard added after that makes the HTTP suite 1,192.

**Plausible, and left, with reasons:**

- **An event recorded before 2026-10-02 can show `Role / Administrator` beside a roster that now says `System Administrator`.** That is a snapshot beside a current value — the same thing that has been true since handoff 41's privilege prefix. Rewriting history in an append-only record is not an option.
- **The naming guard is narrow.** It catches the shape the defect had: a dict keyed on a group xmlid. Widening it to role-key tables and tuples would catch things that are not alias tables. Left.

**Checked by it and found fine:** no other grant in `scripts/`, `k8s/`, `.github/`, `_provision_client_user` or `groups_for_scopes`; nothing implies the system group on `test19` (0 rows); the dashboards `sudo()`; the savepoint dry-run logic; no import cycle; every evidence number matches its file.

## H · Suites, with denominators

| suite | tenant | result |
|---|---|---|
| HTTP, with the group (baseline) | `test19` | 1,176 passed, 2 failed, 12 skipped **of 1,190** — the 2 are §A's outgrown tests |
| `tests/test_audit_logs.py` after the fix, group still held | `test19` | 26 passed **of 26** |
| HTTP, without the group, with this handoff's code | `test19` | 1,181 passed, 0 failed, 10 skipped **of 1,191** |
| `test_approvals.py` + `test_user_roles.py` | `test19` | 48 passed **of 48**, 0 skipped |
| in-registry `myservice_api` (`--workers=0`) | `test19` | 0 failed, 0 error(s) **of 326** |
| in-registry `myservice_api`, after the verification fixes | `test19` | 0 failed, 0 error(s) **of 326** (`odoo-myservice_api-test19-final.filtered.txt`), 0 `CRITICAL` |
| `tests/test_source_guards.py`, final | — | 218 passed **of 218** |
| HTTP users / roles / lifecycle / audit / approvals / guards, final code | `test19` | 329 passed, 1 skipped **of 330** (`pytest-test19-final-targeted.txt`; the skip is the only-credential one) |
| HTTP, fresh tenant | `boot44` | 1,168 passed, 0 failed, 23 skipped **of 1,191** |
| `test_source_guards.py::test_a_role_alias_is_chosen_in_one_place` | — | failed on the plant, then 1 passed **of 1** |

The runs went in CI's order: the HTTP suite first, then the in-registry suite. **The skip count on `test19` is now 10, not 12** — `CLAUDE.md` is updated to say so and why.

## I · Deviations

- **The handoff and report 42 named one grant site; there were two** (§B½). Fixed both rather than one.
- **The handoff speaks of the credentials that matter most as the ones holding root.** They did not. Vendra's and the Tag-Issuing Unit's credentials go through `_ensure_scoped_client`, which never granted the group. Only the `admin`-scoped smoke credential got it. INT-03 and INT-05 were driven on a fresh tenant anyway (§B), as asked.
- **`bootstrap.sh` was not run as a script** on the fresh tenant, because it reads its database name from `.env` (`POSTGRES_DB=odoo`), and changing `.env` would change every later command on this machine. Its two steps were run by hand with the same arguments and the same environment variable, `CADRA_DATABASE_CLASS=test`, that CI uses.
- **Two tests changed that the handoff did not name** (§A): the access-report tests `test19` had outgrown. They were failing on `dev` before this branch.
- **`test19` is left without the group.** It is the target state, the suite is better for it, and it is a test database. `cadra19` and `nrs19` are untouched.

## Needs the owner

1. **Measure the cluster**, read-only, with `db-query` on `staging`, `gtb`, `jaizbankplc` and `lasg`:

   ```sql
   select c.client_id, c.active, c.scopes, u.login,
          exists(select 1 from res_groups_users_rel r where r.uid = u.id
                 and r.gid = (select res_id from ir_model_data
                              where module = 'base' and name = 'group_system')) as sys_direct
   from myservice_api_client c join res_users u on u.id = c.user_id order by c.id;
   ```

2. **Decide whether to strip it, then run `scripts/strip_credential_system_group.py`** — dry run, then `CADRA_APPLY=1` — on each database where a credential holds it. Locally that is `cadra19` and `nrs19`; on the cluster, whatever (1) shows. The command and what to watch for are in the script's header and §B.
3. **Merge the PR.** My permission layer refuses `gh pr merge`.
4. **Drop `boot44`** when convenient. It is this handoff's scratch tenant, marked `test`, and nothing points at it.

## Commits

- `2cbcbea` fix: an API credential is not a system administrator — bootstrap and the 19.0.3.2.0 migration stop granting base.group_system; owner script to strip it; one published name per role
- `57a49ef` docs: report 44
- this commit: the commit list
- PR: https://github.com/wmlmetro/Cadra/pull/102
