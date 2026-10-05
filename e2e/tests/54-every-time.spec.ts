import { test, expect, type Page } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { decideScan } from "../../Frontend/artifacts/nrs-asset-register/src/lib/scanDecision";
import type { ScanHit } from "../../Frontend/artifacts/nrs-asset-register/src/lib/scanFormats";
import { writeBarcode } from "zxing-wasm/full";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Handoff 54, in a browser: one engine, every device, and silence ends.
 *
 * Spec 40 proved ONE case — a Cadra Code 128 through the platform's
 * detector on the one browser that had one. The engine is now bundled
 * (zxing-wasm behind `scanEngine.ts`), so this spec widens the proof the
 * way §6b asks: every Cadra label size, both sides; a manufacturer-style
 * label per 1D family; the two-values frame that becomes a choice instead
 * of a guess; the sentences that end the silent loop (§5, timed); and the
 * lazy wasm (§1 — fetched when the camera starts, never on page load).
 *
 * The §4 acceptance rules (1D twice, 2D once, "Reading…" between) are
 * driven DIRECTLY through `decideScan` — the component's own state machine,
 * imported — because a transient two-frames-disagree state through the fake
 * camera would be a race, not a proof. The fake camera here loops one
 * frame, so a 1D value's two agreeing decodes arrive ~100 ms apart and the
 * end-to-end path stays covered by every camera test below.
 *
 * Fake-camera mechanics as in spec 40, with this spec's OWN frame file so
 * the two files can run in parallel workers.
 */

const FAKE_CAMERA_FILE = join(tmpdir(), "cadra-e2e-54-fake-label.mjpeg");

test.use({
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      `--use-file-for-fake-video-capture=${FAKE_CAMERA_FILE}`,
    ],
  },
  permissions: ["camera"],
});

/* ── Frames ──────────────────────────────────────────────────────────── */

const FRAME_W = 640;
const FRAME_H = 480;

/** The template's per-size barcode sources (asset_tag_report.xml cfg):
 *  the real renderer's pixels, at the real per-size resolutions. §6a
 *  measured physical sizes; here the fake camera hands the component the
 *  pixels directly, so each size's ARTWORK is what varies. */
const CADRA_SIZES = {
  small: { bcw: 400, bch: 80, qrpx: 100 },
  standard: { bcw: 500, bch: 80, qrpx: 120 },
  large: { bcw: 700, bch: 110, qrpx: 220 },
} as const;

async function odooBarcodePngUri(page: Page, params: Record<string, string>) {
  // Same-origin fetch from inside the app: the e2e origin proxies
  // /report/barcode to Odoo exactly as every deployment does.
  const b64 = await page.evaluate(async (qs) => {
    const res = await fetch(`/report/barcode?${qs}`);
    if (!res.ok) throw new Error(`/report/barcode ${res.status}`);
    const buf = new Uint8Array(await res.arrayBuffer());
    let s = "";
    buf.forEach((b) => { s += String.fromCharCode(b); });
    return btoa(s);
  }, new URLSearchParams(params).toString());
  return `data:image/png;base64,${b64}`;
}

async function writtenPngUri(value: string, format: string, px = 440) {
  const w = await writeBarcode(value, { format: format as never, scale: -px });
  if (w.error || !w.image) throw new Error(`writeBarcode ${format}: ${w.error}`);
  const buf = Buffer.from(await w.image.arrayBuffer());
  return `data:image/png;base64,${buf.toString("base64")}`;
}

/** Put arbitrary content in front of the fake camera: a frame-sized white
 *  page holding `innerHtml`, screenshotted to the one-frame mjpeg loop.
 *  Rendered by a throwaway page, as spec 40 does. */
async function putFrame(page: Page, innerHtml: string) {
  const render = await page.context().newPage();
  await render.setViewportSize({ width: FRAME_W, height: FRAME_H });
  await render.setContent(
    `<body style="margin:0;background:#fff;width:${FRAME_W}px;height:${FRAME_H}px;`
    + `display:flex;align-items:center;justify-content:center;gap:24px">${innerHtml}</body>`,
  );
  writeFileSync(FAKE_CAMERA_FILE, await render.screenshot({ type: "jpeg", quality: 92 }));
  await render.close();
}

const img = (uri: string, w: number, h: number, style = "") =>
  `<img src="${uri}" style="width:${w}px;height:${h}px;${style}"/>`;

/* ── Station helpers ─────────────────────────────────────────────────── */

async function openStationCamera(page: Page) {
  await page.getByRole("button", { name: "Camera" }).click();
  await page.getByRole("button", { name: "Start camera" }).click();
}

async function stopCameraIfRunning(page: Page) {
  const stop = page.getByRole("button", { name: "Stop", exact: true });
  if (await stop.isVisible().catch(() => false)) await stop.click();
}

