import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";
import { ensureSapClass, fixedCategory, onTheRegister, readyToAffix } from "../fixtures/gates";

/**
 * Handoff 57 — the receipt gates, driven as the people who keep them.
 *
 * The gate machine is one field on `nrs.asset` (`register_state`) — handoff
 * 57's design, kept by handoff 58 (evaluation §8).
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
 * Handoff 58 §8.6 adds the second describe block below: a `tag_id` unit
 * (furniture — no manufacturer serial, its attributes instead) through all
 * seven gates as the personas, the affix done IN THE BROWSER by the tagger
 * in the Confirm-affixed dialog (the label reading, the tick, and no serial
 * field at all); and the D3 sentence — the person who fired another gate on
 * a unit opens that dialog and is refused 409 in the server's own words.
 *
 * Handoff 59 §2 adds the third block: a `record_only` unit (an invented
 * "Land" class) through the FIVE gates as five people — the two tagging
 * gates skipped by the server, never fired — with `waiting_on` read at every
 * step and never the Asset Controller or Tagging, no label at any point, the
 * skip's sentence in the asset's history, and the register count moving only
 * at the checker. And since 59 §1 the register gate refuses a category with
 * no SAP asset class, so the first two blocks pick a serial class and give it
 * one first (the Asset Controller's PATCH, idempotent — `fixtures/gates.ts`).
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
 *  THEIR work, then find the unit's row and act on it.
 *
 *  Since handoff 60 the page opens on *Waiting on me* (only the units this
 *  person may act on) rather than on their gate's tab, and that gate's tab
 *  is still marked theirs; and the list is OLDEST first, so a unit created
 *  by this run is at the end of a busy tenant's list, not on the first page.
 *  So the unit is found the way a person would find it: its asset code
 *  typed into the search box at the top, which searches this list on the
 *  server. */
