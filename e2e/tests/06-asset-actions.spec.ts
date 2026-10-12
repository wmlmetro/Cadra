import { test, expect } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { appPath } from "../config";
import { receive } from "../fixtures/gates";

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
 * Handoff 30. Mark missing REQUIRES a reason and is `POST /mark-missing`;
 * Condemn is `POST /condemn` and sends no date. Both specs assert the REQUEST
 * as well as the record: a PATCH that happened to leave the same row behind
 * would otherwise pass, and the date coming off the browser's clock is
 * exactly the kind of thing the row cannot show. What may be done to a
 * disposed asset, and what the app does with a field the server refuses, are
 * in `17-disposed-is-terminal.spec.ts` and `18-rejected-fields.spec.ts`.
 *
 * Handoff 31. *Mark found* is Mark missing's other half — `POST /mark-found`,
 * a required "where did it turn up?", offered on a missing asset and on no
 * other. Its specs follow the ones for Mark missing.
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

const MISSING_REASON = "E2E — not found at its desk during the count";

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
  // The unit AS RECEIVED, not walked onto the register (handoff 58 §2, the
  // pytest twin's `registered=False`): this asserts the WHOLE history, and a
  // unit walked through the receipt gates has seven gate events, a label's
  // affix and the maker's SAP code in it — which is what a gated unit's
  // history is. Switch off, this is exactly the asset it always was; switch
  // on, it is a candidate, read by id (which reaches one).
  const name = markedName("HistoryEmpty");
  const received = await receive(api, { name, category_id: await api.firstCategoryId() });
  recordCreated({ kind: "asset", id: received?.id, name });
  const id = String(received.id);
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
  // Since handoff 30 a verification made with the button has a record of its
  // own that nobody can alter (`nrs.asset.event`), and the row says so. Until
  // then the EVENT was a tracked change in the message log and this asserted
  // "Message log only" — which is still what a verification made BEFORE
  // recording began is worth, and `fidelity.events` says where that line is.
  await expect(rows.first()).toContainText("Cannot be altered");
  await expect(rows.first()).not.toContainText("Message log only");
  await expect(page.getByTestId("asset-history-event-recording")).toContainText("Verify button");
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
  // Verify changes `state`. What reverses it is Mark found (it said "use Edit
  // and set the state back" until handoff 31, which worked and recorded
  // nothing) — and the dialog says the other half: a disposal cannot be
  // reversed, and the reason is kept.
  await expect(dialog).toContainText("use Mark found on this page");
  await expect(dialog).not.toContainText("set the state back");
  await expect(dialog).toContainText("cannot be edited or deleted");
  await expect(dialog).not.toContainText("move/verify");
  // No reason, no button. A blank one is no reason either.
  const confirm = page.getByTestId("button-confirm-missing");
  await expect(confirm).toBeDisabled();
  await page.getByTestId("input-missing-reason").fill("   ");
  await expect(confirm).toBeDisabled();
  await page.getByTestId("input-missing-reason").fill(MISSING_REASON);
  await expect(confirm).toBeEnabled();
  const sent = page.waitForRequest((r) => r.method() !== "GET" && r.url().includes(`/api/v1/assets/${id}`));
  await confirm.click();
  const req = await sent;
  // The ROUTE, not a PATCH of `state` — a PATCH has nowhere to put a reason.
  expect(req.method()).toBe("POST");
  expect(new URL(req.url()).pathname).toBe(`/api/v1/assets/${id}/mark-missing`);
  expect(req.postDataJSON()).toEqual({ reason: MISSING_REASON });
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
  // The reason is EVIDENCE: on the newest row of the history, on a record
  // nobody can alter, with the person who gave it.
  const newest = page.getByTestId("asset-history-event").first();
  await expect(newest).toContainText(MISSING_REASON, { timeout: 15_000 });
  await expect(newest).toContainText("Cannot be altered");
  await expect(newest).not.toContainText("No person recorded");
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
  await page.getByTestId("input-missing-reason").fill("typed and abandoned");
  // Cancel writes nothing…
  await page.getByTestId("dialog-mark-missing").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeHidden();
  expect((await api.get(`/api/v1/assets/${id}`))?.state).toBe("active");
  // …and confirming does, still without the browser's own dialog.
  await page.getByTestId("button-missing").click();
  // A cancelled dialog does not reopen with the reason still in it.
  await expect(page.getByTestId("input-missing-reason")).toHaveValue("");
  await page.getByTestId("input-missing-reason").fill(MISSING_REASON);
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
  await expect(dialog).toContainText("cannot be undone");
  await dialog.getByPlaceholder(/required/i).fill("E2E disposal test");
  await expect(condemnBtn).toBeEnabled();
  const sent = page.waitForRequest((r) => r.method() !== "GET" && r.url().includes(`/api/v1/assets/${id}`));
  await condemnBtn.click();
  const req = await sent;
  // `POST /condemn`, carrying the reason and NOTHING else. It was a PATCH of
  // four fields, one of them `disposal_date` off this browser's clock — wrong
  // for the first hour of every Lagos day, with a correct clock. The server
  // dates it now, and a client that still sent a date would be sending one
  // the route does not read.
  expect(req.method()).toBe("POST");
  expect(new URL(req.url()).pathname).toBe(`/api/v1/assets/${id}/condemn`);
  expect(req.postDataJSON()).toEqual({ reason: "E2E disposal test" });
  expect(JSON.stringify(req.postDataJSON())).not.toMatch(/date|state|condition/);
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("disposed");
  // Odoo's own action of the same name writes BOTH fields; the button wrote
  // one, so a condemned asset still read "Good".
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.condition, "condemn also decommissions").toBe("decommissioned");
  expect(fresh?.disposal_reason).toBe("E2E disposal test");
  // Sent no date, and has one: the server's.
  expect(fresh?.dates?.disposal_date, "the SERVER dated the disposal").toMatch(/^\d{4}-\d{2}-\d{2}$/);

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
  await page.getByTestId("input-missing-reason").fill(MISSING_REASON);
  await page.getByTestId("button-confirm-missing").click();
  await expect(page.getByTestId("dialog-mark-missing")).toBeHidden({ timeout: 15_000 });
  // 4. the Edit form must show the NEW state. (The dialog sent people here to
  //    reverse it until handoff 31; it sends them to Mark found now, and the
  //    form's copy going stale is the same defect either way.)
  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  const stateSelect = page.locator("label", { hasText: /^\s*state/i }).first().locator("xpath=following::select[1]");
  await expect(stateSelect).toHaveValue("missing", { timeout: 10_000 });
  // 5. and the dashboard, reached WITHOUT a reload, must have counted it
  await page.locator("aside, nav").getByText("Dashboard", { exact: true }).first().click();
  await expect.poll(missingOnStrip, { timeout: 15_000 }).toBe(before + 1);
});

