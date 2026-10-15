# Addendum A against what we have — Architect's evaluation, 7 October 2026

**Source:** `docs/reference/addendum-a-verification-gated-receipt.md` (WestMetro,
7 October 2026, from the NRS validation session of the same day). It
supersedes the direct Vendra → Cadra push: a received unit is no longer an
asset; it is an *asset candidate* that passes four gates and becomes a
register asset only when a second person approves its registration.

This file says what the addendum keeps, what it replaces, where it
contradicts something we have built or told NRS, and how to sequence the
build. It is the record the handoffs for this work package cite.

---

## 1 · In one paragraph

Today: Store posts a goods receipt with serials; INT-03 creates one
`nrs.asset` per unit at once; the Tag-Issuing Unit prints and affixes a
label; INT-06 sends the asset master to SAP when the label is affixed.
Tomorrow: Store receives against a delivery schedule and a vendor's delivery
notice, captures attributes, and **submits to Internal Audit (IAD)**; IAD
sights the item, attaches evidence and approves (two IAD people); an **Asset
Controller** requests tagging, which **reserves** an asset code; the tagging
team affixes and scans (serial + code, as today); a **Register Maker**
proposes registration with SAP codes and cost; a **Register Checker**
approves — and only then is there a register asset, and only then does SAP
receive the asset master. Store can issue the asset to a custodian only
after that.

---

## 2 · What we already have that the addendum keeps

| Addendum | What we have | Fit |
|---|---|---|
| A1: approved PO from SAP creates schedule lines | INT-01 receives/pulls POs (Vendra) | **Extend** — add DeliverySchedule per PO line (AD-01), asset/stock flag from material code (AD-02) |
| AD-06 one candidate per serialised unit | GRN splits into `Vendra Receipt Serial` rows per unit | **Keep** — the unit row becomes the candidate's Vendra half |
| AD-08/09 serial, make, model, class attributes; serial unique | Handoff 3's capture gate; serial uniqueness across register | **Keep**; add per-class attribute schema |
| AD-19 tagging check: scanned serial = captured serial AND payload = reserved code | Handoffs 39/52/54: affix dialog takes serial + label, server checks both, refusals recorded with symbology | **Exact match** — the strongest thing we built is the addendum's own control |
| AD-21 tag exceptions, reprints void the old tag | Handoff 38 tag replacement with approver; refused-affix record | **Mostly** — add "reprint under the same code" (today replacement mints a new number: see §4.3) |
| Maker ≠ checker, approver ≠ officer | Approvals: nobody approves their own; `_may_decide` | **Pattern exists**; generalise to "no user fires two gates on one record" (§4) |
| Section 10 append-only audit, corrections are new events | `nrs.asset.event` append-only mixin; access record; configuration record | **Keep** — add candidate transitions as events |
| Auditor sees everything, changes nothing | Auditor role and screens (handoff 49) | **Keep** |
| Inventory GRN still posts to SAP (INT-02) | INT-02 outbox, harness, dev endpoint received 5 Oct | **Unchanged** |
| Section 12 Tag-ID / Pool modes | Nothing — this was the hundred-chairs question we asked NRS | **New, and it is their answer** |

---

## 3 · What it replaces

