import { test, expect, type Page } from "../fixtures/test";
import { ApiClient } from "../fixtures/api";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 39, in a browser: the tagger confirms the label is on the asset.
 *
 * `POST /api/v1/assets/<id>/tag-affixed` has carried the control since
 * handoff 03 — the number READ OFF the label is compared with the tag Cadra
 * issued, and a mismatch is refused in a sentence naming both — and nothing
 * in the app had ever called it. This spec drives the station's new
 * *Confirm affixed* control and reads THE ROW after each step, because the
 * screen is not the record.
 *
 * The one assertion that matters more than the rest is the first: when the
 * dialog OPENS its markup does not contain the expected number, in any
 * form, and nothing behind it shows it either. If it did, the check would
 * compare Cadra's number with Cadra's number and manufacture evidence that
 * a human verified something no human verified. (After a WRONG scan the
 * server's refusal names the issued number — the handoff requires that
 * sentence verbatim — and the second test asserts exactly that sentence.)
 *
 * Set `E2E_SHOTS=<dir>` to also save the screenshots report 39 refers to.
 */

const SCAN_INPUT = /NRS-LT|tag/i;

async function scan(page: Page, query: string) {
  const input = page.getByPlaceholder(SCAN_INPUT).first();
  await input.fill(query);
  await page.getByRole("button", { name: "Lookup" }).click();
}

async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/${name}.png`, fullPage: false });
}

/** An asset of our own with a serial of its own. A tag is minted on creation
 *  (`nrs.asset.create`), so the response carries its number under `tag`, and
 *  the label starts `issued` — affixable, since there is no print
 *  precondition. */
async function createTaggedAsset(api: ApiClient, label: string) {
  const name = markedName(label);
  const serial = `E2E-SN-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const asset = await api.createAsset(name, { serial_number: serial });
  recordCreated({ kind: "asset", id: asset.id, name });
  return { id: asset.id as number, name, serial, tag: asset.tag as string | null, code: asset.asset_code as string };
}

/** The scan box → the card → the dialog, with the card proved to offer the
 *  control first. */
async function openConfirmDialog(page: Page, tag: string) {
  await scan(page, tag);
  await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by tag/i, { timeout: 20_000 });
  await expect(page.getByTestId("button-confirm-affixed")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("button-confirm-affixed").click();
  const dialog = page.getByTestId("dialog-confirm-affixed");
  await expect(dialog).toBeVisible();
  return dialog;
}

// ── The control ──────────────────────────────────────────────────────────────

