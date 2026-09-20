# Cadra API — changelog

Changes to the published `/api/v1/*` surface, newest first.

This file did not exist before handoff 09. It was created because two rulings
in that handoff both said "announce it in the API changelog" and there was
nowhere to announce anything — which is itself the problem it now solves. The
API has had a live external consumer since INT-03 (Vendra), and until now the
only record of a behaviour change was a handoff report, which an integrator
does not read.

**What belongs here.** Anything a consumer could observe: a new field, a new
route, a changed enum value, a changed error code, a changed status code, a
change in *when* a field's value moves. Additive changes are safe and are
listed for completeness; the ones that can break a consumer are marked
**BREAKING** or **BEHAVIOUR CHANGE**.

**What does not.** Internal refactors, tests, performance, anything a
consumer cannot see. Rule 1 in `CLAUDE.md` is the test: if Vendra could
branch on it, it goes here.

**And it is not only `/api/v1`.** Handoff 15 changed three status codes on
`/myservice/workflow/callback` — correctly — and the rule above did not reach
it, because that route is not under `/api/v1/*`. It is the route the NRS
WorkSpace POSTs approval outcomes to, and Cadra publishes its URL to that
system itself. There are **27** first-party routes outside `/api/v1`; four of
them are called by an organisation that is not us. They are inventoried in
`docs/api/EXTERNAL-SURFACES.md`, with who calls each one and whether changing
it breaks anything. A change to any surface listed there as breaking belongs
in this file on the same terms as a change to `/api/v1` — the test is still
whether somebody downstream could branch on it, and the path it happens to
live at was never the point.

---

## 2026-09-20 — handoff 27: `GET /assets/<id>/history`

**`GET /api/v1/assets/<id>/history` (ADDITIVE — a new route; nothing existing
changes).** One ordered history of an asset, merged server-side from the
registration, the tag's issue/print/affix, the chain of custody, location
moves, tracked field changes, the disposal approval, outbound integration
events and maintenance requests. Scope `assets:read`. Newest first;
`?sort=oldest` reverses it; any other `sort` is a 400 `invalid_request` with
`details.allowed_values`. Not paged and not capped, for the reason
`/assets/<id>/custody` is exempt from the record cap.

**Every event carries `evidence`, and a consumer should branch on it.** The
records behind the list are not worth the same: `append_only` (a change of
custodian, and nothing else), `system_stamp`, `guarded_record`,
`editable_record`, `chatter`. The grades are defined in the response at
`data.fidelity.evidence_grades`. **A location move is never better than
`editable_record`, and a move made by `PATCH location_id` is `chatter`** —
only `POST /assets/<id>/move` writes a transfer row. If your integration
needs a move to be evidenced, call `/move`, not PATCH.

**`disposal_approved` is `editable_record`.** No API client can name its own
approver, but both columns are inputs on the Odoo form; a rewrite of the
approver since is its own `disposal_recorded` event, with the old name and
the new.

`reconstructed: true` marks an event recovered after the fact (a custody link
with `source: tracking_backfill`). `actor` is null where the record names
nobody and is never inferred. `data.fidelity.not_recorded` names the events
Cadra never writes down — a changed cost, SAP field or GRN reference — on
every response. An asset with nothing after registration says so in
`data.summary.statement`.

`include=custody` and `include=transfers` are unchanged. Reference:
`docs/api/cadra_api_endpoint_reference.md` §3.7.2.

## 2026-09-16 — `?sort` on the asset listing

**`GET /api/v1/assets?sort=newest|oldest` (ADDITIVE — nothing changes unless
you ask for it).** The listing has always walked ascending asset id, so the
register's most recently created asset sits on its LAST page. `sort=newest`
walks the same keyset backwards, putting it first.

**The default has not moved and the default walk is byte-for-byte what it
was.** `sort` absent means `oldest`, which is the order this endpoint has
always returned, and an ascending cursor still decodes to exactly
`{"last_id": N}` — no new key, no new shape. A consumer that ignores this
entry is unaffected in every respect, which is why this is additive rather
than a behaviour change. `oldest` is published as an explicit value so a
caller can state the order it wants instead of relying on a default.

**Keep `sort` the same for every page of one walk.** A keyset cursor means
"everything after the last row I saw", and which side that is depends on the
direction. A descending cursor therefore records its direction, and replaying
a cursor against the other direction is a **400 `invalid_request`** carrying
`details.cursor_direction` and `details.requested_direction`. It is not a
best guess: the comparator would page *away* from the rows you have not seen
and hand you a short list that looks complete — the same silent-degradation
shape handoff 22 refused to keep for corrupt cursors.

**An unknown value is a 400** carrying `details.allowed_values`, not an
unsorted list and not an empty one.

**If your credential is record-capped**, the capped window under
`sort=newest` is the NEWEST N records rather than the oldest N. Same
sentence as before — "the first N records of the domain, sorted by `order`"
— read in the direction you asked for. `pagination.total_estimate` is the
true count of the register on every path, as always.

Only `/api/v1/assets` takes `sort` today. The other listings are unchanged.

---

## 2026-09-15 — handoff 26

**`is_test_fixture` on assets, locations and service requests (ADDITIVE).**
Every asset, location and request envelope now carries a boolean
`is_test_fixture`. It is TRUE when the record was created through an API
credential flagged as a test credential, and it is **derived from the acting
credential at creation** — never from the request body.

Three things a consumer needs to know about it:

* **Sending it is refused.** `is_test_fixture` is in no writable-field
  allow-list, so a payload carrying it gets a 201 with the field listed in
  `data._warnings.rejected_fields`, and the stored value is whatever the
  credential implies. A caller cannot mark its own records as fixtures, and
  cannot mark them as real. There is no route that changes the value after
  creation.
* **FALSE does not mean "real".** The field arrived in `myservice_api`
  19.0.3.9.0 and is NOT retroactive — nothing about a record created before
  it can be reconstructed. Every pre-existing record reads FALSE whatever it
  actually is. **Treat TRUE as conclusive and FALSE as unknown** for anything
  created before this version. `GET /api/v1/meta/database` tells you what
  class of database you are reading.
* **It is a statement about the CREDENTIAL, not about the data.** A real
  record created while somebody was testing with a flagged credential is
  labelled a fixture, and that is the intended reading: it says how the
  record came to exist.

The same label is stamped on eleven further models the API can cause to be
created (tag labels, transfers, asset categories, request events, employees,
departments, partners, import jobs, SAP sync logs, workflow dispatch logs and
chatter messages); those three are the ones with a published serializer.
`nrs.asset.custody` keeps its own older mechanism, `source = 'test'`, which
is unchanged and still the value to read on a custody row.

**Not breaking.** Purely additive: a new key in three response objects. No
field changed meaning, no enum moved, no error code moved, and no existing
key was removed or renamed.

A consumer validating strictly against the published schema should note that
only `Asset` is described in `components.schemas` at all — it declares
`additionalProperties: true` and now documents `is_test_fixture` explicitly.
There is no `Location` or `ServiceRequest` schema in the OpenAPI document, so
those two responses were never schema-constrained and a new key cannot
violate a constraint they do not have.

---

## 2026-09-15 — handoff 25

**`GET /api/v1/meta/database` — new route (ADDITIVE).** Answers with the
database this token was routed to, what class of database a person has
recorded it as (`test` / `client` / `production`, or `null` when nobody has),
whether it accepts test writes, and whether the calling credential is flagged
as a test credential. Any valid bearer token; no scope. It exists so a test
suite can ask *which database am I about to write to* before it writes —
until now nothing could, and the answer had been wrong for 154 sessions.

