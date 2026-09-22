# Report 35 — Nobody moves an asset alone

**Builder:** Claude Code (IDE) · **Branch:** `feat/approvals` · **Base:** `dev`
**Date:** 2026-09-22

---

## In plain words, first

NRS asked, at the demonstration, whether moving an asset should need a second
person. It now does. Somebody presses **Move** or **Transfer custody**, picks
who they are asking, and the asset **does not move**. A request appears in
that person's queue with the reference `CR/2026/NNNN`; when they approve it,
the asset moves and the record says who asked, who agreed, when, and what the
asset was before. The requester cannot approve their own request, and that is
refused in the model rather than by hiding a button — it holds from the Odoo
screen, from the API, from an administrator's shell session and under
`sudo()`.

It is **on by default on every tenant**, including one nobody has configured,
and turning it off is a deliberate act an administrator performs against the
database. It is deliberately **not** switchable over the API, because the
people the rule constrains are exactly the people who hold `settings:write`.

Three things are worth the owner's attention before the detail:

1. **It applies to far more than the two buttons.** The enumeration §A asked
   for found **twelve** production writers of `location_id` and **thirteen**
   of `custodian_id`. The rule is enforced in `nrs.asset.write`, underneath
   all of them, and not in the two routes the app happens to call — because
   one of the writers nobody would have listed is an editable field on the
   Odoo asset form, and two more are the database quietly emptying the column
   when a location or an employee is deleted.
2. **The old approval machinery was never used, and is now the receipt.**
   `nrs.asset.transfer` has had `draft → approved → done → rejected` from the
   beginning. Measured on 2026-09-22: every transfer row on every local
   tenant is in `done` — `test19` 161, `jaizbankplc` 103, `nrs19` 1,
   `cadra19` 0 — and `approved_by` is set on exactly **1 of those 265**, the
   single `nrs19` row somebody once drove through the Odoo screen by hand. It
   was not reused as the request (four measured reasons, §B); it is now
   created *by* an approval, carrying the real approver, so those columns
   stop being always-empty and the INT-09 payload SAP receives starts
   carrying a true one.
3. **This is a breaking change to the API**, announced. `POST /move` and
   `POST /transfer-custody` have returned "the asset moved" for the life of
   this API and now return "a request was raised, and the asset has not
   moved".

---

## §A · Every writer, and whether it is subject to approval

**This is the specification, and it was produced before the code.** The
handoff asked for it in those terms, and it was right to: *"I have been wrong
about this exact list before."* So has this repository — handoff 14 asserted
the transfer route was the only writer of `custodian_id` and an exhaustive
search found six. Two exhaustive sweeps were run for this handoff, one per
field, against every module, every script, every view, every migration and
the FK definitions.

**The ruling applied**, from the handoff: *approval is about a person
deciding to move something. A registration is not a move. An integration
delivering an asset is not a move. A bulk import is not a move.*

**Where the rule is enforced:** `nrs.asset._assert_change_is_approved`,
called from `_write_recorded` immediately after the disposal guard — the one
place every ORM writer passes. Not in the routes. A route-level gate would
have covered rows 1 and 2 of each table below and left the other nineteen
writers untouched — including the Odoo form, which can reassign custody by
typing a name.

### Writers of `nrs.asset.location_id`

