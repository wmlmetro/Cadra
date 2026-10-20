import { deflateSync } from "node:zlib";
import { readFileSync } from "node:fs";
import path from "node:path";
import { request as pwRequest } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { asPersona, personaToken } from "../fixtures/gates";

/**
 * Handoff 66 §8.7 — the audit in the room, in the browser, as the people
 * whose job it is, each signed in through the real sign-in page.
 *
 *   setup        as the administrator a room of its own (a fresh location);
 *                as the Asset Controller a device bound to the capturer, a
 *                block of three codes issued to it, and a campaign over the
 *                room with the capturer and the reviewer as its team — every
 *                step over the API, as the persona whose act it is.
 *   the review   the capturer syncs a photo and a capture found in neither
 *                register (outcome c) over the API, as the phone does, with
 *                the first code of the block printed and scanned. The
 *                reviewer opens *Audit review*, picks the campaign and the
 *                room, sees the photo and the confirmed fields, accepts; the
 *                server holds the capture accepted, by the reviewer, as an
 *                open exception.
 *   web capture  the capturer opens *Audit capture*, chooses the campaign,
 *                the device and the room, uploads a photo (a PNG made here),
 *                chooses *none of these*, gives a description, a class and a
 *                condition, types the code the screen shows as the scanned
 *                label, and sends; the server's `?mine=true` holds exactly
 *                that capture, waiting for review.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/66-the-audit-in-the-room.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const REPO = path.resolve(__dirname, "../..");
const CREDS = process.env.E2E_PERSONAS ?? path.join(REPO, `docs/api/.personas.${TENANT}`);

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

// ── a real PNG, different per seed, so the browser can open and redraw it ──

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

function png(seed: number, w = 64, h = 64): Buffer {
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

// ── the world each test stands in ──

type World = {
  u: string; room: number; campaign: number; device: { id: number; device_code: string };
  codes: string[]; category: { id: number; name: string }; capUid: number; revUid: number;
};

async function ok(res: { status: number; body: any }, status: number, what: string) {
  expect(res.status, `${what}: ${JSON.stringify(res.body?.error ?? res.body).slice(0, 400)}`).toBe(status);
  return res.body.data;
}

async function seed(api: { post: <T = any>(p: string, d: unknown) => Promise<T> }): Promise<World> {
  const u = Math.random().toString(36).slice(2, 8).toUpperCase();
  const room = await api.post<any>("/api/v1/locations", { name: `e2e66 room ${u}` });
  const capUid = uidOf(await personaToken("audit_capturer"));
  const revUid = uidOf(await personaToken("audit_reviewer"));
  const device = await ok(await asPersona("asset_controller", "POST", "/audit/devices",
    { name: `e2e66 phone ${u}`, user_id: capUid }), 201, "register the device");
  const block = await ok(await asPersona("asset_controller", "POST", "/audit/blocks",
    { device_id: device.id, size: 3 }), 201, "issue the block");
  const campaign = await ok(await asPersona("asset_controller", "POST", "/audit/campaigns", {
    name: `e2e66 audit ${u}`, scope: [{ location_id: Number(room.id) }],
    capturer_ids: [capUid], reviewer_ids: [revUid],
  }), 201, "open the campaign");
  const cats = await ok(await asPersona("audit_capturer", "GET", "/asset-categories"), 200, "read the classes");
  const category = cats.find((c: any) => c.identification_mode !== "record_only");
  expect(category, "a class with a label").toBeTruthy();
  return {
    u, room: Number(room.id), campaign: campaign.id, device: { id: device.id, device_code: device.device_code },
    codes: block.codes.map((c: any) => c.code), category: { id: category.id, name: category.name }, capUid, revUid,
  };
}

async function uploadPhoto(seedN: number): Promise<number> {
  const token = await personaToken("audit_capturer");
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN });
  try {
    const res = await ctx.post("/api/v1/audit/photos", {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      multipart: { file: { name: `e2e66-${seedN}.png`, mimeType: "image/png", buffer: png(seedN) }, source: "mobile" },
    });
    expect(res.status(), await res.text()).toBe(201);
    return (await res.json()).data.id;
  } finally {
    await ctx.dispose();
  }
}

test.describe("handoff 66 — the audit in the room", () => {
  test.setTimeout(180_000);
  test.use({ storageState: { cookies: [], origins: [] } });

  test("the reviewer sees the capture's photo and fields, and accepts it", async ({ page, api }) => {
    const w = await seed(api);
    const photoId = await uploadPhoto(Date.now() % 997);
    const captureId = crypto.randomUUID();
    const name = `e2e66 cabinet ${w.u}`;
    await ok(await asPersona("audit_capturer", "POST", "/audit/captures", {
      capture_id: captureId, campaign_id: w.campaign, location_id: w.room, outcome: "in_neither",
      code: w.codes[0], scanned_label: w.codes[0], photo_ids: [photoId],
      captured_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      fields: { name, category_id: w.category.id, condition: "fair", colour: "grey" },
    }, { "X-Cadra-Device": w.device.device_code }), 201, "sync the capture");

    await signIn(page, "audit_reviewer");
    await page.getByRole("navigation", { name: "Primary navigation" }).getByText("Audit review", { exact: true }).click();
    await page.getByTestId("review-campaign").selectOption(String(w.campaign));
    await page.getByTestId("review-room").selectOption(String(w.room));
    const card = page.getByTestId(`capture-card-${captureId}`);
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-state", "pending_review");
    await expect(card.getByTestId("capture-outcome")).toHaveText("Found, not in SAP");
    // The photo is drawn through the bearer token, not a bare <img src>.
    await expect(card.locator("[data-testid='capture-photo'][data-loaded='true']")).toHaveCount(1);
    await expect(card.getByTestId("capture-field-name")).toContainText(name);
    await expect(card.getByTestId("capture-field-category_id")).toContainText(w.category.name);
    await expect(card.getByTestId("capture-field-colour")).toContainText("grey");
    await expect(card.getByTestId("capture-code")).toContainText(w.codes[0]);
    await card.getByTestId(`button-accept-${captureId}`).click();
    // Accepted: it leaves the waiting list.
    await expect(card).toHaveCount(0);

    const after = await ok(await asPersona("audit_reviewer", "GET", `/audit/captures/${captureId}`), 200, "read the capture");
    expect(after.state).toBe("accepted");
    expect(after.reviewed_by.id).toBe(w.revUid);
    expect(after.exception_state).toBe("open");
    expect(after.code).toBe(w.codes[0]);
  });

  test("the capturer captures an item found in neither register at a desk", async ({ page, api }) => {
    const w = await seed(api);
    await signIn(page, "audit_capturer");
    await page.getByRole("navigation", { name: "Primary navigation" }).getByText("Audit capture", { exact: true }).click();
    await page.getByTestId("capture-campaign").selectOption(String(w.campaign));
    await page.getByTestId("capture-device").selectOption(String(w.device.id));
    await page.getByTestId("capture-room").selectOption(String(w.room));
    await expect(page.getByTestId("capture-room-chosen")).toContainText(`e2e66 room ${w.u}`);

    await page.getByTestId("input-capture-photo").setInputFiles({ name: "e2e66-desk.png", mimeType: "image/png", buffer: png(7) });
    await expect(page.locator("[data-testid='capture-photo-thumb'][data-loaded='true']")).toHaveCount(1);

    await page.getByTestId("outcome-in_neither").check();
    const name = `e2e66 filing cabinet ${w.u}`;
    await page.getByTestId("input-field-name").fill(name);
    await page.getByTestId("select-field-category").selectOption(String(w.category.id));
    await page.getByTestId("select-field-condition").selectOption("good");

    // The next code of this device's block, shown to be printed — then the
    // label is "scanned" by typing what it says.
    const code = page.getByTestId("capture-next-code");
    await expect(code).toHaveText(w.codes[0]);
    await expect(page.getByTestId("button-send-capture")).toBeDisabled();
    await page.getByTestId("input-scanned-label").fill(w.codes[0]);
    await expect(page.getByTestId("button-send-capture")).toBeEnabled();
    await page.getByTestId("button-send-capture").click();

    const sent = page.getByTestId("capture-sent");
    await expect(sent).toBeVisible();
    const captureId = await sent.getAttribute("data-capture-id");
    expect(captureId).toBeTruthy();
    await expect(page.getByTestId(`my-capture-${captureId}`)).toHaveAttribute("data-state", "pending_review");
    // The next item: the form is cleared and the next code is offered.
    await page.getByTestId("outcome-in_neither").check();
    await expect(code).toHaveText(w.codes[1]);

    const mine = await ok(await asPersona("audit_capturer", "GET",
      `/audit/captures?mine=true&campaign_id=${w.campaign}`), 200, "read my captures");
    expect(mine.map((c: any) => c.capture_id)).toEqual([captureId]);
    const c = mine[0];
    expect(c.outcome).toBe("in_neither");
    expect(c.state).toBe("pending_review");
    expect(c.code).toBe(w.codes[0]);
    expect(c.scanned_label).toBe(w.codes[0]);
    expect(c.name).toBe(name);
    expect(c.category.id).toBe(w.category.id);
    expect(c.condition).toBe("good");
    expect(c.photos).toHaveLength(1);
    expect(c.captured_by.id).toBe(w.capUid);
    expect(c.device.id).toBe(w.device.id);
    expect(c.location.id).toBe(w.room);
  });
});
