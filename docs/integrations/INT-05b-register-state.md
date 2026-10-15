# INT-05b — `asset.register_state.changed` (Cadra → Vendra)

**Status:** built in Cadra (handoff 62, `myservice_workflow` 19.0.3.3.0).
**Not yet received by anything.** Vendra builds its receiver against this
document (Vendra handoff 57). It is **INT-05b** because it travels INT-05's
road, and INT-10 was already taken.

With the receipt gates on, a unit Vendra sends through INT-03 enters Cadra as
a *candidate* and passes up to seven gates before it is on the register. This
event tells Vendra each time one of its units moves, so Vendra can show where
the unit stands without anyone opening the receipt. Vendra's report 56 §4
designed it; Cadra built it to that design.

---

## When it is raised

**On every change of `register_state` of a unit Vendra sent.** Cadra changes
that state in exactly one place (`nrs.asset._gate_move`; handoff 62 searched
for another writer and found none), so nothing that moves a unit can miss it:

| The act | Who, in Cadra | The unit comes to rest at |
|---|---|---|
| submit | Store | `vfm_pending` |
| verify (single or batch) | IAD officer | `vfm_verified` |
| approve | IAD approver | `vfm_approved` (labelled unit) · `reg_ready` (`record_only` unit) |
| query | IAD officer or approver | `vfm_query` |
| resubmit (Store's answer to a query) | Store | `captured` |
| reject | IAD approver | `vfm_rejected` |
| request tagging | Asset Controller | `tag_issued` |
| affix | Tagger | `tagged` |
| register | Register Maker | `reg_submitted` |
| return the registration | Register Checker | `tagged` (labelled) · `reg_ready` (`record_only`) |
| approve the registration | Register Checker | `registered` |

**One event per act, for the state the act left the unit in.** Two acts make
two moves inside a single call: requesting tagging passes through
`tag_requested` on its way to `tag_issued`, and IAD's approval of a
`record_only` unit passes through `vfm_approved` on its way to `reg_ready`.
No unit is ever in the state it passed through when anyone could look, so
that state is never sent. A labelled unit therefore raises **seven** events
on its way to the register, and a `record_only` unit **five**.

**A batch is N events.** `POST /api/v1/candidates/gates/<action>` is N single
fires, so a batch verify of 20 units raises 20 events. A unit the batch
refuses raises none.

### When it is NOT raised

- **A unit Vendra did not send.** "Vendra sent it" means the asset carries
  `import_source = vendra` **and** a non-empty `grn_reference`, which is what
  INT-03 writes. Anything else (a unit registered in Cadra's own screens, a
  Vendra unit with no receipt reference) raises nothing, because Vendra has
  nothing to match it to.
- **With the gates off.** A unit is born `registered` and never moves, so
  nothing is ever raised. (A tenant that switches the gates off while
  candidates are in flight still moves those candidates. Each such move is a
  real change and is sent.)
- **The unit's birth.** INT-03 creates the unit at `captured` and Vendra
  already has Cadra's answer to that request. A change is a move *from*
  somewhere.
- **A move that rolled back.** The event is written to the outbox in the
  same database transaction as the move, so a refused unit in a batch, a
  `dry_run`, or any failure after the move takes its event with it.
- **A target with no Register-State Endpoint** (below). Nothing is queued,
  and the log says so (`target … has no register-state endpoint; … not
  queued`). This is the state of every Cadra tenant until its Vendra has the
  receiver.

---

## The request

```
POST <rest_base_url><rest_endpoint_register_state>
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>        # the same credential as INT-05
X-Idempotency-Key: <event_id>
X-Event-Id:        <event_id>
X-Request-Id:      WDL-2026-5170     # the Cadra outbox row; quote it in logs
```

The target is the **same** `workflow.config` record as INT-05 (purpose *Asset
lifecycle events*): the same base URL, credential, timeouts and retry policy.
The endpoint is its own field, **Register-State Endpoint**, because Vendra
receives this event beside `asset.tag.affixed`, not in place of it. Proposed
path: **`/api/method/vendra_network.api.cadra.register_state_event`**. If
Vendra names it differently, the field is set to Vendra's name and nothing
else changes.

### Body: Vendra's table, and nothing more

| Key | Always? | Type | What it is |
|---|---|---|---|
| `event_id` | yes | string (32 hex) | This event. Also in both headers. Stable across every redelivery. |
| `asset_id` | yes | integer | Cadra's id for the unit, the key Vendra matches on (never the serial). |
| `asset_code` | yes | string | The unit's asset code (`NRS-AST-…`), which names a tag-ID or record-only unit. |
| `grn_reference` | yes | string | The receipt, as INT-03 sent it. |
| `register_state` | yes | enum | Where the unit now stands. One of the eleven states in the table above. |
| `waiting_on` | yes | enum or `null` | Whose move it is: `store`, `iad`, `iad_approver`, `controller`, `tagging`, `maker`, `checker`, or `null` at `vfm_rejected` and `registered`. The same values as `gates.waiting_on` on `GET /api/v1/assets/<id>`. |
| `state_since` | yes | string, ISO 8601 UTC (`…Z`) | When the unit entered this state: Cadra's `register_state_since`, the column the Candidates list is ordered by. |
| `reason` | only at `vfm_query`, `vfm_rejected`, and a return | string | The words the actor typed: IAD's question, IAD's reason, the checker's reason. |
| `sap_asset_code` | only at `registered` | string | The SAP asset code the checker approved. |

**No person travels.** There is no name, email, login or user id of anyone
who acted. Vendra says *Internal Audit*, not who. There is no `event` key
either: the endpoint names the event. A key not listed here is never sent;
adding one would be announced in the Cadra API changelog.

### Ordering: keep the newest `state_since`

Two events for one unit can arrive out of order, because a retry of the
earlier one may land after the later one. **Keep the event with the newest
`state_since` and treat an older one as a no-op.** Cadra guarantees what makes
that safe: **`state_since` strictly increases per unit.** A database
datetime holds whole seconds, and two moves of one unit share a second every
time one act makes two moves, and whenever two people act within a second (a
test walk lands all seven in one second without the rule; measured in report
62). So the later move always carries a later value. If the clock has not
moved on, the later move takes the earlier value plus one second. The cost
is that `state_since` can run a second or two ahead of the wall clock.

### Examples, one per state

Real payloads from `test19` (report 62, `62-evidence/outbox.txt`), with
`event_id` and `grn_reference` as sent. The resubmit example is written by
hand: the drive did not resubmit, and the in-registry test pins the shape.

```json
{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "71d4b57c4a4346b383a7357fd57b00f2",
 "grn_reference": "GRN-H62-203142", "register_state": "vfm_pending",
 "state_since": "2026-10-15T19:31:47Z", "waiting_on": "iad"}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "73f14275d6c443669bbfaea16a201fc3",
 "grn_reference": "GRN-H62-203142", "register_state": "vfm_verified",
 "state_since": "2026-10-15T19:31:48Z", "waiting_on": "iad_approver"}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "dac0877cffe9439a8f79e545cd2795b1",
 "grn_reference": "GRN-H62-203142", "register_state": "vfm_approved",
 "state_since": "2026-10-15T19:31:50Z", "waiting_on": "controller"}

{"asset_code": "NRS-AST-063936", "asset_id": 100048, "event_id": "17dea404ca484593886940db2ac9a8f6",
 "grn_reference": "GRN-H62-203142", "reason": "Which invoice covers this unit?",
 "register_state": "vfm_query", "state_since": "2026-10-15T19:32:12Z", "waiting_on": "store"}

{"asset_code": "NRS-AST-063936", "asset_id": 100048, "event_id": "<32 hex>",
 "grn_reference": "GRN-H62-203142", "register_state": "captured",
 "state_since": "2026-10-15T19:40:02Z", "waiting_on": "store"}

{"asset_code": "NRS-AST-063937", "asset_id": 100049, "event_id": "3d92680f181f4e958f0f5ca8d0e0a951",
 "grn_reference": "GRN-H62-203142", "reason": "Not the model on the purchase order.",
 "register_state": "vfm_rejected", "state_since": "2026-10-15T19:32:15Z", "waiting_on": null}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "2aacd40903b94efca85857269a2b2409",
 "grn_reference": "GRN-H62-203142", "register_state": "tag_issued",
 "state_since": "2026-10-15T19:31:52Z", "waiting_on": "tagging"}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "77335a282fd34ef3b45b170897132311",
 "grn_reference": "GRN-H62-203142", "register_state": "tagged",
 "state_since": "2026-10-15T19:31:53Z", "waiting_on": "maker"}

{"asset_code": "NRS-AST-063938", "asset_id": 100050, "event_id": "77065b52071a45739fe9f8cbfeba0eef",
 "grn_reference": "GRN-H62-203142", "register_state": "reg_ready",
 "state_since": "2026-10-15T19:32:21Z", "waiting_on": "maker"}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "b14eb101226b4b58960e097c41dcba20",
 "grn_reference": "GRN-H62-203142", "register_state": "reg_submitted",
 "state_since": "2026-10-15T19:31:55Z", "waiting_on": "checker"}

{"asset_code": "NRS-AST-063929", "asset_id": 100041, "event_id": "3d6d35ade319447ab236fcdf648136e6",
 "grn_reference": "GRN-H62-203142", "register_state": "registered",
 "sap_asset_code": "SAP58-1792092713-585EA113",
 "state_since": "2026-10-15T19:31:56Z", "waiting_on": null}
```

A return by the checker looks like `tagged` (or `reg_ready`) with a `reason`.

---

## What Cadra does with your answer

Exactly INT-05's table. It is one classifier (`WorkflowRestAdapter._classify`)
for every outbound event:

| You answer | Cadra records | Retries? |
|---|---|---|
| 2xx with an identity in the body (`name`, `event_id`, `reference`, `ref`, `id`, also inside Frappe's `message`) | `acknowledged`, with your identity | no |
| 2xx without one | `sent` ("received", not acknowledged) | no |
| **409** | `acknowledged`: you already hold this `event_id`, so the event landed | no |
| 408, 425, 429, any 5xx, a timeout, a refused connection, a DNS failure | `error` | **yes**, on the ladder below |
| any other 4xx (400, **401**, 403, 404, 422 …) | **`dead`** on the first attempt | no |

**A 4xx other than 408/425/429 is final.** Use it for "this can never be
taken" (malformed, or a `grn_reference` you do not hold, as INT-05's
`TagUnmatchedError` does), never for "not ready yet". **Until Vendra's
receiver exists, Vendra answers `401 AuthenticationError`** (Frappe's
`validate_auth` refusing the bearer token for a method it does not know;
measured, report 62 §4.2), and every event is dead-lettered on its first
attempt. That is why the endpoint is set only once the receiver is deployed
(see *Deploying* below).

### The retry ladder and the dead letter

Per target, defaults **8 attempts, 60 s base, doubling, 3,600 s cap**. The
attempts land 0, 1, 3, 7, 15, 31, 63 and 123 minutes after the event. After
the eighth failure, **2 h 3 min** after the event, it is **dead**: it stops,
shows under *Workflow → Failed Deliveries*, and a note is posted on the
asset's chatter (*"Integration event not delivered … The unit's register
state in Cadra is unaffected; the downstream system has not been told it
changed."*). The policy is snapshotted on each row when it is queued, so
retuning it does not change events already in flight.

### If Vendra is down for a day (measured, report 62 §5)

Measured on the real drain and ladder with a simulated clock: 490 events
(seventy units a day × seven) raised over a working day.

- **Down 07:00 to 07:00 the next day: 490 of 490 dead-lettered, 0 late.**
  Every event is raised more than 2 h 3 min before Vendra returns.
- **Down overnight, back at 12:00:** of the 218 morning events raised while
  it was down, **107 dead** (raised before 09:57), **111 delivered late**
  (the latest 59 minutes after noon), and the 272 raised after noon on time.

The rule: **an event raised more than 2 h 3 min before Vendra comes back is
dead-lettered; one raised after that is delivered within an hour of its
return.** A longer budget is a per-tenant setting (*Max Delivery Attempts*):
at the 3,600 s cap, each extra attempt buys an hour, so 30 attempts cover a
day.

**Recovering the dead letters** is a person in Cadra's back office:
*Workflow → Failed Deliveries*, filter *Register-State Events*, select them
all, **Retry Delivery** (since handoff 62 the button
works on a selection). Each keeps its `event_id`, so anything Vendra already
holds is a 409 and counts as delivered, and Vendra's newest-`state_since` rule
makes the replay order irrelevant. The alternative is Vendra's own: 55's
refresh-on-open asks Cadra for a receipt's units whenever someone opens it.

---

## Deploying

1. Upgrade `myservice_workflow` on every tenant (the Register-State Endpoint
   column; the cluster's `upgrade-19`). Nothing is sent yet.
2. Deploy Vendra's receiver (Vendra handoff 57).
3. Then set **Register-State Endpoint** on the tenant's *Vendra (INT-05 asset
   events)* target. Events are queued from the next move. Moves made before
   this are not sent: 55's refresh-on-open covers them.

The order matters because of the 401 above: set the endpoint first and every
move in between is dead-lettered on its first attempt.
