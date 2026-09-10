# Report 20 — What a client actually gets

**Builder** · branch `fix/prod-profile-is-19` · base `dev` at `c6e1ef8`.

---

## 1 · Which runtime a client gets, which document says so, and how drift gets caught

**A client gets Odoo 19, and — this is the part I did not expect to be
writing — a client can now start it at all.** The fix is option 1 from the
handoff, plus a retirement it did not ask for, plus a defect the verification
pass found that made the whole question academic.

**The prod profile has never been able to reach its own database.** A compose
`command:` replaces CMD, not ENTRYPOINT, so the Odoo image's `/entrypoint.sh`
runs with `$1` = `bash`, falls through its `*) exec "$@"` branch, and its
`HOST`/`USER`/`PASSWORD` → `--db_user`/`--db_password` injection never
happens. `config/odoo.prod.conf` deliberately commits no database password,
on the strength of a comment saying the entrypoint supplies it. Measured, in
the container, with the template config:

```
psycopg2.OperationalError: connection to server at "db" (172.22.0.2),
port 5432 failed: fe_sendauth: no password supplied
```

**This repository already knew.** `k8s/dev/10-configmap-odoo-19.yaml` says in
as many words that *"the pods override the image entrypoint, so its
HOST/USER/PASSWORD injection does not run"*, and
`k8s/dev/41-odoo-19-deployment.yaml` appends both lines. The compose prod
profile did the identical conf-copy dance and appended only `admin_passwd`.

Nothing caught it because **nothing has ever started it.** CI runs
`docker compose config`, which parses YAML. I had verified the image
resolution and the credential refusal and had not started the thing. So:
I brought the prod profile up on a throwaway compose project with its own
volumes, and after the fix it connects — zero authentication errors in the
log — then tore it down. The remaining errors are `KeyError: 'ir.http'` from
an uninitialised database, which is what an un-bootstrapped database does.

**What I did, and why not just the prod overlay.** The obvious change is to
add `image:` and `dockerfile:` to `docker-compose.prod.yml`. I did the
opposite: I moved the pin into the **base** `docker-compose.yml`, which now
builds `cadra-odoo:19.0-dev` from `Dockerfile.odoo.19.dev`. The whole defect
was an overlay inheriting a runtime it never asked about. Pinning it in the
overlay fixes today's overlay; pinning it in the base means the next one
written inherits the right runtime by default. `docker-compose.19.yml` still
states its own image, harmlessly and now redundantly, and I left it there
because it is the file people read first.

**Then I deleted the Odoo 15 stack rather than repointing it.** Gone:
`docker-compose.dev.yml`, `config/odoo.dev.conf`, `Dockerfile.odoo.dev`,
`Dockerfile.odoo.k8s`. `CADRA_PROFILE=dev` now resolves to
`docker-compose.19.yml`; `dev19` is kept as an alias because it is what CI and
a year of habit type.

This is the part worth arguing. There were **two dev profiles, one per Odoo
major**, and that is not incidental to the bug — it is the cause. `prod` had a
15 half of the tree to inherit from because a 15 half existed. Repointing the
compose files would have left `FROM odoo:15.0` sitting in the repository for
the next `dockerfile:` line to find. A Dockerfile nothing currently references
is not harmless; it is what the next overlay points at.

**Which document says so.** `docs/DEPLOYMENT.md`, rewritten. It now opens by
naming the deployment shape it describes — one client, one server, one
database, one domain — and says which runtime that is, in the third paragraph,
with a pointer to the guard that holds it. It previously contained no
occurrence of the string "19" at all.

**How drift gets caught, twice, and neither can go quiet.**

| Guard | Reads | Cannot skip because |
|---|---|---|
| `tests/test_deployment_profile.py` (12 tests) | the compose YAML and the Dockerfiles, itself | it has no dependency to be missing — the host suite runs on `pytest` and `requests` |
| `prod-compose-lint` job in `.github/workflows/ci.yml` | the **real** `docker compose config` output | it runs in the one place docker genuinely exists |

