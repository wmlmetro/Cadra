# Handoff 57 — demo run sheet: a received unit becomes an asset

**Before the room — the owner, two things:**

1. **Eight people sign in during this run, and you have four Chrome
   profiles.** Make the other four before the room: one profile per person
   below, each signed in once at `https://staging.app.cadra.ng/app/` so the
   first click in front of NRS is not a login. Name each profile after the
   person and their job (e.g. *Kelechi — IAD Approver*). The passwords are in
   `docs/api/.personas.cluster.staging` on your machine, never in the repo.
2. **Receipt gates are on for `staging` only.** Every other tenant — the live
   Jaiz and LASG sites included — behaves exactly as it did yesterday.

**What this is, said once so nobody overclaims it in the room.** Tonight's
build is scaffolding: the gates ride on the existing asset record, and a unit
that has not passed them is hidden from the register. The real build (a
separate *asset candidate* record, Addendum A as written) is handoff 58, about
a week. Everything below is real — real records, real refusals, a real SAP
message — and none of it is a mock-up.

## The eight people

| # | Person | Job | Role in Cadra | Their step |
|---|---|---|---|---|
| 1 | Halima Danjuma | Store Officer | Asset Officer | receives the unit, submits it to IAD |
| 2 | Folasade Ogunbiyi | IAD Value-for-Money Officer | IAD VfM Officer | sights it, verifies with checklist and evidence |
| 3 | Kelechi Ihenacho | IAD Value-for-Money Approver | IAD VfM Approver | approves the verification |
| 4 | Hauwa Dikko | Asset Controller | Asset Controller | requests tagging — the label is minted |
| 5 | Babatunde Olaniyan | Tagging Officer | Asset User + Tag-Issuing Unit | prints and affixes the label |
| 6 | Temitope Oyelaran | Register Maker | Register Maker | submits for registration with SAP code and cost |
| 7 | Obinna Ezeagu | Register Checker | Register Checker | approves — the asset is on the register |
| 8 | Oluwaseun Ajayi | Systems Administrator | Administrator | the register count before and after; the two-gates rule |

All eight are invented, on the reserved `@demo.example` domain, and checked
against the staff roll (no employee or contact carries any of these names).
Chukwudi Anyanwu (Asset Manager) and Zainab Garba (Internal Auditor) keep
their jobs and are not needed for the chain.

## Have ready

* One physical item with a **serial number on it** (a laptop or monitor is
  ideal), and the printer the Barcode Station uses, with label stock.
* The PO number and GRN number you will quote (any realistic pair).
* A photo on the IAD officer's machine to attach as evidence (a picture of
  the item works).
* An SAP asset code to type at step 6 — **a code not already on any asset**
  (the server refuses a duplicate, in words). Suggest `NRS-DEMO-0001`, then
  `-0002` on a rehearsal.

## The run

Each step: **who** (Chrome profile) · **where** · **what to click** · **what
the screen says**. The screen's words are quoted as they appear.

### 0 · The register before — Oluwaseun (Administrator)

1. **Asset Register → All Assets.** Read the total out loud. Write it down:
   ______. *This number does not move until step 7.*
2. **Settings → Receipt gates.** Tonight it says *off*: click the switch once to turn it on (do this at the rehearsal, not in the room). From then on it shows *Gate received units — on*, with the
   sentence: *"On: a unit received from a goods receipt is a candidate, not
   an asset. It joins the register only after Internal Audit has verified and
   approved it, a tag has been affixed, and a Register Maker and a different
   Register Checker have registered it…"* — and who switched it on, and when.

### 1 · Receipt — Halima (Store Officer)

1. **Asset Register → + New Asset** (`/assets/new`). Enter the item: name,
   category, **serial number from the physical label**, PO and GRN numbers,
   location. Save.
   *(If Vendra is posting to staging, the GRN in Vendra creates this record
   instead — INT-03 is unchanged; skip to 1.2.)*
2. Save opens the asset page, with an amber banner across the top: **"Not
   on the register — this is a received unit still passing its gates."** and
   under it **"Captured — received, not yet submitted to IAD · waiting on
   Store"**. The *Asset Tag* row reads **"Not issued yet"** — tonight the tag
   is minted at step 4, not at receipt.
3. Click **Submit to IAD**, confirm. Banner: **"Awaiting IAD verification"**.
4. **Asset Register → All Assets**: the unit is **not** there, and the total
   is unchanged. **Candidates** lists it.

### 2 · Verification — Folasade (IAD Officer)

