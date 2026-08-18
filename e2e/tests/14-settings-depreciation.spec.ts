import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Settings → Depreciation.
 *
 * Every control here restates book value across the register, so the tests
 * restore whatever they change. They deliberately avoid asserting specific
 * figures — those depend on tenant data — and assert behaviour instead.
 */

test.describe("/settings/depreciation", () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page, "/settings/depreciation");
    await expectShell(page);
  });

  test("renders the settings surface", async ({ page }) => {
    await expect(page.getByText("Depreciation settings")).toBeVisible();
    await expect(page.getByTestId("mode-computed")).toBeVisible();
    await expect(page.getByTestId("mode-erp_managed")).toBeVisible();
    await expect(page.getByTestId("toggle-db-switch")).toBeVisible();
    await expect(page.getByTestId("button-recompute")).toBeVisible();
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });

  test("lists categories with an editable policy", async ({ page }) => {
    await expect(page.getByText("Policy by asset category")).toBeVisible();
    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(0);
    // Method is a real select, not a label.
    await expect(rows.first().locator("select")).toBeVisible();
  });

  test("the straight-line switch persists across a reload", async ({ page }) => {
    const toggle = page.getByTestId("toggle-db-switch");
    const before = await toggle.isChecked();
    try {
      await toggle.click();
      // The mutation recomputes the register, so give it room.
      await expect(toggle).toBeChecked({ checked: !before, timeout: 30_000 });

      await page.reload();
      await expectShell(page);
      await expect(page.getByTestId("toggle-db-switch"))
        .toBeChecked({ checked: !before, timeout: 30_000 });
    } finally {
      const t = page.getByTestId("toggle-db-switch");
      if (await t.isChecked() !== before) {
        await t.click();
        await expect(t).toBeChecked({ checked: before, timeout: 30_000 });
      }
    }
  });

  test("recompute reports back", async ({ page }) => {
    await page.getByTestId("button-recompute").click();
    await expect(page.getByText(/Recomputed .* assets/i)).toBeVisible({ timeout: 60_000 });
  });

  test("ERP-managed mode disables the calculation controls", async ({ page }) => {
    const computed = page.getByTestId("mode-computed");
    try {
      await page.getByTestId("mode-erp_managed").click();
      await expect(page.getByText(/This tenant is ERP-managed/i))
        .toBeVisible({ timeout: 30_000 });
      // Cadra must not offer to compute what it does not own.
      await expect(page.getByTestId("toggle-db-switch")).toBeDisabled();
      await expect(page.getByTestId("button-recompute")).toBeDisabled();
    } finally {
      await computed.click();
      await expect(page.getByText(/This tenant is ERP-managed/i))
        .toHaveCount(0, { timeout: 30_000 });
    }
  });
});