The static one is deliberate, not a shortcut. A guard that shells out to the
docker CLI **skips** where the CLI is absent, and a skip is a guard that
passes — the exact green-that-executed-nothing failure `CLAUDE.md` is built
around. So the assertion never depends on docker, and the real resolver is
checked separately where it is guaranteed present.

The static reader states its own limitation instead of leaving it implied.
`test_the_merge_model_matches_what_docker_compose_resolves` asserts the
**precondition**: the compose files stay inside the YAML subset the reader
models (no anchors, merge keys, `!reset`, `!override`, `extends`). The day one
appears, that test fails and says the reader may now disagree with docker,
rather than the reader quietly being wrong.

Both were proven to fail before they passed. `test_the_deployment_runbook_names_the_runtime`
failed on the un-rewritten runbook (11 passed, 1 failed) and passes now.
`test_the_reader_catches_the_drift_it_was_written_for` feeds the reader the
literal defect — base on 15, one overlay on 19, prod overriding neither — as a
fixture, so the failure is demonstrated on every run rather than remembered.

Also fixed on the way, because deleting a file exposed it:
`test_no_long_running_server_names_its_database_on_the_command_line` walked a
hand-written list of compose files and `continue`d past any that were missing.
Deleting `docker-compose.dev.yml` would have left it reciting a dead filename,
asserting nothing, indistinguishable from a pass. A missing entry is now an
assertion failure naming the file.

---

## 2 · What the 15 overlay was doing that 19 does not support

The handoff guessed there was at least one thing, from the `--admin-passwd`
comment. There were three, and **not one of them would have stopped a 19
server from starting.** That is the finding, not the individual settings: a
prod profile that boots and then serves the wrong thing is harder to notice
than one that fails.

**1 · `longpolling_port` is ignored, not rejected.** Odoo 16 renamed it to
`gevent_port`. Measured on `odoo:19.0` rather than assumed:

```
$ printf '[options]\nlongpolling_port = 9999\n' > /tmp/t.conf
$ python3 -c "from odoo.tools import config; config._parse_config(['-c','/tmp/t.conf']); print(config.get('gevent_port'))"
8072
```

`config._parse_config` keeps the old spelling as an unrecognised string and
leaves `gevent_port` at its **default**. The file said `8072`, which is the
default, so it worked by coincidence. An operator who moved the websocket port
for any reason would have had Caddy's `/websocket` upstream pointing at a
closed port with nothing anywhere saying why.

**2 · The addons path pointed at the Odoo 15 vendor tree, and 11 module names
collide.** `config/odoo.prod.conf` listed
`/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/extra-addons/dist`
— that is `dist/`, the Odoo 15 tree, and **neither `crnd-19` nor `oca-19`**,
where the ported 19 foundation actually lives. Measured:

```
$ comm -12 <(ls crnd-19 | sort) <(ls dist | sort)
base_field_m2m_view  generic_condition  generic_location  generic_m2o
generic_mixin  generic_resource  generic_rule  generic_service
generic_tag  generic_team
$ comm -12 <(ls oca-19 | sort) <(ls dist | sort)
web_responsive
```

Odoo resolves a module to the first `addons_path` entry that holds it. So the
old line pointed a 19 server at the Odoo 15 copy of all eleven and at no copy
of the ported ones. The server starts. The registry it builds is the wrong one.

**3 · `--admin-passwd` has never existed, on any Odoo major.** The compose
comment blamed Odoo 15 for its absence; `config/odoo.prod.conf`'s own comment
claimed the opposite, that `admin_passwd` *was* supplied that way. `odoo server
--help` on 19.0 has no such option and 15 had none either. One file described a
mechanism that does not exist and the other blamed the wrong version for it not
existing. The conf-copy-and-append dance in the prod `command:` is what
actually supplies it; both comments now say so, and the dance stays because
there is still no flag.

