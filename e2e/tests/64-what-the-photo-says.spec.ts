import { existsSync } from "node:fs";
import path from "node:path";
import { deflateSync } from "node:zlib";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";
import { personaToken } from "../fixtures/gates";
import { readFileSync } from "node:fs";

/**
 * Handoff 64 §3 — Identify from photo, in the browser, as the Store Officer
 * (`assets:write`), signed in through the real sign-in page, on the TEST
 * STAND-IN provider (`fake`, which answers from the file name and sends no
 * photo anywhere). The tenant's own settings are put back after.
 *
 *   add asset    New asset → the notice → a photo → the form filled, every
 *                filled field MARKED as suggested and Save held until each is
 *                settled → accept four, change the condition → Save → the
 *                asset page; the server says 4 accepted, 1 changed, the
 *                photo is the asset's first, the history has the one line.
 *   cancel       a suggestion filled in, then Cancel → no asset carries the
 *                typed name: nothing was written.
 *   photos tab   an asset whose colour is RED, with a photo → Identify… →
 *                Now / Suggested side by side → Use this on the colour only
 *                → Save 1 field → colour BLACK, name untouched, and the
 *                history says 1 accepted.
 *   off          the switch off → no screen draws the button.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/64-what-the-photo-says.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);
const AI = "/api/v1/settings/ai-identify";

function persona(key: string) {
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

function crc32(buf: Buffer): number {
  let c = ~0;
  for (const b of buf) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function chunk(kind: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(kind, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function png(width: number, height: number, seed = 0): Buffer {
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 3);
    for (let x = 0; x < width; x++) {
      row[1 + x * 3] = (x * 255) / width;
      row[2 + x * 3] = (y * 255) / height;
      row[3 + x * 3] = seed % 256;
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

async function historyLines(api: any, assetId: number): Promise<string[]> {
  const h = await api.get(`/api/v1/assets/${assetId}/history`);
  return (h.events ?? []).filter((e: any) => e.type === "details_suggested").map((e: any) => e.summary);
}

test.describe.serial("64 — what the photo says", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.setTimeout(180_000);
  let was: any = null;

  test.beforeAll(async ({ api }) => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    const settings = await api.get("/api/v1/settings");
    test.skip(settings?.receipt_gated === true,
      "the receipt gates are on: a gated receipt needs its class's fields, which this spec is not about (run gates off)");
    was = await api.get(AI);
    const r = await api.raw("PATCH", AI, { provider: "fake", enabled: true, daily_cap: 100000 });
    expect(r.status, JSON.stringify(r.body)).toBe(200);
  });

  test.afterAll(async ({ api }) => {
    if (!was) return;
    await api.raw("PATCH", AI, { enabled: false, provider: was.provider, daily_cap: was.daily_cap });
    if (was.enabled) await api.raw("PATCH", AI, { enabled: true });
  });

  test("Add asset: suggestions are filled, marked until settled, and the save records what was done", async ({ page, api }) => {
    await signIn(page, "storekeeper");
    await page.goto(appPath("/assets/new"));
    const panel = page.getByTestId("ai-form-panel");
    await expect(panel).toBeVisible({ timeout: 20_000 });
    await expect(panel.getByTestId("ai-notice")).toHaveText(
      /^Photograph the item, not people\. The photo is sent to .+ to read it\.$/);
    await expect(page.getByTestId("ai-notice")).toHaveCount(1);

    await page.getByTestId("ai-form-photo-input").setInputFiles(
      { name: "chair-01.png", mimeType: "image/png", buffer: png(320, 240, 1) });
    await expect(page.getByTestId("ai-suggestion-facts")).toBeVisible({ timeout: 30_000 });

    // Filled in, and marked.
    await expect(page.getByTestId("input-name")).toHaveValue("HIGH BACK EXECUTIVE SWIVEL CHAIR");
    await expect(page.getByTestId("input-colour")).toHaveValue("BLACK");
    await expect(page.getByTestId("input-material")).toHaveValue("LEATHER");
    for (const f of ["name", "colour", "material", "category_id"]) {
      await expect(page.getByTestId(`suggested-${f}`)).toBeVisible();
    }
    // Not legible, so not proposed: the make is neither filled nor marked.
    await expect(page.getByTestId("input-make")).toHaveValue("");
    await expect(page.getByTestId("suggested-make")).toHaveCount(0);
    // The save waits.
    await expect(page.getByTestId("button-save-asset")).toBeDisabled();
    await expect(page.getByTestId("ai-unsettled-count")).toContainText("still to accept or dismiss");

    // The person accepts four, and corrects the condition.
    for (const f of ["name", "colour", "material", "category_id"]) {
      await page.getByTestId(`accept-${f}`).click();
      await expect(page.getByTestId(`suggested-${f}`)).toHaveCount(0);
    }
    await page.getByTestId("select-condition").selectOption("fair");
    await expect(page.getByTestId("button-save-asset")).toBeEnabled();

    const saved = page.waitForResponse((r) => r.url().endsWith("/api/v1/assets") && r.request().method() === "POST");
    await page.getByTestId("button-save-asset").click();
    const res = await saved;
    expect(res.status()).toBe(201);
    const body = await res.json();
    const asset = body.data;
    recordCreated({ kind: "asset", id: asset.id, name: asset.name });
    expect(asset.ai_suggestion.counts).toEqual({ accepted: 4, changed: 1, ignored: 0 });
    await page.waitForURL(new RegExp(`/assets/${asset.id}$`));

    // The row, read back: the photo is the asset's first, the history has the line.
    const photos = await api.get(`/api/v1/assets/${asset.id}/photos`);
    expect(photos.items.filter((p: any) => p.kind === "photo").map((p: any) => p.filename))
      .toEqual(["chair-01.jpg"]);
    expect(await historyLines(api, asset.id)).toEqual(
      ["Details suggested from a photo; 4 accepted, 1 changed."]);
    const got = await api.get(`/api/v1/assets/${asset.id}`);
    expect(got.colour).toBe("BLACK");
    expect(got.condition).toBe("fair");
  });

  test("Cancel after a suggestion writes nothing", async ({ page, api }) => {
    await signIn(page, "storekeeper");
    await page.goto(appPath("/assets/new"));
    await page.getByTestId("ai-form-photo-input").setInputFiles(
      { name: "chair-02.png", mimeType: "image/png", buffer: png(200, 150, 2) });
    await expect(page.getByTestId("ai-suggestion-facts")).toBeVisible({ timeout: 30_000 });
    const name = markedName("AI cancel probe");
    await page.getByTestId("input-name").fill(name);
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.waitForURL(/\/assets$/);
    const found = await api.get("/api/v1/assets", { search: name, limit: 5 });
    expect((found as any[]).filter((a) => a.name === name)).toEqual([]);
  });

  test("Photos tab: suggestions beside the current values, Use this per field", async ({ page, api }) => {
    const asset = await api.post("/api/v1/assets", {
      name: markedName("AI photos-tab asset"), category_id: await api.firstCategoryId(), colour: "RED",
    });
    recordCreated({ kind: "asset", id: asset.id, name: asset.name });
    const token = await personaToken("storekeeper");
    const up = await page.request.post(`${ORIGIN}/api/v1/assets/${asset.id}/photos`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      multipart: {
        file: { name: "chair-03.png", mimeType: "image/png", buffer: png(160, 120, 3) },
        source: "web",
      },
    });
    expect(up.status(), await up.text()).toBe(201);
    const photo = (await up.json()).data;

    await signIn(page, "storekeeper");
    await page.goto(appPath(`/assets/${asset.id}`));
    await page.getByTestId("tab-photos").click();
    await page.getByTestId(`asset-photo-identify-${photo.id}`).click();
    const panel = page.getByTestId(`ai-photo-panel-${photo.id}`);
    await expect(panel.getByTestId("ai-notice")).toBeVisible();
    await panel.getByTestId("ai-photo-identify").click();
    await expect(panel.getByTestId("ai-photo-compare")).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByTestId("ai-now-colour")).toHaveText("RED");
    await expect(panel.getByTestId("ai-suggested-colour")).toHaveText("BLACK");
    // Nothing chosen, nothing to save — it never overwrites by itself.
    await expect(panel.getByTestId("ai-photo-save")).toBeDisabled();
    await panel.getByTestId("ai-use-colour").click();
    const saved = page.waitForResponse((r) => r.url().endsWith(`/api/v1/assets/${asset.id}`) && r.request().method() === "PATCH");
    await panel.getByTestId("ai-photo-save").click();
    expect((await saved).status()).toBe(200);

    const got = await api.get(`/api/v1/assets/${asset.id}`);
    expect(got.colour).toBe("BLACK");
    expect(got.name).toBe(asset.name);
    const lines = await historyLines(api, asset.id);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/^Details suggested from a photo; 1 accepted, \d+ ignored\.$/);
  });

  test("Switched off, no screen draws the button", async ({ page, api }) => {
    const r = await api.raw("PATCH", AI, { enabled: false });
    expect(r.status).toBe(200);
    await signIn(page, "storekeeper");
    await page.goto(appPath("/assets/new"));
    await expect(page.getByTestId("input-name")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("ai-form-panel")).toHaveCount(0);
    // …nor the Photos tab: an asset with a photo shows no Identify.
    const asset = await api.post("/api/v1/assets", {
      name: markedName("AI switched-off asset"), category_id: await api.firstCategoryId(),
    });
    recordCreated({ kind: "asset", id: asset.id, name: asset.name });
    const token = await personaToken("storekeeper");
    const up = await page.request.post(`${ORIGIN}/api/v1/assets/${asset.id}/photos`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      multipart: { file: { name: "desk-09.png", mimeType: "image/png", buffer: png(80, 60, 9) }, source: "web" },
    });
    expect(up.status()).toBe(201);
    const photo = (await up.json()).data;
    await page.goto(appPath(`/assets/${asset.id}`));
    await page.getByTestId("tab-photos").click();
    await expect(page.getByTestId(`asset-picture-photo-${photo.id}`)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId(`asset-photo-identify-${photo.id}`)).toHaveCount(0);
  });
});
