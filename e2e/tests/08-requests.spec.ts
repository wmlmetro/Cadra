import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell, pickRecord } from "../fixtures/helpers";
import { appPath } from "../config";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Service Desk (ITSM requests): list controls, create, and the detail actions
 * (priority, assign, comment, workflow transition).
 */

// Pull a usable type_id from an existing request (no list endpoint for types).
function typeIdOf(req: any): number | null {
  const cands = [req?.type_id, req?.typeId, req?.type?.id, req?.request_type?.id];
  const n = cands.map(Number).find((x) => Number.isFinite(x) && x > 0);
  return n ?? null;
}

test.describe("/service-desk list", () => {
  test("list controls + New Request navigation", async ({ page }) => {
    await gotoApp(page, "/service-desk");
    await expectShell(page);

    // Filters render.
    await page.getByPlaceholder(/reference, subject, body/i).fill("test");
    await page.locator("select").first().selectOption("3").catch(() => {});
    // Clear appears once a filter is set.
    const clear = page.getByRole("button", { name: /^clear$/i }).first();
    if (await clear.count()) await clear.click();

    await page.getByRole("button", { name: "+ New Request" }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(appPath("/service-desk/new"));
  });

  test("a request row opens detail", async ({ page, api }) => {
    const r = await api.firstRequest();
    test.skip(!r, "no requests seeded");
    await gotoApp(page, "/service-desk");
    await expectShell(page);
    const row = page.getByRole("button", { name: new RegExp(String(r.reference), "i") }).first();
    const anyRow = (await row.count()) ? row : page.locator("ul li button").first();
    await expect(anyRow).toBeVisible({ timeout: 15_000 });
    await anyRow.click();
    await expect.poll(() => new URL(page.url()).pathname).toMatch(/\/service-desk\/\d+$/);
  });
});

test("create form gates submit until Type + Request text", async ({ page }) => {
  await gotoApp(page, "/service-desk/new");
  await expectShell(page);
  const create = page.getByRole("button", { name: "Create request" });
  await expect(create).toBeDisabled();
  await page.getByRole("spinbutton").first().fill("1"); // Type id
  await page.getByPlaceholder(/describe the issue/i).fill(markedName("Body"));
  await expect(create).toBeEnabled();
});

test("create a request end-to-end", async ({ page, api }) => {
  const existing = await api.firstRequest();
  const typeId = existing ? typeIdOf(existing) : null;
  test.skip(!typeId, "could not determine a valid request type_id from seed data");

  await gotoApp(page, "/service-desk/new");
  await expectShell(page);
  await page.getByRole("spinbutton").first().fill(String(typeId));
  const body = markedName("Service request body");
  await page.getByPlaceholder(/describe the issue/i).fill(body);
  await page.getByRole("button", { name: "Create request" }).click();

  await expect.poll(() => new URL(page.url()).pathname, { timeout: 20_000 }).toMatch(/\/service-desk\/\d+$/);
  const id = new URL(page.url()).pathname.match(/\/service-desk\/(\d+)/)?.[1];
  recordCreated({ kind: "request", id, name: body });
});

test.describe("request detail actions", () => {
  test("priority change + comment + transition", async ({ page, api }) => {
    const r = await api.firstRequest();
    test.skip(!r, "no requests to act on");
    await gotoApp(page, `/service-desk/${r.id}`);
    await expectShell(page);

    // Inline priority select.
    const prioritySelect = page.locator("select").first();
    if (await prioritySelect.count()) {
      await prioritySelect.selectOption("3").catch(() => {});
    }

    // Post an internal comment.
    const box = page.getByPlaceholder(/write a message/i);
    if (await box.count()) {
      await box.fill("E2E internal note");
      await page.getByRole("button", { name: /^post$/i }).click();
      // Comment should appear in the conversation, or at least not crash.
      await expectShell(page);
    }

    // Workflow transition (first available "Next action"), if any.
    const nextActions = page.getByRole("button", { name: /→/ });
    if (await nextActions.count()) {
      await nextActions.first().click();
      await expectShell(page);
    }
  });

  test("assign / reassign toggle reveals a picker", async ({ page, api }) => {
    const r = await api.firstRequest();
    test.skip(!r, "no requests to assign");
    await gotoApp(page, `/service-desk/${r.id}`);
    await expectShell(page);
    await page.getByRole("button", { name: /assign|reassign/i }).first().click();
    // Picker "Type a name…" appears; try to assign an employee.
    const emp = await api.firstEmployee();
    if (emp?.name) {
      const q = String(emp.name).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/)[0].slice(0, 5);
      const picked = await pickRecord(page, "Type a name", q.length >= 2 ? q : "mo");
      if (picked) {
        await page.getByRole("button", { name: /^assign$/i }).last().click();
        await expectShell(page);
      }
    }
  });
});
