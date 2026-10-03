import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";

/**
 * Handoff 46 — everyone sees their own job, proved by signing in as each.
 *
 * Signs in as every demo persona `scripts/demo_personas.sh <db> seed` made,
 * through the real sign-in page, and for each one:
 *
 *   1. records WHERE it lands — the rule is "the best page this person can
 *      actually open", and the only way to know what a person can open is to
 *      be them;
 *   2. reads which sidebar items were DRAWN (by `data-nav-path`, not by
 *      reading the nav table — the table is what is under test);
 *   3. for EVERY item, asks the server with the person's own token what the
 *      page is for, and asserts the two agree: a drawn item's reads are not
 *      refused, and a hidden item's are — every one of them 403. Hiding is a
 *      courtesy; the refusal is the permission. An item hidden from a person
 *      the server would still answer is the instrument that reports success
 *      while measuring nothing, and this is the test that would say so;
 *   4. TYPES the URL of every hidden item, as the person, and keeps what the
 *      page asked the API and what it was told;
 *   5. screenshots the landing page and the sidebar.
 *
 * Writes probe with the body `{"h46_probe": true}` and id 0, so a holder of
 * the scope is answered 400 "Nothing was written" or 404 — never a write.
 * Two items read no API at all (Identity, Staff Bus: mock pages); they are
 * recorded as having nothing for the server to refuse, not asserted.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 E2E_SHOTS=… \
 *      E2E_MATRIX=…/matrix.json npx playwright test 46-)
 *
 * Skips unless `docs/api/.personas.<tenant>` exists — the passwords live
 * there and nowhere else.
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = `../docs/api/.personas.${TENANT}`;

type Probe = { method: "GET" | "POST" | "PATCH"; path: string };
const G = (path: string): Probe => ({ method: "GET", path });
const W = (method: "POST" | "PATCH", path: string): Probe => ({ method, path });

/** Every sidebar item and what its page asks the server for. */
const ITEMS: { path: string; probes: Probe[] }[] = [
  { path: "/", probes: [G("/assets?limit=1"), G("/locations?limit=1"), G("/identity/employees?limit=1"), G("/dashboard/kpis")] },
  { path: "/dashboards/fleet", probes: [G("/fleet/dashboard")] },
  { path: "/dashboards/it", probes: [G("/dashboard/kpis"), G("/assets?limit=1")] },
  { path: "/assets", probes: [G("/assets?limit=1"), G("/dashboard/kpis")] },
  { path: "/assets/list", probes: [G("/assets?limit=1")] },
  { path: "/approvals", probes: [G("/approvals?limit=1")] },
  { path: "/assets/new", probes: [W("POST", "/assets")] },
  { path: "/locations", probes: [G("/locations?limit=1")] },
  { path: "/locations/new", probes: [W("POST", "/locations")] },
  { path: "/hr/employees", probes: [G("/identity/employees?limit=1")] },
  { path: "/hr/sap-sync", probes: [G("/identity/employees?limit=1&sap_sync_status=synced")] },
  { path: "/hr/import", probes: [W("POST", "/integrations/employees/import")] },
  { path: "/hr/identity", probes: [] },
  { path: "/fleet", probes: [G("/fleet?limit=1")] },
  { path: "/fleet/staff-bus", probes: [] },
  { path: "/reports/fleet-roster", probes: [G("/fleet/dashboard")] },
  { path: "/reports/asset-inventory", probes: [G("/dashboard/kpis"), G("/dashboard/map")] },
  { path: "/reports/maintenance-readiness", probes: [G("/fleet/dashboard")] },
  { path: "/reports/location-coverage", probes: [G("/dashboard/kpis"), G("/locations?limit=1")] },
  { path: "/reports/tag-adoption", probes: [G("/barcode/kpis")] },
  { path: "/reports/depreciation", probes: [G("/reports/depreciation")] },
  { path: "/settings/categories", probes: [W("POST", "/asset-categories")] },
  { path: "/settings/branding", probes: [W("PATCH", "/settings/branding")] },
  { path: "/settings/depreciation", probes: [W("PATCH", "/settings/depreciation")] },
  // Handoff 48. `admin`-only; the probe body is refused 400 to a holder.
  { path: "/settings/sidebar", probes: [W("PATCH", "/settings/sidebar")] },
  { path: "/admin/access-changes", probes: [G("/reports/access-changes?from=2026-10-01&to=2026-10-03&limit=1")] },
  { path: "/admin/users", probes: [G("/users?limit=1")] },
  { path: "/tools/barcode", probes: [G("/barcode/kpis")] },
];

