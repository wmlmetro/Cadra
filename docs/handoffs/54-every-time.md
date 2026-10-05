# Handoff 54 — Every time

**Branch:** `fix/every-time`
**Report:** `docs/handoffs/54-REPORT.md`
**Runs after:** handoff 52 (merged). **Runs before 53** — the owner has
prioritised this; 53 touches the dashboard and this touches the scanner, so
they do not collide, but this one goes first and 53 waits for it unless the
owner says otherwise. Branch from `dev`.

---

## 0 · Why this is first

The owner tested the camera on the Barcode Station and found that **some
barcodes scan and some do not.** That is the first act of every tagging
operation — before the affix check, before the serial lookup, before
anything handoffs 38–40 built — and it is the one act in the product whose
failure is silent: the loop runs under *Point the camera at a tag* for ever,
and the operative cannot tell whether the label is bad, the phone is bad, or
the software is.

I read `BarcodeScanner.tsx` (230 lines) and this is what it is:

| | Today |
|---|---|
| Decoder | **none bundled.** The platform's `BarcodeDetector`, or nothing. |
| Where that exists | Chrome/Edge on Android (when the Play Services module is present on the device); Chrome on macOS. **Not Safari (no iPhone), not Firefox, not Chrome on Windows or Linux.** |
| Formats requested | `code_128`, `qr_code`, `code_39`, `ean_13`, `data_matrix` |
| Formats checked | **none** — `getSupportedFormats()` is never called; a device that honours three of the five silently drops two |
| Camera request | `facingMode: ideal environment` and nothing else — no resolution, no focus mode |
| Region decoded | the whole frame; the reticle is cosmetic |
| Acceptance | first result of the first frame that returns anything |
| Feedback on no decode | none, indefinitely |
| Tested on | a fake camera playing a rendered Cadra label (spec 40). **No real device appears in any report.** |

Cadra's own labels print **Code 128 and a QR, side by side, both encoding
the tag number**, at three sizes: the smallest has a **6 mm-tall Code 128
and a 7 mm QR** (`asset_tag_report.xml`). Both symbologies are in the list,
so on the right Android phone a Cadra label at a sensible distance reads.
That is the case spec 40 proves, and it is the only case anything proves.

**The design is the defect.** A scanner whose behaviour depends on which
phone it is running on cannot be made to work every time by fixing the
code around it. This handoff changes the engine.

---

## 1 · One decoder, every device

Bundle a decoder and make it **the** engine. Not a fallback behind the
platform detector — the engine, everywhere, so the same label through the
same lens produces the same result on every device, and a failure
reproduces instead of depending on whose phone it was.

Use a WebAssembly ZXing build behind the `BarcodeDetector` interface — the
`barcode-detector` ponyfill package (which wraps `zxing-wasm`) is the
obvious candidate, because the component already speaks that interface and
the change is the import, not the component. Evaluate it against
`zxing-wasm` direct and say in the report which you chose and why, with the
**bundle-size cost measured** (the WASM is in the region of a megabyte;
load it lazily when the camera starts, not on app boot, and show the number
before and after).

Consequences the report must state as measurements, not expectations:

- **iPhone Safari now scans.** Safari has `getUserMedia`; it lacked only the
  detector. Drive it on one.
- **Chrome on Windows and Linux now scans.** Drive one.
- **The "no built-in barcode detector" message is retired.** The only
  remaining reasons the camera cannot be used are *no camera*, *not https*,
  and *permission denied*. Each keeps its sentence.

Platform `BarcodeDetector` may stay as an *optional acceleration* only if
you gate it on `getSupportedFormats()` returning the full §2 list and prove
it agrees with the bundled decoder on the §6 corpus. I expect you will not
bother, and I would rather you did not: one engine is the point.

---

## 2 · The formats

Everything the decoder reads that a Nigerian government asset or its
manufacturer's label might carry:

**1D:** Code 128, Code 39, Code 93, Codabar, EAN-13, EAN-8, UPC-A, UPC-E,
ITF (Interleaved 2 of 5).
**2D:** QR, Data Matrix, PDF417, Aztec.

Cadra's own labels are Code 128 + QR and are the must-pass set. The rest
exist for the serial lookup (handoff 38), which reads whatever the
manufacturer printed.