The ported file also picks up three things the 19 config already had and prod
did not: `db_name` deliberately unset (so the cron worker is not pinned),
`publisher_warranty_url` closed (a client server's weekly phone-home would
disclose **the client's** company name, email and phone to a third party), and
`limit_time_real_cron` stated rather than inherited.

---

## 3 · What else in `docs/DEPLOYMENT.md` was no longer true

Nearly all of it. I had it fact-checked claim by claim against the real files
before rewriting. The document was 256 lines; it is now 500, and longer only
because it now covers things it was silent about.

**Wrong:**

- **"Two deployment profiles"** — there were three. `dev19`, the one CI
  actually uses, was undocumented.
- **"You should see `67 passed, 3 xfailed`"** — every number wrong, and the
  concept is gone: there are **zero** `xfail` markers in the suite. Both
  delegated-controller bugs they marked were fixed and their tests now assert
  success. The troubleshooting row pointing at "tests/README.md xfailed" was
  pointing at a section that no longer exists.
- **`git clone https://github.com/<your-org>/myservicenrs.git`** — the remote
  is `git@github.com:wmlmetro/Cadra.git`.
- **The bootstrap step list** was wrong at step 2 ("brings the stack up") — it
  starts **Postgres only**, and the full `up -d` does not happen until after
  the module install. It omitted that the script **sources `.env` into its own
  environment**, which is why every Day-2 command in the document that used
  `$POSTGRES_DB` expanded to nothing in an operator's shell. Line 169 was
  `DROP DATABASE ;`.
- **"Creates (or rotates) the smoke-test API client"** — it provisions
  **three** (`test_client`, `tag_issuing_unit`, `vendra`), each with its own
  `res.users`, and re-narrows the two scoped ones on every run.
- **`.env.runtime`** — promised by `.env.example` and by `bootstrap.py`'s own
  docstring. **Nothing has ever written that file.** Both corrected.
- **The `403 forbidden` troubleshooting row** — "re-run bootstrap, it re-syncs
  scopes" is still right for an **API client** and has been wrong for a
  **session** token since handoff 05, when login scopes started deriving from
  Odoo groups. Re-running bootstrap does nothing for that case. Both rows now.
- **The restore recipe could not work.** `psql -U $POSTGRES_USER` with no `-d`
  connects to the database named after the user — which *is* the one being
  dropped — so Postgres answers `cannot drop the currently open database`. It
  also took no pre-restore backup, verified nothing, left the proxy running so
  a hit on `/web/login` reopened a connection mid-drop, and **said nothing
  about the filestore**. I rewrote it and ran the new drop/create verbatim
  against the live PostgreSQL 13.23 container: `DROP DATABASE ... WITH (FORCE)`
  and the two `-c` flags both work.
- **`pg_dump` was missing `-T`**, so compose allocates a TTY and mangles the
  binary `-Fc` stream.
- **Two false cross-references, both now true.** `docs/ENVIRONMENT-FACTS.md`
  asserted the one-registry / schema-before-code rule "is in `docs/DEPLOYMENT.md`
  in full"; it was not in it at all. `docker-compose.prod.yml` pointed at a
  "build & ship workflow" section that did not exist. I wrote both sections.

**Silent about:** tenancy (the word "tenant" appeared once in 256 lines;
`dbfilter` never), that `odoo` is not a database you can use locally, the
in-registry Odoo suite, the denominator trap, the serialise-your-upgrades
rule, the Kubernetes estate, all 17 workflows, and the filestore.

**One correction to my own instructions.** The handoff said `docs/DEPLOYMENT.md`
is normally an Architect document and mine in this handoff. I have also
appended to `docs/STATUS.md` rather than editing its landed correction — its
third bullet said the prod profile is still 15 — using the append-don't-edit
discipline the handoff's own closing section describes.

---

## 4 · Wall-clock, correction share, and whether the machine behaved

**Wall-clock: about two hours**, from the instruction-file commit to the
report. Three parallel agents: one building §B (workflow module, own files),
one read-only fact-checking `docs/DEPLOYMENT.md`, one verifying the finished
diff. Everything touching the database or the stack ran serialised in the main
session.

**Correction share: low, and concentrated in two places.**

- **The credential-refusal shell block took three attempts.** The first was
  written straight into the YAML and looked right. It was not: `set -e` kills
  the script on `check … && flag=1` when the check *passes* (returns 1), so a
  correct configuration refused to start and an incorrect one printed nothing.
  I only caught it because I rendered the block through `docker compose config`
  and ran it as bash against five configurations rather than reading it. **The
  first version of a start-up guard that refuses on a client's server is not a
  thing to ship on a read-through.** It is now a flag-setting function called
  in statement position, proven across five cases.
- **Two false-positive rounds in the widened credential guard.** `${VAR:?message}`
  supplies *no* default — it is the fix — and my first reader read the refusal
  **message** as a baked password, flagging `docker-compose.prod.yml`. A guard
  that flags the correction is worse than no guard. Fixed, with the negative
  case as a fixture.
- **One factual claim I wrote and then had to retract before committing.** I
  wrote in `config/odoo.prod.conf` that a 19 server "rejects `longpolling_port`
  outright". I then tested it. It does not reject it; it ignores it. The comment
  now says what was measured and shows the measurement.

**The machine behaved.** No Postgres crash-restart, no OOM, no retry needed.
Every `--stop-after-init` ran one at a time. Five in-registry runs plus two
full pytest runs, all clean.

**Denominators, quoted:**

Final run, in CI's order, on `jaizbankplc`:

| Run | Result |
|---|---|
| `pytest tests/` | **483 passed, 28 skipped**, 0 failed |
| In-registry, CI's 11 modules | **0 failed, 0 error(s) of 378 tests** |

And the mutation runs that prove the new tests hold something:

| Mutation | Result |
|---|---|
| §B1 and §B2 both reverted | **5 failed, 1 error of 94 tests** |
| `_last_recorded_comment` domain reverted | **1 failed of 95 tests** |
| the fleet service-schedule guard reverted | **2 failed of 15 tests** |
| `docs/DEPLOYMENT.md` before the rewrite | 11 passed, **1 failed** |
| a dead waiver entry injected | **1 failed**, naming it |
| a `Dockerfile` waiver entry injected | **1 failed** on scope |
| an inline flow mapping injected into a compose file | **1 failed** |
| an `env_file:` injected into a compose file | **1 failed** |

`grep -c CRITICAL` = 0 and `grep -c "of 0 tests"` = 0 on every in-registry run.

The 28 skips are all named: 24 admin-scope, 2 Turnstile-not-configured, 1 no
SAP asset number on this tenant, 1 no active `workflow.config`. None comes from
a file this handoff touched. **`docs/ENVIRONMENT-FACTS.md` said "27 skips is a
healthy run" and I changed it** — a bare number is the wrong thing to check,
because the total moves with the tenant's client scopes and its data, not with
the code. It now carries the breakdown by category and says to check those.

---

## §B — the two contract rulings, and how they were proven

Built by a subagent owning only the `myservice_workflow` / `myservice_api`
files; reviewed and run here.

**B1 · A late `payment_ref` on a replay is recorded.** The disposition is
untouched — still `replay`, the outcome is not applied twice. Writing only
`workflow_payment_ref` produces none of the five forbidden effects, and this
was verified by reading rather than assumed: `stage_id` is not in the vals, so
`request.request.write` computes an **empty** `moved` set and therefore neither
stamps `date_moved` nor calls `_log_event('stage_changed')`; the field carries
no `tracking=True`, so `mail.thread` posts nothing; and no dispatch-log row is
written because the method does not touch the log and both controllers return
before `_reconcile_callback`. `_discarded_by_replay` became
`_record_replay_extras`, returning `(stored, discarded)`, so the two controllers
reach the identical outcome from one method rather than two copies.

**B2 · `queried` dedups on `(outcome, comment)`.** Compared against
`workflow.dispatch.log.workflow_comment` — the verbatim text — never the
chatter body. `approved` and `rejected` are deliberately excluded: a second
approval carrying a different note is still one approval, and treating the note
as a new decision would re-apply a stage.

**Both proven to fail before they pass**, by mutation rather than by assertion.
I reverted the two lines that implement them and re-ran:

```
0 failed, 0 error(s) of 94 tests          ← with the fixes
5 failed, 1 error(s) of 94 tests          ← with both reverted
```

The six that went red:

```
ERROR: TestCallbackReplayHttp.test_a_repeat_carrying_a_late_payment_ref_records_it
FAIL:  TestCallbackDisposition.test_a_replay_records_a_late_payment_ref_and_names_nothing_else
FAIL:  TestCallbackDisposition.test_the_disposition_table_with_the_comment_dimension
FAIL:  TestCallbackReplayHttp.test_a_second_query_carrying_a_new_question_is_applied
FAIL:  TestCallbackReplayHttp.test_a_stored_payment_ref_is_reported_at_info_not_warning
FAIL:  TestCallbackReplayHttp.test_neither_query_case_cries_wolf
```

**API surface.** `stored_fields` is additive on both routes, and sits **beside**
`_warnings` on v1 rather than inside it: every other `_warnings` block on this
API means "what you sent that did not take effect", and a field we accepted and
wrote is the opposite — anything alerting on that key would fire on every late
payment reference. `discarded_fields` keeps its exact meaning. The `queried`
change **is** a behaviour change for WorkSpace — a POST that answered
`replayed: true` yesterday can answer `replayed: false` today — and is in
`docs/api/CHANGELOG.md` marked as one, not as a bugfix. The handoff-18 entry
there is left standing with a superseded note rather than edited, because a
consumer reading the file in order needs the state it is reading forward from.

**B3 · `workspace_ref`** — no code change, as ruled. Recorded in
`docs/DECISIONS.md` and left on the owner's list.

---

## §C — the exception, written

**The four defaults stay.** The credential guard did not read compose files or
`.env*` at all, so "the guard is scoped so these do not fail it" was true by
omission. It reads both now, and the three (path, variable) pairs are waived
with a written reason each.

Four things keep the waiver from rotting:

1. **Keyed on (path, VARIABLE), not on a path.** A fifth default dropped into
   `.env.example` tomorrow does not inherit the exception.
2. **An entry that matches no finding fails the audit.** Proven: I injected a
   dead entry and the suite said so, naming it.
3. **The waiver may only ever cover those two files.** Proven: I injected a
   `Dockerfile.odoo.19.k8s` entry and the scope assertion bit. Scope is checked
   **first**, because a Dockerfile waiver also trips the "matched nothing"
   check and would otherwise be reported as the less serious of the two faults
   — the one somebody fixes by making it match.
4. **The waived values must be values the prod bring-up refuses.**
   `tests/test_deployment_profile.py` reads `.env.example` and asserts it, so
   the exception is wired to the assertion that makes it defensible rather than
   merely agreeing with it today.

**The prod bring-up refuses a default-valued credential.** `${VAR:?…}` already
refused a *missing* one and cannot see the other half. The `command:` now
checks `POSTGRES_PASSWORD`, `ODOO_MASTER_PASSWORD` and `CADRA_JWT_SECRET`
against the values this repository ships, **names every offender at once** so
an operator with two to fix learns both on the first attempt, and exits 1.
Refusing at start rather than warning is deliberate: a warning on a container
that comes up healthy is a line in a log nobody reads, and by then the
deployment is on the internet with a published master password.

Rendered through `docker compose config` and run as bash, five cases:

```
both are repo defaults      -> refused, both named,  exit 1
strong pg, default master   -> refused, master named, exit 1
weak jwt only               -> refused, jwt named,    exit 1
strong, empty jwt           -> starts,                exit 0
all strong                  -> starts,                exit 0
```

An empty `CADRA_JWT_SECRET` is allowed on purpose — bootstrap generates one and
stores it per database in `ir.config_parameter`, and that is the documented
flow. The shell's value list and the test's are asserted equal through a marker
comment, so neither can be widened alone.

**Scope note:** the refusal runs in the `odoo` container. The `db` container
still starts with whatever `POSTGRES_PASSWORD` says, so a refused stack has a
running Postgres and no Odoo. Nothing is served; I judged that sufficient and
am naming it rather than leaving it to be discovered.

---

## The verification pass, and what it changed

A fresh agent that wrote none of the code reviewed the whole diff against the
handoff's acceptance list. It found **fourteen** things. Nine were real and
are fixed; the rest were documentation errors I had introduced. The three that
matter most were all in code I had already convinced myself was correct.

**1 · The prod profile could not connect to Postgres.** §1 above. The single
most valuable finding in the pass, and the reason is worth stating: I had
verified everything about the prod profile that could be verified without
starting it, and the defect was in the half that only starting it reveals.
CI has the same blind spot, by construction — `docker compose config` parses
YAML. Fixed, and proved by an actual bring-up.

**2 · The credential-refusal shell was untestable, so it is a file now.**
`config/prod-entrypoint.sh`, invoked by the compose `command:`.
`tests/test_prod_entrypoint.py` runs the shipped file with a stubbed `odoo`
on `PATH` and a table of values — fifteen tests, including a password
containing a space, a quote, a `$` and a backslash, and one that asserts the
master password never reaches stdout. A test asserts the shell has not crept
back into the YAML. Both bugs this file has had in its short life were
invisible to a read-through and obvious to an execution.

**3 · A failed re-dispatch could turn a redelivered question into a new one.**
`_send_to_workflow` creates its outbound row as `pending` *before* calling the
adapter, and the write that resets `workflow_status` to `pending` lives inside
the success branch. So a re-dispatch whose adapter fails leaves a newer
dispatch-log row with an empty comment while the request still reads
`queried`, and `_last_recorded_comment` — which took the newest row whatever
its status — read that empty string. The next ordinary redelivery of the same
question compared against `''`, was judged new, and applied. **That is exactly
the "fires on the common case" failure the comment comparison exists to
avoid**, arriving from the other side, and a failed dispatch is not exotic.
The domain is now scoped to rows that recorded an *answer*. New test, proven:
`1 failed, 0 error(s) of 95 tests` without the fix.

**4 · My "five forbidden effects" analysis missed a third `write` override,
and I mischaracterised it in an earlier draft of this report.**
`myservice_fleet_maintenance.request_request.write` runs
`_update_vehicle_after_service()` on **every** write to a closed maintenance
ticket without looking at `vals` at all. I had called it "a wasted write, not
a false record". That is wrong: two of the three fields it writes are
idempotent, and the third is `manual_next_service_date = False`, which
**destroys an operator's manual next-service override** — a value somebody
deliberately set on the vehicle. Any unrelated write wiped it, and recording a
late `payment_ref` is now such a write.

Fixed at the source, scoped to the five fields the schedule is derived from,
with four tests in a module whose defect this always was. Proven: `2 failed`
without the guard, and the two tests covering the behaviour that must be
*kept* pass either way.

**5 · Both new guards had silent false-pass holes.** The compose parser in
`tests/test_deployment_profile.py` returned `{}` for a service key carrying a
trailing comment, at four-space indentation, quoted, or written as a flow
mapping — and `{}` in an *overlay* reads as "overrides nothing, inherits the
base", which is a pass on exactly the drift the file exists to catch. It now
tokenises rather than pattern-matches, has six spelling fixtures and two
must-not-flag fixtures, and the flow-mapping form fails loudly instead of
being misread.

The widened credential reader in `tests/test_source_guards.py` walked past a
YAML flow mapping, a quoted list item, a literal on a line that also carried
an unrelated `${...}`, and a `#` inside a value — **three of which are the
same spellings `docs/DECISIONS.md` records defeating the k8s reader one
handoff earlier.** A guard that only catches the keystrokes of the defect it
was written for is a record of that defect, not a rule, and mine was. Ten new
fixtures; the reader now flattens flow syntax and reads pairs off tokens.

**6 · `env_file:` was a hole neither reader could see.** A service loading its
environment from a file not named `.env*` bypasses both. Following the
reference is the wrong fix — the path can be a list, can be relative to
somewhere else, can point outside the repo — so the construct is refused
instead. No compose file here uses one.

**Documentation errors it caught, all mine, all fixed:** the runbook's day-2
commands passed `-c /etc/odoo/odoo.conf` on prod, where that path is the base
image's stub and the real config is `/tmp/odoo.conf`; the runbook quoted test
numbers (419/423) that contradicted the run recorded three documents away in
the same change; `docs/api/EXTERNAL-SURFACES.md` still described the replay
behaviour §B changed, on the route an external organisation actually calls;
`k8s/dev/MULTI-TENANT.md`'s validation recipe was repointed to the 19 image
with `dist/` still on its addons path — the identical defect
`config/odoo.prod.conf` was corrected for in this same change;
`docs/constraint-audit.md`'s premise ("Odoo 15 loads `dist/`") stopped being
true the moment the 15 stack was deleted; `seed_dev.sh` invoked compose with
the overlay alone, which resolves no image for `db` and mounts no repo; the
changelog called `outcome` optional when it is required; and
`scripts/bootstrap.sh` printed the *database-manager* password under the label
`Admin login`, which is both the wrong credential and, on prod, a real secret
echoed to stdout.

**What it checked and found correct**, because a verification pass that only
lists faults is not evidence: the waiver machinery (keyed on the finding's own
path, so a cross-file confusion is impossible), the refusal `case` patterns
(no glob metacharacters, so no strong password matches by accident), `$$` → `$`
rendering, `printf` safety for `%`, quotes, spaces, `$` and backslashes, the
absence of `admin_passwd` and `db_name` from the prod config, every
`addons_path` directory existing, all ten relative links in the runbook,
`DROP DATABASE … WITH (FORCE)` on PostgreSQL 13, the disposition being read
before the dispatch row is reconciled, and that `stored_fields` is additive on
both routes with no OpenAPI annotation needed.

## Deviations from the handoff

1. **I deleted the Odoo 15 stack**, which the handoff did not ask for. Reasons
   in §1. It is the larger half of the change by blast radius and the part most
   worth a second opinion.
2. **`CADRA_PROFILE=dev` changed meaning** — it was the Odoo 15 stack and is
   now the 19 one. `dev19` still works. Anyone with `CADRA_PROFILE=dev` in a
   shell profile gets a different stack than yesterday, and a better one.
3. **I edited files outside the handoff's stated scope** to keep the deletion
   honest: `README.md`, `seed_dev.sh`, `tests/conftest.py`,
   `scripts/load_employees_xlsx.py`, `config/nginx.dev.conf`,
   `k8s/dev/MULTI-TENANT.md`, `k8s/dev/ODOO-19-STACK.md`. All are reference
   fixes, none is behaviour.
4. **I corrected `scripts/bootstrap.py` and `.env.example`** on the
   `.env.runtime` file that neither has ever written. Not asked for; it is a
   docstring that lies about what the function does.

## Findings I did not fix

1. **`.gitlab-ci.yml` pins `SERIES_BRANCH: '15.0'`** and targets
   `gitlab.crnd.pro`. It is a CRND vendor artifact from March 2023, last touched
   by `[yodoo-cockpit] Initialize assembly`, and there is no GitLab remote — it
   cannot run. Inert rather than hazardous (nothing in this repo can point a
   compose overlay at it), so I left it, but it is the last 15-pinned file in
   the tree and deleting it is a decision rather than a fix.
2. **The `printf` that appends `admin_passwd` to the conf** will inject a
   second config option if `ODOO_MASTER_PASSWORD` contains a newline. It is
   operator-supplied and self-inflicted, and pre-existing; I left the working
   path alone rather than harden a line I could not test against a real
   deployment.

## Still on the owner's list, unchanged

- **The Odoo `admin` password is set by nothing in this repository, on any
  tenant.** Report 18's largest finding and still true. Taking the default out
  of the image stopped publishing it; it did not rotate it. `ODOO_MASTER_PASSWORD`
  is a *different* credential — the database-manager password — and the new
  refusal covers that one, not this one. `docs/DEPLOYMENT.md` now says so
  explicitly under "Credentials", but saying it is not doing it.
- **The `ODOO_ADMIN_PASSWORD` Secret**, and the two live-cutover credentials
  from report 17 §3.
- **Merging this PR.** The Builder's permission layer refuses `gh pr merge`.
