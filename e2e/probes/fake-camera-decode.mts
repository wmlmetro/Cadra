/**
 * Probe — can this machine's Playwright Chromium be shown a label it has no
 * camera to point at, and decode it for real?  (handoff 40, 2026-10-01)
 *
 *   cd e2e && node probes/fake-camera-decode.mts
 *
 * Launches Chromium with the fake capture device playing a file that does
 * NOT exist at launch, renders the Code 128 Cadra prints for a value with
 * the app's own encoder, writes it as the file, opens a stream and asks the
 * platform's BarcodeDetector to read it off the video. Prints what it found,
 * how long it took, and the track's settings. `docs/ENVIRONMENT-FACTS.md`
 * carries the three facts this established.
 */
import { chromium } from "@playwright/test";
import { writeFileSync, existsSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { code128Svg } from "../../Frontend/artifacts/nrs-asset-register/src/lib/code128.ts";

const ORIGIN = process.env.E2E_ORIGIN ?? "http://test19.localhost:8069";
const VALUE = process.argv[2] ?? "NRS-ACS-733";
const FAKE = join(tmpdir(), "cadra-probe-fake-label.mjpeg");
if (existsSync(FAKE)) unlinkSync(FAKE);

const browser = await chromium.launch({ args: [
  "--use-fake-device-for-media-stream",
  "--use-fake-ui-for-media-stream",
  `--use-file-for-fake-video-capture=${FAKE}`,
]});
const ctx = await browser.newContext({ viewport: { width: 640, height: 480 } });

// The label, rendered AFTER launch.
const render = await ctx.newPage();
await render.setContent(
  `<body style="margin:0;background:#fff;display:flex;align-items:center;justify-content:center;width:640px;height:480px">`
  + `<div style="width:520px;height:160px">${code128Svg(VALUE).replace("<svg ", '<svg width="520" height="160" ')}</div></body>`,
);
writeFileSync(FAKE, await render.screenshot({ type: "jpeg", quality: 90 }));
await render.close();

const page = await ctx.newPage();
await page.goto(`${ORIGIN}/app/`);
const result = await page.evaluate(async () => {
  const w = window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => { detect(v: HTMLVideoElement): Promise<{ rawValue: string; format: string }[]> } & { getSupportedFormats?: () => Promise<string[]> } };
  const secure = window.isSecureContext;
  if (!w.BarcodeDetector) return { secure, detector: false };
  const formats = await (w.BarcodeDetector as unknown as { getSupportedFormats(): Promise<string[]> }).getSupportedFormats();
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } });
  const v = document.createElement("video"); v.srcObject = stream; v.muted = true; v.playsInline = true;
  document.body.appendChild(v); await v.play();
  const det = new w.BarcodeDetector({ formats: ["code_128", "qr_code", "code_39", "ean_13", "data_matrix"] });
  const t0 = Date.now(); let found: { rawValue: string; format: string }[] = []; let tries = 0;
  while (Date.now() - t0 < 8000) {
    tries++;
    try { found = await det.detect(v); } catch { /* a frame mid-resize */ }
    if (found.length) break;
    await new Promise((r) => requestAnimationFrame(r));
  }
  const tracks = stream.getTracks().map((t) => ({ label: t.label, state: t.readyState, ...t.getSettings() }));
  stream.getTracks().forEach((t) => t.stop());
  return { secure, detector: true, formats, tries, ms: Date.now() - t0, found, tracks };
});
console.log(JSON.stringify(result, null, 1));
await browser.close();
