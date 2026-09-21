# Report 30 — Before the fourth twin

**Branch:** `feat/asset-events` · **Base:** `dev` at `e4bf1eb`. `dev` contained report 29's merge (PR #79, `4c291e9`) — the precondition you set — **and one thing you had not seen:** PR #80 (`8ad0011`, *an asset with no location can be placed*), owner-reported from the screen and merged at 08:46 this morning, four minutes before Step 0. It changes `/move`, which §B touches. I read it before building on it; it is consistent with everything here.

**Needs the owner:**
1. **The PR merge.**
2. **A deploy to any server carries a schema change.** `nrs.asset.event` is a new table; `myservice_asset_register` → `19.0.1.16.0`, `myservice_api` → `19.0.3.10.0`. All eight local databases are upgraded (§6). On staging the `cadra-upgrade` Job must run before the new code serves a request, or every change of status answers 500 for want of a table.
3. **GitHub billing — still yours, still escalated.** Everything below was run locally.

**Two published-contract changes, both ruled by you, both BREAKING for a caller who relied on the old behaviour** — §4.

---

## 1 · One model or four — the case, both ways

**My answer: one model for the three that did not exist yet, and leave custody and movement exactly where they are. Two tables stay, one is added, and the guard is written once. Not four, and not one.** I built that, because the three were ruled regardless; what I did **not** do is touch the two live models, because that is the question you asked to rule on. The case follows, including the half that argues against what I built.

### What the twins actually share — read, not assumed

I read both end to end. They share, line for line: `asset_id` with `ondelete='restrict'`; an instant; the actor's id **and the name as recorded**; a before and an after, each as an id **and a name as recorded**; a `reason`; a `source` selection; the three guards (`create` refuses without a context flag, `write` and `unlink` raise unconditionally); `_resolve_source`; `_record` as the only writer; and an override in `myservice_api` that relabels a test credential's rows `test`.

They differ in exactly three things: the foreign-key target of before/after (`hr.employee` / `generic.location`), movement's link to a transfer document, and two `source` values each.

### The argument for one model — and the evidence is in this handoff

**§D3 is the argument.** Custody was written on 9 September (`48ba659`) with a `source` any caller could claim through the context. Movement was copied from it in handoff 28 (`1510114`) — and the copy was written *without* the hole. **The copy was fixed and the original was not.** So for twelve days anybody able to change a custodian could file a real change of custody under `test` or `tracking_backfill`, and from the moment movement landed the same rule had two answers. Nobody decided that; it is what two copies of a safety rule do.

And the two `myservice_api` overrides — which are supposed to be the same derivation — **are not the same code**: custody's goes through a forwarder method, movement's inlines the lookup. Harmless today. It is how the two answers start to differ.

**Every new pinned table is paid for in seven kinds of place — eleven edits**, which I counted by finding where movement is named: three access-rule lines; two owner-run scripts that must refuse on it *by name*; a seed-script destroy flag; two source guards; the `myservice_api` override; a history adapter; a `copy=False` field. A third, fourth and fifth table would have paid that three times. One model paid it once.

### The argument against — the costs you said you could not see

**1 · The migration is small in rows and large in what it touches.** Measured at 09:00 today on all eight databases, **before this handoff's own suites ran** — `test19` grows with every run (by the end of the day: custody 308, movement 595), and the other seven do not:

| | custody rows | of which `test` | of which reconstructed | movement rows | of which `test` |
|---|---|---|---|---|---|
| `cadra19`, `nrs` | 0 | — | — | 0 | — |
| `nrs19` | 5 | 0 | 1 | 1 | 0 |
| `gtb19` / `lasg` / `gtb` | 152 / 150 / 150 | 0 | all | 0 | — |
| `test19` | 293 | 283 | 0 | 419 | 413 |
| `jaizbankplc` | 591 | 352 | 221 | 0 | — |
| **total** | **1,341** | | | **420** | |

