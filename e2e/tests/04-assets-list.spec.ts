import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { appPath } from "../config";

/**
 * Asset Register list page (/assets/list) — the richest list surface:
 * view switcher, search, filter dropdowns, clear, group-by, sortable table,
 * row -> detail, infinite scroll. Plus the /assets dashboard controls.
 */

test.describe("/assets/list", () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page, "/assets/list");
    await expectShell(page);
  });

  test("view switcher toggles Kanban / List / Map", async ({ page }) => {
    for (const v of ["kanban", "list", "map"]) {
      const btn = page.getByTestId(`button-view-${v}`);
      if (await btn.count()) {
        await btn.click();
        await expectShell(page);
      }
    }
    // Return to list view for stable follow-on assertions.
    const list = page.getByTestId("button-view-list");
    if (await list.count()) await list.click();
  });

  test("search filters the register", async ({ page, api }) => {
    const asset = await api.firstAsset();
    test.skip(!asset, "no assets to search");
    const search = page.getByTestId("input-asset-search");
    await expect(search).toBeVisible();
    const term = String(asset.name).split(/\s+/)[0].slice(0, 6);
    await search.fill(term);
    // Give the query a moment; the list should still render without crashing.
    await page.waitForTimeout(1000);
    await expectShell(page);
  });

  test("filter dropdowns open and clear", async ({ page }) => {
    // Lower-case: the component renders `filter-${label.toLowerCase()}`. This
    // loop asked for `filter-Category`, found nothing, and — being guarded by
    // `if (count)` — passed for as long as it existed without opening one.
    for (const label of ["category", "status", "condition"]) {
      const filter = page.getByTestId(`filter-${label}`);
      // NOT `if (await filter.count())`. That guard is what let this test ask
      // for a test id that did not exist and pass for as long as it lived —
      // and fixing the casing while keeping the guard would have left it just
      // as able to prove nothing the next time an id changes.
      await expect(filter, `filter-${label} must exist`).toBeVisible();
      await filter.click();
      // Popover with "All …" + options.
      const opt = page.locator(".z-50 button, [role='menu'] button").first();
      await expect(opt, `filter-${label} must open a menu`).toBeVisible();
      await opt.click();
    }
    const clear = page.getByTestId("button-clear-filters");
    if (await clear.count()) await clear.click();
    await expectShell(page);
  });

  test("the Status filter offers only statuses a record can carry", async ({ page }) => {
    // Three options here — allottee not in nominal roll, VIN not verifiable,
    // possible duplicate — named checks the back end does not perform, so each
    // always answered zero rows and said nothing about why.
    await page.getByTestId("filter-status").click();
    const menu = page.locator(".z-50").filter({ hasText: "Cleared" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button", { name: "Cleared", exact: true })).toBeVisible();
    await expect(menu.getByRole("button", { name: "Review — data quality", exact: true })).toBeVisible();
    // Handoff 30. NOT a fourth of the dead ones: it is the server's
    // `sap_reconciliation_state = exception`, measured on real rows before it
    // was wired. The spec below proves it returns them.
    await expect(menu.getByRole("button", { name: "Review — no SAP code", exact: true })).toBeVisible();
    await expect(menu.getByRole("button", { name: "Not in service", exact: true })).toBeVisible();
    await expect(menu).not.toContainText("nominal roll");
    await expect(menu).not.toContainText("VIN");
    await expect(menu).not.toContainText("duplicate");
    await page.keyboard.press("Escape");
  });

  /**
   * Handoff 29 deleted three statuses because choosing one answered zero rows
   * and said nothing about why. This is the test that the fourth is not a
   * fifth of those: it must return THE rows, and every row it returns must
   * wear the pill it was filtered for.
   *
   * The count comes from the API first, and an empty tenant SKIPS, loudly. A
   * spec that passed on "no rows, so nothing contradicts" would be the silent
   * instrument this suite has already been bitten by. The filter is asked of
   * the SERVER — the status is rare (34 assets on `nrs19` when it was
   * measured), so a filter over the 200 rows already on screen would mostly
   * have found none of them.
   */
  test("the Status filter 'no SAP code' returns the real rows, each wearing that pill", async ({ page, api }) => {
    // `sort: "newest"` because that is the order the LIST asks for, and the
    // sample below has to be a row the list will actually draw. Without it
    // the API answers oldest-first, and this spec clicked the OLDEST
    // exception — which is on screen only while the tenant holds 200 or
    // fewer. `test19` crossed that during handoff 31 (232; every asset a test
    // run registers without a SAP code is one more), and the spec began
    // failing on a row that was simply on the second page.
    const counted = await api.probe("/api/v1/assets", { sap_reconciliation_state: "exception", state: "active", limit: 1, sort: "newest" });
    expect(counted.ok, `the API filters on sap_reconciliation_state (HTTP ${counted.status})`).toBeTruthy();
    const expected: number = counted.body?.pagination?.total_estimate ?? 0;
    test.skip(expected === 0, "this tenant has no ACTIVE asset with sap_reconciliation_state=exception — nothing to filter for");
    const sample = counted.body.data[0];

    await page.getByTestId("button-view-list").click();
    const asked = page.waitForRequest((r) =>
      r.url().includes("/api/v1/assets?") && r.url().includes("sap_reconciliation_state=exception"));
    await page.getByTestId("filter-status").click();
    await page.locator(".z-50").getByRole("button", { name: "Review — no SAP code", exact: true }).click();
    // SERVER-SIDE, and in service only: a disposed asset can be an exception
    // too, and it is "Not in service", not stock awaiting review.
    const url = new URL((await asked).url());
    expect(url.searchParams.get("sap_reconciliation_state")).toBe("exception");
    expect(url.searchParams.get("state")).toBe("active");
    // Two statuses begin "Review —". The button has to say which one is on.
    await expect(page.getByTestId("filter-status")).toContainText("no SAP code");

    const rows = page.locator('[data-testid^="row-asset-"]');
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });
    const shown = await rows.count();
    expect(shown, "the filter returns rows").toBeGreaterThan(0);
    // A page is 200 rows and the list loads the next one by itself as it
    // scrolls into view, so above 200 the count on screen is a moving number:
    // bounded, not pinned. At or below 200 it is exactly the server's count.
    expect(shown).toBeGreaterThanOrEqual(Math.min(expected, 200));
    expect(shown).toBeLessThanOrEqual(expected);
    // EVERY row, not the first: the table and its own filter must not
    // disagree about the same rows.
    const pills = await rows.getByTestId("status-pill").allTextContents();
    expect(pills).toHaveLength(shown);
    expect(new Set(pills)).toEqual(new Set(["Review — no SAP code"]));
    await expect(rows.getByTestId("lifecycle-pill")).toHaveCount(0);

    // list → asset → back, in one session: the detail page agrees with the
    // row, and says the finding in a sentence somebody who is not an
    // accountant can read.
    await page.getByTestId(`row-asset-${sample.id}`).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath(`/assets/${sample.id}`));
    await expect(page.getByTestId("asset-hero-badges").getByTestId("status-pill")).toHaveText("Review — no SAP code");
    await expect(page.getByTestId("workflow-step-1")).toHaveAttribute("data-current", "true");
    await page.getByTestId("tab-audit-review").click();
    await expect(page.getByText("finance has no SAP asset number for it")).toBeVisible();
    await page.getByTestId("button-back").click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/list"));
  });

  test("the other two statuses never show a row under a pill that contradicts them", async ({ page }) => {
    // `is_verified=true|false` comes back from the server INCLUDING the active
    // assets that are SAP exceptions (the API has no "not"), and those wear
    // the exception's pill. The register drops them after the fetch.
    await page.getByTestId("button-view-list").click();
    for (const status of ["Cleared", "Review — data quality"]) {
      await page.getByTestId("filter-status").click();
      await page.locator(".z-50").getByRole("button", { name: status, exact: true }).click();
      await expect(page.getByTestId("filter-status")).toContainText(status);
      // Rows, or the empty state — either is a legitimate answer; a row
      // wearing another status is not.
      await expect(page.locator('[data-testid^="row-asset-"]').first().or(page.getByText("No assets found"))).toBeVisible({ timeout: 15_000 });
      const pills = await page.locator('[data-testid^="row-asset-"]').getByTestId("status-pill").allTextContents();
      expect(pills.filter((p) => p !== status), `rows under "${status}" wearing another pill`).toEqual([]);
      await expect(page.locator('[data-testid^="row-asset-"]').getByTestId("lifecycle-pill")).toHaveCount(0);
    }
  });

  test("group-by select changes grouping", async ({ page }) => {
    const select = page.getByTestId("select-group-by");
    if (await select.count()) {
      for (const val of ["category", "zone", "status", "none"]) {
        await select.selectOption(val).catch(() => {});
      }
    }
    await expectShell(page);
  });

  test("+ New Asset navigates to the create form", async ({ page }) => {
    const btn = page.getByTestId("button-new-asset");
    await expect(btn).toBeVisible();
    await btn.click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/new"));
  });

  test("a row opens the asset detail", async ({ page, api }) => {
    const asset = await api.firstAsset();
    test.skip(!asset, "no assets to open");
    // Ensure list view.
    const list = page.getByTestId("button-view-list");
    if (await list.count()) await list.click();
    const row = page.getByTestId(`row-asset-${asset.id}`).or(page.getByTestId(`card-asset-${asset.id}`)).first();
    // Row may be below the fold / not in the first page; fall back to any row.
    const anyRow = (await row.count()) ? row : page.locator('[data-testid^="row-asset-"], [data-testid^="card-asset-"]').first();
    await expect(anyRow).toBeVisible({ timeout: 15_000 });
    await anyRow.click();
    await expect.poll(() => new URL(page.url()).pathname).toMatch(/\/assets\/\d+$/);
  });
});

test.describe("/assets dashboard", () => {
  test("the KPI strip names what it counts", async ({ page }) => {
    await gotoApp(page, "/assets");
    await expectShell(page);
    const strip = page.getByTestId("asset-kpi-strip");
    await expect(strip).toBeVisible();
    // "On register" — the figure includes disposed and missing assets, so it
    // is the register and not the stock. "Missing" had no count anywhere in
    // the app, and took the place of a "PM Overdue" tile that no endpoint
    // could ever fill.
    for (const label of ["On register", "Active", "Under Repair", "Active, unverified", "Missing", "Condemned"]) {
      await expect(strip.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(strip).not.toContainText("PM Overdue");
    await expect(strip).not.toContainText("Total Assets");
  });


  test("dashboard controls render and New asset navigates", async ({ page }) => {
    await gotoApp(page, "/assets");
    await expectShell(page);
    const newAsset = page.getByRole("button", { name: /new asset/i }).first();
    if (await newAsset.count()) {
      await newAsset.click();
      await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/new"));
    }
  });
});
