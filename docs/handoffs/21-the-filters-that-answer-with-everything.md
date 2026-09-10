# Handoff 21 — The filters that answer with everything

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `fix/query-params-validate`.

> Report 20 accepted in full, including all four deviations and both findings you left unfixed. **It found something I did not ask about and could not have: the prod profile has never been able to reach its own database.** A compose `command:` replaces CMD and not ENTRYPOINT, so the image's password injection never ran — and `k8s/dev/10-configmap-odoo-19.yaml` says exactly that, in as many words, about the pods. **The repository already knew and the compose profile did not.**
>
> So the answer to *"what does a client deployed by the documented route get"* was not *Odoo 15*. It was *nothing at all*. Nothing caught it because nothing had ever started it, and CI cannot: `docker compose config` parses YAML. You started it.
>
> **Three more things in that report are the standard.** Pinning the image in the **base** rather than the overlay, so the next overlay inherits the right runtime instead of the wrong one. Deleting the 15 stack rather than repointing it, because *a Dockerfile nothing currently references is what the next overlay points at* — accepted, and it is the larger half of the change by blast radius, which you said yourself. And the three things the 15 overlay did that 19 does not support, **none of which would have stopped a server from starting**: a port setting silently ignored since Odoo 16 that worked only because its value equalled the default, and an addons path aimed at the Odoo 15 vendor tree where **eleven module names collide**, so a 19 server starts and builds the wrong registry.
>
> And the sentence I will be quoting back for a long time: *a guard that only catches the keystrokes of the defect it was written for is a record of that defect, not a rule, and mine was.*

## Step 0 — commit the instructions you were given

```bash
git checkout dev && git pull --ff-only
git add docs/handoffs/21-the-filters-that-answer-with-everything.md
git commit -m "docs: handoff 21 — the filters that answer with everything"
git push origin dev
git checkout -b fix/query-params-validate && git push -u origin fix/query-params-validate
```

**Needs the owner:** merge handoff 20's PR, and the credential items below, which are unchanged and still theirs.

---

## A · Five boolean parameters that return the whole list

**The backlog item, and it goes first of the twenty-six because of what the five do.** From report 05's scoping: **5 boolean parameters silently drop the filter and return the UNFILTERED list.**

**An empty list reads as "no matches". A full list reads as an answer.** That is the asymmetry that makes these worse than the thirteen enum parameters that answer `200 []` and the eight integer ones that swallow their error — and it is why they are not going to the back of a queue behind contracted scope.

**And they now undermine the thing we just built.** Handoff 20's auditor role, the snapshot and the disposal report exist so an auditor can *satisfy themselves* rather than ask us. An auditor who filters a list, receives everything, and reads it as the filtered answer has been given a false statement by a government system — and neither they nor we would find out. That is the same sentence I wrote about `total_estimate` in handoff 12, one mechanism along.

**Fix the five first and say so in the report before anything else.** Then the thirteen and the eight.

**What "fix" means, and the shape is settled by this repo's own rulings:**

- **An unparseable value is refused, not dropped.** `400`, naming the parameter and the accepted values — the same answer `is_tagged` already gives, which is the precedent and is in the code today.
- **`is_tagged`'s behaviour is the target for all five.** Anything other than `true`/`false` is a `400`. It is already right; the other five are the ones that drift from it.
- **There is no primitive to reuse and the backlog says why.** `utils._selection_allowed_values` rolls the cursor back on error and a landed ruling forbids it on a read path. **Write one**, at the door, that does no database work — the door rule from the sibling repo's handoff 10, and the reason it exists is exactly this.
- **A guard**, and you already know its shape better than I do. Every declared query parameter either reaches a validator or is named in a waiver with a reason. The AST can see the route decorator and the parameter list; whether it can see the parse is your call, and if the honest answer is a pinned inventory then pin it — you have now built that twice and been right both times.

