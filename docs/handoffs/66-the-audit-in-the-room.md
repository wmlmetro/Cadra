# Handoff 66 — The audit in the room

**Branch:** `feat/the-audit-in-the-room`
**Report:** `docs/handoffs/66-REPORT.md` (~200 lines)
**Runs after:** 65, merged. Branch from `dev`, after pulling.
**Time budget:** 4 hours. If it won't fit, split at Step 0: **66a** the
server (§1–§5), **66b** the web review screens (§6). Follow `CLAUDE.md`'s
*Speed* and *Progress* rules, including the new rule 9: never sit idle
waiting on CI.
**Read first:** `docs/AI-CAPTURE-EVALUATION.md` §2–§3 (R1, R2, R2a, R4,
R8, R11), and your reports 61, 63, 64 and 65.

---

## 0 · Report 65 is accepted

Link to SAP works with two people and sends nothing to SAP. The guard held
a truncated file at 15%, and it caught a double-master case in your own
model before it shipped. The class evidence settles report 59's proposal
for the two classes that matter: **IT Equipment → 3000 (95%)** and
**Fleet / Vehicles → 1000 (99%)**. And §7 found where the real gap is.
5,835 Cadra assets share no words with any SAP description: Cadra says
*HP ProBook 450*, SAP says *LAPTOP*. Only someone in the room can link
those. That's this handoff.

**Rulings:**

1. **`nrs19` stays read-only.** Your safety layer was right to refuse
   seeding people into a copy of a real NRS staff extract. Linking NRS's
   real register happens on NRS's production tenant, with NRS's named
   officers. That tenant is the owner's next decision; it isn't here.
2. **Left items:**
   - the N+1 flag query: fix it if it's under 20 minutes;
   - the serial-basis contested re-check: add it (it's the twin of the
     fix you made for tags);
   - the duplicated CHANGELOG sections: dedupe.
3. **No visual-signature model** (AI-FR-07/08). R11 put recognition on the
   server through a general model. Duplicates are caught by what's
   measurable: the same SAP record, the same Cadra asset, or the same old
   tag, captured twice. The reviewer sees the photos side by side.
   `/ai/signatures` comes off the mobile map, marked *not needed (R11)*.
4. **Idle hours:** `CLAUDE.md` *Speed* rule 9 is new. Follow it.

## 1 · What the audit is (R1, restated with what 63–65 built)

An audit team walks a room. For each item, the phone captures it **offline**
and syncs later. **Each capture ends as exactly one of three outcomes:**

| The item is… | Found by | Outcome |
|---|---|---|
| **a. Already on Cadra's register** | scanning its Cadra label, its old FIRS tag (`legacy_asset_code`), or picking it from the room's asset list | **Verified in place:** the location, condition and a photo are recorded. If its label is missing or unreadable, a reprint **under its existing code**, approved by the reviewer, who is the second person (R3). No new code. |
| **b. In SAP's register, not in Cadra's** | 63's matcher: old tag, description and office, or a pick | **Registered from SAP:** a new `nrs.asset` with SAP's number, class and capitalisation date from the mirror, and **the code the phone printed** (R2). It lands at `registered`, because the receipt gates don't apply (R1), with an event saying why. |
| **c. In neither** | *none of these* | ***Found, not in SAP***: an exception for the Asset Controller. Its code is held (§2), never registered automatically. |

Every outcome needs **two people**: the capturer, and a reviewer who
accepts it. The capturer can't review their own captures.

## 2 · Codes and devices (R2, R2a, R4)

- **`nrs.audit.device`:** a name, the person it is bound to (one at a time),
  who registered it and when, and whether it's active. **The Asset
  Controller registers and rebinds devices.** A device is not a credential:
  the person signs in with `/auth/login` as themselves, and the device is
  identified by an `X-Cadra-Device` header checked against their binding.
- **`nrs.asset.code`, the ledger:**
  - fields: code (unique), state (`reserved` → `in_review` → `active` |
    `void`), block, device, person, reserved/used/voided times, the asset
    it became, and the void reason;
  - **backfill every existing asset code as `active`**, in a migration
    that prints the per-tenant count;
  - every new asset's code writes a ledger row (R2a), so there is one
    answer to "which codes exist".
- **Blocks:** the Asset Controller issues N codes (at most 500) to a
  device and its bound person.
  - Draw them from the asset-code sequence **under a lock**, as 63b did
    for tags.
  - **Returning a block voids its unused codes.** They are never reissued
    (R2).
  - A capture may use only a code reserved to **its** device and person.
  - Say what `_order = 'asset_code desc'` now means (report 61 §7.2), and
    whether anything user-facing needs a different sort.

## 3 · Audit campaigns

**`nrs.audit.campaign`:** a name, the locations or office codes it covers,
the team (capturers and reviewers), dates, and a state (`open` →
`closed`).

