# Handoff 24 — The record starts now

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/access-record`.

> Report 23 stands in full, including the deviation. `Vendra Auditor` was my error — a Frappe role from the sibling repository written into a Cadra acceptance criterion — and `myservice_api.group_auditor` with six read scopes is the right thing to have built instead. The two findings I want kept are not the seven defects: they are **the test file that was never registered**, caught because the denominator did not move, and **`fidelity.tracked` being true for a field another module contributed**. Both are the programme's recurring shape — an instrument that reports more than it measured.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/access-record && git push -u origin feat/access-record
```

**If `dev` does not yet contain report 23's work** — the `feat/audit-logs` PR was unmerged when this was written — branch from `feat/audit-logs` instead, say so in the report, and do not merge it yourself. §A extends the access report, so it needs that code under it.

---

## Why this handoff exists

Report 23's best page is the one that says what the reports **cannot** answer, and the largest entry on it is this: *who was granted or removed from a group, when, and by whom* — specification §13.4, the question the access report exists to answer. Six places it could have been recorded, six measured empty. `res_groups_users_rel` is two integer columns; a grant writes nothing that outlives it.

That is true today and it will be true forever unless something starts writing. **The reconstruction of past grants is NRS's decision** — INT-10 §2.10b holds the three options — but the forward record is not that decision, and every week we wait is a week of the register that can never be recovered. So: the record starts now.

---

## A · Group membership becomes a recorded fact

Model it on `nrs.asset.custody`: append-only, create-only, no `write`, no `unlink`, one row per change carrying the user, the group, the direction, the actor and the timestamp.

**Before you choose where to hook it, enumerate every writer.** Handoff 14 told you the transfer route was the only writer of `custodian_id`; there were six, and recording at the asserted point would have produced a chain with invisible holes. Do not take my list as the list. The ones I know to check, and there will be others:

- `res.users.write` with `group_ids` in the vals — the obvious one.
- **`res.groups.write` with `users` in the vals** — the same change made from the other side, and it does not pass through `res.users.write`.
- `res.users.create` with groups in the vals, and the `create` that follows a signup or an import.
- Group implication — adding a user to a group that implies others changes membership in those too, and the implied rows are what an auditor will ask about.
- Data files, module upgrades and SQL. These will not pass through the ORM at all. **They must not be attributed to a person.**

Report what you found before you report what you built.

**Three properties.**

1. **A change nobody can attribute says so.** `uid 1 __system__` is an upgrade, a cron or the CLI, and the row must carry that as its actor rather than a name. Report 23 measured 100% of every ACL stamp in the estate as `__system__`; a record that renders those as *"the system administrator granted this"* is worse than no record.
2. **The record knows when it begins, per tenant, by measurement.** The access report's `fidelity` block gains the earliest row it holds, read at request time — not a constant, not a migration date. Before that instant the honest answer is still *cannot answer*, and the report must keep saying it for periods that fall wholly before the start.
3. **It is a record, not a mechanism.** Nothing about who may grant what changes in this handoff.

**Acceptance.** A grant made through the user form, a grant made through the group form, a grant made in `create`, and a removal, each produce exactly one row with the right actor. A module upgrade that moves membership produces rows attributed to `__system__`. The access report's `summary.group_changes_in_period` stops being a structural zero on a tenant where a change has since happened, and stays a structural zero on one where none has. A period ending before the first row still answers *cannot answer* — **and there is a test for that, because it is the one an auditor will hit for the next twelve months.**

Fan out to all eight tenants. Say in the report what the start instant is on each.

## B · Test fixtures in a customer's register

Report 23 §8 leaves an asset on `jaizbankplc` — `H23 disposal probe`, id 8396, with an **approved disposal** — and discloses that `tests/test_audit_logs.py` creates `pytest-approval-<epoch>` assets.

Two things, in order. **First, tell me what a test run writes into which database**, measured rather than assumed: if the suite can reach a tenant holding real data, that is the finding and the rest of this section is secondary. **Second, deal with 8396.** Disposal approval may well be one of the things this system deliberately cannot undo; if it is, say so and mark the asset for what it is rather than pretending it away. A fabricated approval sitting unlabelled in a live register is the same defect as a fabricated custody row, which we have already fixed once.

## C · `docs/DECISIONS.md` has entries that later work overturned — mine to correct, yours to apply

Line 101 asserts that the Security Command Center and the barcode station's backend client action are **dead on Odoo 19**. Report 16 mounted them in a real browser. **The entry is withdrawn.** Replace it with what was measured, cite report 16, and keep the original claim visible as withdrawn rather than deleting it — a decision log that quietly loses its wrong entries cannot be used to check anything.

Then sweep the rest of the file the same way: an entry a later report disproved, corrected in place with the evidence and the report number. List every one you change in the report. If you find none beyond line 101, say that — I have been carrying two more in my head for six handoffs and I would rather learn they are already right than have you hunt for them.

## D · `Finance Officer` / `finance_viewer`

Specification §3 names two roles. Report 23 built the first. The second — *"read-only access to asset financial data"* — still does not exist, and `INT-10-audit-access.md` §4 says so in two places.

**Do not build it on my say-so.** Tell me what "asset financial data" resolves to in this codebase — which fields, which scopes, whether `group_auditor`'s six read scopes already cover it — and whether the honest answer is *"this is `group_auditor` under another name"*. If it is, the deliverable is a line in INT-10 saying so, not a second group.

---

## Report

`docs/handoffs/24-REPORT.md`. Short. In it:

1. **Every writer of group membership you found**, and which ones the record covers.
2. The start instant per tenant, and anything about the fan-out that surprised you.
3. What a test run writes, and where.
4. Whether §D is a group or a sentence.
5. Wall-clock, and the correction share.
