import { type Page, expect } from "@playwright/test";
import { appPath } from "../config";

/** Navigate to an in-app route (adds the /app base path). */
export async function gotoApp(page: Page, path: string) {
  await page.goto(appPath(path), { waitUntil: "domcontentloaded" });
}

/**
 * Assert the authenticated shell is present (sidebar rendered). Every
 * authenticated page mounts the sidebar, so this is a cheap "the app booted
 * and didn't fall back to Login / a blank error page" check.
 */
export async function expectShell(page: Page) {
  await expect(page.getByTestId("nav-facility-command-center")).toBeVisible({ timeout: 20_000 });
}

/**
 * Type into a RecordPicker typeahead and select the first matching result.
 * RecordPicker: an input[type=search] whose placeholder starts with the given
 * prefix (min 2 chars, 250ms debounce); results are <button> rows inside a
 * `.z-50` popover. Returns the chosen label, or null if no option appeared
 * (caller decides whether that's a skip or a failure).
 *
 * `placeholderPrefix` is matched with a starts-with selector so callers don't
 * need to reproduce the trailing ellipsis exactly.
 */
export async function pickRecord(
  scope: Page | ReturnType<Page["locator"]>,
  placeholderPrefix: string,
  query: string,
): Promise<string | null> {
  const input = (scope as any).locator(`input[placeholder^="${placeholderPrefix}"]`).first();
  await input.click();
  await input.fill(query);
  const option = (scope as any).locator(".z-50 button").first();
  try {
    await option.waitFor({ state: "visible", timeout: 6000 });
  } catch {
    return null;
  }
  // "No matches." / "Searching…" render as <p>, not <button>, so a visible
  // button here is a real result row.
  const label = (await option.textContent())?.trim() ?? null;
  await option.click();
  return label;
}

/** True if the page shows a "mock data" banner (feature has no live API yet). */
export async function hasMockBanner(page: Page): Promise<boolean> {
  const banner = page.getByText(/mock data|sample data|no .* endpoint/i).first();
  return (await banner.count()) > 0 && (await banner.isVisible().catch(() => false));
}
