import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { appPath } from "../config";

/**
 * Handoff 30 §B — disposed is terminal.
 *
 * Until then the asset page offered *Mark missing* on a disposed asset, and
 * pressing it overwrote `disposed` with `missing`: the asset was back on the
 * register, with a 200. The RULE now lives in the model (`nrs.asset.write`
 * refuses a change of status, location or custodian on a disposed asset, for
 * every writer) and is asserted in-registry. What is asserted HERE is the
 * front end's half, which is smaller and different: the app does not OFFER
 * what the server will refuse, it says WHY on the page rather than in a
 * tooltip, and when it is wrong about the record — a page gone stale — the
 * server's own sentence reaches the screen.
 *
 * `createAsset` makes an asset with NO location and NO custodian, so the
 * buttons read "Place" and "Assign custodian". They are the same two controls
 * and are found by test id, not by their words.
 */

async function createAsset(api: ApiClient, label: string, extra: Record<string, unknown> = {}) {
  const name = markedName(label);
  const created = await api.createAsset(name, extra);
  recordCreated({ kind: "asset", id: created?.id, name });
  return { id: String(created.id), name };
}

const TERMINAL_CONTROLS = ["button-missing", "button-move", "button-transfer-custody", "button-condemn"];

/**
 * ONE page session: list → asset → act → look → Edit → back to the list.
 * Report 29 §8: acting from a cold start proves only the cold start.
 */
