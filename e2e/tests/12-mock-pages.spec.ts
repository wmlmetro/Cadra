import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell, hasMockBanner } from "../fixtures/helpers";

/**
 * Mock-only surfaces (Fleet, Staff Bus, Identity) render read-only sample data
 * and some controls are intentionally inert. We assert they render (no crash)
 * and DOCUMENT the mock-banner + known non-functional-by-design controls as
 * KNOWN-STUB annotations — not failures. (The "Showing mock data" banner only
 * appears when the app is in mock mode; with a live session it may be absent,
 * so its presence is recorded, not asserted.)
 */

async function annotateMock(page: any, label: string) {
  const banner = await hasMockBanner(page);
  test.info().annotations.push({
    type: "known-stub",
    description: `${label}: mock-data banner present=${banner}. Read-only sample data by design.`,
  });
}

test("Fleet page renders (mock)", async ({ page }) => {
  await gotoApp(page, "/fleet");
  await expectShell(page);
  await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  await annotateMock(page, "Fleet");
});

test("Fleet detail renders (mock)", async ({ page }) => {
  await gotoApp(page, "/fleet/1"); // mock detail resolves by id
  await expectShell(page);
  await expect(page.getByText(/^404$/).first()).toHaveCount(0);
});

test("Staff Bus renders with inert Approve/Reject stubs", async ({ page }) => {
  await gotoApp(page, "/fleet/staff-bus");
  await expectShell(page);
  await annotateMock(page, "StaffBus");
  // Tabs schedule/bookings/routes/fuel.
  for (const tab of ["Schedule", "Bookings", "Routes", "Fuel"]) {
    const t = page.getByRole("button", { name: new RegExp(`^${tab}$`, "i") }).first();
    if (await t.count()) await t.click();
  }
  // Approve/Reject exist but are stubs — presence documented, no behaviour asserted.
  const approve = page.getByRole("button", { name: /^approve$/i }).first();
  test.info().annotations.push({
    type: "known-stub",
    description: `StaffBus Approve/Reject present=${await approve.count()} — inert by design.`,
  });
  await expectShell(page);
});

test("Identity (clearance) renders (mock)", async ({ page }) => {
  await gotoApp(page, "/hr/identity");
  await expectShell(page);
  await expect(page.getByText(/^404$/).first()).toHaveCount(0);
  await annotateMock(page, "Identity");
});

test("the top bar offers no dead controls, and names who is signed in", async ({ page }) => {
  // This test used to ASSERT the dead bell: it clicked a button with no
  // handler and a permanent unread dot, confirmed nothing crashed, and
  // annotated it "inert by design". A test blessing a control that does
  // nothing. Handoff 29 removed the bell — there are no notifications in this
  // app — and replaced the hard-coded "Admin User / Administrator" with the
  // session's own user, which matters since Verify records that person.
  await gotoApp(page, "/");
  await expectShell(page);
  await expect(page.getByRole("button", { name: "Notifications", exact: true })).toHaveCount(0);
  const who = page.getByTestId("topbar-user");
  await expect(who).toBeVisible();
  await expect(who).not.toContainText("Admin User");
  // Whoever global-setup signed in as. The name comes from /auth/whoami.
  await expect(who).toContainText(/\S/, { timeout: 10_000 });
});
