# Handoff 19 — Make CLAUDE.md readable again

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `docs/claude-md-diet`.

> **This handoff demonstrates its own main change.** I wrote this file into the working tree and made **no git commit, no push, no fetch and no ref update.** Committing it is your first step. From here that is how every handoff arrives.
>
> It is sequenced **before** handoff 18 (`18-the-callback-that-answers-twice.md`), which is already committed and unstarted. 18 loses nothing by waiting an hour and this is the owner's priority: they have read `CLAUDE.md` as saturated, and a Builder missing a priority instruction because it is buried behind 110 lines of ledger is a defect in every handoff rather than in one.

## Step 0 — commit the instructions you were given

```bash
git checkout dev && git pull --ff-only
git add docs/handoffs/19-make-claude-md-readable-again.md
git commit -m "docs: handoff 19 — make CLAUDE.md readable again"
git push origin dev
git checkout -b docs/claude-md-diet && git push -u origin docs/claude-md-diet
```

**Needs the owner:** nothing. No module upgrade and no fan-out — this handoff touches no Python. Run the source guards at the end; skip the suites unless you end up touching code, and say which you did.

---

## Why

**`CLAUDE.md` is 370 lines and 12,800 words**, loaded into every Builder session. The owner's read is that it has saturated — that priority instructions are being missed because they sit behind a 51-line status table whose cells run to full paragraphs and a 110-line decision ledger.

The cause is structural, not anybody's carelessness: **two different kinds of thing are in one file.** Instructions a Builder needs *at work*, and a record of how the project got here. The second grows without limit and crowds out the first.

**Nothing is deleted.** Everything moves somewhere it is read when relevant.

**The owner's requirement, in their words:** make it linear, remove what is no longer needed, and *"make sure we're not taking out things that will bite us back in the future."* Where you cannot tell which a passage is, keep it and list it in the report.

---

## A · The new git rule, and it is the priority item

**Replace the whole of `### How the Architect's commits reach this repo`** — all 34 lines — with this:

> ### How the next handoff's instructions get here
>
> The Architect writes `docs/handoffs/NN-<slug>.md` straight into the working tree and makes **no git commit, no push, no fetch and no ref update.** Its sandbox can write a file but cannot unlink one, so every aborted git write leaves a lock file that breaks the next command run here — which has twice cost the owner a debugging round and once left six orphaned files blocking a pull.
>
> **So Step 0 of every handoff begins by committing the instruction file you were given**, on `dev`, before you create your own branch:
>
> ```bash
> git checkout dev && git pull --ff-only
> git add docs/handoffs/NN-<slug>.md
> git commit -m "docs: handoff NN — <title>"
> git push origin dev
> git checkout -b <your-branch>
> ```
>
> **The owner runs no git commands at any point in the cycle.** Their whole involvement is merging the previous pull request and starting you. A handoff that asks them for a git command is a defect in the handoff.

**Keep the closing step**, minus the reasoning that no longer applies:

> - **Closing step, every handoff:** after the report is pushed and before notifying the Architect, `git checkout dev && git pull --rebase && git push origin dev`. Leave the working tree on `dev`, current, with nothing local waiting. Never force a rejected push — report it and stop.

**Keep as one line:** merge the previous handoff's PR before the Architect writes the next one, so the instruction file lands on a base that has stopped moving.

**Delete outright:** the `architect/next` branch mechanism and the `git reset --hard HEAD` troubleshooting note. Both exist only because the Architect was moving refs under a live working tree. It no longer does, so they are instructions for a condition that cannot occur — exactly the kind of line the owner is asking to remove.

## B · Move the ledger and the status narrative out

**`## Decisions` is 110 lines; `## Status` is 51 of paragraph-per-row.** Together they are 43% of the file and neither is working memory.

**`docs/DECISIONS.md`** — the ledger, moved **verbatim**, including its `[ruled]` / `[landed]` preamble, which is a rule rather than a note and must travel with it. In `CLAUDE.md` leave:

> ## Decisions
>
> Every product and technical decision, with its date, reasoning and the handoff that landed it: **`docs/DECISIONS.md`**. Read the entries for the area you are about to change before changing it. **Add to it in the same commit as the work** — `[ruled]` by the Architect, `[landed <hash>]` only by the report that confirms it shipped.