/** Drive one label through camera → engine → scan box, assert value and
 *  the format chip. The station flips back to Type on detection, so each
 *  round restarts the camera (the fake device re-reads its file when a
 *  stream opens). */
async function scanOne(page: Page, inner: string, value: string, formatLabel: string) {
  await putFrame(page, inner);
  await openStationCamera(page);
  await expect(page.getByTestId("scan-box")).toHaveValue(value, { timeout: 15_000 });
  await expect(page.getByTestId("scan-format")).toHaveText(`Camera read: ${formatLabel}.`);
}

/* ── §4, driven through the component's own state machine ────────────── */

const hit = (value: string, format: ScanHit["format"]): ScanHit => ({ value, format });

test.describe("§4 — acceptance that does not misread (decideScan, the component's own rules)", () => {
  test("a 2D value is accepted on one decode; a 1D value is not", () => {
    expect(decideScan([hit("NRS-1", "qr_code")], null).decision)
      .toEqual({ kind: "accept", hit: hit("NRS-1", "qr_code") });
    const first = decideScan([hit("NRS-1", "code_128")], null);
    expect(first.decision).toEqual({ kind: "reading" });
    expect(first.pending).toEqual(hit("NRS-1", "code_128"));
  });

  test("a 1D value is accepted when two consecutive decodes agree — and only then", () => {
    const pending = hit("NRS-1", "code_128");
    expect(decideScan([hit("NRS-1", "code_128")], pending).decision)
      .toEqual({ kind: "accept", hit: hit("NRS-1", "code_128") });
    // Same string read as a DIFFERENT symbology is not agreement: a partial
    // Code 39 that happens to equal a Code 128 read proves nothing twice.
    const cross = decideScan([hit("NRS-1", "code_39")], pending);
    expect(cross.decision).toEqual({ kind: "reading" });
    expect(cross.pending).toEqual(hit("NRS-1", "code_39"));
  });

  test("two frames disagreeing is refused and says Reading…, the newer read becoming the candidate", () => {
    const step = decideScan([hit("NRS-2", "code_128")], hit("NRS-1", "code_128"));
    expect(step.decision).toEqual({ kind: "reading" });
    expect(step.pending).toEqual(hit("NRS-2", "code_128"));
    // The agreeing twin of the NEW value then accepts.
    expect(decideScan([hit("NRS-2", "code_128")], step.pending).decision.kind).toBe("accept");
  });

  test("a blank frame keeps the pending read; two different values become a choice, never a guess", () => {
    const pending = hit("NRS-1", "code_128");
    expect(decideScan([], pending).pending).toEqual(pending);
    const two = decideScan([hit("A-1", "qr_code"), hit("B-2", "code_39")], pending);
    expect(two.decision.kind).toBe("choose");
    expect(two.pending).toBeNull();
  });
});

/* ── §1 — the engine loads when the camera starts, not before ────────── */

test("the wasm is not fetched on page load, is fetched when the camera starts, and the station then decodes with it", async ({ page }) => {
  const wasmRequests: string[] = [];
  page.on("request", (r) => { if (r.url().includes(".wasm")) wasmRequests.push(r.url()); });

  const tag = `NRS-LZ-${Date.now() % 100000}`;
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await expect(page.getByTestId("scan-box")).toBeVisible();
  expect(wasmRequests, "no wasm on page load — a person who never opens the camera never fetches it").toEqual([]);

  const uri = await odooBarcodePngUri(page, {
    barcode_type: "Code128", value: tag, width: "500", height: "80", humanreadable: "0" });
  await putFrame(page, img(uri, 500, 80));
  await openStationCamera(page);
  await expect(page.getByTestId("scan-box")).toHaveValue(tag, { timeout: 15_000 });
  expect(wasmRequests.length, "the engine was fetched when the camera started").toBeGreaterThanOrEqual(1);
  expect(wasmRequests[0]).toContain("zxing_reader");
  // The old platform-detector apology is retired: the camera panel rendered
  // (it decoded above), and nothing anywhere says "built-in barcode detector".
  await expect(page.locator("text=built-in barcode detector")).toHaveCount(0);
});

/* ── §6b — every Cadra size, both sides, through the real renderer ───── */

