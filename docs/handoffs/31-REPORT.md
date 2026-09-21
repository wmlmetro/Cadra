# Report 31 — One answer per rule

**Branch:** `feat/one-answer-per-rule` · **Base:** `dev` at `c08a120`. PR #81 had merged (`399780f`, 13:54 UTC) — the precondition you set.

**Needs the owner:**
1. **The PR merge.**
2. **A note to Vendra** — §2. Their own contract document now describes behaviour Cadra no longer has. Nothing of theirs breaks; one page of theirs is wrong.
3. **Two questions for NRS** — §2 (*do you want a location on a service request?*) and §5 (*what does "transferred" mean?*).
4. **A deploy carries a module upgrade** — views and one selection value, no new table or column. `myservice_asset_register` → `19.0.1.17.0`, `myservice_api` → `19.0.3.11.0`.
5. GitHub billing: fourth report. Everything below was run locally.

**One BREAKING contract change, ruled by you, announced in the changelog, the endpoint reference and `INT-10`** — §2.

---

## 1 · What adopting the mixin changed — and whether anything surprised me

**It changed no behaviour, which is the point, and I can say that because the suite says it: `0 failed, 0 error(s) of 734` in-registry on the first run after adoption, before a single test had been written or adjusted for it.** Custody and movement lost their own `create`, `write`, `unlink` and `_resolve_source` — 101 lines out and 51 in across the two files, most of both docstring — and kept what is genuinely theirs: two context keys, the list of sources a caller may claim, and the wording of their refusals (*"the chain of custody is append-only…"*; *"the record of where an asset has been…"*). No migration, no id, no published name.

**Three small surprises, none of them trouble:**

1. **The mixin had to move house.** It lived in `asset_event.py`, which is imported *after* custody and movement; a model cannot be built before the mixin it names. It is now `models/append_only.py`, imported first, with a comment saying why the order is load-bearing.
2. **The three `myservice_api` overrides were not merely "not the same code" — they did not make the same exception.** Custody's and movement's both spared `tracking_backfill` from the test-credential relabel, in two different spellings. **The event record's, which I wrote last handoff, spared nothing.** Harmless, because nothing writes a reconstructed event — but it was a third answer to one question, written by the person who had just finished arguing against two. It is `_never_relabelled` on the mixin now, once.
3. **A comment said a method had to keep its name "because `scripts/` and the docs cite it".** I searched before deleting it. Nothing outside the module did. It had been kept alive for two handoffs by a sentence nobody checked.

**Custody's rows stay where they are — recorded in `DECISIONS.md` as ruled, with the reasoning, so nobody reopens it in six months on aesthetics.**

---

## 2 · What the 400 broke that I did not expect

**It broke nothing of Vendra's, exactly one thing of ours — and that one thing turned out to have been broken for the life of the route. I then described it wrongly twice.**

**Vendra.** I had an independent read of its client done before changing anything. A `400 invalid_request` becomes a plain terminal error, dead-lettered on the first attempt, with its default remedy: *"Fix the underlying data, then use Retry."* **That sentence is now correct, and under the old behaviour it was wrong** — which is why Vendra had to special-case a second remedy for the 201-with-a-warning (*"the asset exists in the register, incomplete"*). Its eleven payload keys are all accepted; it makes no PATCH to any of the ten routes. **And the fear worth having was unfounded:** Vendra's idempotency key is deterministic across retries, so a *stored* 400 would have blocked a corrected mapper for ever. Errors are never stored under a key. I acted it rather than trust the reading: bad body 400 · same body 400 · **corrected body, same key, 201** · again 201, same asset. **One thing for you to send them:** their own `docs/reference/cadra-api-contract.md` still says *"Unknown fields are silently swallowed … the create still returns 201."* Nothing breaks; the page misleads.

**Ours — `POST /requests` has never saved a request's location.** The 400 took down the suite's `test_request` fixture, and would have made *raising a request with a location from the app fail outright*. The cause: the request model's location field became `generic_location_id` in the move to Odoo 19, and the API went on asking the model for `location_id`. It refused the key — the model did not define it — and answered **201**. The endpoint reference's canonical example sends a location. So does the OpenAPI example, the app's request form, the fixture, and the smoke test. `jaizbankplc`: **460 requests, none with a location.** `?location_id=` on the list was ignored the same way and answered with every request — handoff 21's defect, alive under a comment calling it *a registry guard*.

