# Handoff 07 — REPORT: the SAP asset legs (INT-06 / INT-07 / INT-09)

**Builder:** Claude Code (IDE) · 6 September 2026 · Branch `feat/sap-asset-legs` → PR into `dev`
**Commits:** `029d5db` (Part A), `b1618b8` (Parts B and C)

**Owner-blocked:** merging the PR. `gh pr merge` is refused by the Builder's permission layer, as every handoff ending in a PR is.

---

## Step 0 — state of the tenants

`dev` was at `9769fe6`, working tree clean, PR #49 already merged. **Nothing needed fanning out:** the only commits since #49 are `b72c9f7` and `9769fe6`, both documentation. All eight databases were already at `myservice_api` 19.0.3.1.0 and `myservice_workflow` 19.0.2.0.0 from handoff 06's own fan-out. Verified rather than assumed before starting.

The verification table below is therefore the **end** state, after this handoff's own fan-out — which was needed, because this work adds twelve stored columns to `nrs.asset`.

```
DB             ASSET_REG    WORKFLOW     SAP_COLS DUAL_CODE_STATES
cadra19        19.0.1.9.0 19.0.3.0.0     12/12    not_tagged=1335
nrs19          19.0.1.9.0 19.0.3.0.0     12/12    exception=34 not_tagged=11880 reconciled=2
gtb19          19.0.1.9.0 19.0.3.0.0     12/12    not_tagged=156
test19         19.0.1.9.0 19.0.3.0.0     12/12    (no assets)
nrs            19.0.1.9.0 19.0.3.0.0     12/12    not_tagged=1272
lasg           19.0.1.9.0 19.0.3.0.0     12/12    not_tagged=150
gtb            19.0.1.9.0 19.0.3.0.0     12/12    not_tagged=150
jaizbankplc    19.0.1.9.0 19.0.3.0.0     12/12    exception=232 not_tagged=1657
```

**`jaizbankplc` has 232 dual-code exceptions** — 232 assets with a confirmed physical tag and no SAP asset code. That is not a defect in this work; it is the control doing the only thing it exists to do, on a live tenant, the first time it has ever been asked.

One incidental: a stale zero-byte `.git/HEAD.lock` (11 minutes old, no git process running) blocked the first `git checkout -b`. Removed; the branch had already been created by the failed call.

---

## Part A — reported first, as asked

`docs/integrations/INT-06-07-09-sap-requirements.md`, committed and pushed as `029d5db` **before Part B was started**. Written in the same register as `sap-vendra-interface-spec.md` so it folds in without translation. 500 lines.

The four questions, answered:

**1 · INT-06, field by field.** §2.3 is the payload, §2.4 maps every wire field to its source on `nrs.asset` and says whether it is always present. What SAP must return is §2.6 — and the answer is *considerably* more than the asset code. Beyond `sap_asset_number`: the **sub-number** (a main number alone does not identify the asset where sub-numbers are used), the **company code** (the same number can exist under two, so the number alone is not unique), the **asset class as posted** (if it differs from what we sent, our mapping is wrong and we want to know on call one, not at year-end), and the **capitalisation date as posted** — because SAP will override our proposal under period-close rules, and if Cadra displayed the proposed date while SAP posted a different one the two systems would disagree about when NRS started owning the asset.

Also asked for, and the reason is a piece of luck: Cadra already has a first-class **"ERP-managed" depreciation mode** built for precisely this — an external system owns the figures and Cadra never calculates them. So `net_book_value` and `accumulated_depreciation` are asked for as SAP's reported figures. They are stored in their own fields and shown, never fed into Cadra's depreciation engine; two systems computing one number is how they come to disagree.

**2 · INT-07, push or pull.** Recommended **synchronous in the INT-06 response**, with a callback *only* if SAP's asset creation is genuinely deferred, and a **reconciliation range query regardless**. The reasoning is in §3.1, and the load-bearing part is the third one: the dual-code control has a name in the specification and a consequence in an audit, and **a control that depends on one HTTP call succeeding is not auditable**. The range query is also the only way to find the other half of the exception — a SAP asset code with no Cadra asset, which is money on the books with no physical thing behind it, and which Cadra cannot see from where it stands.

It also asks SAP for something easy to miss: **the Cadra asset code must be stored in a queryable field on the SAP asset master.** Without that the reconciliation cannot be verified from either side.

**3 · INT-09.** One endpoint, typed event, three events: `asset.transferred`, `asset.custodian_changed`, `asset.disposed`.

