# Cadra Change Request 01 — asset provenance fields and a tagging callback

**Raised by:** Vendra Network team (WestMetro) · 5 September 2026
**Against:** `myservicenrs` (Cadra) — `myservice_api`, `myservice_asset_register`
**Status:** open · **Blocking:** INT-03 traceability and INT-03 status readback (Vendra ↔ Cadra, September 2026 Integration Flow, Stage 3)

## Why this exists

Vendra is building INT-03, the hand-off that turns an asset-classified goods receipt line into a Cadra asset record. Reading Cadra's source to write the payload mapper surfaced two gaps that Vendra cannot close from its side. Both are small changes in Cadra; neither is a design disagreement.

This is not a defect report — Cadra behaves as built. It is a request to extend it so the integration the signed-off spec describes can actually exist.

---

## CR-1 · An asset cannot record where it came from

**What the spec requires.** The September 2026 Integration Flow, Stage 3 §3.1, defines the INT-03 payload as carrying *"item description, make, model, serial number, quantity, condition, cost, vendor, **GRN reference**, **PO reference**, receiving location."* §5 Key Identifiers then names the GRN Number and PO Number as identifiers *"created once, by one system, and referenced everywhere else"*, explicitly *"carried through … Cadra asset record"*.

**What Cadra has.** Nothing for any of the three. `nrs.asset` has no `grn`, no `goods_receipt`, no `purchase_order`, no `po_ref`, and no purchase-supplier field — the only vendor-shaped field is `maintenance_vendor_id`, which is the maintenance provider and would be a semantic overload. There is also no way to query assets by GRN, so even a free-text workaround is not retrievable.

**Why it matters beyond tidiness.** This is the audit trail the programme is sold on. The business case for Cadra is that one search answers both the financial and the physical question about an asset — and today an auditor holding a GRN cannot get from it to the assets it created, in the system built to answer exactly that. Vendra can hold the link on its side, but a link only one party can traverse is not traceability.

**Requested change (small).** The model already carries `import_source`, `import_date` and `import_ref` — written by the bulk importer (`asset_import.py:127-129`) but absent from the API's writable-field allow-list. We ask for:

1. `import_source` / `import_date` / `import_ref` added to the API allow-list on asset create, so an integration can stamp its own provenance;
2. dedicated fields for `grn_reference`, `purchase_order_reference` and `purchase_vendor` (Char is sufficient — Vendra owns the authoritative records);
3. those fields filterable on `GET /api/v1/assets`, so `?grn_reference=GRN-2026-00001` returns the assets a receipt produced.

Point 3 is the one that turns the data into an audit trail. Points 1–2 without it still leave the link one-directional.

**Interim behaviour.** Until this ships, Vendra will place the references in the free-text `notes` field so the information is at least present on the record, and will move them to the real fields when they exist. Vendra's own `Vendra Receipt Serial` table holds the authoritative mapping in the meantime.

---

## CR-2 · There is no tagging status to read back

**What the spec requires.** Stage 3 steps 3.3–3.4: Cadra issues a tag print instruction, the independent Tag-Issuing Unit prints and affixes it, and the serial-to-tag match is *"recorded at the point of physical tagging."* Vendra's receipt needs to reflect that progress — a storekeeper and an auditor both need to know which received units are actually tagged.

**What Cadra has.** No exposed signal. `state` is `active | in_repair | disposed | transferred | missing` — there is no `tagged`, and `v1_assets.py:4-10` records that the PRD's fuller state machine *"is deferred to a future schema-extension pass."*

Critically, **`data.tag` is not a proxy for "physically tagged"**: `nrs.asset.create` auto-generates a tag on every create (`asset_tag.py:134-149`), so every asset Vendra creates comes back already carrying a tag value whether or not a label was ever printed or affixed. The real signal lives on a separate `nrs.asset.tag.label` record whose state `serialize_asset` does not expose at all.

**Why it matters.** A field that looks like the answer but is always populated is worse than a missing field — it invites an integration to report every asset as tagged from the moment of creation, which would put a false completeness claim straight into the audit trail.

**Requested change.** Either:

- **(preferred)** a webhook/callback to Vendra when a tag label is issued and affixed — Cadra already has the outbound-callback shape at `/integrations/workflow/callback`; or
- expose the `nrs.asset.tag.label` state in `serialize_asset`, plus a filter on `GET /api/v1/assets`, so Vendra can poll.

The callback is preferred because polling for this is inherently wasteful — tagging is an event, and the register knows when it happens. It also matches the spec's own framing of INT-05 as an event ("issuance confirmation … recorded at the point of physical tagging").

**Interim behaviour.** Vendra will record `Registered` on successful create and will not claim `Tagged` for any unit until a real signal exists. The status simply will not advance — which is honest, and visible.

---

## CR-3 · Two smaller correctness items found while reading

Not blocking, but cheap to fix and each is a live trap for any integrator:

1. **The published API schema advertises a `condition` value Cadra rejects.** The docs list `damaged`; `asset.py:69-75` defines `new | good | fair | poor | decommissioned`. Sending the documented value returns 400. *(Vendra has realigned its own field to Cadra's enum rather than wait — this is only a docs fix.)*
2. **The idempotency header is `X-Idempotency-Key`, but the docs say `Idempotency-Key` in nine places.** A key sent under the documented name is silently ignored and the request is processed as new — a duplicate-create bug that gives no error. Additionally, a key longer than 128 characters is silently treated as absent (`utils.py:511-513`); returning 400 would be far safer than degrading to non-idempotent.
3. **`idempotency_store()` runs outside the endpoint's try/except**, so two concurrent requests carrying one key produce a non-enveloped 500 rather than a replay.

---

## What Vendra needs, and by when

INT-03 will be built now against the payload Cadra accepts today. Nothing here blocks that work. What these changes block is the **traceability claim** (CR-1) and the **tagging status** (CR-2) — both of which are commitments in the signed-off Integration Flow, so they need to exist before that document can be demonstrated to NRS, not before Vendra's next sprint.

Suggested sequencing: CR-1 points 1–2 and CR-3 are hours of work; CR-1 point 3 and CR-2 need a little design. Happy to review a PR or supply the exact field shapes Vendra will send.
