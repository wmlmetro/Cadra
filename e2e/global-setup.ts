import { chromium, request, type FullConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { ORIGIN, APP_BASE, USER, PASS, STORAGE_STATE, appPath } from "./config";

/**
 * 1. Preflight: confirm the stack is up and the expected tenant answers.
 * 2. Drive the real login form once and persist storageState (captures the
 *    cadra.* localStorage token keys) so every spec starts authenticated.
 */
export default async function globalSetup(_config: FullConfig) {
  // ── 1. Preflight ──────────────────────────────────────────────────────────
  const rc = await request.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  let brandName = "(unknown)";
  try {
    const appRes = await rc.get(`${APP_BASE}/`);
    if (!appRes.ok()) {
      throw new Error(`GET ${APP_BASE}/ returned HTTP ${appRes.status()}`);
    }
    const brandRes = await rc.get(`/api/v1/brand`);
    if (!brandRes.ok()) {
      throw new Error(`GET /api/v1/brand returned HTTP ${brandRes.status()}`);
    }
    const brand = await brandRes.json();
    brandName = brand?.data?.name ?? brand?.name ?? JSON.stringify(brand).slice(0, 80);
    // eslint-disable-next-line no-console
    console.log(`\n[preflight] ${ORIGIN}${APP_BASE}/ is up · tenant brand = "${brandName}"`);
  } catch (e) {
    throw new Error(
      `\n\n[preflight FAILED] Could not reach the Cadra stack at ${ORIGIN}.\n` +
        `Is the local stack running? Expected ${ORIGIN}${APP_BASE}/ and /api/v1/brand to respond.\n` +
        `Bring it up with the dev compose files, then re-run.\n` +
        `Underlying error: ${(e as Error).message}\n`,
    );
  } finally {
    await rc.dispose();
  }

  // ── 2. UI login → storageState ─────────────────────────────────────────────
  fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  try {
    await page.goto(appPath("/"), { waitUntil: "domcontentloaded" });

    // AuthGate renders the login form when there is no session.
    const username = page.locator('input[autocomplete="username"]');
    await username.waitFor({ state: "visible", timeout: 20_000 });
    await username.fill(USER);
    await page.locator('input[autocomplete="current-password"]').fill(PASS);
    await page.getByRole("button", { name: "Sign in" }).click();

    // Success = authenticated shell. The primary nav item is the tell.
    await page
      .getByTestId("nav-facility-command-center")
      .waitFor({ state: "visible", timeout: 20_000 });

    // Sanity-check a token actually landed in localStorage.
    const token = await page.evaluate(() => localStorage.getItem("cadra.token"));
    if (!token) throw new Error("Login appeared to succeed but no cadra.token in localStorage.");

    await page.context().storageState({ path: STORAGE_STATE });
    // eslint-disable-next-line no-console
    console.log(`[auth] logged in as "${USER}" — storageState saved to ${STORAGE_STATE}\n`);
  } catch (e) {
    await page
      .screenshot({ path: "test-results/global-setup-failure.png", fullPage: true })
      .catch(() => {});
    throw new Error(
      `[auth FAILED] Could not log in as ${USER}/${PASS} at ${ORIGIN}${APP_BASE}/.\n` +
        `Underlying error: ${(e as Error).message}`,
    );
  } finally {
    await browser.close();
  }
}
