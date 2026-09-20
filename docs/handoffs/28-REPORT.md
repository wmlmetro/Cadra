# Report 28 — Where a thing has been

**Branch:** `feat/location-record` · **Base:** `dev` at `a357237` (handoff 27 merged as PR #77).

**Needs the owner:**
1. **The PR merge.**
2. **GitHub billing.** Every workflow on `wmlmetro` has been refused by GitHub since **2026-09-18 14:13 UTC** — *"recent account payments have failed or your spending limit needs to be increased"* — with zero steps run. **CI has not tested this handoff, or handoff 27.** A red X on either PR means *never started*. That also means `uptime-check` has not probed the live sites for two days, and `deploy-dev` will not carry a merge to staging. Everything in §5 was run on this machine and is not a substitute.
3. **On deploy: this is a stored model.** `myservice_asset_register` 19.0.1.15.0 adds a table. The `cadra-upgrade` Job must fan out to every tenant BEFORE the new image serves traffic, or the first asset moved on an un-upgraded tenant is a 500. Done locally on all eight, each verified in its own database.

---

## 0 · Before anything else: do not quote 1,146

You wrote that *"1,146 tracked location changes on `nrs19` and one transfer row"* is the number you will be quoting for the rest of this engagement. **Please don't. I gave it to you, and I never looked inside it.**

It is a true count of rows. **1,145 of the 1,146 were written by Administrator within six seconds** — 2026-08-06, 15:34:24 to 15:34:30 — sixteen minutes after the register was loaded, one per asset: `FCT → North Central / FCT`, `Lagos → South West / Lagos`. It is a script re-mapping locations onto a hierarchy. Nobody moved anything. The one remaining row is OdooBot's, on 6 September.

**What stands, and what does not.** The structural finding stands and is proven by test, not by a count: before this handoff a `PATCH` of `location_id` moved an asset and left nothing but a deletable chatter line. What does not stand is the *scale* — I offered a seeding artefact as the size of NRS's unrecorded moves. I found it only because you asked what a backfill would recover (§3), and the answer on `nrs19` turned out to be *1,145 permanent records of assets that never moved*.

**The lesson is the same one, a third time.** Report 27: *the one claim I did not check against the file was the one that was wrong.* A count is a claim about what the rows ARE.

---

## 1 · Every writer of `location_id`, and which the record covers

Searched for — a dedicated read-only pass, told to assume your list was not the list. It was not: **the two writers that mattered most were not in the Python at all.**

| Writer | Through the ORM? | Recorded? | `source` |
|---|---|---|---|
| `POST /api/v1/assets` | `create` | yes | `api_write` |
| `PATCH /api/v1/assets/<id>` — the quiet door, left open as ruled | `write` | yes | `api_write` |
| `POST /api/v1/assets/<id>/move` | `write` | yes, linked to its transfer | `api_move` |
| `nrs.asset.transfer.action_complete` | `write` | yes, linked to its transfer | `transfer` |
| The bulk importer, new and update lines | `create` / `write` | yes | `direct` |
| `load()` — `scripts/seed_nrs_assets.py`, ~11.9k rows | `create` / `write` | yes | `direct` |
| The seed scripts (hq, gtb, jaiz, lasg, `seeds/nrs_asset_seed`) | `create` | yes | `direct` |
| Odoo **Duplicate** | `copy` → `create` | yes, the twin's own opening row | `direct` |
| A shell or XML-RPC `write` | `write` | yes | `direct` |
| **The Odoo form** | — | **it was never a writer** — see below | `direct` |
| **Deleting a location** | **no — the database does it** | yes, now | `location_deleted` |
| A credential flagged as a test credential | as above | yes | `test` |
| Raw SQL · `_write()` · a restore · anything outside this repo | no | **NO** | — |

**The recorder is the innermost link of both override chains** (`test_fixture` → `sap_asset_events` → `asset_depreciation` → `asset_sap` → `asset.py`), so every module above it has finished with `vals` before it looks, and it compares the STORED value before and after `super()`.

**The database is a writer.** `nrs_asset.location_id` is `ON DELETE SET NULL` and `generic_location.parent_id` is `ON DELETE CASCADE`. Deleting a building empties the location of every asset in every room beneath it — one statement, no `write`, **not even a chatter line**. The asset simply stops being anywhere. No search of the Python finds that; I found it by reading `pg_constraint`. Closed by `generic.location.unlink`, which records each doomed asset as a move to nowhere BEFORE the delete, over `child_of` (the cascade never calls `unlink` on the children), inside a savepoint.

**The Odoo form was never a writer, and your list and my first docstrings both said it was.** `location_id` is `readonly` on the form and filled by the room onchange. Odoo's web client drops a readonly field from the save unless it carries `force_save` — I read it in the 19 image, `record.js` `_getChanges`. So for as long as that form has existed, picking a room **showed a new Location on screen, saved the room, and threw the location away.** A fourth screen saying something that is not so, in Odoo itself. Measured harmless — three of four tenants never use building/floor/room, and on `nrs` all 1,272 agree — and fixed with `force_save`.

**Not covered, said plainly:** the guarantee is Python. No trigger. `tests/test_recorder_bypass_guard.py` now fails on first-party raw SQL that sets `location_id` or `custodian_id`, and on `_write()`; nothing can see a DBA's query or a restore. Every published sentence about this record says *through the application*.

**Not a writer, though it looks like one:** `PATCH {"building_id": …}`. It changes the building and leaves `location_id` where it was, because the derivation is a form onchange that never runs for the API. The movement record correctly reports no move. GO-LIVE §13.4.3 — a question for you (Q2).

**Two things the recorder made worse until fixed.** The importer wrote `location_id` unconditionally on an UPDATE line, so a blank cell — or a name with a typo — wrote `False` and moved the asset to nowhere; with an append-only record underneath, that mistake would have become permanent. Fixed; the line now says *"matched no location, so the asset was left at …"*. And `nrs_hq_seed.py`'s wipe would have died on a raw foreign-key error on every tenant; it now refuses by name, behind its OWN flag — somebody with the custody flag in an old command line did not agree to destroy a record that did not exist when they typed it.

## 2 · What was built

**`nrs.asset.movement`** — custody's twin. `write` and `unlink` raise unconditionally, so they hold under sudo; read-only ACLs for all three groups; `ondelete='restrict'` on the asset; `copy=False`. It holds the instant, who moved it, **the full location paths as they read then** (a rename or a deleted location cannot empty the row), the reason, a `source`, and the transfer document where the move had one. `PATCH` stays open and writes no transfer: a move is not always a transfer, so `transfer_id` is set by `/move` and by a completed transfer and by nothing else. `transfer_reference` is recorded WITH the move, because the document is deletable and the move must outlive its paperwork.

**The four honesty properties, at the source.** An actor is the acting user or null. `tracking_backfill` is in the selection and **nothing writes it** — the label exists before any reconstruction does. `recording_began_at()` is measured from the table. And the history's `fidelity.location` tells every asset that predates the recorder — on a loaded register, nearly all of them — that it was *already somewhere when the recording of moves reached it*.

**In the history** a move made now is `append_only`, with the transfer and the chatter row of the same act folded into one line. **A move made before is graded exactly as it was**: `editable_record` or `chatter`. Both kinds sit in one list and say which they are.

**B1 · Verify records a verifier.** `POST /assets/<id>/verify` — no date, no verifier: today, and the acting user. `last_verified_by` is published and stays out of `_WRITABLE_FIELDS`. **What it buys, plainly: one overwritten column and a chatter line.** It is not an append-only record of verifications.

**B2 · The six provenance fields are tracked — and it was not "one line per field, no migration".** Two guards in `test_snapshot_rollback.py` pull against each other on purpose: a tracked field MUST be in the snapshot's rolled-back list and MUST NOT be in its as-of-today list. So tracking them forced six fields across the boundary of a **published report**, which says of a rolled-back field that *no recorded change since the date means the current value IS the value at the date*. For any date before tracking began — today — that is false. So each database is stamped with the instant tracking began (**eight tenants, eight different stamps — measured, not typed**), and the snapshot classes the six as today's value for an earlier date.

**C · Three screens.** *Legacy Data* → *Provenance*: only what the record holds, or a sentence saying it holds nothing; *"Migrated from FIRS · March 2024"* is gone. `RequestDetail` says *No person recorded*. Evidence labels are buttons that open a legend — tap and keyboard.

**D · Registered:** `require_jwt` discarding scopes is GO-LIVE §14, as an architectural fact. The build trap is in `ENVIRONMENT-FACTS.md`, with a second fact beside it: **the e2e suite is outside the database-class guard and defaults to `jaizbankplc`.**

## 3 · What a location backfill would and would not recover

**Would:** the instant, the author, and both locations by name as they read then, for every tracked change whose message survives.

**Would not:** a first placement — Odoo writes no tracking row on `create`, and **10,439 of `nrs19`'s 11,585 located assets have no location tracking row of any kind**; a reason; whether the author was a mover or a script; anything whose message was deleted.

**And what it WOULD do is the argument against it.** On `nrs19`: 1,145 permanent movement records of assets that never moved (§0). On `jaizbankplc`: 103 rows, every one already matched by a transfer row, 45 written by the test client, on a register that is 88% fixtures. Custody's backfill was worth it because a change of custodian is a person's act. Here the chatter is mostly data loading, and an append-only table is the wrong place to find that out afterwards. **My recommendation: do not backfill.** If you rule otherwise, it should exclude any burst of more than a handful of rows within one minute by one author — and I would want that threshold ruled on, not chosen by me.

## 4 · Whether the provenance fields want more than tracking

**Yes, three of them, and I did not upgrade them.** Tracking bought *visibility*: a changed GRN reference is now a `provenance_changed` event, graded `chatter`, deletable by the people who can make it. `grn_reference`, `purchase_order_reference` and `sap_asset_number` are what an auditor reconciles against Vendra and SAP; they change rarely; and a change to one is exactly the event somebody would want to hide. They are better candidates for the §A treatment than verification is. The other three import fields are rewritten on every re-import and would be noise. **Cost — which your list named — was not tracked:** it is not one of the six, and money is a separate ruling with `value` and depreciation attached.

## 5 · Tests — denominators first

In CI's order, against `test19`:

| Suite | Result |
|---|---|
| `pytest tests/` | **872 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 614 tests** |
| Playwright, `06-asset-actions.spec.ts` | **10 passed, 3 skipped** |
| `tsc --noEmit` / `BASE_PATH=/app/ vite build` | clean / built |

**880 collected** = report 27's 869 + 11 new. **614** in-registry = report 27's 561 + 53 new (32 on the movement record and the verifier, 6 on the snapshot, 15 net on the history). No `of 0 tests`, no `CRITICAL`. The 8 skips are report 27's 8.

**The 3 Playwright skips are the three MOVE specs** — they need two locations of type *building* and `test19` has none. A tenant fact, and the wrong three to skip in this handoff, so I drove the real Move dialog by hand: the move appeared at once as *Location moved · Cannot be altered*, by Administrator, with its transfer reference, no reload; the asset, which predates the recorder, showed the amber *already somewhere* notice.

```
$ CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q -rs
872 passed, 8 skipped in 83.42s (0:01:23)
SKIPPED tests/test_integrations.py:107  no active workflow.config
SKIPPED tests/test_query_params.py:119  `is_tagged` documented
SKIPPED tests/test_query_params.py:195  no data to partition: has_sap_code
SKIPPED tests/test_query_params.py:195  no data to partition: closed
SKIPPED tests/test_query_params.py:195  no data to partition: is_staff_bus
SKIPPED tests/test_sap_reconciliation.py:324  no asset carries a SAP asset number
SKIPPED tests/test_turnstile.py:125, :140  Turnstile is not configured

$ odoo -d test19 -u <CI's 11 modules> --test-enable --stop-after-init --workers=0
odoo.tests.result: 0 failed, 0 error(s) of 614 tests when loading database 'test19'
# The run before it was 1 failed of 614: my own test asserted the tracked-from list was
# exactly the SIX provenance fields, and the verification pass had just added the verifier
# as a seventh. The test was behind the code; it now says what is true.

$ E2E_ORIGIN=http://test19.localhost:8069 npx playwright test tests/06-asset-actions.spec.ts
  ✓ detail tabs switch · ✓ audit & review says in words when there is no history
  ✓ …shows a verification, newest first · ✓ …carries a reconstruction and a blank actor
  ✓ …says where the location record begins, and a tapped label explains itself
  ✓ mark verified (UI) · ✓ mark missing · ✓ condemn · ✓ transfer custody (API) · ✓ transfer custody (UI)
  - move persists server-side (API) · - move via UI · - move to the same location is rejected
  3 skipped, 10 passed (34.8s)

# The fan-out — version | table exists | the 6 tracked | stamp — read from each database:
cadra19 19.0.1.15.0 1 6 2026-09-20 19:45:40    nrs  19.0.1.15.0 1 6 2026-09-20 19:46:03
nrs19   19.0.1.15.0 1 6 2026-09-20 19:45:47    lasg 19.0.1.15.0 1 6 2026-09-20 19:46:10
gtb19   19.0.1.15.0 1 6 2026-09-20 19:45:55    gtb  19.0.1.15.0 1 6 2026-09-20 19:46:18
test19  19.0.1.15.0 1 6 2026-09-20 19:44:34    jaizbankplc 19.0.1.15.0 1 6 2026-09-20 19:46:25
# A second upgrade, hours later, left all eight stamps unchanged: "written once", on real databases.
```

## 6 · What the verification pass found — two blocking, both against me

A fresh reviewer, told to hunt for report 27's error in a new place. **It found it.**

**Blocking 1 — I named a person the record does not have, in the handoff whose ruling was that a verification without a person is a date.** `last_verified_date` is PATCH-writable; `last_verified_by` is not. I left it there. So: Alice verifies in January, an integration PATCHes a June date, and the asset reads ***"verified in June, by Alice"*** — who checked nothing in June. Three published sentences of mine already said it could not happen. **And the test I wrote to hold them passed for the wrong reason:** it PATCHed a never-verified asset, so the null it asserted was the starting state. Fixed in `nrs.asset.write`, where every writer of the date passes — a date that arrives without a verifier clears the old one. The test now verifies FIRST.

**Blocking 2 — a test true here and false in CI.** A fresh database runs no migration, so CI would have had no stamp, and my test asserted one. It would have been this handoff's first red the moment billing is fixed.

**The reviewer's S8 turned Blocking 2 into something larger.** I had let an absent stamp mean *"tracked since the first asset"*. True of a database whose every asset this code created — and **false of the one that matters: the 15→19 cutover builds NEW databases and loads them by ETL with their original `create_date`s.** The snapshot would have rolled a GRN reference back across years it holds no record of. A fresh install is now stamped too, so absence never has to mean anything.

**Should-fix, all fixed.** A movement joined its own chatter row by two wall-clock instants within 120 s, and a message's date is taken at precommit — so in any import over two minutes every early move would have been **listed twice**; they now join on Postgres's transaction stamp, and by recorded name where a deleted location has nulled the id · **the transfer link arrived in the context, which a caller controls, and the history shows the linked document's APPROVER inside an append-only event** — a transfer is now linked only if it is this asset's and names this destination. You are about to be asked for approvals on moves; that was the forgery path to one · `source` was claimable, so anybody able to move an asset could file the move under `test` · the location-deletion rows were written before the delete had been checked, with no savepoint · two verifications on one day changed the verifier with no line anywhere, so **I reversed my own decision and tracked `last_verified_by`**, which also publishes it on the snapshot for the first time · a note-less verification kept the previous verifier's notes under the new name · the route's own docstring still said a move is *"a row an asset manager can delete"* · the sentence nearly every existing asset will show — *already somewhere* — had one assertion anywhere, `isinstance(…, bool)`.

**Not fixed, and why.** *Custody has the claimable-`source` hole too* — GO-LIVE §13.4 item 0; four lines, but handoff 28 did not touch custody. *Both models' `create` guard is a context flag* — what stops a hand-written row is that flag AND an ACL granting create to nobody; the movement docstring now says so, custody's still says otherwise. *On the eight local databases the stamp predates the verifier's tracking by ~3½ hours*, because I added it in a second pass; on a deployment upgraded once both land together.

**Two found by me, by looking rather than testing.** Fact-checking the endpoint reference — which documented a `422 unprocessable` the move route has never returned — I sent a bad `reason` and got my new 400. **And a transfer in state `done`, for a move that never happened**: my validation ran after the document was written, and an error RESPONSE does not roll a transaction back. A false record, written by the change meant to end them. And the Move dialog, which I corrected last handoff from *"immutable"* to *"can be edited or deleted"*, had gone stale the other way: true, and now half the truth.

**The pattern, which is the finding:** `fidelity.verification`, the Move dialog, the route docstring — *words the server owns go stale the day the behaviour under them changes, and nothing fails.* Two of the three are now held by tests that know what the words claim.

## 7 · Noted, not touched

GO-LIVE §13.4. The ones worth your attention: **Odoo's *Duplicate* fails on every asset** (the tag is copied and collides with the one-active-tag rule — pre-existing, found when a test tried it). **Every fixture asset created from now on is permanent** — the suite always sends a location, so `remove_test_residue.py` will refuse all of them; by design, as custody, and the scripts say so by name. **Seven more screens that say what the record does not**, found beside the three you named — the top bar prints *"Admin User / Administrator"* for every session, which now sits beside a Verify button that records somebody else; an untagged asset shows its asset code under *"Asset Tag"*; the *Approval Status* pill is derived from two fields and no approval record exists; the employee screen prints *Permanent*, *Male* and *Not Enrolled* for fields the API never sends.

**`docs/handoffs/29-every-control-on-the-asset-page.md` is in the working tree and was deliberately NOT staged.** It is yours, it belongs to handoff 29's Step 0, and it arrived while this was running.

## 8 · Wall-clock and the correction share

**About 1 h 25 min of work across 3½ hours on the clock** — Step 0 at 20:29, the last green run just after midnight, with roughly 2¼ hours idle in the middle waiting for the owner to say *proceed*. I am reporting both because the first number is an estimate and the second is not.

**Correction share: a little over half.** In the order they cost time: the verification pass (two blocking, eight should-fix, a second fan-out to all eight tenants, a second full run of both suites); B2's collision with the snapshot, which I first solved with a per-row flag that **an existing test correctly rejected** — `_fidelity` on a row is a signal only because a sound row does not carry one — before moving it to where it belonged; the false `done` transfer; the 1,146.

**What I would tell the next Builder.** Four of this handoff's defects were mine and none was found by a test I had written beforehand. They were found by reading a foreign key, by reading Odoo's own JavaScript, by sending a bad request to check a doc, and by asking what a number was made of. *The guard that caught my snapshot design was somebody else's, written for a different reason, two handoffs ago.*

## Questions

1. **Backfill: no?** §3. I recommend against, and the measurement is why.
2. **`PATCH {"building_id": …}` moves nothing.** Put the building→location derivation in `write`, or take the three fields out of `_WRITABLE_FIELDS`?
3. **Append-only for `grn_reference`, `purchase_order_reference`, `sap_asset_number`?** §4.
4. **Close custody's claimable `source`?** Four lines, already written for movements.
5. **Verifications as a record of their own?** B1 made a verification name somebody. It is still one overwritten column. For a government register, *"show me every time this asset was checked, and by whom"* is the custody question again.

## Commits

- `a357237` — docs: handoff 28 — where a thing has been (the instruction file, on `dev`)
- `1510114` — feat: where a thing has been — an append-only record of every move, under every writer
- this report, in the commit after it
