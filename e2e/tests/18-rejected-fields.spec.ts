import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 30 §C — a rejected field must not fail in silence.
 *
 * The API answers 200 to a write that named a field the route does not
 * accept: it drops the field, applies the rest, and lists what it dropped in
 * `data._warnings.rejected_fields`. Nothing in the app read that block. Report
 * 29 found `asset_tag` typed, saved, answered 200 and unchanged, with no
 * message. It is read now, once, for every write (`sendMutation` in
 * `src/lib/api.ts`), and shown until somebody dismisses it.
 *
 * HOW THE WARNING IS PRODUCED HERE, said plainly because it is the weak point
 * of this file. The second spec does NOT reach a rejected field through an
 * unmodified path. The Save is real, the PATCH is real and goes to the real
 * server, and its real response comes back — and then `_warnings` is ADDED to
 * that response on the way to the page (`route.fetch()` + `fulfill`). So what
 * it proves is "the app shows what the envelope carries", not "the server
 * sends it". That half is the pytest suite's — `tests/test_asset_events_api.py`,
 * `test_the_location_hierarchy_is_refused_on_create_and_says_so` and
 * `…_on_patch_and_moves_nothing`, which read the block off a live response.
 *
 * It is done that way because the one sender this handoff knew about is the
 * one it fixed (the first spec). One other real path was found while looking
 * and is NOT used: the Depreciation Settings row sends `method`, where the
 * route's allow-list says `depreciation_method`. A spec built on it would
 * depend on a defect staying unfixed, and would rewrite a category's policy
 * and recompute its assets' book values on the test tenant to do it.
 */

async function createAsset(api: ApiClient, label: string, extra: Record<string, unknown> = {}) {
  const name = markedName(label);
  const created = await api.createAsset(name, extra);
  recordCreated({ kind: "asset", id: created?.id, name });
  return { id: String(created.id), name };
}

/**
 * The known sender. The Edit form has no input for building, floor or room,
 * and sent all three on every save — hydrated from `location_hierarchy` and
 * echoed back. They left `_WRITABLE_FIELDS` in handoff 30, so an untouched
 * save of any LOCATED asset would now raise the warning for three fields the
 * user never saw. The asset is created AT a location for that reason: one
 * created nowhere has no hierarchy to echo and would pass either way.
 */
test("an ordinary edit sends no building, floor or room — and raises no warning", async ({ page, api }) => {
  const loc = await api.firstLocation();
  test.skip(!loc, "no location on this tenant, so no hierarchy for the form to have echoed");
  const { id, name } = await createAsset(api, "NoEcho", { location_id: loc.id });

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  const nameInput = page.locator("label", { hasText: /^\s*name/i }).first().locator("xpath=following::input[1]");
  await expect(nameInput).toHaveValue(name, { timeout: 15_000 });
  await nameInput.fill(`${name} edited`);

  const sent = page.waitForRequest((r) => r.method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`));
  const answered = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`));
  await page.getByRole("button", { name: "Save changes" }).click();
  const body = (await sent).postDataJSON() as Record<string, unknown>;
  for (const k of ["building_id", "floor_id", "room_id", "asset_tag"]) {
    expect(body, `${k} must not be sent`).not.toHaveProperty(k);
  }
  // …and the SERVER agrees that nothing it was sent was refused. This is the
  // assertion that fails if the form grows another field the API does not
  // take: the request is checked against the live allow-list, not a copy.
  const envelope = await (await answered).json();
  expect(envelope?.data?._warnings ?? null, "the server rejected nothing").toBeNull();

  await page.waitForURL(new RegExp(`/assets/${id}$`));
  await expect(page.getByRole("heading", { name: `${name} edited` })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("rejected-fields-warning")).toHaveCount(0);
  // The location it was created at is still where it is.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(loc.id);
});

