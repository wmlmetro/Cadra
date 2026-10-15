# Handoff 61 — The same code, and the photo

**Branch:** `feat/the-same-code-and-the-photo`
**Report:** `docs/handoffs/61-REPORT.md`
**Runs after:** 60, merged. Branch from `dev`, after pulling.
**Read first:**

- `docs/AI-CAPTURE-EVALUATION.md`: new. The rulings R1–R10 on the AI
  addendum, agreed with the owner on 15 October.
- Your own `docs/reference/ai-item-identification-builder-findings-2026-10-15.md`.
  It was the basis for every ruling. Commit it, the two PDFs beside it and
  the evaluation at Step 0, as one docs commit.

This is the first of three Cadra handoffs for the AI addendum. It builds
only what holds whichever way the later work goes: three fixes the findings
turned up, photos, a sync filter, room codes, and a correct endpoint map
for the mobile team. **Nothing here issues a code, creates an asset from a
capture, or touches an SAP mirror.** Those are 62 and 63.

---

## 0 · The findings are accepted

Six "reuse as is" endpoints, and not one is as is. Every claim carries a
file and line, the contradictions with built rulings are named, and the
questions came in the order they unblock. It is the right document at the
right time: before the mobile team builds against a backend that doesn't
exist.

The ruling that changes most of it (R1) came from SAP's export, not from
the code: **a Lot 4 audit capture finds an existing SAP asset, it doesn't
create one.** Read §1 and §3 of the evaluation before anything else.

## 0b · Report 60 is accepted

All four parts were built. Every batch is still N single fires, each checked
and recorded. The verification pass confirmed that rule line by line and
then found ten defects, all fixed. The clicks table now answers the
question I asked: four gates are a wait, not work, and the tagger is
physical work behind a control we keep.

**Rulings on its questions:**

1. **Who reads IAD's evidence: not `candidates:read`.** Delivery notes,
   invoices and photographs taken for value for money are Internal Audit's
   working papers. **Readers:** the IAD officer and approver, the Register
   Maker and Checker (they register cost against them), and the Auditor.
   **Not readers:** every Asset User, and Vendra's credential. Pick the
   scope names, and put one guard in the one place evidence is served, so
   that §5's photo list below obeys it too. A caller without the scope sees
   *"IAD evidence: N items"* and nothing more. Driven: as the Store Officer,
   and with Vendra's credential, refused; as each reader, served.
2. **The four gates-off changes** (the scan box clears; *Hidden while you
   confirm*; the search box resets; the attributes tick for a new `tag_id`
   asset): **all accepted** on every tenant. Each is a correction, not a
   gated rule.
3. **The paste registers with the unit's own class:** accepted, as built.
4. **A configuration record still naming `reference`:** fine at 0 tenants.
5. **The two gates still at 2 clicks a unit: build their batches here.**
   *Submit selected* (Store) and *Request tagging for selected* (Asset
   Controller), by 60's rules: N single fires, per-unit results,
   `dry_run`, and a mixed-GRN selection allowed for these two. **The tag
   request stays a person's act, not an automatic consequence of IAD's
   approval.** It is the Asset Controller's gate (AD-17), and a gate that
   fires itself isn't one.
6. **`GET /asset-categories` at ~3 s:** fix it. One grouped count instead
   of one count per row. Print the time before and after on `test19`.
7. **`test19`'s INT-05 target stays on.** It's a test tenant. The bearer
   key copied from `nrs19` into `test19` is acceptable *on local test
   tenants only*. Record that in ENVIRONMENT-SETUP, so that nobody copies
   the pattern to a cluster tenant.

## 1 · A replacement keeps the code (R3), and the gated defect goes

Findings §5.6 shows two problems:

- on a gated unit, an approved replacement mints a **location-prefix**
  label, not the asset code, which breaks ruling 4.3 today;
- the evaluation's §4.4 recommendation (reprint under the same code) was
  never ruled. It now is.

**Build it:**

- An approved replacement **reprints under the same code.** The label
  record gains:
  - a `reprint_count`;
  - per print, a void reason for the print it replaces.
- The old print is voided, not the code. The history says which print is
  current and why the last was voided.
