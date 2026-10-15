# Report — Handoff 61: the same code, and the photo

Branch `feat/the-same-code-and-the-photo`, from `dev` at `a496193` (PR #119
merged). Step 0: the instruction file, the evaluation
(`docs/AI-CAPTURE-EVALUATION.md`), my findings file, the two addendum PDFs
and the Architect's edit to `docs/ADDENDUM-A-EVALUATION.md` (Pool to Phase
E, R6) committed on `dev` as ONE docs commit (`6c3dd12`), pushed, then the
branch. Module versions: `myservice_asset_register` 19.0.1.30.0,
`myservice_api` 19.0.3.33.0.

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
2. **The deploy.** Run `deploy-dev`, then `upgrade-19` on all four cluster
   tenants (`staging, gtb, jaizbankplc, lasg`) with modules
   `myservice_asset_register,myservice_api`, `scale_down=true`, before any
   traffic. There is a new model (`nrs.asset.photo`), new columns
   (`generic_location.location_code`, `nrs_asset_tag_label.reprint_count`,
   `voided_date`, `void_reason`, `nrs_asset_event.photo_id`) and a
   migration that gives every location its room code; it logs one line per
   tenant (*"location_code filled on N of M …"*). Then
   `https://<tenant>/api/v1/meta/readiness` must say `"ready": true`.
3. **Hosting (R7) — NRS's written acceptance before the first production
   photo.** GO-LIVE §30.1. Nothing in the repository names the region the
   demo cluster runs in (searched, §9); the DigitalOcean console says, or a
   one-line step in a workflow (`doctl kubernetes cluster get
   "$DO_CLUSTER_NAME" --format Region`) — a workflow change, so yours.
4. **The deployed check on `staging`**, after the deploy (Turnstile — in
   the browser):
   1. Sign in as the **Store Officer** persona; open any received unit that
      IAD has verified. The panel reads *"IAD evidence: 1 item"* and opens
      nothing. Sign in as the **IAD approver**: the same unit shows the
      files.
   2. As the Store Officer, open an asset → *Photos* → *Add photo* → pick a
      phone picture. It is shown, labelled *Photo*; *Supersede* asks for a
      reason and marks it.
   3. Open *Locations* → any location: the *Room code* card shows `LOC-…`.
      *Print room label* (medium or large) opens a PDF. Type the code into
      the barcode station's scan box: *This is a room: <name>*.

## In plain words

This is the first of three pieces of work for the AI item identification
addendum — the phone app that photographs a chair and tags it. It builds
only what is right whichever way the later two go, and fixes three things
the findings turned up.

- **A faded tag keeps its number.** Until now, replacing a label gave the
  asset a new tag number — and on a unit received through the approval
  chain, a number in the wrong format altogether. Now the label is
  reprinted with the same number. Cadra records that it is a reprint (1,
  2…) and why the old label was voided. Because the old and new labels
  carry the same number, no scanner can tell them apart; Cadra can catch
  only one case — someone scanning the old label before the new one has
  been printed — and to do that it needs to know when a label is printed.
  The app had never told it (1 print recorded out of 3,069 labels fixed to
  assets), so the app now reports every print it makes.
- **Internal Audit's papers are Internal Audit's.** The delivery notes,
  invoices and photographs IAD attaches when it checks a delivery are now
  read only by IAD, the two people who register the asset, and the
  auditor. Everybody else — the storekeeper, Vendra — is told how many
  there are, and nothing more.
- **Two more "select many and act" buttons**: the storekeeper's *Submit
  selected* and the Asset Controller's *Request tagging for selected*.
  Each still acts on every unit separately, as before.
- **The categories screen loads in a third of a second** instead of three.
- **A unit not yet on the register cannot be verified, or marked missing or
  found** — it is not on the register, so it cannot be missing from it.
- **A chair with no brand can be recorded**: furniture no longer needs a
  make and model by default.
- **Photos on an asset.** Anyone who may edit an asset can add a photo (up
  to 300 KB, JPEG or PNG — the addendum's own limit; the web app shrinks a
  picture to fit). A photo is never deleted; if it is wrong it is marked
  *superseded*, with a reason and who did it. The asset's photo list also
  shows IAD's evidence, to those allowed to see it.
- **A sync filter** for the phone: *give me what changed since…*, and how
  to use it without missing a row.
- **Every room has a code** (`LOC-…`) — all 4,869 locations on the eight
  local databases, no two the same. The station prints a room label, and
  scanning one says *this is a room*, not *not found*.
- **A map for the mobile team** of their 24 endpoints: which exist (and
  where they differ), which arrived in this release, which come later,
  which are not needed, and which are not Cadra's.

**What did not change:** no asset's code, serial, class or SAP number was
rewritten; the no-two-gates rule, the role exclusions and 60's batch rules
are untouched; nothing issues a code from a device, creates an asset from a
capture or touches a SAP mirror — those are 62 and 63.

## Step 0

| | |
|---|---|
| `6c3dd12` (on `dev`) | `docs: handoff 61 — the same code, and the photo; the AI addendum, its findings and the evaluation` — the instruction file, `docs/AI-CAPTURE-EVALUATION.md`, `docs/reference/ai-item-identification-builder-findings-2026-10-15.md`, the two PDFs, and the Architect's `ADDENDUM-A-EVALUATION.md` edit, one commit as asked |

