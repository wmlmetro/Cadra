import { test, expect } from "../fixtures/test";
import { gotoApp, expectShell } from "../fixtures/helpers";
import { markedName, recordCreated } from "../fixtures/marker";

/**
 * Handoff 61 §7 (ruling R8), in a browser: room codes.
 *
 * Every location carries a `location_code` (`LOC-…`). The location page shows
 * it and prints its room label — the server's PDF, fetched with the bearer
 * token and opened for the browser's print, at medium or large and never
 * small. The station's scan box answers a room code with "This is a room:
 * <name>", never "not found". And the form edits the code, refusing one that
 * another location holds in the server's own words, with nothing saved.
 *
 * One session per test, acting in the flow a person takes (CLAUDE.md:
 * "acting from a cold start proves only the cold start") — location page,
 * print, then the station; and the refused edit read back from the API.
 */

function uniq(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`.toUpperCase();
}

async function newRoom(api: any, label: string, extra: Record<string, unknown> = {}) {
  const name = markedName(label);
  const loc = await api.post("/api/v1/locations", { name, ...extra });
  recordCreated({ kind: "location", id: loc.id, name });
  expect(loc.location_code, "a new location is given a room code").toMatch(/^LOC(-[A-Z0-9]+)+$/);
  return loc as { id: number; name: string; location_code: string };
}

test("the location page shows the room code and prints its label, then the station scans it as a room", async ({ page, api }) => {
  const room = await newRoom(api, "RoomCode", { zone_code: `E2E${uniq()}` });

  // ── The location page ────────────────────────────────────────────────
  await gotoApp(page, `/locations/${room.id}`);
  await expectShell(page);
  await expect(page.getByTestId("location-room-code-value")).toHaveText(room.location_code, { timeout: 20_000 });

  // Large, then Print. The PDF is the server's answer to the click; read it
  // off the wire, because the browser's print dialog is not scriptable.
  await page.getByTestId("location-room-code").getByTestId("room-label-size-large").click();
  const labelResponse = page.waitForResponse(
    (r) => r.url().includes(`/api/v1/locations/${room.id}/label`) && r.request().method() === "GET",
    { timeout: 30_000 },
  );
  const popup = page.context().waitForEvent("page", { timeout: 30_000 }).catch(() => null);
  await page.getByTestId("location-room-code").getByTestId("room-label-print-button").click();
  const res = await labelResponse;
  expect(res.status()).toBe(200);
  expect(new URL(res.url()).searchParams.get("size")).toBe("large");
  expect(res.headers()["content-type"]).toContain("application/pdf");
  const pdf = await res.body();
  expect(pdf.subarray(0, 4).toString()).toBe("%PDF");
  await expect(page.getByTestId("location-room-code").getByTestId("room-label-note"))
    .toContainText(room.location_code, { timeout: 15_000 });
  const tab = await popup;
  if (tab) await tab.close();

  // The small size is not offered in the app, and the server refuses it.
  await expect(page.getByTestId("room-label-size-small")).toHaveCount(0);
  const small = await api.probe(`/api/v1/locations/${room.id}/label`, { size: "small" });
  expect(small.status).toBe(400);
  expect(small.body?.error?.message).toContain("There is no small room label");

  // ── The station, same session ────────────────────────────────────────
  await gotoApp(page, "/tools/barcode");
  await expectShell(page);
  await page.getByTestId("scan-box").fill(room.location_code);
  await page.getByRole("button", { name: "Lookup" }).click();
  await expect(page.getByTestId("lookup-room-title")).toHaveText(`This is a room: ${room.name}`, { timeout: 20_000 });
  await expect(page.getByTestId("lookup-room-code")).toHaveText(room.location_code);
  await expect(page.getByTestId("lookup-miss")).toHaveCount(0);
  await expect(page.getByTestId("lookup-result")).toHaveCount(0);

  // And the server's own answer, for the record.
  const hit = await api.get<any>("/api/v1/barcode/lookup", { query: room.location_code });
  expect(hit.matched_by).toBe("location");
  expect(hit.matched_location.id).toBe(room.id);
  expect(hit.asset_id).toBeUndefined();
});

test("the form refuses a room code another location holds, in words, and saves nothing", async ({ page, api }) => {
  const holder = await newRoom(api, "RoomCodeHolder");
  const other = await newRoom(api, "RoomCodeOther", { description: "before" });

  await gotoApp(page, `/locations/${other.id}/edit`);
  await expectShell(page);
  const input = page.getByTestId("location-code-input");
  await expect(input).toHaveValue(other.location_code, { timeout: 20_000 });
  await input.fill(holder.location_code);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(/is already the code of/i).first()).toBeVisible({ timeout: 20_000 });

  const after = await api.get<any>(`/api/v1/locations/${other.id}`);
  expect(after.location_code).toBe(other.location_code);
  expect(after.description).toBe("before");
});
