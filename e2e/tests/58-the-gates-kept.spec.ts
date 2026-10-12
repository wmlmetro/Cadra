import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName } from "../fixtures/marker";

/**
 * Handoff 58 §8.5, on the Users page — rule 2 of Addendum A §4: some roles
 * may not be held by one person, and the table that says so is enforced
 * where a role is GRANTED.
 *
 * Signed in as the administrator persona, through the real sign-in page,
 * one browser session:
 *
 *   1. A fixture person (created over the API, marked, holding Register
 *      Maker) is given Register Checker on the Users page's *Change roles*.
 *      Preview — a dry run of the real route — is refused, and the panel
 *      shows the server's sentence verbatim, naming both roles; Apply stays
 *      dark and nothing is written.
 *   2. On Settings → Role exclusions that exclusion is switched OFF; the
 *      same grant then previews and applies, and the configuration-changes
 *      report shows the row `cadra.role_exclusion.<id>` reading `off; …`.
 *   3. It is switched back ON. Nothing is revoked: the person now holding
 *      the pair is listed under *Conflicting grants*.
 *
 * Everything is put back in `finally`: the exclusion to the state it was
 * found in, the person's roles removed and the person deactivated.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test 58-)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);

type Persona = { key: string; login: string; password: string };

function persona(key: string): Persona | null {
  if (!existsSync(CREDS)) return null;
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key && login && password) return { key: k, login, password };
  }
  return null;
}

async function signIn(page: Page, p: Persona) {
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

let shotSeq = 0;
async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  mkdirSync(dir, { recursive: true });
  const n = String(++shotSeq).padStart(2, "0");
  await page.screenshot({ path: `${dir}/${TENANT}-58-${n}-${name}.png`, fullPage: true });
}

/** Today as the register counts days — Lagos. */
const lagosToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Lagos" }).format(new Date());

type Exclusion = { id: number; role_a: { key: string; name: string }; role_b: { key: string; name: string }; active: boolean; reason: string };

const A = "register_maker";
const B = "register_checker";