async function onCandidatesRow(page: Page, assetId: number, ownFilter: string, code: string) {
  await page.goto(appPath("/candidates"));
  await expect(page.getByTestId("filter-waiting-mine")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId(`filter-waiting-${ownFilter}`)).toContainText("(you)");
  expect(code, `no asset code for unit ${assetId}`).toBeTruthy();
  await page.getByTestId("input-global-search").fill(code);
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

/**
 * A category identified by SERIAL for the seven-gate path — the seed's first
 * when it is one (category 1, as `tests/gates.py` uses), never one of spec
 * 59's fixed fixture classes — with a SAP asset class, which the register
 * gate has required since handoff 59 §1.
 */
async function aRegistrableSerialClass(s: Session): Promise<number> {
  const rows: any[] = (await call(s, "GET", "/asset-categories")).body?.data ?? [];
  const serial = rows.filter((r) => (r.identification_mode ?? "serial") === "serial"
    && !String(r.name).startsWith("e2e-59"));
  const one = serial.find((r) => Number(r.id) === 1) ?? serial[0];
  if (!one) throw new Error("no asset category on this tenant is identified by serial");
  await ensureSapClass(one.id);
  return Number(one.id);
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
      const categoryId = await aRegistrableSerialClass(store);
      const name = markedName("spec57-candidate");
      const created = await call(store, "POST", "/assets", {
        name, category_id: categoryId, serial_number: `S57-${Date.now()}`,
        // Handoff 58 (Section 12): a `serial` class arrives with its serial
        // AND its make and model, or the receipt is refused at the door.
        make: "Spec57 Make", model_name: "Spec57 Model",
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
    const row = await onCandidatesRow(page, unitId, "store", unitCode);
    await row.getByTestId("gate-submit").click();
    await confirmGate(page, "submit");
    expect(await stateOf(unitId)).toBe("vfm_pending");
    await assertRegisterUnchanged("submitted");
  });

  test("IAD officer: verify is refused without the four checks and evidence, then verifies", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.iadOfficer]);
    const row = await onCandidatesRow(page, unitId, "iad", unitCode);
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
    const row = await onCandidatesRow(page, unitId, "iad_approver", unitCode);
    await row.getByTestId("gate-approve").click();
    await confirmGate(page, "approve");
    expect(await stateOf(unitId)).toBe("vfm_approved");
    await assertRegisterUnchanged("approved");
  });

  test("Asset Controller: requests tagging, and the label is minted then", async ({ page }) => {
    test.skip(!unitId, "setup did not create a candidate");
    await signIn(page, P[WHO.controller]);
    const row = await onCandidatesRow(page, unitId, "controller", unitCode);
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
    const row = await onCandidatesRow(page, unitId, "maker", unitCode);
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
    // Handoff 60: the page opens on *Waiting on me*; the checker's own tab is
    // still marked theirs.
    await expect(page.getByTestId("filter-waiting-mine")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("filter-waiting-checker")).toContainText("(you)");
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
    const name = markedName("spec57-two-gates");
    // With its class's identification (handoff 58, Section 12) — a bare name
    // is refused 400 at the door now, which is not the refusal this is about.
    const created = await call(admin!, "POST", "/assets", {
      name, category_id: await aRegistrableSerialClass(admin!),
      serial_number: `S57R-${Date.now()}`, make: "Spec57 Make", model_name: "Spec57 Model",
    });
    expect([200, 201], JSON.stringify(created.body).slice(0, 300)).toContain(created.status);
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

/* ── Handoff 58 §8.6: the tag_id path and the D3 sentence ─────────────────── */

test.describe("58 — a tag_id unit, and the affix refusal's sentence", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  const P = personas();
  let admin: Session | null = null;

  test.beforeAll(async () => {
    if (P.administrator) admin = await apiSession(P.administrator);
  });
  test.afterAll(async () => { await admin?.ctx.dispose(); });

  /** Skip, naming what is missing, unless this tenant can run the chain. */
  const needTheGates = async () => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    for (const k of [...Object.values(WHO), "administrator"]) test.skip(!P[k], `persona "${k}" missing from ${CREDS}`);
    const settings = await call(admin!, "GET", "/settings");
    test.skip(settings.body?.data?.receipt_gated !== true,
      `cadra.receipt.gated is not on for ${TENANT} (GET /settings → ${JSON.stringify(settings.body?.data ?? settings.status)})`);
  };

  /** The station → the card → the Confirm-affixed dialog, for `tag`. */
  const openAffixDialog = async (page: Page, tag: string) => {
    await page.goto(appPath("/tools/barcode"));
    const box = page.getByTestId("scan-box");
    await expect(box).toBeVisible({ timeout: 20_000 });
    await box.fill(tag);
    await box.press("Enter");
    await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by tag/i, { timeout: 20_000 });
    await expect(page.getByTestId("button-confirm-affixed")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("button-confirm-affixed").click();
    const dialog = page.getByTestId("dialog-confirm-affixed");
    await expect(dialog).toBeVisible();
    return dialog;
  };

  test("a tag_id unit: received with attributes and no serial, seven gates, the tagger affixes by label and tick", async ({ page, api }) => {
    await needTheGates();
    const cats = await call(admin!, "GET", "/asset-categories");
    const furniture = (cats.body?.data ?? []).find((c: any) => c.identification_mode === "tag_id");
    test.skip(!furniture, `no category on ${TENANT} is identified by tag_id (Section 12's seeded furniture class is missing)`);
    const mandatory: string[] = furniture.class_attributes_schema?.mandatory ?? [];

    // Received by the store, as INT-03 receives one: the attributes, no serial.
    const name = markedName("spec58-tag-id chair");
    const body: Record<string, unknown> = {
      name, category_id: furniture.id,
      make: "Spec58 Seating", model_name: "S58-CHAIR", colour: "Charcoal",
      material: "Steel and mesh", dimensions: "60 x 60 x 110 cm",
    };
    for (const f of mandatory) expect(body[f], `the class's schema names "${f}" and the spec sends it`).toBeTruthy();
    const store = await apiSession(P[WHO.store]);
    let received: any;
    try {
      const res = await call(store, "POST", "/assets", body);
      expect(res.status, JSON.stringify(res.body).slice(0, 400)).toBe(201);
      received = res.body.data;
    } finally {
      await store.ctx.dispose();
    }
    recordCreated({ kind: "asset", id: received.id, name });
    expect(received.register_state).toBe("captured");
    expect(received.identification_mode).toBe("tag_id");
    expect(received.serial_number || null, "a tag_id unit has no serial").toBeNull();

    // Store → IAD officer → IAD approver → Asset Controller, each as themselves
    // (`fixtures/gates.ts`); proved one by one in the browser by the block above.
    const issued = await readyToAffix(api, received);
    expect(issued.register_state).toBe("tag_issued");
    const tag: string = issued.tagging?.tag_number;
    expect(tag, "request-tagging minted no label").toBeTruthy();
    expect(tag, "the label carries the asset code (ruling 4.3)").toBe(issued.asset_code);

    // The tagger, in the browser.
    await signIn(page, P[WHO.tagger]);
    const dialog = await openAffixDialog(page, tag);
    // No serial to scan: no serial field, and not the "no serial on file"
    // sentence either — for this class that is the design, not a gap.
    await expect(dialog.getByTestId("input-affix-serial")).toHaveCount(0);
    await expect(dialog.getByTestId("affix-no-serial")).toHaveCount(0);
    const tick = dialog.getByTestId("affix-attributes-confirm");
    await expect(tick).toBeVisible();
    await expect(tick).not.toBeChecked();
    const tickLabel = dialog.locator('label[for="affix-attributes-confirm"]');
    await expect(tickLabel).toContainText(`The item matches: ${name}, Spec58 Seating, Charcoal`);
    // The no-leak rule is unchanged: the expected number is nowhere in it.
    expect(await dialog.evaluate((el) => el.outerHTML), "the dialog carries the expected tag number").not.toContain(tag);
    await shot(page, "tag-id-affix-dialog");

    // The label reading alone is not enough: the tick is required.
    await dialog.getByTestId("input-affix-tag-number").fill(tag);
    await expect(dialog.getByTestId("button-submit-affixed")).toBeDisabled();
    await tick.check();
    await expect(dialog.getByTestId("button-submit-affixed")).toBeEnabled();
    const posted = page.waitForResponse((r) => r.url().includes(`/assets/${received.id}/tag-affixed`) && r.request().method() === "POST");
    await dialog.getByTestId("button-submit-affixed").click();
    const res = await posted;
    const sent = res.request().postDataJSON() ?? {};
    expect(res.status(), `POST …/tag-affixed → ${res.status()}: ${await res.text().catch(() => "")}`).toBe(200);
    expect(sent.attributes_confirmed, "the tick rode the POST").toBe(true);
    expect(sent, "a tag_id unit sends no serial").not.toHaveProperty("serial_number");
    await expect(dialog).toBeHidden({ timeout: 20_000 });
    await shot(page, "tag-id-affixed");

    const tagged = await api.get<any>(`/api/v1/assets/${received.id}`);
    expect(tagged.register_state).toBe("tagged");
    expect(tagged.tagging.label_state).toBe("affixed");
    // The gate's event records which check the tagger made.
    const history = await api.get<any>(`/api/v1/assets/${received.id}/history`);
    const affix = (history.events ?? []).find((e: any) => e.type === "gate_fired" && e.detail?.action === "affix");
    expect(affix, "no gate_fired row for the affix").toBeTruthy();
    expect(affix.detail.evidence?.check).toBe("label_and_attributes");
    expect(affix.actor?.name ?? affix.actor_name).toBeTruthy();

    // Register Maker → Register Checker, as themselves: on the register.
    const registered = await onTheRegister(api, tagged);
    expect(registered.register_state).toBe("registered");
    const hit = await api.get<any[]>("/api/v1/assets", { q: registered.asset_code, limit: 5 });
    expect((hit ?? []).map((a) => a.id)).toContain(received.id);
  });

  test("D3: the person who fired another gate opens the affix dialog and is refused 409 in the server's own sentence", async ({ page, api }) => {
    await needTheGates();
    // Received and SUBMITTED by the administrator — who holds every gate's
    // scope, the affix's `tagging:write` among them, which is exactly who
    // the no-two-gates rule is for.
    const cats = await call(admin!, "GET", "/asset-categories");
    const serialClass = (cats.body?.data ?? []).find((c: any) => (c.identification_mode ?? "serial") === "serial");
    const name = markedName("spec58-d3");
    const serial = `S58D3-${Date.now()}`;
    const created = await call(admin!, "POST", "/assets", {
      name, category_id: serialClass.id, serial_number: serial, make: "Spec58 Make", model_name: "Spec58 Model",
    });
    expect(created.status, JSON.stringify(created.body).slice(0, 400)).toBe(201);
    const id = created.body.data.id as number;
    recordCreated({ kind: "asset", id, name });
    const submitted = await call(admin!, "POST", `/assets/${id}/gates/submit`, {});
    expect(submitted.status, JSON.stringify(submitted.body).slice(0, 300)).toBe(200);
    // IAD officer → IAD approver → Asset Controller, each themselves.
    const issued = await readyToAffix(api, submitted.body.data);
    expect(issued.register_state).toBe("tag_issued");
    const tag: string = issued.tagging.tag_number;

    await signIn(page, P.administrator);
    const dialog = await openAffixDialog(page, tag);
    await dialog.getByTestId("input-affix-tag-number").fill(tag);
    // A serial class: the serial field is there, and the right serial is
    // typed — so the ONLY thing wrong is who is holding the scanner.
    await dialog.getByTestId("input-affix-serial").fill(serial);
    const posted = page.waitForResponse((r) => r.url().includes(`/assets/${id}/tag-affixed`) && r.request().method() === "POST");
    await dialog.getByTestId("button-submit-affixed").click();
    const res = await posted;
    const envelope = await res.json().catch(() => null);
    expect(res.status(), JSON.stringify(envelope).slice(0, 400)).toBe(409);
    expect(envelope?.error?.code).toBe("conflict");
    expect(envelope?.error?.details?.reason).toBe("segregation_of_duties");
    expect(envelope?.error?.details?.earlier?.action).toBe("submit");
    const sentence: string = envelope?.error?.message ?? "";
    expect(sentence).toMatch(/^You received this unit on \d{1,2} [A-Z][a-z]{2}; a different person must tag it\.$/);

    // The screen shows the server's sentence, verbatim — not "permission denied".
    const refusal = dialog.getByTestId("affix-refusal");
    await expect(refusal).toBeVisible({ timeout: 20_000 });
    await expect(refusal).toContainText(sentence);
    await expect(refusal).not.toContainText(/permission denied/i);
    await shot(page, "d3-affix-refusal");

    // Nothing was written.
    const after = await api.get<any>(`/api/v1/assets/${id}`);
    expect(after.register_state).toBe("tag_issued");
    expect(after.tagging.label_state).not.toBe("affixed");
  });
});

