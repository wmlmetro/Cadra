import { test, expect, type Page } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { receive, readyToAffix } from "../fixtures/gates";
import { code128Svg } from "../../Frontend/artifacts/nrs-asset-register/src/lib/code128";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Handoff 40, in a browser: the camera in the confirm dialog.
 *
 * Report 39's dialog was built for a handheld scanner — the tag field is
 * auto-focused and the scanner's trailing Enter submits. That stays. This
 * spec proves the second way in: a Type / Camera toggle on the tag field
 * (and the serial field), the camera being the station's own
 * `BarcodeScanner`, and the one rule that makes it different from the
 * handheld — **a detection fills the field and does not submit.**
 *
 * How a browser with no camera is made to see a label: Chromium's fake
 * capture device (`--use-fake-device-for-media-stream`) can play a file
 * (`--use-file-for-fake-video-capture=<path>`, re-read each time a stream
 * is opened), and this spec writes into that file a JPEG of the label
 * Cadra would PRINT for the tag — `code128Svg`, the same encoder the label
 * printer uses — so the number is decoded off a real Code 128, not stubbed.
 * (By the platform's `BarcodeDetector` when this spec was written; by the
 * bundled zxing-wasm engine since handoff 54 — the frames and assertions
 * are engine-agnostic.) A blank frame stands for "the camera is on and
 * nothing is in front of it".
 *
 * Set `E2E_SHOTS=<dir>` to also save the screenshots report 40 refers to.
 */

const FAKE_CAMERA_FILE = join(tmpdir(), "cadra-e2e-fake-label.mjpeg");

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

const SCAN_INPUT = /NRS-LT|tag/i;

async function scan(page: Page, query: string) {
  const input = page.getByPlaceholder(SCAN_INPUT).first();
  await input.fill(query);
  await page.getByRole("button", { name: "Lookup" }).click();
}

