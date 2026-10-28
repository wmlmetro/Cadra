import { readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { asPersona, receive, receiptGated } from "../fixtures/gates";

/**
 * Handoff 70 §7 — the administrator can finish it, in the browser, as the
 * demo administrator signed in through the real sign-in page.
 *
 *   switch       on Settings › Receipt gates, the administrator turns on
 *                "Administrators may act at every step"; the sentence under
 *                it is the server's.
 *   two gates    a candidate the administrator has already submitted and
 *                verified (over the API — the verify dialog's evidence upload
 *                is spec 57's); on its page the administrator's next two acts
 *                read "Approve (as administrator)" and "Request tagging (as
 *                administrator)", and both are clicked through.
 *   the list     on Audit › Administrator overrides, both acts are listed for
 *                that asset, with the rule each lifted; the line at the top
 *                says the override is on.
 *
 * The tenant's own value of the switch is put back at the end.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/70-the-administrator-can-finish-it.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const REPO = path.resolve(__dirname, "../..");
const CREDS = process.env.E2E_PERSONAS ?? path.join(REPO, `docs/api/.personas.${TENANT}`);

function persona(key: string): { login: string; password: string } {
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key) return { login, password };
  }
  throw new Error(`${CREDS} has no "${key}" persona`);
}

async function signIn(page: Page, key: string) {
  const p = persona(key);
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

async function ok(res: { status: number; body: any }, status: number, what: string) {
  expect(res.status, `${what}: ${JSON.stringify(res.body?.error ?? res.body).slice(0, 400)}`).toBe(status);
  return res.body.data;
}

async function fireAsAdmin(page: Page, action: string) {
  const button = page.getByTestId(`gate-${action}`);
  await expect(button).toBeVisible({ timeout: 20_000 });
  await expect(button).toHaveText(/\(as administrator\)/);
  await expect(button).toHaveAttribute("data-as-admin", "true");
  await button.click();
  const dialog = page.getByTestId(`dialog-gate-${action}`);
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("gate-dialog-as-admin")).toBeVisible();
  const done = page.waitForResponse((r) => r.url().includes(`/gates/${action}`)
    && r.request().method() === "POST");
  await dialog.getByTestId("button-confirm-gate").click();
  expect((await done).status()).toBe(200);
  await expect(dialog).toBeHidden({ timeout: 15_000 });
}

test.describe("70 · the administrator can finish it", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  let was: boolean | null = null;

  test.afterAll(async () => {
    if (was !== null) {
      await asPersona("administrator", "PATCH", "/settings/admin-override", { enabled: was });
    }
  });

  test("switch on, two gates as administrator, both listed", async ({ page, api }) => {
    test.skip(!(await receiptGated(api)), "the receipt gates are off on this tenant: no gate to fire");
    test.setTimeout(180_000);
    was = (await ok(await asPersona("administrator", "GET", "/settings"), 200, "settings"))
      .admin_override.enabled;
    if (was) {
      await ok(await asPersona("administrator", "PATCH", "/settings/admin-override", { enabled: false }),
        200, "switch off first");
    }

    // ── the switch, in the browser ──
    await signIn(page, "administrator");
    await page.goto(appPath("/settings/receipt-gate"));
    const section = page.getByTestId("admin-override");
    await expect(section).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId("admin-override-statement")).toContainText(
      "Leave it off where two people must sign.");
    const patched = page.waitForResponse((r) => r.url().includes("/settings/admin-override")
      && r.request().method() === "PATCH");
    await page.getByTestId("admin-override-switch").click();
    expect((await patched).status()).toBe(200);
    await expect(section).toHaveAttribute("data-enabled", "true");

    // ── a candidate the administrator has submitted and verified ──
    const unit = await receive(api, { name: `e2e-70 alone ${Date.now()}` });
    expect(unit.register_state).toBe("captured");
    const id = unit.id;
    await ok(await asPersona("administrator", "POST", `/assets/${id}/gates/submit`, {}), 200, "submit");
    await ok(await asPersona("administrator", "POST", `/assets/${id}/gates/verify`, {
      checklist: { quantity: true, specification: true, condition: true, price: true },
      attachments: [{ name: "sighted.txt", data: "c2lnaHRlZA==" }],
    }), 200, "verify");

    // ── two gates, by the buttons ──
    await page.goto(appPath(`/assets/${id}`));
    await fireAsAdmin(page, "approve");
    await fireAsAdmin(page, "request-tagging");
    const after = await ok(await asPersona("administrator", "GET", `/assets/${id}`), 200, "asset");
    expect(after.register_state).toBe("tag_issued");

    // ── the list ──
    await page.goto(appPath("/audit/admin-overrides"));
    await expect(page.getByTestId("admin-overrides-page")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("admin-overrides-status-line")).toHaveAttribute("data-enabled", "true");
    await page.getByTestId("input-overrides-kind").selectOption("gate");
    const rows = page.getByTestId("admin-overrides-row").filter({ hasText: after.asset_code });
    await expect(rows).toHaveCount(3, { timeout: 20_000 }); // verify, approve, request tagging
    for (const act of ["approve", "request-tagging", "verify"]) {
      const row = rows.and(page.locator(`[data-act="${act}"]`));
      await expect(row).toHaveCount(1);
      await expect(row).toContainText("They ");
    }
  });
});
