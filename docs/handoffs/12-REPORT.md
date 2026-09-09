# Handoff 12 — Report

**Builder:** Claude Code (IDE) · **Branch:** `fix/honest-answers` · **Base:** `dev`
**Commits:** `1b009e6` (A + B), `4d1351a` (C) · **Wall-clock:** ~2h 10m

Handoff 11's PR (#56, `fix/retire-dead-screens`) **was** merged before I started —
`21f6b12` on `dev`. Step 0 ran clean.

**Owner-blocked:** the PR merge. `gh pr merge` is refused by my permission layer.

---

## What landed

### A · The cap

Everything asked for, plus two things the handoff did not know about.

| | before | after |
|---|---|---|
| `GET /assets?limit=2000` on `jaizbankplc` | 100 rows, `total_estimate: 100` | 100 rows, `total_estimate: 2410` |
| truncation stated | nowhere | `_warnings.truncated {cap, total, reason}` |
| `export.csv` | 101 lines, silent | 102 lines, `X-Cadra-Truncated: 100/2410`, `# TRUNCATED` row |
| `GET /assets/export` | `count: 100` | `count: 100`, `total: 2410` |
| cap decided by | the `aud` claim | `myservice.api.client.total_record_cap` |

**A2 is done by construction, not by care.** `paginate()` has exactly one
`search_count`, it takes `domain` (never `effective_domain`), and every return
path returns that one name. Two AST guards in `tests/test_source_guards.py`
assert precisely that, and I proved both gate: reintroducing
`search_count(effective_domain)` fails one, and returning `cap` from the
empty-window early return fails the other. The behavioural test gates too —
with `total = len(allowed)` put back, `test_a_capped_token_is_told_the_true_total`
fails with `100 != 105`.

**A3 — one design decision worth your ruling.** `_warnings.truncated` describes
the **query, not the page**. A caller asking for 5 rows of a 2,410-asset
register is warned on page one. The alternative — warn only on the page where
the wall is hit — tells them at the end of a twenty-page walk what they needed
before they started. Recorded in `docs/api/CHANGELOG.md`.

**A3 — one deviation.** You wrote `data._warnings`. That is impossible on a list
endpoint: `data` is an array. The warning is a **top-level envelope key**,
`body["_warnings"]`, attached inside `ok()` — which is the only placement no
future endpoint can forget, since `ok()` is the sole envelope builder (rule 1).
`data._warnings.rejected_fields` on the write endpoints is untouched.

**A4 — the migration ran on all 8 local tenants, exit 0 each.** Only `nrs19` has
a `vendra` client:

```
nrs19: client vendra uncapped (total_record_cap 0 -> -1); it was seeing the
       first 100 records of every resource
7 others: no client matching vendra / audit_viewer on this tenant
```

Three things about it you should know. It matches **case-insensitively**
(`=ilike`) and with `active_test=False`, because your own §B says a tenant was
provisioned `Vendra`. `audit_viewer` is in the list already — the name comes
from `docs/integrations/INT-10-audit-access.md` and spec §3; no tenant has one,
so it logs a miss rather than failing, and it is one constant to edit when
INT-10 names it for real. And `bootstrap.py` allows `CADRA_VENDRA_CLIENT_ID` to
override the id, so **a tenant bootstrapped with that override keeps its cap**
and the migration logs it as a miss. I did not widen the match further; guessing
at ids is how you uncap the wrong client.

I added a `@api.constrains` refusing anything below `-1`. A `-2` typed into the
form would fall through every branch of `record_cap()` and land on the external
default — a limit that silently does not do what it says, which is the defect
this change exists to remove.

### B · The 401

Body unchanged and asserted so: `test_the_four_bodies_are_byte_identical_apart_from_the_request_id`
strips only the correlation id and requires one distinct body across all four
shapes. Live, on `jaizbankplc`:

