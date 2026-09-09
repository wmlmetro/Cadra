# Report 15 — The handlers that swallow what they were written to catch

**Builder** · branch `fix/nothing-swallowed` · base `dev` at `0fb4bfd`.
**Needs the owner: the PR merge** (`gh pr merge` is refused by the Builder's
permission layer).

---

## 1 · The three counts

**50 broad handlers in first-party code.** Every one now carries a
classification where the code is, and `tests/test_source_guards.py` fails on a
new one that does not.

| Outcome | Count | What it means |
|---|---|---|
| **optional** — narrowed or deleted | **21** | The failure was expected and benign, and the handler could be replaced by a type or by a membership test |
| **reported** — raises, or logs at WARNING and admits the gap | **17** | Not optional. An empty answer was a lie |
| **unknown** — broad, logged at WARNING with the traceback | **12** | Genuinely unaccounted-for. The fallback, not the default |

**Not one handler ended up as a broad `optional`.** Every genuinely optional case
turned out to be narrowable to a type or removable altogether — `env.get('some.model')`
answers `None` and `'some.model' in self.env` works, so "the module may not be
installed" is a membership test and never an exception. That is the answer to
your third outcome being the fallback: it is, and 12 is where it landed.

### The number you actually wanted: **24 of the 50 were hiding something live.**

Report 13 found two by accident. A deliberate look found twenty-four. They fall
into four groups, worst first.

**Four features that had never worked, on any tenant, ever.**

- **Compliance Alerts** counted `insurance_expiration_date` on `fleet.vehicle`.
  There is no such field — not in any version of Odoo, not anywhere in this
  repo. The domain parser rejected it, `except: pass` ate the error, and the
  panel has shown nothing since the day it was written.
- **Recent Maintenance** read `lg.service_id`; the model has `service_type_id`.
  The first row of the loop raised, the handler discarded the partially built
  list, and the panel was empty on every tenant that has any service log. Byte
  for byte the `v.state_id` defect you found in report 13 — twenty lines up, in
  the same function, written the same day.
- **The homepage submit form** has returned `{"success": false}` to every
  visitor since the Odoo 19 port. It writes `website_id`, which
  `request.request` does not have, and calls a `crnd_wsd` method that no longer
  exists — the second from **outside** the try, so an address containing an `@`
  got a hard HTML 500 rather than the JSON error.
- **`get_kpis`'s vendor counts** were the surviving half of report 13's vendor
  bug. Same model, same silent zero, still answering `0` on the other endpoint.

**Eight that destroyed or misreported data.** Four import loops caught per row
and called `self.env.cr.rollback()` to isolate the failure. A rollback is not
row-scoped: it discards everything since the last commit. One unmappable
employee erased **every employee written before it in the batch** — up to 199
rows in the xlsx job, the whole request for the SAP webhook — while the counters
and `POST /api/v1/integrations/sap/employee-sync`'s per-row `"status": "success"`
went on reporting them as written. Each site now takes a savepoint.

The same shape reached three more places. `asset_pm`'s cron rolled back the
whole run on one bad schedule and then logged a created count for requests it
had just erased, with no line saying anything had failed. A swallowed inner
failure in `process_sap_payload` left `log` pointing at a row the rollback had
deleted, and all five callers immediately read `log.status` off it — a
`MissingError` out of the handler written to prevent one. And two handlers
promised isolation they did not have: the portal's most likely failure aborts
the transaction, so `request.render()` on the error page died too — **the error
page was unreachable for the error it was written for** — and the
maintenance-ticket cron returned `False` per vehicle on an aborted transaction,
so every remaining vehicle failed on *"current transaction is aborted"* and the
run signed off *"0 ticket(s) created"*.

