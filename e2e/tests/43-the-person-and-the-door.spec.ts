import { test, expect, type Page } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import type { ApiClient } from "../fixtures/api";
import { MARKER_PREFIX, markedName } from "../fixtures/marker";

/**
 * Handoff 43, in a browser: the person, and the door.
 *
 * The Users page gains the person's lifecycle — create and invite, re-send,
 * deactivate, reactivate — and this spec drives every one of them from the
 * screen in ONE admin session, reading the row back over REST after each,
 * because the screen is not the record. What is proved:
 *
 *   1. Create: name, email, one role, "send the invitation now" left on. The
 *      new row is selected, `roles_direct` is exactly what was ticked, the
 *      invitation is `outstanding` — or `never`, when this tenant cannot send
 *      mail and the spec creates the account without the letter instead
 *      (the local tenants have no mail server; the cluster does). Either way
 *      the access-changes report carries a `granted` event for the login
 *      with the person who CLICKED as the actor: creating a person with
 *      roles IS granting roles, and the handoff-42 recorder sees it with no
 *      code in the route.
 *   2. Re-send: `invitation-sent` and `sends` incremented when mail works;
 *      the server's `server_misconfigured` sentence, verbatim, when it does
 *      not — and "Nothing changed on the account."
 *   3. Deactivate, then reactivate, each through its dialog: the row's
 *      `data-active`, the pill, and REST agree at every step, and an
 *      invitation that had been sent reads `cancelled` after the
 *      deactivation (the token is voided; reactivating does not re-send).
 *   4. The refusal the screen must NOT pre-empt: Deactivate on the viewer's
 *      own row reaches the server, which says "You cannot deactivate your own
 *      account", shown verbatim inside the dialog; the account stays active.
 *   5. A credential's panel has none of the three buttons and says why.
 *
 * NO PASSWORD IS TYPED ANYWHERE in this spec, because there is nowhere to
 * type one. THERE IS NO DELETE: the API has no route and the UI no button, by
 * design — so the account this spec creates stays on the tenant, marked
 * `E2E-<run>` like every other fixture, and is DEACTIVATED in a `finally` so
 * a re-run does not pile up active fixtures. `scripts/remove_test_residue.py`
 * is the owner's tool for the rows themselves.
 *
 * Set `E2E_SHOTS=<dir>` to also save the screenshots the report refers to.
 */

type Invitation = {
  state: "never" | "outstanding" | "expired" | "redeemed" | "cancelled";
  sent_at: string | null; sent_by: { id: number; name: string } | null;
  sends: number; expires_at: string | null;
};
type UserRow = {
  id: number; login: string; name: string; email: string | null; active: boolean; kind: string;
  last_login_at: string | null;
  roles_direct: { key: string; name: string }[];
  invitation: Invitation;
};
type AccessEvent = {
  event: string; at: string; login: string; group?: string; attributable?: boolean;
  actor: { id: number | null; name: string } | null;
};

