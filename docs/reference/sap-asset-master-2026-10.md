# SAP's asset master for NRS: what the October 2026 export shows

**Source:** `NRS Asset (1).XLSX`, an export of SAP's fixed-asset master for
company code `FIRS`, received by the owner on 12 October 2026. It has
211,699 rows and 93 columns, and the latest record was created on
7 October 2026. **The file isn't in this repo and must never be committed:**
it is NRS's register. This page holds aggregates only, measured by the
Architect on 12 October. Examples of identifiers are given as *shapes*,
not as real values.

The export holds **master data only.** It has no acquisition values, no
depreciation, and no cost centre, plant or location: those are time-dependent
or value tables SAP keeps elsewhere. The column set is SAP's ANLA plus a few
fields from ANLU.

## Size

- **211,699 assets: 161,647 active and 50,052 retired.** Retired means
  `Deactivation on` is set. The big retirement years are 2017 (25,626),
  2020 (6,386), 2024 (6,383) and 2018 (6,057).
- **Creations:** 17,920 in 2025, and 13,801 in 2026 up to 7 October. That's
  about **1,500 new assets a month, or roughly 70 per working day**.
- For comparison, Cadra's NRS data (`nrs19`, `staging`) holds about 11,900
  assets, around 7% of SAP's active register.

## The ten asset classes

SAP's class *names* aren't in the export. The "looks like" column is read
off the commonest descriptions and **needs NRS to confirm**.

| SAP class | Account determination | Looks like | Total | Active |
|---|---|---|---|---|
| 1000 | 100 | Motor vehicles | 2,809 | 2,237 |
| 2000 | 200 | Furniture & fittings (desks, chairs, coat hangers, bookshelves) | 95,362 | 80,370 |
| 3000 | 300 | ICT: laptops, printers, cabling, **and** non-physical items such as connectivity, user lines and SAP projects | 62,230 | 45,330 |
| 3500 | 350 | Software & licences | 59 | 59 |
| 4000 | 400 | Office equipment (water dispensers, shredders, fridges, air conditioners, fans) | 34,721 | 24,978 |
| 6000 | 600 | Land | 91 | 90 |
| 7000 | 700 | Plant & power (solar panels, generators, UPS, security lights) | 15,289 | 7,848 |
| 8000 | 800 | Buildings & renovations | 764 | 361 |
| 9000 | 900 | Construction in progress | 16 | 16 |
| 9300 | 910 | Projects / works in progress | 358 | 358 |

**Classes that can't carry a label:** 3500, 6000, 8000, 9000 and 9300,
plus the non-physical part of 3000.

## Serial numbers, active assets only

| SAP class | Active | No serial | Placeholder | Real, unique | Real, shared |
|---|---|---|---|---|---|
| 1000 | 2,237 | 1,791 | 77 | 324 | 45 |
| 2000 | 80,370 | 56,297 | 12,749 | 9,684 | 1,640 |
| 3000 | 45,330 | 0 | 11,974 | 19,809 | 13,547 |
| 3500 | 59 | 5 | 28 | 3 | 23 |
| 4000 | 24,978 | 17,676 | 5,402 | 1,613 | 287 |
| 6000 | 90 | 89 | 0 | 1 | 0 |
| 7000 | 7,848 | 4,933 | 2,863 | 37 | 15 |
| 8000 | 361 | 357 | 3 | 1 | 0 |
| 9000 | 16 | 16 | 0 | 0 | 0 |
| 9300 | 358 | 355 | 0 | 2 | 1 |
| **Total** | **161,647** | **81,519** | **33,096** | **31,474** | **15,558** |

**Placeholders found across all 211,699 rows**, value and count:

| Value | Rows |
|---|---|
| `0` | 22,217 |
| `XXXX` | 10,331 |
| `4A12345FD` | 5,762 |
| `XXX` | 5,537 |
| `XXXXXX` | 362 |
| `XXXXX` | 129 |
| `12345AB` | 85 |
| `12345HFD` | 58 |
| `12345ABC` | 50 |
| `123456` | 26 |
| `XXXXXXXXXX` | 4 |
| `XX` | 3 |

`5D12345M` (820 rows) also looks like a placeholder.

**The most-shared values that look real** are on 900, 854, 847, 523, 406
and 397 assets each.

These are most likely one invoice's or one box's number typed on every unit.

Only **31,474 active assets (19%)** carry a serial that is real-looking
and unique.

## SAP asset numbers

There are two formats:

- **146,224 numeric, 11 digits, starting with the class digit**: the
  shape `2NNNNNNNNNN` for class 2000. These were created from 2014 onward.
- **65,475 alphanumeric legacy codes** from the 2013–14 load, in shapes
  such as `TEMnnXXXnnnn` and `FIRSXXXXnnn`. By prefix: `TEM` 43,653, `FIR` 5,698,
  `TMP` 3,882, `HQT` 2,048, `EMP` 1,161.

53 rows carry a sub-number (`1`, `2000`, `3000`, …), and 5 main numbers
appear twice because of it.

## The old FIRS tag (SAP's "Inventory number")

- **Format:** `FIRS/<office code>/<sequence>`, the shape
  `FIRS/XXXX/nnnn`.
- **Coverage:** set on 131,724 active assets.
- **Not unique:** 12,061 numbers are shared, covering 33,899 assets.
  The most-shared single number is on 4,214 assets.

It can be a reference; it can't be an identity. Ruling 4.3 already makes
the Cadra asset code what the new label carries.
