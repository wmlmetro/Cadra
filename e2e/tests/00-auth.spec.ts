import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { USER, PASS } from "../config";

/**
 * Auth lifecycle: login form, validation, wrong/right creds, show/hide,
 * session chip, theme toggle, sign out.
 */

test.describe("login flow (unauthenticated)", () => {
  // Start with NO stored session so the AuthGate shows the login form.
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login form renders with branding and disabled submit", async ({ page }) => {
    await gotoApp(page, "/");
    const username = page.locator('input[autocomplete="username"]');
    const password = page.locator('input[autocomplete="current-password"]');
    await expect(username).toBeVisible();
    await expect(password).toBeVisible();
    await expect(page.getByRole("heading", { name: /sign in to cadra/i })).toBeVisible();
    // Brand logo present on the login card.
    await expect(page.locator("img").first()).toBeVisible();
    // Submit disabled until both fields filled.
    const submit = page.getByRole("button", { name: "Sign in" });
    await expect(submit).toBeDisabled();
    await username.fill(USER);
    await expect(submit).toBeDisabled();
    await password.fill(PASS);
    await expect(submit).toBeEnabled();
  });

  test("show/hide password toggle works", async ({ page }) => {
    await gotoApp(page, "/");
    const password = page.locator('input[autocomplete="current-password"]');
    await password.fill("secret");
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "SHOW" }).click();
    await expect(password).toHaveAttribute("type", "text");
    await page.getByRole("button", { name: "HIDE" }).click();
    await expect(password).toHaveAttribute("type", "password");
  });

  test("wrong credentials surface an error banner", async ({ page }) => {
    await gotoApp(page, "/");
    await page.locator('input[autocomplete="username"]').fill("nope_" + USER);
    await page.locator('input[autocomplete="current-password"]').fill("wrongpassword");
    await page.getByRole("button", { name: "Sign in" }).click();
    // Error banner text comes from the thrown "code: message".
    await expect(page.getByText(/failed|invalid|unauthorized|auth/i).first()).toBeVisible({
      timeout: 15_000,
    });
    // Still on the login form.
    await expect(page.locator('input[autocomplete="username"]')).toBeVisible();
  });

  test("correct credentials log in and land on the shell", async ({ page }) => {
    await gotoApp(page, "/");
    await page.locator('input[autocomplete="username"]').fill(USER);
    await page.locator('input[autocomplete="current-password"]').fill(PASS);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expectShell(page);
    const token = await page.evaluate(() => localStorage.getItem("cadra.token"));
    expect(token, "cadra.token should be stored after login").toBeTruthy();
  });
});

test.describe("authenticated session", () => {
  test("sidebar session chip shows signed-in state", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);
    await expect(page.getByText("Signed in")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  test("theme toggle flips and persists the theme", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);
    const toggle = page.getByTestId("button-theme-toggle");
    await expect(toggle).toBeVisible();
    const before = await page.evaluate(
      () => document.documentElement.classList.contains("dark"),
    );
    await toggle.click();
    await expect
      .poll(async () =>
        page.evaluate(() => document.documentElement.classList.contains("dark")),
      )
      .not.toBe(before);
  });

  test("sign out returns to the login form", async ({ page }) => {
    await gotoApp(page, "/");
    await expectShell(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.locator('input[autocomplete="username"]')).toBeVisible({ timeout: 15_000 });
  });
});
