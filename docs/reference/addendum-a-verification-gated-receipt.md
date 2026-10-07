<!-- Converted from 'Addendum A - Verification-Gated Receipt to Asset Register.docx' (WestMetro, 7 October 2026) by pandoc on 7 October 2026. The .docx is the signed original; this file is the working copy the handoffs cite by section and AD-number. -->

**WESTMETRO**

**Addendum A**

**Verification-Gated Receipt to Asset Register**

Developer specification for Vendra and Cadra

NRS asset management programme · 7 October 2026

*Supersedes the direct Vendra-to-Cadra push in Flow D of the v0.5 process document*

1\. Purpose and scope

No capital item enters the asset register until Store has received it, IAD has validated it for Value for Money, the Audit Tagging Team has tagged it, and a maker-checker pair has registered it. This addendum specifies that gated process so it can be built as a separate work package.

**What changes.** Today a matched capital purchase pushes straight from Vendra to Cadra and creates a register asset. That push is replaced: receipt now creates an *asset candidate* that moves through verification gates and only becomes a register asset at the final approval.

**In scope:** delivery scheduling from the PO feed, vendor delivery notice, receipt, attribute capture, IAD Value-for-Money validation, tagging request and tagging, asset registration with maker-checker, classification from SAP codes, distribution by Store, and the handling of items without manufacturer serial numbers (Section 12).

**Out of scope:** PO creation and approval, three-way match and payment logic (unchanged, except the optional payment hold in Section 11), and the asset lifecycle after distribution.

**Source:** NRS stakeholder validation session, 7 October 2026. This addendum supersedes the direct Vendra-to-Cadra push described in Flow D of the v0.5 process document.

**Systems.** Vendra hosts scheduling, delivery notice, receipt and capture. Cadra hosts the verification gates, tagging and the register. SAP supplies the PO feed, material codes and asset codes.

2\. End-to-end process

Store receives and captures, then IAD, the Asset Controller, the Audit Tagging Team and a register maker-checker pair each act in turn. Only the registration checker's approval creates a register asset.

*[Figure 1 is in the original .docx: nine steps, four gates, three return paths. The state table in Section 3 is the authoritative form.]*

*Figure 1. Receipt-to-register flow: 9 steps, 4 gates, 3 return paths*

A VfM query loops back to Store for correction, and a rejection exits to GRN reversal. A registration the checker returns goes back to the maker, with the tag and reserved code kept.

3\. Record state machine

Each serialised unit is tracked as one asset candidate with a single status field; only the transitions below are permitted, and each is fired by one role. Non-serialised lines follow Section 12.

| **From**                    | **To**        | **Trigger**                         | **Fired by**                | **Guard**                                                                                                                    |
|-----------------------------|---------------|-------------------------------------|-----------------------------|------------------------------------------------------------------------------------------------------------------------------|
| —                           | EXPECTED      | PO line received from feed          | System                      | PO line approved, asset-flagged                                                                                              |
| EXPECTED                    | NOTIFIED      | Vendor submits delivery notice      | Vendor                      | Notice references an open schedule line                                                                                      |
| NOTIFIED                    | RECEIVED      | Goods received, GRN posted          | Store Officer               | Quantity ≤ open quantity                                                                                                     |
| RECEIVED                    | CAPTURED      | Attributes saved                    | Store Officer               | Mandatory attributes for the asset class complete                                                                            |
| CAPTURED                    | VFM_PENDING   | Submitted to IAD                    | Store Officer               | Record locked to Store from here                                                                                             |
| VFM_PENDING                 | VFM_VERIFIED  | Sighted and verified                | IAD VfM Officer             | Evidence attached; checklist complete                                                                                        |
| VFM_VERIFIED                | VFM_APPROVED  | Value for Money approved            | IAD VfM Approver            | Approver ≠ Officer                                                                                                           |
| VFM_PENDING or VFM_VERIFIED | VFM_QUERY     | Query raised                        | IAD VfM Officer or Approver | Reason mandatory                                                                                                             |
| VFM_QUERY                   | CAPTURED      | Store corrects and resubmits        | Store Officer               | Response recorded                                                                                                            |
| VFM_PENDING or VFM_VERIFIED | VFM_REJECTED  | Rejected                            | IAD VfM Approver            | Reason mandatory; triggers reject path (Section 8)                                                                           |
| VFM_APPROVED                | TAG_REQUESTED | Tagging requested                   | Asset Controller            | Requester holds no Store role                                                                                                |
| TAG_REQUESTED               | TAG_ISSUED    | Asset code reserved, tag job issued | System                      | Code reserved in Cadra, not yet active                                                                                       |
| TAG_ISSUED                  | TAGGED        | Tag affixed and scanned             | Tagging Officer             | Guard depends on identification mode (Section 12); Serial mode: scanned serial = captured serial and payload = reserved code |
| TAGGED                      | REG_SUBMITTED | Register action (maker)             | Register Maker              | SAP material code present; asset class derived                                                                               |
| REG_SUBMITTED               | REGISTERED    | Registration approved (checker)     | Register Checker            | Checker ≠ Maker; SAP asset code linked                                                                                       |
| REG_SUBMITTED               | TAGGED        | Returned to maker                   | Register Checker            | Reason mandatory                                                                                                             |
| REGISTERED                  | ISSUED        | Issued to custodian and location    | Store Officer               | Custodian acknowledgment captured                                                                                            |

