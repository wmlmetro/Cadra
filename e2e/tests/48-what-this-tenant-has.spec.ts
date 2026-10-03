import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";

/**
 * Handoff 48 — what this tenant has, proved by switching it as an
 * administrator and looking as a person.
 *
 * Two axes, both required: the TENANT shows the item (Settings → Sidebar)
 * AND the PERSON's role opens it (handoff 46). And the tenant's switch is
 * presentation, NOT permission — so this spec types the address of every
 * item it switched off and requires the data to come back. If that ever
 * refuses, the two axes have blended.
 *
 * Per tenant, a DIFFERENT set is switched off (`PLAN`), because per-tenant is
 * the whole point. In order, serial:
 *
 *   0. baseline — nothing hidden, and on a tenant nobody has touched every
 *      switch reads `configured: false` (default on), read with the row
 *      count in Postgres beside it;
 *   1. the administrator, in ONE session: opens Sidebar from the sidebar,
 *      sees the not-a-permission sentence and the two locked switches,
 *      switches the plan off, saves, watches the sidebar lose them, walks
 *      to another page and back and finds the state held, types a hidden
 *      address and gets data, is refused the lockout by the API with
 *      nothing written, and the rows are read in Postgres;
 *   2. the Store Officer: the hidden items are not drawn though the role
 *      opens them; Users is not drawn though the tenant shows it; the typed
 *      hidden address returns data;
 *   3. the Auditor: the configuration-change report names the administrator
 *      as the last writer of every switch the plan touched;
 *   afterAll: every switch the plan touched is switched back on.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 E2E_SHOTS=… \
 *      E2E_MATRIX=…/matrix.json npx playwright test 48-)
 *
 * Runs only on a tenant with a plan below AND a personas file — both are
 * test-class databases, so the configuration rows it leaves (`on`, never
 * deleted — see `v1_sidebar.py`) are on a register that accepts them.
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = `../docs/api/.personas.${TENANT}`;

type Plan = {
  groups: string[];
  items: string[];
  /** Keys the plan makes hidden — what the sidebar must lose. */
  hides: string[];
  /** A hidden page the Store Officer's role opens, and the read it makes. */
  typed: { key: string; path: string; read: string };
};

const PLAN: Record<string, Plan> = {
  // A group and an item in another group. Employees is the typed one
  // because `test19` has staff and no vehicles: typing /fleet answered an
  // empty 200, which shows a refusal did not happen and not that data came
  // back (verification pass).
  test19: {
    groups: ["fleet_transport"], items: ["employees"],
    // staff_bus left this list with handoff 47: the key is retired, the
    // server refuses it, and the group now hides Fleet alone.
    hides: ["fleet", "employees"],
    typed: { key: "employees", path: "/hr/employees", read: "/api/v1/identity/employees" },
  },
  // Three items, no group — one of them in the locked Settings group, which
  // is allowed: only the Sidebar item and its group are locked. All Assets
  // is the typed one because the register has rows, so "the data still
  // returned" is rows and not an empty 200.
  boot44: {
    groups: [], items: ["all_assets", "maintenance_readiness", "asset_categories"],
    hides: ["all_assets", "maintenance_readiness", "asset_categories"],
    typed: { key: "all_assets", path: "/assets/list", read: "/api/v1/assets" },
  },
};

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

/** The rows in Postgres — read, never written. */
function psql(sql: string): string {
  return execFileSync("docker", ["exec", "myservicenrs-db-1", "psql", "-U", "odoo",
    "-d", TENANT, "-tAF", "|", "-c", sql], { encoding: "utf8" }).trim();
}
const ROWS_SQL =
  "SELECT p.key, p.value, u.login FROM ir_config_parameter p "
  + "JOIN res_users u ON u.id = p.write_uid WHERE p.key LIKE 'cadra.sidebar.%' ORDER BY p.key";

