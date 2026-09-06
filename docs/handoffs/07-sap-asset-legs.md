# Handoff 07 — The SAP asset legs (INT-06 / INT-07 / INT-09)

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #49. **Branch:** `feat/sap-asset-legs` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
# per-tenant fan-out for anything since #49, all eight databases, then the
# verification table. Paste it into the report.
git checkout -b feat/sap-asset-legs
```

### Needs the owner

- **Merging the PR** (standing).
- **Part A is time-sensitive and the owner is waiting on it** — see below.

---

## Report 06 is accepted

The callback works, and it works the way it needed to: 60s → 120s → delivered on the third attempt, with attempt 1 a real connection failure and attempt 2 a genuine 503 from the receiver. Proving it by **actually stopping the receiver** rather than mocking a failure is the same instinct Vendra used when it killed Cadra mid-run, and it is why both of those claims are worth something.

Two things I want to name. **Verifying the end state directly rather than inferring it from the migration log** — zero un-revoked wildcard session tokens across all eight tenants, checked, not assumed — is exactly right for a security fix; a migration that logs nothing because the work was already done looks identical to one that silently did nothing. And **writing `docs/integrations/INT-05-tag-affixed-callback.md` for Vendra to build against** is the thing that stops this becoming another `print-url`, where a documented route had never rendered anything. Vendra will build the receiver from it.

---

## Part A — first, and quickly: what do you need from SAP?

**Do this before writing any code, and report it before you finish the rest.**

I have written `sap-vendra-interface-spec.md` on the Vendra side — the document that goes to whoever manages SAP at NRS. It currently covers purchase orders in and goods receipts out. **It does not cover the asset side, and the owner is about to send it.** One complete document to one counterpart is worth a great deal more than a spec followed by an addendum a week later, so this is the piece that is genuinely blocking.

Read the September Integration Flow's Stage 4 and Stage 6, then tell me precisely:

1. **INT-06 · asset master creation and capitalisation.** What does Cadra need to send, field by field, for SAP to create the asset and capitalise it? Where does each field come from in `nrs.asset`? What must SAP return beyond the asset code — capitalisation date, net book value, anything else the register should display?
2. **INT-07 · the SAP asset code coming back.** Push or pull? Synchronous in INT-06's response, or a separate call? Your recommendation with reasoning — the spec asks SAP for what we need, so this is our choice to make and defend.
3. **INT-09 · lifecycle events.** Transfers, custodian and location changes, revaluation, impairment, disposal and retirement. Which of these does SAP actually need, what does each carry, and are they one endpoint with an event type or several?
4. **Anything SAP must give us that we do not have** — an asset class mapping, a cost centre list, a company code. Cadra's `category_id` problem on the Vendra side is the warning here: an identifier that exists on both systems and means different things fails silently with a 201.

Write it as `docs/integrations/INT-06-07-09-sap-requirements.md`, in the same register-and-payload shape as the Vendra spec so I can fold it in without translating. **Report it as soon as it is written** — do not wait for Part B.

---

## Part B — build it, mocked

Same posture as Vendra's Phase 3: no SAP access exists, so build behind an adapter with a mock, clean enough that the real connector is a backend swap.

**Reuse, do not rebuild.** The callback machinery from handoff 06 — `workflow.dispatch.log`, the `ir.cron` drain, capped exponential backoff, `event_id` idempotency, the dead-letter state — is precisely what INT-06 and INT-09 need. They are outbound events to a system that will sometimes be down. If you find yourself writing a second delivery mechanism, stop: one system with two delivery models is how the next person loses a day.

**INT-06 · on tagging confirmed**, send the asset master to SAP. The trigger matters: the September register says capitalisation follows tagging, so an asset that has not been physically confirmed must not be capitalised. That is the same discipline as capture-before-GRN on the Vendra side, and it is the reason the tag capture work came first.

**INT-07 · store what SAP returns.** `sap_asset_code` already exists on `nrs.asset` from handoff 03's field work — check before adding anything.

**INT-09 · lifecycle events** through the same delivery machinery, with the event type in the payload.

---

## Part C — the dual-code control, made visible

This is the part with a name in the specification, and it is the reason INT-06 and INT-07 exist as a pair:

> *"An asset is complete only when both the Cadra Asset Code and the SAP asset code are linked on the register."*

Handoff 02 already made half of it real — `asset_code` is unique and `NOT NULL` in every tenant. The other half is that **an asset carrying only one of the two codes is an exception somebody must see**, not a quiet row. A Cadra code with no SAP code means finance never booked it; an SAP code with no Cadra code means there is money on the books with no physical thing behind it. Both are audit findings, and today neither is visible anywhere.

Build: a state on the asset that says whether it is reconciled, a filter for it on the API, and a report or dashboard entry that answers "how many assets are incomplete, and which". Make it something an auditor can be shown, because that is who it is for.

## Acceptance

- Part A's requirements document exists and is reported early.
- With the mock: tagging an asset produces an INT-06 posting; the returned code lands on the register; a lifecycle event delivers; **stopping the mock receiver** queues, retries and delivers on return, as INT-05 did.
- An asset with only one code is findable through the API and appears in the reconciliation view.
- Full suite green, quoted verbatim; per-tenant loop shown.

## Report

`docs/handoffs/07-REPORT.md`. Push, open the PR, name the merge as owner-blocked, notify the Architect.

**Coordination:** Vendra is building its API documentation and then the INT-05 receiver, so nothing here blocks it. When Part A lands I fold it into the SAP spec and the owner sends one document covering all five SAP interfaces.
