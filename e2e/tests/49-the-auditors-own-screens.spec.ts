/**
 * Handoff 49 — the auditor's own screens.
 *
 * Four reads the server has answered to the Auditor's scopes for weeks with
 * no page asking: configuration-changes, disposals, the register snapshot
 * and the export. This spec drives them AS ZAINAB (the auditor persona), the
 * way report 46 proved the sidebar: signed in through the real login, token
 * read back out of the session, nothing mocked.
 *
 * What it proves:
 *   1. The auditor reaches all four screens and each shows the SERVER's
 *      answer (statement / rows / file), never a scope refusal.
 *   2. An empty report says it is empty IN WORDS — driven with a period and
 *      a date (1990) in which this tenant genuinely has nothing, because no
 *      local tenant has an empty register. No mock, no placeholder.
 *   3. A persona whose scopes do not open a screen gets the scope refusal on
 *      the typed URL AND a 403 from the server underneath (the Tag-Issuing
 *      Unit on all four; the Store Officer on configuration-changes
 *      (`settings:read`) and — since handoff 50 ruling 1 — on the export
 *      (`export:read`), the two gates narrower than `assets:read`).
 *   4. The export is driven end to end: the click, the browser download
 *      event, the file's name and its row count on screen.
 *   5. The tenant switches for the four new items hide and restore them
 *      (presentation only — the typed URL still answers while hidden).
 *
 * Run (needs the personas file for the tenant and a local admin):
 *   cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test 49-
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { existsSync, readFileSync, mkdirSync } from "fs";
import * as path from "path";
import { ORIGIN, USER, PASS, appPath } from "../config";

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);
const SHOTS = process.env.E2E_SHOTS ?? "";

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

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${TENANT}-49-${name}.png`), fullPage: false });
}

/** Sign in through the real login page; returns once landed. Clears any
 *  session a previous sign-in IN THE SAME TEST left in localStorage — the
 *  empty storageState only applies at context creation. */