1,761 rows. The row count is not the cost. **The cost is that these are the two tables whose whole value is that nobody rewrites them, and a migration is a rewrite.** It has to go round the guards with raw SQL; it has to preserve `create_date`, because *"recording began at"* is measured as `min(create_date)` and the ORM would stamp every migrated row with the migration's instant — which would tell every auditor that custody recording began this week; and an error in it lands in a table that refuses correction by design. Every one of those is solvable. Each is a place to be wrong in the one model where being wrong is permanent. And then the old tables: dropping an append-only audit table is the act the design forbids, and keeping them frozen makes three tables, not one.

**2 · The ids are published, and they would change.** `custody_change.custody_id`, `data.movement_id` — which PR #80 moved to the top level *this morning* — every row of `GET /assets/<id>/custody`, and every history event's `id` and `record: {model, id}` carry these ids and these model names. Two sequences merged into one table collide, so every custody and movement id on every tenant changes, and `record.model` changes its published value. `nrs.asset.custody` is named in **19 files under `docs/`**, among them `INT-10-audit-access.md` — the contract an external auditor reads — and the endpoint reference. That is a breaking change to the audit contract to tidy our own schema.

**3 · Does a shared table weaken the per-type guarantees? Less than I expected, and in one specific way.** Today *nothing* in either twin is `NOT NULL` beyond the asset, the instant and the source — before and after are both nullable, because *from nowhere* and *to nobody* are real. So there is no database constraint to lose. **What a shared table does lose is the column's type**: `from_custodian_id` can only ever hold an employee, and a generic `from_value` can hold anything. I answered that in the new model with `_PAYLOAD_OF_TYPE` — a table of which keys each type may carry, enforced in `_record`, so a status change cannot arrive carrying verification notes. It is a Python guarantee, as all of this is. For the three new types it costs nothing, because their before and after are *not* foreign keys: a status key, a date, a reference string. **For custody and movement it would cost the foreign keys** — or five sparse nullable ones on every row. That is the real weakening, and it applies only to the two I left alone.

**4 · Does it make the history simpler or the queries worse?** *Simpler, modestly; worse, not measurably.* One adapter was written where there would have been three. But the history was a merge of seven sources before this and is a merge of eight now — chatter, tags, transfers, dispatches and requests are not going anywhere — so that is two adapters saved, not a rewrite. Queries gain a `type =` predicate, and both `asset_id` and `event_type` are indexed. I have no measurement of how fast the table will grow and am not going to offer one: every local register is a demo or a fixture, and the rate at which NRS verifies assets is a fact about NRS. **The one thing a shared table genuinely makes easier to get wrong is *"recording began at"*, which is per type** — a database whose first status change was recorded today did not begin recording verifications today. `recording_began_at(event_type)` takes the type as a required argument for that reason, and a test holds it.

### So: two and one, and the guard once

- **`nrs.asset.event`** — one model, four types: `verified`, `verification_date_set`, `status_changed`, `reference_changed`.
- **`nrs.asset.append.only.mixin`** — the three guards and `_resolve_source`, written once, and the test-credential relabel extended **on the mixin**, so a future append-only record cannot be written without it.
- **Custody and movement: untouched, apart from §D3's four lines.**

**What I am asking you to rule:** whether custody and movement should *adopt the mixin*. It defines no fields, so it needs **no migration, changes no id and no published name** — it is about ten lines per model, and it would have made §D3 impossible. It is the cheap half of "make them one", and I think it is right. **I did not do it, because it is a change to two live audit models that nobody has ruled**, and doing it in the same handoff that asks the question would have been answering it for you. Bringing their *rows* into the event table I recommend against, for costs 1 and 2.

**One thing I changed my mind about while building, which you should know.** My first draft had one `verified` type and used `source` to say whether the actor had checked the asset or merely written a date. Then the first real call came back `source = test` — the credential relabel overwrites it, as it does for custody. *The difference between "Ada checked it" and "a date was written" was being carried by a label that something else is entitled to erase.* They are now two types. Found by acting, not by reading.

---

## 2 · What may be done to a disposed asset — the table

**The rule is `nrs.asset._assert_disposed_is_terminal`, called first thing in `nrs.asset.write`, before anything is written.** It is in the model for the reason you gave, and I checked the reason rather than take it: **every writer of `state` passes through the ORM** — no `_write`, no raw `UPDATE nrs_asset SET state` anywhere outside `dist/`, no server action, no cron. The guard sees all of them.