/**
 * What each persona's JOB needs, beyond the menu — recorded, not asserted.
 * These are the findings of §6: whether the roles fit the people.
 */
const JOB: Record<string, Probe[]> = {
  storekeeper: [W("POST", "/assets"), W("POST", "/assets/0/move"), W("POST", "/assets/0/verify")],
  tagger: [W("POST", "/assets/0/tag-affixed"), W("POST", "/barcode/generate"), W("POST", "/tags/0/request-replacement")],
  tag_unit: [W("POST", "/assets/0/tag-affixed"), G("/barcode/lookup?q=x"), G("/barcode/untagged?limit=1")],
  asset_manager: [W("POST", "/approvals/0/approve"), W("POST", "/tags/0/approve-replacement")],
  auditor: [G("/reports/access-changes?from=2026-10-01&to=2026-10-03&limit=1"), G("/reports/configuration-changes?from=2026-10-01&to=2026-10-03&limit=1"), G("/reports/disposals?from=2026-01-01&to=2026-10-03&limit=1"), G("/reports/asset-register?as_of=2026-10-03&limit=1"), G("/assets/export?limit=1")],
  administrator: [G("/users?limit=1"), G("/meta/diagnostics")],
};

/** Where each persona must land, measured by signing in (handoff 46 §4). */
const LANDING: Record<string, string> = {
  storekeeper: "/assets", tagger: "/assets", asset_manager: "/assets",
  auditor: "/assets", administrator: "/assets", tag_unit: "/no-access",
};

type Persona = { key: string; login: string; password: string };
function personas(): Persona[] {
  if (!existsSync(CREDS)) return [];
  return readFileSync(CREDS, "utf8").split("\n")
    .filter((l) => l.trim() && !l.startsWith("#"))
    .map((l) => { const [key, login, password] = l.trim().split(/\s+/); return { key, login, password }; });
}