**Five that lied to an external caller.** `/auth/token`, `/auth/login` and
`/auth/refresh` returned `str(e)` of **any** exception from `jwt_secret()` to an
**unauthenticated** caller in a 500 body; the function raises exactly one thing,
so a database error there would have put Postgres' own text on the public auth
endpoint. The public WorkSpace callback did the same and worse: `get_active_config()`
runs **before token validation**, so an anonymous POST to an unconfigured tenant
got back a sentence naming our own Settings menu — and because the handler
catches, nothing reached Odoo's dispatcher and the request **committed as a
success** before answering 500 and inviting a resend of the whole thing. A
malformed JSON body was answered *"reference field is required"*, telling an
integration to add a field it had already sent. `/callback/test` answered HTTP
**200** for "not configured", so every status check read a never-wired tenant as
healthy. And a 2xx with an unreadable body made `workspace_ref` fall back to a
string Cadra invented, written onto the request as the WorkSpace's own reference
and shown to the approver — an intercepting proxy answering `200 text/html` is
exactly that shape.

**Seven that returned a confident wrong answer.** The email adapter reported
"Email sent" for mail Odoo never delivered — `mail.mail.send()` defaults to
`raise_exception=False` and records failures **on the mail record**, so the
handler never fired and the chatter said *"Sent to NRS WorkSpace"* while the
request waited forever on a message nobody received. `_serialize_location`'s
`asset_count` fell back to `0` on any fault, under a comment claiming the case
was "nrs.asset not installed" — `env.get` already answers `None` for that, so
the handler could only ever fire on a real fault and published "this location
holds no assets" as the answer. `to_status_dict` answered "no errors" for a job
full of them, and a stored value of the wrong shape sliced a string or raised on
an int. `action_validate` never handled valid JSON of the wrong shape. And four
sites rendered `str(e)` alone, which several ORM and psycopg2 errors stringify
to nothing — operators were shown `Row 12: ` and `Parse error: `.

### And one the work found in itself

**`cadra_route` was swallowing the retries Odoo owns above it.** The new custody
`HttpCase` answered `500` on `POST /assets/<id>/transfer-custody` in a run where
`/auth/token` hit the same condition, on the same cursor, and retried into a
200. `/auth/token` is one of the nine routes **not** wrapped by the decorator —
**the unwrapped route was the one that worked**, which is the wrong way round
for a decorator whose job is to make the contract better.

Odoo recovers from two conditions by seeing an exception come out of the
dispatch and replaying the request: `http.py` re-dispatches on a read/write
cursor when a route turns out to write on a read-only one, and
`service/model.retrying` replays up to five times on a serialization failure —
which is how two callers writing the same row both succeed. The envelope's
`except Exception` sits inside both. A clause above every other now re-raises
them untouched. `IntegrityError` is deliberately not among them: `retrying`
re-raises it at once, and the envelope publishes 409 and 400 for unique and
foreign-key violations.

This is the strongest argument in the report for the exercise. The defect was
in the one handler nobody would have audited, because it is the handler whose
entire job is to catch everything.

---

## 2 · Was the pinned inventory the right mechanism?

**Half of it was, and it is the half you already had.** My judgement, since you
asked for it.

The shape **is** detectable, completely and without ambiguity: `except:`,
`except Exception:`, `except BaseException:` and a tuple containing one of them
are the entire vocabulary, and an AST finds every one with no false positives.
What is not detectable is whether a given one is legitimate — which is exactly
the split report 13 hit, so I used report 13's answer and did not invent a
second mechanism: an inline `catch-all: optional|reported|unknown — why`, on the
`except` line, in the contiguous comment block above it, or in the block that
opens the handler body. A new handler without one fails the guard.

**A separate inventory file would have been worse, and for a reason worth
keeping.** A list lives away from the code, so it is updated by whoever
remembers it exists, and the handler it describes is edited by whoever does not.
Within a month it would be a document that disagrees with the source and cannot
say which is right. The comment cannot drift, because the guard requires
contiguity — the moment a line of code lands between the marker and the
`except`, the marker stops applying and the guard speaks up.

