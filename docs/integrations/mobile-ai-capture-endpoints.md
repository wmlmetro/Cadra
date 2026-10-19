# Cadra's backend for AI item identification: what exists, what is coming

**For:** the Cadra Mobile team (Barcode Station app, AI capture mode).
**Answers:** *Backend Endpoints for AI Item Identification* (your list of
13 October 2026), read against Cadra's code on 15 October 2026.
**Base URL:** as in your list, `https://<tenant>/api/v1`; every path below
is relative to it.

A few words used throughout:

- **Scope**: a permission carried in the sign-in token (`assets:read`,
  `assets:write`, `tagging:write`…). A person's scopes come from the roles
  their account holds. A route that needs a scope the token lacks answers
  `403`.
- **Envelope**: every answer is `{"data": …, "meta": {…}}`, with
  `"pagination": {"next_cursor", "previous_cursor", "total_estimate"}` on
  lists, or `{"error": {"code", "message", "request_id", "details"}}` on a
  refusal.
- **Candidate**: a unit that has been received but is not yet on the asset
  register. On a tenant where the *receipt gates* are switched on (today
  the demo tenant `staging`), a new item passes seven checks by different
  people before it is registered. Lists hide candidates unless you ask.
- **Release numbers** (61–66) are Cadra's build instructions, in order:
  **61** photos, the sync filter, room codes; **62** Cadra telling Vendra
  each receipt step; **63** the SAP copy and the matcher (built — §7);
  **64** AI identification on Cadra's server (§8); **65** Cadra's own
  register linked to SAP's records; **66** devices, code blocks and the
  audit capture. *(Renumbered twice: by release 63 on 18 October 2026 —
  the audit capture was "63" in the first edition — and by release 64 on
  19 October, after ruling R11: it is 66.)*

---

## 1 · Two corrections first

1. **There is no need for `GET /asset-classes/{id}/required-fields`.**
   `GET /asset-categories` already returns, for every class:
   - `identification_mode`: `serial`, `tag_id` (no manufacturer serial;
     identified by Cadra's code, e.g. furniture), `pool` (not built yet; a
     receipt of one is refused) or `record_only` (land, buildings, software:
     no label ever);
   - `class_attributes_schema`: `{"mandatory": [...]}`, always the schema in
     force for that class, never `null`;
   - `sap_asset_class`: SAP's four-digit class, or `null`.

   It is one unpaginated list (the taxonomy is small), scope `assets:read`.
   Cache it offline as you planned. (`myservice_api/controllers/v1_settings.py`,
   route `/api/v1/asset-categories`, GET.)

2. **Serial lookup is `GET /barcode/lookup?query=<scanned text>`, not
   `/assets/by-tag/{tag}`.** `by-tag` tries the tag number, then the asset
   code, and stops: it never tries the serial. `/barcode/lookup` tries tag
   number → asset code → serial number (the serial stripped and compared
   without regard to case), and says which one matched in `matched_by`
   (`tag_number`, `asset_code`, `serial_number`; from this release also
   `location`, see §5.6). A serial carried by more than one asset is a `404`
   with `details.ambiguous: true` and `details.matches: <how many>`, never a
   silent first pick. It finds candidates too. Scope `assets:read`.
   (`myservice_api/controllers/v1.py`, route `/api/v1/barcode/lookup`, GET.
   `/api/v1/tags/lookup` resolves the same way with a narrower payload that
   carries no ids.)

## 2 · Five rulings that change your design

These were agreed between WestMetro and the system owner on 15 October 2026.

**R1. An audit capture finds an existing SAP asset; it does not create one.**
SAP already holds NRS's register: 161,647 active assets in the October
export, 80,370 of them furniture and fittings. A chair the Lot 4 audit team
finds in a room is almost certainly one of them. So the Lot 4 flow is
**capture → match to the SAP record → tag → review**, not *register*.
The operator photographs the item, scans or types its old FIRS tag if it has
one, and picks from up to five SAP records Cadra proposes, or says *none of
these*. A second person on the audit team reviews each day's captures
before anything reaches the register. A capture that matches nothing goes to
a *found, not in SAP* list for the Asset Controller, never straight onto the
register. The receipt checks for new purchases do not apply, because nothing
was bought. The SAP copy and the matcher are in 63 (§7); the capture, the review
and the two exception lists come in 66.