async function shot(page: Page, name: string, fullPage = false) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}/${TENANT}-48-${name}.png`, fullPage });
}

async function apiToken(page: Page, who: Persona): Promise<string> {
  const r = await page.request.post(`${ORIGIN}/api/v1/auth/login`, {
    data: { login: who.login, password: who.password } });
  expect(r.status(), `API sign-in as ${who.key}`).toBe(200);
  return (await r.json()).data.access_token;
}

async function signIn(page: Page, who: Persona) {
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(who.login);
  await page.locator('input[autocomplete="current-password"]').fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

async function drawnKeys(page: Page): Promise<string[]> {
  return page.locator("[data-nav-key]").evaluateAll(
    (els) => els.map((e) => e.getAttribute("data-nav-key") as string));
}

/** Type an address and keep every API answer the page got — and, for the
 *  read named, how much data came back (`rows` of `total`). */
async function typeAddress(page: Page, path: string, read: string): Promise<string[]> {
  const seen: string[] = [];
  const bodies: Promise<void>[] = [];
  const listen = (r: import("@playwright/test").Response) => {
    const u = new URL(r.url());
    if (!u.pathname.startsWith("/api/v1/")) return;
    const line = `${r.request().method()} ${u.pathname} → ${r.status()}`;
    if (u.pathname === read && r.status() === 200) {
      bodies.push(r.json().then((j) => {
        const d = j.data;
        const rows = Array.isArray(d) ? d.length : Array.isArray(d?.vehicles) ? d.vehicles.length : "object";
        seen.push(`${line} · rows ${rows} of ${j.pagination?.total ?? "?"}`);
      }).catch(() => { seen.push(line); }));
    } else {
      seen.push(line);
    }
  };
  page.on("response", listen);
  await page.goto(appPath(path));
  await page.waitForLoadState("networkidle").catch(() => undefined);
  page.off("response", listen);
  await Promise.all(bodies);
  return seen;
}

/** Rows the named read returned — a 200 with nothing in it proves only that
 *  nobody refused, not that the data came back. */
function rowsBack(typed: string[], read: string): number {
  const m = typed.map((s) => s.match(new RegExp(`^GET ${read} → 200 · rows (\\d+)`))).find(Boolean);
  return m ? Number(m[1]) : 0;
}

const matrix: Record<string, unknown> = { tenant: TENANT };
let adminName = "";

test.describe("48 — what this tenant has", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  const plan = PLAN[TENANT];
  const people = personas();
  test.skip(!plan || !people.administrator,
    `no plan for ${TENANT}, or no ${CREDS} — runs on test19 and boot44`);

  test.afterAll(async ({ browser }) => {
    if (plan && people.administrator) {
      const page = await browser.newPage();
      const token = await apiToken(page, people.administrator);
      const body = {
        items: Object.fromEntries(plan.items.map((k) => [k, true])),
        groups: Object.fromEntries(plan.groups.map((k) => [k, true])),
      };
      const r = await page.request.patch(`${ORIGIN}/api/v1/settings/sidebar`, {
        headers: { Authorization: `Bearer ${token}` }, data: body });
      matrix.restored = { status: r.status(), hidden_items: (await r.json()).data?.hidden_items };
      matrix.rows_after_restore = psql(ROWS_SQL).split("\n").filter(Boolean);
      await page.close();
    }
    if (process.env.E2E_MATRIX) writeFileSync(process.env.E2E_MATRIX, JSON.stringify(matrix, null, 2));
  });

  test("0 · baseline: nothing hidden, and untouched means default on", async ({ page }) => {
    const rows = Number(psql("SELECT count(*) FROM ir_config_parameter WHERE key LIKE 'cadra.sidebar.%'"));
    const total = Number(psql("SELECT count(*) FROM ir_config_parameter"));
    const token = await apiToken(page, people.storekeeper);
    const r = await page.request.get(`${ORIGIN}/api/v1/settings/sidebar`, {
      headers: { Authorization: `Bearer ${token}` } });
    // Any signed-in person may read it — the sidebar needs it on every screen.
    expect(r.status()).toBe(200);
    const d = (await r.json()).data;
    const switches = d.groups.flatMap((g: { configured: boolean; items: { configured: boolean }[] }) =>
      [g, ...g.items]);
    const configured = switches.filter((s: { configured: boolean }) => s.configured).length;
    matrix.baseline = { sidebar_rows: rows, of_parameters: total, switches: switches.length,
      configured, hidden_items: d.hidden_items, is_a_permission: d.is_a_permission };
    expect(d.hidden_items).toEqual([]);
    expect(d.is_a_permission).toBe(false);
    // On a tenant that has never had the setting touched there are no rows
    // and nothing reads as configured: the default is on.
    if (rows === 0) expect(configured).toBe(0);
  });

  test("1 · the administrator switches it, in one session", async ({ page }) => {
    test.setTimeout(180_000);
    const admin = people.administrator;
    await signIn(page, admin);
    const before = await drawnKeys(page);
    matrix.admin_drawn_before = before;
    for (const k of plan.hides) expect(before, `${k} drawn before`).toContain(k);
    adminName = (await (await page.request.get(`${ORIGIN}/api/v1/auth/whoami`, {
      headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("cadra.token"))}` },
    })).json()).data.name;

    // Into the screen the way a person goes: from the sidebar.
    await page.locator('[data-nav-key="sidebar_settings"]').click();
    await expect(page.getByTestId("sidebar-not-a-permission")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("sidebar-not-a-permission")).toContainText("not what is permitted");
    await expect(page.getByTestId("sidebar-not-a-permission")).toContainText("can still be opened by its address");
    // The lockout, in the screen: the two switches cannot be moved.
    await expect(page.getByTestId("sidebar-switch-group-settings")).toBeDisabled();
    await expect(page.getByTestId("sidebar-switch-item-sidebar_settings")).toBeDisabled();
    await shot(page, "1-sidebar-screen-before", true);

    for (const g of plan.groups) await page.getByTestId(`sidebar-switch-group-${g}`).click();
    for (const i of plan.items) await page.getByTestId(`sidebar-switch-item-${i}`).click();
    const saved = page.waitForResponse((r) =>
      r.url().endsWith("/api/v1/settings/sidebar") && r.request().method() === "PATCH");
    await page.getByTestId("sidebar-save").click();
    const resp = await saved;
    matrix.patch = { status: resp.status(), body: resp.request().postDataJSON() };
    expect(resp.status()).toBe(200);

    // The sidebar loses them at once, without a reload.
    await expect.poll(async () => (await drawnKeys(page)).filter((k) => plan.hides.includes(k)))
      .toEqual([]);
    // An item hidden only by its GROUP keeps its own switch on, and says why.
    for (const g of plan.groups) {
      for (const k of plan.hides.filter((h) => !plan.items.includes(h))) {
        await expect(page.getByTestId(`sidebar-switch-item-${k}`)).toBeChecked();
        await expect(page.getByTestId(`sidebar-item-${k}`)).toHaveAttribute("data-shown", "false");
        await expect(page.getByTestId(`sidebar-item-${k}`)).toContainText("group is off");
      }
      void g;
    }
    await shot(page, "1-sidebar-screen-after", true);
    matrix.admin_drawn_after = await drawnKeys(page);

    // Walk away and come back, in the same session: the screen and the
    // sidebar must agree with the server, not with a cache.
    await page.locator('[data-nav-key="asset_dashboard"]').click();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.locator('[data-nav-key="sidebar_settings"]').click();
    for (const k of plan.hides) {
      await expect(page.getByTestId(`sidebar-item-${k}`)).toHaveAttribute("data-shown", "false");
    }

    // Typed: the page renders and its data comes back. Presentation, not
    // permission — a refusal here would mean the axes had blended.
    const typed = await typeAddress(page, plan.typed.path, plan.typed.read);
    matrix.admin_typed = typed;
    await shot(page, "1-admin-typed-hidden");
    expect(rowsBack(typed, plan.typed.read), `rows back from ${plan.typed.read}: ${typed.join(", ")}`)
      .toBeGreaterThan(0);
    expect(typed.some((s) => s.startsWith(`GET ${plan.typed.read} → 200`)),
      `the administrator typed ${plan.typed.path}: ${typed.join(", ")}`).toBe(true);
    expect(typed.filter((s) => / → 403$/.test(s))).toEqual([]);

    // The lockout, at the door: refused with the administrator's own token,
    // and NOTHING written — another switch in the same body included.
    const token = await page.evaluate(() => localStorage.getItem("cadra.token"));
    const rowsBefore = psql(ROWS_SQL);
    const refusals: Record<string, unknown> = {};
    for (const body of [
      { groups: { settings: false } },
      { items: { sidebar_settings: false } },
      { items: { sidebar_settings: false, barcode_station: false } },
    ]) {
      const r = await page.request.patch(`${ORIGIN}/api/v1/settings/sidebar`, {
        headers: { Authorization: `Bearer ${token}` }, data: body });
      const j = await r.json();
      refusals[JSON.stringify(body)] = { status: r.status(), message: j.error?.message };
      expect(r.status(), JSON.stringify(body)).toBe(400);
      expect(j.error.message).toContain("Nothing was written");
    }
    matrix.lockout = refusals;
    expect(psql(ROWS_SQL), "a refused lockout wrote something").toBe(rowsBefore);
    const after = (await (await page.request.get(`${ORIGIN}/api/v1/settings/sidebar`, {
      headers: { Authorization: `Bearer ${token}` } })).json()).data;
    expect(after.hidden_items).not.toContain("barcode_station");

    // The rows, in Postgres: one per switch, written by the administrator.
    const rows = rowsBefore.split("\n").filter(Boolean);
    matrix.rows = rows;
    for (const g of plan.groups) expect(rows).toContain(`cadra.sidebar.group.${g}|off|${admin.login}`);
    for (const i of plan.items) expect(rows).toContain(`cadra.sidebar.item.${i}|off|${admin.login}`);
  });

  test("2 · the Store Officer: both axes, and the address still opens", async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page, people.storekeeper);
    const drawn = await drawnKeys(page);
    matrix.storekeeper_drawn = drawn;
    if (process.env.E2E_SHOTS) {
      const size = page.viewportSize();
      await page.setViewportSize({ width: 1280, height: 1500 });
      mkdirSync(process.env.E2E_SHOTS, { recursive: true });
      await page.getByTestId("sidebar-nav").screenshot({ path: `${process.env.E2E_SHOTS}/${TENANT}-48-2-storekeeper-sidebar.png` });
      if (size) await page.setViewportSize(size);
    }
    const token = await page.evaluate(() => localStorage.getItem("cadra.token"));
    const sidebar = (await (await page.request.get(`${ORIGIN}/api/v1/settings/sidebar`, {
      headers: { Authorization: `Bearer ${token}` } })).json()).data;

    // The role opens it, the tenant has it off: not drawn.
    for (const k of plan.hides) expect(drawn, `${k} drawn for the Store Officer`).not.toContain(k);
    // The tenant shows it, the role does not open it: not drawn.
    for (const k of ["users", "sidebar_settings", "new_asset"]) {
      expect(sidebar.hidden_items).not.toContain(k);
      expect(drawn, `${k} drawn for the Store Officer`).not.toContain(k);
    }
    // Both on: drawn.
    expect(drawn).toContain("asset_dashboard");

    const typed = await typeAddress(page, plan.typed.path, plan.typed.read);
    matrix.storekeeper_typed = typed;
    await shot(page, "2-storekeeper-typed-hidden");
    expect(rowsBack(typed, plan.typed.read), `rows back from ${plan.typed.read}: ${typed.join(", ")}`)
      .toBeGreaterThan(0);
    expect(typed.some((s) => s.startsWith(`GET ${plan.typed.read} → 200`)),
      `the Store Officer typed ${plan.typed.path}: ${typed.join(", ")}`).toBe(true);
    expect(typed.filter((s) => / → 403$/.test(s))).toEqual([]);

    // And the write is refused to her by the server, not by the menu.
    const w = await page.request.patch(`${ORIGIN}/api/v1/settings/sidebar`, {
      headers: { Authorization: `Bearer ${token}` }, data: { items: { fleet: true } } });
    matrix.storekeeper_patch = w.status();
    expect(w.status()).toBe(403);
  });

  test("3 · the Auditor reads who changed it", async ({ page }) => {
    const token = await apiToken(page, people.auditor);
    const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
    const rows: { key: string; current_value: string; last_written_by: { name: string } | null }[] = [];
    let cursor: string | null = null;
    do {
      const q = `from=${day(-1)}&to=${day(1)}&limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
      const r = await page.request.get(`${ORIGIN}/api/v1/reports/configuration-changes?${q}`, {
        headers: { Authorization: `Bearer ${token}` } });
      expect(r.status()).toBe(200);
      const j = await r.json();
      rows.push(...j.data.parameters);
      cursor = j.pagination?.next_cursor ?? null;
    } while (cursor);
    const ours = rows.filter((r) => r.key.startsWith("cadra.sidebar."));
    matrix.configuration_report = ours;
    for (const k of [...plan.groups.map((g) => `cadra.sidebar.group.${g}`),
                     ...plan.items.map((i) => `cadra.sidebar.item.${i}`)]) {
      const row = ours.find((r) => r.key === k);
      expect(row, `${k} missing from the configuration-change report`).toBeTruthy();
      expect(row!.current_value).toBe("off");
      expect(row!.last_written_by?.name).toBe(adminName);
    }
  });
});