**`docs/STATUS.md`** — the status table, moved verbatim. In `CLAUDE.md` leave a table of **one line per item**: what it is, built or not, and the handoff that built it. No prose in the cells.

**The invariant, proven rather than asserted:** every decision line and every status row that was in `CLAUDE.md` appears in its new home byte-identical, and both counts match. **Report all four numbers.** A move that loses a line is worse than no move — the line is then gone from the only place anybody would look.

**`## Backlog — agreed, not yet scheduled` stays in `CLAUDE.md`**, and this is the one section I want kept despite its length. It is forward-looking rather than historical, and two of its items — the nine pre-envelope routes and the ~26 unvalidated query parameters, five of which silently return an unfiltered list — are live defects a Builder could walk into this week. **Delete the struck-through closed item**; a backlog that keeps its closed entries stops being a backlog.

## C · What stays inline, and this is the half to get right

Everything a Builder needs **before or during** its first command. Move none of it:

- **Working model, handoff protocol, authoring rules, Architect notification.**
- **Parallel execution rules** — every one was earned, and the serialisation rule is why the last three handoffs had zero Postgres crash-restarts against handoff 14's eight.
- **Stack & environment in full**, including the `_sql_constraints` gotcha, the multi-tenancy section and the stored-field migration rule. All three have caused a cross-tenant outage or come within one upgrade of it.
- **Architecture rules** — all six, verbatim. Shortest high-value thing in the file.
- **Git & attribution**, including the author identity. Standing owner instruction.
- **Owner preferences**, including the plain-English-first rule.

**Add a short index** near the top — five or six lines naming `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/ENVIRONMENT-FACTS.md`, `docs/DEPLOYMENT.md`, `docs/api/EXTERNAL-SURFACES.md` and `docs/integrations/INT-10-audit-access.md`, and what each answers. A Builder should find the archive in one read without carrying it.

## D · Judgement, and I am asking for it rather than specifying it

**Read the whole file and tell me what else should go.** You have run eighteen handoffs against it and know which lines you have actually used. Two things I suspect and cannot confirm from here:

- **Duplication between `CLAUDE.md`, `docs/ENVIRONMENT-FACTS.md` and `docs/DEPLOYMENT.md`.** Several environment facts now live in two places, and when two files say the same thing the one nobody edits is the one that lies. Where `ENVIRONMENT-FACTS.md` covers something, `CLAUDE.md` should point rather than repeat — **except** where the fact will bite before anybody would think to open another file, which is the judgement I am asking you to make.
- **Instructions for conditions that no longer exist.** The `architect/next` mechanism is one. The file still describes the stack as Odoo 15 with a 19 migration in flight in one place and as 19 in another, which report 01 already corrected once — check whether it has drifted back.

**Anything you are unsure about, keep and list in the report.**

---

## Acceptance

- `CLAUDE.md` is **under 180 lines**, and every section in §C is still in it.
- `docs/DECISIONS.md` and `docs/STATUS.md` hold every line that left, byte-identical, all four counts reported and matching.
- The new git rule is in, `architect/next` is out, and Step 0 of this handoff was the new rule working.
- The backlog keeps its open items and loses its closed one.
- No Python changed. Source guards green.

## Report

`docs/handoffs/19-REPORT.md`. Short.

1. **All four counts**, before and after.
2. **Line and word count**, before and after.
3. **§D — what else you cut, and what you kept because you were unsure.** The second list is the one I want.
4. Whether `CLAUDE.md` contradicted itself anywhere. It has at least once before, on the Odoo version.

---

## One thing for me, not you

**The owner is right that this loop used to be self-contained and that I broke it.** Getting handoff instructions into the repo was never their job. I started committing them from a sandbox that cannot push, and every workaround after that — plumbing commits, moving refs, a dedicated branch — was me solving a problem I had created, in their terminal, with their time.

§A is the fix and it is the simplest available: **I write a file, you commit it, they merge a PR.** That is the shape it had before and it needs no mechanism at all.

**Handoff 18 is next and unchanged** — the replayed callback, the v1 twin's two defects, and the credential baked into a published image. Nothing in it depends on this.
