/**
 * The audit in the room (handoff 66) — the wire types and calls behind the
 * five pages under `pages/audit/`.
 *
 * An audit team walks a room; every item ends as one of three outcomes —
 * already on Cadra's register (a), in SAP's register but not Cadra's (b), or
 * in neither (c) — and every outcome needs two people: the capturer and a
 * reviewer who accepts it. The Asset Controller registers the devices,
 * issues the code blocks, opens and closes the campaigns, and resolves the
 * found-not-in-SAP exceptions.
 *
 * Mirrors `myservice_api/controllers/v1_audit_capture.py`; the server decides
 * everything, and every refusal on these pages is the server's sentence.
 */
import { apiGet, apiGetRaw, apiPatch, apiPost, apiUpload, type CadraPagination } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** Every query on the audit pages lives under this prefix, so one
 *  invalidation refreshes them all after any act. */
export const AUDIT_KEY = ["audit"] as const;

/** The header a capture names its device by. */
export const DEVICE_HEADER = "X-Cadra-Device";

/** A batch takes at most this many (the server's `BATCH_MAX`). */
export const AUDIT_BATCH_MAX = 100;

export interface UserRef { id: number; name: string }

// ── devices, blocks, codes ───────────────────────────────────────────────

export interface AuditDevice {
  id: number;
  name: string;
  device_code: string;
  bound_to: UserRef | null;
  bound_at: string | null;
  bound_by: UserRef | null;
  active: boolean;
  registered_by: UserRef | null;
  registered_at: string | null;
  open_block_id: number | null;
}

export type CodeState = "reserved" | "in_review" | "active" | "void";

export interface AuditCode {
  code: string;
  state: CodeState;
  source: "block" | "asset" | "backfill";
  block_id: number | null;
  device_id: number | null;
  reserved_to: UserRef | null;
  reserved_at: string | null;
  used_at: string | null;
  activated_at: string | null;
  voided_at: string | null;
  voided_by: UserRef | null;
  void_reason: string | null;
  asset_id: number | null;
  capture_id: string | null;
}

export interface AuditBlock {
  id: number;
  name: string;
  device: { id: number; name: string };
  issued_to: UserRef | null;
  size: number;
  state: "issued" | "returned";
  first_code: string | null;
  last_code: string | null;
  issued_by: UserRef | null;
  issued_at: string | null;
  returned_by: UserRef | null;
  returned_at: string | null;
  return_reason: string | null;
  codes_by_state: Partial<Record<CodeState, number>>;
  codes?: AuditCode[];
  voided_now?: number;
}

export interface AuditPeople {
  capturers: (UserRef & { login: string })[];
  reviewers: (UserRef & { login: string })[];
}

export const CODE_STATE_WORDS: Record<CodeState, string> = {
  reserved: "Reserved",
  in_review: "In review",
  active: "Active",
  void: "Void",
};

export async function fetchDevices(mine = false): Promise<AuditDevice[]> {
  return (await apiGet<AuditDevice[]>("/api/v1/audit/devices", mine ? { mine: "true" } : undefined)).data ?? [];
}

export async function fetchAuditPeople(): Promise<AuditPeople> {
  return (await apiGet<AuditPeople>("/api/v1/audit/people")).data;
}

export async function registerDevice(name: string, userId: number | null): Promise<AuditDevice> {
  const body: Record<string, unknown> = { name: name.trim() };
  if (userId != null) body.user_id = userId;
  return (await apiPost<AuditDevice>("/api/v1/audit/devices", body)).data;
}

export async function bindDevice(id: number, userId: number | null): Promise<AuditDevice> {
  return (await apiPost<AuditDevice>(`/api/v1/audit/devices/${id}/bind`, { user_id: userId })).data;
}

export async function deactivateDevice(id: number): Promise<AuditDevice> {
  return (await apiPost<AuditDevice>(`/api/v1/audit/devices/${id}/deactivate`, {})).data;
}

export async function fetchBlocks(p: { deviceId?: number; state?: "issued" | "returned" } = {}): Promise<AuditBlock[]> {
  return (await apiGet<AuditBlock[]>("/api/v1/audit/blocks", {
    device_id: p.deviceId, state: p.state,
  })).data ?? [];
}

