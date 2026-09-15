# Handoff 25 — Where the tests are allowed to write

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/tests-know-where-they-are`.

> Report 24 stands in full. Two things in it are better than the feature. The first is §1's correction of my own list: I named group implication as a writer, and you went and read Odoo 19 rather than taking it — `all_implied_ids` is unstored on 19, so an implication grants rights while writing **zero** membership rows, which is a different fact entirely and one the record now carries as its own event. The second is the diffing design: eight security XML files re-apply membership on every upgrade, two full fan-outs ran them, and **zero fabricated rows were written** — where the obvious implementation, parsing `vals`, would have put a few dozen permanent `__system__` grants into an append-only model on the day it shipped. And you wrote "exhaustive" over a set you had stopped searching, a review found two more, and you put that in the docstring instead of in a footnote. That is the standard.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b fix/tests-know-where-they-are && git push -u origin fix/tests-know-where-they-are
```

If handoff 24's PR has not merged, branch from `feat/access-record`, say so, and do not merge it yourself.

---

## Why this handoff exists

I asked §3 as a housekeeping question about one leftover asset. The answer was that **88% of the assets in a client-derived register are test fixtures, 84% of the entries in a public-facing dropdown are test fixtures, and six fabricated approved disposals sit in an auditor-facing report** — accumulated over 154 sessions by a suite whose only control reads one environment variable and writes wherever it points.

Nothing reached production and no real asset is corrupted. That is the whole of the good news, and it is luck rather than design: the same suite, with `CADRA_API_BASE` set one word differently, does all of this to a live tenant, and the first anyone would know is an auditor asking about `pytest-1756203841`.

**The guard is this handoff. The cleanup is second, and the ruling you asked for is below.**

---

## A · A test knows which database it is in, or it does not run

**The ruling you asked for: safety is a property of the database, recorded in the database. Nothing else counts.**

Not the name — `test19` reads safe and `cadra19` does not, and both are wrong the day somebody restores a client dump into one. Not the environment variable, which is the thing that failed. Not a path, a hostname or a branch. A system parameter in the target database, set deliberately by a person, fail-closed when absent:

```
cadra.database_class = test | client | production
```

**Absent means refuse.** Every developer marks their local tenant once, with a command the error message spells out in full. There is **no bypass flag and no override variable** — a flag added for one legitimate afternoon becomes the way everyone runs the suite by the end of the month, and then this handoff never happened.

**Both paths, not just the HTTP one.** The env-var suite is the one I asked about, but report 24 §6 ran the eleven-module in-registry suite against `jaizbankplc` as well, and that writes too. Both converge on the same question — *which database am I about to write to* — so they should converge on the same check, asked once, before the first write of the session.

**A refusal is loud and names the remedy.** Not a skip: this repository's own rule, from report 23 §3, is that a skip is a guard that passes. Fail, name the database, name its class, and print the exact command that marks a database as a test database.

**CI must keep working, and the way it keeps working is by being stamped, not by being exempted.** CI builds a throwaway database with no `CADRA_API_BASE`; the harness that creates it marks it `test` as part of creating it. If you find a path where that is not possible, say so before you write the exemption — an exemption is how the guard acquires its first hole.

**Then give the suite somewhere legitimate to go.** The reason it targets a client-derived register is that `jaizbankplc` is the only tenant carrying a full credential pair. Provision a marked test tenant properly, so that after this handoff the default target is a test database and `jaizbankplc` refuses.

**And close the labelling gap at its cause.** The six disposals are unidentifiable because `Handoff23 Approver` was minted by hand with `is_test_credential` off. Fixtures should not be able to mint a credential that lies about itself: one fixture path, which sets the flag, plus a guard that fails if the suite ever authenticates as a client without it. The custody chain is honest for exactly this reason — 330 rows self-label — so the mechanism is proven and the hole is that it can be walked around.

**Acceptance.** The suite, pointed at an unmarked database, refuses before writing anything, with a message a person can act on. Pointed at one marked `client` or `production`, the same. Pointed at a marked test database, it runs. CI is green without an exemption. A test that mints a credential without the flag fails.

## B · The residue

Produce the removal script. **Dry run by default**, printing exactly what it would remove and what it would leave; removing only records that self-identify — the `pytest-*` names, `source = 'test'`, the credential flag — and **stopping rather than cascading** the moment it reaches something that does not. Where removal is impossible, say so in the output rather than working around it: append-only is append-only, and report 24 already made the right call once by marking asset 8396 instead of fabricating a reversal.

I am not asking you to run it against `jaizbankplc`. That is the owner's, exactly as `mark_test_fixtures.py` is. **Tell me what it would do** — the counts, and anything it would refuse to touch.

Check whether `mark_test_fixtures.py` has been run by the time you get here; if it has, verify it took, because an owner-run script nobody verifies is another instrument reporting on itself.

## C · Three small things that have been open too long

**C1 · The FM `domain` rendered as "System Domain"** (report 22 §7). **My ruling: the field gets its own label.** `adapters.ts` is showing a real value under a name that means something else, and the honest fix is to stop calling it that. Do not add a label lookup — report 22 was right that this makes a wrong field read convincingly. If `systemDomain` has no backing field, it should not have a row.

**C2 · `v1_settings.py:134` publishes `allowed` where everything else publishes `allowed_values`** (report 22 §7). **Publish both, deprecate `allowed`.** A client keying on `allowed_values` gets nothing today; one keying on `allowed` breaks if we simply rename it. Two keys, the same list, a note in the API changelog and a date.

**C3 · `workflow_payment_ref` is stored and serialised by nothing** (report 24 §8). Measure first: does anything write it? If nothing writes it and nothing reads it, it is a dead column and it goes. If something writes it, it is a financial fact invisible to every role including the auditor, and it belongs in the serializer under `financial`. **Report which, then do that** — do not ask me, the measurement decides it.

## D · One thing in report 24 to reconcile

§8 lists *"the CI-series guard ruling from report 22"* as still open. Report 23 §3 appears to have settled it in practice — the `odoo`-on-the-line requirement gone, replaced by an allow-list of the two non-Odoo version shapes, with three real offenders now found where the old logic found none. Check whether anything is genuinely still open there. If it is closed, close it in the ledger and say what closed it.

---

## Report

`docs/handoffs/25-REPORT.md`. Short. In it:

1. **What the guard refuses and what it lets through**, proved by pointing the suite at each class of database.
2. Whether CI needed an exemption, and if so, why one was unavoidable.
3. What the removal script would do to `jaizbankplc`, and what it would refuse to touch.
4. C3's measurement, and what it decided.
5. Wall-clock, and the correction share.
