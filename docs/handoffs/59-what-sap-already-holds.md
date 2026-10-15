# Handoff 59 — What SAP already holds

**Branch:** `feat/what-sap-already-holds`
**Report:** `docs/handoffs/59-REPORT.md`
**Runs after:** 58 (merged as PR #117). Branch from `dev`.
**Vendra:** 54 is running in parallel. Nothing here changes a contract
Vendra 54 depends on. §2 adds an identification mode Vendra doesn't know
yet; a small Vendra follow-up teaches it.

**Read first:**

- `docs/reference/sap-asset-master-2026-10.md` (new): what SAP's own asset
  master for NRS shows.
- `docs/GO-LIVE.md` §29, items 2, 5 and 8, which this handoff works on.

**The source file** is `~/Downloads/NRS Asset (1).XLSX` on the owner's
machine: 75 MB, one sheet, 211,699 rows. You may **read** it to measure
and to build the §1 proposal. **Never copy it, or any extract of its rows,
into the repo, a fixture or evidence.** It is NRS's register. Counts,
class codes and descriptions-with-counts are fine. Asset numbers, serials
and tag numbers of individual records are not. If you need a test fixture,
invent values in the same *shapes*.

---

## 0 · Report 58 is accepted

Every suite is green with the gates on and off, at the same denominator.
The five things my handoff assumed and the code didn't have were each
checked, built and recorded instead of trusted. Thank you. That's exactly
the protocol.

The Store-is-the-Asset-Officer correction is right, and it's now the
ruling. The readiness route without a token is right too. The verification
pass's catch, that a receipt could arrive `disposed` and send SAP a master
for a write-off, was the best find of the run.

The owner received SAP's asset master export on 12 October. It answers
three items on the go-live list and raises one we didn't have. This
handoff is those four.

## 1 · SAP's asset class on every category: GO-LIVE §29 item 5

`nrs.asset.category.sap_asset_class` exists and is blank by default. A
blank class goes to SAP as null, and SAP rejects the master. Today we'd
learn that from SAP's refusal, after two people have registered the unit.

- **Check it at the gate.** With the gates on, *Approve registration* on a
  unit whose category has no `sap_asset_class` is **refused**, with the
  sentence *"<Category> has no SAP asset class, so SAP would reject this
  asset. An Asset Controller sets it under Settings → Asset Categories."*
  Do the same at *Submit to register*, so the maker learns before the
  checker does. With the gates off, nothing changes. Say in DECISIONS
  whether INT-06 should also hold a gated-off master with a blank class,
  and what it does today.
- **The field on the screen.** Asset Categories shows and edits
  `sap_asset_class` for `settings:classes` holders. The value is SAP's
  four-character class code. Validate it as 4 digits; the export's ten
  classes are all 4 digits. Show the ten codes from the reference doc as a
  hint, not as a closed list: NRS may have classes the export didn't use.
  Every change goes to the configuration record, the way 58 records a mode
  change.
- **The proposal: build it, don't write it.** For `nrs19` and `staging`,
  produce a table with these columns:
  - Cadra category;
  - asset count;
  - the SAP class you'd propose, with the export's evidence (the
    descriptions in that SAP class that match the category's
    descriptions);
  - your confidence.

  It goes **in the report and nowhere else.** The mapping is NRS's
  decision. A wrong class sends an asset to the wrong account in SAP's
  ledger, and once INT-06 is live that's a finance error, not a data
  error. The owner takes the table to NRS; a later handoff (or the Asset
  Controller on the screen) writes the confirmed values.

## 2 · Classes that carry no label: a new identification mode

Land (SAP 6000), buildings (8000), software (3500) and works in progress
(9000, 9300) are capitalised assets that can't have a label fixed to them.
Today the chain sends every unit through *Request tagging → Confirm
affixed*. A plot of land can't pass that, so it can never reach the
register.

- Add `identification_mode = 'record_only'`, labelled *"Identified by its
  SAP record — no physical label (land, buildings, software, works in
  progress)"*.
- **At receipt:** no serial is required, and one is refused if present
  (the same reasoning as `pool`). The class schema's attributes are
  required. Default schema: description, plus a reference field: title or
  plot number for land, licence key or contract for software. Name it
  `reference` unless the code has a better existing field.
- **In the chain:** Store submits → IAD verifies → IAD approves → **Register
  Maker** → Register Checker. The two tagging gates are **skipped, not
  fired**:
  - the unit goes from `vfm_approved` straight to waiting on the maker;
  - the transition writes an event saying why (*"no label: <class> is
    identified by its record"*);
  - `waiting_on` never says `controller` or `tagging` for it.
- Add these rows to the **one** `TRANSITIONS` table, not to a second path.
- The no-two-gates rule is unchanged: five people instead of seven.
- No label is ever minted for it. The asset code is still assigned at
  registration, so the asset has an identity.
- **Seed nothing to this mode.** Which Cadra categories are land, buildings,
  software or works in progress is part of the §1 conversation with NRS.
  Measure and report the categories on each tenant whose names suggest it.
- **Vendra doesn't know this mode yet.** The ruling on Vendra's report 54
  will make it treat any mode it doesn't recognise as `serial`, the strict
  side. So a receipt
  from Vendra for a `record_only` class will demand a serial until the
  Vendra follow-up lands. Cadra must not depend on Vendra's behaviour: it
  refuses the serial on a `record_only` unit whoever sends it.
- `GET /api/v1/asset-categories` publishes the new value. CHANGELOG:
  additive enum value. Name in the CHANGELOG the clients that switch on the
  enum (Vendra), so the follow-up is findable.

## 3 · Placeholder serials: GO-LIVE §29 item 8

SAP's register has 33,096 active assets whose "serial" is a placeholder:
`0` (22,217), `XXXX`, `XXX`, `4A12345FD` (5,762) and others; the full list
is in the reference doc. `nrs19` already has 1,291 serials shared by more
than one asset. "No serial, no receipt" means a placeholder is **not a
serial**, and must be refused as one, not accepted and then collided with.

- A tenant-level **placeholder list**: exact values plus patterns. Store it
  wherever the class settings live, editable by `settings:write`, with
  changes on the configuration record. Seed it with:
  - the patterns `^X+$` and `^0+$`;
  - the exact values `4A12345FD`, `5D12345M`, `12345AB`, `12345ABC`,
    `12345HFD`, `123456`, `N/A`, `NA`, `NIL`, `NONE`, `NO SERIAL`.

  Compare case-insensitively, stripped, after collapsing internal spaces.
- **At a gated receipt:** a `serial`-mode unit whose serial matches the
  list is refused with *"'XXXX' is a placeholder, not a serial number.
  Capture the serial printed on the item."* Vendra's missing-serial
  sentence stays Vendra's; this one is new.
- **In the uniqueness check:** 58 refuses a serial already on any asset.
  A placeholder already on a legacy asset must never be the reason a real
  serial is refused. Make the check ignore existing placeholder values.
  Prove it on `nrs19` with a real-looking serial that happens to equal
  nothing, and with one that equals a placeholder (refused as a
  placeholder, not as a duplicate).
- **Measure, don't clean:** per tenant, print how many existing assets
  carry a placeholder serial and the top values. Nothing is rewritten.
  Cleaning legacy serials is NRS's call (§29 item 8).
- With the gates off, nothing changes. A legacy import is not a receipt.

## 4 · SAP asset numbers in both formats

The Register Maker types the SAP asset number at *Submit to register*. SAP
uses two formats, and both must be accepted:

- 11 digits starting with the class digit (shape `2NNNNNNNNNN`);
- legacy alphanumeric codes (shapes such as `TEMnnXXXnnnn` and
  `FIRSXXXXnnn`).

**Measure** what the field, `_check_sap_asset_number_unique` and the maker's
form accept today, and fix what refuses either shape. Normalise for
uniqueness (strip, upper-case).

**When the format is numeric and the category has a `sap_asset_class`,**
warn, don't refuse, if the first digit disagrees with the class's first
digit: *"<number> looks like a class 2000 number; this category maps to
3000."*

Sub-numbers (53 rows of 211,699) are out of scope. Say so in DECISIONS.

## 5 · What must not change

- With the gates off, every response is identical to after 58, except the
  additive enum value and the new settings fields.
- 57/58's seven-gate chain for `serial` and `tag_id` units. Spec 57 runs
  unchanged.
- No asset's data is rewritten: not serials, not classes, not numbers.
- The source file stays out of the repo (top of this file).

## 6 · Verification

1. The full pytest suite, the module suites and the browser suite, gates
   off and gates on, on `test19`. Both denominators printed, the same
   test set. Any difference explained.
2. §1:
   - registration refused at submit and at approve for a category with no
     SAP class, the sentence verbatim;
   - the class set on the screen by the Asset Controller, refused for the
     Store Officer;
   - the configuration record line;
   - the proposal table for `nrs19` and `staging` in the report.
3. §2:
   - a `record_only` unit (invent a "Land" category on `test19`) received
     with no serial and a reference;
   - the same unit refused when sent with a serial;
   - pushed through the **five** gates as five personas;
   - `waiting_on` printed at every step;
   - no label minted;
   - the skip event's sentence in the history;
   - the register count moving only at the checker. In the browser too:
     extend spec 57.
4. §3:
   - each seeded placeholder refused at a gated receipt;
   - a real serial accepted on a tenant where a placeholder already sits
     on legacy assets;
   - the per-tenant placeholder counts printed;
   - one list edit on the configuration record.
5. §4: one number of each shape accepted at submit, the class-digit
   warning shown, and a duplicate refused after normalising.
6. The source-file rule:
   - `git log -p` on the branch greps clean for any 11-digit SAP number
     from the file, `FIRS/` tag numbers, and the export's top shared real
     serials (the reference doc names six);
   - print the grep and its zero.
7. The fan-out to every local tenant and readiness on each; the deploy
   steps written out for the owner, as in report 58.

And the standing sentence check.

## 7 · The question for the report

**SAP creates about 70 assets a working day for NRS. If every one went
through the gates, where would it jam first?** Look at the screens and
routes as they are:

- how many clicks it takes to verify one unit;
- whether anyone can act on ten at once;
- what tells a person something is waiting on them.

Rank the three worst bottlenecks, each with the smallest change that would
relieve it. That ranking becomes the next handoff (Addendum A Phase E,
moved up).
