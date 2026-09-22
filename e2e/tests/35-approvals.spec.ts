import { test, expect } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Nobody moves an asset alone — the journey, clicked. Handoff 35 §E.
 *
 * WHY THIS FILE EXISTS RATHER THAN MORE API TESTS
 * -----------------------------------------------
 * The owner's standing instruction: *"Acting from a cold start proves only
 * the cold start. A screen is proved by the flow a person actually takes —
 * list, asset, act, back to the list — in ONE session, reading the row in
 * Postgres."* Handoff 29's headline fix did not hold in that flow, and its
 * harness could not see it because it loaded every page fresh.
 *
 * So the first test below is one session: open the asset, raise a request,
 * walk to the queue, approve it, walk back, and check the asset page is
 * telling the truth at every step — with the server's own row read back
 * between steps rather than the screen being trusted.
 *
 * TWO IDENTITIES, AND WHY THAT IS NOT OPTIONAL
 * --------------------------------------------
 * `_assert_may_decide` refuses self-approval in the MODEL — under `sudo()`
 * and as SUPERUSER. This suite logs in as one user (`admin`), so it
 * physically cannot approve what it raises, and a spec that tried would be
 * asserting the refusal rather than the journey.
 *
 * The second identity is a SERVICE CREDENTIAL, which since handoff 08 has
 * its own `res.users`. It raises; `admin` approves in the browser. That is
 * the real two-person flow. It defaults to nothing (handoff 17's rule), so
 * without `E2E_CLIENT_ID` / `E2E_CLIENT_SECRET` the approve journeys SKIP
 * with a reason naming the variables — and everything that one identity can
 * prove still runs.
 */

async function createAsset(api: ApiClient, label: string, extra: Record<string, unknown> = {}) {
  const name = markedName(label);
  const asset = await api.createAsset(name, extra);
  recordCreated({ model: "nrs.asset", id: asset.id, name });
  return asset.id as number;
}

/** The tenant's own answer, asked every time. Absent means REQUIRED. */
async function requiresApproval(api: ApiClient) {
  return api.approvalRequired();
}

// ── The switch ───────────────────────────────────────────────────────────────

test("the register says whether it needs a second person, and an unset tenant says yes", async ({ api }) => {
  const probe = await api.probe("/api/v1/settings/approvals");
  expect(probe.ok, "every signed-in user who can see an asset must be able to read this").toBeTruthy();
  const d = probe.body?.data;
  expect(typeof d?.required).toBe("boolean");
  expect(d?.parameter).toBe("cadra.approval.required");
  // `configured` is the fact `required` alone cannot carry: "nobody has ever
  // set this" and "somebody deliberately turned it on" are the same
  // behaviour and very different facts.
  expect(typeof d?.configured).toBe("boolean");
  expect(d?.default_when_unset, "absent must mean required").toBe(true);
  if (!d?.configured) {
    expect(d?.required, "an unconfigured tenant requires approval").toBe(true);
    expect(d?.setting).toBeNull();
  }
});

// ── Raising: nothing happens to the asset ────────────────────────────────────

test("raising a request changes nothing about the asset (API)", async ({ api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");

  const id = await createAsset(api, "ApprRaise", { location_id: locs[0].id });
  const before = await api.get(`/api/v1/assets/${id}`);
  const raised = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id, reason: "e2e raise",
  });

  expect(raised?.pending_approval).toBe(true);
  expect(raised?.request?.reference).toMatch(/^CR\//);
  expect(raised?.request?.state).toBe("pending");
  // WHO IS ASKED is in the response; WHO CLICKED is not, because nobody has.
  expect(raised?.request?.approver?.id).toBe(approver!.id);
  expect(raised?.movement_id).toBeNull();
  expect(raised?.transfer).toBeNull();

  // The asset, read back from the server — not the echo in the response.
  const after = await api.get(`/api/v1/assets/${id}`);
  expect(after?.current_location?.id).toBe(before?.current_location?.id);
  expect(after?.state).toBe(before?.state);

  // And no append-only row was written. This is the single most important
  // assertion in the file: a movement written when somebody merely ASKED
  // would be a permanent record of a move that never happened, in the table
  // whose whole value is that nobody can correct it.
  const history = await api.get<any>(`/api/v1/assets/${id}/history`);
  const events = (history?.events ?? []) as any[];
  expect(events.filter(e => /moved|placed/i.test(String(e.type ?? e.kind ?? ""))).length,
         "no movement may be recorded before approval").toBe(0);
});

test("a second request for the same asset is refused, naming the one in the way", async ({ api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");

  const id = await createAsset(api, "ApprDup", { location_id: locs[0].id });
  const first = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id,
  });
  let refused = "";
  try {
    await api.post(`/api/v1/assets/${id}/move`, {
      to_location_id: locs[0].id, approver_id: approver!.id,
    });
  } catch (e) { refused = String(e); }
  expect(refused).toMatch(/HTTP 409/);
  // It names the blocker, because a person who pressed Move deserves the
  // reference of the thing in their way rather than a constraint name.
  expect(refused).toContain(first.request.reference);
});

