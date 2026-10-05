import * as fs from "fs";
import * as path from "path";

import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";

/**
 * Settings → Depreciation.
 *
 * Every control here restates book value across the register, so the tests
 * restore whatever they change. They deliberately avoid asserting specific
 * figures — those depend on tenant data — and assert behaviour instead.
 */

/** The `depreciation-settings` entry of the PERSISTED react-query cache, as
 *  the browser holds it right now — handoff 51 §3b's measurement. The
 *  reload-persistence failure has carried GO-LIVE §16.3 item 8's
 *  persisted-cache hypothesis since report 50, labelled a hypothesis
 *  because nobody had read this payload mid-test. With E2E_EVIDENCE set to
 *  a directory, the dump lands there; the spec itself asserts nothing
 *  about it, because the cache policy is deliberately not this spec's to
 *  judge (the fix is a product-wide decision, handoff 51 §3b). */
async function dumpPersistedSettings(
  page: any, label: string, context: Record<string, unknown> = {},
) {
  const dir = process.env.E2E_EVIDENCE;
  const dump = await page.evaluate(() => {
    let raw: string | null = null;
    try {
      raw = window.localStorage.getItem("cadra.queryCache");
    } catch {
      return { error: "localStorage unreadable" };
    }
    if (!raw) return { absent: true };
    try {
      const parsed = JSON.parse(raw);
      const queries = parsed?.clientState?.queries ?? [];
      const entry = queries.find(
        (q: any) => Array.isArray(q.queryKey) &&
          q.queryKey[0] === "depreciation-settings");
      return {
        buster: parsed?.buster,
        timestamp: parsed?.timestamp,
        entry: entry ?? null,
      };
    } catch {
      return { error: "cadra.queryCache is not JSON" };
    }
  });
  const record = { label, at: new Date().toISOString(), ...context, ...dump };
  if (dir) {
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(
      path.join(dir, "spec14-persisted-cache.jsonl"),
      JSON.stringify(record) + "\n");
  }
  return record;
}

test.describe("/settings/depreciation", () => {
  test.beforeEach(async ({ page }) => {
    await gotoApp(page, "/settings/depreciation");
    await expectShell(page);
  });

  test("renders the settings surface", async ({ page }) => {
    await expect(page.getByText("Depreciation settings")).toBeVisible();
    await expect(page.getByTestId("mode-computed")).toBeVisible();
    await expect(page.getByTestId("mode-erp_managed")).toBeVisible();
    await expect(page.getByTestId("toggle-db-switch")).toBeVisible();
    await expect(page.getByTestId("button-recompute")).toBeVisible();
    await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  });

  test("lists categories with an editable policy", async ({ page }) => {
    await expect(page.getByText("Policy by asset category")).toBeVisible();
    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(0);
    // Method is a real select, not a label.
    await expect(rows.first().locator("select")).toBeVisible();
  });

  test("the straight-line switch persists across a reload", async ({ page }) => {
    const toggle = page.getByTestId("toggle-db-switch");
    const before = await toggle.isChecked();
    try {
      // The reload must not outrun the WRITE — found by handoff 52 §5's
      // first three runs. The toggle flips optimistically (`onMutate`), so
      // the assertion below is satisfied while the PATCH is still in
      // flight, and reloading then ABORTS it: the server never changes,
      // and this spec used to go green anyway by reading its own restored
      // sketch back out of localStorage. Under the §5 ruling the restored
      // entry is refetched and the screen tells the server's truth, which
      // is what exposed the race. Waiting for the PATCH response is
      // waiting for the act under test; the persister's 1 s throttle is
      // untouched, and the PATCH usually answers inside it — so the copy
      // the reload restores is still typically the PRE-flip payload, and
      // the green below is the refetch's doing, not the cache's.
      const patched = page.waitForResponse(
        r => r.url().includes("/api/v1/settings/depreciation")
          && r.request().method() === "PATCH",
        { timeout: 30_000 });
      await toggle.click();
      // The mutation recomputes the register, so give it room.
      await expect(toggle).toBeChecked({ checked: !before, timeout: 30_000 });

      // §3b's two instants: what localStorage holds between the click and
      // the reload, and what it holds after. Taken IMMEDIATELY, with no
      // settling pause, because the hypothesis is about this exact window:
      // the persister throttles its writes to 1 s, so the copy a reload
      // restores right now may still be the PRE-flip payload. A pause here
      // would let the throttle flush and measure a different spec.
      await dumpPersistedSettings(page, "between click and reload",
        { before, expected_after_click: !before });

      await patched;
      await page.reload();
      await expectShell(page);
      await dumpPersistedSettings(page, "after reload",
        { before, expected_after_click: !before });
      await expect(page.getByTestId("toggle-db-switch"))
        .toBeChecked({ checked: !before, timeout: 30_000 });

      // Handoff 52 §5's proof instant: after the toggle has settled, the
      // restored entry must have been REFETCHED, not merely trusted — a
      // changed `dataUpdatedAt` in the persisted copy once the 1 s write
      // throttle has flushed the post-refetch cache back to disk. (The
      // restore-time invalidation in App.tsx is what makes this true; a
      // restored entry is never fresh.)
      await page.waitForTimeout(1500);
      await dumpPersistedSettings(page, "after settle (52 §5: refetched)",
        { before, expected_after_click: !before });
    } finally {
      const t = page.getByTestId("toggle-db-switch");
      if (await t.isChecked() !== before) {
        // Same race on the restore: wait for ITS write too, or the next
        // run inherits a flipped tenant.
        const restored = page.waitForResponse(
          r => r.url().includes("/api/v1/settings/depreciation")
            && r.request().method() === "PATCH",
          { timeout: 30_000 });
        await t.click();
        await expect(t).toBeChecked({ checked: before, timeout: 30_000 });
        await restored;
      }
    }
  });

  test("recompute reports back", async ({ page }) => {
    await page.getByTestId("button-recompute").click();
    await expect(page.getByText(/Recomputed .* assets/i)).toBeVisible({ timeout: 60_000 });
  });

  test("ERP-managed mode disables the calculation controls", async ({ page }) => {
    const computed = page.getByTestId("mode-computed");
    try {
      await page.getByTestId("mode-erp_managed").click();
      await expect(page.getByText(/This tenant is ERP-managed/i))
        .toBeVisible({ timeout: 30_000 });
      // Cadra must not offer to compute what it does not own.
      await expect(page.getByTestId("toggle-db-switch")).toBeDisabled();
      await expect(page.getByTestId("button-recompute")).toBeDisabled();
    } finally {
      await computed.click();
      await expect(page.getByText(/This tenant is ERP-managed/i))
        .toHaveCount(0, { timeout: 30_000 });
    }
  });
});
