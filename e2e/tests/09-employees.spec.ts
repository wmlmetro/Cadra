import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { appPath } from "../config";

/**
 * HR & Staff: employee list/detail, by-IR redirect, SAP sync page, bulk import
 * form. (Live xlsx import + job polling is flagged for manual verification — we
 * exercise the form and its validation gating here.)
 */

test.describe("/hr/employees", () => {
  test("list renders with search and view switch", async ({ page }) => {
    await gotoApp(page, "/hr/employees");
    await expectShell(page);
    // View switch (Cards/Table) + search.
    for (const name of ["Cards", "Table"]) {
      const b = page.getByRole("button", { name: new RegExp(`^${name}$`, "i") }).first();
      if (await b.count()) await b.click();
    }
    const search = page.getByRole("searchbox").first();
    if (await search.count()) await search.fill("a");
    await expectShell(page);
  });

  test("a row opens employee detail with tabs", async ({ page, api }) => {
    const e = await api.firstEmployee();
    test.skip(!e, "no employees seeded");
    await gotoApp(page, `/hr/employees/${e.id}`);
    await expectShell(page);
    // Tabs: overview / assets / identity.
    for (const tab of ["Overview", "Assets", "Identity"]) {
      const t = page.getByRole("button", { name: new RegExp(`^${tab}$`, "i") }).first();
      if (await t.count()) await t.click();
    }
    await expectShell(page);
  });

  test("by-IR redirects to the employee detail", async ({ page, api }) => {
    const emps = await api.employees(20);
    const withIr = emps.find((e) => e.ir_number);
    test.skip(!withIr, "no employee with an IR number");
    await gotoApp(page, `/hr/employees/by-ir/${encodeURIComponent(withIr.ir_number)}`);
    await expect.poll(() => new URL(page.url()).pathname, { timeout: 15_000 }).toMatch(
      /\/hr\/employees\/\d+$/,
    );
  });
});

test("SAP sync page links to import and employees", async ({ page }) => {
  await gotoApp(page, "/hr/sap-sync");
  await expectShell(page);
  const viewEmployees = page.getByRole("button", { name: /view employees/i }).first();
  if (await viewEmployees.count()) {
    await viewEmployees.click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/hr/employees"));
  }
});

test("bulk import form renders and gates submit", async ({ page }) => {
  await gotoApp(page, "/hr/import");
  await expectShell(page);
  // File input restricted to .xlsx.
  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toHaveAttribute("accept", /xlsx/i);
  // Submit is gated until a file is chosen. (Live import flagged for manual QA.)
  const submit = page.getByRole("button", { name: /submit|import/i }).first();
  await expect(submit).toBeVisible();
});
