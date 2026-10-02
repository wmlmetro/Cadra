import { test, expect, type Page } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import type { ApiClient } from "../fixtures/api";

/**
 * Handoff 42, in a browser: the grant, and the refusal.
 *
 * The *Change roles* section of the Users detail panel is the one writing
 * control handoff 41 deliberately left out. Four things are proved here, in
 * ONE admin session, acting on the screen and reading back over the API:
 *
 *   1. A grant through the screen — tick, Preview (a dry run of the real
 *      route, showing held and can-act-as before → after), Apply — lands on
 *      the row, and the access-changes report records it with the person
 *      who CLICKED as the actor, `attributable: true`. That last assertion
 *      is the handoff's "right actor" proof: everything runs under sudo,
 *      so the recorder could have written the route's user instead. Then
 *      the revert, and the `removed` event lands the same way.
 *   2. The refusal — the viewer's own row is not pre-empted by the screen;
 *      the server says "Nobody grants themselves a role" and the panel
 *      shows that sentence, verbatim, and Apply stays dark.
 *   3. The sentence for a non-grantable role is NOT reachable from here:
 *      there is a checkbox per grantable role and none for `system`.
 *   4. A credential's row has no checkbox at all, and says why.
 *
 * Fixtures: `h41_manager` is seeded on `test19` by handoff 41 part B; where
 * it is missing the first test says so and skips. The global storage state
 * is an admin session, and `api` is that same admin over REST.
 */

type Role = { key: string; name: string; grantable: boolean; implies: string[] };
type UserRow = { id: number; login: string; name: string; kind: string; roles_direct: { key: string; name: string }[] };
type AccessEvent = {
  event: string; at: string; login: string; group?: string; attributable?: boolean;
  actor: { id: number | null; name: string } | null;
};

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

async function grantableRoles(api: ApiClient): Promise<Role[]> {
  const roles = await api.get<Role[]>("/api/v1/roles");
  return (roles ?? []).filter((r) => r.grantable);
}

/** The person's DIRECT roles among the grantable ones — what the route acts on. */
function directGrantable(u: UserRow, grantable: Role[]): string[] {
  const g = new Set(grantable.map((r) => r.key));
  return u.roles_direct.map((r) => r.key).filter((k) => g.has(k)).sort();
}

function isoDate(d: Date) { return d.toISOString().slice(0, 10); }

/**
 * Every event of the access-changes report for a window, walking the cursor:
 * the report pages by ACCOUNT id, so the person this spec is about may be on
 * any page, and the fixture's `get` would hand back only the first.
 */
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
 *  reads it as LOCAL time and on a Lagos machine every event lands an hour
 *  early — which is how this spec's first run found a grant it had just made
 *  "missing" from the window. Report 39 fixed the same thing in the app. */
function parseUtc(at: string): number {
  return Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(at) ? at : at + "Z");
}

/** The newest membership event of `kind` for `login` at or after `since`. */
function newestEvent(events: AccessEvent[], kind: string, login: string, since: number): AccessEvent | null {
  const mine = events
    .filter((e) => e.event === kind && e.login === login && parseUtc(e.at) >= since)
    .sort((a, b) => parseUtc(b.at) - parseUtc(a.at));
  return mine[0] ?? null;
}

/** Preview, then Apply, on the open panel. Returns once `roles-applied` shows. */
async function previewAndApply(page: Page) {
  const panel = page.getByTestId("user-detail");
  await panel.getByTestId("button-preview-roles").click();
  await expect(panel.getByTestId("roles-preview")).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByTestId("roles-preview")).toHaveAttribute("data-applied", "false");
  const apply = panel.getByTestId("button-apply-roles");
  await expect(apply).toBeEnabled();
  await apply.click();
  await expect(panel.getByTestId("roles-applied")).toBeVisible({ timeout: 20_000 });
}

// ── 1 · The grant, through the screen, with the right actor ──────────────────

