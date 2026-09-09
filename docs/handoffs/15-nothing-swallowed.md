# Handoff 15 — The handlers that swallow what they were written to catch

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/nothing-swallowed`.

> Report 14 accepted in full, and the deviation in §2 is the report. **My instruction that the transfer route is the only writer of `custodian_id` was wrong, and you found six.** Putting the recorder in `write`/`create` instead of in the route is the difference between a chain of custody and a chain with holes in it — and you gave the reason better than I would have: *a gap in an append-only record is indistinguishable from a period of no movement*, so an auditor who finds one cannot trust the complete parts either. That is the ninth time this protocol has caught me.
>
> The duplicate-an-asset finding is the one I would put in front of anyone arguing that a verification pass is overhead. Copying an asset fabricated permanent custody history, in the one model whose entire value is that its contents were not invented, and append-only meant **it could never have been removed**.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/nothing-swallowed && git push -u origin fix/nothing-swallowed
```

Handoff 14's PR (#59) is merged — `2b98fb3` on `dev`. **Needs the owner:** nothing.

**Read `docs/ENVIRONMENT-FACTS.md` before you start, and take its OOM entry seriously.** Report 14 lost four hours of seven to a thrashing host, and the owner has been told. Serialise every `--stop-after-init` run, not only the ones that write — see the CLAUDE.md edits below.

---

## A · The catch-all handlers

**Your closing question, and it is the right size for a handoff of its own.** From report 13:

> *The bare `except Exception: pass` is a repo-wide pattern and it has now concealed two published defects … Each one is a live path where a field rename, a missing module or a typo returns a plausible-looking empty answer instead of an error.*

Two things make this the worst of the family we have been working through. A capped count is at least a number, and somebody might notice it stop moving. **This returns "there are none", which is a complete, confident, wrong answer.** And it survives forever: the vendor list told every tenant *"No approved vendors yet"* for three years because a field had been renamed, and nothing anywhere said so.

**The work is not "remove them".** You already named why — some are load-bearing for tenants without the fleet or asset modules, and turning those into hard failures would break working installations. The work is to make every one of them answer the question *what is this hiding?*

**Three outcomes, and each `except` gets exactly one.**

1. **Legitimately optional — narrow it and say so.** A module that may not be installed is an `ImportError` or a missing model, not "any exception". Catch the specific thing, log at `DEBUG` or not at all, and put one sentence above it naming what is optional and why. A narrowed except that cannot hide a typo is the goal.
2. **Not optional — let it raise, or log at `WARNING` and return something that admits it.** `get_fleet_command`'s three are the test case here: if a dashboard panel cannot be built, an empty panel is a lie and an error is the truth. Where the route must still answer, return the envelope's own failure shape rather than an empty list.
3. **Genuinely unknown — log at `WARNING` with the exception, and leave it.** Still an improvement: the next person gets a line in a log instead of silence. This is the fallback, not the default, and the report should say how many landed here.

**A guard, and I expect this one to be harder than handoff 13's.** `except Exception: pass` and `except Exception: return []` are findable by shape; whether a given one is legitimate is not. So:

- **The guard is a pinned inventory, not a shape ban.** Every bare catch-all in first-party code is listed with a one-word classification, and a new one that is not in the list fails the guard. You argued in report 13 that *"a waiver somebody has to write out turns a silent wrong number into a sentence somebody chose to write"* — same instinct, applied where a clever guard cannot reach.
- **The inline-comment convention from handoff 13 carries over.** If it worked for capped counts it works here; do not invent a second mechanism.

**Report the count.** How many there were, how many landed in each of the three outcomes, and — the number I actually want — **how many were hiding something live.** Report 13 found two by accident. I would like to know what a deliberate look finds.

## B · Three rulings from report 14

**B1 · `scripts/nrs_hq_seed.py` refusing to wipe a tenant with custody history — keep the refusal, and build the door.**

You judged the refusal correct and documented it at the field. Agreed, and the reasoning is yours: a script that would destroy an append-only audit record should stop and say so. **But a refusal people route around is worse than a refusal with a documented exit**, and the route around this one is dropping the database — which destroys the chain *and* everything else, with nothing left to say it happened.

So: an explicit flag, off by default, that **prints how many custody links it is about to destroy and on which tenant** before it proceeds. Not a prompt — a flag, so it cannot happen by accident and cannot be answered by hitting return. The refusal stays the default and its message names the flag.

