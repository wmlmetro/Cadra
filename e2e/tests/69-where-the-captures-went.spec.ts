import { deflateSync } from "node:zlib";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { request as pwRequest } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { asPersona, personaToken } from "../fixtures/gates";

/**
 * Handoff 69 §4 — the review page finds every capture, in the browser, as
 * the people whose job it is, each signed in through the real sign-in page.
 *
 *   setup        as the administrator two rooms of their own; as the Asset
 *                Controller a device bound to the capturer, a block of five
 *                codes, campaign B over room B with the reviewer named, and
 *                campaign A over room A with NO reviewer named; as the
 *                capturer (the phone, over the API) capture 1 in B carrying
 *                an old FIRS tag, capture 2 in A, and a third whose scanned
 *                label is not its code — refused, and kept as a refused sync.
 *   find         the reviewer, on Audit review, finds capture 1 by its
 *                capture_id (it names its campaign, open, its device and when
 *                it was received, and offers to review it here — which opens
 *                it on the page, the card naming its device and received
 *                time), finds it again by its old tag written another way
 *                (lower case, backslashes), finds capture 2 by its printed
 *                code and is told in words that nobody reviews on campaign A,
 *                and is told where else to look for an ID nobody holds.
 *   campaigns    the Asset Controller, on Audit campaigns, sees campaign A's
 *                warning ("1 capture waits and no reviewer is named.") and
 *                not B's; finds capture 1 and is told who its reviewer is;
 *                follows the not-found sentence's link to Devices and codes,
 *                where *Refused syncs* holds the refused capture with the
 *                sentence the phone was sent.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/69-where-the-captures-went.spec.ts)
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

// ── a real PNG, different per seed ──

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

function png(seed: number, w = 48, h = 48): Buffer {
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

async function uploadPhoto(seedN: number): Promise<number> {
  const token = await personaToken("audit_capturer");
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN });
  try {
    const res = await ctx.post("/api/v1/audit/photos", {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      multipart: { file: { name: `e2e69-${seedN}.png`, mimeType: "image/png", buffer: png(seedN) }, source: "mobile" },
    });
    expect(res.status(), await res.text()).toBe(201);
    return (await res.json()).data.id;
  } finally {
    await ctx.dispose();
  }
}

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

type World = {
  u: string;
  device: { id: number; name: string; device_code: string };
  campA: { id: number; name: string };
  campB: { id: number; name: string };
  roomB: number;
  cap1: string; cap2: string; refusedId: string;
  code2: string; oldTag: string;
  reviewerName: string;
  refusalMessage: string;
};

let w: World;

test.describe.serial("handoff 69 — where the captures went", () => {
  test.setTimeout(180_000);
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeAll(async ({ api }) => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    const u = Math.random().toString(36).slice(2, 8).toUpperCase();
    const roomA = await api.post<any>("/api/v1/locations", { name: `e2e69 room A ${u}` });
    const roomB = await api.post<any>("/api/v1/locations", { name: `e2e69 room B ${u}` });
    const capUid = uidOf(await personaToken("audit_capturer"));
    const revUid = uidOf(await personaToken("audit_reviewer"));
    const device = await ok(await asPersona("asset_controller", "POST", "/audit/devices",
      { name: `e2e69 phone ${u}`, user_id: capUid }), 201, "register the device");
    const block = await ok(await asPersona("asset_controller", "POST", "/audit/blocks",
      { device_id: device.id, size: 5 }), 201, "issue the block");
    const codes: string[] = block.codes.map((c: any) => c.code);
    const campB = await ok(await asPersona("asset_controller", "POST", "/audit/campaigns", {
      name: `e2e69 reviewed ${u}`, scope: [{ location_id: Number(roomB.id) }],
      capturer_ids: [capUid], reviewer_ids: [revUid],
    }), 201, "open campaign B");
    const campA = await ok(await asPersona("asset_controller", "POST", "/audit/campaigns", {
      name: `e2e69 nobody reviews ${u}`, scope: [{ location_id: Number(roomA.id) }],
      capturer_ids: [capUid], reviewer_ids: [],
    }), 201, "open campaign A with no reviewer");
    const cats = await ok(await asPersona("audit_capturer", "GET", "/asset-categories"), 200, "read the classes");
    const category = cats.find((c: any) => c.identification_mode !== "record_only");
    expect(category, "a class with a label").toBeTruthy();
    const dev = { "X-Cadra-Device": device.device_code };
    const oldTag = `FIRS/ABJ/E2E69/${u}`;

    const cap1 = crypto.randomUUID();
    await ok(await asPersona("audit_capturer", "POST", "/audit/captures", {
      capture_id: cap1, campaign_id: campB.id, location_id: Number(roomB.id), outcome: "in_neither",
      code: codes[0], scanned_label: codes[0], photo_ids: [await uploadPhoto(1)], captured_at: now(),
      fields: { name: `e2e69 desk ${u}`, category_id: category.id, condition: "good", legacy_asset_code: oldTag },
    }, dev), 201, "sync capture 1 (campaign B)");
    const cap2 = crypto.randomUUID();
    await ok(await asPersona("audit_capturer", "POST", "/audit/captures", {
      capture_id: cap2, campaign_id: campA.id, location_id: Number(roomA.id), outcome: "in_neither",
      code: codes[1], scanned_label: codes[1], photo_ids: [await uploadPhoto(2)], captured_at: now(),
      fields: { name: `e2e69 chair ${u}`, category_id: category.id, condition: "fair" },
    }, dev), 201, "sync capture 2 (campaign A)");

    // A capture the server refuses: the scanned label is not the code.
    const refusedId = crypto.randomUUID();
    const refused = await asPersona("audit_capturer", "POST", "/audit/captures", {
      capture_id: refusedId, campaign_id: campB.id, location_id: Number(roomB.id), outcome: "in_neither",
      code: codes[2], scanned_label: `WRONG-${u}`, photo_ids: [await uploadPhoto(3)], captured_at: now(),
      fields: { name: `e2e69 shelf ${u}`, category_id: category.id, condition: "good" },
    }, dev);
    expect(refused.status, JSON.stringify(refused.body).slice(0, 400)).toBeGreaterThanOrEqual(400);
    expect(refused.status).toBeLessThan(500);
    const refusalMessage: string = refused.body?.error?.message;
    expect(refusalMessage, "the refusal is a sentence").toBeTruthy();
    // The server kept it (handoff 69 C2), with the sentence the phone was sent.
    const kept = await ok(await asPersona("asset_controller", "GET",
      `/audit/refusals?capture_id=${refusedId}`), 200, "read the refusal");
    expect(kept).toHaveLength(1);
    expect(kept[0].message).toBe(refusalMessage);
    expect(kept[0].http_status).toBe(refused.status);
    expect(kept[0].device?.id).toBe(device.id);

    // The capture answer names the campaign's reviewers (contract §1).
    const one = await ok(await asPersona("asset_controller", "GET", `/audit/captures?q=${cap1}`), 200, "find capture 1");
    expect(one.map((c: any) => c.capture_id)).toEqual([cap1]);
    expect(one[0].campaign.state).toBe("open");
    expect(one[0].campaign.reviewers.map((r: any) => r.id)).toEqual([revUid]);
    const camps = await ok(await asPersona("asset_controller", "GET", "/audit/campaigns?state=open"), 200, "read campaigns");
    expect(camps.find((c: any) => c.id === campA.id)?.reviewers_active).toBe(0);
    expect(camps.find((c: any) => c.id === campB.id)?.reviewers_active).toBe(1);

    w = {
      u, device: { id: device.id, name: device.name, device_code: device.device_code },
      campA: { id: campA.id, name: campA.name }, campB: { id: campB.id, name: campB.name },
      roomB: Number(roomB.id), cap1, cap2, refusedId, code2: codes[1], oldTag,
      reviewerName: one[0].campaign.reviewers[0].name, refusalMessage,
    };
  });

  test("the reviewer finds a capture by its ID, its old tag and its code — and is told who reviews what", async ({ page }) => {
    await signIn(page, "audit_reviewer");
    await page.getByRole("navigation", { name: "Primary navigation" }).getByText("Audit review", { exact: true }).click();
    const box = page.getByTestId("input-find-capture");

    // By capture_id: where it is, how it got there, and an offer to review it.
    await box.fill(w.cap1);
    await page.getByTestId("button-find-capture").click();
    const found = page.getByTestId(`found-capture-${w.cap1}`);
    await expect(found).toBeVisible();
    await expect(found).toHaveAttribute("data-reviewer", "true");
    await expect(found.getByTestId("found-campaign")).toHaveText(w.campB.name);
    await expect(found.getByTestId("found-campaign-state")).toHaveText("Open");
    await expect(found.getByTestId("found-device")).toHaveText(w.device.name);
    await expect(found.getByTestId("found-received")).not.toHaveText("—");
    await expect(found.getByTestId("found-not-a-reviewer")).toHaveCount(0);
    await found.getByTestId(`button-review-found-${w.cap1}`).click();
    await expect(page.getByTestId("review-campaign")).toHaveValue(String(w.campB.id));
    await expect(page.getByTestId("review-room")).toHaveValue(String(w.roomB));
    const card = page.getByTestId(`capture-card-${w.cap1}`);
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-focused", "true");
    // B4: the device and the received-at time on the card.
    await expect(card.getByTestId("capture-device")).toHaveText(w.device.name);
    await expect(card.getByTestId("capture-received")).not.toHaveText("—");
    await expect(card.getByTestId("capture-provenance")).toContainText("received");
    // B1: the count says how many of how many.
    await expect(page.getByTestId("review-count")).toContainText(/Showing 1 of 1 waiting/);

    // By the old tag, written as somebody might type it.
    await box.fill(w.oldTag.toLowerCase().replace(/\//g, "\\"));
    await page.getByTestId("button-find-capture").click();
    await expect(page.getByTestId(`found-capture-${w.cap1}`)).toBeVisible();

    // By the printed code, in a campaign that names nobody to review it.
    await box.fill(w.code2);
    await page.getByTestId("button-find-capture").click();
    const other = page.getByTestId(`found-capture-${w.cap2}`);
    await expect(other).toBeVisible();
    await expect(other).toHaveAttribute("data-reviewer", "false");
    await expect(other.getByTestId("found-not-a-reviewer")).toHaveText(
      `You are not a reviewer on ${w.campA.name}. Its reviewers: none named; the Asset Controller adds reviewers on Audit campaigns.`);
    await expect(other.getByTestId(`button-review-found-${w.cap2}`)).toHaveCount(0);

    // Nothing holds it: where else to look, in words.
    await box.fill(crypto.randomUUID());
    await page.getByTestId("button-find-capture").click();
    await expect(page.getByTestId("find-capture-none")).toContainText(
      "No capture on this register has that ID or code. If the phone says it was submitted, it may have been refused or sent elsewhere: Devices and codes › Refused syncs.");
  });

  test("the Asset Controller sees a campaign nobody can review, and the refused sync", async ({ page }) => {
    await signIn(page, "asset_controller");
    await page.getByRole("navigation", { name: "Primary navigation" }).getByText("Audit campaigns", { exact: true }).click();
    // B3: A waits with no reviewer named; B names one.
    await expect(page.getByTestId(`campaign-no-reviewer-${w.campA.id}`)).toHaveText("1 capture waits and no reviewer is named.");
    await expect(page.getByTestId(`audit-campaign-row-${w.campB.id}`)).toBeVisible();
    await expect(page.getByTestId(`campaign-no-reviewer-${w.campB.id}`)).toHaveCount(0);

    // The find box on this page: not a reviewer, and who is.
    const box = page.getByTestId("input-find-capture");
    await box.fill(w.cap1);
    await page.getByTestId("button-find-capture").click();
    const found = page.getByTestId(`found-capture-${w.cap1}`);
    await expect(found.getByTestId("found-not-a-reviewer")).toHaveText(
      `You are not a reviewer on ${w.campB.name}. Its reviewers are ${w.reviewerName}; the Asset Controller adds reviewers on Audit campaigns.`);

    // The refused one is not a capture — the sentence links to where it is.
    await box.fill(w.refusedId);
    await page.getByTestId("button-find-capture").click();
    await expect(page.getByTestId("find-capture-none")).toBeVisible();
    await page.getByTestId("link-refused-syncs").click();
    await expect(page).toHaveURL(/\/audit\/devices/);
    const section = page.getByTestId("refused-syncs");
    await expect(section.getByRole("heading", { name: "Refused syncs (last 7 days)" })).toBeVisible();
    const row = section.locator(`[data-capture-id="${w.refusedId}"]`);
    await expect(row).toHaveCount(1);
    await expect(row.getByTestId("refusal-message")).toHaveText(w.refusalMessage);
    await expect(row.getByTestId("refusal-device")).toContainText(w.device.name);
    await expect(row.getByTestId("refusal-status")).toContainText("HTTP 4");
  });
});