```json
{"database": "test19", "database_class": "test",
 "accepts_test_writes": true, "credential_is_test": true}
```

`accepts_test_writes` is derived server-side and is true only for `test`. Do
not re-derive it from `database_class`: a client that computes the policy
itself is a client that can disagree with the server about which databases
are safe.

**`workflow` block on the request serializer (ADDITIVE).**
`GET /api/v1/requests/<id>` and the list route now publish:

```json
"workflow": {"payment_ref": "PAY-2026-04412", "workspace_ref": null}
```

Both sit on the request form and neither had ever been readable over the API.
A Finance Officer tracing a payment reference could not, and neither could an
auditor — report 24 §8 listed it as a financial fact invisible to every role.

**They are written by different paths.** `payment_ref` is written by the
WorkSpace/Workflow **approval callback** — that is the field the measurement
was about. `workspace_ref` is written by the **outbound send** path, and is
measured at **0 of 407** requests across every local tenant, so a consumer
should expect `null` there and not build on it. Either key may be `null`.

**`allowed_values` joins `allowed` on three settings refusals (ADDITIVE, with
a DEPRECATION).** The two unknown-FM-domain refusals on `/api/v1/asset-categories`
(POST and PATCH) and the logo-prefix refusal on the brand settings route
published the accepted set as `details.allowed`, where every other refusal in
this API uses `details.allowed_values`. A client keying on the standard name
got nothing from these three and had no way to know they were the odd ones
out.

Both keys now carry the same list.

> **DEPRECATED: `details.allowed`.** Read `details.allowed_values` instead.
> `allowed` keeps answering with the identical list until the next major
> version of this API, at which point it is removed. A published details key
> is API surface like any other, so renaming it outright would break any
> client reading it today — which is why this is two keys and a date rather
> than a rename.

**Not a published change, but worth an integrator's attention.** Both test
suites now refuse to run against any database not explicitly marked
`cadra.database_class = test`, and absent refuses. That is a change to how
Cadra is developed rather than to what it serves, and no route behaves
differently because of it — but if you run this repository's suite against
your own deployment, mark your database first. The refusal prints the command.

## 2026-09-14 — handoff 23

### ADDITIVE · `GET /api/v1/reports/access-changes` — and the statement that it cannot answer the question as asked

Specification §13.4's fourth standard report. Scope **`identity:read`**. `from` and `to` are required, both bounds inclusive of the whole day; a missing, unparseable or reversed period is a `400 invalid_request` naming the parameter.

**Read `data.summary.statement` before `data.events`.** Cadra holds no record of group grants or removals, and this endpoint does not pretend otherwise. `res_groups_users_rel` is two integer columns with no timestamp and no actor; `res.users.group_ids` carries no tracking; `ir_logging` is empty on every tenant. No history is synthesised.

- `summary.coverage` — `none` | `partial`. **Branch on this, never on `statement`**, whose wording may be improved. There is deliberately no `empty`: the record cannot hold a group change in any period, so a quiet quarter and a busy one give the same answer to the question §13.4 asks, and an `empty` would imply some other period might have answered it. `partial` is unreached today and exists so that a deployment which grows an access history is described rather than misreported.
- `summary.group_changes_in_period` — a **structural zero** at the time of this entry, present so the absence was visible rather than inferred from a missing key. **Superseded in 19.0.3.8.0 (handoff 24):** it is now a real count read from the append-only access record, and `summary.coverage` gained the value `recorded`.
- `data.events` — what IS evidenced: `account_created` (`precision: exact`) and `account_modified` (`precision: last_write_only` — one write stamp covers every change ever made to the record, and it does not say which field moved). Each row names its `evidence`.
- `data.roster` — present-tense access: each account's groups and, for an integration, its API scopes. Current state, never history.
- `data.fidelity` — re-measured on **every request** rather than carried as a constant, so a deployment that grows an access history is described rather than misreported.

`data` is an OBJECT, not an array, for the same reason the register snapshot's is: there is nowhere honest to put a boundary declaration on an array, and a boundary a consumer can miss by reading the obvious key is not a boundary.

### ADDITIVE · `GET /api/v1/reports/configuration-changes` — thin, and it says so

Specification §13.4's fifth standard report. Scope **`settings:read`** (new — see below). Same period semantics.

For each key exactly three facts survive: the **current** value, the **last** writer, the **last** write time. Not the previous value, not the number of changes, and a deleted key leaves no tombstone. `res.config.settings` is transient and vacuumed, so a change made through the Settings screen leaves only the resulting parameter row. Measured estate-wide: **22 keys have ever been written after creation, 12 of them by a named human.**

**Values whose KEY names a credential are redacted** — replaced by `[redacted] sha256:<16 hex>`, with no prefix, no last-four and no length. `ir_config_parameter` holds `myservice_api.jwt_secret`, the key every access token in the tenant is signed with. `value_is_redacted` marks the row; `summary.redacted_values` counts them. The rule matches the key name rather than a list of known secrets, so it over-redacts rather than under-redacts.

### ADDITIVE · `POST /api/v1/assets/<id>/approve-disposal`

Scope **`approvals:write`**, idempotent (`X-Idempotency-Key`), success `200`, and `409` is a declared response.

Report 16 named this as a gap and it is now closed **without making the approver writable**. `disposal_approved_by` and `disposal_approved_date` remain absent from `_WRITABLE_FIELDS`; nothing about `PATCH` changes. The route records **the authenticated caller**, derived from the credential — since handoff 08 every API client acts as its own `res.users`, and Odoo 19's `sudo()` does not change `env.uid`.

- **A body that names an approver is refused `400`, not ignored.** `disposal_approved_by`, `approved_by`, `approver`, `user_id` and six further spellings are rejected by name. Dropping them would return `200` to a caller that believes it appointed somebody, and the recorded approver would then not be the one in the caller's own logs.
- **`409 conflict`** when the disposal is already approved, carrying who holds the approval and when. An approval is a one-time act; a second caller is told rather than quietly succeeding. Replaying with the same idempotency key still returns the original response.
- **`400`** when the asset is not in `disposed` state, carrying the model's own words.

`approvals:write` gated nothing asset-related before this, so granting it to a client is a deliberate act rather than something a broad credential already carries.

### ADDITIVE · `settings:read`, and the `Auditor` group

**`settings:read`** is a new scope. It gates the configuration change log only. A read scope rather than a reuse of `settings:write`, because an auditor whose only way to read the settings is to hold the right to change them is an auditor the control has been handed to. Granted by `myservice_asset_register.group_asset_manager` and by the new group below; it is in `ALL_SCOPES`, so it can be put on a client record.

**`myservice_api.group_auditor`** is new — specification §3's `audit_viewer`, which INT-10 §4.3 had recorded as absent. Six READ scopes (`assets:read`, `locations:read`, `requests:read`, `identity:read`, `dashboards:read`, `settings:read`) and no write scope of any kind. Implied by nothing and implying nothing, deliberately: an auditor who is also an Asset Manager is not independent of what they are auditing.

### WIDENING · what `identity:read` now reaches

No route's scope changed and no scope was removed, but **`identity:read` reaches more data than it did**, and that is worth saying plainly rather than leaving inside "additive".

Before this release it reached `hr.employee` only. `GET /api/v1/reports/access-changes` now returns, for **every account on the tenant**: `login`, `name`, `active`, the full Odoo group list, the creating and last-writing user, and — for an API client — its `api_scopes`.