**What the inline form gives up** is the one-page view. If you want that, it is
a generated artefact, not a second source of truth — `tests/test_source_guards.py`
already walks every site, so a listing is a report and not a thing to maintain.
I have not built it; say the word.

The guard has ten self-tests: every broad spelling, all three placements, a
narrowed handler needing no marker, a classification word that is not one of the
three, and drift. It was proven to fail before it passed — 29 offenders on the
first run — and the same for the retry-order guard, which fails with
*"cadra_endpoint() swallows ConcurrencyError, OperationalError,
ReadOnlySqlTransaction"* when the clause is removed.

---

## 3 · `docs/ENVIRONMENT-FACTS.md`

**One entry is now understated in the right direction, and one is wrong.**

- **The OOM entry overstates today's machine.** The eight-tenant fan-out ran
  **first attempt on all eight, zero crashes**, following the recipe exactly:
  server stopped, one `run --rm` at a time, retry loop armed and never used. The
  host was at 2.0 GB of 3.0 GB swap, not 21.1 of 22.5. The recipe is right and I
  followed it; what changed is the machine. I have not softened the entry —
  the measurement in it is true of the day it was taken, and the recipe costs
  nothing when the host is healthy.
- **New entry, and it is the one that will cost somebody an afternoon:**
  **in test mode Odoo hands a read/write route a READ-ONLY cursor and relies on
  a retry that a controller-level `except Exception` defeats.** This is why
  `ENVIRONMENT-FACTS` already says the `cannot execute INSERT in a read-only
  transaction` lines are noise — they are, *for routes whose exceptions reach
  Odoo*. For a route inside `cadra_route` they were a silent 500 that only an
  `HttpCase` can see, because the live server never hands those routes a
  read-only cursor. I have added it under **The test suites**.

Also confirmed, since it was left open in report 13's notes: **`mobile_phone`
does exist on Odoo 19's `hr.employee`** (`hr/models/hr_employee.py:121`). The
SAP field map is correct and no employee payload carrying `mobile` fails.

---

## 4 · The three rulings

**B1 · The door out of the seed refusal — built and proven both ways.**
`CADRA_SEED_DESTROY_CUSTODY=1`, an environment variable rather than a prompt,
because the script is piped into `odoo shell` and a prompt there is answered by
whatever the rest of the file happens to be. Proven live:

| | |
|---|---|
| Default, on `jaizbankplc` | `REFUSED. Wiping the register would destroy 283 chain-of-custody link(s) on tenant 'jaizbankplc'` — and it stopped before the wipe |
| Under the flag, on `test19` | printed the count and the tenant, then `Removed 3 chain-of-custody links`; 3 → 0 |

Under the flag the deletion is raw SQL, and that is not laziness: the model
refuses `unlink()` unconditionally including under `sudo()`, and that refusal is
its entire value. Going round it is meant to look like going round it. The
refusal's message names the flag, and so does the comment at the `ondelete='restrict'`.

**B2 · A test-written link says so.** `source: test`, a first-class value
alongside `direct`, `transfer` and `tracking_backfill`, returned by the API like
the others. **Decided server-side from the credential** — a new
`myservice.api.client.is_test_credential` — and never from anything the caller
sends: a request able to label its own write could disguise a real change of
custodian as an artefact, in the one model whose whole value is that its
contents were not invented. A test asserts exactly that, by turning the flag off
and sending `"source": "test"` in the body.

Migration `myservice_api 19.0.3.5.0` marked one client on each of the eight
tenants. `vendra` and `tag_issuing_unit` are correctly **not** flagged — those
write real history.

**Historic links are not relabelled.** `nrs.asset.custody` refuses `write`, and
a migration that made an exception for itself would be the first hole in an
append-only record. The links the suite wrote before today keep `api_transfer`
and carry `test_custody._build_a_chain` in their reason, which is where you
found them.

