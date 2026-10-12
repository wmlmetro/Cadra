import { existsSync, readFileSync } from "node:fs";
import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";
import { fixedCategory, receive, walkTo } from "../fixtures/gates";

/**
 * Handoff 59 — what SAP already holds, on the screens that act on it.
 *
 *  (i)  SAP's asset class on a category: the Asset Controller sets it on
 *       Settings → Asset Categories and it reads back; the Store Officer is
 *       offered no control for it and is refused 403 when going round the
 *       screen; the change is a line on the configuration record
 *       (`cadra.class_sap_asset_class.<id>`).
 *  (ii) A unit whose category has NO SAP class cannot be submitted to the
 *       register: the dialog says so first, and the server's refusal is
 *       shown verbatim when the maker presses on anyway.
 *  (iii) The placeholder-serial list, edited once on screen by the
 *       administrator, on the configuration record as
 *       `cadra.serial_placeholders` — and put back as it was, whatever
 *       happens (read first over the API, PUT back in a `finally`).
 *
 * Categories here have FIXED names, found or created and set every run
 * (`fixedCategory`): a category holding assets can never be deleted, and a
 * new one per run would pile up on the tenant.
 *
 * No SAP number from NRS's register appears here — every value is invented
 * at run time in SAP's shapes (handoff 59, the source-file rule).
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test 59-)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? `../docs/api/.personas.${TENANT}`;

/** The fixed fixture classes this spec owns. */
const ON_SCREEN_CATEGORY = "e2e-59 SAP class on screen";
const NO_SAP_CATEGORY = "e2e-59 No SAP class";

type Persona = { key: string; login: string; password: string };

function personas(): Record<string, Persona> {
  if (!existsSync(CREDS)) return {};
  const out: Record<string, Persona> = {};
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [key, login, password] = l.trim().split(/\s+/);
    out[key] = { key, login, password };
  }
  return out;
}

type Session = { ctx: APIRequestContext; token: string };

async function apiSession(p: Persona): Promise<Session> {
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { login: p.login, password: p.password },
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  if (!res.ok()) throw new Error(`persona ${p.key} login failed: HTTP ${res.status()}`);
  const token = (await res.json())?.data?.access_token;
  if (!token) throw new Error(`persona ${p.key} login: no access_token`);
  return { ctx, token };
}

async function call(s: Session, method: "GET" | "POST" | "PATCH" | "PUT", path: string, data?: unknown) {
  const res = await s.ctx.fetch(`/api/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${s.token}`, Accept: "application/json", "Content-Type": "application/json" },
    data: method === "GET" ? undefined : (data ?? {}),
  });
  return { status: res.status(), body: await res.json().catch(() => null) };
}

async function signIn(page: Page, p: Persona) {
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

const isoDay = (offsetDays = 0) => new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

/** Every parameter row on the configuration record touched since yesterday,
 *  all pages. */
async function configurationRows(s: Session): Promise<any[]> {
  const rows: any[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < 20; i++) {
    const q = `/reports/configuration-changes?from=${isoDay(-1)}&to=${isoDay(0)}&limit=100`
      + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : "");
    const r = await call(s, "GET", q);
    expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
    rows.push(...(r.body?.data?.parameters ?? []));
    cursor = r.body?.pagination?.next_cursor ?? undefined;
    if (!cursor) break;
  }
  return rows;
}

