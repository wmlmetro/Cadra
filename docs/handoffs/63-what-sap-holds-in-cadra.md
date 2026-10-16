# Handoff 63 — What SAP holds, in Cadra

**Branch:** `feat/what-sap-holds-in-cadra`
**Report:** `docs/handoffs/63-REPORT.md`
**Runs after:** 62, merged. Branch from `dev`, after pulling.
**Read first:**

- `docs/AI-CAPTURE-EVALUATION.md` §3, the SAP mirror;
- `docs/reference/sap-asset-master-2026-10.md`;
- report 61 §12, your sizing of the matcher.

---

## 0 · Reports 61 and 62 are accepted

**Report 61.** A faded tag keeps its number. IAD's papers are IAD's. Every
room on every tenant has a code, with no collision. The mobile team has a
map they can trust. And §12 sized the matcher from the export: about
three items in four end on one SAP record by the old tag, a shared tag
usually settles on its description, and an untagged item has hundreds of
candidates.

**Report 62.** Cadra tells Vendra every act, down the road Vendra already
trusts. You found the `auth_hooks` gap in Vendra's own code before Vendra
did: I've put it in Vendra 57. And §5 answered the downtime question with a
measurement, not a guess.

**Rulings:**

1. **`POST /tags/printed`: keep it**, with its stated limit. A recorded
   print is better than none, and the voided-print refusal depends on it.
2. **84 tag numbers active on two assets:**
   - give a per-tenant count;
   - add a back-office filter, *Tags active on two assets*, for the owner
     to resolve;
   - add the partial unique index once a tenant reads zero, and say how
     the owner turns it on.

   Nothing is cleaned automatically.
3. **A category policy save at ~30 s for 16,000 assets:** measure where the
   time goes. Fix it if it's one query per asset; otherwise say what it
   would take.
4. **The four unplaced mobile endpoints:**
   - `/ai/config` and the label template as data go to **64**, since the
     offline phone needs both;
   - `/ai/signatures` goes to **64**;
   - swap flags go **after 64**: they need an audit campaign, which no
     handoff has yet.

   Update the map's sixth status to say so.