export async function fetchBlock(id: number): Promise<AuditBlock> {
  return (await apiGet<AuditBlock>(`/api/v1/audit/blocks/${id}`)).data;
}

export async function issueBlock(deviceId: number, size: number): Promise<AuditBlock> {
  return (await apiPost<AuditBlock>("/api/v1/audit/blocks", { device_id: deviceId, size })).data;
}

export async function returnBlock(id: number, reason?: string): Promise<AuditBlock> {
  const body: Record<string, unknown> = {};
  if (reason && reason.trim()) body.reason = reason.trim();
  return (await apiPost<AuditBlock>(`/api/v1/audit/blocks/${id}/return`, body)).data;
}

// ── campaigns ────────────────────────────────────────────────────────────

export interface CampaignProgress {
  captured: number;
  waiting_for_review: number;
  accepted: number;
  returned: number;
  reviewed: number;
  duplicates_held: number;
  exceptions: number;
  exceptions_open: number;
}

export interface CampaignRoom {
  location: { id: number; name: string };
  captured: number;
  waiting_for_review: number;
}

export interface AuditCampaign {
  id: number;
  name: string;
  state: "open" | "closed";
  date_start: string | null;
  date_end: string | null;
  scope: { location: { id: number; name: string } | null; office_code: string | null }[];
  capturers: UserRef[];
  reviewers: UserRef[];
  created_by: UserRef | null;
  closed_by: UserRef | null;
  closed_at: string | null;
  progress: CampaignProgress;
  rooms?: CampaignRoom[];
}

export interface FoundNotInSap {
  office_code: string | null;
  capture_id: string;
  code: string | null;
  name: string | null;
  category: string | null;
  location: string | null;
  location_id: number | null;
  captured_by: string | null;
  captured_at: string | null;
  exception_state: string | null;
}

export interface InSapNotFound {
  office_code: string | null;
  sap_record_id: number;
  asset_number: string;
  sub_number: string | null;
  asset_class: string | null;
  description: string | null;
  old_tag: string | null;
  capitalized_on: string | null;
}

export interface CampaignLists {
  found_not_in_sap: FoundNotInSap[];
  in_sap_not_found: InSapNotFound[];
  by_office: { office_code: string | null; found_not_in_sap: number; in_sap_not_found: number }[];
  sap_records_with_no_office: number;
  no_office_note: string;
  offices?: string[];
  /** `closing` — the lists as they stood when the campaign closed; `now`
   *  — computed for an open campaign. */
  as_of: "closing" | "now";
}

export type ListKey = "found_not_in_sap" | "in_sap_not_found";

export async function fetchCampaigns(state?: "open" | "closed"): Promise<AuditCampaign[]> {
  return (await apiGet<AuditCampaign[]>("/api/v1/audit/campaigns", { state })).data ?? [];
}

export async function fetchCampaign(id: number): Promise<AuditCampaign> {
  return (await apiGet<AuditCampaign>(`/api/v1/audit/campaigns/${id}`)).data;
}

export async function openCampaign(body: {
  name: string;
  scope: { location_id?: number; office_code?: string }[];
  capturer_ids: number[];
  reviewer_ids: number[];
  date_start?: string;
  date_end?: string;
}): Promise<AuditCampaign> {
  const payload: Record<string, unknown> = {
    name: body.name.trim(), scope: body.scope,
    capturer_ids: body.capturer_ids, reviewer_ids: body.reviewer_ids,
  };
  if (body.date_start) payload.date_start = body.date_start;
  if (body.date_end) payload.date_end = body.date_end;
  return (await apiPost<AuditCampaign>("/api/v1/audit/campaigns", payload)).data;
}

export async function patchCampaign(id: number, body: {
  name?: string; capturer_ids?: number[]; reviewer_ids?: number[]; date_end?: string | null;
}): Promise<AuditCampaign> {
  return (await apiPatch<AuditCampaign>(`/api/v1/audit/campaigns/${id}`, body)).data;
}

export async function closeCampaign(id: number): Promise<AuditCampaign & { lists: CampaignLists }> {
  return (await apiPost<AuditCampaign & { lists: CampaignLists }>(`/api/v1/audit/campaigns/${id}/close`, {})).data;
}