1. **Asset Register → Candidates.** It opens filtered to *waiting on IAD
   officer*. Open the unit.
2. Click **Verify (value for money)**. The dialog says: *"Records that you
   have sighted this unit against the order. All four checks and at least
   one piece of evidence are required."*
3. Tick **Quantity matches the order**, **Specification matches the order**,
   **Condition is acceptable**, **Price matches the order**; attach the photo.
   *(Try Verify with a box unticked first if you want the room to see it
   refused.)*
4. Confirm. Banner: **"Verified — awaiting IAD approval"**.

### 3 · Approval — Kelechi (IAD Approver)

1. **Candidates** (opens on *waiting on IAD approver*) → the unit.
2. Click **Approve (value for money)**: *"Approves the verification. You
   cannot approve a unit you verified or received yourself."* Confirm.
3. Banner: **"IAD approved — awaiting a tag request"**.

### 4 · Tag request — Hauwa (Asset Controller)

1. **Candidates** (opens on *waiting on Asset Controller*) → the unit.
2. Click **Request tagging**: *"Asks the Tag-Issuing Unit for a label. The
   label is minted now and can then be printed and affixed at the Barcode
   Station."* Confirm.
3. Banner: **"Tag issued — awaiting the label on the asset · waiting on
   Tagging"**, with a link to the Barcode Station. The *Asset Tag* row now
   shows the tag number.

### 5 · Tagging — Babatunde (Tagging Officer)

1. **Tools → Barcode Station.** Find the unit (scan or type its asset code),
   **Print** the label, stick it on the item.
2. **Confirm affixed** — the dialog the room saw on 6 October: scan the
   **label you just stuck on** and the **serial off the item**. It does not
   tell you the expected numbers; it checks them.
3. The card shows the affixed state. The unit is **"Tagged — awaiting
   submission to the register"**.
4. **SAP has received nothing yet.** (Yesterday, affixing sent the asset
   master. With the gates on, it waits for step 7 — step 8.3 shows the
   outbox to prove it.)

### 6 · Registration — Temitope (Register Maker)

1. **Candidates** (opens on *waiting on Register Maker*) → the unit.
2. Click **Submit to register**: *"Submits this tagged unit to the register
   with its SAP asset code and cost. A different person approves it."*
3. Type the **SAP asset code**, the **Cost (₦)**, the **Cost centre**, the
   **Capitalisation date**; confirm the **Asset class**. Confirm.
4. Banner: **"Submitted — awaiting register approval"**.

### 7 · Approval — Obinna (Register Checker)

1. **Candidates** (opens on *waiting on Register Checker*) → the unit.
2. Click **Approve registration**: *"Puts this unit on the register and sends
   its asset master to SAP. You cannot approve a submission you made."*
   Confirm.
3. The amber banner is gone: the unit is **on the register** and shows the
   register's own status steps, like every other asset.

### 8 · The register after — Oluwaseun (Administrator)

1. **Asset Register → All Assets.** The total is **one more** than at step 0.
   The unit is in the list.
2. Open the unit → **History.** Every gate, in order, each a *Receipt gate*
   line with the person who fired it and when: received (Halima), verified
   (Folasade), approved (Kelechi), tagging requested (Hauwa), tagged
   (Babatunde), submitted (Temitope), registered (Obinna).
3. **The SAP message.** The app does not show the outbox; the back office
   does, and only to an administrator. In Oluwaseun's profile open
   `https://staging.app.cadra.ng/odoo` → **Workflow → Dispatch Log**, newest
   first: the *asset master* message for this unit, timed **after** Obinna's
   approval at step 7 — and nothing for it at step 5, when the label went on.

### 9 · The rule — nobody passes a unit through two gates (optional, 2 min)

Oluwaseun is an administrator: his role earns every gate button. On a
**second** unit, captured and submitted by Halima as in step 1:

1. Oluwaseun clicks **Verify (value for money)** and completes it.
2. Where **Approve** would be, the page now says, in words: **"You verified
   this unit on 8 Oct; a different person must approve it."** — not
   "permission denied". The same sentence form refuses a Register Maker
   approving their own submission.

## If something goes wrong in the room

* **A button you expected is not there:** the person signed in does not hold
  that gate, or has already fired a different one on this unit — the page
  says which, in a sentence where the button would be. Check the Chrome
  profile.
* **"SAP asset code … is already on another asset":** type a new code.
* **The unit is not in All Assets:** that is the point until step 7. It is
  under **Candidates**.
