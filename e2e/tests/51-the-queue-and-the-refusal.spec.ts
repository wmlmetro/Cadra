import { existsSync, readFileSync } from "node:fs";
import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { test, expect, type Page } from "../fixtures/test";
import { ORIGIN, appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 51 §1 — one queue, because a request nobody can find was never made.
 *
 * The defect as the owner hit it: a tag replacement was raised with an
 * approver named, and appeared on neither the approver's screens nor the
 * requester's. The fix is `GET /api/v1/tags/replacements` behind a second
 * section on `/approvals`, and §8 says how it is proved: driven as THREE
 * people, not one, plus the tagging-only refusal of §1c. One request is
 * raised once and every test below reads it as somebody else — which is why
 * the suite is serial, the same convention `35-approvals.spec.ts` uses for
 * its shared journey.
 *
 *   a. the REQUESTER (Tagging Officer) sees their row on *Raised by me*,
 *      waiting, with no decide control and the you-asked sentence — the
 *      server's refusal exists, and the screen declines to offer it;
 *   b. the NAMED APPROVER (Asset Manager) sees it on *Waiting on me*,
 *      approves it, and reads it as replaced under *Decided*;
 *   c. the AUDITOR reads the queue and is offered no control at all;
 *   d. a TAGGING-ONLY token (`tagging:write` and nothing else) is refused
 *      the route 403 with the missing scope NAMED — §1c on record as a
 *      measurement, not an assertion, the way spec 46 probes every route;
 *   e. the requester comes back and reads the outcome on *Raised by me* —
 *      the question `pending-replacements` could never answer.
 *
 * Signs in as the demo personas `scripts/demo_personas.sh <db> seed` made.
 * Skips loudly unless `docs/api/.personas.<tenant>` exists — the passwords
 * live there and nowhere else (spec 46's guard, unchanged).
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const CREDS = `../docs/api/.personas.${TENANT}`;

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

/** A persona's own API session — the row must be RAISED by the officer's
 *  token, or test (a) proves nothing about a requester. */
async function apiSession(p: Persona): Promise<{ ctx: APIRequestContext; token: string }> {
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { login: p.login, password: p.password },
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  if (!res.ok()) throw new Error(`persona ${p.key} login failed: HTTP ${res.status()} — ${await res.text()}`);
  const body = await res.json();
  const token = body?.data?.access_token;
  if (!token) throw new Error(`persona ${p.key} login: no access_token in response`);
  return { ctx, token };
}

/** The real sign-in page, as spec 46 drives it — being the person is the
 *  only way to know what the person sees. */
async function signIn(page: Page, p: Persona) {
  await page.goto(appPath("/"));
  await page.locator('input[autocomplete="username"]').fill(p.login);
  await page.locator('input[autocomplete="current-password"]').fill(p.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => u.pathname !== "/app/" && u.pathname !== "/app", { timeout: 30_000 });
}

test.describe("51 — the queue and the refusal (§1)", () => {
  // Fresh storage per test: the suite's default state is admin's, and every
  // test here is somebody else on purpose.
  test.use({ storageState: { cookies: [], origins: [] } });
  // One request, read by three people in order — the decision in (b) is
  // exactly what (c) and (e) read back.
  test.describe.configure({ mode: "serial" });

  const P = personas();
  const NEEDED = ["tagger", "asset_manager", "auditor", "tag_unit"] as const;

  // Shared across the serial run. Empty means setup skipped, and every
  // later test says so instead of failing on a row that was never raised.
  let labelId = 0;
  let tagNumber = "";

  test("setup: the Tagging Officer asks, naming the Asset Manager", async ({ api }) => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    for (const k of NEEDED) test.skip(!P[k], `persona "${k}" missing from ${CREDS}`);

    // A fresh asset of our own. A tag is minted on creation (spec 38's
    // note), and the `tagging` block on the payload names the label row —
    // with the station's lookup as the fallback for a tenant whose payload
    // does not carry it.
    const name = markedName("spec51-replacement");
    const asset = await api.createAsset(name);
    recordCreated({ kind: "asset", id: asset.id, name });
    labelId = asset?.tagging?.label_id ?? 0;
    tagNumber = asset?.tagging?.tag_number ?? asset?.tag ?? "";
    if (!labelId && asset?.tag) {
      const found = await api.get<any>("/api/v1/barcode/lookup", { query: asset.tag });
      labelId = found?.tag_id ?? 0;
      tagNumber = tagNumber || found?.tag_number || asset.tag;
    }
    test.skip(!labelId || !tagNumber, "the created asset carries no tag label to replace");

    // The Asset Manager's user id, resolved as admin: `GET /users` is
    // admin-scoped and matches by LOGIN, which is a fact; the officer could
    // ask `/approvals/approvers`, but that matches by display name, which
    // is a guess. Resolved through `q`, NOT by paging: test19 holds more
    // accounts than one external page (103+ against the 100-row cap), and
    // the demo personas are the NEWEST accounts — exactly the rows the cap
    // cuts off. This spec's first run proved it by failing here.
    const users = await api.get<any[]>("/api/v1/users", { q: P.asset_manager.login, limit: 10 });
    const manager = (Array.isArray(users) ? users : []).find((u) => u.login === P.asset_manager.login);
    expect(manager, `no account with login ${P.asset_manager.login} on ${TENANT}`).toBeTruthy();

    // The OFFICER raises it, with their own token.
    const officer = await apiSession(P.tagger);
    try {
      const res = await officer.ctx.post(`/api/v1/tags/${labelId}/request-replacement`, {
        headers: {
          Authorization: `Bearer ${officer.token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        data: { reason: "damaged", approver_id: manager.id },
      });
      expect(res.ok(), `request-replacement → HTTP ${res.status()}: ${await res.text().catch(() => "")}`).toBeTruthy();
      const body = await res.json();
      expect(body?.data?.tag?.state).toBe("pending");
      expect(body?.data?.tag?.approver?.id).toBe(manager.id);
    } finally {
      await officer.ctx.dispose();
    }
  });

  test("a: the requester sees their row, waiting, with no decide control", async ({ page }) => {
    test.skip(!labelId, "setup skipped — see its reason");
    test.setTimeout(120_000);
    await signIn(page, P.tagger);
    await page.goto(appPath("/approvals"));
    await page.getByTestId("tab-approvals-mine").click();

    const row = page.locator(`[data-testid="replacement-row"][data-tag="${tagNumber}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(row.getByTestId("replacement-state-pill")).toHaveText("Waiting");
    // The refusal is in the model; the screen simply does not offer it —
    // the same two-sided rule spec 35 pins for movement rows.
    await expect(row.getByTestId("button-approve-replacement")).toHaveCount(0);
    await expect(row.getByTestId("button-reject-replacement")).toHaveCount(0);
    const note = row.getByTestId("replacement-not-yours");
    await expect(note).toBeVisible();
    await expect(note).toContainText("You asked for this replacement");
  });

  test("b: the named approver finds it waiting on them, and approves it", async ({ page }) => {
    test.skip(!labelId, "setup skipped — see its reason");
    test.setTimeout(120_000);
    await signIn(page, P.asset_manager);
    await page.goto(appPath("/approvals"));

    // The default tab IS "Waiting on me" — the screen the owner could not
    // find the request on. It must be here without a single click.
    const row = page.locator(`[data-testid="replacement-row"][data-tag="${tagNumber}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });

    await row.getByTestId("button-approve-replacement").click();
    const dialog = page.getByTestId("dialog-approve-replacement");
    await expect(dialog).toBeVisible();
    await dialog.getByTestId("button-confirm-approve-replacement").click();
    await expect(dialog).toBeHidden({ timeout: 20_000 });

    // Decided, so no longer pending, so gone from the waiting tab.
    await expect(row).toHaveCount(0, { timeout: 20_000 });

    // And on the Decided tab, outcome "approved" → the label's own
    // `scrapped`, read as replaced, naming the successor.
    await page.getByTestId("tab-approvals-decided").click();
    await page.getByTestId("select-decided-state").selectOption("approved");
    const decided = page.locator(`[data-testid="replacement-row"][data-tag="${tagNumber}"]`);
    await expect(decided).toBeVisible({ timeout: 20_000 });
    await expect(decided).toHaveAttribute("data-state", "scrapped");
    await expect(decided.getByTestId("replacement-state-pill")).toHaveText("Approved — replaced");
    await expect(decided.getByTestId("replacement-decision")).toContainText("replaced by");
    // Handoff 61: the successor is the reprint under the SAME number, said
    // with its count — the number alone would not tell the prints apart.
    await expect(decided.getByTestId("replacement-reprint")).toHaveText("reprint 1 under the same number");
  });

  test("c: the auditor reads the queue and is offered no control at all", async ({ page }) => {
    test.skip(!labelId, "setup skipped — see its reason");
    test.setTimeout(120_000);
    await signIn(page, P.auditor);
    await page.goto(appPath("/approvals"));

    // All pending: the section renders — rows or its own empty sentence,
    // never an error and never a stopped spinner (report 49's rule).
    await page.getByTestId("tab-approvals-pending").click();
    await expect(
      page.getByTestId("replacements-list").or(page.getByTestId("replacements-empty")),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("replacements-error")).toHaveCount(0);

    // Decided (any outcome) carries the row this run decided — visible to
    // the auditor, and inert: reading what is waiting and on whom is the
    // auditor's job, deciding any of it is not.
    await page.getByTestId("tab-approvals-decided").click();
    const row = page.locator(`[data-testid="replacement-row"][data-tag="${tagNumber}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-testid="replacements-list"] [data-testid="button-approve-replacement"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="replacements-list"] [data-testid="button-reject-replacement"]')).toHaveCount(0);
  });

  test("d: a tagging-only token is refused the route, and told which scope it lacks", async () => {
    test.skip(Object.keys(P).length === 0, `no ${CREDS} — run scripts/demo_personas.sh ${TENANT} seed`);
    test.skip(!P.tag_unit, `persona "tag_unit" missing from ${CREDS}`);

    // §1c as a measurement: the Tag-Issuing Unit holds `tagging:write` and
    // nothing else, so it cannot read either replacement route — the
    // pairing with Asset User is what brings `assets:read`. The refusal
    // must NAME the missing scope, or the next person rediscovers the
    // pairing requirement as a bug.
    const unit = await apiSession(P.tag_unit);
    try {
      const res = await unit.ctx.get("/api/v1/tags/replacements", {
        headers: { Authorization: `Bearer ${unit.token}`, Accept: "application/json" },
      });
      expect(res.status(), `tagging-only read of /tags/replacements → ${res.status()}`).toBe(403);
      const body = await res.json();
      expect(body?.error?.details?.required_scopes, "the refusal names what is missing")
        .toContain("assets:read");
    } finally {
      await unit.ctx.dispose();
    }
  });

  test("e: the requester comes back and reads the outcome of their own request", async ({ page }) => {
    test.skip(!labelId, "setup skipped — see its reason");
    test.setTimeout(120_000);
    await signIn(page, P.tagger);
    await page.goto(appPath("/approvals"));
    await page.getByTestId("tab-approvals-mine").click();

    // "Raised by me" is every state, because the requester's question is
    // not "what is pending", it is "what happened to mine" — the question
    // the handoff built the new route to answer.
    const row = page.locator(`[data-testid="replacement-row"][data-tag="${tagNumber}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(row).toHaveAttribute("data-state", "scrapped");
    await expect(row.getByTestId("replacement-state-pill")).toHaveText("Approved — replaced");
    await expect(row.getByTestId("replacement-decision")).toContainText("replaced by");
    await expect(row.getByTestId("replacement-reprint")).toHaveText("reprint 1 under the same number");
  });
});