| # | Writer | Kind | Subject? | Why |
|---|---|---|---|---|
| 1 | `POST /assets/<id>/move` | REST route | **YES** | The designed door. A person, today, choosing where a thing goes. Now raises a request. |
| 2 | `PATCH /assets/<id>` (`location_id` in `_WRITABLE_FIELDS`) | REST route | **YES, when the value changes** | The Cadra app's edit form. Report 28 found it moves an asset with no reason and no transfer document — it is a person deciding. Refused 400 pointing at `/move`. **Only when the value actually changes**: the edit form re-sends every field on every save, and refusing the mere presence of the key would make saving a note impossible. |
| 3 | `POST /assets` (create) | REST route | **No** | Registration. This is the INT-03 door Vendra delivers through; there is no previous state for a second person to protect, and gating it would dead-letter every receipt. `create` is not overridden for this at all. |
| 4 | `nrs.asset.transfer.action_complete` | Python, Odoo Transfers UI | **No** | It is the completion of a document that has its own approve step. Declares `source='transfer'`. |
| 5 | `@api.onchange` on `building_id`/`floor_id`/`room_id` → `location_id` | Odoo form | **YES** | A human picking a room on the Odoo form. Reaches `write` as `direct` and is refused there. |
| 6 | The Odoo asset form (`asset_views.xml:97`, `readonly force_save`) | View | **YES** | Same write as #5. The field is readonly but `force_save`, so the form does persist it — that was handoff 28's fix. |
| 7 | `nrs.asset.import` — create branch | Bulk import | **No** | A file load. |
| 8 | `nrs.asset.import` — update branch | Bulk import | **No** | Same. Declares `cadra_approval_exempt='import'`. Approving eleven thousand rows one at a time is not a control; it is a denial of service against the people operating the register. |
| 9 | `generic.location.unlink` → `ON DELETE SET NULL`, cascading through `parent_id ON DELETE CASCADE` | **Database** | **No — and CANNOT be** | No ORM write runs, so no Python gate can stand in front of it. It takes location away rather than granting it, it already refuses outright when a disposed asset is in the subtree, and it already appends a `location_deleted` movement for every other asset (handoff 28). **This is the writer no search of the Python could have found**, and it is named here so the next reader knows the gate does not cover it. |
| 10–14 | `scripts/nrs_hq_seed.py`, `seeds/nrs_asset_seed.py`, `scripts/{gtb,jaiz,lasg}_data_seed.py` | Seed scripts | **No** | Demonstration data dealt out with `random.choice` from a fixed seed. The three `*_data_seed.py` declare `cadra_approval_exempt='seed'` on their one write helper; the other two write only at `create`, which is not gated. |
| — | `scripts/nrs_hq_seed_v4.py` | — | n/a | **Looks like a writer and is not.** It writes `building_id/floor_id/room_id` derived *from* `location_id` and never `location_id` itself (onchanges do not run for ORM writes). Listed so nobody re-derives it. |

### Writers of `nrs.asset.custodian_id`

| # | Writer | Kind | Subject? | Why |
|---|---|---|---|---|
| 1 | `POST /assets/<id>/transfer-custody` | REST route | **YES** | The designed door. Now raises a request. |
| 2 | `PATCH /assets/<id>` | REST route | **YES, when the value changes** | As location #2. |
| 3 | `POST /assets` (create) | REST route | **No** | Registration. |
| 4 | `nrs.asset.transfer.action_complete` | Python | **No** | As location #4. |
| 5 | `myservice_identity.action_mark_retrieved` | Python, Odoo button | **No** | The departure clearance. It clears `custodian_id` — it takes an asset BACK from somebody who has left and hands it to nobody. There is no second person to ask about an asset returning to the store, and requiring one would leave a leaver's assets assigned to them while a queue drained. Declares `cadra_approval_exempt='clearance'`. |
| 6 | The Odoo asset form (`asset_views.xml:107`) | View | **YES** | **A freely editable field** — no `readonly`, no `groups`. `location_id` two lines above got the `readonly force_save` treatment in handoff 28 and `custodian_id` never did. A storekeeper with form access could reassign custody by typing a name and pressing save. Now refused by the model with a message naming the remedy. |
| 7 | `default_custodian_id` from the employee record's *View Assets* action | Odoo context → create | **No** | Registration with a holder. |
| 8 | `hr.employee.unlink` → `ON DELETE SET NULL` | **Database** | **No — and CANNOT be** | As location #9. Already refuses when a disposed asset is involved and already appends a custody link for every other (`asset_custody.HrEmployee.unlink`). |
| 9–11 | `scripts/{gtb,jaiz,lasg}_data_seed.py` | Seed scripts | **No** | Declared `seed`. Unlike the location seeds these write on EXISTING assets, so they genuinely needed the declaration. |
| 12 | Odoo **Duplicate** on `nrs.asset` (no `copy=False`) | ORM create | **No** | A create. |
| 13 | XML-RPC / `call_kw` / `odoo shell` | ORM write | **YES** | Lands on `direct` and is refused. Fail-closed on purpose: an unknown writer gets the safe answer. |

