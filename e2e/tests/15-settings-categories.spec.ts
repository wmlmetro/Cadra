import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Settings → Asset Categories.
 *
 * Tests that mutate clean up after themselves: categories are shared config,
 * and a stray one shows up in every asset form on the tenant.
 */

test.describe("/settings/categories", () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page, "/settings/categories");
    await expectShell(page);
  });

  test("lists categories with editable fields", async ({ page }) => {
    await expect(page.getByText("Asset categories")).toBeVisible();
    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(0);
    // Name is an input and FM domain a select — this is an editor, not a list.
    // Since handoff 58 the row carries a SECOND select, how the class is
    // identified (Section 12), so the FM domain's is named by excluding it.
    await expect(rows.first().locator("input").first()).toBeVisible();
    await expect(rows.first().locator('select:not([data-testid^="select-identification-mode-"])')).toBeVisible();
    await expect(rows.first().locator('[data-testid^="select-identification-mode-"]')).toBeVisible();
  });

  test("a category holding assets cannot be deleted", async ({ page, api }) => {
    const cats = await api.get("/api/v1/asset-categories");
    const inUse = (cats ?? []).find((c: any) => c.asset_count > 0);
    test.skip(!inUse, "no category holds assets on this tenant");

    // Deleting it would orphan assets — category_id is required on nrs.asset.
    await expect(page.getByTestId(`delete-cat-${inUse.id}`)).toBeDisabled();
  });

  test("creates and deletes a category", async ({ page, api }) => {
    const name = `e2e-category-${Date.now()}`;

    await page.getByTestId("button-add-category").click();
    await page.getByTestId("new-category-name").fill(name);
    await page.getByTestId("submit-new-category").click();

    await expect(page.getByText(`Created ${name}.`)).toBeVisible({ timeout: 20_000 });

    const cats = await api.get("/api/v1/asset-categories");
    const made = (cats ?? []).find((c: any) => c.name === name);
    expect(made, "category should exist via the API").toBeTruthy();

    // A brand-new category holds nothing, so delete is offered. The
    // confirmation is the app's own dialog since handoff 29 — it was
    // `window.confirm`, which this spec accepted with `page.once("dialog")`.
    // A native dialog firing now is a regression, so it is recorded and the
    // test fails on it below.
    const fired: string[] = [];
    page.on("dialog", async (d) => { fired.push(d.message()); await d.dismiss(); });
    await page.getByTestId(`delete-cat-${made.id}`).click();
    const confirm = page.getByTestId("dialog-delete-category");
    await expect(confirm).toBeVisible();
    await expect(confirm).toContainText(name);
    await expect(confirm).toContainText("This cannot be undone");
    await page.getByTestId("button-confirm-delete-category").click();
    await expect(confirm).toBeHidden({ timeout: 20_000 });
    expect(fired, "no native browser dialog may fire").toEqual([]);
    await expect(page.getByText(`Deleted ${name}.`)).toBeVisible({ timeout: 20_000 });

    const after = await api.get("/api/v1/asset-categories");
    expect((after ?? []).some((c: any) => c.id === made.id)).toBe(false);
  });

  test("links to depreciation settings without leaving the SPA", async ({ page }) => {
    await page.getByRole("link", { name: /Settings.*Depreciation/i }).click();
    await expectShell(page);
    await expect(page.getByText("Depreciation settings")).toBeVisible();
  });
});
