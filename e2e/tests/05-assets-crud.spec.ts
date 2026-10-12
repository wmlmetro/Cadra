import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { aSerialClass, receiptGated } from "../fixtures/gates";

/**
 * Asset create + edit via the real form. Records are marked (E2E-*) for cleanup.
 * No hard delete exists — created assets persist (see report).
 */

test("create form gates submit until Name is set", async ({ page }) => {
  await gotoApp(page, "/assets/new");
  await expectShell(page);
  const create = page.getByRole("button", { name: "Create asset" });
  await expect(create).toBeDisabled();
  await page.getByRole("textbox").first().fill(markedName("Gate Check"));
  await expect(create).toBeEnabled();
});

test("create an asset end-to-end", async ({ page, api }) => {
  await gotoApp(page, "/assets/new");
  await expectShell(page);

  const name = markedName("Test Asset");
  await page.getByRole("textbox").first().fill(name);

  // category_id is required by the API. The form's first number input is the
  // "Category id" field (no category list endpoint yet, so it takes a raw FK).
  //
  // Handoff 58: with the receipt gates on, this form makes a RECEIPT, and a
  // receipt carries what its class says identifies it (Section 12) or it is
  // refused 400 at the door — a serial, a make and a model for a `serial`
  // class. The form has those three inputs (and none for a `tag_id` class's
  // attributes), so the unit is of a serial class and they are typed. What
  // lands is a candidate; its page opens all the same.
  const gated = await receiptGated(api);
  const categoryId = gated ? await aSerialClass(api) : await api.firstCategoryId();
  test.skip(!categoryId, "no category id available in tenant");
  await page.getByRole("spinbutton").first().fill(String(categoryId));
  if (gated) {
    const field = (label: RegExp) => page.locator("label", { hasText: label }).first().locator("xpath=following::input[1]");
    await field(/^\s*serial number/i).fill(`E2E-SN05-${Date.now()}`);
    await field(/^\s*make/i).fill("E2E Make");
    await field(/^\s*model/i).fill("E2E Model");
  }

  // Exercise the location RecordPicker (best-effort — skip the pick if the
  // tenant search returns nothing for our query, but still create the asset).
  const loc = await api.firstLocation();
  if (loc?.name) {
    const q = String(loc.name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 5);
    if (q.length >= 2) await pickRecord(page, "Search locations", q);
  }

  await page.getByRole("button", { name: "Create asset" }).click();

  // Success -> asset detail /assets/:id
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toMatch(/\/assets\/\d+$/);
  const id = new URL(page.url()).pathname.match(/\/assets\/(\d+)/)?.[1];
  recordCreated({ kind: "asset", id, name });
  await expect(page.getByRole("heading", { name })).toBeVisible();
});

test("edit an asset and persist the change", async ({ page, api }) => {
  // Create a target via API so the edit test is independent of the create test.
  const original = markedName("Edit Target");
  const created = await api.createAsset(original);
  const id = created?.id;
  test.skip(!id, "could not create an asset to edit");
  recordCreated({ kind: "asset", id, name: original });

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);

  const nameInput = page.getByRole("textbox").first();
  await expect(nameInput).toHaveValue(original, { timeout: 15_000 });
  const updated = `${original} EDITED`;
  await nameInput.fill(updated);
  await page.getByRole("button", { name: "Save changes" }).click();

  // Lands back on detail; heading reflects the new name.
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(`/app/assets/${id}`);
  await expect(page.getByRole("heading", { name: updated })).toBeVisible();

  // Confirm persisted on the server, not just in the UI cache.
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.name).toBe(updated);
});
