import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Settings → Branding.
 *
 * Branding is visible to every user on the tenant, so anything that changes it
 * restores afterwards — including on failure.
 */

test.describe("/settings/branding", () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page, "/settings/branding");
    await expectShell(page);
  });

  test("shows the tenant's current brand", async ({ page, api }) => {
    const brand = await api.get("/api/v1/settings/branding");
    await expect(page.getByTestId("brand-name")).toHaveValue(brand.name);
    await expect(page.getByTestId("brand-short-name")).toHaveValue(brand.short_name ?? "");
    // Nothing edited yet, so there is nothing to save.
    await expect(page.getByTestId("brand-save")).toBeDisabled();
  });

  test("rejects a malformed colour before allowing a save", async ({ page }) => {
    await page.getByTestId("brand-primary").fill("not-a-colour");
    await expect(page.getByText(/must be 6-digit hex/i)).toBeVisible();
    await expect(page.getByTestId("brand-save")).toBeDisabled();
  });

  test("saving a colour repaints the app immediately", async ({ page, api }) => {
    const before = await api.get("/api/v1/settings/branding");
    const pill = page.getByTestId("brand-pill").first();

    try {
      await page.getByTestId("brand-primary").fill("#7B1FA2");
      await page.getByTestId("brand-save").click();
      await expect(page.getByText("Branding saved.")).toBeVisible({ timeout: 20_000 });

      // The point of this page: the running app restyles without a reload.
      await expect(pill).toHaveCSS("background-color", "rgb(123, 31, 162)", { timeout: 10_000 });

      // And it really persisted, not just repainted locally.
      const after = await api.get("/api/v1/settings/branding");
      expect(after.primary).toBe("#7B1FA2");
    } finally {
      await api.patch("/api/v1/settings/branding", {
        primary: before.primary,
        primary_dark: before.primary_dark,
      });
    }
  });
});
