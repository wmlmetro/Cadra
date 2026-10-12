import { test, expect, type Page } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 38, in a browser: a scanned serial number finds its asset, and a
 * faded tag is replaced by two people.
 *
 * LOOKUP. The station's scan box searched tag number and asset code only, so
 * the serial of a TAGGED asset — the auditor's case — found nothing, while
 * the API documented the parameter as "tag, asset code, or serial number".
 * The first test creates an asset with a serial nobody else has, then scans
 * its tag, its code, its serial, and its serial with a trailing space as a
 * handheld scanner sends it, and reads the "Found by …" badge each time: a
 * lookup that silently changed meaning is how the next false claim gets made.
 *
 * REPLACEMENT. Two identities, as `35-approvals.spec.ts` explains: the model
 * refuses self-approval, this suite logs in as one user (`admin`), so the
 * SERVICE credential asks and `admin` approves in the browser. Without
 * `E2E_CLIENT_ID` / `E2E_CLIENT_SECRET` that journey skips with a reason
 * naming the variables; the lookups still run.
 */

const SCAN_INPUT = /NRS-LT|tag/i;

async function scan(page: Page, query: string) {
  const input = page.getByPlaceholder(SCAN_INPUT).first();
  await input.fill(query);
  await page.getByRole("button", { name: "Lookup" }).click();
}

/** An asset of our own, with a serial no other asset can share. A tag is
 *  minted on creation (`nrs.asset.create` with the default `tag_source`), so
 *  the response carries its number under `tag`. */