**R2. Codes come from blocks the Asset Controller issues to a registered
device.** The phone may take the next code offline, from a block issued to
that device by the Asset Controller (not requested by the phone on its own
authority). Each code is *reserved*, then *active* (used by a confirmed
capture) or *void*. **"Return unused codes on sync" voids them: a code is
never handed out again, to any device.** (66.)

**R4. A named person signs in; a device never does.** The phone signs in
with `POST /auth/login` and the operator's own account (`{"login",
"password"}`). Every record says which person did it; no shared login, no
device credential. A device is a record bound to one person at a time (66),
not a way to sign in. What you should know about the login today:
- the access token lasts one hour; the answer also carries a refresh token
  that lasts 30 days, and `POST /auth/refresh` exchanges it for a new pair.
  A refresh token is single-use: replaying a spent one revokes the whole
  chain, so store the successor before using it;
- the person's scopes are in the answer's `scope`, derived from their roles.
  An account with no Cadra role signs in and is refused everywhere;
- **a tenant with Cloudflare Turnstile configured also requires a
  `turnstile_token` on `/auth/login`.** Our deployment notes record it as
  on for the hosted tenants. How a native app satisfies that is an open question for us both; raise it before
  you build the sign-in screen;
- some role pairs cannot be held by one person at all (for example the
  Store Officer and the Tag-Issuing Unit). The audit team's roles are set in
  66.

**R5. Condition: *Unserviceable* is recorded as `poor`, with the note
"unserviceable".** The published condition values are `new`, `good`,
`fair`, `poor`, `decommissioned`. *Unserviceable* (AI-FR-04) is not the same
thing as `decommissioned`, so there is no mapping and no new value for now.
Whether NRS wants a value of its own is put to NRS with their open
question 4 (should condition drive maintenance or disposal). Don't send a
value outside the five: it is refused.

**R7. Hosting: the current servers, for now.** AI-NFR-04 asks for photos,
signatures and training data to be hosted in Nigeria. The system owner has
ruled the current servers for now. That is a known deviation from AI-NFR-04,
it covers the whole system and not only photos, and **NRS must accept it in
writing before the first photo is stored on a production tenant.** Photos on
the demo tenants are not blocked by this.

## 3 · Your 24 endpoints, one status each

Your list has 24 rows: 6 "reuse as is" and 18 new. Three rows name two
paths (`/locations` with `/{id}/children`; `/mark-missing` with
`/mark-found`; the model manifest with its download); each is counted once,
as you wrote it.

| # | Your endpoint | Status | Use / what it will be |
|---|---|---|---|
| 1 | `GET /asset-categories` | **exists** | As is, and it replaces #16. §4.1 |
| 2 | `GET /locations` (+ `/{id}/children`) | **exists** | As is; rooms gain a scannable `location_code` in this release. §4.2 |
| 3 | `GET /assets/by-tag/{tag}` | **exists** | No serial step: use `GET /barcode/lookup?query=`. §4.3 |
| 4 | `POST /assets/{id}/tag-affixed` | **exists** | Scope `tagging:write`; offline `affixed_at` accepted. §4.4 |
| 5 | `POST /assets/{id}/verify` | **exists** | `notes` only, no photo; refused on a candidate from this release. §4.5 |
| 6 | `POST /assets/{id}/mark-missing`, `/mark-found` | **exists** | `reason` required; refused on a candidate from this release. §4.6 |
| 7 | `POST /devices` | **comes later (66)** | A device record bound to one person at a time; not a credential (R4). |
| 8 | `POST /devices/{id}/code-blocks` | **comes later (66)** | Blocks issued by the Asset Controller to a registered device (R2). |
| 9 | `GET /devices/{id}/code-blocks` | **comes later (66)** | Balance and state of a device's blocks: reserved / active / void. |
| 10 | `POST /devices/{id}/code-blocks/{block_id}/return` | **comes later (66)** | Specified as a **void** of the unused remainder, never a return to a pool (R2). |
| 11 | `GET /ai/config` | **comes later (66)** | The tenant's settings an offline phone needs, beside the label layout (#23): placed in 66 because the offline phone needs both. The capitalisation threshold has no value anywhere yet: it is NRS's open question 1. |
| 12 | `POST /ai-captures/photos` | **added in this release**, on an asset | Photos attach to an asset: `POST /assets/{id}/photos`. A photo held by a capture before it is matched comes with the capture in 66. §5.1 |
| 13 | `POST /ai-captures` | **comes later (66)** | The audit capture (R1): photos, AI suggestion against confirmed values, the chosen SAP record or *none*, the code used, the operator and the device. Replay-safe by a stored, unique `capture_id`, not by the 24-hour idempotency key. |
| 14 | `GET /ai-captures/{capture_id}` | **comes later (66)** | The capture's sync and review state. |
| 15 | `POST /ai-captures/{capture_id}/void` | **comes later (66)** | Voids an issued code with a reason, in the code ledger (R2). Today codes exist only on assets, so a code voided before any asset exists has nowhere to be recorded. |
| 16 | `GET /asset-classes/{id}/required-fields` | **redundant** | Use `GET /asset-categories` (§1). |
| 17 | `GET /ai/signatures?location_id=&since=` | **comes later (66)** | No signature storage exists yet. It comes with the capture and its review in 66, where the duplicate check inside a room happens. |
| 18 | `GET /assets?location_id=&updated_since=` | **added in this release** | `location_id` exists; `updated_since` is added. §5.5 |
| 19 | `GET /assets/{id}/photos` | **added in this release** | Photos and Internal Audit's evidence in one list. §5.2 |
| 20 | `POST /ai/lost-tag-requests` | **redundant** | Use the existing tag replacement, which from this release reprints under the same code. §5.7 |
| 21 | `POST /assets/{id}/swap-flags` | **comes later (after 66)** | A swap flag belongs to an audit campaign — a record of an audit in progress that a flag is raised in and reviewed against — and no release has built one yet. Placed after 66; the nearest existing record is the refused-affix event. |
| 22 | `GET /ai-captures/flags?since=` | **comes later (66)** | A second capture matching an SAP record already accepted is held for review with both photos side by side. |
| 23 | `GET /barcode/label-template` | **comes later (66)** | The label layout as data, beside `/ai/config` (#11): an offline phone needs both. Until 66, print to the rules in §6. |
| 24 | `GET /ai/models/manifest` + file download | **not needed: Cadra identifies the photo (R11)** | No model is trained, packaged or downloaded. The phone sends the photo to `POST /api/v1/ai/identify` (§8), the same route the web app calls; Cadra's server asks a vision model and returns suggestions a person confirms. Offline, the photo is identified when it syncs. |

Totals: **exists 6 · added in 61 3 · comes later 12 (11 in 66, 1 after 66)
· redundant 2 · not needed (R11) 1** = 24. *Release numbers corrected by
handoff 64: the audit-capture path the "comes later" rows wait for is now
66; 64 is AI identification (§8) and 65 the link to SAP's records.* The sixth status of the first
edition, *not yet scheduled*, is gone: every row now has a release (Cadra's
release 63 placed the last four). The SAP copy and the matcher your step 4
calls are built (§7) — they were never one of your 24 rows.

## 4 · What exists, and how it differs from your list

Each route below is cited as registered in `myservice_api/controllers/`.

### 4.1 `GET /asset-categories`
`v1_settings.py`, `/api/v1/asset-categories`, GET, scope `assets:read`.
Per class: `id`, `name`, `code`, `domain`, `description`, `identification_mode`,
`class_attributes_schema`, `sap_asset_class`, depreciation policy and counts.
Not paginated. **Changing in this release:** the default schema of a `tag_id`
class becomes `name`, `colour`, `material`, `dimensions`; `make` and
`model_name` are no longer mandatory by default, so a chair with no visible
brand can be recorded. A class whose schema was customised keeps it. Read the
schema from this route; don't hard-code it.

### 4.2 `GET /locations` and `GET /locations/{id}/children`
`v1_locations.py`, `/api/v1/locations` and
`/api/v1/locations/<int:id>/children`, GET, scope `locations:read`.
- `/locations` is filtered (`q`, `type_id`, `parent_id`, `state_id`,
  `location_type`, `active`, `has_coordinates`…) and cursor-paginated.
- `/children` returns the direct children as **a plain array, not
  paginated**.
- Each location carries `parent_id` and `parent_path` (the id chain,
  e.g. `"1/4/12/"`), so you can rebuild the tree offline from one walk of
  `/locations`.
- **Until this release no location has anything to scan.** From this
  release each carries a `location_code`: §5.6.

### 4.3 `GET /assets/by-tag/{tag}`
`v1_assets.py`, `/api/v1/assets/by-tag/<string:tag>`, GET, scope
`assets:read`. Exact tag number, then exact asset code. **No serial
step.** It finds candidates. For anything scanned in the field use
`GET /barcode/lookup?query=` (§1, item 2); `by-tag` remains for callers that
want the full asset record by its label.

### 4.4 `POST /assets/{id}/tag-affixed`
`v1_assets.py`, `/api/v1/assets/<int:id>/tag-affixed`, POST, scope
**`tagging:write`** (the Tag-Issuing Unit; not `assets:write`). Idempotent
with `X-Idempotency-Key`.
- Body: `tag_number` (**required**: the number read off the physical label),
  `serial_number` (optional; checked against the record when sent),
  `scanned_format` / `serial_format` (the symbology, e.g. `qr_code`,
  `code_128`; recorded only when the check fails), `attributes_confirmed`
  (**required `true`** for a `tag_id` unit on its first affix),
  `affixed_by_name`, `affixed_at`.
- **Offline:** `affixed_at` may be in the past; a time in the future is
  refused.
- A wrong number is refused, and the refusal is kept as an event nobody can
  alter. The check compares the scanned value with the code exactly, which is
  why §6 says what the label must encode.
- With the receipt gates on, a freshly received unit has no label yet and the
  affix is refused (*"This asset has no active tag to confirm"*) until its tag
  has been requested and issued.

### 4.5 `POST /assets/{id}/verify`
`v1_assets.py`, `/api/v1/assets/<int:id>/verify`, POST, scope
`assets:write`, idempotent. Body: `notes` only. It records who verified and
when. **No photo is accepted here**: AI-FR-12's photo goes to
`POST /assets/{id}/photos` (§5.1). **From this release** it is refused on a
candidate with `409 not_on_the_register`: a unit not yet on the register
cannot be verified on it.

### 4.6 `POST /assets/{id}/mark-missing` and `/mark-found`
`v1_assets.py`, `/api/v1/assets/<int:id>/mark-missing` and
`/api/v1/assets/<int:id>/mark-found`, POST, scope `assets:write`,
idempotent. **`reason` is required on both.** Each answers `409` when the
asset is in the wrong state (already missing; not missing). **From this
release** both are refused on a candidate with `409 not_on_the_register`.
They are not a lost-*tag* flow: they say the *asset* is missing or found.
For a lost or faded tag, see §5.7.

## 5 · Added in this release

Checked against the finished build of release 61 and driven by its test
suite on 15 October 2026.

### 5.1 `POST /assets/{id}/photos`
- **Multipart** form, inside the normal envelope. Parts: `file` (required),
  `caption` (optional), `source` (required: `web` or `mobile`).
- **JPEG or PNG only, judged by the file's bytes, not its name or declared
  type**: a PDF renamed `.jpg` is refused.
- **At most 300 KB per photo** (AI-NFR-07: compress on the device before
  sync). Larger is refused, not resized.
- **At most 12 current photos per asset.**
- Scope `assets:write`. A received unit not yet on the register may have
  photos: a photo is evidence before registration.
- Recorded with who, when, the caption, the image's dimensions and `source`.
  Answers `201` with the photo's item (the shape in §5.2).
- **Refusals**, each in words, and nothing is written: `413` over 300 KB
  (307,200 bytes); `415` not a JPEG or a PNG (`details.detected` says what it
  is); `400` a damaged or truncated image, an empty file, more than 50
  megapixels, a missing or unknown `source`, a part the route does not take
  (`details.writable` lists the three), or not a multipart body; `409` the
  asset already has 12 current photos.
- `X-Idempotency-Key` works as on every write: a retry with the same key
  stores one photo. Keep your own `capture_id` for the five-day offline
  window; the key lasts 24 hours.

### 5.2 `GET /assets/{id}/photos`
- One list answering *"what pictures does this asset have"*: the photos,
  and Internal Audit's evidence from its value-for-money check on receipt,
  **each item labelled `photo` or `iad_evidence`**.
- Internal Audit's evidence is its working papers. **A caller without the
  `evidence:read` scope sees only how many evidence items there are**
  (*"IAD evidence: N items"*), not the items. A field operator will normally
  be in that position.
- Scope `assets:read`. The answer:
  `{"asset_id", "items": [...], "photos": {"count", "standing",
  "superseded", "max_standing": 12, "max_bytes": 307200, "allowed_types"},
  "iad_evidence": {"readable", "count", …}}`, newest first. Each item:
  `kind` (`photo` | `iad_evidence`), `id` (photo ids and evidence ids are
  separate sequences, so the key is `kind` + `id`), `source` (`web` |
  `mobile` | `gate_evidence`), `caption`, `filename`, `mimetype`, `size`,
  `width`, `height`, `sha256`, `uploaded_by`, `uploaded_at`, `superseded`
  (`null`, or who, when and why), and `url` (where its bytes are).

### 5.3 `GET /assets/{id}/photos/{photo_id}`
The image bytes, with their content type (not the JSON envelope), an
`ETag` that is the SHA-256, and `Cache-Control: private, immutable`: a
photo never changes. Scope `assets:read`. A photo of another asset is a
`404`.

### 5.4 `POST /assets/{id}/photos/{photo_id}/supersede`
**A photo is never deleted or replaced.** It can be *superseded*, with a
reason; the record says who did it and when, and the superseded photo stays
in the history. Body `{"reason": "…"}`, required. Scope `assets:write`. A
superseded photo stops counting towards the 12. A second supersede of the
same photo is a `409` naming who did the first and when.

### 5.5 `GET /assets?updated_since=<ISO-8601>`
- A sync filter on the existing list (`v1_assets.py`, `/api/v1/assets`,
  GET, scope `assets:read`): the assets changed at or after that instant.
- A value that cannot be read as an ISO-8601 date-time is refused (`400
  invalid_request`), never ignored.
- It combines with `location_id` and with `register_state=any` (which also
  shows candidates, and needs `candidates:read`).
- Order and paging are unchanged: ascending asset id, with `cursor`. A
  token from `/auth/login` may ask up to 2,000 rows a page (`limit`; default
  50) and is not subject to the 100-record ceiling that service credentials
  have.

#### Paging a sync without missing a row

The list is ordered and paged by asset id, ascending, with a cursor. A row
can change while you are paging: if its id is behind your cursor, this pass
has already read it and will not read it again. **No new cursor is needed to
catch it; one rule is:**

1. Start a sync by asking for page 1 with `updated_since=<the start of your
   last sync>`.
2. **Remember page 1's `meta.timestamp`**, the server's clock at the moment it
   answered. Do not use your phone's clock, and do not use the largest
   `updated_at` you saw.
3. Follow `pagination.next_cursor` until it is null. Upsert every row by its
   `id`.
4. Your next sync starts from the `meta.timestamp` you remembered in step 2,
   minus a safety margin of a few minutes. That covers a write that began
   before the timestamp and finished after it.

A row changed during the pass therefore comes back in the next sync. The
filter is `>=`, so a row may come back twice, which an upsert by id makes
harmless. This is driven end to end in Cadra's test suite
(`tests/test_the_same_code_and_the_photo.py`,
`test_a_sync_across_two_pages_catches_a_row_changed_mid_sync`).

**Three things to know:**

- **`updated_since` reads the asset's own record** (`updated_at`). A new
  photo, a new custody row or a tag affix is a change to another record, so
  it does not move `updated_at`. To see photos, read
  `GET /assets/{id}/photos` for the assets you hold.
- **Hidden units stay hidden.** A unit that is still being received is left
  out unless you ask for `register_state=any`, which needs the
  `candidates:read` scope.
- **A person's sign-in is not record-capped.** A token from `/auth/login` may
  page through the whole register, up to 2,000 rows a page. A machine
  credential (`/auth/token`) is capped, and `_warnings.truncated` says when
  the cap was hit.

### 5.6 `location_code` on every location
- Every location carries a `location_code`, unique within the tenant,
  generated from the location hierarchy when nobody has set one, and
  editable by `locations:write`. Published on `GET /locations`.
- **A room label carries the code verbatim**, as QR and Code 128, printed
  from the barcode station at the medium and large sizes. Scan its QR: the
  medium label's Code 128 does not read by camera (§6).
- **Format:** `LOC-` followed by the zone codes of the location and its
  parents (e.g. `LOC-HQ-F10-OFCN`), or by the location's id where they have
  none (`LOC-1133`). Letters, digits and hyphens only; it never changes
  once set, so a printed room label keeps scanning.
- **Scanning it at `GET /barcode/lookup?query=` answers
  `matched_by: "location"`**, with `matched_location` (`id`, `name`,
  `location_code`, `path`, `location_type`, `parent_id`, `asset_count`) and
  no asset: *this is a room*, never *not found*. That is the room context
  AI-FR-10 asks for: scan the door, then the items. A tag, an asset code
  and a serial resolve before a room code, exactly as they did.
- **The room label** is `GET /locations/{id}/label?size=medium|large`
  (`locations:read`), a PDF; `small` is refused.

### 5.7 A tag replacement reprints under the same code
For a lost or faded label, use the existing replacement, not a new route:

- `POST /tags/{id}/request-replacement` (`v1_tags.py`,
  `/api/v1/tags/<int:id>/request-replacement`, scope `tagging:write`):
  `reason` and `approver_id` required;
- `POST /tags/{id}/approve-replacement` / `reject-replacement`
  (`/api/v1/tags/<int:id>/approve-replacement`,
  `/api/v1/tags/<int:id>/reject-replacement`, scope `approvals:write`).
  The approver is an Asset Manager, and never the person who asked;
- `GET /tags/replacements` lists them, decided ones included.

**Behaviour change in this release:** an approved replacement **reprints the
same number** instead of minting a new one. The label record counts its
reprints, the old print is voided with its reason, and the history says
which print is current. Note what this means on the item: an old print and
its reprint encode the same value, so they **cannot be told apart by
scanning**. Cadra can refuse the old print in one window only: while the
reprint has not been printed, a scan of that number can only be the voided
label, and the affix is refused naming the void and its date. **So report
every print you make**: `POST /tags/printed` with `{"tag_ids": [...]}`
(`tagging:write`) — a reprint is refused at affix until its print is
recorded. Each label (each print) has its own `label_id`; key on that, not
on the number. A
reprint count printed beside the code (e.g. `·R1`) would let a person tell
them apart by eye. It must never be inside the encoded value.

The approver differs from your list: the addendum asks for the custodian
and/or supervisor. That is NRS's open question 5 and is not added now.

## 6 · What your printed label must carry

1. **The asset code, verbatim, as the encoded value.** No URL, no prefix,
   no suffix, no AI-predicted value. Cadra's affix check compares the
   scanned string with the code character for character; a QR that encodes
   `https://…/NRS-AST-000123` instead of the code fails every affix.
   Anything else you print (a reprint mark, a room name) goes beside the
   symbol, outside the encoded value.