**Every existing holder of `identity:read` gained that**: Vendra's client, the demo clients, and any `group_asset_user` session. It is account enumeration plus inter-client scope reconnaissance, and nobody separately decided to grant it. It is the data §13.4's fourth report is *for*, and `identity:read` is the identity register's scope, so the grouping is right — but if that reach is wider than a deployment wants, the fix is to narrow which clients hold `identity:read`, not to expect the report to withhold it.

No password hash, client secret or token is published in any field.

### Summary

**No existing credential loses anything.** Every scope above is additive, no route's existing scope was altered, and the one widening is the paragraph above.

## 2026-09-14 — handoff 22

### BREAKING · A cursor we did not issue is refused, not silently restarted

**Affects every paginated endpoint** — `GET /api/v1/assets`, `/locations`,
`/requests`, `/identity/employees`, `/fleet/vehicles`, the disposal schedule
report, and anything else taking `?cursor=`.

A `cursor` that is not a token this API issued now answers
**`400 invalid_request`**, naming the parameter and echoing the offending
value in `details.cursor`.

It used to answer `200` with the FIRST page. That was documented — `{}` meant
"start from the beginning" — and it is being withdrawn anyway, because
documented silent degradation is still silent degradation. A caller paging
with a corrupted cursor restarted at page one *while believing it was on page
three*: it walked the same records again, or read a later page as empty and
concluded the register had ended. Nothing in the response distinguished that
from a genuine answer. A client sending a cursor it did not get from us has a
bug, and a refusal is the only way it finds out.

Three inputs previously gave three different wrong answers and now give the
same right one:

| cursor | before | now |
|---|---|---|
| not decodable (`"not-a-cursor"`) | `200`, page one | `400 invalid_request` |
| decodes to JSON that is not an object (`[1,2]`) | `200`, page one | `400 invalid_request` |
| `{"last_id": "abc"}` | **`500 internal_error`** | `400 invalid_request` |

**An absent or empty `cursor` is unchanged and still means "start at the
beginning".** That is a different input and it keeps its answer; only a value
we cannot read is refused.

**What a consumer must do:** send back `pagination.next_cursor` byte for byte,
or omit the parameter. Do not construct, decode, truncate or re-encode a
cursor — it is opaque and its contents are not contract. Any client already
doing that is correct and sees no change.

### ADDITIVE · `GET /api/v1/meta/enums` — every Selection set, from the model

New route. Any valid bearer token may call it; no particular scope.

Returns each published Selection field as `[{value, label}]`, keyed by field
name, **in the model's own order** — `priority`, `location_type`,
`asset_level`, `domain`, `condition`, `asset_state`, `fuel_type`. The values
are read off the live Odoo Selection at request time, so a value the model
gains appears here the same day and a value it never had cannot appear at all.

Until now the only way a client could learn a field's accepted values was to
send a wrong one and read `allowed_values` off the 400 (handoff 21) — a
refusal doing documentation's job, and useless for populating a control before
the user types anything. The enums in `/api/v1/openapi.json` are hand-written
literals in the route annotations rather than reads of the model, which is a
copy with the same failure mode in a second place.

`asset_state` rather than `state`: `state` is the most reused field name in
this schema, and a client keying a cache on the bare name would collide the
first time a second one were published.

**Order is significant for `priority`** — its keys are the strings `"0"`–`"4"`
and they read like a scale. `"2"` is **High**, and the model's default is
`"1"`. A blank form must start on the default value, not on the middle of the
list.

### ADDITIVE · `POST /api/v1/home/quick-submit` publishes all five priorities

Its `request_schema` declared `priority` as `["0","1","2","3"]` and described
`3` as "urgent". The model declares `0=Low, 1=Normal, 2=High, 3=Critical,
4=Very Urgent`. Both halves were wrong.

Nothing changes about what the route accepts — `4` was always accepted by the
ORM, so this corrects the document to match the behaviour. Per `CLAUDE.md`
architecture rule 4 the model is the published surface: validating against the
four would have been the breaking change, because it would have started
refusing a `priority=4` the register already stores. Handoff 21 corrected the
same defect in the `/api/v1/requests` annotations and did not reach this copy.

---

## 2026-09-10 — handoff 21

> Written in handoff 22. Handoff 21 shipped the change below and did not
> record it here, which is the gap this file exists to close — the rule is
> whether a consumer could branch on it, and a consumer could branch on every
> line of it.

### BREAKING · A filter we cannot read is refused, not dropped

**Affects roughly 26 query parameters across `GET /api/v1/assets`,
`/locations`, `/requests`, `/identity/employees` and `/fleet/vehicles`.**

A filter value the parser could not interpret used to append no domain term,
so the caller received the list they would have received **with no filter at
all**. Those values now answer `400 invalid_request`, naming the parameter and
carrying the accepted set in `details.allowed_values`.

- **Booleans** (`is_verified`, `has_sap_code`, `has_coordinates`,
  `has_deadline`, `is_staff_bus`, …) — anything but `true`/`false` was
  dropped, and the response was the whole register. This is the dangerous
  half: an empty list reads as "no matches", **a full list reads as an
  answer**, and `GET /assets?has_sap_code=false` is "which assets has finance
  not booked". An auditor satisfying themselves from that list was handed a
  false statement.
- **Enums** (`state`, `condition`, `domain`, `asset_level`, `priority`,
  `kanban_state`, `location_type`, `fuel_type`, …) — an unrecognised value
  answered `200 []`, indistinguishable from a value that genuinely matched
  nothing. `?sap_reconciliation_state=exceptions` — the plural, the natural
  typo — is the worst of them.
- **Foreign keys** (`category_id`, `location_id`, …) — sat inside
  `except (TypeError, ValueError): pass`, so `?category_id=laptops` returned
  every asset on the register.

The accepted values are read off the model at request time, so a value the
model gains is accepted by the filter that publishes it on the same day.

**What a consumer must do:** send `true`/`false` for booleans (not `1`/`0`,
not `yes`), integers for id filters, and a published value for enums — or read
`details.allowed_values` off the refusal. A client already sending correct
values sees no change.

**The `limit` clamp is deliberately NOT part of this.** A `limit` above the
caller's ceiling is still clamped silently rather than refused: the ceiling is
per-credential, so a caller cannot know it in advance, and clamping and
refusing are answers to different inputs.

---

## 2026-09-10 — handoff 20

### ADDITIVE · A late `payment_ref` on a replay is recorded, and says so

**Affects `POST /api/v1/integrations/workflow/callback` and
`POST /myservice/workflow/callback`.**

Handoff 18 made a replay name what it was dropping. It still dropped it. A
payment reference is exactly the thing somebody looks for later and does not
find, and both `payment_ref` and `comment` are optional in the published
schema — so sending the approval when it is granted and the reference when it
clears has always been within contract.

A repeat whose `payment_ref` differs from the one Cadra already holds now
writes it to the request, and reports that it did:

- v1: `data.stored_fields: ["payment_ref"]`, **beside** `_warnings`, not
  inside it. Every other `_warnings` block on this API means "what you sent
  that did not take effect"; a field we accepted and wrote is the opposite,
  and filing it under warnings would make every late reference look like an
  anomaly to anything alerting on that key.
- Legacy: `stored_fields` on the bare body, and the `message` no longer
  claims "nothing changed" when something was recorded.

