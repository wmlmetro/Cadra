# Report 16 — The reports an auditor asks for

**From:** Builder · **To:** Architect · **Branch:** `feat/audit-reports`

---

## 1 · What the browser said about the Fleet Command tab

**You are right, I was wrong, and the tab mounts.**

Logged into `jaizbankplc` in a real Chromium: `myservice_dashboard.action_myservice_dashboard`
mounts through the legacy shim at **20,148 bytes** of client-action DOM with
**zero console errors**. The Fleet Command tab button is present, it clicks,
the panel becomes visible at 4,476 bytes, and its KPI strip populates from the
tenant. So the panels reports 13 and 15 fixed do reach a user in the Odoo
client. Report 15 §6.1 is withdrawn.

| tag | registered | mounted | legacy DOM | console errors |
|---|---|---|---|---|
| `myservice_dashboard` | true | true | 20,148 | 0 |
| `barcode_station` | true | true | 47,362 | 0 |
| `nrs_asset_dashboard` | true | true | 24,063 | 0 |
| `myservice_fm_dashboard` | true | true | 48,548 | 0 |
| `bus_dashboard` | true | **false** | 6,552 | 0 — Access Error dialog |
| the four retired tags | false | false | 0 | 0 |

**Three things came out of proving it, and the middle one is the important one.**

**My first probe was wrong in the same family as the bug it was checking.** It
measured `.o_action_manager` and reported all four *retired* tags as mounted,
because an unresolvable tag still renders ~9,716 bytes of Odoo's own error
surface into that element. A guard written to detect a mount that fires on a
failure is the print-hook defect again. The sound discriminator is the shim's
own root class, `.o_nrs_legacy_action`, which exists only when a legacy client
action really mounted.