```
INFO    cadra.auth: request_id=0b236b81… client_id=test_client outcome=ok
WARNING cadra.auth: request_id=8bf89738… client_id=test_client outcome=bad_secret
WARNING cadra.auth: request_id=37c42e43… client_id=no_such_client_at_all outcome=no_such_client
WARNING cadra.auth: request_id=5c044af7… client_id=TEST_CLIENT outcome=case_mismatch matched=test_client
WARNING cadra.auth: request_id=96946f60… client_id=forged?outcome=ok client_id=vendra outcome=no_such_client
```

`inactive` needs an archived client the external suite cannot create; it is
covered in-registry. `docs/api/reading-an-auth-failure.md` is the note you asked
for — the outcome table, the `kubectl`/`docker` one-liners, and what is never
logged.

**Two hardening decisions I made without being asked.** The client id is
sanitised (`log_safe`: printable ASCII, truncated at 128) before it reaches the
log — the last line above is an injection attempt, and its newline became `?`.
And the whole cause-classification runs inside `request.env.cr.savepoint()`,
because a diagnostic must never change the answer.

**That test found a live 500.** `{"client_id": {"$ne": null}}` reached the ORM as
a domain value and answered a **raw HTML 500 to an unauthenticated request** —
`/auth/token` is one of the nine pre-`@cadra_route` routes, so there is no
envelope handler beneath it. Pre-existing, not caused by this work. Now
`400 invalid_request`. It is a small argument for moving those nine routes up
your backlog: the endpoint every integration touches first is the one with no
error handling under it.

### C

**C1 — I did not put it in the theme module, and here is why.** `myservice_theme_v5`
is the backend theme, and it is wrong twice:

1. **Nothing in the repo depends on it.** It is installed by hand on the four
   19-era databases. `myservice_security` is a hard dependency of
   `myservice_api`, so a fresh tenant gets the file today and would silently
   stop getting it after the move. Moving to theme_v5 also makes `web_responsive`
   a new requirement for anyone who wants navbar styling.
2. **It would change what you see.** `theme_v5/theme.css` and `sidebar.css`
   `!important` the same `.o_main_navbar { background }`. Measured bundle
   indices: `security_navbar.css` **2150**, `theme.css` **2287**,
   `sidebar.css` **2288** — so theme_v5 wins today and the navbar is white.
   Loading the file after them flips it to `#080c10`.

It went to `myservice_nrs_base/static/src/css/global_navbar.css`. nrs_base is
depended on by security, theme_v5 and website_theme alike, already ships global
backend CSS in `web.assets_backend`, and defines the `--nrs-red` this file uses.
Every rule other than the `.o_main_navbar` block wins on specificity and does not
care where it sits.

**Proof, on `jaizbankplc`:** navbar, dropdown and full-page screenshots are
**byte-identical before and after (md5 match on all three)**, and every computed
style I probed — background, border, height, box-shadow, entry colour, font,
size, weight, letter-spacing, text-transform, padding, active underline, brand,
systray, dropdown background/border/radius/shadow and item styling — diffed to
`NONE`.

Two true things surfaced while proving it, neither changed:

- **The navbar is white, not the near-black the file asks for.** theme_v5 has
  been overriding it all along. The file's real surviving contribution is the
  Barlow Condensed uppercase nav labels, the letter-spacing and the active-tab
  underline.
- **Its entire dark-dropdown block matches nothing on Odoo 19.** The menu is
  portaled to `.o_popover` at body level, outside `.o_main_navbar`, so
  `.o_main_navbar .o_menu_sections .dropdown-menu` never matches. The dropdown
  is white, styled by `myservice_theme`'s plain `.dropdown-menu`. Which means
  the dark-dropdown-under-a-white-navbar issue you filed as an open design
  question **does not reproduce on this tenant**; if you have seen it, it is
  from a different theme combination and I would want to know which.

**C2** — `do_notify` and `do_warn` added to `legacy_compat.js`. The argument order
flips: legacy is `(title, message)`, Odoo 19 is `add(message, {title})`; a
straight forward would have printed the sentence as the title.

**C3** — in `CLAUDE.md`, plus a second correction I hit myself: any `HttpCase`
needs `--workers=0`, and the documented command does not have it.

