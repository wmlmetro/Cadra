# Handoff 55 — The side a camera reads

**Branch:** `fix/the-side-a-camera-reads`
**Report:** `docs/handoffs/55-REPORT.md`
**Runs after:** handoff 53 (which was waiting on 54 and now runs). Branch
from `dev`. Small.

---

## 0 · Report 54 is accepted in full, and the ruling it asked for is here

The engine is one engine now, self-hosted, loaded only when the camera
starts, and proved two ways: twelve fake-camera tests and a 408-frame
corpus with a denominator in every cell. Three things in the report deserve
naming before the ruling:

- **The corpus harness lied on its first run and you caught it.** An `<img>`
  at a fractional CSS size lost decodes the same pixels kept through a
  canvas. A harness that under-reports the engine is the mirror of one that
  over-reports it, and you found it by noticing one Code 128 read one way
  and not the other. The committed table is from the fixed pipeline, run
  twice, identical.
- **The first full suite run broke every affix** — two overrides of
  `_mark_affixed` in `myservice_workflow` spelled out the old signature.
  Sixteen failures, fixed, and the lesson is in DECISIONS the right way
  round: *a signature you grow is a contract every overrider holds.*
- **§6c was a defect in my handoff**, and you were right to say so. I wrote
  "no real device, no done" and no *Needs the owner* block, for a step only
  the owner can do. The table is now the owner's, with the procedure, and
  this handoff does not depend on it.

Also accepted: the lookup records no format, because a read records nothing
for a format to ride on — inventing a key that is accepted and never stored
would be our third defect class. The station shows it instead. Correct.

### The ruling the corpus made possible

The Code 128 on the **small** and **standard** labels is **0 of 24** — not
marginal, not close: a 15-character tag at 28.6 mm is about 5 mil per
module, below what any camera pipeline resolves at any distance, and at the
floor of common laser scanners. The QR on the same labels reads **3 of 3**
as printed. The large label's Code 128 reads close-up only; its QR reads at
arm's length.

**So the small and standard labels are printing a code that nothing in
this programme can read, in space the code that everything reads could
use.** That is a label change, and this is it.

---

## 1 · The change, measured not designed

In `asset_tag_report.xml`'s `cfg`:

- **`small`: drop the Code 128.** The QR takes the width the barcode held
  (`bc: 6mm` + `qr: 7mm` + padding becomes one QR as large as the row
  allows — expect roughly 12–13 mm), and the human-readable tag number
  stays, in a size a person can read across a desk. A 7 mm QR demanded a
  closeness a fixed-focus camera could not hold; a 12 mm one does not.
- **`standard`: drop the Code 128 unless it can reach 10 mil.** Compute
  what module width the remaining row gives a 15-to-17-character Code 128
  once the QR is grown to what reads at arm's length. If it reaches ≥ 10
  mil (0.25 mm), keep it, smaller QR gain. If it cannot — and from the
  numbers I expect it cannot — drop it as on `small`. Print the arithmetic
  in the report, the way the corpus table header prints its own.
- **`large`: unchanged.** Both sides read as printed.

Then **the corpus is the acceptance test.** Rerun `corpus:54` against the
new renders: every Cadra size's QR must read at the arm's-length scale (4.2
px/mm), not only as printed; no previously passing cell regresses; and the
baseline `expected-pass.json` is re-committed with the new cells, each
change named in the report. The small QR row going from 9 of 24 to
something near the large row's 18 of 24 is the number this handoff exists
to produce — print before and after.

---

## 2 · What the handheld-scanner question needs before the Code 128 goes

A 1D laser scanner reads Code 128 and cannot read a QR; a 2D imager reads
both. If the tagging unit holds laser scanners, dropping the Code 128 takes
their tool away on the two smaller sizes — for a code that is already at
the floor of what a laser resolves, but still.

**Owner question, carried in the same message as this file:** does the
tagging unit own scanners, and are they 1D or 2D? Until the answer arrives,
build §1 behind a **template-level choice, not a code branch**: the three
sizes stay, and the two smaller ones gain a sibling — `small-qr`,
`standard-qr` — selectable where the print size is chosen today. The
originals keep printing exactly as before. When the owner answers, one
handoff later makes the QR variant the default or deletes the originals,
with the answer written beside it. No label anyone has already printed
changes meaning.

If that makes the size picker awkward, say so and propose the smaller
honest shape; do not hide the choice in a setting nobody will find.

---

## 3 · What must not change

- **The tag number, its format, its sequence.** This is ink, not identity.
- **The QR's content** — the tag number, exactly as the Code 128 carried it.
  The affix check compares strings; a QR that encodes a URL or a prefix
  breaks every affix.
- **`large`.**
- **The corpus harness** — it is the instrument; this handoff is the thing
  it measures. If the harness needs a change to render the new sizes, that
  change is named separately and run against the *old* template first to
  show it did not move the old numbers.

---

## 4 · Verification

1. The corpus, before and after, both tables committed, the baseline
   updated with every changed cell named.
2. The three (or five) sizes rendered from the real template through the
   real Odoo renderer — the PDFs in evidence, with a ruler-scale check that
   the QR's physical size is what `cfg` says it is (the paperformat content
   box arithmetic the corpus header already does).
3. Spec 54's per-size fake-camera tests extended to the new variants, QR
   side, at the arm's-length scale.
4. Full suite, in-registry, browser suite, with times. No fan-out should be
   needed for a QWeb change; say so if that is what you measured.
5. The standing sentence check.

---

## 5 · What is with the owner

Carried in the same message as this file:

- **The §6c device table from report 54** — three labels printed, the
  MacBook first. The report has the procedure; the preview prints what the
  camera granted. Nobody but the owner can hold a label to that camera.
- **The scanner question** (§2).
- **For the demo, from the corpus alone:** scan the QR side, prefer the
  large label. If the small label's QR will not hold focus on the MacBook,
  that is the fixed-focus lens, and the answer on the day is the large
  label at roughly face distance — or an iPhone as Continuity Camera through
  the new picker.
