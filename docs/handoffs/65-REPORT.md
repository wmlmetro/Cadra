# Report — Handoff 65: the link

Branch `feat/the-link`, from `dev` at `d3e5942` (Step 0 committed the
instruction file). Module versions: `myservice_asset_register` 19.0.1.33.0
(one new model, `nrs.sap.link`; run fields; an UNLOGGED scratch table),
`myservice_api` 19.0.3.36.0 (a migration deleting the AI key row),
`myservice_workflow` tests only. Evidence: `docs/handoffs/65-evidence/`.

## Needs the owner

1. **The PR merge** (the Builder's permission layer refuses `gh pr merge`).
2. **The deploy:** `upgrade-19` for `myservice_asset_register,myservice_api`
   on every tenant (a new table and new columns — schema before code).
3. **The AI key, now on the server, not in a database:** put
   `CADRA_AI_API_KEY` in the cluster's `cadra-odoo` secret (the Deployment
   reads it, optional) and roll the Odoo Deployment; locally run
   `scripts/set_ai_key.sh` (no database argument) and recreate `odoo`. The
   upgrade deletes any key stored the old way — none was, on 9 of 9 local
   databases (the eight tenants and `test19f`).
4. **The model choice:** run `scripts/ai_live_check.py --models
   claude-opus-5-5,claude-sonnet-5-5,claude-haiku-5-5` once over your photo
   folder and pick the cheapest model that is right often enough. Opus stays
   the default. The script's per-token prices are marked for you to confirm
   against Anthropic's pricing page; one is left blank rather than guessed.
5. **Linking NRS's real register (`nrs19`) needs two people there.** The
   confident list on `nrs19` is ready (2,445), but nobody on that tenant
   holds the maker or checker role, and I could not seed demo people there
   (below). Either classify `nrs19` and give the two roles to two NRS
   officers, or seed the demo personas there knowingly (GO-LIVE §34.1).
6. **NRS:** confirm the class mapping using the new evidence (§4 below), and
   work the 959 contested assets (GO-LIVE §34.2–34.3).

## In plain words

Cadra can now copy SAP's asset number onto an asset it already holds, the
same way NRS registers anything: one person proposes, a second approves.
The Register Maker opens *Link to SAP* and sees every asset whose old FIRS
tag (or serial) points at exactly one SAP record that no other Cadra asset
points at. They tick a batch, preview it, and propose. The Register Checker
approves or returns it. On approval the asset carries SAP's number, the
record says it was *linked from SAP's export by two people*, and its history
says who proposed and who approved. **Nothing is sent to SAP** — SAP already
has that asset. A link can be undone the same way, with a reason, and
nothing is ever deleted.

Where two or more Cadra assets point at the same SAP record, Cadra does not
guess. The *Contested* tab shows them side by side, with photos, and the
maker either picks one or flags the group as a likely duplicate for NRS.

An SAP import that would mark more than 5% of the mirror "no longer in
SAP's export" now stops before writing anything, and says a truncated or
wrong file is the likely cause. The administrator can confirm and re-run.

On NRS's own data: the list holds **2,445 assets — exactly report 63's
number**. Linked, Cadra would hold 2,445 of SAP's 161,647 active assets
(1.5%), up from 0.

## What was built

**§1 the link.** `nrs.sap.link` (`myservice_asset_register/models/sap_link.py`)
and eight routes (`myservice_api/controllers/v1_sap_links.py`, endpoint
reference §18). Proposals are a batch of single acts with a dry run, 60's
rules. The no-two-gates rule is reused with two new gates, `link_make` and
`link_check`. The approval writes the number, sub-number, company code and
`sap_code_source = linked_from_sap_mirror` — a new value nobody else may
write. History line, verbatim from the drive: *"Linked to SAP asset
3DEE8CE000 (old tag, unique), proposed by Temitope Oyelaran, approved by
Obinna Ezeagu."* Undo: the same two acts with a reason.

**§2 contested.** `GET /sap-links/contested` (side by side: code, name,
location, custodian, created, old tag, serial, photos; counts by office), a
proposal for one asset of the group, or a flag — an append-only event on
each asset, shown as `sap.duplicate_flag` and on the asset page.