test.describe("59 — what SAP already holds", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  const P = personas();
  let admin: Session | null = null;

  test.beforeAll(async () => {
    if (P.administrator) admin = await apiSession(P.administrator);
  });
  test.afterAll(async () => { await admin?.ctx.dispose(); });

  const needPersonas = (...keys: string[]) => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    for (const k of [...keys, "administrator"]) test.skip(!P[k], `persona "${k}" missing from ${CREDS}`);
  };

  test("(i) the Asset Controller sets a SAP class on screen, it reads back, and the configuration record says so", async ({ page }) => {
    needPersonas("asset_controller");
    // A known starting point: the class blank.
    const cat = await fixedCategory(ON_SCREEN_CATEGORY, { sap_asset_class: null });
    expect(cat.sap_asset_class ?? null).toBeNull();
    // A value that varies by run, so the configuration line read below is
    // this run's write and not a leftover equal to it.
    const target = String(4000 + (Date.now() % 1000)).slice(0, 4);

    await signIn(page, P.asset_controller);
    await page.goto(appPath("/settings/categories"));
    const input = page.getByTestId(`input-sap-class-${cat.id}`);
    await expect(input).toBeVisible({ timeout: 20_000 });
    await expect(input).toBeEnabled();
    await expect(page.getByTestId(`sap-class-missing-${cat.id}`)).toBeVisible();
    // The hint names SAP's classes and says NRS must confirm them.
    await expect(page.getByTestId("sap-class-note")).toContainText("need NRS to confirm");
    // Not four digits: said on the row, and Save will not send it.
    await input.fill("40A");
    await expect(page.getByTestId(`sap-class-invalid-${cat.id}`)).toBeVisible();
    await expect(page.getByTestId(`save-cat-${cat.id}`)).toBeDisabled();
    await input.fill(target);
    await expect(page.getByTestId(`save-cat-${cat.id}`)).toBeEnabled();
    const patched = page.waitForResponse((r) => r.url().includes(`/asset-categories/${cat.id}`) && r.request().method() === "PATCH");
    await page.getByTestId(`save-cat-${cat.id}`).click();
    const res = await patched;
    expect(res.status(), await res.text().catch(() => "")).toBe(200);
    // A settings:classes-only caller sends the class keys alone.
    expect(Object.keys(res.request().postDataJSON() ?? {})).toEqual(["sap_asset_class"]);

    // It reads back — after a reload, from the server.
    await page.reload();
    await expect(page.getByTestId(`input-sap-class-${cat.id}`)).toHaveValue(target, { timeout: 20_000 });
    const rows: any[] = (await call(admin!, "GET", "/asset-categories")).body?.data ?? [];
    expect(rows.find((r) => r.id === cat.id)?.sap_asset_class).toBe(target);

    // The configuration record carries the change, under the class's id.
    const key = `cadra.class_sap_asset_class.${cat.id}`;
    const line = (await configurationRows(admin!)).find((r) => r.key === key);
    expect(line, `no ${key} on the configuration record`).toBeTruthy();
    expect(String(line.current_value)).toContain(target);
    console.log(`[spec 59] configuration record: ${key} = ${line.current_value} by ${line.last_written_by?.name ?? "—"} at ${line.last_written_at}`);
  });

  test("(i) …and the Store Officer is offered no control for it, and is refused 403 round the screen", async ({ page }) => {
    needPersonas("storekeeper");
    const cat = (((await call(admin!, "GET", "/asset-categories")).body?.data ?? []) as any[])
      .find((r) => r.name === ON_SCREEN_CATEGORY);
    test.skip(!cat, `${ON_SCREEN_CATEGORY} does not exist — the test above did not run`);
    const held = cat.sap_asset_class ?? null;

    // The column is drawn, the control is not live, and there is no Save.
    await signIn(page, P.storekeeper);
    await page.goto(appPath("/settings/categories"));
    const storeInput = page.getByTestId(`input-sap-class-${cat.id}`);
    await expect(storeInput).toBeVisible({ timeout: 20_000 });
    await expect(storeInput).toBeDisabled();
    await expect(page.getByTestId(`save-cat-${cat.id}`)).toHaveCount(0);

    // And round the screen: refused, nothing written.
    const store = await apiSession(P.storekeeper);
    try {
      const direct = await call(store, "PATCH", `/asset-categories/${cat.id}`, { sap_asset_class: "1000" });
      expect(direct.status, JSON.stringify(direct.body).slice(0, 300)).toBe(403);
    } finally {
      await store.ctx.dispose();
    }
    const after: any[] = (await call(admin!, "GET", "/asset-categories")).body?.data ?? [];
    expect(after.find((r) => r.id === cat.id)?.sap_asset_class ?? null).toBe(held);
  });

  test("(ii) a unit whose class has no SAP class: the register dialog says so first, and the server's refusal is shown verbatim", async ({ page, api }) => {
    needPersonas("storekeeper", "iad_officer", "iad_approver", "asset_controller", "tagger", "register_maker");
    const settings = await call(admin!, "GET", "/settings");
    test.skip(settings.body?.data?.receipt_gated !== true,
      `cadra.receipt.gated is not on for ${TENANT} — the register gate this proves exists only with the gates on`);

    const cat = await fixedCategory(NO_SAP_CATEGORY, {
      identification_mode: "serial", sap_asset_class: null,
      class_attributes_schema: { mandatory: ["make", "model_name"] },
    });
    expect(cat.sap_asset_class ?? null).toBeNull();

    const name = markedName("spec59-no-sap-class");
    const received = await receive(api, { name, category_id: cat.id });
    recordCreated({ kind: "asset", id: received.id, name });
    // Store → IAD officer → IAD approver → Asset Controller → tagger, each
    // themselves (`fixtures/gates.ts`): parked where the maker acts.
    const tagged = await walkTo(api, received, "tagged");
    expect(tagged.register_state).toBe("tagged");

    const expected = `${cat.name} has no SAP asset class, so SAP would reject this asset. ` +
      "An Asset Controller sets it under Settings → Asset Categories.";

    await signIn(page, P.register_maker);
    await page.goto(appPath(`/assets/${received.id}`));
    await expect(page.getByTestId("candidate-banner-waiting")).toHaveText("Register Maker", { timeout: 20_000 });
    await page.getByTestId("gate-register").click();
    const dialog = page.getByTestId("dialog-gate-register");
    await expect(dialog).toBeVisible();
    // Said first, in the server's words — and the button stays live.
    await expect(dialog.getByTestId("gate-no-sap-class")).toHaveText(expected, { timeout: 30_000 });
    await dialog.getByTestId("input-sap-asset-code").fill(`ZZQ${String(Date.now()).slice(-8)}`);
    await dialog.getByTestId("input-cost").fill("150000");
    await dialog.getByTestId("input-cost-centre").fill("CC-59");
    await expect(dialog.getByTestId("button-confirm-gate")).toBeEnabled();
    const posted = page.waitForResponse((r) => r.url().includes(`/assets/${received.id}/gates/register`) && r.request().method() === "POST");
    await dialog.getByTestId("button-confirm-gate").click();
    const res = await posted;
    const envelope = await res.json().catch(() => null);
    expect(res.status(), JSON.stringify(envelope).slice(0, 400)).toBe(400);
    expect(envelope?.error?.code).toBe("validation_failed");
    expect(envelope?.error?.details?.field).toBe("sap_asset_class");
    expect(envelope?.error?.message).toBe(expected);
    await expect(dialog.getByTestId("gate-error")).toContainText(expected);

    // Nothing moved.
    const after = await api.get<any>(`/api/v1/assets/${received.id}`);
    expect(after.register_state).toBe("tagged");
  });

  test("(iii) the placeholder list, edited once on screen, on the configuration record — and put back", async ({ page }) => {
    needPersonas();
    const before = await call(admin!, "GET", "/settings/serial-placeholders");
    expect(before.status, JSON.stringify(before.body).slice(0, 300)).toBe(200);
    const original = { exact: before.body.data.exact as string[], patterns: before.body.data.patterns as string[] };
    const added = `E2E59-NOT-A-SERIAL-${Date.now()}`;

    try {
      await signIn(page, P.administrator);
      await page.goto(appPath("/settings/categories"));
      const section = page.getByTestId("serial-placeholders");
      await expect(section).toBeVisible({ timeout: 20_000 });
      await expect(section.getByTestId("serial-placeholders-statement")).toHaveText(before.body.data.statement);
      await expect(section.getByTestId("serial-placeholders-legacy")).toContainText("assets with a serial carry a placeholder");
      const exact = section.getByTestId("input-placeholders-exact");
      await expect(exact).toHaveValue(original.exact.join("\n"));
      await exact.fill([...original.exact, added].join("\n"));
      const put = page.waitForResponse((r) => r.url().includes("/settings/serial-placeholders") && r.request().method() === "PUT");
      await section.getByTestId("button-save-placeholders").click();
      const res = await put;
      expect(res.status(), await res.text().catch(() => "")).toBe(200);
      const sent = res.request().postDataJSON() ?? {};
      expect(sent.exact).toContain(added);
      expect(sent.patterns).toEqual(original.patterns);
      await expect(section.getByTestId("placeholders-saved")).toBeVisible();
      // Who changed it, now, on the section itself.
      await expect(section.getByTestId("serial-placeholders-changed")).toContainText("Last changed");

      // The configuration record.
      const line = (await configurationRows(admin!)).find((r) => r.key === "cadra.serial_placeholders");
      expect(line, "no cadra.serial_placeholders on the configuration record").toBeTruthy();
      expect(String(line.current_value)).toContain(added);
      console.log(`[spec 59] configuration record: cadra.serial_placeholders changed by ${line.last_written_by?.name ?? "—"} at ${line.last_written_at}`);
    } finally {
      const restored = await call(admin!, "PUT", "/settings/serial-placeholders", original);
      expect(restored.status, `the placeholder list was NOT restored: ${JSON.stringify(restored.body).slice(0, 300)}`).toBe(200);
      expect(restored.body?.data?.exact).toEqual(original.exact);
      expect(restored.body?.data?.patterns).toEqual(original.patterns);
    }
  });
});
