# Handoff 62 — The state, told

**Branch:** `feat/the-state-told`
**Report:** `docs/handoffs/62-REPORT.md`
**Runs after:** 61, merged. Branch from `dev`, after pulling.

**A change of order.** `docs/AI-CAPTURE-EVALUATION.md` §4 numbers the SAP
mirror 62 and the audit-capture path 63. They become **63 and 64**. This
handoff comes first because it closes the gated receipt loop that go-live
needs, and the AI work doesn't. Edit §4's numbers at Step 0, in the same
docs commit as this file.

---

## 0 · What this is

With the gates on, Vendra knows where a unit is only when somebody opens
the receipt and Vendra asks Cadra (Vendra 55). Nobody is **told** when
Internal Audit rejects a unit, queries one, or when a receipt's last unit
reaches the register. Vendra's report 56 §4 designed the smallest message
that fixes it. It's good, and this is Cadra's half, built to that design.

## 1 · One event: `asset.register_state.changed`

- **Raised at the one point every state change passes through.** Vendra's
  report names `asset_gates._gate_move`, where the `gate_fired` row is
  written. Confirm it's the only writer. That includes:
  - query, reject, resubmit and return, which aren't gates (P1) but do move
    the state;
  - the skipped tagging gates of a `record_only` unit (`reg_ready`);
  - every unit of a batch, so a batch of 20 raises **20 events, never 1**.
- **Only for units Vendra sent:** assets that carry a `grn_reference` from
  Vendra's INT-03 (`import_source = vendra`). A unit created any other way
  raises nothing. Gates off: a unit is born `registered` and never moves,
  so nothing is raised. Prove it.
- **Payload: exactly Vendra's table, no more.**
  - every event: `event_id`, `asset_id`, `asset_code`, `grn_reference`,
    `register_state`, `waiting_on`, `state_since`;
  - `reason` on a query, reject or return (the words the actor typed);
  - `sap_asset_code` on `registered`.
  - **No person's name, email or id.** Vendra says *Internal Audit*, not who.
- **Sent down INT-05's road:** the same `workflow.config` target, bearer
  token, outbox, retry ladder and dead-letter, measured 109 of 109 on
  `test19` in report 60. One outbox row per event, written in the gate's
  own transaction, so an event is never sent for a state that rolled back.
- **Ordering.** Two events for one unit can be delivered out of order on
  retry. Vendra keeps the newest by `state_since` (its report says so).
  Cadra's part is that `state_since` is the register column 60 added, and
  is strictly increasing per unit. If two moves can land in the same
  second (60 truncated to seconds), say so, and make the later one carry a
  later value.
- **The contract**, written in `docs/integrations/INT-05b-register-state.md`
  (INT-10 is taken; this rides INT-05's road):
  - the payload;
  - when it is raised and when it isn't;
  - the retry and dead-letter behaviour;
  - one example per state.

  Add it to the endpoint reference's integrations list. CHANGELOG:
  additive.

## 2 · A walk script for test tenants

Vendra's Builder can't fire Cadra's gates. Its permission layer refused
`odoo shell` as credential exploration, and it was right to stop. So give
it one supported tool:

- **`scripts/walk_units.py --tenant <db> --asset <id> --to <state>`**, plus
  `--reject "<reason>"` and `--query "<question>"`.
- It walks a unit forward **as the demo personas, over HTTP**, one gate at
  a time, reading their passwords from the owner's local personas file. It
  prints each state and never prints a password.
- **It refuses any tenant not on the local bench:**
  - a host that isn't `localhost` or `*.localhost`;
  - a database not in an allow-list of test tenants.

  The refusal says why. It never touches the cluster.
- It uses the suites' own helper (`tests/gates.py`) if that can be imported
  outside pytest. If not, one shared module for both, so there's one answer
  to "how do you walk a unit".

## 3 · What must not change

- Every gate's behaviour, sentences and batch rules (57–61).
- INT-05's existing `asset.tag.affixed` message, byte for byte.
- Gates off: no new message is sent, ever.

## 4 · Verification

1. The full suites, gates off and gates on, on `test19`: the same test set,
   both denominators.
2. On `test19`, against the bench's Vendra:
   - one unit walked through all seven gates with the script;
   - the outbox showing **7 events** with their payloads printed (redact
     nothing; there are no names);
   - Vendra's message log receiving them.
   - Vendra 57 doesn't exist yet, so Vendra will answer with a refusal or
     a dead-letter. Print what it answers. The point here is that Cadra
     sends the right thing.
3. A batch verify of 5 units: 5 events.
4. A query, a reject and a `record_only` unit's `reg_ready`, each with its
   event.
5. Gates off: a unit received and affixed, and zero events.
6. A unit not from Vendra, walked: zero events.
7. The script refused for `staging` by name, and for a non-local host.
8. The fan-out, readiness, and the deploy steps for the owner.

And the standing sentence check.

## 5 · The question for the report

**If Vendra is down for a day, what happens to the events, and what does
Vendra see when it comes back?** Measure it against the retry ladder:

- how many are delivered late;
- how many are dead-lettered;
- what a person would have to do to recover the dead-lettered ones.

Vendra's half decides its recovery from that answer.
