# AI item identification: the evaluation and the rulings

**Date:** 15 October 2026.
**Architect.** Rulings agreed with the owner the same day.

**Reads:**

- `reference/ai-item-identification-addendum-2026-10-13.pdf`: the
  addendum, AI-FR-01…14 and AI-NFR-01…08;
- `reference/ai-capture-backend-endpoints-2026-10-13.pdf`: the mobile
  team's 24 endpoints;
- `reference/ai-item-identification-builder-findings-2026-10-15.md`: the
  Builder's findings. The section numbers below (§3, §5.6, Q1…) are that
  file's.

This document does for the AI addendum what `ADDENDUM-A-EVALUATION.md` did
for Addendum A.

---

## 1 · In plain words

The mobile team designed for one person who photographs a chair, prints a
tag and registers it on the spot. The Builder found that this collides with
three things already ruled and built:

- the seven-gate receipt chain;
- the rule that Cadra issues the asset code;
- the rule that a replacement tag gets a new number.

The answer to all three is one fact the Builder couldn't see: **SAP already
holds NRS's register.** The October export
(`reference/sap-asset-master-2026-10.md`) has 161,647 active assets, of
which 80,370 are furniture and fittings. A chair the Lot 4 audit team finds
in a room is almost certainly one of them. **A Lot 4 capture doesn't create
an asset. It finds an existing SAP asset, confirms it physically, and gives
it a Cadra tag.** Creating a new asset per chair would double NRS's
register against SAP's.

## 2 · The rulings

| # | Question (findings §8) | Ruling |
|---|---|---|
| R1 | Q1: is a Lot 4 audit capture a receipt? | **No.** It is its own path: **capture → match to the SAP record → tag → review.** See §3. The receipt gates (IAD value for money, maker-checker on cost) don't apply: nothing was bought and nothing is capitalised. Segregation is kept by a **reviewer**: a second person on the audit team approves each capture batch. A capture that matches no SAP record goes to a *found, not in SAP* exception list, never straight onto the register. SAP records nobody found make the *in SAP, not found* list. Those two lists are the audit's product. |
| R2 | Q2: does the phone issue codes? | **Yes, from blocks the Asset Controller issues to a registered device.** Each code in a block is `reserved`, then `active` (used by a confirmed capture) or `void`. Never reissued. "Return" on sync **voids** the remainder. This is AD-18's ledger, finally built. |
| R2a | Findings §7.1: the code is assigned at create, not at tagging request | **Accept the built behaviour for receipts.** A received unit gets its code at creation, hidden while it is a candidate. D1 now reads: *assigned at capture or creation, printed at tagging, active at registration, never reused*. The ledger records receipt codes as well as device codes, so there is one answer to "which codes exist". |
| R3 | Q3: does a replacement keep the code? | **Yes.** A replacement is a **reprint under the same code**, with a void reason and a reprint count on the label record. The old physical label's print is voided, and the history says which print is current. **Approver unchanged:** an Asset Manager, never the requester (handoff 38). The custodian or supervisor approval the addendum asks for is not added now. The gated-replacement defect (findings §5.6) is fixed by the same change. |
| R4 | Q4: how does the phone authenticate? | **As a named person, always.** `/auth/login` with the person's own account. A device is a registered record **bound to one person at a time**; it is not a credential. No shared or device logins: AI-NFR-05's "operator" must be a person. |
| R5 | Q5: *Unserviceable* or `decommissioned`? | **Not the same thing, so no mapping and no new enum value yet.** The app records *Unserviceable* as `poor`, with the note "unserviceable". The enum is asked of NRS (their open question 4). Rule 4: enums are published surface. |
| R6 | Q6: Pool | **Waits** for D10 (threshold) and D12. **Pool is Phase E**: the refusal sentence is right, and the Addendum A evaluation's §5 table is corrected to match. The *"Pool — {department}"* label clash is fixed when Pool is built. |
| R7 | Q7: hosting (AI-NFR-04) | **Owner's ruling: the current servers for now.** This is a **known deviation** from AI-NFR-04 (Nigerian hosting), recorded in GO-LIVE. **NRS must accept it in writing** before the first photo is stored on a production tenant. The deviation covers the whole system, not only photos. |
| R8 | Q8: room barcode | Every `generic.location` gets a **`location_code`**, unique per tenant, generated if empty. Its QR and Code 128 carry it verbatim (handoff 55 §3). It is printed on a room label from the station. |
| R9 | Findings §7.4: furniture needs make and model | The **default `tag_id` schema** becomes description, colour, material and dimensions. **Make and model become optional.** Classes whose schema was customised keep it. A chair with no visible brand can be recorded. |
| R10 | Findings §3: `/mark-missing`, `/mark-found`, `/verify` on a candidate | **Refused.** A candidate isn't on the register, so it can't be missing from it. The 58 guard (`not_on_the_register`) is extended to these three. |

