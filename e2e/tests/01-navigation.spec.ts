import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { appPath } from "../config";

/**
 * Reach every route and every visible sidebar nav item; assert each renders the
 * authenticated shell with no uncaught page error (console-guard fixture) and
 * does NOT collapse into the 404 page.
 */

// Static routes (no path params) from the router inventory.
const STATIC_ROUTES: string[] = [
  "/",
  "/dashboards/fm",
  "/dashboards/fleet",
  "/dashboards/it",
  "/dashboards/security",
  "/tools/barcode",
  "/service-desk",
  "/service-desk/new",
  "/service-desk/triage",
  "/assets",
  "/assets/list",
  "/assets/new",
  "/locations",
  "/locations/new",
  "/reports/fleet-roster",
  "/reports/asset-inventory",
  "/reports/maintenance-readiness",
  "/reports/location-coverage",
  "/reports/tag-adoption",
  "/hr/sap-sync",
  "/hr/import",
  "/hr/employees",
  "/hr/identity",
  "/fleet",
  "/fleet/staff-bus",
];

test.describe("route reachability", () => {
  for (const route of STATIC_ROUTES) {
    test(`renders ${route}`, async ({ page }) => {
      await gotoApp(page, route);
      await expectShell(page);
      // The NotFound page shows a big "404". A real route must not render it.
      await expect(page.getByText(/^404$/).first()).toHaveCount(0);
    });
  }

  test("unknown route renders the 404 page", async ({ page }) => {
    await gotoApp(page, "/this-route-does-not-exist-xyz");
    // NotFound still renders inside the shell.
    await expect(page.getByText(/404|not found/i).first()).toBeVisible();
  });
});

test.describe("dynamic detail routes (real IDs)", () => {
  test("asset detail /assets/:id", async ({ page, api }) => {
    const a = await api.firstAsset();
    test.skip(!a, "no assets in tenant to open");
    await gotoApp(page, `/assets/${a.id}`);
    await expectShell(page);
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });

  test("location detail /locations/:id", async ({ page, api }) => {
    const l = await api.firstLocation();
    test.skip(!l, "no locations in tenant to open");
    await gotoApp(page, `/locations/${l.id}`);
    await expectShell(page);
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });

  test("employee detail /hr/employees/:id", async ({ page, api }) => {
    const e = await api.firstEmployee();
    test.skip(!e, "no employees in tenant to open");
    await gotoApp(page, `/hr/employees/${e.id}`);
    await expectShell(page);
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });

  test("request detail /service-desk/:id", async ({ page, api }) => {
    const r = await api.firstRequest();
    test.skip(!r, "no requests in tenant to open");
    await gotoApp(page, `/service-desk/${r.id}`);
    await expectShell(page);
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });
});

// Every visible sidebar nav item -> [testid, expected path fragment].
const NAV_ITEMS: [string, string][] = [
  ["nav-facility-command-center", "/"],
  ["nav-fleet-command", "/dashboards/fleet"],
  ["nav-it-assets-command", "/dashboards/it"],
  ["nav-dashboard", "/assets"],
  ["nav-all-assets", "/assets/list"],
  ["nav-+-new-asset", "/assets/new"],
  ["nav-locations", "/locations"],
  ["nav-+-new-location", "/locations/new"],
  ["nav-employees", "/hr/employees"],
  ["nav-sap-sync", "/hr/sap-sync"],
  ["nav-bulk-import", "/hr/import"],
  ["nav-identity-(clearance)", "/hr/identity"],
  ["nav-fleet", "/fleet"],
  ["nav-staff-bus", "/fleet/staff-bus"],
  ["nav-fleet-roster", "/reports/fleet-roster"],
  ["nav-asset-inventory", "/reports/asset-inventory"],
  ["nav-maintenance-readiness", "/reports/maintenance-readiness"],
  ["nav-location-coverage", "/reports/location-coverage"],
  ["nav-tag-adoption", "/reports/tag-adoption"],
  ["nav-barcode-station", "/tools/barcode"],
];

test.describe("sidebar navigation", () => {
  test("every visible nav item navigates to its route", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);
    for (const [testid, path] of NAV_ITEMS) {
      const item = page.getByTestId(testid);
      await expect(item, `nav item ${testid} should be visible`).toBeVisible();
      await item.click();
      await expect
        .poll(() => new URL(page.url()).pathname, { timeout: 10_000 })
        .toBe(appPath(path));
    }
  });
});