**§3 the 5% guard.** A run against a non-empty mirror first reads the file
for its keys only, writing nothing to the mirror; over 5% it stops as
`held`, under it rewinds and writes. `mark_absent=true` ("Yes, mark them
absent") skips the count and is recorded on the run with who.

**§4 class evidence.** `class_evidence` on the coverage report, per Cadra
category, with a sentence. It never writes a category's SAP class.

**The app.** *Link to SAP* (three tabs: Confident matches, Waiting on the
checker, Contested) beside Candidates; a *Propose undoing this link* control
on a linked asset; the duplicate flag and the SAP number with its source on
the asset page; the guard's checkbox, `held` chip and advice on *Settings →
SAP asset master*; the class evidence card on *SAP Coverage*.

**§0 / §0a.** The access-change report on Lagos days (63b's helper); the
endpoint reference's error codes made to match `utils.py` (`unprocessable`
removed, three missing codes added); `legacy_asset_code` documented as the
old FIRS tag. The AI key is read from `CADRA_AI_API_KEY` only — every
database read and write removed (bootstrap's mirror too), a migration
deletes the row; `ai_live_check.py --models`; a field the asset already
holds is recorded *accepted* (`already_held`), not *ignored*; a frozen-clock
test pins the cap's Lagos midnight.

**§0b, for Vendra 59.** On `test19`, unit **106929** (`NRS-AST-070796`, GRN
`MAT-PRE-2026-00784`, received from Vendra): tagger requested a replacement,
the Asset Manager approved, the print was recorded and affixed. INT-05
delivered the second `asset.tag.affixed` as `WDL-2026-13049`, **`label_id`
78806** (the first was 78805), same number, `printed_at` set — acknowledged
by the bench Vendra, HTTP 202, two seconds after the affix.

## The numbers

| | |
|---|---|
| `nrs19` confident list | **2,445** (report 63: 2,445); 3,404 ranked first, 959 contested over 449 records; 1.2 s |
| §7 after linking the 2,445 (rolled back) | Cadra holds **2,445 of 161,647** active SAP assets (1.5%, from 0); 9,513 register assets left without a SAP number |
| §4 on `nrs19` after linking | IT Equipment: 2,353 linked — SAP 3000 for 2,241, 2000 for 58, 4000 for 36, 7000 for 16, 1000 for 2. Fleet / Vehicles: 92 — 1000 for 91, 4000 for 1. Neither has a class configured |
| §6.2 drive, `test19f`, two personas | 50 proposed / 50 approved; propose 0.41 s, approve 0.68 s for 50; 50 of 50 linked, posting `none`, **0 outbox rows** |
| §6.3 undo | 1 proposed + approved; number cleared; 4 history lines |
| §6.4 contested | 1 group resolved (the other asset left unlinked), 1 flagged (flag on both) |
| §6.5 guard, `nrs19`, truncated SAP file | held: 31,700 of 211,699 (15.0%), nothing written, 129 s; overridden: 31,700 marked absent, confirmed by Administrator; full file restored 211,699 of 211,699 |
| HTTP, touched files (gates off, `test19f`) | 420 passed, 2 failed of 423 on the first run (two pins, fixed: 5 of 5); after the verification fixes 159 passed, 1 failed of 160 (a sidebar count pin, 36 → 37, fixed) |
| In-registry | link + outbox + guard 0 failed of 12; AI + audit + import 0 failed of 28 |
| Browser (`test19`, gates on) | specs 46, 48, 63: 19 of 19; spec 65 failed gates-on (its fixture made candidates), fixed and 1 of 1 — 20 of 20. Specs 63 + 65 4 of 4 on `test19f` (gates off) |
| Final local pytest (fresh `test19f`, gates ON) | **1,519 passed, 1 failed, 10 skipped of 1,530** in 30 m 0 s; the one failure a 30 s read timeout while the browser specs shared the server — alone, 1 of 1 in 24 s |
| CI | run 39297610266 on `c753840`: **green, both switch states** — pytest 1,514 passed, 16 skipped of 1,530 each; in-registry step passed (its result line is beyond GitHub's truncated log view). Earlier: 39246000399 red (2 / 8 failed of 1,530), 39248755063 pytest green, in-registry red (the history pin) |

## §7 — the question

**After the 2,445:** the coverage report would say Cadra holds 2,445 of
SAP's 161,647 active assets (1.5%). Of the 9,513 register assets still
without a number, 959 are contested and wait on a person, and nothing else
is confidently linkable.

**If SAP's location extract gave every record an office: about 650 more at
most, as choices for a person rather than confident links.** The reasoning,
measured on `nrs19` (`65-evidence/nrs19-measure.json`):

- An office does not settle a tie on a shared old tag. The tag carries the
  office already, so the two records share it too. The 959 contested assets
  are unaffected.
- 121,435 of SAP's 159,202 active, unlinked records already have an office
  from their tag. The extract adds the other 37,767 (24%).
- What an office helps is the matcher's third tier: class and description
  within the office. Of the 8,554 uncontested assets left, matched by every
  word of their name against SAP's descriptions nationwide:
  - 5,835 match **no** SAP record;
  - 54 match exactly one already;
  - 593 match 2–10;
  - 95 match 11–100;
  - 1,977 match more than 100.
- Split across 900 offices, most of the 593 and some of the 95 would come
  down to one record in their office. That gives roughly 54 + ~600 ≈ 650.
- **But Cadra's locations carry no SAP office code**, so even these need a
  location-to-office mapping first. The matcher also ranks a description
  match for an operator to choose, not as a confident link.
- The large lever is not the extract. It is the 5,835 assets whose Cadra
  names share no full word set with any SAP description (Cadra says
  *"HP ProBook 450"*, SAP says *"LAPTOP"*). Those are an audit team's work
  with the matcher, or the AI capture of 66.

## Deviations and findings

1. **The §6 writing drives ran on `test19f`, not `nrs19`.**
   - `nrs19` has no Register Maker or Checker and no credential with
     `sap_mirror:read`, and the persona seed refuses an unclassified tenant.
   - I made a classified copy of `nrs19` to seed personas into. The safety
     layer refused copying its files and seeding people into it, because it
     holds a real NRS staff extract. I dropped the copy.
   - `nrs19` was measured read-only: the count, §4 and §7 inside a
     rolled-back transaction. The §6.5 guard drive did run on `nrs19`, as
     its administrator, as report 63 did, and the mirror was restored.
2. **Fixed after the verification pass** (its findings 2–7 and 9; finding 1
   was CI red on the first push, now fixed):
   - a link on top of an asset-master posting already in flight would have
     given SAP two masters; it is now refused, and this would have bitten
     19 of `nrs19`'s assets;
   - an approval now re-checks whether the record has become contested
     since the proposal;
   - a run that was mid-import at upgrade time is not counted;
   - the counting pass's scratch rows are cleared when a run fails;
   - the query parameters go through the shared validator;
   - the gates-on test fixtures are legacy-shaped (a gated registration
     always carries a SAP number, so it is never a link candidate);
   - an in-registry test covers the under-5% rewind;
   - `flagged_by` has one shape everywhere.

   Left as is:
   - one event query per asset for the flag (N+1 on asset lists);
   - a serial-basis proposal is not re-checked for contestedness at
     approval.
3. **The outbox test caught a hole in my own model**: the proposal handed
   back still carried the write flag, so a caller holding it could write a
   decision. It now hands it back clean.
4. **The 5% guard reads the file twice.** Guarding only the final "mark
   absent" step would let a wrong file rewrite rows first, so the count
   comes before any write. `nrs19`'s full re-import took 348 s on a busy
   bench, against 63's 100 s.
5. **`test19f` has no SAP target**, so the drive's "0 outbox rows" proves
   little on its own. The proof is the in-registry test, which uses a live
   stub target and shows the same target does queue a master for an
   unlinked affix.
6. **Not run:** the full browser suite. Only specs 46, 48, 63 and 65 ran:
   the new page is one lazy route and one sidebar item, and spec 46 checks
   every persona against every item.
7. **Found, not changed:**
   - `docs/api/CHANGELOG.md` carries the 64 and 63b sections twice
     (pre-existing);
   - the AI subagent flagged that `AnthropicProvider` sends a fallback
     parameter for every model, which Haiku may reject. If the owner's
     Haiku run shows `provider_error` HTTP 400, look there first.
   - The order-dependent `test_every_bare_override_of_an_inherited_route_is_named`
     (report 64) failed again in the isolated in-registry run; CI runs it
     in order.

## Time

Started 12:07 WAT. Budget stated at Step 0: ~5½ h, over the 3 h target,
with §2 + §4 named as the split. The split was not needed.

- **Build** (§0–§4 and the app, three subagents in parallel), 12:07–13:01:
  about 55 min.
- **Tests** while building, plus the final run (30 min, gates on) and the
  browser specs (22 min, run alongside), 12:20–13:36.
- **Verification pass**, 12:39–12:55, run alongside CI; its fixes until
  13:01.
- **CI's hidden failure**, 13:15–13:41 and again 18:49–19:05.
  - The in-registry step's log view stops early in both this branch's run
    and `dev`'s, so I reproduced the run locally.
  - Locally, two real-PDF render tests deadlock wkhtmltopdf against the
    single-threaded test server. That is a fact about this machine, not the
    code (to be added to ENVIRONMENT-FACTS).
- **The session was idle from 13:41 to 18:49** and resumed on the owner's
  ping. Wall clock to the push overstates the work by about 5 hours.
- **Report**, written alongside the runs, ~20 min.
