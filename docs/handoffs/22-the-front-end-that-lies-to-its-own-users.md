# Handoff 22 — The front end that lies to its own users

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/phantom-enums`.

> Report 21 accepted in full. **Seven booleans, not five, and the two you separated out are the worse pair** — an unfiltered list is conspicuously large, while a plausible active-only roster handed to somebody asking for the archived one invites no second look at all. Report 05's inventory missed one entirely and mis-described two.
>
> **And you found the one published value that starts refusing something somebody sends: ours.** `?condition=damaged` has never existed on the model, so the register's *Faulty* chip has always answered empty and the *Damaged* tile has always shown `0` — reading as *there are no faulty assets*. Three broken things, none of which ever said a word. You fixed the front end in the same commit rather than reporting it and leaving it, which was the purpose of the instruction rather than its letter.
>
> **The near miss is the better lesson.** `priority` published four of the model's five values and our own suite creates a request with the fifth. Validating against the annotation would have refused a value the model has always accepted — and rule 4 decides it: **the model wins and the documentation is what gets corrected.**
>
> **And a partition assertion passed on an empty half.** Reverting `has_deadline` produced a *green* run, because nothing on that tenant carries a deadline, so zero plus everything still summed to everything. That is the collapsed denominator one layer up, and it is the thing in your report most worth remembering.

## Step 0 — commit the instructions, then verify the last handoff

```bash
git checkout dev && git pull --ff-only
git add docs/handoffs/22-the-front-end-that-lies-to-its-own-users.md
git commit -m "docs: handoff 22 — the front end that lies to its own users"
git push origin dev
git checkout -b fix/phantom-enums && git push -u origin fix/phantom-enums
```

**Needs the owner:** merge handoff 21's PR.

**And before anything else: run a fresh verification agent over handoff 21's diff.** Its own pass was terminated by a rate limit and the checks were done by hand, by the author. You named that as the one place the report is thinner than it should be, and you were right to — **a handoff verified by the person who wrote it is the weaker claim this protocol exists to avoid.** It is a read-only pass on an already-merged diff, it costs one agent, and whatever it finds goes at the top of your report. If it finds nothing, that is worth having too.

---

## A · Every request created from the front end is filed as High

**Your own open section, and this is the item that makes it a handoff.** The keys match and every label is shifted one step against the model, and the blank form defaults to `"2"` — so **every request a user creates without touching the dropdown is recorded as High priority.**

That is live, it is user-visible, and it corrupts the one field an FM team triages by. Nobody has reported it because the form says *Normal* while the database says High, which is the same shape as everything else in this pair of handoffs: two things that should agree, one of them read by a person and the other acted on by a system.

**Fix it, and fix it against the model's live Selection rather than against a corrected copy.** The server now publishes `allowed_values` on a refusal and `selection_values` reads the model at request time; a front end that holds its own hand-maintained list is a copy that will drift again. **Say in the report whether the SPA can read the set rather than declare it** — from the OpenAPI document, from a small endpoint, from the refusal itself. If it can, that is the durable answer for all five of these and not just for `priority`.

## B · The other four, and two of them raise

**`location_type`** — the form offers `state` and `office`; the model is `building, floor, wing, room, zone`. **Saving either raises.** And `wing` is never offered, so a wing loaded for edit shows a blank select and cannot be re-selected, which means a user cannot save the record they opened without changing it.

**`domain`** — the asset form takes the FM domain as **free text**, with a placeholder advertising a value that is not in the set and not even the right shape. The correct eight-value list already exists two files away and was never adopted.

**`asset_level`** is missing `group`, so a group-level asset **silently demotes** if somebody touches the dropdown. **`fuel_type`** collapses nine backend values into three on display, so `electric` and both plug-in hybrids all render as **CNG** — a fleet manager reading fuel type off this screen is being told something flatly untrue about the vehicle.

**Every one of these is the same defect and I want them fixed as one**, not five times: a front end that declares a set the back end owns. §A's question decides the shape; if the answer is that the SPA cannot read the set at request time, then **one module holds every enum, derived from the model, with a guard that fails when it drifts** — and the guard is the deliverable rather than the five corrections.

## C · The cursor — make it a 400

**Your last item in the family, and you left it for a ruling rather than deciding it. Ruling: refuse it.**

`decode_cursor` returning `{}` for anything it cannot decode means a caller paging with a corrupted cursor **silently restarts at page one while believing they are on page three** — and walks the same records again, or concludes a later page is empty.

You are right that it is *documented* behaviour and that turning it into a 400 is a breaking change. **Documented silent degradation is still silent degradation**, and the argument that cleared the other twenty-six applies without modification: an answer that looks like an answer is worse than a refusal. A client that sends a cursor it did not get from us has a bug, and telling it so is the only way it finds out.

`400 invalid_request`, naming the parameter, **announced as BREAKING in `docs/api/CHANGELOG.md`** rather than as a bugfix. An empty or absent cursor still means *start at the beginning* — that is a different input and keeps its answer.

## D · Two things from the addendum

**D1 · Accepted, including what you did not do.** The CI red was a postgres `initdb` race and not the branch: the wait broke on the first *yes*, then probed a second time with no retry, landing during the temporary server's shutdown. **A check that passes followed by the same check failing** — and your observation that *this repository has been here before* is exactly right, because the prod entrypoint's first draft refused every correct configuration for the mirror-image reason. Requiring readiness to **hold** is the right fix, writing the assignment out longhand rather than as `check && flag=1` is the right scar tissue, and executing the shipped block against a scripted stub is the right test.

**And leaving the three k8s init containers alone was the right trade.** They cannot produce that failure — each exits on the first success — and the worst they do is latch onto the temporary server, fail to connect, and restart into a working database. Self-healing, named, on a branch about query parameters. **Naming it is the deliverable.**

**D2 · The `limit` clamp stays silent, as you ruled.** The ceiling is per-credential so a caller cannot know it in advance, and clamping and refusing are different answers to different inputs. That is the distinction the rest of this work is built on and you applied it in the direction that required restraint.

---

## Acceptance

- A request created from the front end with an untouched dropdown is recorded at the priority the form displays. **Prove it from the database, not from the form state.**
- No front-end select offers a value the model does not have, and none omits one it does.
- A guard fails when a front-end enum drifts from the model, and is proven to fail before it passes.
- A corrupt cursor answers `400`; an absent one still starts at the beginning. Announced as breaking.
- **The fresh verification pass over handoff 21 is reported**, whatever it found.
- Denominators quoted, suites in CI's order, `npx tsc --noEmit` clean.

## Report

`docs/handoffs/22-REPORT.md`. Short.

1. **What the fresh pass over handoff 21 found**, at the top.
2. **Whether the front end can read the model's sets rather than declare them.** That answer decides whether this family is closed or merely corrected.
3. How many records already carry a wrong priority, measured. I expect it to be uncomfortable and I would rather have the number than not.
4. Wall-clock, the correction share, and whether the machine behaved.

---

## Two things for me, not you

**`docs/reference/cadra-vendra-interface.md` §5 trap 3 is now wrong and that is the good kind of wrong.** It says the trap exists *because Cadra does not validate server-side*. Cadra does now. Your §3 answer is the one I am writing in: **Cadra owns the defence, Vendra's local check stays as fast feedback in its own UI and stops being load-bearing**, and the refusal carries `allowed_values` so no client needs its own copy of the set to tell a user what to type. That paragraph is mine and it goes in this week.

**Three corrections in `docs/DECISIONS.md` are still mine and still owed** — the withdrawn R46 entry, the duplicate pairs staying as they are, and the INT-10 §16 citation. Four handoffs now. I will do them with the interface-document edit rather than promising them a fifth time.

## And what is left after this

**Two audit reports and one scope decision**, and then contracted core scope in this repository is finished. The access-change log and the configuration-change log are the last two of the five the specification names. The disposal-approval route needs me to decide whether `approvals:write` is the right gate — a decision I would rather make deliberately than inside a handoff about something else.