**One consequence to rule on if you disagree:** `test` **overrides** the route's
own source rather than sitting beside it, so a test-credential write reads
`test` and not `api_transfer`. I took the reader's first question about a link
to be whether it happened at all, which the route it arrived by does not answer.
The `reason` still carries the caller's string. Two existing suite assertions
pinned the old value and now accept either, with the reason written at the
assertion.

**B3 · The chain is exempt from the cap on both paths.** `paginate(uncapped=True)`,
with the reasoning at `utils.CAP_EXEMPT_REASON_CUSTODY` rather than at the call.
`total_estimate` is unaffected — it is the true count on every path, and the
existing AST guards over `paginate()` still pass. The per-page ceiling is
unchanged: it bounds one `SELECT` and is not the commercial control, so a capped
client walks the whole chain with the cursor.

Five new `HttpCase` tests cover it, including **`test_the_asset_list_is_still_capped`** —
without it, "lift the cap on custody" and "stop capping" pass identically, and
the guard for a commercial control would be a test that never noticed it was
gone. Announced in `docs/api/CHANGELOG.md` as a widening.

---

## 4a · What the verification pass found, including one I introduced

A fresh agent — not an author — reviewed the whole diff against the acceptance
criteria. **Eleven real findings.** All are fixed. Two were serious and the
first is mine.

**A narrowing in this handoff reopened handoff 14's defect, wider.** `jwt_decode`
reads `header.get("alg")` off whatever the header segment decodes to. `[]`,
`"x"` and `1` are all valid JSON and none of them has `.get`, so the
`AttributeError` is not a `ValueError`, escaped the clause I had just narrowed,
escaped `require_jwt` (which catches only `JwtError`) and escaped `cadra_route`
— whose try begins **after** the auth call — and Odoo rendered its own HTML
error page. `Bearer W10.e30.c2ln`, no credentials, **every authenticated route
in the API**.

Fixed by settling the shape rather than widening the clause: catching
`AttributeError` would have worked and taught the wrong lesson, because the
real defect is that a JWT header is required to be an object and nothing said
so. Two tests assert the body is JSON before they assert anything else, and
were **proven red then green against a live tenant** — without the check the
response is literally `<!doctype html>` `500 Internal Server Error`.

This is the finding that justifies the verification pass on its own, and it is
the second time in this handoff that the thing hiding a defect was the code
written to prevent one.

**The custody lookup read a column across a module boundary it does not depend
on.** `myservice_asset_register` was reading
`myservice.api.client.is_test_credential` while not depending on
`myservice_api` — and `myservice_api` depends on **it**, so the dependency
could not simply be declared. Odoo's graph therefore could not order the two: a
tenant carrying the new Python against the older schema would have raised
`UndefinedColumn` on **every** custodian write — the API create and patch, the
transfer route, the transfer completion, the employee-departure clear, the Odoo
form, the importer. One registry serves every database here, so that is a
cross-tenant outage produced by a single-module upgrade.

The policy now lives in `myservice_api` as an override of a new
`nrs.asset.custody._resolve_source`, so the column and the code that reads it
ship in one module and move together. The vocabulary stays on the base model —
the value is the model's, the policy is the API's. It is also `ormcache`d on
the user id, because `_record` runs **per record** from `create` and `write`: a
ten-thousand-row import with custodians was ten thousand extra queries.

The other nine, briefly:

- The marker convention let a comment in the **tail of a try body** classify the
  handler below it — contiguous, and about the statement above it. My guard's
  own docstring asserted that could not happen. Indentation settles it, and
  there is now a test for exactly that shape.
- The dashboard comment claimed `ok()` attaches `truncated` inside `data`. It is
  a **top-level** key, as CLAUDE.md rules and for the reason it rules. Comment
  corrected, and the changelog now says both `_warnings` exist at different
  depths so a client knows to look in two places.