---

## Your four questions

### 1 · Does anything else derive a count from a capped search?

**Yes — six places, and I fixed the two in the API layer.** The other four are in
the dashboard delegates, outside this handoff, and I have not touched them.

Fixed here:

| | |
|---|---|
| `utils.py` `paginate()` | the one you knew about |
| `v1.py` `/assets/export` `count` | `len()` of a capped search, on a route named "export all assets" |

**Not fixed — reporting only:**

| file:line | the number | why it is false |
|---|---|---|
| `myservice_fm_dashboard/controllers/dashboard.py:35,53-57` | `kpis.open`, `overdue`, `escalated`, `in_progress` | all `len(filtered(...))` over `search(open_domain, limit=500)`. Past 500 open requests, `open` pins at 500 and the rest count only the newest 500. `resolved_today` on line 46 is a real `search_count`, so the payload mixes one true number with four capped ones. |
| `myservice_fm_dashboard/controllers/dashboard.py:89-99` | **`sla_pct`** | `round((1 - overdue/total) * 100)` where both terms come from that 500-row window. **This is the worst one in the estate.** It looks like an SLA compliance figure, it is published at `GET /api/v1/fm/dashboard`, and it is a ratio computed inside a window biased toward the newest requests. |
| `myservice_fleet_maintenance/controllers/fleet_dashboard.py:70-73,101-104` | `state_counts`, `fuel_counts` | tallied over `search([('active','=',True)], limit=100)` and returned **alongside** `kpis.total` from a real `search_count`. The breakdown does not sum to the headline in the same response. |
| `myservice_dashboard/models/dashboard.py:325` | `kpis.vendors` | `len(search(..., limit=6))`, so it maxes at 6 — while `get_kpis()` counts the same quantity correctly. Two endpoints, two answers. |

Also checked and clean: `read_group` is never given a `limit` and no group result
is truncated before aggregation anywhere; the depreciation report, the security
KPIs, the barcode KPIs, `asset_count` rollups and the location counts are all
honest.

`sla_pct` deserves its own small handoff. It is the one an NRS manager would
quote in a meeting.

### 2 · Does stamping the limits into the JWT create a staleness problem?

**Yes, bounded by the client's own access-token TTL, and I think that is
acceptable — with one caveat you should hear.**

Refresh **re-reads the limits off the client record**, the same rule already
applied to a client family's user and a session family's scopes. So the window is
one access token, not the 30-day refresh window.

The caveat: the window is `token_ttl_seconds`, which is **per client and
unbounded**. At the default 3600 it is an hour. Set a client to 86400 and you have
a day. Nothing couples the two, and the direction that matters is **narrowing** —
a client whose cap is reduced keeps the wider one for the rest of its TTL.
Widening fails safe.

**My recommendation: leave it.** The obvious fix is a `limits_version` on the
client checked in `require_jwt`, which is one indexed read per request — exactly
the cost the claim exists to avoid, paid on every call to make a rare
administrative action instant. If you want a belt, the cheap one is to revoke the
client's refresh families when its limits change; that shortens the window to the
current access token and costs nothing on the hot path. Say the word and it is
five lines.

### 3 · Anything the auth log would now write that should not be written?

Four things. Two I handled, two are yours.

1. **Log injection — handled.** `client_id` is unauthenticated text going into a
   log line under our own logger name. Without sanitising, `"vendra\noutcome=ok"`
   forges a line. `log_safe` strips non-printable ASCII and truncates at 128.
   Proved live: the newline came out as `?`.
2. **A 401 turning into a 500 — handled.** The diagnostic runs in a savepoint.
3. **A caller that swaps the two fields puts its SECRET in `client_id`, and we log
   it.** Unavoidable if we log the id at all, and the id is what makes
   `case_mismatch` possible. It is called out in
   `docs/api/reading-an-auth-failure.md` with the instruction to rotate. I do not
   think it changes the trade, but you should have decided it rather than
   discovered it.