test("a disposed asset offers no change of status, place or custodian — and says why (UI, one session)", async ({ page, api }) => {
  const { id, name } = await createAsset(api, "Terminal");

  // 1. the LIST first, so its rows are cached before anything happens
  await gotoApp(page, "/assets/list");
  await expectShell(page);
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  const row = page.getByTestId(`row-asset-${id}`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row.getByTestId("lifecycle-pill")).toHaveCount(0);

  // 2. the asset, reached by clicking its row. In service: everything is on
  //    offer and nothing explains itself.
  await row.click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath(`/assets/${id}`));
  for (const c of TERMINAL_CONTROLS) await expect(page.getByTestId(c), `${c} before disposal`).toBeEnabled();
  await expect(page.getByTestId("asset-disposed-notice")).toHaveCount(0);

  // 3. act
  await page.getByTestId("button-condemn").click();
  await page.getByTestId("input-condemn-reason").fill("E2E — terminal-state spec");
  await page.getByTestId("button-confirm-condemn").click();
  await expect(page.getByTestId("dialog-condemn")).toBeHidden({ timeout: 15_000 });
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.state, { timeout: 15_000 })
    .toBe("disposed");

  // 4. the page: all four are off, and the reason is VISIBLE TEXT — this
  //    screen is shown on a tablet, where a `title` is never seen.
  const notice = page.getByTestId("asset-disposed-notice");
  await expect(notice).toBeVisible({ timeout: 15_000 });
  await expect(notice).toContainText("has been disposed of");
  await expect(notice).toContainText("cannot be marked missing, moved");
  await expect(notice).toBeInViewport();
  for (const c of TERMINAL_CONTROLS) await expect(page.getByTestId(c), `${c} after disposal`).toBeDisabled();
  // Not everything is off. A disposed asset's other details stay correctable.
  await expect(page.getByTestId("button-edit")).toBeEnabled();
  // …and it can still be VERIFIED, by ruling (handoff 31 §C2): a disposed
  // asset somebody physically finds on the premises is an audit finding, and
  // a register that refuses to record "I saw it, today" suppresses the one
  // fact that matters. The notice says so, beside a button that is live —
  // otherwise "disposal is the end of an asset's record" reads as though the
  // button were the mistake. Acted on in its own spec, below.
  await expect(notice).toContainText("can still be marked verified");
  await expect(page.getByTestId("button-verify")).toBeEnabled();

  // 5. the Edit form offers no State but the one it holds, lets neither the
  //    location nor the custodian be changed, and says why beside each.
  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  await expect(page.getByTestId("form-disposed-notice")).toContainText("has been disposed of", { timeout: 15_000 });
  const state = page.getByTestId("select-asset-state");
  await expect(state).toBeDisabled();
  await expect(state).toHaveValue("disposed");
  await expect(state.locator("option")).toHaveCount(1);
  await expect(page.getByTestId("hint-disposed-state")).toBeVisible();
  await expect(page.getByTestId("hint-disposed-location")).toContainText("cannot be moved");
  await expect(page.getByTestId("hint-disposed-custodian")).toContainText("cannot change custodian");
  await expect(page.locator('input[placeholder="No location recorded"]')).toBeDisabled();
  await expect(page.locator('input[placeholder="No custodian recorded"]')).toBeDisabled();

  // 6. and a save from that form still WORKS — the rest of the record is not
  //    frozen — and sends none of the three.
  const sent = page.waitForRequest((r) => r.method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`));
  await page.getByRole("button", { name: "Save changes" }).click();
  const body = (await sent).postDataJSON() as Record<string, unknown>;
  for (const k of ["state", "location_id", "custodian_id"]) expect(body, `${k} is not sent for a disposed asset`).not.toHaveProperty(k);
  await page.waitForURL(new RegExp(`/assets/${id}$`));
  expect((await api.get(`/api/v1/assets/${id}`))?.state).toBe("disposed");

  // 7. BACK TO THE LIST, without a reload: the row it started from says so.
  await page.getByTestId("button-back").click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/list"));
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  await expect(page.getByTestId(`row-asset-${id}`).getByTestId("lifecycle-pill")).toHaveText("Disposed", { timeout: 15_000 });
});

/**
 * Handoff 31 §C2. The Odoo form used to hide Verify on a disposed asset while
 * this app offered it — one rule, two answers. The ruling is *allowed*, on
 * both. This is the app's half, by acting: disposed first, THEN verified, and
 * the record read back.
 */
test("a disposed asset can still be verified, and stays disposed (UI)", async ({ page, api }) => {
  const { id } = await createAsset(api, "VerifyDisposed");
  await api.post(`/api/v1/assets/${id}/condemn`, { reason: "E2E — verify-after-disposal spec" });
  const before = await api.get(`/api/v1/assets/${id}`);
  expect(before?.state).toBe("disposed");
  expect(before?.is_verified, "not verified before the button is pressed").toBeFalsy();

  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await expect(page.getByTestId("asset-disposed-notice")).toContainText("can still be marked verified", { timeout: 15_000 });
  const answered = page.waitForResponse((r) => r.url().includes(`/api/v1/assets/${id}/verify`));
  await page.getByTestId("button-verify").click();
  expect((await answered).status(), "the server allows it").toBe(200);
  await expect(page.getByTestId("asset-action-error")).toHaveCount(0);

  const after = await api.get(`/api/v1/assets/${id}`);
  expect(after?.is_verified, "the sighting is recorded").toBeTruthy();
  expect(after?.last_verified_by?.name, "and who made it").toBeTruthy();
  expect(after?.state, "and it did not bring the asset back").toBe("disposed");
  // On the page, and in the history on a record nobody can alter.
  await expect(page.getByText("Verified By")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("tab-audit-review").click();
  const newest = page.getByTestId("asset-history-event").first();
  await expect(newest).toContainText("Verified", { timeout: 15_000 });
  await expect(newest).toContainText("Cannot be altered");
});

/**
 * The page can be WRONG about the record: somebody else disposes of the asset
 * while it is open here. The buttons are still live, because this copy says
 * active. The refusal must not be swallowed — the dialog stays open on the
 * server's sentence — and the page must then catch up.
 */
test("a stale page still gets the server's refusal, in the server's words", async ({ page, api }) => {
  const { id } = await createAsset(api, "TerminalStale");
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await expect(page.getByTestId("button-missing")).toBeEnabled();
  // Behind the page's back.
  await api.post(`/api/v1/assets/${id}/condemn`, { reason: "E2E — disposed elsewhere" });

  await page.getByTestId("button-missing").click();
  await page.getByTestId("input-missing-reason").fill("E2E — pressed on a stale page");
  await page.getByTestId("button-confirm-missing").click();
  const dialog = page.getByTestId("dialog-mark-missing");
  await expect(dialog).toContainText("conflict", { timeout: 15_000 });
  await expect(dialog).toContainText("disposed");
  await expect(dialog).toBeVisible();
  expect((await api.get(`/api/v1/assets/${id}`))?.state, "the refusal wrote nothing").toBe("disposed");

  // The 409 told the app its copy was stale: closing the dialog lands on a
  // page that now knows.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("asset-disposed-notice")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("button-missing")).toBeDisabled();
});

/**
 * The API-level twin, so a UI failure above can be told from a server one —
 * and because greying a button closes one door. These are the doors.
 */
test("the server refuses every route out of disposed (API)", async ({ api }) => {
  const { id } = await createAsset(api, "TerminalApi");
  await api.post(`/api/v1/assets/${id}/condemn`, { reason: "E2E — terminal API twin" });

  const refusal = async (fn: () => Promise<unknown>) => {
    try { await fn(); } catch (e) { return String(e); }
    return "";
  };
  // PATCH of the state: 400, in the model's words.
  const patched = await refusal(() => api.patch(`/api/v1/assets/${id}`, { state: "active" }));
  expect(patched, "PATCH state=active on a disposed asset").toMatch(/HTTP 400/);
  expect(patched).toMatch(/disposed/);
  // The two dedicated routes: 409.
  expect(await refusal(() => api.post(`/api/v1/assets/${id}/mark-missing`, { reason: "e2e" }))).toMatch(/HTTP 409/);
  expect(await refusal(() => api.post(`/api/v1/assets/${id}/condemn`, { reason: "e2e again" }))).toMatch(/HTTP 409/);
  // Re-sending the SAME state is not a change, and an edit form does it.
  await api.patch(`/api/v1/assets/${id}`, { state: "disposed", notes: "E2E — paperwork after disposal" });
  expect((await api.get(`/api/v1/assets/${id}`))?.state).toBe("disposed");

  // A custodian and a location. These two sat behind a bare `if`, so on a
  // tenant with neither the spec passed having asserted neither refusal — a
  // green that ran nothing. A tenant that cannot run them now says so.
  const emp = await api.firstEmployee();
  expect(emp, "this tenant has no employee, so the transfer-custody refusal cannot be tried").toBeTruthy();
  expect(await refusal(() => api.post(`/api/v1/assets/${id}/transfer-custody`, { to_custodian_id: emp!.id })))
    .toMatch(/HTTP 400[\s\S]*disposed/);
  const loc = await api.firstLocation();
  expect(loc, "this tenant has no location, so the move refusal cannot be tried").toBeTruthy();
  expect(await refusal(() => api.post(`/api/v1/assets/${id}/move`, { to_location_id: loc!.id })))
    .toMatch(/HTTP 400[\s\S]*disposed/);
});

test("mark missing without a reason is refused by the server too (API)", async ({ api }) => {
  const { id } = await createAsset(api, "MissingNoReason");
  let refused = "";
  try { await api.post(`/api/v1/assets/${id}/mark-missing`, { reason: "   " }); } catch (e) { refused = String(e); }
  expect(refused).toMatch(/HTTP 400/);
  expect((await api.get(`/api/v1/assets/${id}`))?.state).toBe("active");
});
