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

/**
 * Handoff 27. NRS opened Audit & Review expecting an asset's history and got
 * a status pill and empty space — and "detail tabs switch" above was green the
 * whole time, because it clicks the tab and never reads it. These two read it.
 */
test("audit & review says in words when there is no history", async ({ page, api }) => {
  const id = await createAsset(api, "HistoryEmpty");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("tab-audit-review").click();
  await expect(page.getByTestId("asset-history-empty")).toContainText(
    "There is no recorded history for this asset",
  );
  // The registration is still shown, the list says where it begins, and what
  // is never recorded is named — an empty history is not an empty panel.
  await expect(page.getByTestId("asset-history-event").first()).toBeVisible();
  await expect(page.getByTestId("asset-history-begins")).toBeVisible();
  await expect(page.getByTestId("asset-history-not-recorded")).toContainText("does not record");
});

test("audit & review shows a verification, newest first, with what its record is worth", async ({ page, api }) => {
  const id = await createAsset(api, "HistoryVerify");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-verify").click();
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.is_verified, { timeout: 15_000 })
    .toBeTruthy();
  await page.getByTestId("tab-audit-review").click();
  const rows = page.getByTestId("asset-history-event");
  // Newest first: the verification just made is above the registration, and
  // the mutation invalidated the history so no reload was needed to see it.
  await expect(rows.first()).toContainText("Verified");
  // Verify is a PATCH of a date: a message-log line is ALL that records it.
  await expect(rows.first()).toContainText("Message log only");
  await expect(rows.last()).toContainText("Registered");
  await expect(page.getByTestId("asset-history-empty")).toHaveCount(0);
});

test("audit & review carries a reconstruction and a blank actor all the way to the screen", async ({ page, api }) => {
  // Canned, because no test tenant holds a `tracking_backfill` link or a
  // record that names nobody — and those are the two rows an auditor is most
  // misled by if the adapter or the component quietly drops the distinction.
  // The builder's side of both is asserted in-registry; this is the last hop.
  const id = await createAsset(api, "HistoryCanned");
  await page.route(`**/api/v1/assets/${id}/history*`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        meta: { request_id: "e2e", timestamp: "2026-09-20T00:00:00Z", version: "v1" },
        data: {
          asset: { id: Number(id), asset_code: "E2E", name: "canned" },
          order: "newest_first",
          summary: { events: 2, events_after_registration: 1, by_evidence: {}, reconstructed_events: 1,
                     statement: "1 recorded event(s) since registration." },
          fidelity: {
            registered_at: "2026-08-06T09:00:00", earliest_event_after_registration_at: "2026-08-10T09:00:00",
            custody: { recording_began_at: "2026-09-09T16:12:06", links: 1, reconstructed_links: 1,
                       first_link_at: "2026-08-10T09:00:00", custodian_held_before_first_link: true,
                       statement: "This asset was already held by somebody when custody recording reached it." },
            evidence_grades: [{ grade: "append_only", meaning: "Cannot be edited or deleted." }],
            not_recorded: [{ event: "financial_change", statement: "A change to a cost." }],
            verification: "", undated_records_omitted: 0,
          },
          events: [
            { id: "custody_changed:nrs.asset.custody:1", type: "custody_changed", title: "Custodian changed",
              summary: "unassigned → Ada", at: "2026-08-10T09:00:00", at_precision: "second",
              actor: null, actor_name: null, evidence: "append_only", reconstructed: true,
              source: "tracking_backfill", record: { model: "nrs.asset.custody", id: 1 }, detail: {} },
            { id: "a_type_from_the_future:x:2", type: "a_type_from_the_future", title: "Something new",
              summary: "An event this build has never heard of", at: "2026-08-06", at_precision: "day",
              actor: { id: 2, name: "Ada" }, actor_name: "Ada", evidence: "a_grade_from_the_future",
              reconstructed: false, source: null, record: { model: "x", id: 2 }, detail: {} },
          ],
        },
      }),
    }),
  );
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("tab-audit-review").click();
  const rows = page.getByTestId("asset-history-event");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("Reconstructed");
  await expect(rows.first()).toContainText("No person recorded");
  await expect(rows.first()).not.toContainText("System");
  // An unknown type and an unknown grade still render, from the server's words.
  await expect(rows.last()).toContainText("Something new");
  await expect(rows.last()).toContainText("a_grade_from_the_future");
  await expect(rows.last()).toContainText("2026-08-06");
  await expect(rows.last()).not.toContainText("00:00");
  // Held by somebody the chain never saw arrive: a notice, not muted text.
  await expect(page.getByTestId("asset-history-begins")).toContainText("already held by somebody");
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
