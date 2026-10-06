import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";

/**
 * Handoff 56 — the name and the hat.
 *
 * The top bar names the role the signed-in person holds, under their name,
 * from `whoami.roles` — the server's own list, never derived from scopes.
 * Proved by signing in as EVERY demo persona through the real sign-in page
 * and reading the drawn line against what the API answers that persona:
 *
 *   - one role: its name; two: both, middle-dotted; three or more: the
 *     first two and +N, the full list in the line's tooltip (there is no
 *     account menu — the bar has deliberately had none since handoff 29);
 *   - no roles: NO line at all — a blank is honest, an invented label is
 *     not. (No persona has zero roles, so that leg is the HTTP suite's:
 *     `tests/test_whoami_roles.py` signs in an account created with none.)
 *
 * One screenshot of the top bar per persona (E2E_SHOTS), so the role text
 * can be read off the image — the handoff's own acceptance check.
 *
 * Skips unless `docs/api/.personas.<tenant>` exists — the passwords live
 * there and nowhere else.
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = `../docs/api/.personas.${TENANT}`;

type Persona = { key: string; login: string; password: string };
function personas(): Persona[] {
  if (!existsSync(CREDS)) return [];
  return readFileSync(CREDS, "utf8").split("\n")
    .filter((l) => l.trim() && !l.startsWith("#"))
    .map((l) => { const [key, login, password] = l.trim().split(/\s+/); return { key, login, password }; });
}

/** The Topbar's own folding rule, restated so a drift FAILS here. */
function foldedRoleText(names: string[]): string {
  if (names.length === 0) return "";
  if (names.length <= 2) return names.join(" · ");
  return `${names[0]} · ${names[1]} +${names.length - 2}`;
}

async function shotTopbar(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  mkdirSync(dir, { recursive: true });
  await page.locator("header").first()
    .screenshot({ path: `${dir}/${TENANT}-${name}.png` });
}

test.describe("56 — the name and the hat", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  const all = personas();
  test("the personas file exists for this tenant", () => {
    test.skip(all.length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    expect(all.length).toBeGreaterThanOrEqual(3);
  });

  for (const persona of all) {
    test(`${persona.key}: the top bar names the hat`, async ({ page, request }) => {
      test.setTimeout(120_000);

      // What the server says this persona holds — the expectation is the
      // API's own answer, not a copy of the seed's role table.
      const login = await request.post(`${ORIGIN}/api/v1/auth/login`, {
        data: { login: persona.login, password: persona.password },
      });
      expect(login.ok(), `${persona.key} cannot sign in over the API`).toBeTruthy();
      const token = (await login.json()).data.access_token as string;
      const who = await request.get(`${ORIGIN}/api/v1/auth/whoami`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(who.ok()).toBeTruthy();
      const roles = ((await who.json()).data.roles ?? []) as { key: string; name: string }[];
      expect(roles.length, `${persona.key} holds no role at all — the seed grants every persona one`)
        .toBeGreaterThan(0);

      await page.goto(appPath("/"));
      await page.locator('input[autocomplete="username"]').fill(persona.login);
      await page.locator('input[autocomplete="current-password"]').fill(persona.password);
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });

      const line = page.getByTestId("topbar-role");
      await expect(line).toHaveText(foldedRoleText(roles.map((r) => r.name)));
      if (roles.length > 2) {
        // The +N line's tooltip carries every role, since there is no menu.
        await expect(line).toHaveAttribute("title", roles.map((r) => r.name).join(" · "));
      }
      // The name is still there, above the hat.
      await expect(page.getByTestId("topbar-user")).toContainText(
        (await who.json()).data.name ?? persona.login);

      await shotTopbar(page, `56-${persona.key}-topbar`);
    });
  }
});
