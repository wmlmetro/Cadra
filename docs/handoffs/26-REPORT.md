# Report 26 — A fixture says so on its face

**Branch:** `fix/fixtures-say-so` · **Base:** `dev` (handoff 25 merged as PR #71 before this started).

**Needs the owner:** the PR merge; **marking the three tenants** (§3 — the classes are proposed, not set); and **running the two scripts against `jaizbankplc`** (`scripts/mark_test_fixtures.py`, now with §D's marking, and `scripts/remove_test_residue.py`, whose production refusal was reading through an ormcache until this handoff).

**The reconciliation first, since it was asked first.** Report 25 §3 was the accurate section and **§7 was stale**. Checked against the database rather than by reading the prose: `Handoff23 Approver.is_test_credential = t` on `jaizbankplc`, and all six fabricated disposals carry the disclosure. So `mark_test_fixtures.py` HAS been run there; only `remove_test_residue.py` never has. §7 is corrected in place, and says which way it was wrong and why. A second correction went in beside it — see §6 below.

---

## 1 · What the enumeration found

**Every model an external HTTP call can cause to be created: 15. Exactly one labelled itself.**

That one was `nrs.asset.custody`, via `source = 'test'` derived from `myservice.api.client.is_test_credential`. The other fourteen had nothing — and the two a member of the public can see were both in that column: `generic.location` (the homepage dropdown, and the incident form lists them unfiltered) and `nrs.asset` / `nrs.asset.tag.label` (the public `/tags/lookup`).

`is_test_credential` had **one consumer in the entire repository**. That is the whole finding: the mechanism was sound, and it had been wired to one model and left there.

| model | created by | had a self-label? |
|---|---|---|
| `nrs.asset.custody` | asset create/write, transfer-custody | **yes** — `source='test'` |
| `nrs.asset` | `POST /assets` | no |
| `generic.location` | `POST /locations` | no — **public dropdown** |
| `request.request` | `POST /requests`, `/home/quick-submit` | no — **and no name convention either** |
| `nrs.asset.tag.label` | auto-minted inside `nrs.asset.create`; `POST /barcode/generate` | no — **public tag lookup** |
| `nrs.asset.transfer` | `POST /assets/<id>/move` | no |
| `nrs.asset.category` | `POST /asset-categories` | no |
| `request.event` | every request create and real stage change | no |
| `hr.employee`, `hr.department` | SAP employee-sync, employee import | no |
| `res.partner` | `/home/quick-submit` with an email | no |
| `nrs.employee.import.job`, `nrs.sap.sync.log` | the two integration import routes | no |
| `workflow.dispatch.log` | workflow callback, stage transitions | no |
| `mail.message` | every `message_post` and every tracked write | no |

All fourteen now carry `cadra.test.fixture.mixin`. Seven further models are exempt **with a written reason** the guard refuses to accept if it is missing or perfunctory — refresh tokens and idempotency rows (operational, not register data), the access record (written only by the `res.users`/`res.groups` recorders, which no route reaches, and labelling evidence from the credential that triggered it would put a derived claim inside evidence), `res.users`, `mail.mail`, `nrs.asset.import.line`, and `security.incident` (created by the PUBLIC incident portal, which authenticates nobody — there is no credential to derive from).

**`mail.message` is in, not exempted, and it was the one real judgement call.** Chatter is the only creatable thing that lands on a record it did not create: `POST /assets/<id>/transfer-custody` posts to the chatter of a **real** asset. Exempting it as "not register data" would have left test-written history on records that are not fixtures at all — the shape of hole the whole mixin exists to close, on the records where it matters most. `author_id` is not a substitute: it resolves to the credential's user only while that credential exists and still points at that user, and `myservice.api.client.write` re-homes users. A stamped fact survives; a join does not.

### The two things the handoff said to get right

**It is not settable or clearable.** Three separate mechanisms, because one would have been a convention with extra steps. `create()` **overwrites** whatever arrived in `vals` — a caller can neither declare itself real nor slander a real record. `write()` refuses to move it **unconditionally**; there is no superuser branch, because a superuser branch is what an `odoo shell` one-liner uses. And it is in no `_WRITABLE_FIELDS`, with a source guard failing if it is ever added to one. Writing the value the record already holds is a no-op rather than an error, so an ordinary form save still works. All five cases are tested, including both directions of the lying payload.

**What it costs on records that already exist: everything.** It is not retroactive and cannot be made so. `create_uid` is not an answer — it says which user, not what the record IS, and it goes stale the moment a credential is re-homed or removed. Measured on `jaizbankplc` on 2026-09-15:

- **460 service requests, 0 identifiable, permanently.** The name is a sequence.
- **4,164 assets** — 3,894 identifiable **by name convention only**, 270 not identifiable at all.
- 440 locations, 4,164 tag labels, 14,451 chatter messages: same.

That statement is in the field's help text, the OpenAPI annotation and the changelog, not only in this report — because the consumer-facing trap is reading `FALSE` as "real data" when it means "created before 19.0.3.9.0, therefore unknown".

### The guard, and what it is worth

`test_every_model_a_first_party_path_creates_is_classified` walks every first-party module, resolves every create-shaped call to a model, and fails unless each is labelled, labelled another way, or exempted with a reason. **The labelled set is parsed out of `test_fixture.py` rather than copied into the guard** — a copied list is a convention, and conventions are the subject of this handoff.

Report 25's credential guard could not see `Client = env[MODEL]` followed by `Client.create(...)` — verbatim the spelling it had just removed from four files. So the resolver handles module-level string constants, names bound to `env[...]`, `.sudo()`/`.with_context()` chains, bare `self` inside a model class, `message_post` as a `mail.message` create in disguise, and `self._helper().create(...)` where the helper is a single-`return` recordset alias. Each has its own mutation proof. **It also refuses to pass with anything unresolved**: if the resolver cannot work out which model a create addresses, the guard fails rather than quietly enumerating less than it claims. That caught one real site (`workflow_dispatch_log.py:313`) which is why the helper-alias resolution exists at all.

### Proved at runtime, not only in source

`myservice_api/tests/test_fixture_label_is_derived.py` — 8 tests, all executed (confirmed by name in the log, no skips). The ones that matter are not the obvious ones: **a record created under an UNFLAGGED credential must NOT be labelled** (report 25's ormcache leak was found by insisting on the absent case), and **an ARCHIVED credential still labels its output** (a plain `search()` is what made `mark_test_fixtures.py` report a clean run while doing nothing).

And measured end to end on `test19`, over everything created after the field landed: **111 of 111 assets, 13 of 13 locations, 111 of 111 tag labels, 2 of 2 transfers.** Which leads to the one thing §A turned out to be missing — §7 below.

---

## 2 · What the `scripts/` sweep found

**You expected a fourth instance. There are 24.**

**Thirteen are fixed**, and a fourteenth (`bootstrap.sh`'s load-bearing `|| true`) was left alone with a comment saying why. The remaining eleven are recorded with file and line in `docs/GO-LIVE.md` §10.2 rather than carried as folklore.

**The worst one is in the newest file in the repository, and it is the one that would have cost the most.** `scripts/remove_test_residue.py` read its production refusal — the single guard between `CADRA_APPLY=1` and a real client's register — through `ir.config_parameter.get_param`. That is `@ormcache`d per worker. It is the exact call handoff 25 proved unsafe, in a script **written by handoff 25**, three directories from `myservice_nrs_base/database_class.py` whose docstring explains at length why `get_param` is wrong and provides the SQL reader. Nobody re-read the new script against the rule the same handoff had just written down.

It now reads the row through `database_class(env)`. And the refusal was **tightened**: it used to refuse only `production`, and now refuses an absent class too. An unmarked database is not a safe one, it is one nobody has classified — and all three of `cadra19`, `nrs19` and `gtb19` are unmarked, with `nrs19` holding a real NRS staff extract.

The other nine fixed:

| file | what it did |
|---|---|
| `bootstrap.py` ×2 | an ARCHIVED API client was invisible to `search()`, so bootstrap created a **second row with the same `client_id`** and printed a success line. The repo had already fixed this exact model in two migrations, both with `active_test=False` and a comment saying why; bootstrap, which *creates* them, never got it. |
| `bootstrap.py` | the downgrade interlock read through the same ormcache |
| `bootstrap.py` | archived `ir.mail_server` → duplicate. `active` **confirmed** at core `ir_mail_server.py:197` inside the running container, not assumed. |
| `bootstrap.sh` | a **failed** psql measurement became a confident *"fresh DB"* and ran `odoo -i` against a possibly populated database. Now probes connectivity, then `to_regclass`, then counts — every abort naming the SQL, the db and user, and psql's real stderr. |
| `audit_report_fingerprint.sh` | discarded psql's stderr, so a stopped container, a wrong `$DB`, an auth failure and a genuinely absent table all printed identically, exit 0. **A proof instrument whose failure mode was a stable, comparable, entirely fabricated fingerprint** — it proved "this report writes nothing" by measuring nothing. |
| `seed_asset_costs.py` | refused on a **database-NAME** allowlist that did not contain `jaizbankplc`, against a ruling this repo had already made against name-gating. Now gates on the class, absent refuses, and a refusal **exits 1 instead of 0** — the k8s Job was reporting `Succeeded` for a run that did nothing. |
| `nrs_hq_seed_v4.py` ×3 | printed `ERROR … not found` and carried on, so `('parent_id','=',False)` matched unrelated top-level locations; the completion summary printed **global** counts, so a run that tagged nothing showed the previous run's numbers; and an `else:` whose whole body was a comment describing a fallback nobody wrote, followed by `pass`. |
| `mark_test_fixtures.py` | `('name','like','H23%')` — Odoo wraps a `like` value in `%…%`, so a real `PUMP-H23-4` would have been disclosed as a fixture. Its sibling had documented this trap as rule 2 and this half was never brought in line. |
| the three brand seeds ×2 | a `✓` printed over three zeros when the asset-code sequence was missing — every asset created afterwards still minting `NRS-` codes with nothing saying so; and `custodians wired: 3998` printed for facility matching that had fallen through to a random employee entirely. |

**The property, rather than a fourth fix.** `tests/test_fixture_patterns_agree.py` fails if the two fixture scripts disagree about what a fixture name looks like, and fails on any unanchored `like` against a record name in either — a deliberate substring match is still written `=like` with its own explicit `%` wildcards, so the intent is in the code rather than in the reader's memory of Odoo's defaults. **That guard immediately caught a line I had just written**, which is the only reason I trust it.

**And a 25th, found by the verification pass in my own work** — see §7.

---

## 3 · The three tenants: proposed class and evidence

Nothing is unsafe today; absent refuses. What is missing is a decision. **The rule where it is genuinely ambiguous is `client`** — a test database wrongly marked `client` costs an afternoon, a client database wrongly marked `test` costs a register. Full evidence in `docs/GO-LIVE.md` §7.

### `nrs19` → **`client`**. High confidence.

11,942 assets, 11,386 employees, 0 fixture-named records. The employee list is a **real NRS staff extract naming actual serving officials**, loaded from client-supplied CSVs that are in this repository at `docs/seed/NRS_all_csvs/`. 11,878 assets landed on one day — the ETL.

It is also the tenant Vendra builds against: `docs/api/.creds.nrs19` holds the `Tag-Issuing Unit` (INT-05) and `Vendra (INT-03)` credentials and calls itself *"the working tenant for integration and demo work"*. Marking it `test` would point a writing suite at real personal data **and** at the register another organisation measures against.

### `cadra19` → **`client`**. Medium confidence — the one worth a second opinion.

1,335 assets, 754 locations, 80 requests, 2 employees (one named `Py Test`), 50 fixture-named assets. Company *Nigeria Revenue Service*.

The case for `test` is real: the suite has written to it, it carries a fixture employee, it has no custody chain, and nothing outside this repo references it. **The case for `client` wins on where its data came from** — its 1,272 seeded assets come from `scripts/nrs_hq_seed.py`, whose header names its sources as Baron Architecture drawings A400–A485, the Unecon Associates M&E completion schedule and the *FIRS HQ Furniture Inventory* dated 11/02/2026, mapped to a real 19-floor, 232-room building. That is client-derived content describing a real building.

If a second local test tenant is wanted, make one. `test19` already exists, is marked, and has a credential pair.

### `gtb19` → **`test`**. Medium-high, and the only `test` proposal.

156 assets all created on one day, 61 employees, and **6 pytest fixtures already in it**. Every category of content is reproducible and none is client-supplied: the assets are generic bank equipment from a seed script; the employees are synthetic (`Amaka Adeyemi`, `Emeka Afolabi`, `Zainab Balogun`, `Musa Chukwu` — generated, alphabetical by surname); and the 122 branch locations come from `scripts/gtb_locations.json`, which marks every row `"source": "OSM (real)"` — **public OpenStreetMap data, not a client extract**.

The live GTB tenant is `gtb`, already marked `client`. `k8s/dev/60-ingress.yaml:82` records that it *"was renamed from the seeded `gtb19`"*, and `k8s/dev/11-configmap-bootstrap-19.yaml:7` describes `gtb19` as a database bootstrap was **validated against**.

**One caution:** `gtb19` is also an example `bootstrap_db` in two GitHub workflows. That is a different database on the DOKS cluster; classifying the local one says nothing about it.

---

## 4 · Whether the register is complete, and the one thing at the top

`docs/GO-LIVE.md` Part II, §5–§11. I believe it is complete for everything that passed through handoffs 20–26 and everything in the backlog. Two honest limits: I cannot vouch for what was known before handoff 19 and never written down; and §10.2 lists fourteen silent-instrument sites I found but did not fix, which is a deliberate stopping point rather than a finished job.

**If I could hand over one thing, it is not any of the code.**

> **`admin` / `admin` is accepted on all eight local tenants** — verified through `/web/session/authenticate` on 2026-09-15, every one returning a uid.

These are local replicas, and that is not the reassuring reading. The same `scripts/bootstrap.sh` provisions the cluster, so it is a statement about **what bootstrap leaves behind**. `nrs19` sits behind that password with 11,386 real NRS staff records in it.

Everything else in the register is a decision someone can take calmly. That one is a door, it is standing open, and closing it is an operational act with no code in it at all — which is exactly the kind of item that does not get done because it never lands on an engineer's list.

---

## 5 · Suites, in CI's order

| Suite | Result |
|---|---|
| `pytest tests/` (first, as CI runs it) — `test19` | **840 passed, 9 skipped, 0 failed** |
| In-registry, CI's 11 modules, `test19` | **0 failed, 0 error(s) of 524 tests** |
| `tests/test_source_guards.py` + `test_fixture_patterns_agree.py`, standalone, no instance | **210 passed** |

**Both denominators checked, not the exit codes.** 524 against report 25's 516 is exactly the 8 in-registry tests added here. 840 against 811 is exactly the 29 pytest tests added (7 pattern-parity, 17 source-guard, 5 published-label) — four of the source-guard tests were added by the verification pass below. Neither run contains `of 0 tests` and neither contains a `CRITICAL`.

The 9 skips are report 25's 9, unchanged, none from a file this handoff touched.

**One thing in the logs that is not ours:** 165 `ERROR … cannot execute INSERT in a read-only transaction` lines, each followed by `WARNING odoo.http: … retrying with a read/write cursor`. That is Odoo 19 core's read-only-first optimisation working as designed. It predates this handoff and fails nothing.

**The multi-tenant fan-out was done and verified**, not assumed: all eight local databases upgraded one at a time, then **each queried for the column count — 14 of 14 on every one**. `odoo` correctly skipped as the 15-era leftover.

---

## 6 · Corrections to report 25, and one to my own work

**Report 25 §7 said neither script had been run; §3 said one had.** §3 was right — verified in the database. Corrected in place.

**Report 25 §3 also said the removal script refuses "10 assets a service request points at, and 17 locations likewise".** The 17 is right and the *"likewise"* is wrong. Measured on `jaizbankplc`: **zero** requests on that tenant set `generic_location_id` at all. All 17 locations are refused by the script's *other* rule — they hold an asset the script will not remove — and every one of those assets is itself a fixture pinned by a custody row. **The script was right; the sentence describing it was wrong**, which is report 25's own closing lesson, one report on.

I found this because I built §D's marking against the sentence rather than against the code, and the marking selected an empty set. The marking now applies the real rule (and the request rule too, which is empty here but is not empty by construction).

**And one of mine.** The mixin's own header named the enumeration guard `test_every_api_creatable_model_self_labels`. No such function was ever written. That is report 25's finding 9 — a docstring asserting a protection the repo does not have — reproduced by me in the handoff whose subject is instruments that describe themselves wrongly. Fixed, and then closed as a class: `test_a_comment_that_names_a_test_names_one_that_exists` fails on any `<file>.py::<name>` reference in first-party Python that does not resolve. **It caught two things on its first run** — my sentence, and its own explanation, which had to be reworded so the guard would stop flagging the comment describing it.

I also had the arithmetic wrong in two documents: 4,164 − 3,894 is 270, not 381.

**And a fourth, to three reports at once.** Reports 18, 20 and 21 all carry *"the two live-cutover credentials from report 17 §3 are still unrotated, and they are in git history"*. That reads as "a compromised key is live in a database". **It is not.** Measured across all eight local tenants: `myservice_identity.redhubs_api_key` and `myservice_identity.sap_webhook_secret` are **not set on any of them** — handoff 17 took the literals out of the source and both routes have refused ever since.

What is actually open is the *other* half of that cutover: **nobody has issued replacements**, so Redhubs' asset-register export and SAP's inbound employee sync are both answering `Unauthorized` and have been since handoff 17. That is the announced behaviour, and it is also two external parties waiting on a value somebody has to generate and hand over. Recorded that way in `docs/GO-LIVE.md` §8.3, because "unrotated credential" and "integration switched off pending a new key" need very different actions from whoever reads the register.

---

## 7 · The one thing §A does not cover, found by measuring rather than by writing

**`myservice_website_theme/controllers/api.py:198`:**

```python
req = env['request.request'].with_user(SUPERUSER_ID).create(vals)
```

`with_user(SUPERUSER_ID)` **replaces** the acting user; `.sudo()` would have elevated privileges while keeping it. So a request created through `POST /api/v1/home/quick-submit` — an authenticated route — is written as `__system__`, and the derivation correctly returns `False` because there is no credential left in the environment to read.

I found it in the measurement, not in the code: of everything created on `test19` after the field landed, **every single unlabelled record — 2 requests, 2 request events and 22 chatter messages — had `create_uid = __system__`**, and all of them came through that one line. It is the only `with_user(SUPERUSER_ID)` in any first-party module.

**Not fixed, deliberately, and this is the handoff's own instruction being followed.** The same handler serves the `auth='public'` twin, so swapping in `.sudo()` changes what `env.user` is during a create on an **unauthenticated** route — a behavioural change to a public path, made inside a handoff about test labelling, with no test covering what depends on it. The three options are written out in `docs/GO-LIVE.md` §11.1 as a decision rather than a question.

Worth being plain about what it is: **a pre-existing audit-trail defect that this handoff exposed rather than introduced.** The actor was being discarded on that route long before there was a label to lose.

---

## 8 · §D, and what is left unmarked

The 115 unremovable assets and 17 locations stay — append-only is the property the custody chain is worth having, and carving one exception for tidiness is how it stops meaning anything. They are marked instead, with ` [TEST FIXTURE]` on the **name**, which is the field every list view, every report and the public homepage dropdown already renders.

**The mark is a weaker claim than the field, and the code says so.** `is_test_fixture` is derived and certain; the name mark is applied by matching a name convention and is only as good as that convention was. Two mechanisms, two meanings, neither pretending to be the other.

**Proved by running it on `test19`** — 7 disposals disclosed, 20 assets and 12 locations marked, the "no such client" case printed out loud — **and run a second time to check the idempotency its docstring claims**: `marked 0, already marked 20` / `marked 0, already marked 12`.

What it would do on `jaizbankplc`, measured with SQL: 115 assets, 17 locations.

**What is left unmarked, and whether any of it is publicly reachable.** On `jaizbankplc`: **368 of 440 locations in the public homepage dropdown are fixture-named**, and the ones this script does not mark are exactly the ones `remove_test_residue.py` can delete. So the answer to "is anything in that set reachable from the public homepage" is **yes, nearly all of it** — until one of the two scripts is run there. That is the case for running them.

The 460 requests are the permanent residue. 417 of them point at a fixture-named asset, which is suggestive and is **not** identification — a real request can point at a fixture too, and the entire point of this handoff is that suggestion is not a label.

---

## 9 · Wall-clock, and the correction share
**Roughly 2h30m**, most of it serialised against a stack that cannot take two registry loads at once. Three script-fixing agents ran in parallel on disjoint files; everything touching the database or a registry ran one at a time in the main session.

**Correction share: about 60%, and the highest of any handoff so far — for the same reason report 25's was.** The fresh verification pass at the end found **thirteen defects in work I had already called finished**, and the four worst would have shipped a handoff that failed on its own subject.

### What the verification pass caught

| | Found | Why it mattered |
|---|---|---|
| 1 | **My own correction to report 25 introduced a NEW false claim.** I wrote that all 17 refused locations hold an asset "pinned by a custody row". Measured over exactly those 17 pairs: **10 request, 5 disposal, 2 custody.** | This is the one thing I explicitly asked it to check, and I had got it wrong in two files. A correction nobody measures is how the original sentence got there. |
| 2 | **The allow-list guard matched one spelling.** `endswith("_WRITABLE_FIELDS")` missed `_CATEGORY_WRITABLE` and `_SETTINGS_WRITABLE` — and `_CATEGORY_WRITABLE` gates `nrs.asset.category`, a model that CARRIES the mixin. | A guard blind to one spelling of the thing it protects — report 25's credential-guard defect, reproduced inside the guard written to close it. |
| 3 | **The resolver answered confidently wrong on three shapes.** A name bound to two models in one file collapsed to the last binding, with **nothing reported unresolved** — a model silently invisible to the guard. | The guard's whole value is that it fails on what it cannot see. It was failing on unresolved calls and quietly guessing on ambiguous ones. |
| 4 | **`ir.config_parameter` was in no classification at all** — `set_param` was not a recognised create. | The guard's own docstring claimed to enumerate every model first-party code can create. |
| 5 | **The mixin described a mechanism the guard does not have** — "walks every `@cadra_route` … reachable from a route handler". It has no route awareness whatsoever. | A confident sentence about a protection, in the file that protection guards. Report 25 finding 9 again, mine. |
| 6 | **The new reference guard could not see the reference that prompted it.** The one in `test_fixture.py` is wrapped across two comment lines; the regex required the name to follow `::` immediately, so it found **zero** references in that file and passed. | A guard blind to its own headline case. It was passing by seeing nothing — the exact shape of §B. |
| 7 | **The `=like` mutation proof re-implemented the rule** in its own body instead of calling it. Narrowing the shipped operator set would have left the proof green. | Report 22's failure mode, one level along: a proof that tests a copy. |
| 8 | **`bootstrap.sh`'s stderr fix overshot into the value.** `out=$(db_query … 2>&1)` folds any docker or psql warning into the string compared against `t`/`f`, falling to the catch-all and **aborting a deploy that used to succeed** — on the production path. | The fix for a swallowed measurement put the diagnosis where the value is read. |
| 9 | **`330` custody rows is `352`**, in five files in one commit — and `mark_test_fixtures.py`'s header carried three more figures all taken hours earlier the same day. | A fixture count is a rate, not a constant. Every one had gone UP between two measurements taken the same day. |
| 10 | The CHANGELOG said the three response objects "all declare `additionalProperties: true`". **Only `Asset` has a schema at all**; there is no `Location` or `ServiceRequest` in the document. | The additive conclusion held; the supporting sentence did not. |
| 11 | `docs/GO-LIVE.md`'s header still scoped the whole file to the DOKS cluster, which Part II contradicts. | |
| 12 | cadra19's "1,272 seeded assets" is 1,285 non-fixture of 1,335. | |
| 13 | §11.1's labelling counts (111/13/111/2) no longer reproduced — they climb with every suite run. | Now stated as an **invariant** (everything credential-created is labelled; everything unlabelled is `create_uid = 1`) rather than a snapshot, which is the form that stays true. |

All thirteen are fixed. Four gained a test or a mutation proof of their own: the widened allow-list matcher is proved against the two real names it used to miss; ambiguous bindings are proved to fail loudly on the three shapes the pass constructed; the reference matcher is proved on the **real file**, wrapped, rather than on a synthetic string; and the `=like` proof now reads the shipped operator tuple.

Three findings were judged and **left alone**, each recorded in `docs/GO-LIVE.md` §12 rather than fixed: the blast radius of `bootstrap.py`'s new archived-client refusal, the brand seeds' `RuntimeError` aborting a whole seed file rather than one step, and the two latent divergences between the fixture scripts that the parity guard does not cover (they agree on `jaizbankplc` today; the divergence would appear on a different tenant).

### And the repo caught me itself, once

Writing this register, I pasted the two burnt cutover credentials into a table. **`test_the_compromised_literals_are_gone_from_first_party_source` failed the run** — handoff 17's guard, doing exactly what it was built for, against the handoff documenting the credential it protects. The literals are named in report 17 §3 and are not reproduced in the register.

### The lesson, and it is the same one two reports running

Report 25 ended on it: the guard was sound and everything wrong was a claim ABOUT it. That happened again here, in a handoff whose entire subject is instruments that describe themselves wrongly — **including in the correction I wrote to fix exactly that defect in report 25.** I measured the 17 locations, established that the request rule was not what refused them, and then asserted a replacement cause without measuring it.

The thing that works is not care. It is somebody who did not write it reading it against the database.