**`replayed` is still `true`** and the outcome is still not applied a second
time. None of the five effects a replay is forbidden happens: no stage write,
no `date_moved`, no `request.event` row, no chatter, no second dispatch-log
row. `discarded_fields` keeps its exact meaning and now fires only on what
genuinely has nowhere to go.

The log level for this case moved from WARNING to INFO. It is the contract
working, and a level that says "look at this" on the correct path is how a log
stops being read.

### BEHAVIOUR CHANGE · A second `queried` carrying a NEW question is applied

**Affects both callback routes.** Deduplication for `queried` is now on the
pair `(outcome, comment)` rather than on the outcome alone.

A decision arrives once — a second `approved` is the same approval
redelivered. A question does not: a workflow engine can legitimately ask a
second, different question while the first is still open, and comparing the
outcome alone swallowed it. The text is the only thing that separates a new
question from a redelivery, so the text is what is compared, against the
verbatim comment on the last inbound dispatch-log row.

**What a consumer sees change:** a `queried` callback whose comment differs
from the previous one now answers `"replayed": false` and applies — new
chatter, the dispatch log updated — where it previously answered
`"replayed": true` with the question reported as discarded. **A redelivery of
the SAME text is unchanged**: still a replay, still writes nothing, still
warns about nothing. This is marked a behaviour change rather than a fix
because a consumer branching on `replayed` sees a different value for a POST
it could have sent yesterday.

`approved` and `rejected` are deliberately NOT included. A second approval
carrying a different note is still one approval; treating the note as a new
decision would re-apply a stage.

## 2026-09-10 — handoff 18

### BEHAVIOUR CHANGE · A replayed workflow callback writes nothing

**Affects `POST /api/v1/integrations/workflow/callback` and
`POST /myservice/workflow/callback`.**

Both routes used to act on the CALL. A second byte-identical POST answered
success and applied the outcome again — appending a second dispatch-log row,
re-posting chatter, and re-writing the configured approved stage. Where a
human had moved the request onward after the first approval, the replay
**dragged it back**, and the request's own audit trail gained a
`stage_changed` event for a stage that had not changed.

They now fire on the TRANSITION. An outcome already applied is a no-op that
answers success and writes nothing at all.

- v1: `data.replayed` is `true` on a replay and `false` on a first
  application. Additive field; a consumer that ignores it sees the same 200 it
  saw before.
- Legacy: `"replayed": true` is added to the bare `{"ok": true, …}` body, and
  the `message` says "was already applied … nothing changed". A consumer
  branching on `ok` is unaffected.

Re-sending a request to the workflow engine sets it back to `pending`, so a
second dispatch's decision is a second transition and applies normally.

**"Writes nothing" means the five effects above.** A v1 replay still stamps
the calling client's `last_used_ip` / `last_used_at`, and still records an
idempotency entry when you send `X-Idempotency-Key`, because it answers a
success envelope. Nothing on the request changes.

**A repeat carrying data we do not already hold is reported, not swallowed.**
`payment_ref` and `comment` are both optional, so sending the approval when it
is granted and the payment reference when it clears is within contract — and
a replay applies neither. Anything discarded that way is now named:
`data._warnings.discarded_fields` on v1, `discarded_fields` on the legacy
body, and a WARNING in the server log. Additive. An identical redelivery
reports nothing, so the field's presence means something was genuinely lost.
**A second `queried` carrying a different comment is a replay too**, and its
question is reported as discarded rather than applied.

> **Superseded by handoff 20**, above (this file is newest first), on both counts: a late `payment_ref` is
> now RECORDED rather than named, and a second `queried` carrying new text is
> APPLIED rather than replayed. The paragraph is left standing because it
> describes what shipped, and a consumer reading this file in order needs to
> see the state it is reading forward from.

### BREAKING · A contradicting outcome is refused `409`

**Affects both callback routes.** A callback carrying a DIFFERENT outcome
after a decision has been recorded — `rejected` on a request Cadra holds as
`approved`, or either after the other, or `queried` after either — is refused
and writes nothing. It used to be applied silently.

- v1: `409 conflict`, with `details.current_outcome` and
  `details.attempted_outcome`.
- Legacy: HTTP `409` with `current_outcome` and `attempted_outcome` in the
  body.

Applying it overwrites a recorded decision on the say-so of a message that may
be a stale redelivery arriving out of order, and nothing in the payload can
tell a genuine reversal from one. A real reversal is a human decision: re-send
the request to the workflow engine, which returns it to `pending`.

### BREAKING · The v1 callback answers `503 server_misconfigured` on an unconfigured tenant

**Affects `POST /api/v1/integrations/workflow/callback`.** It used to answer
**`400 validation_failed`** carrying *"No active Workflow integration
configuration found … Please configure one under Settings → WorkSpace
Integration"* — an internal navigation path in the published envelope, and a
validation code for a state that has nothing to do with the caller's payload.
It now answers `503 server_misconfigured` with the body *"Workflow integration
is not available"*; the configuration sentence goes to the server log.

**And it now refuses `queried` as well.** That outcome used to succeed on a
tenant with no WorkSpace configuration, because only the `approved` and
`rejected` handlers looked a config up. A callback from a workflow engine the
tenant is not wired to is not a thing to half-apply, and the legacy route has
refused all three since handoff 15.

`server_misconfigured` was documented as a 500-only code. It is 500 everywhere
else and 503 here, and `docs/api/cadra_api_endpoint_reference.md` says so.

### ADDITIVE · The v1 callback reconciles the outbound dispatch it answers

**Affects `POST /api/v1/integrations/workflow/callback`.** It always appended
a fresh inbound `workflow.dispatch.log` row and never touched the outbound
dispatch it was replying to, so on a tenant using this route an answered
dispatch read `sent` for ever. It now rewrites that row to the outcome, the
way `/myservice/workflow/callback` always has. Nothing in the response
changes; what changes is what an operator sees in the dispatch log.

### ADDITIVE · The generated OpenAPI declares the callback's `409` and `503`

`/api/v1/openapi.json` published only `200/400/401/403/404/500` for every
route, so a client generated from it handled the two new statuses in its
generic error branch. `POST /api/v1/integrations/workflow/callback` now
declares both. No behaviour change — the spec caught up with the route.

### BEHAVIOUR CHANGE · A request stage written to the value it already holds is no longer a move

**Affects `GET /api/v1/requests/<id>` (`data.dates.moved`) and
`?include=events`.** `request.request.write` treated any write mentioning
`stage_id` as a stage change, so writing a request's current stage back over
itself reset `dates.moved` and appended a `stage_changed` entry to the
timeline. It now records only an actual move.

The visible consequence: `POST /api/v1/requests/<id>/transition` along a route
whose `stage_to_id` equals its `stage_from_id` still answers success, and the
timeline and `dates.moved` correctly stand still. A consumer counting timeline
entries or polling `dates.moved` sees fewer of the first and less movement in
the second — because the ones that go away were never real.

### FIXED · `POST /api/sap/employee-sync` answered 500 instead of "Empty payload"

**Affects `POST /api/sap/employee-sync` and
`POST /api/sap/employee-sync/test`.** A body with no JSON-RPC `params` key —
`{}`, an envelope with empty `params`, or a raw JSON object — left `kwargs`
empty and reached `request.jsonrequest`, which does not exist on Odoo 19, and
raised `AttributeError`. The route answered a 500 on exactly the branch whose
intended answer is `{"success": false, "error": "Empty payload"}`. It now
answers what it intends.