- The website form's partner resolve was **still outside** the try it was
  supposedly moved into — the fix named the right defect and left it in place.
- The public WorkSpace callback could still render HTML at a machine if the
  config lookup failed for a non-`UserError` reason, which is the one thing its
  own comment forbids.
- A comment claimed all three `process_sap_payload` callers catch a raise. The
  SAP webhook does not.
- `today_s` was left assigned and unread, in the block whose comment
  congratulates itself for removing an unread variable.
- My own new `HttpCase` had a fixture-order bug and could not pass; caught by
  the run, fixed before it reached CI.

**Categories where it found nothing**, which is worth as much: all six savepoint
scopes are correct (no surviving `commit`/`rollback` inside one, the `log` row
survives its rollback, the one nested savepoint is legal, `continue` releases
rather than rolls back); handler order is right in every new multi-clause try;
every narrowing other than `jwt_decode` is sound; the seed script's door cannot
be bypassed and its `DELETE` is complete; `paginate(uncapped=True)` keeps
`total_estimate` true; and every factual claim in the new comments checks out
against Odoo 19 in the running container.

---

## 5 · Verification

| | |
|---|---|
| External API suite (`jaizbankplc`) | **309 passed, 27 skipped** — the documented healthy skip count |
| In-registry Odoo tests (`test19`) | **0 failed, 0 error(s) of 186 tests**, exit 0 |
| Source guards | **66 passed** |
| Tenant fan-out | 8 of 8, first attempt, zero crashes, zero `CRITICAL`, run twice |

**The denominators are quoted, per the CLAUDE.md edit this handoff carries.**
The failing in-registry run before the fixes reported the same **161** the
passing one did, which is what makes it a genuine pass rather than a collapsed
one; 186 is that plus the twenty-five added here.

**Twelve new tests, and ten of them were proven red before green.** The two
custody credential tests and the two malformed-token tests were run against a
live tenant with the fix removed — the malformed-token one returns literally
`<!doctype html>` `500 Internal Server Error` without it. Eight of the ten
regression tests for the savepoints and the dashboard panels go red when the
old `cr.rollback()` and the old `lg.service_id` are put back, and green when
they are restored. A test that has not been seen to fail is a test of nothing,
and this handoff is about exactly that class of mistake.

Three external failures on the first run were all real and all fixed — two
suite assertions pinned to a `source` the credential now overrides, and
**`test_quick_submit`'s success branch, which had never executed** because the
endpoint it covers has been broken since the 19 port. It expected 200 for a
create.

### The regression tests that did not exist

`myservice_identity` had no `tests/` directory at all, so the savepoint change
— announced in `docs/api/CHANGELOG.md` as a published behaviour change — had
nothing asserting it. It now proves the actual regression: employee A survives
employee B failing in the same batch, B's row says `error` with the exception
type in it, C is still created, and the error lands on the row created
`pending` rather than a replacement. The failing payload is **data**
(`hireDate: "not-a-date"`), not a monkeypatch, so it fails identically on any
tenant.

`get_fleet_command` had no test, which is why `lg.service_id` survived. The new
one **creates a service-log row**, because a model with no rows produces
output identical to the bug — that is precisely why nobody caught it — and then
asserts the panel is not empty.

---

## 6 · Open, and yours to rule on

1. **The Fleet Command tab is DEAD in the Odoo web client on 19.**
   `myservice_dashboard/static/src/js/dashboard.js` is an `odoo.define` module
   requiring `web.AbstractAction` and `web.rpc`; I confirmed against the running
   container that **neither exists anywhere under `web/static/src/` on 19**.
   Third instance of exactly what you met as R46 in handoff 10. So the panels I
   fixed reach a user only through `GET /api/v1/dashboard/fleet-command` and the
   SPA — and `data._warnings.unavailable` has no reader in the Odoo client
   because that client cannot load. Fixing the panels was still right; making
   the tab work is a separate piece of work and a separate decision.