**I have argued revaluation and impairment OUT, and this is a deviation from the handoff.** The handoff listed them; the September flow's Stage 6 does not, and neither does INT-09 in the integration register — 6.2 is location/custodian/transfers and 6.3 is disposal/retirement. I agree with the flow. These are valuation judgements, SAP is the system of record for financial postings, and Cadra has no revaluation or impairment concept at all — no approval, no effective date, no audit trail. Inventing one so Cadra can push numbers into the system that owns them would put two systems in charge of one figure. Recommended instead that they flow **SAP → Cadra** in the reconciliation refresh. If NRS wants the *decision* captured in Cadra with approvals and evidence, that is a scope change, and the document says so.

`missing` is raised as a **finance policy question for NRS**, not answered. An asset missing for a week is very often found; whether that should trigger a write-off, a flag, or nothing is not a decision the Builder should make.

**4 · What SAP must give us.** §5: the asset class mapping (all 22 live categories tabulated), the cost centre list, company code, vendor identity and the capitalisation threshold. Three of those deserve naming here:

- **Cost centre is the one we are most likely to get wrong, and the document says so.** Cadra's `department` is free text and the live register holds **808 distinct values**. Deriving a cost centre from that by string matching would be a fiction. The document asks whether cost centres follow **location or organisational unit** — a question whose answer changes what we build — and commits to sending null rather than a guess.
- **The capitalisation threshold**, with an explicit request for a *distinguishable* response for items below it. If SAP silently expenses them and returns no code, those assets become permanent dual-code exceptions that are not actually findings — the fastest way to make an exception report worthless.
- **Sub-numbers.** Cadra models sub-assets and components under a parent. Whether a component becomes a SAP sub-number or its own asset master changes the payload and the reconciliation, and is far easier to answer now than to migrate later.

**§7 is the section I would read first.** The measured state of the live register, because a requirements document that ignores data quality is how "fails silently with a 201" happens:

| | Count | Share |
|---|---|---|
| **No cost at all** (neither acquisition cost nor purchase value) | **11,885** | **99.8%** |
| No custodian | 5,271 | 44% |
| No serial number | 618 | 5% |
| Carrying a SAP asset number | **0** | **0%** |

**An asset master posted with a zero acquisition value is not a capitalisation, it is a defect on SAP's books.** The recommendation is not to run INT-06 over the legacy population at all: load the existing SAP asset numbers as a one-off link-not-create reconciliation, and let INT-06 handle only assets tagged from go-live forward. Creating twelve thousand asset masters at zero value to satisfy a completeness control would defeat the control. The document asks for the SAP fixed-asset extract that makes that possible, and names the resulting match report as the control's **opening balance**.

Two corrections were made to the document after the code was written, both because building it taught me the wording was wrong — recorded here rather than quietly:

1. It said a lifecycle event for an asset with no SAP number is *"held, not sent"*. The implementation does not hold it, and holding would be wrong. Corrected to say it is **not sent at all**, with the reason: there is no asset master to update, and nothing is lost because the INT-06 create carries the current location and custodian when it fires.
2. Added a **live API reference** section pointing at Cadra's `/openapi.json` and `/docs`, mirroring the section `sap-vendra-interface-spec.md` gained during this handoff, including the same reasoning about the hand-written idempotency header that was silently ignored.

---

## Part B — built, mocked, and proven live

### Reuse, not a second delivery mechanism

Everything from handoff 06 is reused unchanged: the `workflow.dispatch.log` outbox, the `ir.cron` drain, capped exponential backoff, `event_id` idempotency, the 4xx-is-permanent classifier, the dead-letter state and its chatter note. **No new transport was written.** What is new is payloads, triggers and one response reader.

`workflow.config` gained a third `purpose` (`sap_assets`) rather than more fields on the Vendra row. SAP and Vendra fail differently — SAP is an ERP behind a corporate gateway with change windows, Vendra is a service we operate — and sharing one retry policy would mean tuning for whichever is worse and being wrong for the other.

### One thing the handoff got wrong about the code

> *"`sap_asset_code` already exists on `nrs.asset` from handoff 03's field work — check before adding anything."*

It does not. The field is **`sap_asset_number`** (`myservice_asset_register/models/asset_tag.py:260`). Nothing named `sap_asset_code` exists anywhere in the repo. I used the existing field and added nothing duplicating it — the instruction's substance was right and its name was wrong.

### Live proof — nrs19, real HTTP, a real Odoo cron worker