**And then I nearly "fixed" it by deleting the feature — this is the correction you should read.** My first reading was *the register cannot hold a request's location*. I reached it by checking `ir_model_fields` for `location_id`, finding nothing, and stopping. On that I **ruled** the app's location picker removed and the fixture's location dropped, told both authors so, and wrote the conclusion into five documents. Two hours later I read a comment the front-end author had left while obeying me: *"the model's field is `generic_location_id`."* The independent sweep had named that field in its report too, and I had read straight past it. **The register could hold it all along.** I fixed the API instead — the published key is the contract, and translating it onto the model's field is the controller's job — restored the picker and the fixture, and rewrote all five documents. Acted, and read from Postgres: saved, published as `data.location`, and the filter returns 1 of 201.

**And then I over-corrected, and the verification pass caught that too.** Having retracted *"the register cannot hold it"*, I wrote the opposite absolute into nine places: a request's location had *never been saved, by anyone*; no earlier request had one; none could be recovered. My evidence was *"`nrs19`: zero requests with a location"*. **`nrs19` has zero requests.** The reviewer ran one SELECT: `cadra19` holds 80 requests and **all 80 have a location** — written by `POST /home/quick-submit`, the PM scheduler, fleet maintenance and the Odoo form, every one of which knew the field's real name. Only `POST`/`PATCH /requests` dropped it. **So the fix is also a read-side change I had not announced:** `GET /requests` published `location: null` for those 80 and will now show what they always held. It is announced now. *Two absolutes in one afternoon, each reached by stopping at the first query that agreed with me.*

**The fixture and the smoke test now FAIL unless the location comes back.** That is the assertion nobody had ever made. *A 201 was taken as evidence that what was sent was kept, for the life of the suite.*

It is the depreciation-method bug one layer down: a published name, and the thing underneath answering to another. **Worth a sweep nobody has done** — every other published key against the model field it claims to write, on 19. The 400 will now surface the *write* side of any sibling. A serializer that publishes `null` for a renamed field still fails nothing (GO-LIVE §16.3).

**Smaller, and expected once looked for:** `approve-disposal` reads no body, so *any* key is now a 400 — and it is refused before the route looks at the asset, so a stray key on an already-approved asset is a 400 where it was a 409; the `hint` about `stage_id` used to ride on every rejected request field and now appears only when `stage_id` is the field; one test (`is_test_fixture` cannot be set by the caller) proved the derivation by reading the record the create made, and there is no such record now — the refusal is proved over HTTP and the derivation is left to the in-registry test that already held it.

---

## 3 · What `no_disposal_date` now means

**A legacy row; an asset registered as already disposed with no date given; or a date somebody later cleared. It is a finding about legacy rows and deliberate gaps, no longer about last week's disposals** — as you expected, and it is stated rather than discovered: `INT-10` §2.9, the changelog and `DECISIONS.md` all say it.

The model stamps the date and the condition whenever an asset *becomes* disposed, by any writer; both `action_condemn` overrides that each stamped it are deleted. **Measured across eight databases before this handoff's tests ran: two undated disposals — `pytest-h29-undated-disposal` on `test19` and `H23 disposal probe` on `jaizbankplc`. Both are our own probes.** So the finding's opening balance on real data is zero. *(My own new test — an asset registered as already disposed gets no date — then added one to `test19` on every run, permanently, because the asset sits at a location and can never be deleted. Three, before the reviewer counted them. The test now dates the asset once it has made its assertion.)*

**Two judgements inside it that are mine, and one door I left open:**

- **A `condition` sent beside `state: disposed` is overridden.** `decommissioned` is what disposed *means* on this register, and a disposed asset in `good` condition is how the condition tiles came to count things that are gone.
- **`create` is not stamped.** An asset *registered* as already disposed was disposed of on a day this system never saw. Stamping today would replace a finding the report can show — *no date* — with a date that is wrong, which it cannot.
- **`disposal_date` is writable, so `PATCH {"disposal_date": null}` un-dates a disposal.** The one remaining way to make the finding on a new disposal. Named in the register, not shut: nobody ruled on it.

**The tests that needed an undated disposal now make one the honest way** — they are simulating a *legacy row*, so they null the date with raw SQL and say so.

---

## 4 · Tests — denominators first