**When both a Code 128 and a QR are in frame with the same value — a Cadra
label — accept once.** When two *different* values decode in one frame — a
laptop's underside — do not take the first: prefer the one inside the
reticle (§3), and if that still leaves two, show both and let the
operative tap. Guessing which of four barcodes on a laptop is the serial is
how a wrong serial gets looked up with a confident face.

---

## 3 · The camera is asked for what the label needs

- `width: { ideal: 1920 }, height: { ideal: 1080 }`, `facingMode:
  environment`, `focusMode: continuous` where the track supports it. Print
  in the report what each real device actually granted
  (`track.getSettings()`), because *ideal* is a request, not an outcome.
- **Zoom**, where `getCapabilities().zoom` exists — a control next to the
  torch. A 6 mm Code 128 at arm's length is small in a 1080p frame; 2× zoom
  is the difference between reading it and not.
- **Decode the reticle region, not the whole frame.** Crop the video frame
  to the reticle's rectangle on a canvas and hand *that* to the decoder.
  This is what makes the reticle true, and it is what makes §2's
  "prefer the one inside the reticle" possible. Keep the full-frame decode
  as a second pass only if the crop finds nothing, so a label held
  off-centre is still read.
- **Throttle.** WASM decode on a low-end Android is not free; decode at
  about 10 frames a second, not every animation frame, and measure the CPU
  cost on the weakest device you can get hold of.
- **A camera picker when there is more than one.** `enumerateDevices()`
  after permission; if it lists more than one video input, a select beside
  the Start button, remembering the last choice per browser. Today the
  component takes whatever `facingMode: environment` resolves to, which on
  a laptop is the only camera there is — and the demo machine (§6c) is a
  laptop whose built-in camera is **fixed-focus**. A macOS Continuity
  Camera (an iPhone acting as the Mac's webcam, with autofocus) or a USB
  webcam appears as a second device, and the operative needs to be able to
  choose it without a developer present.

---

## 4 · Acceptance that does not misread

1D barcodes have no error correction worth the name; a partial Code 39 read
can yield a valid, wrong string. 2D codes correct their own errors.

- **A 1D value is accepted when two consecutive decodes agree.** Not one.
- **A 2D value is accepted on one decode.**
- The accepted value is trimmed, and the format is passed up with it
  (`onDetected(value, format)`) so the affix dialog and the lookup can
  record what kind of code was read — the history event from handoff 51
  has a `scanned` field; a `scanned_format` beside it costs nothing and
  tells an auditor whether the number came off Cadra's label or a
  manufacturer's.

---

## 5 · Silence ends

The loop stops being silent:

- After **4 seconds** with no decode: *"Nothing read yet — move closer,
  hold steady, or try the light."* (torch and zoom controls visibly
  present).
- After **10 seconds**: the same, plus *"or type the code"* with the typed
  field focused and the camera left running.
- A decode that was **refused by §4's agreement rule** (two frames
  disagreed) says so briefly — *"Reading…"* — so a flicker of success is
  not mistaken for a failure.
- Camera stopped by the component after a successful read: the existing
  behaviour, unchanged.

The component's existing honesty about *why* the camera cannot start (no
camera, not https, denied) stays word for word.

---

## 6 · Proof — a corpus with a denominator, and real phones

"Every time" is a measurement or it is a hope.

### 6a · The corpus

A script, committed, that **generates** label images and **decodes** them
offline through the same bundled decoder (Node + the same WASM), printing a
table with a denominator:

- Every §2 symbology, encoding a realistic value for its kind (Cadra tag
  numbers for Code 128 and QR; plausible manufacturer serials for the
  rest).
- Cadra's three label sizes rendered **from the real report template**, not
  approximated — the 6 mm / 8 mm / 18 mm Code 128 and the 7 / 9 / 21 mm QR.
