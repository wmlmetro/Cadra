import { writeFileSync } from "node:fs";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName } from "../fixtures/marker";

/**
 * Handoff 45, in a browser: the first five minutes, as a new officer meets
 * them — and the back office shut to everybody who is not a developer.
 *
 * Run it once per tenant (two differently-branded tenants for the report):
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 E2E_SHOTS=… npx playwright test 45-)
 *
 * 1. The letter, read out of the INBOX (Mailpit, `E2E_MAILPIT`, default
 *    http://localhost:8025), links to the app; the person opens it, sets a
 *    password and is signed in — and in that whole journey the browser makes
 *    NO request to Odoo's back office (`/web…`, `/odoo…`).
 * 2. Every way a link can be dead, as the page renders it: used, cancelled,
 *    never valid — and expired when `E2E_EXPIRED_TOKEN` is supplied (only the
 *    server can mint one; the in-registry suite proves the state itself).
 * 3. *Forgot password?* from the sign-in page, the reset letter, a new
 *    password, signed in; the old password refused afterwards.
 * 4. The new officer — a NON-administrator — uses the app, prints a label
 *    from the barcode station (the QR on the label is fetched from Odoo's
 *    public `/report/barcode`, the one non-API Odoo URL the app requests),
 *    and is sent to the app when they type `/odoo`.
 * 5. The administrator still reaches the back office.
 *
 * Every person this spec makes is a marked fixture, deactivated afterwards.
 * Set `E2E_SHOTS=<dir>` to save the screenshots the report refers to.
 */