export async function fetchCampaignLists(id: number): Promise<CampaignLists> {
  return (await apiGet<CampaignLists>(`/api/v1/audit/campaigns/${id}/lists`)).data;
}

/** One of the two lists as a file, through the bearer token. Returns the
 *  file's name and its object URL; the caller revokes it. */
export async function downloadCampaignList(id: number, list: ListKey): Promise<{ filename: string; url: string; bytes: number }> {
  const res = await apiGetRaw(`/api/v1/audit/campaigns/${id}/lists.csv`, { list });
  const text = await res.text();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const filename = m ? decodeURIComponent(m[1]) : `campaign-${id}-${list.replace(/_/g, "-")}.csv`;
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  return { filename, url, bytes: new Blob([text]).size };
}

// ── a room's slice ───────────────────────────────────────────────────────

export interface SliceAsset {
  id: number;
  asset_code: string;
  name: string | null;
  asset_tag: string | null;
  legacy_asset_code: string | null;
  serial_number: string | null;
  category: string | null;
  condition: string | null;
  state: string | null;
  sap_asset_number: string | null;
  location_id: number | null;
}

export interface SliceSapRecord {
  id: number;
  asset_number: string;
  sub_number: string | null;
  class: string | null;
  description: string | null;
  old_tag: string | null;
  serial_number: string | null;
  capitalized_on: string | null;
  linked_asset_id: number | null;
}

export interface Slice<T> {
  kind?: "assets" | "sap_records";
  office_code: string | null;
  location?: { id: number; name: string; location_code: string | null };
  records: T[];
  note?: string;
  total: number | null;
}

export async function fetchSlice<T extends SliceAsset | SliceSapRecord>(
  campaignId: number, locationId: number, kind: "assets" | "sap_records",
): Promise<Slice<T>> {
  const res = await apiGet<Omit<Slice<T>, "total">>(`/api/v1/audit/campaigns/${campaignId}/slice`, {
    location_id: locationId, kind, limit: 200,
  });
  const pg: CadraPagination | undefined = res.pagination;
  return { ...res.data, records: res.data?.records ?? [], total: pg?.total_estimate ?? null };
}

// ── photos and captures ──────────────────────────────────────────────────

export interface AuditPhoto {
  id: number;
  url: string;
  mimetype: string | null;
  size: number;
  width: number | null;
  height: number | null;
  sha256: string | null;
  already_synced?: boolean;
}

export type Outcome = "on_register" | "in_sap" | "in_neither";
export type CaptureState = "pending_review" | "accepted" | "returned";
export type LabelState = "present" | "missing" | "unreadable";

export const OUTCOME_WORDS: Record<Outcome, string> = {
  on_register: "Already on Cadra's register",
  in_sap: "In SAP's register, not in Cadra's",
  in_neither: "Found, not in SAP",
};

export const STATE_WORDS: Record<CaptureState, string> = {
  pending_review: "Waiting for review",
  accepted: "Accepted",
  returned: "Returned",
};

export const LABEL_WORDS: Record<LabelState, string> = {
  present: "Label on the item",
  missing: "Label missing",
  unreadable: "Label unreadable",
};

/** The confirmed fields a capture may carry (`CONFIRMED_FIELDS`). */
export interface ConfirmedFields {
  name?: string;
  category_id?: number;
  condition?: "new" | "good" | "fair" | "poor";
  make?: string;
  model_name?: string;
  serial_number?: string;
  colour?: string;
  material?: string;
  dimensions?: string;
  legacy_asset_code?: string;
  notes?: string;
}

export const CONFIRMED_FIELD_WORDS: Record<keyof ConfirmedFields, string> = {
  name: "Description",
  category_id: "Class",
  condition: "Condition",
  make: "Make",
  model_name: "Model",
  serial_number: "Serial",
  colour: "Colour",
  material: "Material",
  dimensions: "Dimensions",
  legacy_asset_code: "Old tag",
  notes: "Notes",
};