A committed mock SAP receiver (`docs/api/mock_sap.py`, stdlib only) implements the §2.3/§2.6/§3.3/§4 contract with a control surface for the failure modes.

**INT-06 → INT-07, the happy path.** Asset created through the `vendra` client, tag confirmed through the `tag_issuing_unit` client:

```
CREATE 201   asset_id 11919  code NRS-AST-047553
sap block at creation: posting_state "none", reconciliation_state "not_tagged"
issued tag NRS-PC-035  label_state issued
AFFIX 200
```

Both events queued, each to its own target:

```
 WDL-2026-0009 | asset.tag.affixed   | pending |    11919 | config 1
 WDL-2026-0010 | asset.master.create | pending |    11919 | config 2
```

then drained by a throwaway cron worker (`--database=nrs19`, no `db_name`, `--max-cron-threads=1`, the pattern handoff 06 established):

```
Job 'Cadra: deliver outbound asset events (INT-05)' (28) starting
Workflow event deliver → http://host.docker.internal:8899/fixed-assets  status=201
workflow: delivered WDL-2026-0010 in 1 attempt(s)
workflow: INT-07 — asset 11919 linked to SAP asset number 000000012345
```

and the register:

```
asset_code               | NRS-AST-047553
sap_asset_number         | 000000012345
sap_asset_subnumber      | 0000
sap_company_code         | NRS1
sap_asset_class          | 3100
sap_capitalisation_date  | 2026-09-06
sap_capitalised_amount   | 450000.00
sap_net_book_value       | 450000.00
sap_code_source          | integration
sap_posting_state        | posted
sap_reconciliation_state | reconciled
```

Note `sap_code_source = integration`: evidence, not a claim.

**`asset.tag.affixed` (WDL-2026-0009) stayed `pending` throughout, and that is correct.** Handoff 06 left the Vendra target disabled because its receiver does not exist yet, and the drain excludes disabled targets in its domain. This is the `event_enabled` ruling demonstrating itself: delivery paused, event kept.

**INT-09.** A transfer created, approved and completed:

```
transfer TRF/2026/0001 state done
  WDL-2026-0011 asset.transferred  pending
```

**Exactly one row.** The transfer set a custodian as well as a location, and the suppression works — one physical act, one event, not a move plus a reassignment. Delivered:

```
 WDL-2026-0011 | asset.transferred | acknowledged | 1 | 202 | f1082c5c80714a7697c9e718de5ed257
```

**The receiver taken down and brought back**, which is the acceptance criterion. Mock killed, then an asset created and tagged:

```
receiver-check (should fail): 000
CREATE 201   asset_id 11920  code NRS-AST-047554
AFFIX 200
```

**The affix returned 200 with the receiver down** — the point of the outbox. Then, verbatim from `delivery_history`:

```
[2026-09-06 21:58:08] queued for SAP (mock) — INT-06/07/09
[2026-09-06 21:58:08] attempt 1 failed, retrying in 60s: ConnectionError: HTTPConnectionPool(host='host.docker.internal', port=8899): Max retries exceeded with url: /fixed-assets (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x7ffff4bcd610>: Failed to establish a new connection: [Errno 101] Network is unreachable'))
[2026-09-06 21:59:11] attempt 2 failed, retrying in 120s: HTTP 503: SAP is unavailable
[2026-09-06 22:01:18] attempt 3 delivered (HTTP 201) ref=000000012345
[2026-09-06 22:01:19] SAP asset number 000000012345 recorded on NRS-AST-047554
```

Attempt 1 a genuine connection failure, attempt 2 a genuine 503 from a receiver brought back in a deliberate failure mode, attempt 3 a real delivery — the same shape handoff 06 proved for INT-05, and proven by actually stopping the process rather than mocking a failure.

---

## The bug that outage test found

Look at the last two lines above. `000000012345` had **already been issued to NRS-AST-047553.** The mock had been restarted and its in-memory sequence reset — and **Cadra accepted a SAP asset number already linked to a different asset, without complaint.**

That is a real hole, and a bad one. Handoff 02 made `asset_code` unique and NOT NULL on this reasoning:

> *"INT-06/07 assumes one asset per code. Without the constraint, two assets can share a code, and the reconciliation silently matches the wrong one."*

**That argument is symmetrical and only one side of it had been built.** Two Cadra assets sharing one SAP asset number is the same defect pointed the other way, and a worse one to find: it means finance's single asset master is claimed by two physical things, and the dual-code control reports both as `reconciled`.

Fixed, and the constraint proven to bite:

```
CONSTRAINT FIRED: SAP asset number 000000012345 is already linked to asset
NRS-AST-047553. An asset is complete only when both codes are linked, and that
control assumes one SAP asset master per physical asset — two assets sharing
one SAP number means finance has booked one thing and the register holds two.
```

**Why Python and not the database, which is a deliberate departure from handoff 02's precedent.** The key is the **triple** (`sap_asset_number`, `sap_company_code`, `sap_asset_subnumber`), not the number alone — a SAP asset number is only unique within a company code, which is the same reasoning that makes `company_code` a required field in the INT-07 response I specified in Part A. A `UNIQUE` index over three nullable columns enforces nothing on exactly the rows that matter today, because Postgres does not compare NULLs and the legacy extract will land asset numbers with no company code at all. **The true key depends on whether NRS uses more than one company code — which is an open question I asked SAP in §5.3 and have not had answered.** Once it is answered this should become a database constraint on the settled key. Until then the Python constraint catches every ORM path, including the integration, which is where the duplicate actually came from.

Checked across all eight tenants: `nrs19` held the one duplicate (mine), every other tenant zero. Repaired, and the asset re-posted cleanly to a fresh number:

```
 11919 | NRS-AST-047553 | 000000012345 | integration | posted | reconciled
 11920 | NRS-AST-047554 | 000000012346 | integration | posted | reconciled
```

The mock now persists its high-water mark so a restart cannot re-issue — a real SAP does not forget what it has issued, and neither should the stand-in.

---

## Part C — the dual-code control, made visible

`sap_reconciliation_state`, stored and indexed, four states:

| State | Meaning | A finding? |
|---|---|---|
| `reconciled` | Both codes linked | no |
| `not_tagged` | Not tagged, so INT-06 is not due | no |
| `pending` | Posted to SAP, awaiting the code | not yet |
| `exception` | **Tagged, and no SAP code** | **yes** |

Two ordering decisions carry the whole design:

**`reconciled` is checked first, on the presence of the SAP code alone.** A legacy asset linked to an existing SAP asset number is genuinely complete even though Cadra never posted it and may never tag it. Refusing to call that reconciled would turn this control's opening balance into twelve thousand permanent exceptions.

**`not_tagged` is not an exception.** INT-06 fires on tagging confirmed, so an untagged asset has no SAP code because it is not yet due one. Colouring that red would bury the 34 real cases on `nrs19` in 11,880 false ones — and an exception report nobody can read is the same as no exception report.

Delivered: a read-only reconciliation list view opening **on the exceptions** (`decoration-danger`), a search view whose first and most prominent filter is *Dual-Code Exceptions*, group-bys, an `ir.actions.act_window` with an auditor-facing help block, a menu entry, and a SAP block on the asset form.

The search view also carries a filter that is not obvious and matters: **"SAP Code Entered by Hand"**. A hand-typed SAP number and one SAP returned are the same string and very different facts, and an auditor sampling the register needs to isolate the claims from the evidence. That is what `sap_code_source` exists for, and a verification pass found it was freely writable — so a user could have relabelled a typed code as one SAP returned, defeating the distinction entirely. Now only the integration may claim `integration`; a person may still honestly record `manual` or `import`, which the legacy linking exercise in Part A §7 needs.

**API.** `data.sap` as a nested block of twelve keys — nested for the reason `provenance` is, since twelve flattened keys would be twelve new breaking-change surfaces on a contract Vendra builds against. Three filters, each of which errors rather than degrading:

```
sap_reconciliation_state=exceptions  -> 400  "`sap_reconciliation_state` must be one of: not_tagged, pending, reconciled, exception"
has_sap_code=1                       -> 400  "`has_sap_code` must be `true` or `false`"
has_sap_code=true                    -> 200  NRS-AST-047553 000000012345 integration reconciled
                                             NRS-AST-047554 000000012346 integration reconciled
```

The plural typo is the one that matters. `?sap_reconciliation_state=exceptions` answering `200 []` would tell an auditor there are no findings — the single most reassuring wrong answer this API can give. It is a 400 with `details.allowed_values`. The boolean is the same discipline applied to the half the CLAUDE.md backlog calls the dangerous one: an empty list reads as "no matches", an unfiltered list reads as an answer.

None of the SAP fields is in `_WRITABLE_FIELDS`, and the OpenAPI document describes the block read-only.

---

## Other defects found and fixed during this work

Four, all found by verification rather than theorised, and all in code written during this handoff except the last:

