import { defineConfig, devices } from "@playwright/test";
import { ORIGIN, STORAGE_STATE } from "./config";

/**
 * E2E config for the Cadra /app SPA.
 *
 * - baseURL is the ORIGIN; specs navigate with absolute /app/... paths via the
 *   appPath() helper (the SPA lives under a base path, so a bare "/" would miss it).
 * - No `webServer`: the stack is expected to be already running. global-setup
 *   preflights it and fails fast with a clear message if it isn't.
 * - Auth is established once in global-setup and reused via storageState.
 */
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  fullyParallel: false,          // shared tenant DB — keep writes serialized & legible
  workers: 1,
  retries: process.env.CI ? 1 : 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  use: {
    baseURL: ORIGIN,
    storageState: STORAGE_STATE,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
