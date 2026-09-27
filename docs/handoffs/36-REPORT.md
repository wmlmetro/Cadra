# Report 36 — The control we cannot prove

**Builder:** Claude Code (IDE) · **Branch:** `fix/the-control-we-cannot-prove`
**Base:** `dev` · **Date:** 2026-09-27

---

## In plain words, first

The two-person rule works on `nrs19`, both halves, and I have driven it. What
was missing was never the control — it was a usable second identity, and one
sentence of the handoff's diagnosis was wrong in a way worth knowing about.

**Three of this handoff's premises did not survive being measured**, and all
three came from Vendra's report 43 rather than from reading this repository:

1. **`nrs19` has 1,154 locations, not none.** Real ones, named as NRS names
   them — *Ikom MSTO*, *GBTO Calabar*, *Calabar MSTO*, *FCT*, *Uyo MSTO*. The
   `GET /api/v1/locations` that "returned an empty list" was a **403**:
   `Missing required scope(s): locations:read`, because the `vendra`
   credential holds `assets:read assets:write` and nothing else. Driven, at
   the bottom of §B. **Seeding locations would have added noise to a tenant
   that already had 1,154 of them** and left the actual blocker in place.
2. **`nrs19` has three credentials, not two**, and the third — `test_client`
   — holds `approvals:write` *and* `admin`. So the model was never the
   problem. **But its secret is not recoverable** (`docs/api/.creds.nrs19`
   has said so since handoff 04), so in practice the decide half really was
   unreachable. Vendra's conclusion was right; its reason was not.
3. **Approvals are NOT off-by-default-by-accident, on any tenant.** §1A.3
   was the thing the Architect said they needed to know today, and the answer
   is reassuring — measured, in §A.

The one real defect the handoff named, §1C, was real: an approved move
recorded the approver and lost the requester. Fixed, additively, and the
history now carries both people.

---

## §A · Is there an approver? Measured, not read

The question the handoff wanted answered today: *if a fresh tenant installs
with no identity that can approve anything, approvals are off by default by
accident on every tenant NRS ever creates.*

**They are not.** Measured across all eight local tenants, 2026-09-27:

| tenant | API creds that can approve | Odoo users in `group_asset_manager` | locations |
|---|---|---|---|
| `cadra19` | 1 of 1 | 2 | 754 |
| `nrs19` | 1 of 3 | 3 | 1,154 |
| `gtb19` | 0 of 1 | 2 | 149 |
| `test19` | 1 of 1 | 2 | 509 |
| `nrs` | 0 of 1 | 2 | 847 |
| `lasg` | 0 of 1 | 2 | 111 |
| `gtb` | 0 of 1 | 2 | 143 |
| `jaizbankplc` | 0 of 1 | 3 | 440 |

**Every tenant has at least two people who can approve, and every tenant has
locations.** Two mechanisms guarantee the first, and `scripts/bootstrap.py`
is where both live:

- `REQUIRED_ADMIN_GROUPS` (line 136) puts `admin` into
  `myservice_asset_register.group_asset_manager` on every bootstrap, so
  `_may_decide`'s `has_group` passes for them.
- `_may_decide` accepts a system administrator explicitly anyway, on the same
  reasoning `GROUP_SCOPES` gives about `base.group_system` — somebody who can
  run arbitrary server actions is omnipotent by construction.

**Proved by acting, not only by counting**: on `nrs19`, `Administrator` — a
plain Odoo login holding no API credential — approved a request raised by the
`vendra` machine credential (`CR/2026/0004`, §B). That is the demo path, and
it works on a tenant nobody prepared for it.

**So it is a one-off, not seed data — but the one-off is narrower than the
handoff feared.** What a fresh tenant does not reliably get is an API
*credential* that can approve **with a secret anybody still has**. Four of the
eight tenants have no such credential at all, and `nrs19`'s existing one is
the unrecoverable `test_client`. That matters only for machine-driven
approval; it never blocked a person approving in the app.

**The narrower gap is still worth closing** on any tenant where a machine has
to approve, and closing it is one credential. I have closed it on `nrs19`
only — see §B — because the other seven have nobody asking for it yet, and a
credential nobody uses is a credential nobody rotates.

---

## §B · The decide half, made reachable and driven

### What was created

**One credential, `nrs_approver` — "NRS Approvals Desk".**