1. **`_set_sap_master` discarded every zero.** `if value not in (None, '', False)` — and `0 == False` is true in Python, so a SAP `net_book_value` of exactly `0.00` was silently dropped. A fully depreciated asset's net book value could never have been recorded. That is the exact inversion of the method's own docstring rule, *"absent and zero are different answers and only one of them is a figure"*.

2. **A refused INT-07 response left the asset at `posted`**, so a correlation failure read as `pending` — "awaiting SAP code" — for ever. A permanently pending row is the quiet failure this control exists to remove; it now drops to `exception`.

3. **A dead-lettered posting could not be recovered cleanly.** `action_retry_now` put the event back on the queue but left the asset at `failed`, so the reconciliation view called it an exception while it was actually in flight. An exception report with rows that are not exceptions is one people learn to ignore.

4. **The REST adapter built one URL from `rest_endpoint_event`.** INT-06 and INT-09 are different operations on different SAP endpoints, and every event would have gone to one path — a transfer arriving at the create-asset endpoint is a new asset master, not a change to the existing one. The event now says where it goes (`_endpoint_for_event`), with `asset.tag.affixed` falling through to the existing field so INT-05 is untouched.

---

## Tests

**Odoo suite** — `myservice_workflow` + `myservice_asset_register` on `test19`, after every change above:

```
2026-09-06 22:05:43,148 INFO test19 odoo.tests.stats: myservice_asset_depreciation: 16 tests 0.95s 527 queries
2026-09-06 22:05:43,148 INFO test19 odoo.tests.stats: myservice_workflow: 56 tests 4.92s 3423 queries
2026-09-06 22:05:43,150 INFO test19 odoo.tests.result: 0 failed, 0 error(s) of 66 tests when loading database 'test19'
```

22 new tests in `myservice_workflow/tests/test_sap_events.py` — the INT-06 trigger and its repeat-suppression, the payload's cost-basis branches, the null asset class, the five INT-07 response cases, all four INT-09 triggers including the transfer-suppression and the no-SAP-number skip, the four dual-code states, dead-letter → exception, the legacy reconciled case, and one proving an affix feeds both Vendra and SAP from their own targets with different `event_id`s. The 30 INT-05 tests from handoff 06 still pass unchanged.

**API suite** — full run, `CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q`:

```
....................................ssssssssss.......................... [ 27%]
.............................................ssssssss.ssss.............. [ 54%]
...............................s..............................s......... [ 82%]
............................................ss                           [100%]
============================ cadra api test report =============================
236 passed, 26 skipped in 64.44s (0:01:04)
```

19 of those are new (`tests/test_sap_reconciliation.py`); the skips are the expected admin-scope ones plus one real signal noted below.

`tests/test_source_guards.py`: 16 passed — no `_sql_constraints` reintroduced.

---

## Open questions and things I did not build

1. **The SAP-orphan half of the control is not built, and cannot be from here.** An asset row in Cadra always has a Cadra code (`asset_code` is NOT NULL), so *"a SAP code with no Cadra code"* is not representable as a row. Finding those requires the §3.3 reconciliation range query against a real SAP, which is exactly why Part A asks for it. Part C's build instruction covers the asset side and that is what is delivered; the other half is named in the requirements document rather than guessed at here.

2. **`sap_asset_number` uniqueness should become a database constraint** once NRS answers §5.3 (one company code or several). Reasoning above.

3. **`not_capitalised` has no distinguishable state.** SAP declining to capitalise is recorded in the delivery history and the asset's chatter, but the asset reads `pending` — "awaiting a code" — for a code that will never come. Building a fifth state now would be guessing at a response shape I have asked SAP for and not received; CLAUDE.md rule 4 says the model does not grow a value to match a document. It should be added the day §5.5 is answered.

4. **`sap_cost_center` and `sap_plant` are sent as null on every payload.** Deliberate, and Part A §5.2 says so. Cadra has `department` as free text with 808 distinct values and deriving a cost centre from it would be a fiction. A null gets rejected; a guess posts to the wrong cost centre and nothing about that looks like a failure.

5. **One API test skips for a real reason.** `test_sap_asset_number_is_exact_not_a_substring_search` has no positive-match coverage because no asset on `jaizbankplc` carries a SAP asset number. The filter is proven to return empty for a non-existent number and to over-match nothing, but the positive arm needs a tenant with the field populated. Not fixable from the API, which deliberately cannot write these fields.

6. **`workflow.config.sap_company_code` and `nrs.asset.sap_company_code` share a name and mean different things** — the tenant's own code sent outbound, and the code SAP returned. Not a bug, and the second is genuine confirmation of the first, but worth knowing before someone assumes they must agree.