export interface AuditCapture {
  capture_id: string;
  id: number;
  campaign: { id: number; name: string };
  location: { id: number; name: string; location_code: string | null };
  outcome: Outcome;
  state: CaptureState;
  asset: { id: number; asset_code: string; name: string | null; location: string | null } | null;
  sap_record: {
    id: number; asset_number: string; sub_number: string | null; class: string | null;
    description: string | null; old_tag: string | null; office_code: string | null;
    capitalized_on: string | null;
  } | null;
  code: string | null;
  scanned_label: string | null;
  label: LabelState | null;
  name: string | null;
  category: { id: number; name: string } | null;
  condition: string | null;
  fields: ConfirmedFields & Record<string, unknown>;
  photos: AuditPhoto[];
  ai_suggestion: { id: number; result: string; suggested: Record<string, unknown> | null } | null;
  captured_at: string | null;
  received_at: string | null;
  captured_by: UserRef | null;
  device: { id: number; name: string };
  duplicate_of: string | null;
  duplicate_basis: "cadra_asset" | "sap_record" | "old_tag" | null;
  reviewed_by: UserRef | null;
  reviewed_at: string | null;
  return_reason: string | null;
  result_asset: { id: number; asset_code: string; register_state: string } | null;
  reprint_label_id: number | null;
  photos_copied: number | null;
  exception_state: "open" | "registered" | "voided" | null;
  exception_resolved_by: UserRef | null;
  exception_resolved_at: string | null;
  exception_void_reason: string | null;
  replayed?: boolean;
}

export const DUPLICATE_WORDS: Record<string, string> = {
  cadra_asset: "the same Cadra asset",
  sap_record: "the same SAP record",
  old_tag: "the same old tag",
};

export async function uploadAuditPhoto(picture: Blob, filename: string): Promise<AuditPhoto> {
  const form = new FormData();
  form.append("file", picture, filename);
  form.append("source", "web");
  return (await apiUpload<AuditPhoto>("/api/v1/audit/photos", form)).data;
}

export interface CaptureBody {
  capture_id: string;
  campaign_id: number;
  location_id: number;
  outcome: Outcome;
  asset_id?: number;
  sap_record_id?: number;
  code?: string;
  scanned_label?: string;
  label?: LabelState;
  photo_ids: number[];
  ai_suggestion_id?: number;
  captured_at: string;
  fields: ConfirmedFields;
}

export async function sendCapture(deviceCode: string, body: CaptureBody): Promise<AuditCapture> {
  return (await apiPost<AuditCapture>("/api/v1/audit/captures", body, {
    headers: { [DEVICE_HEADER]: deviceCode },
  })).data;
}

