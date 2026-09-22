import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";
import { appPath } from "../config";

/**
 * Handoff 34 — a warranty, entered the way a storekeeper quotes one.
 *
 * ONE page session, the way a person goes: the register list, the asset, its
 * Edit form, Save, the asset page, back to the register, the Warranty filter,
 * and Back. Report 29 §8: acting from a cold start proves only the cold start.
 * The only full page load is the first.
 *
 * What is held here, and where each half of it comes from:
 *   - the form sends a DURATION and a start date, and never the expiry beside
 *     them — the server derives it and refuses one that disagrees;
 *   - the start is offered from the purchase date, visibly, in the field;
 *   - the server's derived expiry is the date the form showed before saving
 *     (calendar months, clamped to month end, on both sides);
 *   - the asset page prints the server's `basis`, who honours it and the
 *     reference, read back from the record rather than from what was typed;
 *   - the warranty moves NOTHING about the asset's service status;
 *   - the register's Under warranty filter finds it, and Expiring soon names
 *     its window in dates.
 */

/** Lagos today — the server's `snapshot_today`. UTC is wrong for an hour a night. */
const lagosToday = () => new Date(Date.now() + 3600_000).toISOString().slice(0, 10);
const addDays = (iso: string, n: number) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
};
/** dateutil `relativedelta(months=n)`: 31 Jan + 1 month = 28/29 Feb. */
const addMonths = (iso: string, n: number) => {
  const [y, m, d] = iso.split("-").map(Number);
  const total = y * 12 + (m - 1) + n;
  const ty = Math.floor(total / 12), tm = total - ty * 12;
  const last = new Date(Date.UTC(ty, tm + 1, 0)).getUTCDate();
  return new Date(Date.UTC(ty, tm, Math.min(d, last))).toISOString().slice(0, 10);
};

