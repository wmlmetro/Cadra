/**
 * Handoff 54 §6a — the corpus.
 *
 * Measures, offline, what the bundled decoder (zxing-wasm, the same package
 * and version the SPA's scanEngine.ts bundles) can read of every label Cadra
 * prints and of every symbology a manufacturer might print, and writes a
 * table with denominators to docs/handoffs/54-evidence/corpus-table.md.
 *
 * Cadra's own labels are NOT approximated: the Code 128 and QR PNGs are
 * fetched from the running Odoo's own renderer (`/report/barcode`, the same
 * public route the report template calls through `get_barcode_base64`) at the
 * template's per-size source resolutions, and displayed at the physical sizes
 * the template's cfg dict and the paperformat content boxes produce.
 *
 * Run: node e2e/corpus/run54.mjs        (or: cd e2e && npm run corpus:54)
 * Needs: the local stack up and test19 reachable (ODOO_ORIGIN to override).
 *
 * Exit codes: 0 = the invariant holds (every Cadra label size has at least
 * one side the engine reads as printed, straight on, undegraded) and no
 * cell that passed at the committed baseline (expected-pass.json) has
 * regressed; 1 = the invariant or the baseline failed (cells printed);
 * 2 = Odoo's /report/barcode was unreachable (the run STOPS rather than
 * substituting a different generator — handoff 54 §6a).
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { readBarcodes, writeBarcode } from "zxing-wasm/full";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const OUT_PATH = join(REPO_ROOT, "docs", "handoffs", "54-evidence", "corpus-table.md");

const ODOO_ORIGIN = process.env.ODOO_ORIGIN || "http://test19.localhost:8069";
const TAG = "HQ-GF-MR-FF-001";

/* ── The thirteen formats, exactly as scanEngine.ts publishes and asks ── */

const SCAN_FORMATS = [
  "code_128", "code_39", "code_93", "codabar",
  "ean_13", "ean_8", "upc_a", "upc_e", "itf",
  "qr_code", "data_matrix", "pdf417", "aztec",
];
const ZXING_FORMATS = [
  "Code128", "Code39", "Code93", "Codabar",
  "EAN13", "EAN8", "UPCA", "UPCE", "ITF",
  "QRCode", "DataMatrix", "PDF417", "Aztec",
];
const ZXING_TO_SCAN = Object.fromEntries(ZXING_FORMATS.map((z, i) => [z, SCAN_FORMATS[i]]));
// The same decode-variant tolerance scanEngine.ts carries.
Object.assign(ZXING_TO_SCAN, {
  ITF14: "itf", Code39Std: "code_39", Code39Ext: "code_39",
  CompactPDF417: "pdf417", AztecCode: "aztec",
  QRCodeModel1: "qr_code", QRCodeModel2: "qr_code",
});

/** The component's READER_OPTIONS, verbatim (scanEngine.ts). The handoff's
 *  §6a names four keys; the shipped component also passes
 *  `maxNumberOfSymbols: 4`, and measuring with anything but the component's
 *  exact options would measure a cousin. It changes nothing for these
 *  single-symbol frames. */
const READER_OPTIONS = {
  formats: [...ZXING_FORMATS],
  tryHarder: true,
  tryRotate: true,
  tryInvert: true,
  maxNumberOfSymbols: 4,
};

/* ── Physical geometry ──────────────────────────────────────────────────
 * From myservice_asset_register/views/asset_tag_report.xml: the per-size cfg
 * dict and the paperformat content boxes. The Code 128 has a row of its own
 * across the whole content box, so its printed width is the box's:
 *   bc_w = content_w
 * (Until 2026-10-25 the artwork had a brand column and the QR shared the
 * barcode's row; the baseline in expected-pass.json was measured on that.)
 */
const CADRA_SIZES = {
  small:    { contentW: 46, qr: 11, bch: 8,  bcw: 1000, bchpx: 80,  qrpx: 200 },
  standard: { contentW: 46, qr: 13, bch: 10, bcw: 1000, bchpx: 80,  qrpx: 200 },
  large:    { contentW: 92, qr: 26, bch: 20, bcw: 1600, bchpx: 110, qrpx: 360 },
};
for (const c of Object.values(CADRA_SIZES)) {
  c.bcWmm = c.contentW; // printed Code 128 width, mm
}

