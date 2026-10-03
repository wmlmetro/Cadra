# Handoff 37 — The doors, and the two red tests nobody named

**Branch:** `fix/the-doors-and-the-red-tests`
**Report:** `docs/handoffs/37-REPORT.md`
**Runs after** `fix/the-control-we-cannot-prove` is merged.

> ## RUN THIS ONE. Premises re-checked 3 October.
>
> This was written on 30 September and **eleven handoffs have landed since** (38–48). I re-checked its three load-bearing premises today before handing it over:
>
> - **`myservice_asset_depreciation` is untouched since this was written** — no commits — and both named tests are still in `test_policy_inheritance.py`. §3 stands.
> - **`myservice_identity` has one commit since**, handoff 42's role guard, which does not touch the webhook. The door is still `auth='none'` with the `X-SAP-Webhook-Secret` header, exactly as report 36 described it.
> - **The authenticated sibling still exists** at `POST /api/v1/integrations/sap/employee-sync`. §A's ruling is still available.
>
> **Anything else in here that smells stale, verify before obeying and report the drift.** Five weeks is long enough for a premise to rot, and this programme's worst instructions have all been ones nobody re-measured.
>
> One thing that did change and that §A and §B must not fight: handoff 42 added `access_guard.py`, which refuses any `base.*` group over the API and refuses self-granting, under every writer. If the identity work creates or alters users, it meets that guard. That is intended — do not go round it.

---

## 0 · Report 36, accepted — and three of my premises were wrong

Accepted in full. The two-person rule is proved on `nrs19`, both halves, including a person as the second half, which is the demo path.

**Three of the premises I gave you did not survive contact with the tenant, and all three were mine to check and I did not.** They came from Vendra's report 43, about *your* system, and I turned them into instructions without asking you to measure them first.

1. **`nrs19` has 1,154 locations, not none.** The "empty list" was a **403 — `Missing required scope(s): locations:read`**. An empty list and a refusal are different answers and the difference was one status code that nobody read.
2. **Three credentials, not two**, one of them holding `approvals:write` all along. Your conclusion — that the decide half was unreachable in practice — was right for a different reason: the secret is gone.
3. **Approvals are not off-by-default-by-accident**, on any of the eight tenants. That was the thing I said I needed to know today, and the answer is the reassuring one, measured rather than assumed.

**Had you followed §1B as written you would have seeded locations into a tenant that already had 1,154 of them** and left the real blocker standing. You measured before obeying. Keep doing that; it is worth more to this programme than anything either of us has built.

**Your `locations:read` deviation is ruled: keep it.** A partner required to quote a `location_id` on every INT-03 receipt, and unable to list locations, is the relationship backwards. Additive, read-only, correct.

**And your §C reasoning on `actor` is right and I would not have got there.** Not redefining a published key on one of fourteen event types — and adding the second person as a block that is `null` rather than absent, so a consumer can tell *nobody approved this* from *this server is too old to say* — is exactly the discipline that stops the next false statement.

---

## 1 · The naming convention, ruled — so 33 §B2 stops blocking

You found the collision: handoff 33 says *accept the published name as a write alias*; handoff 34 ruled *publish under the writable name*. You are right that somebody has to pick.

**Handoff 34's convention wins. One name per field, published and writable.** The reason is the one you supplied: a second accepted spelling would slip past `PATCH /assets/<id>`'s gate, which tests `f in ("location_id", "custodian_id")` **literally**, and surface as the model's `UserError` instead of the designed 400. A convenience that opens a hole in the approval control is not a convenience. That it is also undefined for `current_location`, which publishes an object, settles it twice.

**Where a published name and a writable name already differ**, the fix is to publish the writable one, and keep the old published name as a **read-only output alias** where a consumer already depends on it — never as an accepted input. Write the rule into `DECISIONS.md` in those terms so the next person does not have to rediscover it.

**Not in this handoff.** This ruling exists so §B2 can be queued honestly later, not so you do it now.

---

## 2 · Handoff 33, reduced — your table, taken as written

Your assessment is accepted and your table is the plan: keep §A2+§A4, §B1, §C, §D1, §D3-for-the-words-guard; re-specify §A1+§A3; drop §B2 (now ruled above, so it can return) and §D2; delete the closing sentence, which three handoffs have answered.

**This handoff takes only the security-shaped half** — your words: *the only open items in the programme with a security shape.* The rest returns as 38.

### A · The identity door

You found the third option and I am ruling for it: **retire the identity door and point SAP at `POST /api/v1/integrations/sap/employee-sync`, which already authenticates and already validates.** It closes items 1, 2 and 4 at once, and it replaces an unvalidated door with a validated one rather than adding a second guard to the first.

**Two conditions, because this one touches a live integration:**

- **Do not remove the old route in this handoff.** Make the authenticated route provably equivalent first, and leave the old one in place with its behaviour unchanged. Retiring a door SAP may be posting to is an outage, and 33's own §A argues against exactly that.
- **Establish whether anything is actually posting to it, and say how you established it.** Your own §4 flags that 33's *"179 `api` rows and zero `webhook` rows"* is a number that has moved twice and must be re-taken before it is quoted. Re-take it, across all eight tenants, and quote the new figure with its date. If something *is* posting, that changes the ruling and I want to hear it before you go further.

### B · §A2 and §A4 — validate the identity webhook and its four siblings

Unchanged from 33, with your correction: **four siblings, not three.** `scripts/load_employees_xlsx.py:109` is the fourth. An unvalidated dict reaching a model is the defect; the shared secret in front of it is not validation.

### C · §C

Unchanged from 33. Take it as written.

---

## 3 · The two red tests on `dev` that no report has named

`TestPolicyInheritance::test_condemning_an_asset_stops_the_clock` and `test_a_disposal_by_a_bare_write_stops_the_clock_too`, both `AssertionError: 'fully_depreciated' != 'disposed'`, pre-existing since handoff 31 and **proved pre-existing by you, by stashing and re-running.**

**Fix them.** You flagged this for a ruling and the ruling is that it matters more than its size suggests. A condemned asset whose depreciation state reads `fully_depreciated` rather than `disposed` is a wrong number in the register a government auditor reads, and *"the clock stops when the asset is condemned"* is a promise the tests were written to hold.

**Two things I want in the report:** whether the defect is in the test's expectation or in the behaviour — they are different findings and only one of them is a bug in the product — and **why two red tests sat on `dev` through six handoffs without appearing in a single report.** The second question is worth more than the fix. If the suite that runs them is not in the gate, say so; if it is, then something is reading past a failure.

---

## 4 · Verification

The standing pass, reported including what it caught: **every sentence in your code, comments and docs checked against something you measured.** It has caught something every time, including a comment whose label described a guard the branch could never reach.

Specific to this one:

- The equivalence of the two employee-sync routes, driven, both answering the same body the same way.
- The re-taken census, with its date and all eight denominators.
- For §3, the failing assertion before and the passing one after, and a statement of which side was wrong.
- Suites with denominators, and no run reporting `of 0 tests`.

---

## 5 · Not yours, going to the owner today

Your §A table is going to the owner as it stands — it is the clearest picture of tenant readiness this programme has produced, and four tenants having no credential that can approve is theirs to decide about, not ours. So is the question of whether SAP is posting to the identity door at all, which only they can ask.
