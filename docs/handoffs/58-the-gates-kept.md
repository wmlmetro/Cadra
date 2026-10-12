# Handoff 58 — The gates, kept

**Branch:** `feat/the-gates-kept`
**Report:** `docs/handoffs/58-REPORT.md`
**Runs after:** handoff 57, merged and deployed (it is). Branch from `dev`.
Handoffs 53 and 55 are not touched by this one; 55 stays on hold.
**Before Vendra:** Vendra's handoff 54 reads what §4 publishes. Merge and
deploy this one first.

**Read first:** `docs/handoffs/57-REPORT.md` (all of it, including the
verification pass's left findings), then `docs/ADDENDUM-A-EVALUATION.md`
§8, which is new and changes §4.6.

The earlier draft of this handoff, *58 — The candidate*, is in
`docs/handoffs/_superseded/`. **Do not run it.** §0 says why.

---

## 0 · Report 57 is accepted, and the scaffolding is kept

Seven people, one unit, every gate in the browser as the right persona:
spec 57 ran 10 of 10 on `test19` with the gates on. The register-filter
probe read eleven routes before and after a candidate arrived, and nine
didn't move. The two that should move did. The suite is 1,324 passed,
0 failed, with the gates off. Deployed to all four cluster tenants with the
migration's own count on each. The owner turned the gates on for
`staging`, rehearsed the demo, and the demo on 8 October ran as written.

The one defect in the run was mine: Turnstile on the cluster blocks every
scripted sign-in. That was known from report 56 and was not in a
"Needs the owner" block. §6 handles it properly this time.

**The ruling this handoff rests on.** §4.6 of the evaluation ruled for a
separate `nrs.asset.candidate` model, because a flag on `nrs.asset` would
mean every report, count and dashboard filters on it forever. Report 57
answered that objection better than the ruling expected. The filter lives
in **one** place, `nrs.asset._search`. New code is filtered by default, and
the probe proved it on every route that lists or counts. The failure mode
is now the safe one: code that forgets the context flag *can't find a
candidate*. It doesn't *show* one. Rebuilding the chain on a second model
would cost a week, lose the in-flight candidates on `staging`, and buy one
property we already have.

**So §4.6 is reversed. The candidate stays a state on `nrs.asset`.** This
handoff turns the scaffolding into the product:

- take the "SCAFFOLDING" labels off;
- make every suite pass with the gates **on**;
- close the findings 57 left open;
- add what the old 58 had that 57 doesn't: identification mode per class
  (Section 12) and the role-exclusion table.

Nothing a tenant sees changes while its switch is off.

---

## 1 · The word comes off

- `asset_gates.py`'s module docstring: rewrite it as the design, not as an
  apology. Keep the paragraph on the one table and the one method. Replace
  "REPLACED BY HANDOFF 58" and "Do not build on it" with the sentence that
  the register filter in `_search` is load-bearing (P8) and why.
- Report 57's title, the `CLAUDE.md` gotcha and the `DECISIONS.md` entry:
  add a line each saying *kept by handoff 58; see evaluation §8*. Don't
  rewrite history; append.
- Grep the tree for `SCAFFOLDING`, `scaffolding`, `replaced by 58`,
  `handoff 58 replaces`. Print the count before and after. The count after
  is zero outside `docs/handoffs/5[78]*` and `_superseded/`.

## 2 · Green with the gates on

NRS will run with the switch on. Report 57's switch-on run was
`91 failed, 1231 passed, 9 skipped`. The red was predicted and correct: the
suites create an asset through `POST /assets`, get a hidden, unlabelled
candidate, then try to list it, tag it or count it. That was acceptable for
one night. It isn't acceptable for a product, because a suite that only
passes with the switch off proves nothing about the tenants that matter.

The fix is in the fixtures, not in the tests' assertions:

- A test that is **about** an asset already on the register gets one. It
  either drives the seven gates through a shared helper or creates the
  record at `registered` the way the migration did for existing assets.
  Pick one helper, name it in DECISIONS, and use it everywhere.
- A test that is **about** the receipt path (`POST /assets` as the INT-03
  credential) asserts the switch-dependent answer: `captured` when on, the
  old response when off. Parametrise it over both.
- **No test is deleted, skipped or loosened to get there.** If a test's
  meaning changes under the switch, say so in the report, with the test's
  name.

Target: the full pytest suite, the three module suites and the browser
suite **green on both switch states**. Print both denominators. They must
be the same set of tests: if a count differs, explain the difference.

## 3 · The findings 57 left open

Each one is closed, or kept with a sentence in DECISIONS saying why.

- **D3, the affix refusal shape.** A no-two-gates refusal at the affix step
  answers `400 validation_failed`; every other gate answers
  `409 segregation_of_duties`. Make the affix one `409` with the same code
  and the same sentence. Every other affix refusal keeps its existing shape.
  CHANGELOG entry. The SPA's affix dialog shows the sentence either way;
  assert it in spec 57.
- **P4, SAP's number overwriting the maker's.** When INT-06's answer carries
  an asset number different from the one the Register Maker typed, **don't
  replace it silently**:
  - keep the maker's number on the record;
  - store SAP's next to it;
  - raise a discrepancy on the existing SAP reconciliation surface, naming
    both numbers, the maker and the checker.
  - Equal numbers: the label changes from *entered by hand* to *confirmed by
    SAP* and nothing else happens.
- **P5, a custodian on a candidate.** Assigning a custodian to a unit that
  isn't on the register is **refused**, with the sentence *"This unit is
  not on the register yet (waiting on <who>); a custodian can be assigned
  once it is registered."* The same goes for a move, a transfer and a
  disposal raised against a candidate. Check every writer, and list them in
  the report with the refusal driven for each.
- **P8, the filter is load-bearing.** A tenant whose module wasn't upgraded
  fails every asset list, not just the new column. The fan-out before the
  restart is already the rule. Make the failure **say what it is**: if
  `register_state` is missing on a tenant, the API's health or readiness
  answer for that tenant names the missing upgrade, instead of every list
  failing with a database error. Do it in the place that costs least, and
  say where.
- **D6** (`iad_approver` in `waiting_on`): fix the endpoint reference so the
  published list matches what's served.
- **P1, D5, INT-05:** correct as they are. Make sure each has its DECISIONS
  line. No code.

## 4 · Identification mode on the class — Section 12

This is the owner's ruling from evaluation §7/4.1: "no serial, no receipt"
stays for serialised items, and furniture follows Section 12.

- `nrs.asset.category` gains two fields:
  - `identification_mode`: Selection `serial` / `tag_id` / `pool`, default
    `serial`;
  - `class_attributes_schema`: JSON listing the mandatory capture fields.
- Default schemas:
  - `serial`: make and model;
  - `tag_id`: description, make or brand, model or catalogue reference,
    colour, material, dimensions (AD-32).
- Seed defaults per D11:
  - vehicles and electronics: `serial`;
  - furniture: `tag_id`;
  - nothing defaults to `pool`. The owner skipped the threshold decision,
    so `pool` is declared but **refused at receipt** with *"Pool
    identification is not built yet (Addendum A Phase E)."*
- A change of mode affects new receipts only (AD-31). Pin that with a test.
- Both fields are published on `GET /api/v1/asset-categories`, additive,
  with a CHANGELOG entry. Vendra 54 reads them.
- Settings: an Asset Controller (`settings:classes`, already granted to the
  role) can change a class's mode on the categories screen. The change goes
  to the configuration record.

What `tag_id` changes in the chain, and nothing else:

- **Receipt (`POST /assets`, gates on):** a `tag_id` unit arrives with no
  serial and with the schema's attributes. Refuse a `tag_id` unit missing an
  attribute, naming it.
- **Defence in depth:** refuse a `serial`-mode unit with no serial, using
  the same sentence Vendra uses. Vendra already enforces this; Cadra now
  does too.
- **Serial uniqueness:** ignores empty serials. It already should, so prove
  it.
- **IAD verify:** unchanged. The four checks and evidence don't depend on a
  serial.
- **Affix (Act 6):** for a `tag_id` unit there's no manufacturer serial to
  scan. The dialog asks for **the label reading only**, plus a tick:
  *"The item matches: <description, make, colour>."* The refusal on a wrong
  label is unchanged. The event records which check was used.
- **The asset code is the identity** from tagging onward. The label already
  carries it (57's ruling 2).

## 5 · The role-exclusion table — Addendum A §4, rule 2

Rule 1 (no one fires two gates on one unit) is in 57. Rule 2 stops the
wrong combinations being **granted** in the first place.

- A new model `nrs.role.exclusion` with `group_a`, `group_b`, `active` and
  `reason`.
- Seeded defaults:
  - Store (Asset User / Asset Officer) with any IAD, Asset Controller,
    Tag-Issuing Unit, Register Maker or Register Checker role;
  - Register Maker with Register Checker;
  - IAD Officer with IAD Approver.
- Enforced where grants happen, beside the existing `access_guard.py`
  checks, in the model under every writer. The refusal names both roles and
  the reason. The Users page shows it verbatim.
- **Before seeding, measure:** on each local tenant and on `staging`, count
  the users who already hold an excluded pair. The demo personas will
  (Halima is Store Officer in Vendra and Asset Officer in Cadra; check
  Babatunde, Chukwudi and Oluwaseun). An existing pair is **not** revoked.
  It's listed in the report and on a *Conflicting grants* view for
  `settings:write` holders, so the owner decides.
- Editable on the Settings surface by `settings:write` holders. Every
  change goes to the configuration record.

## 6 · Turnstile, said this time

**Needs the owner.** The cluster's `/api/v1/auth/login` requires a
Turnstile token, so nothing scripted can sign in to `staging`, `gtb`,
`jaizbankplc` or `lasg`.

- Every automated proof in this handoff runs on `test19`.
- The deployed check on `staging` is the owner's, in the browser, after the
  merge and the deploy.
- Write the owner's check as a short numbered list at the top of the report:
  - sign in as the administrator persona;
  - confirm the switch still reads *on*;
  - push one unit through all seven steps;
  - see the register count move only at the end;
  - change one class to `tag_id` and receive a unit of it.

**Don't disable Turnstile anywhere on the cluster**, not even briefly.

The switch stays as it is on every tenant: on for `staging`, off for the
rest. Turning it on for an NRS production tenant is the owner's decision
after go-live readiness (§9). This handoff doesn't do it.

## 7 · What must not change

- With the switch off, every response is byte-identical to after 57, except
  the additive category fields. The full suite with the switch off is the
  proof.
- INT-02 (the goods receipt to SAP) and Vendra's side of INT-03: no
  contract change. Vendra 54 adds attributes for `tag_id` lines. The route
  and the idempotency key stay as they are.
- SAP owns depreciation: candidates stay invisible to the depreciation
  module.
- Existing grants: nothing is revoked (§5).

## 8 · Verification

1. The full pytest suite, the three module suites and the browser suite,
   **switch off, then switch on**, on `test19`. Both denominators printed.
   Zero failures on both. Any count difference explained.
2. The scaffolding grep, before and after.
3. Each finding in §3 driven over HTTP with its answer printed, including
   the P5 refusal on every writer you list and the P8 message on a tenant
   with the column dropped (on a throwaway copy, never a real tenant).
4. Section 12:
   - a `tag_id` unit received with its attributes and no serial, pushed
     through all seven gates, the affix step taking the label plus the tick;
   - a `tag_id` unit missing colour, refused with "colour" named;
   - a `serial` unit with no serial, refused;
   - a `pool` unit, refused with the Phase E sentence;
   - a class's mode changed, with existing candidates of that class
     unaffected.
5. Rule 2:
   - the conflicting-grants count per tenant, printed before seeding;
   - each default exclusion refused at grant, over the API and on the Users
     page;
   - one exclusion toggled off, the grant going through, the configuration
     record showing it.
6. Spec 57 extended with the `tag_id` path and the D3 sentence. It runs
   green as the personas on `test19`.
7. The fan-out to every local tenant; then the deploy steps for the owner,
   written out exactly as in report 57's addendum.

And the standing sentence check.

## 9 · The question for the report

**What stands between this and switching it on for NRS in production?**
List everything you would want true first, each item with an owner (us,
NRS or SAP). Include at least these:

- named people for every gate;
- the class list deciding `serial` versus `tag_id`;
- the conflicting grants from §5;
- INT-06 against the real SAP endpoint;
- what an in-flight candidate does if the switch is turned off.

Add anything else you find. That list becomes the go-live checklist.