test("each Cadra label size decodes off its Code 128 side, at the template's own source resolution, and says so", async ({ page }) => {
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  for (const [size, cfg] of Object.entries(CADRA_SIZES)) {
    const tag = `NRS-C1${size[0].toUpperCase()}-${Date.now() % 100000}`;
    const uri = await odooBarcodePngUri(page, {
      barcode_type: "Code128", value: tag,
      width: String(cfg.bcw), height: String(cfg.bch), humanreadable: "0" });
    // Every size is shown filling the frame's width (600 of 640 px), which
    // is what a tagger does: hold the phone so the label fills the reticle.
    // What varies per size is the ARTWORK — the template's own source
    // resolution per size — which is the thing this test exercises; at its
    // native 400 px the small side does not survive the fake camera's JPEG,
    // the same density finding as the corpus table's small row.
    const w = 600;
    const h = Math.round(cfg.bch * (w / cfg.bcw));
    await scanOne(page, img(uri, w, h), tag, "Code 128");
    // Typing clears the claim: a typed string has no format.
    await page.getByTestId("scan-box").fill("typed-over");
    await expect(page.getByTestId("scan-format")).toHaveCount(0);
  }
});

test("each Cadra label size decodes off its QR side, at the template's own source resolution, and says so", async ({ page }) => {
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  for (const [size, cfg] of Object.entries(CADRA_SIZES)) {
    const tag = `NRS-QR${size[0].toUpperCase()}-${Date.now() % 100000}`;
    const uri = await odooBarcodePngUri(page, {
      barcode_type: "QR", value: tag,
      width: String(cfg.qrpx), height: String(cfg.qrpx) });
    await scanOne(page, img(uri, cfg.qrpx, cfg.qrpx), tag, "QR code");
  }
});

test("one manufacturer-style label per family decodes to its value and its format", async ({ page }) => {
  test.setTimeout(240_000);
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  // Values are what the ENGINE canonically reads (check digits completed,
  // UPC-E expanded, UPC-A answered as its EAN-13 superset) — §6a's table
  // records the same equivalences.
  const families: Array<[string, string, string, string, number, number]> = [
    // [writer format, written value, expected read, chip label, w, h]
    ["Code39", "SN 84729-A", "SN 84729-A", "Code 39", 500, 90],
    ["Code93", "HP-5CD1234XYZ", "HP-5CD1234XYZ", "Code 93", 500, 90],
    ["Codabar", "A2043157B", "A2043157B", "Codabar", 440, 90],
    ["EAN13", "615123456789", "6151234567891", "EAN-13", 400, 110],
    ["EAN8", "6151234", "61512344", "EAN-8", 330, 110],
    ["UPCA", "036000291452", "0036000291452", "EAN-13", 400, 110],
    ["UPCE", "01234565", "0012345000065", "UPC-E", 330, 110],
    ["ITF", "15400141288763", "15400141288763", "ITF", 500, 90],
    ["PDF417", "S/N 5CD1234XYZ REV A01", "S/N 5CD1234XYZ REV A01", "PDF417", 520, 170],
    ["Aztec", "ASSET 11385 NRS", "ASSET 11385 NRS", "Aztec", 200, 200],
    ["DataMatrix", "5CD1234XYZ", "5CD1234XYZ", "Data Matrix", 200, 200],
  ];
  for (const [format, value, read, label, w, h] of families) {
    const uri = await writtenPngUri(value, format, Math.max(w, h));
    await scanOne(page, img(uri, w, h), read, label);
  }
});

/* ── §2 — two values in one frame ────────────────────────────────────── */

test("two different values in one frame become a choice; the tap fills the box; Neither keeps scanning", async ({ page }) => {
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const a = await writtenPngUri("SN-AAA-111", "QRCode", 140);
  const b = await writtenPngUri("SN-BBB-222", "QRCode", 140);
  // Both inside the reticle's central region, as on a laptop's underside.
  await putFrame(page, img(a, 140, 140) + img(b, 140, 140));
  await openStationCamera(page);

  const chooser = page.getByTestId("scan-chooser");
  await expect(chooser).toBeVisible({ timeout: 15_000 });
  await expect(chooser.getByTestId("scan-choice")).toHaveCount(2);
  await expect(page.getByTestId("scan-box")).toHaveValue("", { timeout: 1000 });

  // "Neither" resumes scanning: the chooser clears, the camera stays up,
  // and the same frame brings it straight back.
  await chooser.getByTestId("scan-choice-dismiss").click();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
  await expect(page.getByTestId("scan-chooser")).toBeVisible({ timeout: 15_000 });

  // The tap is the decision: the tapped value lands, with its format.
  await page.getByTestId("scan-choice").filter({ hasText: "SN-BBB-222" }).click();
  await expect(page.getByTestId("scan-box")).toHaveValue("SN-BBB-222");
  await expect(page.getByTestId("scan-format")).toHaveText("Camera read: QR code.");
});

