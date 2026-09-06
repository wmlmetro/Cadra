# INT-05 — `asset.tag.affixed` (Cadra → Vendra)

**Status:** built in Cadra (handoff 06). **Not yet received by anything** — this
document is the contract Vendra builds its endpoint against.

Cadra raises this event when a Tag-Issuing Unit operative confirms, through
`POST /api/v1/assets/{id}/tag-affixed`, that the label Cadra issued for an
asset is physically on that asset. It is the signal that lets a Vendra receipt
line move from `Registered` to `Tagged` — the first time Vendra has had one.

---

## Delivery model

Cadra does **not** POST inline. An affix confirmation writes a row to an
outbox (`workflow.dispatch.log`) inside the same transaction as the capture,
and an `ir.cron` delivers it afterwards. Two consequences you can rely on:

- **Cadra never announces an affix that did not commit.** If the confirmation
  rolls back, so does the queued event.
- **Your availability does not affect Cadra's.** The Tag-Issuing Unit's
  confirmation succeeds whether or not you are up, and the event waits.

Retry is capped exponential backoff — `min(base × 2^(attempts-1), cap)`,
defaulting to 60 s base / 1 h cap / 8 attempts, configurable per tenant. After
the budget is exhausted the event is **dead-lettered**: it stops retrying, is
listed under *Workflow → Failed Deliveries* in Cadra, and a note is posted to
the asset's chatter. A human then fixes the cause and presses Retry, which
reuses the same `event_id`.