## 3 · The audit-capture path (R1), for the handoffs that build it

**The SAP mirror.** A read-only reference table in Cadra holding SAP's
asset master, refreshed from SAP's export:

- the asset number;
- the class;
- the description;
- the old FIRS tag number (*inventory number*), which is not unique;
- the serial;
- the capitalisation date;
- active or retired.

It is **not** `nrs.asset`, and it never appears on the register. The owner
loads it from the export file with an owner-run import, the way the SAP
spreadsheet arrived. Later it comes over INT-07 once SAP's endpoint is live.

**On the phone, per item:**

1. The operator scans the **room code** (R8).
2. They photograph the item. The model suggests class, attributes and
   condition (AI-FR-01…05).
3. If the item carries an old FIRS tag, the operator scans or types it.
4. Cadra's matcher, from the cached slice of the mirror for that office,
   proposes up to five SAP records, ranked by:
   - the old tag number;
   - the description and class;
   - the office code in the old tag against the room's office.
5. The operator **picks one or says *none of these*.**
6. The phone takes the next code from its block (R2), prints the label,
   and the operator confirms the affix by scanning it.
7. Offline throughout. The capture syncs with a stored, unique
   `capture_id`, never the 24-hour idempotency cache (findings §7.3).

**On sync, per capture:** a `captured_audit` record (an append-only event
model, not fields on an asset) holding:

- the photos;
- the AI suggestion against the confirmed values (AI-NFR-05);
- the chosen SAP record or *none*;
- the code used;
- the operator and the device.

**Review:** a reviewer on the audit team (a different person; a new role
exclusion pair, capturer × reviewer) works through each day's captures by
room. For each:

- **Accept a matched capture:** the SAP asset is registered in Cadra as an
  `nrs.asset`, with its SAP number, class and capitalisation date from the
  mirror and the code from the capture. It enters at `registered`; the
  receipt gates don't apply (R1). The event says why.
- **Accept *none of these*:** the capture goes to the *found, not in SAP*
  list, for the Asset Controller to resolve. NRS decides later whether it
  becomes a new SAP asset through the normal registration.
- **Return:** with a reason, to the operator.

**Duplicates:** a second capture matching an SAP record that is already
accepted is held for review, with both photos side by side. The visual
signature (AI-FR-07/08) adds a check *within a room*. As the findings say,
no vector store is needed at that scale.

## 4 · What gets built, in order

*Renumbered by handoff 62 (2026-10-15): Cadra 62 is the register-state
event to Vendra, which closes the gated receipt loop go-live needs. The SAP
mirror is now 63 and the audit-capture path 64.*

1. **Cadra 61: the safe pieces and the fixes.**
   - The fixes: R3, R9, R10, and the R2a decision record.
   - The pieces any ruling allows: photos on an asset, the `updated_since`
     filter, `location_code` (R8).
   - The corrected endpoint map for the mobile team.
   - Nothing that issues a code, creates an asset from a capture, or
     touches the SAP mirror.
2. **Cadra 63: the SAP mirror and the matcher.** The owner-run import from
   the export, the matching route, and the *in SAP, not found* report per
   office.
3. **Cadra 64: devices, code blocks and the audit-capture path.** Device
   registration bound to a person, blocks issued by the Asset Controller,
   the ledger (R2, R2a), capture sync, review, and the two exception
   lists.
4. **The mobile app** is the mobile team's, built against 61, 63 and 64's
   published contracts. The model, its manifest and download are theirs
   (findings §4, "mostly outside Cadra").

## 5 · For the owner

- **R7:** tell NRS in writing that photos and data are on the current
  servers, outside Nigeria, and get their acceptance before production
  photos.
- **The SAP mirror (63)** needs the export file on hand when it runs. The
  October file serves for now; ask SAP's team for a refresh cadence.
- **NRS's open questions in the addendum** still stand: threshold, pilot
  sites, devices, condition → disposal, lost-tag approver, photo
  retention. Ask the threshold **once**: D10, AI-FR-13 and INT-06 §5.5 are
  the same question.
