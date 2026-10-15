import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Locator, Response } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";
import { asPersona, ensureSapClass, receiptBody } from "../fixtures/gates";

/**
 * Handoff 60 — seventy a day. ONE receipt (GRN) of 20 units walked through
 * the seven gates by the seven demo personas, every batch the handoff built
 * driven in the browser by the person whose job it is, each signed in
 * through the real sign-in page in one session, and every act read back from
 * the server afterwards:
 *
 *   store        Waiting on me → GRN → select all → Submit selected → 20 fired
 *                (the batch since handoff 61, ruling 5 on report 60)
 *   IAD officer  Waiting on me → GRN in the search box → one click on the GRN
 *                selects the receipt → Verify selected → all four + one file
 *                → 20 fired; the server holds ONE attachment linked from all 20
 *   IAD approver opens what IAD saw from the row and from the asset page;
 *                Back returns to Candidates; select all → Approve → 20 fired
 *   controller   Waiting on me → GRN → select all → Request tagging for
 *                selected → 20 fired, each label under its own code (61)
 *   tagger       Labels to fix lists the receipt; the Tagging tab hides the
 *                code; ONE unit confirmed at the station (scan box empty and
 *                focused afterwards); 19 more over the API
 *   maker        pastes 20 lines, line 20 a duplicate of line 19's SAP code →
 *                preview writes nothing; submit → 19 fired, line 20 refused
 *   checker      sees SAP code, cost, cost centre and class on each row;
 *                select all → Approve → 19 on the register
 *
 * At every step the per-person count (`waiting_on_me`, the sidebar badge's
 * own source) is read for ALL seven people and must move by exactly the
 * units that entered or left their queue — deltas, because other units sit
 * on `test19`. Each browser persona's badge is read before and after their
 * step and must equal the server's count at that moment.
 *
 * Every browser action a person takes for the 20 is counted (clicks,
 * keystrokes, pastes, file picks, scans) and printed as a table at the end.
 * Sign-in is not counted; assertion-only navigation is not counted.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test tests/60-seventy-a-day.spec.ts)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = process.env.E2E_PERSONAS ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);
const CLICKS_OUT = process.env.E2E_CLICKS_OUT
  ?? "/private/tmp/claude-502/-Users-macbookprom1-Desktop-WML-myservicenrs/b11d804c-7035-4917-ab23-11e276c97213/scratchpad/clicks-60.json";

const N = 20;
const CREW = [
  "storekeeper", "iad_officer", "iad_approver", "asset_controller",
  "tagger", "register_maker", "register_checker",
] as const;
type Who = typeof CREW[number];

type Persona = { key: string; login: string; password: string };
function persona(key: string): Persona {
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [k, login, password] = l.trim().split(/\s+/);
    if (k === key) return { key: k, login, password };
  }
  throw new Error(`${CREDS} has no "${key}" persona`);
}

async function signIn(page: Page, key: Who) {
  const p = persona(key);
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

// ── what a person did ──────────────────────────────────────────────────────

type Tally = { clicks: number; keystrokes: number; pastes: number; filePicks: number; scans: number; units: number; how: string };
const TALLY: Record<string, Tally> = {};
const tally = (who: string) => (TALLY[who] ??= { clicks: 0, keystrokes: 0, pastes: 0, filePicks: 0, scans: 0, units: N, how: "browser" });

/** Every user action goes through here, so the table is what was DONE. */
const act = {
  click: async (who: string, loc: Locator) => { await loc.click(); tally(who).clicks++; },
  check: async (who: string, loc: Locator) => { await loc.check(); tally(who).clicks++; },
  /** Click into a field and type: one click, one keystroke per character. */
  type: async (who: string, loc: Locator, text: string) => {
    await loc.click(); tally(who).clicks++;
    await loc.fill(text); tally(who).keystrokes += text.length;
  },
  /** Click into a field and paste: one click, one paste. */
  paste: async (who: string, loc: Locator, text: string) => {
    await loc.click(); tally(who).clicks++;
    await loc.fill(text); tally(who).pastes++;
  },
  pick: async (who: string, loc: Locator, files: Parameters<Locator["setInputFiles"]>[0]) => {
    await loc.setInputFiles(files); tally(who).filePicks++;
  },
  /** A handheld scan: the value lands in the focused field, then Enter. */
  scan: async (who: string, loc: Locator, value: string) => {
    await loc.fill(value); await loc.press("Enter"); tally(who).scans++;
  },
};

