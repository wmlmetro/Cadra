# Handoff 06 — Tag transport (INT-05 outbound), and the loose ends

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Base:** `dev` after PR #48. **Branch:** `feat/tag-callback` → PR into `dev`.

## Step 0

```bash
git checkout dev && git pull
# PR #48 carries myservice_api migration 19.0.3.1.0 — fan out per tenant across
# all eight, then the verification table. Un-upgraded tenants keep minting
# wildcard session tokens, so this one matters more than most.
git checkout -b feat/tag-callback
```

### Needs the owner

- **Merging the PR** (standing).
- **The production deploy of #48 must fan out per tenant** — until it does, un-upgraded tenants still hand every logged-in user `tagging:write`. This is the security fix; a partial deploy leaves the hole open where it is not applied.
- **Rotating `test_client`'s secret on `nrs19`** — still outstanding, still owner-blocked, still not blocking.
- **Three test users on `nrs19`** (`h05_storekeeper`, `h05_tagger`, `h05_nobody`) left deliberately so the Part A transcripts reproduce. Delete when satisfied; they must not reach staging.

---

## Report 05 is accepted

**The `settings:write` scope was the right call, and I am glad you asked rather than assumed.** You found the trap I had not: `admin` is itself a wildcard in `require_jwt`, so the obvious mapping — Asset Manager → `admin` — would have moved the hole rather than closed it, handing every asset manager `tagging:write` in the name of keeping the Settings pages working. Both literal options were bad; inventing a narrower scope was the third. Additive, non-breaking, and it closes the hole without breaking the desk UI. **Explicitly sanctioned**, as you asked.

**Shipping the data migration was correct too.** Without it the fix would have been cosmetic for thirty days while refresh tokens replayed stored wildcard scopes — a fix that reports success and does nothing is worse than no fix, and it is a close cousin of the `[ruled]` vs `[landed]` problem you caught last time.

**And item 7 is the one that matters most.** `print-url` was emitting a path built from the report action's xmlid rather than its `report_name`, so it resolved to nothing and returned the website's 404 page — with a 26KB HTML body, so anything checking merely for a non-empty response would believe it had a label. The one published route from an asset to a printable label had **never rendered anything**, and the contract documented that broken URL as the print step. Vendra's demo has been printing nothing this whole time. Nobody caught it because the SPA composes labels client-side. Reading `report_name` off the action record so a template rename cannot reintroduce it is the right fix.

### Rulings

1. **`tagging:write` stays inside the `admin` wildcard — agreed, no change.** "Absolute below system-administrator" is a defensible posture and breaking `admin`-holding clients to tighten it is not worth it today. Document the limit where the scope is defined, so the next reader knows it is a decision rather than an oversight.
2. **`settings:write` — sanctioned**, per above.
3. **Fix the `phase1_*` seed users.** Honestly-empty scopes are correct behaviour exposing bad seed data. Give them the role their purpose implies, or delete them if the accounts are dead — but do not leave accounts whose scopes are empty by accident looking like accounts whose scopes are empty by design.
4. **`dashboards:read` and `requests:write` stay coarse — backlogged.** Splitting them is a bigger contract change than its value today, and nothing downstream is asking for it.

---

## The work — transport, now that capture exists

Handoff 03 established the sequence: capture first, transport second, because building transport first would have shipped an event that could only fire from data nobody recorded. Capture now exists — `label_state`, print stamping at the render layer, the scoped affix confirmation — so the callback has something true to carry.

**The gap you identified in report 01 is the one to solve properly:** `workflow.dispatch.log` records attempts, but **nothing retries**. A callback fired while Vendra is redeploying is lost, and the log faithfully records the loss. That is the whole job here — the payload is easy, the delivery guarantee is not.

**B1 · The event.** `asset.tag.affixed`, raised when an affix confirmation lands. Payload per your own proposal in report 01 §Part C — asset id, asset code, serial, tag number, `label_state`, issued/affixed timestamps and who affixed it, **plus the `provenance` block**. Echoing provenance is what lets Vendra match the event to a receipt line without holding a Cadra id, and it closes the loop the fields in CR-01 opened.

**B2 · Delivery that survives the other end being down.** Build on `workflow.config` / `workflow.dispatch.log` — they already carry adapters, auth modes, timeouts and a permanent audit trail. Add: an `ir.cron` draining `pending` and `error` with capped exponential backoff, `event_id` as the idempotency key so a redelivery is safe for Vendra to dedupe, and a dead-letter state after N attempts that is **visible to a human**, not merely logged. Vendra's outbox is the sibling of this and its shape is worth reading — `Vendra Integration Message` in `vendra_network`; the two systems having recognisably the same delivery model is worth something when someone debugs both at 2am.

**B3 · Configuration.** Which endpoint, which auth, whether the callback is enabled at all — per tenant, since `nrs19` is the only one wired to a Vendra today.

**B4 · Do not claim more than the event proves.** `printed` means a PDF was rendered; `affixed` means someone confirmed through the scoped endpoint. The whole point of handoff 03 was refusing to let a field imply a physical fact it does not know. The callback inherits that discipline.

## Acceptance

- An affix confirmation on `nrs19` results in a delivered callback, recorded in `workflow.dispatch.log`.
- **With the receiver down**, the event queues, retries with backoff, and delivers when it returns — proven live by stopping the receiver, exactly as Vendra proved INT-03 by stopping Cadra.
- A redelivery carries the same `event_id`.
- Dead-lettering after N attempts is visible to a human.
- Full suite green, quoted verbatim; per-tenant loop shown.

## Report

`docs/handoffs/06-REPORT.md`. Push, open the PR, name the merge as owner-blocked, notify the Architect.

**Coordination:** Vendra is building the SAP leg in parallel and is not waiting on this. When this lands, Vendra gets a real `Tagged` signal for the first time and its C4 readback — deferred since handoff 04 — becomes buildable. Say in your report what Vendra needs to implement to receive it, and I will write that handoff.