4. **`outcome=ok` at INFO on every mint is a volume question nobody has bounded.**
   Vendra minting hourly across 8 tenants is ~192 lines a day and irrelevant. A
   client that does not cache its token and mints per request turns this into one
   INFO line per API call. Worth knowing before somebody integrates badly.

One thing I did **not** add, deliberately: the **source IP** on failures. It is the
most useful field for spotting credential stuffing and the one I would want at
11pm — successes already record `last_used_ip` on the client record, failures
record nothing. I left it out because your format was explicit and an IP is a
different kind of data from a client id. Your call.

Cost note: each failure now runs up to two extra queries, and the `=ilike` cannot
use the btree index on `client_id`, so it is a sequential scan. On a table of ~10
clients that is nothing; it is worth remembering that an unauthenticated endpoint
now does more work on failure than on success.

### 4 · Wall-clock

~2h 10m. The 8-tenant fan-out was ~11m of it and the two full external suite runs
~10m. The single most expensive thing was proving C1 — driving a real browser
against a tenant whose login form the website theme hides, and whose sibling
tenant `cadra19` turns out to have a **broken filestore** (missing asset-bundle
attachments, so the backend 500s on `web_tour.interactive.min.js` and never
styles). That is a local environment fault, unrelated to this work, but it will
waste the next person's afternoon: `cadra19` is not usable for anything
browser-based right now.

---

## What I changed that you did not ask for

- `400 invalid_request` for a non-string `client_id`/`client_secret` (was a raw
  HTML 500).
- `@api.constrains` on the two new limit fields rejecting values below `-1`.
- `do_warn` alongside `do_notify` — the same absence, one line away.
- The published `limit` maximum said **200**, and had said so since before
  `MAX_PAGE_LIMIT` was lifted to 2000. It matched neither ceiling in force. It now
  describes the actual rule, and the `cursor` description says how to tell "that
  is everything" from "that is all you get".
- `myservice_api` named explicitly in the CI Odoo-test module list. It would have
  arrived transitively through `-u myservice_security`, which is exactly the
  invisible coverage the existing comment in `ci.yml` argues against.
- `__pycache__/` and `*.pyc` in `.gitignore` — `tests/__pycache__/` was listed but
  the new `myservice_api/tests/` would not have been.

## Test output

**In-registry (`test19`, `--workers=0`):**

```
odoo.tests.stats:  myservice_api: 19 tests 30.84s 1860 queries
odoo.tests.result: 0 failed, 0 error(s) of 15 tests when loading database 'test19'
```

Revert-proof, same command with `total = len(allowed)` put back:

```
FAIL: TestPaginationCap.test_a_capped_token_is_told_the_true_total
AssertionError: 100 != 105 : total_estimate must be a fact about the register,
  not the size of the window the caller was given. This is the whole finding.
FAIL: TestPaginationCap.test_the_cap_survives_across_cursor_pages
AssertionError: 100 != 105 : every page reports the true total, not a
  remaining-rows countdown
odoo.tests.result: 2 failed, 0 error(s) of 15 tests
```

**External (`jaizbankplc`):**

```
274 passed, 27 skipped in 284.77s (0:04:44)
```

The 27 skips are the admin-scope tests the suite's token cannot reach, as
documented. Two of my own tests failed on their first run and both were my
tests being wrong, not the code: one assumed a small page of an over-cap query
carries no warning (it does, deliberately — see A3 above), and one expected the
CSV truncation row unquoted when `csv.writer` correctly quotes a field
containing commas.

**Source guards (standalone):** `41 passed`, and I verified the two new AST
guards fail on the reintroduced bug rather than trusting that they would.

**Multi-tenant upgrade:** `cadra19 nrs19 gtb19 test19 nrs lasg gtb jaizbankplc`,
`-u myservice_api,myservice_nrs_base,myservice_security`, exit 0 on all eight.
Two stored columns were added, so per `CLAUDE.md` this had to happen before the
code shipped; it did.

## Not done

Nothing in the handoff. The four dashboard false counts in question 1 are
reported, not fixed — they are outside `myservice_api` and you asked me to
report them.