```
# CI's order. The HTTP suite FIRST, against test19.
$ CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
1002 passed, 8 skipped in 265.00s              # the FINAL run
#   The FIRST full run, before a single test was touched: 17 failed, 914 passed, 12 errors.
#   All 12 errors were one fixture — `test_request`, on `location_id` (§2).
#   New file, tests/test_rejected_fields_are_refused.py: 28 tests over ELEVEN routes.
#   8 skipped is this tenant's known figure, the same eight categories.

# then the in-registry suites — CI's command, eleven modules, --workers=0:
$ odoo -d test19 -u <CI's 11 modules> --test-enable --stop-after-init --workers=0
0 failed, 0 error(s) of 775 tests when loading database 'test19'
#   grep 'of 0 tests|CRITICAL' -> 0. The denominator reconciles at every step:
#   733 (handoff 30) + 12 mixin + 5 label + 8 retrieval + 15 asset_event + 2 = 775
#   (the 2: one disposal-report test, one depreciation test).
#   Counted in the log rather than trusted: 12, 5 and 8 STARTED by name, and
#   test_asset_event went 95 -> 110 between handoff 30's final run and this one.
#   The FIRST in-registry run after custody and movement adopted the mixin — before any
#   test had been written or adjusted for it — was 0 failed of 734. That is the evidence
#   for §1: the adoption changed no behaviour.

# the browser, against test19 — never the default, which is a client's replica:
$ E2E_ORIGIN=http://test19.localhost:8069 npx playwright test
2 failed · 4 skipped · 141 passed (9.0m), zero flaky
#   The two are the two `docs/GO-LIVE.md` §13.5 item 13 records as failing on `dev`.
#   All new specs passed, including the sweep: every Save in the app, pressed.
```

**Acted before any test existed**, against `test19`, and the rows read from Postgres: the eleven routes' refusals, `mark-found`, a bare `PATCH` into `disposed`, verify on a disposed asset — and the idempotency sequence §2 rests on (400 · 400 · corrected body under the same key 201 · 201, one asset).

**The fan-out — read from each database, not from exit codes:**

```
db           | register    | api         | api_mark_found in the enum | Mark Found on the form
cadra19      | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
nrs19        | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
gtb19        | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
test19       | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
nrs          | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
lasg         | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
gtb          | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
jaizbankplc  | 19.0.1.17.0 | 19.0.3.11.0 | 1 | 1
```

Eight upgrades, one at a time, each `exit=0`, zero `ERROR`/`CRITICAL`. **No new table and no new column** — a selection value and two views.

---

## 6 · What the verification pass found

A fresh reviewer over the whole backend and every new document. **It found no blocking code defect: the mixin adoption and `_stamp_disposal` hold up under a method-by-method comparison against `HEAD`.** What it found was five false claims — *the class of thing this handoff had already retracted four times before it ran* — and two routes nobody had counted.

1. **The correction in §2 over-corrected, and it reached the audit contract.** Covered there: *never saved, by anyone* was as wrong as *the register cannot hold it*, and my evidence for it (`nrs19`: zero requests with a location) was vacuous because `nrs19` has zero requests. Nine places corrected, and the read-side change announced.
2. **A twelfth door, of a shape my search could not see.** `POST /home/quick-submit` and `POST /integrations/sap/employee-sync` CREATE records from a body by passing it to a function that takes `**kwargs`. Send quick-submit the sibling route's `request_text` and it raises a request with no description, 201 — and it swallows a non-integer `service_id` or `location_id` with a bare `except: pass`, which is rule 3 verbatim. **Not an allow-list, so grepping for allow-lists missed it. That is exactly how the eleventh was missed, twice in one handoff.** Registered, not ruled (GO-LIVE §16.3 item 10), and the endpoint reference now says what the ruling does *not* cover rather than leaving an "every" that is not.
3. **`PATCH /settings/branding` refused AFTER writing.** `{"primary": "#123456", "name": " "}` stored the colour, then answered 400 — `err()` does not roll back. Pre-existing, and precisely the rule §B states. Three lines moved; a test now proves the colour is unchanged, with a probe colour nobody would choose so that "unchanged" cannot pass by coincidence.
4. **My own new test was minting permanent undated disposals.** *An asset registered as already disposed gets no date* created one per run, at a location, so it can never be deleted: `test19`'s `no_disposal_date` finding would have grown by one for ever. Three had accumulated before the reviewer counted them. The test now dates the asset once it has made its assertion.
5. **`no_disposal_date` has three doors, not two.** I wrote "one of two things only" into `INT-10` while naming the third — a writable `disposal_date` that can be cleared — two paragraphs later in the register. The auditor's document carried the absolute and not the exception.