The work was split by file across four agents (the reprint; photos; room
codes; the mobile map, §12 and §9's region) with the evidence scope, the
batches, §2, §3, §6, the category counts, the manifests, the migration
version, the fan-out, the suites and the docs in the main session; the
three building agents ran nothing against the stack, every upgrade and
suite ran serially here.

---

## §0b · Report 60's rulings, built

### Ruling 1 — who reads IAD's evidence

**Scope `evidence:read`** (`myservice_api/controllers/utils.py`). Held, in
`GROUP_SCOPES`, by exactly: IAD VfM officer, IAD VfM approver, Register
Maker, Register Checker, Auditor. Not by Asset User (and so not by any role
that implies it alone), not by Vendra's credential (`assets:read
assets:write candidates:read`). `SCOPE_GROUPS` maps it to the Auditor — the
one read-only role among the five — so a credential granted it is never put
in a gate role and never inherits that role's exclusions. It ends `:read`,
so the Auditor-is-read-only pin holds.

**One guard**, `utils.evidence_readable()`, and one answer for everybody
else, `utils.evidence_count_only(n)`:

| Where evidence is served | Reader | Anybody else |
|---|---|---|
| `GET /assets/<id>/evidence` | `readable: true`, `count`, the verifications | `readable: false`, `count`, `summary: "IAD evidence: N items"`, `requires_scope`, `verifications: []` |
| `GET /assets/<id>/evidence/<file>` | the file | `403` naming `evidence:read` |
| `GET /assets/<id>/photos` (§5) | the evidence items, labelled `iad_evidence` | `iad_evidence: {readable: false, count, summary}` and no items |
| `GET /assets/<id>/history`, a `verify` gate event | `detail.evidence` as before | `detail.evidence = {"attachments": <the count block>}` — checklist and notes withheld too (the verification pass, F1) |

The app's panel says *"IAD evidence: N items"* for a non-reader.

**Driven** — HTTP, `tests/test_the_same_code_and_the_photo.py::
test_iads_evidence_is_read_by_its_five_readers_and_counted_for_the_rest`,
gates on, one unit walked to `vfm_verified`: the **Store Officer** gets the
count and a 403 on the file and the count-only history; **each of the five
readers** (IAD officer, IAD approver, maker, checker, auditor) gets the
verification and the file, byte for byte. **Vendra's credential**: its
secret is not on this machine, so a credential with Vendra's exact scopes
is minted in-registry
(`myservice_api/tests/test_the_same_code_and_the_photo.py::
TestEvidenceScope`): count only, file 403, history without the papers; a
reader credential is served. The scope table is pinned there to the five.

### Ruling 2 — the four gates-off changes: accepted, nothing to build.

### Ruling 5 — *Submit selected* and *Request tagging for selected*

`POST /api/v1/candidates/gates/submit` (`assets:write`) and
`/request-tagging` (`tagging:request`), through 60's `_simple_batch`: one
`_fire_gate` per unit, each in its own savepoint inside one outer
savepoint, `dry_run` by rolling the outer one back, per-unit lines with the
single route's status and sentence. No single-receipt check for these two
(a selection may mix receipts). The tag request stays the Asset
Controller's act — nothing fires it.

**Driven** (`tests/test_the_same_code_and_the_photo.py`): three units on
three GRNs, one already submitted → dry run *would_fire, would_fire,
refused*, nothing moved; real run 2 fired, 1 refused with the single route's
409 and sentence (compared by firing it alone); one `submit` event per unit.
Request tagging: the storekeeper refused 403 at the door; the controller's
dry run 2 + 1, then 2 fired, each unit `tag_issued` with its label number =
its asset code, the captured third refused 409. In the browser, spec 60 now
drives both batches as the store and the controller instead of 20 API calls
each (`e2e/tests/60-seventy-a-day.spec.ts`).

### Ruling 6 — `GET /asset-categories`

`asset_count` and `asset_depreciating_count` were one `search_count` per
category: 320 queries for `test19`'s 160 categories. Now one `_read_group`
per count over the recordset (through `nrs.asset._search`, so the register's
candidate filter applies exactly as before). In-registry: the query count
is the same for 2 categories and for 20.

| `test19`, 160 categories, 5 calls | seconds |
|---|---|
| before | 8.00 (cold), 2.76, 3.08, 4.10, 4.23 |
| after, warm | 0.52, 0.42, 0.32, 0.42, 0.27 |

(`docs/handoffs/61-evidence/asset-categories-timing.txt`; the first run
after the restart is there too — 0.43, 4.03, 1.52, 0.20, 0.15 while workers
warmed.)

### Ruling 7 — recorded in `docs/ENVIRONMENT-FACTS.md` ("`test19` sends
INT-05 … on local test tenants only"), with *do not copy this to a cluster
tenant* and why.

## §1 · A replacement keeps the code (R3)

**Design** — one `nrs.asset.tag.label` row is one physical print.
- New: `reprint_count` (0 for a first print), and on the VOIDED row
  `voided_date` and `void_reason` (a stamp taking `replacement_reason`'s
  values, because `replacement_reason` stays editable on the form). The
  void sits on the voided row because it is a fact about that print, and
  the refusal of that print names it; the reprint reaches it through
  `replaces_id`.
- `action_approve_replacement`: the old row is written `scrapped` (state
  and `label_state` — no new enum values) with its void stamped, THEN the
  reprint is created: same `name`, `replaces_id`, `source` copied,
  `reprint_count` + 1. `_check_unique_active` holds because the void is
  written first. `asset_tag`/`active_tag_number` do not change.
- `_generate_tag` is no longer called on approval, gates on or off — which
  removes findings §5.6 (on a gated unit the replacement minted a
  location-prefix label instead of the asset code). A location-prefix
  label keeps its own number too.
- The comment in `_generate_tag` ("reissuing … two different physical
  labels sharing one code") now says what answers it: the print count and
  the void, recorded on each row. `_generate_tag` still never reissues a
  number for a NEW label.
- The stamps are refused on `write` and `create` without the approval's
  context. A number active on TWO assets is refused a reprint (it would be
  the other asset's label too) — **84 such numbers exist today** (68
  `test19`, 15 `jaizbankplc`, 1 `nrs19`: `NRS-FURN-001`), so
  `_check_unique_active`'s promise does not hold in today's data; cause not
  established (candidates: the Jaiz seed's SQL re-brand of tag prefixes,
  concurrent mints). A partial unique index is the fix once they are
  cleared — for the Architect.
- **Approver unchanged**: an Asset Manager, never the requester.
- The station's *Generate* no longer lists or mints for an asset whose
  label is pending replacement (`physical_tag_id`, not `active_tag_id`) —
  §5.6 by another door, found by the reprint agent.

**Telling a voided print from its reprint — measured.** They encode the
same value, so no scanner can tell them apart, and the handoff's *"scanning
a voided print's label is refused"* can hold in one window only: **while
the reprint has not been printed**, a matching scan can only be the voided
label. `_mark_affixed` refuses then (`voided_print`, recorded as
`affix_refused` before the refusal):

> *"Tag X is reprint 1 and has not been printed yet, so the label being
> scanned can only be the original print, voided on 2026-10-15 (Damaged /
> Unreadable). Print reprint 1, then confirm it."*

and the scrapped-label refusal names the void and its date. That needs
prints to be RECORDED, and **the app never recorded one**: it draws labels
in the browser and never reaches the PDF funnel — 1 of 3,069 affixed labels
on the 8 tenants had a `printed_date`, 0 of 2,421 on `test19`. Without a
record every reprint confirmed from the app would have been refused. Hence
the deviation below: `POST /api/v1/tags/printed`.

**`·R1`.** Printed beside the code (outside the encoded value — handoff 55
§3) it would add human legibility only: a person holding two labels could
see which print is current. **Not built**: four of the app's five print
paths carry no count in their payloads, and marking some reprints and not
others would make an unmarked reprint read as an original. The exact
template change is in the reprint agent's notes, for when it is wanted.

**Driven**: `tests/test_reprint_same_code.py` (14 HTTP), in-registry
`myservice_api/tests/test_reprint_same_code.py` (14) — a gates-off
location-prefix label and a gated unit's asset-code label each reprinted
under its own number with the count and the void in the history; the
voided-print refusal and its event; a printed reprint affixed; first prints
unchanged; self-approval still refused; the stamps unforgeable; reprint 2.
`tests/test_tag_replacement.py` and `myservice_asset_register`'s
replacement tests had asserted a new number — reversed, announced.

## §2 · Not on the register, so not missing from it (R10)

`_assert_on_the_register` (under every ORM writer) now refuses, on a unit
not on the register, a change of `state` and a `last_verified_date`, beside
58's custodian, move and disposal; `verify`, `mark-missing`, `mark-found`
and `condemn` ask first (`_on_the_register_or_409`), so a candidate is told
what it is rather than *"not missing"*. A gated receipt may not ARRIVE
missing, in repair or verified either (the verification pass, F2 — the
create door was open: 24 `missing` and 8 `in_repair` candidates are on
`test19`, all fixtures from before).

> *"This unit is not on the register yet (waiting on <who>); it cannot be
> missing from a register it is not on yet."* — 409 `conflict`,
> `details.reason = "not_on_the_register"`.

**The `assets:write` routes checked** (an AST census of every
`cadra_route`):

| Route | On a candidate |
|---|---|
| `GET /approvals/approvers` | a read — nothing to refuse |
| `POST /approvals/<id>/withdraw`, `/renominate` | a change request cannot exist on a candidate (its `create` refused since 58) |
| `POST /assets` | creation; a gated receipt arriving missing / in repair / verified now refused |
| `PATCH /assets/<id>` | receipt corrections allowed; custodian, location (58), `state`, `last_verified_date` (61), disposal (58) refused |
| `POST /assets/<id>/move`, `/transfer-custody` | refused (58) |
| `POST /assets/<id>/verify`, `/mark-missing`, `/mark-found` | **refused (61)** |
| `POST /assets/<id>/condemn` | refused (58, disposal) — now asked first |
| `POST /assets/<id>/gates/submit`, `/resubmit`, `/candidates/gates/submit` | the candidate's own path |
| `POST /assets/<id>/photos` | allowed (§5: a received unit's photo is evidence) |

Nothing in the gate chain writes `state` or `last_verified_date` (checked
by the verification pass), so the chain is unaffected — both suites ran
green with the switch on. Driven: `tests/test_the_same_code_and_the_photo.py`
(each route and two PATCHes refused, nothing written; a registered asset
still verified and marked missing) and `TestCandidateNotOnTheRegister`.

## §3 · A chair with no brand (R9)

**Measured first** (`ir` read on `nrs_asset_category`, every local tenant):

| Tenant | `tag_id` classes on the default | customised |
|---|---|---|
| cadra19 | 2 | 0 |
| nrs19 | 1 | 0 |
| gtb19 | 2 | 0 |
| test19 | 1 | 0 |
| nrs | 2 | 0 |
| lasg | 1 | 0 |
| gtb | 2 | 0 |
| jaizbankplc | 2 | 0 |
| **all** | **13 of 13** | **0 of 13** |

`DEFAULT_MANDATORY['tag_id']` is now `name, colour, material, dimensions`;
the app's mirror of the default too. No stored schema is touched. Driven: a
chair with no make received on `test19` with the gates on (`201`,
`captured`, `tag_id`); in-registry, a customised schema naming `make` still
refuses a chair without one. CHANGELOG names Vendra: its own make/model
question is its rule and stays.

## §4 · When a code is born (R2a)

`docs/DECISIONS.md` (2026-10-15): D1 reads *assigned at capture or
creation, printed at tagging, active at registration, never reused*; the
built behaviour is the ruling; 63's ledger records receipt codes too.
`docs/reference/addendum-a-verification-gated-receipt.md`: one appended
note, NRS's text untouched.

## §5 · Photos on an asset

**Caps, from AI-NFR-07** — *"Photos are compressed to a maximum of 300 KB
each on the device before sync"* — which gives a size and no count: **300
KB (307,200 bytes)** per photo, refused `413`; **12 standing per asset**
(the handoff's fallback, said so), counting photos not superseded — nothing
is ever deleted, so a superseded photo frees its slot; refused `409`. JPEG
and PNG judged by **sniffing** (magic number, then Pillow must open it as
that format), `415` otherwise whatever the name; a 50-megapixel header
ceiling added so a tiny file cannot declare a huge picture.

**The model** `nrs.asset.photo`: the append-only mixin (the fifth thing that
pins an asset), `asset_id` restrict, the bytes `Binary(attachment=True)`
written with `image_no_postprocess` (without it Odoo re-encodes any image
over 1920 px and the photo comes back as different bytes — the same flag
is now on IAD's evidence store, which had the same latent defect), SHA-256
stored and re-checked on every read, uploader from the acting user.
**Superseding** is an `nrs.asset.event` `photo_superseded` (`photo_id`,
`reason`, the actor); the photo row is never touched. `source` is `web` |
`mobile`, declared; `gate_evidence` labels IAD's items in the list and is
refused as an upload value. The test label is `is_test_fixture`.

**The routes**: `POST /assets/<id>/photos` (multipart — `file`, `source`,
`caption`; the multipart parsing built once, `utils.get_multipart`, inside
the envelope, idempotency and the unknown-field refusal working as for
JSON); `GET /assets/<id>/photos` (photos and IAD evidence, `kind: photo |
iad_evidence`, the guard of §0b); `GET /assets/<id>/photos/<photo_id>` (the
bytes, `ETag` = SHA-256, immutable); `POST …/supersede` (`reason`
required, a second one `409`). History kinds `photo_added`,
`photo_superseded`. **The asset page** has a *Photos* tab with *Add photo*
for `assets:write` (the browser re-encodes to ≤ 300 KB JPEG, as the phone
must) and *Supersede*.

**Driven** (`tests/test_asset_photos.py`, 17 HTTP; in-registry 22): a photo
up and back byte for byte (and its SHA-256); 300 KB accepted, 301 KB `413`;
the 13th `409` until one is superseded; a PDF renamed `.jpg` `415`; a GIF
`415`; a truncated JPEG `400`; an unknown form field refused and nothing
written; a supersede with its event, the second `409`; the list with a
gate-evidence item beside a photo — the Auditor sees the labelled item and
opens it, the Store Officer sees the photo, the count, and a 403 on the
file; a candidate accepts a photo. Browser: `e2e/tests/61-photos.spec.ts`.

## §6 · A sync filter

`GET /assets?updated_since=<ISO-8601>`: `write_date >=` the instant; a date
or a date-time, `Z`/offset or none (= UTC, as everything this API publishes
is), `T` or a space — an `updated_at` the API published is accepted back
verbatim. Unparseable is `400 invalid_request` (`yesterday`, `2026-13-01`,
`15/10/2026`, `null`); never "no filter". Composes with every filter;
order and paging unchanged (id). `GET /reports/register-snapshot`, which
shares the domain builder, refuses it (a snapshot is not the live register —
the verification pass, F8).

**Paging a sync — no cursor needed.** The next sync starts from the FIRST
page's `meta.timestamp` (minus a margin), not from the largest
`updated_at` seen. Driven
(`test_a_sync_across_two_pages_catches_a_row_changed_mid_sync`): three
assets, two to a page; between page 1 and page 2 the first row — behind the
cursor — is changed; this pass does not see the change; the next sync from
page 1's timestamp returns it, and exactly the rows whose own record changed
since (a new asset's record can be rewritten a moment after creation by
the system — an outbound message's delivery state — and that is a change
too; the test's first draft assumed it was not, and failed on it). Written
up for the mobile team in their map.

## §7 · Room codes (R8)

`generic.location.location_code`: `LOC-` + the zone codes of the location
and its ancestors (cleaned to `[A-Z0-9]`, `_tag_prefix`'s rule), or ending
in the id where the location has none of its own (`LOC-1133`,
`LOC-HQ-F10-1133`); a derived code already taken gets `-<id>`. Never equal
to an asset code or a tag number (always `LOC-`; 0 of either begins so on
8 tenants; a typed code equal to one refused). Unique tenant-wide, archived
rows included (`models.Constraint` + a Python check that refuses in words
first). Stable once stored; empty on edit means regenerate. `locations:write`
edits it; `409` taken, `400` wrong shape, nothing written.

**Fan-out** (`docs/handoffs/61-evidence/fanout.txt`):

| Tenant | locations | coded | distinct | malformed |
|---|---|---|---|---|
| test19 | 1,271 | 1,271 | 1,271 | 0 |
| cadra19 | 754 | 754 | 754 | 0 |
| nrs19 | 1,154 | 1,154 | 1,154 | 0 |
| gtb19 | 149 | 149 | 149 | 0 |
| nrs | 847 | 847 | 847 | 0 |
| lasg | 111 | 111 | 111 | 0 |
| gtb | 143 | 143 | 143 | 0 |
| jaizbankplc | 440 | 440 | 440 | 0 |
| **all** | **4,869** | **4,869** | **4,869** | **0** |

510 of 4,869 keep a zone-derived code (the HQ trees of `nrs19`/`nrs`, 2
`test19` fixtures), 28 took the `-<id>` suffix (`test19` fixtures sharing
zone `E2E-01`), 4,331 are id-based — names were not abbreviated, because an
invented abbreviation is not the hierarchy.

**Labels**: `GET /locations/<id>/label?size=medium|large` (`locations:read`),
a PDF, QR and Code 128 carrying the code verbatim; `small` refused in words.
**A finding against the handoff**: §7 says "medium and large only (the small
Code 128 doesn't read)", but handoff 54's corpus reads the MEDIUM
("standard") Code 128 0 of 24 too (small 0/24, medium 0/24, large 9/24; QR
9, 11, 18 of 24) — so a medium room label is read by its QR (GO-LIVE §30.2).
Room labels are not asset labels and take no print-funnel record.

**The scan**: `/barcode/lookup` tries a room code LAST — `matched_by:
"location"`, `matched_location {id, name, location_code, path,
location_type, parent_id, asset_count}`, no asset keys; tag → asset code →
serial unchanged; `/tags/lookup` (the public portal's shape) unchanged. The
station shows *"This is a room: <name>"* and has a room-label panel; the
location page has a *Room code* card with print.

Driven: `tests/test_location_code.py` (20), in-registry
`test_location_code.py` (format, uniqueness under both checks, the fill
idempotent, and a whole-tenant fill that leaves an `nrs_asset` fingerprint
of code, serial, class, SAP number and `write_date` unchanged — §10),
`e2e/tests/61-room-codes.spec.ts` (code shown, large label printed, small
not offered, the station scan answering *This is a room*; a held code
refused in words, nothing saved).

## §8 · The endpoint map for the mobile team

`docs/integrations/mobile-ai-capture-endpoints.md`. Their list has **24**
endpoints (6 "reuse as is", 18 new; three rows name two paths each and are
counted once, as the PDF does). By status:

| Status | Rows |
|---|---|
| exists (real path and differences) | 6 |
| added in 61 | 3 (`/ai-captures/photos` → `POST /assets/{id}/photos`; `GET /assets?updated_since=`; `GET /assets/{id}/photos`) |
| comes in 63 | 8 (devices; code blocks POST/GET/return-as-void; `POST /ai-captures`; `GET /ai-captures/{id}`; void; flags) |
| comes later — **not yet placed in 62 or 63** | 4 (`/ai/config`, `/ai/signatures`, swap flags, label template) — a sixth status, see Deviations |
| redundant | 2 (`required-fields` → `/asset-categories`; lost-tag requests → the replacement, now a reprint) |
| not Cadra's | 1 (the model manifest and download) |

The two corrections are at the top; R1, R2, R4, R5, R7 in plain words; what
their label must carry (the code verbatim, QR first, no Code 128 at small —
and none to rely on at medium). §5 was checked against the finished build
and the "shapes to be confirmed" notes removed. Also flagged for them:
`/auth/login` needs a Turnstile token where Turnstile is configured (an
open question for a native app); a person's token is not record-capped.

## §9 · Hosting (R7)

GO-LIVE §30.1: AI-NFR-04 requires Nigerian hosting; the owner has ruled the
current servers for now; NRS's written acceptance before production photos,
owner the owner. **No region is recorded anywhere in the repository** —
every DigitalOcean region slug, `region` and `topology.kubernetes.io`
searched across `k8s/`, `.github/`, the deployment docs, scripts and compose
files. `cadra-dev` is a namespace; the cluster is the GitHub variable
`vars.DO_CLUSTER_NAME`. The read-only workflows (`db-query`,
`audit-tenant`, `debug-job`, `uptime-check`) cannot print a region — none
was run.

## §10 · What did not change

The one migration writes only `generic_location.location_code`; the
in-registry whole-tenant fill test fingerprints every asset's code, serial,
class, SAP number and `write_date` before and after and finds them equal.
With the gates off, the changes are the added routes and fields, the
default `tag_id` schema, the replacement keeping its number — and three
reads §10 did not list, each announced in the CHANGELOG: (a) a label
printed at the station now reads `printed` before it is affixed (the
`/tags/printed` deviation); (b) IAD's evidence needs `evidence:read` (ruling
1 — on every tenant, not only gated ones, since the evidence exists only
there); (c) the station's `untagged` count and list leave out an asset
whose label is pending replacement.

---

## Verification

All on `test19`, after the fan-out, in CI's order (pytest, then the module
suites, then the browser), first with `cadra.receipt.gated` OFF, then ON;
the switch put back ON (its value before) at the end. Full outputs in
`docs/handoffs/61-evidence/`.

### pytest — the same test set, both denominators

| Switch | Result | File |
|---|---|---|
| off | **1,457 passed, 7 skipped, 0 failed** of 1,464 (11 min 51 s) | `pytest-switch-off.txt` |
| on | **1,457 passed, 7 skipped, 0 failed** of 1,464 (19 min 22 s) | `pytest-switch-on.txt` |

The 7 skips, both states, by category: 2 Turnstile not configured; 2
partition-data-absent (`closed`, `is_staff_bus`); 1 no active
`workflow.config`; 1 `is_tagged`'s documented `null`; 1 the API cannot
create an untagged asset (handoff 38). None is new.

**The first full run (before the final fixes) had 3 failures**, all named
and fixed before the run above: two pinned the history's list of kinds
(`photo_superseded`, `photo_added` are additive), and
`test_patch_category_policy_propagates_to_its_assets` **timed out at 30 s**
— see *A finding about `test19`'s size* below; it passed in both final runs
at the edge.

### The module suites — `N failed, M error(s) of X tests`

| Module | switch off | switch on |
|---|---|---|
| `myservice_api` | 0 failed, 0 error(s) of **505** | 0 failed, 0 error(s) of **505** |
| `myservice_asset_register` | 0 failed, 0 error(s) of **482** | 0 failed, 0 error(s) of **482** |
| `myservice_workflow` | 0 failed, 0 error(s) of **96** | 0 failed, 0 error(s) of **96** |
| `myservice_barcode_station` | 0 failed, 0 error(s) of **20** | 0 failed, 0 error(s) of **20** |

0 `CRITICAL` in every run (`module-suites-switch-{off,on}.txt`; the
`ERROR:` lines there are the SQL errors tests provoke on purpose — the
read-only-transaction guard, the FK refusals — not failures). The first run
had 3 failed / 2 errors in `myservice_api`: the Auditor's pinned scope set
(now with `evidence:read`), the history's pinned kinds, and `GateCrew._to`
having no step from `reg_submitted` (no caller had walked to `registered`
before) — all fixed.

### The browser suite — 275 specs

| Switch | passed | skipped | flaky | failed | File |
|---|---|---|---|---|---|
| off | 241 | 31 | 0 | 2 (+1 did not run) | `e2e-switch-off.txt` |
| on | 258 | 12 | 1 | 4 | `e2e-switch-on.txt` |

- **Off, the 2 failures were spec 61's own** (written blind by the agents):
  the photos spec received an asset with no category, and the room-code
  spec read the PDF off the click's consumed response. Fixed (`cb88de3`);
  **rerun off: 8 of 9 passed** (`e2e-rerun-61-14-switch-off.txt`) — both 61
  specs green; the ninth is spec 14, below.
- **On, the 4 failures are spec 54's decoding tests**, at 0.5 s each with
  *"Aborted(both async and sync fetching of the wasm failed)"* — the test
  process failing to fetch the decoder; they passed with the switch off.
  **Rerun on: spec 54 and both 61 specs, 16 of 16 passed**
  (`e2e-rerun-54-61-switch-on.txt`).
- **Spec 14 (`ERP-managed mode disables the calculation controls`) was
  flaky on, and failed in the off rerun** — in its clean-up: switching the
  tenant back from ERP-managed to computed recomputes the register, and the
  button stayed disabled past 15 s. It left `test19` in `erp_managed`; I
  switched it back — **14.1 s** by curl. Same cause as the category PATCH
  below; nothing in this handoff touches that path.
- Skips: off, 31 — 18 are the gates-only specs (57/58/59, and one in 61),
  the rest the building-location and approval-state data skips named in
  report 49; on, 12, as in report 60.

### A finding about `test19`'s size — not a regression

`PATCH /asset-categories/1` with a new useful life took **27.9 s and 29.3
s** by curl (the suite's timeout is 30 s); the depreciation-mode switch
**14.1 s** (spec 14 waits 15 s). Profiled in a shell: the model write takes
0.1 s; the time is the route re-deriving **16,445** inheriting assets one
tracked write each (`mail.thread._track_prepare` and `write` dominate; no
handoff-61 frame in the top 25). The same class had 12,715 at handoff 58.
On a client with a large class, saving a category's policy is a 30-second
request. For the Architect: batch the propagation (a grouped SQL update of
the derived fields, or untracked writes), or move it to a job.

### §0b, §1–§7 driven — where each check lives

| Item | Proof |
|---|---|
| §0b-1 the evidence guard, each role | `tests/test_the_same_code_and_the_photo.py`, `TestEvidenceScope` |
| §0b-5 the two batches by 60's rules | `tests/test_the_same_code_and_the_photo.py`; spec 60 (browser, 20 units) |
| §0b-6 the category time | `asset-categories-timing.txt`; `TestCategoryCountsGrouped` |
| §1 reprint gated / gates-off, count, void, voided-print scan, approver | `tests/test_reprint_same_code.py`, `TestReprintSameCode`; specs 38, 39, 51 |
| §2 each route on a candidate | `tests/test_the_same_code_and_the_photo.py`, `TestCandidateNotOnTheRegister` |
| §3 default vs customised; a chair with no make, gates on | the table above; `test_a_chair_with_no_brand_is_received_with_the_gates_on`; `TestChairWithNoBrand` |
| §5 byte for byte, each cap, PDF-as-jpg, supersede, evidence beside a photo | `tests/test_asset_photos.py`, `TestAssetPhotos`, spec 61-photos |
| §6 two pages with a row changed between | `test_a_sync_across_two_pages_catches_a_row_changed_mid_sync` |
| §7 counts, zero collisions, a label printed, the room scan | `fanout.txt`; `tests/test_location_code.py`; spec 61-room-codes |
| §8 the 24 rows | each "exists" row cites a registered path; each "added" row is a route in this branch; each "later" row cites evaluation §4 |
| §9 fan-out, readiness | `fanout.txt`; `GET /meta/readiness` on `test19`: `{"ready": true}` |

## §12 · Sizing 62's matcher — how often does an old FIRS tag find one SAP record?

From `~/Downloads/NRS Asset (1).XLSX` under 59's rules: counts only, read
with `python3 -I` from a scratch copy that was then deleted; nothing from
it is in the repo. 211,699 rows; **active** = `Deactivation on` empty
(161,647, the reference doc's figure). The old tag is `Inventory number`;
uniqueness is judged among ALL active records. Tag normalised: trimmed and
upper-cased (a looser form — whitespace removed, `\` → `/` — changes the
shares by < 0.4 points). **The export carries no office, location or
cost-centre column** (the four candidates empty on 80,370 of 80,370 and
24,978 of 24,978 active records), so the only office is the one inside the
tag.

| | Furniture (2000) | Office equipment (4000) |
|---|---|---|
| active records | 80,370 | 24,978 |
| **has an old tag** | **65,660 of 80,370 (81.7%)** | **20,736 of 24,978 (83.0%)** |
| **tag unique among active records** | **52,795 of 65,660 tagged (80.4%)** — 65.7% of active | **14,998 of 20,736 (72.3%)** — 60.0% of active |
| tag follows `FIRS/<office>/…` | 61,427 of 65,660 (93.6%) | 19,055 of 20,736 (91.9%) |
| **a shared tag made unique by the office** | **0 of 12,865** | **0 of 5,738** |
| shared tag: candidates by tag + description | mean 8.55, median 1, max 200; one left for 9,657 of 12,865 (75.1%) | mean 15.02, median 1, max 160; one for 3,694 of 5,738 (64.4%) |
| shared tag: candidates by office + description (tag ignored) | mean 92.2, median 41, max 600 | mean 58.8, median 21, max 443 |
| no tag: candidates by description, nationwide (no office known) | 14,710 records: mean 727, median 373 | 4,242 records: mean 195, median 66 |
| **ends on one record by tag (+ description)** | **62,452 of 80,370 (77.7%)** | **18,692 of 24,978 (74.8%)** |

**What it says.** (3) is zero by construction: the office is part of the tag,
so records sharing a whole tag share its office — the office is a
plausibility check on a scanned tag, not a tie-breaker (it does matter for a
bare sequence number: number alone unique 0.1%, number + office 78.7% /
69.5%). So **about three items in four can be "this is the one" off the old
tag**; for a shared tag the description usually settles it (median one
candidate); an **untagged** item has hundreds of candidates and the operator
picks — and since an untagged SAP record carries no office in this file, a
per-office slice of the mirror cannot even contain them unless 62 gets an
office from elsewhere. That is the question for 62.

## Deviations, with why

1. **`POST /api/v1/tags/printed`** (`tagging:write`) — not asked for. The
   voided-print refusal §1 asks for needs prints recorded, and the app had
   recorded 1 of 3,069. Without the route, every reprint confirmed from the
   app is refused; without the refusal, nothing at all distinguishes the
   voided print. Its limit, plainly (the verification pass, F3): the app
   calls it when the print dialog opens, whether or not paper came out, and
   the person who records the print can be the person who affixes — so it
   catches the case where nobody pressed *Print*, and no more. Rule it out
   and the `voided_print` refusal goes with it.
2. **The photo cap is 300 KB, not 5 MB** — AI-NFR-07's number, as §5 says to
   use; the handoff's 5 MB was the fallback. The count (12) is the fallback,
   because the NFR gives none.
3. **A gated receipt may not arrive missing, in repair or verified** — R10
   names three routes; the create door would otherwise make a candidate
   that can never be marked found (verification pass, F2).
4. **The history withholds a non-reader's checklist and notes too**, not only
   the attachment ids — to give the same answer as `/evidence`
   (verification pass, F1).
5. **`register-snapshot` refuses `updated_since`** rather than inheriting it
   through the shared domain builder (F8).
6. **The mobile map has a sixth status** — *comes later, not yet placed in 62
   or 63* — for four endpoints the evaluation's §4 does not assign. Placing
   them is the Architect's.
7. **`·R1` not printed** (§1) and **no Code 128 to rely on at medium** (§7) —
   both measured, both explained above.
8. **The label templates are in `views/asset_tag_report.xml`**, not the
   `data/` file the reprint brief named — only noted.

## The verification pass (a fresh agent, not an author)

Read-only, over the whole diff against §0b–§10. Its findings and what was
done:

| # | Finding | Done |
|---|---|---|
| F1 | the history published a non-reader IAD's checklist and notes while `/evidence` gave the count | fixed: one answer, the count |
| F2 | a gated receipt could arrive `missing`/`in_repair`, then be stuck | fixed: refused at creation, and a verification date too |
| F3 | `/tags/printed` lifts the voided-print check on the dialog's opening | stated (Deviation 1) |
| F4 | the app refused a picture already smaller than 320 px | fixed |
| F5 | CHANGELOG pending | written |
| F6 | `is_test_fixture` null on evidence items vs a non-nullable schema; `voided_at: false`; "voided (False)" | fixed |
| F7 | `scripts/nrs_hq_seed.py`'s wipe does not name the photo pin (it would fail on the FK instead of refusing in words) | **left** — the seed is not run on tenants with photos; for a later pass |
| F8 | `updated_since` reached the register snapshot | fixed: refused there |
| F9 | the sixth status on the map | stated (Deviation 6) |
| F10 | unlisted read changes: the station's `untagged` count; INT-05 sends a reprint's affix with the same number and a new `label_id` | announced in the CHANGELOG, Vendra told to key on `label_id` |
| F11 | the photo list reads each image evidence file's bytes for its dimensions | left — evidence per unit is a handful of files |
| F12 | `/condemn` on a candidate answers with the disposal sentence | left — it is a disposal |

It confirmed sound: the scope holders, every place evidence is served, the
batches as N single fires, the grouped counts' filter, the reprint's write
order and stamps, nothing in the chain writing `state` or a verification
date, the photo model and caps, the sync filter, every location coded on
every tenant, and no migration touching an asset's code, serial, class or
SAP number.

## For the Architect

1. **`POST /tags/printed`** — keep it (and the voided-print refusal), or rule
   both out (Deviation 1).
2. **84 tag numbers are active on two assets** (§1). A partial unique index
   once they are cleared; which assets are the real holders is a data
   question.
3. **A category policy save takes ~30 s on a class of 16,000** (Verification).
4. **The four unplaced mobile endpoints** (`/ai/config`, `/ai/signatures`,
   swap flags, label template) — 62, 63 or later.
5. **Untagged SAP records carry no office** (§12) — where does 62's
   per-office mirror get one?
6. **INT-05 and a reprint**: Vendra receives a second `asset.tag.affixed` for
   the same number with a new `label_id`. Told in the CHANGELOG; whether to
   add `reprint_count` to the payload is a Vendra-contract change, not made.

## The standing sentence check

Every refusal added says what happened and what to do, in words; none says
"permission denied":

| Refusal | Sentence |
|---|---|
| Candidate, verify | *"This unit is not on the register yet (waiting on <who>); it can be verified once it is registered."* |
| Candidate, mark missing | *"… it cannot be missing from a register it is not on yet."* |
| Candidate, mark found | *"… it cannot be found on a register it is not on yet."* |
| Candidate, other status | *"… its status can change once it is registered."* |
| Voided print | *"Tag X is reprint 1 and has not been printed yet, so the label being scanned can only be the original print, voided on <date> (<reason>). Print reprint 1, then confirm it."* |
| Scrapped print | *"Tag X has been scrapped: the original print was voided on <date> (<reason>) and cannot be confirmed as affixed. The label in service is reprint 1, under the same number."* |
| Duplicate number | *"Tag X cannot be reprinted: the same number is also active on <asset>. …"* |
| Photo too large | *"A photo may be at most 300 KB (307,200 bytes); this one is N bytes (N KB). Compress it and send it again. Nothing was written."* |
| Not a photo | *"A photo must be a JPEG or a PNG. This file is application/pdf, judged from its contents — its name and the type it was sent as are not consulted. Nothing was written."* |
| Too many photos | *"This asset already has 12 photos, the most it may hold (12 per asset). Supersede one it no longer needs — a superseded photo is kept and stops counting — and add this one again. Nothing was written."* |
| Supersede twice | *"This photo was already superseded on <when> by <who>: “<reason>”. A photo is superseded once. Nothing was written."* |
| Not multipart | *"This route takes a multipart/form-data body (a file and its fields), not <type>."* |
| `updated_since` | *"`updated_since` must be an ISO-8601 date or date-time, for example 2026-10-15 or 2026-10-15T09:30:00Z; 'X' is neither"* |
| Snapshot + `updated_since` | *"`updated_since` is a sync filter on the live register and does not apply to a snapshot as of a date."* |
| Room code taken | *"Room code X is already the code of <name> (location N). Each location's code is unique, archived locations included. Choose another code, or leave it empty to have one generated."* |
| Room code shape | *"Room code X cannot be printed as a room label. A room code begins LOC-, uses only the letters A-Z, the digits 0-9 and single hyphens between them, and is at most 24 characters long — so a scan can never be mistaken for a tag number or an asset code."* |
| Small room label | *"A room label is printed at medium (50 x 30 mm) or large (100 x 60 mm). There is no small room label: at 50 x 25 mm the Code 128 is too fine for a camera to read (measured in handoff 54: 0 of 24 reads), …"* |
| Evidence, non-reader | *"IAD evidence: N items"* — and the file route's 403 names `evidence:read` |

## Commits

| Commit | What |
|---|---|
| `6c3dd12` (on `dev`) | Step 0: the instruction file, the evaluation, the findings, the PDFs, the Architect's evaluation edit |
| `0bad794` | The code and its tests: §0b, §1, §2, §3, §5, §6, §7, the history, the app |
| `cb88de3` | Spec 61's two fixes, found by the browser run |
| `18a644b` | DECISIONS, CHANGELOG, GO-LIVE §30, ENVIRONMENT-FACTS, the endpoint index, the mobile map, the D1 note, CLAUDE.md, STATUS |
| (this commit) | This report and `docs/handoffs/61-evidence/` |