const FOUND_REASON = "E2E — turned up in the 2nd-floor store room, tag intact";

/** Missing by the ROUTE, so the asset has a real "why it went" event for the
 *  "where it turned up" one to sit beside. */
async function createMissingAsset(api: ApiClient, label: string) {
  const name = markedName(label);
  const created = await api.createAsset(name);
  recordCreated({ kind: "asset", id: created?.id, name });
  const id = String(created.id);
  await api.post(`/api/v1/assets/${id}/mark-missing`, { reason: MISSING_REASON });
  return { id, name };
}

test("mark found is offered on a missing asset and on no other", async ({ page, api }) => {
  const live = await createAsset(api, "FoundNotOffered");
  await gotoApp(page, `/assets/${live}`);
  await expectShell(page);
  await expect(page.getByTestId("button-missing")).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByTestId("button-found")).toHaveCount(0);

  // …nor on a disposed one, where the server would answer 409. A SECOND
  // asset, disposed of before this browser has ever seen it — not the first
  // one condemned behind the page's back and reloaded. That was this spec's
  // first draft, and in the full-suite run it failed once and passed on the
  // retry, which is what a race looks like: the asset query is fresh for
  // a minute and its cache is persisted, so a reload inside that minute
  // restores the copy that says "active" and does not ask again.
  const gone = await createAsset(api, "FoundNotOfferedDisposed");
  await api.post(`/api/v1/assets/${gone}/condemn`, { reason: "E2E — mark-found is not offered here" });
  await gotoApp(page, `/assets/${gone}`);
  await expect(page.getByTestId("asset-disposed-notice")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("button-found")).toHaveCount(0);
});