**Also corrected:** `details.writable` is *what this deployment can store* only on `/requests`; everywhere else it is the allow-list. The changelog said eleven routes named their dropped keys when ten did and the eleventh named nothing. A cited section number, a comment pointing the wrong way, a stale line number in a script, and "nineteen files" carried from report 30 rather than counted (it is about twenty).

**Registered, not fixed:** the disposal stamp keeps a *stale* `disposal_date` — one PATCHed with last year's date and disposed today is dated last year, and *"a date the caller sent is respected"* cannot tell a date sent with the disposal from one sent months before it.

---

## 7 · Wall-clock and the correction share

**About 2 h 20 min of work across nine hours on the clock.** Step 0 at 14:59, the last green run at 00:02. Two of the three agents I was running were killed by a usage limit mid-task and were resumed from their transcripts; a third — the first verification reviewer — died having read one file. Both numbers, because the first is an estimate and the second is not.

**Correction share: more than half, and for the first time most of it was mine rather than the work's.** In the order it cost time:

1. **The request location, twice.** Two absolutes in one afternoon, each reached by stopping at the first query that agreed with me, each written into five to nine documents before it was checked, each caught by somebody else — the first by a comment an author left while obeying my wrong ruling, the second by a reviewer running one SELECT. **That is the same failure as the "34 real cases" in report 30 and the false `require_jwt` fact in report 29, and knowing about it demonstrably does not prevent it.** What would have: `nrs19` returning zero was one `count(*)` away from being exposed as vacuous, and I did not run it because it already said what I expected.
2. **The verification pass** — five false claims, two uncounted routes, one route that wrote before refusing; a test written, three suites re-run.
3. **Coordinating three agents through a usage limit**, including overwriting one author's file when I misread its silence as a stall. It had been blocked on a five-minute test run. Restored from its own context; its version was better than mine and is what shipped.

**What I would tell the next Builder.** *The query that agrees with you is the one to run twice.* Both of this handoff's false absolutes survived because the first measurement I reached confirmed what I already believed, and I stopped there — once on a database with no rows to disagree, once on a field name that was not the one being written. A denominator would have caught both: **not "zero have it" but "zero of how many".**

---

## Commits

- `c08a120` — docs: handoff 31 — one answer per rule (the instruction file, on `dev`)
- `cd5493e` — feat: one answer per rule — the append-only guard written once; a refused field is a 400
- this report, in the commit after it
- **PR #82** — https://github.com/wmlmetro/Cadra/pull/82 — `feat/one-answer-per-rule` → `dev`. The merge is the owner's.

## 5 · `transferred` — the question for NRS

**What the register does today if somebody sets it by hand: nothing at all, and that is the finding.** I looked for every reader rather than recall one. `transferred` is a published status, a list filter, and an option in the app's edit form (the Odoo form's status bar is display-only and does not even show it). Setting it writes an append-only *Status changed* event, like any other change. **And then no rule anywhere treats the asset differently from an active one:** it keeps its location and its custodian and both can still be changed; it can be moved, verified, marked missing, condemned; it goes on depreciating; it stays on a leaver's clearance list; it is counted in every total that does not ask specifically for `active`. The app shows a *Transferred* pill and files it under *Not in service*; the asset dashboard has tiles for Active, Under Repair, Missing and Condemned and **none for Transferred, so on a register that used it the strip would not add up.** Nothing in the code writes it, and no asset on any of the eight databases has ever carried it. *(Last handoff an author told me the app "maps transferred to Active for display". It does — for an EMPLOYEE's SAP status, a different enum in the same file. I had not written it down; I checked it today because I was about to.)*

**The paragraph, for you to put to them:**

> *The register has a status called "Transferred", alongside Active, Under Repair, Missing and Disposed. Today nothing in the system ever sets it and no asset has it, so we would like to know what NRS means by it before we either build it or remove it. **When NRS transfers an asset, where does it go?** If it moves between NRS offices or departments, the register already records that as a move and a change of custodian, and the asset stays Active — in which case "Transferred" means nothing extra and we will remove it. But if an asset can leave NRS's books altogether — handed to another agency, another tier of government, or returned to a donor — then it is a different thing: like a disposal, it should be final, it should record who authorised it and to whom it went, it should stop depreciating on NRS's books, and SAP will need to be told. **Does that ever happen, and if it does, who approves it and what paper is produced?***

**If the answer is that it means nothing, it is removed under this release's announcement** — it is a published enum value, so removal is BREAKING, and the changelog entry for the 400 is already open.