test("a grant through the screen lands on the row and is recorded with the person who clicked", async ({ page, api }) => {
  const manager = await findUser(api, "h41_manager");
  test.skip(!manager, "h41_manager is not on this tenant's roster (test19 has it, from handoff 41 part B)");
  const grantable = await grantableRoles(api);
  const tiu = grantable.find((r) => r.key === "tag_issuing_unit");
  test.skip(!tiu, "tag_issuing_unit is not a grantable role on this tenant");
  const me = await api.whoami();
  expect(me?.name, "whoami carries a name").toBeTruthy();

  // Start from a known state: h41_manager without Tag-Issuing Unit. A
  // previous run that failed between Apply and the revert leaves it on, and
  // the spec would then "grant" nothing.
  const baseline = directGrantable(manager!, grantable).filter((k) => k !== tiu!.key);
  if (directGrantable(manager!, grantable).includes(tiu!.key)) {
    await api.post(`/api/v1/users/${manager!.id}/roles`, { roles: baseline });
  }
  test.info().annotations.push({ type: "baseline-direct-grantable", description: baseline.join(",") || "(none)" });

  // Clock skew between this machine and the server is nil locally; the
  // minute of slack is for a container whose clock drifted.
  const since = Date.now() - 60_000;
  const from = isoDate(new Date(Date.now() - 24 * 3600_000));
  const to = isoDate(new Date());

  try {
    await openUsers(page);
    await searchFor(page, "h41_manager");
    const row = page.locator('[data-testid="user-row"][data-login="h41_manager"]');
    await expect(row).toBeVisible({ timeout: 20_000 });
    await expect(row.locator(`[data-testid="role-pill-direct"][data-role="${tiu!.name}"]`)).toHaveCount(0);
    await row.click();

    const panel = page.getByTestId("user-detail");
    await expect(panel).toBeVisible();
    const section = panel.getByTestId("user-section-change-roles");
    await expect(section).toBeVisible();
    await expect(section.getByTestId("roles-follow-scopes")).toHaveCount(0);

    // Before anything is ticked, Apply is dark: there is no preview yet.
    await expect(section.getByTestId("button-apply-roles")).toBeDisabled();

    const box = section.locator('[data-testid="role-checkbox"][data-role="tag_issuing_unit"]');
    await expect(box).not.toBeChecked();
    await box.check();

    // Preview is a dry run of the real route: what it shows is what the
    // server will do. Held gains Tag-Issuing Unit; can-act-as keeps the
    // implied Asset User and gains Tag-Issuing Unit.
    await section.getByTestId("button-preview-roles").click();
    const preview = section.getByTestId("roles-preview");
    await expect(preview).toBeVisible({ timeout: 20_000 });
    await expect(preview).toHaveAttribute("data-applied", "false");
    await expect(preview.getByTestId("roles-preview-grant")).toContainText(`Will grant: ${tiu!.name}`);
    await expect(preview.getByTestId("roles-preview-grant")).toHaveAttribute("data-keys", "tag_issuing_unit");
    await expect(preview.getByTestId("roles-preview-revoke")).toContainText("Will revoke: nothing");
    const effAfter = (await preview.getByTestId("roles-preview-effective").getAttribute("data-after")) ?? "";
    expect(effAfter.split("|"), "can act as, after").toEqual(expect.arrayContaining(["asset_user", "tag_issuing_unit"]));
    const directAfter = (await preview.getByTestId("roles-preview-direct").getAttribute("data-after")) ?? "";
    expect(directAfter.split("|"), "roles held, after").toContain("tag_issuing_unit");

    // The preview wrote nothing.
    const stillBefore = await findUser(api, "h41_manager");
    expect(directGrantable(stillBefore!, grantable), "a dry run writes nothing").toEqual(baseline);

    // Apply: enabled now, and only because the boxes are what the preview
    // was asked about. Untick + retick to prove the gate follows the boxes.
    const apply = section.getByTestId("button-apply-roles");
    await expect(apply).toBeEnabled();
    await box.uncheck();
    await expect(apply).toBeDisabled();
    await box.check();
    await expect(apply).toBeEnabled();
    await apply.click();

    const applied = section.getByTestId("roles-applied");
    await expect(applied).toBeVisible({ timeout: 20_000 });
    await expect(applied).toContainText("Applied.");
    await expect(applied).toContainText(`Granted: ${tiu!.name}`);
    await expect(applied).toHaveAttribute("data-granted", "tag_issuing_unit");

    // The panel and the row now carry the role (the list is re-read).
    await expect(panel.getByTestId("user-section-roles-direct")).toContainText(tiu!.name);
    await expect(row.locator(`[data-testid="role-pill-direct"][data-role="${tiu!.name}"]`)).toBeVisible({ timeout: 20_000 });

    // Read back over the API: the register agrees, and the access-changes
    // report recorded WHO clicked — the admin session's own name — not
    // whatever the route ran as.
    const after = await findUser(api, "h41_manager");
    expect(directGrantable(after!, grantable)).toEqual([...baseline, tiu!.key].sort());

    const granted = newestEvent(await allEvents(api, from, to), "granted", "h41_manager", since);
    expect(granted, "a `granted` event for h41_manager in the window").not.toBeNull();
    expect(granted!.attributable, "the event is attributable").toBe(true);
    expect(granted!.actor?.name, "the actor is the person who clicked").toBe(me.name);
    test.info().annotations.push({ type: "granted-event", description: JSON.stringify(granted) });

    // Revert through the same screen, and the `removed` event lands too.
    await box.uncheck();
    await previewAndApply(page);
    await expect(section.getByTestId("roles-applied")).toContainText(`Revoked: ${tiu!.name}`);
    await expect(row.locator(`[data-testid="role-pill-direct"][data-role="${tiu!.name}"]`)).toHaveCount(0, { timeout: 20_000 });

    const reverted = await findUser(api, "h41_manager");
    expect(directGrantable(reverted!, grantable)).toEqual(baseline);
    const removed = newestEvent(await allEvents(api, from, to), "removed", "h41_manager", since);
    expect(removed, "a `removed` event for h41_manager in the window").not.toBeNull();
    expect(removed!.attributable).toBe(true);
    expect(removed!.actor?.name).toBe(me.name);
    test.info().annotations.push({ type: "removed-event", description: JSON.stringify(removed) });
  } finally {
    // Whatever happened above, h41_manager leaves as it arrived.
    const now = await findUser(api, "h41_manager");
    if (now && directGrantable(now, grantable).join(",") !== baseline.join(",")) {
      await api.post(`/api/v1/users/${now.id}/roles`, { roles: baseline });
    }
  }
});

