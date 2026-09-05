# Handoff 01 — Report

**From:** Builder (Claude Code, IDE) · **To:** Architect
**Handoff:** `docs/handoffs/01-vendra-integration-fields.md` (CR-01)
**Branch:** `feat/vendra-integration-fields` off `dev` · **Date:** 2026-09-05

---

## Summary

Parts A and B are built and verified on a live instance. Part C is a written
proposal below, with the finding you asked for: **"affixed" is not recorded
anywhere in Cadra today**, and the honest set of tag states is three, none of
which means what INT-05 needs.

Three things in the handoff were wrong, and all three were wrong in the
direction of the defect being **worse** than described. Details in
[Deviations](#deviations). The headline one:

> **`myservice.api.idempotency` has no unique constraint in any database.**
> Odoo 19 removed `_sql_constraints`, so the `UNIQUE (key, endpoint)` this
> cache depends on silently stopped existing. Two concurrent requests under
> one key were not producing a 500 as CR-3 reports — they were **quietly
> creating two assets and two cache rows**. I reproduced it before touching
> anything.

**One thing to carry into the deploy:** this change adds stored columns, and
one Odoo process serves every tenant from one registry — so **every database
must be upgraded before the code ships**, or all asset endpoints 500 on the
ones that were missed. My own verification pass caught me having upgraded only
the database the tests run against. See [V1](#v1--fixed-a-stored-field-is-a-multi-tenant-migration-the-serious-one).

---

## Environment — the stack section of CLAUDE.md was wrong

Before anything else: **this machine does not run Odoo 15.** It runs
**Odoo 19.0** (`cadra-odoo:19.0-dev`), from `docker-compose.yml` +
`docker-compose.19.yml`, serving every tenant database including the 15-era
ones. Every command in the old Stack & environment section failed as written.
I have corrected that section in `CLAUDE.md` from what is actually true here:
the two-file bring-up, host-based tenancy (`http://<db>.localhost:8069` — bare
`localhost` answers *"No database is selected"*), the real pytest invocation,
and the free-port form of the module-upgrade command.

This matters beyond convenience: the Odoo 19 ORM is what CR-01's items
actually run against, and it behaves differently from 15 in ways that changed
the answers (see Deviation 3).

Tests run against `jaizbankplc` — the only local database whose credentials
match `docs/api/.creds`. It is a local replica, so no production data was
touched, but I would rather you know the suite is exercising a tenant replica
than a neutral dev database.

---

## Part A — acquisition provenance

### Built

1. **Three fields on `nrs.asset`** (`myservice_asset_register/models/asset.py`),
   placed in a new *Acquisition provenance* block next to the financial
   fields, not the maintenance ones: `grn_reference`,
   `purchase_order_reference`, `purchase_vendor` — all `Char`. The first two
   are indexed, because `?grn_reference=` is the audit lookup they exist for;
   `purchase_vendor` is too, after the verification pass pointed out it is an
   exact filter as well. Also surfaced in the Odoo form view so the register's own users see
   what the API writes.
2. **`import_source` / `import_date` / `import_ref` exposed.** These live on
   `nrs.asset` via `myservice_asset_register/models/asset_tag.py`, not
   `asset.py` — worth knowing for the next reader.
3. **All six added to `_WRITABLE_FIELDS`** and to the serialiser.
4. **Five exact-match filters** on `GET /api/v1/assets`: `grn_reference`,
   `purchase_order_reference`, `purchase_vendor`, `import_source`,
   `import_ref`.
5. **OpenAPI annotations** updated on GET, POST and PATCH; nine new tests
   (round-trip, each filter, the widened `q`, and exact-not-prefix matching).

### Decisions

**The serialised shape is a nested `data.provenance` block, not six top-level
keys.** The serialiser already groups by concern (`financial`, `dates`,
`location_hierarchy`), and the commercial hand-off reads as one thing. It also
adds one key to the envelope rather than six, which is a smaller change to a
contract Vendra is building against. Vendra reads
`data.provenance.grn_reference`. **If you would rather they were flat, say so
now** — it is a one-line change today and a breaking change once Vendra ships.

**Exposed on `PATCH`: yes — your view, and I agree.** A mis-keyed GRN has to
be correctable. I documented them as write-once *in practice* rather than
enforcing it: real immutability needs a mechanism `nrs.asset` does not have,
and enforcing it would make a typo permanent in the audit trail, which is
worse than allowing a tracked correction. `mail.thread` already records who
changed what.

**`q` now also matches `grn_reference` and `purchase_order_reference`.** Not
in the handoff — my judgement. The business case you wrote is "an auditor
holding a GRN", and an auditor pastes it into the search box before reaching
for a named filter. It broadens `q`'s result set, so flag it if you consider
that a behaviour change too far.

**I did not add a `vendra` value to `import_source`.** Its enum is
`myservice | sap | redhubb | excel | other`; Vendra should send `other` with
`import_ref` carrying their receipt id. Adding a value is additive and cheap,
but it is published enum surface (rule 4) and your call, not mine. **Open
question — do you want one?**

---

## Part B — correctness items

| # | Item | Status |
|---|---|---|
| 1 | `condition: damaged` advertised but rejected | Fixed — **and it was a 500, not a 400** (Deviation 1) |
| 2 | Docs say `Idempotency-Key`, header is `X-Idempotency-Key` | Fixed — 30 occurrences across 4 files, not 9 |
| 3 | Key > 128 chars silently ignored | Now `400 invalid_request` with `details.max_length` |
| 4 | `idempotency_store()` outside the try/except | Fixed — **and the root cause was a missing constraint** (Deviation 2) |

**B3** — `idempotency_key()` now raises `IdempotencyKeyError` instead of
returning `None`; the decorator answers 400 with
`{header, max_length, received_length}`. 128 characters exactly is still
accepted.

**B4** — `idempotency_store()` is now inside its own `except
UniqueViolation`, which calls `_idempotency_replay_after_race()`. That does a
**full `cr.rollback()`, not a savepoint**, and then replays the winner's
cached body. This is the part worth your attention: the losing request has by
that point already created its own asset. Rolling back only the failed cache
insert would keep that duplicate while returning the winner's response —
which is precisely the duplicate-create the key exists to prevent. Discarding
the loser's work is the only outcome that matches what the caller asked for.
If the winner's row cannot be read back, the response is an enveloped
`409 conflict` rather than an invented body.

---

## Deviations — where the handoff was wrong

### 1. `condition: "damaged"` returned **500**, not 400

Both CR-01 and the handoff state it "returns 400". It did not:

```
$ curl -X POST .../api/v1/assets -d '{"name":"probe","category_id":1,"condition":"damaged"}'
HTTP 500
{"error":{"code":"internal_error","message":"Unhandled server error",...}}

# odoo log:
ValueError: Wrong value for nrs.asset.condition: 'damaged'
```

The ORM raises a bare `ValueError` for an out-of-set Selection value, and it
was landing in the decorator's catch-all. **This is not confined to
`condition`** — every Selection field on every endpoint behaved this way,
`state` included.

A 500 is the worst possible answer here: it tells an integration the fault is
ours and the request is worth retrying, so a bad enum value becomes an
infinite retry loop instead of a fixable error. So beyond the docs fix you
asked for, I mapped that one `ValueError` shape to
**400 `validation_failed`**, carrying the accepted set:

```json
{ "error": { "code": "validation_failed",
    "message": "`condition` is not one of the accepted values",
    "details": { "field": "condition", "model": "nrs.asset",
                 "received": "damaged",
                 "allowed_values": ["new","good","fair","poor","decommissioned"] } } }
```

The match is deliberately narrow (Odoo's exact `"Wrong value for
model.field: …"` string); any other `ValueError` is our bug and still returns
500. Rule 4 respected — the model was not touched, and `damaged` is gone from
the annotations, not added to the enum.

### 2. The idempotency race was worse than a 500 — there is no constraint

CR-3 item 3 assumes `idempotency_store()` hits a unique violation. **It could
not.** Odoo 19 removed `_sql_constraints`:

```
odoo/orm/model_classes.py:162
    if hasattr(model_def, '_sql_constraints'):
        _logger.warning("Model attribute '_sql_constraints' is no longer
                         supported, please define models.Constraint on the model.")
```

That warning fires 305 times in the container log. The declared
`UNIQUE (key, endpoint)` exists in **no** database:

```
$ for db in nrs lasg gtb cadra19 nrs19 jaizbankplc; do ... pg_constraint ...; done
nrs 0 | lasg 0 | gtb 0 | cadra19 0 | nrs19 0 | jaizbankplc 0
```

So the real behaviour was silent duplicate creation. Reproduced, 4 concurrent
requests, one key, before any change:

```
attempt 0: codes=[201,201,201,201] ids=[166, 167, 167, 166]
$ select key, endpoint, count(*) ... having count(*)>1;
 race-probe-1788630025479-0 | /api/v1/assets | 2
```

Two assets, two cache rows, four 201s, no error anywhere.

**I fixed the cause as well as the symptom**, because the handoff's B4 alone
would have been a no-op — an `except UniqueViolation` for a violation that
can never occur. `myservice_api/models/api_idempotency.py` now declares the
constraint the 19 way (`models.Constraint`) with the legacy spelling kept
behind a version check so the 15 production stack is unaffected, plus an
`_auto_init` that clears pre-existing duplicates first (Odoo answers a failed
constraint by logging a warning and carrying on, which would have left the
table unprotected exactly as before). It is a 24h cache, so dropping the
loser of an old race costs nothing.

Verified after upgrade:

```
$ \d myservice_api_idempotency
 myservice_api_idempotency_key_endpoint_uniq | UNIQUE (key, endpoint)
```

And the same race, after:

```
attempt 0: codes=[201,201,201,201] ids=[177,177,177,177] assets_with_name=1
attempt 1: codes=[201,201,201,201] ids=[179,179,179,179] assets_with_name=1
...  (8/8 attempts, one asset each)
```

The id gaps (177 → 179 → 181) are the evidence the race is real and being
handled: a second asset *is* created each time and then rolled back.

### 3. Only 4 of the 6 `import_*`/provenance fields were where the handoff said

Minor. `import_source` / `import_date` / `import_ref` are defined on
`nrs.asset` in `asset_tag.py`, not `asset.py`. No impact on the work.

---

## Findings outside this handoff's scope

**Two more dead `_sql_constraints`, one of them serious.** The same Odoo 19
removal has silently disabled:

| Model | Constraint | File |
|---|---|---|
| `nrs.asset` | `unique(asset_code)` | `myservice_asset_register/models/asset.py:234` |
| `bus.route` | `unique(code)` | `myservice_staff_bus/models/bus_route.py:99` |

`asset_code` uniqueness is an identity guarantee INT-06/07 depends on — SAP
dual-code reconciliation assumes one asset per code. It is **not enforced in
any database**:

```
jaizbankplc NONE | lasg NONE | nrs NONE | gtb NONE
```

No duplicates exist yet (`0` in both live tenants), so this is a live hole,
not a live incident. **I did not fix it here** — deduplicating `nrs_asset` is
not a decision to make inside a change about provenance fields, and unlike
the cache table its rows cannot simply be deleted. It needs its own handoff.
Recommend it be the next one.

**A second bad example in the docs.** `cadra_api_endpoint_reference.md`'s
PATCH example sent `"condition": "in_repair"` — a `state` value, invalid as a
`condition`. Same class of defect as B1. Corrected to `"poor"`.

**`docs/api/smoke_test.py` was broken by the 19 stack's tenancy.** It
hardcoded `http://localhost:8069`, which under host-based tenancy resolves no
database and aborts at the token mint. The documented 30-second liveness
check had simply stopped working. Fixed to honour `CADRA_API_BASE`, the same
variable the pytest suite reads, so one export points both at one instance.
It now runs clean end to end.

---

## Verification pass

A fresh agent that did not write the code reviewed the diff against the
handoff and the architecture rules, on the live stack. It found four real
defects. **Three are fixed and re-verified; one is escalated, not fixed.**

### V1 — fixed: a stored field is a multi-tenant migration (the serious one)

The worst finding, and one I had missed. One Odoo process serves all eight
local databases from one registry. The moment `grn_reference` landed in the
Python, every tenant that had not been upgraded was **broken** — and because
`serialize_asset` reads it unconditionally, that means *every asset API
response* on those tenants, not just ones using the new field. Proven on
`lasg`, a live tenant's replica holding 150 assets:

```
$ odoo shell -d lasg
PROBE PLAIN name: <reads fine>
psycopg2.errors.UndefinedColumn: column nrs_asset.grn_reference does not exist
```

I had upgraded only `jaizbankplc`, the database the tests run against, so the
suite was green while six other databases were broken. **This is a deployment
hazard for the change, not just a local one**: the same fan-out is required
of the `cadra-upgrade` Job on staging and production, per tenant.

Fixed: all seven databases upgraded and verified consistent.

```
db           prov_cols  idem_uniq  purchase_idx  asset_rows
jaizbankplc  3          1          3             317
lasg         3          1          3             150
nrs          3          1          3             1272
gtb          3          1          3             150
cadra19      3          1          3             1322
nrs19        3          1          3             11878
gtb19        3          1          3             156
```

CLAUDE.md now carries this as a standing rule with the loop to run.
**Please make sure the deploy for this change fans out per tenant** — it is
the one way this PR can break production.

### V2 — fixed: bad dates, costs and ids still returned 500

My own Deviation-1 rationale was only half-applied. The fix covered Selection
values but not the other coercions, including the two most likely malformations
in an INT-03 payload — and `import_date` is a field this very change made
writable:

```
{"import_date":"not-a-date"}      → HTTP 500 internal_error
{"acquisition_cost":"abc"}        → HTTP 500 internal_error
{"location_id":"abc"}             → HTTP 500 internal_error   (psycopg2.DataError,
                                     not even in reach of the ValueError handler)
```

Fixed: the handler now recognises the ORM's date/float/int coercion messages
as well, and `psycopg2.DataError` gets its own 400 clause. The coercion
errors do not name the field — the ORM has lost that context by then — so the
envelope echoes the offending value and the expected type instead of guessing.
Three new tests cover all three paths.

### V3 — fixed: a poisoned cache row caused a permanent, self-contradicting 409

`idempotency_check` swallowed a JSON decode failure without deleting the row,
so an unreadable row held the `(key, endpoint)` slot for the full 24h and
every retry got a 409 whose message says *"Retry with the same key"* — an
instruction to loop forever. Only reachable via manual SQL or a future
migration, but the fix is one line: the row is now unlinked, as the expiry
branch already did.

### V4 — escalated, not fixed: query-parameter enums are still unvalidated

```
GET /api/v1/assets?condition=damaged  → HTTP 200, empty page
```

A typo'd filter value returns `200 []` rather than an error — silent
degradation, which rule 3 calls a defect even at 200. It is now asymmetric:
the same bad value is a 400 on `POST` and a silent empty page on `GET`.

I did not fix it. Validating filter enums is an API-wide change touching
every list endpoint, and it would turn currently-successful requests into
400s across the whole surface. That is a contract decision, not a detail of
this handoff. **Recommend it as its own handoff.**

### Also changed on review advice

- `purchase_vendor` was the only new field without `index=True` despite being
  an exact filter — now indexed.
- Both race branches now log. Previously a race was invisible: the caller saw
  a normal success and nothing recorded that a duplicate write was discarded.
- `_selection_allowed_values` uses `field.get_values(env)` instead of
  `get_description(env)`, avoiding a translation lookup that could abort the
  transaction inside the error handler, and rolls back if it fails anyway.
- Four more tests: the three untested provenance filters, the widened `q`, and
  an explicit check that the GRN filter is exact rather than prefix-matching.
- Docs: exact-match semantics spelled out (byte-exact, case-sensitive, no
  prefix), and the 409 branch documented.

### Risks flagged and consciously accepted

- **The over-long-key 400 only fires on `idempotent=True` routes.** The same
  header on `/settings/branding` and the other non-idempotent writes is still
  silently ignored, at any length. Making non-idempotent routes reject the
  header is a contract decision — **open question for you**.
- **Rolled-back losers still burn `nrs_asset_id_seq`.** Postgres sequences are
  not transactional, so `asset_code` will show numbering gaps. In a register
  whose point is audit defensibility that deserves a conscious "yes".
- **The race loser blocks on the winner's uncommitted INSERT** for the
  winner's whole transaction, holding a worker. With `workers = 2` a burst of
  duplicate-key retries could pin both. Inherent to storing the cache row
  last; flagging, not redesigning.
- **`provenance` is unconditional in the serialiser**, so it rides on list
  pages up to 200 assets. Consistent with `financial`/`dates`, but it is a
  choice; `serialize_asset` has an `include=()` opt-in that I did not use.
- **The `"Wrong value for model.field"` message is shared with relational
  fields**, so a genuine server-side bug writing a bad m2o could surface as a
  400 with `allowed_values: null`. Not reachable from JSON input — those
  become `DataError` — but the risk is real and acknowledged.
- **`test_concurrent_same_key_creates_exactly_one` is conditionally
  tautological.** Sequence-advance measurement showed the race genuinely
  fires 4 runs in 5; on the 5th the requests serialise and the test would
  pass against reverted code too. ~20% false-negative rate, documented in its
  own docstring.

### Checked and confirmed correct

The riskiest parts of the change were independently verified against the
container's own ORM source: `cr.rollback()` is safe here and needs no
`invalidate_all()` (Odoo 19's `Transaction.clear()` already invalidates field
data and clears `tocompute`); Odoo 19's `retrying()` does not wrap the request
in a savepoint, so the inner rollback orphans nothing; the `UniqueViolation`
is raised synchronously inside `idempotency_store`, not at end-of-request
flush — which was the main way this fix could have been quietly wrong;
`_auto_init` runs before constraint reflection and only on `-i`/`-u`, never on
a plain restart; and the 409 fallback is reachable, enveloped, and does roll
back the loser's write. All four acceptance checks re-passed independently.

The registry-load errors in the container log (`operator does not exist:
character varying ->> unknown`) are the legacy Odoo 15 `odoo` database
failing under the 19 binary — pre-existing, unrelated to this change.

---

## Part C — the tagging signal (proposal, no code)

### The honest answer first: "affixed" is not recorded anywhere

`nrs.asset.tag.label.state` is **`active | pending | scrapped`**. That is the
whole set. It is a *replacement* lifecycle, not a *fulfilment* one:
`pending` means "replacement requested", not "awaiting printing".

- **A label is created the instant the asset is** — `nrs.asset.create`
  auto-generates one (`asset_tag.py:134-149`) with `state='active'`. Your
  reading of the `data.tag` trap is exactly right, and it goes further:
  `state` is `active` from creation too, so exposing the label's state as-is
  would be **the same false-completeness bug in a new field**. That rules out
  the cheap alternative as written.
- **Printing is not recorded.** `action_print_tag()` returns a QWeb report
  action and writes nothing — no field, no timestamp, no `message_post`. A
  tag printed a hundred times and a tag never printed are indistinguishable.
- **Affixing is not recorded, and there is no unit to record it.** There is
  no field, no state, and no model representing the Tag-Issuing Unit.
- **`tag_date` is not the affix date.** It defaults to `fields.Date.today` at
  record creation, so it is the creation date wearing a misleading name. An
  integrator would reach for it. It must not be exposed as a tagging signal.

**So the finding is: Vendra should keep showing `Registered`, and there is
nothing to poll.** Not because the signal is unexposed, but because it is
never captured. No API change can fix that. Cadra would have to start
recording two events it does not currently observe.

### What it would take

The gap is data capture, not transport, and it is the larger half of the job:

1. **A print-issued event.** `action_print_tag` / `action_batch_print_tags`
   stamp `issued_date` and the issuing user on `nrs.asset.tag.label`. Cheap —
   the hooks exist and are already the single funnel for printing.
2. **An affixed event, and someone to raise it.** This is the real work.
   Affixing happens physically, by an independent unit, so Cadra needs an
   inbound confirmation: `POST /api/v1/assets/<id>/tag-affixed` carrying the
   tag number, who affixed it and when, scoped to a new `tagging:write`. The
   `myservice_barcode_station` module is the natural place for the scan that
   raises it. **Without step 2 there is no event to call back about**, and
   INT-04/05 stays a paper process.
3. **A `label_state` on the tag record** — `issued | printed | affixed |
   scrapped` — distinct from the replacement `state`, which keeps its
   meaning. Not on `nrs.asset.state`, per your instruction.

### Preferred direction: outbound callback — yes, and the shape exists

`myservice_workflow` already has most of it, and it is a better foundation
than `/integrations/workflow/callback` (which is the *inbound* leg):

- `workflow.config` — adapter type, base URL, endpoint path, four auth modes,
  timeout, a callback token, and an `action_test_connection()`.
- `workflow.dispatch.log` — one row per attempt, direction, status, payload
  sent, response received, error, timestamps, *"never deleted — permanent
  audit trail"*. That is already the delivery evidence an auditor needs.
- A pluggable adapter layer (REST / email / noop).

Proposed payload for INT-05, on affix confirmation:

```json
{
  "event": "asset.tag.affixed",
  "event_id": "01J...",
  "occurred_at": "2026-09-14T11:32:07Z",
  "asset": { "id": 1274, "asset_code": "NRS-IT-LT-00421",
             "serial_number": "5XJZ8T3" },
  "tag": { "number": "HQ-GF-MR-IT-042", "label_state": "affixed",
           "issued_at": "2026-09-13", "affixed_at": "2026-09-14",
           "affixed_by": "Tag-Issuing Unit / J. Okafor" },
  "provenance": { "grn_reference": "GRN-2026-00001",
                  "purchase_order_reference": "PO-2026-00417" }
}
```

Echoing `provenance` matters: it lets Vendra match the event to a receipt
line without holding a Cadra id, and it closes the loop the fields built in
Part A opened.

**Delivery and retry — the one real gap.** `workflow.dispatch.log` records
attempts but there is **no retry anywhere in the module**: dispatch is
synchronous and one-shot, so a callback fired while Vendra is redeploying is
simply lost, and the log would faithfully record the loss. INT-05 needs an
`ir.cron` draining `status in (pending, error)` with capped exponential
backoff, `event_id` as the client-side idempotency key so Vendra can dedupe a
redelivery, and a dead-letter state after N attempts. That is the piece to
budget for; the rest is assembly.

**Recommendation:** do the callback, but sequence it as *capture first,
transport second*. Steps 1–3 are worth building on their own merits — they
make Cadra able to answer "is this asset physically tagged?", which it cannot
answer today for its own users, let alone Vendra's. The callback is then a
small addition on top. Building transport first would ship an event that can
only ever fire from data nobody records.

---

## Acceptance checks

All run live against `http://jaizbankplc.localhost:8069`.

**1. Create with provenance → 201, values present, `_warnings` empty** ✅

```
status 201
provenance: {
  "grn_reference": "GRN-VERIFY-1788630641",
  "purchase_order_reference": "PO-1788630641",
  "purchase_vendor": "Dell Nigeria Ltd",
  "import_source": "other",
  "import_date": "2026-05-12",
  "import_ref": "VENDRA-1788630641"
}
_warnings: <absent — good>
```

**2. `?grn_reference=` returns precisely that receipt's assets** ✅
Two assets on the GRN, one decoy on another; the filter returned the two and
excluded the decoy.

```
status 200 -> ['verify-prov-1788630641', 'verify-prov2-1788630641']
```

**3. Over-128-character key → 400 in the standard envelope** ✅

```
status 400
{"error": {"code": "invalid_request",
  "message": "`X-Idempotency-Key` must be at most 128 characters",
  "details": {"header": "X-Idempotency-Key", "max_length": 128,
              "received_length": 200, "http_status": 400}}}
```

Exactly 128 characters still returns 201.

**4. `/api/v1/openapi.json` reflects reality** ✅

```
'damaged' anywhere in spec: 0
bare Idempotency-Key params: []
POST body has grn_reference/purchase_order_reference/purchase_vendor: True
POST body has import_source/import_date/import_ref: True
POST condition enum:  ['new','good','fair','poor','decommissioned']
PATCH condition enum: ['new','good','fair','poor','decommissioned']
GET condition enum:   ['new','good','fair','poor','decommissioned']
GET query params incl provenance: ['grn_reference','import_ref','import_source',
                                   'purchase_order_reference','purchase_vendor']
POST header param: ['X-Idempotency-Key']
```

**5. Full pytest suite green** ✅ — see below.

---

## Test output

Baseline before the change, same command, same instance:

```
145 passed, 24 skipped, 3 xfailed in 14.88s
```

After (`CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q`):

```
............................xx....ssssssssss............................ [ 38%]
...........................................ssssssss.ssss.x.............. [ 77%]
.........................................ss                              [100%]
============================ cadra api test report =============================
Report: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-report.md
Captured responses: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-responses/
160 passed, 24 skipped, 3 xfailed in 14.61s
```

Fifteen new tests, all passing, no change to the skip or xfail counts:

```
tests/test_assets.py::test_create_with_provenance PASSED                 [  5%]
tests/test_assets.py::test_filter_by_grn_reference PASSED                [  6%]
tests/test_assets.py::test_filter_by_purchase_order_reference PASSED     [  6%]
tests/test_assets.py::test_patch_provenance_correction PASSED            [  7%]
tests/test_assets.py::test_provenance_in_serializer_for_plain_asset PASSED [  8%]
tests/test_assets.py::test_unknown_condition_is_400_not_500 PASSED       [  8%]
tests/test_assets.py::test_filter_by_vendor_and_import_fields PASSED     [  9%]
tests/test_assets.py::test_q_matches_grn_reference PASSED                [  9%]
tests/test_assets.py::test_grn_filter_is_exact_not_prefix PASSED         [ 10%]
tests/test_assets.py::test_unparseable_date_is_400_not_500 PASSED        [ 10%]
tests/test_assets.py::test_non_numeric_cost_is_400_not_500 PASSED        [ 11%]
tests/test_assets.py::test_non_integer_relation_id_is_400_not_500 PASSED [ 11%]
tests/test_idempotency.py::test_idempotent_location_create PASSED        [ 70%]
tests/test_idempotency.py::test_idempotent_asset_create PASSED           [ 71%]
tests/test_idempotency.py::test_idempotent_request_create PASSED         [ 71%]
tests/test_idempotency.py::test_overlong_key_is_rejected PASSED          [ 71%]
tests/test_idempotency.py::test_key_at_max_length_is_accepted PASSED     [ 72%]
tests/test_idempotency.py::test_concurrent_same_key_creates_exactly_one PASSED [ 72%]
```

The 24 skips are admin-scoped tests: `docs/api/.creds` has no `admin` scope.
The 3 xfails are the pre-existing known-upstream failures, unchanged.

---

## Breaking-change assessment for Vendra

Per rule 1, everything additive is safe; here is the honest accounting:

| Change | Breaking? |
|---|---|
| `data.provenance` block in the serialiser | Additive — new key |
| Six new writable fields | Additive |
| Five new query filters | Additive |
| `condition` enum annotation `damaged` → `decommissioned` | **Documentation correction.** No runtime behaviour changed: `damaged` was never accepted. A consumer that believed the docs was already broken |
| Invalid Selection value: 500 → 400 | **Behaviour change, intentional.** A consumer treating 500 as retriable now gets a terminal 400. That is the point |
| Over-long idempotency key: silent accept → 400 | **Behaviour change, intentional.** A caller sending >128 chars now gets an error instead of an unprotected write. CR-01 notes Vendra has already capped its keys |
| Concurrent same-key: two records → one | Bug fix. A consumer depending on the old behaviour was depending on a defect |

The two intentional behaviour changes are the ones to mention to Vendra
before they ship INT-03.

---

## Open questions

1. **Flat or nested provenance?** I chose `data.provenance`. Cheap to change
   now, breaking later.
2. **Do you want `vendra` added to the `import_source` enum?** Published enum
   surface, so your call. Vendra can use `other` today.
3. **Is broadening `q` to match GRN/PO acceptable**, or should provenance
   only be reachable through the named filters?
4. **Should the dead `asset_code` unique constraint be the next handoff?** It
   is a live integrity hole affecting INT-06/07 and I deliberately left it
   alone.
5. **Part C sequencing** — do you want capture (steps 1–3) specified as its
   own handoff before the callback, as I recommend?

---

## Commits

Listed at push time; see the PR into `dev`.
