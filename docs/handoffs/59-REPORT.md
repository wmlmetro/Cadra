# Report — Handoff 59: what SAP already holds

Branch `feat/what-sap-already-holds`, from `dev` at `002c8ae` (PR #117 merged).
Step 0: the instruction file and `docs/reference/sap-asset-master-2026-10.md`
committed on `dev` (`b1d5a0e`), pushed, then the branch. No migration was owed by the merge: report 58 had already fanned out every local tenant.

## Needs the owner

1. **The PR merge** — the Builder's permission layer refuses `gh pr merge`.
2. **The deploy** — `deploy-dev`, then `upgrade-19` on all four tenants
   (`staging, gtb, jaizbankplc, lasg`), modules
   `myservice_asset_register,myservice_api`, `scale_down=true`. Then
   `https://<tenant>/api/v1/meta/readiness` must say `"ready": true` (no
   token). Mandatory before traffic: a new column (`nrs_asset.reference`).
3. **The class-mapping conversation with NRS** — §1's table below is a
   proposal; NRS decides. Nobody should type these values into a tenant
   until NRS confirms them.
4. **The deployed check on `staging`** (Turnstile — yours, in the browser),
   after the deploy:
   1. Without signing in: `https://staging.app.cadra.ng/api/v1/meta/readiness`
      → `{"data": {"ready": true, …}}`.
   2. Sign in as the **Asset Controller** persona. **Settings → Asset
      Categories**: the table has a *SAP class* column; set one class (e.g.
      *Desktop / Laptop Computer* → `3000`) and see it saved.
   3. Same page, *Placeholder serials*: the list shows `^X+$`, `^0+$` and the
      eleven values, and *0 of 11,317 assets with a serial* (staging's
      measure).
   4. Sign in as the **Store Officer**: the SAP class column is read-only.
   5. Push one unit of that class through the seven steps as in report 58;
      at *Submit to register* the class shows its SAP class. Then clear the
      class (as the Asset Controller) on a second unit's class and see the
      maker refused with the sentence in §1.

## In plain words

On 12 October the owner received SAP's own list of every asset NRS owns —
about 212,000 records. Three things on the go-live list could be answered
from it, and one new problem showed up. This handoff is those four.

- **SAP will only accept an asset if Cadra tells it the asset's SAP "class"**
  (furniture, ICT, vehicles, land…). Cadra had a place for that on each
  category but it was empty everywhere, so SAP would have refused every new
  asset — after two people had already signed for it. Now Cadra refuses
  first, at the Register Maker's step and again at the Checker's, and tells
  them who fixes it. The Asset Controller sets the class on the categories
  screen. **Which class each category belongs to is NRS's call**, so the
  report proposes a mapping (below) and nothing was written into any real
  tenant.
- **Some assets cannot carry a sticker**: land, buildings, software, works in
  progress. The gates insisted every unit be tagged, so a plot of land could
  never reach the register. There is now a fourth kind of category,
  *identified by its SAP record*: no serial number, no label, and the two
  tagging steps are skipped (and the history says so) — five people instead
  of seven. No category was switched to it: none of Cadra's categories today
  is land, buildings or software (0 of 381 across ten tenants).
- **Fake serial numbers.** In SAP's list, a third of the "serial numbers" are
  fillers — `0`, `XXXX`, `4A12345FD`. With the gates on, Cadra now refuses
  those as fillers ("this is a placeholder, not a serial number") instead of
  accepting one and then refusing the next unit as a "duplicate". The list of
  fillers is the tenant's own and can be edited. Nothing already in the
  register was changed; Cadra's tenants hold none of these fillers today.
- **SAP numbers come in two shapes** — 11 digits, and older codes with
  letters. Both were already accepted; what was missing is that `abc` and
  `ABC` counted as different numbers. They are now one. If the first digit
  of an 11-digit number doesn't match the category's class, the maker gets a
  warning, not a refusal.

What it means: nothing changes on a tenant whose gates are off, apart from
the new fields on the screen. On `staging` (gates on) every category needs a
SAP class before anything can be registered — the deployed check above sets
one.

**Which tenants are touched by the staging point above:** `staging` holds 9
units in the chain today (2 at *registration submitted*), all in *Desktop /
Laptop Computer*, whose SAP class is blank there — after the deploy their
checker approval is refused until a class is set. That is the rule working,
and it is why step 2 of the check sets it first.

## The source file

`~/Downloads/NRS Asset (1).XLSX` (211,699 rows) was read on this machine
only, by a measurement agent, into a scratchpad outside the repo; the
row-level conversion was deleted the same hour. Nothing in this report or in
the branch is a row of it: counts, class codes and descriptions with counts.
The grep proving it is §6.6 below.

## §1 · SAP's asset class on every category

**Built.**
- With the gates on, *Submit to register* (the maker) and *Approve
  registration* (the checker) refuse a class with no SAP class, before
  anything is written: **"<Category> has no SAP asset class, so SAP would
  reject this asset. An Asset Controller sets it under Settings → Asset
  Categories."** The maker's check reads the class the maker *confirms*; the
  checker's reads the unit's class, because it can be cleared in between.
  With the gates off nothing is checked.
- `sap_asset_class` is published on every category and editable by the Asset
  Controller (`settings:classes`) or `settings:write`; four digits, or empty.
  The Store Officer is refused (403). Each change is a row on the
  configuration record, `cadra.class_sap_asset_class.<id>` = `<code>; class:
  <name>`. The screen offers SAP's ten codes as a hint, not a closed list.
- **What INT-06 does with a gates-off master and a blank class today:** sends
  `null`; a strict SAP refuses it (422), the queue retries and abandons it,
  and the asset becomes a dual-code exception. It should be held instead —
  recorded in DECISIONS as `[open]`, not built, because §5 forbids changing
  gates-off behaviour.

**Driven** (`tests/test_what_sap_already_holds.py`, `test19`, gates on):

```
at submit: 400 pytest-59 No SAP class has no SAP asset class, so SAP would reject this asset. An Asset Controller sets it under Settings → Asset Categories.
at approve: 400 pytest-59 No SAP class has no SAP asset class, so SAP would reject this asset. An Asset Controller sets it under Settings → Asset Categories.
configuration record: cadra.class_sap_asset_class.27698 = '4000; class: pytest-59 No SAP class'
```

The Asset Controller's PATCH answered 200; the Store Officer's, 403 naming
`settings:classes`. Five malformed codes (`300`, `30000`, `3A00`, ` 30 0`,
the number `3000`) answered 400 with *"`sap_asset_class` must be SAP's
four-digit asset class code, for example 3000."*

### The proposal — for NRS to decide, not to type in

**Measured first:** `sap_asset_class` is set on **1 of 22** categories on
`nrs19` (*Desktop / Laptop Computer* = `3100`, set 2026-09-21 — **not one of
the ten classes in SAP's export**) and on **0 of 22** on `staging`; 0 on
every other tenant. SAP's export carries no class *names*; what a class "is"
below is read off its commonest descriptions, as the reference doc does.

**Method.** For each Cadra category, the words of its own asset names (type,
make, model) — or its name, where it holds no assets — were counted against
SAP's 161,647 ACTIVE rows, per class, as whole words. The evidence is the
share of matching SAP rows in the proposed class and its commonest matching
descriptions.

**`nrs19`** (11,955 assets; 11,953 registered and active):

| Cadra category | Assets | Proposed SAP class | SAP's evidence (matching descriptions in that class) | Confidence |
|---|---|---|---|---|
| IT Equipment | 10,259 | **3000**, except UPS units (split 3000/4000) | LAPTOP: 25,289 of 25,300 SAP rows in 3000 (SUPPLY OF LAPTOPS ×3,232, DELL LAPTOP ×3,107, HP LAPTOP ×2,363). PRINTER: 2,358 of 2,506 in 3000 (HP LASERJET PRO M203DW ×900). WIRELESS ACCESS POINT 1,267 of 1,267; ROUTER 212 of 213; SCANJET 861 of 892 — all 3000. UPS: **4000 ×651 vs 3000 ×535** | **High** for 9,969 of 10,259 (laptops 5,812, printers 2,255, desktops 587, scanners 492, switches 310, access points 283, routers 230 — each ≥94% one class). **Split** for the 290 UPS units: SAP files small UPSes in both classes, by no visible rule |
| Fleet / Vehicles | 1,619 | **1000** | TOYOTA 1,379 of 1,379, HIACE 631 of 631, COROLLA 434 of 434, PEUGEOT 400 of 400, INNOSON 149 of 149 — all 1000 (TOYOTA COROLLA ×347, TOYOTA HIACE BUS ×168) | **High** — every make lands 100% in one class |
| Desktop / Laptop Computer | 69 | **3000** (the stored `3100` is not a class SAP's export uses) | DELL 5,490 of 5,490, LENOVO 2,133 of 2,133 in 3000 | High on the words — but these 69 rows are demo and handoff probes, not NRS data, and the existing `3100` needs NRS to say where it came from |
| Office Furniture | 4 | **2000** | CHAIR 44,358 of 44,539 in 2000 (HIGH BACK EXECUTIVE SWIVEL CHAIR ×4,976) | High on the words (4 rows) |
| Access Control System | 3 | **4000** (3000 for standalone biometric readers) | ACCESS CONTROL 34 of 38 in 4000; BIOMETRIC 3000 ×231 vs 4000 ×108 | **Low** — name only; the 3 assets are probes |
| Generator | 1 | **7000** | GENERATOR 220 of 233 in 7000 (PERKINS GENERATOR 100KVA ×26) | Medium — name only |
| Server / Network Equipment | 0 | **3000** | SERVER 183 of 183 in 3000 | High (by name) |
| Printer / Photocopier | 0 | **split: printers 3000, photocopiers 4000** | PRINTER 2,358 of 2,506 in 3000; PHOTOCOPIER 730 of 761 in 4000 | High that this category **cannot carry one class** |
| Air Conditioning Unit | 0 | **4000** | AIR CONDITIONER 3,536 of 3,559 in 4000 | High (by name) |
| Fire Extinguisher | 0 | **4000** | EXTINGUISHER 493 of 508 in 4000 | High (by name) |
| Vehicle | 0 | **1000** | as Fleet / Vehicles | High (by name) |
| Fire Safety System | 0 | **4000** | FIRE ALARM 89 of 125, SMOKE DETECTOR 69 of 86 in 4000 | Medium |
| CCTV System | 0 | **split 3000 / 4000** | CAMERA 3000 ×711 vs 4000 ×328; CCTV 4000 ×28 vs 3000 ×13 | Medium — a real split |
| UPS / Battery Backup | 0 | **split 4000 / 3000 / 7000** | UPS as above; BATTERY 224 of 269 in 7000 | Low |
| Water Treatment Plant | 0 | **7000** | WATER TREATMENT 9 of 9 in 7000 | Medium (9 rows) |
| Overhead / Storage Tank | 0 | **7000** | TANK 77 of 85 in 7000 — mostly diesel tanks | Medium-low |
| Water Pump / Borehole | 0 | **split 7000 (pumps) / 8000–9300 (boreholes as works)** | PUMP 13 of 14 in 7000; BOREHOLE across 8000, 9000, 9300 | Low |
| Lift / Elevator | 0 | **7000** | PASSENGER LIFT ×4 in 7000 (SAP's 93 "LIFT" rows in 3000 are microphone lifts) | Low |
| Compressor | 0 | **4000** | COMPRESSOR 2.5 ×7, 4000 only | Low |
| Electrical Panel / Distribution Board | 0 | **7000** | no direct match; nearest CHANGE OVER SWITCH ×15 (7000) | Low |
| HVAC Plant / Chiller | 0 | **no match** | CHILLER 0, HVAC 0 in SAP | — |
| Air Handling Unit (AHU) | 0 | **no match** | AIR HANDLING / AHU 0 in SAP | — |

**`staging`** (11,935 assets; 9 in the chain): the same 22 categories, and
the two that hold the register are identical to `nrs19`'s name for name and
count for count — so the same proposals. **Category ids differ** (*IT
Equipment* is 21 on `nrs19` and 22 on `staging`; *Fleet / Vehicles* the
other way round): a mapping must be applied by name, never by id.

| Cadra category | Assets (registered / in the chain) | Proposed | Confidence |
|---|---|---|---|
| IT Equipment | 10,259 / 0 | 3000; UPS units split 3000/4000 | High for 9,969; split for 290 |
| Fleet / Vehicles | 1,619 / 0 | 1000 | High |
| Desktop / Laptop Computer | 48 / 9 | 3000 (blank on `staging`) | High on the words; demo rows |
| the other 19 | 0 each | as `nrs19`'s name-based rows | as `nrs19` |

**What NRS has to decide, beyond the table:** three Cadra categories cannot
carry one SAP class as they stand — *Printer / Photocopier*, *CCTV System*,
*UPS / Battery Backup* — and 290 of *IT Equipment*'s units are UPSes SAP files
in two classes. Either the category is split or NRS names the rule.

## §2 · Classes that carry no label — `record_only`

**Built.** A fourth identification mode, labelled *"Identified by its SAP
record — no physical label (land, buildings, software, works in
progress)"*, default mandatory attributes `name` + `reference` (a new field
— title or plot number, licence key or contract; no existing field fit). At a
gated receipt a serial is refused whoever sends it. In the chain, IAD's
approval moves the unit straight to a new state, **`reg_ready`** (*ready for
registration — no label*), waiting on the Register Maker; the move is an
event of its own with no gate on it (skipped, not fired) and the reason
**"no label: <class> is identified by its record"**. Every row is in the one
`TRANSITIONS` table, limited by a `modes` key. No label is minted at any
point — `_generate_tag` refuses one, so the back-office station and a
replacement cannot either. The asset code is assigned at creation, as for
every unit. `return-registration` sends it back to `reg_ready`.

Why a new state rather than `tagged`: the maker's state was `tagged`, and a
plot of land would have published *Tagged*. The `waiting_on` set is unchanged
(seven values); `reg_ready` waits on `maker`.

**Driven** (`test19`, gates on, the throwaway category *pytest-59 Land
(record_only)*, SAP class 6000), as five personas:

```
waiting_on at every step: captured (store) → vfm_pending (iad) → vfm_verified (iad_approver) → reg_ready (maker) → reg_submitted (checker) → registered (None)
history: Tagging skipped (VfM approved → ready for registration (no label)) — no label: pytest-59 Land (record_only) is identified by its record
```

- received with no serial and a reference → 201 `captured`, `tag: null`, an
  asset code;
- the same with a serial → 400 *"pytest-59 Land (record_only) is identified
  by its SAP record and carries no serial number; send the unit without one
  (its title, plot number, licence key or contract goes in `reference`)."*;
  without its reference → 400, `missing_fields: ["reference"]`;
- the Asset Controller's *Request tagging* at `reg_ready` → 409
  `invalid_state`;
- the register count read before every step: unchanged until the checker,
  then +1;
- no label at the end (`tag: null`; in-registry, `tag_ids` empty and
  `_generate_tag` refused); in-registry also: five distinct people fired five
  gates, and SAP's INT-06 master was queued once, at the checker.

**Measured, seeded nothing:** categories whose names suggest land,
buildings, renovation, software, licences, works in progress, construction
or projects — **0 of 381 categories across 10 tenants** (the nine local ones
and `staging`). Cadra holds nothing today that maps to SAP 3500, 6000, 8000,
9000 or 9300.

**Vendra:** a Vendra receipt for a `record_only` class will demand a serial
until its follow-up lands (it treats an unknown mode as `serial`); Cadra
refuses a serial on such a unit regardless. The CHANGELOG names Vendra as
the client that switches on the enum.

## §3 · Placeholder serials

**Built.** The tenant's list is one configuration parameter,
`cadra.serial_placeholders` (seeded with `^X+$`, `^0+$` and the eleven
values), read and edited on Settings → Asset Categories and over `GET` /
`PUT /api/v1/settings/serial-placeholders`; compared stripped, upper-cased,
internal spaces collapsed. At a gated receipt a placeholder is refused
**"'XXXX' is a placeholder, not a serial number. Capture the serial printed
on the item."** — before the attributes and before the uniqueness check, so
it is never refused as a duplicate. A `tag_id` unit carrying one is refused
too (deviation, below). With the gates off nothing is checked (driven: a
gates-off `POST` with `XXXX` → 201, as before).

**The uniqueness check and legacy placeholders.** The check is only reached
by a serial that is not a placeholder, and two values equal stripped and
case-insensitively are placeholders together or not at all — so a legacy
placeholder cannot be the clash. The rows are filtered through the list
anyway. **The first draft accepted every duplicate**: it loaded the list on
the same database cursor after running the clash query, and then read an
empty result. Its own test caught it (a real serial already on the register
went through with 201); fixed before anything shipped.

**Driven on `test19`:** each of 16 placeholder spellings (`XXXX`, `x`, `0`,
`0000`, `5d12345m`, ` Nil `, `no   serial`, …) refused with the sentence;
legacy `XXXX` and a legacy real serial planted with the gates off, then with
the gates on: a new real serial → 201; `xxxx` → refused **as a
placeholder**; the legacy real serial in lower case → refused as the
duplicate it is. One list edit (adding *to be confirmed*) appeared on the
configuration record as `cadra.serial_placeholders`, then was put back.

**Proved on `nrs19`, read-only** (the receipt check called directly in a
shell, nothing written, rolled back; no NRS serial printed):

```
category: IT Equipment serial
assets on nrs19 already carrying the real-looking serial: 0
a real-looking serial equal to nothing           -> accepted
placeholder 'XXXX'                               -> REFUSED (validation_failed): 'XXXX' is a placeholder, not a serial number. Capture the serial printed on the item.
placeholder '0'                                  -> REFUSED (validation_failed): '0' is a placeholder, not a serial number. Capture the serial printed on the item.
placeholder '4A12345FD'                          -> REFUSED (validation_failed): '4A12345FD' is a placeholder, not a serial number. Capture the serial printed on the item.
placeholder 'no serial'                          -> REFUSED (validation_failed): 'no serial' is a placeholder, not a serial number. Capture the serial printed on the item.
an existing nrs19 serial (value withheld)        -> REFUSED (validation_failed): Serial number <withheld> is already registered …
```

**Measured, not cleaned** (the upgrade's own line, every local tenant; and
`staging` through the read-only `db-query` workflow):

| Tenant | Assets | With a serial | Placeholders |
|---|---|---|---|
| cadra19 | 1,335 | 13 | 0 |
| nrs19 | 11,955 | 11,332 | 0 |
| gtb19 | 156 | 0 | 0 |
| test19 | 16,938 | 2,749 | 0 (before this handoff's own fixtures; 4 after) |
| nrs | 1,272 | 0 | 0 |
| lasg | 150 | 0 | 0 |
| gtb | 150 | 0 | 0 |
| jaizbankplc | 4,164 | 210 | 0 |
| boot44 | 231 | 38 | 0 |
| staging | 11,935 | 11,317 | 0 |

**0 of 25,659 serials on 10 tenants** match the seeded list. `nrs19` does
hold near-misses the list does not catch: `N\A` ×3 and three-letter codes
typed into the serial field — `DEL` ×53, `TOG` ×44, `BAD` ×13, `TRF` ×2 —
which NRS may want to add on the screen. SAP's export, same list: **33,092
of 80,128** active serials (the reference doc says 33,096; the four are in
class 3000 and the doc does not state its definition — `.`, `***` and
`UNKNOWN` are three candidates).

## §4 · SAP asset numbers in both formats

**Measured before changing anything:** the field is an unbounded text field,
the maker's form is free text, and both the gate's duplicate check and the
model's uniqueness rule compared **exactly**. So both shapes were already
accepted — what failed was normalising: `abc123` and `ABC123` were two SAP
assets. 0 SAP numbers on any local tenant are shared once normalised, so
tightening the rule disturbs nothing.

**Built.** The maker's code is stored stripped and upper-cased; the gate's
duplicate check and the model's rule compare in that form (the refusal names
the asset holding it). **No format is refused**: SAP's legacy codes contain
`/` (3,299 rows), `&` (97), `\` (73) and spaces (4), 7 to 12 characters — a
pattern would refuse SAP's own numbers. The class-digit warning returns as
`data._warnings.sap_asset_number` on *Submit to register* and *Approve
registration*, and is kept on the maker's event. **Class 3500 is the
exception the export shows**: all 59 of its numeric numbers start `5`, not
`3` (146,165 of 146,224 eleven-digit numbers start with their class's digit;
those 59 are the rest), so a 3500 number starting `5` is not warned and a
3000 category given a `5…` number is told *"looks like a class 3500
number"*. Sub-numbers (53 of 211,699 rows) are out of scope — DECISIONS.

**Driven** (`test19`, a class mapped to 3000, numbers invented at run time):
an 11-digit number starting `3` → 200, no warning; a legacy code typed
`  zzq…ict… ` → 200, stored upper-case; the same code again → 400 *"SAP asset
code ZZQ… is already on another asset (NRS-AST-…)"*; an 11-digit number
starting `2` → 200 with

```
warning: 29772170864 looks like a class 2000 number; this category maps to 3000.
```

(an invented number, generated by the test).

## §7 · If 70 units a day went through the gates, where would it jam first?

**How it was counted.** Every screen and route on the path, read from the
code as it stands, for one unit, starting on the Candidates page with the
person's own tab open (the sidebar click and first load paid once a session).
A click is a mouse click or tap; a scan is one handheld trigger pull; typed
values use the route schema's own examples. Optional fields counted as
skipped.

**What is true of every gate.** Each action is one POST for one unit — no
route accepts a list of ids, and `_fire_gate` is single-record. The
Candidates page has no multi-select. It does let a person fire their gate
from the list row without opening the asset. It shows 100 rows a page,
**newest first** (so past 100 waiting, the oldest are the ones off the
screen), its search box is switched off (the API's `?q=`, which matches the
GRN, is not offered), and *waiting on me* is by role, not by person — a unit
the no-two-gates rule bars you from still sits in your tab, as a sentence.
After every action the whole list reloads, and each row's server cost grows
with the history it carries. **Nothing tells anyone a unit is waiting:** the
sidebar badge counts movement requests and tag replacements only, there is no
email, activity or digest from a gate, and the list does not refresh on its
own. `state_since` is shown as an age, with no threshold and no sort.

| Persona | Per unit | Per day (×70) |
|---|---|---|
| Store — submit | 2 clicks | 140 clicks |
| IAD officer — verify | 9 clicks + 1 file pick + 1 upload | **630 clicks, 70 file picks, 70 uploads** |
| IAD approver — approve | 2 clicks (and cannot see the evidence in the app) | 140 clicks |
| Asset Controller — request tagging | 2 clicks | 140 clicks |
| Tagger — at the station | 2 scans + 3–5 clicks + 5 requests, plus printing | **140 scans, 210–350 clicks, 70 print selections** |
| Register Maker — submit | 3 clicks + ~25 keystrokes + 1 lookup in SAP | **210 clicks, ~1,900 keystrokes, 70 SAP lookups** |
| Register Checker — approve | 2 clicks blind; 4 clicks + 2 page loads to check | 140–280 clicks |

### The three worst, ranked

**1. IAD verification — a full checklist and a fresh evidence upload for
every unit.** Four separate ticks (no "all four"), a file picker each time
(the picked files live only in the dialog and are lost when it closes), and
the same delivery note uploaded again for every unit on the GRN: ten laptops
on one note is ten uploads and forty ticks attesting the same price. It is
the first heavy gate, so everything after it waits on it. And the approver
after it cannot open the evidence anywhere in the app — they approve blind or
go to the back office. *Smallest relief:* a checkbox column on the Candidates
`iad` tab with *Verify selected*, backed by one batch route that takes one
checklist and one evidence set for N units **of the same GRN** and fires the
existing gate per unit (one event each, so the audit record is unchanged);
turn on the existing `?q=` search so the officer can show one delivery. A
front-end stopgap alone (an *all four* toggle, keeping picked files across
dialogs) gets it to about four clicks a unit. Then show the evidence on the
asset page for the approver.

**2. Tagging — one at a time, two scans, a manual reset, no worklist.** The
affix step is not on the Candidates page at all (it is a station action), so
the tagger has no list of *labels to fix today*. The station's batch print
exists but lists the 200 newest labels of every asset, register and
candidate alike, with nothing to tell today's apart. After each confirmation
the scan box is neither cleared nor focused, so the next scan appends to the
last one. *Smallest relief:* after a confirmation, clear and focus the scan
box (two lines — saves 140 interactions a day); and a *Labels to fix* panel
on the station reading the existing `GET /candidates?waiting_on=tagging`,
with select-all into the existing batch print. The second scan inside the
dialog is the control and should stay. (Note for the Architect: the label's
number IS the asset code, and the asset code is printed on every Candidates
row, so the dialog's "never hand the number over" rule protects less than it
did before handoff 57.)

**3. Register Maker — three fields typed per unit, the SAP code looked up by
hand.** Cost and cost centre start empty although the unit's cost is already
in the payload; only the date and class are prefilled; the SAP code is one
free-text box per unit with no paste-a-list. That is ~1,900 keystrokes and
70 SAP lookups a day, each a chance of a typo the duplicate check cannot
catch. The checker then has none of the three on the list row, so checking
properly means opening each asset (and *Back* goes to the asset list, not to
Candidates). *Smallest relief:* prefill cost from the unit, carry the cost
centre and date over from the maker's previous submission (front end only —
down to the SAP code, ~11 keystrokes); then a paste box on the `maker` tab
(asset code → SAP code) feeding a batch route that fires the existing gate
per unit; and SAP code and cost columns on the `checker` tab.

**Across all three, and cheap:** a sidebar badge counting the person's own
`waiting_on` (`GET /candidates?waiting_on=<their gate>&limit=1`, the same
cheap count the approvals badge uses), and the list sorted oldest first.
Without the badge nothing at all tells anyone a unit is waiting.

What none of this changes: one person may still not fire two gates on a unit,
and every unit still gets its own append-only events. The relief is in how
many units a person can act on at once, not in how many people sign.

## §6 · Verification

### 1. The suites, gates off and gates on, `test19` (`59-evidence/`)

**pytest** — the same 1,392 tests in both runs:

| Run | Result |
|---|---|
| switch OFF (`pytest-switch-off.txt`) | **1,385 passed, 0 failed, 7 skipped** — of 1,392, 13 min 41 s |
| switch ON (`pytest-switch-on.txt`) | **1,385 passed, 0 failed, 7 skipped** — of 1,392, 36 min 50 s |

The seven skips are report 58's seven, by reason, in both runs: 2 Turnstile
not configured, 2 partition data absent, 1 `is_tagged` documented, 1 no
`workflow.config`, 1 untagged serial (handoff 38). 1,357 (report 58) →
1,392: 35 tests in `tests/test_what_sap_already_holds.py` (16 of them the
placeholder spellings, parametrised). One handoff-58 test's meaning
widened: `test_every_class_publishes_its_identification` now accepts
`record_only` (an additive enum value; a test category of it exists on any
tenant this suite has run on).

**Module suites, `test19`, after pytest** (CI's order), each in a throwaway
container with the server stopped — the recipe in `docs/ENVIRONMENT-FACTS.md`;
a first attempt alongside the running server was killed by the host's memory
(exit 137) and is not counted (`module-suites.txt`):

```
myservice_api | 0 failed, 0 error(s) of 424 tests | CRITICAL: 0
myservice_asset_register | 0 failed, 0 error(s) of 482 tests | CRITICAL: 0
myservice_workflow | 0 failed, 0 error(s) of 96 tests | CRITICAL: 0
myservice_barcode_station | 0 failed, 0 error(s) of 20 tests | CRITICAL: 0
```

414 → 424 in `myservice_api`: the ten tests of `TestWhatSapAlreadyHolds`.
No `of 0 tests`. (The Postgres `ERROR:` lines in the logs are tests that
provoke a refusal on purpose.)

**Browser suite** (`e2e-switch-off.txt`, `e2e-switch-on.txt`), the app
rebuilt with `BASE_PATH=/app/` first:

| Run | Result |
|---|---|
| switch OFF | **231 passed, 1 flaky, 0 failed, 31 skipped** — of 263 |
| switch ON | **250 passed, 1 flaky, 0 failed, 12 skipped** — of 263 |

253 (report 58) → 263: spec 57's six `record_only` tests and spec 59's four.
Skips with the switch off: report 58's twelve environmental ones (8 need the
service credential, 3 need building locations, 1 a request `type_id` —
specs 06, 08, 35, 38, 39) plus **19 that say the gates are off** (spec 57's
18, spec 59's one step that needs them); with the switch on, exactly the
twelve environmental ones. **One flaky test per run, each passing on its
retry:** switch off, `14-settings-depreciation` *ERP-managed mode disables
the calculation controls* — GO-LIVE §13.5's known depreciation spec; switch
on, `06-asset-actions` *mark found via the app dialog*, whose first attempt
found the history's second row to be the Register Maker's SAP-number entry
rather than the mark-missing event — two events written in the same second,
ordered the other way (`e2e-switch-on.txt`, line 306). The history's
same-second tie order is not something this handoff touched; recorded, not
fixed. `test19`'s receipt switch is left **on**, as found.

**Specs 57 and 59 alone**, run first by the app's author with nothing else
writing to `test19` (the *All Assets* total is tenant-wide, so a concurrent
suite moves it): **22 passed of 22** (`e2e-specs-57-59.txt`).

### 2–5. Each section driven — in §1 to §4 above.

### 6. The source-file rule

`git log -p dev..HEAD` on this branch (every commit, so an intermediate one
cannot hide a value later removed), every added line checked against a set
of NRS's identifiers built from the source file in the scratchpad — 211,694
asset numbers, 112,280 inventory (FIRS tag) numbers, 44,859 distinct serials
— and deleted afterwards. The script prints counts, never a value:

```
added lines scanned: 4455
11-digit numbers in the diff: 2; of them in SAP's register: 0
FIRS/<office>/<n> tags in the diff: 0; of them in SAP's register: 0
alphanumeric legacy SAP asset numbers in the diff: 0
the six named shared serials in the diff: 0
serials shared by >=50 SAP rows (len>=6) in the diff: 0 of 55 checked
```

The two 11-digit numbers are invented (an OpenAPI example and one the test
generated, quoted in §4), and neither is in SAP's register. Scoped to
`dev..HEAD` on purpose: the handoff file and the reference doc on `dev` carry
real ones — see *For the Architect* below. **This check caught me first:**
before committing, two of my code comments and one OpenAPI description had
reused the handoff's example numbers, which are real NRS asset numbers; they
were replaced with descriptions of the shape before any commit, so no commit
on the branch carries them.

### 7. Fan-out and readiness (`fanout.txt`)

Every local tenant, one at a time, `-u myservice_asset_register,myservice_api`,
then a restart — the migration's own three lines per tenant are in §3 and §2
above (0 errors on 9 of 9), and readiness after the restart:

```
cadra19 | {"data": {"ready": true, "database": "cadra19"}} 200
nrs19 | {"data": {"ready": true, "database": "nrs19"}} 200
gtb19 | {"data": {"ready": true, "database": "gtb19"}} 200
test19 | {"data": {"ready": true, "database": "test19"}} 200
nrs | {"data": {"ready": true, "database": "nrs"}} 200
lasg | {"data": {"ready": true, "database": "lasg"}} 200
gtb | {"data": {"ready": true, "database": "gtb"}} 200
jaizbankplc | {"data": {"ready": true, "database": "jaizbankplc"}} 200
boot44 | {"data": {"ready": true, "database": "boot44"}} 200
```

**The deploy, for the owner, after the merge:**
1. Merge the PR → **`deploy-dev`** builds and pins the backend and frontend.
2. **`upgrade-19`**, all four tenants (`staging, gtb, jaizbankplc, lasg`),
   modules `myservice_asset_register,myservice_api`, `scale_down=true`. Each
   tenant prints three `handoff 59:` lines (placeholders, label-less
   categories, SAP classes). **Mandatory before traffic:** a new column,
   `nrs_asset.reference`.
3. Then the check under *Needs the owner* — readiness first.

## CI — red since handoff 58 merged, green now

The owner found the PR's checks red after the report was pushed. **The cause
predates this handoff:** `dev` had been red on every CI run since PR #117
(handoff 58) — 8 failed and 2 errors each time — and report 58's "green" was
local only. Two causes, both environmental, neither a product defect:

1. **CI's fresh database has no demo personas.** Since 58 the HTTP suite
   walks units through the gates as the seven personas and FAILS, by design,
   when there are none: *"The receipt gates are ON on this tenant and
   docs/api/.personas.localhost does not exist…"*. `test19` has the file;
   CI never did. This handoff's own walks added seven more of the same.
   **Fixed** by a CI step that seeds the personas the way every classified
   tenant has them (`scripts/demo_personas.sh <db> seed`, masked, never
   printed, not in the uploaded artifacts) — not by a skip, which would turn
   a switch-on run green by proving nothing.
2. **CI has no outgoing mail**, and handoff 58's role-exclusion fixture
   created its person with an invitation letter → 500. **Fixed** with
   `send_invitation: false`, the convention every other person-creating
   test already follows.

After the fix (`f1f224f`), CI on the PR: **pytest 1,353 passed, 39 skipped,
0 failed** on CI's own database (different data and skips from `test19`, so
a different count), the in-registry step and every other check green.
One thing seen and not chased: the in-registry step's log, as `gh run view
--log` serves it, stops mid-run (it did on PR #116's green run too), so
CI's module-suite denominators cannot be read from it; the local ones above
are the evidence.

## The verification pass (a fresh agent, not an author)

Found and **fixed**, each with a test:
1. The new `PUT /settings/serial-placeholders` was missing from the
   published-names table, so `myservice_api`'s guard would have gone red.
2. A registered `record_only` unit would have sat in the station's
   *untagged* list for ever, and a batch *Generate* containing one would have
   failed whole — the refusal uncaught in the loop, rolling back every label
   minted before it. Now it is left out of the list and the count, and
   skipped in a batch (`reason: record_only`).
3. The receipt rules guarded creation only: a `PATCH` on a unit still in the
   chain could put a serial on a `record_only` unit, a placeholder on any, or
   clear its reference. The model's `write` now applies the same rules to
   such a unit.
4. The placeholder list could be saved empty (every placeholder then
   accepted) or with `.*` (every serial refused) — both refused; an
   unreadable stored list now reads `configured: false`.
Also: a method name wrong in DECISIONS; the HTTP test's hard-coded category
1 replaced by a fixed-name serial class; two of my own code comments quoted
real NRS asset numbers (§6.6).

**Left, with reasons** (DECISIONS): 58's serial-uniqueness check is still
receipt-only (a `PATCH` can give a candidate a duplicate serial —
pre-existing); INT-06's master does not carry `reference`, so SAP would get
a land master with only its description (a payload change belongs with the
real SAP endpoint, GO-LIVE §29 item 5); a registered `record_only` asset
reads `is_tagged: false` for ever, which is true; the asset's new top-level
`reference` sits beside two other `reference` keys with other meanings (a
move's transfer name, `disposal.reference`) — no guard fails, but it is a
naming question for the Architect under handoff 37's one-name rule.

## Deviations, with why

1. **A new register state, `reg_ready`**, rather than reusing `tagged` —
   which would publish *Tagged* on a plot of land. Additive enum value.
2. **Two changes reach gates-off tenants, against the letter of §5:** SAP
   numbers unique once normalised, in the model rule every writer meets; and
   a category's SAP class four digits from every writer. A rule only the gate
   obeyed would let INT-07 or an import create what the gate refuses. 0
   tenants affected by either, measured. Both announced as BEHAVIOUR CHANGE,
   every tenant. Reversible by narrowing them to the gate if the Architect
   rules §5's letter.
3. **A `tag_id` unit carrying a placeholder serial is refused too** (§3
   names `serial` mode). Storing `0` through the gates would seed the next
   collision; the sentence tells the storekeeper the unit may come with no
   serial. Under 58 such a line was accepted — announced.
4. **No format is refused for SAP asset numbers** — SAP's own legacy codes
   carry `/`, `&`, `\` and spaces; §4 asked only that both shapes be
   accepted.
5. **The class-digit warning knows class 3500** — on the export's evidence,
   its numbers start `5`.
6. **INT-06 holding a gates-off master with a blank class** — asked to be
   *said*, not built: recorded `[open]`.

## For the Architect — the reference doc and the handoff carry NRS's identifiers

Checked against the source file: `docs/reference/sap-asset-master-2026-10.md`
quotes **1 real SAP asset number, 2 real legacy codes, 1 real FIRS tag number
and the 6 real shared serials**; `docs/handoffs/59-what-sap-already-holds.md`
quotes the same SAP number and the 2 legacy codes. The handoff's own rule says
asset numbers, serials and tag numbers of individual records do not belong in
the repo. Step 0 committed both files on `dev` as instructed (`b1d5a0e`,
pushed) before this was noticed. The Builder does not edit the Architect's
files and will not rewrite pushed history; replacing the examples with
shapes is a one-line edit each for the Architect, and whether to purge them
from history (a force push to `dev`) is the owner's decision. My own branch
carries none of them (§6.6).

## The standing sentence check

Every refusal this handoff adds says what happened and what to do, naming
the thing: the category and who sets its SAP class; the class and that its
units carry no serial, and where the title goes instead; the value and that it
is a placeholder, and what to capture; the SAP code and the asset already
holding it; the bad SAP class and its shape; an empty or catch-all
placeholder list and why it cannot be saved. None says "permission denied".
The handoff's sentences are used verbatim — §1's refusal, §3's placeholder
refusal, §2's skip reason, §4's warning — asserted by equality in the HTTP
and in-registry tests and, for §1, in the browser (spec 59 (ii)).

## Commits

| Commit | What |
|---|---|
| `b1d5a0e` (on `dev`) | Step 0: the instruction file and the SAP asset-master reference |
| `a3e97ae` | the server: the SAP class at both registration gates, `record_only` and `reg_ready`, placeholder serials, SAP numbers normalised, the verification pass's fixes, migration 19.0.1.28.0 |
| `e327363` | the app: SAP class on categories, placeholder serials, the receive form and register dialog; specs 57 (extended) and 59 |
| `408f3f7` | the HTTP and in-registry suites; the walk reads the next gate off the state |
| `93b612a` | decisions, CHANGELOG, endpoint reference §14.11, GO-LIVE §29, STATUS, CLAUDE.md, this report and its evidence |
| (this commit) | §6.6's grep result |

## Addendum, 2026-10-15 — deployed to the cluster

After the owner merged PR #118: `ci` and `deploy-dev` ran green on the merge
(`e8fe906`, image `cadra-odoo-19:dev-e8fe906`). Then, at the owner's word,
**`upgrade-19`** (run 38692128591): tenants `staging, gtb, jaizbankplc,
lasg`, modules `myservice_asset_register,myservice_api`, `scale_down=true`,
the image pinned to the merge's build. Every tenant upgraded, then the
server rolled forward (*"every tenant upgraded — rolling forward to: …
dev-e8fe906"*, *"deployment "odoo-19" successfully rolled out"*). Each
tenant's own lines:

```
handoff 59: placeholder serials on staging — 0 of 11317 assets with a serial (of 11935 assets) carry a placeholder; top: none
handoff 59: categories on staging whose names suggest a label-less class — 0 of 22 (none); none switched to record_only
handoff 59: SAP on staging — 0 of 22 categories carry a SAP asset class; 0 SAP asset numbers shared once stripped and upper-cased (of 3 assets with one)
handoff 59: placeholder serials on gtb — 0 of 0 assets with a serial (of 150 assets) carry a placeholder; top: none
handoff 59: categories on gtb whose names suggest a label-less class — 0 of 29 (none); none switched to record_only
handoff 59: SAP on gtb — 0 of 29 categories carry a SAP asset class; 0 SAP asset numbers shared once stripped and upper-cased (of 0 assets with one)
handoff 59: placeholder serials on jaizbankplc — 0 of 0 assets with a serial (of 150 assets) carry a placeholder; top: none
handoff 59: categories on jaizbankplc whose names suggest a label-less class — 0 of 29 (none); none switched to record_only
handoff 59: SAP on jaizbankplc — 0 of 29 categories carry a SAP asset class; 0 SAP asset numbers shared once stripped and upper-cased (of 0 assets with one)
handoff 59: placeholder serials on lasg — 0 of 0 assets with a serial (of 150 assets) carry a placeholder; top: none
handoff 59: categories on lasg whose names suggest a label-less class — 0 of 29 (none); none switched to record_only
handoff 59: SAP on lasg — 0 of 29 categories carry a SAP asset class; 0 SAP asset numbers shared once stripped and upper-cased (of 0 assets with one)
```

Readiness, no token, after the roll:

```
staging.app.cadra.ng | {"data": {"ready": true, "database": "staging"}} 200
gtb.cadra.ng | {"data": {"ready": true, "database": "gtb"}} 200
jaizbankplc.cadra.ng | {"data": {"ready": true, "database": "jaizbankplc"}} 200
lasg.cadra.ng | {"data": {"ready": true, "database": "lasg"}} 200
```

The cluster's `jaizbankplc` carries 150 assets and no serials — not the
local replica's 4,164 and 210; the two databases are not the same data.
**Still the owner's:** the browser check on `staging` (Turnstile) under
*Needs the owner* at the top — set a SAP class on *Desktop / Laptop
Computer* first, or `staging`'s units in the chain cannot be approved for
registration.