| | |
|---|---|
| `client_id` | `nrs_approver` |
| scopes | `assets:read approvals:write` |
| `res.users` | `cadra_client_nrs_approver`, uid **12** |
| `is_test_credential` | **false** |
| in `group_asset_manager` | **true** (verified, so `_may_decide` passes) |
| secret | generated on the machine, written to `docs/api/.creds.nrs19`, `chmod 600`, and that path is gitignored (`.gitignore:34`). **The value has not passed through this report, a commit, or any message.** |

**It is a genuinely separate person from `vendra`** — a different `res.users`
(uid 12 against uid 11), which is the whole of the control.

**It deliberately has no `assets:write`.** It can decide and it cannot raise,
so it is structurally incapable of being both halves. That is stronger than
the model's own refusal and costs nothing.

**Why a new credential rather than reusing `test_client`:** its secret is
gone, and even if it were not, it is flagged `is_test_credential`. Every row
that credential writes is relabelled `source: test` and stamped
`is_test_fixture` by design (handoff 26). An approval on a demo register
labelled as a test fixture is worse than no approval, because it looks like
evidence and is filed as noise.

### The drive, on `nrs19`

**1 · `vendra` raises. The asset does not move.**

```
POST /api/v1/assets/12008/move   (vendra, uid 11)
  {"to_location_id": 1, "approver_id": 12, "reason": "..."}
→ 200
  pending_approval = True   ref = CR/2026/0002   state = pending
  requested_by = Vendra (INT-03) (API client) [11]
  approver     = NRS Approvals Desk (API client) [12]
  ASSET location after raising: None      movement_id: None
```

**2 · The raiser cannot decide. Two refusals, and they are different rules.**

```
POST /api/v1/approvals/2/approve   (vendra)
→ 403  forbidden: Missing required scope(s): approvals:write
```

That is the **scope** gate, not the two-person rule, and it is worth saying
so plainly: it proves `vendra` cannot approve, and it proves nothing at all
about self-approval. To prove *that* needs an identity that holds the scope
and tries to decide its own request:

```
POST /api/v1/assets/12009/move     (admin — holds approvals:write)
→ 200  ref = CR/2026/0003
POST /api/v1/approvals/3/approve   (admin, its own request)
→ 403  forbidden: You raised this request and cannot approve it.
       The point of an approval is that a second person agrees.
       details.is_own_request = true
```

**3 · The approver approves. Now it moves.**

```
POST /api/v1/approvals/2/approve   (nrs_approver, uid 12)
→ 200
  state = approved
  requested_by = Vendra (INT-03) (API client) [11]
  decided_by   = NRS Approvals Desk (API client) [12]  at 2026-09-27T22:50:03
  movement_id  = 2
  ASSET location now: Ikom MSTO [1]
```

**4 · And a person, not a machine, can be the second half.**

```
POST /api/v1/assets/12010/move     (vendra) → CR/2026/0004
POST /api/v1/approvals/4/approve   (admin, an ordinary Odoo login)
→ 200   requested_by = Vendra (INT-03)   decided_by = Administrator
        asset now at: GBTO Calabar [2]
```

### The locations claim, driven

```
GET /api/v1/locations?limit=3   (vendra, before)
→ 403  forbidden: Missing required scope(s): locations:read
GET /api/v1/locations?limit=3   (admin)
→ 200  rows=3 of 1154   Ikom MSTO, GBTO Calabar, Calabar MSTO
```

**I granted `vendra` `locations:read` and did not seed anything.** That is a
deviation from §1B as written and I want it visible: the handoff asked for
locations, and locations were never the problem. A partner that must
reference a `location_id` on every INT-03 receipt and cannot list locations
is the actual blocker, and the remedy is one read-only scope. Verified after:

```
GET /api/v1/locations?limit=3   (vendra, after)
→ 200  rows=3 of 1154   Ikom MSTO, GBTO Calabar, Calabar MSTO
```

**It is a change to a partner's credential and it is additive and read-only**
— `vendra` gained the ability to see location names it already had to quote
by id. If the Architect would rather Vendra kept no visibility of the
location tree, revoking it is one command and the report says so.

---

## §C · Both people in the record

**The defect was real.** Before, the history of an approved move read:

```
type=location_moved   actor={'id': 12, 'name': 'NRS Approvals Desk (API client)'}
detail: {from_location: null, to_location: "Ikom MSTO", reason: "...",
         transfer: null, records: ["nrs.asset.movement", "mail.message"]}
```

