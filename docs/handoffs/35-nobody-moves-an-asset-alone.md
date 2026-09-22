# Handoff 35 — Nobody moves an asset alone

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev`. **Branch:** `feat/approvals`.

> **The second thing NRS asked for at the demonstration.** Moving an asset and assigning a custodian should go to somebody else for approval. The owner has decided the shape; it will be reshaped later to match NRS's real structure, and it is explicitly a first version that has to work rather than a final one.
>
> **Two things you already know that change the size of this.** `nrs.asset.transfer` has had `draft → approved → done → rejected` from the beginning, with `action_approve` stamping the approver and `action_reject` beside it. **Nothing in the API or the app has ever used it** — report 27 measured zero approvers on 18 transfers and on 103, because `/move` creates its transfer already at `done`. And handoff 28 built the append-only movement record, which report 27 §13.2 said had to come first: *an approval recorded on a row an asset manager can delete is not an approval record.* **The prerequisite is done.**

## Step 0

```bash
git checkout dev && git pull --ff-only
git checkout -b feat/approvals && git push -u origin feat/approvals
```

Commit the instruction file first. **Run this before handoff 33** — 33 widens guards and can wait; this has stakeholders attached. Register your new routes in the guards as they stand, and 33 will widen around them.

---

## The shape, decided with the owner

- **A move or a custody change becomes a request.** Nothing happens to the asset until somebody approves it.
- **The approver is anyone who could have made the change themselves — and never the requester.**
- **The requester names who they are asking**, in the dialog.
- **The approver gets a queue in the app and a notification when something lands.**
- **On by default, switchable per tenant.**

---

## A · Which writers this applies to — answer this before you build

**Report 28 found six writers of `location_id`, and my list had named one.** So the first question is not how approval works, it is *what it applies to*, and getting it wrong in either direction is bad: approval on everything means an import of eleven thousand assets needs eleven thousand approvals, and approval on too little means the control is theatre.

**My ruling on the principle, for you to apply:** **approval is about a person deciding to move something.** A registration is not a move. An integration delivering an asset is not a move. A bulk import is not a move. **A human choosing, today, to put this asset somewhere else or in somebody else's hands is what needs a second person.**

**Enumerate every writer — both of `location_id` and of `custodian_id` — and say for each whether it is subject to approval and why.** That table is the specification, and I would rather read it before the code than after. INT-03 from Vendra, the importer, the seed scripts and `create` are the ones I expect to be outside it; tell me if I am wrong, because I have been wrong about this exact list before.

## B · One queue — and you decide how

Location has a workflow model. Custody has none. **The approver must see one list**, because *"what is waiting on me"* is one question and a person should not have to look in two places to answer it.

**How you get there is yours and I want the case made, both ways, as you did in report 30 §1.** A single request model covering both, with the existing transfer becoming the *result* of an approved location request rather than the request itself — or the transfer kept as the location request and something new for custody, with the queue unioning them. **You have read both models and I have not.** Say what each costs, including what happens to the eighteen and the hundred-and-three transfers already sitting in `done`.

**What is not negotiable, whichever you choose:**

- **The append-only records are written on approval, never on request.** A movement row or a custody link written when somebody *asks* would be a permanent record of a move that had not happened and might never happen. That is the worst thing this handoff could do, and the two models it would corrupt are the two the programme spent handoffs 14 and 28 building.
- **A request carries who is being asked. An approval records who clicked.** Those are two different fields and they must never be the same one. Handoff 23 ruled it for disposals — *the approver is the authenticated caller, never a field in the payload* — and the reason is unchanged: a requester who can name the approver can forge one.
- **Self-approval is refused in the model**, not hidden in the app. A hidden button is a door closed on one screen; report 30 found the same lesson when a disposed asset could be un-disposed through a route nobody had looked at.

## C · The switch, and why it is a safety setting rather than a preference

On by default, off per tenant, as the owner decided.

**Read it the way `database_class` is read.** When this switch says *off* an asset moves without a second person, so a stale value is a control that has stopped applying and nobody knows. **Handoff 25's ormcache leak is the precedent** — a guard served from a cache said *test* about a database whose mark had been deleted, and twenty-four writing tests went through. That was found by insisting on the absent case; do the same here.

**And a value that is neither on nor off is on.** Absent, unreadable, unrecognised — the safe direction is the one that asks for a second person.

## D · What happens while a request is waiting

This is where this kind of feature usually rots, so decide it deliberately and write the answers down:

- **Two requests for the same asset.** Can they exist? If both are approved, the second applies to a world the first changed.
- **The asset changes underneath.** It is disposed, or moved by a writer outside §A. **A request whose premise no longer holds must not be approvable in silence** — refuse it, saying what changed.
- **Withdrawal.** The requester changes their mind.
- **Rejection.** With a reason, and the requester finds out — the same way the approver found out.

**Say what you chose and why.** I am not ruling these from here because they interact with each other and with whatever you decide in §B.

## E · The app

- **The Move and Transfer-custody dialogs** in `AssetActionDialogs.tsx` gain an approver picker and their button becomes a request. **Say plainly on the dialog what will happen** — that the asset does not move until this is approved — because a storekeeper who thinks they have moved something and has not is the defect this programme is named after.
- **A pending-approvals queue**: what is waiting on me, who asked, what they want to change, what it is now, approve or reject with a reason.
- **A notification when one arrives.** Odoo has a mechanism for *somebody needs to do something* and it gives an inbox for free; use it rather than inventing one, and say what you used.
- **The asset itself shows a pending request.** Somebody opening an asset should not have to guess why the Move button is behaving differently.
- **Rebuild the bundle and run the journeys** — and per yesterday's finding, remember the built bundle is not the published one.

---

## Report

`docs/handoffs/35-REPORT.md`.

1. **§A's table first.** Every writer of location and custodian, in or out of approval, and why.
2. **§B's case**, both ways, and what you chose.
3. §D's answers.
4. What the switch does when its value is absent, proved by making it absent.
5. Wall-clock, and the correction share.

---

**This is a first version by the owner's own framing**, and NRS will reshape it around their structure — who may approve what, by value, by category, by office. **So build it so the rule can change without the record changing.** What must survive any reshaping is the record: who asked, who approved, when, and what it was before.
