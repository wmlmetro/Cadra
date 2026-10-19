import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { request as pwRequest } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { personaToken } from "../fixtures/gates";

/**
 * Handoff 65 — the link, in the browser, as the two people whose job it is,
 * each signed in through the real sign-in page:
 *
 *   setup            two register assets with old tags `FIRS/<office>/0001`
 *                    and `…/0002` that exist nowhere else (`api.createAsset`
 *                    walks them through the gates when the switch is on), and
 *                    an INVENTED SAP export carrying a record for each, imported
 *                    over the API as the administrator persona with
 *                    `mark_absent=true` (handoff 65 §3: a three-record file
 *                    would otherwise be held by the 5% guard).
 *   Register Maker   ONE session: the sidebar's *Link to SAP* → filter by the
 *                    office → select both → *Propose selected* → the preview
 *                    (a dry run) says 2 would be proposed → *Propose 2* → the
 *                    answer says 2 of 2 proposed.
 *   Register Checker *Waiting on the checker* → select both → *Approve
 *                    selected* → 2 of 2 approved → opens one asset and reads
 *                    its SAP number and "Linked from SAP's export by two
 *                    people".
 *   the server       both assets carry SAP's number with
 *                    `code_source = linked_from_sap_mirror`.
 *   Register Maker   back in her session, proposes undoing one link from the
 *                    asset page, with a reason; the server holds a proposed
 *                    `unlink` and the asset keeps its number until a checker
 *                    decides.
 *
 * The export is invented by the one generator the Python suites use
 * (`myservice_asset_register/tests/sap_export_shapes.py`), as spec 63 does.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19f.localhost:8069 npx playwright test tests/65-the-link.spec.ts)
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

/** An invented export: one record per old tag, SAP class 3000. */
function inventedExport(u: string, office: string): { file: string; numbers: string[] } {
  const numbers = [`3K${u}001`, `3K${u}002`];
  const script = `
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1])
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
office, n1, n2 = sys.argv[3], sys.argv[4], sys.argv[5]
rows = [s.record(n1, cls="3000", tag="FIRS/%s/0001" % office, description="LAPTOP"),
        s.record(n2, cls="3000", tag="FIRS/%s/0002" % office, description="DESKTOP")]
open(sys.argv[2], "wb").write(s.build_xlsx(rows))
`;
  const dir = mkdtempSync(path.join(tmpdir(), "e2e65-"));
  const file = path.join(dir, "invented-export.xlsx");
  writeFileSync(path.join(dir, "make.py"), script);
  execFileSync("python3", ["-I", path.join(dir, "make.py"),
    path.join(REPO, "myservice_asset_register/tests/sap_export_shapes.py"), file, office, ...numbers]);
  return { file, numbers };
}

/** Upload as the administrator persona with "Yes, mark them absent", wait
 *  out a run somebody else left reading, and read the run to its end. */
async function importExport(file: string): Promise<any> {
  const token = await personaToken("administrator");
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN });
  const deadline = Date.now() + 200_000;
  try {
    let res;
    for (;;) {
      res = await ctx.post("/api/v1/sap-assets/imports", {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        multipart: {
          file: { name: "invented-export.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: readFileSync(file) },
          mark_absent: "true",
        },
      });
      if (res.status() !== 409 || Date.now() > deadline) break;
      await new Promise((r) => setTimeout(r, 3000));
    }
    expect(res.status(), await res.text()).toBe(202);
    const id = (await res.json()).data.id;
    while (Date.now() < deadline) {
      const run = (await (await ctx.get(`/api/v1/sap-assets/imports/${id}`, {
        headers: { Authorization: `Bearer ${token}` } })).json()).data;
      if (["done", "failed", "held"].includes(run.state)) return run;
      await new Promise((r) => setTimeout(r, 2000));
    }
    throw new Error(`import ${id} did not finish`);
  } finally {
    await ctx.dispose();
  }
}