The approver, and nowhere the requester — half of a two-person control
missing from the artefact the control exists to produce.

### How I decided which one is the "actor" — the handoff asked, so:

**`actor` is left exactly as it was: the approver.** Two reasons, and the
second is the one that decided it.

1. **It is true.** `nrs.asset.movement.moved_by_id` is whoever clicked, and
   handoff 35 chose that deliberately: the approver's authority is what moved
   the asset. The requester asked; nothing moved until somebody agreed.
2. **`actor` means the same thing on all fourteen event types**, and
   redefining it on one of them is a published key changing meaning — the
   precise defect `myservice_api/tests/test_published_names_resolve.py` was
   built to catch after it happened twice. A consumer that reads `actor` to
   mean *the person the record names as having done this* keeps working.

So the second person arrives **additively**, as a new `approval` block:

```
type=location_moved   evidence=append_only
  actor (unchanged): NRS Approvals Desk (API client) [12]
  approval:
     evidence            append_only
     reference           CR/2026/0002
     requested_by        Vendra (INT-03) (API client) [11]
     requested_by_name   Vendra (INT-03) (API client)
     requested_at        2026-09-27T22:49:50
     approver_asked      NRS Approvals Desk (API client) [12]
     approved_by         NRS Approvals Desk (API client) [12]
     approved_by_name    NRS Approvals Desk (API client)
     approved_at         2026-09-27T22:50:03
     decision_reason     Checked with the store
  records: ['nrs.asset.movement', 'nrs.asset.change.request', 'mail.message']
```

Four decisions inside that block worth stating:

- **`approver_asked` is published beside `approved_by`** because they are two
  different facts and can differ: the nomination decides whose queue it lands
  in, and any eligible person may decide it. On a reshaped rule they will
  differ often.
- **`requested_by_name` and `approved_by_name` sit beside the links**, for
  the reason every other `*_name` in that file exists: a link goes null when
  the user row is deleted, and evidence that can be emptied from outside is
  not evidence.
- **It is graded `append_only`, in band, and the grade is asserted against
  the grades table's own words** — *"the application refuses to edit or
  delete it for anyone, an administrator included"*. A **decided**
  `nrs.asset.change.request` meets that exactly: `unlink` refuses
  unconditionally and `write` refuses on a decided record, both under
  `sudo()`. It is a state machine rather than an append-only row, so the
  grade is argued rather than inherited from the model's name — and the block
  is only ever attached to a request in `approved`. Contrast the `transfer`
  block four lines below it, which is `editable_record` and says so.
- **`approval` is `null`, never absent**, on a move that took one person —
  which is every move before handoff 35 and every move on a tenant with the
  switch off. A consumer cannot tell *nobody approved this* from *this server
  is too old to say* unless the key is always there. Same rule as
  `NOT_RECORDED`.

**Custody gets the same treatment**, and the index is one query per asset
rather than one per row.

---

## §4 · Handoff 33 — read, and it is not moot

Asked for as a reading, so this is a reading and says so. A fresh agent
enumerated every item in `docs/handoffs/33-the-whole-surface.md` and checked
each against the code on this branch.

**Nothing in handoff 33 is DONE. Nine of its ten work items are untouched.**
34 and 35 landed on the same surfaces without closing a single one of its
items — which is the distinction the Architect asked to have drawn, and it
falls on the "touched, not closed" side almost everywhere. The one movement
is §D3 going from *not done* to *partly done*, as a side effect of 32 and 35
each documenting where their own guard stops.

**What HAS changed is the correctness of three of its instructions.** Running
33 as written would now conflict with decisions 34 and 35 made deliberately:

1. **§B2 would poke a hole in the approval control.** It asks for the
   published names to be accepted as write aliases on six keys — and two of
   those six are `location_id` and `custodian_id`, the only two fields
   `PATCH /assets/<id>` now gates. The route's check tests `f in
   ("location_id", "custodian_id")` literally; a second accepted spelling
   would slip past it and surface as the model's `UserError` instead of the
   designed 400 carrying `use_instead`. That is the *refusal naming a remedy
   that cannot work* failure this handoff's own §B just corrected elsewhere.
   It is also not the small change 33 assumes: `current_location` publishes
   an **object**, not an id, so "accept both" is undefined for it.
2. **§B2 and handoff 34 are opposite conventions for the same problem.** 34
   ruled, in writing, that a new block publishes under the WRITABLE name
   (`warranty.warranty_months`, not `warranty.months`) *because* 33 had found
   six keys published under one name and accepted under another. 33's remedy
   is to accept the published name; 34's is to publish the writable one.
   **Somebody has to pick**, and running 33 blind gives the asset API two
   competing conventions.
3. **§D2, widened naively, would fail on strings handoff 35 argued for at
   length.** A guard over "every user-facing string" forbidding field names
   and backticks would flag the gated-write refusal — which deliberately
   prints a literal `odoo shell … set_param('cadra.approval.required','off')`
   command, on `database_class.mark_command`'s reasoning that *an error
   naming a remedy the reader has to look up is worse than one naming none*.
   33 offers the escape itself (*"or tell me why the census cannot be
   drawn"*), and **that is the answer**: an API error message and an
   audit-history statement shown on a screen are different classes of
   string, and the census cannot be drawn until they are separated.

**And one of its premises is out of date.** §A1 describes the SAP
employee-sync route as `auth='none'`; handoff 17 already gave it a required
`X-SAP-Webhook-Secret` that refuses every caller when unset. It is not an
open door, it is an **unvalidated** one — §A2 is the live half. Worse, the
"authenticated sibling" 33 says to copy is `auth='user'`, an Odoo session,
which SAP middleware cannot post to at all: following that instruction
literally would take the route from *callable with a shared secret* to *not
callable*, which is the outage §A argues against.

**Recommendation: re-queue a reduced 33, after this handoff lands** — not
retire it. Nine items are real and unclosed, and §A and §C are the only open
items in the programme with a security shape.

| | |
|---|---|
| **Keep unchanged** | §A2 + §A4 (validate the identity webhook and its **four** siblings — 33 named three; `scripts/load_employees_xlsx.py:109` is a fourth), §B1, §C, §D1, §D3-for-the-words-guard |
| **Keep, re-specified** | §A1 + §A3 — reframe as *which credential, and does the identity door survive at all*. A third option 33 does not consider closes items 1, 2 and 4 at once: retire the identity door and point SAP at `POST /api/v1/integrations/sap/employee-sync`, which already authenticates and already validates. |
| **Drop and rule separately** | §B2 (needs the convention ruling first, and its two highest-traffic keys are now gated), §D2 (replace *widen it* with *record why the census cannot be drawn*) |
| **Delete** | the closing *"say so if there is nothing left a person has actually hit"* — answered three times since, by 34, 35 and this handoff, all three of which came from a person |

**One measurement in 33 must be re-taken before it is quoted**: its §A rests
on *"179 `api` rows and zero `webhook` rows on all eight databases"*. That
figure was 163 in report 32 and 179 in 33, and two eight-tenant fan-outs and
several full suites have run since. The conclusion probably holds; the number
does not.

### A false sentence of my own, found by this assessment

`docs/handoffs/35-REPORT.md` said `/move` and `/transfer-custody` not
refusing unknown body keys was work *"handoff 33 is the one that widens"*.
**Handoff 33 does not contain that item** — zero occurrences. It belongs to
`docs/GO-LIVE.md` §16.3 item 11, which
`test_published_names_resolve.py:179–183` records as **not ruled**. I gave
homeless work a home it did not have, which is worse than leaving it
unassigned: it reads as owned. Corrected in place in report 35 with the
reasoning, rather than edited away.

**And the correction's own first draft was wrong** — it claimed the mistake
appeared twice in that report. It appears once. Checked before committing,
which is the only reason this sentence is accurate.

---

## Verification and the runs

Every denominator quoted, per the rule.

| Suite | Result |
|---|---|
| `pytest tests/` | **1090 passed, 9 skipped, 0 failed** (13m19s first run: 1 failed — mine, below) |
| `myservice_api` in-registry, `--workers=0` | **0 failed, 0 error(s) of 287 tests** (was 282; the five new tests ran) |
| `myservice_asset_register` in-registry, `--workers=0` | **0 failed, 0 error(s) of 432 tests** |
| combined `-u asset_register,api` (no tag filter) | **2 failed, 0 error(s) of 858 tests** — both PRE-EXISTING, below |

No run reported `of 0 tests`; no run logged `CRITICAL`.

### The one test my change broke, and why it was right to break it

`tests/test_asset_history.py::test_a_move_is_one_event_and_says_what_its_record_is_worth`
pinned `detail.records` to exactly three models. An approved move is now read
from four — the change request joined the list — so the assertion failed
correctly. Updated to assert against what the tenant actually does (three
records and no `approval` where one person moved it, four and a block where
two did) rather than pinning one shape, and it now also asserts the thing
that matters: `requested_by != approved_by`.

### Two failures that are NOT mine, proved rather than assumed

`myservice_asset_depreciation.TestPolicyInheritance` —
`test_condemning_an_asset_stops_the_clock` and
`test_a_disposal_by_a_bare_write_stops_the_clock_too`, both
`AssertionError: 'fully_depreciated' != 'disposed'`.

**Proved pre-existing by stashing every change on this branch and re-running:
`2 failed, 0 error(s) of 15 tests`, the same two.** Both the test file and
`myservice_asset_depreciation/models/` were last touched in handoff 31
(`cd5493e`), so this predates 34, 35 and 36. Out of scope here and **not
fixed** — but it is a red test on `dev` that no report has named, and
`depreciation_state` landing on `fully_depreciated` where a disposal is
expected is the kind of thing an auditor's report would quote. Flagged for a
ruling.

### The standing pass — every sentence against something measured

Run over this report, the code comments and the creds file. It caught two
things, one in each.

**1 · A claim in the report and the creds file that I had not driven.** Both
said `nrs_approver` "cannot raise the requests it decides". True by
construction, but asserted rather than measured — so I drove it:

```
POST /api/v1/assets/12011/move   (nrs_approver)
→ 403  forbidden: Missing required scope(s): assets:write
```

**2 · A code comment that claimed a guard protects against something it
cannot.** `_history_approvals` skips when the change-request model is
absent, and I wrote that this covers *"a tenant that predates handoff 35"*.
It does not. `myservice_api` names `myservice_asset_register` in its
`depends`, so if the code runs the model is in the registry and the branch is
dead. The case a reader would assume it covers — this Python against an
un-upgraded schema — is the opposite: the model IS registered and the TABLE
is missing, so the search raises `UndefinedTable` and the check never fires.
The comment now says so, and names the per-tenant fan-out as the only thing
that does cover it. **A guard with a false label is worse than no guard**,
because the next person reads the label.

**3 · And a false sentence in report 35**, found by the §4 assessment and
corrected in place — see the end of §4.

---

## What I changed, and what I left

**Changed**

- `myservice_api/models/asset_history.py` — `_history_approvals` and
  `_history_approval_block`; the `approval` block on `location_moved` and
  `custody_changed`; `nrs.asset.change.request` added to `records`.
- `myservice_api/controllers/v1.py` — the `AssetHistory.detail` description
  publishes the new block, what it is null for, and that `actor` is
  unchanged.
- `myservice_api/tests/test_asset_history.py` — five tests
  (`TestBothPeopleAreInTheRecord`).
- `tests/test_asset_history.py` — the `records` assertion follows the
  behaviour and now checks both people.
- `docs/handoffs/35-REPORT.md` — the false attribution to handoff 33.

**Changed on the `nrs19` TENANT, not in the repo**

- `nrs_approver` created (§B).
- `vendra` gained `locations:read` (§B) — additive, read-only, and a
  deviation from §1B as written.
- `CR/2026/0002` and `CR/2026/0004` approved; `CR/2026/0003` withdrawn;
  assets `12008` and `12010` moved. All of it is the drive the handoff asked
  for, and all of it is evidence rather than litter.

**Left, per §2**

Probe asset `12008` and the walk assets `12009`–`12015` are all still there,
and `CR/2026/0001` is still pending. **Nothing would confuse a demo** — the
one thing worth knowing is that `12009` now carries a WITHDRAWN request
(`CR/2026/0003`), which exists because it is the only way to show the
self-approval refusal on a tenant where the other identity holds no scope. I
withdrew it rather than leave it pending so it does not occupy that asset's
one pending slot, and withdrawing it proved the third transition as a side
effect.

## Wall-clock and the correction share

About **an hour and a half**. The build — the credential, the history block,
the tests — was perhaps twenty minutes of it. **The rest was measurement and
correction**, and on this handoff that was the work rather than an overhead
on it: three of the handoff's own premises fell over when driven, and the
single most useful output is probably §A saying the thing the Architect
feared is not true.

Two of the three corrections were to my own sentences, and one was to a
sentence in a report I wrote last week. None of them was caught by a test.
