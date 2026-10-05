# Handoff 54 §6a — corpus table

Produced by `e2e/corpus/run54.mjs` on 2026-10-05T21:22:17.035Z — re-run with `node e2e/corpus/run54.mjs` (stack up, `http://test19.localhost:8069` reachable).

## Assumptions and arithmetic

- Decoder: zxing-wasm (`zxing-wasm/full` in Node — the same WASM core version the SPA bundles via `zxing-wasm/reader`), reader options verbatim from `scanEngine.ts`: the 13 formats, `tryHarder`, `tryRotate`, `tryInvert`, `maxNumberOfSymbols: 4`.
- Cadra barcode PNGs fetched from the real renderer: `http://test19.localhost:8069/report/barcode` at the template's cfg source sizes (Code 128: 400×80 / 500×80 / 700×110 px; QR: 100 / 120 / 220 px), value `HQ-GF-MR-FF-001`.
- Cadra printed sizes derived from `asset_tag_report.xml`'s cfg and the paperformat content boxes — Code 128 width = content − side − 2·pad − QR − pad:
  - small: 46 − 8 − 2×0.8 − 7 − 0.8 = **28.6 mm** × 6 mm (bar height = cfg `bc`); QR 7 mm square.
  - standard: 46 − 9 − 2×1 − 9 − 1 = **25.0 mm** × 8 mm (bar height = cfg `bc`); QR 9 mm square.
  - large: 92 − 16 − 2×2 − 21 − 2 = **49.0 mm** × 18 mm (bar height = cfg `bc`); QR 21 mm square.
- Manufacturer labels: written by the same package's `writeBarcode`, displayed 40 mm × 10 mm (1D) and 15 mm square (2D). Fitting PDF417 — a natively wide, many-module symbology — into 15 mm COMPRESSES its module width to ≈ 0.1 mm, which is why its row scores low; that is a fact about printing PDF417 at 15 mm, not about the engine.
- Pixel scales (px per mm): **as printed** = 11.81 (300 dpi flatbed, 300/25.4); **arm's length** = 4.2 (a 1920 px frame spanning ~46 cm of scene — a phone at ~40 cm with ~60° horizontal FOV).
- Per cell: 3 rotations (0°, 15°, 90°) × 2 scales × 4 degradation states = 24 attempts. Degradations: none; slight blur (`blur(1px)` as-printed, `blur(0.5px)` arm's-length); low contrast (`contrast(0.35) brightness(1.15)`); torn (20 % clipped off the left edge).
- Frames composited by Playwright Chromium on a CANVAS (white background, `imageSmoothingQuality: "high"`, `ctx.filter` for blur/contrast, source-rect clip for torn) and decoded from the canvas PNG. Not via an `<img>` and a screenshot: Chromium's `<img>` rasterisation at fractional CSS sizes was measured to lose decodes the same pixels keep through canvas — a harness artifact that under-measured the engine.
- A decode COUNTS only when text equals the expected value exactly AND the format maps to the expected published name. Expected per row = the engine's own decode of the pristine source (so check digits and expansions are the writer's: ean_13 `615123456789` → `6151234567891`; ean_8 `6151234` → `61512344`; upc_e `01234565` is answered expanded as `0012345000065`; **the upc_a label is answered as `ean_13` text `0036000291452` by this engine** when all 13 formats are requested — what the SPA will see too).
- Must-pass column = 0° + 90°, undegraded, both scales (n of 4) — §6a's bar, reported per row. The script's own exit gate is different, because the small and standard Code 128 miss §6a's bar for a reason that belongs to the LABEL (see §9 below): it exits non-zero when any label size has NO side readable as printed, straight on, undegraded, or when a cell that passed at the committed baseline (`e2e/corpus/expected-pass.json`) regresses.

## Results — N of M everywhere