(A genuinely empty body never got that far: Odoo's JSON-RPC dispatcher parses
it first and aborts `400 Invalid JSON data` before any handler runs. An
earlier draft of this entry said otherwise.)

Both routes also now refuse a JSON body that is neither an object nor a list
of objects — `["a","b"]` or a bare number used to reach `.get()` and raise,
which on the `auth='none'` route was a 500 for a malformed payload.

---

## 2026-09-10 — handoff 17

### BREAKING · Four routes outside `/api/v1` now refuse an unconfigured credential

**Affects `POST /myservice/workflow/callback`, `POST /api/myservice/assets/export`,
`GET /api/myservice/assets/export/csv` and `POST /api/sap/employee-sync`.**
These are the routes the NRS WorkSpace, Redhubs and SAP SuccessFactors call.
They are listed as breaking in `docs/api/EXTERNAL-SURFACES.md`, which is what
puts them in this file's scope.

**This is a live cutover on every tenant, not a gradual one**, because on
every tenant measured the credential was unconfigured:

| | measured at handoff 17 |
|---|---|
| tenants with `workflow.config.callback_token` set | 0 of 8 |
| tenants with `myservice_identity.redhubs_api_key` set | 0 of 8 |
| tenants with `myservice_identity.sap_webhook_secret` set | 0 of 8 |

**What changed.**

- **`/myservice/workflow/callback` answers a NEW `503`** when the tenant has
  no `callback_token`. It previously performed **no authentication at all** in
  that state — the token check was `if config.callback_token:`, so an absent
  credential and a passing check were the same code path, on the endpoint that
  approves and rejects requests. Proved live before the fix: an anonymous POST
  carrying a deliberately *wrong* token was answered `404 "Request '…' not
  found"`, which is a reference lookup, which is past the gate. `503` is a
  status this route has not returned for this reason before; WorkSpace should
  treat it as "not configured here", not as "retry later and it will work".
- **The two Redhubs routes and the SAP webhook answer `Unauthorized`** where
  they previously fell back to a credential literal committed to this
  repository. Any caller relying on that default stops working until an
  operator sets the parameter. The literals are compromised and are being
  rotated; they are in git history and cannot be removed from it.
- Every refusal is logged at **ERROR** naming the exact `ir.config_parameter`
  or field and the tenant database, so the cutover is findable in a log rather
  than discovered from a support call.

**How to restore service.** Set the credential on the tenant. For WorkSpace,
`workflow.config.callback_token` (Settings → WorkSpace Integration); for the
others, the `ir.config_parameter` named in the ERROR line.

### DEPRECATED · Credentials in a query string, removed next release

`GET /api/myservice/assets/export/csv` takes `X-API-Key` and
`POST /myservice/workflow/callback` takes `X-Callback-Token`. Both still
accept the old `?api_key=` / `?token=` query parameter **for one more
release**, and both still *compare* it — a wrong one is still a `401`. Every
use logs a WARNING naming the caller's IP, so the migration has a visible end
date rather than an assumed one.

A credential in a URL is in nginx's access log, every proxy in front of us,
and the caller's browser history. Send the header.

The callback additionally distinguishes a token sent as a **form field** from
one sent in the **query string**, because only the second is exposed in access
logs and a migration list that conflates them is wrong about who is at risk.


### REMOVED · `no_sap_asset_number` is no longer a disposal-report finding

**Affects `GET /api/v1/reports/disposals` only. Vendra reads none of this and
writes none of it.** Shipped in handoff 16 on 2026-09-09 and removed one day
later, before anything downstream can have come to depend on it — which is
what makes removing it the honest option rather than deprecating it in place.

`no_sap_asset_number` **can no longer appear in any row's `findings`**, and no
longer appears in `summary.findings`. It is removed from the `findings` enum
in `/openapi.json`: a documented value the endpoint cannot return is a value
an integrator writes a branch for and never sees fire.

**Why.** It fired on close to every row — 2 of 11,942 assets on `nrs19` carry
a SAP asset number and none does on any other tenant — and a control that
fires on ~100% of rows is one a reader learns to skip. That cost is not
confined to the noisy finding: `no_approver` and `no_authorising_reference`
sit in the same column and get skimmed with it.

**Nothing true was hidden.** The fact is published in two places, both of them
unchanged or new:

- **Per row**, as it always was: `sap_asset_number`, `null` where there is
  none. No row lost any data in this change.
- **Once for the period**, in the new `summary.sap_coverage` below.

### ADDED · `summary.sap_coverage` on the disposal report

Additive. A new object on `data.summary`, describing the WHOLE PERIOD on
every page like the rest of the summary:

```json
"sap_coverage": {
  "total": 63,
  "with_sap_asset_number": 0,
  "without_sap_asset_number": 63,
  "coverage": "none",
  "statement": "No disposal in this period carried a SAP asset number, so INT-09 sent no disposal instruction to the financial system for any of them."
}
```

**`coverage` is the field to branch on.** Four values, and they are published
API surface:

| value | meaning |
|---|---|
| `empty` | the period holds no disposals at all |
| `none` | disposals exist and not one carried a SAP asset number |
| `partial` | some did and some did not |
| `complete` | every disposal in the period carried one |

`empty` and `none` are kept apart deliberately even though both counts are
zero: *"no disposal carried a SAP asset number"* is true of the empty set and
reads to a human as a finding about disposals that do not exist.

**`statement` is prose for a reader, not a contract.** The wording may be
improved without notice; `coverage` may not. It is deliberately **not
translated** — a published payload whose text changes with the acting user's
language cannot be stored, diffed or reconciled against last quarter's run.

**The statement is period-scoped and stays that way.** It says *"no disposal
**in this period**"*, and does not claim INT-09 has never sent a disposal
instruction at all. This report reads one period; a disposal outside its
bounds could carry a SAP number, and asserting "never" from a bounded window
is the same defect as counting a register from a page of it.

---

## 2026-09-09 — handoff 16

### ADDED · The two audit reports the specification names (§13.4)

**Additive. Nothing removed, no enum value changed, no error code changed.**
Vendra reads none of this and writes none of it.

**`GET /api/v1/reports/asset-register?as_of=YYYY-MM-DD`** — the register as it
stood at a past date. Scope `assets:read`. `as_of` is REQUIRED and a future
date is a `400`: a snapshot that quietly means "today" is `GET /api/v1/assets`
wearing a report's name.

**`data` is an OBJECT on this route, not an array** — the only list endpoint
in this API where that is true, and it is deliberate. The rows are at
`data.assets`, **inside** `data.fidelity`, which names every field the
snapshot rolled back (`rolled_back`, 28), every field published at its
CURRENT value because no history supports a rollback (`as_of_today`, 21), and
every field it cannot answer at all (`not_recoverable`, 23). A row degraded
beyond that carries its own `_fidelity`. An array had nowhere honest to put
the boundary, and the envelope's `_warnings` is the one part of the body a
client reading `body["data"]` never sees — a boundary a consumer can miss by
reading the obvious key is not a boundary.

**Read the declaration before reconciling any figure.** A snapshot that
silently mixed as-of-the-date with as-of-today would produce a discrepancy in
an audit, and the discrepancy would be ours.

`data.cutoff` is the exact instant the rollback cut at, naive UTC, with
`fidelity.notes.cutoff` saying which day boundary was taken — end of day
**Africa/Lagos**, which is 23:00 UTC. `data.filters` records that filters
match CURRENT values: the rows are rolled back, the selection is not.