5. **Untagged SAP records carry no office.** This handoff builds the mirror
   with what the export has: the office from the old tag where there is
   one, and **none** otherwise. The owner asks SAP's team for the cost
   centre and location extract (SAP's ANLZ). When it arrives, a later import
   fills the office. §1 makes room for it.
6. **INT-05 on a reprint:** no payload change. Vendra keys on `label_id`
   (Vendra 57 is told).
7. **One event per act** (62): accepted.
8. **The retry budget** (62 §5, GO-LIVE §31.1):
   - make the default delivery policy cover **a full day plus margin**:
     30 attempts at the 3,600 s cap, about 26 hours;
   - apply it to every existing target that still carries the old default,
     by migration, printing per tenant what changed;
   - a target someone has customised is left alone, and listed.

   It is shared with `asset.tag.affixed`, which is fine: that should
   survive a day too.

## 1 · The SAP mirror

A **read-only reference table** of SAP's asset master, `nrs.sap.asset`.
It is **not** `nrs.asset`, and it never appears on the register, in a
count, in a report of assets, or in an export of assets.

- **Fields:**
  - company code;
  - SAP asset number and sub-number (the key is both);
  - class;
  - description (both description columns);
  - old FIRS tag (*Inventory number*), with the office code parsed out of
    a `FIRS/<office>/…` tag;
  - serial;
  - capitalisation date, first acquisition date, created on;
  - deactivation date (so *active* is computed);
  - vendor;
  - **`office_code`**: from the tag today, filled from SAP's location
    extract later, and recording which source filled it.
- **The import is a job, not a request.** The System Administrator uploads
  SAP's export (the `.XLSX` as SAP produced it) on a new *Settings → SAP
  asset master* screen.
  - The server parses it in the background with a streaming XML reader.
    The October file is 655 MB of sheet XML: don't load it whole.
  - It upserts on (asset number, sub-number), and marks records missing
    from the new file as *not in the latest export*. Never delete one.
  - Each run is recorded: who, when, file name, rows read, created,
    updated, unchanged, refused (with the reasons counted), and duration.
  - **The uploaded file is not kept** after the run. It is NRS's register,
    and the table holds what's needed.
  - **Placeholder serials** (59's list) are stored as *placeholder*, never
    as a serial.
  - Columns are matched **by header name**, and a missing required header
    refuses the file in words, naming it.
- **Who reads it:** a new scope, `sap_mirror:read`, for the Asset
  Controller, Register Maker and Checker, Auditor and System Administrator.
  **Not Asset Users, and not Vendra's credential.** Importing needs
  `settings:write` held by a System Administrator.
- **The link to the register:** a Cadra asset whose `sap_asset_number`
  matches a mirror record (normalised as 59 does) is linked to it, read
  only, both ways. Compute it, or store it and refresh on import and on
  every SAP-number write; say which and why.

## 2 · The matcher

`GET /api/v1/sap-assets/match`, with `old_tag`, `description`, `class` and
`office` (any of them), returns **up to five** active, unlinked records,
ranked:

1. an exact old tag (normalised: trimmed, upper-case, `\` → `/`);
2. among records sharing that tag, the description;
3. without a tag, class and description within the office, then
   nationwide when the office is unknown.

- **Each answer says why it ranked:** *old tag, unique*; *old tag, shared
  by 7; description matches*; *description and class; office unknown*.
- **Records already linked** to a Cadra asset are excluded, and counted
  (*3 more already on Cadra's register*).
- **Description matching:** whole-word, case-insensitive, on both
  description columns. No fuzzy-matching library unless you measure that
  it changes the outcome on the export. Report 61 §12 is the baseline;
  reprint its table from the matcher.

**For offline phones:** `GET /api/v1/sap-assets?office=<code>&class=<class>&updated_since=`
pages a slice, same paging and sync rules as 61 §6. Report the size of the
largest office's slice for furniture, in rows and in bytes.

## 3 · The first reconciliation, available today

Before any audit capture exists, the mirror already answers the question
NRS will ask first: **how much of SAP's register does Cadra hold?**

**`GET /api/v1/reports/sap-coverage`**, by class and by office:

- SAP records, active;
- linked to a Cadra asset;
- not linked;
- Cadra assets with an SAP number **not found** in the mirror (the
  reverse gap);
- Cadra assets with **no** SAP number.

It goes on the Reports page for `sap_mirror:read`. Every count says what
it is a count of (the standing rule).

## 4 · What must not change

- `nrs.asset`, its lists, counts, reports and exports: nothing from the
  mirror appears in any of them. Run 57's register-filter probe again,
  with the mirror loaded.
- Every gate, batch and event from 57–62.
- **No row of the export enters the repository**, not in a fixture and not
  in evidence (59's rule). Tests invent records in the export's *shapes*.

## 5 · Verification

1. The full suites, gates off and gates on, on `test19`: the same test set,
   both denominators.
2. **The import, run on the real export on `nrs19`** (on this machine, the
   file from `~/Downloads`):
   - the run's record;
   - the counts against the reference doc's (211,699 rows; 161,647
     active; the class table);
   - the duration and peak memory;
   - a second run of the same file: everything *unchanged*;
   - a run with a header removed: refused, naming it.
3. **The matcher:** report 61 §12's table reprinted *from the matcher* on
   `nrs19`, and five worked examples, one per ranking reason, described by
   shape not value.
4. **The coverage report on `nrs19`:** every row. This is the first real
   number for the owner's conversation with NRS.
5. **Scopes:** each reader served; the Store Officer, an Asset User and
   Vendra's credential refused.
6. **The register-filter probe** with the mirror loaded: all eleven routes
   unchanged.
7. **§0:**
   - the duplicate-tag counts;
   - the category-save timing;
   - the retry budget migration's per-tenant line;
   - the map's placements.
8. The fan-out, readiness, and the deploy steps for the owner. **Loading
   the mirror on `staging` is the owner's**, through the new screen, after
   the deploy.

And the standing sentence check.

## 6 · The question for the report

**From the coverage report on `nrs19`: how many of SAP's active assets does
Cadra hold, and of the Cadra assets with no SAP number, how many could the
matcher link with confidence today?**

Count the ones the matcher would rank first by a unique old tag or an exact
serial. That is the size of a reconciliation we could run before any audit
team goes into a room.
