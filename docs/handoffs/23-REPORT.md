# Report 23 — The last two audit reports

**Branch:** `feat/audit-logs` · 7 commits off `dev` · **Needs the owner: merge the PR.**

Everything the handoff asked for is built. **One acceptance criterion rested on a
premise that is not true of this repository** — `Vendra Auditor` does not exist in
Cadra — and §5 says what was built instead and why.

---

## 1 · What each report can and cannot answer

**This is the deliverable more than the code is, so it is first.**

### B1 · Access changes

**Can answer**

- **Who has access now** — every real account, its groups, and for an integration its API scopes. Present tense, labelled as such throughout, never presented as history.
- **Which accounts were created in the period** — with the exact timestamp and the creating user. `precision: exact`.
- **Which accounts were last modified in the period** — with the timestamp and the writing user. `precision: last_write_only`.
- **Whether an account is active**, and who created it, for every account including deactivated ones.
- **What the record itself can support** — `fidelity`, re-measured on every request.

**Cannot answer, and never will from these databases**

- **Who was granted or removed from a group, when, or by whom.** The question as §13.4 asks it.
- **Any historical group state**, at any date.
- **Which field an `account_modified` event actually changed** — a timezone edit and a group grant are indistinguishable.
- **Previous values** of anything on a user.
- **Deleted accounts** — no tombstone, so the roster is a lower bound.
- **Password changes, login history, IdP correlation** (specification §7.6's other half).

**Why, measured rather than asserted — six places it could have been:**

| Source | What is there |
|---|---|
| `res_groups_users_rel` | **`(gid, uid)`. Two integer columns.** No timestamp, no actor. A grant writes nothing that outlives it. |
| `res.users.group_ids` tracking | **No `tracking=`** in Odoo core, first-party, `crnd-19/` or `oca-19/`. |
| `mail_tracking_value` on `res.users`/`res.groups` | **0 rows. All eight tenants.** |
| `ir_logging` | **0 rows. All eight tenants.** `log_db` is unset in `config/odoo.19.conf` and always has been. |
| An audit module | **None.** `oca-19/` has one module, `web_responsive`; none of `crnd-19/`'s 23 is an audit log. |
| `res_groups`/`ir_model_access`/`ir_rule` write stamps | Present, and **100% uid 1 `__system__`** — upgrade churn. Not one ACL in any tenant was ever written by a human. |

**Nothing was synthesised.** `summary.group_changes_in_period` is `0` and it is a
**structural zero in the payload**, so a consumer reading counts sees the absence
rather than inferring it from a missing key.

### B2 · Configuration changes

**Can answer**

- **Which parameters were created or written in the period.**
- For each: the **current value**, the **last writer**, the **last write time**, the creator and creation time.
- **Whether the last writer was a person or `__system__`** — cron, CLI or module upgrade.
- **Whether the value is redacted**, and a comparable fingerprint of it.

**Cannot answer**

- **The previous value.** Not stored anywhere.
- **How many times a key changed.** One row per key, last-write-wins; a key changed five times shows the fifth.
- **Anything about a deleted key** — no tombstone.
- **What else changed in the same save**, or who opened which settings form. `res.config.settings` is transient and vacuumed — **0 rows on every tenant** — so a settings-screen save leaves only the resulting parameter row. This is the biggest reason the report is thin and the one an auditor is least likely to guess, so it is in `fidelity.notes`.
- **Views, crons, server actions, ACLs and rules.** All carry a write stamp and **every stamp on every tenant is `__system__`**; the 800 "changed" `ir_ui_view` rows on `jaizbankplc` are upgrade churn. Named in `fidelity.notes.scope` rather than reported, because 1,634 view rows nobody edited would bury the handful of parameters somebody did.

---

## 2 · How many configuration changes are recoverable at all

**22 keys estate-wide. 12 of them attributable to a named human.**

| tenant | written after creation | by a named human |
|---|---|---|
| `jaizbankplc` | 7 | 5 |
| `cadra19` | 7 | 5 |
| `nrs19` | 2 | 1 |
| `test19` | 2 | 1 |
| `gtb19`, `nrs`, `lasg`, `gtb` | 1 each | 0 each |
| **total** | **22** | **12** |

```sql
SELECT count(*) FROM ir_config_parameter
 WHERE write_date > create_date + interval '2 second';
```

The two-second tolerance separates "written again later" from the same-transaction
stamp Odoo puts on both columns; without it every key in every database reports as
changed. **Read the number correctly**: it counts *keys known to have been modified
at least once*, not changes. On `jaizbankplc` the five human ones are
`cadra.brand_primary`, `cadra.brand_short_name`, `cadra.depreciation.mode`,
`cadra.depreciation.declining_switches_to_straight_line` and `web.base.url`.

**Values are redacted by key name.** `ir_config_parameter` holds
`myservice_api.jwt_secret` — the key every access token in the tenant is signed
with — beside `database.secret`. The value becomes `[redacted] sha256:<16 hex>`:
no prefix, no last-four, no length, because a truncated secret is a head start and
a published length narrows a brute force. **Checked against all 26 distinct keys
in the estate**: 4 redacted (`myservice_api.jwt_secret`, `database.secret`,
`database.uuid`, `auth_signup.reset_password`), 22 not, and no genuine secret
missed. The last of the four is an over-redaction — its value is a boolean — and
that direction is the correct one to err in.

---

## 3 · Part A — the guard that did not fire

The old logic found **0** offenders in the real `.gitlab-ci.yml`; the new logic
finds **3** (`SERIES_BRANCH: '15.0'` and the two `- "15.0"` refs). It had passed
only because the proof invented `ODOO_SERIES_BRANCH`.

The `odoo`-on-the-line requirement is gone, replaced by an allow-list of the two
non-Odoo version shapes these files contain. **The fixture is committed rather than
recovered from git at run time**: `actions/checkout@v4` clones at depth 1, so a
git-based proof would *skip* in CI — and this file's own docstring says a skip is a
guard that passes. A second test re-derives the bytes from history wherever the
clone is deep enough, and skips only there.

---

## 4 · Part C — the disposal approval

`POST /api/v1/assets/<id>/approve-disposal`, `approvals:write`, idempotent,
`409` declared. The control is unchanged: `disposal_approved_by` stays off
`_WRITABLE_FIELDS` and nothing about `PATCH` changes.

Proved live on `jaizbankplc`, in this order:

1. Body `{"disposal_approved_by": 2, "approver": "somebody else"}` → **400**, naming both rejected fields.
2. Body `{}` → **200**, `approved_by: {id: 287, name: "Handoff23 Approver (API client)"}` — the caller's own user, not the uid 2 the first call asked for. **That ordering is the proof the refused call wrote nothing.**
3. Same call again → **409**, naming who holds the approval and when.

A body naming an approver is **refused, not ignored**: dropping it would return
`200` to a caller that believes it appointed somebody, and the recorded approver
would then disagree with the caller's own logs.

---

## 5 · The deviation — `Vendra Auditor` does not exist in Cadra

The acceptance criterion *"both must be openable by `Vendra Auditor`, proved by
acting"* assumes a role this repository does not have. `Vendra Auditor` is a
**Frappe role in the sibling repository**; `docs/integrations/INT-10-audit-access.md`
§4.3 had already recorded Cadra's `audit_viewer` as absent, and the string appears
nowhere in this codebase outside the handoff itself.

So **`myservice_api.group_auditor`** was built: six READ scopes, no write scope of
any kind, implied by nothing and implying nothing — an auditor who is also an Asset
Manager is not independent of what they are auditing.

**The `audit:read` scope INT-10 §4.3 proposed was deliberately NOT built.** The
five reports are views of the register, the identity roster and the configuration,
so they take those things' scopes; a scope no group grants makes a report
unreachable on the day it ships, which is the ruling `v1_assets.py` already made
for the first two reports. `settings:read` is new and is a *read* scope rather
than a reuse of `settings:write`, because an auditor whose only way to read the
settings is to hold the right to change them is an auditor the control has been
handed to.

**Proved by acting, and it mattered.** A user holding exactly this group logs in
through `POST /auth/login`, takes a real token, and opens all five reports —
**5 × 200** — then is refused **5 × 403** on five writes. The acting proof was
itself nearly worthless: `test_auditor_access.py` was written and **never
registered in `myservice_api/tests/__init__.py`**, so it did not run. The suite
reported *121 tests, 0 failed*; with the import it reports **126**. It was caught
by noticing the denominator had not moved across a change that should have moved
it — the discipline `CLAUDE.md` asks for, applied to the one file whose absence
nothing else would have revealed.

---

## 6 · What the verification pass found

Two agents wrote tests against code they had not written. **Between them they
found seven defects in code an hour old, none of which I had found.**

1. **Both reports declared `limit` and `cursor` and read neither.** `?limit=1` returned every row, `?limit=abc` answered `200` where the disposal report answers `400`, and there was no `pagination` block at all — a caller walking `next_cursor` read `None` on page one and stopped, correct by accident. **The roster was unbounded**, which is the uncapped-response shape the external record cap exists to prevent, reachable with a read-only scope. Both now page; a page of the access report is a window of **accounts**, and the route spells out its own `limit` description to say so, because `roster` and `events` are two views of one window.
2. **`period` published `{from, to, bounds}`** where `DisposalReport` publishes `{date_from, date_to, inclusive}` — the same fact under two names, on reports an auditor reads side by side. Now matches the one that shipped first.
3. **The configuration report had three branches and two coverage values**, so "none modified" and "some modified" were indistinguishable to a consumer obeying *branch on `coverage`, never on `statement`*. That is the exact failure `sap_coverage` exists to prevent, reproduced in its sibling. Four values now, and `partial` is reachable so the report cannot go stale silently.
4. **`fidelity.tracked` was true if *any* field on the model was tracked**, including one contributed by another module — a fidelity block that *overstates* is worse than one that is thin.
5. **The secret rule required a delimiter on both sides**, so `database.secretkey`, `cadra.jwtSecret` and `myservice_api.apikey` were **not redacted**. Two tiers now, verified against 27 constructed keys and all 26 real ones.
6. **The closing bound kept `23:59:59.000000`** — a one-second hole at the top of every period documented as inclusive of the whole closing day.
7. **One `myservice.api.client` search per user** — N+1 on a report that did not paginate.

One defect was found by the code itself rather than by a reader: the first version
read `self._fields[field].tracking` directly and **500'd**, because a plain
`Many2many` in Odoo 19 does not carry the attribute. **A hard-coded "no tracking"
would have shipped and been wrong in silence** — which is the argument for
measuring the boundary on every request rather than declaring it.

---

## 7 · Denominators, in CI's order

| Run | Result |
|---|---|
| `pytest tests/` (full) | **753 passed, 32 skipped** — skip count unchanged from before this work |
| `myservice_api` in-registry, `--workers=0` | **0 failed, 0 error(s) of 126 tests** |
| CI's full eleven-module in-registry run | **0 failed, 0 error(s) of 452 tests** |

No run collapsed to `of 0 tests`; no `CRITICAL`. The 117 `cannot execute INSERT in
a read-only transaction` lines in the in-registry output are **pre-existing** —
measured by stashing this branch's work and re-running, which produced the same
117. They are Odoo 19's readonly-cursor retry, not this change.

**Fan-out:** `myservice_api` upgraded on all eight tenants (`-u myservice_api`),
`CRITICAL=0` and `Modules loaded.` on each; `group_auditor` confirmed present in
`ir_model_data` on all eight. **No stored column moved** — both report models are
read-only method inherits — so the fan-out was for the group data file, not a
schema migration. Both reports verified on a second tenant (`nrs19`: 2 modified,
1 human, no leaked value), matching the independent measurement exactly.

---

## 8 · Artefacts and open items

- **Artefacts left on `jaizbankplc`**: an asset `H23 disposal probe` (id 8396, approved — the evidence for §4), plus a user `handoff23_auditor` and a client `Handoff23 Approver`, **both deactivated** after use. `tests/test_audit_logs.py` also creates `pytest-approval-<epoch>` assets, disclosed in its docstring.
- **`auth_signup.reset_password` is over-redacted** — its value is a boolean. Kept: carving exceptions into a security rule by name is how the rule stops meaning anything, and `value_is_redacted` tells the reader it happened.
- **An API client provisioned with `settings:read` is placed in `group_auditor`** by `SCOPE_GROUPS`, since that is the only group granting the scope. Intended and consistent with every other scope, but it means "member of `group_auditor`" is not the same population as "a person doing audit work". Named, not changed.
- **`Finance Officer` / `finance_viewer`** (specification §3) still does not exist.
- **Nothing about the access gap is retroactive.** `INT-10` §2.10b carries the three options and the recommendation; the record begins the day one is done, and that is NRS's decision rather than a backlog item.

---

## 9 · Wall-clock and correction share

**The commits span 09-14 12:04 to 09-15 07:07**, but that is not working time — it
includes two long idle gaps between my turns. Measured agent time is about **45
minutes** across six subagents; my own share is the larger part and I cannot
separate it honestly from here, so I am giving the span and the caveat rather than
a number I would be inventing.

**The correction share was the highest of any handoff I have run, and all of it was
worth it.** Six subagents: three read-only mapping agents whose output needed no
correction, two test authors who between them found seven defects in my code, and
one verification pass. **Every defect in §6 came from somebody who had not written
the code**, and two of them — the unregistered acting proof and the unread `limit`
— are the same shape as the four findings report 22 made about handoff 21: not
mechanisms that are wrong, but evidence that is weaker than it looks.

**The machine behaved.** No Postgres crash-restarts. Every `--stop-after-init` was
serialised in the main session; eleven container restarts, each waited on with an
until-loop rather than a fixed sleep. The one real friction was self-inflicted: a
`Many2many` attribute error that only appeared when the endpoint was called,
because nothing in the module-load path exercises it.
