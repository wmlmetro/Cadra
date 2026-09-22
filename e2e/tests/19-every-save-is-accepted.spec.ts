import { test, expect } from "../fixtures/test";
import type { Page } from "../fixtures/test";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 31 §B, the sweep — proved by acting.
 *
 * A body field a route does not accept used to be a 200 that dropped it.
 * It is a 400 now and NOTHING is saved, so one stray key in a form's body
 * turns a working Save into a failure. Every Save in the app that reaches one
 * of the refusing routes is pressed here, through the real UI, with as many
 * of its inputs filled as this tenant has valid values for — a key is only
 * sent when its input is set, so an empty form proves nothing about the keys
 * it left out. Each spec asserts the STATUS the real server gave the real
 * body, names any `rejected_fields` in the failure message, and lists the
 * keys that were actually sent, so a reader of the run can see what was and
 * was not exercised.
 *
 * What this cannot reach, said plainly: the asset form's Subcategory id,
 * Asset type id and Maintenance vendor id are raw foreign-key inputs and this
 * suite has no way to discover a valid id for them, so those three keys are
 * held against the allow-list by reading it, not by sending them.
 */

function field(page: Page, label: RegExp, tag: "input" | "select" | "textarea" = "input") {
  return page.locator("label", { hasText: label }).first().locator(`xpath=following::${tag}[1]`);
}

/** Press `click`, and return the write it caused: its body's keys and the
 *  server's answer. Fails, naming the refused fields, unless it was a 2xx. */
async function savedBy(page: Page, method: "POST" | "PATCH", path: RegExp, click: () => Promise<void>) {
  const match = (url: string, m: string) => m === method && path.test(new URL(url).pathname);
  const sent = page.waitForRequest((r) => match(r.url(), r.method()));
  const answered = page.waitForResponse((r) => match(r.url(), r.request().method()), { timeout: 120_000 });
  await click();
  const body = ((await sent).postDataJSON() ?? {}) as Record<string, unknown>;
  const response = await answered;
  const envelope = await response.json().catch(() => null);
  expect(
    response.status(),
    `${method} ${path} was refused: ${JSON.stringify(envelope?.error?.details?.rejected_fields ?? envelope?.error ?? null)}` +
      ` — body keys sent: ${Object.keys(body).join(", ")}`,
  ).toBeLessThan(300);
  await expect(page.getByTestId("refused-fields")).toHaveCount(0);
  console.log(`[sweep] ${method} ${new URL(response.url()).pathname} ← ${Object.keys(body).sort().join(", ")} → ${response.status()}`);
  return { body, data: envelope?.data };
}

/** A word of the name a picker can be searched by: the first with three
 *  letters or more. NOT simply the first word — this suite's own records are
 *  named "E2E-<digits> …", whose first alphabetic run is "E", and the first
 *  location on the test tenant is usually one of them. */
const searchTerm = (name: unknown) =>
  String(name ?? "").replace(/[^A-Za-z ]/g, " ").split(/\s+/).find((w) => w.length >= 3)?.slice(0, 6) ?? "";