- `_check_unique_active` keeps one active label per code. Show the reprint
  with a count, and describe the model change in DECISIONS.
- **Gates off, existing location-prefix labels:** a replacement of a label
  whose number is *not* the asset code keeps that label's number too. Same
  rule: the number on the asset doesn't change because a sticker faded.
  Say what the code's current comment ("two physical labels sharing one
  code make the history ambiguous") becomes. The answer is the print count
  and the void, recorded.
- **Approver unchanged:** an Asset Manager, never the requester
  (handoff 38).
- **The affix check:** a reprint is affixed and checked like the first
  print. Scanning a voided print's label is refused, naming the void and
  its date. Measure whether a voided print can be told apart physically.
  If the old and new labels encode the same value, it can't. Say so, and
  say what the reprint count printed on the label would add (`·R1`
  outside the encoded value, never inside it: handoff 55 §3).

## 2 · Not on the register, so not missing from it (R10)

`/mark-missing`, `/mark-found` and `/verify` on a candidate are refused with
58's `409 not_on_the_register` and its sentence. Extend the guard to every
other `assets:write` route that 58's list didn't name, and print the list
you checked.

## 3 · A chair with no brand (R9)

- The **default** `tag_id` schema becomes `name`, `colour`, `material`,
  `dimensions`. `make` and `model_name` are no longer mandatory by default.
- **Measure first:** on every tenant, list the `tag_id` classes whose
  schema is the default and those that were customised. Customised schemas
  are left alone.
- The published `class_attributes_schema` changes for default classes.
  CHANGELOG, and **name Vendra**: Vendra 54 still asks make and model on its
  own account. That's Vendra's rule and it stays.

## 4 · When a code is born (R2a): the record, not code

Write the DECISIONS entry:

- D1 now reads *assigned at capture or creation, printed at tagging,
  active at registration, never reused*;
- the built behaviour (code at `create`, hidden while a candidate) is the
  ruling;
- the device ledger in 63 records receipt codes too.

Update the line in `docs/reference/addendum-a-verification-gated-receipt.md`
only with an appended note. Don't rewrite NRS's document.

## 5 · Photos on an asset

Photos are evidence: AD-10 (Store may attach), AD-34 (a photo showing the
tag on the item), and the AI addendum.

- **The routes:**
  - `POST /assets/{id}/photos`: multipart, **inside `cadra_route`'s
    envelope**. It is the first such route, so build the multipart parsing
    once, in `utils.py`, for every future upload.
  - `GET /assets/{id}/photos`: a list with metadata.
  - `GET /assets/{id}/photos/{photo_id}`: the bytes, with a content type.
- **Scope:** `assets:write` to add, `assets:read` to read. Candidates
  allowed: a received unit's photo is evidence before it's registered.
- **Limits:** read AI-NFR-07 in the addendum PDF for the size and count
  caps, and use its numbers. If it gives none, use 5 MB per photo and 12
  per asset, and say so. JPEG and PNG only; anything else is refused by
  sniffing, not by extension.
- **Immutable.** A photo is never deleted or replaced. It can be
  *superseded* with a reason, and the event says who. That is the
  append-only rule, in its existing mixin.
- **The list also shows IAD's evidence** from the gate events, each item
  labelled with what it is: *photo* or *IAD evidence*. That gives one
  answer to "what pictures does this asset have". **Evidence obeys §0b
  ruling 1's guard:** a caller without the evidence scope sees the count
  only.
- **Metadata per photo:** who, when, the caption, the dimensions, and
  `source` (`web`, `mobile`, `gate_evidence`).
- **The asset page** shows them, with an *Add photo* control for
  `assets:write`.

## 6 · A sync filter

`GET /assets?updated_since=<ISO-8601>` is additive.

- Refuse what you can't parse (handoff 21).
- It composes with `location_id` and `register_state=any`.
- Order and paging are unchanged (`id`).
- Document how a client should page a sync without missing a row changed
  mid-sync. If the answer needs a cursor, say so; don't build it here.

## 7 · Room codes (R8)

- `generic.location` gains `location_code`: unique per tenant, generated
  when empty from the existing hierarchy (say the format), and editable by
  `locations:write` with a uniqueness refusal.