test.describe("handoff 65 — the link", () => {
  test.setTimeout(300_000);
  test.use({ storageState: { cookies: [], origins: [] } });

  test("a maker proposes two confident matches and a checker approves them", async ({ page, browser, api }) => {
    const u = Math.random().toString(36).slice(2, 8).toUpperCase();
    const office = `K${u}`;
    const tags = [`FIRS/${office}/0001`, `FIRS/${office}/0002`];
    const assets = [];
    for (const [i, tag] of tags.entries()) {
      assets.push(await api.createAsset(`e2e65 link ${u} ${i + 1}`, { legacy_asset_code: tag }));
    }
    const ids: number[] = assets.map((a) => Number(a.id));
    const { file, numbers } = inventedExport(u, office);
    const run = await importExport(file);
    expect(run.state, JSON.stringify(run).slice(0, 400)).toBe("done");
    expect(run.created).toBe(2);
    expect(run.absent_guard.confirmed).toBe(true);

    // ── the Register Maker, one session ──
    await signIn(page, "register_maker");
    await page.getByRole("navigation", { name: "Primary navigation" }).getByText("Link to SAP", { exact: true }).click();
    await expect(page.getByTestId("sap-links-tab-confident")).toHaveAttribute("aria-selected", "true");
    await page.getByTestId("sap-links-office").selectOption(office);
    await expect(page.getByTestId("sap-links-sentence")).toContainText("2 register assets");
    for (const id of ids) {
      const row = page.getByTestId(`sap-candidate-row-${id}`);
      await expect(row).toContainText("old tag, unique");
      await row.getByTestId(`select-candidate-${id}`).check();
    }
    await expect(page.getByTestId("button-propose-selected")).toHaveText("Propose selected (2)");
    await page.getByTestId("button-propose-selected").click();
    const dialog = page.getByTestId("propose-dialog");
    await expect(dialog).toHaveAttribute("data-phase", "preview");
    await expect(dialog.getByTestId("propose-summary")).toContainText("2 of 2 would be proposed");
    for (const id of ids) {
      await expect(dialog.getByTestId(`propose-line-${id}`)).toHaveAttribute("data-outcome", "would_do");
    }
    await dialog.getByTestId("button-propose-send").click();
    await expect(dialog).toHaveAttribute("data-phase", "sent");
    await expect(dialog.getByTestId("propose-summary")).toContainText("2 of 2 proposed");
    await dialog.getByTestId("button-propose-close").click();
    // The list now says so: both rows have left "not yet proposed".
    await expect(page.getByTestId(`sap-candidate-row-${ids[0]}`)).toHaveCount(0);
    // The maker may not decide what they proposed: the checker's tab offers
    // them no control on these rows.
    await page.getByTestId("sap-links-tab-checker").click();
    const makersRow = page.locator(`[data-testid^='sap-link-row-'][data-asset-id='${ids[0]}']`);
    await expect(makersRow).toBeVisible();
    await expect(makersRow.locator("[data-testid^='button-approve-link-']")).toHaveCount(0);

    // ── the Register Checker ──
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const checker = await ctx.newPage();
    try {
      await signIn(checker, "register_checker");
      await checker.getByRole("navigation", { name: "Primary navigation" }).getByText("Link to SAP", { exact: true }).click();
      await checker.getByTestId("sap-links-tab-checker").click();
      for (const id of ids) {
        const row = checker.locator(`[data-testid^='sap-link-row-'][data-asset-id='${id}']`);
        await expect(row).toBeVisible();
        await row.locator("[data-testid^='select-link-']").check();
      }
      await checker.getByTestId("button-approve-selected").click();
      const decide = checker.getByTestId("decide-dialog");
      await expect(decide).toContainText("Approve 2 proposals");
      await decide.getByTestId("button-decide-send").click();
      await expect(checker.getByTestId("sap-link-results-summary")).toContainText("2 of 2 approved");
      await checker.getByTestId("button-close-sap-link-results").click();
      await expect(checker.locator(`[data-testid^='sap-link-row-'][data-asset-id='${ids[0]}']`)).toHaveCount(0);

      // The asset page, same session: its SAP number and where it came from.
      await checker.goto(appPath(`/assets/${ids[0]}`));
      await expect(checker.getByTestId("asset-sap-number")).toContainText(numbers[0]);
      await expect(checker.getByTestId("asset-sap-code-source")).toHaveText("Linked from SAP's export by two people");
    } finally {
      await ctx.close();
    }

    // ── the server ──
    for (const [i, id] of ids.entries()) {
      const a = await api.get<any>(`/api/v1/assets/${id}`);
      expect(a.sap.code_source).toBe("linked_from_sap_mirror");
      expect(a.sap.asset_number).toBe(numbers[i]);
    }

    // ── an undo is proposed the same way: the maker, back in her session,
    //    opens the second asset and proposes undoing its link with a reason.
    //    Nothing changes on the asset until a checker approves it.
    await page.goto(appPath(`/assets/${ids[1]}`));
    await expect(page.getByTestId("asset-sap-code-source")).toHaveText("Linked from SAP's export by two people");
    await page.getByTestId("button-sap-link-undo").click();
    await expect(page.getByTestId("button-sap-link-undo-send")).toBeDisabled();
    await page.getByTestId("input-sap-link-undo-reason").fill("e2e 65: the old tag was misread at intake.");
    await page.getByTestId("button-sap-link-undo-send").click();
    await expect(page.getByTestId("sap-link-undo-done")).toBeVisible();
    const undo = await api.get<any[]>(`/api/v1/sap-links`, { state: "proposed", asset_id: ids[1] });
    expect(undo.map((l) => l.kind)).toEqual(["unlink"]);
    expect((await api.get<any>(`/api/v1/assets/${ids[1]}`)).sap.asset_number).toBe(numbers[1]);
  });
});