async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/${name}.png`, fullPage: false });
}

async function createTaggedAsset(api: ApiClient, label: string) {
  const name = markedName(label);
  const serial = `E2ESN${Date.now()}${Math.floor(Math.random() * 1000)}`;
  // Handoff 58 §2: a label ISSUED and not yet affixed — with the receipt
  // gates on, the unit is received and walked to `tag_issued` by the
  // personas (`fixtures/gates.ts`); switch off, the create already is.
  const asset = await readyToAffix(api, await receive(api, {
    name, category_id: await api.firstCategoryId(), serial_number: serial,
  }));
  recordCreated({ kind: "asset", id: asset.id, name });
  return { id: asset.id as number, name, serial, tag: asset.tag as string | null };
}

/** Put a label in front of the fake camera: the label Cadra prints for
 *  `value`, or a blank frame when `value` is null. An `.mjpeg` is a run of
 *  JPEG frames, so one JPEG is a one-frame loop. Rendered by a throwaway
 *  page because the repo has no raster library and Playwright already has
 *  a renderer. */
async function putInFrontOfCamera(page: Page, value: string | null) {
  const render = await page.context().newPage();
  const svg = value ? code128Svg(value).replace("<svg ", '<svg width="520" height="160" ') : "";
  expect(value === null || svg.length > 0, `${value} must be Code 128 encodable`).toBe(true);
  await render.setViewportSize({ width: 640, height: 480 });
  await render.setContent(
    `<body style="margin:0;background:#fff;width:640px;height:480px;display:flex;align-items:center;justify-content:center">`
    + `<div style="width:520px;height:160px">${svg}</div></body>`,
  );
  writeFileSync(FAKE_CAMERA_FILE, await render.screenshot({ type: "jpeg", quality: 92 }));
  await render.close();
}

/** Streams the page opened, for proving the camera STOPS. Installed before
 *  the app loads; the app's `getUserMedia` call is unchanged. */
async function trackStreams(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __streams: MediaStream[] };
    w.__streams = [];
    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (c) => {
      const s = await orig(c);
      w.__streams.push(s);
      return s;
    };
  });
}

async function trackStates(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const w = window as unknown as { __streams: MediaStream[] };
    return w.__streams.flatMap((s) => s.getTracks().map((t) => t.readyState));
  });
}

async function openConfirmDialog(page: Page, tag: string) {
  await scan(page, tag);
  await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by tag/i, { timeout: 20_000 });
  await expect(page.getByTestId("button-confirm-affixed")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("button-confirm-affixed").click();
  const dialog = page.getByTestId("dialog-confirm-affixed");
  await expect(dialog).toBeVisible();
  return dialog;
}

/** Camera on under the field and started. The fake device needs no
 *  permission prompt; a real one prompts the first time (report 40).
 *  `expectRunning` waits for the Stop button — only right when nothing is in
 *  front of the lens: with a label there the platform decodes it within a
 *  frame or two and the scanner has stopped itself before Playwright looks. */
async function startCamera(dialog: ReturnType<Page["getByTestId"]>, field: "tag" | "serial", expectRunning = true) {
  await dialog.getByTestId(`affix-${field}-mode-camera`).click();
  const camera = dialog.getByTestId("affix-camera");
  await expect(camera).toHaveAttribute("data-for", field);
  await camera.getByRole("button", { name: "Start camera" }).click();
  if (expectRunning) await expect(camera.getByRole("button", { name: "Stop" })).toBeVisible({ timeout: 10_000 });
  return camera;
}

// ── The camera fills, the person confirms ───────────────────────────────────

test("a label read by the camera fills the field and is not submitted; the serial too; confirming then records the row", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "CamAffix");
  test.skip(!a.tag, "the created asset carries no tag number, so there is nothing to confirm");
  await trackStreams(page);

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const dialog = await openConfirmDialog(page, a.tag!);

  // Default is Type, the field focused, as in report 39.
  await expect(dialog.getByTestId("affix-tag-mode-type")).toHaveAttribute("aria-pressed", "true");
  await expect(dialog.getByTestId("input-affix-tag-number")).toBeFocused();
  await expect(dialog.getByTestId("affix-camera")).toHaveCount(0);

  // 1 · CAMERA ON, NOTHING IN FRONT OF IT. The dialog still carries the
  //     expected number nowhere, and the page behind is still blurred with
  //     the scan box emptied — the preview changed none of that.
  await putInFrontOfCamera(page, null);
  await startCamera(dialog, "tag");
  await expect(dialog.getByTestId("affix-tag-mode-camera")).toHaveAttribute("aria-pressed", "true");
  expect((await trackStates(page)).filter((s) => s === "live").length, "one live camera track").toBe(1);
  const markup = await dialog.evaluate((el) => el.outerHTML);
  expect(markup, "the dialog's markup must not carry the expected tag number, camera running").not.toContain(a.tag!);
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue("");
  await expect(dialog.getByTestId("button-submit-affixed")).toBeDisabled();
  await expect(page.getByTestId("scan-box")).toHaveValue("");
  await expect(page.getByTestId("lookup-tag-number-hidden")).toBeVisible();
  await expect(page.getByTestId("barcode-station")).toHaveAttribute("data-blurred", "true");
  // The dialog is still where it was: inside the viewport, footer reachable.
  const box = (await dialog.boundingBox())!;
  const vp = page.viewportSize()!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(vp.height);
  await expect(dialog.getByTestId("button-submit-affixed")).toBeInViewport();
  await shot(page, "01-camera-running-no-number");

  // 2 · THE LABEL. Stop, put it in front of the lens, start again (the fake
  //     device reads its file when a stream opens). The number is decoded
  //     off the Code 128 and lands in the field. NOT submitted: the dialog
  //     is still open, no request went, the row is untouched, and the
  //     toggle is back on Type with the cursor in the field.
  await dialog.getByTestId("affix-camera").getByRole("button", { name: "Stop" }).click();
  await putInFrontOfCamera(page, a.tag!);
  await dialog.getByTestId("affix-camera").getByRole("button", { name: "Start camera" }).click();
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(a.tag!, { timeout: 15_000 });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("affix-camera")).toHaveCount(0);
  await expect(dialog.getByTestId("affix-tag-mode-type")).toHaveAttribute("aria-pressed", "true");
  await expect(dialog.getByTestId("input-affix-tag-number")).toBeFocused();
  await expect(dialog.getByTestId("affix-refusal")).toHaveCount(0);
  await expect(dialog.getByTestId("affix-already")).toHaveCount(0);
  await expect(dialog.getByTestId("button-submit-affixed")).toBeEnabled();
  expect((await trackStates(page)).filter((s) => s === "live").length, "the scanner stopped itself on detection").toBe(0);
  let read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state, "nothing was posted").not.toBe("affixed");
  expect(read.tagging.affixed_at).toBeNull();
  await shot(page, "02-camera-filled-not-submitted");

  // 3 · THE SERIAL, the same way, into its own field.
  await putInFrontOfCamera(page, a.serial);
  await startCamera(dialog, "serial", false);
  await expect(dialog.getByTestId("input-affix-serial")).toHaveValue(a.serial, { timeout: 15_000 });
  await expect(dialog.getByTestId("input-affix-serial")).toBeFocused();
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(a.tag!);
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");

  // 4 · THE PERSON CONFIRMS. One tap.
  await dialog.getByTestId("input-affix-fitted-by").fill("E2E Camera Tagger");
  await dialog.getByTestId("button-submit-affixed").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  // THE ROW.
  const me = await api.whoami();
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).toBe("affixed");
  expect(read.tagging.is_tagged).toBe(true);
  expect(read.tagging.affixed_by_name).toBe("E2E Camera Tagger");
  expect(read.tagging.affixed_by?.id).toBe(me.id);
  await expect(page.getByTestId("tag-affixed-state")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("tag-affixed-by")).toHaveText("E2E Camera Tagger");
  expect((await trackStates(page)).every((s) => s === "ended"), "every stream ever opened is ended").toBe(true);
  await shot(page, "03-card-shows-affixed");
});

// ── The wrong label through the camera ──────────────────────────────────────

test("the wrong label read by the camera is refused in the server's words, the inputs kept; the right one typed then submits on Enter", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "CamWrong");
  test.skip(!a.tag, "the created asset carries no tag number");

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const dialog = await openConfirmDialog(page, a.tag!);

  // The neighbouring asset's label, say.
  const wrong = `${a.tag}9`;
  await putInFrontOfCamera(page, wrong);
  await startCamera(dialog, "tag", false);
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(wrong, { timeout: 15_000 });
  // Filled, shown, not sent — the person can see it is the wrong one…
  await expect(dialog.getByTestId("affix-refusal")).toHaveCount(0);
  let read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");
  // …and if they commit anyway, the server's sentence, as written.
  await dialog.getByTestId("button-submit-affixed").click();
  const refusal = dialog.getByTestId("affix-refusal");
  await expect(refusal).toBeVisible({ timeout: 20_000 });
  await expect(refusal).toContainText(
    `Scanned tag ${wrong} does not match the tag issued for this asset (${a.tag}). `
    + `The label on the asset is not the one Cadra issued for it.`,
  );
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(wrong);
  await expect(dialog.getByTestId("affix-tag-mode-type")).toHaveAttribute("aria-pressed", "true");
  await shot(page, "04-camera-wrong-tag-refused");
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");
  expect(read.tagging.affixed_at).toBeNull();

  // The handheld path, untouched: type (what a keyboard-wedge scanner does)
  // and the trailing Enter submits.
  await dialog.getByTestId("input-affix-tag-number").fill(a.tag!);
  await dialog.getByTestId("input-affix-tag-number").press("Enter");
  await expect(dialog).toBeHidden({ timeout: 20_000 });
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).toBe("affixed");
  expect(read.tagging.is_tagged).toBe(true);
});

// ── The typed path, and the camera's lifecycle ──────────────────────────────

test("camera off: auto-focus and Enter submits exactly as before; toggling the camera on and off returns focus", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "CamTyped");
  test.skip(!a.tag, "the created asset carries no tag number");

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const dialog = await openConfirmDialog(page, a.tag!);
  const field = dialog.getByTestId("input-affix-tag-number");
  await expect(field).toBeFocused();

  // Toggle on (not started) and off: focus comes back.
  await dialog.getByTestId("affix-tag-mode-camera").click();
  await expect(dialog.getByTestId("affix-camera")).toBeVisible();
  await expect(field).not.toBeFocused();
  await dialog.getByTestId("affix-tag-mode-type").click();
  await expect(dialog.getByTestId("affix-camera")).toHaveCount(0);
  await expect(field).toBeFocused();

  // Toggle on, STARTED, and off: the camera stops and focus comes back.
  await trackStreams(page); // init scripts apply from the next navigation…
  await page.reload();
  await expectShell(page);
  const d2 = await openConfirmDialog(page, a.tag!);
  await putInFrontOfCamera(page, null);
  await startCamera(d2, "tag");
  expect((await trackStates(page)).filter((s) => s === "live").length).toBe(1);
  await d2.getByTestId("affix-tag-mode-type").click();
  await expect(d2.getByTestId("affix-camera")).toHaveCount(0);
  await expect(d2.getByTestId("input-affix-tag-number")).toBeFocused();
  expect((await trackStates(page)).filter((s) => s === "live").length, "switching to Type stopped the camera").toBe(0);

  // The keyboard-wedge flow: characters then Enter.
  await d2.getByTestId("input-affix-tag-number").pressSequentially(a.tag!);
  await d2.getByTestId("input-affix-tag-number").press("Enter");
  await expect(d2).toBeHidden({ timeout: 20_000 });
  const read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).toBe("affixed");
});

test("closing the dialog with the camera running stops the camera", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "CamClose");
  test.skip(!a.tag, "the created asset carries no tag number");
  await trackStreams(page);

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const dialog = await openConfirmDialog(page, a.tag!);
  await putInFrontOfCamera(page, null);
  await startCamera(dialog, "tag");
  expect((await trackStates(page)).filter((s) => s === "live").length).toBe(1);
  await shot(page, "05-camera-running-before-close");

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("barcode-station")).not.toHaveAttribute("data-blurred", "true");
  expect((await trackStates(page)).every((s) => s === "ended"), "the camera stopped when the dialog closed").toBe(true);

  // Reopened, the dialog is back on Type with the camera gone.
  await page.getByTestId("button-confirm-affixed").click();
  const again = page.getByTestId("dialog-confirm-affixed");
  await expect(again).toBeVisible();
  await expect(again.getByTestId("affix-tag-mode-type")).toHaveAttribute("aria-pressed", "true");
  await expect(again.getByTestId("affix-camera")).toHaveCount(0);
  await expect(again.getByTestId("input-affix-tag-number")).toBeFocused();
  // Nothing was written by any of this.
  const read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");
});
