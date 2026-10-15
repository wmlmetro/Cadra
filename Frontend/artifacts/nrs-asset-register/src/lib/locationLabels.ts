/**
 * Room codes and room labels — handoff 61 §7 (ruling R8).
 *
 * Every location carries a `location_code` (`LOC-…`): unique on the tenant,
 * generated from the hierarchy's zone codes when empty, editable by
 * `locations:write`. A scan of one at the station answers
 * `matched_by: "location"` from `GET /api/v1/barcode/lookup` — a ROOM, with
 * no asset at all — and the room's label is printed from
 * `GET /api/v1/locations/<id>/label?size=medium|large`.
 *
 * Why the label is a server PDF and not composed here like an asset label
 * (`lib/labels.ts`): the code is the whole of the label, both symbologies
 * carry it verbatim (handoff 55 §3), and the server renders the same file
 * for the phone team's printer path as for this screen. It is fetched with
 * the bearer token (`apiGetRaw`) because a plain link cannot carry one, and
 * the back office's `/report/pdf/...` is an administrator's door.
 *
 * There is no SMALL room label: handoff 54 measured the 50 × 25 mm Code 128
 * at 0 of 24 camera reads, and the server refuses `size=small` saying so.
 */
import { apiGet, apiGetRaw } from "./api";

export type RoomLabelSize = "medium" | "large";

export const ROOM_LABEL_SIZES: Array<{ value: RoomLabelSize; label: string; hint: string }> = [
  { value: "medium", label: "Medium", hint: "50 × 30 mm" },
  { value: "large", label: "Large", hint: "100 × 60 mm" },
];

/** The room a scanned code names — `matched_location` on the lookup. */
export interface MatchedLocation {
  id: number;
  name: string;
  location_code: string;
  /** Root-first names joined by " / ". */
  path: string;
  location_type: string | null;
  type: { id: number; name: string } | null;
  parent_id: number | null;
  /** False for an archived location — its label still resolves. */
  active: boolean;
  /** Registered assets whose location IS this one (not sub-locations). */
  asset_count: number;
}

export interface RoomLookupHit {
  found: true;
  matched_by: "location";
  matched_location: MatchedLocation;
}

/** True when a `/barcode/lookup` answer is a ROOM, not an asset. Branch on
 *  this before reading any asset field: a room answer carries none. */
export function isRoomHit(result: unknown): result is RoomLookupHit {
  if (!result || typeof result !== "object") return false;
  const r = result as { found?: unknown; matched_by?: unknown; matched_location?: unknown };
  return r.found === true && r.matched_by === "location"
    && !!r.matched_location && typeof r.matched_location === "object";
}

/** A location's room code, read off `GET /api/v1/locations/<id>`. */
export async function fetchLocationCode(id: string | number): Promise<string | null> {
  const res = await apiGet<{ location_code?: string | null }>(`/api/v1/locations/${id}`);
  return res.data.location_code ?? null;
}

export interface RoomOption {
  id: number;
  name: string;
  location_code: string | null;
  location_type: string | null;
}

/** Locations matching `q` by name, description, zone code, city or room
 *  code — the list route's own `?q=`. */
export async function searchRooms(q: string, limit = 10): Promise<RoomOption[]> {
  const res = await apiGet<Array<{
    id: number; name: string; location_code?: string | null; location_type: string | null;
  }>>("/api/v1/locations", { q, limit });
  return res.data.map((l) => ({
    id: l.id, name: l.name, location_code: l.location_code ?? null, location_type: l.location_type,
  }));
}

/** The room label PDF, as the server rendered it. */
export async function fetchRoomLabel(id: number | string, size: RoomLabelSize): Promise<Blob> {
  const res = await apiGetRaw(`/api/v1/locations/${id}/label`, { size });
  return res.blob();
}

export interface RoomPrintResult {
  /** "tab": the PDF opened in a new tab, printed from the browser's viewer.
   *  "download": a popup blocker refused the tab, so the file was saved. */
  how: "tab" | "download";
  filename: string;
}

/**
 * Fetch the label and put it in front of the person to print.
 *
 * The tab is opened SYNCHRONOUSLY, inside the click, and pointed at the PDF
 * once it arrives — a `window.open` after an `await` is outside the user's
 * gesture and most browsers block it. If the tab was refused anyway, the
 * file is downloaded instead, and the caller says so.
 */
export async function printRoomLabel(
  id: number | string, code: string, size: RoomLabelSize,
): Promise<RoomPrintResult> {
  const tab = typeof window !== "undefined" ? window.open("", "_blank") : null;
  const filename = `room-label-${code}-${size}.pdf`;
  try {
    const blob = await fetchRoomLabel(id, size);
    const url = URL.createObjectURL(blob);
    // Long enough for the viewer to load it; a blob URL is per-document and
    // costs memory until revoked.
    setTimeout(() => URL.revokeObjectURL(url), 120_000);
    if (tab && !tab.closed) {
      tab.location.href = url;
      return { how: "tab", filename };
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return { how: "download", filename };
  } catch (e) {
    if (tab && !tab.closed) tab.close();
    throw e;
  }
}

/** The room a `/barcode/lookup` answer names, or null when it names an
 *  asset (or nothing). Takes `unknown` and does not narrow the caller's
 *  type: the asset union and a room answer share `found: true`, and a type
 *  guard over both would collapse to `never`. */
export function roomOf(result: unknown): MatchedLocation | null {
  return isRoomHit(result) ? result.matched_location : null;
}