/**
 * ONE page session: list → asset → act → look → back to the list. Report 29
 * §8: acting from a cold start proves only the cold start — and the bug this
 * flow is most likely to catch is last handoff's, a dialog that stays open
 * after the save it was opened for has succeeded.
 */
test("mark found via the app dialog: list → asset → act → back (UI, one session)", async ({ page, api }) => {
  const { id, name } = await createMissingAsset(api, "Found");

  // 1. the LIST first, so the row saying Missing is cached before anything happens
  await gotoApp(page, "/assets/list");
  await expectShell(page);
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  const row = page.getByTestId(`row-asset-${id}`);
  await expect(row.getByTestId("lifecycle-pill")).toHaveText("Missing", { timeout: 15_000 });

  // 2. the asset, by clicking its row. Mark missing is off; Mark found is on offer.
  await row.click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath(`/assets/${id}`));
  await expect(page.getByTestId("button-missing")).toBeDisabled();
  await page.getByTestId("button-found").click();
  const dialog = page.getByTestId("dialog-mark-found");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Where did it turn up?");
  await expect(dialog).toContainText("cannot be edited or deleted");
  // It does not verify, and says so — whoever found it may not be who checks it.
  await expect(dialog).toContainText("does not verify");

  // 3. no reason, no button. A blank one is no reason either.
  const confirm = page.getByTestId("button-confirm-found");
  await expect(confirm).toBeDisabled();
  await page.getByTestId("input-found-reason").fill("   ");
  await expect(confirm).toBeDisabled();
  await page.getByTestId("input-found-reason").fill(FOUND_REASON);
  await expect(confirm).toBeEnabled();
  const sent = page.waitForRequest((r) => r.method() !== "GET" && r.url().includes(`/api/v1/assets/${id}`));
  await confirm.click();
  const req = await sent;
  // The ROUTE, not a PATCH of `state` — a PATCH has nowhere to put a sentence.
  expect(req.method()).toBe("POST");
  expect(new URL(req.url()).pathname).toBe(`/api/v1/assets/${id}/mark-found`);
  expect(req.postDataJSON()).toEqual({ reason: FOUND_REASON });
  // Success CLOSES it.
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  const fresh = await api.get(`/api/v1/assets/${id}`);
  expect(fresh?.state).toBe("active");
  expect(fresh?.is_verified, "found is not verified").toBeFalsy();

  // 4. the page: no lifecycle pill, Mark missing back on offer, Mark found gone.
  const hero = page.getByTestId("asset-hero-badges");
  await expect(hero.getByTestId("lifecycle-pill")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("button-found")).toHaveCount(0);
  await expect(page.getByTestId("button-missing")).toBeEnabled();
  // Both sentences are in the history, newest first, on a record nobody can alter.
  await page.getByTestId("tab-audit-review").click();
  const rows = page.getByTestId("asset-history-event");
  await expect(rows.nth(0)).toContainText(FOUND_REASON, { timeout: 15_000 });
  await expect(rows.nth(0)).toContainText("Cannot be altered");
  await expect(rows.nth(0)).not.toContainText("No person recorded");
  await expect(rows.nth(1)).toContainText(MISSING_REASON);

  // 5. BACK TO THE LIST, without a reload: the row it started from is Active again.
  await page.getByTestId("button-back").click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/list"));
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  await expect(page.getByTestId(`row-asset-${id}`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId(`row-asset-${id}`).getByTestId("lifecycle-pill")).toHaveCount(0, { timeout: 15_000 });
});