test("a field the server refuses is SHOWN, stays, and can be dismissed", async ({ page, api }) => {
  const { id, name } = await createAsset(api, "Rejected");
  const HINT = "Use POST /api/v1/assets/<id>/move to change where an asset is.";
  // The real request, the real response, and a `_warnings` block added to it.
  await page.route(`**/api/v1/assets/${id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    const response = await route.fetch();
    const json = await response.json();
    json.data._warnings = { rejected_fields: ["building_id", "asset_tag"], hint: HINT };
    await route.fulfill({ response, json });
  });

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  const nameInput = page.locator("label", { hasText: /^\s*name/i }).first().locator("xpath=following::input[1]");
  await expect(nameInput).toHaveValue(name, { timeout: 15_000 });
  await nameInput.fill(`${name} saved`);
  await page.getByRole("button", { name: "Save changes" }).click();

  // The form navigates away on success. The warning has to outlive it.
  await page.waitForURL(new RegExp(`/assets/${id}$`));
  const warning = page.getByTestId("rejected-fields-warning");
  await expect(warning).toBeVisible({ timeout: 15_000 });
  // WHICH fields, in words a person reads, with the key they will be asked for.
  await expect(warning).toContainText("not accepted and were not changed");
  const fields = warning.getByTestId("rejected-fields-list").locator("li");
  await expect(fields).toHaveCount(2);
  await expect(fields.nth(0)).toContainText("Building");
  await expect(fields.nth(0)).toContainText("building_id");
  await expect(fields.nth(1)).toContainText("Asset tag");
  await expect(warning.getByTestId("api-warning-hint")).toHaveText(HINT);
  // It does not claim the whole save failed — it did not.
  await expect(warning).toContainText("Everything else you entered was saved");
  expect((await api.get(`/api/v1/assets/${id}`))?.name).toBe(`${name} saved`);

  // Reachable without eyes or a mouse: a live region announces it, and it
  // sits in the labelled region F8 moves focus to.
  await expect(page.getByRole("region", { name: /Notifications/ })).toHaveCount(1);
  await expect(page.locator('[role="status"]').filter({ hasText: "not accepted" }).first()).toBeAttached();

  // Radix closes a toast after five seconds unless told otherwise. This one
  // is told otherwise: five seconds is long enough to notice a list of
  // fields, not to read it.
  await page.waitForTimeout(6_500);
  await expect(warning).toBeVisible();

  // It survives moving around the app…
  await page.getByTestId("tab-audit-review").click();
  await expect(warning).toBeVisible();
  // …and goes when it is told to, by a button with a word on it.
  await page.getByTestId("button-dismiss-api-warning").click();
  await expect(warning).toBeHidden({ timeout: 5_000 });
});

/**
 * shadcn's toast ships with a limit of ONE, so a second toast replaces the
 * first. The only toast this app raises is this warning and it stays until it
 * is dismissed — so two saves in a row would have had the second silently
 * erase the first, unread. Both saves happen in ONE page session, reached by
 * the Edit button: a full navigation would take the first warning with it and
 * prove nothing.
 */
test("a second warning does not erase the first", async ({ page, api }) => {
  const { id, name } = await createAsset(api, "RejectedTwice");
  let n = 0;
  await page.route(`**/api/v1/assets/${id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    const response = await route.fetch();
    const json = await response.json();
    n += 1;
    json.data._warnings = { rejected_fields: [n === 1 ? "first_refused_field" : "second_refused_field"] };
    await route.fulfill({ response, json });
  });
  const nameInput = () => page.locator("label", { hasText: /^\s*name/i }).first().locator("xpath=following::input[1]");
  const warnings = page.getByTestId("rejected-fields-warning");

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  await expect(nameInput()).toHaveValue(name, { timeout: 15_000 });
  await nameInput().fill(`${name} one`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`/assets/${id}$`));
  await expect(warnings).toHaveCount(1, { timeout: 15_000 });

  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  await expect(nameInput()).toHaveValue(`${name} one`, { timeout: 15_000 });
  await nameInput().fill(`${name} two`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`/assets/${id}$`));

  await expect(warnings).toHaveCount(2, { timeout: 15_000 });
  await expect(warnings.filter({ hasText: "first_refused_field" })).toBeVisible();
  await expect(warnings.filter({ hasText: "second_refused_field" })).toBeVisible();
});
