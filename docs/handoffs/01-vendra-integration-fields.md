# Handoff 01 — Asset provenance fields and integration correctness (CR-01)

**From:** Architect · **To:** Builder (Claude Code in IDE)
**Source:** `docs/change-requests/CR-01-vendra-integration.md` (copied into this repo from the Vendra side, where it was raised)
**Branch:** `feat/vendra-integration-fields` off `dev`, PR into `dev` per the existing convention.

## Context — read this before the steps

Cadra is now the downstream of a real integration. Vendra (the Frappe/ERPNext goods-receipt system in the same programme) is building **INT-03**: every asset-classified line on a goods receipt becomes an asset in Cadra's register, created through `POST /api/v1/assets`.

Vendra's team read this repo's source to write their payload mapper and stopped, because three things make the integration the signed-off spec describes impossible to build honestly. Two are in this handoff. The third needs design and is Part C.

**This is not a defect report.** Cadra behaves as built. It was built before it had an integration partner, and now it has one.

Read `CLAUDE.md` first, especially §The ecosystem — the point that `POST /api/v1/assets` is now a contract another system depends on is the frame for everything below.

---

## Part A — an asset cannot record where it came from (CR-1)

**The gap.** The September 2026 Integration Flow §3.1 says the hand-off carries *"…cost, vendor, GRN reference, PO reference, receiving location"*, and §5 names the GRN Number and PO Number as identifiers *"created once … carried through … Cadra asset record"*. `nrs.asset` has none of them: no `grn`, no `goods_receipt`, no `purchase_order`, no `po_ref`, and no purchase-supplier field (`maintenance_vendor_id` is the maintenance provider — do not repurpose it). There is also no way to filter assets by any of them.

**Why it matters in business terms.** The programme is sold on one search answering both the financial and the physical question about an asset. Today an auditor holding a GRN cannot get from it to the assets that GRN created — in the system built to answer exactly that. Vendra can hold the link on its side, but a link only one party can traverse is not traceability.

**Build:**

1. **Fields on `nrs.asset`** — `grn_reference`, `purchase_order_reference`, `purchase_vendor` (Char; Vendra owns the authoritative records, so no relational modelling is needed here). Place them with the existing commercial/acquisition fields, not the maintenance ones.
2. **Expose `import_source` / `import_date` / `import_ref`** in `_WRITABLE_FIELDS`. These already exist and are written by the bulk importer (`asset_import.py:127-129`) but are not writable through the API, so an integration cannot stamp its own provenance.
3. **Add all six to `_WRITABLE_FIELDS`** (`v1_assets.py:214`) and to the serialised asset, so a create round-trips.
4. **Make them filterable on `GET /api/v1/assets`** — `?grn_reference=GRN-2026-00001` must return the assets that receipt produced. **This is the item that turns the data into an audit trail**; 1–3 without it leave the link one-directional and are worth much less.
5. OpenAPI annotations updated so the generated spec stays true, and pytest coverage in `tests/test_assets.py`: create-with-provenance round-trips, filter-by-GRN returns exactly the right set, and the fields appear in the serialiser.

**Decide and record:** whether these should also be exposed on `PATCH`. My view is yes for correction but they should be treated as write-once-in-practice; state what you chose and why.

## Part B — correctness items an integrator hits immediately (CR-3)

Each of these is small, and each currently fails **silently**, which is the worst shape for an integration bug.

1. **The published schema advertises a `condition` value the model rejects.** Docs list `damaged`; `asset.py:69-75` defines `new | good | fair | poor | decommissioned`. Sending the documented value returns 400. **Fix the docs, not the model** (Architecture rule 4). Vendra has already realigned its own field to Cadra's enum rather than wait.
2. **The idempotency header is `X-Idempotency-Key`, but the docs say `Idempotency-Key` in nine places.** A key sent under the documented name is silently ignored and the request processed as new — a duplicate-create bug with no error. Fix the docs.
3. **A key longer than 128 characters is silently treated as absent** (`utils.py:511-513`). Return **400** instead: degrading to non-idempotent without telling the caller defeats the mechanism, and the caller cannot detect it. Vendra has capped its key length on their side, but the next integrator will not know to.
4. **`idempotency_store()` runs outside the endpoint's try/except**, so two concurrent requests carrying one key produce a non-enveloped 500 rather than a replay. Bring it inside so a race returns the envelope.

Tests for 3 and 4; 1 and 2 are documentation.

## Part C — the tagging signal: design, do not build

**The gap.** Integration Flow steps 3.3–3.4 have Cadra issue a tag print instruction, the independent Tag-Issuing Unit print and affix it, and the serial-to-tag match recorded *"at the point of physical tagging"*. Vendra's receipt needs to reflect that progress. Cadra exposes no such signal: `state` is `active | in_repair | disposed | transferred | missing`, and `v1_assets.py:4-10` records that the PRD's fuller state machine *"is deferred to a future schema-extension pass."*

**The trap, which matters more than the gap.** `data.tag` looks like the answer and is not: `nrs.asset.create` auto-generates a tag on every create (`asset_tag.py:134-149`), so every asset carries a tag value whether or not a label was ever printed or affixed. An integrator trusting it would report every asset as tagged from the moment of creation — a false completeness claim written straight into the audit trail. The real state lives on `nrs.asset.tag.label`, which `serialize_asset` does not expose at all.

**What I want back — a short written proposal in your report, not code:**

- **Preferred direction: an outbound callback to Vendra when a label is issued and affixed.** This repo already has the shape at `/integrations/workflow/callback`. Tagging is an event; the register knows when it happens; polling for it is inherently wasteful. Tell me what it would take, what the payload should be, and how delivery/retry would work.
- **Alternative: expose `nrs.asset.tag.label` state** in `serialize_asset` plus a filter, so Vendra can poll. Cheaper; worse.
- Either way, say what the honest set of tag states actually is today, and whether "affixed" is even recorded anywhere — if it is not, that is the finding, and Vendra will keep showing `Registered` rather than claim `Tagged`.

Do not extend the `state` enum on `nrs.asset` as a shortcut. That is published API surface with a downstream consumer now.

---

## Acceptance

On the dev instance:

1. `POST /api/v1/assets` with `grn_reference`, `purchase_order_reference`, `purchase_vendor` and the `import_*` fields → 201, all values present on the returned asset, and `data._warnings.rejected_fields` **empty** (a non-empty warnings list is exactly what Vendra will treat as a failure).
2. `GET /api/v1/assets?grn_reference=<that GRN>` returns precisely the assets from that receipt.
3. An over-128-character idempotency key returns 400 with the standard envelope, not a silent non-idempotent create.
4. The generated OpenAPI at `/api/v1/openapi.json` reflects the new fields; the documented `condition` values and header name match reality.
5. Full pytest suite green (quote the run verbatim — with no CI gate on the Vendra side, the report is the audit trail, and I would rather this repo set the better example).

## Report

`docs/handoffs/01-REPORT.md` — what you built, decisions and why, deviations from this handoff with evidence, the Part C proposal, full test output, open questions, commit hashes and the PR link. Then notify the Architect per `CLAUDE.md`.

**On deviating:** the sibling project's best two outcomes both came from the Builder proving an instruction wrong before implementing it — a design I had specified confidently turned out to be impossible in the framework, and an exception class I named was the wrong one. If something here is wrong, that is the most useful thing you can tell me.
