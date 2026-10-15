# Handoff 60 — Seventy a day

**Branch:** `feat/seventy-a-day`
**Report:** `docs/handoffs/60-REPORT.md`
**Runs after:** 59, merged (PR #118). Branch from `dev`, after pulling.
Step 0 commits two Architect edits found in the working tree (§0, ruling 1)
as their own docs commit.

---

## 0 · Report 59 is accepted

The SAP class is checked before two people sign, not after SAP refuses. A
plot of land can reach the register. Placeholders are refused as
placeholders. The proposal table is exactly what NRS needs to decide the
mapping, and nothing was typed into a real tenant. CI was put right, which
had been red since 58 merged. And §7 measured the gates at real volume: the
best question a report has answered.

**The rulings:**

1. **The identifiers in my docs.** You were right: the reference doc and
   handoff 59 quoted real SAP numbers, legacy codes, a FIRS tag number and
   six shared serials, against the rule I wrote in the same handoff. I've
   replaced them with shapes in both files; the edits are in the working
   tree. Commit them at Step 0. **No history rewrite.** The repo is private,
   these are identifiers, not secrets, and `docs/seed/` already holds NRS
   register rows from before the programme's rule (§6). A force push to
   `dev` would cost more than it protects.
2. **`reg_ready`:** accepted. *Tagged* on a plot of land would be false.
3. **The two gates-off changes** (SAP numbers unique once normalised; a
   category's SAP class four digits from every writer): accepted. A rule
   only the gate obeys is a rule an import walks around. §5's letter yields
   to that.
4. **`tag_id` units with a placeholder serial refused:** accepted.
5. **No format refused for SAP numbers:** accepted.
6. **INT-06 holding a gates-off master with a blank class:** stays `[open]`.
   It is built with the first real post to SAP's endpoint, not before. Until
   then nothing reaches SAP.
7. **The top-level `reference`:** rename it to `record_reference` before
   anything outside Cadra reads it. Handoff 37's one-name rule applies:
   three keys named `reference` with three meanings is the defect that rule
   exists for. CHANGELOG: BREAKING (rename), additive since 59 only, no
   client reads it yet. Vendra 56 is told the new name.
8. **The mapping proposal** goes to NRS through the owner. The three
   categories that can't carry one class (*Printer / Photocopier*, *CCTV
   System*, *UPS / Battery Backup*), the UPS units inside *IT Equipment*,
   and `nrs19`'s stored `3100` are NRS's questions. They're on the owner's
   list. Nothing here.

## 1 · From Vendra's report 55: three Cadra fixes

1. **Vendra can't see candidates.** `GET /assets?register_state=any` and
   `GET /candidates` need `candidates:read`, and the `vendra` API client
   holds `assets:read assets:write` only.
   - Add `candidates:read` to the scopes `bootstrap.ensure_vendra_client`
     grants.
   - Add a **migration** that adds it to every existing client named
     `vendra` on every tenant, printing the per-tenant count. It is read
     only.
   - The PR merge is the owner's authorisation of this grant. It is a
     change in code, reviewed. Don't grant it by hand anywhere.
2. **A tag-ID asset created with the gates off publishes
   `identification_mode: null`** (report 54 §5.3, asset 12016 on `nrs19`).
   A new asset should carry its class's mode whatever the switch says.
   Find why and fix it. Existing records stay as 58 left them (null on
   pre-58 rows), unless the fix is a computed field, in which case say what
   every record now reads.
3. **INT-05 didn't reach Vendra from `test19`** when a chair was affixed.
   Check `test19`'s `workflow.config` (or whatever routes INT-05) against
   the Vendra the bench runs. Make the one-line fix if it's configuration on
   a test tenant. If it's a defect, fix it and say so.

## 2 · The three bottlenecks, relieved

Report 59 §7 is the specification. Build the "smallest relief" for each,
in this order, and stop after any one if the next would take the handoff
past its size. Say where you stopped.

**What doesn't change:** one person may not fire two gates on a unit, and
every unit gets its own append-only events. A batch action is N
single-unit gate fires, each checked and each recorded. **A batch never
writes one event for many units, and one refused unit never rolls back the
others.** The answer lists, per unit, fired or refused with the sentence.

### 2a · Everyone, first: told, and oldest first

- **A sidebar badge per person:** the count of units waiting on *their*
  gate that they are *allowed* to fire. Exclude the units the no-two-gates
  rule bars them from; a badge must not count work they can't do. Use the
  same cheap count the approvals badge uses.
- **The Candidates list oldest first** by `state_since`, with the age
  visible.
- **Turn on the existing `?q=` search** (it matches the GRN).
- **`waiting on me`** shows only units the person may act on. The barred
  ones stay findable under the plain gate tab, with their sentence.

### 2b · IAD verification, the heaviest gate

- **A batch route:** one checklist and one evidence set for N units **of
  the same GRN**. It fires `verify` per unit; the evidence attachments are
  stored once and linked from each unit's event.
  - Refuse a batch mixing GRNs: *"These units come from 3 receipts; verify
    one receipt at a time so the evidence matches."*
- **On the Candidates `iad` tab:** a checkbox column, *Verify selected*,
  and the search from 2a.
- **The dialog:**
  - an *all four* toggle;
  - picked files kept while the dialog is open.
- **The approver sees the evidence** on the asset page, and from the list
  row. Today they approve blind.
- **Batch approve** on the approver's tab, by the same rules: per-unit
  fires, per-unit result.

### 2c · Tagging

- **After a confirmation, clear and focus the scan box.**
- **A *Labels to fix* panel on the station**, reading
  `GET /candidates?waiting_on=tagging`, with select-all into the existing
  batch print.
- **The second scan inside the confirm dialog stays.** It is the control.
- **Ruling on your note.** The label number is the asset code, and it's on
  every Candidates row, so "never hand the number over" protects less than
  it did. Keep the rule that the dialog doesn't pre-fill it. Hide the asset
  code on the `tagging` tab's rows, so the tagger reads it off the physical
  label and not off the screen. Say what else shows it.

### 2d · The Register Maker and Checker

- **Prefill:**
  - cost from the unit;
  - cost centre and capitalisation date carried from the maker's previous
    submission, in the session.
- **A paste box on the `maker` tab:** lines of `<asset code> <SAP code>`,
  previewed per line (found, class, any warning, any refusal) before
  anything fires. Then per-unit submits.
- **The `checker` tab** shows SAP code, cost, cost centre and class on each
  row, with batch approve by the same rules. *Back* from an asset opened
  from Candidates returns to Candidates.

## 3 · What must not change

- With the gates off, nothing a user sees changes, except the badge, which
  is zero.
- Every gate's single-unit route keeps its contract. Batch routes are new
  and additive.
- The no-two-gates rule, the exclusions, the placeholder and SAP-class
  checks: all fire per unit inside a batch, with the same sentences.

## 4 · Verification

1. The full pytest suite, the module suites and the browser suite, gates
   off and gates on, on `test19`: the same test set, both denominators.
2. §1:
   - the migration's per-tenant line;
   - Vendra's `register_state=any` answered 200 with the `vendra`
     credential on `test19`;
   - a new tag-ID asset created with the gates off reading `tag_id`;
   - INT-05 arriving at the bench's Vendra.
3. §2, driven as the personas on `test19` with **one GRN of 20 units**.
   **Count the clicks and keystrokes per unit for each gate, before and
   after**, the way report 59 §7 counted them, and print the table.
4. The batch rules:
   - a batch of 20 where the actor is barred on 3 → 17 fired, 3 refused
     with the no-two-gates sentence;
   - a mixed-GRN verify refused;
   - one unit's SAP code duplicated inside a paste → only that line
     refused;
   - the history of one unit from the batch reads like a single-unit fire.
5. The badge for each persona at each step: right count, zero for barred
   units.
6. The fan-out, readiness, and the deploy steps for the owner, as in
   report 59.

And the standing sentence check.

## 5 · The question for the report

**After this, which gate is slowest per unit, and is it still a person's
work or now a wait?** Reprint §7's table with the new numbers. Add one
column: what the person still does by hand that a system could do.

## 6 · For the owner (not the Builder)

`docs/seed/` contains NRS register rows (asset numbers and serials) in
about a dozen CSV files, committed before this programme's
identifier rule. Is that acceptable for this repository's access list? It
is the owner's question, not a code change.
