import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";

/**
 * Handoff 63 — the SAP mirror in the browser, as the people whose job it is,
 * each signed in through the real sign-in page.
 *
 *   administrator  Settings → SAP asset master → choose an export → Import →
 *                  the run is read in the background and the card ends
 *                  `done` with the counts → Reports → SAP coverage, in the
 *                  SAME session, says what Cadra holds. The run is read from
 *                  the server after the act.
 *   asset manager  the same Settings page says importing is the system
 *                  administrator's act and offers no upload, though the
 *                  account holds `settings:write`.
 *   store officer  the coverage report is refused in words.
 *
 * The export is INVENTED in SAP's shapes by the one generator the Python
 * suites use (`myservice_asset_register/tests/sap_export_shapes.py`), run
 * here with the system `python3`; no row of NRS's export is in the repo.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test tests/63-what-sap-holds.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const REPO = path.resolve(__dirname, "../..");
const CREDS = process.env.E2E_PERSONAS ?? path.join(REPO, `docs/api/.personas.${TENANT}`);

type Persona = { key: string; login: string; password: string };
function persona(key: string): Persona {
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key) return { key: k, login, password };
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

async function apiToken(key: string): Promise<string> {
  const p = persona(key);
  const r = await fetch(`${ORIGIN}/api/v1/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login: p.login, password: p.password }),
  });
  return (await r.json()).data.access_token;
}

/** An invented export: three records of one invented office, one refused. */
function inventedExport(): { file: string; office: string } {
  const u = Math.random().toString(36).slice(2, 8).toUpperCase();
  const office = `E${u}`;
  const script = `
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1])
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
u, office = sys.argv[3], sys.argv[4]
rows = [s.record("2E%s001" % u, tag="FIRS/%s/0001" % office),
        s.record("2E%s002" % u, tag="FIRS/%s/0002" % office, serial="XXXX"),
        s.record("2E%s003" % u, tag="FIRS/%s/0002" % office),
        s.record("", description="NO NUMBER")]
open(sys.argv[2], "wb").write(s.build_xlsx(rows))
`;
  const dir = mkdtempSync(path.join(tmpdir(), "e2e63-"));
  const file = path.join(dir, "invented-export.xlsx");
  writeFileSync(path.join(dir, "make.py"), script);
  execFileSync("python3", ["-I", path.join(dir, "make.py"),
    path.join(REPO, "myservice_asset_register/tests/sap_export_shapes.py"), file, u, office]);
  return { file, office };
}

test.describe("handoff 63 — what SAP holds, in Cadra", () => {
  test.setTimeout(240_000);

  test("the administrator imports an export and reads the coverage in the same session", async ({ page }) => {
    const { file, office } = inventedExport();
    await signIn(page, "administrator");
    await page.goto(appPath("/settings/sap-asset-master"));
    await expect(page.getByRole("heading", { name: /SAP asset master/ })).toBeVisible();
    // One import runs at a time: wait out a run somebody else left reading.
    await expect(page.getByTestId("sap-import-run").filter({ has: page.locator("[data-state='running'], [data-state='queued']") }))
      .toHaveCount(0, { timeout: 120_000 });
    await page.getByTestId("sap-import-file").setInputFiles(file);
    await page.getByTestId("sap-import-submit").click();
    await expect(page.getByTestId("sap-import-queued")).toBeVisible();
    const card = page.getByTestId("sap-import-run").first();
    await expect(card).toHaveAttribute("data-state", "done", { timeout: 180_000 });
    await expect(card.getByTestId("run-rows-read")).toHaveText("4");
    await expect(card.getByTestId("run-created")).toHaveText("3");
    await expect(card.getByTestId("run-refused")).toHaveText("1");
    await expect(card).toContainText("no asset number");
    await expect(card).toContainText("The uploaded file was not kept.");

    // The row, from the server: the newest run is this one, done, no file.
    const token = await apiToken("administrator");
    const runs = await (await fetch(`${ORIGIN}/api/v1/sap-assets/imports?limit=1`, {
      headers: { Authorization: `Bearer ${token}` } })).json();
    expect(runs.data[0].state).toBe("done");
    expect(runs.data[0].created).toBe(3);
    expect(runs.data[0].file_kept).toBe(false);
    const slice = await (await fetch(`${ORIGIN}/api/v1/sap-assets?office=${office}`, {
      headers: { Authorization: `Bearer ${token}` } })).json();
    expect(slice.pagination.total_estimate).toBe(3);

    // Same session: the sidebar's Reports → SAP Coverage.
    await page.getByRole("link", { name: "SAP Coverage" }).click();
    await expect(page.getByTestId("sap-coverage-sentence")).toContainText("Cadra holds");
    await expect(page.getByTestId("cov-by-class")).toContainText("2000");
    await page.getByPlaceholder("Office code").fill(office);
    await expect(page.getByTestId("cov-by-office")).toContainText(office);
    await expect(page.getByTestId("cov-definitions")).toContainText("sap_active");
  });

  test("the asset manager holds settings:write and is not offered the import", async ({ page }) => {
    await signIn(page, "asset_manager");
    await expect(page.getByRole("link", { name: "SAP asset master" })).toHaveCount(0);
    await page.goto(appPath("/settings/sap-asset-master"));
    await expect(page.getByTestId("sap-import-not-allowed")).toContainText("system administrator's act");
    await expect(page.getByTestId("sap-import-file")).toHaveCount(0);
  });

  test("the store officer is refused the coverage report in words", async ({ page }) => {
    await signIn(page, "storekeeper");
    await expect(page.getByRole("link", { name: "SAP Coverage" })).toHaveCount(0);
    await page.goto(appPath("/reports/sap-coverage"));
    await expect(page.getByText(/sap_mirror:read/)).toBeVisible();
  });
});