test.describe("58 — a forbidden pair, refused on the Users page", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("refused at preview naming both roles; switched off, granted, on the configuration record; switched on, a conflicting grant", async ({ page, api }) => {
    const administrator = persona("administrator");
    test.skip(!administrator, `no administrator persona in ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);

    const all = await api.get<Exclusion[]>("/api/v1/settings/role-exclusions");
    const ex = (all ?? []).find((e) => new Set([e.role_a.key, e.role_b.key]).size === 2
      && [e.role_a.key, e.role_b.key].includes(A) && [e.role_a.key, e.role_b.key].includes(B));
    expect(ex, `the seeded exclusion ${A} × ${B} (Addendum A §4) is on ${TENANT}`).toBeTruthy();
    const exId = ex!.id;
    const wasActive = ex!.active;
    const names = [ex!.role_a.name, ex!.role_b.name];

    // A person of our own: marked, holding Register Maker, no letter sent.
    const email = `e2e-58-${Date.now()}-${Math.floor(Math.random() * 1e4)}@demo.example`;
    const created = await api.raw("POST", "/api/v1/users", {
      name: markedName("spec58 pair"), email, roles: [A], send_invitation: false,
    });
    expect(created.status, JSON.stringify(created.body).slice(0, 300)).toBe(201);
    const personId = created.body.data.id as number;

    try {
      // The rule must be in force for step 1, whatever a failed run left.
      if (!wasActive) await api.patch(`/api/v1/settings/role-exclusions/${exId}`, { active: true });

      await signIn(page, administrator!);

      // ── 1 · Refused at preview, the server's sentence verbatim ──────────
      await page.goto(appPath(`/admin/users/${personId}`));
      const panel = page.getByTestId("user-detail");
      await expect(panel).toBeVisible({ timeout: 20_000 });
      const section = panel.getByTestId("user-section-change-roles");
      await expect(section.locator(`[data-testid="role-checkbox"][data-role="${A}"]`)).toBeChecked();
      const boxB = section.locator(`[data-testid="role-checkbox"][data-role="${B}"]`);
      await expect(boxB).not.toBeChecked();
      await boxB.check();
      const dry = page.waitForResponse((r) => r.url().includes(`/api/v1/users/${personId}/roles`) && r.request().method() === "POST");
      await section.getByTestId("button-preview-roles").click();
      const refusedRes = await dry;
      const refused = await refusedRes.json().catch(() => null);
      expect(refusedRes.status(), JSON.stringify(refused).slice(0, 300)).toBe(403);
      expect(refusedRes.request().postDataJSON()?.dry_run, "the refusal came from the PREVIEW").toBe(true);
      const sentence: string = refused?.error?.message ?? "";
      for (const n of names) expect(sentence, `the refusal names ${n}`).toContain(n);
      expect(sentence).toContain("cannot be held by one person");
      const refusal = section.getByTestId("roles-refusal");
      await expect(refusal).toBeVisible({ timeout: 20_000 });
      await expect(refusal).toContainText(sentence);
      await expect(section.getByTestId("button-apply-roles")).toBeDisabled();
      await shot(page, "pair-refused");
      const untouched = await api.get<any>(`/api/v1/users/${personId}`);
      expect(untouched.roles_direct.map((r: any) => r.key), "a refused preview writes nothing").not.toContain(B);

      // ── 2 · Switched off on Settings → Role exclusions ─────────────────
      await page.goto(appPath("/settings/role-exclusions"));
      await expect(page.getByTestId("role-exclusions")).toBeVisible({ timeout: 20_000 });
      const row = page.getByTestId(`exclusion-row-${exId}`);
      await expect(row).toHaveAttribute("data-active", "true");
      const off = page.waitForResponse((r) => r.url().includes(`/role-exclusions/${exId}`) && r.request().method() === "PATCH");
      await page.getByTestId(`exclusion-toggle-${exId}`).click();
      expect((await off).status()).toBe(200);
      await expect(row).toHaveAttribute("data-active", "false", { timeout: 20_000 });
      await shot(page, "exclusion-off");

      // The same grant now goes through: preview, then apply.
      await page.goto(appPath(`/admin/users/${personId}`));
      await expect(panel).toBeVisible({ timeout: 20_000 });
      await boxB.check();
      await section.getByTestId("button-preview-roles").click();
      const preview = section.getByTestId("roles-preview");
      await expect(preview).toBeVisible({ timeout: 20_000 });
      await expect(preview.getByTestId("roles-preview-grant")).toHaveAttribute("data-keys", B);
      await expect(section.getByTestId("roles-refusal")).toHaveCount(0);
      await section.getByTestId("button-apply-roles").click();
      await expect(section.getByTestId("roles-applied")).toHaveAttribute("data-granted", B, { timeout: 20_000 });
      await shot(page, "pair-granted-while-off");
      const both = await api.get<any>(`/api/v1/users/${personId}`);
      expect(both.roles_direct.map((r: any) => r.key)).toEqual(expect.arrayContaining([A, B]));

      // The configuration record says it was switched off.
      const today = lagosToday();
      const report = await api.get<any>("/api/v1/reports/configuration-changes", { from: today, to: today, limit: 500 });
      const param = (report?.parameters ?? []).find((p: any) => p.key === `cadra.role_exclusion.${exId}`);
      expect(param, `cadra.role_exclusion.${exId} is in the configuration-changes report for ${today}`).toBeTruthy();
      expect(param.current_value).toMatch(/^off; /);
      for (const n of names) expect(param.current_value).toContain(n);
      test.info().annotations.push({ type: "configuration-record", description: JSON.stringify(param) });

      // ── 3 · Switched back on: nothing revoked, a conflicting grant ─────
      await page.goto(appPath("/settings/role-exclusions"));
      await expect(row).toHaveAttribute("data-active", "false", { timeout: 20_000 });
      const on = page.waitForResponse((r) => r.url().includes(`/role-exclusions/${exId}`) && r.request().method() === "PATCH");
      await page.getByTestId(`exclusion-toggle-${exId}`).click();
      expect((await on).status()).toBe(200);
      await expect(row).toHaveAttribute("data-active", "true", { timeout: 20_000 });
      const conflicts = page.getByTestId("conflicting-grants");
      await expect(conflicts).toBeVisible({ timeout: 20_000 });
      const mine = page.getByTestId(`conflict-row-${personId}`);
      await expect(mine).toBeVisible({ timeout: 20_000 });
      await expect(mine.locator(`[data-testid="conflict-pair"][data-exclusion="${exId}"]`)).toBeVisible();
      await shot(page, "conflicting-grant");
      const still = await api.get<any>(`/api/v1/users/${personId}`);
      expect(still.roles_direct.map((r: any) => r.key), "switching an exclusion on revokes nothing")
        .toEqual(expect.arrayContaining([A, B]));
    } finally {
      // Put everything back, whatever happened above.
      const now = (await api.get<Exclusion[]>("/api/v1/settings/role-exclusions").catch(() => []))
        .find((e) => e.id === exId);
      if (now && now.active !== wasActive) {
        await api.patch(`/api/v1/settings/role-exclusions/${exId}`, { active: wasActive }).catch(() => undefined);
      }
      await api.raw("POST", `/api/v1/users/${personId}/roles`, { roles: [] }).catch(() => undefined);
      await api.raw("POST", `/api/v1/users/${personId}/deactivate`, {}).catch(() => undefined);
    }
  });
});