**Terminal states:** ISSUED (hand-off to lifecycle) and VFM_REJECTED. A record is a *register asset* only from REGISTERED onwards; every earlier state is a candidate, invisible to depreciation, lifecycle and reporting of the register.

4\. Roles, permissions and segregation of duties

Store can receive, capture and distribute, but never verify, tag or register; every gate after capture is held by a different role, and every maker-checker pair must be two different users.

| **Role**            | **Belongs to**                  | **Can do**                                                                                                     | **Cannot do**                                                  |
|---------------------|---------------------------------|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| Vendor              | Supplier                        | View own scheduled deliveries; submit delivery notice                                                          | See any internal record                                        |
| Store Officer       | Store                           | Receive against schedule; post GRN; capture attributes; submit to IAD; answer queries; issue registered assets | Edit after submission; verify, tag, register; push to register |
| IAD VfM Officer     | IAD                             | Sight and verify; attach evidence; raise query                                                                 | Approve own verification; edit Store's captured data           |
| IAD VfM Approver    | IAD                             | Approve; raise query; reject                                                                                   | Verify and approve the same record                             |
| Asset Controller    | Configurable (Asset/Admin unit) | Request tagging for VfM-approved candidates; maintain class-to-mode mapping                                    | Tag or register                                                |
| Tagging Officer     | Audit Tagging Team              | Print, affix and scan tags; record tag exceptions                                                              | Change captured attributes; register                           |
| Register Maker      | Asset register unit             | Run the Register action; confirm classification and SAP codes                                                  | Approve own submission                                         |
| Register Checker    | Asset register unit             | Approve or return registration                                                                                 | Make and check the same record                                 |
| Procurement Officer | Procurement                     | Resolve unscheduled deliveries and quantity exceptions                                                         | Receive goods                                                  |
| Auditor (read-only) | IAD / Value for Money           | View all records, evidence and audit trail at any state                                                        | Change anything                                                |

**Enforcement rules**

1.  A user may hold several roles, but the system blocks the same user from firing two different gates on the same record (receipt, VfM verify, VfM approve, tag request, tagging, register make, register check).

2.  A configurable role-exclusion table blocks incompatible role combinations at assignment time. Default exclusions: Store Officer with any IAD, Tagging or Register role; Register Maker with Register Checker.

3.  Delegation (leave cover) is allowed only to a user holding the same role, is time-bound, and is logged.

4.  Every block raises a clear message naming the conflicting earlier action, not a generic permission error.

5\. Functional requirements

The requirements are numbered AD-01 to AD-30 by stage, with AD-31 to AD-37 in Section 12. Each acceptance criterion is a test the build must pass.

Stage 0 — Expected receipt

- **AD-01** On ingestion of an approved PO from the SAP feed (or Vendra PO), create one delivery schedule line per PO line, status EXPECTED, visible in the Store receiving queue. *Accept:* a new approved PO appears in the queue with PO number, vendor, item, quantity and expected date, without manual entry.