2. **`fleet_command_patch.py` at the repo root is tracked and carries both dead
   field names.** It is the one-shot generator these two panels were copied
   from, writing to `/opt/odoo/myservicenrs/...`, a path that does not exist on
   any current machine. It will re-seed both defects for anyone who reads it as
   a reference. I have **not** deleted it — that is a tracked file and outside
   what the handoff asked for — but the handoff-09 precedent on the repo-root
   `odoo.conf` says the answer is probably deletion.
3. **The public WorkSpace callback's status codes changed** (503 for an
   unconfigured tenant, 400 for unparseable JSON, 503 from the probe that used
   to answer 200). That is `/myservice/workflow/callback`, not `/api/v1/*`, so
   `docs/api/CHANGELOG.md`'s own rule does not reach it — and there is no
   document that does. It is a published surface with no published contract.
4. **`asset_pm` has two more of the family, neither swallow-related.** The
   already-created check matches on translatable stage **names**
   (`not in ['Resolved', 'Closed']`) where `request.stage.closed` is the boolean
   that means it — the same shape as report 13's `stage_id.code == 'progress'`,
   working today only because the stock data happens to match. And the PM
   description is passed as `request.request.name`, the Reference field, so PM
   requests carry no sequence reference.
5. **49 first-party catch-alls sit outside the guard's scope**, and this is
   the one acceptance criterion I have not fully met. The guard walks the Odoo
   modules, where it is complete; it does not walk `scripts/`, `seeds/`,
   `docs/api/smoke_test.py`, `tests/conftest.py` or the loader scripts at the
   repo root. That is measured, not estimated, and the number is now written
   **in the guard** so nobody reads a green run as "there are none" — which
   would be this handoff's own defect, one level up.

   I classified `scripts/bootstrap.py` by hand regardless, because it
   provisions the credentials every tenant authenticates with and because this
   handoff edits it. One of its three was narrowed: the canonical-scope import
   was a broad catch that would have hidden a typo in `ALL_SCOPES` behind a
   hard-coded list, and that list decides what every client in the estate is
   provisioned with.

   Widening the guard is a real decision rather than an omission — it puts ~46
   one-shot tenant seeds in front of CI, and a seed's `except: pass` around an
   `env.ref` is the genuinely optional case the convention says to narrow
   rather than annotate. Yours to schedule.
6. **A latent one in `workflow_config`.** `_send_to_workflow` stores the payload
   with `json.dumps(..., default=str)` and `requests` serialises it for the wire
   **without** a default. Every value is `str()`-ed today so it cannot fire; with
   the outer clause now `RequestException`-only it would surface as a loud
   `TypeError` rather than as *"Failed to send to NRS WorkSpace: Object of type
   date is not JSON serializable"*, which points the user at the wrong system.

---

## 7 · Wall-clock, and the machine

**About two hours**, start to push, of which roughly twenty minutes was the
eight-tenant fan-out and the two full test runs.

**The machine behaved.** No Postgres crash-restart, no OOM kill, no discarded
run — against seven hours lost across two repositories in the day report 14
covers. Three classification agents ran in parallel and were held to static
analysis only, with every `--stop-after-init` run and every `odoo shell`
serialised in the main session, per the CLAUDE.md edit this handoff carries.
The host sat at 2.0 GB of 3.0 GB swap throughout. Whether that is the OOM
finding having reached the owner or simply a lighter day, I cannot tell from
here — but the discipline cost nothing and I would keep it either way.

---

## 8 · CLAUDE.md

All three edits landed:

1. **Check the denominator, not the exit code** — beside the in-registry test
   command, where somebody about to run it will read it.
2. **Serialise every `--stop-after-init` run**, in Parallel execution, next to
   the rule it widens.
3. **A claim that one code path is the only writer of a field is a hypothesis** —
   in the handoff protocol, where the Builder reads the instructions.