| row | overall | must-pass (0°+90° undegraded) | none | blur | low contrast | torn |
|---|---|---|---|---|---|---|
| cadra code_128 small | 0 of 24 | 0 of 4 | 0 of 6 | 0 of 6 | 0 of 6 | 0 of 6 |
| cadra code_128 standard | 0 of 24 | 0 of 4 | 0 of 6 | 0 of 6 | 0 of 6 | 0 of 6 |
| cadra code_128 large | 9 of 24 | 2 of 4 | 3 of 6 | 3 of 6 | 3 of 6 | 0 of 6 |
| cadra qr small | 9 of 24 | 2 of 4 | 3 of 6 | 3 of 6 | 3 of 6 | 0 of 6 |
| cadra qr standard | 11 of 24 | 2 of 4 | 4 of 6 | 4 of 6 | 3 of 6 | 0 of 6 |
| cadra qr large | 18 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 0 of 6 |
| code_39 | 8 of 24 | 2 of 4 | 3 of 6 | 3 of 6 | 2 of 6 | 0 of 6 |
| code_93 | 11 of 24 | 2 of 4 | 4 of 6 | 4 of 6 | 3 of 6 | 0 of 6 |
| codabar | 9 of 24 | 2 of 4 | 3 of 6 | 3 of 6 | 3 of 6 | 0 of 6 |
| ean_13 | 9 of 24 | 2 of 4 | 3 of 6 | 3 of 6 | 3 of 6 | 0 of 6 |
| ean_8 | 18 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 0 of 6 |
| upc_a | 17 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 5 of 6 | 0 of 6 |
| upc_e | 18 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 0 of 6 |
| itf | 18 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 0 of 6 |
| pdf417 | 4 of 24 | 2 of 4 | 2 of 6 | 0 of 6 | 2 of 6 | 0 of 6 |
| aztec | 24 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 6 of 6 |
| data_matrix | 18 of 24 | 4 of 4 | 6 of 6 | 6 of 6 | 6 of 6 | 0 of 6 |

Row sources: cadra code_128 small (src 400×80px → 28.6×6 mm); cadra code_128 standard (src 500×80px → 25.0×8 mm); cadra code_128 large (src 700×110px → 49.0×18 mm); cadra qr small (src 100×100px → 7×7 mm); cadra qr standard (src 120×120px → 9×9 mm); cadra qr large (src 220×220px → 21×21 mm); code_39 (input "SN 84729-A" → engine reads code_39:"SN 84729-A"); code_93 (input "HP-5CD1234XYZ" → engine reads code_93:"HP-5CD1234XYZ"); codabar (input "A2043157B" → engine reads codabar:"A2043157B"); ean_13 (input "615123456789" → engine reads ean_13:"6151234567891"); ean_8 (input "6151234" → engine reads ean_8:"61512344"); upc_a (input "036000291452" → engine reads ean_13:"0036000291452"); upc_e (input "01234565" → engine reads upc_e:"0012345000065"); itf (input "15400141288763" → engine reads itf:"15400141288763"); pdf417 (input "S/N 5CD1234XYZ REV A01" → engine reads pdf417:"S/N 5CD1234XYZ REV A01"); aztec (input "ASSET 11385 NRS" → engine reads aztec:"ASSET 11385 NRS"); data_matrix (input "5CD1234XYZ" → engine reads data_matrix:"5CD1234XYZ").

## Failing cells

207 of 408 attempts failed:

- cadra code_128 small · 0° · as-printed · none
- cadra code_128 small · 0° · as-printed · blur
- cadra code_128 small · 0° · as-printed · contrast
- cadra code_128 small · 0° · as-printed · torn
- cadra code_128 small · 15° · as-printed · none
- cadra code_128 small · 15° · as-printed · blur
- cadra code_128 small · 15° · as-printed · contrast
- cadra code_128 small · 15° · as-printed · torn
- cadra code_128 small · 90° · as-printed · none
- cadra code_128 small · 90° · as-printed · blur
- cadra code_128 small · 90° · as-printed · contrast
- cadra code_128 small · 90° · as-printed · torn
- cadra code_128 small · 0° · arms-length · none
- cadra code_128 small · 0° · arms-length · blur
- cadra code_128 small · 0° · arms-length · contrast
- cadra code_128 small · 0° · arms-length · torn
- cadra code_128 small · 15° · arms-length · none
- cadra code_128 small · 15° · arms-length · blur
- cadra code_128 small · 15° · arms-length · contrast
- cadra code_128 small · 15° · arms-length · torn
- cadra code_128 small · 90° · arms-length · none
- cadra code_128 small · 90° · arms-length · blur
- cadra code_128 small · 90° · arms-length · contrast
- cadra code_128 small · 90° · arms-length · torn
- cadra code_128 standard · 0° · as-printed · none
- cadra code_128 standard · 0° · as-printed · blur
- cadra code_128 standard · 0° · as-printed · contrast
- cadra code_128 standard · 0° · as-printed · torn
- cadra code_128 standard · 15° · as-printed · none
- cadra code_128 standard · 15° · as-printed · blur
- cadra code_128 standard · 15° · as-printed · contrast
- cadra code_128 standard · 15° · as-printed · torn
- cadra code_128 standard · 90° · as-printed · none
- cadra code_128 standard · 90° · as-printed · blur
- cadra code_128 standard · 90° · as-printed · contrast
- cadra code_128 standard · 90° · as-printed · torn
- cadra code_128 standard · 0° · arms-length · none
- cadra code_128 standard · 0° · arms-length · blur
- cadra code_128 standard · 0° · arms-length · contrast
- cadra code_128 standard · 0° · arms-length · torn
- cadra code_128 standard · 15° · arms-length · none
- cadra code_128 standard · 15° · arms-length · blur
- cadra code_128 standard · 15° · arms-length · contrast
- cadra code_128 standard · 15° · arms-length · torn
- cadra code_128 standard · 90° · arms-length · none
- cadra code_128 standard · 90° · arms-length · blur
- cadra code_128 standard · 90° · arms-length · contrast
- cadra code_128 standard · 90° · arms-length · torn
- cadra code_128 large · 0° · as-printed · torn
- cadra code_128 large · 15° · as-printed · torn
- cadra code_128 large · 90° · as-printed · torn
- cadra code_128 large · 0° · arms-length · none
- cadra code_128 large · 0° · arms-length · blur
- cadra code_128 large · 0° · arms-length · contrast
- cadra code_128 large · 0° · arms-length · torn
- cadra code_128 large · 15° · arms-length · none
- cadra code_128 large · 15° · arms-length · blur
- cadra code_128 large · 15° · arms-length · contrast
- cadra code_128 large · 15° · arms-length · torn
- cadra code_128 large · 90° · arms-length · none
- cadra code_128 large · 90° · arms-length · blur
- cadra code_128 large · 90° · arms-length · contrast
- cadra code_128 large · 90° · arms-length · torn
- cadra qr small · 0° · as-printed · torn
- cadra qr small · 15° · as-printed · torn
- cadra qr small · 90° · as-printed · torn
- cadra qr small · 0° · arms-length · none
- cadra qr small · 0° · arms-length · blur
- cadra qr small · 0° · arms-length · contrast
- cadra qr small · 0° · arms-length · torn
- cadra qr small · 15° · arms-length · none
- cadra qr small · 15° · arms-length · blur
- cadra qr small · 15° · arms-length · contrast
- cadra qr small · 15° · arms-length · torn
- cadra qr small · 90° · arms-length · none
- cadra qr small · 90° · arms-length · blur
- cadra qr small · 90° · arms-length · contrast
- cadra qr small · 90° · arms-length · torn
- cadra qr standard · 0° · as-printed · torn
- cadra qr standard · 15° · as-printed · torn
- cadra qr standard · 90° · as-printed · torn
- cadra qr standard · 0° · arms-length · none
- cadra qr standard · 0° · arms-length · blur
- cadra qr standard · 0° · arms-length · contrast
- cadra qr standard · 0° · arms-length · torn
- cadra qr standard · 15° · arms-length · contrast
- cadra qr standard · 15° · arms-length · torn
- cadra qr standard · 90° · arms-length · none
- cadra qr standard · 90° · arms-length · blur
- cadra qr standard · 90° · arms-length · contrast
- cadra qr standard · 90° · arms-length · torn
- cadra qr large · 0° · as-printed · torn
- cadra qr large · 15° · as-printed · torn
- cadra qr large · 90° · as-printed · torn
- cadra qr large · 0° · arms-length · torn
- cadra qr large · 15° · arms-length · torn
- cadra qr large · 90° · arms-length · torn
- code_39 · 0° · as-printed · torn
- code_39 · 15° · as-printed · contrast
- code_39 · 15° · as-printed · torn
- code_39 · 90° · as-printed · torn
- code_39 · 0° · arms-length · none
- code_39 · 0° · arms-length · blur
- code_39 · 0° · arms-length · contrast
- code_39 · 0° · arms-length · torn
- code_39 · 15° · arms-length · none
- code_39 · 15° · arms-length · blur
- code_39 · 15° · arms-length · contrast
- code_39 · 15° · arms-length · torn
- code_39 · 90° · arms-length · none
- code_39 · 90° · arms-length · blur
- code_39 · 90° · arms-length · contrast
- code_39 · 90° · arms-length · torn
- code_93 · 0° · as-printed · torn
- code_93 · 15° · as-printed · torn
- code_93 · 90° · as-printed · torn
- code_93 · 0° · arms-length · none
- code_93 · 0° · arms-length · blur
- code_93 · 0° · arms-length · contrast
- code_93 · 0° · arms-length · torn
- code_93 · 15° · arms-length · contrast
- code_93 · 15° · arms-length · torn
- code_93 · 90° · arms-length · none
- code_93 · 90° · arms-length · blur
- code_93 · 90° · arms-length · contrast
- code_93 · 90° · arms-length · torn
- codabar · 0° · as-printed · torn
- codabar · 15° · as-printed · torn
- codabar · 90° · as-printed · torn
- codabar · 0° · arms-length · none
- codabar · 0° · arms-length · blur
- codabar · 0° · arms-length · contrast
- codabar · 0° · arms-length · torn
- codabar · 15° · arms-length · none
- codabar · 15° · arms-length · blur
- codabar · 15° · arms-length · contrast
- codabar · 15° · arms-length · torn
- codabar · 90° · arms-length · none
- codabar · 90° · arms-length · blur
- codabar · 90° · arms-length · contrast
- codabar · 90° · arms-length · torn
- ean_13 · 0° · as-printed · torn
- ean_13 · 15° · as-printed · torn
- ean_13 · 90° · as-printed · torn
- ean_13 · 0° · arms-length · none
- ean_13 · 0° · arms-length · blur
- ean_13 · 0° · arms-length · contrast
- ean_13 · 0° · arms-length · torn
- ean_13 · 15° · arms-length · none
- ean_13 · 15° · arms-length · blur
- ean_13 · 15° · arms-length · contrast
- ean_13 · 15° · arms-length · torn
- ean_13 · 90° · arms-length · none
- ean_13 · 90° · arms-length · blur
- ean_13 · 90° · arms-length · contrast
- ean_13 · 90° · arms-length · torn
- ean_8 · 0° · as-printed · torn
- ean_8 · 15° · as-printed · torn
- ean_8 · 90° · as-printed · torn
- ean_8 · 0° · arms-length · torn
- ean_8 · 15° · arms-length · torn
- ean_8 · 90° · arms-length · torn
- upc_a · 0° · as-printed · torn
- upc_a · 15° · as-printed · torn
- upc_a · 90° · as-printed · torn
- upc_a · 0° · arms-length · torn
- upc_a · 15° · arms-length · contrast
- upc_a · 15° · arms-length · torn
- upc_a · 90° · arms-length · torn
- upc_e · 0° · as-printed · torn
- upc_e · 15° · as-printed · torn
- upc_e · 90° · as-printed · torn
- upc_e · 0° · arms-length · torn
- upc_e · 15° · arms-length · torn
- upc_e · 90° · arms-length · torn
- itf · 0° · as-printed · torn
- itf · 15° · as-printed · torn
- itf · 90° · as-printed · torn
- itf · 0° · arms-length · torn
- itf · 15° · arms-length · torn
- itf · 90° · arms-length · torn
- pdf417 · 0° · as-printed · blur
- pdf417 · 0° · as-printed · torn
- pdf417 · 15° · as-printed · none
- pdf417 · 15° · as-printed · blur
- pdf417 · 15° · as-printed · contrast
- pdf417 · 15° · as-printed · torn
- pdf417 · 90° · as-printed · blur
- pdf417 · 90° · as-printed · torn
- pdf417 · 0° · arms-length · none
- pdf417 · 0° · arms-length · blur
- pdf417 · 0° · arms-length · contrast
- pdf417 · 0° · arms-length · torn
- pdf417 · 15° · arms-length · none
- pdf417 · 15° · arms-length · blur
- pdf417 · 15° · arms-length · contrast
- pdf417 · 15° · arms-length · torn
- pdf417 · 90° · arms-length · none
- pdf417 · 90° · arms-length · blur
- pdf417 · 90° · arms-length · contrast
- pdf417 · 90° · arms-length · torn
- data_matrix · 0° · as-printed · torn
- data_matrix · 15° · as-printed · torn
- data_matrix · 90° · as-printed · torn
- data_matrix · 0° · arms-length · torn
- data_matrix · 15° · arms-length · torn
- data_matrix · 90° · arms-length · torn