- **AD-02** Flag each schedule line as *asset* or *stock* from the SAP material code (Section 9). Only asset lines enter this process; stock lines follow the existing inventory receipt. *Accept:* a line with an unmapped material code is held as *classification pending* and listed for the Asset Controller.

Stage 1 — Vendor delivery notice

- **AD-03** The vendor submits a delivery notice through the Vendra vendor portal or link (email or WhatsApp), choosing open schedule lines, quantities and delivery date. *Accept:* Store is notified and the line moves to NOTIFIED.

- **AD-04** A notice cannot exceed the open quantity on a line. Partial notices are allowed. *Accept:* over-quantity is rejected with the open balance shown.

Stage 2 — Receipt

- **AD-05** Store can receive only against a NOTIFIED schedule line. *Accept:* there is no receive action on goods without a notice; such goods follow the unscheduled-delivery path (Section 8).

- **AD-06** Receipt posts a GRN with received quantity, condition on arrival, receiving officer and timestamp, and splits serialised lines into one candidate per unit. *Accept:* receiving 5 laptops creates 5 candidates, each RECEIVED.

- **AD-07** After receipt, Store has no action other than Capture and Submit. *Accept:* register, tag and approve controls are absent for Store users.

Stage 3 — Capture

- **AD-08** Store captures serial number, make, model and the class-specific attributes defined per asset class (for example chassis and engine number for vehicles). *Accept:* submit is disabled until the class's mandatory fields are complete.

- **AD-09** Serial numbers are unique across the register and all open candidates. *Accept:* a duplicate serial is blocked and the existing record is named.

- **AD-10** Store may attach photos of the item and its serial plate. Capture is saved as draft until submitted.

- **AD-11** On submission the candidate moves to VFM_PENDING, is locked to Store, and is not pushed to the register. *Accept:* no register entry exists for a candidate in any state before REGISTERED.

Stage 4 — Value-for-Money validation (IAD)

- **AD-12** IAD is notified on submission and sees a review screen: PO line (specification, unit price, quantity), GRN, Store's captured data and photos side by side.

- **AD-13** The VfM Officer records a sighting and checklist (quantity matches, specification matches, condition acceptable, price consistent with PO) and attaches evidence. *Accept:* verification cannot be saved without at least one evidence item and a completed checklist.

- **AD-14** The VfM Approver approves, queries or rejects. Approver and Officer must differ. *Accept:* the same user cannot both verify and approve.

- **AD-15** A query returns the candidate to Store with a mandatory reason. Store responds and resubmits. The query, the response and every version of the captured data are retained.

- **AD-16** IAD may approve in bulk across candidates from the same GRN line, but evidence and checklist are recorded per GRN line.

Stage 5 — Tagging request

- **AD-17** The Asset Controller sees VfM-approved candidates and requests tagging, singly or in bulk. *Accept:* the request is unavailable to users holding a Store role.

- **AD-18** On request, Cadra reserves an asset code per candidate (status reserved, not active), generates the barcode and QR payload equal to the asset code, and issues a tag job to the Audit Tagging Team with item location in Store. *Accept:* a reserved code is never reused, including after a rejected registration.

Stage 6 — Tagging

- **AD-19** The Tagging Officer prints the variable data on the pre-printed label stock and affixes the tag. The officer then scans the tag and the item's serial (or enters the serial if it cannot be scanned). *Accept:* the candidate moves to TAGGED only when the scanned serial equals the captured serial and the scanned payload equals the reserved code.

- **AD-20** Where a tag carries an RFID inlay, the RFID tag ID is captured in the same scan and bound to the asset code.

- **AD-21** A mismatch, damaged tag or reprint is recorded as a tag exception. A reprint voids the earlier physical tag and records the reason.

Stage 7 — Registration (maker-checker)

- **AD-22** A **Register asset** action is available only on TAGGED candidates, to the Register Maker.

- **AD-23** The maker confirms the asset class, which is derived automatically from the SAP material code and can be changed only with a reason. The maker also confirms cost (from the PO or invoice), location, cost centre and capitalisation date. The SAP asset code is requested or entered at this point (Section 9).

- **AD-24** The Register Checker approves or returns. Checker and maker must differ, and approval is blocked until the SAP asset code is linked. *Accept:* on approval the reserved code becomes active and the record becomes a register asset with depreciation scheduled from the capitalisation date.

