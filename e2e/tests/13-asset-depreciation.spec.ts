import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Depreciation on the asset detail page (PRD §8.6).
 *
 * Depreciation lives in its own tab on the asset detail page, so every test
 * opens that tab first.
 *
 * The card renders whenever the API returns a `financial.depreciation` block.
 * The value-over-time chart only renders for methods Cadra actually computes —
 * `none` has nothing to plot and `erp_managed` is owned by the tenant's ERP,
 * which supplies a book value but no schedule.
 *
 * Skips rather than fails when the tenant has no asset in the relevant state:
 * these run against whichever tenant E2E_ORIGIN points at, and a register with
 * no depreciation policy configured is a legitimate state, not a regression.
 */

/** First asset whose depreciation block matches `pred`.
 *
 *  Pages through the register rather than taking one big page. The list is
 *  ordered by id, and a tenant's ERP-managed or non-depreciating assets are
 *  typically a handful at the *end* — with a single page they fall off the
 *  bottom and the test skips while looking like it ran. Uses `probe` because
 *  `get` unwraps to `data` and drops the cursor. */
async function findAsset(
  api: { probe: (p: string, q?: Record<string, string | number>) => Promise<any> },
  pred: (d: any) => boolean,
) {
  const PAGE = 500;
  const MAX_PAGES = 40;          // 20k assets — well past any current tenant
  let cursor: string | undefined;

  for (let i = 0; i < MAX_PAGES; i++) {
    const params: Record<string, string | number> = { limit: PAGE };
    if (cursor) params.cursor = cursor;
    const { body } = await api.probe("/api/v1/assets", params);
    for (const a of body?.data ?? []) {
      const d = a?.financial?.depreciation;
      if (d && pred(d)) return a;
    }
    cursor = body?.pagination?.next_cursor ?? undefined;
    if (!cursor) break;
  }
  return null;
}

/** Open an asset and switch to its Depreciation tab. */
async function openDepreciationTab(page: any, id: number | string) {
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  const tab = page.getByTestId("tab-depreciation");
  await expect(tab).toBeVisible();
  await tab.click();
}

test("asset detail has a Depreciation tab", async ({ page, api }) => {
  const asset = await findAsset(api, () => true);
  test.skip(!asset, "no asset exposes a depreciation block");

  await openDepreciationTab(page, asset.id);

  await expect(page.getByText("Net Book Value")).toBeVisible();
  await expect(page.getByText(/^404$/).first()).toHaveCount(0);
});

test("a computed asset charts its value over time", async ({ page, api }) => {
  // The first COMPUTED asset is not the first CHARTABLE asset — handoff 51
  // §3a, after this spec spent its life red on test19 because the first
  // straight-line asset there has neither a cost nor a useful life, and the
  // product rendered its honest "No schedule yet" empty state. The engine
  // (depreciation_engine.build_schedule) returns an empty schedule unless
  // the method is computed AND there is a start date AND cost > 0 AND the
  // useful life > 0 AND salvage < cost AND (declining balance only) a rate;
  // selecting on fewer of those just moves the same fixture defect onto the
  // next field. A tenant with no such asset SKIPS LOUDLY below — a spec
  // that quietly finds nothing to assert and goes green is the same defect
  // class wearing a test's clothing.
  const asset = await findAsset(api, d =>
    (d.method === "straight_line" || d.method === "declining_balance") &&
    (d.depreciable_cost ?? 0) > 0 &&
    (d.useful_life_months ?? 0) > 0 &&
    !!d.start_date &&
    (d.salvage_value ?? 0) < (d.depreciable_cost ?? 0) &&
    (d.method !== "declining_balance" || (d.declining_rate ?? 0) > 0),
  );
  test.skip(
    !asset,
    "no CHARTABLE asset on this tenant: nothing has a computed method with " +
    "a cost, a useful life and a start date, so there is no schedule for " +
    "the product to draw and nothing for this spec to assert",
  );

  await openDepreciationTab(page, asset.id);

  await expect(page.getByText("Value over time")).toBeVisible();
  // The chart itself, not just the heading.
  await expect(page.locator("svg.recharts-surface").first()).toBeVisible();

  // The year-by-year schedule expands and has rows.
  const toggle = page.getByTestId("toggle-depreciation-schedule");
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(page.locator("table tbody tr").first()).toBeVisible();
});

test("an ERP-managed asset shows no schedule, and says why", async ({ page, api }) => {
  const asset = await findAsset(api, d => d.method === "erp_managed");
  test.skip(!asset, "no asset is ERP-managed on this tenant");

  await openDepreciationTab(page, asset.id);

  // NRS spec §6.2 — Cadra reads but does not compute.
  await expect(page.getByText(/supplied by an external ERP/i)).toBeVisible();
  await expect(page.getByText("Value over time")).toHaveCount(0);
});

test("a non-depreciating asset charts nothing", async ({ page, api }) => {
  const asset = await findAsset(api, d => d.method === "none");
  test.skip(!asset, "every asset on this tenant has a depreciation policy");

  await openDepreciationTab(page, asset.id);
  await expect(page.getByText("Value over time")).toHaveCount(0);
});