test("asset create — every input this tenant can fill", async ({ page, api }) => {
  const seed = (await api.assets(50)).find((a) => a?.category?.id);
  expect(seed, "an existing asset to borrow a category from").toBeTruthy();
  const loc = await api.firstLocation();
  const emp = await api.firstEmployee();
  const name = markedName("Sweep asset");

  await gotoApp(page, "/assets/new");
  await expectShell(page);
  await field(page, /^\s*name/i).fill(name);
  await field(page, /^\s*legacy code/i).fill("E2E-LEG-1");
  await field(page, /^\s*serial number/i).fill(`E2E-SN-${Date.now()}`);
  await field(page, /^\s*manufacturer/i).fill("E2E Manufacturer");
  await field(page, /^\s*make/i).fill("E2E Make");
  await field(page, /^\s*model/i).fill("E2E Model");
  await field(page, /^\s*category id/i).fill(String(seed.category.id));
  await field(page, /^\s*domain/i, "select").selectOption({ index: 1 });
  await field(page, /^\s*department/i).fill("E2E Department");
  await field(page, /^\s*parent asset id/i).fill(String(seed.id));
  if (seed.currency?.id) await field(page, /^\s*currency id/i).fill(String(seed.currency.id));
  await field(page, /^\s*purchase value/i).fill("1000");
  await field(page, /^\s*replacement cost/i).fill("1200");
  await field(page, /^\s*acquisition cost/i).fill("1000");
  await field(page, /^\s*current value/i).fill("900");
  await field(page, /^\s*purchase date/i).fill("2026-01-15");
  // Handoff 34: a duration, not a date. The start fills in from the purchase
  // date above, visibly; the expiry is the server's to derive and is not sent.
  await field(page, /^\s*duration \(months\)/i).fill("36");
  await expect(field(page, /^\s*start date/i)).toHaveValue("2026-01-15");
  await field(page, /^\s*who honours it/i).fill("E2E Warrantor Ltd");
  await field(page, /^\s*certificate/i).fill("E2E-WC-1");
  await field(page, /^\s*acquisition date/i).fill("2026-01-20");
  await field(page, /^\s*internal notes/i, "textarea").fill("E2E — sweep");
  const locQ = searchTerm(loc?.name);
  const pickedLoc = locQ ? await pickRecord(page, "Search locations", locQ) : null;
  const empQ = searchTerm(emp?.name);
  const pickedEmp = empQ ? await pickRecord(page, "Search employees", empQ) : null;

  const { body, data } = await savedBy(page, "POST", /\/api\/v1\/assets$/, () =>
    page.getByRole("button", { name: /create asset/i }).click());
  recordCreated({ kind: "asset", id: data?.id, name });
  const expected = [
    "name", "legacy_asset_code", "serial_number", "manufacturer", "make", "model_name",
    "category_id", "asset_level", "domain", "department", "parent_id", "condition", "state",
    "purchase_value", "replacement_cost", "acquisition_cost", "current_value",
    "purchase_date", "acquisition_date", "notes",
    "warranty_months", "warranty_start_date", "warrantor", "warranty_reference",
    ...(pickedLoc ? ["location_id"] : []),
    ...(pickedEmp ? ["custodian_id"] : []),
    ...(seed.currency?.id ? ["currency_id"] : []),
  ];
  for (const k of expected) expect(body, `${k} was typed, so it is sent`).toHaveProperty(k);
  expect(body, "the tag is Cadra's to mint").not.toHaveProperty("asset_tag");
  expect(body, "the expiry is derived from the duration, never sent beside it").not.toHaveProperty("warranty_expiry");
  // Read back: it was SAVED, not merely accepted.
  const fresh = await api.get(`/api/v1/assets/${data.id}`);
  expect(fresh?.name).toBe(name);
  expect(fresh?.department).toBe("E2E Department");
});

test("location create, then edit — every input", async ({ page, api }) => {
  const parent = await api.firstLocation();
  const name = markedName("Sweep location");
  await gotoApp(page, "/locations/new");
  await expectShell(page);
  await field(page, /^\s*name/i).fill(name);
  await field(page, /^\s*description/i, "textarea").or(field(page, /^\s*description/i)).first().fill("E2E — sweep");
  await field(page, /^\s*type/i, "select").selectOption("building");
  await field(page, /^\s*zone code/i).fill("E2E-01");
  await field(page, /^\s*floor number/i).fill("2");
  await field(page, /^\s*street\s*$/i).fill("1 Sweep Street");
  await field(page, /^\s*street 2/i).fill("Suite 2");
  await field(page, /^\s*city/i).fill("Abuja");
  await field(page, /^\s*zip/i).fill("900001");
  if (parent?.address?.country?.id) await field(page, /^\s*country id/i).fill(String(parent.address.country.id));
  if (parent?.address?.state?.id) await field(page, /^\s*state id/i).fill(String(parent.address.state.id));
  await page.getByPlaceholder("e.g. 9.0820").fill("9.0820");
  await page.getByPlaceholder("e.g. 8.6753").fill("8.6753");
  const parentQ = searchTerm(parent?.name);
  if (parentQ) await pickRecord(page, "Search parent", parentQ);

  const created = await savedBy(page, "POST", /\/api\/v1\/locations$/, () =>
    page.getByRole("button", { name: /create location/i }).click());
  const id = created.data?.id;
  recordCreated({ kind: "location", id, name });
  for (const k of ["name", "description", "active", "location_type", "zone_code", "floor_number",
    "street", "street2", "city", "zip", "latitude", "longitude"]) {
    expect(created.body, `${k} was typed, so it is sent`).toHaveProperty(k);
  }

  // The same session, straight into Edit: the form is now hydrated from a GET,
  // which is where an echoed read-only key would come from.
  await gotoApp(page, `/locations/${id}/edit`);
  await expect(field(page, /^\s*name/i)).toHaveValue(name, { timeout: 15_000 });
  await field(page, /^\s*name/i).fill(`${name} edited`);
  await savedBy(page, "PATCH", new RegExp(`/api/v1/locations/${id}$`), () =>
    page.getByRole("button", { name: /save changes/i }).click());
  expect((await api.get(`/api/v1/locations/${id}`))?.name).toBe(`${name} edited`);
});