/**
 * The page can be WRONG about the record: somebody else finds the asset while
 * it is open here as missing. The button is still live. The 409 must stay in
 * the dialog, in the server's words, and the page must then catch up.
 */
test("a stale Mark found gets the server's 409 in the dialog, and the page catches up", async ({ page, api }) => {
  const { id } = await createMissingAsset(api, "FoundStale");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await expect(page.getByTestId("button-found")).toBeVisible({ timeout: 15_000 });
  // Somebody else gets there first.
  await api.post(`/api/v1/assets/${id}/mark-found`, { reason: "E2E — found by somebody else first" });

  await page.getByTestId("button-found").click();
  await page.getByTestId("input-found-reason").fill(FOUND_REASON);
  const answered = page.waitForResponse((r) => r.url().includes(`/api/v1/assets/${id}/mark-found`));
  await page.getByTestId("button-confirm-found").click();
  expect((await answered).status()).toBe(409);
  const dialog = page.getByTestId("dialog-mark-found");
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId("mark-found-error")).toContainText("This asset is not missing");
  // What was typed is still there; nothing was thrown away with the refusal.
  await expect(page.getByTestId("input-found-reason")).toHaveValue(FOUND_REASON);
  // Closing it lands on the truth: the page was refetched, the offer is gone.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("button-found")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("button-missing")).toBeEnabled();
});

/**
 * An asset with NO location — which is what `createAsset` here makes, and what
 * 358 assets on `nrs19` and 1,920 on `jaizbankplc` are. The Move button used
 * to fail on them outright: *"validation_failed: Required field missing:
 * from_location_id"*, because the route always built a transfer document and a
 * transfer needs both ends. Reported by the owner, from the screen. It is
 * PLACED now, and the dialog says so rather than promising a transfer.
 */
test("an asset with no location can be placed, and the dialog promises no transfer (UI)", async ({ page, api }) => {
  const locs = await api.locations(1);
  test.skip(!locs.length, "no location on this tenant to place it at");
  const id = await createAsset(api, "Place");
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location ?? null).toBeNull();
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await expect(page.getByTestId("button-move")).toHaveText(/Place/);
  await page.getByTestId("button-move").click();
  const dialog = page.getByRole("dialog");
  const needsApprovalHere = await api.approvalRequired();
  if (needsApprovalHere) {
    // On an approval tenant the dialog is about a REQUEST, and the wording
    // has to say so before anything else — that is handoff 35 §E's whole
    // point. The promise about the transfer document belongs to the act,
    // which has not happened yet, so it is not made here.
    await expect(dialog).toContainText("Request a placement");
    await expect(dialog).toContainText(/does NOT place the asset/i);
  } else {
    await expect(dialog).toContainText("Place asset");
    await expect(dialog).toContainText("No transfer document is created");
  }
  const q = String(locs[0].name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 6);
  const picked = await pickRecord(dialog, "Search locations", q.length >= 2 ? q : "of");
  test.skip(!picked, "location search returned no options");

  // A PLACEMENT is a move for this purpose — a person deciding, today, where
  // a thing goes — so it goes through approval too. Approving it here rather
  // than stopping at the request, because the second half of this test is
  // about what the history says once the asset IS placed.
  if (needsApprovalHere) {
    const approver = await api.anApprover();
    test.skip(!approver, "no eligible approver other than the caller");
    const pickedApprover = await pickRecord(dialog, "Search people who can approve", String(approver!.name).split(/\s+/)[0].slice(0, 5));
    test.skip(!pickedApprover, "approver search returned no options");
    await dialog.getByTestId("button-confirm-move").click();
    await expect(dialog.getByTestId("approval-raised")).toBeVisible({ timeout: 15_000 });
    const second = await ApiClient.forServiceCredential();
    test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET to approve — "
                     + "the model refuses self-approval, so one identity cannot");
    const pending = await api.get<any[]>("/api/v1/approvals", { asset_id: Number(id), state: "pending" });
    await second!.post(`/api/v1/approvals/${pending[0].id}/approve`, {});
    await page.reload();
    await expectShell(page);
  } else {
    await dialog.getByRole("button", { name: "Place asset" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  }
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_location?.id ?? null, { timeout: 15_000 })
    .not.toBeNull();
  // Placed, so from now on it is MOVED — and the history has the placement.
  //
  // The button's LABEL is only asserted on the path where the app itself did
  // the placing. On the approval path above, the approval is made by a
  // second credential OUT OF BAND — a thing no real user flow does — so this
  // browser never learns of it and paints its own persisted copy of the
  // asset for the rest of the five-minute `staleTime`. That is by design
  // (`buster` in `App.tsx` exists precisely to manage it) and asserting
  // against it here would be asserting that an out-of-band write is
  // telepathic. **The label after an approval made THROUGH the app is
  // covered**, in one session, by `35-approvals.spec.ts` — *list → asset →
  // request → queue → approve → back*.
  if (!needsApprovalHere) {
    await expect(page.getByTestId("button-move")).toHaveText(/Move/);
  }
  await page.getByTestId("tab-audit-review").click();
  await expect(page.getByTestId("asset-history-event").first()).toContainText("Placed at");
});