test("the dialog never shows the expected number; the wrong number is refused in the server's words; the right one records who and when", async ({ page, api }) => {
  const a = await createTaggedAsset(api, "Affix");
  test.skip(!a.tag, "the created asset carries no tag number, so there is nothing to confirm");

  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await scan(page, a.tag!);
  await expect(page.getByTestId("lookup-matched-by")).toHaveText(/found by tag/i, { timeout: 20_000 });

  // The card says where the label is and that it is not yet on the asset.
  const state = page.getByTestId("tag-label-state");
  await expect(state).toBeVisible({ timeout: 20_000 });
  await expect(state).toContainText(/not yet confirmed/i);
  await expect(page.getByTestId("tag-affixed-state")).toHaveCount(0);
  await shot(page, "01-card-offers-confirm");

  await page.getByTestId("button-confirm-affixed").click();
  const dialog = page.getByTestId("dialog-confirm-affixed");
  await expect(dialog).toBeVisible();

  // 1 · THE EXPECTED NUMBER IS NOWHERE IN THE DIALOG — not as text, not as a
  //     value, not as a placeholder, not in any attribute.
  const markup = await dialog.evaluate((el) => el.outerHTML);
  expect(markup, "the dialog's markup must not carry the expected tag number").not.toContain(a.tag!);
  for (const input of await dialog.locator("input").all()) {
    expect(await input.inputValue(), "every field starts empty").toBe("");
  }
  // …and the page behind it has covered its own copies of the number: the
  //     card's line is replaced, the scan box (which IS the number when the
  //     lookup was by tag) is emptied, and the whole page is blurred.
  await expect(page.getByTestId("lookup-tag-number-hidden")).toBeVisible();
  await expect(page.getByTestId("lookup-tag-number")).not.toContainText(a.tag!);
  await expect(page.getByTestId("scan-box")).toHaveValue("");
  await expect(page.getByTestId("barcode-station")).toHaveAttribute("data-blurred", "true");
  // Nothing to confirm until something is scanned.
  await expect(dialog.getByTestId("button-submit-affixed")).toBeDisabled();
  await shot(page, "02-dialog-open-no-number");

  // 2 · THE WRONG TAG. The server's sentence, as written, and the input kept.
  const wrong = `${a.tag}-9`;
  await dialog.getByTestId("input-affix-tag-number").fill(wrong);
  await dialog.getByTestId("button-submit-affixed").click();
  const refusal = dialog.getByTestId("affix-refusal");
  await expect(refusal).toBeVisible({ timeout: 20_000 });
  await expect(refusal).toContainText(
    `Scanned tag ${wrong} does not match the tag issued for this asset (${a.tag}). `
    + `The label on the asset is not the one Cadra issued for it.`,
  );
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(wrong);
  await shot(page, "03-wrong-tag-refused");
  // The row is untouched.
  let read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");
  expect(read.tagging.affixed_at).toBeNull();
  expect(read.tagging.is_tagged).toBe(false);

  // 3 · THE WRONG SERIAL, with the right tag: refused too, and still nothing
  //     written. The sentence names both serials.
  await dialog.getByTestId("input-affix-tag-number").fill(a.tag!);
  await dialog.getByTestId("input-affix-serial").fill(`${a.serial}-NOT`);
  await dialog.getByTestId("button-submit-affixed").click();
  await expect(refusal).toContainText(`Scanned serial ${a.serial}-NOT does not match the serial on this asset (${a.serial})`, { timeout: 20_000 });
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).not.toBe("affixed");

  // 4 · THE RIGHT LABEL, the right serial, and who fitted it.
  await dialog.getByTestId("input-affix-serial").fill(a.serial);
  await dialog.getByTestId("input-affix-fitted-by").fill("E2E Tagger");
  await dialog.getByTestId("button-submit-affixed").click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });

  // THE ROW.
  const me = await api.whoami();
  read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.label_state).toBe("affixed");
  expect(read.tagging.is_tagged).toBe(true);
  expect(read.tagging.affixed_by_name).toBe("E2E Tagger");
  expect(read.tagging.affixed_by?.id, "affixed_by is the user behind the token").toBe(me.id);
  expect(read.tagging.affixed_at).toBeTruthy();

  // And the card, in the SAME session: the record instead of the button.
  const affixed = page.getByTestId("tag-affixed-state");
  await expect(affixed).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("tag-affixed-by")).toHaveText("E2E Tagger");
  await expect(page.getByTestId("button-confirm-affixed")).toHaveCount(0);
  await expect(page.getByTestId("lookup-tag-number")).toHaveText(a.tag!);
  // The scan box got its query back when the dialog closed.
  await expect(page.getByTestId("scan-box")).toHaveValue(a.tag!);
  await expect(page.getByTestId("barcode-station")).not.toHaveAttribute("data-blurred", "true");
  await shot(page, "04-card-shows-affixed");
});