// ── 2 · The refusal: the server's sentence, verbatim, on the viewer's own row ─

test("ticking a role on one's own row is refused by the server, in its own words, and Apply stays dark", async ({ page, api }) => {
  const me = await api.whoami();
  test.skip(!me?.id, "whoami did not answer with an id");
  const grantable = await grantableRoles(api);
  const mine = await api.get<UserRow>(`/api/v1/users/${me.id}`);
  const held = new Set(directGrantable(mine, grantable));
  // A role the viewer does not directly hold — auditor first, else any
  // other: the refusal is about WHO, not WHICH.
  const target = grantable.find((r) => r.key === "auditor" && !held.has(r.key)) ?? grantable.find((r) => !held.has(r.key));
  test.skip(!target, "the admin already directly holds every grantable role; nothing to tick");
  const directBefore = [...mine.roles_direct].map((r) => r.key).sort();

  await gotoApp(page, `/admin/users/${me.id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toHaveAttribute("data-login", me.login);
  const section = panel.getByTestId("user-section-change-roles");
  const heldText = await panel.getByTestId("user-section-roles-direct").textContent();

  const box = section.locator(`[data-testid="role-checkbox"][data-role="${target!.key}"]`);
  await expect(box).not.toBeChecked();
  await box.check();
  await section.getByTestId("button-preview-roles").click();

  // The screen did not pre-empt it: the sentence is the server's, and it
  // names the person.
  const refusal = section.getByTestId("roles-refusal");
  await expect(refusal).toBeVisible({ timeout: 20_000 });
  await expect(refusal).toContainText("Nobody grants themselves a role");
  await expect(refusal).toContainText(me.login);
  await expect(section.getByTestId("roles-preview")).toHaveCount(0);
  await expect(section.getByTestId("button-apply-roles")).toBeDisabled();

  // Nothing changed — on the screen or in the register.
  await expect(panel.getByTestId("user-section-roles-direct")).toHaveText(heldText ?? "");
  const mineNow = await api.get<UserRow>(`/api/v1/users/${me.id}`);
  expect([...mineNow.roles_direct].map((r) => r.key).sort()).toEqual(directBefore);
});

// ── 3 · The non-grantable sentence is not reachable: no checkbox for `system` ─

test("a person's panel has one checkbox per grantable role and none for system", async ({ page, api }) => {
  const roles = await api.get<Role[]>("/api/v1/roles");
  const grantable = (roles ?? []).filter((r) => r.grantable);
  expect(grantable.length, "the vocabulary says which roles are grantable").toBeGreaterThan(0);
  expect(grantable.map((r) => r.key), "`system` is never grantable").not.toContain("system");

  const people = await api.get<UserRow[]>("/api/v1/users", { is_api_client: "false", active: "true", limit: 1 });
  test.skip(!people?.length, "no person on this roster");

  await gotoApp(page, `/admin/users/${people[0].id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  const boxes = panel.getByTestId("role-checkbox");
  await expect(boxes).toHaveCount(grantable.length);
  const keys = await boxes.evaluateAll((els) => els.map((e) => e.getAttribute("data-role")));
  expect(keys.sort()).toEqual(grantable.map((r) => r.key).sort());
  expect(keys).not.toContain("system");
  await expect(panel.locator('[data-testid="role-checkbox"][data-role="system"]')).toHaveCount(0);
});

// ── 4 · A credential: no checkbox, and the reason ────────────────────────────

test("a credential's panel offers no checkbox and says its roles follow its scopes", async ({ page, api }) => {
  const creds = await api.get<UserRow[]>("/api/v1/users", { is_api_client: "true", limit: 1 });
  test.skip(!creds?.length, "no API credential on this roster");

  await gotoApp(page, `/admin/users/${creds[0].id}`);
  await expectShell(page);
  const panel = page.getByTestId("user-detail");
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByTestId("kind-pill-api")).toBeVisible();
  const section = panel.getByTestId("user-section-change-roles");
  await expect(section.getByTestId("roles-follow-scopes")).toHaveText("A credential's roles follow its scopes and are not changed here.");
  await expect(panel.getByTestId("role-checkbox")).toHaveCount(0);
  await expect(panel.getByTestId("button-preview-roles")).toHaveCount(0);
  await expect(panel.getByTestId("button-apply-roles")).toHaveCount(0);
});
