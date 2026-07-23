import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Asset lifecycle actions from the detail page.
 *
 * WORKS in the UI: tabs, Mark verified, Mark missing (native confirm), Condemn.
 * BROKEN in the UI (confirmed bugs, encoded as test.fail): Move and Transfer
 * custody — moveAsset()/transferCustody() map the {asset, transfer|custody_change}
 * envelope through apiAssetToAsset() as if it were a bare asset, so
 * buildAssetLocation() dereferences an undefined location_hierarchy and throws
 * "Cannot read properties of undefined (reading 'building')". The dialog stays
 * open with a red error even though the server-side change DID persist (proven
 * by the API-level tests below). See the report's confirmed-findings section.
 */

async function createAsset(api: ApiClient, label: string, extra: Record<string, unknown> = {}): Promise<string> {
  const name = markedName(label);
  const created = await api.createAsset(name, extra);
  recordCreated({ kind: "asset", id: created?.id, name });
  return String(created.id);
}

test("detail tabs switch", async ({ page, api }) => {
  const id = await createAsset(api, "Tabs");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  for (const tab of ["tab-details", "tab-custodian-assignment", "tab-audit-review", "tab-legacy-data"]) {
    const t = page.getByTestId(tab);
    await expect(t, `${tab} present`).toBeVisible();
    await t.click();
  }
});

test("mark verified (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Verify");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-verify").click();
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.is_verified, { timeout: 15_000 })
    .toBeTruthy();
});

test("mark missing via native confirm (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Missing");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("button-missing").click();
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("missing");
});

test("condemn soft-deletes to disposed (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Condemn");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-condemn").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const condemnBtn = dialog.getByRole("button", { name: "Condemn" });
  await expect(condemnBtn).toBeDisabled();
  await dialog.getByPlaceholder(/required/i).fill("E2E disposal test");
  await expect(condemnBtn).toBeEnabled();
  await condemnBtn.click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("disposed");
});

// ── Move ─────────────────────────────────────────────────────────────────────

test("move persists server-side (API)", async ({ api }) => {
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const id = await createAsset(api, "MoveApi", { location_id: locs[0].id });
  await api.post(`/api/v1/assets/${id}/move`, { to_location_id: locs[1].id, reason: "e2e" });
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.current_location?.id).toBe(locs[1].id);
});

test("move via UI closes the dialog and persists", async ({ page, api }) => {
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const id = await createAsset(api, "MoveUI", { location_id: locs[0].id });
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-move").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const q = String(locs[1].name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 6);
  const picked = await pickRecord(dialog, "Search locations", q.length >= 2 ? q : "of");
  test.skip(!picked, "location search returned no options");
  await dialog.getByPlaceholder(/floor reorganisation|reason/i).fill("E2E move");
  await dialog.getByRole("button", { name: "Move asset" }).click();
  // Fixed: the envelope is mapped correctly, so the move succeeds and closes.
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_location?.id, { timeout: 15_000 })
    .toBe(locs[1].id);
});

// ── Transfer custody ──────────────────────────────────────────────────────────

test("transfer custody persists server-side (API)", async ({ api }) => {
  const emp = await api.firstEmployee();
  test.skip(!emp, "no employees");
  const id = await createAsset(api, "CustodyApi");
  await api.post(`/api/v1/assets/${id}/transfer-custody`, { to_custodian_id: emp.id, reason: "e2e" });
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.current_custodian?.id).toBe(emp.id);
});

test("transfer custody via UI closes the dialog and persists", async ({ page, api }) => {
  const emp = await api.firstEmployee();
  test.skip(!emp, "no employees");
  const id = await createAsset(api, "CustodyUI");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-transfer-custody").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const q = String(emp.name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 5);
  const picked = await pickRecord(dialog, "Search employees", q.length >= 2 ? q : "mo");
  test.skip(!picked, "employee search returned no options");
  await dialog.getByRole("button", { name: "Transfer custody" }).click();
  // Fixed: the envelope is mapped correctly, so the transfer succeeds and closes.
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id, { timeout: 15_000 })
    .toBe(emp.id);
});

// ── Business rule ─────────────────────────────────────────────────────────────

test("move to the same location is rejected", async ({ page, api }) => {
  const loc = (await api.twoBuildings())[0];
  test.skip(!loc, "no building location available");
  const id = await createAsset(api, "SameLoc", { location_id: loc.id });

  // UI: the Move dialog opens.
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-move").click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // API: same-location move is rejected.
  let rejected = false;
  try {
    await api.post(`/api/v1/assets/${id}/move`, { to_location_id: loc.id, reason: "same-loc" });
  } catch (e) {
    rejected = /same|conflict|unprocess|validation|invalid|422/i.test(String(e));
  }
  expect(rejected, "moving to the current location should be rejected").toBeTruthy();
});