test("you cannot ask yourself, and you cannot approve your own request", async ({ api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");
  const me = await api.whoami();
  const myUserId = me?.id;

  const id = await createAsset(api, "ApprSelf", { location_id: locs[0].id });

  // Naming yourself as the approver.
  if (myUserId) {
    let refusedNomination = "";
    try {
      await api.post(`/api/v1/assets/${id}/move`, {
        to_location_id: locs[1].id, approver_id: myUserId,
      });
    } catch (e) { refusedNomination = String(e); }
    expect(refusedNomination).toMatch(/HTTP 400/);
    expect(refusedNomination).toMatch(/yourself/i);
  }

  // Raising properly, then approving it yourself.
  const raised = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id,
  });
  let refusedApproval = "";
  try {
    await api.post(`/api/v1/approvals/${raised.request.id}/approve`, {});
  } catch (e) { refusedApproval = String(e); }
  expect(refusedApproval).toMatch(/HTTP 403/);
  expect(refusedApproval).toMatch(/second person/i);
  // Still pending, still not moved.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[0].id);
});

test("a body that names who decided is refused, not ignored", async ({ api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");
  const id = await createAsset(api, "ApprForge", { location_id: locs[0].id });
  const raised = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id,
  });
  let refused = "";
  try {
    await api.post(`/api/v1/approvals/${raised.request.id}/approve`, { approved_by_id: approver!.id });
  } catch (e) { refused = String(e); }
  expect(refused).toMatch(/HTTP 400/);
  expect(refused).toMatch(/cannot be supplied|credential/i);
});

// ── The queue screen ─────────────────────────────────────────────────────────

test("the approvals queue renders and shows what is waiting (UI)", async ({ page, api }) => {
  await gotoApp(page, "/approvals");
  await expectShell(page);
  // Either rows or the empty state — never a blank screen and never an error.
  const list = page.getByTestId("approvals-list");
  const empty = page.getByTestId("approvals-empty");
  await expect(list.or(empty)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("approvals-error")).toBeHidden();
});