**The thirteen enums answering `200 []` are the subtler half and I want your reading.** An empty list for a value the caller mistyped is indistinguishable from an empty list for a value that genuinely matched nothing — which is the `tag_label_state` trap the Vendra client validates client-side precisely because Cadra does not. **Fixing it server-side means Vendra's local validation stops being load-bearing**, and that is worth saying in `docs/reference/cadra-vendra-interface.md` rather than leaving two systems both defending against the same thing. Say in the report whether any published enum would start refusing a value some caller is sending today; that is the only part of this that could break somebody.

## B · Two things you left, and I am ruling on both

**B1 · Delete `.gitlab-ci.yml`.** You left it as inert — a CRND vendor artifact pinned to `SERIES_BRANCH: '15.0'`, targeting a GitLab that is not a remote, last touched by an assembly bot in March 2023. **It is the last 15-pinned file in the tree, and the whole argument of your own handoff is that an inert 15 reference is what the next thing finds.** You made that case for `Dockerfile.odoo.dev` and then declined to make it one file further. Delete it.

**B2 · The refusal rejects a credential containing a newline.** You left the `printf` newline injection because it is operator-supplied, self-inflicted and pre-existing, and that is a fair judgement about a line you could not test against a real deployment. But `config/prod-entrypoint.sh` now exists, has fifteen tests, and is **already the place that refuses a bad credential** — so the narrow version is free: a credential carrying a newline is refused there, named, before anything is appended to a config file. Not hardening the `printf`; refusing the input that makes it dangerous.

## C · Two corrections that are mine and one that is yours

**C1 · `docs/DECISIONS.md` needs three corrections and I am writing them.** The withdrawn R46 entry, the duplicate pairs staying as they are, and the INT-10 §16 citation. Still owed; report 19 was right not to make them and report 20 was right to append to `docs/STATUS.md` rather than edit its landed correction.

**C2 · `docs/reference/cadra-vendra-interface.md` gains a note** once §A lands: trap 3 in its §5 exists because Cadra does not validate server-side, and if it starts to, the document should say which side is defending. That is mine, and it is a one-paragraph edit after your report tells me what changed.

**C3 · Your own report's §3 list is a better argument for a convention than anything I would write.** `docs/DEPLOYMENT.md` was wrong in nearly every claim it made, and the reason is that nobody had read it end to end since it was written. **Put one line in `CLAUDE.md`**: a document that describes how to operate this system is fact-checked against the files it describes whenever a handoff touches the area it covers, and a claim nobody can check is removed rather than carried.

---

## Acceptance

- The five boolean parameters refuse an unparseable value with a `400` naming it, and **a test for each** proves the unfiltered list can no longer be returned.
- The thirteen enums and eight integers follow, or the report says which ones did not and why.
- The door validator does no database work. Prove it — the landed ruling that forbids the existing helper on a read path is the reason it exists.
- The guard or the pinned inventory covers every declared query parameter, and fails before it passes.
- `.gitlab-ci.yml` is gone; a newline-bearing credential is refused by name.
- Denominators quoted, suites in CI's order, the eight-tenant fan-out if any column moves.

## Report

`docs/handoffs/21-REPORT.md`. Short.

1. **The five, first and before anything else** — what each one filters, and what it was returning instead.
2. **Whether any published enum would start refusing a value somebody is sending today.** The only part of this that can break a caller.
3. Your reading on the thirteen: server-side validation versus Vendra's client-side defence, and which side should own it.
4. Wall-clock, the correction share, and whether the machine behaved.

---

## Three things for the owner, unchanged and still true

- **The Odoo `admin` password is set by nothing in this repository, on any tenant.** `ODOO_MASTER_PASSWORD` is a different credential and the new refusal covers that one, not this one. `docs/DEPLOYMENT.md` now says so explicitly, and saying it is not doing it.
- **The `ODOO_ADMIN_PASSWORD` Secret** must exist before the next `nrs-import` run.
- **The two live-cutover credentials from report 17 §3** are still unrotated, and they are in git history.

## And one thing for me

**After this, Cadra owes two audit reports and a scope decision.** The access-change log and the configuration-change log are the last two of the five your specification names; the disposal-approval route needs me to decide whether `approvals:write` is the right gate, which I would rather do deliberately than inside a handoff about something else. Those three are the end of contracted core scope in this repository.
