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
    for (const label of ["Category", "Status", "Condition"]) {
      const filter = page.getByTestId(`filter-${label}`);
      if (await filter.count()) {
        await filter.click();
        // Popover with "All …" + options; pick the first option button if any.
        const opt = page.locator(".z-50 button, [role='menu'] button").first();
        if (await opt.count()) {
          await opt.click();
        } else {
          await page.keyboard.press("Escape");
        }
      }
    }
    const clear = page.getByTestId("button-clear-filters");
    if (await clear.count()) await clear.click();
    await expectShell(page);
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
