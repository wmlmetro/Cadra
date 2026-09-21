# Handoff 31 — One answer per rule

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/one-answer-per-rule`.

> Report 30 is accepted in full, and §1 is the best piece of design work either repository has produced. You were asked whether four tables should be one, you answered *two and one*, you built only the part that was already ruled, and you left the question you were asked to ask. That is exactly right.
>
> **The evidence that settled it is the evidence you found by accident.** Custody was written with a `source` any caller could claim; movement was copied from it twelve days later *without* the hole; the copy was fixed and the original was not. **Nobody decided that. It is what two copies of a safety rule do**, and it is a better argument for the mixin than anything I could have reasoned.
>
> Two more worth keeping. **§D2 as I specified it would have relocated the Lagos-midnight bug to the server** where handoff 29's fix could not reach it — every API credential's user has no timezone, so `context_today` falls back to UTC. My sentence *"kills the bug at its source"* was wrong, and you checked it. And **the depreciation method could never be changed from its own settings screen** — the API publishes `method` and accepts `depreciation_method`, so the screen sent the one field the API refused, got a 200, and said *"policy saved"*. Nobody knew until the warnings became visible. That single bug is the whole argument for §B.
>
> *"Is that sentence true?"* is now the most productive question in this programme, and it has been asked of my sentences as often as yours.

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/one-answer-per-rule && git push -u origin feat/one-answer-per-rule
```

Commit the instruction file first. **Do not start until PR #81 has merged**, and say so if it has not.

---

## A · Q1 — yes. The mixin, not the rows.

**Custody and movement adopt `nrs.asset.append.only.mixin`.** No migration, no id changes, no published name changes, about ten lines each — and it would have made §D3 structurally impossible rather than a thing somebody had to notice twelve days late. One answer per rule is the whole point.

**And I accept your recommendation against bringing their rows into the event table**, on the ground you raised that I could not have: `nrs.asset.custody` and its ids are named in nineteen documents including the contract an external auditor reads, and merging two sequences changes every id on every tenant. **Tidying our schema is not worth a breaking change to the audit contract.** Recorded as decided, with your reasoning, so nobody reopens it in six months on aesthetics.

While you are in there: the two `myservice_api` overrides that are supposed to be the same derivation and are not the same code. One of them, on the mixin.

## B · Q2 — 400, announced. Your argument, not mine.

I expected to rule for caution and you changed my mind by reading the consumer. **Vendra already treats a rejected field as terminal and dead-letters it — after Cadra has created the asset, incomplete, with an idempotency key that pins the same 201 on every retry.** So the lenient answer costs our only integrator a manual repair and buys nobody anything. Rule 3 of `CLAUDE.md` has called it a defect since before either of us wrote a line, and three route families already answer 400.

**Ship it, with the announcement, in one release:**

- The shape you proposed — `400 invalid_request`, `details.rejected_fields`, `details.writable` — so a caller can repair itself from the response.
- **The `PATCH` whose every field is refused, and which today answers 200 having written nothing, goes with it.** It is the same defect with the volume turned up.
- **Announced properly**: the changelog, the endpoint reference, and `INT-10-audit-access.md`, with the date and the old behaviour described. **No long deprecation window** — the lenient behaviour is actively harmful to the one system consuming it, and that system already treats the strict answer as correct.

**The forward-compatibility argument is noted and overruled**, for the reason you gave: a consumer sending a field we do not accept is wrong about our schema, and the sooner it is told the cheaper the repair.

## C · Four small ones, all ruled

**C1 · Q4 — yes, the model stamps it.** A disposal that arrives through any door gets its date and its condition, the way `/condemn` does. `/condemn` being the proper door does not close the others, which is the sentence this programme keeps having to write. Say in the report what it does to the disposal report's `no_disposal_date` finding — I expect it becomes a finding about legacy rows only, which is an improvement and should be stated rather than discovered.

**C2 · Q3 — verification of a disposed asset stays allowed, and your reasoning is the ruling.** *A disposed asset somebody physically finds on the premises is an audit finding, and a register that refuses to record "I saw it, today" is suppressing the one fact that matters.* Put that in `DECISIONS.md` in those words, so the next person to meet it does not tidy it away.

**But the app offers Verify on a disposed asset and the Odoo form hides it.** Two surfaces, one rule, two answers — the defect this handoff is named for. Make them agree, and the agreed answer is *allowed*.

**C3 · Q6 — yes, `POST /assets/<id>/mark-found`.** *Where it turned up* is exactly as much an audit fact as *why it went missing*, and an asset that reappears through a bare PATCH records nothing about the most interesting event in its life.

**C4 · Q7 — yes.** A disposed asset is not outstanding and should not be on a leaver's clearance list. Widen into `myservice_identity` far enough to stop the flag, and no further.

## D · Q5 — `transferred`: ask, do not guess

Published, filterable, selectable, and nothing in the system writes it. **Do not remove it on our judgement and do not invent a producer.** Whether an asset can be *transferred* — to another agency, another entity, out of NRS's register entirely — is a fact about NRS's process that neither of us knows.

**Write the question, one paragraph, for me to put to them**, alongside what the register does today if somebody sets it by hand. **If the answer is that it means nothing, it is removed in §B's announcement** — we are already making one breaking change to these routes and a second announcement for the same release costs nothing.

---

## Report

`docs/handoffs/31-REPORT.md`. Short — this is a small handoff and should read like one.

1. What adopting the mixin changed about custody and movement, and whether anything surprised you.
2. What §B's 400 broke that you did not expect — ours or anyone's.
3. What `no_disposal_date` now means.
4. Wall-clock, and the correction share.

---

## Not yours

**GitHub billing is now in its third report.** I have escalated it again. Nothing you do about it; keep quoting the `Ran … / OK` lines.

**PR #80** — the owner's own fix, merged from the screen four minutes before your Step 0. You read it before building on it. That is the right instinct and I would rather you kept doing it than waited to be told.