// ── the counts ─────────────────────────────────────────────────────────────

/** The server's count of units waiting on an act this person may do — the
 *  badge's own query (`waiting_on_me=true&limit=1`). */
async function waitingOnMe(who: Who): Promise<number> {
  const r = await asPersona(who, "GET", "/candidates?waiting_on_me=true&limit=1");
  expect(r.status, `${who} waiting_on_me: ${JSON.stringify(r.body).slice(0, 200)}`).toBe(200);
  return Number(r.body?.pagination?.total_estimate);
}
type Snapshot = Record<Who, number>;
async function snapshot(): Promise<Snapshot> {
  const out = {} as Snapshot;
  for (const w of CREW) out[w] = await waitingOnMe(w);
  return out;
}
const SNAPS: { step: string; counts: Snapshot }[] = [];
const BADGES: { who: Who; when: string; badge: number; server: number }[] = [];

/** Take a snapshot after `step` and assert every person's count moved by
 *  exactly `moved` (absent = 0) since the previous one. */
async function stepTaken(step: string, moved: Partial<Record<Who, number>>) {
  const prev = SNAPS[SNAPS.length - 1];
  const now = await snapshot();
  SNAPS.push({ step, counts: now });
  for (const w of CREW) {
    expect(now[w] - prev.counts[w], `"${step}": ${w}'s count went ${prev.counts[w]} → ${now[w]}`)
      .toBe(moved[w] ?? 0);
  }
}

/** Reload and read the sidebar badge, from the same response the badge
 *  draws; it must equal the server's count read separately. 0 = no pill. */
async function readBadge(page: Page, who: Who, when: string): Promise<number> {
  const isBadge = (r: Response) => r.request().method() === "GET"
    && /\/api\/v1\/candidates\?/.test(r.url()) && /[?&]waiting_on_me=true(&|$)/.test(r.url())
    && /[?&]limit=1(&|$)/.test(r.url());
  const resP = page.waitForResponse(isBadge, { timeout: 30_000 });
  await page.reload();
  const res = await resP;
  expect(res.status()).toBe(200);
  const total = Number((await res.json())?.pagination?.total_estimate);
  const pill = page.getByTestId("nav-candidates-badge");
  if (total > 0) await expect(pill).toHaveAttribute("aria-label", `${total} waiting on you`);
  else await expect(pill).toHaveCount(0);
  const server = await waitingOnMe(who);
  expect(total, `${who}'s badge (${total}) is not the server's count (${server}) ${when}`).toBe(server);
  BADGES.push({ who, when, badge: total, server });
  return total;
}

// ── the receipt ────────────────────────────────────────────────────────────

const STAMP = String(Date.now()).slice(-8);
const GRN = `GRN60-${STAMP}`;
const SAP = (i: number) => `3${STAMP}${String(i + 1).padStart(2, "0")}`; // 11 digits
let ids: number[] = [];
let codes: string[] = [];
let category: { id: number; name: string; sap: string } | null = null;
let attachmentId = 0;
let gateWasOn: boolean | null = null;

const stateOf = async (id: number) => (await asPersona("register_checker", "GET", `/assets/${id}`)).body?.data;
async function states(): Promise<string[]> {
  const out: string[] = [];
  for (const id of ids) out.push((await stateOf(id))?.register_state);
  return out;
}

/** Candidates, reached the way a person does: the sidebar item. Lands on
 *  *Waiting on me*. Counted. */
async function openCandidates(page: Page, who: Who) {
  await act.click(who, page.getByTestId("nav-candidates"));
  await expect(page).toHaveURL(/\/app\/candidates/);
  await expect(page.getByTestId("filter-waiting-mine")).toHaveAttribute("aria-selected", "true");
}

/** The GRN typed into the top bar's search box, and the list answering it:
 *  the count line says it is matching the GRN and the rows are the receipt's.
 *  (No wait on a network response: a search repeated within the list's
 *  15-second staleTime is answered from the cache.) */