- **Published on `GET /locations`. Fan-out:** every location on every
  tenant gets a code. Print the count, and confirm zero collisions.
- **The station prints room labels:** QR and Code 128 carrying the code
  verbatim (handoff 55 §3), at the medium and large sizes only (handoff 54:
  the small Code 128 doesn't read).
- **Scanning a room code** at the station's scan box answers *this is a
  room: <name>*, never "not found". `GET /barcode/lookup` gains
  `matched_by: location`.

## 8 · The endpoint map for the mobile team

Write `docs/integrations/mobile-ai-capture-endpoints.md`. Its reader is the
mobile team, outside this repo's history, so plain words, no handoff
numbers without a one-line gloss.

- **The rulings that change their design:** R1 (an audit capture matches an
  SAP record, it doesn't create an asset), R2 (codes from device blocks,
  voided not returned), R4 (a person signs in, never a device), R5
  (condition) and R7 (hosting, for now).
- **All 24 of their endpoints**, each with one status:
  - **exists**: the real path and its differences, from findings §3;
  - **added in 61**: this handoff;
  - **comes in 62 or 63**: one line on what it will be;
  - **redundant**: what to use instead;
  - **not Cadra's**: the model manifest and download.
- **Two corrections called out at the top:**
  - `/asset-categories` replaces `/asset-classes/{id}/required-fields`;
  - serial lookup is `/barcode/lookup`, not `/by-tag`.
- **What their printed label must carry:** the code verbatim, QR first, and
  no Code 128 at the small size.

## 9 · Hosting (R7)

Add a GO-LIVE entry:

- AI-NFR-04 requires Nigerian hosting. The owner has ruled the current
  servers for now.
- Name the region the `cadra-dev` cluster runs in, if anything in the repo
  or the cluster's read-only metadata says it. Use the `db-query` or
  cluster-read workflows only.
- NRS's written acceptance is required before production photos. Owner:
  the owner.

## 10 · What must not change

- With the gates off, everything reads as after 60, except:
  - the added routes and fields;
  - the default `tag_id` schema;
  - the replacement keeping its number, announced as a BEHAVIOUR CHANGE.
- The no-two-gates rule, the role exclusions, and the batch rules from 60.
- No asset's code, serial, class or number is rewritten by any migration
  here.

## 11 · Verification

1. The full pytest suite, the module suites and the browser suite, gates
   off and gates on, on `test19`. The same test set; both denominators.
   Then §0b driven:
   - the evidence guard, as each role;
   - the two new batches, by 60's batch rules;
   - the category list's time, before and after.
2. §1:
   - a replacement on a gated unit and on a gates-off unit, each reprinted
     under its own number, with the count and the void reason in the
     history;
   - the voided print's scan refused with its sentence;
   - the approver rule unchanged.
3. §2: each route on a candidate refused, with the list printed.
4. §3: per-tenant default vs customised `tag_id` classes, printed; a chair
   with no make received on `test19` with the gates on.
5. §5:
   - a photo up and back, byte for byte;
   - each cap refused;
   - a PDF renamed `.jpg` refused;
   - a supersede with its event;
   - the list showing a gate-evidence item beside a photo.
6. §6: a sync across two pages with a row changed between them, and what
   the client sees.
7. §7: per-tenant code counts and zero collisions; a room label printed;
   its scan answering *this is a room*.
8. §8: the map's 24 rows, each checked against a route that exists or a
   handoff that names it.
9. The fan-out, readiness, and the deploy steps for the owner.

And the standing sentence check.

## 12 · The question for the report: sizing 62's matcher

**How often does an old FIRS tag number find exactly one SAP record?**

Read the export (`~/Downloads/NRS Asset (1).XLSX`) under 59's rules:
counts only, no row in the repo. For **active** furniture (class 2000) and
office equipment (class 4000), give:

- the share of records with an old tag number;
- the share whose tag number is unique among active records;
- the share that becomes unique when the office code inside the tag
  (`FIRS/<office>/…`) is matched against the room's office;
- for the rest, how many candidates a description plus office leaves on
  average.

That sizes how often the phone can say *this is the one* and how often the
operator has to pick.