| Today | Addendum | Size |
|---|---|---|
| INT-03 creates `nrs.asset` at GRN submit | **A2**: candidates created in Cadra on Store's *submit to IAD*; no asset until REGISTERED | **Large** — new `AssetCandidate` spine with a 17-state machine; `nrs.asset` is created (or activated) at the checker's approval |
| Tag number minted at asset creation (`asset_code` + location-built `asset_tag`) | **AD-18/D1**: asset code **reserved** at tagging request, active at registration, never reused; barcode/QR payload = the asset code | **Large** — the label binds to a candidate before any asset exists; see §4.3 on which identifier the tag carries |
| INT-06 asset master to SAP at affix | **A6** at registration approval, carrying SAP asset code, cost, cost centre, capitalisation date | **Medium** — move the trigger, widen the payload |
| INT-07 SAP asset number returned | **A5** request/receive SAP asset code at the maker step; mode D2 open | **Medium** |
| Six roles | **Ten roles** incl. IAD VfM Officer/Approver, Asset Controller, Register Maker/Checker, Vendor; role-exclusion table at assignment; per-record gate conflict | **Medium** — our access guard and `_may_decide` are the seeds |
| No notifications (meeting 30 Sept §3.3) | **Section 7**: in-app + email on every transition, SLA clocks, escalation, daily digest; WhatsApp to vendors | **Large** — none of it exists |
| Nothing | **AD-03/04** vendor delivery notice via portal or link; **AD-05** receive only against a notice | **Large** — a new external surface |
| Nothing | **AD-12–16** VfM review screen, checklist, evidence, bulk per GRN line, query/reject | **Large** |
| Nothing | **A3** GRN reversal request Vendra ← Cadra on rejection | **Medium** |
| Nothing | **A4** SAP material master sync → MaterialClassMap | **Medium** |
| Nothing | **AD-26/27** issue with custodian acknowledgment (in-app or signature) | **Medium** — custody exists; acknowledgment does not |
| Nothing | **AD-28/29** per-role work queues with age and SLA; dashboards by state/age/gate | **Medium** — the "whose desk" line (Vendra 52 §1) is the seed |
| Named out of scope on 30 Sept | **Section 10** evidence pack export per asset | **Medium** |
| Nothing | **AD-35/36** Pool holdings and quantity transfers | **Medium** |
| Nothing | **AD-20** RFID tag ID captured in the same scan | **Hardware-dependent** — a camera cannot read RFID; build the field, require a reader |

---

## 4 · Contradictions and decisions — read before building anything

### 4.1 The serial gate moves, and the control we demonstrated yesterday weakens

Today **no serial, no goods receipt** — the refusal we showed NRS as "the
product". The addendum posts the GRN at RECEIVED (AD-06) and captures
serials afterwards (AD-08), so a GRN — and its INT-02 posting to SAP
inventory — can exist with no serials. The gate becomes *cannot submit to
IAD without attributes* (AD-11).

**Recommendation:** keep receipt and capture on one screen so RECEIVED and
CAPTURED are seconds apart, and keep the existing refusal on *posting* for
Serial-mode lines unless NRS explicitly wants GRNs without serials.
Tag-ID and Pool lines have no serial and are the reason the addendum
separates the steps. **Decision for the owner/NRS** before Phase A: does a
Serial-mode GRN post without serials?

### 4.2 Who owns depreciation

AD-24: on approval "depreciation [is] scheduled from the capitalisation
date". We told NRS yesterday that SAP owns depreciation and we do not touch
it. Our depreciation module can hold a schedule for reporting, but **which
figure is authoritative must be decided and written down** before AD-24 is
built as stated. Recommendation: Cadra schedules for reporting only, labelled
as such; SAP's figure is the book.

### 4.3 One identifier or two

We have `asset_code` (`NRS-AST-000150`, sequential) **and** `asset_tag`
(`HQ-GF-MR-FN-150`, location-built), and we pitched the second as better
than NRS asked. The addendum has **one**: the asset code, reserved at tag
request, printed as the barcode and QR payload (AD-18). Section 12 uses a
separate *room barcode* for pools.

**Decision:** does the printed label carry the asset code (addendum) or the
location-built tag (ours)? A location prefix on a label that is reserved
before the asset has a location is a contradiction in itself, so the
addendum's choice is the coherent one. Recommendation: label = asset code;
retire the location-built tag as the *printed* identifier; keep location on
the record. This touches handoffs 38, 39, 51, 52, 54, 55 and the label
template.

### 4.4 Reprint under the same code

AD-21/§8: a reprint keeps the asset code and voids the old physical tag.
Our replacement flow (handoff 38) mints a **new** number and retires the
old. The addendum's rule is simpler and is what AD-18's "never reused" needs.
Change the replacement flow to a reprint with a void reason and a count.