async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/${name}.png`, fullPage: false });
}

async function openUsers(page: Page) {
  await gotoApp(page, "/admin/users");
  await expectShell(page);
  await expect(page.getByTestId("admin-users-page")).toBeVisible();
}

async function searchFor(page: Page, q: string) {
  const box = page.getByTestId("input-user-search");
  await box.fill(q);
  await box.press("Enter");
}

async function findUser(api: ApiClient, login: string): Promise<UserRow | null> {
  const found = await api.get<UserRow[]>("/api/v1/users", { q: login, limit: 10 });
  return (found ?? []).find((u) => u.login === login) ?? null;
}

function isoDate(d: Date) { return d.toISOString().slice(0, 10); }

/** Every event of the access-changes report for a window, walking the
 *  cursor: the report pages by ACCOUNT id, and a freshly created account has
 *  the highest id on the tenant — it is on the LAST page, never the first. */
async function allEvents(api: ApiClient, from: string, to: string): Promise<AccessEvent[]> {
  const out: AccessEvent[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < 50; i++) {
    const params: Record<string, string | number> = { from, to, limit: 100 };
    if (cursor) params.cursor = cursor;
    const probe = await api.probe("/api/v1/reports/access-changes", params);
    if (!probe.ok) throw new Error(`access-changes → HTTP ${probe.status}: ${JSON.stringify(probe.body).slice(0, 200)}`);
    out.push(...((probe.body?.data?.events ?? []) as AccessEvent[]));
    cursor = probe.body?.pagination?.next_cursor ?? undefined;
    if (!cursor) break;
  }
  return out;
}

/** The report's `at` is a naive UTC `isoformat()`; parsed bare, `Date.parse`
 *  reads it as LOCAL time — spec 42's first run lost its own grant that way. */
function parseUtc(at: string): number {
  return Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(at) ? at : at + "Z");
}

/** Deactivate over REST without throwing — for the `finally`, where a throw
 *  would replace the failure the test is about with this one. */
async function quietlyDeactivate(api: ApiClient, id: number) {
  try { await api.post(`/api/v1/users/${id}/deactivate`, {}); } catch { /* already inactive, or gone */ }
}

// ── 1 · 2 · 3 — create and invite, re-send, deactivate, reactivate ───────────

test("a person is created and invited from the screen, re-sent, deactivated and reactivated — the row agreeing at every step", async ({ page, api }) => {
  const me = await api.whoami();
  expect(me?.name, "whoami carries a name").toBeTruthy();
  const name = markedName("Person");
  const email = `${MARKER_PREFIX.toLowerCase()}@example.invalid`;
  const login = email.toLowerCase();
  test.info().annotations.push({ type: "fixture", description: `${name} <${email}>` });

  const since = Date.now() - 60_000;
  const from = isoDate(new Date(Date.now() - 24 * 3600_000));
  const to = isoDate(new Date());

  let createdId: number | null = null;
  let mailWorks: boolean | null = null;

  try {
    await openUsers(page);
    await expect(page.getByTestId("user-row").first()).toBeVisible({ timeout: 20_000 });

    // ── 1 · Create ──────────────────────────────────────────────────────────
    await page.getByTestId("button-create-user").click();
    const dialog = page.getByTestId("dialog-create-user");
    await expect(dialog).toBeVisible();
    // No password field anywhere in the dialog, and the sentence that says why.
    await expect(dialog.locator("input[type=password]")).toHaveCount(0);
    await expect(dialog).toContainText("no password is typed here");

    await dialog.getByTestId("input-create-name").fill(name);
    await dialog.getByTestId("input-create-email").fill(email);
    const roleBox = dialog.locator('[data-testid="create-role-checkbox"][data-role="asset_user"]');
    await expect(roleBox, "asset_user is a grantable role with a checkbox").toBeVisible();
    await roleBox.check();
    // `system` has no checkbox: the model's sentence is not reachable here.
    await expect(dialog.locator('[data-testid="create-role-checkbox"][data-role="system"]')).toHaveCount(0);
    const sendNow = dialog.getByTestId("checkbox-send-invitation");
    await expect(sendNow).toBeChecked();
    await expect(dialog.getByTestId("button-confirm-create")).toContainText("Create and invite");
    await dialog.getByTestId("button-confirm-create").click();

    // Either the dialog closes on the server's row, or the server refuses —
    // and the one refusal this spec expects on a tenant with no mail is
    // `server_misconfigured`, with the account NOT created.
    const refusal = dialog.getByTestId("create-user-refusal");
    const detailLogin = page.getByTestId("user-detail-login");
    await expect(refusal.or(detailLogin)).toBeVisible({ timeout: 30_000 });
    if (await refusal.isVisible()) {
      const text = (await refusal.textContent()) ?? "";
      expect(text, "the only refusal expected here is an undeliverable letter").toContain("server_misconfigured");
      expect(text).toContain("The account was not created");
      expect(await findUser(api, login), "a refused create leaves no account behind").toBeNull();
      test.info().annotations.push({ type: "mail-on-tenant", description: `cannot send: ${text.slice(0, 200)}` });
      mailWorks = false;
      // What was typed is still there; untick send-now and create without the letter.
      await expect(dialog.getByTestId("input-create-email")).toHaveValue(email);
      await sendNow.uncheck();
      await expect(dialog.getByTestId("button-confirm-create")).toHaveText("Create");
      await dialog.getByTestId("button-confirm-create").click();
      await expect(detailLogin).toBeVisible({ timeout: 30_000 });
    } else {
      mailWorks = true;
      test.info().annotations.push({ type: "mail-on-tenant", description: "the invitation was sent" });
    }
    await expect(dialog).toBeHidden();

    // The new row is selected: the panel shows the server's row.
    await expect(detailLogin).toHaveText(login);
    const panel = page.getByTestId("user-detail");
    await expect(panel.getByTestId("user-detail-name")).toHaveText(name);
    await expect(panel.getByTestId("active-pill")).toBeVisible();
    const invLine = panel.getByTestId("user-invitation");
    await expect(invLine).toHaveAttribute("data-state", mailWorks ? "outstanding" : "never");
    await expect(invLine).toContainText(mailWorks ? "Invitation sent" : "No invitation has been sent.");

    // REST agrees.
    const created = await findUser(api, login);
    expect(created, "the account is on the roster").not.toBeNull();
    createdId = created!.id;
    expect(created!.kind).toBe("person");
    expect(created!.active).toBe(true);
    expect(created!.roles_direct.map((r) => r.key)).toEqual(["asset_user"]);
    expect(created!.invitation.state).toBe(mailWorks ? "outstanding" : "never");
    expect(created!.invitation.sends).toBe(mailWorks ? 1 : 0);
    if (mailWorks) {
      expect(created!.invitation.sent_by?.name, "the letter names who sent it").toBe(me.name);
      expect(created!.invitation.expires_at).toBeTruthy();
    }
    await expect(page).toHaveURL(new RegExp(`/admin/users/${createdId}$`));

    // Creating a person with roles IS granting roles: the recorder saw it,
    // with the person who clicked as the actor.
    const events = (await allEvents(api, from, to)).filter((e) => e.login === login && parseUtc(e.at) >= since);
    test.info().annotations.push({ type: "events-for-login", description: JSON.stringify(events.map((e) => e.event)) });
    const granted = events.find((e) => e.event === "granted");
    expect(granted, "a `granted` event for the new login in the window").toBeTruthy();
    expect(granted!.actor?.name, "the actor is the person who clicked").toBe(me.name);
    expect(granted!.attributable).toBe(true);
    await shot(page, "01-created-and-invited");

    // The row: searched for, because a fresh account has the highest id and
    // on a roster of more than a page is not on the first one.
    await searchFor(page, login);
    const row = page.locator(`[data-testid="user-row"][data-login="${login}"]`);
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(row).toHaveAttribute("data-active", "true");
    if (mailWorks) await expect(row.getByTestId("invitation-pill")).toHaveAttribute("data-state", "outstanding");
    else await expect(row.getByTestId("invitation-pill")).toHaveCount(0);

    // ── 2 · Re-send ─────────────────────────────────────────────────────────
    const resend = panel.getByTestId("button-resend-invitation");
    await expect(resend).toBeVisible();
    await expect(resend).toHaveText(mailWorks ? /Re-send invitation/ : /Send invitation/);
    await resend.click();
    const sentLine = panel.getByTestId("invitation-sent");
    const actionRefusal = panel.getByTestId("user-action-refusal");
    await expect(sentLine.or(actionRefusal)).toBeVisible({ timeout: 30_000 });
    if (mailWorks) {
      await expect(sentLine).toContainText(`Invitation sent just now to ${email}`);
      const resent = await findUser(api, login);
      expect(resent!.invitation.sends, "sends incremented").toBe(2);
      expect(resent!.invitation.state).toBe("outstanding");
      await expect(invLine).toContainText("Sent 2 times");
    } else {
      await expect(actionRefusal).toContainText("server_misconfigured");
      await expect(actionRefusal).toContainText("Nothing changed on the account.");
      const unchanged = await findUser(api, login);
      expect(unchanged!.invitation.state).toBe("never");
      expect(unchanged!.invitation.sends).toBe(0);
    }
    await shot(page, "02-resent");

    // ── 3 · Deactivate, then reactivate ─────────────────────────────────────
    await panel.getByTestId("button-deactivate-user").click();
    const deact = page.getByTestId("dialog-deactivate-user");
    await expect(deact).toBeVisible();
    await expect(deact).toContainText(`${name} will no longer be able to sign in.`);
    await expect(deact).toContainText("nothing is deleted");
    await deact.getByTestId("button-confirm-deactivate").click();
    await expect(deact).toBeHidden({ timeout: 30_000 });

    await expect(panel.getByTestId("inactive-pill")).toBeVisible({ timeout: 20_000 });
    await expect(row).toHaveAttribute("data-active", "false", { timeout: 20_000 });
    await expect(row.getByTestId("inactive-pill")).toBeVisible();
    await expect(panel.getByTestId("button-deactivate-user")).toHaveCount(0);
    await expect(panel.getByTestId("button-resend-invitation"), "no re-send for a deactivated account").toHaveCount(0);
    const deactivated = await findUser(api, login);
    expect(deactivated!.active).toBe(false);
    expect(deactivated!.roles_direct.map((r) => r.key), "roles stay as they were").toEqual(["asset_user"]);
    if (mailWorks) {
      expect(deactivated!.invitation.state, "the deactivation cancels the token").toBe("cancelled");
      await expect(invLine).toHaveAttribute("data-state", "cancelled");
      await expect(invLine).toContainText("Invitation cancelled (not used)");
    } else {
      expect(deactivated!.invitation.state).toBe("never");
    }
    await shot(page, "03-deactivated");

    await panel.getByTestId("button-reactivate-user").click();
    const react = page.getByTestId("dialog-reactivate-user");
    await expect(react).toBeVisible();
    await expect(react).toContainText("a cancelled invitation is not re-sent");
    await react.getByTestId("button-confirm-reactivate").click();
    await expect(react).toBeHidden({ timeout: 30_000 });

    await expect(panel.getByTestId("active-pill")).toBeVisible({ timeout: 20_000 });
    await expect(row).toHaveAttribute("data-active", "true", { timeout: 20_000 });
    const reactivated = await findUser(api, login);
    expect(reactivated!.active).toBe(true);
    // Not re-sent: the state the deactivation left is the state it has.
    expect(reactivated!.invitation.state).toBe(mailWorks ? "cancelled" : "never");
    expect(reactivated!.invitation.sends).toBe(mailWorks ? 2 : 0);
    // And the door back to an invitation is one click away again.
    await expect(panel.getByTestId("button-resend-invitation")).toBeVisible();
  } finally {
    // There is no delete. The fixture leaves DEACTIVATED, marked, on the roster.
    if (createdId == null) {
      const maybe = await findUser(api, login).catch(() => null);
      createdId = maybe?.id ?? null;
    }
    if (createdId != null) await quietlyDeactivate(api, createdId);
  }
});

// ── 4 · The refusal the screen must not pre-empt ─────────────────────────────

test("Deactivate on one's own row reaches the server and is refused in its words; the account stays active", async ({ page, api }) => {
  const me = await api.whoami();
  test.skip(!me?.id, "whoami did not answer with an id");
  const mine = await api.get<UserRow>(`/api/v1/users/${me.id}`);
  test.skip(mine.kind !== "person", "the session's account is a credential's user; the button is not offered for one");
  expect(mine.active).toBe(true);

  await gotoApp(page, `/admin/users/${me.id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toHaveAttribute("data-login", me.login);

  // The button is THERE on the viewer's own row — the screen does not decide.
  await panel.getByTestId("button-deactivate-user").click();
  const dialog = page.getByTestId("dialog-deactivate-user");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("button-confirm-deactivate").click();

  const refusal = dialog.getByTestId("user-action-refusal");
  await expect(refusal).toBeVisible({ timeout: 20_000 });
  await expect(refusal).toContainText("You cannot deactivate your own account");
  await expect(refusal).toContainText("Another administrator has to.");
  await expect(dialog, "the dialog stays open on the refusal").toBeVisible();
  await shot(page, "04-self-deactivate-refused");

  // Nothing changed — on the screen or in the register.
  await expect(panel.getByTestId("active-pill")).toBeVisible();
  const still = await api.get<UserRow>(`/api/v1/users/${me.id}`);
  expect(still.active).toBe(true);
});

// ── 5 · A credential: none of the three, and the reason ──────────────────────

test("a credential's panel offers no lifecycle button and says its sign-in is managed with the credential", async ({ page, api }) => {
  const creds = await api.get<UserRow[]>("/api/v1/users", { is_api_client: "true", limit: 1 });
  test.skip(!creds?.length, "no API credential on this roster");
  expect(creds[0].kind).toBe("api_credential");

  await gotoApp(page, `/admin/users/${creds[0].id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByTestId("kind-pill-api")).toBeVisible();
  const section = panel.getByTestId("user-section-signin");
  await expect(section.getByTestId("lifecycle-follows-credential"))
    .toHaveText("Sign-in and status are managed with the credential, not here.");
  await expect(panel.getByTestId("button-resend-invitation")).toHaveCount(0);
  await expect(panel.getByTestId("button-deactivate-user")).toHaveCount(0);
  await expect(panel.getByTestId("button-reactivate-user")).toHaveCount(0);
  await expect(panel.getByTestId("user-invitation")).toHaveCount(0);
});