**There were two open doors, not one.** The PATCH you named — and `nrs.asset.transfer.action_complete`, which writes `'state': 'active'` *unconditionally*, so completing a transfer on a disposed asset un-disposed it without anybody asking. It now raises and leaves the asset disposed.

### Status → status

| from ↓ · to → | `active` | `in_repair` | `missing` | `transferred` | `disposed` |
|---|---|---|---|---|---|
| **`active`** | — | allowed | allowed | allowed | allowed |
| **`in_repair`** | allowed | — | allowed | allowed | allowed |
| **`missing`** | **allowed** — it turned up | allowed | — | allowed | allowed — written off |
| **`transferred`** | allowed | allowed | allowed | — | allowed |
| **`disposed`** | **REFUSED** | **REFUSED** | **REFUSED** | **REFUSED** | no-op, allowed |

**Every allowed change writes one append-only `status_changed` event**, with the keys before and after, the actor, and the reason where one was given. **I restricted nothing you did not rule.** The only rule with a ruling behind it is the bottom row, and inventing the others — *may an asset under repair go missing?* obviously yes; *may `transferred` become anything?* — would have been me legislating a lifecycle from a Python file. Two things I measured instead of deciding: **before this handoff's tests ran, no asset on any of the eight databases was `in_repair` or `transferred`** (`test19` now holds two `in_repair` fixtures, written by the new test file), **and nothing in the code ever writes `transferred`** — it is published, filterable, and has no producer. It is report 29's dead-status class. I left it, because removing a published enum value is a breaking change and it was not what you asked.

### Everything else, on a DISPOSED asset

| Act | Answer | Why |
|---|---|---|
| Mark missing | **refused** — 409 on the route, 400 on a PATCH | ruled |
| Move / place | **refused** — 400, and **no transfer row is left behind** (read from Postgres: 0 transfers, 0 movements, 0 custody links after four refused calls) | ruled. Handoff 28's refused `/move` left a `done` transfer; this one cannot, because the refusal is an exception and an exception rolls back |
| Change custodian / transfer custody | **refused** — 400 | ruled |
| Condemn again | **refused** — 409 | disposal is terminal |
| Re-send the SAME status, location or custodian | allowed | the app's edit form re-sends them on every save; refusing would make a disposed asset's notes uneditable |
| Edit the disposal paperwork, the notes, the costs | allowed | a disposal's method, reference and proceeds are completed AFTER it is disposed |
| Approve the disposal | allowed | it requires `disposed` |
| SAP master sync (INT-07), depreciation figures | allowed | they arrive after |
| **Verify** | **allowed — and not ruled. Your call.** | see below |
| Register an asset as ALREADY disposed (`POST /assets`) | allowed | a legacy import of things already gone. It writes no event — an event is a change — and the registration is the record |

**Verify, on a disposed asset, I left open deliberately.** Your ruling was *"not missing, not moved, not a custody change"*. The Odoo form already hides Verify on a disposed asset; the app still offers it. I did not refuse it in the model because of what a refusal would hide: **a disposed asset that somebody physically finds on the premises is an audit finding**, and a register that refuses to record *"I saw it, today"* is suppressing the one fact that matters. If you rule it refused, it is one line in the same method.

**One wrinkle the rule creates, which I found and did not fix.** When an employee leaves, their assets are flagged for retrieval; *Mark retrieved* clears the custodian. A disposed asset still assigned to a leaver is flagged like any other, and can now never be marked retrieved — the rule refuses the custody change. It is one button on one asset answering with a plain sentence, and nothing automated calls it, so nothing breaks. But the leaver's clearance list will show an asset nobody can retrieve. The honest fix is for the exit flow not to flag disposed assets; it is in `myservice_identity` and I did not widen the handoff to it.

### What un-disposing should mean — you asked me to say before building

**The honest answer is the one you offered: nobody has ever needed this. So it is refused outright, and I built no way round.**

I measured it rather than assert it. The tracked history of every asset on all eight databases holds **one** transition out of `disposed`:

```
NRS-AST-047641 | Dell Latitude 5450 (E2E-0915223412HQJ9-1) | Disposed → Missing | 2026-09-20 19:37:32 | Administrator
```