7. **The local cron situation is unchanged from handoff 06.** `config/odoo.19.conf` still sets `db_name = odoo`, so no tenant cron fires on this machine and every live proof here was driven by a throwaway worker container. I have not changed it: doing so would silently start running the depreciation and PM crons against eight local databases, which is outside this handoff. Still flagged for a decision.

8. **Pre-existing, not introduced here:** `Field generic.location.building_id should be declared with recursive=True` warns on registry build. Confirmed it comes from the vendored CRND model and not from any field added in this work.

---

## Verification pass

A fresh agent that authored none of the code reviewed the diff against the handoff's acceptance criteria. It found items 1, 2 and 3 in *Other defects* above, and the `sap_code_source` writability hole in Part C — all four are fixed in `b1618b8`, and its findings are why the outage test was run in the shape that exposed the missing uniqueness constraint.

---

## Addendum — CI failed after the merge, and why my verification did not catch it

PR #50 was merged with `bootstrap-and-test` red. The cause was mine, in this handoff, and the way it evaded every check in the report above is the part worth recording.

**The fault.** `views/asset_sap_views.xml` declares the reconciliation menu, whose parent `menu_asset_root` is defined in `views/asset_menu.xml`. I placed the new file in the manifest's `data` list **before** that one. Odoo resolves an external ID against what is already in `ir_model_data`, so a cold install fails:

```
ValueError: External ID not found in the system: myservice_asset_register.menu_asset_root
while parsing /mnt/extra-addons/myservice_asset_register/views/asset_sap_views.xml:151
```

**Why everything above was green anyway.** An **upgrade** resolves the parent from the row a previous install left behind; only a **cold install** has nothing to resolve against. So:

- the eight-tenant fan-out passed — every one of those databases was an upgrade;
- `deploy-dev` on `dev` passed after the merge, because staging's databases already exist and the `cadra-upgrade` Job runs `-u`;
- the pytest and Odoo suites passed, because both run against databases that already exist;
- CI is the only thing in the pipeline that installs from nothing, and it was the only thing that went red.

The verification table in Step 0 is real and it could not have caught this. **I never ran a cold install locally, and that is the gap** — the handoff's acceptance criteria did not ask for one, and I did not think to add it. Note also the exact split in the CI history: the Part A docs commit (`029d5db`) passed; the code commit (`b1618b8`) failed. That was visible and I did not look at it before opening the PR.

**Why it mattered more than a red build.** Staging was never broken, so the visible damage was nil. The latent damage was not: **every tenant provisioned from that commit onward would have refused to install**, and CLAUDE.md already records that installing modules is the step people get wrong when standing up a tenant (*"Installing modules is not provisioning a tenant"*, handoff 04). It would have surfaced as a broken new-client deployment, a long way from the change that caused it.

**Fixed** in `b3b9cb8`, PR #51: the manifest loads `asset_sap_views.xml` after `asset_menu.xml`, with a comment saying why so it is not helpfully "tidied" back.

**Guarded**, because the instance is less interesting than the class. `tests/test_source_guards.py` gained `test_menu_parents_are_defined_before_they_are_used`: it walks each first-party manifest's `data` list in load order and fails on a `menuitem` whose same-module parent is not yet defined. Proven against the real regression rather than a synthetic one — with the broken order restored it names the offending file and menu; corrected, it passes.

One note on building it, because it is the kind of thing that makes a guard worthless. The first version compared each file against only what **previous** files had defined, and reported 20 false positives across five modules — Odoo processes a data file element by element, so a root defined at the top of a file is available to children below it, which is how nearly every menu file in this repo is written. It now walks in document order. A guard that cries wolf gets disabled, and then it is worse than not having one.

**Verified locally by doing what CI does**, on a fresh database, before and after:

- before: the `ValueError` above, exit 255 — the same failure CI saw;
- after: `75 modules loaded`, all 34 SAP external IDs present in `ir_model_data`, 12/12 SAP columns on `nrs_asset`, and CI's dead-`_sql_constraints` gate at 0.

Full API suite after the fix: `238 passed, 26 skipped`. `tests/test_source_guards.py`: 18 passed.

**For the next handoff:** an acceptance criterion of "the suite is green and the tenants are upgraded" does not cover a cold install, and the difference between `-i` and `-u` is exactly where this class of defect lives. A fresh-database install is cheap — two and a half minutes locally — and it is the only check that would have caught this before the merge.
