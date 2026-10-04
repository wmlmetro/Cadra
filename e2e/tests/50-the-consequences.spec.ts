/**
 * Handoff 50 — the consequences.
 *
 * Three rulings, each driven as the person it protects:
 *
 *   1. A page that throws renders a SENTENCE inside the shell, never a blank
 *      white screen (ruling 2, `RouteErrorBoundary`). Report 49 found one
 *      null render value unmounted the entire app; this test makes a page
 *      crash on purpose — a well-formed envelope whose `locations` is a
 *      string — and reads the words, the surviving sidebar, and the recovery
 *      by navigating away (the boundary is keyed on location).
 *   2. A copy of the register is the Auditor's act, not every reader's
 *      (ruling 1, `export:read` on BOTH export routes): the Store Officer is
 *      not drawn the item, is refused on the typed URL in words, and is
 *      refused by the server underneath; the auditor gets all three the
 *      other way round.
 *   3. `/dashboard/map` stopped carrying the fleet (§2.1): a
 *      `dashboards:read` holder receives locations and no plate, driver or
 *      vehicle row; the vehicle rows live on `/fleet/map` behind
 *      `operations:read`.
 *
 * Imports `test` from @playwright/test DIRECTLY, not ../fixtures/test: the
 * fixtures' pageErrors hook would fail the deliberate-crash test on the very
 * error it exists to render.
 *
 * Run (needs the personas file for the tenant):
 *   cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test 50-
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { existsSync, readFileSync } from "fs";
import * as path from "path";
import { ORIGIN, appPath } from "../config";

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);

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

/** API sign-in — a frontend-audience token, for probes. */
async function apiToken(request: APIRequestContext, login: string, password: string): Promise<string> {
  const res = await request.post(`${ORIGIN}/api/v1/auth/login`, { data: { login, password } });
  expect(res.status(), `API login as ${login}`).toBe(200);
  return (await res.json()).data.access_token;
}

async function ask(request: APIRequestContext, token: string, p: string) {
  return request.fetch(`${ORIGIN}/api/v1${p}`, {
    method: "GET", headers: { Authorization: `Bearer ${token}` },
  });
}

const P = personas();

