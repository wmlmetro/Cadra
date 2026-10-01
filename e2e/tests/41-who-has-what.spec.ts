import { test, expect, type Page } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Handoff 41, in a browser: who has what — read only, end to end.
 *
 * Two pages under Administration: `/admin/users` (the roster, with the
 * direct-versus-effective distinction drawn on every row) and
 * `/admin/access-changes` (the existing report, filtered to a person). The
 * one assertion that matters more than the rest is the ABSENCE proof: on
 * both pages there is no control that would change anything — not disabled,
 * absent — and no input other than the search box, the two date fields and
 * the filter buttons.
 *
 * The global storage state is an admin session. The fixtures this suite
 * leans on (`h41_manager`, `h41_leaver`) are seeded on `test19` by handoff
 * 41 part B; where one is missing the test says so and skips rather than
 * asserting against a roster it cannot see.
 */

const CHANGE_WORDS = /\b(create|add|edit|remove|deactivate|invite|grant|revoke|save|reset)\b/i;

/** Every button inside the page root. Scoped to the page's own test id so
 *  the sidebar's "+ New Asset" and the topbar never leak into the proof. */
async function buttonTexts(page: Page, rootId: string) {
  const root = page.getByTestId(rootId);
  const buttons = await root.locator("button").all();
  const out: string[] = [];
  for (const b of buttons) {
    const text = (await b.textContent())?.trim() ?? "";
    const label = (await b.getAttribute("aria-label")) ?? "";
    const title = (await b.getAttribute("title")) ?? "";
    out.push([text, label, title].filter(Boolean).join(" | "));
  }
  return out;
}

async function inputTypes(page: Page, rootId: string) {
  const root = page.getByTestId(rootId);
  const inputs = await root.locator("input, textarea, select").all();
  const out: string[] = [];
  for (const i of inputs) {
    const tag = await i.evaluate((el) => el.tagName.toLowerCase());
    const type = (await i.getAttribute("type")) ?? "";
    out.push(tag === "input" ? type || "text" : tag);
  }
  return out;
}

async function openUsers(page: Page) {
  await gotoApp(page, "/admin/users");
  await expectShell(page);
  await expect(page.getByTestId("nav-users")).toBeVisible();
  await expect(page.getByTestId("admin-users-page")).toBeVisible();
}

async function searchFor(page: Page, q: string) {
  const box = page.getByTestId("input-user-search");
  await box.fill(q);
  await box.press("Enter");
}

// ── The roster ───────────────────────────────────────────────────────────────

test("the roster lists accounts, marks API credentials, and the Inactive filter yields only inactive rows", async ({ page, api }) => {
  // Ask the API first, so a tenant with no inactive account skips with its
  // denominator instead of the spec reading an empty table mid-refetch as
  // "none to prove on" — which is exactly what its first run did on test19,
  // where h41_leaver exists.
  const inactive = await api.get<{ login: string }[]>("/api/v1/users", { active: "false", limit: 100 });
  const expectedInactive = (inactive ?? []).length;
  test.info().annotations.push({ type: "inactive-accounts-on-tenant", description: String(expectedInactive) });
  test.skip(expectedInactive === 0, "this tenant has no inactive account to prove the filter on (test19 has h41_leaver)");

  await openUsers(page);
  await expect(page.getByTestId("admin-scope-refusal")).toHaveCount(0);

  const rows = page.getByTestId("user-row");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  expect(await rows.count()).toBeGreaterThan(0);

  // At least one API credential on the roster: every tenant has the
  // credential pair the suites authenticate with.
  await expect(page.getByTestId("kind-pill-api").first()).toBeVisible();

  await page.getByTestId("filter-status").click();
  await page.locator('[data-testid="filter-status-option"][data-value="inactive"]').click();
  await expect(page.getByTestId("filter-status")).toContainText("Inactive");
  // The filtered walk has settled when the table holds exactly the API's
  // inactive accounts and nothing else; an empty table in between is the
  // refetch, not an answer.
  await expect.poll(async () => {
    const n = await rows.count();
    if (n !== expectedInactive) return `rows=${n}`;
    const states = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-active")));
    return states.every((s) => s === "false") ? "all-inactive" : "mixed";
  }, { timeout: 20_000 }).toBe("all-inactive");
  await expect(page.getByTestId("inactive-pill")).toHaveCount(expectedInactive);
});