test("a request I raised offers me no Approve button (UI)", async ({ page, api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const approver = await api.anApprover();
  test.skip(!approver, "no eligible approver other than the caller");
  const id = await createAsset(api, "ApprMine", { location_id: locs[0].id });
  const raised = await api.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: approver!.id, reason: "e2e mine",
  });

  await gotoApp(page, "/approvals");
  await expectShell(page);
  await page.getByTestId("tab-approvals-mine").click();
  const row = page.locator(`[data-testid="approval-row"][data-reference="${raised.request.reference}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  // The refusal is in the model; the screen simply does not offer it. Both
  // matter, and this asserts the second — report 30's lesson was that a
  // hidden button is not a control, not that a control needs no button.
  await expect(row.getByTestId("button-approve")).toHaveCount(0);
  // Withdrawing my own is offered, because that is mine to do.
  await expect(row.getByTestId("button-withdraw")).toBeVisible();
});

// ── The whole journey, in one session ────────────────────────────────────────

test("list → asset → request → queue → approve → back, in one session", async ({ page, api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET — the model refuses "
                   + "self-approval, so one identity cannot walk this journey");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");

  // The SERVICE credential is the requester; `admin`, in the browser, is the
  // approver. Two people, which is the whole point of the feature.
  const me = await api.whoami();
  const adminUserId = me?.id;
  test.skip(!adminUserId, "cannot resolve the browser user's id from /auth/whoami");

  const id = await createAsset(api, "ApprJourney", { location_id: locs[0].id });
  const raised = await second!.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: adminUserId, reason: "e2e journey",
  });
  expect(raised?.pending_approval).toBe(true);
  const reference = raised.request.reference as string;

  // 1 · The asset page says a request is waiting, rather than leaving
  //     somebody to guess why Move is behaving differently (§E).
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  const banner = page.getByTestId("asset-pending-approval");
  await expect(banner).toBeVisible({ timeout: 20_000 });
  await expect(banner).toContainText(reference);
  await expect(page.getByTestId("button-move")).toBeDisabled();

  // 2 · Walk to the queue THROUGH THE APP — not a fresh load. The cache the
  //     app keeps is exactly what handoff 29 found lying.
  await banner.getByTestId("link-asset-approval-queue").click();
  await expect(page).toHaveURL(/\/approvals/, { timeout: 20_000 });
  const row = page.locator(`[data-testid="approval-row"][data-reference="${reference}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  // It says what it is now and what it would become.
  await expect(row.getByTestId("approval-change-from")).toContainText(String(locs[0].name).slice(0, 12));
  await expect(row.getByTestId("approval-change-to")).toContainText(String(locs[1].name).slice(0, 12));

  // 3 · Approve it, for real.
  await row.getByTestId("button-approve").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("button-confirm-approval-approve").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  // 4 · THE ROW. The server's own record, not the screen.
  await expect
    .poll(async () => (await api.get(`/api/v1/assets/${id}`))?.current_location?.id, { timeout: 20_000 })
    .toBe(locs[1].id);
  const decided = await api.get<any>(`/api/v1/approvals/${raised.request.id}`);
  expect(decided.state).toBe("approved");
  expect(decided.movement_id, "the append-only record is written ON APPROVAL").toBeTruthy();
  // The two fields that must never be the same field.
  expect(decided.decided_by?.id).toBe(adminUserId);
  expect(decided.requested_by?.id).not.toBe(adminUserId);

  // 5 · Back to the asset, in the SAME session. The banner must be gone and
  //     the new location must be on screen — this is the step handoff 29's
  //     harness could not take, and the one that caught `refetchOnMount`.
  await gotoApp(page, `/assets/${id}`);
  await expectShell(page);
  await expect(page.getByTestId("asset-pending-approval")).toBeHidden({ timeout: 20_000 });
  await expect(page.getByTestId("button-move")).toBeEnabled();
});

test("a rejected request leaves the asset alone and tells the requester why", async ({ page, api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET to reject somebody else's request");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const me = await api.whoami();
  const adminUserId = me?.id;
  test.skip(!adminUserId, "cannot resolve the browser user's id");

  const id = await createAsset(api, "ApprReject", { location_id: locs[0].id });
  const raised = await second!.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: adminUserId, reason: "e2e reject",
  });

  await gotoApp(page, "/approvals");
  await expectShell(page);
  const row = page.locator(`[data-testid="approval-row"][data-reference="${raised.request.reference}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.getByTestId("button-reject").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // A reason is REQUIRED — the button is not offered until there is one,
  // and the server refuses without it either way.
  await expect(dialog.getByTestId("button-confirm-approval-reject")).toBeDisabled();
  await dialog.getByTestId("input-approval-reject-reason").fill("E2E — that room is being repurposed");
  await dialog.getByTestId("button-confirm-approval-reject").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  const decided = await api.get<any>(`/api/v1/approvals/${raised.request.id}`);
  expect(decided.state).toBe("rejected");
  expect(decided.decision_reason).toContain("repurposed");
  expect(decided.movement_id, "a rejection records no movement").toBeNull();
  // The asset did not move.
  expect((await api.get(`/api/v1/assets/${id}`))?.current_location?.id).toBe(locs[0].id);
});

// ── The premise ──────────────────────────────────────────────────────────────

test("a request whose asset changed underneath cannot be approved in silence", async ({ api }) => {
  test.skip(!(await requiresApproval(api)), "this tenant does not require approval");
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET — two identities are needed twice over here");
  const locs = await api.twoBuildings();
  test.skip(locs.length < 2, "need two building locations");
  const me = await api.whoami();
  const adminUserId = me?.id;
  test.skip(!adminUserId, "cannot resolve the browser user's id");

  const id = await createAsset(api, "ApprStale", { location_id: locs[0].id });
  // The service credential asks; `admin` is the one who could approve.
  const pending = await second!.post(`/api/v1/assets/${id}/move`, {
    to_location_id: locs[1].id, approver_id: adminUserId, reason: "e2e premise",
  });

  // Now break the premise. Condemning is the cleanest way and also the most
  // important one: disposed is TERMINAL (handoff 30), so an approval applied
  // afterwards would be refused deep in `nrs.asset.write` with the model's
  // words about a write the approver did not know they were making. The
  // premise check exists so they are told what CHANGED instead.
  await api.post(`/api/v1/assets/${id}/condemn`, { reason: "e2e — breaks the premise" });

  let refused = "";
  try {
    await api.post(`/api/v1/approvals/${pending.request.id}/approve`, {});
  } catch (e) { refused = String(e); }
  expect(refused).toMatch(/HTTP 409/);
  expect(refused, "the refusal must say WHAT changed").toMatch(/disposed/i);

  const read = await api.get<any>(`/api/v1/approvals/${pending.request.id}`);
  expect(read.premise_holds).toBe(false);
  expect(read.premise_broken_reason).toMatch(/disposed/i);
  expect(read.state, "a broken premise does not decide the request").toBe("pending");
});
