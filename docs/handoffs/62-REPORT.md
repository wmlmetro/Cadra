# Report — Handoff 62: the state, told

Branch `feat/the-state-told`, from `dev` at `ca742d9`, rebased onto
`d250319` (below). Step 0: the instruction file and `docs/AI-CAPTURE-EVALUATION.md`
§4's renumbering (SAP mirror 62 → 63, audit capture 63 → 64, with a dated
note) committed on `dev` as ONE docs commit (`ca742d9`), pushed, then the
branch. Handoff 61 was already merged (`f3f75f6`); the module versions on
all eight local tenants matched it, so no catch-up upgrade was needed.
Module version: `myservice_workflow` 19.0.3.3.0 (one new column).
`myservice_asset_register` changed Python only (no version bump).

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
2. **The deploy, in this order** (GO-LIVE §31.2):
   1. `deploy-dev`, then `upgrade-19` with `target_dbs=staging,gtb,jaizbankplc,lasg`,
      `upgrade_modules=myservice_workflow`, `scale_down=true`. There is one
      new column (`workflow_config.rest_endpoint_register_state`); a tenant
      running the code without it fails every gate move and every affix
      (each reads the Vendra target) with `503 server_misconfigured`, so
      schema before traffic. Then `https://<tenant>/api/v1/meta/readiness`
      must say `"ready": true`. **Nothing is sent yet** after this step.
   2. Vendra handoff 57 deployed: its receiver **and the receiver's path in
      Vendra's `auth_hooks`** (Frappe answers 401 before routing for any
      bearer request on a path no hook authenticates — the verification
      pass's finding, below).
   3. **Only then**, on each cluster tenant whose Vendra has the receiver:
      back office → *Workflow → Integration Settings* → the *Vendra (INT-05
      asset events)* target → **Register-State Endpoint** =
      `/api/method/vendra_network.api.cadra.register_state_event` (or the
      name Vendra 57 gives it). Setting it before Vendra's receiver and its
      hook entry exist dead-letters every move on its first attempt (§4.2:
      Vendra answers `401`).
3. **A decision for the Architect, not the owner, but before go-live:**
   how long Cadra keeps trying (§5, GO-LIVE §31.1).

## In plain words

When Internal Audit rejected one of Vendra's units, queried it, or a
receipt's last unit reached the register, nobody in Vendra found out until
someone opened the receipt. Vendra's last report designed one small message
that fixes that, and this handoff builds Cadra's half of it exactly as
designed.

- **Every time one of Vendra's units moves, Cadra tells Vendra.** One
  message per act: who acted is never in it ("Internal Audit", not a name),
  only which unit, which receipt, where it now stands, whose move it is,
  and since when. A query and a rejection carry Internal Audit's own words;
  the last step carries the SAP asset code. A unit takes seven acts to reach
  the register, so Vendra hears seven times; land and software take five.
  A batch of twenty is twenty messages.
- **It travels the road Vendra already trusts.** The same connection,
  password, queue, retries and failure handling as the "tag affixed"
  message, which had delivered 999 of 999 from `test19` when this work began. A move that is
  undone never sends anything, because the message is written in the same
  step as the move.
- **The times always go forward.** Vendra keeps whichever message has the
  latest time on it. Two moves often happened in the same second — in a
  test walk all seven did — so Cadra now makes each move of a unit at least
  a second later than the one before.
- **Vendra cannot receive it yet, and says so with "401".** Its receiver is
  Vendra's next handoff — and it must also tell Vendra's sign-in check to
  let Cadra's password through on the new address, or the answer stays
  "401" even after the receiver is built. So the new setting that says where to send it is
  switched on only on the test bench, and should be switched on elsewhere
  only after Vendra has the receiver.
- **If Vendra is down for a whole day, the day's messages are given up
  on.** Cadra tries for about two hours per message, then marks it failed
  and notes it on the asset. Measured: a working day's 490 messages, all
  490 failed. Anything raised in the last two hours before Vendra returns
  gets through, within an hour. Recovering the rest used to mean opening
  each failure one at a time; now a person selects them all and presses
  *Retry Delivery* once. Whether two hours is long enough is the
  Architect's call.
- **Vendra's builder now has a tool to walk units through Cadra's steps**
  on the test bench only, as the seven demo people, printing each step.
  It refuses the live and client systems by name, before it touches
  anything.