### The exemption mechanism

`cadra_approval_exempt=<reason>` in the context, where the reason must be one
of `import`, `seed`, `clearance`, `migration`, `test`. **An unrecognised value
is treated as no exemption at all** — a typo must not open a door that a blank
cannot, which is `approval_policy`'s own rule applied to the other end. Proved:
`cadra_approval_exempt='yes-please'` is refused.

It is a reason string and never `True`, so the declaration reads as a sentence
at the call site and a grep for the constant finds every one of them. There
are **five** call sites, and each is a row above.

### What the gate cannot see, said plainly

**The guarantee is Python.** A writer that goes round the ORM — raw SQL,
`_write()`, a DBA's query, a restore — is not gated, exactly as the three
append-only recorders are not. `tests/test_recorder_bypass_guard.py` watches
for the first two in first-party code. The two FK cascades above are inside
this category and are the reason it is stated rather than implied.

---

## §B · One queue — the case both ways, and what I chose

**Chosen: a single new model, `nrs.asset.change.request`, covering both
kinds of change. `nrs.asset.transfer` is left exactly as it is and becomes
the RESULT of an approved location change.**

### The case FOR keeping `nrs.asset.transfer` as the location request

It is real and it is why I read both models before writing either line. The
machinery already exists — four states, an Approve button restricted to
`group_asset_manager` that stamps `approved_by`/`approved_date` from the
acting user, a Complete step that performs the move, a form, a list, a menu,
a sequence and ACL rows. Building a second model to do a job a model already
does is how a codebase grows two answers to one question, which is the thing
handoff 30 spent a whole section refusing to do for custody and movement. If
it had fitted, reuse would have been right.

### The four measured reasons it does not fit

1. **It cannot express half the moves this register makes.**
   `from_location_id` and `to_location_id` are both `required=True`, and
   `_check_locations` forbids them being equal. An asset that is NOWHERE
   cannot be the subject of a transfer at all. That is not an edge case:
   **1,920 of `jaizbankplc`'s 4,164 assets (46%)** and **358 of `nrs19`'s**
   had no location when handoff 28 measured them, and `/move` already had to
   stop creating a transfer for them after the owner reported the Move button
   failing outright with *"Required field missing: from_location_id"*. A
   request model that cannot carry the most common move on the register is
   disqualified by that alone.
2. **It cannot express a custody change at all** — same two required
   columns, same constraint. `POST /assets/<id>/transfer-custody` already
   says so in its own docstring: *"a pure custody change cannot be recorded
   in it at all."* Making it fit means making both location columns optional
   and dropping the constraint, which is not reuse — it is a different model
   wearing the old one's name and the old one's 265 rows.
3. **An asset manager can delete one.** `ir.model.access.csv` grants
   `group_asset_manager` `1,1,1,1`, and `asset_id` is `ondelete='cascade'`,
   so a transfer dies with its asset. That is exactly why
   `nrs.asset.movement.transfer_id` is `ondelete='set null'` with a Char
   reference beside it. Report 27 §13.2 ruled the prerequisite for this
   handoff in one sentence: *an approval recorded on a row an asset manager
   can delete is not an approval record.*
4. **Its `approved_by` is already published, meaning something else.**
   `myservice_workflow/models/sap_asset_events.py` puts `approved_by` and
   `approved_at` into the INT-09 payload SAP receives on transfer
   completion. Redefining those columns is an integration-visible change to
   a live interface, made as a side effect of a UI feature.

