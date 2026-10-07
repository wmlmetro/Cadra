import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 57 — the receipt gates, driven as the people who keep them.
 *
 * SCAFFOLDING, 2026-10-07: the gate machine is one field on `nrs.asset`
 * (`register_state`) until handoff 58's candidate model replaces it.
 *
 * One received unit, created the way INT-03 creates one, walked through every
 * gate by a different person, each signed in through the real sign-in page:
 *
 *   store submits → IAD officer verifies (four checks + evidence) → IAD
 *   approver approves → Asset Controller requests tagging (the label is minted
 *   NOW, not at creation) → the tagger confirms it affixed (the existing
 *   route) → Register Maker submits with the SAP code and cost → Register
 *   Checker approves on the asset page → the unit is on the register.
 *
 * The register's own count is read before and after every step and must not
 * move until the checker approves. Then the refusals, every one asserted as
 * the server's answer, not the screen's:
 *
 *   - the same person at two gates (no-two-gates: 409 segregation_of_duties,
 *     and the asset page draws the sentence, not the button);
 *   - approve without verify (409 invalid_state);
 *   - submit to the register without the SAP code (400; the dialog says so
 *     first and will not send);
 *   - approve a registration nobody has submitted (409 invalid_state).
 *
 * The affix step is the tagger's own token on `POST /assets/<id>/tag-affixed`,
 * not the station's dialog: that dialog is proved by specs 39/40 and is
 * unchanged; what is new here is that its success moves the gate.
 *
 * Needs the switch on (`receipt_gated` on `GET /api/v1/settings`) and the
 * personas file; skips loudly naming whichever is missing.
 *
 *   (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test 57-)
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
// The cluster's persona file is named for the cluster, not the host
// (`demo_personas_fetch.sh` writes `.personas.cluster.<db>`), so a run
// against `staging.app.cadra.ng` names its file explicitly.
const CREDS = process.env.E2E_PERSONAS ?? `../docs/api/.personas.${TENANT}`;

/** The personas file's KEY for each job (Stream C's seed names them). */
const WHO = {
  store: "storekeeper",
  iadOfficer: "iad_officer",
  iadApprover: "iad_approver",
  controller: "asset_controller",
  tagger: "tagger",
  maker: "register_maker",
  checker: "register_checker",
} as const;

type Persona = { key: string; login: string; password: string };

function personas(): Record<string, Persona> {
  if (!existsSync(CREDS)) return {};
  const out: Record<string, Persona> = {};
  for (const l of readFileSync(CREDS, "utf8").split("\n")) {
    if (!l.trim() || l.startsWith("#")) continue;
    const [key, login, password] = l.trim().split(/\s+/);
    out[key] = { key, login, password };
  }
  return out;
}

type Session = { ctx: APIRequestContext; token: string };

async function apiSession(p: Persona): Promise<Session> {
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { login: p.login, password: p.password },
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  if (!res.ok()) throw new Error(`persona ${p.key} login failed: HTTP ${res.status()} — ${await res.text()}`);
  const token = (await res.json())?.data?.access_token;
  if (!token) throw new Error(`persona ${p.key} login: no access_token`);
  return { ctx, token };
}

/** One call with a session's token, never throwing — the status and body are
 *  what the refusal tests assert on. */
async function call(s: Session, method: "GET" | "POST", path: string, data?: unknown) {
  const res = await s.ctx.fetch(`/api/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${s.token}`, Accept: "application/json", "Content-Type": "application/json" },
    data: method === "POST" ? (data ?? {}) : undefined,
  });
  const body = await res.json().catch(() => null);
  return { status: res.status(), body };
}

async function signIn(page: Page, p: Persona) {
  signedInAs = p.key;
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

/** Open the Candidates page as the signed-in person and assert it opened on
 *  THEIR gate, then act on the unit's row. */
async function onCandidatesRow(page: Page, assetId: number, ownFilter: string) {
  await page.goto(appPath("/candidates"));
  await expect(page.getByTestId(`filter-waiting-${ownFilter}`)).toHaveAttribute("aria-selected", "true");
  const row = page.getByTestId(`candidate-row-${assetId}`);
  await expect(row, `unit ${assetId} is not on ${ownFilter}'s Candidates page`).toBeVisible({ timeout: 20_000 });
  return row;
}

/** Evidence for the report: one image per gate, before and after, when
 *  `E2E_SHOTS` names a directory. */
let shotSeq = 0;
let signedInAs = "nobody";
async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  mkdirSync(dir, { recursive: true });
  // Numbered, so the directory listing IS the run sheet: order, who, what.
  const n = String(++shotSeq).padStart(2, "0");
  await page.screenshot({ path: `${dir}/${TENANT}-57-${n}-${signedInAs}-${name}.png`, fullPage: true });
}