/** px per mm. "As printed": 300 dpi flatbed = 300/25.4 = 11.81. "Arm's
 *  length": a 1920 px frame spanning ~46 cm of scene (a phone at ~40 cm with
 *  ~60° horizontal FOV) = 1920/460 ≈ 4.2. */
const SCALES = { "as-printed": 11.81, "arms-length": 4.2 };

/** Manufacturer labels: 1D displayed 40 mm × 10 mm, 2D 15 mm square (handoff
 *  §6a sizing; pdf417 is displayed 15 mm square per that instruction, which
 *  stretches its native wide aspect — vertical stretch does not alter module
 *  widths). */
const ONE_D = new Set(["code_128", "code_39", "code_93", "codabar", "ean_13", "ean_8", "upc_a", "upc_e", "itf"]);

const MANUFACTURER = [
  { name: "code_39",     zxing: "Code39",     value: "SN 84729-A" },
  { name: "code_93",     zxing: "Code93",     value: "HP-5CD1234XYZ" },
  { name: "codabar",     zxing: "Codabar",    value: "A2043157B" },
  { name: "ean_13",      zxing: "EAN13",      value: "615123456789" },   // 615 = Nigeria; writer appends check digit
  { name: "ean_8",       zxing: "EAN8",       value: "6151234" },
  { name: "upc_a",       zxing: "UPCA",       value: "036000291452" },
  { name: "upc_e",       zxing: "UPCE",       value: "01234565" },
  { name: "itf",         zxing: "ITF",        value: "15400141288763" },
  { name: "pdf417",      zxing: "PDF417",     value: "S/N 5CD1234XYZ REV A01" },
  { name: "aztec",       zxing: "Aztec",      value: "ASSET 11385 NRS" },
  { name: "data_matrix", zxing: "DataMatrix", value: "5CD1234XYZ" },
];

const ROTATIONS = [0, 15, 90];
const DEGRADATIONS = ["none", "blur", "contrast", "torn"];

/* ── Sources ─────────────────────────────────────────────────────────── */

async function fetchOdooPng(params) {
  const url = `${ODOO_ORIGIN}/report/barcode?${new URLSearchParams(params)}`;
  let res;
  try {
    res = await fetch(url);
  } catch (e) {
    console.error(`FATAL: Odoo's /report/barcode is unreachable at ${ODOO_ORIGIN} (${e.message}).`);
    console.error("Handoff 54 §6a: stopping rather than substituting a different generator.");
    process.exit(2);
  }
  if (!res.ok) {
    console.error(`FATAL: ${url} answered ${res.status}. Stopping (no substitute generator).`);
    process.exit(2);
  }
  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf[0] !== 0x89 || buf[1] !== 0x50) {
    console.error(`FATAL: ${url} did not answer a PNG. Stopping.`);
    process.exit(2);
  }
  return buf;
}

/** Decode a pristine source at native resolution; the single result is the
 *  engine's own canonical answer (text AND published format) and is what
 *  every degraded attempt must reproduce exactly. */
async function pristineExpected(png, rowLabel) {
  const results = await readBarcodes(png, READER_OPTIONS);
  if (results.length !== 1) {
    throw new Error(`${rowLabel}: pristine source decoded to ${results.length} results, expected exactly 1`);
  }
  const r = results[0];
  const fmt = ZXING_TO_SCAN[r.format];
  if (!fmt) throw new Error(`${rowLabel}: pristine decode format ${r.format} maps to no published name`);
  return { text: r.text.trim(), format: fmt, zxingFormat: r.format };
}

