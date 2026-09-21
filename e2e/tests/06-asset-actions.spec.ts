import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { appPath } from "../config";

/**
 * Asset lifecycle actions from the detail page.
 *
 * Everything here is expected to PASS; there is no `test.fail` in this file.
 * Covered in the UI: the detail tabs, the Audit & Review history (live and
 * canned), Mark verified, Mark missing (the app's own dialog — it was a
 * native `window.confirm` until handoff 29), Condemn, Move and Transfer
 * custody. Move and Transfer custody each also have an API-level twin, so a
 * UI failure can be told apart from a server one.
 *
 * Handoff 29. Mark missing and Condemn both passed here while the page was
 * wrong: each spec polled the API for the new `state` and never read the
 * screen, which went on saying "Cleared" in green over a missing asset and a
 * condemned one. Both now read the hero — the lifecycle label must be there
 * and the word "Cleared" must not.
 *
 * This header used to say Move and Transfer custody were BROKEN in the UI and
 * encoded as `test.fail`. They were — moveAsset()/transferCustody() mapped the
 * {asset, transfer|custody_change} envelope through apiAssetToAsset() as if it
 * were a bare asset — and that was fixed: both now read `res.data.asset`, and
 * the two UI specs below assert the dialog closes and the change persists.
 * Mark verified is the same envelope shape (`POST /assets/<id>/verify` returns
 * {asset, verification}) and is read the same way.
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
  // "Provenance" was "Legacy Data" until handoff 28: the tab printed a
  // migration source and date as literals on every asset, and now prints only
  // what the record holds — so it is no longer about legacy data.
  for (const tab of ["tab-details", "tab-custodian-assignment", "tab-audit-review", "tab-provenance"]) {
    const t = page.getByTestId(tab);
    await expect(t, `${tab} present`).toBeVisible();
    await t.click();
  }
  // Left on the last tab. An asset made through the API has a registration
  // instant and a registering user at the very least, so the panel has rows —
  // and neither of the two sentences the old tab invented.
  await expect(page.getByTestId("asset-provenance")).toContainText("Registered");
  await expect(page.getByTestId("asset-provenance")).not.toContainText("FIRS legacy system");
  await expect(page.getByTestId("asset-provenance")).not.toContainText("March 2024");
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
  // The button is `POST /assets/<id>/verify` since handoff 28, which records
  // WHO on the asset — but the EVENT is still a tracked change in the message
  // log, so that is still all its record is worth, and the row still says so.
  await expect(rows.first()).toContainText("Message log only");
  await expect(rows.first()).not.toContainText("No person recorded");
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

test("audit & review says where the location record begins, and a tapped label explains itself", async ({ page, api }) => {
  // Canned so the assertion does not depend on which assets a tenant holds.
  // (NOT because none exists: since the recorder landed, every located asset
  // that predates it is one, on every tenant.) The spec above
  // sends NO `fidelity.location` and proves the screen tolerates an older
  // server; this one sends it, with the flag that turns it into a notice.
  const id = await createAsset(api, "HistoryLocation");
  const MEANING = "Recorded when it happened, and refused to every edit afterwards.";
  const LOCATED = "This asset was already at a location when movement recording reached it.";
  await page.route(`**/api/v1/assets/${id}/history*`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        meta: { request_id: "e2e", timestamp: "2026-09-20T00:00:00Z", version: "v1" },
        data: {
          asset: { id: Number(id), asset_code: "E2E", name: "canned" },
          order: "newest_first",
          summary: { events: 1, events_after_registration: 1, by_evidence: {}, reconstructed_events: 0,
                     statement: "1 recorded event(s) since registration." },
          fidelity: {
            registered_at: "2026-08-06T09:00:00", earliest_event_after_registration_at: "2026-09-19T09:00:00",
            custody: { recording_began_at: "2026-09-09T16:12:06", links: 0, reconstructed_links: 0,
                       first_link_at: null, custodian_held_before_first_link: false,
                       statement: "No custodian has been recorded for this asset." },
            location: { recording_began_at: "2026-09-19T08:00:00", movements: 1, reconstructed_movements: 0,
                        first_movement_at: "2026-09-19T09:00:00", located_before_first_movement: true,
                        statement: LOCATED },
            evidence_grades: [
              { grade: "append_only", meaning: MEANING },
              { grade: "chatter", meaning: "A change noted in the message log and nowhere else." },
            ],
            not_recorded: [], verification: "", undated_records_omitted: 0,
          },
          events: [
            // The transfer document has since been deleted: `id` is null and
            // the reference, recorded with the move, is all that is left.
            { id: "location_moved:nrs.asset.movement:1", type: "location_moved", title: "Moved",
              summary: "HQ → Annex", at: "2026-09-19T09:00:00", at_precision: "second",
              actor: { id: 2, name: "Ada" }, actor_name: "Ada", evidence: "append_only", reconstructed: false,
              source: "test", record: { model: "nrs.asset.movement", id: 1 },
              detail: { transfer: { id: null, reference: "TRF/E2E/0001" } } },
          ],
        },
      }),
    }),
  );
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("tab-audit-review").click();

  // Already somewhere the record never saw it arrive: a notice, not muted text.
  await expect(page.getByTestId("asset-history-begins")).toContainText(LOCATED);
  await expect(page.getByTestId("asset-history-location-notice")).toContainText(LOCATED);

  const row = page.getByTestId("asset-history-event").first();
  await expect(row).toContainText("TRF/E2E/0001");
  await expect(row).toContainText("Test data");

  // The legend is on the page and collapsed; the meaning is not yet readable.
  const legend = page.getByTestId("asset-history-legend");
  await expect(page.getByTestId("toggle-history-legend")).toHaveAttribute("aria-expanded", "false");
  await expect(legend).not.toContainText(MEANING);
  // A tap on the pill — no hover involved — opens it.
  await row.getByTestId("history-evidence-pill").click();
  await expect(page.getByTestId("toggle-history-legend")).toHaveAttribute("aria-expanded", "true");
  await expect(legend).toContainText(MEANING);
  await expect(legend).toBeInViewport();
});

test("mark verified (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Verify");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-verify").click();
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.is_verified, { timeout: 15_000 })
    .toBeTruthy();
  // A verification with a date and no person is a date. The button used to
  // PATCH the date and leave this null.
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.last_verified_by?.name, "the verifier is recorded").toBeTruthy();
  await expect(page.getByText("Verified By")).toBeVisible();
  await expect(page.getByText("No person recorded")).toHaveCount(0);
});

test("mark missing via the app dialog, and the page stops saying Cleared (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Missing");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-missing").click();
  const dialog = page.getByTestId("dialog-mark-missing");
  await expect(dialog).toBeVisible();
  // The sentence the native confirm carried was false — neither Move nor
  // Verify changes `state`. What reverses it is Edit.
  await expect(dialog).toContainText("use Edit and set the state back");
  await expect(dialog).not.toContainText("move/verify");
  await page.getByTestId("button-confirm-missing").click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("missing");

  // The point of the handoff. The record says missing; so must the screen.
  const hero = page.getByTestId("asset-hero-badges");
  await expect(hero.getByTestId("lifecycle-pill")).toHaveText("Missing", { timeout: 15_000 });
  await expect(hero.getByTestId("lifecycle-pill")).toHaveAttribute("data-state", "missing");
  await expect(hero).not.toContainText("Cleared");
  // No step of the header stepper describes a missing asset, so none is lit.
  await expect(page.locator('[data-testid^="workflow-step-"][data-current="true"]')).toHaveCount(0);
  // And the Audit & Review tab agrees with the hero.
  await page.getByTestId("tab-audit-review").click();
  await expect(page.getByText("Approval Status")).toHaveCount(0);
  await expect(page.getByTestId("lifecycle-pill").last()).toHaveText("Missing");
});

test("mark missing fires no native browser dialog", async ({ page, api }) => {
  const id = await createAsset(api, "MissingNoNative");
  const fired: string[] = [];
  // Registered for the whole test, and dismissed so a regression fails on the
  // assertion below rather than hanging the page on an unanswered dialog.
  page.on("dialog", async (d) => {
    fired.push(`${d.type()}: ${d.message()}`);
    await d.dismiss();
  });
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-missing").click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeVisible();
  // Cancel writes nothing…
  await page.getByTestId("dialog-mark-missing").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeHidden();
  expect((await api.get(`/api/v1/assets/${id}`))?.state).toBe("active");
  // …and confirming does, still without the browser's own dialog.
  await page.getByTestId("button-missing").click();
  await page.getByTestId("button-confirm-missing").click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("missing");
  expect(fired, "no window.confirm / alert / prompt may fire").toEqual([]);
});

test("condemn sets state and condition, and the page stops saying Cleared (UI)", async ({ page, api }) => {
  const id = await createAsset(api, "Condemn");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-condemn").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // The description used to promise the asset would "no longer appear in
  // active workflows". It still appears in the register and in every Total.
  await expect(dialog).toContainText("It stays on the register");
  await expect(dialog).toContainText("carries no approver");
  const condemnBtn = dialog.getByRole("button", { name: "Condemn" });
  await expect(condemnBtn).toBeDisabled();
  await dialog.getByPlaceholder(/required/i).fill("E2E disposal test");
  await expect(condemnBtn).toBeEnabled();
  await condemnBtn.click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("disposed");
  // Odoo's own action of the same name writes BOTH fields; the button wrote
  // one, so a condemned asset still read "Good".
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.condition, "condemn also decommissions").toBe("decommissioned");
  expect(fresh?.disposal_reason).toBe("E2E disposal test");

  const hero = page.getByTestId("asset-hero-badges");
  await expect(hero.getByTestId("lifecycle-pill")).toHaveText("Disposed", { timeout: 15_000 });
  await expect(hero).not.toContainText("Cleared");
  await expect(hero).toContainText("Decommissioned");
  // "Disposed" was an unreachable step; a condemned asset sat on "Cleared".
  await expect(page.getByTestId("workflow-step-2")).toHaveAttribute("data-current", "true");
  await expect(page.getByTestId("workflow-step-0")).toHaveAttribute("data-current", "false");
});

test("a cancelled condemn does not reopen pre-filled", async ({ page, api }) => {
  const id = await createAsset(api, "CondemnCancel");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-condemn").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder(/required/i).fill("typed and abandoned");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await page.getByTestId("button-condemn").click();
  await expect(page.getByRole("dialog").getByPlaceholder(/required/i)).toHaveValue("");
});

test("back goes to the register list, not the KPI dashboard", async ({ page, api }) => {
  const id = await createAsset(api, "Back");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-back").click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/list"));
});

/**
 * The ORDINARY flow, in ONE page session: list → asset → act → back out.
 *
 * Every other spec here starts from a cold cache and reads a page it has just
 * loaded, and so did the harness that "proved" handoff 29's first version. The
 * app then had `refetchOnMount: false`, which makes `invalidateQueries` a no-op
 * for any query not on screen — and at the moment of an action the user is on
 * the asset's page, so the list and every count are off screen. Acted: mark an
 * asset missing, open the dashboard from the sidebar — *Missing: 8* on screen,
 * 9 in the database. And the Edit form, hydrated from a cached copy, read
 * *Active* for an asset just marked missing; saving anything wrote it back.
 */
test("after marking an asset missing, the dashboard count and the edit form both know", async ({ page, api }) => {
  const id = await createAsset(api, "FlowMissing");
  const missingOnStrip = async () => {
    const strip = page.getByTestId("asset-kpi-strip");
    await expect(strip).toContainText(/MISSING\s*[\d,]+/i, { timeout: 15_000 });
    return Number(((await strip.innerText()).replace(/\n+/g, " ").match(/MISSING\s*([\d,]+)/i) ?? [])[1]?.replace(/,/g, ""));
  };
  // 1. the dashboard first, so its counts are CACHED before anything happens
  await gotoApp(page, "/assets");
  await expectShell(page);
  const before = await missingOnStrip();
  // 2. warm the Edit form's copy too, as somebody who had edited this asset would have
  await gotoApp(page, `/assets/${id}`);
  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  await page.goBack();
  // 3. act
  await page.getByTestId("button-missing").click();
  await page.getByTestId("button-confirm-missing").click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeHidden({ timeout: 15_000 });
  // 4. the Edit form — which the dialog sends people to — must show the NEW state
  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  const stateSelect = page.locator("label", { hasText: /^\s*state/i }).first().locator("xpath=following::select[1]");
  await expect(stateSelect).toHaveValue("missing", { timeout: 10_000 });
  // 5. and the dashboard, reached WITHOUT a reload, must have counted it
  await page.locator("aside, nav").getByText("Dashboard", { exact: true }).first().click();
  await expect.poll(missingOnStrip, { timeout: 15_000 }).toBe(before + 1);
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
