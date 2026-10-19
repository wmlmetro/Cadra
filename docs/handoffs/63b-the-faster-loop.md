# Handoff 63b — The faster loop

**Branch:** `chore/the-faster-loop`
**Report:** `docs/handoffs/63b-REPORT.md` (keep it to ~150 lines)
**Runs after:** 63, merged. **Before 64.** Branch from `dev`, after
pulling.
**Time budget:** 3 hours. This handoff exists to make every later one
shorter.

**Step 0:** commit `CLAUDE.md`'s two new sections, *Speed* and *Progress*,
as their own docs commit. Follow both from here.

---

## 0 · Why

The owner is spending hours on each Cadra handoff. Most of that time isn't
building; it's waiting on tests that run on a tenant that grows every week,
and repeating runs that CI already does on a fresh database. Fix the loop
once.

## 1 · Gates-on in CI (30 min)

CI runs the pytest suite and the module suites on a fresh database, gates
**off**. Add the gates-**on** run **as a parallel job**, not a second step.
Use a matrix or a second job with the switch set after seeding. Then both
states are proved on every push, at the same time, without anyone's laptop.

- Keep each job inside its timeout. If the gates-on job doesn't fit 25
  minutes, raise that job's timeout and say how long it takes.
- Report both jobs' durations from a real run on this branch.

## 2 · A fresh `test19` on demand (60 min)

- **Measure first:** `test19`'s asset count, its largest class, its
  database size, and the full pytest time on it today (gates off).
- **Build `scripts/fresh_test_tenant.sh`.** It recreates a test tenant
  from a **template database**: a fresh install, the modules, the demo
  personas and the fixtures the suites expect, made once and refreshed by
  the same script with `--rebuild-template`. Restoring from a template
  (`createdb -T`) should take a minute or two. Measure it.
- **Refuse any tenant not in the local allow-list**, the way
  `walk_units.py` does. It must never touch `nrs19` (a replica of real
  data) or anything on the cluster.
- **Run the full pytest suite on the fresh tenant** and print the time next
  to §2's first measurement.
- **Leave `test19` as it is** unless the owner says otherwise. Create the
  fresh one as `test19f` and allow both. Say which the suites should use
  from now on, and why.

## 3 · Faster suites (45 min)

- **Try `pytest-xdist`** on the HTTP suite against one tenant: `-n 4`,
  then `-n 8`. Run each twice. If both runs are green, adopt the fastest
  stable setting in the documented command and in CI. If tests share
  state and fail under parallelism, list the first five that do and stop.
  Don't rewrite tests here.
- **The category policy save** (report 61: 28–30 s on 16,445 assets, at
  the suite's timeout). If 63 didn't already fix it, batch the propagation
  now: one grouped update of the derived fields, or untracked writes, with
  the history line kept per asset if the history needs it. The two
  timeouts in report 62 trace to this.

- **The configuration-change report's "today" is a UTC day** (report 63
  §For the Architect 3). Between 00:00 and 01:00 Lagos time, four tests
  fail depending on the hour they run, and a flaky suite costs reruns. Make
  it a **Lagos day**, like every other date the register publishes.
  CHANGELOG: behaviour change. The tests must pass at any hour; prove it
  by running them with the clock set to 00:30 Lagos.

## 3b · Two receipts at once get the same tag (a real bug, 30 min)

Vendra report 58: two chairs of one receipt, delivered by Vendra's two
INT-03 calls 100 ms apart, both got `NRS-FURN-018` (`test19`, assets
106911 and 106912). Report 63's unique index now makes the second create a
`409` on the cluster tenants, so a receipt can lose a unit to a race.

- **Make the location-built tag number safe under concurrency.** Use a
  row lock or a database sequence per prefix, whichever fits
  `asset_tag.py`'s generator with the least change. Never read
  max-then-insert.
- **Prove it with a test** that fires 20 concurrent creates at one
  location prefix and gets 20 distinct tags.
- **If a collision can still happen in any path**, answer it with a
  distinct error code (e.g. `tag_number_taken`) and say so in the
  endpoint reference. Vendra 59 will treat that code as retryable.
- Fix the two duplicate tags on `test19` the same way as report 63's other
  duplicates: listed, not silently renumbered.

## 4 · What must not change

- No test deleted, skipped or loosened.
- `nrs19` and every cluster tenant untouched.

## 5 · The report: one table

| | Before | After |
|---|---|---|
| Full pytest, gates off (local) | | |
| Full pytest, gates on (local) | | |
| CI, both jobs (wall clock) | | |
| Category policy save | | |
| Fresh test tenant, restore time | — | |

Then the documented command a Builder now runs at the end of a handoff,
and the time it takes.