// ── Move ─────────────────────────────────────────────────────────────────────

/**
 * BREAKING since handoff 35, and this spec is where it shows first.
 *
 * On a tenant that requires approval — which is EVERY tenant that has not
 * been configured, because the switch is absent-means-on — `POST /move` no
 * longer moves anything. It raises a request and answers `pending_approval:
 * true` with the asset UNCHANGED.
 *
 * So this asserts both halves against whatever the tenant actually says,
 * asked of the server rather than assumed: the request is raised and the
 * asset has NOT moved, and then — only when a second credential exists,
 * because the model refuses self-approval — it is approved and the asset
 * HAS moved. On a tenant with approval off the old behaviour is asserted
 * unchanged.
 */
test("move persists server-side (API)", async ({ api }) => {
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const id = await createAsset(api, "MoveApi", { location_id: locs[0].id });
  const needsApproval = await api.approvalRequired();

  if (!needsApproval) {
    await api.post(`/api/v1/assets/${id}/move`, { to_location_id: locs[1].id, reason: "e2e" });
    expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[1].id);
    return;
  }

  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller on this tenant");
  const raised = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id, reason: "e2e",
  });
  expect(raised?.pending_approval, "a move should now raise a request").toBe(true);
  expect(raised?.movement_id, "nothing is recorded until it is approved").toBeNull();
  // THE POINT OF THE WHOLE HANDOFF: the asset has not moved. Read back from
  // the server rather than trusting the echo in the response.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[0].id);

  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET to prove the approve half — "
                   + "the model refuses self-approval, so one identity cannot");
  // The SERVICE credential raised it above? No — `api` did. So the second
  // credential is the approver here, and it must be eligible.
  await second!.post(`/api/v1/approvals/${raised.request.id}/approve`, {});
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[1].id);
});

/**
 * The UI half. On an approval tenant the button says what it does and the
 * dialog does NOT close on success — it is replaced by a panel naming the
 * reference, because "a storekeeper who thinks they have moved something and
 * has not is the defect this programme is named after" (handoff 35 §E).
 */