### What happens to the 161, the 103 and the 1

**Nothing, and that settles it.** Under the alternative those 265 `done`
rows become "requests" retroactively: 265 rows with no requester, no
approver and no premise, sitting in the model an auditor is told to read for
who authorised what. Leaving the model untouched keeps them meaning exactly
what they have always meant — a completed move, mostly created by `/move` at
`state='done'` as paperwork.

**And nothing is stranded**, which is the other half of the question: not one
row anywhere is in `draft` or `approved`. There is no in-flight work in the
old machinery to migrate, because nothing has ever used it.

### What the new model costs, honestly

A table, a sequence, three views, three ACL rows and a fixture label. It does
NOT adopt `nrs.asset.append.only.mixin` — deliberately: that mixin refuses
every write unconditionally, which is right for a completed fact and wrong
for a record that legitimately moves from `pending` to one of three terminal
states. What it takes from the mixin is the SHAPE of the enforcement: the
transition methods set a context flag on themselves and `write` refuses
without it, so the state machine is enforced by the model rather than by who
holds which group. `unlink` is refused outright, always. A decided request is
frozen to everything, including `sudo()`.

`test_append_only_mixin.test_nothing_but_these_three_adopts_the_guard` still
asserts exactly three adopters, and still passes, which is the right answer:
this is not a fourth append-only record.

### The three non-negotiables, and where each one lives

| Non-negotiable | Where it is enforced | Proved by |
|---|---|---|
| Append-only rows written **on approval, never on request** | The request writes nothing to the asset. Rows appear when `action_approve` writes the asset and the recorders in `nrs.asset.write` see the change — the same recorders, under the same ORM, as every other writer. | Model probe and HTTP: asset field and movement count identical before and after raising. |
| **Who is asked** and **who clicked** are two fields | `approver_id` (nomination, from the body) and `approved_by_id` (from `env.uid`, never from any payload). A body naming the decider is refused 400. | HTTP: `requested_by` = the API client's user, `approver` = Administrator, `decided_by` = Administrator, all three distinct keys on one record. |
| **Self-approval refused in the model** | `_assert_may_decide`, called by `action_approve`. No path to the state change goes round it. | Probe: refused for the requester under `.with_user()`, under `sudo()`, and as SUPERUSER. HTTP: 403 with `details.is_own_request`. |

**A nomination confers nothing.** `approver_id` decides whose queue a request
lands in and who is notified. Any eligible person may decide it, and the
requester may not, whoever was named. That split is what makes it safe to let
the requester choose the approver at all.

---

## §C · The switch, and what it does when its value is absent

`cadra.approval.required`, a system parameter, values `on` / `off`.
`myservice_asset_register/approval_policy.py`.

**Read with raw SQL, never `get_param`** — the handoff said to read it the way
`database_class` is read, and that is the substance of it, not the style.
`get_param` is `@ormcache`d per worker; under the committed `workers = 2` the
cache is per process and invalidation does not reliably reach a worker between
requests. Handoff 25 did not deduce that, it watched it: one worker reported
`database_class = "client"` for a database whose row had been DELETED while
another answered `"test"` for the same instant, and twenty-four writing tests
ran to a green pass. The failure here is the same shape and worse in kind — a
worker serving `off` from a cache for a tenant whose row says `on` is a control
that has stopped applying, with no symptom at all.

### Proved by making it absent

`test19` has **never** had the parameter set. Live, on that tenant:

```
GET /api/v1/settings/approvals
{"required": true, "setting": null, "configured": false,
 "default_when_unset": true, "parameter": "cadra.approval.required"}
```

and a direct ORM write on that tenant raises:

```
UserError: Moving probe35-asset to <location> needs somebody else to approve it.
```

