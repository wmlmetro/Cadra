import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Locations: list controls, create form (with coordinate preview), edit, and
 * the detail page (descendants + map).
 */

test.describe("/locations list", () => {
  test("list renders and + New Location navigates", async ({ page }) => {
    await gotoApp(page, "/locations");
    await expectShell(page);
    const newBtn = page.getByTestId("button-new-location").or(
      page.getByRole("button", { name: /new location/i }),
    ).first();
    await expect(newBtn).toBeVisible();
    await newBtn.click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/locations/new"));
  });

  test("view switchers and clear render", async ({ page }) => {
    await gotoApp(page, "/locations");
    await expectShell(page);
    // Tree/Cards/List buttons — best-effort by accessible name.
    for (const name of ["Tree", "Cards", "List"]) {
      const b = page.getByRole("button", { name: new RegExp(`^${name}$`, "i") }).first();
      if (await b.count()) await b.click();
    }
    await expectShell(page);
  });
});

test("create a location end-to-end", async ({ page }) => {
  await gotoApp(page, "/locations/new");
  await expectShell(page);

  const create = page.getByRole("button", { name: "Create location" });
  await expect(create).toBeDisabled();

  const name = markedName("Test Location");
  await page.getByRole("textbox").first().fill(name);
  await expect(create).toBeEnabled();

  // Type + coordinates (coordinates render a live map preview).
  await page.locator("select").first().selectOption("building").catch(() => {});
  await page.getByPlaceholder("e.g. 9.0820").fill("9.0820");
  await page.getByPlaceholder("e.g. 8.6753").fill("8.6753");
  // Coordinate preview map should appear.
  await expect(page.getByText(/coordinate preview/i)).toBeVisible();

  await create.click();
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toMatch(/\/locations\/\d+$/);
  const id = new URL(page.url()).pathname.match(/\/locations\/(\d+)/)?.[1];
  recordCreated({ kind: "location", id, name });
  await expect(page.getByText(name).first()).toBeVisible();
});

test("edit a location and persist", async ({ page, api }) => {
  const original = markedName("Edit Loc");
  const created = await api.post("/api/v1/locations", { name: original });
  const id = created?.id;
  test.skip(!id, "could not create a location to edit");
  recordCreated({ kind: "location", id, name: original });

  await gotoApp(page, `/locations/${id}/edit`);
  await expectShell(page);
  const nameInput = page.getByRole("textbox").first();
  await expect(nameInput).toHaveValue(original, { timeout: 15_000 });
  const updated = `${original} EDITED`;
  await nameInput.fill(updated);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(`/app/locations/${id}`);

  const fresh = await api.get(`/api/v1/locations/${id}`);
  expect(fresh?.name).toBe(updated);
});

test("location detail renders", async ({ page, api }) => {
  const loc = await api.firstLocation();
  test.skip(!loc, "no locations to open");
  await gotoApp(page, `/locations/${loc.id}`);
  await expectShell(page);
  // Edit button present.
  await expect(page.getByRole("button", { name: /^edit$/i }).first()).toBeVisible();
});
