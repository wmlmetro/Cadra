import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";

/**
 * Handoff 68 — a second provider, on the screen a person uses.
 *
 * Signed in as the Systems Administrator persona, in ONE session:
 * Settings → Identify from photo lists Anthropic and OpenAI by name (and
 * the test stand-in, on a test database), says for EACH whether the server
 * holds its key — never the key — and switching the provider to OpenAI
 * shows OpenAI's own model and default. A reload still says OpenAI (the
 * server's row, read back over the API too); switching back shows
 * Anthropic's model exactly as it was. The switch stays OFF throughout:
 * nothing is identified, nothing leaves the machine.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/68-a-second-provider.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);
const AI = "/api/v1/settings/ai-identify";

function persona(key: string) {
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

test.describe.serial("68 — a second provider", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.setTimeout(120_000);
  let was: any = null;

  test.beforeAll(async ({ api }) => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    was = await api.get(AI);
    test.skip(was.enabled, "identification is switched on on this tenant; this spec switches providers only while it is off");
    if (was.provider !== "anthropic") {
      const r = await api.raw("PATCH", AI, { provider: "anthropic" });
      expect(r.status, JSON.stringify(r.body)).toBe(200);
    }
  });

  test.afterAll(async ({ api }) => {
    if (was) await api.raw("PATCH", AI, { provider: was.provider });
  });

  test("both providers by name, each key said, the model follows the provider", async ({ page, api }) => {
    await signIn(page, "administrator");
    await page.goto(appPath("/settings/ai-identify"));
    const select = page.getByTestId("ai-settings-provider");
    await expect(select).toBeVisible({ timeout: 20_000 });

    // The list, by name: the stand-in only because this is a test database.
    const options = await select.locator("option").allTextContents();
    expect(options).toEqual(["Anthropic (Claude)", "OpenAI (GPT)", "Cadra's test stand-in (nothing leaves the server)"]);

    // One line per provider that needs a key, each saying present/absent.
    const server = await api.get(AI);
    for (const p of ["anthropic", "openai"]) {
      const line = page.getByTestId(`ai-settings-key-${p}`);
      await expect(line).toBeVisible();
      await expect(line).toHaveAttribute("data-placed", server.keys[p].placed ? "true" : "false");
      await expect(line).toContainText(server.keys[p].placed ? "key present" : "key absent");
      await expect(line).toContainText(server.keys[p].variable);
    }
    const anthropicModel = server.model;
    await expect(page.getByTestId("ai-settings-model")).toHaveValue(anthropicModel);

    // Switch to OpenAI: the model field shows OpenAI's, and its default.
    await select.selectOption("openai");
    await expect(page.getByTestId("ai-settings-note")).toHaveText("Saved.");
    const openaiModel = server.provider_options.find((o: any) => o.value === "openai").model;
    await expect(page.getByTestId("ai-settings-model")).toHaveValue(openaiModel);
    await expect(page.getByTestId("ai-settings-default-model")).toContainText("OpenAI (GPT)'s default: gpt-6.1-sol");
    await expect(page.getByTestId("ai-settings-key")).toContainText("OpenAI (GPT)");

    // The server's row says so, and a reload reads it back.
    expect((await api.get(AI)).provider).toBe("openai");
    await page.reload();
    await expect(page.getByTestId("ai-settings-provider")).toHaveValue("openai", { timeout: 20_000 });
    await expect(page.getByTestId("ai-settings-model")).toHaveValue(openaiModel);

    // Back to Anthropic: its model exactly as it was.
    await page.getByTestId("ai-settings-provider").selectOption("anthropic");
    await expect(page.getByTestId("ai-settings-note")).toHaveText("Saved.");
    await expect(page.getByTestId("ai-settings-model")).toHaveValue(anthropicModel);
    const after = await api.get(AI);
    expect([after.provider, after.model, after.enabled]).toEqual(["anthropic", anthropicModel, false]);
  });
});