### 4.5 WhatsApp, vendor portal, RFID — three things outside our stack

- **WhatsApp** to vendors (Section 7) needs a Meta Business account and a
  provider — a commercial decision, not a build; email first.
- **Vendor portal** (AD-03): Vendra has Website Users already (firs_erpnext
  clients); a delivery-notice page for suppliers is feasible but is a new
  external surface and needs its own security review.
- **RFID** (AD-20): no camera reads RFID. Build the `rfid_tag_id` field;
  capture needs a reader and is a hardware line item for NRS.

### 4.6 Candidate model: separate entity, not a flag on `nrs.asset`

The addendum's data model has `AssetCandidate` separate from the register
asset and says candidates are "invisible to depreciation, lifecycle and
reporting of the register". A flag on `nrs.asset` would make every report,
count and dashboard filter on it for ever — the badge/strip class of defect
(Cadra 52/53) multiplied. **Ruling: a new `nrs.asset.candidate` model**, its
own state field, its own routes; `nrs.asset` is created at REGISTERED from
the candidate, carrying the reserved code and the tag binding. The affix
dialog and the tag label bind to the candidate from TAG_ISSUED.

### 4.7 What this does to the queued handoffs

- **Vendra 51 (the first real SAP)** — unchanged and still first; INT-02 is
  untouched by the addendum.
- **Vendra 50 (the walk)** — merge as is; the approvals chain it drove is
  "out of scope, unchanged" in the addendum.
- **Vendra 52 (whose desk)** — §1 becomes the seed of AD-28 work queues;
  §5 (reset move) and §6 (emails) stand. Re-cut after Phase A.
- **Cadra 53 (the first screen)** — stands; small.
- **Cadra 55 (the label QR)** — **hold**: §4.3 decides what the label
  carries before the template is changed.

---

## 5 · Sequencing — six phases, each a few handoffs per repo

Build so that the current flow keeps working on every tenant until a tenant
is switched to the gated flow (a per-tenant flag, like the sidebar
switches). Nothing in Phase A changes what a client tenant sees.

| Phase | Cadra | Vendra | Needs from NRS first |
|---|---|---|---|
| **A · Spine** | `nrs.asset.candidate` + state machine + audit events; roles and exclusion table; per-record gate conflict; work-queue route per role | DeliverySchedule from INT-01 (AD-01/02); receipt → capture → submit; **A2** push on submit; retire INT-03 asset creation behind the tenant flag | §4.1 (serial gate), §4.6 ruled here |
| **B · IAD** | VfM review screen, checklist, evidence, query/reject, bulk per GRN line; **A3** reversal request | Receive the reversal request; GRN reversal with reason | D6 (which classes go through VfM) |
| **C · Tagging** | Tag request by Asset Controller; **reserved** code; tag job; affix rewired to candidates; reprint-under-same-code; Tag-ID mode (AD-31–34). *Pool (AD-35–37) moved to Phase E: see `AI-CAPTURE-EVALUATION.md` R6.* | — | §4.3 (what the label carries), D10–D12 |
| **D · Register** | Maker-checker registration; MaterialClassMap + **A4** sync; **A5** SAP asset code (mode D2); **A6** at approval; `nrs.asset` created here | — | D2, D5, §4.2 |
| **E · Issue and visibility** | Issue with acknowledgment; dashboards by state/age/gate; SLA clocks + escalation + digest; evidence pack | Notifications in Vendra for Store | D9 (SLA durations), WhatsApp decision |
| **F · Vendor** | — | Delivery notice portal/link; receive only against a notice; unscheduled-arrival log | Vendor identities; WhatsApp decision |

Rough size, one Builder per repo, at the pace of the last three weeks:
**A 1 week · B 1 week · C 1.5 weeks · D 1.5 weeks · E 1.5 weeks · F 1 week.**
Phases B–D on Cadra and F on Vendra can overlap. The whole package is in the
order of **seven to eight weeks**, not counting NRS's answers.