- **AD-25** On approval, the complete record is sent to SAP: asset code, SAP asset code, serial, make, model, class, cost and location.

Stage 8 — Distribution

- **AD-26** Store can issue only REGISTERED assets. *Accept:* the issue action is absent for any earlier state.

- **AD-27** An issue records custodian, location (building, floor, room), date and the custodian's acknowledgment (in-app or by signature). *Accept:* the asset moves to ISSUED and hands off to the lifecycle module.

Cross-cutting

- **AD-28** Every user has a work queue per role showing items awaiting their action, with age and SLA status.

- **AD-29** Dashboard counts by state, by age and by gate, filterable by PO, vendor and asset class, are visible to Store, IAD, the Asset Controller and auditors.

- **AD-30** All gates can act on a single unit or in bulk across a GRN line. Bulk actions are recorded per unit.

6\. Data model

The process needs nine core entities. The asset candidate is the spine: one record per unit, carrying the status from Section 3 and linking every gate's record. Section 12 adds two pool entities.

| **Entity**        | **Owned by** | **Key fields**                                                                                                                                                                                     | **Relationships**                    |
|-------------------|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------|
| DeliverySchedule  | Vendra       | schedule_id, po_number, po_line, vendor_id, sap_material_code, description, ordered_qty, open_qty, expected_date, line_type (asset/stock), status                                                  | 1 PO line → 1 schedule line          |
| DeliveryNotice    | Vendra       | notice_id, vendor_id, schedule_lines\[\] with qty, delivery_date, contact, submitted_at                                                                                                            | n per schedule line                  |
| GoodsReceipt      | Vendra       | grn_number, schedule_id, notice_id, received_qty, condition, received_by, received_at, sap_grn_ref                                                                                                 | 1 notice → 1..n GRNs                 |
| AssetCandidate    | Cadra        | candidate_id, grn_number, po_line, identification_mode, serial_no (nullable), make, model, class_attributes (JSON per class), photos\[\], status, version                                          | 1 GRN line → n candidates            |
| VfmReview         | Cadra        | review_id, candidate_ids\[\], checklist (JSON), evidence\[\], verified_by, verified_at, approved_by, approved_at, outcome (approved/query/rejected), reason                                        | 1..n per candidate (one per round)   |
| TaggingRequest    | Cadra        | request_id, candidate_ids\[\], requested_by, requested_at, store_location                                                                                                                          | 1 per batch                          |
| TagBinding        | Cadra        | asset_code, candidate_id, barcode_payload, qr_payload, rfid_tag_id, scanned_serial (nullable), tag_photo, room_id, tagged_by, tagged_at, reprint_count, void_reason                                | 1 per candidate (reprints versioned) |
| AssetRegistration | Cadra        | asset_code, candidate_id, sap_material_code, asset_class, class_override_reason, cost, cost_centre, location_id, capitalisation_date, sap_asset_code, maker, made_at, checker, checked_at, outcome | 1 per candidate                      |
| AssetIssue        | Cadra        | issue_id, asset_code, custodian_id, location_id, issued_by, issued_at, acknowledgment (type, ref, at)                                                                                              | 1..n per asset over its life         |

**Supporting tables:** MaterialClassMap (SAP material code or material group → Cadra asset class, active flag), ClassAttributeSchema (mandatory fields and identification mode per asset class), RoleExclusion (Section 4), SlaConfig (Section 7), AuditEvent (Section 10).

**Rules:** serial_no, where present, is unique across all non-rejected candidates and register assets. asset_code is never reused once reserved. Candidate edits create a new version rather than overwriting.

7\. Notifications and SLAs

Every state change notifies the next role in-app and by email, and every waiting state runs an SLA clock that escalates when breached. The SLA durations are configuration values for NRS to set; none are hard-coded.