`setting: null` with `configured: false` beside `required: true` is the point:
*nobody has ever set this and it is getting the default* and *somebody
deliberately turned it on* are the same behaviour and very different facts, and
a settings screen that cannot tell them apart cannot tell an administrator
whether anyone has ever thought about it.

**Absent, blank, misspelt and unrecognised all resolve to ON.** A typo must not
open a door that a blank cannot. There is no bypass flag and no override
environment variable, for the reason `database_class.py` gives at length.

### It is deliberately NOT settable over the API

`GET /api/v1/settings/approvals` is read-only and has no PATCH twin, which
makes it the only settings block on that controller without one. The reason is
the point of the control: `assets:write`, `approvals:write` and
`settings:write` are **all granted by the single group
`group_asset_manager`**. A PATCH would let exactly the people the rule
constrains switch it off, move the asset and switch it back on. That is not a
control; it is a speed bump with an audit trail nobody reads.

An administrator sets it in the database. The command is printed **inside the
refusal** a gated write raises, so nobody has to go looking for it —
`database_class.mark_command`'s argument: an error naming a remedy the reader
then has to look up is worse than one naming none.

---

## §D · What happens while a request is waiting

The handoff declined to rule these from outside because they interact. Here is
what I chose and why.

### 1 · Two requests for the same asset — refused

**At most one PENDING request per asset**, enforced by a PostgreSQL partial
unique index (`nrs_asset_change_request_one_pending_per_asset`, created in
`init()`). Partial, because the constraint is only on `pending`: an asset
accumulates any number of approved, rejected and withdrawn requests over its
life and that is its history.

The reason is not tidiness. Each request records the world it was raised in
(§D2). If two are pending and the first is approved, the second's premise is
broken **by definition**, so the second could only ever be refused. Allowing it
to be raised is an interface inviting somebody to queue work that cannot
happen.

`models.Constraint` cannot express this — Odoo 19's replacement for
`_sql_constraints` builds TABLE constraints and a partial unique index is not
one. **And the index alone is not enough**: the probe showed it raises a raw
`psycopg2.UniqueViolation` that aborts the whole transaction. So the route
checks first and answers **409** naming the blocking request, its reference,
who asked and who was asked. The index remains the authority; the check exists
so a person who pressed Move gets a reference number instead of a 500.

### 2 · The asset changes underneath — refused, saying what changed

Each request stores **the premise**: `from_location_id`, `from_custodian_id`,
`from_state`, plus Char copies of every name. Read from the asset at creation,
never accepted from the caller — a premise the requester can write is a premise
the requester can choose, and catching the case where what they believed is no
longer true is the entire use of these columns.

`premise_holds` is **computed on every read and never stored**. A stored value
would be a snapshot of the last time something recomputed it, and the thing
that breaks a premise — somebody else moving the asset — touches no field on
this record. An approver reading a stale `true` is precisely the silent failure
the handoff forbade.

One method, `_premise_check`, answers `(holds, what_changed)` and is called
both by the compute (for display) and by `action_approve` (before it writes),
so a queue that shows a request as applicable and an approve that refuses it
can never disagree. It refuses when: the asset is gone; the asset has been
**disposed** (terminal, handoff 30 — and refusing here says what changed,
where letting the write raise would give the model's words about a write the
approver did not know they were making); the status has changed; the asset is
no longer where/with whom it was; the destination has been deleted; or the
asset is already at the destination.

A pending request whose premise has broken is **not auto-cancelled**. It stays
pending, shows its reason, offers no Approve button, and 409s if approved
anyway. Auto-cancelling would need a cron and would delete information — the
requester should see that their request was overtaken, not find it silently
gone.

### 3 · Withdrawal — the requester's, and only theirs

`POST /approvals/<id>/withdraw`, state `withdrawn`, terminal. Reason optional.