An `E2E-…` fixture, on `nrs19`, the evening before report 29. **That is handoff 29's own probe — the act that discovered the hole.** Every other state change on `nrs19` is on that asset or one other, all by Administrator, all in the last two days. No real asset has ever left `disposed`.

**There is no context flag round the rule, on purpose:** a context is something an RPC caller sets, so a flag would be a way round that anybody able to call `write` could use.

**The one case I can construct is a mistake** — somebody condemns the wrong asset. Today the only cure is SQL. If that ever happens and you want a door, this is what I would build, and I have not: a **reversal as a recorded act** — `action_reverse_disposal(reason)`, asset-manager group only, `approvals:write` over the API; reason required; writes a `status_changed` event `disposed → active` with its own `source`, so the history shows the disposal, the reversal, who, and why, all unalterable; **refused once the disposal has been approved**, because an approved disposal has been authorised by somebody else and undoing it is not the condemner's to do; and the register afterwards says `active` with both events in its history — it does *not* erase the disposal date or reason silently, it clears them and the event carries what they were. Until somebody needs it, a register that cannot un-dispose is the stronger register.

---

## 3 · A rejected field: 400, or 200 with a warning

**My recommendation: 400. And the argument is not mine — it is in Vendra's source, which I read before writing this.**

I expected to recommend caution, on the grounds that Vendra is live and a 400 would stop receipts landing. Then I opened `vendra_network/integrations/cadra/client.py`. **Vendra already treats a rejected field as a hard failure.** `_raise_on_rejected_fields` runs after every `create_asset`, and raises `CadraSchemaRejectedError` — terminal, dead-lettered. That error's `remedy` text — what Vendra shows its own operator — is the case for the 400, written by the consumer:

> *"Cadra ACCEPTED this write and dropped fields from it — **the asset exists in the register, incomplete**. … retrying as it stands replays the same 201 and drops the same fields."*

**That is what the 2xx actually costs.** Vendra refuses the response — *after* Cadra has created the asset. The register now holds an asset the sending system has rejected, missing whatever field was dropped, and the idempotency key pins it: a retry replays the same 201. Somebody has to find it and repair it by hand. **With a 400 nothing is created**, the mapper is fixed, the same receipt is re-delivered, and the asset lands whole. The only consumer we have is paying for the lenient answer and getting nothing from it.

Three more, in our own code:

1. **A `PATCH` whose every field is refused answers 200 and writes nothing at all** — `if not vals and not rejected` lets it through. That is the `asset_tag` case exactly: typed, saved, 200, unchanged.
2. **The precedents all point one way.** A filter that cannot be read is a 400 with `allowed_values` (handoff 21). A body naming an approver is a 400 carrying `details.rejected_fields` (handoff 23), and its docstring calls a 200 there *"the answer that looks like an answer"*. The three settings routes already answer 400, with a `writable` list, when nothing writable was sent. Assets, locations and requests are the ones left behind.
3. **Rule 3 of `CLAUDE.md` already calls it a defect**: *"Anything that silently degrades — a dropped field … — is a defect even when it returns 200."*

**What I would want ruled alongside it, because they are the real cost:**

- **It is BREAKING and should be announced, not slipped in** — which is why I did not make it. Ten routes across four controllers produce the warning today.
- **The shape:** `400 invalid_request`, `details.rejected_fields`, and `details.writable` naming what *is* accepted — the settings routes' shape, so a caller can repair itself from the response.
- **The one argument for leniency is forward compatibility** — a consumer that starts sending a new field before we accept it. I do not think it outweighs the above: that consumer is *wrong about our schema*, and the sooner it is told the better. But it is a judgement about how we want integrators to meet us, and it is yours.

**What I built instead, as ruled: the app surfaces it** — §5. And **`building_id`, `floor_id` and `room_id` are out of `_WRITABLE_FIELDS`**, with a step the handoff did not name. You sequenced it *surface first, then refuse*, so the refusal would not be silent. **There was a third step:** the only live sender of those three fields was *our own edit form*, which has no input for any of them — it read them out of the response's `location_hierarchy` and echoed them back on every save (verified at `HEAD`, `AssetForm.tsx:129-131` and `:274-276`). Done in your order, the new warning would have fired on **every edit of every located asset**, for three fields the user never touched. The echo is removed in the same change. Vendra sends none of the three (checked in its `payload.py`), and no test, script or document of ours did.