test("move via UI closes the dialog and persists", async ({ page, api }) => {
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const id = await createAsset(api, "MoveUI", { location_id: locs[0].id });
  const needsApproval = await api.approvalRequired();
  const approver = needsApproval ? await api.anApprover() : null;
  test.skip(needsApproval && !approver, "no eligible approver other than the caller");

  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await page.getByTestId("button-move").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const q = String(locs[1].name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 6);
  const picked = await pickRecord(dialog, "Search locations", q.length >= 2 ? q : "of");
  test.skip(!picked, "location search returned no options");
  await dialog.getByPlaceholder(/floor reorganisation|reason/i).fill("E2E move");

  if (!needsApproval) {
    await dialog.getByRole("button", { name: "Move asset" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    await expect
      .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_location?.id, { timeout: 15_000 })
      .toBe(locs[1].id);
    return;
  }

  // The dialog must SAY the asset does not move. Asserted on the words a
  // person reads, not on a test id, because the wording is the control.
  await expect(dialog).toContainText(/does not move|does NOT move/i);
  const pickedApprover = await pickRecord(dialog, "Search people who can approve", String(approver!.name).split(/\s+/)[0].slice(0, 5));
  test.skip(!pickedApprover, "approver search returned no options");
  await dialog.getByTestId("button-confirm-move").click();
  // It does NOT close. It shows the reference.
  await expect(dialog.getByTestId("approval-raised")).toBeVisible({ timeout: 15_000 });
  await expect(dialog.getByTestId("approval-raised-reference")).toContainText(/CR\//);
  // And the asset has not moved. The real row, read from the server.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[0].id);
});

// ── Transfer custody ──────────────────────────────────────────────────────────

test("transfer custody persists server-side (API)", async ({ api }) => {
  const emp = await api.firstEmployee();
  test.skip(!emp, "no employees");
  const id = await createAsset(api, "CustodyApi");
  const needsApproval = await api.approvalRequired();

  if (!needsApproval) {
    await api.post(`/api/v1/assets/${id}/transfer-custody`, { to_custodian_id: emp.id, reason: "e2e" });
    expect((await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id).toBe(emp.id);
    return;
  }

  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller on this tenant");
  const raised = await api.post(`/api/v1/assets/${id}/transfer-custody`, {
    to_custodian_id: emp.id, approver_id: approver!.id, reason: "e2e",
  });
  expect(raised?.pending_approval).toBe(true);
  expect(raised?.custody_change, "no custody link until it is approved").toBeNull();
  expect((await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id ?? null).toBeNull();

  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET to prove the approve half");
  await second!.post(`/api/v1/approvals/${raised.request.id}/approve`, {});
  expect((await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id).toBe(emp.id);
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
  const needsApproval = await api.approvalRequired();
  if (!needsApproval) {
    await dialog.getByRole("button", { name: "Transfer custody" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    await expect
      .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id, { timeout: 15_000 })
      .toBe(emp.id);
    return;
  }
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");
  await expect(dialog).toContainText(/does not move|does NOT move|until.*approve/i);
  const pickedApprover = await pickRecord(dialog, "Search people who can approve", String(approver!.name).split(/\s+/)[0].slice(0, 5));
  test.skip(!pickedApprover, "approver search returned no options");
  await dialog.getByTestId("button-confirm-transfer-custody").click();
  await expect(dialog.getByTestId("approval-raised")).toBeVisible({ timeout: 15_000 });
  // Custody has NOT changed.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_custodian?.id ?? null).toBeNull();
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

  // API: same-location move is rejected — and still BEFORE any request is
  // raised. Handoff 35 put the approval branch below every validation on the
  // route, for the reason handoff 28 learned the hard way: an `err(...)`
  // return does not roll the transaction back, so anything that can refuse
  // must refuse before anything is written. A same-location move that left a
  // pending request behind would be that bug wearing a new hat.
  let rejected = false;
  try {
    const approver = await api.anApprover();
    await api.post(`/api/v1/assets/${id}/move`, {
      to_location_id: loc.id, reason: "same-loc",
      ...(approver ? { approver_id: approver.id } : {}),
    });
  } catch (e) {
    rejected = /same|conflict|unprocess|validation|invalid|422/i.test(String(e));
  }
  expect(rejected, "moving to the current location should be rejected").toBeTruthy();
});