test.describe("50 — the consequences", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });
  test.skip(Object.keys(P).length === 0, `no personas file for ${TENANT} (${CREDS})`);

  test("a page that throws renders a sentence, not a blank screen", async ({ page }) => {
    test.setTimeout(120_000);

    // A WELL-FORMED envelope whose data is the wrong shape: `locations` is a
    // string, so the dashboard's pins memo calls `.filter` on it and throws
    // in render — exactly the class of failure report 49 found (a value the
    // serializer may legally send, a page that cannot draw it). Installed
    // before sign-in so the landing page itself is the crash.
    await page.route("**/api/v1/dashboard/map*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: { locations: "boom" }, meta: {} }),
      }));

    try {
      const admin = P.administrator;
      await signIn(page, admin.login, admin.password); // lands on /assets
      await page.goto(appPath("/assets"));

      // The sentence, inside the shell: the boundary renders in the page
      // area and the sidebar survives, so "use the menu" is true.
      const boundary = page.getByTestId("route-error-boundary");
      await expect(boundary, "the crash renders the boundary, not a white page").toBeVisible({ timeout: 30_000 });
      await expect(boundary).toContainText("This page failed to draw.");
      await expect(boundary).toContainText("use the menu to open another page");
      await expect(page.getByTestId("route-error-message"), "something to report").toBeVisible();
      await expect(page.getByTestId("sidebar-nav"), "the shell survives the page").toBeVisible();

      // The boundary is keyed on location: walking to another page through
      // the surviving menu clears the error without a reload.
      await page.locator('[data-nav-path="/assets/list"]').click();
      await page.waitForURL((u) => u.pathname.endsWith("/assets/list"), { timeout: 20_000 });
      await expect(page.getByTestId("route-error-boundary"), "navigating away clears the error").toHaveCount(0);
      await expect
        .poll(async () => {
          if (await page.getByTestId("table-asset-list").count()) return "table";
          if (await page.locator('[data-testid^="card-asset-"]').count()) return "cards";
          return null;
        }, { timeout: 30_000, message: "the next page renders its own content" })
        .not.toBeNull();
    } finally {
      await page.unroute("**/api/v1/dashboard/map*");
      // The persisted react-query cache would otherwise carry the mocked
      // payload into whatever runs next in this browser profile.
      await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); }).catch(() => undefined);
    }
  });

  test("a store officer may not take a copy of the register", async ({ page, request }) => {
    test.setTimeout(180_000);

    // The Store Officer holds assets:read — the register's screens are
    // theirs; the file of it is not (handoff 50 ruling 1).
    const store = P.storekeeper;
    const storeToken = await apiToken(request, store.login, store.password);
    await signIn(page, store.login, store.password);
    await expect(page.getByTestId("sidebar-nav")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-nav-key="register_export"]'),
      "the Export item is not drawn for the Store Officer").toHaveCount(0);

    await page.goto(appPath("/reports/export"));
    const refusal = page.getByTestId("scope-refusal");
    await expect(refusal, "the typed URL shows the refusal in words").toBeVisible({ timeout: 20_000 });
    await expect(refusal).toHaveAttribute("data-scope", "export:read");

    const refused = await ask(request, storeToken, "/assets/export?limit=1");
    expect(refused.status(), "the server refuses the Store Officer's copy").toBe(403);

    // The auditor: drawn, rendered, answered.
    const z = P.auditor;
    const auditorToken = await apiToken(request, z.login, z.password);
    await signIn(page, z.login, z.password);
    await expect(page.getByTestId("sidebar-nav")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-nav-key="register_export"]'),
      "the Export item is drawn for the auditor").toHaveCount(1);
    await page.goto(appPath("/reports/export"));
    await expect(page.getByTestId("export-register-page")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("scope-refusal")).toHaveCount(0);
    const answered = await ask(request, auditorToken, "/assets/export?limit=1");
    expect(answered.status(), "the server answers the auditor's copy").toBe(200);
  });

  test("the map no longer hands over the fleet", async ({ request }) => {
    test.setTimeout(120_000);
    const store = P.storekeeper;
    const storeToken = await apiToken(request, store.login, store.password);

    // `dashboards:read` still opens the map — and the map is now locations
    // and nothing else. No vehicle key, and no plate or driver ANYWHERE in
    // the body, which is the fact the key check cannot prove on its own.
    const mapRes = await ask(request, storeToken, "/dashboard/map");
    expect(mapRes.status(), "the Store Officer still reads the locations map").toBe(200);
    const mapText = await mapRes.text();
    const mapBody = JSON.parse(mapText);
    expect(Array.isArray(mapBody.data?.locations), "the map carries locations").toBe(true);
    expect("fleet" in mapBody.data, "no fleet key on the dashboard map").toBe(false);
    expect("recent_requests" in mapBody.data, "no recent_requests key either").toBe(false);
    expect(mapText.includes('"plate"'), "no plate anywhere in the body").toBe(false);
    expect(mapText.includes('"driver"'), "no driver anywhere in the body").toBe(false);

    // The vehicle rows moved behind the fleet's own scope.
    const fleetRefused = await ask(request, storeToken, "/fleet/map");
    expect(fleetRefused.status(), "the Store Officer is refused the fleet map").toBe(403);

    const admin = P.administrator;
    const adminToken = await apiToken(request, admin.login, admin.password);
    const fleetRes = await ask(request, adminToken, "/fleet/map");
    expect(fleetRes.status(), "an administrator reads the fleet map").toBe(200);
    const fleetBody = await fleetRes.json();
    expect(Array.isArray(fleetBody.data?.fleet), "the fleet map carries the vehicle rows").toBe(true);
  });
});