async function shot(page: Page, name: string, fullPage = false) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}/${TENANT}-${name}.png`, fullPage });
}

const matrix: Record<string, unknown> = {};

test.describe("46 — everyone sees their own job", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  test.afterAll(() => {
    if (process.env.E2E_MATRIX) writeFileSync(process.env.E2E_MATRIX, JSON.stringify(matrix, null, 2));
  });

  const all = personas();
  test("the personas file exists for this tenant", () => {
    test.skip(all.length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    expect(all.map((p) => p.key).sort()).toEqual(Object.keys(LANDING).sort());
  });

  for (const persona of all) {
    test(`${persona.key}: lands, sees, and is refused what it does not see`, async ({ page }) => {
      test.setTimeout(240_000);
      const stops: string[] = [];
      page.on("framenavigated", (f) => { if (f === page.mainFrame()) stops.push(new URL(f.url()).pathname); });
      await page.goto(appPath("/"));
      await page.locator('input[autocomplete="username"]').fill(persona.login);
      await page.locator('input[autocomplete="current-password"]').fill(persona.password);
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
      // Read where it SETTLED, and record every stop on the way: a redirect
      // that passes through /no-access and moves on is a defect too, and
      // this spec's first run of the front-door rule caught exactly that.
      await page.waitForLoadState("networkidle").catch(() => undefined);
      const landed = new URL(page.url()).pathname.replace(/^\/app/, "") || "/";
      expect(stops.filter((s) => s.endsWith("/no-access")).length,
        `${persona.key} passed through /no-access on the way to ${landed}: ${stops.join(" → ")}`)
        .toBe(landed === "/no-access" ? 1 : 0);
      await shot(page, `46-${persona.key}-landing`);
      expect(landed, `${persona.key} landed on ${landed}`).toBe(LANDING[persona.key]);

      const nav = page.getByTestId("sidebar-nav");
      const drawn = await page.locator("[data-nav-path]").evaluateAll(
        (els) => els.map((e) => e.getAttribute("data-nav-path") as string));
      if (await nav.count() && process.env.E2E_SHOTS) {
        // Tall enough that the whole menu is on one image — the sidebar
        // scrolls, and a screenshot at 720px shows half of what a person sees.
        const size = page.viewportSize();
        await page.setViewportSize({ width: 1280, height: 1500 });
        await nav.screenshot({ path: `${process.env.E2E_SHOTS}/${TENANT}-46-${persona.key}-sidebar.png` });
        if (size) await page.setViewportSize(size);
      }

      const token = await page.evaluate(() => localStorage.getItem("cadra.token"));
      const scope = await page.evaluate(() => localStorage.getItem("cadra.tokenScope"));
      expect(token, "no token stored after sign-in").toBeTruthy();
      const ask = async (p: Probe) => {
        const r = await page.request.fetch(`${ORIGIN}/api/v1${p.path}`, {
          method: p.method,
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          data: p.method === "GET" ? undefined : { h46_probe: true },
        });
        return r.status();
      };

      const rows: Record<string, unknown>[] = [];
      for (const item of ITEMS) {
        const isDrawn = drawn.includes(item.path);
        const statuses: string[] = [];
        for (const p of item.probes) statuses.push(`${p.method} ${p.path} → ${await ask(p)}`);
        let typed: string[] | undefined;
        if (!isDrawn) {
          // Type the URL, as the person, and keep what the page was told.
          const seen: string[] = [];
          const listen = (r: import("@playwright/test").Response) => {
            const u = new URL(r.url());
            if (u.pathname.startsWith("/api/v1/") && !/\/(auth\/whoami|meta\/enums)$/.test(u.pathname)) {
              seen.push(`${r.request().method()} ${u.pathname} → ${r.status()}`);
            }
          };
          page.on("response", listen);
          await page.goto(appPath(item.path));
          await page.waitForLoadState("networkidle").catch(() => undefined);
          page.off("response", listen);
          typed = seen;
          if (item.path === "/") {
            // The front door is the one hidden URL that redirects: a person
            // who cannot open the command centre is sent to their landing
            // page, not shown a dashboard of refusals (verification pass, R5).
            expect(new URL(page.url()).pathname.replace(/^\/app/, ""), `${persona.key} typed / and stayed on it`)
              .toBe(LANDING[persona.key]);
          }
          await shot(page, `46-${persona.key}-typed${item.path.replace(/\//g, "_")}`);
        }
        rows.push({ path: item.path, drawn: isDrawn, probes: statuses, typed });
        for (const s of statuses) {
          const code = Number(s.split("→ ")[1]);
          if (isDrawn) expect(code, `${persona.key} is shown ${item.path} but the server refuses: ${s}`).not.toBe(403);
          else expect(code, `${persona.key} is NOT shown ${item.path} but the server answers: ${s}`).toBe(403);
        }
      }

      // One level down from the menu: the controls ON a page. An asset the
      // person can read, and the branding screen typed by URL. A write
      // button drawn for somebody the server refuses is the same defect as a
      // menu item drawn for them, and the first screenshot of this spec
      // showed a Store Officer a "New Asset" button.
      const holds = (s: string) => (scope ?? "").split(/\s+/).some((x) => x === s || x === "admin" || x === "*");
      const inPage: Record<string, boolean | string> = {};
      if (holds("assets:read")) {
        const r = await page.request.get(`${ORIGIN}/api/v1/assets?limit=1&state=active`, { headers: { Authorization: `Bearer ${token}` } });
        const assetId = (await r.json()).data?.[0]?.id;
        expect(assetId, "no active asset to open on this tenant").toBeTruthy();
        await page.goto(appPath(`/assets/${assetId}`));
        // Wait on something EVERY reader is drawn — the workflow strip — not
        // on a button inside the gated bar: waiting on the thing under test
        // let a blank page pass for everybody without assets:write
        // (verification pass, D1). No catch: a page that never renders fails.
        await expect(page.getByTestId("workflow-step-0")).toBeVisible({ timeout: 20_000 });
        await page.waitForLoadState("networkidle").catch(() => undefined);
        await shot(page, `46-${persona.key}-asset`);
        inPage.asset_action_bar = await page.getByTestId("asset-action-bar").isVisible();
        expect(inPage.asset_action_bar, `${persona.key}: asset action bar drawn=${inPage.asset_action_bar}, holds assets:write=${holds("assets:write")}`)
          .toBe(holds("assets:write"));
      }
      await page.goto(appPath("/settings/branding"));
      await page.waitForLoadState("networkidle").catch(() => undefined);
      if (holds("assets:read")) {
        inPage.settings_read_only = await page.getByTestId("settings-read-only").isVisible();
        expect(inPage.settings_read_only, `${persona.key}: branding read-only note`).toBe(!holds("settings:write"));
      }

      const job: string[] = [];
      for (const p of JOB[persona.key] ?? []) job.push(`${p.method} ${p.path} → ${await ask(p)}`);
      matrix[persona.key] = { login: persona.login, scope, landed, drawn, items: rows, inPage, job };
    });
  }
});