This is deliberately the same model as Vendra's own `Vendra Integration
Message` outbox pointing the other way, down to the status names — `Queued`,
`Sent`, `Acknowledged`, `Failed`, `Dead` — so that debugging INT-03 and INT-05
at the same time does not mean learning two systems.

---

## The request

```
POST <rest_base_url><rest_endpoint_event>
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>        # or X-API-Key / Basic — configurable
X-Idempotency-Key: <event_id>
X-Event-Id:        <event_id>
X-Request-Id:      WDL-2026-0001     # the Cadra outbox row; quote it in logs
```

`X-Idempotency-Key` is spelled with the `X-` prefix on purpose: it is the same
header Cadra reads on the inbound INT-03 leg, so neither side has to remember
which direction it is going.

### Body

```json
{
  "event": "asset.tag.affixed",
  "event_id": "633d46ed525c4c848d49b4b18f24b3d7",
  "occurred_at": "2026-09-06T19:03:38Z",
  "source": "cadra",
  "asset": {
    "id": 11911,
    "asset_code": "NRS-IT-LT-00421",
    "name": "INT-05 transport probe",
    "serial_number": "SN-INT05-1788...",
  },
  "tag": {
    "label_id": 11907,
    "number": "NRS-ACS-001",
    "label_state": "affixed",
    "issued_at": "2026-09-06T19:03:12Z",
    "printed_at": null,
    "affixed_at": "2026-09-06T19:03:38Z",
    "affixed_by": "Administrator",
    "affixed_by_name": "J. Okafor"
  },
  "provenance": {
    "grn_reference": "GRN-2026-00001",
    "purchase_order_reference": "PO-2026-00417",
    "purchase_vendor": "Dell Nigeria Ltd",
    "import_source": "vendra",
    "import_date": null,
    "import_ref": "MAT-PRE-2026-00001"
  }
}
```

Notes that matter when you write the handler:

- **`event_id` appears in the body as well as the header**, and they are always
  equal. Dedupe on either.
- **`asset.id` is the Cadra asset id** — the same integer INT-03 returned to you
  as `data.id`, so you can match on it directly.
- **`tag.label_id` is NOT an asset id.** The two id spaces collide numerically
  in Cadra (22 assets on `nrs19` have an asset id that is a valid label id for
  a *different* asset). Never feed one where the other is expected.
- **`provenance` is echoed so you never need to hold a Cadra id to match.**
  `grn_reference` is your own GRN and `import_ref` is the document name you
  sent on INT-03; either resolves the receipt line.
- **`printed_at` may be `null` on a genuinely affixed label.** Cadra records a
  print only when it actually rendered a PDF. A null means "we did not observe
  a print", not "not tagged" — `label_state` is the field that answers tagging.
- **`affixed_by` and `affixed_by_name` are different things.** `affixed_by` is
  the Cadra API credential that submitted the confirmation (the Tag-Issuing
  Unit's client); `affixed_by_name` is the human who physically fitted the
  label, who is not a Cadra user. Either may be null.
- Timestamps are ISO 8601 with an explicit `Z`.

---

## The response Cadra expects

| You return | Cadra records | Retries? |
|---|---|---|
| `200` / `201` / `202` / `204` with a JSON body carrying an identifier | `Acknowledged`, and stores your id in `external_ref` | no |
| `2xx` with no identifier in the body | `Sent` | no |
| **`409`** | `Acknowledged` — a duplicate is a successful dedupe, not a failure | no |
| `408`, `425`, `429` | `Failed`, backs off | yes |
| `5xx`, timeout, connection error | `Failed`, backs off | yes |
| any other `4xx` (`400`, `401`, `403`, `404`, `422`) | **`Dead` immediately** | **no** |

The last row is the one to design against: **a 4xx dead-letters on the first
attempt.** A request does not become valid by being sent eight more times, and
burning the budget only delays the moment a human sees the problem. If you
want Cadra to retry, return a 5xx or a 429.

To be recorded as `Acknowledged` rather than merely `Sent`, return an
identifier in the body — Cadra reads `event_id`, `name`, `reference`, `ref` or
`id`, looking through one level of a `message` or `data` wrapper (so Frappe's
own `{"message": {...}}` envelope works unmodified).

---

## What Vendra needs to implement

1. **A whitelisted endpoint**, e.g.
   `vendra_network.api.tag_event`, allowing guest/API access with the same
   credential model INT-03 already uses in reverse.
2. **Dedupe on `X-Idempotency-Key`.** Store it. On a repeat, return `409` with
   the original message's name; do not process twice. This is the sibling of
   what Cadra already does for you on `POST /api/v1/assets`.
3. **Resolve the receipt line** from `provenance.import_ref` (the Purchase
   Receipt name you sent) plus `asset.serial_number`, or from
   `asset.id` against the unit's stored `cadra_asset_id`.
4. **Set `cadra_status = "Tagged"` on the unit**, and let the existing
   weakest-link roll-up move the line and document summary. The `Tagged` value
   already exists in Vendra's select — nothing has ever been able to set it.
5. **Return an identifier** so Cadra records `Acknowledged` rather than `Sent`.
6. **Return a 4xx only when the payload is genuinely unusable** (unknown serial,
   unknown asset). Anything transient must be a 5xx.

Once that exists, the C4 readback deferred since handoff 04 becomes buildable:
Vendra will hold a real `Tagged` state rather than inferring one.

---

## Configuring the Cadra side

Per tenant, under **Workflow → Integration Settings**, a second configuration
row with **Purpose = "Asset lifecycle events (INT-05 → Vendra)"**:

| Field | Value |
|---|---|
| Adapter Type | REST API |
| Workflow API Base URL | e.g. `https://vendra.nrs.gov.ng` |
| Event Endpoint | e.g. `/api/method/vendra_network.api.tag_event` |
| Auth Type + credential | as Vendra requires |
| Emit Asset Events | on |
| Max Delivery Attempts / Base Delay / Cap | 8 / 60 s / 3600 s |

A tenant with **no** such row emits nothing — which is the correct state for
the seven Cadra tenants that have no Vendra. The absence is logged at INFO on
every affix, not silently ignored.

`nrs19` has the row already, **disabled**, pending Vendra's endpoint: set the
base URL and event endpoint and switch *Emit Asset Events* on.
