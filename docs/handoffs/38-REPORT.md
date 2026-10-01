# Report 38 — Before the demo

**Builder:** Claude Code (IDE) · **Branch:** `fix/before-the-demo` · **Base:** `dev` · **Date:** 2026-10-01

---

## In plain words, first

Both things we said in the room on 30 September are now true, and both are
proved in the browser on the built app, in one session, with the row read
back from Postgres.

**Scanning.** The scan box on the barcode station searched the tag number
and the asset code. The serial of a tagged asset — an auditor walking round
with a scanner — found nothing, while the API had documented *"tag, asset
code, or serial number"* since June. It now finds the asset and the card
says *Found by serial number*. The order is tag, then asset code, then
serial, so a scanned tag can never lose to a serial that happens to read the
same (there are none: 0 collisions on all eight tenants). A scanner's
trailing space does not matter; a serial typed in a different case does not
matter; a space inside a serial or a leading zero DOES matter, because the
real data has both. And when a serial is on more than one asset — `nrs19`
has 1,291 such values, because somebody typed `PROBOOK` into the serial
field of 94 laptops — the station says so and refuses to pick one.

**Reprinting a faded tag.** The back office could do it; nothing a person at
a scanner could reach could. Now the card has *Replace tag*: pick a reason,
name who you are asking, and the request waits. A second person approves it
from the same station (or rejects it, with a reason the requester sees). On
approval the old number is scrapped, a new one is minted, the two records
name each other, and the old number never comes back — done, read back from
the row, in the app. It is two-person because the model already had a
request step and an approve step and because approvals are what NRS asked
for by name. **It is NOT on the approvals queue from handoff 35** — that
model is wired to moves and custody in fifteen places and its one-request-
per-asset rule would have made a pending label block a move on the same
asset, the day before the demo. That is a judgement call and §B says what
it costs and how to reverse it.

**The IR number (item C) was not built, and measuring it changed the
question.** The field Cadra reads is empty on `nrs19`. NRS's real IR
numbers are there — 11,385 of 11,386 employees — in a column named
`x_ir_number`, and they are all digits, five or eight long, with no letter
`O` in any of them. An "IR + digits" rule would have refused every real one.
What the format is, and whether Cadra is reading the right column, are
questions for NRS; the counts are in §C.

**One thing found that nobody asked for:** the station's *"no match"* panel
had never rendered. A miss is a 404, the page caught it as a generic error,
and the branch that explained a miss in words was dead code with a comment
saying the opposite. Fixed on this page; the same false comment lives on
the register dashboard and is named, not fixed.

**Nothing in §D was touched.** Not the capture gate, not serial generation,
not the Vendra hand-off, not depreciation, not the identity webhook, and
nothing on `nrs19` beyond `SELECT`s.

---

## A · A scanned serial number must find its asset

### What was there

`lookup_tag` searched `nrs.asset.tag.label.name` (active only) then
`nrs.asset.asset_code`; `portal_lookup` was a second copy of the same two
searches. No serial term in either. Both `/api/v1` twins described the
parameter as *"Tag, asset code, or serial number to look up"* — since
`e189ff0` (2026-06-09), not since the routes were written (`2397f68`,
2026-05-24); the first draft of the changelog said "since they were written"
and the fact-check pass corrected it.

### The four things the handoff asked to get right

**1 · Collision and precedence.** Measured first, on all eight tenants
(`scratchpad` queries, 2026-10-01, before any code):

| tenant | assets | with serial | serial = tag number | serial = asset code | tag number = asset code |
|---|---|---|---|---|---|
| cadra19 | 1,335 | 13 | 0 | 0 | 0 |
| nrs19 | 11,951 | 11,332 | 0 | 0 | 0 |
| gtb19 | 156 | 0 | 0 | 0 | 0 |
| test19 | 6,067 | 149 | 0 | 0 | 0 |
| nrs | 1,272 | 0 | 0 | 0 | 0 |
| lasg | 150 | 0 | 0 | 0 | 0 |
| gtb | 150 | 0 | 0 | 0 | 0 |
| jaizbankplc | 4,164 | 210 | 0 | 0 | 0 |