**`GET /api/v1/reports/disposals?from=YYYY-MM-DD&to=YYYY-MM-DD`** — disposals
in a period with the documentation behind each. Scope `assets:read`. Both
bounds INCLUSIVE. `data.rows` pages; `data.summary` describes the WHOLE
PERIOD on every page, so *"41 of 63 carry no authorising reference"* is one
read of page one. `summary.total` and `pagination.total_estimate` come from
one model call and cannot disagree. Rows are ordered by ascending asset id,
because cursor pagination walks ascending ids and a date-ordered list cannot
be paged honestly with this cursor; every row carries `disposal_date`.

**A disposal with no authorising reference is never filtered out** — it
appears carrying `no_authorising_reference` in `findings`. `data.unplaceable`
carries disposals that belong to no period at all, in full and uncapped:
dropping them makes them invisible in every report, and putting them in one
period double-counts them in the next.

Findings: `no_authorising_reference`, `no_approver`, `no_approval_date`,
`no_disposal_method`, `no_disposal_date`, `no_disposal_reason`,
`no_proceeds_recorded`, `disposal_date_reconstructed`, `no_sap_asset_number`.

**Both reports are READ-ONLY and neither repairs what it finds.** A report
that quietly fixes what it finds can never honestly report zero. Proved by
fingerprinting every table they read, before and after six calls: identical.

### ADDED · `data.disposal` on the asset serialiser, and three writable fields

`data.disposal` carries `date`, `date_reconstructed`, `method`, `reference`,
`approved_by`, `approved_at`, `proceeds`, `currency`, `reason`. Grouped like
`provenance` and `sap`. `dates.disposal_date` and the top-level
`disposal_reason` are unchanged and are not going away.

**Newly writable:** `disposal_method`, `disposal_reference`,
`disposal_proceeds`.

**Deliberately NOT writable:** `disposal_approved_by`,
`disposal_approved_date`, `disposal_date_reconstructed`. `no_approver` is one
of the report's own findings — a client able to PATCH the approver could
create a disposal and name any user as its authority in the same request,
turning that finding into a clean row without anybody having authorised
anything. An approval is recorded from the acting user by
`action_approve_disposal`. A writable approval date beside a read-only
approver would additionally let a caller backdate an approval across a
financial year. Rejected fields are reported in `data._warnings.rejected_fields`,
never dropped silently.

**Consequence, stated rather than hidden:** there is currently **no API route
that records a disposal approval**. That is a gap and not a control; closing
it needs its own scope decision.

### CHANGED · The outbound `asset.disposed` SAP event carries the authorisation

**Not an `/api/v1` surface — it is INT-09, outbound to SAP — and it is in this
file because the scope note above says it should be.** `disposal_type` was a
hardcoded literal `'disposal'` on every event ever sent, and no approver went
with it, while `asset.transferred` has carried `approved_by`/`approved_at`
since the day it was written. `disposal_type` is now derived from
`disposal_method`, so a scrapping or a write-off sends `retirement` where the
SAP requirements document §4.2 always said it should; `disposal_method`,
`reference`, `approved_by`, `approved_at`, `proceeds` and `proceeds_currency`
are new keys.

**Additive and non-breaking.** An asset with no recorded method — every asset
on every tenant today — still sends `disposal`, the exact value SAP has been
receiving. New keys are **present and null** where Cadra does not know, rather
than omitted: a receiver seeing a null knows Cadra does not know, where one
seeing no key cannot tell that from a Cadra too old to send it. The mapping is
in `docs/integrations/INT-06-07-09-sap-requirements.md` §4.2.

### CHANGED · `disposal_date` and `disposal_reason` are now tracked

They were not, which meant the two fields an auditor reads first on a
disposal could be changed with no record. Five new disposal fields are
tracked from birth. No API shape changes; what changes is that a change to
any of them now leaves a trail.

---

## 2026-09-09 — handoff 15

### WIDENING · The chain of custody is exempt from the per-credential record cap

**Who is affected:** any client provisioned with a `total_record_cap` — the
external default is 100 records of any one resource across all cursor pages.
This is a widening, so it breaks nobody. It is listed because a client that
built around 100 links should be able to find out that it no longer is.

`GET /assets/<id>/custody` now returns the **whole** chain however the
credential is capped. `include=custody` always did, because it does not
paginate — so until today the same question had two answers, one of them
silently shorter, depending on which way you asked it.

The cap is not going anywhere else. A chain of custody is not a page of a
register: it is one asset's complete record, bounded by how often that asset
changed hands rather than by how much data a tenant holds, and **a truncated
chain cannot be told from a complete one** — which is the entire finding the
model was built to close. `total_estimate` is the true count on both paths,
as everywhere.

The per-page ceiling is unchanged. It bounds the cost of one `SELECT` and is
not the commercial control; a capped client walks the whole chain with the
cursor.

### ADDITIVE · `GET /dashboard/fleet-command` names a panel it could not build

**Who is affected:** anybody reading the fleet-command payload. The new key is
present only when something failed, so its absence carries no meaning and a
client that never looks is unaffected.

Three panels — vendor performance, compliance alerts and recent maintenance
logs — returned an empty list for any failure, with nothing anywhere saying
so. Two of the three had been empty on **every tenant since they were
written**, because they read fields that do not exist on Odoo's fleet models:
compliance counted an `insurance_expiration_date` that is in no version of
`fleet.vehicle`, and the maintenance log read a `service_id` off
`fleet.vehicle.log.services`, which has `service_type_id`. Both are fixed.

A panel that now fails is named:

```json
{ "data": { "...": "...", "_warnings": { "unavailable": ["vendors"] } } }
```

A key listed there means the value in this payload is a placeholder, not an
answer. `[]` and "I could not build this" were the same response until today.

**This is not the envelope's `_warnings`.** The truncation warning
(`_warnings.truncated`) is a **top-level** key, because a list endpoint's
`data` is an array with nowhere to hang it. This one is inside `data`,
alongside `rejected_fields`. Both can appear in one response, at different
depths — a client reading warnings should look in both places.

### BEHAVIOUR CHANGE · `POST /integrations/sap/employee-sync` no longer reports rows it then destroyed

**Who is affected:** anybody sending more than one employee in a batch. The
response shape is unchanged; what changes is that it is now true.

The per-employee handler isolated a failed row by calling `rollback()`. A
rollback is not row-scoped — it discards everything since the last commit —
so one unmappable employee erased **every employee written before it in the
same request**, while the `results` array had already recorded them as
`"status": "success"`. A caller reconciling against that array believed it
had written rows that no longer existed, and nothing in the response said
otherwise.

Each employee is now applied inside its own savepoint. A failure undoes that
employee and nothing else, `status` is `error` for it and stays correct for
the rows before it, and `error_message` carries the exception type as well as
its text — several ORM and Postgres errors stringify to an empty string, so
some callers were shown nothing at all.

The same fix applies to the file-upload path
(`POST /integrations/employees/import`, read back with
`GET /integrations/employees/import/<job_id>`), where a batch is 200 rows
between commits. That job's `error_samples` also returned `[]` when its own
stored error list could not be read — "no errors" for a job full of them —
and now returns an entry saying the detail is unreadable.

### NEW ENUM VALUE · `source: "test"` on a custody link

**Who is affected:** anybody reading `source` off a custody link. Additive —
a new value in an existing enum. If you branch on `source`, treat an
unrecognised value as "not a live change of custodian" rather than failing.