| **Event**                 | **Notify**                                   | **Channel**                              | **SLA clock starts** | **Escalate to on breach**       |
|---------------------------|----------------------------------------------|------------------------------------------|----------------------|---------------------------------|
| PO line scheduled         | Vendor; Store                                | Email, WhatsApp (vendor); in-app (Store) | —                    | —                               |
| Delivery notice submitted | Store                                        | In-app, email                            | Expected date        | Store Supervisor                |
| Submitted to IAD          | IAD VfM Officers                             | In-app, email                            | Submission           | IAD Head                        |
| VfM query raised          | Store Officer who captured                   | In-app, email                            | Query                | Store Supervisor                |
| VfM approved              | Asset Controller                             | In-app, email                            | Approval             | Asset Controller's line manager |
| Tag job issued            | Audit Tagging Team                           | In-app, email                            | Request              | Tagging Team Lead               |
| Tagged                    | Register Makers                              | In-app                                   | Tagging              | Asset register lead             |
| Registration submitted    | Register Checkers                            | In-app                                   | Submission           | Asset register lead             |
| Registered                | Store; requesting unit                       | In-app, email                            | Registration         | Store Supervisor                |
| VfM rejected              | Store; Procurement; vendor (via Procurement) | In-app, email                            | Rejection            | Procurement Head                |

**Rules:** SLA durations are set per gate in SlaConfig and may differ by asset class. Clocks pause while a record sits in a query state awaiting the other party, and the pause is shown. A daily digest per role lists items due and breached. Escalation recipients are configurable roles, not named users.

8\. Exceptions and alternate paths

Every exception keeps the item out of the register and leaves a reason on record. None of them lets Store bypass a gate.

| **Exception**                               | **Detected at**           | **Handling**                                                                                                                                                                                                                    |
|---------------------------------------------|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Vendor arrives with no delivery notice      | Receipt                   | Store logs an *unscheduled arrival* (vendor, PO if quoted, items) without receiving. Procurement links it to a schedule line or rejects it, and once linked the vendor or Procurement raises the notice.                        |
| No PO exists                                | Receipt                   | Logged as unscheduled. Procurement resolves outside this process, so no receipt is possible.                                                                                                                                    |
| Partial delivery                            | Notice / receipt          | Allowed. The open quantity stays on the schedule line and each delivery creates its own GRN and candidates.                                                                                                                     |
| Over-delivery                               | Receipt                   | Store receives only up to the open quantity. The excess is logged and returned.                                                                                                                                                 |
| Damaged on arrival                          | Receipt                   | Store records condition. Goods are received with condition *damaged* and flagged for IAD, or refused at the door with a note to Procurement.                                                                                    |
| VfM query                                   | IAD                       | Returns to Store (CAPTURED) with a reason. Data is versioned and the SLA clock pauses (Section 7).                                                                                                                              |
| VfM rejection                               | IAD                       | The candidate is VFM_REJECTED. The system raises a GRN reversal request in Vendra and notifies Procurement, which arranges the vendor return and a debit note. If the invoice is already paid, Finance is flagged for recovery. |
| Serial on item ≠ captured serial            | Tagging                   | The tag is not bound, and the candidate returns to IAD with a tag exception for re-verification.                                                                                                                                |
| Tag count short of GRN quantity             | Tagging (Tag-ID mode)     | The line stays at TAG_ISSUED. The shortfall is either found and tagged, or returned to IAD for re-count.                                                                                                                        |
| Tag damaged, misprinted or lost             | Tagging / later           | A reprint is issued under the same asset code. The old physical tag is voided and the reprint count incremented.                                                                                                                |
| Unmapped SAP material code                  | Scheduling / registration | Held as *classification pending*. The Asset Controller maps the code before the register maker can proceed.                                                                                                                     |
| SAP asset code not available                | Registration              | Checker approval stays blocked. The record shows *awaiting SAP asset code* with the SLA running.                                                                                                                                |
| Bundled items (e.g. laptop + charger + bag) | Capture                   | Captured as one candidate with accessories listed as attributes, unless the asset class is set to split components. The rule is configured per class.                                                                           |
| Registration returned by checker            | Registration              | Back to TAGGED with a reason, and the maker corrects and resubmits. The reserved code is retained.                                                                                                                              |
| Candidate cancelled after tagging           | Any post-tag state        | Asset code is voided (never reused) and the tag recovered and destroyed, with the reason logged.                                                                                                                                |

9\. Integration points

This addendum touches six interfaces. One existing push is retired, one changes, and four are new or extended.