/**
 * The one the 400 exposed. The request form has always had a Location picker
 * and has always sent `location_id`; the API looked for a model field of that
 * name, the Odoo 19 model calls it `generic_location_id`, and every request
 * raised with a location was saved WITHOUT it, with a 201. The API now
 * translates the key. This raises one from the app and reads it back — from
 * the API, from the detail page, and from the Edit form.
 */
test("a request raised with a location KEEPS it — create, detail, edit", async ({ page, api }) => {
  // There is no list endpoint for request types, so one is borrowed — from
  // ANY request that has one; the newest on the test tenant often has none.
  const typeId = Number((await api.requests(100)).find((r) => r?.type?.id)?.type?.id);
  test.skip(!Number.isFinite(typeId) || typeId <= 0, "no request on this tenant carries a type to borrow");
  const loc = (await api.locations(50)).find((l) => searchTerm(l?.name));
  test.skip(!loc, "no searchable location on this tenant");
  const asset = await api.firstAsset();
  const text = markedName("Sweep request — raised with a location");

  await gotoApp(page, "/service-desk/new");
  await expectShell(page);
  await field(page, /^\s*type id/i).fill(String(typeId));
  await field(page, /^\s*priority/i, "select").selectOption("2");
  await field(page, /^\s*deadline/i).fill("2026-12-31");
  await field(page, /^\s*impact/i).fill("2");
  await field(page, /^\s*urgency/i).fill("3");
  await page.getByPlaceholder(/describe the issue/i).fill(text);
  const location = page.locator("label", { hasText: /^\s*location/i }).first().locator("xpath=..");
  const pickedLoc = await pickRecord(location, "Search", searchTerm(loc.name));
  expect(pickedLoc, "the Location picker offered a location").toBeTruthy();
  const assetQ = searchTerm(asset?.name);
  const linked = page.locator("label", { hasText: /^\s*linked asset/i }).first().locator("xpath=..");
  const pickedAsset = assetQ ? await pickRecord(linked, "Search", assetQ) : null;

  const { body, data } = await savedBy(page, "POST", /\/api\/v1\/requests$/, () =>
    page.getByRole("button", { name: "Create request" }).click());
  recordCreated({ kind: "request", id: data?.id, name: text });
  for (const k of ["type_id", "priority", "deadline_date", "impact", "urgency", "request_text", "location_id",
    ...(pickedAsset ? ["nrs_asset_id"] : [])]) {
    expect(body, `${k} was entered, so it is sent`).toHaveProperty(k);
  }

  // Read back from the API: the location is ON the request.
  const fresh = await api.get(`/api/v1/requests/${data.id}`);
  expect(fresh?.location?.id, "the request kept its location").toBe(body.location_id);
  // The detail page — where the form lands — has a place for it and fills it.
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toMatch(new RegExp(`/service-desk/${data.id}$`));
  await expect(page.getByText(/^Location:/).first()).toContainText(String(fresh.location.name), { timeout: 15_000 });

  // Edit, same session: the picker shows what was saved, and an untouched
  // save neither loses it nor is refused.
  await gotoApp(page, `/service-desk/${data.id}/edit`);
  await expect(page.getByPlaceholder(/describe the issue/i)).not.toHaveValue("", { timeout: 15_000 });
  await expect(page.locator("label", { hasText: /^\s*location/i }).first().locator("xpath=..")).toContainText(String(fresh.location.name));
  const edited = await savedBy(page, "PATCH", new RegExp(`/api/v1/requests/${data.id}$`), () =>
    page.getByRole("button", { name: "Save changes" }).click());
  expect(edited.body).toHaveProperty("location_id", body.location_id);
  expect((await api.get(`/api/v1/requests/${data.id}`))?.location?.id).toBe(body.location_id);

  // And the inline priority select on the detail page — the fourth PATCH.
  await gotoApp(page, `/service-desk/${data.id}`);
  await expectShell(page);
  const priority = page.locator("select").first();
  await expect(priority).toBeVisible({ timeout: 15_000 });
  const inline = await savedBy(page, "PATCH", new RegExp(`/api/v1/requests/${data.id}$`), async () => {
    await priority.selectOption("3");
  });
  expect(Object.keys(inline.body)).toEqual(["priority"]);
});