**`data._warnings.unavailable` still had no reader — but not for the reason
either of us thought.** The tab loads fine; `dashboard.js` simply never read
the key. So a panel the server dropped and honestly announced rendered as *"No
approved vendors yet"* — the precise lie the warning exists to replace, one
layer above where handoff 13 fixed it. I added the reader, and proved it both
ways: with `unavailable` forced non-empty the banner renders (*"Some panels
could not be loaded: Approved vendors, Compliance alerts"*), with it empty the
banner is absent, zero console errors in both.

**Report 11 measured this correctly and never committed the probe**, which is
why report 15 had to reason from a source tree and got it wrong. The probe is
committed now at `e2e/probes/odoo-client-actions.mjs`; `node
e2e/probes/odoo-client-actions.mjs` reproduces the table above. The shim is in
`ENVIRONMENT-FACTS.md` under its own heading, with the measurement trap, which
is the more useful half.

**One thing I did not chase:** `bus_dashboard` registers and then answers an
Access Error on the admin account. Report 11 saw the same flakiness and
re-probed it green in isolation. It is not this handoff's work and I have not
called it a regression.

## 2 · Which fields the snapshot cannot roll back

**28 fields roll back. 44 do not, and the response says so on its face.**

The declaration is at `data.fidelity`, and the rows sit *inside* it at
`data.assets` — so `data` is an object on this one route. That was the shape
decision: an array has nowhere honest to carry the boundary, and the envelope's
`_warnings` is the one part of the body a client reading `body["data"]` never
sees. **A boundary a consumer can miss by reading the obvious key is not a
boundary.**

**Published at today's value and labelled (21)** — omitted columns would send
an auditor to a second query that answers as-of-today without saying so:

> `serial_number`, `legacy_asset_code`, `make`, `model_name`, `manufacturer`,
> `department`, `floor_room`, `parent_id`, `grn_reference`,
> `purchase_order_reference`, `purchase_vendor`, `import_source`,
> `import_date`, `import_ref`, `acquisition_date`, `acquisition_cost`,
> `purchase_date`, `purchase_value`, `sap_asset_number`, `sap_posting_state`,
> `sap_reconciliation_state`

**Named and deliberately not published at all (23)** — a today's figure under a
heading an auditor reads as historical is the specific harm:

> `deleted_assets`, `change_source`, `current_value`, `replacement_cost`,
> `accumulated_depreciation`, `current_book_value`, `is_verified`,
> `last_verified_by`, `verification_notes`, `assignment_date`,
> `retrieval_reason`, `retrieval_date`, `maintenance_vendor_id`, `notes`, and
> the eight `sap_*` figure and provenance fields

**Read as one list, that is the answer to what NRS can and cannot ask.** Every
financial figure, every SAP field including `sap_asset_number`, the whole
acquisition provenance trail, the serial number, the department, and the asset
hierarchy. §2.4's observation, made concrete: **the identity and location of an
asset are historical; its money is not.** An external audit that opens with
*"reconcile the register at 31 March to the ledger"* cannot be answered from
this report, and it now says so rather than producing a number that looks like
it can.

Three things beyond the field lists:

- **`deleted_assets` is in `not_recoverable`, so the snapshot is a lower
  bound** on the register's size. An auditor reconciling a count has to know
  that, and it is on the face of every response.
- **The cutoff is published.** `data.cutoff` is the exact instant, naive UTC,
  and `fidelity.notes.cutoff` names the day boundary taken: end of day
  Africa/Lagos, 23:00 UTC. WAT is a fixed +01:00 and Nigeria has never observed
  DST, so this is exact arithmetic rather than a guess. A change at 23:30 UTC
  on 31 March is 00:30 on 1 April locally and is not in the 31 March snapshot.
- **`data.filters` is the half neither of us named.** Filters match *current*
  values, so `?as_of=2026-03-31&state=active` means "assets active **today**,
  reported as they stood on 31 March" — a different population from "active on
  31 March". The response says so instead of implying otherwise.

**Verified empirically, not by reading.** An asset created 5 January, changed
today from `good`/`active` to `poor`/`in_repair`: the snapshot at 30 June
returns `good`/`active` with `_changed_since: [condition, state]`; at today
returns `poor`/`in_repair`; at 1 January returns nothing at all. The Selection
values come back as **technical keys** although the tracking table stores the
translated labels *"Good"* and *"Under Repair"* — that mapping is the failure
mode that would have looked exactly like success.

**A field count you should carry into INT-10: there are 20 tracked fields on
`nrs.asset`, not 18.** `tag_label_state` and `active_tag_number` are
`related=` fields that declare no `tracking=` of their own and **inherit it
from their target**, so a grep cannot see them. INT-10 has been contradicting
itself on this — its measured table has been showing `tag_label_state` as the
largest tracked field on `nrs.asset` while the prose above it denied the field
was tracked. Both are corrected. A consequence worth having: **"was this asset
tagged on 31 March?" is answerable after all**, because `is_tagged` is computed
from `tag_label_state` rather than stored.

## 3 · Disposals with no authorising reference

**There are no disposals. Not one, on any tenant, ever.**

| | |
|---|---|
| assets estate-wide | 17,795 |
| `state = 'disposed'` | **0** |
| `state = 'missing'` | 0 |
| `state` tracking rows, all eight tenants | **0** |
| `condition = 'decommissioned'` | 0 |

You expected an uncomfortable number and it is uncomfortable in a way neither
of us predicted. No asset has ever changed state in Cadra on any tenant, so
the migration found nothing to recover on all eight. The 8 disposals now on
`jaizbankplc` are pytest fixtures, named `pytest-*`; my own two probe rows are
deleted.

**That absence is what makes it safe to have built this now.** It is R29's
reasoning a fourth time: being true on zero rows is precisely what makes a
published field safe to correct before anybody relies on the old behaviour.

Both halves are built. `disposal_method`, `disposal_reference`,
`disposal_approved_by`, `disposal_approved_date` and `disposal_proceeds` now
exist and are tracked, and so are `disposal_date` and `disposal_reason`, which
were not. `GET /api/v1/reports/disposals?from=&to=` reports the period, and a
disposal missing any of it appears **carrying the finding** — never filtered
out. Exercised against the fixtures: 9 rows, `no_authorising_reference` on 6,
`no_approver` on 9, nothing dropped.

**One number that will fire on essentially every future row:
`no_sap_asset_number`.** 2 of 11,942 assets on `nrs19` carry a SAP number and
none does elsewhere, so INT-09 has never sent a disposal instruction to the
financial system. It is true and it is a real finding, and the summary counts
findings separately so it does not dilute the others — but it is also a finding
that says the same thing about every row, and that is the shape of a control
readers learn to ignore. **Yours to rule on**; one line removes it.

## 4 · Non-`/api/v1` external surfaces

**27**, in 9 controller files across 7 modules. Derived independently — 36 real
route decorators in first-party code, minus the 9 raw pre-envelope `/api/v1`
routes, which confirms that backlog item's count too. Inventoried in
`docs/api/EXTERNAL-SURFACES.md`; the changelog's scope now names them.

| who calls it | routes |
|---|---|
| an external organisation | 4 |
| an anonymous browser | 5 |
| our own Odoo web client, and nothing else | 8 |
| **nothing at all** | **10** |

**Published shape: 0 of 27.** Every `docs/` hit for one of these paths turns
out to be its `/api/v1` mirror.

Three findings a reader should not have to derive, and the first is the one
that matters:

1. **`/myservice/workflow/callback` is `auth='public'`, `csrf=False`, mutates
   `request.request` state, and its token guard is optional** — the code reads
   `if config.callback_token:`, so a tenant with no token configured has **no
   authentication at all** on the endpoint that approves and rejects requests.
   It also accepts the token in the query string.
2. **The documented callback is not the one WorkSpace calls.**
   `/api/v1/integrations/workflow/callback` and `/myservice/workflow/callback`
   are two separate handlers, and Cadra publishes the *legacy* one's URL to
   WorkSpace itself. So the documentation describes a route the integration
   does not use.
3. **`/api/myservice/assets/export/csv` dumps the whole asset register
   authenticated by a `?api_key=` query parameter** — into nginx access logs,
   proxy logs and browser history — and both Redhubs routes fall back to a
   hardcoded key literal in source when the config parameter is unset. SAP's
   webhook has the same fallback.

## 5 · Wall-clock, and the machine

**About eight hours end to end**, of which a large part was a session rate
limit pause; active working time was roughly three. The five parallel builders
account for most of the rest — two ran over sixteen minutes each.

**The machine behaved unusually well.** Eight sequential module upgrades across
every tenant, four modules each, **zero Postgres crash-restarts** — against
handoff 14's eight. Serialising every `--stop-after-init` run in the main
session is what did it, and it is worth keeping.

Everything green, with denominators:

| suite | result |
|---|---|
| `myservice_asset_register` | 0 failed, 0 errors **of 123 tests** |
| `myservice_api` | 0 failed **of 52** |
| `myservice_workflow` | 0 failed **of 56** (52 before the verification pass added four) |
| `myservice_nrs_base` · `myservice_fm_dashboard` · `myservice_fleet_maintenance` | 0 failed of 2 · 8 · 11 |
| `tests/` (pytest, `jaizbankplc`) | **338 passed, 27 skipped** |
| `tests/test_source_guards.py` | **68 passed of 68** |

---

## What the acceptance criteria asked, and how each was proved

**Neither report writes anything.** Fingerprinted `nrs_asset`,
`nrs_asset_custody`, `nrs_asset_tag_label`, `mail_tracking_value`,
`mail_message` and `nrs_asset_transfer` — row count, newest `write_date`, and
an md5 over each table's whole ordered content — before and after six calls
across both reports. **Byte-identical.** The harness is committed at
`scripts/audit_report_fingerprint.sh` so the next report can prove the same
thing. `write_date` is in there deliberately: a recompute that writes an
unchanged value still bumps it, which is exactly the silent defect handoff 09
found in the daily sweeps.

**The cap really applies to the snapshot.** This was the one that could have
gone badly. The snapshot takes the same filters as `GET /api/v1/assets`, so
exempting it would not have loosened a cap on an audit report — it would have
**deleted the record cap API-wide**, because any capped credential could route
round its own limit by asking here. Asking for `limit=1000` returns 100 rows,
`total_estimate: 2457`, and the truncation warning. The remedy for a real audit
credential is `total_record_cap = -1` on its client row, which already exists.

**The approval fields cannot be asserted over the API.** PATCHing
`disposal_approved_by`, `disposal_approved_date` and
`disposal_date_reconstructed` returns them in
`data._warnings.rejected_fields` and changes nothing, while
`disposal_reference` in the same request goes through. `no_approver` is one of
the report's own findings; a client able to PATCH the approver could create a
disposal and name any user as its authority in the same request, turning that
finding into a clean row with nobody having authorised anything.

**Guards proven to fail before they pass.** The catch-all guard now walks
`scripts/` and the repo-root loaders and was demonstrated red three ways —
one marker removed, the collector silently narrowed back, and the historical
shape replayed — then green at 68 of 68. 38 handlers were brought into scope:
**4 deleted** as dead code rather than marked (a `try` around a dict item
assignment, which cannot raise), 28 classified `reported`, 6 `optional`, none
`unknown`. `seeds/` stays out on your reasoning, and the SCOPE comment carries
a freshly measured **12** still outside the boundary, so nobody reads a green
run as "there are none".

---

## Deviations, and why

1. **I added the `_warnings.unavailable` reader to `dashboard.js`.** §A only
   asked me to report what the browser said. But the handoff's reasoning was
   *"if it mounts, `data._warnings.unavailable` has a reader after all"*, and
   that turned out to be false for a different reason. Ten lines make the
   sentence true; leaving it would have left a server announcement with nothing
   listening, which is rule 3.

2. **A sixth disposal field, `disposal_date_reconstructed`.** The brief had the
   migration write a recovered date into `disposal_date`. A reconstructed value
   in the same column as a recorded one is indistinguishable from it — which is
   exactly what `custody.source = 'tracking_backfill'` exists to prevent. The
   flag is published and is a finding. Without it the migration would quietly
   convert *"we do not know when this was disposed of"* into a date that looks
   recorded.

3. **The eight disposal fields moved into the rolled-back set, and a contract
   test is why.** They started in `as_of_today`, correctly — when that module
   was written they carried no tracking. The disposal work then added tracking
   to all eight in the same change, and
   `test_every_tracked_field_is_rolled_back` failed, saying these fields now
   have a history the snapshot is silently not using. **That is the guard doing
   the whole job it exists for**, catching two modules built in parallel
   disagreeing. It also means the two reports now reconcile against each other
   for the same date instead of quietly disagreeing.

4. **The browser probe is committed.** Report 11 measured this and did not,
   which cost report 15 a wrong conclusion and this handoff its §A.

5. **`action_condemn` now stamps `disposal_date`.** It never did; the
   depreciation module patched it, so a tenant without that module silently
   produced undated disposals.

## What the verification pass found

One real finding, and it was mine: **I expanded the outbound `asset.disposed`
SAP payload and shipped it untested.** Six keys changed or were added,
including `disposal_type`, whose value genuinely changes behaviour — a
scrapping now sends `retirement` where every prior event sent `disposal`. The
mapping table had an exhaustive test; the payload builder that reads it had
none, and *"a table proven correct in isolation says nothing about whether the
builder reads it"* is exactly right. Straight rule 6.

Fixed rather than argued: four tests added at that call site, covering the
retirement mapping, the unset-method default that keeps it non-breaking, the
authorisation and proceeds keys, and that an undocumented disposal sends
**nulls rather than omitting the keys**. `myservice_workflow` now runs **0
failed of 56 tests**, up from 52. The retirement test was proved to gate:
reverting `disposal_type` to the old literal fails it with `'disposal' !=
'retirement'`, and restoring it returns 56 of 56. The payload change is now
documented in `INT-06-07-09-sap-requirements.md` §4.2 with the mapping table,
and in the API changelog under the widened scope this handoff created — which
is the first use of that scope for a non-`/api/v1` surface, and the reason §D
was worth doing.

Everything else the pass attacked came back clean: no write path in either
report, the rollback decode, tracked-versus-untracked, period placement,
`summary`/`pagination` agreement, the cap, module layering, the writable-field
gate, both source guards, comment accuracy and no AI references.

## Open, and yours to rule on

1. **`no_sap_asset_number` fires on ~100% of rows.** §3 above. True, and
   possibly noise.
2. **There is no API route that records a disposal approval.**
   `action_approve_disposal` is Odoo-form only, because the approver is
   deliberately not writable. That is a gap rather than a control, and closing
   it needs a scope decision — probably `approvals:write`, which exists in the
   scope table and gates nothing asset-related today.
3. **`data.unplaceable`** — disposals with no date and no recoverable
   transition, returned in full and uncapped in every report, never mixed into
   period totals. Dropping them makes them invisible in every report; putting
   them in one double-counts them in the next. Empty today.
4. **The two workflow callbacks are separate handlers** and the documented one
   is not the one WorkSpace calls. §4 finding 2. Resolving that is real work,
   not a doc fix.
5. **The two geocoders write plausible coordinates on a network outage.** Found
   while classifying catch-alls, not fixed. A swallowed `urlopen` failure is
   indistinguishable from *"Nominatim has no such place"*, and both scripts
   respond by writing a jittered state-capital coordinate into
   `generic.location.latitude/longitude` and committing it. A total outage or a
   403 rate-limit produces coordinates for the entire estate, reported as
   `fallback` rather than as network errors. The markers now say so; the
   behaviour is unchanged.
6. **`load_offices_v3.py:65` has a latent `AttributeError`** that prints as
   *"Type X skipped"* for every type in turn, where the truth is "there is no
   location-type model on this tenant". Named in its marker, not fixed.

## An environment fact that cost two tests

**A `TransactionCase` that writes a tracked field finds no tracking row.**
Odoo 19 defers tracking to `cr.precommit`, and a `TransactionCase` never
commits. Worse, `mail_thread.create` registers `_track_discard`, so **a write
issued after a create and before that point records nothing at all** — which is
the natural way to write the test and silently tests nothing. One test failed
on the run meant to prove it and would otherwise have shipped green. It is in
`ENVIRONMENT-FACTS.md` beside the frozen-`create_date` and pending-compute
lessons, which are the same shape: the test is green and has tested nothing.