A collision is not impossible — seven serials on `nrs19` are shaped like a
tag (`H43A-SN-001`…, handoff-32 fixtures) and nothing stops a future one —
so the order is **tag number → asset code → serial number**, written in
`_resolve_lookup`'s docstring and proved by two in-registry tests that
manufacture each collision and check the earlier field wins.

**2 · Which field matched.** Every hit carries `matched_by` (`tag_number` /
`asset_code` / `serial_number`); the card shows *Found by tag* / *Found by
asset code* / *Found by serial number* (`data-testid="lookup-matched-by"`),
and a miss says which kind it is. Both routes, through ONE helper so they
cannot drift again.

**3 · Exact or partial.** Exact, case-insensitive, after stripping the
query. Evidence for each choice:

- stored serials carry no padding on any tenant (0 of 11,704 with a serial
  have `serial_number <> btrim(serial_number)`), so stripping the QUERY is
  the whole whitespace rule and a scanner's trailing space or CR/LF works;
- 574 serials on `nrs19` have a space INSIDE (`PROBOOK 440 G3`,
  `PF-13SZW8 18/02`) and 10 begin with `0` (`00C58E1408`,
  `00330-50136-99881-AAOEM`), so neither is normalised away;
- 237 contain lower-case letters and 3 duplicate groups differ ONLY by case,
  so the comparison is case-insensitive (`=ilike`, which Odoo 19 renders as a
  bare `ILIKE` with the value passed through — checked in
  `odoo/orm/fields.py` lines 1312–1332 in the container — with `%`, `_` and
  `\` escaped so a serial like `SN_100%` is literal);
- partial matching was rejected because 1,291 serial values on `nrs19` are
  already on more than one asset (3,455 rows; `PROBOOK` ×94, `THINKPAD L470`
  ×75); a substring rule would make almost every real scan ambiguous.

**A serial on more than one asset is a miss that says how many**:
`404 not_found`, message *"Serial number X is on N assets; scan the tag or
the asset code instead"*, `details.ambiguous: true`, `details.matches: N`,
`details.matched_by: "serial_number"`. The station renders it in words.

**4 · Scrapped and pending tags.** The tag-number branch is byte-for-byte
the old search: `state = 'active'` only. Pinned by two in-registry tests
(scrapped number → miss; pending number → miss). What changed around it: an
asset found by CODE or SERIAL with no active tag is now a hit with
`tagged: false` — carrying its pending label if it has one (`tag_state:
"pending"`, so the station can show *Replacement pending* and the Approve
control), or `tag_id: null` and empty strings if it has none. Before, such
an asset was a miss on both routes. **That is the one behaviour change**
(`/barcode/lookup`'s `tag_id` can be null) and it is announced in
`docs/api/CHANGELOG.md`.

### Files

- `myservice_barcode_station/controllers/main.py` — `_escape_like`,
  `_resolve_lookup`; `lookup_tag` and `portal_lookup` rewritten over it.
  `/tags/lookup` additionally gains `asset_code`, `tag_state`,
  `serial_number`, `matched_by`, `tagged`; it never published ids and still
  does not.
- `myservice_api/controllers/v1.py` — the two twins pass `ambiguous`,
  `matches`, `matched_by` into `error.details`; response schemas name the
  new keys.
- `myservice_barcode_station/tests/test_lookup_resolution.py` — 16 tests
  (14 on the helper, 2 on the wire).
- `tests/test_barcode.py` — +12 HTTP tests, one a named skip (below).
- `Frontend/…/pages/BarcodeStation.tsx`, `lib/dataProvider.ts` — the
  heading, placeholder, badge, serial field, state pill from
  `/meta/enums`, the miss panel made reachable.
- `docs/api/EXTERNAL-SURFACES.md` — both non-`/api/v1` routes re-described.

### One skip, named

`tests/test_barcode.py::test_lookup_by_the_serial_of_an_untagged_asset`
skips: `POST /api/v1/assets` always mints a tag (`tag_source` and
`asset_tag` are not in `_WRITABLE_FIELDS`), so the HTTP suite cannot create
the asset the test needs. The case is proved in-registry
(`test_the_serial_of_an_untagged_asset_resolves_and_says_untagged`, and on
the wire in `TestLookupRoutesOnTheWire`) and the nearest HTTP-reachable
case — an asset whose only label is pending — is tested over HTTP. **The
`test19` skip count is 10, not 9**; `CLAUDE.md` carries the new category.

---

## B · Reprinting a faded tag

### The three decisions

**1 · Two-person, yes — on the tag model, not on `nrs.asset.change.request`.**
Before writing anything I had the approval model mapped
(`asset_change_request.py`, `v1_approvals.py`, `Approvals.tsx`): `change_type`
is a two-value selection; the premise columns, `_premise_check`,
`_check_change_is_complete`, `action_approve`, the activity text,
`nrs.asset._approval_clears`, `CHANGE_TYPES`, `serialize_request`, the
queue page's `ChangeSummary` and row label are all location/custody-
specific — more than fifteen sites; and `init()` creates a partial unique
index of ONE pending request per asset, so a pending tag replacement would
409 a move on that asset. Changing the model that gates moves, and the
queue page NRS has seen, the day before the demo, is the "spread beyond the
shape" the handoff said to stop at.

The tag model already had `active → pending → scrapped`, `requested_by`,
`requested_date`, `approved_by`, `approved_date`, `replacement_reason`,
`replacement_notes`, `replaces_id`, `replaced_by_id`. What it lacked was
every convention handoff 35 settled, so those were added TO IT:

- `approver_id` (who is ASKED), `rejected_by`, `rejected_date`,
  `decision_reason` — four new columns;
- `_may_decide(user)` with exactly the change request's rule, reading the
  change request's `APPROVER_GROUP` so "who is an approver" has one answer;
  `_assert_may_decide` refuses the requester, under `sudo()` too;
- `action_request_replacement(reason, notes, approver)` refuses a non-
  active tag, a missing or invalid reason, no approver, the caller as
  approver, an ineligible approver; stamps everything; clears an earlier
  decision's stamps (a new slot); posts to the chatter and notifies the
  approver's partner;
- `action_approve_replacement(decision_reason)` requires `pending`, the
  decider's eligibility, then the old body (scrap, mint, link) plus the
  decision stamps; returns the new tags;
- `action_reject_replacement(decision_reason)` requires `pending`,
  eligibility and a reason; back to `active` with who said no and why;
- `write` refuses the nine stamp fields without `cadra_tag_replacement`,
  and refuses any `state` change on a scrapped tag.

**What it costs, said rather than glossed:** tag replacements are not in
`/approvals` or the sidebar badge; they have their own queue
(`GET /api/v1/tags/pending-replacements` and the station's *Pending
replacements* card). Handoff 35's *"what is waiting on me is one question"*
is two questions for now. If the Architect rules for one queue, the reuse
path is the six-layer list the exploration produced (selection value, new
to/result fields and five method branches on the model; a tag branch in
`_approval_clears`'s spent-check and field map or a bypass; `CHANGE_TYPES`
and `serialize_request`; a raising route; the queue page's summary/label
and the asset banner; a decision on the one-pending index). `[for the
Architect]` in `docs/DECISIONS.md`.

**2 · The reason is recorded.** `action_request_replacement` wrote the state
and the requester only. It now takes `reason` and `notes` and refuses
without a reason — one of the model's five values, published as
`tag_replacement_reason` on `/meta/enums` and seeded in the app. From the
Odoo form the reason and the approver come off the record (the form gained
`approver_id` and `decision_reason`), so the back-office buttons work when
the fields are typed first — and refuse, naming what is missing, when they
are not. **Consequence:** the legacy back-office station's one-click
*Replace* (`static/src/js/barcode_station.js:198`, which calls the method
with no arguments) now refuses with that message. It is not the demo path
(the SPA's station is) and I left it, named here and in `CLAUDE.md`.

**3 · The old number never comes back — proved by doing one.** `_generate_tag`
counts every tag on the candidate number with no state filter. On `test19`:
`NRS-GEN-5565` (tag 28994) requested by the service credential, approved by
`admin`; `NRS-GEN-5568` (28997) minted; `select count(*) … where
name='NRS-GEN-5565'` → 1 row, `scrapped`; `generate` on the asset again →
`skipped: already_tagged NRS-GEN-5568`. In-registry, two replacements in a
row on one asset yield three distinct numbers and a fresh mint avoids both
scrapped ones (`test_the_old_number_is_never_reissued`).

### The API

| Route | Scope | Body | Refusals |
|---|---|---|---|
| `GET /api/v1/tags/pending-replacements` | `assets:read` | cursor pagination | — |
| `GET /api/v1/tags/<id>` | `assets:read` | — | 404 |
| `POST /api/v1/tags/<id>/request-replacement` | `assets:write`, idempotent | `reason` (enum), `notes?`, `approver_id` | 400 stray key / stamp claim / bad reason (`allowed_values`) / self-nomination; 404; 409 not active (names who is waiting on whom) |
| `POST /api/v1/tags/<id>/approve-replacement` | `approvals:write`, idempotent | `reason?` | 403 own request (`is_own_request`) or ineligible; 409 decided (`decided_by`, `decided_at`) |
| `POST /api/v1/tags/<id>/reject-replacement` | `approvals:write`, idempotent | `reason` REQUIRED | as above |

`serialize_tag` publishes the label with `requested_by` / `approver` /
`approved_by` / `rejected_by` as four separate fields, the chain as
`replaces` / `replaced_by`, and `can_decide` for the caller. Registered in
`test_published_names_resolve.py` (three action routes, one serializer);
`myservice_api` 19.0.3.14.0; changelog entry.

### The station

*Replace tag* on an active card → dialog (reason from the enum, notes,
approver picker over `GET /approvals/approvers`) → the card re-looks-up by
ASSET CODE and shows the amber *Replacement pending* panel (reason,
requested by, approver asked, notes) with Approve / Reject for anybody
`can_decide` → on approval a green notice, *Print new label NRS-…*, and the
card on the new number. A *Pending replacements* card lists the queue with
the same two buttons and *Not yours to decide* for the requester. A
page-triggered re-lookup now also puts the string it ran into the scan box
(found by looking at the screenshot: the badge said *Found by tag* over a
box still showing the asset code — fixed and rebuilt before the final run).

### Files

`myservice_asset_register/models/asset_tag.py`, `views/asset_tag_views.xml`,
`tests/test_tag_replacement.py` (17 tests), `__manifest__.py` 19.0.1.20.0;
`myservice_api/controllers/v1_tags.py` (new), `__init__.py`, `v1_meta.py`,
`tests/test_published_names_resolve.py`, `tests/test_asset_history.py`
(its one direct approval now requests first, as a second user);
`tests/test_tag_replacement.py` (15 HTTP tests), `tests/test_frontend_enums.py`;
`Frontend/…/components/TagReplacementDialogs.tsx` (new), `BarcodeStation.tsx`,
`dataProvider.ts`, `enums.ts`; `e2e/tests/38-serial-lookup-and-replacement.spec.ts`.

---

## C · IR number format — not built; counted

Across the eight tenants, `hr.employee.ir_number`:

| tenant | employees | with `ir_number` | `^IR[0-9]+$` | what they are |
|---|---|---|---|---|
| nrs19 | 11,386 | **0** | 0 | — |
| cadra19 | 2 | 1 | 0 | `PYTEST-IRTEST-001` |
| gtb19 | 61 | 1 | 0 | `PYTEST-IRTEST-001` |
| test19 | 73 | 70 | 0 | `PYTEST-TWELFTH-…` fixtures |
| nrs | 1 | 0 | 0 | — |
| lasg | 60 | 60 | 0 | `LASG-IR-00001`… seeds |
| gtb | 60 | 0 | 0 | — |
| jaizbankplc | 61 | 61 | 0 | `JAIZ-IR-00001`… seeds + 1 fixture |

**193 of 193 existing IR numbers would fail an `IR`+digits rule, and none of
them is real.** The real ones are on `nrs19` in `x_ir_number` — a studio
field (`ir_model_fields.state = manual`, created 2026-08-06, labelled *IR
Number (NRS/contractor)*): 11,385 of 11,386 employees, every one pure
digits, 10,498 five long and 887 eight long, 0 containing an `O`, 0
duplicates. `scripts/seed_nrs_assets.py` maps `x_ir_number → ir_number` on
import; whatever loaded this tenant did not. So:

- the format NRS described (*"supposed to be zero, we see O"*) is a digit
  string, not `IR…`, on the only real data we hold;
- the column Cadra's API, app and SAP sync read is empty for NRS;
- a rule derived from one tenant's extract is a guess with a denominator.

Per the handoff: not started. Two questions for Friday, in
`docs/DECISIONS.md`: what the IR format is, and whether `x_ir_number` is the
column Cadra should be reading.

---

## D · Do not touch — confirmation

`git diff --stat dev` touches no file under `myservice_asset_depreciation/`,
`myservice_identity/`, the goods-receipt capture gate, or the Vendra
hand-off; `nrs19` was read with `SELECT` only (its row counts above) and
upgraded in the fan-out like every other tenant.

---

## E · Verification — in a browser

**Built and deployed first** (`BASE_PATH=/app/ npm run build`, twice — once
after the front end landed, once after the scan-box fix), then driven.

**Spec 38, with the service credential** (`E2E_CLIENT_ID`/`_SECRET` from
`docs/api/.creds.test19`): scans tag, code, serial, serial+space and reads
the badge each time; unknown serial → the miss panel; the service
credential asks, `admin` approves from the pending panel in the SAME
session; the API read back shows old scrapped / `approved_by` admin /
`requested_by` not admin / reason `damaged` / `replaced_by` set, new active
/ `replaces` set / number differs; the card shows the new number; the old
number is a miss; a rejection needs a reason and returns the label to
active. Then a hand-driven pass with screenshots (scratchpad `shots/01`–`12`)
and the API transcript appended below: four lookups with `matched_by`
`tag_number` / `asset_code` / `serial_number` / `serial_number`, the twin
route, ambiguity, the stray-key 400, self-nomination 400, the request, the
pending number not resolving while the serial names the pending label, the
second request 409, the requester's 403, the queue, the approval, both
labels read back, the second approval 409, the new number resolving, the
old one not, `generate` skipping.

**Suites, with denominators:**

```
HTTP (tests/, test19):                1127 passed, 10 skipped in 969.42s
in-registry myservice_asset_register: 0 failed, 0 error(s) of 448 tests
in-registry myservice_barcode_station: 0 failed, 0 error(s) of 20 tests
in-registry myservice_api:            0 failed, 0 error(s) of 287 tests
Playwright (01, 10, 38 on test19):    38 passed (1.4m)
tests/test_source_guards.py:          216 passed
```

No run reported `of 0 tests`; no `CRITICAL`. The ERROR lines in the
asset-register and station logs are the existing tests' deliberate failure
probes (`a_table_that_does_not_exist`, the read-only asset-bundle insert).

**The standing pass.** Sentences checked and corrected: the changelog's
*"since they were written"* (it was a June fix, `e189ff0`); builder B's
*"0 of 11,704 … on nrs19"* (the 11,704 is across all eight tenants); the
history test's comment; the screenshot that showed a badge describing a
different string from the box. Builder C's three unverifiable sentences
were each checked by me against the code (`eligible_approvers` excludes the
caller; the model stamps `approved_by`/`approved_date`; the one-pending
index is in `init()`).

**Residue on `test19`:** the HTTP suite leaves pending tag replacements
(16 at the time of the screenshots) on `pytest-` assets, raised by `admin`
as the second person and never decided; they are on a test tenant and
labelled through their asset names. `scripts/remove_test_residue.py` does
not know the tag model's `pending` state; nothing is blocked by it.

---

## Deviations from the handoff

1. **§B.1 — "use the pattern handoff 35/36 established"** read as the
   conventions, applied to the tag model's own state machine, for the
   reasons in §B and `DECISIONS.md`. Reversible; cost named.
2. **§C — not built**, as the handoff allowed; the count is §C and it
   reframes the item.
3. **Step 0** committed handoff 37's instruction file and the meeting
   evaluation alongside 38, so neither is lost from the working tree; 37 is
   not started.

## Open questions

- One queue or two for approvals (§B).
- NRS's IR number format, and which column Cadra should read (§C).
- Whether the legacy back-office station's *Replace* should get a reason
  prompt or be retired (§B.2).

## Commits

- `c511d36` docs: handoffs 37 and 38, and the 30 September NRS meeting evaluation (Step 0, on `dev`)
- `0592c56` feat: a scanned serial finds its asset, and a faded tag is replaced by two people
- `3445cd5` docs: report 38 — before the demo
- the commit carrying this list, on `fix/before-the-demo`; PR opened against `dev`

---

## Appendix — API transcript (test19, 2026-10-01)

```
asset 65476 tag NRS-GEN-5565 code NRS-AST-029428 serial PYTEST-H38-1790870334

### 1 scan the TAG
HTTP 200
{
 "matched_by": "tag_number",
 "tagged": true,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 2 scan the ASSET CODE
HTTP 200
{
 "matched_by": "asset_code",
 "tagged": true,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 3 scan the SERIAL of a TAGGED asset
HTTP 200
{
 "matched_by": "serial_number",
 "tagged": true,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 3b same, lower-case
HTTP 200
{
 "matched_by": "serial_number",
 "tagged": true,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 4 serial with a trailing space (as a scanner sends it)
HTTP 200
{
 "matched_by": "serial_number",
 "tagged": true,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 4b /api/v1/tags/lookup twin, serial
HTTP 200
{
 "found": true,
 "matched_by": "serial_number",
 "tagged": true,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "active",
 "asset_name": "pytest-h38-serial-1790870334",
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "category": "Generator",
 "location": "",
 "condition": "good",
 "state": "active",
 "last_service_date": ""
}

### 5 a serial on TWO assets
HTTP 404
{
 "code": "not_found",
 "message": "Serial number PYTEST-H38-DUP-1790870334 is on 2 assets; scan the tag or the asset code instead",
 "request_id": "ad8a7ff24bcb4f7cb51e6fa2f9142103",
 "details": {
  "query": "PYTEST-H38-DUP-1790870334",
  "ambiguous": true,
  "matches": 2,
  "matched_by": "serial_number",
  "http_status": 404
 }
}

### 6 nothing matches
HTTP 404
{
 "code": "not_found",
 "message": "No active tag, asset code or serial number matches: PYTEST-NOTHING-1790870334",
 "request_id": "8dce78c205c94008b408d7cec1e68d56",
 "details": {
  "query": "PYTEST-NOTHING-1790870334",
  "http_status": 404
 }
}

### 7 request, body with a key the route does not take
HTTP 400
{
 "code": "invalid_request",
 "message": "Who asked, who decided and what state a label is in are taken from the credential that made the call and the act it performed, and cannot be supplied: remove `approved_by` and call again.",
 "request_id": "2beb192dba4349928fe8d0ff80f42929",
 "details": {
  "rejected_fields": [
   "approved_by"
  ],
  "writable": [
   "approver_id",
   "notes",
   "reason"
  ],
  "http_status": 400
 }
}

### 8 request, approver = self
HTTP 400
{
 "code": "invalid_request",
 "message": "You cannot ask yourself to approve your own change. Name somebody else.",
 "request_id": "891e7373eead46f28de916f3bb805dc7",
 "details": {
  "asset_id": 65476,
  "http_status": 400
 }
}

### 9 REQUEST by the service credential, naming admin (uid 2)
HTTP 200
{
 "pending_approval": true,
 "tag": {
  "id": 28994,
  "tag_number": "NRS-GEN-5565",
  "state": "pending",
  "label_state": "issued",
  "source": "auto",
  "tag_date": "2026-10-01",
  "scrapped_date": null,
  "asset": {
   "id": 65476,
   "name": "pytest-h38-serial-1790870334"
  },
  "asset_code": "NRS-AST-029428",
  "serial_number": "PYTEST-H38-1790870334",
  "replacement_reason": "damaged",
  "replacement_notes": "faded on the air conditioner",
  "requested_by": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "requested_at": "2026-10-01T15:59:05",
  "approver": {
   "id": 2,
   "name": "Administrator"
  },
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "decision_reason": null,
  "replaces": null,
  "replaced_by": null,
  "can_decide": false
 },
 "asset": {
  "id": 65476,
  "asset_code": "NRS-AST-029428",
  "tag": "NRS-GEN-5565",
  "legacy_asset_code": null,
  "name": "pytest-h38-serial-1790870334",
  "is_test_fixture": true,
  "serial_number": "PYTEST-H38-1790870334",
  "make": null,
  "model": null,
  "manufacturer": null,
  "category": {
   "id": 1,
   "name": "Generator"
  },
  "subcategory": null,
  "asset_type": null,
  "asset_level": "asset",
  "domain": "plant",
  "parent_asset": null,
  "child_count": 0,
  "current_location": null,
  "location_hierarchy": {
   "building": null,
   "floor": null,
   "room": null
  },
  "floor_room": null,
  "address_display": null,
  "coordinates": null,
  "current_custodian":

### 10 the pending tag's NUMBER no longer resolves
HTTP 404
{
 "code": "not_found",
 "message": "No active tag, asset code or serial number matches: NRS-GEN-5565",
 "request_id": "9344093373a4471a9cb27d5998791779",
 "details": {
  "query": "NRS-GEN-5565",
  "http_status": 404
 }
}

### 11 ...but its SERIAL does, and names the pending label
HTTP 200
{
 "matched_by": "serial_number",
 "tagged": false,
 "tag_id": 28994,
 "tag_number": "NRS-GEN-5565",
 "tag_state": "pending",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 12 a second request while pending
HTTP 409
{
 "code": "conflict",
 "message": "A replacement for NRS-GEN-5565 is already waiting \u2014 Smoke Test (API client) asked Administrator on 2026-10-01. Decide that one first.",
 "request_id": "f3638593aa104686959704846ba33083",
 "details": {
  "tag_id": 28994,
  "state": "pending",
  "requested_by": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "approver": {
   "id": 2,
   "name": "Administrator"
  },
  "replaced_by": null,
  "http_status": 409
 }
}

### 13 the requester tries to approve
HTTP 403
{
 "code": "forbidden",
 "message": "You asked for this replacement and cannot approve it. The point of an approval is that a second person agrees.",
 "request_id": "02dc1ab89c004b558edd810e7e028890",
 "details": {
  "tag_id": 28994,
  "is_own_request": true,
  "requested_by": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "http_status": 403
 }
}

### 14 pending queue, as admin
HTTP 200
[
 {
  "id": 28994,
  "tag_number": "NRS-GEN-5565",
  "state": "pending",
  "label_state": "issued",
  "source": "auto",
  "tag_date": "2026-10-01",
  "scrapped_date": null,
  "asset": {
   "id": 65476,
   "name": "pytest-h38-serial-1790870334"
  },
  "asset_code": "NRS-AST-029428",
  "serial_number": "PYTEST-H38-1790870334",
  "replacement_reason": "damaged",
  "replacement_notes": "faded on the air conditioner",
  "requested_by": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "requested_at": "2026-10-01T15:59:05",
  "approver": {
   "id": 2,
   "name": "Administrator"
  },
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "decision_reason": null,
  "replaces": null,
  "replaced_by": null,
  "can_decide": true
 },
 {
  "id": 28307,
  "tag_number": "NRS-GEN-5562",
  "state": "pending",
  "label_state": "issued",
  "source": "auto",
  "tag_date": "2026-10-01",
  "scrapped_date": null,
  "asset": {
   "id": 64782,
   "name": "pytest-tagrepl-decision-body-1790869929-f10fd808"
  },
  "asset_code": "NRS-AST-028748",
  "serial_number": "PYT-TAG-AD8D6316",
  "replacement_reason": "damaged",
  "replacement_notes": null,
  "requested_by": {
   "id": 2,
   "name": "Administrator"
  },
  "requested_at": "2026-10-01T15:52:13",
  "approver": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "decision_reason": null,
  "replaces": null,
 

### 15 ADMIN approves
HTTP 200
{
 "tag": {
  "id": 28994,
  "tag_number": "NRS-GEN-5565",
  "state": "scrapped",
  "label_state": "scrapped",
  "source": "auto",
  "tag_date": "2026-10-01",
  "scrapped_date": "2026-10-01",
  "asset": {
   "id": 65476,
   "name": "pytest-h38-serial-1790870334"
  },
  "asset_code": "NRS-AST-029428",
  "serial_number": "PYTEST-H38-1790870334",
  "replacement_reason": "damaged",
  "replacement_notes": "faded on the air conditioner",
  "requested_by": {
   "id": 6,
   "name": "Smoke Test (API client)"
  },
  "requested_at": "2026-10-01T15:59:05",
  "approver": {
   "id": 2,
   "name": "Administrator"
  },
  "approved_by": {
   "id": 2,
   "name": "Administrator"
  },
  "approved_at": "2026-10-01T15:59:05",
  "rejected_by": null,
  "rejected_at": null,
  "decision_reason": "seen it, agreed",
  "replaces": null,
  "replaced_by": {
   "id": 28997,
   "tag_number": "NRS-GEN-5568"
  },
  "can_decide": false
 },
 "new_tag": {
  "id": 28997,
  "tag_number": "NRS-GEN-5568",
  "state": "active",
  "label_state": "issued",
  "source": "manual",
  "tag_date": "2026-10-01",
  "scrapped_date": null,
  "asset": {
   "id": 65476,
   "name": "pytest-h38-serial-1790870334"
  },
  "asset_code": "NRS-AST-029428",
  "serial_number": "PYTEST-H38-1790870334",
  "replacement_reason": null,
  "replacement_notes": null,
  "requested_by": null,
  "requested_at": null,
  "approver": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "decision_reason": null

### 16 the OLD label, read back
HTTP 200
{
 "id": 28994,
 "tag_number": "NRS-GEN-5565",
 "state": "scrapped",
 "label_state": "scrapped",
 "source": "auto",
 "tag_date": "2026-10-01",
 "scrapped_date": "2026-10-01",
 "asset": {
  "id": 65476,
  "name": "pytest-h38-serial-1790870334"
 },
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "replacement_reason": "damaged",
 "replacement_notes": "faded on the air conditioner",
 "requested_by": {
  "id": 6,
  "name": "Smoke Test (API client)"
 },
 "requested_at": "2026-10-01T15:59:05",
 "approver": {
  "id": 2,
  "name": "Administrator"
 },
 "approved_by": {
  "id": 2,
  "name": "Administrator"
 },
 "approved_at": "2026-10-01T15:59:05",
 "rejected_by": null,
 "rejected_at": null,
 "decision_reason": "seen it, agreed",
 "replaces": null,
 "replaced_by": {
  "id": 28997,
  "tag_number": "NRS-GEN-5568"
 },
 "can_decide": false
}

### 17 the NEW label, read back
HTTP 200
{
 "id": 28997,
 "tag_number": "NRS-GEN-5568",
 "state": "active",
 "label_state": "issued",
 "source": "manual",
 "tag_date": "2026-10-01",
 "scrapped_date": null,
 "asset": {
  "id": 65476,
  "name": "pytest-h38-serial-1790870334"
 },
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "replacement_reason": null,
 "replacement_notes": null,
 "requested_by": null,
 "requested_at": null,
 "approver": null,
 "approved_by": null,
 "approved_at": null,
 "rejected_by": null,
 "rejected_at": null,
 "decision_reason": null,
 "replaces": {
  "id": 28994,
  "tag_number": "NRS-GEN-5565"
 },
 "replaced_by": null,
 "can_decide": false
}

### 18 approve again (a decision is taken once)
HTTP 409
{
 "code": "conflict",
 "message": "This tag is scrapped, not pending replacement \u2014 decided by Administrator. A decision is taken once.",
 "request_id": "604df95d705c4e38aae1397ae5142055",
 "details": {
  "tag_id": 28994,
  "state": "scrapped",
  "decided_by": {
   "id": 2,
   "name": "Administrator"
  },
  "decided_at": "2026-10-01T15:59:05",
  "http_status": 409
 }
}

### 19 scan the NEW number
HTTP 200
{
 "matched_by": "tag_number",
 "tagged": true,
 "tag_id": 28997,
 "tag_number": "NRS-GEN-5568",
 "tag_state": "active",
 "asset_id": 65476,
 "asset_code": "NRS-AST-029428",
 "serial_number": "PYTEST-H38-1790870334",
 "asset_name": "pytest-h38-serial-1790870334"
}

### 20 scan the OLD number
HTTP 404
{
 "code": "not_found",
 "message": "No active tag, asset code or serial number matches: NRS-GEN-5565",
 "request_id": "f61b17b8c2af47ea9f5d34641684beac",
 "details": {
  "query": "NRS-GEN-5565",
  "http_status": 404
 }
}

### 21 generate on the asset again (already tagged -> skipped, no reissue)
HTTP 200
{
 "generated": [],
 "skipped": [
  {
   "asset_id": 65476,
   "reason": "already_tagged",
   "tag_number": "NRS-GEN-5568"
  }
 ]
}

OLD=NRS-GEN-5565 NEW=NRS-GEN-5568 ASSET=65476 TAGID=28994 NEWID=28997
```