It is deliberately not the same act as a rejection and does not borrow its
meaning: a requester withdrawing their own request owes nobody an explanation;
an approver refusing somebody else's does. It needs `assets:write`, not
`approvals:write` — requiring the latter would mean a requester who cannot
approve could not cancel their own request either, leaving a dead row in an
approver's queue for ever.

### 4 · Rejection — with a reason, and the requester finds out

Reason **required**, in the model and at the route. A rejection without one
leaves the requester with a dead request and nothing to act on, and they will
simply raise it again — that is the shape of control that produces noise and no
information. `/condemn`, `/mark-missing` and `/mark-found` all require a reason
on the same argument.

**How each side finds out** (§E's notification question, answered once for
both):

- **The approver** gets an Odoo **`mail.activity`** — the *somebody needs to do
  something* mechanism the handoff asked for by name, scheduled on the request
  with `activity_schedule`. `mail.activity.mixin` was already on seven
  first-party models and on `nrs.asset`'s own form, and **nothing in this
  repository had ever scheduled one**; this is the first. It gives the bell
  counter, the Activities menu and the inbox for free.
- **The requester** gets a `message_post` addressed to their partner, which
  lands in their Odoo Inbox. Not an activity: an activity means *you must do
  something*, and a decided request asks nothing of them.
- **Neither is the record.** `asset_custody.py` says why in its own docstring —
  the chain used to live in `mail.thread` and a user with the right groups can
  delete a message. Everything that matters is in the columns; deleting every
  activity in the database loses a notification and no evidence. Both calls are
  wrapped and **logged** rather than swallowed (handoff 15 classified 50 bare
  handlers; this is not a 51st), so a notification failing cannot roll back the
  request it is announcing.

### 5 · One more, not asked but forced by the answers

**A decision is taken once.** The three terminal states have no route back and
there is no reversal route, deliberately — handoff 30 refused to build one for
disposal on the same reasoning, and the measurement there was that the only
asset which ever left `disposed` was handoff 29's own probe. Somebody who
changes their mind raises a new request, which leaves both records standing.

---

## §E · The app

**The switch is asked of the server and the front end fails CLOSED on it.**
`useApprovalRequirement()` treats loading, an error and a 403 as *required* —
the same direction as `REQUIRED_WHEN_UNSET` — and the submit button is
disabled while the answer is in flight rather than showing one wording and
flipping under the user's hand. When it cannot read the setting at all it
says so on the dialog instead of guessing quietly.

**One scope change came out of building the screen.** `GET
/settings/approvals` was written with `settings:read`, which
`group_asset_manager` and `group_auditor` hold and `group_asset_user` does
not. Since the front end fails closed, that would have shown a correct-looking
"who are you asking?" dialog to a user on a tenant that does not want one. It
now takes `assets:read` — the value is not sensitive, it says whether this
register asks for a second person, and anyone who can see an asset may as well
know. Found by wiring the screen, not by reading the route.

**The dialogs.** Move and Transfer custody gain an approver picker, shown only
when approval is required. The title becomes *Request a move* / *Request a
placement* / *Request a custody transfer*, the button becomes *Request
approval to move*, and the description's FIRST clause is that the asset does
not move. **On a tenant with approval off, the title, description and button
label are byte-identical to today** — which is also what keeps the existing
e2e specs meaningful on such a tenant.

**On success the dialog does not close.** It is replaced by a panel naming the
reference, who was asked, where it would go, and *"until then this asset is
still at its current location, and that is what the register says"*. That is
the handoff's sentence about the storekeeper, implemented: closing the dialog
the way a completed move closes it is precisely how somebody comes away
believing they moved something.

**A 400 for want of an approver reveals the picker** with the server's own
candidate list, so a wrong setting still ends in a name being chosen rather
than an error about a field. A 409 gets its own panel naming the blocking
reference with a link to the queue.