export interface CapturesPage {
  rows: AuditCapture[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchCaptures(p: {
  campaign_id?: number; location_id?: number; state?: CaptureState; outcome?: Outcome;
  exception_state?: "open" | "registered" | "voided"; duplicates?: boolean; mine?: boolean;
  cursor?: string; limit?: number;
}): Promise<CapturesPage> {
  const res = await apiGet<AuditCapture[]>("/api/v1/audit/captures", {
    campaign_id: p.campaign_id, location_id: p.location_id, state: p.state,
    outcome: p.outcome, exception_state: p.exception_state,
    duplicates: p.duplicates == null ? undefined : String(p.duplicates),
    mine: p.mine ? "true" : undefined, cursor: p.cursor, limit: p.limit ?? 100,
  });
  const pg: CadraPagination | undefined = res.pagination;
  return { rows: res.data ?? [], nextCursor: pg?.next_cursor ?? null, totalEstimate: pg?.total_estimate ?? null };
}

export async function fetchCapture(captureId: string): Promise<AuditCapture> {
  return (await apiGet<AuditCapture>(`/api/v1/audit/captures/${encodeURIComponent(captureId)}`)).data;
}

export async function acceptCapture(captureId: string): Promise<AuditCapture> {
  return (await apiPost<AuditCapture>(`/api/v1/audit/captures/${encodeURIComponent(captureId)}/accept`, {})).data;
}

export async function returnCapture(captureId: string, reason: string): Promise<AuditCapture> {
  return (await apiPost<AuditCapture>(`/api/v1/audit/captures/${encodeURIComponent(captureId)}/return`,
    { reason: reason.trim() })).data;
}

export interface AcceptLine {
  capture_id: string;
  outcome: "done" | "would_do" | "refused";
  status: number;
  code: string | null;
  message: string | null;
  details: Record<string, unknown> | null;
  asset_id?: number | null;
}

export interface AcceptBatchAnswer {
  action: "accept";
  dry_run: boolean;
  total: number;
  done: number;
  refused: number;
  results: AcceptLine[];
}

export async function acceptRoom(campaignId: number, locationId: number, dryRun: boolean): Promise<AcceptBatchAnswer> {
  return (await apiPost<AcceptBatchAnswer>("/api/v1/audit/captures/accept", {
    campaign_id: campaignId, location_id: locationId, dry_run: dryRun,
  })).data;
}

export async function acceptCaptures(captureIds: string[], dryRun: boolean): Promise<AcceptBatchAnswer> {
  return (await apiPost<AcceptBatchAnswer>("/api/v1/audit/captures/accept", {
    capture_ids: captureIds, dry_run: dryRun,
  })).data;
}

export async function registerException(captureId: string): Promise<AuditCapture> {
  return (await apiPost<AuditCapture>(`/api/v1/audit/captures/${encodeURIComponent(captureId)}/register-new`, {})).data;
}

export async function voidException(captureId: string, reason: string): Promise<AuditCapture> {
  return (await apiPost<AuditCapture>(`/api/v1/audit/captures/${encodeURIComponent(captureId)}/void`,
    { reason: reason.trim() })).data;
}

// ── the room, by its code ────────────────────────────────────────────────

export interface RoomRef { id: number; name: string; location_code: string | null }

export type ScanAnswer =
  | { kind: "room"; room: RoomRef }
  | { kind: "asset"; asset: { id: number; asset_code: string; name: string | null; matched_by: string } };

/** A scanned or typed value, resolved by the lookup every scan box uses:
 *  a Cadra label, an asset code or a serial answers the asset; a room code
 *  answers `matched_by: "location"` (handoff 61). A miss throws the
 *  server's 404, in words. */
export async function lookupScan(value: string): Promise<ScanAnswer> {
  const res = await apiGet<{
    matched_by?: string;
    matched_location?: { id: number; name: string; path?: string; location_code: string | null };
    asset_id?: number; asset_code?: string; asset_name?: string;
  }>("/api/v1/barcode/lookup", { query: value.trim() });
  const d = res.data ?? {};
  if (d.matched_by === "location" && d.matched_location) {
    const l = d.matched_location;
    return { kind: "room", room: { id: l.id, name: l.path || l.name, location_code: l.location_code ?? null } };
  }
  return { kind: "asset", asset: { id: Number(d.asset_id), asset_code: d.asset_code ?? "", name: d.asset_name ?? null, matched_by: d.matched_by ?? "" } };
}

/** The rooms directly under a location (one level), for the room picker. */
export async function fetchRoomsUnder(locationId: number): Promise<RoomRef[]> {
  const res = await apiGet<{ id: number; name: string; location_code?: string | null }[]>(
    "/api/v1/locations", { parent_id: locationId, limit: 200 });
  return (res.data ?? []).map(l => ({ id: l.id, name: l.name, location_code: l.location_code ?? null }));
}

// ── SAP's matcher (handoff 63) ───────────────────────────────────────────

export interface MatchResult {
  rank: number;
  reason_code: string;
  reason: string;
  sap_asset: {
    id: number; asset_number: string; sub_number: string | null; class: string | null;
    description: string | null; description_2?: string | null; old_tag: string | null;
    office_code: string | null; capitalized_on: string | null;
  };
}

export interface MatchAnswer {
  basis: string | null;
  pool: number;
  notes: string[];
  results: MatchResult[];
}

export async function matchSap(p: { old_tag?: string; description?: string; office?: string; serial?: string }): Promise<MatchAnswer> {
  return (await apiGet<MatchAnswer>("/api/v1/sap-assets/match", {
    old_tag: p.old_tag?.trim() || undefined,
    description: p.description?.trim() || undefined,
    office: p.office || undefined,
    serial: p.serial?.trim() || undefined,
  })).data;
}

/** Now, as the server reads `captured_at`. */
export function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** The signed-in person's user id, read off the access token's payload
 *  (`uid`). Used only to narrow a list to the campaigns this person is on;
 *  the server decides who may act. */
export function myUid(): number | null {
  try {
    const t = getToken();
    if (!t) return null;
    const part = t.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((part.length + 3) % 4));
    const uid = JSON.parse(json)?.uid;
    return typeof uid === "number" ? uid : null;
  } catch {
    return null;
  }
}