| **\#** | **From → To**  | **Payload**                                                                                                                | **When**                           | **Change**                                                                  |
|--------|----------------|----------------------------------------------------------------------------------------------------------------------------|------------------------------------|-----------------------------------------------------------------------------|
| A1     | SAP → Vendra   | Approved PO header and lines, including material code                                                                      | On PO approval (or scheduled pull) | Extended: now creates delivery schedule lines                               |
| A2     | Vendra → Cadra | Asset candidates with GRN reference and captured attributes                                                                | On Store's submit to IAD           | New. Replaces the push-on-three-way-match, which is retired for asset lines |
| A3     | Cadra → Vendra | GRN reversal request with reason                                                                                           | On VfM rejection                   | New                                                                         |
| A4     | SAP → Cadra    | Material master: material code, material group, description                                                                | Daily sync, plus on-demand lookup  | New: feeds MaterialClassMap for classification                              |
| A5     | Cadra ↔ SAP    | Request or receive the SAP asset code for a candidate at registration                                                      | At the Register maker step         | New. Mode depends on Decision D2 (Section 11)                               |
| A6     | Cadra → SAP    | Registered asset: asset code, SAP asset code, serial, make, model, class, cost, cost centre, location, capitalisation date | On checker approval                | Changed: fires at registration, no longer at match                          |

**Classification rule.** Asset class = MaterialClassMap lookup on the SAP material code, falling back to the material group. The derived class pre-fills at registration. Overriding it needs a reason and is shown to the checker.

**Inventory.** The GRN still posts the goods receipt to SAP inventory as today. This addendum does not change the inventory receipt. It only delays the asset register entry.

**Idempotency.** A2 and A6 carry the candidate_id or asset_code as an idempotency key, so retries never create duplicates.

10\. Audit trail and evidence

Every transition writes an append-only audit event. From any register asset, an auditor can reconstruct who did what, when, and on what evidence, back to the PO line.

- **AuditEvent fields:** event_id, entity, record_id, from_state, to_state, action, user_id, role, timestamp (server time), reason or comment, before and after values for edited fields, evidence references, client (web, mobile, scanner).

- **Append-only:** events cannot be edited or deleted by any role, including administrators. Corrections are new events.

- **Evidence pack:** for each register asset, a one-click export (PDF plus attachments) holds the PO line, delivery notice, GRN, captured data with all versions, VfM checklist and evidence, tag binding scan and photos, registration maker and checker, and SAP confirmations. This feeds the evidence pack in Section 8 of the v0.5 process document.

- **Read-only audit access:** the Auditor role sees all of the above at any state, including candidates and rejected records.

- **Access log:** views of evidence and exports are logged with user and time.

11\. Build defaults and open decisions

Build with the defaults below, each behind a configuration flag, so that NRS's answers change settings rather than code. Decisions D10 to D12 on items without serial numbers are in Section 12.

| **\#** | **Decision**                                                                  | **Build default**                                                                       | **Configurable as**                                         |
|--------|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-------------------------------------------------------------|
| D1     | When is the asset code created, given the tag carries it before registration? | Reserved at tagging request, made active at registration approval, and never reused     | Fixed                                                       |
| D2     | How is the SAP asset code obtained at registration?                           | The maker enters it or pulls it via A5. Checker approval is blocked until it is present | Mode: manual entry / API request / back-fill after approval |
| D3     | Which role requests tagging?                                                  | Asset Controller in a non-Store unit                                                    | Role mapping                                                |
| D4     | Does vendor payment wait for VfM approval?                                    | No hold, and the rejection path flags paid invoices for recovery                        | Flag: hold payment until VFM_APPROVED                       |
| D5     | Which date is the capitalisation date?                                        | The maker sets it; it pre-fills with the VfM approval date                              | Source: GRN / VfM approval / tag date / registration date   |
| D6     | Do all asset classes go through VfM?                                          | Yes                                                                                     | Value threshold and class exemptions                        |
| D7     | Can Store distribute before registration?                                     | No                                                                                      | Fixed                                                       |
| D8     | Are bundled items one asset or several?                                       | One asset with accessories, per class                                                   | Per-class split rule                                        |
| D9     | What are the SLA durations per gate?                                          | To be set by NRS; the build ships the clock and escalation only                         | SlaConfig                                                   |

