import { test as base, expect, type Page } from "@playwright/test";
import { ApiClient } from "./api";

/**
 * Extended test with:
 *  - `api`   worker-scoped REST client (one login per worker) for discovering
 *            real record IDs and setting up preconditions.
 *  - console-guard: an auto fixture that captures uncaught page exceptions and
 *            fails the test if any occur — so a button that silently blows up
 *            the page is caught even when no assertion targets it directly.
 *            Opt out per-test with test.info().annotations 'allow-page-errors'.
 */
type WorkerFixtures = { api: ApiClient };
type TestFixtures = { pageErrors: string[] };

export const test = base.extend<TestFixtures, WorkerFixtures>({
  api: [
    async ({}, use) => {
      const api = await ApiClient.login();
      await use(api);
      await api.dispose();
    },
    { scope: "worker" },
  ],

  pageErrors: [
    async ({ page }, use, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(String(err?.stack || err?.message || err)));
      await use(errors);

      const optOut = testInfo.annotations.some((a) => a.type === "allow-page-errors");
      if (!optOut && errors.length) {
        await testInfo.attach("page-errors.txt", { body: errors.join("\n\n---\n\n") });
        expect(errors, `Uncaught page exception(s) during "${testInfo.title}"`).toEqual([]);
      }
    },
    { auto: true },
  ],
});

export { expect };
export type { Page };
