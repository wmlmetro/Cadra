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

## 2026-10-28 — handoff 69: where the captures went · `myservice_api` 19.0.3.39.0, `myservice_asset_register` 19.0.1.37.0

Additive throughout; the one behaviour change below alters no answer.

- **New query parameter (additive):** `GET /api/v1/audit/captures?q=<text>` (`audit:read`, unchanged) — *find a capture*. Matches a capture whose `capture_id` equals `q` read as a UUID (case-insensitive, braces accepted), whose `code` equals `q` trimmed and case-insensitively, exactly, or whose confirmed old FIRS tag (`fields.legacy_asset_code`) equals `q` under the SAP matcher's normalisation (upper case, `\` → `/`, whitespace removed). Never a partial match. ANDed with every other filter; paged and ordered as before (id ascending). Empty `q` ignored; over 200 characters `400 invalid_request`. Endpoint reference §19.6.
- **New keys (additive) on every capture row:** `campaign.state` (`open` | `closed`) and `campaign.reviewers` (`[{id, name}]`, the campaign's active reviewers) beside `campaign.id` and `campaign.name`.
- **New key (additive) on `GET /api/v1/audit/campaigns` and `GET /api/v1/audit/campaigns/<id>`:** `reviewers_active` — the count of active users named as reviewers. `progress.waiting_for_review > 0` with `reviewers_active: 0` is a campaign whose captures nobody can review. §19.4.
- **New route:** `GET /api/v1/audit/refusals` (`audit:manage`) — every `POST /api/v1/audit/captures` answered 4xx/5xx after the token was accepted, newest first, cursor-paged; filters `device_id`, `user_id`, `since` (a Lagos day or an ISO date-time), `capture_id`. A row: `id`, `refused_at`, `capture_id`, `user`, `device_code`, `device`, `campaign`, `location`, `outcome`, `code` (the identifying values as sent), `http_status`, `error_code`, `reason`, `message` (the sentence sent back), `request_id`. **Not recorded:** a `401` and a scope `403`. Never the body's photos, fields or GPS. Kept 90 days. §19.10.
- **BEHAVIOUR CHANGE (no change to any answer):** a refused `POST /api/v1/audit/captures` still saves no capture and answers exactly as before, but now leaves one `nrs.audit.capture.refusal` row, written on its own cursor so the refusal's rollback does not remove it. A replay refused again is a second row.

## 2026-10-20 — handoff 68: a second provider · no module version changed

- **New enum value (additive):** `provider` = `openai` on `GET`/`PATCH /api/v1/settings/ai-identify`, on every `POST /api/v1/ai/identify` answer and on `GET /api/v1/settings` → `ai_identify.provider`. OpenAI's Responses API, the same prompt (67.1) and the same schema; `provider_label` "OpenAI (GPT)". A client that branches on `provider` should expect three values: `anthropic`, `openai`, `fake`.
- **New (additive) on `GET`/`PATCH /settings/ai-identify`:** `keys` — per provider that needs one, `{placed, variable, command}` (`CADRA_AI_API_KEY` for Anthropic, `CADRA_OPENAI_API_KEY` for OpenAI; never the key); `provider_options` — each choosable provider with its label, the model it is asked with on this tenant, its `default_model`, `needs_key` and `key_placed`; `default_model` — the configured provider's default (OpenAI's: `gpt-6.1-sol`).
- **BEHAVIOUR CHANGE — the model is per provider.** `model` is now the CONFIGURED provider's: Anthropic's stays `cadra.ai.model`, OpenAI's is `cadra.ai.model.openai`, the stand-in's `cadra.ai.model.fake` (default `cadra-fake-1`, where it read Anthropic's before). A `PATCH` with `model` writes the model of the provider the same body switches to, else of the configured one; switching provider never changes another provider's model. `key_placed`, `key_variable` and `key_command` describe the configured provider's key (`scripts/set_ai_key.sh openai` for OpenAI); on the stand-in they describe Anthropic's, as before.
- **BEHAVIOUR CHANGE — `providers` lists what this tenant may choose:** the stand-in only on a database marked `test` (or when already set to it). The `PATCH` refused it elsewhere already.
- BEHAVIOUR CHANGE — switching ON, or switching provider while on, is refused (`400 validation_failed`, `provider_not_ready`) when the server lacks the key of the provider being switched TO, naming its variable.
- **New (additive) on `GET /settings/ai-identify/acceptance`:** `by_provider`, and `provider` on each `by_model` row.

## 2026-10-19 — handoff 66: the audit in the room · `myservice_asset_register` 19.0.1.34.0, `myservice_api` 19.0.3.37.0

- **New:** the audit capture — 28 routes under `/api/v1/audit/*` plus `GET /api/v1/ai/config`. Endpoint reference §19.
  - devices (R4: a device is not a credential): `GET /audit/devices` (`audit:read`, `?mine=`), `POST /audit/devices`, `POST /audit/devices/<id>/bind`, `POST /audit/devices/<id>/deactivate`, `GET /audit/people` (`audit:manage`);
  - code blocks and the ledger (R2, R2a): `POST /audit/blocks` (1–500 codes to a device and its bound person), `POST /audit/blocks/<id>/return` (unused codes VOIDED, never reissued) (`audit:manage`); `GET /audit/blocks`, `GET /audit/blocks/<id>`, `GET /audit/codes` (`audit:read`);
  - campaigns: `POST /audit/campaigns`, `PATCH /audit/campaigns/<id>`, `POST /audit/campaigns/<id>/close` (`audit:manage`; closing refused `409` while a capture waits, `details.waiting_for_review`); `GET /audit/campaigns`, `GET /audit/campaigns/<id>`, `GET /audit/campaigns/<id>/lists`, `GET /audit/campaigns/<id>/lists.csv?list=` (a file, not the envelope), `GET /audit/campaigns/<id>/slice?location_id=&kind=assets|sap_records` (`audit:read`);
  - capture: `POST /audit/photos` (`audit:capture`, multipart `file` + `source`; the same bytes from the same person answer the photo kept, `already_synced: true`), `GET /audit/photos/<id>` (`audit:read`, the bytes); **`POST /audit/captures`** (`audit:capture` and the **`X-Cadra-Device`** header, checked against the device's binding) — **idempotent on the body's `capture_id`, a UUID stored unique, not on the 24-hour `X-Idempotency-Key` cache**: a second sync answers the stored capture with `replayed: true`; `GET /audit/captures` (`?campaign_id=`, `?location_id=`, `?state=`, `?outcome=`, `?exception_state=`, `?duplicates=`, `?mine=`), `GET /audit/captures/<capture_id>` (`audit:read`);
  - review: `POST /audit/captures/<capture_id>/accept`, `…/return` (a `reason`), `POST /audit/captures/accept` (a batch — `capture_ids` or a room — N single acts, `dry_run`) (`audit:review`). The capturer is refused their own: `409 conflict`, `details.reason = "segregation_of_duties"`;
  - exceptions: `POST /audit/captures/<capture_id>/register-new` (to the Register Maker at `register_state = tagged`) and `…/void` (a `reason`; the code is voided) (`audit:manage`);
  - `GET /ai/config` (`audit:capture` or `assets:write`): the AI switch, model and calls left today, the label layout as data, the capture limits.
- **Three outcomes, each accepted by a second person:** `on_register` — a verification in place (room, condition, photos; a missing label reprinted under the same code); `in_sap` — a new asset ON the register from SAP's record, with the phone's code, **no asset master queued**; `in_neither` — a found-not-in-SAP exception. A second capture of the same Cadra asset, SAP record or old tag in a campaign is **held** (`duplicate_of`, `duplicate_basis`), not refused. `captured_at` up to five working days back, never in the future.
- **New scopes (additive):** `audit:read`, `audit:capture`, `audit:review`, `audit:manage` — 32 scopes in all.
- **New roles (additive):** `audit_capturer` (`audit:read`, `audit:capture`, `sap_mirror:read`) and `audit_reviewer` (`audit:read`, `audit:review`, `sap_mirror:read`), both implying Asset User, both grantable on `POST /users/<id>/roles`, and **not grantable to one person together** (a new row in `GET /settings/role-exclusions`). The Asset Controller gains `audit:read` and `audit:manage`; the Auditor `audit:read`. The `role` / `role_direct` filters and `roles` bodies on `/users` accept the two new keys.
- **New enum value (additive):** `sap.code_source` = `audit_from_sap_mirror`, written only by the acceptance of an `in_sap` capture; a hand write of it is refused.
- **New history type (additive enum value):** `audit_capture` on `GET /api/v1/assets/<id>/history` and in its `fidelity.events`; **new event source** `api_audit`.
- **New approval exemption:** `audit` — an outcome-a acceptance moves an asset found in another room without a move request; the capturer and the reviewer are the two people. Its movement row says `approval`.
- **The asset-code ledger:** every existing asset's code is recorded `active` by the 19.0.1.34.0 migration, which prints the count per tenant; every new asset's code writes a ledger row. Nothing changes in any asset payload.
- **BEHAVIOUR CHANGE — `POST /ai/identify`:** opened to `audit:capture` as well as `assets:write`. The route now declares no scope and checks in its body: a caller with neither is `403 forbidden` with `details.required_scopes_any` (it was the scope gate's `details.required_scopes` / `granted_scopes`).
- BEHAVIOUR CHANGE — `POST /sap-links/approve`: a serial-basis proposal is now refused `409`, `details.contested: true`, when another Cadra asset has come to carry the same serial since it was proposed.
- **PERFORMANCE — every asset list:** `sap.duplicate_flag` is read once per page, not once per asset. The payload is unchanged.

## 2026-10-19 — handoff 65: the link · `myservice_asset_register` 19.0.1.33.0, `myservice_api` 19.0.3.36.0

- **New:** the link — a register asset given its SAP asset number from the SAP mirror by two people. `GET /api/v1/sap-links/candidates` (`sap_mirror:read`), `POST /api/v1/sap-links/propose` (`register:make`, a batch with `dry_run`), `GET /api/v1/sap-links` (`sap_mirror:read`), `POST /api/v1/sap-links/approve` and `/return` (`register:check`), `POST /api/v1/assets/<id>/sap-link/undo` (`register:make`). One person may not propose and decide one asset's link: `409 conflict`, `details.reason = "segregation_of_duties"`. An approval writes `sap.asset_number`, `asset_subnumber`, `company_code` and **nothing is sent to SAP**. A link is refused while the asset has an asset-master posting in flight (`sap.posting_state` `queued`/`posted`).
- **New:** the contested list — `GET /api/v1/sap-links/contested`, `POST /api/v1/sap-links/contested/<sap_id>/propose` and `/flag` (`register:make`). A flag is a record for NRS; nothing is merged, retired or deleted.
- **New enum value (additive):** `sap.code_source` = `linked_from_sap_mirror`, written only by a link's approval; a hand write of it is refused.
- **New key (additive):** `sap.duplicate_flag` on every asset — `{sap_asset_number, note, flagged_by: {id, name}, flagged_at}` or null.
- **New history types (additive enum values):** `sap_link` (proposed, approved, returned, and the same for an undo — *"Linked to SAP asset N (old tag, unique), proposed by A, approved by B."*) and `sap_duplicate_flagged`, in the history and its `fidelity.events`.
- **BEHAVIOUR CHANGE — `POST /api/v1/sap-assets/imports`:** a run against a mirror that already holds records first counts what it would mark "not in the latest export", writing nothing; over 5% it stops as the new run state **`held`** (additive enum value) with `message` and `absent_guard`. A second text part `mark_absent=true` ("Yes, mark them absent") skips the count and is recorded on the run (`absent_guard.confirmed`, `confirmed_by`). A guarded re-import reads the file twice.
- **New key (additive):** `absent_guard` on every import run. `duration_seconds` is now given for a `held` run too.
- **New key (additive):** `class_evidence` on `GET /api/v1/reports/sap-coverage` — per Cadra category, the SAP classes its linked assets carry, with a definition. Nothing writes a category's SAP class from it.
- **BEHAVIOUR CHANGE — `GET /api/v1/reports/access-changes`:** a day in the period is a LAGOS day (`lagos_days_in_utc`, the configuration report's helper since 63b). A caller naming UTC dates sees its window move one hour earlier; the payload is unchanged.
- **BEHAVIOUR CHANGE — *Identify from photo*:** the key is read from the server's environment (`CADRA_AI_API_KEY`), not a tenant parameter; the upgrade deletes `myservice_api.ai_api_key` on every tenant. Until the variable is set, `POST /ai/identify` answers `503 server_misconfigured` and `GET /settings/ai-identify` says `key_placed: false`. `key_command` is `scripts/set_ai_key.sh` (no database); **new (additive)** `key_variable`.
- **BEHAVIOUR CHANGE — `ai_suggestion` outcomes:** a proposed field neither sent nor named in `ignored` that the asset already holds is `accepted` with `already_held: true` (it was `ignored`). **Additive:** the `already_held` key.
- **Docs:** the endpoint reference's error codes match `utils.py` — `unprocessable` (422, never defined) removed; `validation_failed`, `not_implemented`, `idempotency_mismatch` listed. `legacy_asset_code` is documented as the old FIRS tag every SAP reconciliation reads.

## 2026-10-19 — handoff 64 (Identify from photo, R11)

- **New:** `POST /api/v1/ai/identify` (`assets:write`, multipart: `photo_id`, or `file` + `source`), behind the tenant switch `cadra.ai.identify`, **off on every tenant**. Returns a suggestion — class with confidence and up to two alternatives, attributes, condition, text read, SAP candidates (records only with `sap_mirror:read`, else the count), `suggestion_id`. Writes nothing on any asset. Refusals: `403 forbidden` `switched_off`, `429 rate_limited` `daily_cap`, `503 server_misconfigured` `provider_not_ready`, `503`/`502 internal_error` (`provider_timeout`, `provider_error`, `provider_declined`, `answer_discarded`). Endpoint reference §17.
- **New:** `GET` / `PATCH /api/v1/settings/ai-identify` (`settings:read` / `settings:write`): switch, provider, model, timeout, daily cap, effort, today's count, `key_placed`. The key is never returned or accepted.
- **New (additive):** `GET /api/v1/settings` carries `ai_identify` (`enabled`, `provider`, `provider_label`, `notice`).
- **New (additive):** `POST /api/v1/assets` and `PATCH /api/v1/assets/<id>` accept `ai_suggestion: {"id", "ignored": [...]}`, and answer `data.ai_suggestion` (`id`, `event_id`, `counts`, `fields`) when sent. Not an asset field; it is not in `details.writable`. Refused before anything is written: malformed `400`, unknown id `404`, `not_identified` / `other_asset` `400`, `already_applied` / `photo_expired` / `photo_limit` `409`.
- **New history type (additive enum value):** `details_suggested` on `GET /api/v1/assets/<id>/history`, and in its `fidelity.events`.

## 2026-10-19 — handoff 63b: the faster loop · no module version change (Python only; a tag sequence is created per prefix on first use)

**ADDITIVE — a new error code, `409 tag_number_taken`, and the one 409 to
retry.** A location-prefix tag number (`NRS-FURN-018`) was the highest
number under its prefix plus one, read through each request's snapshot, so
two receipts of one class in flight at once drew the SAME number — Vendra
report 58's two chairs, 100 ms apart. Where report 63's unique index stands
the second was refused `409 conflict` and Vendra dead-lettered the unit;
where it does not, both were minted. **Numbers now come from a Postgres
sequence per prefix**: concurrent receipts draw different numbers (20 at
once, 20 numbers, `tests/test_tag_number_race.py`; on the old code 2 and 7
of 20 were refused). The one collision left — with a number issued around
the sequence, by an import, between a request's read and its write —
answers `409 tag_number_taken` with `details.retryable: true`; nothing is
written and the same request sent again draws a new number. Every other
unique violation still answers `409 conflict`. Numbers are not reused and
not renumbered; a prefix's sequence starts at its highest number the first
time it is used.

**PERFORMANCE — `PATCH /api/v1/asset-categories/<id>` with a policy field**
restates the class once, not twice, and each asset's schedule once, not
twice: `test19`'s class of 19,042 from 13.2 s / 20.6 s to 9.7 s / 9.7 s.
`assets_recomputed` and every figure are unchanged.

**BEHAVIOUR CHANGE — `GET /api/v1/reports/configuration-changes`: a day in
the period is a LAGOS day.** `from` and `to` were bounded as UTC days, so
from 00:00 to 01:00 Lagos a parameter written a minute ago fell on the
previous UTC date and was missing from "today's" report — on a register
whose every other published date (the snapshot's `as_of`, a disposal's
date, the warranty's `status_as_of`) is a Lagos day. The period is now
Lagos midnight of `from` to the last microsecond of `to` in Lagos, both
inclusive (`audit_configuration.lagos_days_in_utc`). A caller that already
named Lagos dates gets the day it asked for; one that named UTC dates sees
its window move one hour earlier. Nothing else in the payload changed —
`period.date_from`/`date_to` echo the dates sent, as before.
`GET /api/v1/reports/access-changes` still bounds UTC days; it is named in
report 63b for the Architect, not changed here.

---

## 2026-10-18 — handoff 63: what SAP holds, in Cadra · `myservice_api` 19.0.3.34.0, `myservice_asset_register` 19.0.1.31.0, `myservice_workflow` 19.0.3.4.0

**Additive**, plus two behaviour changes a consumer can observe (marked).
Nothing about an asset's payload, list, count, report or export changed:
the SAP mirror is not the register (measured, report 63 §5.6).

- **New scope `sap_mirror:read`** — SAP's asset master as Cadra holds it.
  Held by the Asset Controller, the Register Maker and Checker and the
  Auditor (and `admin`). NOT by Asset Users, the Store Officer or Vendra's
  credential. A credential granted it is put in the Auditor group
  (`SCOPE_GROUPS`, the `evidence:read` shape).
- **New routes** (reference §16):
  - `POST /api/v1/sap-assets/imports` — multipart `file`, SAP's .XLSX.
    `settings:write` held by a System Administrator (the token must also
    carry `admin`). `202` and the run; read in the background. A missing
    column is a `400 validation_failed` naming it, and nothing is stored;
    a second upload while one runs is a `409`; over 150 MB a `413` in
    words (over 200 MB the proxy refuses it first, with its own HTML 413);
    a zip that is not SAP's workbook a `400` in words.
  - `GET /api/v1/sap-assets/imports`, `GET /api/v1/sap-assets/imports/<id>`
    — the runs and their counts.
  - `GET /api/v1/sap-assets` — the slice, by `office` (or `none`), `class`,
    `updated_since`, `active`, `in_latest_export`; paged.
  - `GET /api/v1/sap-assets/match` — up to five active, unlinked records,
    each with `reason_code` and `reason`.
  - `GET /api/v1/sap-assets/<id>` and `GET /api/v1/assets/<id>/sap-record`
    — one record and its linked asset, both ways.
  - `GET /api/v1/reports/sap-coverage` — how much of SAP's register Cadra
    holds, by class and by office, every count defined.
- **BEHAVIOUR CHANGE — outbound retry budget (INT-05, INT-05b).** A new
  delivery target's default is 32 attempts (60 s doubling to a 3,600 s
  cap: 26 h 3 min of trying), was 8 (2 h 3 min). The 19.0.3.4.0 migration
  moved every target still on the old default and left customised ones
  alone. A receiver down for a working day now receives that day's
  `asset.tag.affixed` and `asset.register_state.changed` events when it
  returns, late, instead of none of them; it never received them twice
  (each keeps its `event_id`). Events already queued keep the budget they
  were queued with.
- **BEHAVIOUR CHANGE — a depreciation recompute moves `updated_at` only
  for assets whose figures changed.** Saving a category's policy, switching
  the depreciation mode and the monthly recompute used to rewrite every
  asset they touched, so `GET /assets?updated_since=` (handoff 61 §6)
  handed a sync every asset of the class as changed. Now an asset whose
  accumulated depreciation, book value, depreciation state and end date are
  unchanged keeps its `updated_at`. The figures are the same figures.
- **A tag number active on two labels is refused by the database** on every
  tenant where none is today (5 of 8 local tenants): the unique index
  `nrs_asset_tag_label_active_name_uniq`. The ORM already refused it in
  words; the index catches a writer that goes round the ORM. A tenant with
  such numbers (`test19` 68, `jaizbankplc` 15, `nrs19` 1) gets the index
  on the first upgrade after they are resolved.

## 2026-10-15 — handoff 62: the state, told · `myservice_workflow` 19.0.3.3.0

**Additive.** Nothing a consumer already receives changed: `asset.tag.affixed`
is the same body, headers and endpoint, byte for byte, and every `/api/v1`
route answers as before. With the gates off no unit is a candidate, so
nothing new is sent (a candidate still in flight when a tenant switches the
gates off still moves, and its moves are sent).

- **New outbound event: `asset.register_state.changed`** (INT-05b, contract
  `docs/integrations/INT-05b-register-state.md`). Cadra POSTs it to Vendra
  each time a receipt unit Vendra sent (`import_source = vendra` with a
  `grn_reference`) moves through the receipt gates: one event per act, the
  state the act left the unit in — seven for a labelled unit, five for a
  `record_only` one; N for a batch of N. Body: `event_id`, `asset_id`,
  `asset_code`, `grn_reference`, `register_state`, `waiting_on`,
  `state_since`; `reason` on a query, a rejection and a return;
  `sap_asset_code` at `registered`. No person. INT-05's road: the same
  target, credential, outbox, retry ladder and dead letter.
- **New config field on the INT-05 target: *Register-State Endpoint***
  (`workflow.config.rest_endpoint_register_state`). Blank (every tenant
  today): nothing is queued for the event.
- **`state_since` (`gates.state_since` on `GET /assets/<id>`, and the
  Candidates list's order) now strictly increases per unit.** Two moves of a
  unit in the same second used to carry the same value; the later now
  carries one second more. A value can run a second or two ahead of the
  clock.

## 2026-10-15 — handoff 61: the same code, and the photo · `myservice_api` 19.0.3.33.0, `myservice_asset_register` 19.0.1.30.0

With the receipt switch off, a tenant sees the additive routes and keys
below and three changes of behaviour: a tag replacement keeps its number,
the default `tag_id` schema, and IAD's evidence behind its own scope. A
room-code string at the scan box now answers instead of 404.

- **BEHAVIOUR CHANGE — a replacement keeps its number.**
  `POST /api/v1/tags/<id>/approve-replacement` voids the print and reprints
  the label under the SAME number: `new_tag.tag_number` equals
  `tag.tag_number`, with `reprint_count` one higher and a new `id`. Until
  61 it minted a new number — and on a gated unit a location-prefix one
  instead of the asset code (the defect ruling 4.3 forbids). A consumer
  keyed on the tag number sees the same number on a new label id. One row
  is still one physical print; the voided one is `state: scrapped`.
- **BEHAVIOUR CHANGE — `POST /api/v1/assets/<id>/tag-affixed` on a reprint
  that has not been printed** is refused `400 validation_failed`: *"Tag X is
  reprint 1 and has not been printed yet, so the label being scanned can
  only be the original print, voided on <date> (<reason>). Print reprint 1,
  then confirm it."* — and recorded as `affix_refused`, reason
  `voided_print`. The two prints encode the same value, so time is the only
  thing the server can tell them apart by.
- **New: `POST /api/v1/tags/printed`** (`tagging:write`), `{"tag_ids":
  [...]}` (≤ 500): records that the app printed these labels, through the
  print funnel's own rule (only the label in service; an affixed label is
  not walked back). The app draws labels in the browser and had never
  recorded a print (1 of 3,069 affixed labels had one). A label printed at
  the station now reads `label_state: printed` before it is affixed.
- **BEHAVIOUR CHANGE — `GET /api/v1/barcode/kpis` `untagged` and
  `GET /barcode/untagged`** no longer count or list an asset whose label is
  pending replacement (it still carries its label, and its replacement
  reprints under the same number); `POST /barcode/generate` skips one with
  `reason: replacement_pending` instead of minting it a second label.
- **INT-05 (to Vendra):** a reprint's affix sends `asset.tag.affixed` with
  the SAME `tag.number` and a new `label_id`; before 61 a replacement's
  affix carried a different number. **Vendra:** key a label on `label_id`,
  not on the number.
- **Added on every tag payload:** `reprint_count`, `voided_at`,
  `void_reason`; `reprint_count` on `replaces`/`replaced_by`, and on the
  asset's `tagging` block.
- **BEHAVIOUR CHANGE — IAD's evidence needs `evidence:read`** (new scope:
  IAD officer and approver, Register Maker and Checker, Auditor). `GET
  /api/v1/assets/<id>/evidence` answers a caller without it with `readable:
  false`, `count`, `summary` (*"IAD evidence: N items"*) and no
  verifications; with it, `readable: true` and `count` beside the list
  (additive). The file route `GET /assets/<id>/evidence/<attachment_id>` is
  `403` without it. **Vendra's credential does not hold it** and is told the
  count. The asset history's `gate_fired` verify event carries
  `evidence.attachments` (the count) in place of `attachment_ids` for such
  a caller.
- **New: `POST /api/v1/candidates/gates/submit`** (`assets:write`) and
  **`/request-tagging`** (`tagging:request`) — the same N-single-fires
  batches as handoff 60's, `dry_run` included; a selection may mix
  receipts.
- **BEHAVIOUR CHANGE — a candidate is refused** `POST /assets/<id>/verify`,
  `/mark-missing`, `/mark-found` and `/condemn` with `409 conflict`,
  `details.reason = "not_on_the_register"`, asked before the route's own
  state checks; and `PATCH` cannot change a candidate's `state` or
  `last_verified_date` (same 409), nor can a gated receipt (`POST /assets`,
  INT-03 included) arrive with a `state` other than `active` or with a
  `last_verified_date`. Nothing is written.
- **BEHAVIOUR CHANGE — the default `tag_id` schema** is now `{"mandatory":
  ["name", "colour", "material", "dimensions"]}`: make and model are no
  longer mandatory by default (published on `GET /asset-categories`).
  Classes whose schema was set keep it — 0 of 13 `tag_id` classes on the 8
  local tenants had one. **Vendra:** your own receipt still asks make and
  model on its own account; that is Vendra's rule and is unaffected.
- **New: photos.** `POST /api/v1/assets/<id>/photos` (`assets:write`) — the
  first `multipart/form-data` route inside the envelope: parts `file`
  (required), `source` (required, `web` | `mobile`), `caption`; JPEG or PNG
  judged by the bytes (`415` otherwise, whatever the name), at most 300 KB
  (AI-NFR-07; `413`), at most 12 standing photos per asset (`409`); a
  candidate may get one. `GET /api/v1/assets/<id>/photos` (`assets:read`) —
  photos and IAD's evidence in one list, each item `kind: photo |
  iad_evidence`, evidence items only with `evidence:read` (otherwise
  `iad_evidence` is the count). `GET /api/v1/assets/<id>/photos/<photo_id>`
  — the bytes. `POST /api/v1/assets/<id>/photos/<photo_id>/supersede`
  (`assets:write`, `reason` required) — a photo is never deleted or
  replaced; a second supersede is `409`. New history kinds `photo_added`
  and `photo_superseded`.
- **`GET /api/v1/reports/register-snapshot`** refuses `updated_since`
  (400): it is a filter on the live register, not on a snapshot.
- **New: `?updated_since=<ISO-8601>` on `GET /api/v1/assets`** — assets
  whose own record changed at or after the instant (`updated_at`), no zone
  meaning UTC; composes with every filter, `location_id` and
  `register_state=any` included; order and paging unchanged; unparseable
  is a 400. How to page a sync without missing a row:
  `docs/integrations/mobile-ai-capture-endpoints.md`.
- **New: `location_code` on every location** (`GET /locations` and every
  location answer; writable on `POST`/`PATCH /locations` with
  `locations:write` — `409` when taken or when it reads as a tag number or
  asset code, `400` on the wrong shape; empty means generate). Format
  `LOC-` + the hierarchy's zone codes, or the id. `?q=` searches it.
  Filled on every location on every tenant by the 19.0.1.30.0 migration.
- **New: `GET /api/v1/locations/<id>/label?size=medium|large`**
  (`locations:read`) — the room label PDF, QR and Code 128 carrying the
  code verbatim; `small` is refused (the small Code 128 does not read).
- **BEHAVIOUR CHANGE — `GET /api/v1/barcode/lookup`** resolves a room code
  as its last step: `matched_by: "location"`, `matched_location`, and no
  asset keys. A string that used to 404 now answers 200 when it is a room
  code; tag → asset code → serial resolve exactly as before.
  `/tags/lookup` is unchanged.
- **OpenAPI:** a request body that is not JSON is published under its own
  media type; `413` and `415` are described.

## 2026-10-15 — handoff 60: seventy a day · `myservice_api` 19.0.3.32.0, `myservice_asset_register` 19.0.1.29.0

With the receipt switch off, a tenant sees the additive routes and keys
below, the renamed key, and one change of behaviour (a new asset carries
its class's identification mode). Everything else is for the gates.

- **BREAKING (rename): `reference` → `record_reference`** on `POST` /
  `PATCH /api/v1/assets`, on every asset, and as a capturable name in a
  class's `class_attributes_schema` (the `record_only` default is now
  `{"mandatory": ["name", "record_reference"]}`). Handoff 59 published the
  asset's top-level `reference` beside two other `reference` keys with other
  meanings (a move's transfer, a disposal's); handoff 37's one-name rule
  renames it before anything outside Cadra reads it. Additive since 59 only
  (three days); **no client reads or sends it yet — Vendra's `record_only`
  follow-up (its handoff 56) is told the new name.** `reference` is now
  refused on `POST`/`PATCH /assets` like any unknown key (`400
  invalid_request`, `details.rejected_fields`). Each tenant's stored values
  and class schemas are carried over by the 19.0.1.29.0 migration.
- **New: `POST /api/v1/candidates/gates/verify`** (`vfm:verify`),
  **`/approve`** (`vfm:approve`), **`/register`** (`register:make`) and
  **`/approve-registration`** (`register:check`) — a gate fired on many units
  at once, as N single-unit fires, each checked by every rule and recorded
  on its own; one refused unit rolls back nothing else. Always `200` with a
  per-unit `results` list carrying the status, code and sentence each unit
  would have had alone; `dry_run: true` previews and writes nothing. `verify`
  takes one checklist and one evidence set for the units of ONE receipt
  (several GRNs: `400 validation_failed`, *"These units come from N
  receipts; verify one receipt at a time so the evidence matches."*), stored
  once and linked from each unit's event. `register` takes pasted lines of
  `{asset_code, sap_asset_code, cost?}`. Endpoint reference §14.12.
- **New: `GET /api/v1/assets/<id>/evidence`** (`candidates:read`) — each
  verification's checklist, notes and files; and **`GET
  /api/v1/assets/<id>/evidence/<attachment_id>`** — the file itself (not the
  envelope), `404` for any attachment that unit's verifications do not name.
- **Additive: `waiting_on_me` and `sort` on `GET /api/v1/candidates`.**
  `waiting_on_me=true` lists only what the caller may act on (their scope,
  and the no-two-gates rule not barring them); the app's sidebar badge is
  its `total_estimate`. `sort=oldest` lists the unit longest in its state
  first; `newest` (the default) is unchanged. A cursor from one `sort` is a
  `400` on the other.
- **Additive: `gates.registration`** on every asset — `null`, or the
  Register Maker's submission as entered (`sap_asset_code`, `cost`,
  `cost_centre`, `capitalisation_date`, `asset_class`). `cost_centre` and
  the maker's capitalisation date were published nowhere before.
- **BEHAVIOUR CHANGE, every tenant: a new asset carries its class's
  `identification_mode`**, gates on or off (`serial` when the class names
  none). Until now a gates-off asset published `null` (Vendra report 54
  §5.3). Stamped, not checked: nothing a gates-off receipt sends is refused
  that was not before. Two consequences, both of the mode itself: a new
  `tag_id` unit (a chair) is affixed with the attributes tick, as a gated
  one is (`attributes_confirmed: true` on `POST /assets/<id>/tag-affixed`);
  a new `record_only` unit is minted no label at creation. Records created
  before keep what they had (`null` on older gates-off rows).
- **Vendra's credential gains `candidates:read`** (the 19.0.3.32.0
  migration, every tenant; `scripts/bootstrap.py` for a new one). Read only;
  it adds no group. **Vendra must call `/auth/token` again** — a refresh
  family keeps the scopes it was issued with.

## 2026-10-12 — handoff 59: what SAP already holds · `myservice_api` 19.0.3.31.0, `myservice_asset_register` 19.0.1.28.0

With the receipt switch off, a tenant sees the additive keys and enum values
below and exactly two changes of behaviour, both listed at the end under
**every tenant**: SAP asset numbers are unique once normalised, and a
category's `sap_asset_class` must be four digits.

- **Additive enum value: `identification_mode = record_only`** on `GET
  /api/v1/asset-categories` (and accepted on `PATCH` / `POST`), labelled
  *"Identified by its SAP record — no physical label (land, buildings,
  software, works in progress)"*; default schema `{"mandatory": ["name",
  "reference"]}`. **Clients that switch on this enum: Vendra** (its receipt
  reads the mode to decide what a line must carry). Until Vendra's
  follow-up lands it treats a mode it does not recognise as `serial` and
  will demand a serial for such a line; Cadra refuses one regardless (below).
- **Additive: `reference`** on `POST` / `PATCH /api/v1/assets` and on every
  asset (null when unset) — the title or plot number, licence key or
  contract that identifies a `record_only` unit; a capturable name in
  `class_attributes_schema`.
- **Additive enum value: `register_state = reg_ready`** (*Ready for
  registration — no label*), with `gates.waiting_on = maker`. A
  `record_only` unit goes `vfm_verified → vfm_approved → reg_ready` inside
  IAD's `approve` (the two tagging gates are skipped; the history carries a
  `gate_fired` row with `detail.action = "skip-tagging"`, `detail.gate =
  null` and the reason *"no label: <class> is identified by its
  record"*), then `register` → `reg_submitted` → `approve-registration`.
  `return-registration` sends it back to `reg_ready`. `request-tagging` is
  never offered for it (409 `invalid_state` if called). The `waiting_on`
  set is unchanged.
- **Additive: `sap_asset_class` on `GET /api/v1/asset-categories`** (SAP's
  four-digit class, or null) and accepted on `PATCH` by `settings:write` or
  `settings:classes`; anything but four digits is `400 invalid_request`
  *"`sap_asset_class` must be SAP's four-digit asset class code, for example
  3000."*; null or `""` clears it.
- **New: `GET /api/v1/settings/serial-placeholders`** (`settings:read`) and
  **`PUT`** (`settings:write`, both `exact` and `patterns` required) — the
  tenant's placeholder-serial list, who changed it and when, and how many
  assets on the tenant carry a placeholder now.
- **BEHAVIOUR CHANGE, only on a tenant whose switch is on:**
  - `POST /api/v1/assets` refuses `400 validation_failed`, nothing written:
    a serial that is on the placeholder list (*"'XXXX' is a placeholder, not
    a serial number. Capture the serial printed on the item."*,
    `details.placeholder = true`) — before the uniqueness check, so a
    placeholder is never refused as a duplicate. **This includes a `tag_id`
    unit that carries a placeholder serial** (its sentence adds *"…or send
    none — <class> is identified by its tag and attributes"*): a furniture
    line typed `0` was accepted under handoff 58 and is refused now; send no
    serial instead. And a `record_only` unit carrying any `serial_number`
    (*"<class> is identified by its SAP record and carries no serial number;
    …"*).
  - `PATCH /api/v1/assets/<id>` on a unit still in the chain applies the
    same identification rules as its receipt: no serial on a `record_only`
    unit, no placeholder serial, and a class's mandatory attribute (its
    `reference`, a `serial`-mode unit's serial) cannot be cleared — `400
    validation_failed`, the same sentences.
  - `POST …/gates/register` and `…/gates/approve-registration` refuse `400
    validation_failed`, `details.field = sap_asset_class`, when the
    (confirmed) class has no SAP asset class: *"<Category> has no SAP asset
    class, so SAP would reject this asset. An Asset Controller sets it under
    Settings → Asset Categories."*
  - `register` stores `sap_asset_code` stripped and **upper-cased**, and its
    duplicate check compares in that form (the refusal now names the asset
    holding the code). Both of SAP's shapes are accepted — 11 digits, and
    the legacy alphanumeric codes (which may contain `/`, `&`, `\`, spaces).
    An 11-digit number whose first digit is not the class's answers 200 with
    `data._warnings.sap_asset_number`, e.g. *"2xxxxxxxxxx looks like a class
    2000 number; this category maps to 3000."* (class 3500's numbers start
    `5`, as in SAP).
- **Additive: `skipped[].reason = "record_only"`** on `POST
  /api/v1/barcode/generate` — a unit identified by its SAP record is skipped,
  not minted (and not refused, so the rest of the batch is), and it is no
  longer listed by `GET /api/v1/barcode/untagged` or counted as untagged.
- **BEHAVIOUR CHANGE, every tenant:** two assets whose SAP asset numbers
  differ only in case or surrounding spaces (same company code and
  sub-number) are now refused as one SAP asset by the model's uniqueness
  rule, whoever writes them (INT-07, an import, a PATCH). 0 such pairs on any
  local tenant before the change.
- **BEHAVIOUR CHANGE, every tenant:** a category's `sap_asset_class` is
  refused unless it is four digits (or empty), from every writer — the API,
  the back-office form, a script. A value already stored in another shape is
  kept and stays readable until somebody edits it. 0 categories on 10
  tenants carry a value of another shape (`nrs19`'s one value, `3100`, is
  four digits).

## 2026-10-12 — handoff 58: the gates, kept · `myservice_api` 19.0.3.30.0, `myservice_asset_register` 19.0.1.27.0

**The receipt gates of 2026-10-07 are the product, not a stand-in** — the
routes, scopes and keys below stand and may be integrated against
(`docs/ADDENDUM-A-EVALUATION.md` §8). Vendra keeps calling `POST
/api/v1/assets` for INT-03; there is no `/candidates/ingest`.

- **Additive: `identification_mode` and `class_attributes_schema` on `GET
  /api/v1/asset-categories`** — `serial` | `tag_id` | `pool` (default
  `serial`), and `{"mandatory": [field, ...]}` over the `POST /assets`
  names `name`, `make`, `model_name`, `manufacturer`, `colour`, `material`,
  `dimensions` (always the effective schema; what is read can be PATCHed
  back). Both accepted on `PATCH` / `POST /asset-categories` — `PATCH` by a
  holder of `settings:write`, or of the new **`settings:classes`** for these
  two keys alone (any other key from such a caller is a 403). A change
  applies to units received from then on (AD-31). Vendra 54 reads them.
- **Additive: `colour`, `material`, `dimensions`** (writable on `POST` /
  `PATCH /assets`, published on every asset, null when unset) and
  **`identification_mode`** (read-only, published on every asset: the mode a
  unit was received under through the gates; null for anything else).
- **BEHAVIOUR CHANGE, only on a tenant whose switch is on:** `POST
  /api/v1/assets` refuses `400 validation_failed`, nothing written, a unit
  its class cannot accept — a `serial` class with no `serial_number`
  (*"<class>: 0 of 1 serial numbers captured. Capture one serial number per
  accepted unit."* — Vendra's sentence), any class missing a mandatory
  attribute (`details.missing_fields`, named in the message), a `pool` class
  (*"Pool identification is not built yet (Addendum A Phase E)."*), and a
  `serial_number` already on any asset (empty serials are never compared).
  And it refuses a receipt carrying `custodian_id` (`409 conflict`,
  `details.reason = "not_on_the_register"`). Switch off: none of this is
  asked.
- **Additive: `attributes_confirmed`** (boolean) on `POST
  /assets/<id>/tag-affixed`. REQUIRED (`true`) for a unit received as
  `tag_id` — no manufacturer serial to scan — and refused 400 without it;
  ignored for every other asset.
- **BREAKING (status code), affix only:** a no-two-gates refusal at
  `POST /assets/<id>/tag-affixed` — the person who fired another gate on a
  candidate trying to tag it — is now **`409 conflict`,
  `details.reason = "segregation_of_duties"`, `details.earlier`**, like
  every gate route; it was `400 validation_failed`. Same sentence. Every
  other affix refusal keeps its 400.
- **BEHAVIOUR CHANGE, candidates only:** assigning a custodian, moving,
  transferring or disposing of a unit that is not on the register is refused
  `409 conflict`, `details.reason = "not_on_the_register"`,
  `details.waiting_on` — *"This unit is not on the register yet (waiting on
  <who>); a custodian can be assigned once it is registered."* — on `PATCH
  /assets/<id>`, `/move`, `/transfer-custody`, `/condemn`, and on `POST
  /assets` carrying `custodian_id` or `state: "disposed"`. Approving a
  request that would move a candidate answers the approvals route's own
  `409 conflict` (`details.request_id`) with the candidate sentence.
  Registered assets: unchanged.
- **Additive: `data.sap.discrepancy`** — null, or `{maker_number,
  sap_number, maker, checker, raised_at}` when SAP's INT-06 answer carried
  an asset number different from the one the Register Maker entered. The
  entered number stays in `sap.asset_number` (it is no longer replaced) and
  `sap.reconciliation_state` is `exception` — until the entered number is
  corrected to SAP's (back office), which closes it as `confirmed`. **Additive enum value:
  `sap.code_source = "confirmed"`** — entered by hand, then returned
  unchanged by SAP.
- **Additive: role exclusions** — `GET /api/v1/settings/role-exclusions`
  (`settings:read`), `POST` and `PATCH /api/v1/settings/role-exclusions[/<id>]`
  (`settings:write`), `GET /api/v1/settings/conflicting-grants`
  (`settings:write`). **BEHAVIOUR CHANGE:** `POST /users/<id>/roles` (and
  `POST /users`) refuse `403 forbidden` a grant that would give one person
  both roles of an active exclusion, preview included, naming both roles and
  the reason. Existing holders are not revoked.
- **Additive: `GET /api/v1/meta/readiness`** — no token; 200 `{ready: true}`
  or 503 `server_misconfigured` listing every column this database lacks and
  the module to upgrade. **BEHAVIOUR CHANGE:** any route meeting a missing
  column or table answers `503 server_misconfigured` naming it (was `500
  internal_error`, "Unhandled server error").
- **Additive scope: `settings:classes`** (Asset Controller, Asset Manager).
- **Docs:** `gates.waiting_on` has seven values — `iad_approver` was served
  and not listed (D6).

## 2026-10-07 — handoff 57: the receipt gates (SCAFFOLDING) · `myservice_api` 19.0.3.29.0, `myservice_asset_register` 19.0.1.26.0, `myservice_workflow` 19.0.3.2.0

**Scaffolding for one demonstration; handoff 58 replaces all of it with a
separate candidate model and its own routes. Do not integrate against the
gate routes.** Endpoint reference §14.

**Kept by handoff 58 (2026-10-12) — see the entry above: the gate routes
stand and are integrated against; the sentence before this one is the
record of what was said on 2026-10-07.**

- **Additive: `register_state` and `gates`** on every serialised asset
  (`GET /assets`, `/assets/<id>`, every write's answer). `register_state` is
  read-only and refused in any body.
- **Additive: ten routes, `POST /api/v1/assets/<id>/gates/<action>`** —
  `submit`, `verify`, `approve`, `query`, `resubmit`, `reject`,
  `request-tagging`, `register`, `approve-registration`,
  `return-registration` — and **`GET /api/v1/candidates`**
  (`candidates:read`). Not idempotent (no `X-Idempotency-Key` honoured).
- **Additive: six scopes** — `candidates:read`, `vfm:verify`,
  `vfm:approve`, `tagging:request`, `register:make`, `register:check` —
  and five grantable roles: `iad_vfm_officer`, `iad_vfm_approver`,
  `asset_controller`, `register_maker`, `register_checker`. Asset User and
  the Auditor gain `candidates:read`.
- **Additive: `?register_state=any|<state>` on `GET /api/v1/assets`**
  (`candidates:read`; 403 without it, 400 on an unknown value).
- **BEHAVIOUR CHANGE, only on a tenant whose switch is on
  (`cadra.receipt.gated`, absent = off):** `POST /api/v1/assets` (INT-03)
  answers a candidate — `register_state: "captured"`, `tag: null` — and the
  record is absent from every list, count, report and export until a
  Register Checker approves it. INT-06 (`asset.master.create`) is then sent
  at that approval, not at affix; its payload gains
  `capitalisation.cost_centre` and `capitalisation.sap_asset_number_entered`
  (additive, null for every asset that did not pass the gates), and
  `proposed_capitalisation_date` is the maker's date where there is one.
  **Switch off — every tenant by default — nothing a consumer can observe
  changes except the two additive keys.**
- **Additive: `GET /api/v1/settings`** (`assets:read`): `receipt_gated`
  (bool) and the `receipt_gate` block. **Additive: `PATCH
  /api/v1/settings/receipt-gate`** (`settings:write`, body `{"enabled":
  bool}` only). Parameter `cadra.receipt.gated`, absent = off. A change
  shows in `/reports/configuration-changes`.
- **Additive: `gate_fired`** in `GET /assets/<id>/history` — one per
  transition, append-only, with `from`, `to`, `gate`, `action`, `reason` and
  the recorded evidence.

## 2026-10-06 — handoff 56: the name and the hat · `myservice_api` 19.0.3.28.0

- **Additive: `GET /api/v1/auth/whoami` answers `roles`** — the caller's
  direct roles as `[{key, name}]`, the same rows `/users/<id>` publishes as
  `roles_direct` (same `PUBLISHED_ROLE_NAMES` vocabulary, same key, same
  `GROUP_SCOPES` order), so the app's top bar can name the hat the signed-in
  person wears without `access:read`. Empty list for an account holding no
  role in the published vocabulary.

---

## 2026-10-05 — handoff 54: every time · `myservice_api` 19.0.3.27.0, `myservice_asset_register` 19.0.1.25.0

- **Additive: `POST /api/v1/assets/<id>/tag-affixed` accepts `scanned_format`
  and `serial_format`** — how `tag_number` and `serial_number` were READ,
  when the client knows. The app's camera (whose decoder is now bundled —
  zxing-wasm — rather than the platform's `BarcodeDetector`) passes the
  symbology up with every decode; a typed or keyboard-wedge entry omits the
  keys. The enum, published verbatim: `code_128`, `code_39`, `code_93`,
  `codabar`, `ean_13`, `ean_8`, `upc_a`, `upc_e`, `itf`, `qr_code`,
  `data_matrix`, `pdf417`, `aztec`. A value outside it is a
  `400 invalid_request` naming `allowed_values`, and nothing is written —
  not even the affix a correct `tag_number` beside it would have earned.
  `serial_format` without `serial_number` is refused the same way
  (contradictory input, handoff 34's rule).
- **Additive: every `affix_refused` history entry carries
  `detail.scanned_format`** — the format of the refused value (the tag
  read's on `number_mismatch` and `scrapped`, the serial read's on
  `serial_mismatch`), or `null` where none was claimed: a typed entry, a
  hardware scanner's keyboard wedge, or any row from before this change.
  Null means *not known*, never a guess.
- **A successful affix stores nothing new.** The format is recorded ONLY on
  the refusal record, by ruling (handoff 54 §7): it earns its column where
  it tells an auditor whether a refused number came off Cadra's own label
  (`code_128` / `qr_code`) or a manufacturer's, and nowhere else. The
  response envelope, the `tagging` block and the idempotent replay are
  byte-identical to before for every caller that does not send the new keys.

## 2026-10-05 — handoff 52: the Builder's list · `myservice_api` 19.0.3.26.0, `myservice_asset_register` 19.0.1.24.0

- **Additive: two more affix refusals are recorded, and every `affix_refused`
  history entry says WHICH refusal it was.** The scrapped-label refusal in
  `_mark_affixed` (unreachable through the route, reachable by every other
  caller of the check) and the route's serial-mismatch refusal (the `err()`
  path — the *label going onto the wrong box* event) now write the same
  append-only `affix_refused` event as handoff 51's number mismatch. The
  history entry's `detail` gains a `reason` key — `number_mismatch`,
  `scrapped` or `serial_mismatch` — and the `summary` sentence differs per
  reason, so a reader can tell a wrong label from a dead one. A row written
  before this change has no stored reason and is published as
  `number_mismatch`, the only kind that was recorded then. Refusal texts and
  status codes are byte-for-byte unchanged; nothing about the 400s moved.
- **Documentation: the endpoint index in
  `docs/api/cadra_api_endpoint_reference.md` is complete — all 115
  first-party `/api/v1` routes, with method and scope — and is now held to
  the code by a test** (`tests/test_endpoint_reference.py`). It had carried
  64 rows of 115; the 51 missing included `POST /assets/<id>/tag-affixed`,
  `GET /assets/<id>/history`, all six auth routes beyond `/auth/token`, the
  five report routes and the whole §12/§13 users, roles and sidebar surface.
  No route changed; the index stopped lying by omission.

## 2026-10-05 — handoff 51: the queue and the refusal · `myservice_api` 19.0.3.25.0, `myservice_asset_register` 19.0.1.23.0

- **Additive: `GET /api/v1/tags/replacements`** (`assets:read`) — every tag
  replacement REQUEST, decided ones included, filterable by `state` (the
  label's own values: `pending` is waiting, `scrapped` was approved and
  replaced, `active` was rejected or back in service), `waiting_on_me` and
  `raised_by_me`, with the standard pagination. The sibling of
  `pending-replacements`, not a widening of it: that route stays
  pending-only by its published name and is unchanged. The new route's base
  set is labels that have ever had a replacement requested — a label nobody
  has asked about is not a replacement request and is not listed. Rows are
  the same shape `pending-replacements` publishes, `can_decide` computed
  per caller. A tagging-only credential (`tagging:write` alone) cannot read
  either route; a human tagger reads them through the Asset User pairing.
- **Additive: a new asset-history event type, `affix_refused`.** A tag-affix
  confirmation the register refused because the scanned number did not
  match the label issued now leaves an append-only `nrs.asset.event` row:
  the scanned value as entered (`detail.scanned`), who presented it, when.
  It appears in `GET /assets/<id>/history` with its own `title` and
  `summary`, in `fidelity.events` as a sixth kind, and in the
  `AssetHistoryEvent.type` enum — the additive growth that enum's own
  description promises. The refusal response itself is byte-for-byte
  unchanged (400 `validation_failed`, the message still names the scanned
  and the expected number), and a refused affix still changes nothing on
  the label; what changed is that a refusal followed by a confirmation is
  now a visible sequence instead of a clean affix record.

## 2026-10-04 — handoff 50: the consequences · `myservice_api` 19.0.3.24.0, `myservice_dashboard` 19.0.1.1.0, `myservice_identity` 19.0.1.2.0

- **BREAKING: `GET /assets/export` and `GET /assets/export.csv` take
  `export:read`** (new scope), not `assets:read`. Reading a page of the
  register and taking a copy of all of it are different acts, and one name
  carried both — the same defect handoff 47 split twice. The Auditor group
  grants the new scope; the `admin` wildcard covers administrators; no other
  group or scope changed, so every Asset User, Officer and Manager keeps
  every page read and loses only the whole-register copy. A non-admin
  credential that calls either export route needs `export:read` added to
  its row (8 active non-admin credentials across the nine local tenants
  hold `assets:read` today; for an API credential the export was already
  capped at 100 rows, so the register-sized loss is session-only).
- **BREAKING: `GET /dashboard/map` returns `locations` only.** The `fleet`
  and `recent_requests` keys are gone. The fleet rows carried one row per
  geocoded vehicle — license plate and driver's name — to every holder of
  `dashboards:read`, which handoff 47 split precisely so a person refused
  `/fleet` could not read the fleet (GO-LIVE §25: found by 47's own
  verification pass, left as the open hole in its fix). `recent_requests`
  was read by nothing first-party and its documented shape had already
  drifted from what the server sent. Measured before changing: 0 geocoded
  vehicles exist on all nine local tenants, so no live payload shrank —
  the shape did.
- **Additive: `GET /fleet/map`** (`operations:read`) — the geocoded vehicle
  rows, exactly as `/dashboard/map` used to shape them, on the scope that
  already gates every other fleet read. The fleet map is a fleet screen;
  it now wears the fleet's scope.
- **BREAKING: the employee-sync feed no longer accepts `mobile`.** Removed
  from the model-level accepted set (`nrs.sap.sync.log`), so all six
  callers — `POST /api/v1/integrations/sap/employee-sync`, the legacy door
  and its `/test` twin, the xlsx job, the CSV wizard, the loader script —
  now refuse a body carrying it (the v1 route's whole-batch 400 with
  `details.rejected_fields`; the model's per-row error elsewhere). Measured
  before removing (2026-10-03): 0 of 15,780 employees across all nine local
  tenants hold a mobile number — nrs19's real 11,386-employee extract
  included — and 0 of 321 sync payloads ever carried the key. A key that
  is accepted, never stored anywhere a reader can see, and never sent is
  not a contract, it is a trap (an accepted key nobody can read back is
  unverifiable by construction); the feed is live on no tenant (secret set
  on 0 of 8, report 37), so no caller can hit the refusal today.
- **Additive: two write-only keys are now readable.** `salvage_rate` is
  published in the asset's `financial.depreciation` block beside the
  `salvage_value` it derives, and `verification_notes` on the asset GET
  beside the verification fields. Both were writable since their routes
  opened and readable nowhere; a round-trip can now verify what it wrote
  (the third of the three, `mobile`, went the other way — above).
- `/auth/login` tokens: an Auditor's token now carries `export:read`. No
  other role's token changed.

## 2026-10-03 — handoff 49: the auditor's own screens · `myservice_api` 19.0.3.23.0

- **Additive: four new sidebar item keys** in `GET /api/v1/settings/sidebar`
  and writable through its PATCH — `configuration_changes`,
  `disposals_report`, `register_snapshot`, `register_export`, all in the
  `audit` group, default on. Published item keys 26 → 30; nothing retired,
  nothing renamed, every existing key and its stored switch untouched. No
  other route changed: the four report/export routes the new screens read
  are exactly as published.

## 2026-10-03 — handoff 37: the doors, and the red tests · `myservice_api` 19.0.3.22.0, `myservice_website_theme` 19.0.1.1.0, `myservice_identity` 19.0.1.1.0, `myservice_asset_depreciation` 19.0.1.1.0

(Numbered 37 and landing after 48: it was written on 30 September, held while
the demo handoffs ran, and re-checked by the Architect on 3 October.)

- **BREAKING: `POST /api/v1/home/quick-submit` enforces the two fields its
  schema has always declared `required`.** A body missing `type_id`, or
  missing a non-blank `description`, is now `400 invalid_request` with
  `details.missing_fields` (plus `details.required` and `details.writable`),
  and nothing is written. Until now an absent type fell back to whichever
  request type happened to be first and active, and an absent description
  created a request titled *"Quick facilities request"* — an empty record
  under a 201. The public twin `/api/myservice/quick-submit` refuses the
  same bodies in a visitor's sentence with the same `missing_fields` list
  beside it; the homepage form has always enforced both fields in
  JavaScript, so no live caller sent what is now refused.
  `details.missing_fields` is the third refusal key of this route, beside
  `rejected_fields` (the key is not accepted) and `unusable_fields` (the
  value names no record): three refusals, three different repairs.
- **BEHAVIOUR CHANGE on the legacy identity door `POST /api/sap/employee-sync`
  (outside `/api/v1`; inventoried in `docs/api/EXTERNAL-SURFACES.md`): a row
  carrying a key the feed does not read is refused whole.** The rule now
  lives on the model (`nrs.sap.sync.log.process_sap_payload`), underneath
  all six callers — this door, its `/test` twin, the v1 route, the xlsx
  import job, the CSV import wizard and `scripts/load_employees_xlsx.py` —
  so a CSV column the wizard does not recognise, or a webhook key the feed
  never read, is an `error` row naming the keys and the accepted set
  instead of a silent drop. The v1 route's whole-batch 400 (handoff 32) is
  unchanged and still fires first for its callers. Measured before
  changing: the webhook secret is set on 0 of 8 tenants and nothing in the
  repo provisions it, so no caller can reach the changed behaviour today.
- **The v1 route `POST /api/v1/integrations/sap/employee-sync` is the
  employee-sync door an integration should use.** Ruled in handoff 37 §A:
  the legacy identity door will be retired once SAP is pointed at the v1
  route; it is NOT removed in this change and its secret gate, shapes and
  response envelope are untouched. Driven side by side on 2026-10-03, the
  v1 route answers every body the legacy door can actually accept, against
  the same register, with the same per-row `results[]` schema — and the
  legacy door cannot do its own job on Odoo 19: every employee create and
  update it attempts fails (`hr_version.last_modified_uid` is NOT NULL and
  an `auth='none'` environment has no user to stamp), reported per-row as
  `status: "error"` under a top-level `"success": true`, and the list shape
  its own documentation promises is refused by Odoo 19's JSON-RPC
  dispatcher (`Invalid JSON-RPC data`) before the route runs.

## 2026-10-03 — handoff 47: a role is a job · `myservice_api` 19.0.3.21.0, `myservice_asset_register` 19.0.1.22.0

(Heading restored by handoff 50: report 37's commit `eb52157` deleted it,
leaving the bullets below reading as part of the handoff 37 section above.)

Three scope moves, each **BREAKING** for a credential provisioned under the
old scope. No route, field, enum or status code changed — only which scope a
token must carry. The `admin` wildcard covers all of them, so admin-scoped
credentials are unaffected.

- **BREAKING: `GET /reports/access-changes` takes `access:read`** (new
  scope), not `identity:read`. The scope was two data sets under one name:
  the employee roster a custodian picker needs, and the record of who
  granted whom which role. Every route under `/identity/*` keeps
  `identity:read`. The Auditor group now grants `access:read`; a non-admin
  credential that reads this report needs `access:read` added to its row.
- **BREAKING: the fleet, FM and security routes take
  `operations:read`** (new scope), not `dashboards:read`:
  `/dashboard/fleet-command`, `/fleet`, `/fleet/<id>`, `/fleet/dashboard`,
  `/fm/dashboard`, `/security/kpis`, `/security/map-data`,
  `/security/trend`, `/security/recent`. The asset register's own figures —
  `/dashboard/kpis`, `/dashboard/map`, `/reports/depreciation` — keep
  `dashboards:read`. The Security Officer and Bus User groups now grant
  `operations:read` (and no longer `dashboards:read`).
- **BREAKING: `POST /barcode/generate` and `POST /tags/<id>/request-replacement`
  take `tagging:write`**, not `assets:write`. Minting and replacing a label
  is the Tag-Issuing Unit's job; until now the unit could confirm a label
  and not print one, while every `assets:write` holder could. Deciding a
  replacement (`/tags/<id>/approve-replacement`, `/reject-replacement`)
  stays `approvals:write`. `POST /assets` still mints a tag server-side,
  so registration is unaffected.
- **New role in `/roles`: `asset_officer`** (grantable) — Asset User's
  reads plus `assets:write`; Asset Manager now implies it. A session token
  for a user holding the group carries the union as always. The Manager's
  own `GROUP_SCOPES` row lists only its delta now; no manager's effective
  scopes changed.
- `/auth/login` tokens: users in the Security Officer or Bus User groups
  now carry `operations:read` instead of `dashboards:read`; Auditors
  additionally carry `access:read`. Asset User, Officer, Manager and
  Tag-Issuing Unit tokens are otherwise unchanged.

## 2026-10-03 — handoff 48: what this tenant has · `myservice_api` 19.0.3.20.0

Additive throughout; the one behaviour change below alters no answer.

- **New route `GET /api/v1/settings/sidebar`** — any valid token. Which
  sidebar items and groups this tenant shows, each switch's own position
  (`enabled`), what is drawn (`shown`, items: the item's switch AND its
  group's), whether anybody ever set it (`configured`), `locked`, and who
  last changed it (`changed_by`, `changed_at`). `hidden_items` lists the
  item keys not drawn. **`is_a_permission: false` and `statement` say in
  words that this is presentation**: no route reads these switches, and an
  item switched off still opens by its address.
- **New route `PATCH /api/v1/settings/sidebar`** — `admin`. Body
  `{"items": {key: bool}, "groups": {key: bool}}`; only the switches named
  change. Every refusal is `400 invalid_request` before anything is written:
  an unknown body key (`rejected_fields`/`writable`), an empty body, an
  unknown key (`unknown`, `allowed_values`), a non-boolean value
  (`not_boolean`), and switching off `sidebar_settings` or its group
  `settings` (`locked_items`, `locked_groups`) — the screen these are
  changed from. Not idempotent-keyed (it is a set, so a replay is harmless).
- **Keys are stable identifiers**, never renamed or reused: 10 groups and 28
  items, listed in the endpoint reference §13. One `ir.config_parameter` row
  per switch (`cadra.sidebar.item.<key>` / `cadra.sidebar.group.<key>`,
  `on`/`off`), so each switch appears in `/reports/configuration-changes`
  under its own key. Absent = on.

## 2026-10-03 — handoff 46: everyone sees their own job · `myservice_api` 19.0.3.19.0

Additive throughout; the one behaviour change below alters no answer.

- **New key on every user row** (`GET /api/v1/users`, `/users/<id>`, and the
  rows the user writes return): `is_test_fixture` (boolean, read-only, in no
  allow-list). `true` for an account created by a test credential — the
  suites' invited officers and the demo personas
  (`scripts/seed_demo_personas.py`) — so a screen can tell an invented
  officer from a real one. Derived from the partner, never settable.
- **BEHAVIOUR CHANGE, labelling only:** a record created by an account that
  is itself a fixture is now labelled `is_test_fixture: true` (and an
  append-only row it causes carries `source: "test"`), where before only a
  record created through a flagged CREDENTIAL was. Nothing a real
  credential or a real person creates changes. A consumer that filters
  fixtures out will now also filter out what a demo persona did — which is
  the intent: an invented officer's verification is not history.

## 2026-10-02 — handoff 45: the first five minutes · `myservice_api` 19.0.3.18.0, `myservice_asset_register` 19.0.1.21.0

All additive except where marked.

- **New, anonymous:** `POST /api/v1/auth/password-token/inspect` `{token}` →
  `{state, kind, expires_at, organisation, password_rules, name?, login?,
  message?, next?}`; `state` ∈ `outstanding · expired · redeemed · cancelled ·
  invalid`, `kind` ∈ `invitation · reset`. Always 200 for a well-formed body.
- **New, anonymous:** `POST /api/v1/auth/password-token/redeem` `{token,
  password, confirm_password}` → the same `data` block as `/auth/login`, plus
  `signed_in` and `login`. `409 conflict` with `details.state` for a link that
  cannot be used; `400 invalid_request` for a password refused, in words.
- **New, anonymous:** `POST /api/v1/auth/password-reset` `{login,
  turnstile_token?}` → one sentence, the same whether or not an account
  matched.
- **BEHAVIOUR CHANGE — the letter's link.** Invitation and reset letters link
  to `/app/accept-invite?token=…` and `/app/reset-password?token=…` (only the
  token). A GET of the old `/web/signup?…token=…` or
  `/web/reset_password?…token=…` redirects there with the same token.
- **BEHAVIOUR CHANGE — the back office.** `/web`, `/odoo` and every
  `/odoo/<path>` redirect a non-administrator (signed out of Odoo first) and an
  anonymous visitor to `/app/`. `/web/login`, `/web/health`, assets, images,
  `/report/*` and `/websocket` are unchanged. A non-administrator who signs in
  on `/web/login` is sent to `/app/` with no Odoo session.
- **New:** `POST /api/v1/approvals/<id>/renominate` `{approver_id, reason}`
  (scope `assets:write`) re-points a pending request; the approval row gains
  `approver.active`, `can_renominate` and `renominations`.
- **New events in `GET /reports/access-changes`:** `deactivated`,
  `reactivated` (`group: null`), with `summary.account_state_changes_in_period`,
  `account_state_changes_not_shown`, `account_state_coverage` and
  `fidelity.account_state_record_starts_at` / `_rows`.
- **BEHAVIOUR CHANGE — event order.** Within one second, an account's events
  are ordered by the record's id (the order they happened) and no longer by
  event name.
- **New:** `GET/PATCH /settings/branding` carry `sender_email` (the main
  company's email), validated before any write.
- **Wording:** a refusal naming `base.group_system` says *System
  Administrator* (handoff 44, released in the same build).

## 2026-10-02 — handoff 43: the person, and the door · `myservice_api` 19.0.3.17.1

Four new WRITE routes, scope `admin`, one additive block on every user row,
one public image route, and one **BEHAVIOUR CHANGE** on every authenticated
request. Nothing on an existing response changed shape or lost a key.

### New — `POST /api/v1/users` (201)

Create a person and send them the invitation. Body `{"name", "email",
"roles": [...], "send_invitation": true}` — `email` is also the sign-in
name (lower-cased), `roles` is the vocabulary of `GET /roles` and is written
exactly as `/users/{id}/roles` writes it (so a role the model refuses,
`system` included, is `403 forbidden` in the model's sentence and **the
account is not created**), and `send_invitation` defaults to true. Answers
the user row as `GET /users/{id}` publishes it. Refusals: `400
invalid_request` (a stray key → `details.rejected_fields` + `writable`; a
bad value → `details.field`), `409 conflict` when the address is already
held by an account, active or deactivated (`details.user_id`,
`details.active`), and `500 server_misconfigured` when the letter could
not be sent (no outgoing mail server, relay refused) — in which case
**nothing is created** and the message names the cause and the way round
it (`send_invitation: false`, then `/invite`). The letter's From falls back
as core's reset does — the company's address, the sender's, the
recipient's own — so a tenant without a company address still sends.
Idempotent under `X-Idempotency-Key`.

### New — `POST /api/v1/users/{user_id}/invite`, `/deactivate`, `/reactivate` (200)

No body key is accepted on any of the three (a `reason` has nowhere to
live, so it is refused rather than dropped). Each answers the user row.
`/invite` re-sends the letter with a fresh link and is refused for a
credential (400), a deactivated account (409), an account with no address
(400) and a person who has already signed in (409 — a reset is theirs to
ask for from the sign-in page). `/deactivate` is refused for the caller's
own account (403), for the user behind an API credential (400 — revoke the
credential), when already inactive (409) and when they are the last active
system administrator on the tenant who is a person (409 — the users behind
API credentials hold the group too and do not count). `/reactivate` is refused for a
credential (400) and when already active (409). All idempotent.

### Additive — `invitation` on every `User` row

`{"state", "sent_at", "sent_by", "sends", "expires_at"}`; `state` is one of
`never`, `outstanding`, `expired`, `redeemed`, `cancelled`. Always `never`
for an API credential. `tests/test_users.py` holds the key list.

### New — `GET /api/v1/brand/logo` (public)

The tenant's `cadra.brand_logo` served as an image (`image/svg+xml`, `png`,
`jpeg` or `webp`), 404 when the tenant has none. Exists because mail
clients strip `data:` images and the invitation letter needs a URL.

### BEHAVIOUR CHANGE — a deactivated account's token is refused now, not at `exp`

`require_jwt` reads `res.users.active` on every request and answers `401
unauthorized` "Account is disabled" for a deactivated account. Until now
only `/auth/login` and `/auth/refresh` looked; an access token minted before
deactivation kept working for up to 3600 s. A consumer that caches tokens
across a deactivation now sees a 401 where it saw 200 — which is the point.

### BEHAVIOUR CHANGE — a deactivated nominee is refused on `/move`, `/transfer-custody` and tag replacement

`approver_id` naming an archived user answers `400 invalid_request` ("…
cannot be asked: their account is deactivated"). Until now the picker
(`/approvals/approvers`) hid archived users and the nomination check did
not, so a request could be raised that waited on somebody who cannot sign
in.

### Outside `/api/v1` — the sign-up door, the letters, and a cron

Odoo's *Users: Notify About Unregistered Users* cron is switched off on
upgrade and on install: five days after an unredeemed invitation it mailed
the inviter Odoo's own letter. An anonymous `/web/reset_password` builds
its link on `web.base.url` exactly as before; only an authenticated caller
(an API token or a back-office session) gets the link on the host they
came in on, so a forged `X-Forwarded-Host` on a public request cannot
choose where a victim's link points.

`GET /web/signup` without a token answers 404 on every tenant **by code**:
`res.users._get_signup_invitation_scope` returns `b2b` regardless of
`auth_signup.invitation_scope` or the website's setting. The invitation and
password-reset emails Odoo sends on every path (`/web/reset_password`, the
user form, `res.users.create`) are now Cadra's templates in the tenant's
brand, with the link on the host the request came in on.

## 2026-10-02 — handoff 42: the grant, and the refusal · `myservice_api` 19.0.3.16.0

One new WRITE route, scope `admin`, and one additive key on `GET /roles`.
Nothing on an existing response changed shape.

### New — `POST /api/v1/users/{user_id}/roles`

Set the Cadra roles an account holds DIRECTLY. The body is `{"roles":
[...], "dry_run": false}`: `roles` is the **full set** of direct role keys
the account should hold afterwards, among the vocabulary of `/roles` — not
a delta. A key present and not held is granted; a key held and absent is
revoked; groups outside the vocabulary are never touched. Any other body
key is `400 invalid_request` with `details.rejected_fields` and
`details.writable`; an unknown key is `400` with `details.allowed_values`.
Idempotent under `X-Idempotency-Key`. `404` for a structural account, a
portal user or an unknown id, through the same domain as `GET /users/{id}`.

The answer (`RoleChange`) is the account as `GET /users/{id}` would now
publish it, `before` and `after` (each `roles_direct` AND `roles_effective`,
so a grant of Asset Manager shows Asset User arriving by implication),
`granted`, `revoked` and `applied`. **`dry_run: true` previews**: the same
write is computed by Odoo and rolled back, `after` is what the account
would hold, `applied` is `false`, and nothing is written — a refusal is
previewed too.

**Two refusals, both `403 forbidden`, both raised on the MODEL under every
writer of membership and shown in the model's own sentence** (handoff 42
§2–3; `models/access_guard.py`):

| Refused | The sentence begins |
|---|---|
| naming any role `/roles` does not mark `grantable` — `system` first among them, and every other Odoo group | *Over the API only these roles can be granted or removed: Asset User, Asset Manager, Tag-Issuing Unit, Auditor. '…' is not one of them. …* |
| adding a role to the caller's OWN account (removing one is allowed) | *Nobody grants themselves a role. `<login>` asked to add `<role>` to their own account; another administrator has to do that. …* |

`system` is a VALID key at the route on purpose: it reaches the write so the
refusal the caller reads is the model's. A refused call writes nothing — the
access record included, because the refusal is an exception and the
transaction rolls back. The record of an applied change (`GET
/reports/access-changes`) names the token's user as the actor, a credential
or a person, never Administrator, although the route runs under sudo.

The same guard refuses, over the API only and from any route that might
ever try: creating or deleting a group, changing what a group implies,
deleting an account, and a membership change from the group side — with
sentences of their own. Nothing without a bearer token is guarded: the back
office, `odoo shell`, migrations, security XML and `auth_signup` work as
before.

### Additive — `grantable` on every `GET /roles` entry

`true` for exactly the four Cadra roles (`asset_user`, `asset_manager`,
`tag_issuing_unit`, `auditor`); `false` for `system` and the rest. Read off
the same constant the model refuses on, so a screen that disables what
`grantable` is `false` for disables exactly what the server would refuse.

---

## 2026-10-01 — handoff 41: who has what · `myservice_api` 19.0.3.15.0

Three new READ routes, all scope `admin`, and one behaviour change on four
existing reads. Nothing here changes membership; that is handoff 42.

### New — `GET /api/v1/users`, `GET /api/v1/users/{user_id}`, `GET /api/v1/roles`

The people on this tenant and what they hold. Every row publishes TWO role
lists, because on Odoo 19 implication is computed at read time and
materialises no rows:

| Key | Meaning |
|---|---|
| `roles_direct` | the Cadra roles this account is a MEMBER of — what somebody granted |
| `roles_effective` | the roles it HOLDS once implication is applied (Asset Manager implies Asset User) |
| `scopes` | what a token minted for this account carries |
| `scopes_source` | `"roles"` for a person (the union over `roles_effective`), `"credential"` for an API credential, whose token is not minted from groups |
| `kind` | `"person"` or `"api_credential"`; `api_client` carries the credential's `id`, `name`, `client_id`, `active`, `is_test_credential` |

Role keys: `system`, `asset_user`, `asset_manager`, `tag_issuing_unit`,
`auditor`, `identity_manager`, `security_officer`, `bus_user` — the eight
groups that grant API scopes, in that order, each with its `scopes` and
`implies` on `/roles`. Filters on `/users`: `q`, `role` (EFFECTIVE), `role_direct`,
`active`, `is_api_client`, plus `limit`/`cursor`. Structural accounts
(`__system__`, `public`, `portaltemplate`) and portal users are never listed
and answer `404` on the detail route.

### BEHAVIOUR CHANGE — `GET /barcode/lookup`, `/barcode/kpis`, `/barcode/recent-tags`, `/barcode/print-url`

These four read as the TOKEN'S user, where every other route reads under
sudo; a session user holding `assets:read` without an Odoo access rule on
the models behind them got `403 forbidden` with an ORM sentence in it
(*You are not allowed to access 'Asset Barcode Tag' records*, or
*'Location'* on recent-tags). They now read under sudo like every other
route: the scope is the only gate, as documented. An API credential never
saw the difference. No payload changed.

---

## 2026-10-01 — handoff 38: a scanned serial finds its asset, and a faded tag can be replaced · `myservice_api` 19.0.3.14.0

Two things NRS asked for on 30 September. Both additive, with one
behaviour change on the lookup payload that is called out below.

### The serial lookup now works — `GET /barcode/lookup` and `GET /tags/lookup`

Both routes have documented their parameter as *"Tag, asset code, or serial
number to look up"* since June 2026 (`e189ff0`), and neither searched serial
numbers: the serial of a TAGGED asset answered `404`. The description is
now true. Resolution is **tag number, then asset code, then serial number**,
each an exact match; the serial is compared case-insensitively after the
query is stripped, so a scanner's trailing space or Enter still finds it.
Internal whitespace and leading zeros stay significant. Scrapped and
pending tags still do not resolve by their number — that branch is
unchanged.

**Additive, both routes:**

| Key | Meaning |
|---|---|
| `matched_by` | `"tag_number"`, `"asset_code"` or `"serial_number"` — which field the query matched |
| `tagged` | whether the asset has an ACTIVE tag |
| `serial_number` | the asset's serial, `""` when none |

`/tags/lookup` also gains `asset_code` and `tag_state`, which it did not
publish before.

**BEHAVIOUR CHANGE — `/barcode/lookup` `tag_id` can be `null`.** An asset
found by code or serial that has no ACTIVE tag now answers `200` with
`tagged: false`. If a replacement is pending, the tag block (`tag_id`,
`tag_number`, `tag_state: "pending"`, `tag_date`) describes that pending
label; if the asset has no tag at all, `tag_id` is `null` and the three
strings are `""`. Before this release such an asset could not be found at
all, so no consumer has seen a `200` with an empty tag block — but a client
that indexes `tag_id` on every hit must now allow for `null`.
`/tags/lookup` has never published an id and still does not.

**A serial on more than one asset is a `404` that says so.** `nrs19` carries
1,291 serial values on more than one asset (model names typed into the
serial field — `PROBOOK` on 94). Resolving one to whichever row sorts first
would show the wrong asset with a green tick on it, so:

```json
{ "error": { "code": "not_found",
  "message": "Serial number PROBOOK is on 94 assets; scan the tag or the asset code instead",
  "details": { "query": "PROBOOK", "ambiguous": true,
               "matched_by": "serial_number", "matches": 94 } } }
```

A plain miss carries `details.query` only; `details.ambiguous` is PRESENT
only on the ambiguous kind, so a screen branches on its presence.

### New — tag labels: five endpoints

A tag replacement is a request and a decision by two different people, on
the pattern handoff 35 published for a move: a nominated `approver_id` at
request time, the decider taken from the bearer token, self-approval refused
in the model, a reason required when asking and when refusing, and a
decision taken once. The model has had the state machine (`active → pending
→ scrapped`) since the barcode station was built; it was reachable only from
the Odoo back office.

| Route | Scope | Notes |
|---|---|---|
| `GET /api/v1/tags/pending-replacements` | `assets:read` | Labels in `pending`, newest request first. Cursor-paginated |
| `GET /api/v1/tags/<id>` | `assets:read` | One label — the `nrs.asset.tag.label` id (`tagging.label_id` on an asset, `tag_id` on a lookup), NOT an asset id |
| `POST /api/v1/tags/<id>/request-replacement` | `assets:write` | Idempotent. `{"reason", "notes"?, "approver_id"}`. `reason` is one of `tag_replacement_reason` (below), else `400` with `details.allowed_values`. `approver_id` required, resolved exactly as `/assets/<id>/move` does. `409 conflict` when the label is not `active` — `details` name `requested_by`, `approver` and `replaced_by` |
| `POST /api/v1/tags/<id>/approve-replacement` | `approvals:write` | Idempotent. `{"reason"?}`. Scraps the label, mints the next number, links the two. `403 forbidden` with `details.is_own_request` for the requester; `409` once decided, naming `decided_by` / `decided_at` |
| `POST /api/v1/tags/<id>/reject-replacement` | `approvals:write` | Idempotent. **`reason` is REQUIRED.** The label returns to `active` |

A request answers `200` with `pending_approval: true` first, the label, and
the asset UNCHANGED — the same shape and the same reasoning as a raised move
(handoff 35: the status cannot vary per call without breaking byte-exact
idempotent replay). An approval answers `{tag, new_tag, asset}`; a rejection
`{tag, asset}`. Every label is published as:

```json
{ "id": 913, "tag_number": "NRS-ITC-041", "state": "scrapped", "label_state": "scrapped",
  "source": "auto", "tag_date": "2026-09-30", "scrapped_date": "2026-10-01",
  "asset": {"id": 124, "name": "…"}, "asset_code": "AST-00124", "serial_number": "5CD1234ABC",
  "replacement_reason": "damaged", "replacement_notes": "faded past reading",
  "requested_by": {"id": 2, "name": "…"}, "requested_at": "2026-10-01T09:12:03",
  "approver": {"id": 7, "name": "…"},
  "approved_by": {"id": 7, "name": "…"}, "approved_at": "2026-10-01T09:40:11",
  "rejected_by": null, "rejected_at": null, "decision_reason": "sighted it — unreadable",
  "replaces": null, "replaced_by": {"id": 914, "tag_number": "NRS-ITC-042"},
  "can_decide": false }
```

`approver` is WHO IS BEING ASKED and comes from the requester's body;
`approved_by` / `rejected_by` is WHO CLICKED and comes from the token. A
body naming either, or `requested_by`, `state`, `label_state` or a date, is
**refused `400`** with `details.rejected_fields` and `details.writable`,
as is any key the route does not accept — nothing is written. `can_decide`
is computed for the CALLER.

**The old number is never reissued.** `nrs.asset._generate_tag` checks every
label on the tenant, scrapped ones included, before minting;
`tests/test_tag_replacement.py` proves it by doing one. A pending label's
number does not resolve on the lookup routes until the decision — look the
asset up by its code or serial meanwhile; after approval the new number
resolves and the old one answers `404`.

### `GET /api/v1/meta/enums` — two more sets

`tag_replacement_reason` (`damaged`, `lost`, `stolen`, `reassign`, `other`)
and `tag_state` (`active`, `pending`, `scrapped`), read from
`nrs.asset.tag.label` like every other set. Prefixed `tag_` for the reason
`asset_state` and `approval_state` are.

---

## 2026-09-22 — handoff 35: nobody moves an asset alone · `myservice_api` 19.0.3.13.0

**BREAKING.** On any tenant where approval is required — **which is the
default, and the default is what an unconfigured tenant gets** — `POST
/api/v1/assets/<id>/move` and `POST /api/v1/assets/<id>/transfer-custody` no
longer move the asset. They raise a request for a second person to agree to,
and `approver_id` becomes required on both. `PATCH /api/v1/assets/<id>`
refuses a `location_id` or `custodian_id` that would move the asset to a
DIFFERENT one — re-sending the value it already has, and clearing it to
`null`, both still save.

**The version that behaves this way is `myservice_api` 19.0.3.13.0** (with
`myservice_asset_register` 19.0.1.19.0). An integration can tell without
asking: `GET /api/v1/settings/approvals` returns `{"required": …}`, and on a
Cadra that predates this it is a `404`.

### The status stays 200, and the body carries it

A raised request answers **`200`**, not `202`, with:

```json
{ "data": { "pending_approval": true, "action": "move",
            "request": { "id": 41, "reference": "CR/2026/0041", "state": "pending", "…": "…" },
            "asset": { "…": "UNCHANGED, read back in this response" },
            "movement_id": null, "transfer": null, "custody_change": null } }
```

`pending_approval` is the first key and a boolean, so the cheapest possible
read of the response is the correct one. The three keys the old contract
published are explicitly `null` rather than absent, because a consumer
reading `movement_id` must be able to tell *not yet* from *gone*.

**Why not 202.** This API has no per-call success status — it comes from the
`cadra_route` decorator — and adding one would have to be carried through the
idempotency cache as well, or a replay of the same `X-Idempotency-Key` would
answer `202` once and `200` afterwards. An idempotent replay that is not
byte-exact is the property handoff 18 built and handoff 31 protected, and
that was judged worth more than a better-looking status code on one route.
**Read `data.pending_approval`, or read `data.asset` — do not read the
status.**

### BREAKING — `POST /assets/<id>/move`

| | Before | Now, where approval is required |
|---|---|---|
| the asset | moved | **unchanged** |
| `approver_id` in the body | not read | **required** — `400 invalid_request` without it, `details.approvers` lists who may be asked |
| `data.movement_id` | the new movement row | **`null`** |
| `data.transfer` | the transfer document, or `null` | **`null`** |
| another request already pending on this asset | n/a | **`409 conflict`**, `details.pending_request` names it |
| the asset is disposed | `400 validation_failed` | `400 validation_failed` (unchanged — refused before anything is raised) |


Where approval is NOT required the route behaves exactly as before,
`approver_id` is ignored, and nothing in the response changes.

### BREAKING — `POST /assets/<id>/transfer-custody`

The same, with `data.custody_change` `null` instead of the custody block —
**with one difference, and it is a defect rather than a decision.** `/move`
refuses a disposed asset before it raises anything; `/transfer-custody` has
no such check, so on a disposed asset it answers `200` with a pending request
that can never be approved — the premise check refuses it when the approver
clicks, saying the asset has been disposed of — and it occupies that asset's
one pending slot until somebody withdraws it. Do not send one.

### BREAKING — `PATCH /assets/<id>`

A body that would CHANGE `location_id` or `custodian_id` is
**`400 invalid_request`** and **nothing in the call is written** — not the
other fields either, which is the whole-body refusal handoff 31 published.

```json
{ "error": { "code": "invalid_request",
  "message": "This register requires a second person to approve a change of `location_id`, so it cannot be PATCHed: use POST /api/v1/assets/124/move, which raises a request. Nothing in this call was written.",
  "details": { "asset_id": 124, "approval_required": true,
               "rejected_fields": ["location_id"],
               "writable": ["…everything else…"],
               "use_instead": { "location_id": "POST /api/v1/assets/124/move" } } } }
```

**A body that NAMES either field with the value it already has still saves.**
The Cadra app's edit form re-sends every field on every save, and refusing
the presence of the key rather than the change would make saving a note on
an asset impossible — the trap `CLAUDE.md` names about a screen that PATCHes
back the object it GET-ed.

**And CLEARING either field still saves.** `{"custodian_id": null}` and
`{"location_id": null}` are not refused on any tenant: taking an asset back
from somebody, or off a location, hands it to nobody. Going the other way —
nobody to somebody, nowhere to somewhere — is a grant and is refused, so two
calls buy a caller nothing one would not. Refusing a clear was the first
draft's behaviour and was a dead end, not a control: the message named
`POST …/transfer-custody`, which requires `to_custodian_id`, so un-assigning
a custodian would have become impossible through the API.

### New — seven endpoints

| Route | Scope | Notes |
|---|---|---|
| `GET /api/v1/approvals` | `assets:read` | The queue. Cursor-paginated, newest first. Filters: `state`, `change_type`, `asset_id`, `waiting_on_me`, `raised_by_me` |
| `GET /api/v1/approvals/<id>` | `assets:read` | One request |
| `GET /api/v1/approvals/approvers` | `assets:write` | Who this caller may ask — everyone who could have made the change themselves, minus the caller. `?q=`, `?limit=` |
| `POST /api/v1/approvals/<id>/approve` | `approvals:write` | Idempotent. `{"reason": …}` optional |
| `POST /api/v1/approvals/<id>/reject` | `approvals:write` | Idempotent. **`reason` is REQUIRED** |
| `POST /api/v1/approvals/<id>/withdraw` | `assets:write` | Idempotent. The requester's own |
| `GET /api/v1/settings/approvals` | `assets:read` | Whether this tenant requires a second person, and whether anybody ever set it. **`assets:read`, not `settings:read`** — the app asks it wherever it draws a Move button, and `settings:read` is held only by Asset Manager and Auditor |

Reading the queue is `assets:read` and not `approvals:write`, so an Auditor
can read who authorised what without being able to authorise anything.
Withdrawing is `assets:write`, because taking back your own request is not a
decision about somebody else's — requiring `approvals:write` would leave a
requester who cannot approve unable to cancel their own request.

### Two fields that are never the same field

* **`approver`** — WHO IS BEING ASKED. Sent by the requester as
  `approver_id` on `/move` and `/transfer-custody`. A nomination: it puts the
  request in somebody's queue and addresses the notification. It confers
  nothing — anyone eligible may decide any pending request.
* **`decided_by`** — WHO CLICKED. Taken from the bearer token, exactly as
  `POST /assets/<id>/approve-disposal` takes its approver. **A body naming
  `decided_by`, `approved_by`, `decided_at`, `requested_by` or `state` on any
  of the three action routes — `/approve`, `/reject`, `/withdraw` — is
  `400 invalid_request`**, not ignored. Those three accept `reason` and
  nothing else.

### The three ways an approval says no

* **`403 forbidden`** — you raised it, or you could not have made the change
  yourself. `details.is_own_request` tells the two apart.
* **`409 conflict`** — already decided, or the premise no longer holds. A
  request records what the asset WAS when it was raised; if somebody else has
  moved it, disposed of it or changed its status since, it cannot be approved
  and `details.premise_broken_reason` says what changed.
* **`400 invalid_request`** — the body tries to say who decided, or sends a
  key the route does not read (only `reason` is accepted).

### New enums on `GET /api/v1/meta/enums`

`approval_state` (`pending` | `approved` | `rejected` | `withdrawn`) and
`approval_change_type` (`location` | `custody`). Prefixed for the reason
`asset_state` is: `state` is the most reused field name in this schema.

### The switch is read-only over the API, on purpose

`GET /api/v1/settings/approvals` publishes it; **nothing sets it.** Every
other settings block on that controller has a `PATCH` twin and this one does
not, because `assets:write`, `approvals:write` and `settings:write` are all
granted by the one group `group_asset_manager` — a `PATCH` would let exactly
the people the rule constrains switch it off, act, and switch it back on. An
administrator sets `cadra.approval.required` in the database, once, and the
exact command is printed inside the refusal a gated write raises.

**Absent, blank, misspelt and unrecognised all mean ON.** `configured` in the
response is what tells *nobody has ever set this* from *somebody turned it
on* — the same behaviour, two very different facts.

See the endpoint reference, §3.5.2, §3.6, §3.7 and §11.

---

## 2026-09-22 — handoff 34: warranty · `myservice_api` 19.0.3.12.0

**Additive. Nothing renamed, nothing that used to be accepted is refused.**
A consumer that sends none of the new keys sees one new block on every asset
and nothing else.

**The version that accepts the new keys is `myservice_api` 19.0.3.12.0**
(with `myservice_asset_register` 19.0.1.18.0). An integration can check it
without asking: `GET /api/v1/openapi.json` lists `warranty_months` among the
properties of `POST /api/v1/assets`'s request body on a Cadra that accepts
them, and not on one that does not. **Sending these keys to an older Cadra
is a `400` for the whole body** (handoff 31), so check first.

- **New writable keys on `POST` and `PATCH /api/v1/assets`:**
  `warranty_start_date`, `warranty_months`, `warrantor`,
  `warranty_reference`. `warranty_expiry` was already writable and is
  unchanged in name and type; **it is now DERIVED when a start date and a
  duration are both present, and a value that contradicts them is a `400
  validation_failed`** — send the start and the duration and leave the
  expiry out. Half a basis (one without the other) is also a `400`.
- **New block `data.warranty`** on every asset: `status`,
  `status_as_of`, the five writable keys under their writable names, and
  `basis`. `dates.warranty_expiry` is unchanged.
- **New list filters:** `warranty_status` (`under_warranty` | `expired` |
  `none`) and `warranty_expires_within_days` (1–3650). Lagos days.
- **New enum on `GET /api/v1/meta/enums`:** `warranty_status`.
- **New history event type** on `GET /assets/<id>/history`:
  `warranty_changed`, append-only, and a fifth entry in `fidelity.events`.
  A reader that switches on event type should expect it.

See the endpoint reference, §3.4 *Warranty*.

---

## 2026-09-22 — handoff 32: the last two doors that dropped fields · `status` and four documented keys that were never read

### BREAKING — `POST /home/quick-submit` and `POST /integrations/sap/employee-sync` refuse a key they do not read

Handoff 31 made eleven routes refuse a body key they do not accept. **It
missed two**, and it missed them for a reason worth naming: those eleven were
found by searching for routes that declare an allow-list, and these two
create records by handing the body to a function taking `**kwargs`. There was
nothing to find.

| Route | Before | Now |
|---|---|---|
| `POST /home/quick-submit` | **201**, request created without the key | **400 `invalid_request`**, nothing written |
| `POST /integrations/sap/employee-sync` | **200**, employee synced without the field | **400 `invalid_request`**, nothing written — **for the whole batch** |

Same shape as the other eleven: `details.rejected_fields` names what was
refused, `details.writable` is the whole accepted set so a caller can repair
itself from the response.

**A batch is refused whole.** `employee-sync` takes a list and a list is one
request. Refusing the eleventh employee after ten have been created would
leave a partial sync under an idempotency key that replays the same answer on
every retry.

**`POST /home/quick-submit` accepts exactly seven keys**: `type_id`,
`description`, `service_id`, `location_id`, `priority`, `reporter_name`,
`reporter_contact`.

**`POST /integrations/sap/employee-sync` accepts exactly twenty-two**:
`ir_number`, `userId`, `personIdExternal`, `displayName`, `firstName`,
`lastName`, `email`, `phone`, `mobile`, `department`, `jobTitle`,
`costCenter`, `gradeCode`, `managerIR`, `hireDate`, `terminationDate`,
`locationName`, `location`, `employmentStatus`, `sap_status`,
`previous_status`, `event`.

### BREAKING — `status` on the SAP sync is refused, and it was never read

`nrs.sap.sync.log` has never read `status`. Employment status arrives as
**`employmentStatus`** (or `sap_status`). But `status` is what this API's
OpenAPI `SapEmployee` schema published — with an enum,
`active`/`inactive`/`terminated`, of which `inactive` is not a value this
system has — what `docs/api/cadra_api_endpoint_reference.md` §9.1 sent, and
what `docs/api/cadra_api_demo_card.md` sent. `officeCode`, also in that
example, has never been read either.

**So every integrator following our own documentation sent an employment
status that went nowhere, under a `200`.** Both keys are now a `400`. Per
rule 4 of `CLAUDE.md` the model is the published surface and the document is
what gets corrected: the schema, the example, the demo card and this
repository's own test are fixed.

This is the third time a published name and the thing underneath it have
been found disagreeing — after a category's `depreciation_method`/`method`
(handoff 30) and a request's `location_id`/`generic_location_id`
(handoff 31). A guard now watches every published key against the field it
claims to write, in both directions, and fails when one stops resolving.

### BREAKING — `POST /home/quick-submit` refuses an id it cannot resolve

A `service_id`, `location_id` or `type_id` that is not a number, or is a
number naming no record, used to be dropped by a bare
`except (ValueError, TypeError): pass` or an unchecked `.exists()` — the
request was created without it and the route answered **201**. It is now a
**400 `invalid_request`** carrying **`details.unusable_fields`**.

Deliberately **not** `rejected_fields`: those keys ARE accepted, and the
repair is different. A caller told `service_id` is "not writable" would drop
the key; what it must do is correct the value.

### BREAKING — a disposed asset's `disposal_date` cannot be cleared

`PATCH /assets/<id> {"disposal_date": null}` on a **disposed** asset is now a
**400 `validation_failed`** and nothing is written. It was the one remaining
way to produce the disposal report's `no_disposal_date` finding against a
disposal made after handoff 31 dated every one of them.

**Correcting the date to another day is unchanged and still allowed** — it is
clearing it that is refused. A **live** asset's `disposal_date` can still be
cleared, and an asset that is already undated may still be sent an empty date
without a refusal, so the Odoo form — which re-sends every field it displays —
can still save a legacy row.

### BEHAVIOUR CHANGE — only a date sent WITH the disposal is the caller's

A disposal is dated with the caller's date **when that date arrives in the
same write as `state: "disposed"`**. Otherwise the register stamps today, in
Lagos.

Before this release the rule was "a date already on the asset is kept", which
could not tell a date sent *with* the disposal from one PATCHed months
earlier: `disposal_date` is writable on a live asset, so an asset given last
year's date while still in service and disposed of today was dated last year,
and the register said it left a year before it did.

**If you record a disposal date agreed in advance** — at a board of survey,
say — send it in the same request as the status:

```json
PATCH /api/v1/assets/1234
{ "state": "disposed", "disposal_date": "2026-09-15" }
```

A date PATCHed first and a status PATCHed later is now stamped with today.
Correcting it afterwards remains a legitimate write. `disposal_date` is
tracked, so the previous value stays in the record either way.

### BEHAVIOUR CHANGE — the documented quick-submit body was never the body

`docs/api/cadra_api_endpoint_reference.md` §8.2 published an example sending
`name`, `email`, `phone`, `subject` and `description`. **Four of those five
have never been read by this route**, and it answered 201 to all of them,
raising a request that carried only the description.
`docs/api/cadra_api_demo_guide.md` sent `name`, `email`, `message` and
`location_name` — four keys, none accepted, and no `type_id`. Both are
corrected; both bodies are now a 400.

If you copied either example, you are sending a body this route has never
accepted. The accepted seven are listed above.

---

## 2026-09-21 — handoff 31: a field the API does not accept is a 400 · `mark-found` · a disposal is dated whichever door it came by

### BREAKING — a body field a route does not accept is refused, and NOTHING is written

**Until this release** eleven write routes answered **2xx**, wrote the fields
they recognised and silently dropped the rest; ten of them named the dropped
keys in `data._warnings.rejected_fields`, and one named nothing at all. **They now answer `400 invalid_request` and
write nothing** — not the refused field, and not the accepted fields sent
beside it.

```json
{ "error": { "code": "invalid_request",
    "message": "This route does not accept: `asset_tag`. Nothing was written.",
    "details": { "rejected_fields": ["asset_tag"],
                 "writable": ["acquisition_cost", "acquisition_date", "…"],
                 "http_status": 400 } } }
```

`details.writable` is every key the route accepts, so a caller can repair
itself from the response. `PATCH /requests/<id>` adds `details.hint` when —
and now only when — `stage_id` is among the refused keys.

| Route | Before | Now |
|---|---|---|
| `POST /assets` · `POST /locations` · `POST /requests` | **201**, record created without the field | **400**, no record |
| `PATCH /assets/<id>` · `/locations/<id>` · `/requests/<id>` | **200**, the other fields written | **400**, nothing written |
| `PATCH /asset-categories/<id>` · `/settings/branding` · `/settings/depreciation` | **200** if any field was accepted, 400 if none | **400** if any field is refused |
| `POST /asset-categories` | **201**, the field dropped and **not even reported** — the one route of the eleven that named nothing in `_warnings` | **400**, no category |
| `POST /assets/<id>/approve-disposal` — reads no body | **200**, approval recorded, keys listed | **400** for ANY body key, no approval; `writable` is `[]` |
| a `PATCH` whose EVERY field was refused (assets, locations, requests) | **200, having written nothing** | **400** |

`data._warnings.rejected_fields` no longer exists on any route. A consumer
that checks it may keep the check; it will never fire. `_warnings.truncated`
on lists and `_warnings.discarded_fields` on the workflow callback are
different facts and are unchanged.

**Why, and why with no deprecation window.** The lenient answer was actively
harmful to the one system consuming it. Vendra's client already treats a
rejected field as a terminal failure and dead-letters the receipt — but
*after* Cadra had created the asset, incomplete, under an idempotency key
that replays the same 201 on every retry; its own operator message says
*"the asset exists in the register, incomplete"*. With a 400 nothing is
created, the mapper is fixed, the receipt is re-delivered and the asset lands
whole. And on the day the Cadra app first showed these warnings to a person,
it turned out that a category's depreciation method had never been changeable
from its own settings screen: the screen sent the one key the API refused,
got a 200, and said *"policy saved"*. A consumer sending a field we do not
accept is wrong about our schema, and the sooner it is told the cheaper the
repair. **A refusal does not burn the idempotency key.** Error responses are never
stored under a key, so a retry is evaluated afresh: the same body is refused
again, and **a corrected body sent under the SAME key succeeds** — then
replays as usual. Acted against `test19`: 400 · 400 · 201 · 201, one asset.
Under the old behaviour the key pinned the incomplete 201, which is what
made the repair manual.

### FIX, found by the 400 — `POST`/`PATCH /requests` SAVE `location_id`. They never did.

**BEHAVIOUR CHANGE, a fix.** `POST` and `PATCH /requests` accept
`location_id`, and **for the life of this API it was dropped with a 201.**
The request model's location field was renamed in the move to Odoo 19, and
this route went on asking the model for the old name: the key was refused,
named in `data._warnings.rejected_fields`, and nobody read it. This
document's reference example, the OpenAPI example, the Cadra app's own
request form and the test suite's fixture all sent a location through these
routes, and none was stored. **`?location_id=` on `GET /requests` was ignored for the same
reason, and answered with every request.**

All three now work: the location is saved, published back as
`data.location: {id, name}` (it was always `null`), and the filter filters.
A consumer that sent `location_id` needs to change nothing.

**READ-SIDE CHANGE — `data.location` will now appear on OLDER requests that
always had one.** The fault was these routes', not the register's: requests
raised by `POST /home/quick-submit`, by a PM schedule, by fleet maintenance
or on the Odoo form have stored their location all along, and
`GET /requests` published `location: null` for them anyway. On `cadra19`
that is all 80 requests. A consumer that treated `null` as *no location*
was misinformed and is now told the truth. A request raised through
`POST /requests` before 21 September 2026 has none — `jaizbankplc`: 0 of
460 — and can be given one now with `PATCH`.

It was found because this release turned the silent drop into a 400. That is
the argument for the change, in one bug.

### NEW — `POST /assets/<id>/mark-found`

Scope `assets:write` · idempotent · body `{"reason": "…"}`, **required** —
where it turned up. Answers `{asset, event_id}` and sets `state` back to
`active`. **409** `conflict` unless the asset is `missing` · 400 if `reason`
is absent, blank or not a string · 404. It does not verify the asset.
`PATCH {"state": "active"}` still works and still records no reason.

### BEHAVIOUR CHANGE — a disposal is dated and decommissioned whichever route made it

Any write that takes an asset into `disposed` — `PATCH {"state": "disposed"}`
included — now sets **`condition = decommissioned`** and, where the asset has
no `disposal_date` and the request sent none, **stamps one: the server's
Lagos day.** Until now only `POST /assets/<id>/condemn` did, and a PATCH into
`disposed` produced an undated disposal in whatever condition it was last in.
A `disposal_date` the caller sends is kept. A `condition` sent in the same
request as `state: disposed` is overridden — `decommissioned` is what
disposed means on this register. **`POST /assets` registering an asset as
ALREADY disposed is not stamped**: it was disposed of on a day this system
never saw, and a wrong date would hide what a missing one shows.

### OUTBOUND — the `asset.disposed` event to SAP (INT-09) follows the register

Two keys of that event's `change` block move with the stamp above, because
the event is built after it:

- **`disposal_date`** is the date the register STORED. Where the caller sent
  no date, the event used to be built before one was stamped — `/condemn`
  and the Odoo button included — so it fell back to the server's UTC day — for
  a disposal made between 00:00 and 01:00 in Lagos, the day BEFORE the one
  the register then recorded. The event and the register now agree.
- **`condition_at_disposal`** is `decommissioned` for a disposal made by
  `PATCH`, where it used to carry whatever condition the asset was last in.
  **It has always been `decommissioned` for every disposal made with
  `/condemn` or the Odoo button**, which set the condition in the same
  write — so the key has never said what condition the asset was in when it
  was disposed of, and now says so consistently. Whether it should carry the
  condition BEFORE disposal is an open question; it is SAP's payload and was
  not changed on our judgement.

### NOT CHANGED, and ruled

**A disposed asset may still be verified** — `POST /assets/<id>/verify`
answers 200. A disposed asset somebody physically finds on the premises is an
audit finding, and a register that refuses to record *"I saw it, today"* is
suppressing the one fact that matters.

---

## 2026-09-21 — handoff 30: disposal is terminal · three fields stop being writable · what happened to an asset, recorded so nobody can alter it

**Two BREAKING changes, both rulings, both closing a request that answered
200 and did the wrong thing.** Then two new routes and the additive rest.

### BREAKING — a disposed asset cannot change status, move, or change hands

Through **any** route. Until now `PATCH {"state": "missing"}` on a disposed
asset answered **200** and put it back on the register; so did any other
`state`. Measured before ruling: across every database we hold, the only
asset that ever left `disposed` was the fixture used to discover that it
could.

| Request on a DISPOSED asset | Before | Now |
|---|---|---|
| `PATCH` with a different `state` | 200, un-disposed | **400 `validation_failed`** |
| `PATCH` with a different `location_id` or `custodian_id` | 200 | **400 `validation_failed`** |
| `POST /assets/<id>/move` | 200 | **400 `validation_failed`** |
| `POST /assets/<id>/transfer-custody` | 200 | **400 `validation_failed`** |
| `POST /assets/<id>/mark-missing` *(new)* | — | **409 `conflict`** |
| `POST /assets/<id>/condemn` *(new)* | — | **409 `conflict`** |
| `PATCH` re-sending the **same** `state`/`location_id`/`custodian_id` | 200 | 200 — unchanged |
| `PATCH` of `disposal_method`, `disposal_reference`, `disposal_proceeds`, `disposal_reason`, `notes`, … | 200 | 200 — unchanged |
| `POST /assets/<id>/approve-disposal` | 200 | 200 — unchanged |

The message is a plain sentence naming the asset. **Every refusal writes
nothing** — no transfer document, no movement, no custody link.
`POST /assets` with `"state": "disposed"` is unchanged: an asset may be
REGISTERED as already disposed. **`missing` is not terminal** — a missing
asset that turns up is `PATCH {"state": "active"}`, as before.

**There is no way to reverse a disposal over the API.** That is deliberate
and is an open ruling, not an oversight.

### BREAKING — `building_id`, `floor_id` and `room_id` are no longer writable

On `POST /assets` and `PATCH /assets/<id>`. They are now reported in
`data._warnings.rejected_fields` like any other field the API does not
accept. **They never did what a caller sending them wanted:** on the Odoo
form they drive `location_id`, through a rule the API never ran, so
`PATCH {"building_id": …}` answered 200, rewrote the building — and with it
the published `address_display` and `coordinates` — and **moved nothing**,
leaving an asset that contradicted itself. `location_id` is the one writable
statement of where an asset is; `POST /assets/<id>/move` is the act.

Unchanged: all three are still **published**, read-only, under
`data.location_hierarchy`, and are still **filters** on `GET /assets` and
`GET /reports/asset-register`. No Cadra document ever told an integrator to
send them; the only place they were advertised was the generated schema for
`POST /assets`, which no longer lists them.

### NEW — `POST /assets/<id>/mark-missing`

Scope `assets:write` · idempotent · body `{"reason": "…"}`, **required**.
Answers `{asset, event_id}`. **400** `invalid_request` if `reason` is absent,
blank or not a string · **409** `conflict` if the asset is already missing,
or disposed · 404.

`PATCH {"state": "missing"}` still works and still carries no reason — a
PATCH has nowhere to put a sentence. The reason given here is kept on a
record nobody can edit or delete; it is **not** a field on the asset.

### NEW — `POST /assets/<id>/condemn`

Scope `assets:write` · idempotent · body `{"reason": "…"}`, **required**.
Answers `{asset, disposal, event_id}`. Sets `state = disposed`,
`condition = decommissioned`, `disposal_reason`, and **`disposal_date` —
stamped by the server, as a LAGOS day** (UTC+01:00, fixed; the day the
register snapshot cuts on). It takes no date. **409** if already disposed.
It does **not** approve the disposal: that is `approve-disposal`, a
different scope.

A consumer disposing of an asset with `PATCH {"state": "disposed",
"disposal_date": …}` can keep doing so. This route exists so that it does
not have to send a date from its own clock.

### ADDITIVE

- **`POST /assets/<id>/verify` answers `data.event_id`** — the record this
  call wrote. Every call writes one, including a second on the same day.
- **`GET /assets/<id>/history`:**
  - a verification made with `/verify`, **every** change of `state`, and a
    change to `grn_reference`, `purchase_order_reference` or
    `sap_asset_number` are now graded **`append_only`**, with
    `record.model = "nrs.asset.event"`. Each is listed **once**: the
    message-log line of the same act is folded into it. Anything that
    happened *before* this release is still a `chatter` event.
  - **new event type `verification_date_set`** — a `last_verified_date`
    written by PATCH. It is *not* a `verified` event: the record does not
    say that anybody checked the asset. A consumer that switches on
    `events[].type` must allow for it.
  - `status_changed` carries `detail.from`, `detail.to` (the enum **keys**)
    and `detail.reason`.
  - `maintenance_request` carries **`detail.reference`** — published to a
    caller that also holds `requests:read`, `null` otherwise — and
    **`detail.reference_withheld`**, so that a `null` reads as *withheld* and
    not as a request with no reference. It was withheld from everybody until
    now, for a reason that turned out to be false.
  - **`fidelity.events`** — per kind of event, the instant from which it has
    been recorded on this database, and a sentence. Per kind, because they
    did not necessarily begin together.
  - **Reworded, because this release made them false:**
    `fidelity.verification`, and the `sap_change`, `provenance_change` and
    `disposal_executor` entries of `fidelity.not_recorded`. **Who carried
    out a disposal is now recorded** — the actor of the `status_changed`
    event into `disposed` — from this release forward, and not before.

### Not reachable over the API, and said so you need not look

A disposed asset's location and custodian are also protected from the two
changes no write makes: **deleting the location, or the employee, it names is
now refused in Odoo** (archive instead), because both columns are
`ON DELETE SET NULL` and the database would otherwise have moved or
un-assigned it. No `/api/v1` route deletes either. Deleting an employee who
holds LIVE assets now appends a custody link for each (`source: direct`) —
visible in `GET /assets/<id>/custody` — where it used to leave the chain
saying somebody still held them.

### NOT CHANGED, and asked about

> **Superseded later the same day — see handoff 31, above. It is a 400 now.**

**An unaccepted field is still a 2xx with `data._warnings.rejected_fields`,
not a 400.** Whether it should be a 400 is an open ruling. The Cadra app now
shows the warning to the person who caused it, which it never did.

---

## 2026-09-21 — `POST /assets/<id>/move` places an asset that has no location

**BEHAVIOUR CHANGE, a fix: a 400 becomes a 200.** Moving an asset whose
`current_location` is null answered **400 `validation_failed` — *"Required
field missing: from_location_id"***. The route always built an
`nrs.asset.transfer`, and that model requires both locations. So an asset
with no location could not be given one through this route at all — 358
assets on `nrs19`, 1,920 (46%) on `jaizbankplc`.

It is now PLACED: `location_id` is set, the append-only movement records it
(`source: api_move`, the reason, no `from`), and **no transfer document is
created — a move is not always a transfer.**

- **`data.transfer` is `null` in that case.** A consumer that reads
  `data.transfer.id` must allow for it. It is still an object whenever the
  asset had a location to be transferred from, exactly as before.
- **`data.movement_id` is new, at the top level (ADDITIVE), and always
  present.** Where there is a transfer, `data.transfer.movement_id` carries
  the same value, where handoff 28 put it.

Every refusal is unchanged: a destination that does not exist is still 404, a
non-string `reason` still 400, the asset's own location still 400 — and none
of them writes anything.

## 2026-09-21 — handoff 29: today is a Lagos day

**`GET /reports/asset-register?as_of=` no longer refuses TODAY for the first
hour of every Lagos day (BEHAVIOUR CHANGE, a fix).** The snapshot's cutoff has
always been the end of `as_of` in West Africa Time, but the *"`as_of` cannot
be in the future"* check compared against the UTC date — which is yesterday
between 00:00 and 01:00 in Lagos. A caller asking for today's register in
that hour got a 400 saying the date had not happened. Both sides of the
question now use the Lagos day, and `details.today` in that 400 is the Lagos
date. A consumer running in UTC and sending the UTC date is unaffected.

Nothing else in the API changed in handoff 29; it was a front-end handoff.
One thing an integrator may notice in DATA: the Cadra app's **Condemn** now
sends `condition: "decommissioned"` along with `state: "disposed"`, as Odoo's
own action of that name always has, so disposals made from the app stop
arriving with a condition of `good`.

## 2026-09-20 — handoff 28: a move is recorded, a verification names somebody

**Nothing here removes or renames a field, an enum value or an error code.**
Two entries are marked BEHAVIOUR CHANGE; read those.

**Every change of an asset's location is now recorded append-only (BEHAVIOUR
CHANGE in what `/history` reports; no request changes).** `nrs.asset.movement`
is written by the asset model itself, underneath every writer of
`location_id` — `POST /assets`, `PATCH /assets/<id>`, `POST
/assets/<id>/move`, a completed transfer, the Odoo form, an import, and the
deletion of a location. **`PATCH location_id` still works exactly as it did
and still writes no transfer document.** What changed is that it is no longer
the quiet way to move an asset: the move is recorded either way.

In `GET /assets/<id>/history`, a `location_moved` event for a move made from
now on has `evidence: "append_only"` (it was `editable_record` via `/move`,
`chatter` via PATCH), `record.model: "nrs.asset.movement"`, a `source`
(`api_move`, `api_write`, `transfer`, `direct`, `location_deleted`, `test`),
and `detail.reason`. `detail.transfer` is null when the move had no transfer
document; where it had one, **`detail.transfer.id` can now be null** — the
document was deleted since, and `detail.transfer.reference` is the reference
recorded WITH the move, which survives that. A move made BEFORE this release
is reported exactly as before, graded `editable_record` or `chatter`. An
asset created at a location gains an opening `location_moved` event (*"Placed
at …"*, no `from`); it is listed and is not counted in
`summary.events_after_registration`.

**The opening state is not history (BEHAVIOUR CHANGE to a number shipped in
handoff 27).** Whatever the `create` that made an asset also wrote — its tag,
its first placement, **and its first custody link when it was created
already assigned** — is listed and is NOT counted in
`summary.events_after_registration` or in
`fidelity.earliest_event_after_registration_at`. Handoff 27 counted that
custody link; an asset created assigned and never touched since now reads
*"There is no recorded history for this asset…"*, which is what it has.
Inside an `append_only` move, `detail.transfer.evidence` is
`"editable_record"`: only `transfer.reference` was recorded with the move,
and the rest of that block — the approver included — is read live from a
document an asset manager can edit.

**`POST /assets/<id>/move` (ADDITIVE, and one BEHAVIOUR CHANGE).**
`data.transfer.movement_id` is the append-only record the call produced —
the same shape as `custody_change.custody_id`. **A `reason` that is not a
string is now a 400 `invalid_request`**, as it already was on
`transfer-custody`; it used to be stored as whatever was sent.

**`POST /assets/<id>/verify` (NEW ROUTE).** Scope `assets:write`, idempotent,
optional body `{"notes": "…"}`. Takes no date and no verifier: the date is
today and the verifier is the ACTING user. Returns `{asset, verification:
{verified_on, verified_by, notes}}`. `notes` describe THIS verification: a
call that sends none clears `verification_notes` rather than leaving the
previous verifier's in place.

**`PATCH {"last_verified_date": …}` now CLEARS `last_verified_by` (BEHAVIOUR
CHANGE).** It still works, and it still cannot name a verifier — but it used
to leave the PREVIOUS one standing beside the new date, so an asset verified
by Alice in January and PATCHed with a June date read *"verified in June, by
Alice"*. A date that arrives without a verifier now has none. Use PATCH to
carry a verification made elsewhere, and `/verify` to make one.

**`last_verified_by` on the asset (ADDITIVE, read-only).** `{id, name}` or
null. Null means nobody is recorded, not that nobody checked: every
verification made through the Cadra app before this release is null. Sending
it is refused and reported in `_warnings.rejected_fields`, as for any field
outside the allow-list.

**Seven fields are now tracked (ADDITIVE in `/history`).** Six provenance
fields — `grn_reference`, `purchase_order_reference`, `purchase_vendor`,
`import_source`, `import_date`, `import_ref` — and `last_verified_by`, so
that a verifier being replaced or cleared is a `verified` event of its own: a
second verification on one day changes no date, and used to change the
verifier without a line anywhere. A change to one is a new
`/history` event type, **`provenance_changed`**, graded `chatter` — visible,
which it was not, and not protected. `fidelity.not_recorded` keeps the key
`provenance_change`; its sentence now says *before tracking began* rather
than *never*. **New in `fidelity`:** `provenance_tracked_from` (the instant,
per database; null = since the first asset) and `location` (when move
recording began, and `located_before_first_movement`), the twin of `custody`.
`fidelity.verification` was reworded, because the Verify button no longer
does what it said.

**`GET /reports/asset-register` (BEHAVIOUR CHANGE in `data.fidelity`).** The
six provenance fields move from `fidelity.as_of_today` to
`fidelity.rolled_back`, and `last_verified_by` — until now
`not_recoverable` and unpublished — joins them and IS NOW A KEY ON EVERY ROW — **but
only for an `as_of` at or after `fidelity.tracked_from.since`.** For an
earlier date they stay in `as_of_today`, exactly where they were, because a
change made before tracking began left nothing to roll back to. So the two
lists now depend on the date asked for. `fidelity.tracked_from: {fields,
since}` and `fidelity.notes.tracked_from` are new. No row shape changed.

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
