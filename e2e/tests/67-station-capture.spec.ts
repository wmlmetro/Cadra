import { deflateSync } from "node:zlib";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { asPersona, personaToken } from "../fixtures/gates";

/**
 * Handoff 67 §5.1 — a capture at the Barcode Station, end to end, as the
 * people whose job it is, each signed in through the real sign-in page.
 *
 *   setup        as the administrator a room of its own (a fresh location,
 *                whose room code is read back) and a second room outside the
 *                campaign; as the Asset Controller a device bound to the
 *                capturer (the station), a block of three codes, and a
 *                campaign over the room; Identify from photo switched on with
 *                the stand-in provider `fake` (put back afterwards).
 *   the station  the capturer opens the Barcode Station — the Scan & print
 *                tab still draws its scan box — chooses Capture, the station
 *                says which device it is, the room outside the campaign is
 *                refused in words, the room is found by typing its room code
 *                (a handheld scanner types and presses Enter), a photo named
 *                `chair-01.png` is added and identified by the id it was
 *                synced under (the fake answers a chair, medium), the outcome
 *                is "found, not in SAP", the code's label is printed through
 *                the station's funnel and the print is RECORDED (the ledger
 *                says print_count 1), the code is typed back as the scanned
 *                label, GPS is ticked, and the capture is sent.
 *   the codes    the next code is voided as a spoiled label (reason given),
 *                the screen moves to the one after, and the capturer returns
 *                their own block — the ledger says void, and returned.
 *   the review   the reviewer accepts it in *Audit review*; the server holds
 *                it accepted, with the GPS it was sent.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/67-station-capture.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const REPO = path.resolve(__dirname, "../..");
const CREDS = process.env.E2E_PERSONAS ?? path.join(REPO, `docs/api/.personas.${TENANT}`);
const AI = "/api/v1/settings/ai-identify";
const WHERE = { latitude: 9.0579, longitude: 7.4951 };

function persona(key: string): { login: string; password: string } {
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key) return { login, password };
  }
  throw new Error(`${CREDS} has no "${key}" persona`);
}

async function signIn(page: Page, key: string) {
  const p = persona(key);
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

function uidOf(token: string): number {
  const part = token.split(".")[1];
  return Number(JSON.parse(Buffer.from(part, "base64url").toString("utf8")).uid);
}

// ── a real PNG, so the browser can open and redraw it ──

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(kind: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(kind, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function png(seed: number, w = 96, h = 72): Buffer {
  const rows: Buffer[] = [];
  for (let y = 0; y < h; y++) {
    const row = Buffer.alloc(1 + w * 3);
    for (let x = 0; x < w; x++) {
      row[1 + x * 3] = (seed * 37 + x * 11 + y * 7) % 256;
      row[2 + x * 3] = (seed * 13 + x * 3) % 256;
      row[3 + x * 3] = (y * 30 + seed) % 256;
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr), chunk("IDAT", deflateSync(Buffer.concat(rows))), chunk("IEND", Buffer.alloc(0)),
  ]);
}

async function ok(res: { status: number; body: any }, status: number, what: string) {
  expect(res.status, `${what}: ${JSON.stringify(res.body?.error ?? res.body).slice(0, 400)}`).toBe(status);
  return res.body.data;
}

test.describe.serial("handoff 67 — the station captures", () => {
  test.setTimeout(240_000);
  test.use({
    storageState: { cookies: [], origins: [] },
    geolocation: WHERE,
    permissions: ["geolocation"],
  });
  let was: any = null;

  test.beforeAll(async ({ api }) => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    const settings = await api.get("/api/v1/settings");
    test.skip(settings?.receipt_gated === true,
      "the receipt gates are on: this spec drives the station's capture with the gates off (handoff 67 §5)");
    was = await api.get(AI);
    const r = await api.raw("PATCH", AI, { provider: "fake", enabled: true, daily_cap: 100000 });
    expect(r.status, JSON.stringify(r.body)).toBe(200);
  });

  test.afterAll(async ({ api }) => {
    if (!was) return;
    await api.raw("PATCH", AI, { enabled: false, provider: was.provider, daily_cap: was.daily_cap });
    if (was.enabled) await api.raw("PATCH", AI, { enabled: true });
  });

  test("a capture at the station: room by its code, identify, print recorded, scan, send — and the reviewer accepts", async ({ page, api, browser }) => {
    // ── setup, over the API, as the person whose act each step is ──
    const u = Math.random().toString(36).slice(2, 8).toUpperCase();
    const room = await api.post<any>("/api/v1/locations", { name: `e2e67 room ${u}` });
    const elsewhere = await api.post<any>("/api/v1/locations", { name: `e2e67 elsewhere ${u}` });
    const roomCode: string = room.location_code ?? (await api.get<any>(`/api/v1/locations/${room.id}`)).location_code;
    const elsewhereCode: string = elsewhere.location_code ?? (await api.get<any>(`/api/v1/locations/${elsewhere.id}`)).location_code;
    expect(roomCode, "a location carries its room code (handoff 61)").toMatch(/^LOC-/);
    const capUid = uidOf(await personaToken("audit_capturer"));
    const revUid = uidOf(await personaToken("audit_reviewer"));
    const device = await ok(await asPersona("asset_controller", "POST", "/audit/devices",
      { name: `e2e67 station ${u}`, user_id: capUid }), 201, "register the station's device");
    const block = await ok(await asPersona("asset_controller", "POST", "/audit/blocks",
      { device_id: device.id, size: 3 }), 201, "issue the block");
    const codes: string[] = block.codes.map((c: any) => c.code);
    const campaign = await ok(await asPersona("asset_controller", "POST", "/audit/campaigns", {
      name: `e2e67 audit ${u}`, scope: [{ location_id: Number(room.id) }],
      capturer_ids: [capUid], reviewer_ids: [revUid],
    }), 201, "open the campaign");

    // The browser's print view is not scriptable: every frame's print() —
    // the label iframe's included — counts instead of opening a dialog.
    await page.addInitScript(() => {
      window.print = () => {
        const top = window.top as unknown as { __printed?: number };
        top.__printed = (top.__printed ?? 0) + 1;
      };
    });

    // ── the station, as the capturer ──
    await signIn(page, "audit_capturer");
    await page.evaluate(() => { try { localStorage.removeItem("cadra.station.mode"); } catch { /* fresh */ } });
    await page.goto(appPath("/tools/barcode"));
    // Scan & print is the default, and unchanged: its scan box draws.
    await expect(page.getByTestId("station-mode-scan")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("scan-box")).toBeVisible();
    await page.getByTestId("station-mode-capture").click();
    await expect(page.getByTestId("station-capture")).toBeVisible();

    await page.getByTestId("capture-campaign").selectOption(String(campaign.id));
    // The persona may be bound to devices earlier runs made; the station
    // says which one it is, and remembers the choice.
    const which = page.getByTestId("capture-device");
    if (await which.count()) await which.selectOption(String(device.id));
    await expect(page.getByTestId("station-device-line")).toHaveAttribute("data-device-code", device.device_code);
    await expect(page.getByTestId("station-device-line")).toContainText("bound to you");
    await expect(page.getByTestId("station-block-line")).toContainText("3 codes left");
    await expect(page.getByTestId("station-shift-rule")).toContainText("returns their block");

    // A room outside the campaign is refused in words.
    const roomBox = page.getByTestId("input-room-code");
    await roomBox.fill(elsewhereCode);
    await roomBox.press("Enter");
    await expect(page.getByTestId("room-scan-error")).toContainText("outside campaign");
    await expect(page.getByTestId("capture-room-chosen")).toHaveCount(0);
    // The campaign's room, by its code — typed and Enter, as a handheld does.
    await roomBox.fill(roomCode);
    await roomBox.press("Enter");
    await expect(page.getByTestId("capture-room-chosen")).toContainText(`e2e67 room ${u}`);

    // The photo, synced; then identified by the id it was synced under.
    const identified = page.waitForResponse((r) => r.url().endsWith("/api/v1/ai/identify") && r.request().method() === "POST");
    await page.getByTestId("input-capture-photo").setInputFiles({ name: "chair-01.png", mimeType: "image/png", buffer: png(67) });
    await expect(page.locator("[data-testid='capture-photo-thumb'][data-loaded='true']")).toHaveCount(1);
    await page.getByTestId("button-identify").click();
    const idRes = await identified;
    expect(idRes.status(), await idRes.text()).toBe(201);
    const sentForm = idRes.request().postData() ?? "";
    expect(sentForm, "identified by its audit photo id, not uploaded twice").toContain('name="audit_photo_id"');
    expect(sentForm).not.toContain('name="file"');
    await expect(page.getByTestId("identify-done")).toBeVisible();
    await expect(page.getByTestId("input-field-name")).toHaveValue("HIGH BACK EXECUTIVE SWIVEL CHAIR");
    await expect(page.getByTestId("ai-size-band")).toHaveAttribute("data-band", "medium");
    await expect(page.getByTestId("ai-size-band")).toContainText("Approximate size");

    // Found, not in SAP: the next code of the station's block.
    await page.getByTestId("outcome-in_neither").check();
    const category = page.getByTestId("select-field-category");
    if (!(await category.inputValue())) {
      const cats = await ok(await asPersona("audit_capturer", "GET", "/asset-categories"), 200, "read the classes");
      const c = cats.find((x: any) => x.identification_mode !== "record_only");
      await category.selectOption(String(c.id));
    }
    await page.getByTestId("select-field-condition").selectOption("good");
    const code = page.getByTestId("capture-next-code");
    await expect(code).toHaveText(codes[0]);

    // Print through the station's funnel, and the print is recorded.
    const recorded = page.waitForResponse((r) => r.url().endsWith("/api/v1/audit/codes/printed"));
    await page.getByTestId("button-print-code").click();
    const recRes = await recorded;
    expect(recRes.status(), await recRes.text()).toBe(200);
    expect(recRes.request().headers()["x-cadra-device"]).toBe(device.device_code);
    await expect(page.getByTestId("capture-code-printed")).toHaveAttribute("data-print-count", "1");
    expect(await page.evaluate(() => (window as unknown as { __printed?: number }).__printed ?? 0)).toBeGreaterThanOrEqual(1);
    const ledger = await ok(await asPersona("audit_capturer", "GET", `/audit/codes?code=${encodeURIComponent(codes[0])}`), 200, "read the code");
    expect(ledger).toHaveLength(1);
    expect(ledger[0].print_count).toBe(1);
    expect(ledger[0].state).toBe("reserved");

    // Scan the printed label back (typed), tick GPS, send.
    await expect(page.getByTestId("button-send-capture")).toBeDisabled();
    await page.getByTestId("input-scanned-label").fill(codes[0]);
    await page.getByTestId("input-capture-gps").check();
    await expect(page.getByTestId("button-send-capture")).toBeEnabled();
    await page.getByTestId("button-send-capture").click();
    const sent = page.getByTestId("capture-sent");
    await expect(sent).toBeVisible({ timeout: 20_000 });
    const captureId = (await sent.getAttribute("data-capture-id"))!;
    expect(captureId).toBeTruthy();
    await expect(page.getByTestId("capture-gps-note")).toHaveCount(0);

    const mine = await ok(await asPersona("audit_capturer", "GET", `/audit/captures/${captureId}`), 200, "read the capture");
    expect(mine.state).toBe("pending_review");
    expect(mine.outcome).toBe("in_neither");
    expect(mine.code).toBe(codes[0]);
    expect(mine.scanned_label).toBe(codes[0]);
    expect(mine.device.id).toBe(device.id);
    expect(mine.location.id).toBe(Number(room.id));
    expect(mine.ai_suggestion?.id, "the capture names the suggestion it used").toBeTruthy();
    expect(mine.gps?.latitude).toBeCloseTo(WHERE.latitude, 4);
    expect(mine.gps?.longitude).toBeCloseTo(WHERE.longitude, 4);

    // ── a spoiled label, then the block returned ──
    await page.getByTestId("outcome-in_neither").check();
    await expect(code).toHaveText(codes[1]);
    await page.getByTestId("button-spoil-code").click();
    await expect(page.getByTestId("button-spoil-confirm")).toBeDisabled();
    await page.getByTestId("input-spoil-reason").fill("e2e67 label torn at print");
    await page.getByTestId("button-spoil-confirm").click();
    await expect(page.getByTestId("station-print-notice")).toContainText("never reissued");
    await expect(code).toHaveText(codes[2]);
    const spoiled = await ok(await asPersona("audit_capturer", "GET", `/audit/codes?code=${encodeURIComponent(codes[1])}`), 200, "read the spoiled code");
    expect(spoiled[0].state).toBe("void");
    expect(spoiled[0].void_reason).toContain("e2e67 label torn at print");

    await page.getByTestId("button-return-block").click();
    await expect(page.getByTestId("return-block-confirm")).toContainText("never reissued");
    await page.getByTestId("input-return-block-reason").fill("e2e67 end of shift");
    await page.getByTestId("button-return-block-confirm").click();
    await expect(page.getByTestId("return-block-done")).toContainText("1 unused code voided");
    await expect(page.getByTestId("station-no-block")).toBeVisible();
    const returned = await ok(await asPersona("audit_capturer", "GET", `/audit/blocks/${block.id}`), 200, "read the block");
    expect(returned.state).toBe("returned");
    expect(returned.codes.find((c: any) => c.code === codes[0]).state).toBe("in_review");
    expect(returned.codes.find((c: any) => c.code === codes[2]).state).toBe("void");

    // ── the review, as the reviewer, in a browser of their own ──
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    try {
      const rev = await ctx.newPage();
      await signIn(rev, "audit_reviewer");
      await rev.getByRole("navigation", { name: "Primary navigation" }).getByText("Audit review", { exact: true }).click();
      await rev.getByTestId("review-campaign").selectOption(String(campaign.id));
      await rev.getByTestId("review-room").selectOption(String(room.id));
      const card = rev.getByTestId(`capture-card-${captureId}`);
      await expect(card).toBeVisible();
      await expect(card.getByTestId("capture-code")).toContainText(codes[0]);
      await card.getByTestId(`button-accept-${captureId}`).click();
      await expect(card).toHaveCount(0);
    } finally {
      await ctx.close();
    }
    const after = await ok(await asPersona("audit_reviewer", "GET", `/audit/captures/${captureId}`), 200, "read the capture");
    expect(after.state).toBe("accepted");
    expect(after.reviewed_by.id).toBe(revUid);
  });
});