Cadra's own API test suite runs against live-shaped tenants and moves an
asset's custodian on purpose, because a test that does not exercise the
recorder proves nothing about whether the chain is written at all. The
recorder is append-only, so those links are **permanent**.

`source: "test"` is how you can tell. It is decided server-side from the
credential that made the change and never from anything a caller sends —
a header saying "this one is a test" would let anybody disguise a real change
of custodian as an artefact, in the one model whose whole value is that its
contents were not invented.

Same argument as `tracking_backfill`, one step further on: a reader of the
chain must be able to see what a link is without being told the artefacts
exist.

---

## 2026-09-09 — handoff 14

### NEW · The chain of custody is readable — `GET /assets/<id>/custody`

**Who is affected:** anybody asking who has held an asset. Nothing existing
changes shape.

Cadra now keeps an append-only record of every change of custodian, on a new
`nrs.asset.custody` model. Until this release the chain lived in Odoo's
chatter tracking values: no route exposed it, and a user with the right
groups could delete it. The PRD requires a record that *"cannot be edited
retrospectively, only appended"*, and a chain of custody that can be deleted
is not a chain of custody.

Two ways to read it:

```
GET /api/v1/assets/<id>/custody          # paginated, oldest first
GET /api/v1/assets/<id>?include=custody  # the whole chain, embedded
```

Both need `assets:read`. **There is no write endpoint and there will not
be** — a link is a side effect of a custodian change, never a payload, and a
route that accepted one would be a way to write history directly.

A link carries: `changed_at`, `from_custodian` / `to_custodian` (plus the
names **as recorded**, which survive the employee record being deleted),
`changed_by` — the acting user, which is a different question from who held
it — `reason`, and `source`.

**Read `source` before you draw a conclusion from a chain.** It is one of
`api_transfer`, `api_write`, `transfer`, `direct` or `tracking_backfill`.
`tracking_backfill` marks a link **reconstructed** from the chatter tracking
values that predate this model. The reconstruction is faithful — those rows
carry the actor and the timestamp — but it begins where `custodian_id` became
a tracked field, not where the register does. **A chain is therefore sparser
than the asset's own age, and that is the honest picture rather than a
defect.** An auditor told where the record begins can work with it; one who
discovers the gap later cannot trust any of it, including the complete part.

`include=custody` is deliberately **not** capped. The embedded `transfers`
list takes the last 20; "the last twenty custodians" is precisely the answer
an auditor cannot use, because a truncated chain cannot be told from a
complete one. The paginated route is there for a chain long enough to want
paging, and reports a true `total_estimate` like every other list endpoint.

> **Deployment note — schema before code, on every tenant.** This release
> adds a stored model (`nrs.asset.custody`), so `myservice_asset_register`
> must be upgraded on **every** tenant database *before* the image rolls
> forward. One Odoo registry serves them all: on a tenant that has not been
> upgraded, `nrs.asset.write({'custodian_id': ...})` reaches a table that
> does not exist and answers `500` with the transaction aborted — and that
> includes `POST /assets` carrying a custodian, which is on Vendra's INT-03
> path. The `upgrade-19` fan-out runs per database and must complete first.

### ADDITIVE · `custody_id` on the transfer-custody response

`POST /assets/<id>/transfer-custody` now returns
`data.custody_change.custody_id` — the append-only link that call produced.
Existing fields are unchanged.

### FIXED · Three auth routes answered HTML to a malformed body

`POST /auth/login`, `POST /auth/refresh` and `POST /auth/revoke` returned a
raw Odoo HTML 500 page — not a Cadra envelope — when an unauthenticated
caller sent a non-string where a string was expected. They now answer
`400 invalid_request` in the envelope, as `POST /auth/token` has since
handoff 12. `POST /auth/revoke` in particular documents that it always
answers `200 {"revoked": true}`, which was not true under a malformed body.

### ADMINISTRATIVE · A non-default record cap forces a one-hour token

`myservice.api.client` refuses to save a `token_ttl_seconds` above 3600 when
`max_page_limit` or `total_record_cap` differs from the default. The cap is
stamped into the access JWT and a JWT is unrevocable for its lifetime, so a
long-lived token is a raised limit that outlives the decision to lower it
again. Every client on every tenant is already at 3600, so nothing changes
today.

---

## 2026-09-08 — handoff 12

### BEHAVIOUR CHANGE · `pagination.total_estimate` now reports the TRUE count

**Who is affected:** every consumer of a list endpoint holding a token issued
by `POST /auth/token`. That is Vendra, and it will be Audit.

`total_estimate` used to report the size of the capped window, not the size of
the register. A credential limited to the first 100 records asked
`jaizbankplc` for its assets, received 100 rows, `next_cursor: null`, and
`total_estimate: 100` — while the tenant held 2,363. Nothing about that
response looked wrong.

It is now a `search_count` on the caller's own unclamped domain, on every
path. The rows a capped credential receives have **not** changed; only the
number describing them has.

**What this means for a consumer that already trusts `total_estimate`:** it
may now be much larger than the number of rows you can actually page through.
That is the honest picture. Compare it against what you received and branch on
the new `_warnings.truncated` block below rather than on `next_cursor: null`,
which cannot distinguish "that is everything" from "that is all you get".

Affected routes: `GET /assets`, `/locations`, `/locations/<id>/descendants`,
`/identity/employees`, `/identity/employees/<id>/assets`, `/requests`,
`/fleet`.

### NEW · `_warnings.truncated` on any response the record cap bit

A top-level envelope key, additive, present only when records were withheld:

```json
{"data": [...], "meta": {...}, "pagination": {...},
 "_warnings": {"truncated": {
   "cap": 100, "total": 2363,
   "reason": "This credential is limited to the first 100 records of any query. Filter the query, or contact WestMetro to raise the limit."}}}
```

It is a sibling of `data`, not a key inside it, because a list endpoint's
`data` is an array — unlike `data._warnings.rejected_fields` on the write
endpoints, which is unchanged.

**It describes the query, not the page.** Asking for 5 rows of a 2,410-asset
register warns on page one, because the wall at record 100 is already certain.
Telling you at the end of a twenty-page walk what you needed before you started
would be the same defect in a new place.

### NEW · `X-Cadra-Truncated` response header and a trailing comment on `export.csv`

`GET /assets/export.csv` bypasses the envelope, so a truncated file now
carries `X-Cadra-Truncated: 100/2363` and a final row beginning `# TRUNCATED:`.
A CSV that is silently a twentieth of the register is the artefact that gets
saved, emailed and cited.

### NEW · `total` on `GET /assets/export`

The JSON export's `count` was `len()` of a capped search, so a route calling
itself "export all assets" answered `count: 100` on a 2,363-asset tenant.
`count` still means "rows in this response"; the new `total` is the register.

### BEHAVIOUR CHANGE · the cap is per-client, not per-audience

It used to be decided by the `aud` claim, which only `POST /auth/login`
stamps — so the rule in force was "browsers are trusted, programs are not",
and the partner cap was pointed at Vendra, which holds a machine credential.
It is now decided by two fields on the client record (`total_record_cap`,
`max_page_limit`), stamped into the access token at mint time.