async function buildRows() {
  const rows = [];

  // Cadra's own labels, from the real renderer at the template's source px.
  for (const [size, c] of Object.entries(CADRA_SIZES)) {
    const png = await fetchOdooPng({
      barcode_type: "Code128", value: TAG,
      width: String(c.bcw), height: String(c.bchpx), humanreadable: "0",
    });
    const exp = await pristineExpected(png, `cadra code_128 ${size}`);
    if (exp.text !== TAG) throw new Error(`Odoo Code128 for ${size} decoded as ${JSON.stringify(exp.text)}, not the tag`);
    rows.push({ label: `cadra code_128 ${size}`, cadra: true, png, expected: exp, wmm: c.bcWmm, hmm: c.bch,
      note: `src ${c.bcw}×${c.bchpx}px → ${c.bcWmm.toFixed(1)}×${c.bch} mm` });
  }
  for (const [size, c] of Object.entries(CADRA_SIZES)) {
    const png = await fetchOdooPng({
      barcode_type: "QR", value: TAG, width: String(c.qrpx), height: String(c.qrpx),
    });
    const exp = await pristineExpected(png, `cadra qr ${size}`);
    if (exp.text !== TAG) throw new Error(`Odoo QR for ${size} decoded as ${JSON.stringify(exp.text)}, not the tag`);
    rows.push({ label: `cadra qr ${size}`, cadra: true, png, expected: exp, wmm: c.qr, hmm: c.qr,
      note: `src ${c.qrpx}×${c.qrpx}px → ${c.qr}×${c.qr} mm` });
  }

  // Manufacturer symbologies, written by the same package's writer.
  for (const m of MANUFACTURER) {
    const w = await writeBarcode(m.value, { format: m.zxing, scale: -600 });
    if (w.error || !w.image) throw new Error(`writeBarcode ${m.zxing} failed: ${w.error}`);
    const png = new Uint8Array(await w.image.arrayBuffer());
    const exp = await pristineExpected(png, m.name);
    const is1d = ONE_D.has(m.name);
    rows.push({
      label: m.name, cadra: false, png, expected: exp,
      wmm: is1d ? 40 : 15, hmm: is1d ? 10 : 15,
      note: `input ${JSON.stringify(m.value)} → engine reads ${exp.format}:${JSON.stringify(exp.text)}`,
    });
  }
  return rows;
}

/* ── Rendering one attempt ───────────────────────────────────────────────
 * Composited on a CANVAS inside the page, not via an <img> and a
 * screenshot: Chromium's <img> rasterisation at fractional CSS sizes was
 * measured to lose decodes that the same pixels through
 * `drawImage(imageSmoothingQuality: "high")` keep (an Odoo Code 128
 * displayed at 675.6 px read through canvas and not through <img> on this
 * machine). The canvas path is deterministic and is the harness; the <img>
 * discrepancy was a harness artifact, not an engine difference. */

const PAGE_PAD = 24; // white margin around the rotated label, px

async function renderAttempt(page, dataUri, dispW, dispH, rotation, degradation, scaleName) {
  const blurPx = scaleName === "as-printed" ? 1 : 0.5;
  const b64 = await page.evaluate(async ({ dataUri, dispW, dispH, rotation, degradation, blurPx, pad }) => {
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUri; });
    const rad = (rotation * Math.PI) / 180;
    const w = Math.ceil(dispW * Math.abs(Math.cos(rad)) + dispH * Math.abs(Math.sin(rad))) + 2 * pad;
    const h = Math.ceil(dispW * Math.abs(Math.sin(rad)) + dispH * Math.abs(Math.cos(rad))) + 2 * pad;
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, w, h);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.translate(w / 2, h / 2);
    ctx.rotate(rad);
    if (degradation === "blur") ctx.filter = `blur(${blurPx}px)`;
    else if (degradation === "contrast") ctx.filter = "contrast(0.35) brightness(1.15)";
    if (degradation === "torn") {
      // 20 % torn off the LEFT edge: the leftmost fifth of the SYMBOL is
      // simply not there.
      const sx = img.width * 0.2;
      ctx.drawImage(img, sx, 0, img.width - sx, img.height,
        -dispW / 2 + dispW * 0.2, -dispH / 2, dispW * 0.8, dispH);
    } else {
      ctx.drawImage(img, -dispW / 2, -dispH / 2, dispW, dispH);
    }
    return c.toDataURL("image/png").split(",")[1];
  }, { dataUri, dispW, dispH, rotation, degradation, blurPx, pad: PAGE_PAD });
  return new Uint8Array(Buffer.from(b64, "base64"));
}

