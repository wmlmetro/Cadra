# Report 14 — Who has held this laptop

**Builder → Architect.** Branch `feat/custody-chain` off `dev`. Handoff 13's
PR (#58) **had merged** before this started, so Step 0 needed nothing beyond
the branch.

---

## Environment facts

One, and it is the standing Postgres crash-restart from report 13 with its
cause measured. Written straight into `docs/ENVIRONMENT-FACTS.md` as asked,
and summarised here only because it is the wall-clock line below.

**It is the Docker VM's OOM killer, and the host is far past tight.** Every
*"all server processes terminated; reinitializing"* is preceded in the `db`
log by `statistics collector process … was terminated by signal 9: Killed`,
and the container reports `OOMKilled=false` with no memory limit — so the
kill comes from the VM's kernel, not from Docker. Measured on the host at the
time: about 60 MB of free pages, and **21.1 GB of 22.5 GB of swap in use**.

Overlapping Odoo runs are the trigger, not the condition. It fired eight
times, every early one while a subagent's `-u myservice_api` run overlapped
this session's `-u myservice_asset_register` run **against a different
database** — different databases do not help, the memory is the shared
resource and not the registry lock. Serialising cut the rate sharply and did
not end it: `nrs19` still crash-restarted three times on its 77-module
registry load with nothing else of ours running at all.

The full entry, with the recipe that works and the false-green to watch for,
is in `docs/ENVIRONMENT-FACTS.md`.

---

## What was built, in plain terms

Cadra could not answer "who has held this laptop". It knew who holds it now,
and every change it had ever recorded sat in Odoo's chatter — reachable from
the record's message log, exposed by no API route, and deletable by anyone
with the groups that let them delete a message. A chain of custody that can
be deleted is not a chain of custody.

There is now a real one. Every change of custodian appends a link to a model
that **refuses to be edited or deleted afterwards** — refuses it in code, on
the model, so it holds for an administrator too. Each link says who held it
before, who holds it now, when, **who made the change**, why if a reason was
given, and where the change came from.

The history that was in the chatter has been moved across on all eight
tenants, and every moved link is marked as reconstructed rather than passed
off as contemporaneous.

Two smaller things went with it. Three unauthenticated login endpoints
answered a raw Odoo error page instead of a Cadra error when sent a
malformed body; they now answer properly. And a client granted a raised
record limit can no longer also be given a day-long token, which was the one
way the old limit could outlive the decision to withdraw it.

---

## 1 · The backfill numbers, per tenant

**They agree on every tenant.** Read from the log the migration writes, and
then verified independently in SQL rather than taken on the migration's own
word:

| Tenant | tracking values read | custody links written | of those, `tracking_backfill` |
|---|---|---|---|
| `jaizbankplc` | 221 | 221 | 221 |
| `gtb19` | 152 | 152 | 152 |
| `gtb` | 150 | 150 | 150 |
| `lasg` | 150 | 150 | 150 |
| `nrs19` | 1 | 1 | 1 |
| `cadra19` | 0 | 0 | 0 |
| `test19` | 0 | 0 | 0 |
| `nrs` | 0 | 0 | 0 |
| **total** | **674** | **674** | **674** |

All eight are at `myservice_asset_register 19.0.1.12.0`. Nothing was skipped
for a deleted asset and nothing for a no-op custodian change, on any tenant —
the migration counts both and reported zero of each everywhere.

**Nowhere do the two numbers differ, so there is no discrepancy to explain.**
There are two things worth saying about the numbers themselves:

- **`jaizbankplc` is 221, and INT-10 measured 217.** Four custody changes
  happened on that tenant between the two measurements. Not a discrepancy in
  the backfill — a discrepancy between two dates.
- **`nrs19` is 1 against roughly 11,878 assets, and three tenants are 0.**
  That is the honest shape of this data and not a fault in the reconstruction.
  The chain begins where `custodian_id` became a tracked field, and a register
  seeded by direct SQL produced no tracking value at all. Every one of those
  674 links says `tracking_backfill` on its face so a reader can see where the
  record starts without being told.

---

## 2 · Does anything else write `custodian_id`?

**Yes. Five other writers, and the handoff's premise that the transfer route
is the only one is wrong.** This is the report question that changed the
design, so it is answered before the numbers.

The handoff said: *"Written from one place. `POST /assets/<id>/transfer-custody`
is the only writer today and stays so."* An exhaustive search over every
`.py`, `.xml`, `.js` and `.csv` in the repo finds:

| Writer | Where | What it does |
|---|---|---|
| `POST /assets/<id>/transfer-custody` | `v1_assets.py` | the route the handoff named |
| `POST /assets` and `PATCH /assets/<id>` | `v1_assets.py` | **`custodian_id` is in `_WRITABLE_FIELDS`** — a client can move custody with a PATCH and never touch the transfer route |
| `nrs.asset.transfer.action_complete()` | `asset_transfer.py` | the Transfers UI button, on completion |
| `action_mark_retrieved()` | `myservice_identity/models/asset_identity.py` | clears the custodian when an employee leaves — the single most audit-relevant movement there is |
| the three tenant seed scripts | `scripts/{jaiz,gtb,lasg}_data_seed.py` | assign custodians in bulk, through the ORM |
| the Odoo form | `views/asset_views.xml:75` | `custodian_id` is an editable field; plus `default_custodian_id` from an employee's "Assigned Assets" action |

**So the recorder is in `nrs.asset.write` and `nrs.asset.create`, not in the
route.** Recording in the route would have produced a chain that was
incomplete on its first day, and **a gap in an append-only record is
indistinguishable from a period of no movement** — which is the one failure
this model cannot recover from, because an auditor cannot tell the two apart
and therefore cannot trust the parts that are complete either.

Callers that know why they are writing declare it in the context
(`cadra_custody_source`, `cadra_custody_reason`); the transfer route, the
API's create and patch, and the transfer completion all do. Everything else
lands on `direct`, labelled *"Direct write (Odoo UI, import or script)"*,
which is accurate rather than vague-sounding: it is exactly what a form save
or a seed script is.

**What is NOT covered, and cannot be:** a write issued as raw SQL. There is
no such path in the repo today — the seed scripts use `record.write()` inside
a savepoint — but the guarantee is "every ORM writer", not "every possible
write".

---

## 3 · Did `include=custody` inherit handoff 12's honesty for free?

**The paginated route did. The embed did not need it, and that is deliberate.**

`GET /assets/<id>/custody` goes through `paginate()` like every other list
endpoint, so it gets the true `total_estimate` and the `_warnings.truncated`
block for nothing — `paginate()` runs `search_count` on the caller's own
unclamped domain before any cap is applied, and `ok()` attaches the
truncation warning for every route including ones written later. Checked
rather than assumed: `tests/test_custody.py::test_the_total_counts_the_chain_not_the_page`
asks for one link of an N-link chain and asserts the response still reports
N, which is the exact defect handoff 12 fixed.

`include=custody` is **uncapped**, so there is no truncation for it to
report. That is the answer to the handoff's other instruction — it must not
be capped at 20 the way the embedded `transfers` list is — and the reasoning
is the handoff's own: "the last twenty custodians" is not a weaker answer, it
is a wrong one, because a truncated chain cannot be told from a complete one.

**Proved live on `jaizbankplc`**, on an asset with a chain of nine, using the
suite's own service credential with its record cap temporarily set to 2 and
restored afterwards:

| request | rows back | `total_estimate` | `_warnings.truncated` |
|---|---|---|---|
| `GET /assets/2815/custody?limit=1`, cap 0 | 1 | **9** | none |
| `GET /assets/2815/custody?limit=100`, cap 2 | 2 | **9** | `{cap: 2, total: 9, reason: …}` |
| `GET /assets/2815?include=custody`, cap 2 | **9** | n/a | none |

The middle row is the one that matters: two rows returned, nine reported, and
the response says out loud that it was cut. The third row is the asymmetry
named at the end of this report — the embed ignores the cap, which is the
handoff's instruction followed, and it means a capped client can get two
different answers to the same question with only one of them saying so.

Two things were needed rather than free:

- **The orderings had to be made to agree.** `paginate()` pages on an
  ascending `id` cursor and cannot sort any other way, while the model's
  `_order` is `changed_at, id` for the Odoo UI. The serializer now sorts the
  embed by `id` explicitly, so a reader who switches from the embed to the
  route sees the same chain in the same order. A test asserts the two id
  lists are identical.
- **Both are oldest-first.** A chain reads forwards, and it is also the only
  direction the published cursor can walk honestly.

---

## What the verification pass caught

A fresh agent that authored none of it reviewed the diff against the
acceptance criteria. Five of the six criteria were met outright; the sixth
was Part A sitting in its deliberate RED state. It also found seven real
defects, all fixed before this report:

1. **Duplicating an asset fabricated permanent custody history.** `custody_ids`
   is a one2many and Odoo's Duplicate action re-creates a one2many's lines on
   the copy — so the new asset opened with the original's links, same
   timestamps, same actors, same `source`, and **they are append-only, so the
   fabrication could never be removed.** `copy=False`. `transfer_ids` has the
   identical shape and is merely untidy; here it would have been invented
   evidence in the one model whose whole value is that its contents are not
   invented.
2. **`create` was guarded only by the ACL** — which is precisely what the
   model's own docstring argues is insufficient for `write` and `unlink`. One
   `1,1,1,1` line in `ir.model.access.csv` and an internal user could
   `call_kw` a backdated link naming an arbitrary actor into a record that
   then cannot be corrected. `create` now raises unless the caller carries the
   flag `_record` sets, the same shape as `workflow.dispatch.log` from
   handoff 06.
3. **The comment defending `ondelete='restrict'` was factually false.** It
   said nothing in the codebase unlinks an `nrs.asset`. `scripts/nrs_hq_seed.py`
   unlinks **every** asset in the database as its opening act. The restrict
   stays and the comment now says what actually happens: that script will
   stop on the five tenants that have custody history. **That is the intended
   behaviour, not a casualty of it** — a script that would destroy an
   append-only audit record should refuse and say so, and an operator who
   genuinely means to discard the register can drop the database. A cascade
   would have made the wipe silent, which is the one outcome nobody could
   audit afterwards. *This is the item most likely to surprise somebody, and
   it needs the Architect's eye.*
4. **Three pytest tests asserted nothing on a normal run.** A freshly created
   session asset has one custody link or none, so every pagination assertion
   took its early-return branch — a green run that checked nothing, which is
   worse than a red one. They now build a chain of three links first and
   `pytest.skip` loudly if the tenant has fewer than two employees to move
   an asset between.
5. **Two tests would have broken past 100 links.** They asked for `limit=200`,
   and `parse_limit` clamps a service token to 100 — so "the whole chain" was
   silently a page. Exactly the false answer this endpoint exists to prevent,
   inside its own test. They walk the cursor now.
6. **A test's name promised a guarantee its body never exercised** —
   `test_the_names_survive_the_employee_being_deleted` never deleted an
   employee. It does now, and asserts the link goes null while the name
   stays.
7. **`_()` was being passed a variable**, so Odoo's message extractor would
   never have seen the string and it could not have been translated,
   whatever the runtime call looked like. The literal moved inside a
   function.

Two more it raised that are rulings rather than defects, and are for the
Architect:

- **The pytest suite writes permanent, undeletable rows** into a live-shaped
  tenant's chain of custody, one per run, carrying `reason:
  "test_custody._build_a_chain"`. `tests/test_assets.py` already moved
  custody, so this is not new in kind — it is new in permanence, because
  nothing can remove them afterwards. The alternative is a test that does not
  exercise the recorder, which would be worse.
- **`include=custody` bypasses the per-client record cap** where the
  paginated route applies it and announces truncation. That is the handoff's
  own instruction followed, and it means a capped client gets two different
  answers to the same question with only one of them saying so. Naming it
  rather than leaving it to be found.

---

## Test output

Every guard was proven to fail before it was accepted. The runs are on
`test19`, `--workers=0` as any `HttpCase` needs.

**Watch the denominator, not just the count.** A run that loses its database
reports `0 failed, 0 error(s) of 0 tests` and **exits 0** — a green that
executed nothing. That happened repeatedly here while Postgres was being
OOM-killed, and it is why every line below carries its `of N tests`.

### The chain of custody — `-u myservice_asset_register --test-enable --test-tags /myservice_asset_register`

RED, with all five guards neutered (the two `write`/`unlink` raises, the
`create` guard, and the recorder in both `nrs.asset.create` and
`nrs.asset.write`):

```
15 failed, 5 error(s) of 55 tests when loading database 'test19'
```

Twenty distinct custody tests failed, across all four classes — every test in
`TestAppendOnly`, `TestEveryChangeIsRecorded`, `TestTheSourceIsTruthful` and
`TestLinksCannotBeHandWritten`. A sample of what they said, which is the
point of a RED run:

```
FAIL: TestAppendOnly.test_write_raises_under_sudo
      AssertionError: UserError not raised
FAIL: TestAppendOnly.test_deleting_the_asset_cannot_erase_the_chain
      AssertionError: Exception not raised
FAIL: TestEveryChangeIsRecorded.test_creation_with_a_custodian_opens_the_chain
FAIL: TestLinksCannotBeHandWritten.test_a_hand_written_link_is_refused
```

GREEN, guards restored, nothing else changed:

```
0 failed, 0 error(s) of 55 tests when loading database 'test19'
```

### The auth routes and the TTL ceiling — `-u myservice_api --test-enable --test-tags /myservice_api:TestAuthMalformedBody,/myservice_api:TestTokenTtlCeiling`

RED, with the three auth type checks commented out and the TTL constraint's
`raise` made unreachable:

```
31 failed, 0 error(s) of 17 tests when loading database 'test19'
```

Thirty-one against seventeen because the malformed-body test uses subtests —
one per field per non-string shape — and each counts. Ten distinct tests
failed, both classes. The auth failures are the defect itself:

```
FAIL: Subtest TestAuthMalformedBody.test_no_auth_route_answers_html_to_a_non_string
      (path='/api/v1/auth/revoke', field='refresh_token', value={'$ne': None})
ERROR odoo.http: Exception during request handling.
FAIL: TestTokenTtlCeiling.test_uncapped_is_a_non_default_limit_not_an_exemption
FAIL: TestTokenTtlCeiling.test_the_ttl_may_not_be_raised_first_and_the_limit_second
```

That `Exception during request handling` line beside each auth failure **is**
the raw HTML 500 this part of the handoff exists to remove.

GREEN:

```
0 failed, 0 error(s) of 17 tests when loading database 'test19'
```

### The external suite — `CADRA_API_BASE=http://jaizbankplc.localhost:8069 pytest tests/ -q`

```
292 passed, 27 skipped in 44.51s
```

27 skips is the documented healthy figure — admin-scoped tests the suite's
token cannot reach, plus pagination tests that skip when a tenant fits inside
the record cap. The seven new custody tests all **passed rather than
skipped**, which is worth stating because five of them skip loudly on a
tenant with fewer than two employees and a skip would have proved nothing:

```
tests/test_custody.py::test_custody_route_returns_a_chain PASSED
tests/test_custody.py::test_the_total_counts_the_chain_not_the_page PASSED
tests/test_custody.py::test_the_chain_pages_forwards PASSED
tests/test_custody.py::test_include_custody_is_not_capped PASSED
tests/test_custody.py::test_a_transfer_appends_exactly_one_link PASSED
tests/test_custody.py::test_a_patch_of_the_custodian_also_appends PASSED
tests/test_custody.py::test_the_chain_has_no_write_endpoint PASSED
7 passed in 3.34s
```

---

## 4 · Wall-clock

Roughly **seven hours of session time, of which about four were the machine
and not the work.**

| | |
|---|---|
| Writing the code, the tests and the documents | ~2h |
| Verification pass and fixing what it found | ~1h |
| Lost to Postgres being OOM-killed | ~4h |

The last row is the honest one and it is why the environment fact above is
written the way it is. Eight crash-restarts, four of them while a subagent's
module upgrade overlapped this session's; the rest with nothing else of ours
running at all, because the host was at 21.1 GB of 22.5 GB of swap before any
of this started. Work stopped and the owner freed the machine; **after that
the entire remaining sequence — the eight-tenant fan-out, both red-then-green
proofs and the external suite — took under five minutes with no retries.**

Two process notes worth more than the hours:

- **A run that loses its database exits 0 and reports `0 failed, 0 error(s)
  of 0 tests`.** Both subagents hit this and one of them nearly reported a
  green from it. Any wrapper around an Odoo test run has to check the
  denominator, not the exit code.
- **Handing two subagents a module upgrade each was the wrong partition
  here.** `CLAUDE.md` says to serialise anything touching the database and I
  followed that for writes, but not for test runs — and on this machine a
  second registry load is itself the shared resource. The rule wants
  widening: serialise every `--stop-after-init` run, not only the ones that
  write.

---

## Open questions for the Architect

1. **`scripts/nrs_hq_seed.py` now stops on any tenant with custody history.**
   `ondelete='restrict'` refuses to let a wipe destroy an append-only audit
   record, which I judge correct and have documented at the field. But it
   makes a re-seed of `jaizbankplc`, `gtb19`, `gtb`, `lasg` or `nrs19`
   impossible without dropping the database. Ruling wanted: is that the
   intended cost, or should the script grow an explicit
   "yes, discard the chain of custody" step?
2. **The pytest suite now writes permanent, undeletable links** into a
   live-shaped tenant, one per run. The alternative is a test that does not
   exercise the recorder, which is worse. Naming it because "the test suite
   appends to the audit record" is a sentence somebody should agree to rather
   than discover.
3. **`include=custody` ignores the per-client record cap** where the route
   applies it, so a capped client gets two different answers to the same
   question and only one of them says so. Proved live in §3. This follows the
   handoff's instruction; it is the instruction I would want re-examined.