async function createSerialAsset(api: ApiClient, label: string) {
  const name = markedName(label);
  const serial = `E2E-SN-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const asset = await api.createAsset(name, { serial_number: serial });
  recordCreated({ kind: "asset", id: asset.id, name });
  return { id: asset.id as number, name, serial, tag: asset.tag as string | null, code: asset.asset_code as string };
}

// ── Lookup ───────────────────────────────────────────────────────────────────

test("tag, asset code, serial and serial-with-trailing-space all find the asset, and say how", async ({ page, api }) => {
  const a = await createSerialAsset(api, "SerialScan");
  test.skip(!a.tag, "the created asset carries no tag number, so the tag scan cannot be proved");

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);

  const badge = page.getByTestId("lookup-matched-by");

  // 1 · The tag.
  await scan(page, a.tag!);
  await expect(badge).toHaveText(/found by tag/i, { timeout: 20_000 });
  await expect(page.getByText(a.name, { exact: false }).first()).toBeVisible();

  // 2 · The asset code. With the receipt gates on, the label is minted at
  //     request-tagging and its number IS the asset code (ruling 4.3: one
  //     identifier), so the code scan resolves at the first rung, the tag —
  //     the pytest twin asserts the same (`test_lookup_by_asset_code_says_so`).
  await scan(page, a.code);
  await expect(badge).toHaveText(a.tag === a.code ? /found by tag/i : /found by asset code/i, { timeout: 20_000 });

  // 3 · The serial of a TAGGED asset — the case that found nothing before.
  await scan(page, a.serial);
  await expect(badge).toHaveText(/found by serial number/i, { timeout: 20_000 });
  await expect(page.getByText(a.name, { exact: false }).first()).toBeVisible();

  // 4 · The serial as a scanner sends it, with a trailing space. The box
  //     trims and the server strips, so it must match the same way.
  await scan(page, `${a.serial} `);
  await expect(badge).toHaveText(/found by serial number/i, { timeout: 20_000 });

  // And the server's own answer, for the record: the field it matched on.
  const byTag = await api.get<any>("/api/v1/barcode/lookup", { query: a.tag! });
  expect(byTag.matched_by).toBe("tag_number");
  const bySerial = await api.get<any>("/api/v1/barcode/lookup", { query: a.serial });
  expect(bySerial.matched_by).toBe("serial_number");
  expect(bySerial.asset_id).toBe(a.id);
  expect(bySerial.tagged).toBe(true);
});

test("a serial nobody has is a miss that says so, not an error page", async ({ page }) => {
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await scan(page, `E2E-NO-SUCH-SERIAL-${Date.now()}`);
  await expect(page.getByTestId("lookup-miss")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("lookup-matched-by")).toHaveCount(0);
});

// ── Replacement, two people ──────────────────────────────────────────────────

test("service credential asks, admin approves in the browser: old scrapped, new minted, chain intact", async ({ page, api }) => {
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET — the model refuses "
                   + "self-approval, so one identity cannot walk this journey");
  const me = await api.whoami();
  const adminUserId = me?.id;
  test.skip(!adminUserId, "cannot resolve the browser user's id from /auth/whoami");

  const a = await createSerialAsset(api, "TagReplace");
  test.skip(!a.tag, "the created asset carries no tag number to replace");
  const found = await api.get<any>("/api/v1/barcode/lookup", { query: a.tag! });
  const oldTagId = found.tag_id as number;
  expect(oldTagId).toBeTruthy();

  // 1 · Somebody else asks, naming admin.
  const raised = await second!.post(`/api/v1/tags/${oldTagId}/request-replacement`, {
    reason: "damaged", notes: "e2e — label faded", approver_id: adminUserId,
  });
  expect(raised?.pending_approval).toBe(true);
  expect(raised?.tag?.state).toBe("pending");
  expect(raised?.tag?.approver?.id).toBe(adminUserId);
  expect(raised?.tag?.replacement_reason).toBe("damaged");

  // A pending tag's NUMBER no longer resolves — by design — but the asset
  // code does, and the card shows the pending label.
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await scan(page, a.code);
  await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by asset code/i, { timeout: 20_000 });
  const panel = page.getByTestId("tag-pending-panel");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toContainText(/damaged/i);

  // 2 · admin approves it, in the browser, from that panel.
  await panel.getByTestId("button-approve-replacement").click();
  const dialog = page.getByTestId("dialog-approve-replacement");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("button-confirm-approve-replacement").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  // 3 · THE ROW. The server's record, not the screen.
  const old = await api.get<any>(`/api/v1/tags/${oldTagId}`);
  expect(old.state).toBe("scrapped");
  expect(old.approved_by?.id).toBe(adminUserId);
  expect(old.requested_by?.id).not.toBe(adminUserId);
  expect(old.replacement_reason).toBe("damaged");
  expect(old.replaced_by?.id, "the old label names its successor").toBeTruthy();
  const fresh = await api.get<any>(`/api/v1/tags/${old.replaced_by.id}`);
  expect(fresh.state).toBe("active");
  expect(fresh.asset?.id).toBe(a.id);
  expect(fresh.replaces?.id).toBe(oldTagId);
  // The old number must never come back.
  expect(fresh.tag_number).not.toBe(a.tag);

  // 4 · And the screen, in the SAME session, now shows the new number and
  //     scanning the OLD number is a miss.
  await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by tag/i, { timeout: 20_000 });
  await expect(page.getByText(fresh.tag_number, { exact: false }).first()).toBeVisible();
  await scan(page, a.tag!);
  await expect(page.getByTestId("lookup-miss")).toBeVisible({ timeout: 20_000 });
});

test("a rejection needs a reason and sends the label back to active", async ({ page, api }) => {
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET to reject somebody else's request");
  const me = await api.whoami();
  const adminUserId = me?.id;
  test.skip(!adminUserId, "cannot resolve the browser user's id");

  const a = await createSerialAsset(api, "TagReject");
  test.skip(!a.tag, "the created asset carries no tag number to replace");
  const found = await api.get<any>("/api/v1/barcode/lookup", { query: a.tag! });
  const tagId = found.tag_id as number;
  await second!.post(`/api/v1/tags/${tagId}/request-replacement`, {
    reason: "other", approver_id: adminUserId,
  });

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const row = page.locator(`[data-testid="pending-replacement-row"][data-tag="${a.tag}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.getByTestId("button-reject-replacement").click();
  const dialog = page.getByTestId("dialog-reject-replacement");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("button-confirm-reject-replacement")).toBeDisabled();
  await dialog.getByTestId("input-reject-reason").fill("E2E — the label reads fine");
  await dialog.getByTestId("button-confirm-reject-replacement").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  const read = await api.get<any>(`/api/v1/tags/${tagId}`);
  expect(read.state).toBe("active");
  expect(read.rejected_by?.id).toBe(adminUserId);
  expect(read.decision_reason).toContain("reads fine");
  expect(read.replaced_by).toBeNull();
  await expect(row).toBeHidden({ timeout: 20_000 });
});