test("h41_manager: Asset Manager under Roles held, Asset User via implication, and the scopes in words", async ({ page, api }) => {
  const found = await api.get<any[]>("/api/v1/users", { q: "h41_manager", limit: 5 });
  const manager = (found ?? []).find((u) => u.login === "h41_manager");
  test.skip(!manager, "h41_manager is not on this tenant's roster");

  await openUsers(page);
  await searchFor(page, "h41_manager");
  const row = page.locator('[data-testid="user-row"][data-login="h41_manager"]');
  await expect(row).toBeVisible({ timeout: 20_000 });

  // The row leads with the DIRECT role, and the implied one is lighter.
  await expect(row.locator('[data-testid="role-pill-direct"][data-role="Asset Manager"]')).toBeVisible();
  await expect(row.locator('[data-testid="role-pill-implied"][data-role="Asset User"]')).toBeVisible();

  await row.click();
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/admin/users/${manager.id}$`));
  await expect(panel.getByTestId("user-detail-login")).toHaveText("h41_manager");
  await expect(panel.getByTestId("user-section-roles-direct")).toContainText("Asset Manager");
  await expect(panel.getByTestId("user-section-roles-direct")).not.toContainText("Asset User");
  await expect(panel.getByTestId("user-section-roles-implied")).toContainText("Asset User");
  await expect(panel.getByTestId("user-section-scopes")).toContainText("Approve and reject requests");
});

test("the role filter is on EFFECTIVE membership: Asset User includes h41_manager", async ({ page, api }) => {
  const found = await api.get<any[]>("/api/v1/users", { q: "h41_manager", limit: 5 });
  test.skip(!(found ?? []).some((u) => u.login === "h41_manager"), "h41_manager is not on this tenant's roster");

  await openUsers(page);
  await page.getByTestId("filter-role").click();
  await page.locator('[data-testid="filter-role-option"][data-value="asset_user"]').click();
  await expect(page.getByTestId("filter-role")).toContainText("Asset User");
  await searchFor(page, "h41_manager");
  await expect(page.locator('[data-testid="user-row"][data-login="h41_manager"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("role-filter-hint")).toContainText(/implication/i);
});

// ── The absence proof ────────────────────────────────────────────────────────

test("ABSENCE: no control on either page would change anything", async ({ page }) => {
  await openUsers(page);
  await expect(page.getByTestId("user-row").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("user-row").first().click();
  await expect(page.getByTestId("user-detail")).toBeVisible();

  let buttons = await buttonTexts(page, "admin-users-page");
  for (const b of buttons) expect(b, `users page button: "${b}"`).not.toMatch(CHANGE_WORDS);
  let inputs = await inputTypes(page, "admin-users-page");
  for (const t of inputs) expect(["search"], `users page input type "${t}"`).toContain(t);
  // The page has nothing a form would need.
  await expect(page.getByTestId("admin-users-page").locator("form, textarea, select, input[type=text], input[type=password], input[type=email]")).toHaveCount(0);

  await gotoApp(page, "/admin/access-changes");
  await expect(page.getByTestId("admin-access-changes-page")).toBeVisible();
  await expect(page.getByTestId("report-summary")).toBeVisible({ timeout: 30_000 });
  buttons = await buttonTexts(page, "admin-access-changes-page");
  for (const b of buttons) expect(b, `access-changes button: "${b}"`).not.toMatch(CHANGE_WORDS);
  inputs = await inputTypes(page, "admin-access-changes-page");
  for (const t of inputs) expect(["date"], `access-changes input type "${t}"`).toContain(t);
  await expect(page.getByTestId("admin-access-changes-page").locator("form, textarea, select")).toHaveCount(0);
});

// ── The link into the report, and the deep link back ─────────────────────────

test("'Access changes for this person' filters the report to that login", async ({ page }) => {
  await openUsers(page);
  const first = page.getByTestId("user-row").first();
  await expect(first).toBeVisible({ timeout: 20_000 });
  const login = (await first.getAttribute("data-login"))!;
  const id = (await first.getAttribute("data-user-id"))!;
  await first.click();
  await expect(page.getByTestId("user-detail")).toBeVisible();

  await page.getByTestId("link-access-changes").click();
  await expect(page).toHaveURL(new RegExp(`/admin/access-changes\\?user_id=${id}$`));
  await expect(page.getByTestId("admin-access-changes-page")).toBeVisible();
  const chip = page.getByTestId("user-filter-chip");
  await expect(chip).toHaveAttribute("data-user-id", id);
  await expect(chip.getByTestId("user-filter-login")).toHaveText(login, { timeout: 20_000 });

  // Let the walk finish, then every row shown is that person's.
  // The table is an answer only once it holds a row or says it is empty —
  // between the first page's request and its render there is neither, and
  // `walk-progress` is absent then too. The first run counted zero rows in
  // that gap on a person who had two.
  const rows = page.getByTestId("event-row");
  await expect(rows.first().or(page.getByTestId("events-empty"))).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("walk-progress")).toHaveCount(0, { timeout: 60_000 });
  const n = await rows.count();
  test.info().annotations.push({ type: "events-for-user", description: `${login}: ${n}` });
  if (n > 0) {
    const logins = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-login")));
    expect(logins.every((l) => l === login), `rows for ${login}: ${JSON.stringify(logins)}`).toBe(true);
  } else {
    await expect(page.getByTestId("events-empty")).toBeVisible();
  }

  // The clearer takes the filter off the URL.
  await page.getByTestId("button-clear-user").click();
  await expect(page).toHaveURL(/\/admin\/access-changes$/);
  await expect(chip).toHaveCount(0);
});

test("deep link /admin/users/<id> opens the panel directly", async ({ page, api }) => {
  const users = await api.get<any[]>("/api/v1/users", { limit: 1 });
  test.skip(!users?.length, "the roster is empty");
  const u = users[0];

  await gotoApp(page, `/admin/users/${u.id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toHaveAttribute("data-login", u.login);
  await expect(panel.getByTestId("user-detail-name")).toHaveText(u.name);
});