**For NRS confirmation:** D2, D4, D5, D6 and D9 need an answer before go-live. D1, D3, D7 and D8 can be signed off at the next validation session.

12\. Items without serial numbers

Where there is no manufacturer serial, the system-generated asset code becomes the item's identity, created at tagging. The tagging control shifts from serial matching to count matching plus a photo of each tag on its item. Each asset class carries an **identification mode** that selects the rules below.

| **Mode** | **Use for**                                                                                                 | **Identity**                                                 | **Tagging check**                                        | **Tracked as**        |
|----------|-------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------|----------------------------------------------------------|-----------------------|
| Serial   | Laptops, vehicles, generators, phones                                                                       | Manufacturer serial (chassis and engine number for vehicles) | Scanned serial = captured serial                         | One asset per unit    |
| Tag-ID   | Furniture and fittings above the threshold: desks, conference tables, cabinets, office chairs where tracked | The asset code                                               | Tags bound = GRN quantity; photo of each tag on its item | One asset per unit    |
| Pool     | Low-value, high-volume items below the threshold: stackable chairs, small fittings                          | One record per lot per location                              | Room or zone label; counted quantity = GRN quantity      | Quantity per location |

Requirements

- **AD-31** Each asset class has an identification_mode (Serial, Tag-ID or Pool), set by the Asset Controller. A schedule line inherits the mode from the class derived from its SAP material code. *Accept:* changing a class's mode affects only new schedule lines.

- **AD-32 Tag-ID capture.** Store captures description, make or brand, model or catalogue reference, colour, material and dimensions once per GRN line, and every unit on the line inherits them. AD-08 and AD-09 serial rules do not apply. *Accept:* submit is enabled without a serial for Tag-ID lines.

- **AD-33 Tag-ID VfM.** IAD sights and counts the line against the PO quantity and specification. Approval is per GRN line, with evidence.

- **AD-34 Tag-ID tagging.** For each unit, the Tagging Officer affixes and scans the tag, takes a photo showing the tag on the item, and records the room. A distinguishing-features note is optional. *Accept:* binding is blocked once bound tags equal GRN quantity, and the line moves to TAGGED only when every unit is bound with a photo.

- **AD-35 Pool records.** A Pool line creates one asset record per receiving location holding quantity, unit cost and total cost. The room or zone barcode serves as the tag, and an optional pool label may be fixed at the storage point. *Accept:* registration (stage 7) is per pool record, not per unit.

- **AD-36 Pool movements.** Distribution and later moves are quantity transfers between locations, each with from-location, to-location, quantity, user and date. *Accept:* a transfer cannot exceed the quantity at the source location.

- **AD-37 Count verification.** Scanning a room barcode lists every Tag-ID asset and pool quantity expected there. The auditor records found, missing and unexpected items, and pool count variances. *Accept:* variances raise an exception with a mandatory explanation.

State machine and data model changes

- **TAG_ISSUED → TAGGED guard by mode:** Serial = scanned serial matches. Tag-ID = all units bound with photo and room. Pool = counted quantity at the location equals GRN quantity.

- **AssetCandidate:** add identification_mode. serial_no becomes nullable and is mandatory only in Serial mode.

- **TagBinding:** add tag_photo and room_id. scanned_serial becomes nullable.

- **New entity PoolHolding:** pool_id, asset_code, location_id, quantity, unit_cost.

- **New entity PoolTransfer:** transfer_id, pool_id, from_location, to_location, quantity, user_id, at.

Decisions for NRS

| **\#** | **Decision**                                                   | **Build default**                                                                | **Configurable as**                        |
|--------|----------------------------------------------------------------|----------------------------------------------------------------------------------|--------------------------------------------|
| D10    | What value threshold separates Tag-ID from Pool?               | None set; mode chosen per class                                                  | Threshold per class, or class mapping only |
| D11    | Which classes default to which mode?                           | Electronics and vehicles = Serial; furniture = Tag-ID; no class defaults to Pool | Class-to-mode table                        |
| D12    | Are pooled items capitalised or kept on a memorandum register? | Capitalised as a pool                                                            | Flag per class                             |