async function signIn(page: Page, login: string, password: string) {
  await page.goto(appPath("/"));
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(login);
  await page.locator('input[autocomplete="current-password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

/** API sign-in — a frontend-audience token, for probes and the switch PATCH. */
async function apiToken(request: APIRequestContext, login: string, password: string): Promise<string> {
  const res = await request.post(`${ORIGIN}/api/v1/auth/login`, { data: { login, password } });
  expect(res.status(), `API login as ${login}`).toBe(200);
  return (await res.json()).data.access_token;
}

async function ask(request: APIRequestContext, token: string, p: string): Promise<number> {
  const res = await request.fetch(`${ORIGIN}/api/v1${p}`, {
    method: "GET", headers: { Authorization: `Bearer ${token}` },
  });
  return res.status();
}

/** The four screens: path, its page testid, and what a NON-EMPTY tenant
 *  must show (any one of the listed testids — statement or table). */
const SCREENS = [
  { key: "configuration_changes", path: "/admin/configuration-changes", page: "configuration-changes-page",
    content: ["report-statement"], probe: "/reports/configuration-changes?from=2026-10-01&to=2026-10-03&limit=1" },
  { key: "disposals_report", path: "/reports/disposals", page: "disposals-report-page",
    content: ["report-sap-statement", "disposals-empty-sentence"], probe: "/reports/disposals?from=2026-01-01&to=2026-10-03&limit=1" },
  { key: "register_snapshot", path: "/reports/asset-register", page: "register-snapshot-page",
    content: ["snapshot-table", "snapshot-empty-sentence"], probe: "/reports/asset-register?as_of=2026-10-01&limit=1" },
  // The export's gate is `export:read` since handoff 50 ruling 1 — the
  // Auditor's alone. Its probe is only ever asserted as a 403 for personas
  // without it; the auditor's pass is the real download in the first test.
  { key: "register_export", path: "/reports/export", page: "export-register-page",
    content: ["export-size"], probe: "/assets/export?limit=1" },
] as const;

const P = personas();

test.describe("49 — the auditor's own screens", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });
  test.skip(Object.keys(P).length === 0, `no personas file for ${TENANT} (${CREDS})`);

  test("Zainab reaches all four screens, and the export downloads", async ({ page, request }) => {
    test.setTimeout(240_000);
    const z = P.auditor;
    await signIn(page, z.login, z.password);

    for (const s of SCREENS) {
      await page.goto(appPath(s.path));
      await expect(page.getByTestId(s.page), `${s.path} renders its page`).toBeVisible({ timeout: 20_000 });
      await expect(page.getByTestId("scope-refusal"), `${s.path} is not refused to the auditor`).toHaveCount(0);
      await expect
        .poll(async () => {
          for (const c of s.content) if (await page.getByTestId(c).count()) return c;
          return null;
        }, { timeout: 30_000, message: `${s.path} shows the server's answer` })
        .not.toBeNull();
      // The sidebar draws the item for her — drawn means answered.
      await expect(page.locator(`[data-nav-key="${s.key}"]`), `${s.key} is drawn`).toHaveCount(1);
      await shot(page, `auditor-${s.key}`);
    }

    // The register snapshot's departed-custodians card (handoff 49 §4): the
    // auditor holds identity:read, so the card must render — with a
    // denominator, holders or none.
    await page.goto(appPath("/reports/asset-register"));
    await expect(page.getByTestId("departed-holders-card")).toBeVisible({ timeout: 30_000 });
    const sentence = await page.getByTestId("departed-holders-sentence").innerText();
    expect(sentence, "the card states a denominator").toMatch(/departed people on record/);
    console.log(`[49] ${TENANT} departed-holders: ${sentence.replace(/\s+/g, " ")}`);

    // The export, end to end: click, download event, file name, row count.
    await page.goto(appPath("/reports/export"));
    await expect(page.getByTestId("export-size")).toBeVisible({ timeout: 20_000 });
    const started = Date.now();
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 120_000 }),
      page.getByTestId("button-download-csv").click(),
    ]);
    expect(download.suggestedFilename()).toBe("nrs_assets.csv");
    await expect(page.getByTestId("export-done")).toBeVisible({ timeout: 120_000 });
    const doneText = await page.getByTestId("export-done").innerText();
    const rows = Number(/([\d,]+)\s+rows/.exec(doneText)?.[1]?.replace(/,/g, "") ?? "0");
    expect(rows, "the file carries the register, not a sample").toBeGreaterThan(0);
    await expect(page.getByTestId("export-truncated"), "a frontend session is uncapped").toHaveCount(0);
    console.log(`[49] ${TENANT} export: ${rows} rows in ${Date.now() - started}ms — "${doneText.replace(/\s+/g, " ")}"`);
    await shot(page, "auditor-export-done");
  });

  test("an empty report says so in words — nothing invented", async ({ page }) => {
    test.setTimeout(120_000);
    const z = P.auditor;
    await signIn(page, z.login, z.password);

    // A period in which this tenant has nothing: 1990. Not 2020 — the seed
    // fixtures backdate disposals to exactly 2020-01-01 on every local
    // tenant, which is itself a lesson in picking an "empty" period by
    // measurement rather than assumption. The empty state must be the
    // tenant's own answer.
    await page.goto(appPath("/admin/configuration-changes"));
    await expect(page.getByTestId("configuration-changes-page")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("input-period-from").fill("1990-01-01");
    await page.getByTestId("input-period-to").fill("1990-12-31");
    await expect(page.getByTestId("parameters-empty")).toBeVisible({ timeout: 30_000 });
    await shot(page, "empty-configuration-changes");

    await page.goto(appPath("/reports/disposals"));
    await expect(page.getByTestId("disposals-report-page")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("input-period-from").fill("1990-01-01");
    await page.getByTestId("input-period-to").fill("1990-12-31");
    await expect(page.getByTestId("disposals-empty-sentence")).toBeVisible({ timeout: 30_000 });
    const disposalsEmpty = await page.getByTestId("disposals-empty-sentence").innerText();
    expect(disposalsEmpty).toContain("1990");
    await shot(page, "empty-disposals");

    await page.goto(appPath("/reports/asset-register"));
    await expect(page.getByTestId("register-snapshot-page")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("input-as-of").fill("1990-01-01");
    await expect(page.getByTestId("snapshot-empty-sentence")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("snapshot-row")).toHaveCount(0);
    await shot(page, "empty-register-snapshot");
  });

  test("a persona without the scope is refused on the typed URL and by the server", async ({ page, request }) => {
    test.setTimeout(180_000);

    // The Tag-Issuing Unit holds tagging:write alone: all four refused.
    const unit = P.tag_unit;
    const unitToken = await apiToken(request, unit.login, unit.password);
    await signIn(page, unit.login, unit.password);
    for (const s of SCREENS) {
      await page.goto(appPath(s.path));
      await expect(page.getByTestId("scope-refusal"), `${s.path} typed by ${unit.key} shows the refusal`).toBeVisible({ timeout: 20_000 });
      const code = await ask(request, unitToken, s.probe);
      expect(code, `${unit.key} on ${s.probe}`).toBe(403);
      await shot(page, `refused-tag_unit-${s.key}`);
    }

    // The Store Officer holds assets:read: disposals and the snapshot are
    // THEIRS by the server's own gate; configuration-changes (settings:read)
    // is not, and neither — since handoff 50 ruling 1 — is the export
    // (export:read, the Auditor's). The export probe (SCREENS[3]) is
    // therefore exercised only where it is expected to FAIL: a persona
    // expected to pass it is the auditor alone, and her pass is proved by
    // the real download in the first test, not by this probe.
    const store = P.storekeeper;
    const storeToken = await apiToken(request, store.login, store.password);
    await signIn(page, store.login, store.password);
    await page.goto(appPath("/admin/configuration-changes"));
    await expect(page.getByTestId("scope-refusal"), "configuration-changes typed by the Store Officer").toBeVisible({ timeout: 20_000 });
    expect(await ask(request, storeToken, SCREENS[0].probe), "storekeeper on configuration-changes").toBe(403);
    expect(await ask(request, storeToken, SCREENS[1].probe), "storekeeper on disposals (the server's own gate is assets:read)").not.toBe(403);
    await shot(page, "refused-storekeeper-configuration_changes");

    await page.goto(appPath(SCREENS[3].path));
    const exportRefusal = page.getByTestId("scope-refusal");
    await expect(exportRefusal, "the export typed by the Store Officer shows the refusal").toBeVisible({ timeout: 20_000 });
    await expect(exportRefusal).toHaveAttribute("data-scope", "export:read");
    expect(await ask(request, storeToken, SCREENS[3].probe), "storekeeper on the export (export:read since handoff 50)").toBe(403);
    await shot(page, "refused-storekeeper-register_export");
  });

  test("the tenant switch hides and restores the new items — presentation, not permission", async ({ page, request }) => {
    test.setTimeout(180_000);
    const admin = await apiToken(request, USER, PASS);
    const KEYS = SCREENS.map(s => s.key);
    const patch = (shown: boolean) => request.fetch(`${ORIGIN}/api/v1/settings/sidebar`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${admin}`, "Content-Type": "application/json" },
      data: { items: Object.fromEntries(KEYS.map(k => [k, shown])) },
    });

    try {
      const off = await patch(false);
      expect(off.status(), "switching the four items off").toBe(200);

      const z = P.auditor;
      await signIn(page, z.login, z.password);
      await expect
        .poll(async () => {
          const drawn = await page.locator("[data-nav-key]").evaluateAll(els => els.map(e => e.getAttribute("data-nav-key")));
          return KEYS.filter(k => drawn.includes(k)).length;
        }, { timeout: 30_000, message: "the four items leave the sidebar" })
        .toBe(0);
      // Hidden is not forbidden: the typed URL still answers with data.
      await page.goto(appPath("/reports/disposals"));
      await expect(page.getByTestId("disposals-report-page")).toBeVisible({ timeout: 20_000 });
      await expect(page.getByTestId("scope-refusal")).toHaveCount(0);
      await shot(page, "hidden-but-answering-disposals");

      const on = await patch(true);
      expect(on.status(), "switching the four items back on").toBe(200);
      await page.reload();
      await expect
        .poll(async () => {
          const drawn = await page.locator("[data-nav-key]").evaluateAll(els => els.map(e => e.getAttribute("data-nav-key")));
          return KEYS.filter(k => drawn.includes(k)).length;
        }, { timeout: 30_000, message: "the four items return" })
        .toBe(KEYS.length);
    } finally {
      await patch(true); // never leave a tenant with the auditor's screens off
    }
  });
});