async function searchGrn(page: Page, who: Who, expectRows: number) {
  await act.type(who, page.getByTestId("input-global-search"), GRN);
  await expect(page.getByTestId("candidates-count")).toContainText(`matching “${GRN}”`, { timeout: 20_000 });
  await expect(page.locator('[data-testid^="candidate-row-"]')).toHaveCount(expectRows, { timeout: 20_000 });
}

test.describe.serial("60 — seventy a day: one GRN of 20, seven people", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.setTimeout(240_000);

  test.beforeAll(async ({ api }) => {
    test.skip(!existsSync(CREDS), `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    const s = await api.get<any>("/api/v1/settings");
    gateWasOn = s?.receipt_gated === true;
    if (!gateWasOn) {
      const r = await api.raw("PATCH", "/api/v1/settings/receipt-gate", { enabled: true });
      expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
    }
  });

  test.afterAll(async ({ api }) => {
    if (gateWasOn === false) await api.raw("PATCH", "/api/v1/settings/receipt-gate", { enabled: false });
    // The table, whatever happened above — a partial run still says what it measured.
    if (Object.keys(TALLY).length) {
      const rows = [...CREW.slice(0, 5), "tagger:affix", ...CREW.slice(5)].map((w) => {
        const t = TALLY[w];
        if (!t) return { persona: w, how: "API (no batch for this gate)" };
        const per = (n: number) => Math.round((n / t.units) * 100) / 100;
        return {
          persona: w, how: t.how, units_driven_in_browser: t.units,
          clicks: t.clicks, keystrokes: t.keystrokes, pastes: t.pastes, file_picks: t.filePicks, scans: t.scans,
          per_unit: { clicks: per(t.clicks), keystrokes: per(t.keystrokes), pastes: per(t.pastes), file_picks: per(t.filePicks), scans: per(t.scans) },
        };
      });
      console.log(`\nHandoff 60 — what each person did for one GRN of ${N} units (${GRN}, ${TENANT})`);
      console.table(rows.map((r: any) => ({
        persona: r.persona, how: r.how, clicks: r.clicks ?? "-", keystrokes: r.keystrokes ?? "-",
        pastes: r.pastes ?? "-", file_picks: r.file_picks ?? "-", scans: r.scans ?? "-",
        "per unit (c/k/p/f/s)": r.per_unit
          ? `${r.per_unit.clicks}/${r.per_unit.keystrokes}/${r.per_unit.pastes}/${r.per_unit.file_picks}/${r.per_unit.scans}` : "-",
      })));
      console.log("waiting_on_me per step:");
      console.table(SNAPS.map((s) => ({ step: s.step, ...s.counts })));
      console.log("badge in the browser:");
      console.table(BADGES);
      try {
        mkdirSync(path.dirname(CLICKS_OUT), { recursive: true });
        writeFileSync(CLICKS_OUT, JSON.stringify({ tenant: TENANT, grn: GRN, units: N, ids, codes, tally: rows, snapshots: SNAPS, badges: BADGES }, null, 2));
      } catch { /* the table is on stdout either way */ }
    }
  });

  test("setup: the storekeeper receives one GRN of 20 units", async ({ api }) => {
    // A serial class (Section 12) with a SAP class (handoff 59 §1).
    const cats: any[] = (await asPersona("asset_controller", "GET", "/asset-categories")).body?.data ?? [];
    const serial = cats.filter((r) => (r.identification_mode ?? "serial") === "serial" && !String(r.name).startsWith("e2e-59"));
    const one = serial.find((r) => Number(r.id) === 1) ?? serial[0];
    expect(one, "no serial class on this tenant").toBeTruthy();
    const sap = await ensureSapClass(one.id);
    category = { id: Number(one.id), name: one.name, sap };

    SNAPS.push({ step: "before", counts: await snapshot() });
    for (let i = 0; i < N; i++) {
      const name = markedName(`spec60 unit ${i + 1} of ${N}`);
      const body = await receiptBody(api, {
        name, category_id: category.id, serial_number: `SN60${STAMP}${String(i + 1).padStart(2, "0")}`,
        make: "Spec60 Make", model_name: "Spec60 Model",
        purchase_order_reference: `PO60-${STAMP}`, grn_reference: GRN, acquisition_cost: 1850,
      });
      const r = await asPersona("storekeeper", "POST", "/assets", body);
      expect([200, 201], JSON.stringify(r.body).slice(0, 300)).toContain(r.status);
      expect(r.body.data.register_state).toBe("captured");
      ids.push(r.body.data.id);
      codes.push(r.body.data.asset_code);
      recordCreated({ kind: "asset", id: r.body.data.id, name });
    }
    await stepTaken("received (20 captured)", { storekeeper: +N });
  });

  test("store: the badge counts the 20; Submit selected takes it down by 20", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "storekeeper";
    await signIn(page, who);
    const before = await readBadge(page, who, "before submitting");
    expect(before).toBeGreaterThanOrEqual(N);
    // The store gate's batch (handoff 61, ruling 5 on report 60): N single
    // fires on the server, one selection and one click here.
    await openCandidates(page, who);
    await searchGrn(page, who, N);
    await act.check(who, page.getByTestId("select-all-visible"));
    await expect(page.getByTestId("batch-selected-count")).toContainText(`${N} selected`);
    await act.click(who, page.getByTestId("button-batch-submit"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "submit");
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes("/api/v1/candidates/gates/submit"), { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-batch-submit"));
    const res = await posted;
    const body = await res.json();
    expect(res.status(), JSON.stringify(body).slice(0, 400)).toBe(200);
    expect(body.data.fired).toBe(N);
    const results = page.getByTestId("batch-results");
    await expect(results.getByTestId("batch-results-summary"))
      .toHaveText(`${N} of ${N} submitted to Internal Audit, 0 refused.`);
    await act.click(who, results.getByTestId("button-close-batch-results"));
    expect(await readBadge(page, who, "after submitting")).toBe(before - N);
    expect(new Set(await states())).toEqual(new Set(["vfm_pending"]));
    await stepTaken("store submitted 20", { storekeeper: -N, iad_officer: +N });
  });

  test("IAD officer: one receipt, one checklist, one file — Verify selected", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "iad_officer";
    await signIn(page, who);
    const before = await readBadge(page, who, "before verifying");
    await openCandidates(page, who);
    await searchGrn(page, who, N);

    // One click on the GRN selects every unit of the receipt.
    await act.click(who, page.getByTestId(`select-receipt-${ids[0]}`));
    await expect(page.getByTestId("batch-selected-count")).toContainText(`${N} selected`);
    await act.click(who, page.getByTestId("button-batch-verify"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "verify");
    await expect(dialog.getByTestId("batch-units").locator("li")).toHaveCount(N);
    await act.check(who, dialog.getByTestId("check-all-four"));
    for (const k of ["quantity", "specification", "condition", "price"]) {
      await expect(dialog.getByTestId(`check-${k}`)).toBeChecked();
    }
    await act.pick(who, dialog.getByTestId("input-evidence"), {
      name: `delivery-note-${GRN}.txt`, mimeType: "text/plain", buffer: Buffer.from(`Sighted ${N} units of ${GRN} against PO60-${STAMP}.`),
    });
    await expect(dialog.getByTestId("evidence-files")).toContainText(`delivery-note-${GRN}.txt`);
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes("/api/v1/candidates/gates/verify"), { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-batch-submit"));
    const res = await posted;
    const body = await res.json();
    expect(res.status(), JSON.stringify(body).slice(0, 400)).toBe(200);
    expect(body.data.fired).toBe(N);
    expect(body.data.refused).toBe(0);
    const results = page.getByTestId("batch-results");
    await expect(results.getByTestId("batch-results-summary")).toHaveText(`${N} of ${N} verified, 0 refused.`);
    await act.click(who, results.getByTestId("button-close-batch-results"));
    await expect(results).toBeHidden();
    expect(await readBadge(page, who, "after verifying")).toBe(before - N);

    // Read back: every unit verified, and ONE attachment behind all twenty.
    expect(new Set(await states())).toEqual(new Set(["vfm_verified"]));
    const att = new Set<number>();
    for (const id of ids) {
      const ev = await asPersona("iad_approver", "GET", `/assets/${id}/evidence`);
      expect(ev.status).toBe(200);
      const v = ev.body?.data?.verifications ?? [];
      expect(v.length, `unit ${id} has ${v.length} verifications`).toBe(1);
      expect(v[0].checklist).toMatchObject({ quantity: true, specification: true, condition: true, price: true });
      expect(v[0].files.length).toBe(1);
      att.add(Number(v[0].files[0].id));
    }
    expect([...att], "the 20 do not share one attachment").toHaveLength(1);
    attachmentId = [...att][0];
    expect(body.data.evidence?.attachment_ids ?? [attachmentId]).toEqual([attachmentId]);
    await stepTaken("IAD verified 20", { iad_officer: -N, iad_approver: +N });
  });

  test("IAD approver: sees the evidence from the row and the asset page, Back returns, approves 20", async ({ page }) => {
    test.skip(!attachmentId, "the verification did not land");
    const who: Who = "iad_approver";
    await signIn(page, who);
    const before = await readBadge(page, who, "before approving");
    await openCandidates(page, who);
    await searchGrn(page, who, N);

    // What IAD saw, from the row.
    await act.click(who, page.getByTestId(`button-row-evidence-${ids[0]}`));
    const ev = page.getByTestId("row-evidence-dialog");
    await expect(ev.getByTestId(`gate-evidence-file-${attachmentId}`)).toBeVisible();
    await expect(ev.locator('[data-check][data-ticked="true"]')).toHaveCount(4);
    await act.click(who, ev.getByRole("button", { name: "Close" }).last());
    await expect(ev).toBeHidden();

    // And from the asset page, then Back to the list.
    await act.click(who, page.getByTestId(`candidate-row-${ids[0]}`).getByRole("link", { name: codes[0] }));
    await expect(page).toHaveURL(new RegExp(`/app/assets/${ids[0]}\\?from=candidates`));
    const panel = page.getByTestId("gate-evidence");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId(`gate-evidence-file-${attachmentId}`)).toBeVisible();
    const back = page.getByTestId("button-back");
    await expect(back).toHaveText(/Back to Candidates/);
    await act.click(who, back);
    await expect(page).toHaveURL(/\/app\/candidates(\?|$)/);
    await expect(page.getByTestId("candidates-table")).toBeVisible();
    await expect(page.getByTestId("filter-waiting-mine")).toHaveAttribute("aria-selected", "true");

    // Back returns to the SAME list: the tab, and the GRN in both the top
    // bar's box and the list under it (handoff 60 §2d; the box once kept the
    // GRN over an unfiltered list).
    await expect(page).toHaveURL(new RegExp(`[?&]q=${encodeURIComponent(GRN)}(&|$)`));
    await expect(page.getByTestId("input-global-search")).toHaveValue(GRN);
    await expect(page.getByTestId("candidates-count")).toContainText(`matching “${GRN}”`);
    await expect(page.locator('[data-testid^="candidate-row-"]')).toHaveCount(N);
    for (const id of ids) await expect(page.getByTestId(`candidate-row-${id}`)).toBeVisible();

    await act.check(who, page.getByTestId("select-all-visible"));
    await expect(page.getByTestId("batch-selected-count")).toContainText(`${N} selected`);
    await act.click(who, page.getByTestId("button-batch-approve"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "approve");
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes("/api/v1/candidates/gates/approve") && !r.url().includes("registration"), { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-batch-submit"));
    const res = await posted;
    const body = await res.json();
    expect(res.status(), JSON.stringify(body).slice(0, 400)).toBe(200);
    expect(body.data.fired).toBe(N);
    const results = page.getByTestId("batch-results");
    await expect(results.getByTestId("batch-results-summary")).toHaveText(`${N} of ${N} approved, 0 refused.`);
    await act.click(who, results.getByTestId("button-close-batch-results"));
    expect(await readBadge(page, who, "after approving")).toBe(before - N);
    expect(new Set(await states())).toEqual(new Set(["vfm_approved"]));
    await stepTaken("IAD approved 20", { iad_approver: -N, asset_controller: +N });
  });

  test("Asset Controller: Request tagging for selected, the 20 at once", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "asset_controller";
    await signIn(page, who);
    const before = await readBadge(page, who, "before requesting tagging");
    // The controller's batch (handoff 61, ruling 5 on report 60). Still a
    // person's act: nothing requests a label on IAD's approval.
    await openCandidates(page, who);
    await searchGrn(page, who, N);
    await act.check(who, page.getByTestId("select-all-visible"));
    await expect(page.getByTestId("batch-selected-count")).toContainText(`${N} selected`);
    await act.click(who, page.getByTestId("button-batch-request-tagging"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "request-tagging");
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes("/api/v1/candidates/gates/request-tagging"), { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-batch-submit"));
    const res = await posted;
    const body = await res.json();
    expect(res.status(), JSON.stringify(body).slice(0, 400)).toBe(200);
    expect(body.data.fired).toBe(N);
    const results = page.getByTestId("batch-results");
    await expect(results.getByTestId("batch-results-summary"))
      .toHaveText(`${N} of ${N} given a label to print, 0 refused.`);
    await act.click(who, results.getByTestId("button-close-batch-results"));
    expect(await readBadge(page, who, "after requesting tagging")).toBe(before - N);
    expect(new Set(await states())).toEqual(new Set(["tag_issued"]));
    // A gated unit's label number IS its asset code.
    for (let i = 0; i < N; i++) expect((await stateOf(ids[i]))?.tagging?.tag_number).toBe(codes[i]);
    await stepTaken("controller requested tagging for 20", { asset_controller: -N, tagger: +N });
  });

  test("tagger: Labels to fix, the code hidden on the Tagging tab, one unit confirmed at the station", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "tagger";
    await signIn(page, who);
    const before = await readBadge(page, who, "before affixing");

    // The station. Labels to fix lists the OLDEST first, so a fresh delivery
    // behind a backlog is found by its GRN in the panel's own filter
    // (server-side `q`); then select all, and Print is ready.
    await page.goto(appPath("/tools/barcode"));
    const panel = page.getByTestId("labels-to-fix");
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("labels-to-fix-count")).not.toContainText("Counting");
    const unfiltered = (await page.getByTestId("labels-to-fix-count").innerText()).replace(/\s+/g, " ");
    const filtered = page.waitForResponse((r) => r.request().method() === "GET"
      && r.url().includes("/api/v1/candidates?") && r.url().includes("waiting_on=tagging")
      && r.url().includes(`q=${encodeURIComponent(GRN)}`), { timeout: 30_000 });
    await act.type(who, page.getByTestId("labels-to-fix-filter"), GRN);
    const fixRes = await (await filtered).json();
    expect(Number(fixRes.pagination?.total_estimate)).toBe(N);
    await expect(page.getByTestId("labels-to-fix-count")).toContainText(`matching “${GRN}”`);
    await expect(panel.locator('[data-testid^="labels-to-fix-row-"]')).toHaveCount(N);
    for (const id of ids) await expect(panel.getByTestId(`labels-to-fix-row-${id}`)).toBeVisible();
    for (const code of codes) await expect(panel).not.toContainText(code);
    console.log(`Labels to fix: unfiltered "${unfiltered}"; filtered by ${GRN}: ${N} of ${N} rows`);
    const print = page.getByTestId("button-print-labels-to-fix");
    await expect(print).toBeDisabled();
    await act.check(who, page.getByTestId("labels-to-fix-select-all"));
    await expect(page.getByTestId("labels-to-fix-count")).toContainText(`${N} selected`);
    await expect(print).toBeEnabled();
    await expect(print).toHaveText(`Print ${N} labels`);
    // Print itself is not clicked: it opens the browser's print path, and
    // selecting the receipt is what this measures. (Not counted.)

    // The Tagging tab on Candidates names the units and hides their codes
    // (assertion only — not counted as the tagger's work).
    await page.goto(appPath("/candidates"));
    await page.getByTestId("filter-waiting-tagging").click();
    await page.getByTestId("input-global-search").fill(GRN);
    await expect(page.locator('[data-testid^="candidate-row-"]')).toHaveCount(N, { timeout: 20_000 });
    await expect(page.getByTestId("unit-code-hidden")).toBeVisible();
    await expect(page.getByTestId("candidate-name-link")).toHaveCount(N);
    const table = page.getByTestId("candidates-table");
    for (const code of codes) await expect(table).not.toContainText(code);

    // One unit confirmed at the station, as the tagger does it: scan the
    // label into the box, Confirm affixed, scan the label in the dialog.
    await page.goto(appPath("/tools/barcode"));
    const AFFIX = "tagger:affix";
    const box = page.getByTestId("scan-box");
    await expect(box).toBeFocused();
    await act.scan(AFFIX, box, codes[0]);
    await expect(page.getByTestId("lookup-result")).toBeVisible({ timeout: 20_000 });
    await act.click(AFFIX, page.getByTestId("button-confirm-affixed"));
    const dialog = page.getByTestId("dialog-confirm-affixed");
    await expect(dialog).toBeVisible();
    const affixed = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes(`/api/v1/assets/${ids[0]}/tag-affixed`), { timeout: 30_000 });
    await act.scan(AFFIX, dialog.getByTestId("input-affix-tag-number"), codes[0]);
    const res = await affixed;
    expect(res.status(), await res.text()).toBe(200);
    await expect(dialog).toBeHidden();
    await expect(box).toHaveValue("");
    await expect(box).toBeFocused();
    tally(who).how = "browser: Labels to fix, find + select the 20";

    tally(AFFIX).units = 1;
    tally(AFFIX).how = "browser: station, 1 unit confirmed (19 over the API)";

    // The other 19 over the API, with the label number and the serial.
    for (let i = 1; i < N; i++) {
      const a = await stateOf(ids[i]);
      const r = await asPersona(who, "POST", `/assets/${ids[i]}/tag-affixed`,
        { tag_number: a.tagging.tag_number, serial_number: a.serial_number });
      expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
    }
    expect(await readBadge(page, who, "after affixing")).toBe(before - N);
    expect(new Set(await states())).toEqual(new Set(["tagged"]));
    await stepTaken("tagger affixed 20", { tagger: -N, register_maker: +N });
  });

  test("Register Maker: 20 pasted lines, a duplicate on line 20 — preview writes nothing, submit fires 19", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "register_maker";
    await signIn(page, who);
    const before = await readBadge(page, who, "before registering");
    await openCandidates(page, who);

    await act.click(who, page.getByTestId("button-paste-sap"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "register");
    const lines = codes.map((c, i) => `${c} ${i === N - 1 ? SAP(N - 2) : SAP(i)}`);
    await act.paste(who, dialog.getByTestId("input-paste-sap"), lines.join("\n"));
    await expect(dialog.getByTestId("paste-count")).toContainText(`${N} lines read`);
    await act.type(who, dialog.getByTestId("input-cost-centre"), "CC-60");
    // The capitalisation date starts at today (the session carry's default).
    await expect(dialog.getByTestId("input-capitalisation-date")).not.toHaveValue("");

    const isRegister = (r: Response) => r.request().method() === "POST" && r.url().includes("/api/v1/candidates/gates/register");
    const previewP = page.waitForResponse(isRegister, { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-paste-preview"));
    const preview = await previewP;
    const pv = await preview.json();
    expect(preview.status(), JSON.stringify(pv).slice(0, 400)).toBe(200);
    expect(pv.data.dry_run).toBe(true);
    const dupSentence = `SAP asset code ${SAP(N - 2)} is already on another asset (${codes[N - 2]}).`;
    for (let l = 1; l < N; l++) await expect(dialog.getByTestId(`paste-line-${l}`)).toHaveAttribute("data-outcome", "would_fire");
    await expect(dialog.getByTestId(`paste-line-${N}`)).toHaveAttribute("data-outcome", "refused");
    await expect(dialog.getByTestId(`paste-line-${N}`).getByTestId("batch-result-message")).toHaveText(dupSentence);
    await expect(dialog.getByTestId("paste-preview-summary"))
      .toHaveText(`${N - 1} of ${N} would be submitted to the register, 1 would be refused. Nothing has been written yet.`);

    // The preview wrote nothing.
    for (const id of ids) {
      const a = await stateOf(id);
      expect(a.register_state, `preview moved unit ${id}`).toBe("tagged");
      expect(a.gates?.registration ?? null, `preview wrote a registration on ${id}`).toBeNull();
    }

    const submitP = page.waitForResponse(isRegister, { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-paste-submit"));
    const submitted = await submitP;
    const sb = await submitted.json();
    expect(submitted.status(), JSON.stringify(sb).slice(0, 400)).toBe(200);
    expect(sb.data.dry_run).toBe(false);
    expect(sb.data.fired).toBe(N - 1);
    expect(sb.data.refused).toBe(1);
    await expect(dialog.getByTestId("batch-results-summary"))
      .toHaveText(`${N - 1} of ${N} submitted to the register, 1 refused.`);
    for (let l = 1; l < N; l++) await expect(dialog.getByTestId(`paste-line-${l}`)).toHaveAttribute("data-outcome", "fired");
    await expect(dialog.getByTestId(`paste-line-${N}`)).toHaveAttribute("data-outcome", "refused");
    await expect(dialog.getByTestId(`paste-line-${N}`).getByTestId("batch-result-message")).toHaveText(dupSentence);
    await act.click(who, dialog.getByTestId("button-close-batch-results"));

    expect(await readBadge(page, who, "after registering")).toBe(before - (N - 1));
    for (let i = 0; i < N; i++) {
      const a = await stateOf(ids[i]);
      if (i === N - 1) {
        expect(a.register_state).toBe("tagged");
        expect(a.gates?.registration ?? null).toBeNull();
      } else {
        expect(a.register_state).toBe("reg_submitted");
        expect(a.gates.registration).toMatchObject({
          sap_asset_code: SAP(i), cost: 1850, cost_centre: "CC-60",
          asset_class: { id: category!.id, sap_asset_class: category!.sap },
        });
      }
    }
    await stepTaken("maker submitted 19 (line 20 refused)", { register_maker: -(N - 1), register_checker: +(N - 1) });
  });

  test("Register Checker: SAP code, cost, cost centre and class on each row — approves 19", async ({ page }) => {
    test.skip(ids.length !== N, "setup did not receive the 20");
    const who: Who = "register_checker";
    await signIn(page, who);
    const before = await readBadge(page, who, "before approving registrations");
    await openCandidates(page, who);
    await searchGrn(page, who, N - 1);
    for (let i = 0; i < N - 1; i++) {
      const id = ids[i];
      await expect(page.getByTestId(`checker-sap-${id}`)).toHaveText(SAP(i));
      await expect(page.getByTestId(`checker-cost-${id}`)).toHaveText("₦1,850");
      await expect(page.getByTestId(`checker-cost-centre-${id}`)).toHaveText("CC-60");
      await expect(page.getByTestId(`checker-class-${id}`)).toContainText(category!.name);
      await expect(page.getByTestId(`checker-class-${id}`)).toContainText(category!.sap);
    }
    await expect(page.getByTestId(`candidate-row-${ids[N - 1]}`)).toHaveCount(0);

    await act.check(who, page.getByTestId("select-all-visible"));
    await expect(page.getByTestId("batch-selected-count")).toContainText(`${N - 1} selected`);
    await act.click(who, page.getByTestId("button-batch-approve-registration"));
    const dialog = page.getByTestId("batch-dialog");
    await expect(dialog).toHaveAttribute("data-action", "approve-registration");
    const posted = page.waitForResponse((r) => r.request().method() === "POST"
      && r.url().includes("/api/v1/candidates/gates/approve-registration"), { timeout: 60_000 });
    await act.click(who, dialog.getByTestId("button-batch-submit"));
    const res = await posted;
    const body = await res.json();
    expect(res.status(), JSON.stringify(body).slice(0, 400)).toBe(200);
    expect(body.data.fired).toBe(N - 1);
    const results = page.getByTestId("batch-results");
    await expect(results.getByTestId("batch-results-summary")).toHaveText(`${N - 1} of ${N - 1} put on the register, 0 refused.`);
    await act.click(who, results.getByTestId("button-close-batch-results"));
    expect(await readBadge(page, who, "after approving registrations")).toBe(before - (N - 1));

    const final = await states();
    expect(final.slice(0, N - 1).every((s) => s === "registered"), JSON.stringify(final)).toBe(true);
    expect(final[N - 1]).toBe("tagged");
    await stepTaken("checker approved 19", { register_checker: -(N - 1) });
  });
});
