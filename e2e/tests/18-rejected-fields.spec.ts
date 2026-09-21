import { test, expect } from "../fixtures/test";
import type { Page } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 31 §B — a body field the API does not accept is a 400, and the app
 * says WHICH field, in words, where the person pressed Save.
 *
 * This file was written in handoff 30 for the answer the server gave then: a
 * 200 that dropped the field, applied the rest and listed what it dropped in
 * `data._warnings.rejected_fields`, shown by the app as a toast. Two of its
 * three specs produced that block by ADDING it to a real response on the way
 * to the page — and would have stayed green for ever, asserting the sentence
 * "Everything else you entered was saved" about a server that, since handoff
 * 31, saves nothing and answers `400 invalid_request` with
 * `details.rejected_fields`. They are rewritten around the real refusal.
 *
 * HOW THE REFUSAL IS PRODUCED HERE, said plainly because it is the weak point
 * of this file. After handoff 31's sweep no screen in the app sends a key its
 * route refuses, so there is no unmodified path to a 400 — which is the point
 * of the sweep, and what the first spec holds. The refusing specs therefore
 * intercept the REQUEST and add a key the route does not accept
 * (`route.continue({ postData })`). Everything after that is real: the real
 * server reads the body, really refuses it, and its real 400 comes back to
 * the page untouched. Nothing about the response is faked.
 */

async function createAsset(api: ApiClient, label: string, extra: Record<string, unknown> = {}) {
  const name = markedName(label);
  const created = await api.createAsset(name, extra);
  recordCreated({ kind: "asset", id: created?.id, name });
  return { id: String(created.id), name };
}

const nameInputOf = (page: Page) =>
  page.locator("label", { hasText: /^\s*name/i }).first().locator("xpath=following::input[1]");

/**
 * The canary: the only assertion in the repository that holds the live Edit
 * form's body against the live allow-list rather than a copy of it.
 *
 * The known sender was this form. It has no input for building, floor or
 * room, and sent all three on every save — hydrated from `location_hierarchy`
 * and echoed back. They left `_WRITABLE_FIELDS` in handoff 30. Under handoff
 * 31 an untouched save of any LOCATED asset would be refused outright for
 * three fields the user never saw. The asset is created AT a location for
 * that reason: one created nowhere has no hierarchy to echo and would pass
 * either way.
 */
test("an ordinary edit sends nothing the server refuses — and is answered 200", async ({ page, api }) => {
  const loc = await api.firstLocation();
  test.skip(!loc, "no location on this tenant, so no hierarchy for the form to have echoed");
  const { id, name } = await createAsset(api, "NoEcho", { location_id: loc.id });

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  await expect(nameInputOf(page)).toHaveValue(name, { timeout: 15_000 });
  await nameInputOf(page).fill(`${name} edited`);

  const sent = page.waitForRequest((r) => r.method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`));
  const answered = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`));
  await page.getByRole("button", { name: "Save changes" }).click();
  const body = (await sent).postDataJSON() as Record<string, unknown>;
  for (const k of ["building_id", "floor_id", "room_id", "asset_tag"]) {
    expect(body, `${k} must not be sent`).not.toHaveProperty(k);
  }
  // …and the SERVER agrees, which is the assertion that fails if the form
  // grows another field the API does not take: the body is judged by the live
  // allow-list. A refused key is a 400 naming it, so the status is the test.
  const response = await answered;
  const envelope = await response.json();
  expect(
    response.status(),
    `the server refused ${JSON.stringify(envelope?.error?.details?.rejected_fields ?? envelope?.error)}`,
  ).toBe(200);
  expect(envelope?.error ?? null, "a 200 carries no error").toBeNull();

  await page.waitForURL(new RegExp(`/assets/${id}$`));
  await expect(page.getByRole("heading", { name: `${name} edited` })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("refused-fields")).toHaveCount(0);
  await expect(page.getByTestId("api-warning")).toHaveCount(0);
  // The location it was created at is still where it is.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(loc.id);
});