---

## Step 0

- `git checkout dev && git pull --ff-only` (fast-forward to `f3f75f6`, PR
  #120); committed `docs/handoffs/62-the-state-told.md` and the §4
  renumbering in `ca742d9`; pushed; `git checkout -b feat/the-state-told`.
- **A parallel session shared this working tree.** While I worked, another
  session committed *"docs: report 61 addendum — deployed to the cluster,
  four tenants ready"* onto whatever branch was checked out — mine
  (`2f8c18c`) — and landed the same patch on `dev` as `d250319` (same
  content, same timestamp). My branch was not pushed yet, so I rebased my
  two commits onto `origin/dev` (`git rebase --onto origin/dev 2f8c18c`)
  and the duplicate is gone. Nothing of mine was lost; nothing of theirs
  was changed. The addendum's deploy facts are what §Needs the owner
  quotes.
- `boot44` (a scratch database from handoff 44, not in CLAUDE.md's fan-out
  loop) was **already behind** before this handoff (`myservice_api`
  19.0.3.32.0, `myservice_asset_register` 19.0.1.29.0: it missed 61's
  fan-out too). Left as found; it serves nothing.

---

## §1 · One event: `asset.register_state.changed`

### Where it is raised — the single-writer claim, verified

The handoff named `asset_gates._gate_move` as the one point every state
change passes through, and CLAUDE.md says a claim of exclusivity is the
Architect's guess until a search backs it. The search:

| Writer of `register_state` | What it is | Covered? |
|---|---|---|
| `nrs.asset.write` | refuses the field without `_GATE_WRITE_KEY` (`asset_gates.py:564`) | — |
| `_GATE_WRITE_KEY` set | **only** in `_gate_move` (`asset_gates.py:786`; `grep -rn "_GATE_WRITE_KEY\|cadra_gate_fire"` over the repo: 4 hits, all in this file — the definition, two guards that READ it, the one write) | yes |
| `nrs.asset.create` | sets a BIRTH state (`captured`, or `registered` by default) — not a change | n/a |
| migration `19.0.1.26.0` | one-off `NULL → registered` backfill, history | n/a |
| raw SQL in modules, `scripts/`, `tests/`, `e2e/` | none writes `register_state` (one test backdates `register_state_since`) | — |

`_gate_move`'s callers: `_fire_gate` (every row of `TRANSITIONS` — the
seven gates and query, reject, resubmit, return), `_gate_issue_tag` and
`_gate_skip_tagging` (both inside `_fire_gate`), and the label's
`_mark_affixed` (the affix). The batch route fires `_fire_gate` per unit
in its own savepoint. So the claim holds, and the event hangs on
`_gate_move` (`myservice_workflow/models/register_state_event.py`).

### One event per act (a judgement — say if it is wrong)

A labelled unit makes **eight** moves for seven gates: `request-tagging`
passes through `tag_requested` to `tag_issued` in one call, because it
issues the label in the same act. A `record_only` unit's approval passes
through `vfm_approved` to `reg_ready`. No unit is ever *in* the passed-
through state when anyone could look, and `vfm_approved` would tell Vendra
a plot of land waits on the Asset Controller when it waits on the maker. So
`_fire_gate` holds its inner moves back (context
`cadra_register_state_one_act`) and raises **one** event, for the state the
act left; a `_gate_move` outside `_fire_gate` — the affix — is its own act.
Result: **7 events** for a labelled unit's seven gates, **5** for a
`record_only` unit's five — the counts the handoff expected in §4. Sending
every move instead is one line (drop the deferral) and adds `tag_requested`
to the contract.

### Only for units Vendra sent

`import_source = vendra` **and** a non-blank `grn_reference`. Measured on
`test19` before the drive: 18 `vendra`-sourced candidates, **8 of 18**
with no GRN — those raise nothing.

### The payload — Vendra's table, no more