test("a warranty entered as 24 months — form, asset page, register filter (UI, one session)", async ({ page, api }) => {
  // Bought a month ago, so 24 months from then is plainly under warranty and
  // plainly NOT inside the 90-day expiring window, whatever day this runs.
  const purchase = addDays(lagosToday(), -30);
  const expectedExpiry = addMonths(purchase, 24);
  const name = markedName("Warranty");
  const created = await api.createAsset(name, { purchase_date: purchase });
  const id = String(created.id);
  recordCreated({ kind: "asset", id, name });

  const before = await api.get(`/api/v1/assets/${id}`);
  expect(before?.warranty?.status, "a new asset has no warranty recorded — the ordinary case").toBe("none");

  // 1. the LIST, then the asset by clicking its row
  await gotoApp(page, "/assets/list");
  await expectShell(page);
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  const row = page.getByTestId(`row-asset-${id}`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath(`/assets/${id}`));

  // No warranty is said plainly — and is not an alarm.
  await expect(page.getByTestId("warranty-none")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("warranty-status")).toHaveText("No warranty recorded");
  const pillsBefore = await page.getByTestId("status-pill").allTextContents();
  const lifecycleBefore = await page.getByTestId("lifecycle-pill").allTextContents();

  // 2. Edit — reached by the page's own button
  await page.getByTestId("button-edit").click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath(`/assets/${id}/edit`));
  const months = page.getByTestId("input-warranty-months");
  const start = page.getByTestId("input-warranty-start");
  // WAIT FOR THE FORM TO HOLD THE ASSET before typing. An empty start date
  // is also what the form shows before it has loaded, so waiting on that
  // alone let the first run type "24" into a form the load then overwrote.
  // The purchase date is the asset's own value, so it proves the load.
  const purchaseInput = page.locator("label", { hasText: /^\s*purchase date/i })
    .first().locator("xpath=following::input[1]");
  await expect(purchaseInput).toHaveValue(purchase, { timeout: 15_000 });
  await expect(start).toHaveValue("");
  await months.fill("24");
  // The purchase date is OFFERED as the start: in the field, and said.
  await expect(start).toHaveValue(purchase);
  await expect(page.getByTestId("hint-warranty-start-from-purchase")).toBeVisible();
  await page.getByTestId("input-warrantor").fill("E2E Dell Nigeria Ltd");
  await page.getByTestId("input-warranty-reference").fill("E2E-WC-88812");
  // The answer and its working, before anything is saved.
  await expect(page.getByTestId("warranty-computed-expiry")).toContainText("24 months from");
  // The expiry-only input is not on offer while a duration is given.
  await expect(page.getByTestId("input-warranty-expiry-only")).toHaveCount(0);
  await expect(page.getByTestId("button-warranty-expiry-only")).toHaveCount(0);

  const match = (r: { url(): string; method(): string }) =>
    r.method() === "PATCH" && new URL(r.url()).pathname.endsWith(`/api/v1/assets/${id}`);
  const sent = page.waitForRequest(match);
  const answered = page.waitForResponse((r) => match(r.request()));
  await page.getByRole("button", { name: "Save changes" }).click();
  const body = (await sent).postDataJSON() as Record<string, unknown>;
  const response = await answered;
  const envelope = await response.json().catch(() => null);
  expect(response.status(), `the save was refused: ${JSON.stringify(envelope?.error ?? null)}`).toBe(200);
  expect(body).toMatchObject({
    warranty_months: 24,
    warranty_start_date: purchase,
    warrantor: "E2E Dell Nigeria Ltd",
    warranty_reference: "E2E-WC-88812",
  });
  expect(body, "the expiry is the server's to derive, never sent beside a duration").not.toHaveProperty("warranty_expiry");
  expect(body, "the published block is read-only and never echoed").not.toHaveProperty("warranty");

  // 3. The RECORD, read back — not what was typed.
  const after = await api.get(`/api/v1/assets/${id}`);
  expect(after?.warranty).toMatchObject({
    status: "under_warranty",
    warranty_months: 24,
    warranty_start_date: purchase,
    warranty_expiry: expectedExpiry,
    warrantor: "E2E Dell Nigeria Ltd",
    warranty_reference: "E2E-WC-88812",
  });
  expect(after?.dates?.warranty_expiry, "the published date key agrees with the block").toBe(expectedExpiry);
  expect(after?.warranty?.basis, "the working is published with the answer").toBeTruthy();
  // A warranty moves nothing about the asset itself.
  expect(after?.state).toBe(before?.state);
  expect(after?.condition).toBe(before?.condition);
  expect(after?.is_verified).toBe(before?.is_verified);

  // 4. The asset page, where Save lands: the server's words.
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toBe(appPath(`/assets/${id}`));
  await expect(page.getByTestId("warranty-status")).toContainText("Under warranty", { timeout: 15_000 });
  await expect(page.getByTestId("warranty-basis")).toHaveText(after.warranty.basis);
  await expect(page.getByTestId("warranty-warrantor")).toHaveText("E2E Dell Nigeria Ltd");
  await expect(page.getByTestId("warranty-reference")).toHaveText("E2E-WC-88812");
  await expect(page.getByTestId("warranty-none")).toHaveCount(0);
  // …and the service pills say exactly what they said before.
  expect(await page.getByTestId("status-pill").allTextContents()).toEqual(pillsBefore);
  expect(await page.getByTestId("lifecycle-pill").allTextContents()).toEqual(lifecycleBefore);

  // 5. Back to the register by the page's own link, then the Warranty filter.
  await page.getByTestId("button-back").click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/assets/list"));
  await page.getByTestId("filter-warranty").click();
  await page.getByRole("button", { name: "Under warranty", exact: true }).click();
  await expect.poll(() => new URL(page.url()).search).toContain("warranty=under_warranty");
  await page.getByTestId("button-view-list").click();
  await page.getByTestId("input-asset-search").fill(name);
  await expect(page.getByTestId(`row-asset-${id}`)).toBeVisible({ timeout: 15_000 });

  // The same query the register just ran, asked of the API: the count is the rows.
  const probe = await api.probe("/api/v1/assets", { warranty_status: "under_warranty", q: name, limit: 5 });
  expect(probe.status).toBe(200);
  expect(probe.body?.pagination?.total_estimate).toBe(1);

  // Expiring soon: the window is NAMED, and an asset two years from expiry
  // is not in it.
  await page.getByTestId("filter-warranty").click();
  await page.getByRole("button", { name: /^Expiring within \d+ days$/ }).click();
  await expect(page.getByTestId("warranty-window")).toContainText("(Lagos dates)");
  await expect(page.getByTestId("warranty-window")).toContainText("between");
  await expect(page.getByText("Loading assets…")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId(`row-asset-${id}`)).toHaveCount(0);

  // 6. Back: to the asset, which still says what the record says.
  await page.goBack();
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 15_000 }).toBe(appPath(`/assets/${id}`));
  await expect(page.getByTestId("warranty-basis")).toHaveText(after.warranty.basis, { timeout: 15_000 });

  // 7. THE TILE IS ITS FILTER — proved by clicking it, in this same session.
  // The dashboard's Under-warranty number is read, the tile is pressed, and
  // the register it opens must announce that same number of rows; the API is
  // asked the same question as a third witness. A count that is not its
  // filter is this repository's most repeated defect (verification pass).
  await page.getByTestId("nav-dashboard").click();
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 15_000 }).toBe(appPath("/assets"));
  const tile = page.getByTestId("warranty-tile-under_warranty");
  await expect(tile).toBeVisible({ timeout: 15_000 });
  await expect(tile).not.toContainText("—", { timeout: 15_000 });
  const tileCount = Number(((await tile.locator("p").nth(1).textContent()) ?? "").replace(/[^\d]/g, ""));
  const counted = await api.probe("/api/v1/assets", { warranty_status: "under_warranty", limit: 1 });
  expect(counted.body?.pagination?.total_estimate, "the tile against the API").toBe(tileCount);
  await tile.click();
  await expect.poll(() => new URL(page.url()).searchParams.get("warranty")).toBe("under_warranty");
  await expect(page.getByText("Loading assets…")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("register-total")).toHaveText(tileCount.toLocaleString("en-US"), { timeout: 15_000 });
});