## Decode time per frame

Across all 408 attempts on this machine (Apple M1 Pro — stands in for the CPU-cost measurement until a weak Android is driven): median 1.9 ms, p95 8.2 ms. The time is `readBarcodes` on the screenshot PNG (PNG decode included), per frame.

## §9 answer — from the numbers only

- **small code_128** at arm's length undegraded: 0 of 3 rotations read (as-printed undegraded: 0 of 3).
- **small qr** at arm's length undegraded: 0 of 3 rotations read (as-printed undegraded: 3 of 3).
- **standard code_128** at arm's length undegraded: 0 of 3 rotations read (as-printed undegraded: 0 of 3).
- **standard qr** at arm's length undegraded: 1 of 3 rotations read (as-printed undegraded: 3 of 3).
- **large code_128** at arm's length undegraded: 0 of 3 rotations read (as-printed undegraded: 3 of 3).
- **large qr** at arm's length undegraded: 3 of 3 rotations read (as-printed undegraded: 3 of 3).

Honestly marginal cells (pass clean, fail one step worse — or pass only as-printed):

- cadra code_128 large: reads as printed (3 of 3) but not at arm's length (0 of 3)
- cadra qr small: reads as printed (3 of 3) but not at arm's length (0 of 3)
- cadra qr standard: reads as printed (3 of 3) but not at arm's length (1 of 3)
- cadra qr large: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
- code_39: reads as printed (3 of 3) but not at arm's length (0 of 3)
- code_93: reads as printed (3 of 3) but not at arm's length (1 of 3)
- codabar: reads as printed (3 of 3) but not at arm's length (0 of 3)
- ean_13: reads as printed (3 of 3) but not at arm's length (0 of 3)
- ean_8: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
- upc_a: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
- upc_e: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
- itf: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
- data_matrix: arm's-length undegraded reads (3 of 3) but torn at arm's length is 0 of 3