/* ── Handoff 59 §2: a record_only unit — five gates, no label ──────────────── */

/** Spec 57's invented land class: one fixed name, found or created and set
 *  every run (a category holding assets can never be deleted). */
const LAND_CATEGORY = "e2e-59 Land (record_only)";
const LAND_SAP_CLASS = "6000";

test.describe("59 — a record_only unit: five gates, no label", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.describe.configure({ mode: "serial" });

  const P = personas();
  let admin: Session | null = null;
  let landId = 0;
  let landName = "";
  let unitId = 0;
  let unitCode = "";
  let registerBefore = -1;
  /** `waiting_on` as the server said it after each step — printed at the end. */
  const waitingLog: string[] = [];

  const registerCount = async () => {
    const r = await call(admin!, "GET", "/assets?limit=1");
    expect(r.status).toBe(200);
    return r.body?.pagination?.total_estimate as number;
  };

  /** The unit as the server holds it now, with the invariants of a unit
   *  that has no label: never waiting on the Asset Controller or Tagging,
   *  never a tag, never a label — whatever the step. */
  const readUnit = async (step: string) => {
    const a = (await call(admin!, "GET", `/assets/${unitId}`)).body?.data;
    const waiting = a?.gates?.waiting_on ?? null;
    waitingLog.push(`${step}: register_state=${a?.register_state} waiting_on=${waiting}`);
    console.log(`[spec 59 record_only] ${step}: register_state=${a?.register_state} waiting_on=${waiting}`);
    expect(["controller", "tagging"], `waiting on ${waiting} at "${step}"`).not.toContain(waiting);
    expect(a?.tag ?? null, `a tag number appeared at "${step}"`).toBeNull();
    expect(a?.tagging?.label_id ?? null, `a label was minted at "${step}"`).toBeNull();
    expect(a?.tagging?.tag_number ?? null, `a label number appeared at "${step}"`).toBeNull();
    return a;
  };
  const assertRegisterUnchanged = async (step: string) => {
    expect(await registerCount(), `the register count moved at "${step}"`).toBe(registerBefore);
  };

  test.beforeAll(async () => {
    if (P.administrator) admin = await apiSession(P.administrator);
  });
  test.afterAll(async () => {
    if (waitingLog.length) console.log(`[spec 59 record_only] waiting_on, step by step:\n  ${waitingLog.join("\n  ")}`);
    await admin?.ctx.dispose();
  });

  test("setup: a Land class identified by its record; a receipt with a serial is refused, one with a reference is accepted", async () => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    for (const k of [...Object.values(WHO), "administrator"]) test.skip(!P[k], `persona "${k}" missing from ${CREDS}`);
    const settings = await call(admin!, "GET", "/settings");
    test.skip(settings.body?.data?.receipt_gated !== true,
      `cadra.receipt.gated is not on for ${TENANT} (GET /settings → ${JSON.stringify(settings.body?.data ?? settings.status)})`);

    const land = await fixedCategory(LAND_CATEGORY, {
      identification_mode: "record_only",
      sap_asset_class: LAND_SAP_CLASS,
      class_attributes_schema: { mandatory: ["name", "record_reference"] },
    });
    landId = land.id;
    landName = land.name;
    expect(land.identification_mode).toBe("record_only");
    expect(land.sap_asset_class).toBe(LAND_SAP_CLASS);

    registerBefore = await registerCount();
    const store = await apiSession(P[WHO.store]);
    try {
      // A serial on a unit that has none is refused, whoever sends it — and
      // nothing is written.
      const refusedName = markedName("spec59-land-with-serial");
      const refused = await call(store, "POST", "/assets", {
        name: refusedName, category_id: landId, record_reference: `PLOT-E2E-${Date.now()}`,
        serial_number: `S59-${Date.now()}`,
      });
      expect(refused.status, JSON.stringify(refused.body).slice(0, 400)).toBe(400);
      expect(JSON.stringify(refused.body?.error ?? {})).toMatch(/serial/i);
      const leftover = await call(admin!, "GET",
        `/assets?q=${encodeURIComponent(refusedName)}&register_state=any&limit=5`);
      expect(leftover.body?.data ?? [], "a refused receipt left a record behind").toHaveLength(0);

      // Name + reference, no serial: accepted as a candidate.
      const name = markedName("spec59-land plot");
      const created = await call(store, "POST", "/assets", {
        name, category_id: landId, record_reference: `PLOT-E2E-${Date.now()}`,
        purchase_order_reference: "PO-59-DEMO", grn_reference: `GRN-59-${Date.now()}`,
      });
      expect(created.status, JSON.stringify(created.body).slice(0, 400)).toBe(201);
      unitId = created.body.data.id;
      unitCode = created.body.data.asset_code;
      recordCreated({ kind: "asset", id: unitId, name });
      expect(created.body.data.register_state).toBe("captured");
      expect(created.body.data.identification_mode).toBe("record_only");
      expect(created.body.data.serial_number || null).toBeNull();
      expect(created.body.data.record_reference).toMatch(/^PLOT-E2E-/);
    } finally {
      await store.ctx.dispose();
    }
    const a = await readUnit("received");
    expect(a.gates.waiting_on).toBe("store");
    await assertRegisterUnchanged("received");
  });

  test("store submits; the Candidates row says who it waits on", async ({ page }) => {
    test.skip(!unitId, "setup did not create a record_only candidate");
    await signIn(page, P[WHO.store]);
    const row = await onCandidatesRow(page, unitId, "store", unitCode);
    await expect(row.getByTestId("candidate-mode")).toHaveText("SAP record");
    await expect(row.getByTestId("candidate-waiting")).toHaveText("Store");
    await row.getByTestId("gate-submit").click();
    await confirmGate(page, "submit");
    const a = await readUnit("submitted");
    expect(a.register_state).toBe("vfm_pending");
    expect(a.gates.waiting_on).toBe("iad");
    await assertRegisterUnchanged("submitted");
  });

  test("IAD officer verifies", async ({ page }) => {
    test.skip(!unitId, "setup did not create a record_only candidate");
    await signIn(page, P[WHO.iadOfficer]);
    const row = await onCandidatesRow(page, unitId, "iad", unitCode);
    await expect(row.getByTestId("candidate-waiting")).toHaveText("IAD officer");
    await row.getByTestId("gate-verify").click();
    const dialog = page.getByTestId("dialog-gate-verify");
    for (const k of ["quantity", "specification", "condition", "price"]) await dialog.getByTestId(`check-${k}`).check();
    await dialog.getByTestId("input-evidence").setInputFiles({
      name: "title-deed.txt", mimeType: "text/plain", buffer: Buffer.from("Sighted the title against PO-59-DEMO."),
    });
    await confirmGate(page, "verify");
    const a = await readUnit("verified");
    expect(a.register_state).toBe("vfm_verified");
    expect(a.gates.waiting_on).toBe("iad_approver");
    await assertRegisterUnchanged("verified");
  });

  test("IAD approver approves — and the server skips both tagging gates", async ({ page }) => {
    test.skip(!unitId, "setup did not create a record_only candidate");
    await signIn(page, P[WHO.iadApprover]);
    const row = await onCandidatesRow(page, unitId, "iad_approver", unitCode);
    await row.getByTestId("gate-approve").click();
    await confirmGate(page, "approve");
    const a = await readUnit("approved");
    // Never `vfm_approved` / waiting on the Asset Controller: straight on.
    expect(a.register_state).toBe("reg_ready");
    expect(a.gates.waiting_on).toBe("maker");
    // The asset page says it in words.
    await page.goto(appPath(`/assets/${unitId}`));
    await expect(page.getByTestId("candidate-banner")).toBeVisible();
    await expect(page.getByTestId("candidate-banner-state")).toHaveText("Ready for registration — no label");
    await expect(page.getByTestId("candidate-banner-waiting")).toHaveText("Register Maker");
    await expect(page.getByTestId("candidate-banner-no-label")).toBeVisible();
    await shot(page, "record-only-reg-ready");
    await assertRegisterUnchanged("approved (tagging skipped)");
  });

  test("Register Maker submits — the dialog never says tagged, and shows the class's SAP code", async ({ page }) => {
    test.skip(!unitId, "setup did not create a record_only candidate");
    await signIn(page, P[WHO.maker]);
    const row = await onCandidatesRow(page, unitId, "maker", unitCode);
    await expect(row.getByTestId("candidate-waiting")).toHaveText("Register Maker");
    await row.getByTestId("gate-register").click();
    const dialog = page.getByTestId("dialog-gate-register");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("gate-dialog-sentence")).not.toContainText(/tagged/i);
    await expect(dialog.getByTestId("gate-dialog-sentence")).toContainText("no label");
    // Drawn once the category list is read — a slow read on a busy tenant
    // (it counts every category's assets), so a generous wait.
    await expect(dialog.getByTestId("gate-sap-class")).toContainText(LAND_SAP_CLASS, { timeout: 30_000 });
    await expect(dialog.getByTestId("gate-no-sap-class")).toHaveCount(0);
    // An invented number in SAP's numeric shape, its first digit the class's
    // — so no class-digit warning, and the dialog closes on success.
    const sapNumber = LAND_SAP_CLASS[0] + String(Date.now()).slice(-10).padStart(10, "0");
    await dialog.getByTestId("input-sap-asset-code").fill(sapNumber);
    await dialog.getByTestId("input-cost").fill("25000000");
    await dialog.getByTestId("input-cost-centre").fill("CC-59");
    await expect(dialog.getByTestId("gate-sap-digit-hint")).toHaveCount(0);
    await confirmGate(page, "register");
    const a = await readUnit("submitted to the register");
    expect(a.register_state).toBe("reg_submitted");
    expect(a.gates.waiting_on).toBe("checker");
    await assertRegisterUnchanged("submitted to the register");
  });

  test("Register Checker approves; the register gains exactly this unit, with no label and the skip in its history", async ({ page }) => {
    test.skip(!unitId, "setup did not create a record_only candidate");
    await signIn(page, P[WHO.checker]);
    await page.goto(appPath(`/assets/${unitId}`));
    await expect(page.getByTestId("candidate-banner-waiting")).toHaveText("Register Checker");
    await page.getByTestId("gate-approve-registration").click();
    await confirmGate(page, "approve-registration");
    await expect(page.getByTestId("candidate-banner")).toBeHidden();
    const a = await readUnit("registered");
    expect(a.register_state).toBe("registered");
    expect(a.gates?.waiting_on ?? null).toBeNull();
    expect(await registerCount(), "the register did not gain exactly the one unit").toBe(registerBefore + 1);
    const hit = await call(admin!, "GET", `/assets?q=${encodeURIComponent(unitCode)}&limit=5`);
    expect((hit.body?.data ?? []).map((x: { id: number }) => x.id)).toContain(unitId);

    // The skip is an event, not a silence: a gate_fired row naming why.
    const history = (await call(admin!, "GET", `/assets/${unitId}/history`)).body?.data;
    const events: any[] = history?.events ?? [];
    const skip = events.find((e) => e.type === "gate_fired" && e.detail?.action === "skip-tagging");
    expect(skip, "no gate_fired row for the skipped tagging gates").toBeTruthy();
    const why = `no label: ${landName} is identified by its record`;
    expect(skip.detail.reason).toBe(why);
    // No tagging gate ever FIRED: skipped, not fired.
    const fired = events.filter((e) => e.type === "gate_fired").map((e) => e.detail?.action);
    expect(fired).not.toContain("request-tagging");
    expect(fired).not.toContain("affix");

    // And the sentence reads on the asset's history, in the browser.
    await page.getByTestId("tab-audit-review").click();
    await expect(page.getByTestId("asset-history-event").filter({ hasText: why }).first()).toBeVisible({ timeout: 20_000 });
    await shot(page, "record-only-registered-history");
    // The tag row says there is none — not the asset code dressed as one
    // (the mapped asset falls back to the code when there is no tag).
    await page.getByTestId("tab-details").click();
    await expect(page.getByText("None — identified by its SAP record")).toBeVisible();
  });
});