---

## 6 · What to ask NRS now, so Phase A is not built on a guess

1. §4.1 — may a Serial-mode goods receipt post to SAP without serials, or do
   we keep the refusal?
2. §4.2 — is Cadra's depreciation schedule for reporting only?
3. §4.3 — confirm the printed label carries the asset code and nothing else.
4. D2, D5, D6, D9 (the addendum's own "before go-live" list).
5. Who the Asset Controller is, organisationally (D3), and whether the
   Audit Tagging Team is the Tag-Issuing Unit we have.
6. WhatsApp: yes or email only.
7. RFID: are tags with inlays being bought, and is a reader?

---

## 7 · Rulings — owner, 7 October 2026

The four questions in §4 were put to the owner the same day. Answers, and
what each one fixes in the build:

| § | Question | Ruling | Consequence |
|---|---|---|---|
| 4.1 | GRN without serials? | **No, for serialised items: "no serial, no receipt" stays.** For items that have no manufacturer serial (furniture), the addendum's Section 12 applies: Tag-ID and Pool modes need no serial, and their identity is the asset code or the pool. | The receipt learns the item's **identification mode** from its class. Serial mode: serials mandatory at posting, as today. Tag-ID: the per-line attributes of AD-32 mandatory, no serial. Pool: quantity per location. AD-06/AD-08's split into RECEIVED then CAPTURED is honoured as two states that a Serial-mode receipt passes through in one posting. |
| 4.2 | Who owns depreciation? | **SAP.** | Cadra's schedule is reporting-only and is labelled so on every screen that shows it; AD-24's "depreciation scheduled" means Cadra's shadow schedule starts from the capitalisation date, nothing more. Nothing Cadra computes is sent to SAP as a figure. |
| 4.3 | One identifier or two? | **One: the asset code is what the label carries.** | The location-built `asset_tag` is retired as the *printed* identifier. The code is reserved at tagging request (D1), printed as barcode and QR, active at registration, never reused. Handoff 55 (label QR sizes) is folded into Phase C. Location stays a field on the record. |
| 4.5 | WhatsApp, RFID, vendor portal | **Skip WhatsApp and RFID for now.** Vendor portal stays in Phase F. | Section 7 channels are in-app and email only. AD-20's `rfid_tag_id` field is built nullable and nothing reads a reader. |

§4.6 (candidate is a separate model) stands as the Architect's ruling.

---

## 8 · Revision — Architect, 12 October 2026

**§4.6 is reversed.** The candidate stays a state (`register_state`) on
`nrs.asset`. It does not become a separate `nrs.asset.candidate` model.

§4.6's objection was that a flag would make every report, count and
dashboard filter on it forever. Cadra's handoff 57 put that filter in one
place, `nrs.asset._search`, so new code is filtered by default. Report 57's
probe read every route that lists or counts assets, before and after a
candidate arrived, and none of the register routes moved. The failure mode
is the safe one: code that forgets the context flag can't *find* a
candidate; it can't *show* one. The seven-gate chain is built, tested
10 of 10 in the browser, deployed, and was demonstrated to NRS on 8 October.
A second model would rebuild it for one property we already have.

Consequences:

- **INT-03 is the hand-off.** Vendra keeps calling `POST /api/v1/assets`.
  With the gates on, Cadra creates the unit at `captured`. There is no
  `/candidates/ingest` route, and Vendra doesn't read the switch.
- **Store's *Submit to IAD* is in Cadra**, as it is in 57.
- **Cadra 58 is re-cut** as *The gates, kept*. The draft that built the
  separate model is in `docs/handoffs/_superseded/`.
- **Vendra 54 is re-cut** to the receipt's identification mode (Section 12)
  only. The delivery schedule (AD-01/02) moves to a later Vendra handoff.
- Phases B to F keep their scope. They act on `register_state`, not on a
  second model.
