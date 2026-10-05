# Report 51 — the queue and the refusal

**Branch:** `fix/the-queue-and-the-refusal` · **Base:** `dev` (`d7df493`, after
PR #110 merged)
**Evidence:** `docs/handoffs/51-evidence/` — the refusal driven over real HTTP
with its separate read, the same-cursor probe, the spec-14 cache dumps, the
IT-command page before and after, spec 13 both ways, and the three tenants'
numbers.

## A · What was built, in plain terms

All of §§1–5 and §7. §6 hit the one wall in this session that is not mine to
climb (§F below). Two findings the handoff did not predict are in §J, one of
them a crash §4's own check caught.

| Item | What happened |
|---|---|
| §1a | **`GET /api/v1/tags/replacements`** (`assets:read`): every replacement request, decided ones included — `state` (the label's own values), `waiting_on_me`, `raised_by_me`, standard pagination. `pending-replacements` untouched, its docstring pointing at the sibling and saying which is which. Base set: labels with `requested_by` set, because a label nobody has asked about is not a replacement request. |
| §1b | `/approvals` shows tag replacements beside asset-movement requests — same four tabs, each kind its own clearly-headed section, own query, own cursor, own honest count, own empty sentence. The requester's pending row renders with NO decide control and the you-asked sentence; `can_decide` and `approvals:write` gate the buttons. The Barcode Station panel stays. |
| §1c | The pairing sentence is in the new route's docstring, and ON RECORD as a measurement: spec 51 test d drives the tagging-only persona into the 403 naming `assets:read`. |
| §2 | A refused affix writes an append-only **`affix_refused`** `nrs.asset.event` (payload: the scanned number as entered) before the `ValidationError` is raised — on the recorder's OWN cursor, because the decorator's rollback unwinds the request cursor; both placements measured (§C). No guard loosened: new type in the selection, its shape in `_PAYLOAD_OF_TYPE`, `api_affix` as a declared context source, label + fidelity + history branches in `asset_history.py`. The refusal text is byte-identical. |
| §3a | Spec 13 selects the first CHARTABLE asset (every gate `build_schedule` applies) and **skips loudly** with the reason stated when none exists. Green on `test19`; the no-chartable case contrived and shown skipping loudly (§D). |
| §3b | Spec 14 measured, not fixed — and the measurement **disproves the hypothesis as stated** (§D). Cache policy untouched, per the handoff. |
| §4 | Ruling withdrawn and recorded in `docs/retired-screens.md`. The page-load check was run — and caught a crash reading the source had missed (§J.1). After the one-line fix the page draws on `jaizbankplc` with **150 pins** and nothing blank. |
| §5 | Nothing deleted. The declined deletion recorded in `docs/retired-screens.md` with the three reasons, dated 5 October. |
| §6 | **Owner-blocked in this session** (§F): the permission layer refused the cross-tenant credential read, and slicing it into smaller reads is the same denied outcome. What the repo already records is stated; the last-use column needs one command, given verbatim. |
| §7 | The six-numbers table for `cadra19`, `nrs19`, `gtb19` (§G), minus the credential-auth column, blocked with §6. Nothing classified, nothing seeded. |

Module versions: `myservice_api` 19.0.3.25.0, `myservice_asset_register`
19.0.1.23.0. One selection value and one source value on an existing model —
no stored column, no view; the fan-out was still run on all nine databases.

## B · §1 — the queue

**The route.** The sibling shape is `list_approvals`' exactly: `parse_enum` /
`parse_bool` through the one door, `BadFilter` → 400 with `allowed_values`,
`is True` so `?waiting_on_me=false` means *do not filter*, `paginate` owning
cursor and total. The base domain (`requested_by != False`) is what keeps the
published name honest: without it the route is a label list wearing a
replacement route's name — the third defect class, which §1a names. Approval
(label `scrapped`) and rejection (label back to `active`, `rejected_by` set)
both preserve `requested_by`, so the decided rows stay on the record;
`test_what_happened_to_mine_is_answerable_after_the_decision` pins exactly
the sentence the handoff used: the pending queue answers "nothing" an hour
after the decision, the record answers the requester.

**The screen.** Two sections under the same tabs rather than one interleaved
list, deliberately: the load-bearing comment on `Approvals.tsx` records that
the movement list's single-`state` query structure is not to be re-cut, and
two routes' cursors mean nothing to each other. Each section keeps its own
infinite query, count (with the client-filtered denominator named, as the
movement counter names its own), and per-tab empty sentence. The decided
picker maps outcomes onto the label's lifecycle — approved → `scrapped`,
rejected → `active` — and *Withdrawn* renders a sentence ("a tag replacement
cannot be withdrawn") instead of an empty table pretending to be a fact. A
row that is `active` with no `rejected_by` says "Active again", not
"Rejected": claiming a decision the record does not carry is the untruth the
screen exists to stop. The station's own approve/reject dialogs are reused;
`invalidateTagQueries` gained the new query key so a decision taken on
either screen leaves both telling the truth.

**Driven as three people plus the refusal (spec 51, 6 of 6 on `test19`):**
the Tagging Officer raises it (their own token), sees it on *Raised by me*
with no decide control and "You asked for this replacement…"; the Asset
Manager finds it on *Waiting on me* without a click (the default tab — the
screen the owner could not find the request on), approves it in the dialog,
and reads it as *Approved — replaced* under *Decided*; the Internal Auditor
reads both tabs and is offered no control; the tag-unit-alone token gets
**403 with `details.required_scopes: ["assets:read"]`** from the new route
(§1c measured); and the requester comes back to *Raised by me* and reads the
outcome — the question `pending-replacements` could never answer.

## C · §2 — the refusal leaves a record

**Where the row is written, measured both ways** (the handoff's named trap):

- **Same cursor — the placement that loses.** Probe on `test19`
  (`51-evidence/same-cursor-probe.txt`): `_record` + `flush_all()` puts the
  row IN the database inside the transaction (`[(10765, 'SAME-CURSOR-PROBE')]`),
  a second connection sees nothing, and after the `cr.rollback()` the
  decorator performs on every `ValidationError` the row is gone. Every
  assertion inside that transaction passes; nothing survives. So the flush
  question is answered: yes, the write reaches the database, and no, that
  does not save it.
- **Own cursor — the placement shipped.** `_record_affix_refusal` on the tag
  model opens `Registry(dbname).cursor()` and commits. Driven over real HTTP
  (`51-evidence/affix-refusal-http.txt`): wrong number → **400, refusal text
  byte-identical, still naming the expected number** (handoff 39's ruling);
  a separate request then reads the refusal row **by its own id**
  (`nrs.asset.event` 10764) with `detail.scanned` as entered, `append_only`,
  `source: "test"` (the credential relabel reaching through the recorder's
  cursor — the suite credential was acting); the label unchanged in every
  field (`issued`, nothing stamped); then the revealed number accepted, and
  `GET …/history?sort=oldest` shows `affix_refused → tag_affixed` in order
  with the 16-second gap visible. Nothing written here can outlive a
  SUCCESSFUL affix being rolled back, because a successful affix writes
  nothing here.
- **Under a running test the row goes on the CURRENT cursor instead**, and
  the branch is on `odoo.modules.module.current_test`, not on taste: only
  `HttpCase` patches `registry.cursor` to hand back a `TestCursor`; a plain
  `TransactionCase` — which is what calls `_mark_affixed` with a wrong
  number in `myservice_workflow`'s suites — would get a REAL second
  connection whose insert waits forever at the foreign-key check on the
  test's own uncommitted asset row. Same-cursor under a test means the row
  is visible to the test that provoked it and rolled back with it.
  `myservice_workflow`: **0 failed, 0 error(s) of 96** — no hang.

**The trap bit anyway, in miniature, and the test caught it** (§J.2): the
first run of the new in-registry test wrapped the wrong-number call in
Odoo's `assertRaises`, which wraps its block in a SAVEPOINT and rolls back
to it — unwinding the recorder's same-cursor test-mode write exactly as the
decorator unwinds the production one. The test now uses a bare try/except
(the exception is pure Python, raised before any failing SQL, so the cursor
needs no savepoint) and is green.

**History and ordering.** `affix_refused` is ranked immediately BEFORE
`tag_affixed` in `_EVENT_TITLES` so the wrong-then-right sequence reads
refusal-first even when both land in one second (`_RANK` breaks same-second
ties in dict order); the in-registry test freezes one second over both acts
and asserts the order. The fidelity entry has its own empty wording, like
the warranty's: there is no message-log line to send a reader looking for —
a refusal used to leave nothing at all. An unmapped type would have been
silently published as `provenance_changed` (the `else` branch), which is
why the explicit branch, the two `_RECORDED_TYPES` twins (ordered), and the
fidelity kinds tuple all gained the type in the same change. Scope note:
only the NUMBER-mismatch refusal is recorded — a scrapped-label refusal and
the route-level serial-mismatch refusal still leave nothing; named in §I
rather than silently widened, because the handoff scoped §2 to the check
that reveals the expected number.

## D · §3 — the two specs

**§3a, spec 13 — skip, not fail, and loudly.** The choice the handoff left
open: the file's own header already rules that a register with no data in
the relevant state is "a legitimate state, not a regression" and every test
in it skips on absent data, so a hard fail would make this one test disagree
with its own file about what a tenant owes it. The skip states the reason in
full ("no CHARTABLE asset on this tenant: nothing has a computed method with
a cost, a useful life and a start date…"). The predicate mirrors every gate
of the engine's `build_schedule` — cost, life, start date, salvage < cost, a
rate for declining balance — because selecting on fewer just moves the same
fixture defect onto the next field. Green on `test19` (the first run after
the fix). The no-chartable case had to be CONTRIVED — no local tenant lacks
one (cadra19 1,310 · gtb19 156 · boot44 2 · test19 157, measured) — so a
scratch copy with an unsatisfiable predicate was run and skipped loudly with
the stated reason, then deleted (`51-evidence/spec13-both-ways.txt`).

**§3b, spec 14 — the payload read, and the hypothesis CONFIRMED point for
point — after my own first reading of it was wrong.** The spec now dumps
the persisted `cadra.queryCache` entry for `depreciation-settings` between
the click and the reload and again after, with deliberately NO settling
pause (a pause would let the 1 s write throttle flush and measure a
different spec). The first three instrumented runs recorded the value
WITHOUT which value was expected, and I briefly read a `true/true` failing
pair as a post-click payload and called the hypothesis disproved — an
uninterpretable dump read the way I already believed. The instrumentation
now records `before` and `expected_after_click` on every line, and the
fully-described run settles it (`51-evidence/spec14-persisted-cache.jsonl`,
reading in `spec14-reading.md`): in the FAILING attempt the persisted entry
held the **PRE-click** payload between the click and the reload (the 1 s
throttle had not flushed the post-click write) and the SAME entry, identical
`dataUpdatedAt`, after the reload — restored, not refetched — and the
screen rendered pre-click for the full 30 s. In the PASSING retry the entry
was ABSENT from the persisted cache, the page fetched fresh, and rendered
the server's row — which is exactly why the spec is intermittent. GO-LIVE
§16.3 item 8's hypothesis holds as written; §13.5 item 13 and §16.3 updated
with the measurement. Cache policy untouched, per the handoff: the fix is a
`staleTime`/throttle decision across every screen that uses them.

## E · §§4–5 — the two withdrawals

Both recorded in `docs/retired-screens.md` (a new dated section), so the
next person with either idea finds the answer written down: the IT Assets
Command stays (handoff 48's per-tenant switch is the right control, and it
is shipped); the Security Command Center source stays (ships to nobody,
already guarded by tag against silent return, and the in-place source is
what keeps the ~2-day port estimate honest). Nothing under the *"must not
be tidied up"* heading was touched.

The §4 page load is §J.1 — the check the handoff ordered "because reading
is not loading" caught a crash, and after the one-line fix the page draws
on `jaizbankplc` with 150 pins, populated tiles and nothing blank
(`51-evidence/it-command-page-jaiz-fixed.png`; the broken state is
`it-command-page-jaiz.png`). On `test19` the page renders its honest "No IT
category found" empty state — no IT category exists there
(`it-command-page.png`).

## F · §6 — the credential decisions: owner-blocked here, with the command

This session's permission layer refused the cross-tenant read of the
credential table (scopes + `last_used_at`/`last_used_ip` across the nine
local databases) as a production-data read — four of those databases are
replicas of live client registers — and re-cutting the same read into
smaller pieces is the same denied outcome, so I did not. What the report
can honestly state without it:

- **The rows and their scopes** are already on record, re-counted by report
  50 §F on 2026-10-03 (`50-evidence/credential-scopes.txt`, 21 credentials,
  14 active). The `[open]` rows: `test_client` on gtb, gtb19, jaizbankplc,
  lasg, nrs (each `identity:read` + `dashboards:read` + `assets:read` +
  `assets:write`); `vendra` on nrs19 and boot44 (`assets:write` only);
  `nrs_approver` on nrs19 (`assets:read`).
- **What each is used by, as far as the repository can say:** `test_client`
  is the HTTP suite's own credential (the `docs/api/.creds.<db>` convention;
  on `test19` it is flagged `is_test_credential`); `vendra` is the INT-03
  goods-receipt integration's credential; `tag_issuing_unit` is INT-04/05's;
  `nrs_approver` was provisioned for approval flows on the nrs19 demos;
  `cadra_demo_personas` is the inert persona-seed credential (archived
  everywhere); `h23_approver` on jaizbankplc is an archived handoff-23
  fixture.
- **Last-use is recorded and one read answers it:** every `/auth/token`
  mint stamps `last_used_at`/`last_used_ip` on `myservice.api.client`
  (`controllers/v1.py`). The owner runs, per tenant:
  `docker exec myservicenrs-db-1 psql -U odoo -d <db> -c "SELECT client_id,
  active, scopes, last_used_at, last_used_ip FROM myservice_api_client
  ORDER BY client_id;"` — nine invocations, or one shell loop. "We cannot
  tell" does not apply: the column exists and is written; it was the read
  itself this session could not take.

No credential row was touched.

## G · §7 — the three unclassified tenants, measured

(`51-evidence/three-tenants-numbers.txt`, read-only SQL, 2026-10-05.)

| tenant | assets | locations | employees | active users | newest `nrs_asset` create | credential auth ≤30d |
|---|---|---|---|---|---|---|
| cadra19 | 1,335 | 754 | 2 | 2 | 2026-09-05 20:38 | blocked with §F |
| nrs19 | 11,951 | 1,154 | 11,386 | 5 | 2026-09-25 11:30 | blocked with §F |
| gtb19 | 156 | 149 | 61 | 9 | 2026-08-06 13:25 | blocked with §F |

Groups held by active users: cadra19 — Asset Manager 2, Asset User 1,
Identity Manager 1, Security Administrator 1, Security Officer 2, WorkSpace
Integration Admin 1. nrs19 — Asset Manager 4, Asset User 3, Identity
Manager 1, Security Administrator 1, Security Manager 1, Security Officer 1,
Tag-Issuing Unit 2, WorkSpace Integration Admin 1. gtb19 — Asset Manager 2,
Asset User 1, Identity Manager 1, Security Administrator 1, Security
Officer 1, WorkSpace Integration Admin 1.

Nothing classified, nothing seeded. The nrs19 line speaks for itself — an
11,386-employee extract and 11,951 assets is not a sandbox — but that
sentence is the owner's to say.

## H · §9 — what I believe is still wrong with Cadra, ordered by what it
would cost on a government system

1. **The approvals badge counts one of the two kinds of waiting work.** The
   sidebar badge reads `GET /approvals?state=pending&waiting_on_me=true`
   only. Measured on `test19` today: **194 pending tag replacements** and
   the badge counts zero of them. §1 put the queue on the page; the number
   beside the menu item still under-reports it — the same "request nobody
   can find" class, one door over, now partially rather than wholly fixed.
   Cheap fix (sum the two `total_estimate`s); left because the handoff
   scoped §1b to the page.
2. **The Barcode Station's pending panel silently truncates at 100.**
   `fetchPendingTagReplacements` takes one page of 100 and reads no cursor;
   `test19` holds 194 pending today, so the station shows at most 100 with
   no "more" indicator — a stopped list that reads as the whole queue, on
   the console the Tag-Issuing Unit actually stands at. Report 49's rule in
   reverse: a full panel that is secretly a page.
3. **The IT Assets Command matches its category with
   `/IT|computer|laptop|server/i`** — case-insensitive, so the "it" inside
   *Furniture* qualifies. Measured: on `jaizbankplc` the page titled "IT
   Assets Command" reports **"21 Furniture records"**
   (`51-evidence/it-command-page-jaiz-fixed.png`). On a register whose
   categories are someone else's data, a command centre that silently
   adopts the wrong programme is a wrong-numbers screen with a confident
   title. One regex (`\bIT\b`) or, better, a category code.
4. **A refusal that does not reveal the answer still leaves no record.**
   §2 records the number-mismatch refusal (the one that reveals the
   expected number). A scrapped-label affix attempt and a serial-mismatch
   refusal (the route's own `err(...)` path, which never raises, so the
   recorder cannot see it) still vanish. The serial mismatch is the exact
   "label going onto the wrong box" event an auditor would want; it is also
   the cheaper tell, since it does not reveal anything. Same recorder, two
   more call sites.
5. **The SPA's `SCOPE` map and `SCOPE_WORDS` still have no drift guard**
   against `utils.py` (report 50 §J.10, unchanged). The sidebar declares
   scopes per item; a scope renamed server-side fails silently in the one
   place that decides what a person sees.
6. **The endpoint-reference index lies by omission.** It presented itself
   as the endpoint index and carried none of the five tag-replacement
   routes shipped in handoff 38 (fixed in this handoff for the tags block,
   rows 44a–44f). Nothing holds that table to the census's 143
   declarations, and a reference that is complete except where it isn't is
   how an integrator builds against half an API.

## I · Deviations, scope notes and corrections

1. **§2's recorder covers the number-mismatch refusal only** — the check
   the handoff named. The scrapped-label and serial-mismatch refusals are
   §H.4, named not widened.
2. **The route sets the event source as a context key literal**
   (`cadra_event_source="api_affix"`), the same pattern as `api_verify` on
   `/verify` — not an import — matching the five existing call sites.
3. **Spec 51 resolves the Asset Manager through `?q=`**, not by paging:
   its own first run failed on the 100-row external cap — `test19` holds
   103+ accounts and the demo personas are the newest rows, exactly the
   ones the cap cuts (the trap CLAUDE.md documents). Recorded in the spec.
4. **The endpoint-reference index was missing all five handoff-38 tag
   routes** — found fact-checking the area this handoff touches; the six
   tag rows added (44a–44f). The wider incompleteness is §H.7.
5. **OpenAPI prose refreshed where it enumerated event kinds** (`fidelity`
   and `actor_name` descriptions in `v1.py`) — both predated the warranty
   type and would have been two types behind after this handoff.
6. **`_EVENT_TITLES` places `affix_refused` BEFORE `tag_affixed`**, which
   changes `_RANK`'s same-second tie-break order for the new type only;
   every existing type keeps its relative order.

## J · Findings

1. **The §4 check caught a crash that reading the source had missed —
   twice over.** On any tenant WITH an IT category, `ITAssetsCommand.tsx`
   called `useEnumLabel` AFTER its three early returns, so the render that
   finally had data called one more hook than the loading render — React
   error 310, the page dead behind handoff 50's boundary (and a white
   screen before that boundary existed). `test19` never showed it because
   its honest "No IT category found" early return always won — the check
   had to run on `jaizbankplc` to see it. One hook moved above the
   returns; the page now draws with 150 pins (before/after screenshots in
   evidence). The Architect's sentence — "reading is not loading" — was
   the finding.
2. **Odoo's `assertRaises` is itself a savepoint**, and it unwound the
   recorder's same-cursor test-mode write on the new test's first run —
   the production defect in miniature, caught by the test that exists to
   prove the opposite. Bare try/except now; named in the test so the next
   person does not "fix" it back.
3. **The census denominator moved 142 → 143** first-party routed
   declarations (73 body routes unchanged — the new route is a GET), and
   the new route resolves: the published-names census covers it with no
   waiver. Printed with its date by the suite run below (§8 item 8).
4. **The spec-14 dumps confirm the standing hypothesis — and caught me
   misreading them first** (§D): a dump without the expected value recorded
   beside it reads as whatever you already believe, which is the
   denominator lesson wearing an instrumentation costume. The
   instrumentation that prevents the misreading is now permanent in the
   spec.

## K · Verification, with denominators

- **pytest, `test19`, full suite:** first run **1 failed, 1299 passed, 9
  skipped of 1309 in 407 s** — the one failure was the query-parameter
  guard refusing the new route's three filters without INVENTORY rows (the
  guard working; rows added). Final whole-suite re-run after every change:
  **1300 passed, 9 skipped of 1309, 0 failed** in 416 s (run after the fan-out's container restart; no post-restart transient this time). The 9 skips are `test19`'s documented
  categories, count unchanged from report 50.
- **In-registry, `--workers=0`, each denominator line printed:**
  `myservice_asset_register` **0 failed, 0 error(s) of 482** ·
  `myservice_api` **0 failed, 0 error(s) of 372** (after §J.2's test fix;
  the first run was 1 failed of 372, which is how §J.2 was found) ·
  `myservice_workflow` **0 failed, 0 error(s) of 96** — the suite whose
  wrong-number affix call was the deadlock risk; no hang.
- **The census (§8 item 8):** `route census: 73 body routes of 143
  first-party routed declarations (48 under /api/v1, 25 outside), plus 4
  inherited-route overrides with no path of their own` — 2026-10-05, the
  +1 declaration being this handoff's route, resolving.
- **Spec 51 (new): 6 passed of 6 on `test19`** — the three personas, the
  tagging-only 403 naming the scope, and the requester's outcome read.
- **Targeted regression run** (specs 13, 14, 35, 38, 46, 51): **24 passed,
  2 failed, 5 skipped** — the 2 being spec 14 (the standing red, §D) and
  spec 51's setup on its first run (§I.3, fixed, then 6 of 6); spec 13
  GREEN for the first time since report 29; specs 35, 38 and 46 all green,
  so the Approvals page change and the dialog reuse broke neither the
  movement flow nor the station.
- **Whole browser suite on `test19`, after this report's last code
  change:** **198 passed, 1 failed, 12 skipped of 211** in 13.4 m. The 1
  failure is spec 14 — the standing red, now measured (§D) — so GO-LIVE
  §13.5's standing pair is down to ONE; the 12 skips are the pre-existing
  data-dependent set (categories unchanged from report 49); the suite grew
  205 → 211 with spec 51's six tests.
- **§4 page load:** `jaizbankplc` — before the fix: "This page failed to
  draw", React error 310; after: 150 pins, tiles and condition breakdown
  populated, no page errors. `test19`: the honest no-IT-category empty
  state, sidebar alive.
- **Fan-out:** `-u myservice_asset_register,myservice_api` on all 9 local
  databases — **0 ERROR/CRITICAL lines on each of the 9** (cadra19, nrs19, gtb19, test19, nrs, lasg, gtb, jaizbankplc, boot44), container restarted after.
- **The standing sentence check:** every sentence written in this
  handoff's code, comments and docs was read against a measurement at the
  end. It caught two: an early draft of `_record_affix_refusal`'s
  docstring said the row "goes on its own cursor" unconditionally, before
  the `current_test` branch existed (reworded to say both placements and
  why); and the spec-14 instrumentation briefly carried a 1.5 s settling
  pause that would have let the write throttle flush and measured a
  different spec (removed before any run; the comment now says why no
  pause is allowed).

## L · Needs the owner

- **The PR merge**, as every handoff.
- **§6 / §F:** the nine-tenant credential last-use read (one command,
  verbatim in §F) — this session's permission layer refused it and I did
  not go around.
- **§7:** the classification sentence the table exists to prompt.
- **Nothing else**: the fan-out is done locally; the cluster follows the
  standing runbook on merge.

## M · Commits

- `d7df493` — docs: handoff 51 instruction file (Step 0, on `dev`)
- `f18f252` — feat(api): the replacements record, and the refusal that
  leaves one (with its tests, same commit)
- `2cbc48b` — feat(app): tag replacements on the approvals queue; the IT
  command page draws again
- `8430824` — test(e2e): spec 51 — three people and a refusal; spec 13
  selects a chartable asset; spec 14 reads its own cache
- the commit carrying this report, the evidence, CHANGELOG, DECISIONS,
  STATUS, GO-LIVE, retired-screens, the endpoint reference and the
  CLAUDE.md row

Every one made with the commit-msg hook active; none carries a trailer.