test("a refused save names the fields in words, saves NOTHING, keeps what was typed — and then saves", async ({ page, api }) => {
  const { id, name } = await createAsset(api, "Refused");
  let tamper = true;
  let refusedStatus = 0;
  await page.route(`**/api/v1/assets/${id}`, async (route) => {
    const req = route.request();
    if (req.method() !== "PATCH" || !tamper) return route.fallback();
    // Two keys the route does not accept, added to the form's own body. The
    // request then goes to the real server, which answers for itself.
    const body = { ...(req.postDataJSON() as Record<string, unknown>), building_id: 1, asset_tag: "E2E-NOT-MINE" };
    await route.continue({ postData: JSON.stringify(body) });
  });
  page.on("response", (r) => {
    if (r.request().method() === "PATCH" && r.url().includes(`/api/v1/assets/${id}`) && tamper) refusedStatus = r.status();
  });

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  await expect(nameInputOf(page)).toHaveValue(name, { timeout: 15_000 });
  await nameInputOf(page).fill(`${name} typed`);
  await page.getByRole("button", { name: "Save changes" }).click();

  // WHICH fields, in words a person reads, with the key they will be asked for.
  const panel = page.getByTestId("refused-fields");
  await expect(panel).toBeVisible({ timeout: 15_000 });
  expect(refusedStatus, "the real server refused the body").toBe(400);
  await expect(panel).toContainText("These fields were not accepted, so nothing was saved");
  const fields = panel.getByTestId("refused-fields-list").locator("li");
  await expect(fields).toHaveCount(2);
  await expect(panel.locator('li[data-field="building_id"]')).toContainText("Building");
  await expect(panel.locator('li[data-field="building_id"]')).toContainText("building_id");
  await expect(panel.locator('li[data-field="asset_tag"]')).toContainText("Asset tag");
  // Not the server's sentence, which is written for an integrator.
  await expect(panel).not.toContainText("This route does not accept");
  // Said ONCE: in the panel beside the button, not in a toast as well.
  await expect(page.getByTestId("api-warning")).toHaveCount(0);

  // NOTHING was saved — including the name, which the route does accept.
  expect((await api.get(`/api/v1/assets/${id}`))?.name, "the good field in the same body was not written").toBe(name);
  // The form did not navigate, and kept what the person typed.
  expect(new URL(page.url()).pathname).toMatch(new RegExp(`/assets/${id}/edit$`));
  await expect(nameInputOf(page)).toHaveValue(`${name} typed`);

  // And it recovers in the same session: the same form, the same text, a body
  // the server accepts — saved, and the refusal gone with it.
  tamper = false;
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`/assets/${id}$`));
  await expect(page.getByRole("heading", { name: `${name} typed` })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("refused-fields")).toHaveCount(0);
  expect((await api.get(`/api/v1/assets/${id}`))?.name).toBe(`${name} typed`);
});

/**
 * `details.hint` is advice about ONE field and the server sends it for one:
 * `stage_id` on a request, which belongs to the transition route. Reached the
 * same way — the key is added to the Edit form's real PATCH.
 */
