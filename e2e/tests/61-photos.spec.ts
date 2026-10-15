import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { deflateSync } from "node:zlib";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";
import { asPersona, receive, walkTo } from "../fixtures/gates";

/**
 * Handoff 61 §5 — photos on an asset, in the browser, as the people whose
 * job it is, each signed in through the real sign-in page.
 *
 *   writer       the Store Officer (`assets:write`): asset page → Photos →
 *                Add photo → the picture is redrawn under 300 KB in the
 *                browser → Upload → it is drawn from its bytes → Supersede
 *                with a reason → marked, kept → back to the list → the asset
 *                again, and the mark is still there (read fresh, in the
 *                same session). The row is read from the server after each
 *                act.
 *   non-reader   the same Store Officer on a unit IAD has verified: the
 *                Photos tab says "IAD evidence: 1 item" and draws no
 *                evidence card — the evidence guard (ruling 1 on report 60).
 *   reader       the Auditor on the same unit: the evidence card, labelled
 *                *IAD evidence*, beside the photo.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test tests/61-photos.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);

type Persona = { key: string; login: string; password: string };
function persona(key: string): Persona {
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key) return { key: k, login, password };
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

// ── a real picture, made here ──────────────────────────────────────────────

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

/** An RGB PNG with a gradient — a picture the browser decodes and redraws. */
function png(width: number, height: number): Buffer {
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 3);
    for (let x = 0; x < width; x++) {
      row[1 + x * 3] = (x * 255) / width;
      row[2 + x * 3] = (y * 255) / height;
      row[3 + x * 3] = 128;
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

async function photosOf(api: any, assetId: number) {
  return api.get(`/api/v1/assets/${assetId}/photos`);
}

async function openPhotosTab(page: Page, assetId: number) {
  await page.goto(appPath(`/assets/${assetId}`));
  await page.getByTestId("tab-photos").click();
  await expect(page.getByTestId("asset-photos")).toBeVisible({ timeout: 20_000 });
}

test.describe.serial("61 — photos on an asset", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.setTimeout(180_000);

  test.beforeAll(() => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
  });

  test("the Store Officer adds a photo, sees it, supersedes it — and it is still marked after the list", async ({ page, api }) => {
    const me = await asPersona("storekeeper", "GET", "/auth/whoami");
    expect(me.status).toBe(200);
    const storeName: string = me.body.data.name;
    const asset = await receive(api, { category_id: await api.firstCategoryId(), name: markedName("Photo spec asset") });
    recordCreated({ kind: "asset", id: asset.id, name: asset.name });
    await signIn(page, "storekeeper");
    await openPhotosTab(page, asset.id);
    await expect(page.getByTestId("asset-photos-count")).toHaveText("No photos of this asset yet.");

    // Add: a 2000 × 1500 PNG, which the browser redraws as a JPEG under 300 KB.
    await page.getByTestId("asset-photo-input").setInputFiles({
      name: "tag-in-frame.png", mimeType: "image/png", buffer: png(2000, 1500),
    });
    await expect(page.getByText(/Ready to send: \d+ × \d+, \d+ KB JPEG\./)).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("asset-photo-caption").fill("Tag on the left side panel");
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().endsWith(`/api/v1/assets/${asset.id}/photos`));
    await page.getByTestId("asset-photo-upload").click();
    const res = await posted;
    expect(res.status(), await res.text()).toBe(201);
    const sent = (await res.json()).data;

    // The server's row: what was sent, by whom, from where.
    const listed = await photosOf(api, asset.id);
    const row = listed.items.find((i: any) => i.kind === "photo" && i.id === sent.id);
    expect(row, JSON.stringify(listed).slice(0, 400)).toBeTruthy();
    expect(row.caption).toBe("Tag on the left side panel");
    expect(row.source).toBe("web");
    expect(row.mimetype).toBe("image/jpeg");
    expect(row.size).toBeLessThanOrEqual(300 * 1024);
    expect(Math.max(row.width, row.height)).toBeLessThanOrEqual(1600);
    expect(row.uploaded_by_name).toBe(storeName);
    expect(row.superseded).toBeNull();

    // Drawn from its bytes, labelled.
    const card = page.getByTestId(`asset-picture-photo-${sent.id}`);
    await expect(card).toBeVisible();
    await expect(card.getByTestId("asset-picture-kind")).toHaveText("Photo");
    await expect(card.getByText("Tag on the left side panel")).toBeVisible();
    const img = card.getByTestId("asset-picture-image");
    await expect(img).toBeVisible({ timeout: 20_000 });
    expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBe(row.width);
    await expect(page.getByTestId("asset-photos-count")).toHaveText("1 of 12 photos.");

    // Supersede, with a reason.
    await card.getByTestId(`asset-photo-supersede-${sent.id}`).click();
    await expect(card.getByTestId("asset-photo-supersede-confirm")).toBeDisabled();
    await card.getByTestId("asset-photo-supersede-reason").fill("Blurred; retaken with the tag in frame");
    const superseded = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().endsWith(`/photos/${sent.id}/supersede`));
    await card.getByTestId("asset-photo-supersede-confirm").click();
    expect((await superseded).status()).toBe(200);
    const mark = card.getByTestId(`asset-photo-superseded-${sent.id}`);
    await expect(mark).toContainText(`Superseded by ${storeName}`);
    await expect(mark).toContainText("Blurred; retaken with the tag in frame");
    await expect(card).toHaveAttribute("data-superseded", "true");
    await expect(page.getByTestId("asset-photos-count"))
      .toHaveText("0 of 12 photos (and 1 superseded, kept and not counted).");

    const after = await photosOf(api, asset.id);
    const kept = after.items.find((i: any) => i.kind === "photo" && i.id === sent.id);
    expect(kept.superseded?.reason).toBe("Blurred; retaken with the tag in frame");
    expect(kept.superseded?.by_name).toBe(storeName);

    // Back to the list, then the asset again — the same session.
    await page.getByTestId("button-back").click();
    await page.waitForURL((u) => !u.pathname.endsWith(`/assets/${asset.id}`));
    await page.goBack();
    await page.getByTestId("tab-photos").click();
    await expect(page.getByTestId(`asset-photo-superseded-${sent.id}`))
      .toContainText("Blurred; retaken with the tag in frame", { timeout: 20_000 });
  });

  test("IAD's evidence: a count in words for the Store Officer, a labelled card for the Auditor", async ({ page, browser, api }) => {
    const settings = await api.get<any>("/api/v1/settings");
    const gateWasOn = settings?.receipt_gated === true;
    if (!gateWasOn) {
      const r = await api.raw("PATCH", "/api/v1/settings/receipt-gate", { enabled: true });
      expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
    }
    let unit: any;
    try {
      unit = await receive(api, { category_id: await api.firstCategoryId(), name: markedName("Photo spec IAD unit") });
      recordCreated({ kind: "asset", id: unit.id, name: unit.name });
      unit = await walkTo(api, unit, "vfm_verified");
      expect(unit.register_state).toBe("vfm_verified");
    } finally {
      if (!gateWasOn) await api.raw("PATCH", "/api/v1/settings/receipt-gate", { enabled: false });
    }

    // The Store Officer: no `evidence:read`.
    await signIn(page, "storekeeper");
    await openPhotosTab(page, unit.id);
    await expect(page.getByTestId("asset-photos-evidence-count")).toHaveText("IAD evidence: 1 item");
    await expect(page.locator('[data-kind="iad_evidence"]')).toHaveCount(0);

    // The Auditor, in a session of their own: the evidence, labelled.
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    try {
      const auditor = await ctx.newPage();
      await signIn(auditor, "auditor");
      await openPhotosTab(auditor, unit.id);
      const evidence = auditor.locator('[data-kind="iad_evidence"]');
      await expect(evidence).toHaveCount(1);
      await expect(evidence.getByTestId("asset-picture-kind")).toHaveText("IAD evidence");
      await expect(evidence).toContainText("IAD verification");
      await expect(auditor.getByTestId("asset-photos-evidence-count")).toHaveCount(0);
      // A reader who cannot write is offered no control that changes anything.
      await expect(auditor.getByTestId("asset-photo-add")).toHaveCount(0);
    } finally {
      await ctx.close();
    }
  });
});