**Default is unchanged** (`0` = today's 100 on both), so an existing client
sees no difference. **The `vendra` client is uncapped by data migration on
every tenant** — as will be the audit client when INT-10 names one. Raising a
limit takes effect on the client's next token or refresh, i.e. within its TTL
(1 hour by default), not at the end of the 30-day refresh window.

### NO CHANGE · `POST /auth/token` still answers one 401 for every cause

Deliberately. Wrong secret, unknown client, archived client and a client id in
the wrong case (`Vendra` vs `vendra` — Postgres `=` is case-sensitive) are one
body, because distinguishing them is a client-id enumeration oracle. The cause
is now written server-side against the `request_id` the response already
carries; quote that id to WestMetro and the answer is one grep away. See
`docs/api/reading-an-auth-failure.md`.

---

## 2026-09-08 — handoff 10

### BEHAVIOUR CHANGE · `data.tagging.printed_at` / `printed_by` / `label_state` start moving

**Who is affected:** any consumer reading the `tagging` block, and anyone
filtering on `tag_label_state`.

`label_state` moves `issued → printed` from exactly one place —
`ir.actions.report._render_qweb_pdf`, the single funnel every print path goes
through. That hook declined to record anything whenever `res_ids` could be tag
label ids, and tag label ids and asset ids collide by construction: on the NRS
register **11,928 of 11,932 asset ids are also valid label ids**, 99.97%. So
the guard written for a rare edge case fired on the normal one. Every real
print was declined and the register held 11,879 labels at `issued` and exactly
one at `printed`.

The ids are now unambiguous — a report's `res_ids` are ids of the report's own
declared model, enforced where the caller hands them over — so:

| Field | Before | After |
|---|---|---|
| `data.tagging.printed_at` | `null` for effectively every asset | the datetime the label was rendered |
| `data.tagging.printed_by` | `null` | who issued the print instruction |
| `data.tagging.label_state` | `issued` until an affix skipped straight to `affixed` | `issued → printed → affixed` |
| `?tag_label_state=printed` | matched one row estate-wide | matches labels that have actually been printed |

**Nothing about the shape changes** — same keys, same types, same enum values.
What changes is that two of them stop being permanently null and one of them
starts visiting a state it was already documented to have. A consumer treating
`printed_at != null` as "a label exists on paper" gets the answer it always
expected; a consumer that had learned to ignore `printed` as a state that
never occurs should stop.

`is_tagged` is **unchanged**: it is still true only after an affix
confirmation whose scanned tag number matched the issued one. Printing is not
tagging.

### BEHAVIOUR CHANGE · `data.pm[].next_due_date` for a schedule that has never been serviced

**Who is affected:** any consumer reading the `pm` block on
`GET /api/v1/assets/{id}`.

A `nrs.asset.pm` row with an interval and no `last_done_date` reported
`next_due_date = today` — every day. That is not a due date, it is the absence
of one: it moved forward with the clock, so such a schedule could never be
overdue and the daily refresh rewrote the row on every tick. It now reports
`create_date + interval_days`, a fixed point, and can fall overdue like any
other.

Latent when shipped: there are zero `nrs.asset.pm` rows on any tenant, so no
consumer has ever seen the old value.

---

## 2026-09-07 — handoff 09

### BEHAVIOUR CHANGE · `error.code` — `forbidden` and `not_found` are reachable again

**Who is affected:** any consumer branching on `error.code` or on
`error.details.http_status`.

In Odoo 19 `AccessError`, `MissingError` and `ValidationError` are all
subclasses of `UserError`. The `cadra_route` handler chain caught `UserError`
first, so the `AccessError` and `MissingError` clauses beneath it were dead
code. Every Odoo-level access refusal answered `400 validation_failed` and
every missing record answered `400 validation_failed`. Two published error
codes were unreachable through that path for the whole life of the envelope.

The handlers are now ordered specific-first:

| Cause | Before | After |
|---|---|---|
| Odoo access refusal | `400 validation_failed` | `403 forbidden` |
| Record does not exist | `400 validation_failed` | `404 not_found` |
| Constraint / `UserError` | `400 validation_failed` | unchanged |

Routes that raise their own explicit `err(ERR_NOT_FOUND, …)` — which is most
of them — are unaffected; they never reached this path.

This corrects the envelope toward what the PRD §10.7 error table always said.
A consumer that pattern-matched on `validation_failed` to mean "any failure"
will now see the two more specific codes.

Guarded by `tests/test_source_guards.py::test_a_user_error_handler_never_shadows_a_more_specific_one`.

### BEHAVIOUR CHANGE · `GET /dashboard/{kpis,map,fleet-command}` — the scope is the gate

**Who is affected:** session tokens (`POST /auth/login`) holding
`dashboards:read`. API client tokens are unaffected in practice.

These three were the only routes in the API that did not `sudo()`. They read
`fleet.vehicle` and `generic.location` directly, so a caller holding
`dashboards:read` without the corresponding Odoo groups got an access refusal
carrying an Odoo group name — *"You are not allowed to access 'Vehicle'"* —
into the published envelope.

They now `sudo()` like every other route. Consequences:

- A caller **without** `dashboards:read` gets `403 forbidden` naming the
  scope, from the token gate, as on every other route.
- A caller **with** `dashboards:read` gets data. Previously a Security Officer
  holding the scope but no fleet group got an error; they now get the payload.
  That is the intended change: in this API the declared scope is the gate, and
  an Odoo group acting as a second, undeclared gate behind it is the defect,
  not the protection.
- No Odoo group name can reach a consumer through these routes any more.

The scope→group mapping in `utils.SCOPE_GROUPS` is retained as defence in
depth, not as the control.

Guarded by `tests/test_source_guards.py::test_the_dashboard_routes_sudo`.

### BEHAVIOUR CHANGE · `is_verified` on `nrs.asset` now expires

**Who is affected:** consumers reading `data.is_verified` or filtering with
`GET /assets?is_verified=`. Vendra does not read this field.

`is_verified` is a stored compute measured against today's date, but nothing
in the database changes on the day a verification lapses and nothing pushed a
recompute. It could therefore only ever move from `false` to `true` — an asset
verified once was reported verified for ever, and the field meant "verified
at some unknown point in the past", not "verified".

A daily cron now re-evaluates it, so the field can move `true → false` without
any write to the asset. The window is per-category
(`nrs.asset.category.verification_interval_days`), falling back to the tenant
parameter `cadra.assets.verification_interval_days`, falling back to 365 days.

**Nothing flips on any current tenant.** Measured across all eight local
databases: 17,123 assets, and `is_verified` is true on exactly **one** — a
single asset on `jaizbankplc`, the only one in the estate carrying a
`last_verified_date` at all, and recent enough to stay true under any of these
windows. (The ruling that prompted this said "true on zero assets"; it is one,
and that one does not move.) So this changes no value any consumer has ever
seen. It changes what the field will mean the first time anyone uses the
Verify button in earnest.

A permanent `true` is not a weaker version of this control. It is the
opposite of one.

### Additive · `verification_interval_days` on the asset-category settings API

Per-category verification window, in days. `0` or unset means "use the tenant
default" (`cadra.assets.verification_interval_days`, itself defaulting to 365).

- Serialised on `GET /settings/categories` and `GET /settings/categories/{id}`
  as `data.verification_interval_days` (integer, `null` when unset).
- Writable on `POST /settings/categories` and `PATCH /settings/categories/{id}`
  under `settings:write`, alongside its sibling `pm_interval_days`.
- Present in the OpenAPI request schemas for both write routes.

Additive and safe: a consumer that does not send it is unaffected, and a
consumer that does not read it sees no change. It is on the API rather than
back-office-only because `pm_interval_days` — the same kind of setting, the
same screen — already is, and a per-category cadence that can only be set in
Odoo would make the Settings screen quietly incomplete.
