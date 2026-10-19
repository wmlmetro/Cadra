# Handoff 65 — The link

**Branch:** `feat/the-link`
**Report:** `docs/handoffs/65-REPORT.md` (~200 lines, per `CLAUDE.md`)
**Runs after:** 64, merged. Branch from `dev`, after pulling.
**Time budget:** 3 hours. Follow `CLAUDE.md`'s *Speed* and *Progress*
rules.

---

## 0 · Report 63 is accepted

The October export loaded in 100 seconds, matched the reference counts
exactly, and moved nothing on the register. Vendra was refused with its
real credential. And §6 gave the owner the first real number:

- Cadra's NRS register holds **0** of SAP's 161,647 active assets;
- **2,445** of its assets could be linked to their SAP record today, with
  confidence;
- **959** point at a SAP record that another Cadra asset also points at.

This handoff builds that link.

**Rulings on report 63's questions:**

1. **The 959 contested assets:** a review list (§2), never an automatic
   choice.
2. **The wide untagged search:** waits for SAP's location extract. Nothing
   here.
3. **The UTC day:** fixed in 63b.
4. **A truncated export:** yes, guard it (§3).
- **From report 63b, two small items:**
  - `GET /reports/access-changes` still uses UTC days. Make them Lagos
    days, as 63b did for the configuration report.
  - The endpoint reference lists `unprocessable` (422), which `utils.py`
    doesn't define. Make the reference match the code.
5. **`legacy_asset_code` holds the old FIRS tag:** the matcher, this
   handoff and 66's audit capture all read that one field. Say so in the
   endpoint reference.

## 0a · Report 64 is accepted (20 min of follow-ups)

Identify-from-photo was built, verified and documented in about 1½ hours
of a 4½-hour budget. The verification pass caught a phone's GPS location
going to the provider. Nothing is saved without a person, and the
suggestion's audit is per field. Good work.

1. **The key lives in the environment, never in the database** (deviation
   2). An `ir_config_parameter` row is readable by any back-office system
   administrator, and it lands in database backups.
   - The server reads `CADRA_AI_API_KEY` from its environment: the
     cluster's `cadra-odoo` secret, or the local `.env`.
   - **Remove the database road and any stored value** (a migration that
     deletes the row, printing per tenant whether one existed).
   - `scripts/set_ai_key.sh` writes the local `.env` entry instead,
     prompting with no echo.
   - *Settings* still says whether a key is present: true or false, never
     the key.
2. **Choosing the model from the live check:** `scripts/ai_live_check.py`
   takes `--models a,b,c` and runs the same folder through each. One table
   per model: category right first time, right in the top three, seconds,
   and cost per photo. The owner runs it once across **Opus 5.5, Sonnet
   5.5 and Haiku 5.5**, and picks the cheapest model that's right often
   enough. The default stays Opus until he does.
3. **The two known nits** (a field shown *Same* is recorded *ignored*; no
   test pins the cap's Lagos midnight): fix both. They're small.

## 0b · One real reprint, for Vendra (15 min)

Vendra's report 58 could only prove reprint handling by test: no reprint
had ever arrived from Cadra on `test19`. Do one:

1. On `test19`, take a registered, tagged unit that came from a Vendra
   receipt.
2. Request a replacement as the tagger and approve it as the Asset
   Manager.
3. Affix the reprint.
4. Confirm INT-05 delivered the second `asset.tag.affixed`, with its new
   `label_id`, to the bench's Vendra.

Note the asset id and the receipt in the report so Vendra 59 can read the
result.

## 1 · Link with confidence, by two people

A link puts SAP's asset number on a Cadra asset that is already on the
register. It changes what Cadra tells SAP later, so it's maker-checker,
like registration.

- **The Register Maker** opens *Link to SAP* (a new tab beside
  Candidates). It lists the confident matches: a unique old tag or an
  exact unique serial, and **not** contested. Each row shows:
  - the Cadra asset (code, description, location);
  - the SAP record (number, class, description, capitalisation date);
  - the reason (*old tag, unique*).

  Filter by office and class. *Propose selected* is a batch with 60's
  rules: N single acts, per-unit results, `dry_run`.
- **The Register Checker** approves or returns, singly or in a batch. One
  person can't do both on one asset (the no-two-gates rule, with a new gate
  name).
- **On approval:** the asset's `sap_asset_number` is set from the mirror,
  with `code_source = linked_from_sap_mirror`. **No `asset.master.create`
  is queued:** the master already exists in SAP. Prove it in the outbox.
  The history says *"Linked to SAP asset <n> (old tag, unique), proposed by
  <maker>, approved by <checker>."*
- **A link is undone the same way, by two people, with a reason.** It's
  never deleted.
- With the gates off, the same screens and the same two-person rule apply.
  A link isn't a receipt.

## 2 · The contested list

For each SAP record that two or more Cadra assets point at, show them side
by side: Cadra code, description, location, custodian, photos (61), created
date. The Register Maker can:

- **propose the link for one of them**, which then goes through §1's
  checker step; the others are left unlinked;
- **flag the group as a likely duplicate**, with a note. That's a record
  for NRS. **Nothing is merged, retired or deleted.**

The list shows counts by office. The flag is visible on each asset.

## 3 · An import that would mark too much absent

If a new upload would mark **more than 5%** of the mirror *not in the
latest export*, the run stops before writing. It says how many, and that a
truncated or wrong file is the likely cause. The System Administrator can
re-run with an explicit *Yes, mark them absent*, recorded on the run.

## 4 · What the links tell NRS about the class mapping

Once assets are linked, each Cadra category has evidence: the SAP classes
its linked assets actually carry. Add it to the SAP coverage report, per
category: *IT Equipment: 2,104 linked; SAP class 3000 for 2,090, 4000 for
14*. This is the evidence for report 59's proposed mapping, which NRS still
has to confirm. **Don't write `sap_asset_class` from it.**

## 5 · What must not change

- No asset is linked without two people.
- Nothing is sent to SAP by a link.
- The register's counts, lists and exports.
- 63's matcher and mirror.

## 6 · Verification

Targeted tests while building, one final local run (gates off), and CI
cited, per *Speed*. Then, on `nrs19`:

1. The confident list's count against report 63's 2,445.
2. Fifty proposed and approved as two personas, with the outbox showing
   no master queued.
3. One undone.
4. One contested group resolved, and one flagged.
5. The 5% guard tripped with a deliberately truncated copy of the file
   (made locally, never committed), then overridden.
6. §4's per-category evidence.

## 7 · The question for the report

**After linking the 2,445, what does the coverage report say?** Then
estimate how many of the remaining ~9,500 Cadra NRS assets could be linked
if SAP's location extract gave every record an office.
