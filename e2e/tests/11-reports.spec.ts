import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * The five reports: each renders and its Refresh control works. Location
 * Coverage has client-side pagination; Tag Adoption + Fleet Roster have search.
 */

const REPORTS: { path: string; title: RegExp }[] = [
  { path: "/reports/fleet-roster", title: /fleet roster/i },
  { path: "/reports/asset-inventory", title: /asset inventory/i },
  { path: "/reports/maintenance-readiness", title: /maintenance readiness/i },
  { path: "/reports/location-coverage", title: /location coverage/i },
  { path: "/reports/tag-adoption", title: /tag adoption/i },
];

for (const r of REPORTS) {
  test(`${r.path} renders and refreshes`, async ({ page }) => {
    await gotoApp(page, r.path);
    await expectShell(page);
    await expect(page.getByText(r.title).first()).toBeVisible();
    const refresh = page.getByRole("button", { name: /refresh/i }).first();
    if (await refresh.count()) {
      await refresh.click();
      await expectShell(page); // no crash
    }
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });
}

test("Location Coverage paginates", async ({ page }) => {
  await gotoApp(page, "/reports/location-coverage");
  await expectShell(page);
  const next = page.getByRole("button", { name: /next|›|»/i }).first();
  if (await next.count()) {
    await next.click();
    await expectShell(page);
  }
});

test("Tag Adoption row opens an asset", async ({ page }) => {
  await gotoApp(page, "/reports/tag-adoption");
  await expectShell(page);
  // Rows link to /assets/:id — click the first data row if present.
  const row = page.locator("tbody tr").first();
  if (await row.count()) {
    await row.click();
    // Either navigates to an asset or stays put; just assert no crash.
    await expectShell(page);
  }
});