test("category: create, edit its identity, save its depreciation policy, delete", async ({ page, api }) => {
  const name = markedName("Sweep category");
  await gotoApp(page, "/settings/categories");
  await expectShell(page);
  await page.getByTestId("button-add-category").click();
  await page.getByTestId("new-category-name").fill(name);
  const created = await savedBy(page, "POST", /\/api\/v1\/asset-categories$/, () =>
    page.getByTestId("submit-new-category").click());
  const id = created.data?.id;
  expect(id, "the category was created").toBeTruthy();

  try {
    // Identity — a row whose draft is built from the category the GET returned.
    const save = page.getByTestId(`save-cat-${id}`);
    await expect(save).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr", { has: save });
    await row.locator("input").first().fill(`${name} edited`);
    const identity = await savedBy(page, "PATCH", new RegExp(`/api/v1/asset-categories/${id}$`), () => save.click());
    expect(Object.keys(identity.body).sort()).toEqual(
      ["code", "description", "domain", "name", "pm_interval_days", "sequence"]);

    // Policy — the screen where `method` was sent for `depreciation_method`.
    // An EMPTY category, so the recompute this triggers restates nothing.
    // Reached by the page's own link, in the SAME session — the way a person
    // gets there, and not a reload: a full load inside 30 seconds restores
    // the persisted category list from before this category existed and,
    // under that query's `staleTime`, does not refetch it.
    await page.getByRole("link", { name: /Settings.*Depreciation/i }).click();
    const savePolicy = page.getByTestId(`save-category-${id}`);
    await expect(savePolicy).toBeVisible({ timeout: 20_000 });
    const policyRow = page.locator("tr", { has: savePolicy });
    await policyRow.locator("select").first().selectOption("straight_line");
    await policyRow.locator('input[type="number"]').first().fill("48");
    const policy = await savedBy(page, "PATCH", new RegExp(`/api/v1/asset-categories/${id}$`), () => savePolicy.click());
    expect(policy.body).toHaveProperty("depreciation_method", "straight_line");
    expect(policy.body, "the API's READ name is not a write key").not.toHaveProperty("method");
    const fresh = (await api.get<any[]>("/api/v1/asset-categories")).find((c) => c.id === id);
    expect(fresh?.depreciation?.method, "the method really changed").toBe("straight_line");
    expect(fresh?.depreciation?.useful_life_months).toBe(48);
    expect(fresh?.name).toBe(`${name} edited`);
  } finally {
    // By the API, not the screen: a cleanup that clicks can fail, and a
    // failure in a `finally` REPLACES the one the test is about. (It did, on
    // this spec's first run.) Deleting through the screen is spec 15's job.
    const gone = await api.delete(`/api/v1/asset-categories/${id}`);
    expect(gone.status, "the sweep category was removed").toBe(200);
  }
});

test("depreciation settings and branding — a save, and the save that puts it back", async ({ page, api }) => {
  test.setTimeout(240_000);
  // Proration: one key per click. It recomputes the register, so it is slow.
  const settings = await api.get("/api/v1/settings/depreciation");
  test.skip(settings?.mode !== "computed", "proration is disabled while the tenant is ERP-managed");
  const other = settings.proration === "daily" ? "whole_month" : "daily";
  await gotoApp(page, "/settings/depreciation");
  await expectShell(page);
  await expect(page.getByTestId(`proration-${other}`)).toBeEnabled({ timeout: 20_000 });
  try {
    const changed = await savedBy(page, "PATCH", /\/api\/v1\/settings\/depreciation$/, () =>
      page.getByTestId(`proration-${other}`).click());
    expect(changed.body).toEqual({ proration: other });
  } finally {
    await expect(page.getByTestId(`proration-${settings.proration}`)).toBeEnabled({ timeout: 120_000 });
    await savedBy(page, "PATCH", /\/api\/v1\/settings\/depreciation$/, () =>
      page.getByTestId(`proration-${settings.proration}`).click());
  }
  expect((await api.get("/api/v1/settings/depreciation"))?.proration).toBe(settings.proration);

  // Branding saves the object the GET returned, edited — the five writable
  // keys and, since handoff 31, never anything else the GET might grow.
  const brand = await api.get("/api/v1/settings/branding");
  await gotoApp(page, "/settings/branding");
  await expect(page.getByTestId("brand-short-name")).toHaveValue(brand.short_name, { timeout: 15_000 });
  try {
    await page.getByTestId("brand-short-name").fill(`${brand.short_name}x`);
    const saved = await savedBy(page, "PATCH", /\/api\/v1\/settings\/branding$/, () =>
      page.getByTestId("brand-save").click());
    expect(Object.keys(saved.body).sort()).toEqual(["logo", "name", "primary", "primary_dark", "short_name"]);
  } finally {
    await page.getByTestId("brand-short-name").fill(brand.short_name);
    await savedBy(page, "PATCH", /\/api\/v1\/settings\/branding$/, () => page.getByTestId("brand-save").click());
  }
  expect((await api.get("/api/v1/settings/branding"))?.short_name).toBe(brand.short_name);
});