test("the server's hint about a refused field is shown with it", async ({ page, api }) => {
  const r = await api.firstRequest();
  test.skip(!r, "no request on this tenant to edit");
  const before = await api.get(`/api/v1/requests/${r.id}`);

  await page.route(`**/api/v1/requests/${r.id}`, async (route) => {
    const req = route.request();
    if (req.method() !== "PATCH") return route.fallback();
    const body = { ...(req.postDataJSON() as Record<string, unknown>), stage_id: 1 };
    await route.continue({ postData: JSON.stringify(body) });
  });

  await gotoApp(page, `/service-desk/${r.id}/edit`);
  await expectShell(page);
  const save = page.getByRole("button", { name: "Save changes" });
  await expect(save).toBeEnabled({ timeout: 15_000 });
  // Wait for the form to be hydrated from the request before saving it.
  await expect(page.getByPlaceholder(/describe the issue/i)).not.toHaveValue("", { timeout: 15_000 });
  const answered = page.waitForResponse((x) => x.request().method() === "PATCH" && x.url().includes(`/api/v1/requests/${r.id}`));
  await save.click();
  expect((await answered).status(), "the real server refused `stage_id`").toBe(400);

  const panel = page.getByTestId("refused-fields");
  await expect(panel).toBeVisible({ timeout: 15_000 });
  await expect(panel).toContainText("This field was not accepted, so nothing was saved");
  await expect(panel.locator('li[data-field="stage_id"]')).toContainText("Stage");
  await expect(panel.getByTestId("refused-fields-hint")).toContainText("/transition");
  // Nothing was written.
  const after = await api.get(`/api/v1/requests/${r.id}`);
  expect(after?.stage?.id, "the stage did not move").toBe(before?.stage?.id);
  expect(after?.updated_at, "the request was not written at all").toBe(before?.updated_at);
});

/**
 * What is LEFT of the handoff-30 toast, and the one spec here that does fake
 * a response — said plainly. `lib/apiWarnings.tsx` still shows any `_warnings`
 * block that rides on a successful write, but no write this app makes can
 * draw one from the server any more: `rejected_fields` is a 400, `truncated`
 * rides on lists, `discarded_fields` on a callback the app never calls. So a
 * block is ADDED to a real 200 (`route.fetch()` + `fulfill`), under a name no
 * build has heard of — which is the case the code is kept for. What this
 * proves is "the app shows what the envelope carries, and a second notice
 * does not erase the first" (shadcn's toast ships with a limit of ONE). It
 * does not prove the server sends anything.
 */
test("a `_warnings` block on a SUCCESSFUL write is still shown, and a second does not erase the first", async ({ page, api }) => {
  const { id, name } = await createAsset(api, "Warned");
  let n = 0;
  await page.route(`**/api/v1/assets/${id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    const response = await route.fetch();
    const json = await response.json();
    n += 1;
    json.data._warnings = { a_block_this_build_has_not_heard_of: n === 1 ? "first note" : "second note" };
    await route.fulfill({ response, json });
  });
  const warnings = page.getByTestId("api-warning");

  await gotoApp(page, `/assets/${id}/edit`);
  await expectShell(page);
  await expect(nameInputOf(page)).toHaveValue(name, { timeout: 15_000 });
  await nameInputOf(page).fill(`${name} one`);
  await page.getByRole("button", { name: "Save changes" }).click();
  // The form navigates away on success. The notice has to outlive it.
  await page.waitForURL(new RegExp(`/assets/${id}$`));
  await expect(warnings).toHaveCount(1, { timeout: 15_000 });
  await expect(warnings.first()).toContainText("first note");
  // It does not claim a field was refused: that is not what happened.
  await expect(page.getByTestId("refused-fields")).toHaveCount(0);

  // Both saves in ONE page session, reached by the Edit button: a full
  // navigation would take the first notice with it and prove nothing.
  await page.getByTestId("button-edit").click();
  await page.waitForURL(/\/edit$/);
  await expect(nameInputOf(page)).toHaveValue(`${name} one`, { timeout: 15_000 });
  await nameInputOf(page).fill(`${name} two`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.waitForURL(new RegExp(`/assets/${id}$`));

  await expect(warnings).toHaveCount(2, { timeout: 15_000 });
  await expect(warnings.filter({ hasText: "first note" })).toBeVisible();
  await expect(warnings.filter({ hasText: "second note" })).toBeVisible();
  // Radix closes a toast after five seconds unless told otherwise; these are
  // told otherwise, and go when a button with a word on it is pressed.
  await page.waitForTimeout(6_500);
  await expect(warnings).toHaveCount(2);
  await page.getByTestId("button-dismiss-api-warning").first().click();
  await expect(warnings).toHaveCount(1, { timeout: 5_000 });
});