/* ── The run ─────────────────────────────────────────────────────────── */

function quantile(sorted, q) {
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

async function main() {
  const rows = await buildRows();
  const browser = await chromium.launch();
  const context = await browser.newContext({ deviceScaleFactor: 1 });
  const page = await context.newPage();

  const timings = [];
  const failures = [];

  for (const row of rows) {
    const dataUri = "data:image/png;base64," + Buffer.from(row.png).toString("base64");
    row.attempts = [];
    for (const [scaleName, ppmm] of Object.entries(SCALES)) {
      const dispW = row.wmm * ppmm;
      const dispH = row.hmm * ppmm;
      for (const rotation of ROTATIONS) {
        for (const degradation of DEGRADATIONS) {
          const shot = await renderAttempt(page, dataUri, dispW, dispH, rotation, degradation, scaleName);
          const t0 = performance.now();
          const results = await readBarcodes(shot, READER_OPTIONS);
          const ms = performance.now() - t0;
          timings.push(ms);
          const ok = results.some(
            (r) => (r.text ?? "").trim() === row.expected.text && ZXING_TO_SCAN[r.format] === row.expected.format,
          );
          const attempt = { scaleName, rotation, degradation, ok, ms };
          row.attempts.push(attempt);
          if (!ok) failures.push({ row: row.label, ...attempt });
        }
      }
    }
  }
  await browser.close();

  /* ── Score ── */
  const count = (attempts, pred) => {
    const sel = attempts.filter(pred);
    return { n: sel.filter((a) => a.ok).length, m: sel.length };
  };
  const nm = ({ n, m }) => `${n} of ${m}`;

  for (const row of rows) {
    row.overall = count(row.attempts, () => true);
    row.byDeg = {};
    for (const d of DEGRADATIONS) row.byDeg[d] = count(row.attempts, (a) => a.degradation === d);
    row.mustPass = count(row.attempts, (a) => a.degradation === "none" && (a.rotation === 0 || a.rotation === 90));
  }

  const sorted = [...timings].sort((a, b) => a - b);
  const median = quantile(sorted, 0.5);
  const p95 = quantile(sorted, 0.95);

  /* ── Table ── */
  const lines = [];
  lines.push("# Handoff 54 §6a — corpus table");
  lines.push("");
  lines.push(`Produced by \`e2e/corpus/run54.mjs\` on ${new Date().toISOString()} — re-run with \`node e2e/corpus/run54.mjs\` (stack up, \`${ODOO_ORIGIN}\` reachable).`);
  lines.push("");
  lines.push("## Assumptions and arithmetic");
  lines.push("");
  lines.push(`- Decoder: zxing-wasm (\`zxing-wasm/full\` in Node — the same WASM core version the SPA bundles via \`zxing-wasm/reader\`), reader options verbatim from \`scanEngine.ts\`: the 13 formats, \`tryHarder\`, \`tryRotate\`, \`tryInvert\`, \`maxNumberOfSymbols: 4\`.`);
  lines.push(`- Cadra barcode PNGs fetched from the real renderer: \`${ODOO_ORIGIN}/report/barcode\` at the template's cfg source sizes (Code 128: 1000×80 / 1000×80 / 1600×110 px; QR: 200 / 200 / 360 px), value \`${TAG}\`.`);
  lines.push("- Cadra printed sizes derived from `asset_tag_report.xml`'s cfg and the paperformat content boxes — Code 128 width = the content box's:");
  for (const [size, c] of Object.entries(CADRA_SIZES)) {
    lines.push(`  - ${size}: **${c.bcWmm.toFixed(1)} mm** × ${c.bch} mm (bar height = cfg \`bc\`); QR ${c.qr} mm square.`);
  }
  lines.push("- Manufacturer labels: written by the same package's `writeBarcode`, displayed 40 mm × 10 mm (1D) and 15 mm square (2D). Fitting PDF417 — a natively wide, many-module symbology — into 15 mm COMPRESSES its module width to ≈ 0.1 mm, which is why its row scores low; that is a fact about printing PDF417 at 15 mm, not about the engine.");
  lines.push("- Pixel scales (px per mm): **as printed** = 11.81 (300 dpi flatbed, 300/25.4); **arm's length** = 4.2 (a 1920 px frame spanning ~46 cm of scene — a phone at ~40 cm with ~60° horizontal FOV).");
  lines.push("- Per cell: 3 rotations (0°, 15°, 90°) × 2 scales × 4 degradation states = 24 attempts. Degradations: none; slight blur (`blur(1px)` as-printed, `blur(0.5px)` arm's-length); low contrast (`contrast(0.35) brightness(1.15)`); torn (20 % clipped off the left edge).");
  lines.push("- Frames composited by Playwright Chromium on a CANVAS (white background, `imageSmoothingQuality: \"high\"`, `ctx.filter` for blur/contrast, source-rect clip for torn) and decoded from the canvas PNG. Not via an `<img>` and a screenshot: Chromium's `<img>` rasterisation at fractional CSS sizes was measured to lose decodes the same pixels keep through canvas — a harness artifact that under-measured the engine.");
  lines.push("- A decode COUNTS only when text equals the expected value exactly AND the format maps to the expected published name. Expected per row = the engine's own decode of the pristine source (so check digits and expansions are the writer's: ean_13 `615123456789` → `6151234567891`; ean_8 `6151234` → `61512344`; upc_e `01234565` is answered expanded as `0012345000065`; **the upc_a label is answered as `ean_13` text `0036000291452` by this engine** when all 13 formats are requested — what the SPA will see too).");
  lines.push("- Must-pass column = 0° + 90°, undegraded, both scales (n of 4) — §6a's bar, reported per row. The script's own exit gate is different, because the small and standard Code 128 miss §6a's bar for a reason that belongs to the LABEL (see §9 below): it exits non-zero when any label size has NO side readable as printed, straight on, undegraded, or when a cell that passed at the committed baseline (`e2e/corpus/expected-pass.json`) regresses.");
  lines.push("");
  lines.push("## Results — N of M everywhere");
  lines.push("");
  lines.push("| row | overall | must-pass (0°+90° undegraded) | none | blur | low contrast | torn |");
  lines.push("|---|---|---|---|---|---|---|");
  for (const row of rows) {
    lines.push(`| ${row.label} | ${nm(row.overall)} | ${nm(row.mustPass)} | ${nm(row.byDeg.none)} | ${nm(row.byDeg.blur)} | ${nm(row.byDeg.contrast)} | ${nm(row.byDeg.torn)} |`);
  }
  lines.push("");
  lines.push("Row sources: " + rows.map((r) => `${r.label} (${r.note})`).join("; ") + ".");
  lines.push("");
  lines.push("## Failing cells");
  lines.push("");
  if (failures.length === 0) {
    lines.push(`None — ${rows.length * 24} of ${rows.length * 24} attempts decoded.`);
  } else {
    lines.push(`${failures.length} of ${rows.length * 24} attempts failed:`);
    lines.push("");
    for (const f of failures) {
      lines.push(`- ${f.row} · ${f.rotation}° · ${f.scaleName} · ${f.degradation}`);
    }
  }
  lines.push("");
  lines.push("## Decode time per frame");
  lines.push("");
  lines.push(`Across all ${timings.length} attempts on this machine (Apple M1 Pro — stands in for the CPU-cost measurement until a weak Android is driven): median ${median.toFixed(1)} ms, p95 ${p95.toFixed(1)} ms. The time is \`readBarcodes\` on the screenshot PNG (PNG decode included), per frame.`);
  lines.push("");
  lines.push("## §9 answer — from the numbers only");
  lines.push("");
  for (const [size] of Object.entries(CADRA_SIZES)) {
    for (const side of ["code_128", "qr"]) {
      const row = rows.find((r) => r.label === `cadra ${side} ${size}`);
      const arm = count(row.attempts, (a) => a.scaleName === "arms-length" && a.degradation === "none");
      const printed = count(row.attempts, (a) => a.scaleName === "as-printed" && a.degradation === "none");
      lines.push(`- **${size} ${side}** at arm's length undegraded: ${nm(arm)} rotations read (as-printed undegraded: ${nm(printed)}).`);
    }
  }
  lines.push("");
  const marginal = [];
  for (const row of rows) {
    const armNone = count(row.attempts, (a) => a.scaleName === "arms-length" && a.degradation === "none");
    const printedNone = count(row.attempts, (a) => a.scaleName === "as-printed" && a.degradation === "none");
    if (printedNone.n === printedNone.m && armNone.n < armNone.m) {
      marginal.push(`${row.label}: reads as printed (${nm(printedNone)}) but not at arm's length (${nm(armNone)})`);
    } else if (armNone.n === armNone.m) {
      for (const d of ["blur", "contrast", "torn"]) {
        const dArm = count(row.attempts, (a) => a.scaleName === "arms-length" && a.degradation === d);
        if (dArm.n === 0) marginal.push(`${row.label}: arm's-length undegraded reads (${nm(armNone)}) but ${d} at arm's length is ${nm(dArm)}`);
      }
    }
  }
  lines.push("Honestly marginal cells (pass clean, fail one step worse — or pass only as-printed):");
  lines.push("");
  if (marginal.length === 0) lines.push("- none");
  else for (const m of marginal) lines.push(`- ${m}`);
  lines.push("");

  mkdirSync(dirname(OUT_PATH), { recursive: true });
  writeFileSync(OUT_PATH, lines.join("\n"));
  console.log(lines.join("\n"));
  console.log(`\nWritten: ${OUT_PATH}`);

  /* ── Gates ──────────────────────────────────────────────────────────
   * Two, and neither is the handoff's literal "M of M at 0° and 90°":
   * that bar is not met by the LABEL (the small and standard Code 128 are
   * too dense for their printed size at these pixel scales — §9's finding,
   * which §6a itself anticipates: "a finding about the label, not the
   * scanner"). What the script can honestly gate:
   *
   * 1. INVARIANT — every Cadra label size has at least one side the
   *    engine reads as printed, straight on, undegraded. A label no
   *    machine can read in good conditions is a printing defect.
   * 2. BASELINE — every cell that passed when the baseline was committed
   *    (expected-pass.json beside this script) still passes. An engine or
   *    harness change that loses a cell fails loudly; a new pass is
   *    reported so the baseline can be advanced deliberately.
   */
  let failed = false;

  for (const size of Object.keys(CADRA_SIZES)) {
    const readable = ["code_128", "qr"].some((side) => {
      const row = rows.find((r) => r.label === `cadra ${side} ${size}`);
      return row.attempts.some((a) =>
        a.scaleName === "as-printed" && a.rotation === 0 && a.degradation === "none" && a.ok);
    });
    if (!readable) {
      console.error(`\nINVARIANT FAILED — the ${size} label has NO side the engine reads as printed, straight on, undegraded.`);
      failed = true;
    }
  }

  const BASELINE_PATH = join(__dirname, "expected-pass.json");
  const passing = [];
  for (const row of rows) {
    for (const a of row.attempts) {
      if (a.ok) passing.push(`${row.label} · ${a.rotation}° · ${a.scaleName} · ${a.degradation}`);
    }
  }
  let baseline = null;
  try { baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8")); } catch { /* first run */ }
  if (baseline === null) {
    writeFileSync(BASELINE_PATH, JSON.stringify(passing, null, 1) + "\n");
    console.log(`\nBaseline written: ${BASELINE_PATH} (${passing.length} passing cells).`);
  } else {
    const now = new Set(passing);
    const regressed = baseline.filter((c) => !now.has(c));
    const gained = passing.filter((c) => !baseline.includes(c));
    if (regressed.length) {
      console.error(`\nREGRESSED vs baseline (${regressed.length}):`);
      for (const c of regressed) console.error(`  ${c}`);
      failed = true;
    }
    if (gained.length) {
      console.log(`\nNew passes vs baseline (${gained.length}) — advance the baseline deliberately if real:`);
      for (const c of gained) console.log(`  ${c}`);
    }
    if (!regressed.length) console.log(`\nBaseline held: all ${baseline.length} baseline cells still pass.`);
  }

  if (failed) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