async function confirmGate(page: Page, action: string) {
  const dialog = page.getByTestId(`dialog-gate-${action}`);
  await expect(dialog).toBeVisible();
  await shot(page, `${action}-dialog`);
  const done = page.waitForResponse((r) => r.url().includes(`/gates/${action}`) && r.request().method() === "POST");
  await dialog.getByTestId("button-confirm-gate").click();
  const res = await done;
  // The success handler invalidates the page's gate query; wait for that
  // refetch, or the "after" screenshot shows the state before the gate.
  const refetched = page.waitForResponse((r) => r.request().method() === "GET"
    && /\/api\/v1\/(assets\/\d+|candidates)(\?|$)/.test(new URL(r.url()).pathname + "?"), { timeout: 15_000 })
    .catch(() => undefined);
  expect(res.status(), `POST …/gates/${action} → ${res.status()}: ${await res.text().catch(() => "")}`).toBe(200);
  await expect(dialog).toBeHidden();
  await refetched;
  await page.waitForLoadState("networkidle").catch(() => undefined);
  const state = (await res.json().catch(() => null))?.data?.register_state ?? "unknown";
  await shot(page, `${action}-now-${state}`);
}

test.describe("57 — the gates, tonight", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  const P = personas();
  let admin: Session | null = null;
  let unitId = 0;
  let unitCode = "";
  let registerBefore = -1;

  /** The register's own count: `GET /assets` with no `register_state`. */
  const registerCount = async () => {
    const r = await call(admin!, "GET", "/assets?limit=1");
    expect(r.status).toBe(200);
    return r.body?.pagination?.total_estimate as number;
  };
  const stateOf = async (id: number) => (await call(admin!, "GET", `/assets/${id}`)).body?.data?.register_state;
  const assertRegisterUnchanged = async (step: string) => {
    expect(await registerCount(), `the register count moved at "${step}"`).toBe(registerBefore);
    const hit = await call(admin!, "GET", `/assets?q=${encodeURIComponent(unitCode)}&limit=5`);
    expect((hit.body?.data ?? []).map((a: { id: number }) => a.id), `the register lists the candidate at "${step}"`)
      .not.toContain(unitId);
  };

  test.beforeAll(async () => {
    if (P.administrator) admin = await apiSession(P.administrator);
  });
  test.afterAll(async () => { await admin?.ctx.dispose(); });

  test("setup: a received unit arrives as a candidate, unlabelled and off the register", async () => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    for (const k of [...Object.values(WHO), "administrator"]) test.skip(!P[k], `persona "${k}" missing from ${CREDS}`);
    const settings = await call(admin!, "GET", "/settings");
    test.skip(settings.body?.data?.receipt_gated !== true,
      `cadra.receipt.gated is not on for ${TENANT} (GET /settings → ${JSON.stringify(settings.body?.data ?? settings.status)})`);

    registerBefore = await registerCount();
    expect(registerBefore).toBeGreaterThanOrEqual(0);

    // The store creates it, as INT-03 would: same route, same body shape.
    const store = await apiSession(P[WHO.store]);
    try {
      const cats = await call(store, "GET", "/asset-categories");
      const categoryId = cats.body?.data?.[0]?.id;
      const name = markedName("spec57-candidate");
      const created = await call(store, "POST", "/assets", {
        name, category_id: categoryId, serial_number: `S57-${Date.now()}`,
        purchase_order_reference: "PO-57-DEMO", grn_reference: `GRN-57-${Date.now()}`,
      });
      expect([200, 201], JSON.stringify(created.body).slice(0, 300)).toContain(created.status);
      unitId = created.body.data.id;
      unitCode = created.body.data.asset_code;
      recordCreated({ kind: "asset", id: unitId, name });
      expect(created.body.data.register_state).toBe("captured");
      // No label at creation any more: the mint moved to request-tagging.
      expect(created.body.data.tagging?.label_id ?? null, "a label was minted at creation").toBeNull();
    } finally {
      await store.ctx.dispose();
    }
    await assertRegisterUnchanged("created");
    const listed = await call(admin!, "GET", "/candidates?register_state=captured&limit=100");
    expect(listed.status).toBe(200);
    expect((listed.body?.data ?? []).map((r: { id: number }) => r.id)).toContain(unitId);
  });

  test("store: submits the unit to IAD from the Candidates page", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.store]);
    const row = await onCandidatesRow(page, unitId, "store");
    await row.getByTestId("gate-submit").click();
    await confirmGate(page, "submit");
    expect(await stateOf(unitId)).toBe("vfm_pending");
    await assertRegisterUnchanged("submitted");
  });

  test("IAD officer: verify is refused without the four checks and evidence, then verifies", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.iadOfficer]);
    const row = await onCandidatesRow(page, unitId, "iad");
    await row.getByTestId("gate-verify").click();
    const dialog = page.getByTestId("dialog-gate-verify");
    await expect(dialog.getByTestId("button-confirm-gate")).toBeDisabled();
    await expect(dialog.getByTestId("gate-missing")).toContainText("all four checks");
    await expect(dialog.getByTestId("gate-missing")).toContainText("at least one piece of evidence");
    for (const k of ["quantity", "specification", "condition", "price"]) await dialog.getByTestId(`check-${k}`).check();
    await expect(dialog.getByTestId("button-confirm-gate")).toBeDisabled();
    await dialog.getByTestId("input-evidence").setInputFiles({
      name: "delivery-note.txt", mimeType: "text/plain", buffer: Buffer.from("Sighted against PO-57-DEMO."),
    });
    await expect(dialog.getByTestId("button-confirm-gate")).toBeEnabled();
    await confirmGate(page, "verify");
    expect(await stateOf(unitId)).toBe("vfm_verified");
    await assertRegisterUnchanged("verified");
  });

  test("IAD approver: approves", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.iadApprover]);
    const row = await onCandidatesRow(page, unitId, "iad_approver");
    await row.getByTestId("gate-approve").click();
    await confirmGate(page, "approve");
    expect(await stateOf(unitId)).toBe("vfm_approved");
    await assertRegisterUnchanged("approved");
  });

  test("Asset Controller: requests tagging, and the label is minted then", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.controller]);
    const row = await onCandidatesRow(page, unitId, "controller");
    await row.getByTestId("gate-request-tagging").click();
    await confirmGate(page, "request-tagging");
    const after = (await call(admin!, "GET", `/assets/${unitId}`)).body?.data;
    expect(after?.register_state).toBe("tag_issued");
    expect(after?.tagging?.tag_number, "request-tagging minted no label").toBeTruthy();
    await assertRegisterUnchanged("tag issued");
  });

  test("tagger: confirms the label affixed — the existing route moves the gate", async () => {
    test.skip(!unitId, "setup did not create a candidate");
    const tagger = await apiSession(P[WHO.tagger]);
    try {
      const a = (await call(tagger, "GET", `/assets/${unitId}`)).body?.data;
      const res = await call(tagger, "POST", `/assets/${unitId}/tag-affixed`, { tag_number: a.tagging.tag_number });
      expect(res.status, JSON.stringify(res.body).slice(0, 300)).toBe(200);
    } finally {
      await tagger.ctx.dispose();
    }
    expect(await stateOf(unitId)).toBe("tagged");
    await assertRegisterUnchanged("tagged");
  });

  test("refusal: nobody approves a registration that was never submitted", async () => {
    test.skip(!unitId, "setup did not create a candidate");
    const checker = await apiSession(P[WHO.checker]);
    try {
      const res = await call(checker, "POST", `/assets/${unitId}/gates/approve-registration`, {});
      expect(res.status).toBe(409);
      expect(res.body?.error?.details?.reason ?? res.body?.details?.reason).toBe("invalid_state");
    } finally {
      await checker.ctx.dispose();
    }
    expect(await stateOf(unitId)).toBe("tagged");
  });

  test("Register Maker: the SAP code is required, then submits with code and cost", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    // The server's refusal first, with the maker's own token.
    const maker = await apiSession(P[WHO.maker]);
    try {
      const a = (await call(maker, "GET", `/assets/${unitId}`)).body?.data;
      const res = await call(maker, "POST", `/assets/${unitId}/gates/register`, {
        cost: 125000, cost_centre: "CC-57", capitalisation_date: "2026-10-07", asset_class: a.category?.id,
      });
      expect(res.status, JSON.stringify(res.body).slice(0, 300)).toBe(400);
      expect(res.body?.error?.code).toBe("validation_failed");
      expect(res.body?.error?.message ?? "").toMatch(/SAP/i);
    } finally {
      await maker.ctx.dispose();
    }
    expect(await stateOf(unitId)).toBe("tagged");

    await signIn(page, P[WHO.maker]);
    const row = await onCandidatesRow(page, unitId, "maker");
    await row.getByTestId("gate-register").click();
    const dialog = page.getByTestId("dialog-gate-register");
    await dialog.getByTestId("input-cost").fill("125000");
    await dialog.getByTestId("input-cost-centre").fill("CC-57");
    // The dialog says what is missing before the server does, and will not send.
    await expect(dialog.getByTestId("gate-missing")).toContainText("the SAP asset code");
    await expect(dialog.getByTestId("button-confirm-gate")).toBeDisabled();
    await dialog.getByTestId("input-sap-asset-code").fill(`SAP-57-${unitId}`);
    await expect(dialog.getByTestId("button-confirm-gate")).toBeEnabled();
    await confirmGate(page, "register");
    expect(await stateOf(unitId)).toBe("reg_submitted");
    await assertRegisterUnchanged("submitted to the register");
  });

  test("Register Checker: approves on the asset page, and the unit joins the register", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.checker]);
    await page.goto(appPath(`/candidates`));
    await expect(page.getByTestId("filter-waiting-checker")).toHaveAttribute("aria-selected", "true");
    await page.goto(appPath(`/assets/${unitId}`));
    await expect(page.getByTestId("candidate-banner")).toBeVisible();
    await expect(page.getByTestId("candidate-banner-waiting")).toHaveText("Register Checker");
    await page.getByTestId("gate-approve-registration").click();
    await confirmGate(page, "approve-registration");
    await expect(page.getByTestId("candidate-banner")).toBeHidden();
    expect(await stateOf(unitId)).toBe("registered");
    expect(await registerCount(), "the register did not gain exactly the one unit").toBe(registerBefore + 1);
    const hit = await call(admin!, "GET", `/assets?q=${encodeURIComponent(unitCode)}&limit=5`);
    expect((hit.body?.data ?? []).map((a: { id: number }) => a.id)).toContain(unitId);
  });

  test("refusals: approve without verify, and the same person at two gates", async ({ page }) => {
    test.skip(!admin || Object.keys(P).length === 0, "no personas");
    const settings = await call(admin!, "GET", "/settings");
    test.skip(settings.body?.data?.receipt_gated !== true, "receipt gating is off");

    // A second unit, received and submitted by the administrator — who holds
    // every gate's scope, which is exactly who the no-two-gates rule is for.
    const cats = await call(admin!, "GET", "/asset-categories");
    const name = markedName("spec57-two-gates");
    const created = await call(admin!, "POST", "/assets", { name, category_id: cats.body?.data?.[0]?.id });
    expect([200, 201]).toContain(created.status);
    const id = created.body.data.id as number;
    recordCreated({ kind: "asset", id, name });
    expect((await call(admin!, "POST", `/assets/${id}/gates/submit`, {})).status).toBe(200);

    // Approve without verify: the approver's own token, refused on state.
    const approver = await apiSession(P[WHO.iadApprover]);
    try {
      const res = await call(approver, "POST", `/assets/${id}/gates/approve`, {});
      expect(res.status).toBe(409);
      expect(res.body?.error?.details?.reason ?? res.body?.details?.reason).toBe("invalid_state");
    } finally {
      await approver.ctx.dispose();
    }

    // The same person at a second gate: the sentence, never "permission denied".
    const twice = await call(admin!, "POST", `/assets/${id}/gates/verify`, {
      checklist: { quantity: true, specification: true, condition: true, price: true },
      attachments: [{ name: "x.txt", mimetype: "text/plain", data: Buffer.from("x").toString("base64") }],
    });
    expect(twice.status).toBe(409);
    expect(twice.body?.error?.details?.reason ?? twice.body?.details?.reason).toBe("segregation_of_duties");
    const sentence: string = twice.body?.error?.message ?? twice.body?.message ?? "";
    expect(sentence).toMatch(/different person/i);
    expect(sentence).not.toMatch(/permission denied/i);
    expect(await stateOf(id)).toBe("vfm_pending");

    // And the screen agrees with the server: no Verify button for the
    // administrator, the sentence in its place.
    await signIn(page, P.administrator);
    await page.goto(appPath(`/assets/${id}`));
    await expect(page.getByTestId("candidate-banner")).toBeVisible();
    await expect(page.getByTestId("gate-verify")).toHaveCount(0);
    await expect(page.getByTestId("gate-refusal").first()).toContainText(/different person/i);
    await shot(page, "two-gates-refusal");
  });
});