test("confirming the same label twice says already confirmed, and the original record stands", async ({ page, context, api }) => {
  const a = await createTaggedAsset(api, "AffixTwice");
  test.skip(!a.tag, "the created asset carries no tag number");

  // Two screens look the asset up before either confirms — two taggers, or
  // one tagger's two tabs. The second screen is stale by the time it acts.
  const other = await context.newPage();
  for (const p of [page, other]) {
    await gotoApp(p, "/tools/barcode");
    await expectShell(p);
    await scan(p, a.tag!);
    await expect(p.getByTestId("button-confirm-affixed")).toBeVisible({ timeout: 20_000 });
  }

  // The first confirms.
  await page.getByTestId("button-confirm-affixed").click();
  const d1 = page.getByTestId("dialog-confirm-affixed");
  await d1.getByTestId("input-affix-tag-number").fill(a.tag!);
  await d1.getByTestId("input-affix-fitted-by").fill("FIRST Tagger");
  await d1.getByTestId("button-submit-affixed").click();
  await expect(d1).toBeHidden({ timeout: 20_000 });
  const first = (await api.get<any>(`/api/v1/assets/${a.id}`)).tagging;
  expect(first.label_state).toBe("affixed");
  expect(first.affixed_by_name).toBe("FIRST Tagger");

  // The second confirms the same label from the stale screen. Not an error
  // — nothing went wrong — and not "done" — nothing was done.
  await other.getByTestId("button-confirm-affixed").click();
  const d2 = other.getByTestId("dialog-confirm-affixed");
  await d2.getByTestId("input-affix-tag-number").fill(a.tag!);
  await d2.getByTestId("input-affix-fitted-by").fill("SECOND Tagger");
  await d2.getByTestId("button-submit-affixed").click();
  const already = d2.getByTestId("affix-already");
  await expect(already).toBeVisible({ timeout: 20_000 });
  await expect(already).toContainText(/already confirmed on/i);
  await expect(already).toContainText("FIRST Tagger");
  await expect(d2.getByTestId("affix-refusal")).toHaveCount(0);
  await shot(other, "05-already-confirmed");

  // THE ROW: the original date and the original name, unchanged.
  const second = (await api.get<any>(`/api/v1/assets/${a.id}`)).tagging;
  expect(second.affixed_at).toBe(first.affixed_at);
  expect(second.affixed_by_name).toBe("FIRST Tagger");
  expect(second.affixed_by?.id).toBe(first.affixed_by?.id);

  await d2.getByTestId("button-close-affix").click();
  await expect(d2).toBeHidden();
  await expect(other.getByTestId("tag-affixed-state")).toBeVisible({ timeout: 20_000 });
  await expect(other.getByTestId("tag-affixed-by")).toHaveText("FIRST Tagger");
  await other.close();
});

// ── A label that is no longer the one issued ────────────────────────────────

test("a label replaced since the card was loaded is refused: while pending there is no active tag, and once scrapped the number in hand is not the tag now issued", async ({ page, api }) => {
  const second = await ApiClient.forServiceCredential();
  test.skip(!second, "set E2E_CLIENT_ID / E2E_CLIENT_SECRET — the model refuses "
                   + "self-approval, so one identity cannot replace a label");
  const me = await api.whoami();
  test.skip(!me?.id, "cannot resolve the browser user's id from /auth/whoami");

  const a = await createTaggedAsset(api, "AffixScrapped");
  test.skip(!a.tag, "the created asset carries no tag number");
  const found = await api.get<any>("/api/v1/barcode/lookup", { query: a.tag! });
  const oldTagId = found.tag_id as number;
  expect(oldTagId).toBeTruthy();

  // The tagger's screen, loaded while the label is still active.
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  const dialog = await openConfirmDialog(page, a.tag!);

  // 1 · Meanwhile somebody asks for a replacement: the label is PENDING and
  //     the asset has no active tag to confirm.
  await second!.post(`/api/v1/tags/${oldTagId}/request-replacement`, {
    reason: "damaged", notes: "e2e — label faded", approver_id: me.id,
  });
  await dialog.getByTestId("input-affix-tag-number").fill(a.tag!);
  await dialog.getByTestId("button-submit-affixed").click();
  const refusal = dialog.getByTestId("affix-refusal");
  await expect(refusal).toBeVisible({ timeout: 20_000 });
  await expect(refusal).toContainText("This asset has no active tag to confirm");

  // 2 · Then the replacement is approved: the old label is SCRAPPED and a
  //     new number issued. The label in the tagger's hand is the old one.
  const approved = await api.post<any>(`/api/v1/tags/${oldTagId}/approve-replacement`, {});
  const newNumber = approved.new_tag.tag_number as string;
  expect(newNumber).not.toBe(a.tag);
  await expect(dialog.getByTestId("input-affix-tag-number")).toHaveValue(a.tag!);
  await dialog.getByTestId("button-submit-affixed").click();
  await expect(refusal).toContainText(
    `Scanned tag ${a.tag} does not match the tag issued for this asset (${newNumber}). `
    + `The label on the asset is not the one Cadra issued for it.`,
    { timeout: 20_000 },
  );
  await shot(page, "06-scrapped-label-refused");

  // THE ROWS: the scrapped label stays scrapped, the new one is not affixed.
  const old = await api.get<any>(`/api/v1/tags/${oldTagId}`);
  expect(old.state).toBe("scrapped");
  expect(old.label_state).toBe("scrapped");
  const read = await api.get<any>(`/api/v1/assets/${a.id}`);
  expect(read.tagging.tag_number).toBe(newNumber);
  expect(read.tagging.label_state).not.toBe("affixed");
  expect(read.tagging.is_tagged).toBe(false);
});