2. **QR first.** It is the side every phone camera reads.
3. **No Code 128 at the small size, nor at the medium one.** Measured on
   Cadra's own labels through the same decoder the app uses (408 offline
   decodes, 24 conditions per symbol: angles, blur, low contrast, torn): the
   Code 128 on the **small** label (28.6 mm wide, about 5 mil a bar) read
   **0 of 24**, and on the **medium** label (25.0 mm wide) **0 of 24**. The
   large label's Code 128 (49.0 mm) read 9 of 24. The QR read 9 of 24 on the
   small label, 11 of 24 on the medium and 18 of 24 on the large, and read
   at its printed scale on every size. At small and medium sizes a Code
   128 serves only handheld laser scanners, and 5 mil is at their floor too.
   (Cadra's sizes: small 50×25 mm, medium 50×30 mm, large 100×60 mm.)
4. **Prints made offline must be reported on sync.** Cadra records every
   label it prints; a phone printing offline goes round that record unless
   the capture says what it printed (66).

## 7 · Added in release 63: SAP's register, and which record an item is

Release 63 (18 October 2026) loaded SAP's asset master into Cadra as a
**read-only copy** — not the asset register — and built the matcher your
step 4 calls. Both need the scope `sap_mirror:read`, which the audit
team's roles will carry (66); today the Asset Controller, the Register
Maker and Checker and the Auditor hold it. An operator who is only an Asset
User is refused, `403`.

### 7.1 `GET /sap-assets?office=<code>&class=<class>&updated_since=` — the slice to cache

A page of SAP's records for one office (and class), the same paging and
sync rules as `GET /assets` (§5.5): `limit` up to the page ceiling,
`next_cursor`, and the next sync from the FIRST page's `meta.timestamp`.
A record SAP dropped from its latest export comes back with
`in_latest_export: false` — keep it, never offer it. `active: false` is a
record SAP retired; never offer it either.

**Records with no office.** SAP's export carries no location: the office is
read from a `FIRS/<office>/…` old tag, and an untagged record has none.
`office=none` pages those (37,831 active records on the October import).
NRS has been asked for SAP's location extract; when a later import brings
it, those records gain an office and come back through `updated_since`.

The size of the largest office's furniture slice is measured in release
63's report (rows and bytes), so the phone's cache can be sized.

### 7.2 `GET /sap-assets/match` — the five candidates

`old_tag`, `description`, `class`, `office`, `serial` — any of them. Up to
five active records **not already on Cadra's register**, ranked by: the
exact old tag; among records sharing it, the description; then (when no
record carries the tag) an exact serial; then class and description within
the office (the one given, or the one inside the tag), nationwide only when
no office is known. Each answer has a `reason` to show the operator —
*old tag, unique*; *old tag, shared by 7; description matches*;
*description and class; office unknown* — and the answer says how many
records were passed over because they are already on Cadra's register
(*3 more already on Cadra's register*). A placeholder serial (`XXXX`, `0`)
is never matched, and the answer says so. Offline, run the same rules over
the cached slice; the order and the reasons are the ones above.


## 8 · Added in release 64: Cadra identifies the photo (R11)

There is no model to train, package or download. The phone sends the photo
to Cadra, Cadra's server asks a vision model, and the answer comes back as
suggestions a person confirms — the same route the web app calls. Full
contract: `docs/api/cadra_api_endpoint_reference.md` §17.

### 8.1 `POST /api/v1/ai/identify` — `assets:write`

**multipart/form-data**, exactly one of:

- `photo_id` — a photo already on an asset (§5.1); or
- `file` + `source=mobile` — a photo for an item not yet registered. Cadra
  holds it 24 hours; the save that registers the item claims it as the
  asset's first photo.

Send `X-Idempotency-Key`: a re-send after a dropped connection gets the same
answer and is not counted twice. **Offline:** queue the photo and identify it
when the phone syncs; until then the person picks the class themselves. They
confirm the suggestion anyway, so nothing depends on the AI being reachable.

The answer: `suggestion_id`; `category` (one of the tenant's classes, its
`confidence`, up to two `alternatives`); `attributes` (`name` in SAP's style,
`colour`, `material`, `make` and `model_name` only if legible, `dimensions`
only if a label states them); `condition` (the published enum —
*unserviceable* is `poor` with the note `unserviceable`); `text_read` (each
string with `looks_like`: `brand`, `model`, `serial_like`, `firs_tag_like`,
`other`); `sap_candidates` (up to five with their ranking reason for a caller
holding `sap_mirror:read`, otherwise the count); `notes`; `notice`.

Refused in words, nothing identified: `403` switched off on the tenant;
`429` the day's cap used (*"fill the details by hand"*); `503` the provider
timed out or failed, `502` its answer failed the schema (*"The photo could
not be identified just now; fill the details by hand."*); the photo's own
`413`/`415`/`400`.

### 8.2 Saving what the person confirmed

`POST /api/v1/assets` (or `PATCH /api/v1/assets/<id>`) with the fields the
person kept or typed, plus `ai_suggestion: {"id": <suggestion_id>, "ignored":
[fields the person dismissed]}`. Cadra records per field accepted, changed
(from → to) or ignored — AI-NFR-05's audit trail — and the history shows it
in one line. A field is never written from a suggestion the save did not
send. An SAP candidate fills nothing: the SAP number is set at registration
by the Register Maker, or by SAP.

### 8.3 Whether to draw the button

`GET /api/v1/settings` → `ai_identify.enabled`. Off — the default on every
tenant — draw nothing. `ai_identify.notice` is the sentence to show once:
*"Photograph the item, not people. The photo is sent to <provider> to read
it."*
