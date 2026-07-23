import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { ORIGIN } from "../config";

/**
 * Per-tenant branding: /api/v1/brand drives the tenant identity, and the SPA
 * themes itself from it at boot. Jaiz-specific assertions (#004080) run only
 * when the target host is the Jaiz tenant, so the suite also works in CI
 * against whatever tenant the pipeline seeds.
 */
const IS_JAIZ = /jaiz/i.test(ORIGIN);

test("brand endpoint returns a valid tenant identity", async ({ api }) => {
  const brand = await api.brand();
  expect(brand?.name, "brand name should be present").toBeTruthy();
  expect(String(brand?.primary), "brand primary colour should be a hex value").toMatch(/^#?[0-9a-f]{3,8}$/i);
  expect(brand?.logo, "brand logo should be present").toBeTruthy();
  if (IS_JAIZ) {
    expect(brand?.name).toMatch(/jaiz/i);
    expect(String(brand?.primary).toLowerCase()).toBe("#004080");
    expect(brand?.short_name ?? brand?.name).toMatch(/jaiz/i);
  }
});

test("document title and favicon present", async ({ page }) => {
  await gotoApp(page, "/");
  await expectShell(page);
  await expect(page).toHaveTitle(/cadra/i);
  const favicon = page.locator('link[rel="icon"]');
  await expect(favicon).toHaveCount(1);
});

test("brand logo renders in the sidebar", async ({ page }) => {
  await gotoApp(page, "/");
  await expectShell(page);
  // Sidebar logo <img alt="Jaiz Bank Plc"> (alt = brand name).
  const logo = page.locator('aside img').first();
  await expect(logo).toBeVisible();
  const alt = await logo.getAttribute("alt");
  expect(alt).toMatch(/jaiz/i);
});

test("active nav item uses the Jaiz brand colour", async ({ page }) => {
  await gotoApp(page, "/");
  await expectShell(page);
  const active = page.getByTestId("nav-facility-command-center");
  // Active item background is set to brand primary (#004080 -> rgb(0,64,128)).
  const bg = await active.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg.replace(/\s/g, "")).toBe("rgb(0,64,128)");
});