test("of two values, the one inside the reticle wins without asking", async ({ page }) => {
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const centre = await writtenPngUri("SN-CENTRE-1", "QRCode", 150);
  const edge = await writtenPngUri("SN-EDGE-2", "QRCode", 100);
  // The centre code sits in the reticle; the edge code hugs the frame's
  // left border, outside the 74%×38% crop.
  await putFrame(page,
    `<img src="${edge}" style="position:absolute;left:0;top:4px;width:84px;height:84px"/>`
    + `<img src="${centre}" style="width:150px;height:150px"/>`);
  await openStationCamera(page);
  await expect(page.getByTestId("scan-box")).toHaveValue("SN-CENTRE-1", { timeout: 15_000 });
  await expect(page.getByTestId("scan-chooser")).toHaveCount(0);
});

/* ── §5 — silence ends ───────────────────────────────────────────────── */

test("after 4 s with no decode a sentence arrives; after 10 s it offers typing, focuses the box and leaves the camera running", async ({ page }) => {
  test.setTimeout(90_000);
  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await openStationCamera(page);
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible({ timeout: 10_000 });

  // Early on: no hint yet (the clock starts after the first decode attempt,
  // so the engine's first-start compile is not counted as silence).
  await page.waitForTimeout(1_500);
  await expect(page.getByTestId("scanner-hint")).toHaveCount(0);

  const hint = page.getByTestId("scanner-hint");
  await expect(hint).toHaveText(
    "Nothing read yet — move closer, hold steady, or try the light.",
    { timeout: 7_000 });

  await expect(hint).toHaveText(
    "Nothing read yet — move closer, hold steady, or try the light — or type the code.",
    { timeout: 10_000 });
  // The typed field is focused for the operative's next move…
  await expect(page.getByTestId("scan-box")).toBeFocused();
  // …and the camera was NOT shut off on them.
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
  // What the camera actually granted is on the preview (§3's getSettings).
  await expect(page.getByTestId("scanner-granted")).toBeVisible();
  await stopCameraIfRunning(page);
});

/* ── The affix dialog: the format rides the POST onto the refusal record ── */

async function createTaggedAsset(api: ApiClient, label: string) {
  const name = markedName(label);
  const serial = `E2ESN${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const asset = await api.createAsset(name, { serial_number: serial });
  recordCreated({ kind: "asset", id: asset.id, name });
  return { id: asset.id as number, name, serial, tag: asset.tag as string | null };
}

test("a camera-read wrong tag is refused and the refusal record names the symbology it was read from", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "Scan54");
  test.skip(!a.tag, "the created asset carries no tag number");

  await putFrame(page, "");
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const input = page.getByPlaceholder(/NRS-LT|tag/i).first();
  await input.fill(a.tag!);
  await page.getByRole("button", { name: "Lookup" }).click();
  await expect(page.getByTestId("button-confirm-affixed")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("button-confirm-affixed").click();
  const dialog = page.getByTestId("dialog-confirm-affixed");
  await expect(dialog).toBeVisible();

  // The neighbouring asset's label, read off a QR by the camera. NOT built
  // by appending to the real tag: the dialog's no-leak assertion below
  // checks the markup does not contain the expected number, and a wrong
  // value that embeds it as a prefix would fail that check against the
  // field's own legitimate contents.
  const wrong = `${a.tag!.slice(0, -1)}${a.tag!.endsWith("9") ? "8" : "9"}X`;
  const uri = await writtenPngUri(wrong, "QRCode", 160);
  await putFrame(page, img(uri, 160, 160));
  await dialog.getByTestId("affix-tag-mode-camera").click();
  await dialog.getByTestId("affix-camera").getByRole("button", { name: "Start camera" }).click();
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(wrong, { timeout: 15_000 });
  // The dialog says what kind of code filled the field…
  await expect(dialog.getByTestId("affix-tag-format")).toHaveText("Camera read: QR code.");
  // …and never the expected number (handoff 39's rule, unchanged).
  expect(await dialog.evaluate((el) => el.outerHTML)).not.toContain(a.tag!);

  await dialog.getByTestId("button-submit-affixed").click();
  await expect(dialog.getByTestId("affix-refusal")).toBeVisible({ timeout: 20_000 });

  // The record: refused, with the symbology beside the refused value.
  const history = await api.get<any>(`/api/v1/assets/${a.id}/history`);
  const refusals = history.events.filter((e: any) => e.type === "affix_refused");
  expect(refusals.length).toBe(1);
  expect(refusals[0].detail.scanned).toBe(wrong);
  expect(refusals[0].detail.scanned_format).toBe("qr_code");

  // Typing over the camera's read clears the claim; the typed retry that
  // then succeeds carries no format, exactly as a keyboard wedge would.
  await dialog.getByTestId("input-affix-tag-number").fill(a.tag!);
  await expect(dialog.getByTestId("affix-tag-format")).toHaveCount(0);
  await dialog.getByTestId("input-affix-tag-number").press("Enter");
  await expect(dialog).toBeHidden({ timeout: 20_000 });
  const read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).toBe("affixed");
});