**B2 · The suite writing permanent links into a live-shaped tenant — acceptable, and they must be visible as what they are.**

Your framing is right and the alternative is worse: a test that does not exercise the recorder proves nothing. What I am not willing to accept is a reader of that chain being unable to tell. The reason string carries `test_custody._build_a_chain` today, which is a string somebody has to know to look for.

**Make it a first-class `source`.** `test`, alongside `direct`, `transfer` and `tracking_backfill`, returned by the API like the others. Then anyone reading `jaizbankplc`'s chain can see which links are artefacts without being told they exist — which is the same argument as `tracking_backfill`, and you already won it once.

**B3 · `include=custody` bypassing the record cap — and the instruction you wanted re-examined was right to question. Here is the ruling, and it goes the other way.**

You proved the asymmetry live: two rows back and nine reported on the route, nine rows back and no warning on the embed. One question, two answers, one of them silent about it.

**I am not capping the embed. I am exempting the chain from the cap on both paths.** A chain of custody is not a page of a register. It is one asset's complete record, it is bounded by reality rather than by data volume, and **a truncated chain cannot be told from a complete one** — which is the entire finding this model was built to close. Applying a cap to it reintroduces the defect in the one place we have just spent a handoff removing it.

So: `GET /assets/<id>/custody` is exempt from `total_record_cap`, the embed stays exempt, both return the whole chain, and the exemption is written down **at the exemption** with that reasoning. `total_estimate` stays true, as it must everywhere. Note it in `docs/api/CHANGELOG.md` — it is a widening, so it breaks nobody, but a client that was building around 100 rows should be able to find out.

---

## CLAUDE.md — three edits, in this handoff

**1 · Check the denominator, not the exit code.** Report 14's most transferable finding:

> - **An Odoo test run that loses its database reports `0 failed, 0 error(s) of 0 tests` and exits 0.** A green that executed nothing, and both subagents hit it — one nearly reported it as a pass. **Quote the `of N tests` in every result, and treat a collapsed denominator as a failed run.** Never accept an exit code as proof a suite ran.

**2 · Serialise every `--stop-after-init` run.** The existing rule serialises anything that writes. Report 14 showed that is too narrow:

> - **Serialise every `--stop-after-init` run, not only the ones that write.** On this host a second registry load is itself the contended resource — eight Postgres crash-restarts, four of them with two upgrades running against *different* databases. Different databases do not help; memory is the shared thing, not the registry lock.

**3 · The Architect's instructions about "the only writer" are a hypothesis.** Mine, and it has now cost two handoffs:

> - **When a handoff asserts that one code path is the only writer of a field, verify it before building on it.** Handoff 14 said the transfer route was the only writer of `custodian_id`; an exhaustive search found six, including `_WRITABLE_FIELDS`, the Transfers UI, an employee-departure routine and three seed scripts. Recording at the asserted single point would have produced an audit record with invisible holes. A claim of exclusivity is the Architect's guess unless a search backs it.

---

## Acceptance

- Every bare catch-all in first-party code is classified, and the classification is visible where the code is.
- The guard fails on a new unlisted catch-all, and is proven to fail before it passes.
- `get_fleet_command`'s three no longer return an empty panel for a reason nobody can see.
- The seed script refuses by default and proceeds under a flag that first prints what it will destroy, with the count and the tenant.
- A test-written custody link is identifiable as one from the API alone.
- The custody route and the embed return the same complete chain for a capped client, and `total_estimate` is true on both.
- Suite green, guards green, the eight-tenant fan-out if any column moves.

## Report

`docs/handoffs/15-REPORT.md`. Short.

1. **The three counts from §A**, and especially how many were hiding something live.
2. Whether the pinned inventory was the right mechanism or whether part of it is shape-detectable after all. You are better placed to judge that than I was when I wrote it.
3. Anything in `docs/ENVIRONMENT-FACTS.md` that is now wrong, or a new entry.
4. Wall-clock, and whether the machine behaved.

---

## One thing for me, not you

**The owner has the OOM finding**, with your numbers: 60 MB free, 21.1 of 22.5 GB of swap, seven hours lost across two repositories in one day, and the whole remaining sequence finishing in under five minutes once the machine was free. It is the cheapest available improvement to this programme and it is not a code change. Your measurement is what made it arguable rather than a complaint, which is the only reason it got anywhere.