- Captures belong to a campaign.
- **Closing a campaign produces the two lists the audit exists for**, per
  office:
  - ***Found, not in SAP***: outcome c;
  - ***In SAP, not found***: the active SAP records whose office is in the
    campaign and which no capture matched and no Cadra asset links to.
    Records with no office are reported as a count, not as "not found":
    without SAP's location extract (report 63) they can't be placed.
- **Closing needs every capture reviewed.** Say how many are still
  waiting.

## 4 · The capture route, for phone and web

**`POST /api/v1/audit/captures`**, idempotent on a client `capture_id`
(a UUID, **stored unique**, never the 24-hour cache: report 61 §7.3).

- **Body:**
  - campaign, room (`location_id`, from its scanned room code: 61 §7);
  - photos (61's photo ids, or upload);
  - `ai_suggestion_id` (64), optional;
  - the confirmed fields;
  - the outcome and its target (Cadra asset id, SAP record id, or *none*);
  - for b and c, the code used and the **scanned label value**, which must
    equal it (the affix check);
  - `captured_at`: up to **5 working days** in the past (AI-NFR-02),
    never in the future.
- **Refusals, in words:**
  - a code not reserved to this device and person;
  - a code already used;
  - a closed campaign;
  - a room outside the campaign;
  - a Cadra asset or SAP record already accepted in this campaign. That
    one is **held for review** as a duplicate, not refused, so the
    reviewer sees both.
- **The record:** an append-only `nrs.audit.capture` with everything sent,
  plus the operator, the device, `received_at` and `state =
  pending_review`. It is AI-NFR-05's trail, with 64's suggestion linked.
- **`GET /api/v1/audit/captures/{capture_id}`**, for the phone to confirm a
  sync.
- **For offline phones:**
  - `GET /api/v1/audit/campaigns/{id}/slice?location_id=` gives the room's
    Cadra assets plus the mirror's records for its office, paged with 61's
    sync rule;
  - and `GET /api/v1/ai/config`: the switch, the model, the cap remaining
    today, and the label layout as data (QR first, the code verbatim, no
    Code 128 below large: handoffs 54 and 61).

## 5 · Review

**`nrs.audit.reviewer`** is a new role; the capturer is **`nrs.audit.capturer`**.
Add a role exclusion, capturer × reviewer (58's table).

- **Accept:**
  - a: the location and condition are written as a verification, with the
    photo on the asset;
  - b: the asset is created at `registered` with the mirror's data and the
    capture's code, and the code goes `active`. **No `asset.master.create`
    is queued**, because SAP has it (65's rule; prove it);
  - c: the capture goes to the exception list, and the code stays
    `in_review`.
- **Return:** with a reason, to the capturer. The code is kept for the
  re-capture.
- **Reprint (outcome a, label missing):** the reviewer's acceptance *is* the
  approval. The reprint follows 61's same-code rules.
- **Batch accept per room,** by 60's rules: N single acts, per-item
  results.
- **Exceptions (c):** the Asset Controller either *registers it as new*
  (through the normal Register Maker and Checker gates, with the capture's
  code) or *voids it*, with a reason, which voids the code. Either way the
  physical label is accounted for.

## 6 · The web screens

- ***Audit*** in the sidebar, for the two roles and the Asset Controller:
  - **Campaigns**: open or close, with progress (captured, reviewed,
    exceptions);
  - **Review**: by room, photos side by side, the AI suggestion against
    what was confirmed, and duplicates highlighted;
  - **Devices and code blocks**: the Asset Controller's;
  - **Exceptions**;
  - the two **closing lists**, exportable.
- **Web capture, for a desk-side audit:** the same capture route, with the
  browser camera and 64's *Identify*. One screen. The phone app remains
  the mobile team's.

## 7 · What must not change

- The receipt gates and everything else from 57–65, gates on and gates off.
- `nrs19` (read-only) and every cluster tenant.
- Nothing is sent to SAP by an audit outcome.

## 8 · Verification

Targeted tests while building; one final local run; CI cited; per *Speed*.
On `test19f`, seed a campaign over two rooms, with SAP mirror records and
Cadra assets in the export's *shapes*, never real rows. Then:

1. Each outcome a, b and c, end to end, as the personas, through the HTTP
   route, with the second person accepting.
2. Each refusal, a duplicate held for review, and a capture synced twice
   with the same `capture_id` making one record.
3. The block lifecycle: issue, use, return (unused codes voided), and a
   void reason on an exception.
4. A campaign closed, with both lists printed.
5. The capturer refused their own review; the role exclusion refused at
   grant.
6. No master queued for b (in-registry, with a live stub target, as in 65).
7. The browser: the review screen and the web capture, one spec each.

## 9 · The question for the report

**What does the mobile team need now that they didn't have yesterday?**
Rewrite `docs/integrations/mobile-ai-capture-endpoints.md` so that every
row is **exists** or **not needed**, with nothing left *comes later*. List
anything they still can't build.