---

## 4 · What §D4 measured — `sap_reconciliation_state = exception`

**It is real, it is live, and every row that carries it is a fixture. Both halves matter, so I wired it.**

**What puts it there.** Nothing *writes* it. It is a stored compute over three fields, with no clock and no cron: **a tag is physically affixed, there is no SAP asset number, and no posting to SAP is in flight.** The model's own words: *"Finance has not booked a physical asset that demonstrably exists: an audit finding."*

**How many, and where** — read from all eight databases at 09:00, before this handoff's suites ran (`test19` has since grown to 192; it grows with every run):

| | `exception` | `pending` | `reconciled` | `not_tagged` |
|---|---|---|---|---|
| `nrs19` | **34** | 18 | 2 | 11,889 |
| `test19` | **184** | 0 | 0 | 1,415 |
| `jaizbankplc` | **593** | 0 | 0 | 3,571 |
| `cadra19`, `gtb19`, `nrs`, `lasg`, `gtb` | 0 | 0 | 0 | all |

**What the 811 are.** I grouped them by name and by who created them, because the fixture flag only dates from handoff 26 and is null on most:

- **`nrs19`, 34** — every one created on 5–6 September. **29 are handoff 04's demo assets** (25 *"Dell Latitude 5450 (DEMO-…)"*, 4 *"HP LaserJet Pro M404dn"*); **the other five are handoff-05 and -06 probes** (*"Handoff05 separation proof"*, *"post-verification recheck"*, three *"INT-05 transport probe …"*). It is the *"34 real cases"* the model's docstring cites and report 07 quoted — **and not one is real.** *(My first draft said all 34 were handoff 04's and named two products; the verification pass ran the SELECT and found five that were neither.)*
- **`test19`, 184** — all `pytest-*`, all by the test credential.
- **`jaizbankplc`, 593** — 585 `pytest-*`, 8 others; on a register that is 88% fixtures.

**So: not one real asset on any database carries it. That is not the same as dead, and the difference is the ruling.** The three statuses handoff 29 deleted could not be *reached* — nothing in the system could put an asset in them. This one is reached by the most ordinary act in the programme: **the day a real NRS asset has its tag affixed and finance has not booked it, it fires.** Every row is a fixture because on these databases only fixtures have ever been tagged. The mechanism is sound and has simply never met real data.

**What I would not want quoted:** *"811 assets need SAP reconciliation."* Zero do. What is true is that the control works and has an opening balance of zero.

**Wired as a second review status** — *Review — no SAP code* — in the pill, the dashboard and the register's Status filter, which maps to `?sap_reconciliation_state=exception` **server-side**, so choosing it returns the real rows. Handoff 29 deleted three statuses precisely because choosing them returned nothing and said nothing; this one returns every active exception on the tenant — 184 on `test19` when measured — and a browser spec holds that each row listed wears that pill.

---

## 5 · What was built

**§A — `nrs.asset.event`.** Four types. Written in `nrs.asset.write`, under every writer, as the two before it. *Every* `action_verify` is an event, including a second on the same day, which changes no date and used to leave nothing. A change of status carries its reason; the reason for *Mark missing* lives there and **is not a field on the asset**. A change to `grn_reference`, `purchase_order_reference` or `sap_asset_number` carries the value before and after, as recorded. I checked all three references have only ORM writers — the INT-07 setter, the importer, the form — before putting the recorder there.

**An event is a CHANGE, so creating an asset writes none.** A deliberate difference from custody and movement. Every asset has a `state` from birth; recording it would pin every asset ever created, for a row that says only that it was created.

**The history reads them, and lists each act once.** The message-log line of the same act is folded into the event — by transaction, as movement's is. Three published `not_recorded` statements and `fidelity.verification` **were made false by this handoff and are reworded**; a fourth, `deleted_records`, said *"only a change of custodian is protected from deletion"* and **had been false since handoff 28**. `fidelity.events` says, per kind, from when.

**§B** — §2. **§C** — §3, plus: the app shows `_warnings` for every write, at the one function every write passes through, as a notice that stays until dismissed. **§D1** — the reference is published to a holder of `requests:read`, and `reference_withheld` says when it is not; the scope rule was *extracted* from `require_jwt` rather than copied, so the gate and the shaping ask one question. **§D2** — `/condemn`, below. **§D3** — four lines. **§D4** — §4.

### §D2 would have moved the bug it was ruled in to kill

You wrote that `/condemn` *"kills the one-hour-a-night bug at its source"*. **As specified it would have relocated it to the server, where handoff 29's fix could not reach it.** `action_condemn` stamped `context_today`, which resolves the acting user's timezone and falls back to UTC — and **every API credential's user has no timezone** (read from `test19` and `nrs19`). Today the app sends the browser's local date, which is right for somebody in Lagos. The route as described would have dated every disposal made between 00:00 and 01:00 in Lagos to the day before. It now stamps `snapshot_today()` — the register snapshot's definition of the day, so a disposal and a snapshot asked for that day cannot disagree. A test freezes the clock at 23:30 UTC and asserts tomorrow's date.

### Two things found because §C was closed as a class

1. **A category's depreciation method could never be changed from the Depreciation settings screen.** The API publishes it as `method` and accepts it as `depreciation_method`; the screen echoed `method`; the API refused that one field, saved the three numbers beside it, answered 200, and the screen said *"policy saved"*. Proved against `test19`: what the screen sends → `200 rejected_fields: ["method"]`. **It is `asset_tag` again, on a different screen, and nobody knew** — found by the front-end pass on the day the warnings became visible. Fixed, one translation at the API boundary. *That is the argument for §3 in one bug.*
2. **The terminal rule made an existing control dangerous.** The edit form's State dropdown offered *Disposed* for a live asset. Yesterday a mis-click was undone from the same dropdown. Today it would have been permanent — no confirmation, no reason, no date. Removed on edit, with a line pointing at Condemn; kept on create, where registering something already gone is legitimate.

---

## 6 · Tests — denominators first

```
# CI's order: the HTTP suite FIRST, against test19 (marked `test`; credential flagged is_test_credential).
$ CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
942 passed, 8 skipped in 158.83s          # the FINAL run, after the verification pass's fixes
#   The first full run was `2 failed, 939 passed, 8 skipped`. Both failures were in the NEW file
#   and both were the TEST's: one compared `details` exactly, and the envelope adds `http_status`;
#   the other asserted the literal "`fidelity.events`" in a published sentence — written against
#   my first wording, which a standing test had refused (§7).
#   8 skipped is this tenant's known figure and the same eight categories (CLAUDE.md).
#   60 of the 942 are the new file, tests/test_asset_events_api.py.

# then the in-registry suites — CI's command, all eleven modules, --workers=0:
$ odoo -d test19 -u <CI's 11 modules> --test-enable --stop-after-init --workers=0
0 failed, 0 error(s) of 733 tests when loading database 'test19'      # the FINAL run
#   grep 'of 0 tests|CRITICAL' → 0.   The denominator reconciles at every step:
#   615 before  + 88 event + 4 custody + 19 history = 726 (first run, also 0 failed)
#   726         + 7 written for the verification pass's findings        = 733.
#   I counted the new tests in the log rather than trust the total: 88 event tests STARTED.

# the static guards (no server):
$ pytest tests/test_source_guards.py tests/test_recorder_bypass_guard.py tests/test_query_param_guard.py -q
228 passed        # BEFORE the guard was taught the new model: 1 failed, 221 passed —
                  # `nrs.asset.event` reported as creatable and unlabelled. The guard works.

# the browser, against test19 — NOT the default. `e2e/config.ts` defaults to jaizbankplc,
# a client's replica; the suite is outside the database-class guard (GO-LIVE §13.4 item 6).
$ E2E_ORIGIN=http://test19.localhost:8069 npx playwright test
2 failed · 4 skipped · 131 passed          # twice: before and after the verification fixes
#   The two failures are the two GO-LIVE §13.5 item 13 already records as failing on `dev`:
#   "a computed asset charts its value over time" · "the straight-line switch persists across a reload".
#   Still not investigated, and NOT touched by the depreciation fix above — the second is the
#   register-wide recompute toggle, a different control.
#   All 12 new or rewritten specs passed; none skipped. The Status-filter spec returned real rows.
```

**One guard proved to fail first.** A refused `/move` rolled its transfer row back but not the `ir.sequence` number, so every refused move left a gap in the transfer references that no transfer explained. The route now asks the model's rule before drawing one. With that line removed the test fails — *"the refused move consumed transfer reference(s) [227]"* — and with it restored it passes.

**Acted, before any test existed.** Every new and changed route, by hand, against `test19`, then the rows read from Postgres: after four refused calls on a disposed asset — **0 transfers, 0 movements, 0 custody links.**

**The fan-out — read from each database, not from exit codes:**

```
db           | register   | api         | event table | write/create/unlink grants on it
cadra19      | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
nrs19        | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
gtb19        | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
test19       | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
nrs          | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
lasg         | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
gtb          | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
jaizbankplc  | 19.0.1.16.0 | 19.0.3.10.0 | t | 0
```

Eight upgrades, one at a time, each `exit=0`, zero `ERROR`/`CRITICAL`. **Schema before code:** the owner was using `nrs19` from the screen this morning, so every database was upgraded *before* Odoo was restarted onto the new Python — an extra table is harmless to the old code, and a missing one is a 500 to the new.

---

## 7 · What the verification pass found

A fresh reviewer, not an author, over the whole diff. **It found no route that validates after writing, no idempotency defect, and no ORM write that gets a disposed asset out of `disposed`. It found one real hole in the rule, one document I had not opened, and four claims of mine that were wrong.** Everything below is fixed unless it says otherwise.

**1 · BLOCKING — `INT-10-audit-access.md` was untouched, and its evidence table had become false.** Report §1 calls it *"the contract an external auditor reads"*, and I updated the endpoint reference's copy of that table and not the contract's. Worse, parts of it were **already stale before today**: it still listed the GRN and PO references as untracked (handoff 28 tracked them) and said `last_verified_by` was not published (handoff 28 published it). Corrected, with dated notes; the old text is left readable where it records how things stood.

**2 · "Disposed is terminal" was not true through every door — and I had written that it was, in four places.** `location_id` and `custodian_id` are both `ON DELETE SET NULL`. Deleting a location — or its parent, by cascade — moved every disposed asset in it to nowhere, **and deleting an employee un-assigned them, with no `write` at all.** `generic.location.unlink` and a new `hr.employee.unlink` now refuse when a disposed asset names the record, and offer archiving. **The second also closes custody's twin of the hole handoff 28 closed for location**: deleting an employee who holds live assets now appends the custody link the database used to make silently. I had *found* that hole myself an hour earlier, read the foreign key, written it into the register as "noted, not touched" — **and not connected it to the rule I was building.** The reviewer did, by asking whether *"through any door"* was true.

**3 · The published OpenAPI strings for `actor_name` and `source`** said they were populated only on a custody event. False for movements since handoff 28, and wider today. Reworded; `fidelity.events` added to the schema's description.

**4 · I described the 34 `nrs19` rows wrongly** — "every one" handoff 04's, naming two products. The reviewer ran the SELECT: 29 are, five are handoff-05/06 probes. The conclusion stood; the sentence did not. §4 carries the correction in place.

**5 · My "measured today" tables had gone stale by the afternoon, because my own suites moved `test19`** — custody 293 → 308, movement 419 → 595, `exception` 184 → 192 — and *"no asset anywhere is `in_repair`"* stopped being true when my new test file wrote two. Every table now says when it was measured.

**6 · The register's count ran ahead of its rows.** Under *Cleared* and *Review — data quality* the server count included the active SAP exceptions, which the page then drops: about 190 too many on `test19`, nearly 600 on a register like `jaizbankplc`. The front-end author had flagged it — **in a code comment.** Fixed: the overlap is subtracted, one extra `limit: 1` read.

**7 · `event_id` was "the newest of that type", not "the one this call wrote".** Unreachable today and one refactor from publishing somebody else's verification as the record of yours. It now takes the newest id *before* the action and returns only a row written after it.

**Also fixed:** a same-date PATCH over a standing verifier cleared them and recorded nothing, leaving a message-log line titled *"Verified"* for an act that removed a verifier · `action_condemn` over the ORM on an already-disposed asset overwrote the reason given at the time, with no event · two e2e assertions sat behind a bare `if` and could pass having asserted nothing · the Vendra quote is that error's `remedy` text, not a docstring.

**Registered, not fixed** — GO-LIVE §15.3: a verification is still dated by the UTC day, and that date is now frozen in an append-only row (the event's `occurred_at` is exact; the asset's date column is what is a day out, and it is tied to a stored compute that is UTC on purpose) · the Odoo form's buttons ask for no reason · `PATCH {"state": "disposed"}` still disposes and stamps nothing · an approved transfer of an asset later condemned can never be completed.

**Found by the authors, before the reviewer:** the in-registry author refused to weaken a standing test that caught my reworded sentences containing the literal `` `fidelity.events` `` — text a client reads on a screen. The HTTP author found the burned transfer reference and the latent UTC fallback in depreciation's `action_condemn`. The front-end author found the depreciation-method bug (§5) and caught four errors of its own, including reporting *"tsc exit: 0"* when it was `head`'s exit code.

---

## 8 · Wall-clock and the correction share

**About 1 h 35 min of work across six hours on the clock.** Step 0 at 08:50. At about 09:40 the session hit its usage limit and everything stopped — including the first verification reviewer, which died having read one file. Resumed at 14:05 on the owner's *proceed*; the last green run finished at 14:45. Roughly 4 h 25 min of that was idle. Both numbers, because the first is an estimate and the second is not. *(The first draft of this paragraph said 15:20. The clock said 14:46. See item 2 below.)*

**Correction share: a little under half, and again almost none of it was found by a test I had written beforehand.** In the order it cost time:

1. **The verification pass** — one blocking, six should-fix; seven more tests; a third full run of all three suites.
2. **Claims I wrote before checking them, and then checked** — *"a month apart"* (it was twelve days, and I had put it in two code comments as well as this report); *"nine places"* (my own list added up to eleven); section numbers §3.11 and §3.12, which do not exist; an invented growth estimate. **Five, counting the time in the paragraph above — caught by me, all after I had typed them as fact.** That is your rule again, and the habit is evidently not broken by knowing it.
3. **`verified` with a `source`** became two event types, after the first real call came back `source = test`.
4. **The Lagos day** — not a correction of mine but of the handoff; it cost a read of the snapshot module and a check of two databases.

**What I would tell the next Builder.** *The most useful question anybody asked today was "is that sentence true?"* — of *"through any door"*, of *"kills the bug at its source"*, of *"policy saved"*. Each was false, each was somebody's confident summary, and each was settled in under a minute by opening one file or running one SELECT. And: **read the consumer.** I was about to recommend caution on the 400 out of respect for Vendra, and Vendra's own source said the opposite.

---

## Questions

1. **Should custody and movement adopt the mixin?** §1. No migration, no id changes. I recommend yes.
2. **400, or 200 with a warning?** §3. I recommend 400, announced; ten routes.
3. **May a disposed asset be verified?** §2. Allowed today, on purpose.
4. **Should the MODEL stamp the disposal date and condition for every writer into `disposed`** — so that `PATCH {"state": "disposed"}` cannot make an undated disposal? `/condemn` is the proper door and did not close the other. It would change what the disposal report's `no_disposal_date` finding means.
5. **`transferred`** — published, filterable, selectable, and nothing writes it. Remove it (BREAKING), or give it a producer?
6. **A found asset has no reason.** *Mark missing* takes one; *it turned up* is a PATCH and cannot. `POST …/mark-found`?
7. **The leaver's disposed asset** can never be marked retrieved. Should the exit flow stop flagging disposed assets?

## Commits

- `e4bf1eb` — docs: handoff 30 — before the fourth twin (the instruction file, on `dev`)
- `6658e9f` — feat: before the fourth twin — what happened to an asset, recorded so nobody can alter it; disposal is terminal
- this report, in the commit after it
- **PR #81** — https://github.com/wmlmetro/Cadra/pull/81 — `feat/asset-events` → `dev`. The merge is the owner's.