`event_id`, `asset_id`, `asset_code`, `grn_reference`, `register_state`,
`waiting_on`, `state_since`; `reason` on a query, a rejection and a return
(the actor's words, stripped); `sap_asset_code` on `registered`. No `event`
key either — the endpoint names the event — so the queue tells the adapter
the type for a body that does not name itself, and every existing event
(`asset.tag.affixed`, the SAP events) is called exactly as before (pinned
by a test with the old three-argument adapter). The person check is a test
too: no actor's name, login or email in any body, no key naming a person.

### Down INT-05's road

`_enqueue_event` unchanged: the same target (`get_event_config`,
`include_disabled=True` — a paused target still queues), bearer token,
outbox row, `X-Idempotency-Key` / `X-Event-Id` / `X-Request-Id`, retry
ladder and dead letter. The row is written in the gate's own transaction:
a refused unit in a batch, a dry run, or a raise after the move takes its
event with it (test `test_a_move_that_rolls_back_takes_its_event`; and on
the bench, the batch's refused unit has 0 events).

**Its own endpoint.** New field on the target, **Register-State Endpoint**
(`rest_endpoint_register_state`), on the form beside the Event Endpoint.
**Blank queues nothing** (logged), because a Vendra whose auth hook does
not cover the path answers `401` (§4.2) and a 401 is final: queueing would
dead-letter every move of every unit. This is a deviation in shape from "the same
`workflow.config` target" only in that the target has one more field; the
handoff's sentence on the endpoint was Vendra 57's ("beside INT-05's").

**The dead-letter note** on the asset's chatter says *"The unit's register
state in Cadra is unaffected; the downstream system has not been told it
changed."* for this event; the tag's sentence is unchanged.

### Ordering — yes, two moves land in the same second

Asked directly: **yes, and usually.** `register_state_since` holds whole
seconds; one act's two moves always share a second, and an in-registry
walk lands all seven in one second. Proved by removing the guard: 2 tests
fail, and the failing walk's seven `state_since` values are **one value**
(`62-evidence/t1-mut.txt`: *"First list contains 6 additional elements"*).
`_next_state_since`: now, or the unit's last value plus one second if now
is not later. It is the column itself (published as `gates.state_since`
since 60 and the Candidates sort), so what Vendra stores and what Cadra
shows agree; the cost is a value up to a second or two ahead of the clock,
said in the contract and the CHANGELOG.

### The contract

`docs/integrations/INT-05b-register-state.md`: when raised and when not,
the request, the body table, ordering, one example per state (ten real
payloads from the drive and one marked as written by hand), what Cadra
does with each answer, the ladder, a day of downtime, recovery, the deploy
order. Added to the endpoint reference as §9.3 *What Cadra sends* (INT-05,
INT-05b, INT-06, INT-09); INT-05's contract points to it. CHANGELOG:
additive, plus the `state_since` behaviour change said as one.

---

## §2 · `scripts/walk_units.py`

```
tests/.venv/bin/python scripts/walk_units.py --tenant test19 --asset <id> --to registered
tests/.venv/bin/python scripts/walk_units.py --tenant test19 --asset <id> --reject "<reason>"
tests/.venv/bin/python scripts/walk_units.py --tenant test19 --asset <id> --query "<question>"
```

- **The suites' own walker.** `tests/gates.py` now imports without pytest
  (a failure is `pytest.fail` inside a pytest run, as before, and
  `GateWalkError` outside one) and gains `walk_to`, `query`, `reject` and
  an `on_step` callback. One answer to "how do you walk a unit".
- As the demo personas over HTTP, passwords from
  `docs/api/.personas.<tenant>`; a persona is printed by its role, never a
  password (a test reads the personas file and asserts none of its
  passwords is in the output).
- `--to` takes a resting state; a state behind the unit, or one its kind
  skips (`tag_issued`/`tagged` for a `record_only` unit, `reg_ready` for a
  labelled one), is refused in words rather than walked past.
- **Refused before it reads a file or opens a connection**
  (`62-evidence/walk-refusals.txt`, exit 2 each):

```
$ scripts/walk_units.py --tenant staging --asset 95682 --to registered
Refused: 'staging' is not a local test tenant (the cluster's demonstration tenant). This script walks units only on test19 and never contacts the cluster.
$ scripts/walk_units.py --tenant test19 --origin https://staging.cadra.ng …
Refused: 'https://staging.cadra.ng' is not this machine. This script walks units only on the local bench (localhost or <tenant>.localhost) and never touches the cluster.
$ scripts/walk_units.py --tenant test19 --origin http://10.0.0.5:8069 …
Refused: 'http://10.0.0.5:8069' is not this machine. …
$ scripts/walk_units.py --tenant test19 --origin http://nrs19.localhost:8069 …
Refused: 'http://nrs19.localhost:8069' is another tenant's host; --tenant test19 is served at test19.localhost.
$ scripts/walk_units.py --tenant nrs19 --asset 95682 --reject x
Refused: 'nrs19' is not a local test tenant (a replica of NRS's real staff register). …
$ scripts/walk_units.py --tenant test19 --asset 95682 --reject "   "
Refused: --reject needs the words — say why.
```

- The allow-list is `("test19",)`: the one tenant marked `test` with
  personas seeded. `gtb19` is ruled `test` (2026-09-16) but not marked; it
  joins by a commit when it is.
- Pinned by `tests/test_walk_units.py` (13 tests; no skip in either switch
  state — with the gates off the walk is refused *"already at
  'registered', past 'vfm_verified'"* and that is asserted).

**For Vendra 57:** its five staged units (95682–95686) were **not
touched** — still `captured`. `test19`'s Vendra target has the
Register-State Endpoint set to the proposed path. Once Vendra's receiver is
deployed under that name **and that path is in Vendra's `auth_hooks`** (as
`tag_event`'s is, through `authenticate_cadra_callback`), its drives are
received with no Cadra step. Without the hook entry they 401 exactly as
§4.2 shows. (My first draft said only "once the receiver is deployed" —
wrong; the verification pass found it in Vendra's own `hooks.py`.)

---

## §3 · What did not change

- **Every gate's behaviour, sentences and batch rules (57–61).** No
  refusal, transition, scope or sentence touched; the in-registry suites of
  `myservice_api` and `myservice_asset_register` and the full HTTP suite
  ran green in both switch states (§Verification). The one visible
  difference is `gates.state_since` strictly increasing.
- **`asset.tag.affixed`, byte for byte.** `asset_tag_event.py` untouched;
  its payload builder, endpoint and headers unchanged; the adapter is
  called with the same three arguments for any body carrying `event`
  (`test_tag_affixed_is_routed_and_called_exactly_as_before`). On the
  bench the drive's three affixes were acknowledged by Vendra (`202`) as
  before.
- **Gates off: nothing new is sent.** A unit is born `registered` and never
  passes `_gate_move` (in-registry test, and §4.5 on the bench).

---

## Verification

All on `test19`, after the fan-out, in CI's order (pytest, then the module
suites, then the browser), first with `cadra.receipt.gated` OFF, then ON,
the switch put back ON (its value before) at the end. Full outputs in
`docs/handoffs/62-evidence/`.

### §4.1 — the full suites, both switch states

**pytest** (`tests/`):

| Switch | Result | File |
|---|---|---|
| off | **1,469 passed, 7 skipped, 2 failed of 1,478** (13 min 9 s) — the 2 are 30 s read timeouts, both **green on rerun** (below) | `pytest-switch-off.txt` |
| on | **1,471 passed, 7 skipped, 0 failed of 1,478** (19 min 44 s) | `pytest-switch-on.txt` |

The first switch-off run (`pytest-switch-off-first.txt`, **1,470 passed, 7
skipped, 0 failed of 1,477**, 12 min 15 s) collected `test_walk_units.py`
before the verification pass's fix added a test; it was rerun on the final
code so both states are the same 1,478. The 7 skips, both states, are 61's
seven by category: 2 Turnstile not configured; 2 partition-data-absent
(`closed`, `is_staff_bus`); 1 no active WorkSpace `workflow.config`; 1
`is_tagged`'s documented `null`; 1 the API cannot create an untagged asset.
None is new. New: `tests/test_walk_units.py`, 14 tests.

**The two switch-off failures are timeouts, not assertions** — `requests`
gave up at 30 s: `test_custody.py::test_the_chain_pages_forwards` (inside
`transfer_custody`, a POST) and
`test_depreciation_settings.py::test_patch_category_policy_propagates_to_its_assets`
(report 61's named finding: a category policy PATCH recomputes ~16,000
assets on `test19`, at the suite's timeout). Both passed in the two earlier
full runs, and rerun alone on a quiet server **2 of 2 passed**, the second
taking 55 s across its calls (`pytest-rerun-two-timeouts-switch-off.txt`).
Nothing in this handoff touches custody or depreciation; why the
custody POST stalled past 30 s in that one run I did not establish. Said
rather than rerun-until-green: the
denominator is 1,478 and two of them timed out once.

**Module suites** — `N failed, M error(s) of X tests`, 0 `CRITICAL` in
every run (`module-suites-switch-{off,on}.txt`):

| Module | switch off | switch on |
|---|---|---|
| `myservice_api` | 0 failed, 0 error(s) of **505** | 0 failed, 0 error(s) of **505** |
| `myservice_asset_register` | 0 failed, 0 error(s) of **482** | 0 failed, 0 error(s) of **482** |
| `myservice_workflow` | 0 failed, 0 error(s) of **116** | 0 failed, 0 error(s) of **116** |
| `myservice_barcode_station` | 0 failed, 0 error(s) of **20** | 0 failed, 0 error(s) of **20** |

`myservice_workflow` is 61's 96 plus this handoff's 20
(`TestRegisterStateEvent` 18, `TestADayWithoutVendra` 2).

**Browser suite** (no SPA change in this handoff; run for completeness):

| Switch | passed | skipped | flaky | failed | File |
|---|---|---|---|---|---|
| off | 241 | 32 | 0 | 2 | `e2e-switch-off.txt` |
| on | 262 | 12 | 1 | 0 | `e2e-switch-on.txt` |

- **Off, the 2 failures are report 61's**: spec 14 (*ERP-managed mode
  disables the calculation controls*) waits 15 s for a control while the
  tenant recomputes, and spec 19 (*save its depreciation policy*) the same
  through the category PATCH. **Spec 14 left `test19` in `erp_managed`**,
  as in 61: I put it back to `computed` by the API before the switch-on
  run measured anything (**15.4 s**, 61 measured 14.1 s;
  `depreciation-mode-restored.txt`). Rerun with the switch off, specs 14
  and 19: **10 of 10 passed** (`e2e-rerun-14-19-switch-off.txt`).
- **On, the 1 flaky** is spec 06's *mark found via the app dialog*, passed
  on retry; it touches no gate and no outbox.
- Skips: off 32, on 12, of 275 both times. Report 61 had 31 off — with
  1 *did not run* that this run does not have, so the same 275 add up
  differently; I did not diff the two skip lists spec by spec. On, 12, as
  in 61.

### §4.2 — one unit through all seven gates, against the bench's Vendra

`test19`'s Vendra target (`workflow_config` 4852, `http://vendra.network:8080`,
bearer) given the Register-State Endpoint
`/api/method/vendra_network.api.cadra.register_state_event` (one SQL
`UPDATE` on the test tenant — left set, for Vendra 57). Unit 100041, new,
`import_source=vendra`, GRN `GRN-H62-203142` (a receipt Vendra does not
hold), walked with the script (`drive.txt`):

```
test19 asset 100041 NRS-AST-063929 (serial): captured
  captured -> vfm_pending   [submit, as storekeeper]
  vfm_pending -> vfm_verified   [verify, as iad_officer]
  vfm_verified -> vfm_approved   [approve, as iad_approver]
  vfm_approved -> tag_issued   [request-tagging, as asset_controller]
  tag_issued -> tagged   [affix, as tagger]
  tagged -> reg_submitted   [register, as register_maker]
  reg_submitted -> registered   [approve-registration, as register_checker]
now: registered
```

**The outbox: 7 events** for 100041, payloads printed in full in
`outbox.txt` (nothing redacted; there are no names), one per state in the
contract's examples. Their `state_since`: 19:31:47, :48, :50, :52, :53, :55,
:56 — strictly increasing.

**What Vendra answered — every one:** `HTTP 401`
`{"exception":"frappe.exceptions.AuthenticationError", … "frappe/auth.py",
line 628, in validate_auth …}`, classified final, **dead-lettered on attempt
1** (`status dead, http_status 401, attempts 1` × 24). **Vendra's message
log** (`tabVendra Integration Message`, read with `bench mariadb`): **0 of
the 24 event ids** — the request never reaches Vendra's code, because no
auth hook covers the path (the verification pass's finding; see below). In
the same hour Vendra DID log the drive's three `asset.tag.affixed` events
(`VIM-2026-03659…61`, filed `Dead` by Vendra as unmatched — the made-up
GRN), which Cadra recorded as `acknowledged 202`: INT-05 beside it,
unchanged (`vendra-message-log.txt`).

### §4.3 — a batch verify of 5 units: 5 events

Units 100042–100046 submitted with the script, then ONE
`POST /candidates/gates/verify` as the IAD officer with those five and
100047 (still `captured`): `fired=5 refused=1`, 100047 *"This unit is
"Captured"; "verify" cannot be done from there."* Outbox: **5
`vfm_verified` events**, one per unit (plus each unit's own submit event),
and **0** for 100047.

### §4.4 — a query, a reject, and a `record_only` unit's `reg_ready`

| Unit | Walk | Its event |
|---|---|---|
| 100048 | `--query "Which invoice covers this unit?"` | `vfm_query`, `waiting_on: store`, `reason: "Which invoice covers this unit?"` |
| 100049 | `--reject "Not the model on the purchase order."` | `vfm_rejected`, `waiting_on: null`, `reason: "Not the model on the purchase order."` |
| 100050 (`e2e-59 Land`, `record_only`) | `--to reg_ready` | `reg_ready`, `waiting_on: maker` — straight after IAD's approval; no `vfm_approved` sent |

A return's `reason` is pinned in-registry (`test_a_return_carries_the_checkers_reason`).

### §4.5 — gates off: received and affixed, zero events

Switch off over the API, unit 100052 (`vendra`, GRN) received — born
`registered` — and affixed as the tagger (`200`); switch back on. Outbox:
**0** register-state events, **1** `asset.tag.affixed` (acknowledged 202).

### §4.6 — a unit not from Vendra, walked: zero events

Unit 100051 (`import_source=myservice`, the same GRN) walked through all
seven gates to `registered`: **0** register-state events, 1
`asset.tag.affixed`. Totals for the drive's 12 units: **24 events, of
exactly the 24 expected** (7 + 5×2 + 0 + 2 + 2 + 3 + 0 + 0).

### §4.7 — the script refused for `staging` by name, and for a non-local host

§2 above; `walk-refusals.txt`. After the verification pass, a bare
`localhost` is refused too (*"names no tenant"*), and the database the host
actually serves is read from `GET /meta/readiness` before any password is
read — `gtb19.localhost` for `--tenant test19`: *"Refused:
http://gtb19.localhost:8069 serves the database 'gtb19', not 'test19'."*

### §4.8 — the fan-out, readiness, and the deploy steps

`fanout.txt`: `-u myservice_workflow` on all eight tenants (test19 by the
test run, then the other seven one at a time), **twice** (the column, then
the list view); 0 CRITICAL, 0 ERROR, version 19.0.3.3.0 and the column
present on 8 of 8; the button in the list view on 8 of 8. Readiness after
the restart: `{"ready": true}` on 8 of 8 (`readiness.txt`). `boot44` not
in the loop and already behind (Step 0). Deploy steps: §Needs the owner 2.

---

## §5 · If Vendra is down for a day

Measured, not computed: `TestADayWithoutVendra` runs the REAL drain,
backoff and dead-letter code on a simulated clock (`fields.Datetime.now`
patched — every time the queue reads, the verification pass confirmed), the
target's default policy (8 attempts, 60 s doubling, 3,600 s cap), and 490
events (seventy units a day × seven) raised evenly over a working day
08:00–17:00 Lagos. While Vendra is down every attempt fails as a stopped
receiver does (refused connection — retryable).

**The ladder.** Attempts at 0, 1, 3, 7, 15, 31, 63 and 123 minutes after an
event; after the eighth failure — **2 h 3 min** — it is dead. Measured:
every dead row's span from raise to last attempt is exactly 7,380 s.

| Outage | Delivered late | Dead-lettered | On time |
|---|---|---|---|
| **Down a whole day** (07:00 → 07:00 next day) | **0** | **490 of 490** | 0 |
| Down overnight, **back at 12:00** | **111** (raised 09:57–12:00; the latest lands 59 min after noon) | **107** (raised 08:00–09:57) | 272 (raised after noon) |

The rule: **an event raised more than 2 h 3 min before Vendra returns is
dead-lettered; one raised after that is delivered within an hour (the cap)
of its return.** So for a day's outage: nearly everything dies.

**What Vendra sees when it comes back:** only the events from the last
2 h 3 min before its return, each within the hour; for every unit that
moved earlier, nothing — its stored state is stale until somebody opens the
receipt (55's refresh-on-open) or the dead letters are re-sent. Missed
rejections and queries are never NOTIFIED unless the dead letters are
re-sent.

**What a person must do to recover the dead-lettered ones:** in Cadra's back
office, *Workflow → Failed Deliveries*, filter *Register-State Events*,
select all, **Retry Delivery** — one action. Until this handoff the button
was on the form only, so it was one click per event (490 forms after a
day). Each re-send keeps its `event_id` (a 409 from Vendra counts as
delivered) and its budget is extended by the target's eight attempts; the
replay order does not matter, because Vendra keeps the newest `state_since`
and a stale one is a no-op. Re-sent rejections and queries notify late, but
they notify. Pinned by `test_dead_letters_are_retried_together_keeping_their_ids`.

**For Vendra's half:** a *Resync from Cadra* per receipt (55's
one-question-per-receipt) recovers the STATE without anyone in Cadra; only
re-sending the dead letters recovers the NOTICES. **For the Architect**
(GO-LIVE §31.1): the budget is per target — 30 attempts cover a day at the
3,600 s cap — and it is shared with `asset.tag.affixed`, so lengthening it
lengthens both.

---

## The verification pass (a fresh agent, not an author)

Read-only, while the suites ran. Two defects, both fixed in `3026cfb`:

1. **DEFECT — the 401 was explained wrongly, in seven places.** I had
   written that Frappe refuses the bearer token "for a method it does not
   know", which would have told Vendra 57 that deploying the method is
   enough. It is not: Frappe's `validate_auth` answers ANY unauthenticated
   two-part `Authorization` header with 401 *before routing*
   (`frappe/auth.py:627-628`); `tag_event` gets through only because
   Vendra's `auth_hooks` carry `authenticate_cadra_callback`, which covers
   that one path (`vendra_network/hooks.py`, `auth.py
   _authenticate_bearer_route`). I confirmed it in Vendra's own hooks file
   (its comment says exactly this). Corrected in the contract, DECISIONS,
   GO-LIVE §31.2, ENVIRONMENT-FACTS, STATUS, CLAUDE.md and this report;
   Vendra 57 must add the new path to its auth hook.
2. **DEFECT — `walk_to` overshot a `record_only` unit to `registered`.**
   `--to vfm_approved` on a plot would have run past (approval goes straight
   to `reg_ready`), registered it with a fixture SAP code, and printed
   `now: registered`, exit 0. Now refused in words, and `walk_to` fails if
   the walk ends anywhere but the state asked for.

Risks and nits, and what was done:

3. *"Gates off: nothing is ever sent"* was absolute in the CHANGELOG and
   CLAUDE.md, while a candidate in flight when a tenant switches off still
   moves and is sent (the contract said so). **Wording corrected**; the
   behaviour is kept on purpose — the move is real.
4. The script accepted a bare `localhost`, and checked a NAME, not the
   database it reaches. **Fixed**: `<tenant>.localhost` only, and the served
   database read from `/meta/readiness` before any password.
5. The retry-policy comment said "a little over three hours"; it is 2 h 3
   min. **Corrected** (comment only).
6. `register_state_since` is strictly increasing against `_gate_move`'s own
   writes only; the column itself is writable (a test backdates it by SQL).
   No production writer does. **Left, said here.**
7. "A dry run raises none" is by construction (savepoints), not measured.
   **Said so in the contract**; the batch with a refused unit IS measured
   (§4.3).
8. The contract's identity list omitted two keys `_ref_from` reads, and its
   "nothing is queued" holds for a REST target only. **Corrected.**
9. Whether a unit is "Vendra's" is `import_source`, which any
   `assets:write` caller can set (it is in `_WRITABLE_FIELDS`); a unit
   claimed falsely would be refused by Vendra as unmatched and dead-letter.
   **Left, said here** — the handoff's definition.
10. The list view's *Retry Delivery* has none of the form button's
    visibility rules (a list header cannot). A selection with a delivered
    row is refused WHOLE by `action_retry_now`, in words; selecting
    `pending`/`error` rows pulls them forward with their budget extended.
    The documented path (Failed Deliveries) shows dead rows only. **Left,
    said here.**
11. Process: DECISIONS stamped `[landed 8c9f45e]`; evidence committed with
    this report; `drive.txt`'s command echo omits `--tenant` (the driver
    printed `cmd[3:]`; fixed in `drive_62.py`, the transcript left as
    produced). `grn_reference` is sent as stored, not stripped — what
    INT-03 sent, as the contract says.

---

## Deviations, with why

- **One event per act, not per move** (§1): the handoff's own counts (7 for
  seven gates) and Vendra's `waiting_on` both read right this way; a
  passed-through state is never observable. One line to reverse.
- **The endpoint is a new field, and blank queues nothing** (§1): Vendra 57
  receives "beside INT-05's", and an unconfigured endpoint would
  dead-letter every move. One new column → a fan-out.
- **A recovery button the handoff did not ask for** (§5): *Retry Delivery*
  on a selection, because answering "what would a person have to do" with
  "open 490 forms" is not an answer.
- **`test19`'s Register-State Endpoint was set by SQL and left set**, for
  Vendra 57's drives. I left it set through the suites expecting the
  gates-on HTTP run to exercise the event; **it did not**: 24 register-state
  rows on `test19`, all 24 the drive's — the HTTP suite creates no
  Vendra-sourced unit with a GRN that then moves through a gate. The event
  is proved by the 20 in-registry tests and the drive, not by the HTTP
  suite.
- **Vendra's message log does not show the events** (§4.2 asked for it):
  Vendra's auth layer refuses them before any Vendra code runs. Printed
  what Vendra answers instead, and Vendra's log showing 0 of 24.

## For the Architect

1. **Vendra 57 must put `register_state_event`'s path in its
   `auth_hooks`** (or extend `authenticate_cadra_callback` to cover both
   paths). Without it the receiver is unreachable and everything 401s. Its
   handoff does not say so.
2. **The retry budget** for a day's outage — GO-LIVE §31.1.
3. **One event per act** — rule on it if you wanted every move.

## The standing sentence check

Every new refusal and notice says what happened and what to do, in words:

| Where | Sentence |
|---|---|
| Walk, a tenant off the bench | *"Refused: 'staging' is not a local test tenant (the cluster's demonstration tenant). This script walks units only on test19 and never contacts the cluster."* |
| Walk, a host off this machine | *"Refused: 'https://staging.cadra.ng' is not this machine. This script walks units only on the local bench (<tenant>.localhost) and never touches the cluster."* |
| Walk, another tenant's host | *"Refused: 'http://nrs19.localhost:8069' is another tenant's host; --tenant test19 is served at test19.localhost."* |
| Walk, bare localhost | *"Refused: 'http://localhost:8069' names no tenant; the bench serves one database per host — use test19.localhost."* |
| Walk, the wrong database answers | *"Refused: http://gtb19.localhost:8069 serves the database 'gtb19', not 'test19'."* |
| Walk, empty words | *"Refused: --reject needs the words — say why."* |
| Walk, a state behind the unit | *"asset N is already at 'registered', past 'vfm_verified'; a walk only goes forward."* |
| Walk, a state a plot never rests in | *"asset N is record_only: it has no label, and its chain never rests at 'vfm_approved' (IAD's approval takes it straight to reg_ready)."* |
| Walk, query/reject out of turn | *"asset N is at 'tagged'; Internal Audit can query a unit only while it waits on them (vfm_pending or vfm_verified)."* |
| Dead letter, on the asset | *"Integration event not delivered — … could not be delivered to <target> after N attempt(s). The unit's register state in Cadra is unaffected; the downstream system has not been told it changed."* |
| Log, nothing queued | *"workflow: target <name> has no register-state endpoint; asset.register_state.changed for asset N not queued"* |

## Commits

| Commit | What |
|---|---|
| `ca742d9` (on `dev`) | Step 0: the handoff, evaluation §4 renumbered |
| `8c9f45e` | the event, the endpoint field, `state_since`, the retry button, the walk script, the tests |
| `0c710a5` | the INT-05b contract, the reference's outbound list, CHANGELOG, DECISIONS, GO-LIVE §31, ENVIRONMENT-FACTS, STATUS, CLAUDE.md |
| `3026cfb` | the verification pass's fixes |
| (this commit) | this report and its evidence |