const MAILPIT = (process.env.E2E_MAILPIT || "http://localhost:8025").replace(/\/$/, "");
const LINK = /(https?:\/\/[^\s"'<>]+\/app\/(accept-invite|reset-password)\?token=([A-Za-z0-9_-]+))/;

async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  const tenant = new URL(ORIGIN).hostname.split(".")[0];
  await page.screenshot({ path: `${dir}/${tenant}-${name}.png`, fullPage: false });
}

type Letter = { id: string; link: string; html: string; text: string };

async function letterTo(address: string, page: "accept-invite" | "reset-password"): Promise<Letter> {
  try {
    const ping = await fetch(`${MAILPIT}/api/v1/messages?limit=1`);
    if (!ping.ok) throw new Error(String(ping.status));
  } catch (e) {
    test.skip(true, `the inbox at ${MAILPIT} cannot be read (${e}); the letter cannot be proved here`);
  }
  for (let i = 0; i < 30; i++) {
    const found = await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent("to:" + address)}`)).json();
    for (const m of found.messages ?? []) {
      const msg = await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
      const both = `${msg.Text ?? ""} ${msg.HTML ?? ""}`;
      const hit = both.match(LINK);
      if (hit && hit[2] === page) return { id: m.ID, link: hit[1], html: msg.HTML ?? "", text: msg.Text ?? "" };
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`0 letters to ${address} with an /app/${page} link arrived in 30s`);
}

/** Every request this page makes to the tenant's own host, by path. */
function watchOdoo(page: Page) {
  const host = new URL(ORIGIN).host;
  const paths: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.host === host) paths.push(u.pathname);
  });
  return {
    paths,
    backOffice: () => paths.filter((p) => p === "/web" || p.startsWith("/web/") || p === "/odoo" || p.startsWith("/odoo/")),
  };
}

async function invite(api: any, roles: string[]) {
  // `markedName` is per RUN; a second person in one run needs its own name,
  // or the address collides with the first (409, found on the first run).
  const name = markedName(`officer-${Math.random().toString(36).slice(2, 8)}`);
  const email = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}@example.invalid`;
  const res = await api.raw("POST", "/api/v1/users", { name, email, roles, send_invitation: true });
  if (res.status === 500) test.skip(true, `this tenant refuses to send the letter: ${JSON.stringify(res.body).slice(0, 200)}`);
  expect(res.status, JSON.stringify(res.body)).toBe(201);
  return { id: res.body.data.id as number, login: res.body.data.login as string, name, email };
}

/** A person who has already accepted their invitation — through the same
 *  two API calls the page makes — for the tests that start AFTER the first
 *  five minutes. Each test makes its own, so no test depends on another. */
async function officer(api: any, roles: string[], made: number[]) {
  const person = await invite(api, roles);
  made.push(person.id);
  const letter = await letterTo(person.email, "accept-invite");
  const token = new URL(letter.link).searchParams.get("token")!;
  const password = `pw-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const res = await fetch(`${ORIGIN}/api/v1/auth/password-token/redeem`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password, confirm_password: password }),
  });
  expect(res.status, await res.clone().text()).toBe(200);
  return { ...person, password, link: letter.link };
}

async function setPassword(page: Page, password: string) {
  await page.locator("#new-password").fill(password);
  await page.locator("#confirm-password").fill(password);
}

test.describe("handoff 45 — the first five minutes", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  const made: number[] = [];

  test.afterAll(async ({ api }) => {
    for (const id of made) {
      await api.raw("POST", `/api/v1/users/${id}/deactivate`, {}).catch(() => undefined);
    }
  });

  // FIRST, on purpose: core rewrites `web.base.url` from the host an
  // administrator signs in on, and an ANONYMOUS reset link (Forgot
  // password?) is built on it — by design, handoff 43 §F. On a tenant no
  // administrator has signed into, it is still the install default
  // (`http://localhost:8069`) and the reset letter points nowhere: found on
  // this spec's second run, `docs/GO-LIVE.md` §22.2.
  test("a system administrator still reaches the back office", async ({ page }) => {
    const user = process.env.E2E_USER || "admin";
    const pass = process.env.E2E_PASS || "admin";
    await page.goto(`${ORIGIN}/web/login`);
    await page.locator('form.oe_login_form input[name="login"]').fill(user);
    await page.locator('form.oe_login_form input[name="password"]').fill(pass);
    await page.locator('form.oe_login_form button[type="submit"]').click();
    await page.waitForURL(/\/odoo/, { timeout: 30_000 });
    await expect(page.locator(".o_main_navbar").first()).toBeVisible({ timeout: 30_000 });
    await shot(page, "13-admin-backoffice");
  });

  test("the letter → our page → a password → signed in, and Odoo never appears", async ({ page, api }) => {
    const person = await invite(api, ["asset_manager", "tag_issuing_unit"]);
    made.push(person.id);
    const letter = await letterTo(person.email, "accept-invite");
    expect(letter.html + letter.text).not.toContain("/web/");

    await page.goto(`${MAILPIT}/view/${letter.id}.html`);
    await shot(page, "1-letter");

    const odoo = watchOdoo(page);
    await page.goto(letter.link);
    await expect(page.getByTestId("token-person")).toContainText(person.name, { timeout: 20_000 });
    await shot(page, "2-our-page");

    await setPassword(page, "short");
    await page.locator("#confirm-password").fill("shorx");
    await expect(page.getByTestId("password-missing")).toHaveText(/do not match/);
    const password = `pw-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await setPassword(page, password);
    await shot(page, "3-password-typed");
    await page.getByRole("button", { name: /Set password and sign in/ }).click();
    await expect(page.getByTestId("nav-facility-command-center")).toBeVisible({ timeout: 20_000 });
    await shot(page, "4-signed-in");

    expect(odoo.backOffice(), `requests to Odoo's back office: ${odoo.backOffice().join(", ")}`).toEqual([]);
    expect(new URL(page.url()).pathname.startsWith("/app")).toBe(true);
    // No Odoo letter followed the password into the inbox.
    await page.waitForTimeout(2000);
    const notices = await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${person.email} subject:"Security Update"`)}`)).json();
    expect(notices.messages ?? [], "Odoo's own security notice reached the person").toEqual([]);
    const row = (await api.get(`/api/v1/users/${person.id}`)) as any;
    expect(row.invitation.state).toBe("redeemed");
  });

  test("every dead link says why, and offers a way forward", async ({ page, api }) => {
    // Used: a link somebody has already set their password with.
    const used = await officer(api, ["asset_user"], made);
    await page.goto(used.link);
    await expect(page.getByTestId("token-state-redeemed")).toContainText("already been used", { timeout: 20_000 });
    await shot(page, "5-link-redeemed");

    // Cancelled: invited, then switched off before opening it.
    const leaver = await invite(api, ["asset_user"]);
    made.push(leaver.id);
    const letter = await letterTo(leaver.email, "accept-invite");
    await api.raw("POST", `/api/v1/users/${leaver.id}/deactivate`, {});
    await page.goto(letter.link);
    await expect(page.getByTestId("token-state-cancelled")).toContainText("no longer valid", { timeout: 20_000 });
    await shot(page, "6-link-cancelled");

    // Never valid.
    await page.goto(appPath("/accept-invite?token=this-was-never-a-token"));
    await expect(page.getByTestId("token-state-invalid")).toContainText("not valid", { timeout: 20_000 });
    await shot(page, "7-link-invalid");

    // Expired: minted by the server for the report run.
    const expired = process.env.E2E_EXPIRED_TOKEN;
    if (expired) {
      await page.goto(appPath(`/accept-invite?token=${expired}`));
      await expect(page.getByTestId("token-state-expired")).toContainText("expired", { timeout: 20_000 });
      await shot(page, "8-link-expired");
    }
  });

  test("Forgot password? → the reset letter → a new password → signed in", async ({ page, api }) => {
    const person = await officer(api, ["asset_user"], made);
    const odoo = watchOdoo(page);
    await page.goto(appPath("/"));
    await page.getByTestId("link-forgot-password").click();
    await expect(page.getByTestId("forgot-password-form")).toBeVisible();
    await page.locator("#forgot-login").fill(person.login);
    await shot(page, "9-forgot");
    await page.getByRole("button", { name: /Send me a link/ }).click();
    await expect(page.getByTestId("auth-notice")).toContainText("If an account matches");

    const letter = await letterTo(person.email, "reset-password");
    await page.goto(letter.link);
    await expect(page.getByTestId("set-password-form")).toBeVisible({ timeout: 20_000 });
    const next = `pw2-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await setPassword(page, next);
    await shot(page, "10-reset-page");
    await page.getByRole("button", { name: /Save new password and sign in/ }).click();
    await expect(page.getByTestId("nav-facility-command-center")).toBeVisible({ timeout: 20_000 });
    expect(odoo.backOffice()).toEqual([]);

    const ctx = page.context().request;
    const old = await ctx.post(`${ORIGIN}/api/v1/auth/login`, { data: { login: person.login, password: person.password } });
    expect(old.status()).toBe(401);
    const fresh = await ctx.post(`${ORIGIN}/api/v1/auth/login`, { data: { login: person.login, password: next } });
    expect(fresh.status()).toBe(200);
  });

  test("a non-administrator uses the app, prints a label, and cannot reach the back office", async ({ page, api }) => {
    const tagged = (await api.get("/api/v1/assets", { is_tagged: "true", limit: 1 })) as any[];
    test.skip(!tagged?.length, "0 tagged assets on this tenant: no 'Print label' to press");
    const tagger = await officer(api, ["asset_manager", "tag_issuing_unit"], made);

    // The print dialog cannot be driven; the label's own frame calls print().
    await page.addInitScript(() => {
      window.print = () => {
        (window.top as any).__labelsPrinted = ((window.top as any).__labelsPrinted || 0) + 1;
      };
    });
    const odoo = watchOdoo(page);
    const qr: { status: number; type: string }[] = [];
    page.on("response", (r) => {
      if (new URL(r.url()).pathname === "/report/barcode") qr.push({ status: r.status(), type: r.headers()["content-type"] ?? "" });
    });

    await page.goto(appPath("/"));
    await page.locator('input[autocomplete="username"]').fill(tagger.login);
    await page.locator('input[autocomplete="current-password"]').fill(tagger.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByTestId("nav-facility-command-center")).toBeVisible({ timeout: 20_000 });

    for (const path of ["/assets", "/approvals", "/tools/barcode"]) {
      await page.goto(appPath(path));
      await page.waitForLoadState("networkidle").catch(() => undefined);
    }
    const box = page.getByTestId("scan-box");
    await box.fill(tagged[0].tag);
    await box.press("Enter");
    await expect(page.getByTestId("lookup-result")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("lookup-result").getByRole("button", { name: "Print label", exact: true }).click();
    await expect.poll(() => page.evaluate(() => (window as any).__labelsPrinted || 0), { timeout: 20_000 }).toBeGreaterThan(0);
    await expect.poll(() => qr.length, { timeout: 10_000 }).toBeGreaterThan(0);
    expect(qr.every((r) => r.status === 200 && r.type.startsWith("image/")), JSON.stringify(qr)).toBe(true);
    await shot(page, "11-label-printed");
    expect(odoo.backOffice(), `requests to Odoo's back office: ${odoo.backOffice().join(", ")}`).toEqual([]);
    // The enumeration §2.2 asks for: every path on the tenant's host this
    // session requested that is neither the app nor its API.
    const outsideApp = [...new Set(odoo.paths.filter((p) => !p.startsWith("/api/v1/") && !p.startsWith("/app")))].sort();
    test.info().annotations.push({ type: "app-requests-to-odoo", description: outsideApp.join(" ") });
    if (process.env.E2E_SHOTS) {
      const tenant = new URL(ORIGIN).hostname.split(".")[0];
      const all = [...new Set(odoo.paths)].sort();
      writeFileSync(`${process.env.E2E_SHOTS}/${tenant}-requests.txt`,
        `Every path the non-administrator's session requested on ${new URL(ORIGIN).host}, ` +
        `${all.length} distinct (of ${odoo.paths.length} requests):\n` + all.join("\n") +
        `\n\nOutside /app and /api/v1: ${outsideApp.length ? outsideApp.join(", ") : "none"}\n`);
    }

    // Typing the back office: sent to the app.
    for (const path of ["/odoo", "/web", "/odoo/action-base.action_res_users"]) {
      await page.goto(`${ORIGIN}${path}`);
      expect(new URL(page.url()).pathname, path).toBe("/app/");
    }
    // Signing in on Odoo's own page: sent to the app, no Odoo session kept.
    await page.goto(`${ORIGIN}/web/login`);
    await page.locator('form.oe_login_form input[name="login"]').fill(tagger.login);
    await page.locator('form.oe_login_form input[name="password"]').fill(tagger.password);
    await page.locator('form.oe_login_form button[type="submit"]').click();
    await page.waitForURL(/\/app\/?$/, { timeout: 20_000 });
    await shot(page, "12-backoffice-refused");
    await page.goto(`${ORIGIN}/odoo`);
    expect(new URL(page.url()).pathname).toBe("/app/");
  });

});