- Each at three rotations (0°, 15°, 90°), two scales (as printed, and
  shrunk to what a phone sees at arm's length), and three degradations
  (slight blur, low contrast, a 20 % crop of one edge to stand for a torn
  label).

Report decode rate per symbology and per Cadra size as **N of M**. Cadra's
own labels must be **M of M** at 0° and 90° undegraded; where anything else
falls short, say which cell and why — a 6 mm Code 128 at arm's length may
honestly be beyond a phone camera, and if so **that is a finding about the
label, not the scanner**, and the report says it so the owner can decide
whether the smallest label should carry the QR larger.

### 6b · Spec 40's fake camera, widened

The fake-capture mechanism already works. Extend spec 40 (or a sibling, 54)
to play a Cadra label of **each of the three sizes**, Code 128 side and QR
side, and assert the decoded value and format each time. Then one
manufacturer-style label per 1D family. Then the two-barcodes-two-values
frame, asserting the chooser appears.

### 6c · Real devices

A table in the report. Device, OS version, browser, what `getSettings()`
granted, and the result for each of the three Cadra sizes plus two
manufacturer labels you have to hand (a laptop underside and a monitor's
serial sticker will do). Photograph nothing — the table is the evidence; a
photo of a phone proves it was pointed.

**The first row is the demo device, and the owner has named it: a MacBook
Pro M1 Pro (2021), built-in camera, Chrome — and Safari in a second row,
since on a Mac both are one click away.** Three facts about that camera
decide the demo and must be measured, not assumed:

1. It is **fixed-focus**, tuned for a face at roughly half a metre. A label
   held close enough to be large in frame will be out of focus; held far
   enough to be sharp, it is small. There is a distance band where a given
   label size reads and outside it nothing does. **Find the band for each
   of the three Cadra sizes** — nearest and farthest distance at which the
   Code 128 reads, and separately the QR — and put the centimetres in the
   table. That number is what the owner will stand at on the day.
2. It has **no torch and no zoom**; those controls must simply be absent on
   it, not present and inert.
3. It is **user-facing**, so `facingMode: environment` does not match and
   the `ideal` fallback is what selects it. Confirm the preview is not
   mirrored in a way that confuses the operative lining up a label — the
   frame handed to the decoder is what matters and ZXing reads either
   orientation, but a mirrored preview makes a reticle hard to use.

Then **at minimum** one Android Chrome phone and one iPhone Safari, so the
report shows the same engine on the three kinds of device the tagging unit
will actually hold.

No real device, no "done". If you cannot get an iPhone, say so and the
owner will find one; do not mark the row from a simulator.

---

## 7 · What must not change

- **The typed field.** Always present, always accepts a hardware scanner's
  keyboard-wedge input. The industrial answer to "every time" is a
  Bluetooth scanner in the tagging unit's hand, and this field is its door.
- **The affix rule from handoff 39.** The expected number is still never
  pre-filled, never shown, never derived from the camera. The camera fills
  the field; a human presses the button.
- **The camera does not submit** (handoff 40). Unchanged.
- **Handoff 51's refusal record.** A scanned value that does not match is
  still recorded as refused; §4's format rides beside it, nothing else
  changes.

---

## 8 · Verification

1. Full suite, browser suite, with times. Bundle size before and after,
   and proof the WASM loads lazily (network trace: not fetched until the
   camera starts).
2. §6a's table, committed with the script that produces it.
3. §6b green, each size and side.
4. §6c's device table.
5. §5 timed: a frame with no barcode, the two sentences arriving at the
   stated seconds.
6. §3's `getSettings()` on each real device.
7. The standing sentence check — and this handoff's own §0 table is in
   scope: if any cell of my reading of the component is wrong, correct it
   in the report first. My greps have a record this month.

---

## 9 · The question for the report

**Is there a label Cadra prints today that a phone cannot be expected to
read?** Answer from §6a's numbers, size by size. If the smallest label's
Code 128 is honestly marginal, say so and say what the QR on the same label
achieves, because the fix to that is a template change the owner can make
before the demo and I need to know whether to write it.

**And specifically for the demo machine:** which Cadra label size, held at
what distance, reads first time on the MacBook's built-in camera — and
which do not read at all on it. If the answer is *only the 18 mm label, at
about 30 cm*, that is fine, but the owner needs to print that label and
know that distance before the room, not in it. If the built-in camera
cannot read the label the demo will use, say so plainly and name the
alternative (an iPhone as Continuity Camera through §3's picker, or a USB
webcam with autofocus) so the owner can bring one.