**The queue** (`/approvals`): four tabs — *Waiting on me* (the default), *All
pending*, *Raised by me*, *Decided*. Each row shows the reference, the state,
the asset, `from → to`, who asked and when, who is waiting, the reason, and
the decision. Approve/Reject/Withdraw are gated on `can_decide` /
`can_withdraw` **and** on the caller's scopes. Reject will not submit without
a reason. **`premise_holds: false` removes Approve** and shows
`premise_broken_reason` in its place — Reject stays, because the row still has
to be closed.

**The asset page** carries a banner naming the reference, who asked, who was
asked and what for, with Move and Transfer disabled while it is pending — the
unique index is per ASSET, not per change type, so a pending custody request
would 409 a move too and a live Move button would be a lie. On a failed read
it renders nothing and leaves the buttons live: the server is the authority
and the dialog prints the 409.

**Sidebar**: *Approvals* with a live count badge that draws nothing on null or
zero, so a 403 never reads as *your queue is empty*.

### Three things the front end found in the contract

1. **`GET /approvals` takes one `state`.** The *Decided* tab wants three, so
   with "Any outcome" it fetches every state and filters in the browser — and
   names its own denominator (*"N decided, out of M loaded of T in every
   state"*) rather than printing `total_estimate` as if it counted decided
   requests. A count without its denominator is the rule this programme has
   broken three times.
2. **`premise_holds` is `true` on every DECIDED row**, because
   `_compute_premise` short-circuits rather than re-judging closed history —
   deliberate, and documented in the compute, but a naive read would paint an
   old rejection as still applicable. Every read of it in the UI is guarded on
   `state === "pending"`.
3. **`from_*_name` means "when asked", not "now".** It is shown as *now* only
   when the row is pending AND the premise holds — which is exactly what
   `_premise_check` asserts — and labelled *as at the request* otherwise.

---

## Judgement calls, stated so they can be overturned

1. **200, not 202, when a route raises a request.** The body carries
   `pending_approval: true`, the `request`, and the asset UNCHANGED, with
   `movement_id`/`transfer`/`custody_change` explicitly null. 202 is the
   better-looking answer; this API takes its success status from the
   `cadra_route` decorator, and a per-call override would have to be carried
   through the idempotency cache too or a replay would answer 202 once and 200
   afterwards. A byte-exact replay is what handoff 18 built and handoff 31
   protected. **Cheap to overturn** — one field in the cache.
2. **PATCH refuses rather than raising a request.** A PATCH carries a whole
   object; turning part of it into a request while writing the rest leaves the
   caller with a half-applied save and no way to tell which half.
3. **The Odoo form's `custodian_id` was left editable.** The model refuses the
   change with a message naming the remedy, which is honest. Making the field
   readonly would be a second statement of the same rule that goes wrong the
   day a tenant turns approval off.
4. **`nrs.asset.transfer` was left completely alone** — no new fields, no
   changed meanings, no migration. It gains rows created BY approvals.
5. **The `test` exemption exists but nothing first-party uses it in
   production code.** It is for an in-registry test declaring, per call, that
   it is writing a fixture. Per call and never globally, for the reason
   `database_class.py` gives about bypass flags.

---

## Open, and for the Architect

- **`POST /move` and `POST /transfer-custody` still do not refuse unknown body
  keys.** They were not among handoff 31's eleven, so a stray `approver_id`
  sent to a tenant with approval OFF is dropped with a 200. Benign today — a
  misspelt `approver_id` on an approval tenant gets the *"approver_id is
  required"* 400, which is the right answer — but it is the thirteenth and
  fourteenth door, and handoff 33 is the one that widens these guards. Named,
  not fixed, per the instruction to register new routes in the guards as they
  stand.
- **Who may approve is one method** (`_eligible_approver_domain`) plus
  `_may_decide`, both meant to be replaced when NRS give us their structure.
  Nothing about the RECORD changes when they are.
- **The switch has to be set per tenant by hand.** No tenant on this machine
  has it, so every one of them now requires approval. If any demonstration
  tenant should not, that is one command per tenant and it belongs to the
  owner.
