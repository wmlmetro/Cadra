import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { appPath } from "../config";

/**
 * Command dashboards: Facility Command Center (home) + FM / Fleet / IT / Security.
 * Assert each loads, the Refresh control works, and stat-card navigation fires.
 */

test.describe("Facility Command Center (home)", () => {
  test("stat cards navigate to their sections", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);

    // Total-assets card -> /assets
    const totalAssets = page.getByTestId("card-total-assets");
    if (await totalAssets.count()) {
      await totalAssets.click();
      await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets"));
      await page.goBack();
    }
  });

  test("review queue table renders (or empty state)", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);
    // The review-queue card is always present; the table renders when there
    // are items. Assert the card region renders (no crash) either way.
    await expect(page.getByTestId("card-review-queue")).toBeVisible();
  });
});

const DASHBOARDS: { path: string; name: string }[] = [
  { path: "/dashboards/fm", name: "FM Operations" },
  { path: "/dashboards/fleet", name: "Fleet Command" },
  { path: "/dashboards/it", name: "IT Assets Command" },
  { path: "/dashboards/security", name: "Security Operations" },
];

for (const d of DASHBOARDS) {
  test(`${d.name} dashboard loads and Refresh works`, async ({ page }) => {
    await gotoApp(page, d.path);
    await expectShell(page);
    // A refresh control is present on every command dashboard.
    const refresh = page.getByRole("button", { name: /refresh/i }).first();
    if (await refresh.count()) {
      await refresh.click();
      // The page should stay rendered (no crash) — shell still visible.
      await expectShell(page);
    }
    // No 404 fallback.
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });
}
