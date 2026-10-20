import type {
  Asset,
  Location,
  Employee,
  DashboardStats,
  FleetVehicle,
  VehicleType,
  VehicleStatus,
  FuelCard,
  FuelTransaction,
  BusRoute,
  BusSchedule,
  BusBooking,
  IdentityRecord,
} from "../types";
import { allMockAssets } from "../mock/assets";
import { mockLocations } from "../mock/locations";
import { mockEmployees } from "../mock/employees";
import {
  mockFleetVehicles,
  mockFuelCards,
  mockFuelTransactions,
} from "../mock/fleet";
import {
  mockBusRoutes,
  mockBusSchedules,
  mockBusBookings,
} from "../mock/staffBus";
import { mockIdentityRecords } from "../mock/identity";
import { apiConfigured, apiGet, apiPost, apiPatch, apiPut, apiDelete, apiUpload, newIdempotencyKey } from "./api";
import { ENUM_SEED } from "./enums";
import { lagosToday, addDaysIso } from "./utils";
import {
  apiEmployeeToEmployee, type ApiEmployee,
  apiAssetToAsset, type ApiAsset,
  apiLocationToLocation, type ApiLocation,
  apiRequestToRequest, type ApiRequest,
  type ApiAssetDepreciation,
  apiAssetHistoryToAssetHistory, type ApiAssetHistory,
} from "./adapters";
import type { ServiceRequest, AssetHistory } from "../types";
import type {
  ConfigurationChangeReport, DisposalReport, AssetRegisterSnapshot,
} from "../types";

// ─── ASSETS ───────────────────────────────────────────────────────────────────
export interface AssetFilters {
  category?: string;
  status?: string;
  /** A `nrs.asset.condition` key (`new`/`good`/…), passed to the API verbatim.
   *  Never a display label — see the note above `fetchAssetsPage`. */
  condition?: string;
  zone?: string;
  search?: string;
  /** Register-wide row order, passed straight to `GET /api/v1/assets?sort`.
   *  `newest` walks descending asset id so the most recently created asset is
   *  the first row of page one; `oldest` is the API's own default and the
   *  order this list used to show. NOT a filter — it never clears with them.
   *
   *  Whatever sets this MUST include it in the react-query key: the API
   *  records the direction in the cursor and refuses one replayed against
   *  the other, so changing it has to restart the walk from page one. */
  sort?: "newest" | "oldest";
  /** A warranty view — see `warrantyToServerFilter`, the one place it becomes
   *  a server query. */
  warranty?: WarrantyFilter;
  /** `GET /api/v1/assets?register_state=` (handoff 57). Left unset — every
   *  register screen leaves it unset — the server answers with registered
   *  assets only, so a received unit still passing its gates is never counted
   *  as part of the register. `any` (or one state) needs `candidates:read`. */
  registerState?: "any" | RegisterState;
}
export function listAssets(f?: AssetFilters): Asset[] {
  let r = allMockAssets;
  if (f?.category) r = r.filter((a) => a.category === f.category);
  if (f?.status) r = r.filter((a) => a.status === f.status);
  if (f?.condition) r = r.filter((a) => a.condition === f.condition);
  if (f?.zone) r = r.filter((a) => a.location.zone === f.zone);
  // Mock rows carry no warranty block, so every view but the server's is
  // empty here — including `expiring`, which only the server can judge.
  if (f?.warranty) r = r.filter((a) => a.warranty?.status === f.warranty);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.assetTag.toLowerCase().includes(q) ||
        a.legacyCode.toLowerCase().includes(q) ||
        (a.custodianName ?? "").toLowerCase().includes(q) ||
        a.department.toLowerCase().includes(q),
    );
  }
  return r;
}
export function getAsset(id: string): Asset | undefined {
  return allMockAssets.find((a) => a.id === id);
}

// ─── API-BACKED ASSETS ───────────────────────────────────────────────────────

// There is no display->API condition map here any more, and there must not be
// one again. `CONDITION_TO_API` used to translate a four-member display union
// into `nrs.asset.condition`, which has FIVE values. Its own comment argued
// that keying the record by the display union made a dropped filter a compile
// error — and it did, but it made the missing fifth value invisible instead:
// `new` had no display form, so the register could not offer it, and the
// adapter had already relabelled every `new` asset as "Good". Selecting Good
// sent `condition=good` and the API correctly returned only the `good` rows,
// omitting 282 assets (204 jaizbankplc, 54 nrs19, 24 cadra19) that the very
// same table was calling Good. The filter value is now the model's key, taken
// straight from `useEnum("condition")`, and goes to the API untouched.

/**
 * A front-end `status` as the query the server can answer — the ONE place the
 * two are tied together, so the register's Status filter and the dashboard's
 * review queue cannot ask for different sets under the same word.
 *
 * Every mapped status carries `state=active`. All three verdicts are
 * statements about an asset in service (`deriveStatus` in adapters.ts), so a
 * filter that sent `is_verified` alone asked the server for a different set
 * than the one the word names: the dashboard's review queue listed missing
 * and disposed assets as awaiting review.
 *
 * "Review — no SAP code" is `sap_reconciliation_state=exception`, a stored
 * compute the server filters on natively, and because `deriveStatus` ranks it
 * first among active assets EVERY row this returns wears that pill. The other
 * two are not exact the other way round: the API's enum filter takes one
 * value and has no "not", so `is_verified=true|false` also returns the active
 * assets that are SAP exceptions, whose pill says so. The register drops
 * those rows after the fetch (it compares `asset.status` as well); it never
 * shows a row under a status its pill contradicts.
 *
 * "Not in service" has no server filter — the API's `state` takes one value
 * and that status is every state but one — so it is left unfiltered here and
 * narrowed on the rows already loaded.
 */
export function statusToServerFilter(status: string | undefined): Record<string, unknown> {
  switch (status) {
    case "Cleared":               return { state: "active", is_verified: true };
    case "Review — data quality": return { state: "active", is_verified: false };
    case "Review — no SAP code":  return { state: "active", sap_reconciliation_state: "exception" };
    default:                      return {};
  }
}

/**
 * How far ahead "expiring soon" looks, in days. Named because the screen must
 * NAME the window rather than imply it: every place that says "expiring soon"
 * prints this number and the two Lagos dates it spans.
 */
export const WARRANTY_SOON_DAYS = 90;

/** The dates `expiring` spans, as Lagos calendar dates, both inclusive —
 *  the server's `warranty_expires_within_days` window, for printing beside
 *  anything that says "expiring soon". */
export function warrantySoonWindow(): { from: string; to: string } {
  const from = lagosToday();
  return { from, to: addDaysIso(from, WARRANTY_SOON_DAYS) };
}

/** The register's warranty views: the server's three verdicts, plus
 *  `expiring` — under warranty, with the expiry inside `WARRANTY_SOON_DAYS`. */
export type WarrantyFilter = "under_warranty" | "expired" | "none" | "expiring";

/** The views in the order a person reads them: covered, about to lapse,
 *  lapsed, and — the ordinary case — nothing recorded. */
export const WARRANTY_VIEWS: readonly WarrantyFilter[] = ["under_warranty", "expiring", "expired", "none"];

/** A `?warranty=` value, or "" for anything that is not one of the views. */
export function parseWarrantyFilter(v: string | null | undefined): WarrantyFilter | "" {
  return (WARRANTY_VIEWS as readonly string[]).includes(v ?? "") ? (v as WarrantyFilter) : "";
}

/**
 * A warranty view as the query the server can answer — the ONE place the two
 * are tied together, as `statusToServerFilter` is for status. The register's
 * Warranty filter and the dashboard's warranty tiles both go through here, so
 * a tile's number is the count of exactly the rows clicking it shows: a count
 * that is not its filter is this repository's most repeated defect.
 *
 * All four are exact on the server — `warranty_status` and
 * `warranty_expires_within_days` are native filters, the latter judged
 * against the Lagos date (from today to today + N inclusive, so nothing
 * already expired) — and there is no client-side narrowing after the fetch.
 *
 * Nothing here touches `state`. A warranty is a fact about a contract, not
 * about whether the asset is in service: an expired one is not a condition,
 * a lifecycle state or a review finding, and these views include disposed
 * and missing assets exactly as the register does.
 */
export function warrantyToServerFilter(w: WarrantyFilter | "" | undefined): Record<string, unknown> {
  switch (w) {
    case "under_warranty": return { warranty_status: "under_warranty" };
    case "expired":        return { warranty_status: "expired" };
    case "none":           return { warranty_status: "none" };
    case "expiring":       return { warranty_expires_within_days: WARRANTY_SOON_DAYS };
    default:               return {};
  }
}

export interface AssetsPage {
  assets: Asset[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchAssetsPage(
  cursor: string | undefined,
  f?: AssetFilters,
): Promise<AssetsPage> {
  if (!apiConfigured) {
    const all = listAssets(f);
    return { assets: all, nextCursor: null, totalEstimate: all.length };
  }
  const res = await apiGet<ApiAsset[]>("/api/v1/assets", {
    q: f?.search,
    condition: f?.condition || undefined,
    ...statusToServerFilter(f?.status),
    ...warrantyToServerFilter(f?.warranty),
    // Newest-first unless the caller says otherwise. The API's own default
    // is `oldest` and stays that way for every other consumer — this is the
    // register UI choosing its order, not the contract changing under
    // anyone. Only this listing passes it; the count and lookup helpers
    // below fetch by id or ask for `limit: 1`, where order means nothing.
    sort: f?.sort ?? "newest",
    register_state: f?.registerState,
    limit: 200,
    cursor,
  });
  // THE COUNT MUST BE A COUNT OF THE ROWS. Under *Cleared* and *Review — data
  // quality* the server is asked for `is_verified=true|false`, and the API
  // has no way to say "and NOT a SAP exception" — so it also returns the
  // active exceptions, which wear a different pill and are dropped from the
  // list on this side. Its total still counted them: on `test19` the
  // data-quality filter announced about 190 more assets than it listed, and
  // on a register like `jaizbankplc` it would be nearly 600. A number beside
  // a list that does not add up to it is this programme's oldest defect, and
  // handoff 30's first draft shipped it with the explanation in a comment.
  // One extra `limit: 1` read, on the first page only; the dashboard has
  // always subtracted the same overlap.
  let totalEstimate = res.pagination?.total_estimate ?? null;
  const server = statusToServerFilter(f?.status);
  if (totalEstimate !== null && !cursor && "is_verified" in server) {
    const overlap = await countAssets({
      q: f?.search,
      condition: f?.condition || undefined,
      ...server,
      // The overlap is taken over the SAME query as the total it is taken
      // from, warranty view included, or the subtraction mixes two sets.
      ...warrantyToServerFilter(f?.warranty),
      sap_reconciliation_state: "exception",
    });
    totalEstimate = Math.max(0, totalEstimate - overlap);
  }
  return {
    assets: res.data.map(apiAssetToAsset),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate,
  };
}

export type AssetInclude = "transfers" | "pm" | "children";

// `include` opts ride along with both single-asset GETs (serialize_asset expands
// transfers/pm/children inline). We return both the mapped Asset and the raw
// API shape so the detail page can render the embedded collections.
export interface FetchAssetResult {
  asset: Asset;
  raw: ApiAsset & {
    transfers?: ApiAssetTransfer[];
    pm_schedules?: ApiPmSchedule[];
    children?: { id: number; name: string; asset_code: string }[];
  };
}

export interface ApiAssetTransfer {
  id: number;
  reference: string;
  from_location: { id: number; name: string } | null;
  to_location: { id: number; name: string } | null;
  from_custodian: { id: number; name: string } | null;
  to_custodian: { id: number; name: string } | null;
  transfer_date: string | null;
  state: string;
  reason: string | null;
}

export interface ApiPmSchedule {
  id: number;
  name: string | null;
  next_due_date: string | null;
  active: boolean;
}

export async function fetchAsset(id: string, includes?: AssetInclude[]): Promise<Asset | null> {
  if (!apiConfigured) return getAsset(id) ?? null;
  try {
    const res = await apiGet<ApiAsset>(`/api/v1/assets/${id}`, {
      include: includes?.length ? includes.join(",") : undefined,
    });
    return apiAssetToAsset(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

export async function fetchAssetWithIncludes(
  id: string,
  includes: AssetInclude[],
): Promise<FetchAssetResult | null> {
  if (!apiConfigured) {
    const a = getAsset(id);
    if (!a) return null;
    // Mock fallback can't synthesize transfers/pm — return the shaped Asset
    // with empty include collections.
    return { asset: a, raw: {} as FetchAssetResult["raw"] };
  }
  try {
    const res = await apiGet<FetchAssetResult["raw"]>(`/api/v1/assets/${id}`, {
      include: includes.join(","),
    });
    return { asset: apiAssetToAsset(res.data), raw: res.data };
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

// ─── ASSET MUTATIONS ─────────────────────────────────────────────────────────

/**
 * A SUBSET of `_WRITABLE_FIELDS` in myservice_api/controllers/v1_assets.py —
 * the keys this app has a control for — and never a superset. That is the
 * whole job of this type since handoff 31: a key the route does not accept is
 * a `400` that saves NOTHING, so a key declared here and absent there is a
 * Save button that fails. The compiler should refuse what the server refuses.
 *
 * `asset_tag` was declared here until then, although the server has left it
 * out of the allow-list on purpose since handoff 04 and `AssetForm.toBody`
 * deliberately does not send it. Nothing sent it; the type merely offered to
 * let the next form do so.
 */
export interface AssetWriteBody {
  name?: string;
  legacy_asset_code?: string | null;
  serial_number?: string | null;
  make?: string | null;
  model_name?: string | null;
  manufacturer?: string | null;
  // Section 12 (handoff 58): writable on POST/PATCH /assets.
  colour?: string | null;
  material?: string | null;
  dimensions?: string | null;
  // Handoff 59: what a `record_only` unit (land, a building, a licence) is
  // identified by — a title or plot number, a licence key, a contract.
  record_reference?: string | null;
  category_id?: number | null;
  subcategory_id?: number | null;
  asset_type_id?: number | null;
  asset_level?: string | null;
  domain?: string | null;
  parent_id?: number | null;
  // No `building_id` / `floor_id` / `room_id`. They left `_WRITABLE_FIELDS` in
  // handoff 30: on the Odoo form they drive `location_id` through an onchange
  // the API never runs, so a PATCH of one rewrote the building and moved
  // nothing. `location_id` is the one writable statement of where an asset
  // is. They are still READ, under `location_hierarchy`.
  location_id?: number | null;
  custodian_id?: number | null;
  department?: string | null;
  // Model keys, not unions. These two were hand-written copies of
  // `nrs.asset.condition` and `nrs.asset.state` — the last pair of local
  // declarations of a set the back end owns in the write path, and the same
  // kind of copy that lost `new` on the read path. The sets are read from the
  // model at request time via `useEnum`/`ENUM_SEED`, and `AssetForm` populates
  // both fields from that published set, so narrowing them here would only
  // re-create a second opinion about the model's own Selection. A value the
  // model gains is accepted by this body the day it exists; an invalid one is
  // refused by the API with a 400, which is where that judgement belongs.
  condition?: string;
  state?: string;
  currency_id?: number | null;
  purchase_date?: string | null;
  // Handoff 34. `warranty_expiry` is written ONLY when there is no duration:
  // with `warranty_months` + `warranty_start_date` the server derives it, and
  // refuses one sent that disagrees — so the form leaves it out entirely.
  // Months and start date travel together; one without the other is refused.
  warranty_expiry?: string | null;
  warranty_months?: number | null;
  warranty_start_date?: string | null;
  warrantor?: string | null;
  warranty_reference?: string | null;
  purchase_value?: number | null;
  replacement_cost?: number | null;
  acquisition_date?: string | null;
  acquisition_cost?: number | null;
  current_value?: number | null;
  disposal_date?: string | null;
  disposal_reason?: string | null;
  maintenance_vendor_id?: number | null;
  last_verified_date?: string | null;
  verification_notes?: string | null;
  notes?: string | null;
  // Handoff 64: the suggestion from a photo this save worked from, and the
  // fields the person dismissed. It decides what the save RECORDS (per field
  // accepted / changed / ignored), never what it writes; the server takes it
  // off the body before the allow-list.
  ai_suggestion?: { id: number; ignored?: string[] };
}

export async function createAsset(body: AssetWriteBody): Promise<Asset> {
  const res = await apiPost<ApiAsset>("/api/v1/assets", body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiAssetToAsset(res.data);
}

export async function updateAsset(id: string, body: AssetWriteBody): Promise<Asset> {
  const res = await apiPatch<ApiAsset>(`/api/v1/assets/${id}`, body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiAssetToAsset(res.data);
}

/**
 * WHAT A MOVE OR A CUSTODY CHANGE ACTUALLY DID — and since handoff 35 there
 * are two answers, on the same HTTP 200.
 *
 * On a tenant that requires approval, `POST /assets/<id>/move` and
 * `POST /assets/<id>/transfer-custody` no longer move anything: they raise an
 * `nrs.asset.change.request` and answer `pending_approval: true` with the
 * request and with the asset UNCHANGED, read back in the same response. The
 * status stays 200 — the API has no per-call status override and the server
 * explains at length why it did not invent one for this — so **the status
 * tells the caller nothing and the body tells it everything.**
 *
 * That is why this returns a discriminated union rather than an `Asset`. A
 * caller that took the asset out of the envelope and closed its dialog would
 * report a move that has not happened, to a storekeeper standing next to the
 * thing that has not moved. The union makes that unrepresentable: you cannot
 * read `.asset` without having gone past `pendingApproval` in the type.
 */
export interface ApprovalRef { id: number; name: string }

/** The `request` block of a raised request, as the two ASSET routes publish
 *  it. Deliberately a subset of `ApprovalRequest` below — `/move` answers
 *  with what it just created and not with the queue's computed view of it
 *  (`premise_holds`, `can_decide`), and typing it as the full record would
 *  invite a screen to read keys that are not on the wire. */
export interface RaisedApprovalRequest {
  id: number;
  reference: string;
  state: ApprovalState;
  change_type: ApprovalChangeType;
  approver: ApprovalRef | null;
  requested_by: ApprovalRef | null;
  requested_at: string | null;
  to_location: ApprovalRef | null;
  to_custodian: ApprovalRef | null;
  reason: string | null;
}

export type AssetChangeResult =
  | { pendingApproval: true; request: RaisedApprovalRequest | null; asset: Asset }
  | { pendingApproval: false; asset: Asset };

/** The shape both routes answer with, with every key either contract may
 *  carry. `pending_approval` is absent on a tenant that does not require
 *  approval; it is never `false` from the server today, and this reads it as
 *  a strict `=== true` so that an absent key and an unexpected one both fall
 *  to "it happened", which is what the old contract means. */
interface AssetChangeResponse {
  asset: ApiAsset;
  pending_approval?: boolean;
  action?: string;
  request?: RaisedApprovalRequest;
  transfer?: ApiAssetTransfer | null;
  custody_change?: unknown;
  movement_id?: number | null;
}

function readAssetChange(d: AssetChangeResponse): AssetChangeResult {
  // BRANCH ON `pending_approval` ALONE. The first cut read
  // `d.pending_approval === true && d.request`, and the `&& d.request` was
  // on the wrong side of the safety argument: a 200 saying the change is
  // PENDING but carrying no `request` object would have fallen into the
  // success branch, closed the dialog, invalidated the asset and told the
  // storekeeper it moved. The whole point of this function is that the one
  // thing we must never get wrong is that direction. A missing `request` is
  // a server defect, and the honest answer to it is "we do not know the
  // reference", not "it happened". Found by the verification pass.
  if (d.pending_approval === true) {
    return { pendingApproval: true, request: d.request ?? null, asset: apiAssetToAsset(d.asset) };
  }
  return { pendingApproval: false, asset: apiAssetToAsset(d.asset) };
}

/**
 * `approverId` is WHO IS BEING ASKED, and it is only ever sent when the
 * tenant requires approval — the server refuses a nomination it did not ask
 * for on some routes and ignores it on others, and sending a key the route
 * does not want is the class of defect handoff 31 spent a whole handoff
 * closing. The caller (`AssetMoveDialog`) reads
 * `GET /api/v1/settings/approvals` and passes it only then.
 */
export async function moveAsset(
  id: string,
  to_location_id: number,
  reason?: string,
  approverId?: number,
): Promise<AssetChangeResult> {
  // The move endpoint returns an envelope { asset, transfer }, not a bare
  // asset — or, on a tenant requiring approval, { pending_approval, request,
  // asset } with the asset unchanged. See `readAssetChange`.
  const res = await apiPost<AssetChangeResponse>(
    `/api/v1/assets/${id}/move`,
    { to_location_id, reason, ...(approverId ? { approver_id: approverId } : {}) },
    { idempotencyKey: newIdempotencyKey() },
  );
  return readAssetChange(res.data);
}

export async function transferCustody(
  id: string,
  to_custodian_id: number,
  reason?: string,
  approverId?: number,
): Promise<AssetChangeResult> {
  // The transfer-custody endpoint returns an envelope { asset, custody_change }
  // — or the pending-approval envelope. See `moveAsset`.
  const res = await apiPost<AssetChangeResponse>(
    `/api/v1/assets/${id}/transfer-custody`,
    { to_custodian_id, reason, ...(approverId ? { approver_id: approverId } : {}) },
    { idempotencyKey: newIdempotencyKey() },
  );
  return readAssetChange(res.data);
}

// ─── ASSET COUNTS (cheap dashboard primitives) ───────────────────────────────

/** Single count via limit=1 + total_estimate. */
async function countAssets(params: Record<string, unknown>): Promise<number> {
  if (!apiConfigured) return 0;
  const res = await apiGet<ApiAsset[]>("/api/v1/assets", { ...params, limit: 1 });
  return res.pagination?.total_estimate ?? 0;
}

/** One count per warranty view, keyed by the view. */
export type WarrantyCounts = Record<WarrantyFilter, number>;

/**
 * The dashboard's warranty tiles. Each count is `warrantyToServerFilter` of
 * its view and nothing else, which is also exactly what the tile's link opens
 * the register on — so the number on the tile and the rows behind it are one
 * query asked twice.
 *
 * Deliberately NOT part of `fetchAssetRegisterCounts`: those are statements
 * about stock, and a warranty is not one.
 */
export async function fetchWarrantyCounts(): Promise<WarrantyCounts> {
  const views = WARRANTY_VIEWS;
  if (!apiConfigured) {
    return Object.fromEntries(views.map(v => [v, 0])) as WarrantyCounts;
  }
  const counts = await Promise.all(views.map(v => countAssets(warrantyToServerFilter(v))));
  return Object.fromEntries(views.map((v, i) => [v, counts[i]])) as WarrantyCounts;
}

export interface AssetRegisterCounts {
  total: number;
  active: number;
  inRepair: number;
  disposed: number;
  missing: number;
  /** ACTIVE and unverified. Not "unverified" over the whole register. */
  unverified: number;
  /** ACTIVE and verified: `active - unverified`. */
  verified: number;
}

/**
 * Asset Register dashboard top strip. Runs six count queries in parallel —
 * each is a single limit=1 call so this is cheap.
 *
 * `unverified` carries `state: "active"`, and it did not. Unfiltered, it
 * counted every missing and every disposed asset that had never been verified
 * as unverified STOCK — work for somebody to go and do, on an asset that is
 * gone — and the derived `verified = total - unverified` then counted every
 * disposed asset as VERIFIED. Both figures are now statements about assets in
 * service, which is the only place a verification means anything.
 *
 * `missing` is here because nothing counted it: Total − Active − Under Repair
 * − Condemned did not come to zero and nothing on the strip explained the gap.
 * It replaced a "PM Overdue" tile that was permanently "—": the API exposes no
 * maintenance due/overdue count for assets, so that tile could never say
 * anything.
 */
export async function fetchAssetRegisterCounts(): Promise<AssetRegisterCounts> {
  if (!apiConfigured) {
    return { total: 0, active: 0, inRepair: 0, disposed: 0, missing: 0, unverified: 0, verified: 0 };
  }
  const [total, active, inRepair, disposed, missing, unverified] = await Promise.all([
    countAssets({}),
    countAssets({ state: "active" }),
    countAssets({ state: "in_repair" }),
    countAssets({ state: "disposed" }),
    countAssets({ state: "missing" }),
    countAssets({ is_verified: false, state: "active" }),
  ]);
  return { total, active, inRepair, disposed, missing, unverified, verified: Math.max(0, active - unverified) };
}

/** The figures the dashboard's status breakdown is made of, as counts over
 *  the register rather than a window of it. Named by what they ARE — the
 *  chart derives its slices, and says how, where it draws them.
 *
 *  Five counts for four slices, because the slices have to PARTITION the
 *  register and two of the facts overlap: an active asset can be both
 *  unverified and an SAP exception, and `deriveStatus` gives it one status
 *  (the exception). `activeUnverifiedException` is that overlap, counted so it
 *  can be taken out of the data-quality slice instead of being drawn twice —
 *  the server ANDs its filters, so it is one request like the others.
 *
 *  Every exception figure carries `state: "active"`. A disposed asset can be
 *  an SAP exception too, and it is "Not in service": counting it here would
 *  fold it back into stock, which is what handoff 29 took out. */
export interface AssetStatusCounts {
  total: number;
  active: number;
  activeUnverified: number;
  activeException: number;
  activeUnverifiedException: number;
}

export async function fetchAssetStatusCounts(): Promise<AssetStatusCounts> {
  if (!apiConfigured) {
    return { total: 0, active: 0, activeUnverified: 0, activeException: 0, activeUnverifiedException: 0 };
  }
  const [total, active, activeUnverified, activeException, activeUnverifiedException] = await Promise.all([
    countAssets({}),
    countAssets({ state: "active" }),
    countAssets({ is_verified: false, state: "active" }),
    countAssets({ sap_reconciliation_state: "exception", state: "active" }),
    countAssets({ sap_reconciliation_state: "exception", is_verified: false, state: "active" }),
  ]);
  return { total, active, activeUnverified, activeException, activeUnverifiedException };
}

// ─── CATEGORY-SCOPED DASHBOARD (e.g. IT Assets Command) ──────────────────────

export interface CategoryDashboardData {
  categoryId: number;
  categoryName: string;
  total: number;
  active: number;
  inRepair: number;
  disposed: number;
  /** ACTIVE and unverified — see `fetchAssetRegisterCounts` for why the state
   *  filter is there. */
  unverified: number;
  /** One count per `nrs.asset.condition` value, keyed by the model's own key.
   *  Not a five-field object: that shape wrote the Selection out a sixth
   *  time, so a value the model gained would have been dropped from the
   *  dashboard without anybody being told. */
  byCondition: Record<string, number>;
  recent: Asset[];
}

/** Resolves a category id by name match against the /dashboard/kpis payload.
 *  Returns null when the category isn't present (or the kpi payload doesn't
 *  carry the assets block — older API builds). */
async function findCategoryByName(rx: RegExp): Promise<{ id: number; name: string } | null> {
  const res = await apiGet<{ assets?: { categories?: Array<{ id: number | null; name: string; count: number }> } }>(
    "/api/v1/dashboard/kpis",
  );
  const cats = res.data.assets?.categories ?? [];
  const found = cats.find(c => c.id != null && rx.test(c.name));
  return found?.id != null ? { id: found.id, name: found.name } : null;
}

/** Build a category-scoped command-centre payload. Internal helper — the IT
 *  flavour is exposed below; mirror for other categories (Furniture, etc.) as
 *  needed without re-implementing the orchestration. */
async function fetchCategoryDashboard(categoryRegex: RegExp): Promise<CategoryDashboardData | null> {
  if (!apiConfigured) return null;
  const cat = await findCategoryByName(categoryRegex);
  if (!cat) return null;
  const id = cat.id;
  // One count per condition, derived from the set rather than written out.
  // These five calls used to be five literals — the last copy of
  // `nrs.asset.condition` left in the front end after this handoff, and the
  // quietest: a value the model gained would simply not have been counted,
  // and a bar chart with a missing bar looks exactly like a bar chart.
  //
  // `ENUM_SEED` rather than `useEnum` because this is not a component and
  // cannot call a hook. The seed is held against the model by
  // `tests/test_frontend_enums.py`, so it is a guarded copy rather than a
  // second opinion.
  const conditions = ENUM_SEED.condition.map(o => o.value);
  const [
    total, active, inRepair, disposed, unverified,
    conditionCounts,
    recentRes,
  ] = await Promise.all([
    countAssets({ category_id: id }),
    countAssets({ category_id: id, state: "active" }),
    countAssets({ category_id: id, state: "in_repair" }),
    countAssets({ category_id: id, state: "disposed" }),
    countAssets({ category_id: id, is_verified: false, state: "active" }),
    Promise.all(conditions.map(c => countAssets({ category_id: id, condition: c }))),
    apiGet<ApiAsset[]>("/api/v1/assets", { category_id: id, limit: 20 }),
  ]);
  return {
    categoryId: id,
    categoryName: cat.name,
    total, active, inRepair, disposed, unverified,
    byCondition: Object.fromEntries(
      conditions.map((c, i) => [c, conditionCounts[i]]),
    ),
    recent: recentRes.data.map(apiAssetToAsset),
  };
}

// Word boundaries, not substrings — handoff 52 §3. The unanchored
// case-insensitive `/IT|.../i` was satisfied by the "it" inside
// "Furn**it**ure" and "Secur**it**y/CCTV", and on jaizbankplc the page
// titled IT Assets Command reported 21 Furniture records. Matching on a
// stable key was measured and lost: `nrs.asset.category` carries `code`
// and `domain`, but both are SEED values — on jaizbankplc the one
// IT-populated category, "IT Equipment" (21 assets), has neither, so a
// `domain = 'it'` match would have missed every real IT asset on the one
// tenant that showed the defect. The category's name is the only key every
// tenant fills in; `\b` is what keeps it from matching the inside of a word.
export const fetchITAssetsDashboard = () =>
  fetchCategoryDashboard(/\b(IT|computer|laptop|server)\b/i);

// NOT a PATCH, and it used to be one. `PATCH {last_verified_date}` records a
// date and NO PERSON — `last_verified_by` is deliberately not writable, because
// a verifier the client can name is a claim rather than evidence — so every
// verification made from this button left a government register unable to say
// who had checked the asset. `POST /assets/<id>/verify` takes no date and no
// verifier: the date is the server's today and the verifier is whoever is
// logged in. It also stops this browser's clock deciding the date.
export async function markAssetVerified(id: string): Promise<Asset> {
  // Like /move, the route returns an envelope { asset, verification }.
  const res = await apiPost<{
    asset: ApiAsset;
    verification: { verified_on: string | null; verified_by: { id: number; name: string } | null; notes: string | null };
  }>(
    `/api/v1/assets/${id}/verify`,
    {},
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data.asset);
}

// NOT a PATCH, and until handoff 30 it was one: `PATCH {state: "missing"}`,
// which has nowhere to put a sentence — so the first question anybody asks
// about an asset that cannot be found, *why*, had no answer anywhere. The
// route REQUIRES a reason and writes it to the asset's append-only
// `status_changed` event: what was said when it was marked, and by whom,
// which nobody can tidy up afterwards. It is not a field on the asset.
//
// 409 `conflict` when the asset is already missing, or disposed — a disposed
// asset's status cannot change, for any caller. 400 when the reason is blank.
export async function markAssetMissing(id: string, reason: string): Promise<Asset> {
  const res = await apiPost<{ asset: ApiAsset; event_id: number | null }>(
    `/api/v1/assets/${id}/mark-missing`,
    { reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data.asset);
}

// The other half of `markAssetMissing`, and new in handoff 31. A missing asset
// that turned up used to be put back through Edit → State, which is a PATCH,
// which has nowhere to put a sentence: the asset reappeared having recorded
// nothing about where it had been. The route REQUIRES a reason — where it
// turned up — and writes it to the same append-only `status_changed` event
// record. It sets the state back to `active` and does NOT verify the asset:
// whoever found it may not be whoever checks it.
//
// 409 `conflict` unless the asset is missing. 400 when the reason is blank.
export async function markAssetFound(id: string, reason: string): Promise<Asset> {
  const res = await apiPost<{ asset: ApiAsset; event_id: number | null }>(
    `/api/v1/assets/${id}/mark-found`,
    { reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data.asset);
}

// The reason and NOTHING else. `POST /assets/<id>/condemn` calls the model's
// own `action_condemn`, which sets the state, the condition and the disposal
// date together, on the server, as a Lagos day. This used to be a PATCH of all
// four with the date read off this browser's clock, because a PATCH was then a
// plain `write` that stamped nothing. (Since handoff 31 the model dates a
// disposal and sets its condition through any door, PATCH included; this
// route is still the one that takes the REASON.) No date is sent now, and one
// must not be added back: a date a client sends is whatever the client's
// clock says, and the model respects a date it is sent.
//
// 409 `conflict` when the asset is already disposed. Disposal is terminal.
export async function condemnAsset(id: string, reason: string): Promise<Asset> {
  const res = await apiPost<{ asset: ApiAsset; disposal: unknown; event_id: number | null }>(
    `/api/v1/assets/${id}/condemn`,
    { reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data.asset);
}
export function getAssetsByCategory() {
  return [
    { name: "IT Equipment", value: 10259 },
    { name: "Fleet / Vehicles", value: 1619 },
    { name: "Furniture & Fittings", value: 1272 },
  ];
}
// MOCK figures, for mock mode only (`!apiConfigured`). With an API configured
// the dashboard plots `fetchAssetStatusCounts()` instead: this used to be drawn
// as percentages of the LIVE total, five invented numbers beside real ones.
// Three of the five were statuses no record can carry and are gone.
export function getAssetsByStatus() {
  return [
    { name: "Cleared", value: 10842 },
    { name: "Review — data quality", value: 985 },
  ];
}
export function getReviewQueueAssets(): Asset[] {
  return allMockAssets.filter((a) => a.status !== "Cleared").slice(0, 8);
}

// ─── LOCATIONS ────────────────────────────────────────────────────────────────
export function listLocations(): Location[] {
  return mockLocations;
}
export function getLocation(id: string): Location | undefined {
  return mockLocations.find((l) => l.id === id);
}

// ─── API-BACKED LOCATIONS ────────────────────────────────────────────────────

export interface LocationsPage {
  locations: Location[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchLocationsPage(
  cursor: string | undefined,
  search?: string,
): Promise<LocationsPage> {
  if (!apiConfigured) {
    const r = search
      ? mockLocations.filter(l => l.name.toLowerCase().includes(search.toLowerCase()))
      : mockLocations;
    return { locations: r, nextCursor: null, totalEstimate: r.length };
  }
  // Backend bumped MAX_PAGE_LIMIT to 2000 for frontend tokens, so the full
  // ~1.2k location set fits in a single round-trip. External tokens still
  // get clamped to 100 server-side regardless of what we ask for.
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", {
    q: search,
    limit: 2000,
    cursor,
  });
  return {
    locations: res.data.map(apiLocationToLocation),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

// Eager loader for callers that need the full tree (Locations page builds
// parent paths and zone lookups across the whole set). 1.1k records, ~6
// round-trips through cursor pagination; cached by react-query thereafter.
export async function fetchAllLocations(): Promise<Location[]> {
  if (!apiConfigured) return mockLocations;
  const all: ApiLocation[] = [];
  let cursor: string | undefined;
  do {
    const res = await apiGet<ApiLocation[]>("/api/v1/locations", { limit: 200, cursor });
    all.push(...res.data);
    cursor = res.pagination?.next_cursor ?? undefined;
  } while (cursor);
  return all.map(apiLocationToLocation);
}

// ─── LOCATION TREE-WALK ENDPOINTS ────────────────────────────────────────────

export async function fetchLocationChildren(id: string): Promise<Location[]> {
  if (!apiConfigured) return mockLocations.filter(l => l.parent === id);
  const res = await apiGet<ApiLocation[]>(`/api/v1/locations/${id}/children`);
  return res.data.map(apiLocationToLocation);
}

export async function fetchLocationAncestors(id: string): Promise<Location[]> {
  if (!apiConfigured) {
    const out: Location[] = [];
    let cur = mockLocations.find(l => l.id === id);
    while (cur?.parent) {
      const p = mockLocations.find(l => l.id === cur!.parent);
      if (!p) break;
      out.unshift(p);
      cur = p;
    }
    return out;
  }
  const res = await apiGet<ApiLocation[]>(`/api/v1/locations/${id}/ancestors`);
  return res.data.map(apiLocationToLocation);
}

export interface LocationsPageMeta extends LocationsPage {}

export async function fetchLocationDescendantsPage(
  id: string,
  cursor: string | undefined,
): Promise<LocationsPageMeta> {
  if (!apiConfigured) {
    const all = mockLocations.filter(l => l.parent === id);
    return { locations: all, nextCursor: null, totalEstimate: all.length };
  }
  const res = await apiGet<ApiLocation[]>(`/api/v1/locations/${id}/descendants`, {
    limit: 200, cursor,
  });
  return {
    locations: res.data.map(apiLocationToLocation),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

// ─── LOCATION MUTATIONS ──────────────────────────────────────────────────────

/** Body shape mirrors _WRITABLE_FIELDS in v1_locations.py. */
export interface LocationWriteBody {
  name?: string;
  description?: string | null;
  active?: boolean;
  parent_id?: number | null;
  type_id?: number | null;
  location_type?: string | null;
  street?: string | null;
  street2?: string | null;
  zip?: string | null;
  city?: string | null;
  state_id?: number | null;
  country_id?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  zone_code?: string | null;
  floor_number?: number | null;
  building_id?: number | null;
  partner_id?: number | null;
}

export async function createLocation(body: LocationWriteBody): Promise<Location> {
  const res = await apiPost<ApiLocation>("/api/v1/locations", body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiLocationToLocation(res.data);
}

export async function updateLocation(id: string, body: LocationWriteBody): Promise<Location> {
  const res = await apiPatch<ApiLocation>(`/api/v1/locations/${id}`, body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiLocationToLocation(res.data);
}

// ─── IDENTITY EXTRAS ─────────────────────────────────────────────────────────

/** Fast count via `limit=1` + total_estimate. */
async function countEmployees(params: Record<string, unknown>): Promise<number> {
  if (!apiConfigured) return 0;
  const res = await apiGet<ApiEmployee[]>("/api/v1/identity/employees", { ...params, limit: 1 });
  return res.pagination?.total_estimate ?? 0;
}

export async function fetchSapSyncStatusCounts(): Promise<{
  synced: number; pending: number; error: number; never: number; total: number;
}> {
  if (!apiConfigured) {
    return { synced: 0, pending: 0, error: 0, never: 0, total: 0 };
  }
  const [synced, pending, error, never, total] = await Promise.all([
    countEmployees({ sap_sync_status: "synced" }),
    countEmployees({ sap_sync_status: "pending" }),
    countEmployees({ sap_sync_status: "error" }),
    countEmployees({ sap_sync_status: "never" }),
    countEmployees({}),
  ]);
  return { synced, pending, error, never, total };
}

/** Latest sync timestamp — found by sorting employees by sap.last_sync DESC. */
export async function fetchLatestSapSync(): Promise<string | null> {
  if (!apiConfigured) return null;
  const res = await apiGet<ApiEmployee[]>("/api/v1/identity/employees", {
    sap_sync_status: "synced",
    limit: 200,
  });
  const stamps = res.data
    .map(e => e.sap.last_sync)
    .filter((s): s is string => !!s)
    .sort((a, b) => b.localeCompare(a));
  return stamps[0] ?? null;
}

/** Lookup an employee by IR number — returns the Employee record or null. */
export async function fetchEmployeeByIr(ir: string): Promise<Employee | null> {
  if (!apiConfigured) {
    return mockEmployees.find(e => e.irNumber === ir) ?? null;
  }
  try {
    const res = await apiGet<ApiEmployee>(`/api/v1/identity/employees/by-ir/${encodeURIComponent(ir)}`);
    return apiEmployeeToEmployee(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

// ─── EMPLOYEE BULK IMPORT (multipart + async polling) ────────────────────────

export interface ImportJobStatus {
  job_id: number;
  state: "queued" | "running" | "done" | "error" | string;
  rows_total?: number | null;
  rows_processed?: number | null;
  rows_created?: number | null;
  rows_updated?: number | null;
  rows_failed?: number | null;
  errors?: Array<{ row: number; field?: string; message: string }>;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
}

export async function submitEmployeeImport(file: File, sheet?: string): Promise<ImportJobStatus> {
  const form = new FormData();
  form.append("file", file);
  if (sheet) form.append("sheet", sheet);
  const res = await apiUpload<ImportJobStatus>("/api/v1/integrations/employees/import", form, {
    idempotencyKey: newIdempotencyKey(),
  });
  return res.data;
}

export async function fetchImportJobStatus(jobId: number): Promise<ImportJobStatus> {
  const res = await apiGet<ImportJobStatus>(`/api/v1/integrations/employees/import/${jobId}`);
  return res.data;
}

// ─── DASHBOARDS (aggregate endpoints) ────────────────────────────────────────

export interface DashboardKpis {
  fleet:     { total: number; overdue: number; due_soon: number; ok: number; no_schedule: number };
  locations: { total: number; mapped: number };
  requests:  { open: number; maintenance: number; today: number };
  vendors:   { total: number; approved: number };
  // Added in the asset_categories backend slice. Optional so older API
  // builds without the change still typecheck.
  assets?:   { total: number; categories: Array<{ id: number | null; name: string; count: number }> };
}

export interface DashboardMapLocation {
  id: number; name: string; lat: number; lng: number;
  state: string; type: string; open_requests: number; model: string;
}
export interface DashboardMapFleet {
  id: number; name: string; plate: string; lat: number; lng: number;
  status: string; driver: string; location: string; state: string; type: string; model: string;
}
/** `GET /dashboard/map` carries ONLY the locations since handoff 50 §2.1.
 *  The vehicle rows moved to `GET /fleet/map` (`FleetMap`, `operations:read`)
 *  so a `dashboards:read` holder stops receiving every plate and driver, and
 *  `recent_requests` is gone outright — the keys declared here were never
 *  the ones the server sent, a recorded drift nothing ever read. */
export interface DashboardMap {
  locations: DashboardMapLocation[];
}
/** The fleet's own map feed (handoff 50 §2.1): the old vehicle-row shape,
 *  behind the fleet's own scope. */
export interface FleetMap {
  fleet: DashboardMapFleet[];
}

// ── Depreciation (PRD §8.6) ───────────────────────────────────────────────

export interface DepreciationPeriod {
  sequence: number;
  period_end: string;
  charge: number;
  accumulated_depreciation: number;
  book_value: number;
}

export interface AssetDepreciationSchedule {
  asset: { id: number; asset_code: string; name: string };
  summary: ApiAssetDepreciation;
  as_of: string | null;
  currency: { id: number; name: string } | null;
  period_count: number;
  periods: DepreciationPeriod[];
}

export interface DepreciationCategoryRow {
  id: number;
  name: string;
  asset_count: number;
  depreciable_cost: number;
  accumulated_depreciation: number;
  current_book_value: number;
}

export interface DepreciationReport {
  totals: {
    asset_count: number;
    depreciable_cost: number;
    accumulated_depreciation: number;
    current_book_value: number;
  };
  by_category: DepreciationCategoryRow[];
  by_state: Record<string, number>;
  by_method: Record<string, number>;
  /** Assets whose start date was inferred rather than recorded. */
  needs_start_date: number;
  /** Assets with a depreciation method but no cost to depreciate. */
  missing_cost: number;
}

/** The period-by-period board for one asset. `asOf` truncates it for a
 *  point-in-time view (PRD §13.4). */
// ── Who is signed in ──────────────────────────────────────────────────────

/** One role the signed-in person holds — the server's `{key, name}` rows,
 *  the same vocabulary the Users page prints (handoff 56). */
export interface WhoAmIRole { key: string; name: string }

export interface WhoAmI { id: number; name: string | null; login: string | null; roles: WhoAmIRole[] }

/** The signed-in user, from the token. `GET /auth/whoami` has existed for as
 *  long as the login has and nothing called it: the top bar printed a name it
 *  had been given in the source instead. Null without a live API — there is
 *  nobody signed in to name, and the top bar then names nobody. A server
 *  that predates `roles` (handoff 56) answers without the key: an empty
 *  list, and the bar degrades to naming nobody's role rather than crashing. */
export async function fetchWhoAmI(): Promise<WhoAmI | null> {
  if (!apiConfigured) return null;
  const res = await apiGet<{ id: number; name?: string | null; login?: string | null; roles?: WhoAmIRole[] | null }>("/api/v1/auth/whoami");
  return {
    id: res.data.id,
    name: res.data.name || null,
    login: res.data.login || null,
    roles: Array.isArray(res.data.roles) ? res.data.roles : [],
  };
}

export const fetchAssetDepreciation = async (id: string | number, asOf?: string) =>
  (await apiGet<AssetDepreciationSchedule>(
    `/api/v1/assets/${id}/depreciation`,
    asOf ? { as_of: asOf } : undefined,
  )).data;

// ── Asset history ─────────────────────────────────────────────────────────

/** Everything recorded about one asset, on one clock — with the server's own
 *  account of where that record begins and what it never holds.
 *
 *  `sort` is the order of `events` and nothing else; whatever calls this MUST
 *  put it in the react-query key.
 *
 *  Returns `null` without a live API. There is no mock history and there must
 *  not be one: an invented chain of custody on a demo build is exactly the
 *  claim this endpoint exists to stop the screen making. The caller says, in
 *  words, that history needs a live server. */
export async function fetchAssetHistory(
  id: string | number,
  sort: "newest" | "oldest" = "newest",
): Promise<AssetHistory | null> {
  if (!apiConfigured) return null;
  const res = await apiGet<ApiAssetHistory>(`/api/v1/assets/${id}/history`, { sort });
  return apiAssetHistoryToAssetHistory(res.data);
}

export const fetchDepreciationReport = async (categoryId?: number) =>
  (await apiGet<DepreciationReport>(
    "/api/v1/reports/depreciation",
    categoryId ? { category_id: categoryId } : undefined,
  )).data;

export const fetchDashboardKpis = async () =>
  (await apiGet<DashboardKpis>("/api/v1/dashboard/kpis")).data;
export const fetchDashboardMap = async () =>
  (await apiGet<DashboardMap>("/api/v1/dashboard/map")).data;
/** The vehicle pins, from the fleet's own route (handoff 50 §2.1). Refused
 *  without `operations:read` — the server's gate, not this function's. */
export const fetchFleetMap = async () =>
  (await apiGet<FleetMap>("/api/v1/fleet/map")).data;

// ── FM dashboard ──────────────────────────────────────────────────────────

export interface FmRecentRequest {
  id: number; name: string; stage: string; stage_code: string;
  category: string; location: string; priority: string;
  deadline: string; is_overdue: boolean; create_date: string;
}
export interface FmDashboard {
  kpis: { open: number; overdue: number; escalated: number; in_progress: number; resolved_today: number };
  sla_data: Array<{ domain: string; open: number; overdue: number; escalated: number; sla_pct: number }>;
  recent_requests: FmRecentRequest[];
  team_workload?: Array<{ user_id: number | null; name: string; assigned: number }>;
  overdue_list?: FmRecentRequest[];
  map_locations?: DashboardMapLocation[];
}
export const fetchFmDashboard = async () =>
  (await apiGet<FmDashboard>("/api/v1/fm/dashboard")).data;

// ── Fleet dashboard ──────────────────────────────────────────────────────

export interface FleetVehicleRow {
  id: number; name: string; license: string; model: string; brand: string;
  state: string; driver: string; location: string; maint_status: string;
  next_service: string; fuel_type: string; odometer: number; is_staff_bus: boolean;
}
export interface FleetDashboard {
  kpis: {
    total: number; active: number; ok: number; due_soon: number; overdue: number;
    expiring_insurance: number; expiring_roadworthy: number; staff_buses: number;
    vendors: number; approved_vendors: number;
  };
  vehicles: FleetVehicleRow[];
}
export const fetchFleetDashboard = async () =>
  (await apiGet<FleetDashboard>("/api/v1/fleet/dashboard")).data;

// ── Security ──────────────────────────────────────────────────────────────

export interface SecurityKpis {
  incidents: { open: number; critical: number; high: number; today: number; this_week: number };
  guards:    { total: number; on_duty: number };
  access:    { today_in: number; today_out: number; flagged: number };
}
export interface SecurityMapData {
  incidents: Array<{ id: number; name: string; lat: number; lng: number; severity: string }>;
  guards:    Array<{ id: number; name: string; lat: number; lng: number; status: string }>;
  locations: Array<{ id: number; name: string; state: string; lat: number; lng: number; open_incidents: number }>;
}
export interface SecurityIncident {
  id: number; name: string; severity: string; stage: string;
  location: string; create_date: string;
}
export const fetchSecurityKpis    = async () => (await apiGet<SecurityKpis>("/api/v1/security/kpis")).data;
export const fetchSecurityMap     = async () => (await apiGet<SecurityMapData>("/api/v1/security/map-data")).data;
export const fetchSecurityRecent  = async () => (await apiGet<SecurityIncident[]>("/api/v1/security/recent")).data;
export const fetchSecurityTrend   = async () => (await apiGet<Array<{ date: string; count: number }>>("/api/v1/security/trend")).data;

// ── Barcode station ──────────────────────────────────────────────────────

export interface BarcodeKpis {
  total_assets: number; active_tags: number; pending_replacement: number;
  scrapped_tags: number; untagged: number;
}
export interface BarcodeTag {
  tag_id: number; tag_number: string; tag_state: string;
  asset_id: number; asset_name: string; domain: string; location: string; condition: string;
}

// The `domain` values `recent-tags` and `lookup` return are raw selection keys.
//
// `ASSET_DOMAINS`, `DOMAIN_LABELS` and `domainLabel` used to be declared here.
// `ASSET_DOMAINS` was a hand-written copy of the Selection on
// `nrs.asset.category.domain` — and 630 lines further down this same file,
// `FM_DOMAINS` was a second, byte-identical copy of it, each carrying its own
// comment claiming to mirror the model. Two copies of one server-owned set, in
// one file, is not redundancy that pays for itself: it is two places to forget
// when the model gains a ninth domain, and neither would have said a word.
//
// Both are gone. The set is read from `GET /api/v1/meta/enums` via
// `useEnum("domain")`, seeded by `ENUM_SEED.domain` in `lib/enums.ts`, which a
// pytest guard fails the build over when it disagrees with the model. Labels
// come from `useEnumLabel("domain")` at the display site; a non-component
// caller can use `enumLabel(ENUM_SEED.domain, key)` directly. There are none
// today, which is why no non-hook `domainLabel` wrapper survives here — a
// second label path that reads the seed instead of the live set would be the
// beginning of the same drift.

/**
 * A miss on `/api/v1/barcode/lookup` is a 404 `not_found`, NOT a 200 with
 * `{found: false}`: the route hands the station controller's
 * `{found: False, error: ...}` to `_delegate_failure` (`v1.py`), which turns
 * it into an error envelope, and `parseEnvelope` in `lib/api.ts` throws that
 * as a `CadraApiError`. So `lookupBarcode` either resolves with a hit or
 * rejects — a caller reads the miss off the error (`code === "not_found"`),
 * and an ambiguous serial carries `details.ambiguous`, `details.matches` and
 * `details.matched_by` on the same error (handoff 38).
 *
 * `matched_by` says which field the query hit — tag number, asset code or
 * serial number, tried in that order, each an exact match — so a screen can
 * say "found by serial number" instead of letting a lookup silently change
 * meaning. `tagged` is whether the asset has an ACTIVE tag; when it does not,
 * `tag_id` is null and the tag strings are empty UNLESS the asset has a
 * pending replacement, in which case the tag block describes that pending
 * tag (`tag_state: "pending"`).
 */
export type BarcodeMatchedBy = "tag_number" | "asset_code" | "serial_number";
export interface BarcodeLookupHit extends Omit<BarcodeTag, "tag_id"> {
  found: true;
  tag_id: number | null;
  matched_by: BarcodeMatchedBy;
  serial_number: string;
  tagged: boolean;
  asset_code: string;
  category: string;
  custodian: string;
  state: string;
  tag_date: string;
  last_service_date: string;
  next_service_date: string;
  sap_asset_number: string;
  import_source: string;
}
/**
 * The `{found: false}` arm does not come back through `/api/v1/barcode/lookup`
 * (see above) — it is kept in the union only because
 * `pages/AssetRegisterDashboard.tsx` narrows on it, and that file is outside
 * this change. Nothing should branch on it; branch on the thrown error.
 */
export type BarcodeLookupResult = BarcodeLookupHit | { found: false; error?: string };

/**
 * An asset with no barcode yet. Note that it still has an `asset_code` — that
 * is an ir.sequence value assigned when the asset is created, independent of
 * whether anyone has ever physically labelled it. The barcode is the separate
 * location-derived code that lives on the tag record.
 */
export interface UntaggedAsset {
  asset_id: number; asset_name: string; asset_code: string;
  category: string; domain: string; location: string; condition: string;
}

export interface GeneratedTag {
  asset_id: number; asset_name: string; asset_code: string;
  tag_id: number; tag_number: string; location: string;
}
export interface GenerateTagsResult {
  generated: GeneratedTag[];
  skipped: Array<{ asset_id: number; reason: string; tag_number?: string }>;
}

export const fetchUntaggedAssets = async (params?: { q?: string; limit?: number }) =>
  (await apiGet<UntaggedAsset[]>("/api/v1/barcode/untagged", params)).data;

/** Mint barcodes for assets that have none. Already-tagged assets come back
 *  under `skipped`, so a retry after a dropped response is harmless. */
export const generateBarcodes = async (assetIds: number[]) =>
  (await apiPost<GenerateTagsResult>("/api/v1/barcode/generate", { asset_ids: assetIds },
    { idempotencyKey: newIdempotencyKey() })).data;

export const fetchBarcodeKpis       = async () => (await apiGet<BarcodeKpis>("/api/v1/barcode/kpis")).data;
export const fetchBarcodeRecentTags = async (params?: { domain_filter?: string; limit?: number }) =>
  (await apiGet<BarcodeTag[]>("/api/v1/barcode/recent-tags", params)).data;
export const lookupBarcode = async (query: string) =>
  (await apiGet<BarcodeLookupResult>(`/api/v1/barcode/lookup`, { query })).data;

// ── Tag replacement (handoff 38) ─────────────────────────────────────────
//
// A faded or damaged label is REPRINTED UNDER THE SAME NUMBER (handoff 61,
// ruling R3 — "the number on the asset doesn't change because a sticker
// faded"). One label record is one physical print: the approval voids the
// print (`scrapped`, `voided_at`, `void_reason`) and creates the reprint, a
// new record with the same `tag_number` and `reprint_count` one higher;
// `replaces` / `replaced_by` keep the chain. Until handoff 61 a new number
// was minted, which is why a replacement made before then names a different
// number in `replaced_by`. It is the two-person pattern of
// handoff 35 on the tag model's own state machine — somebody asks and names
// an approver, and somebody ELSE decides — rather than a reuse of
// `nrs.asset.change.request`, whose one-pending-per-asset index would let a
// pending label block a move.

export type TagState = "active" | "pending" | "scrapped";

/** `serialize_tag` in `myservice_api/controllers/v1_tags.py`. `*_at` are ISO
 *  datetimes; `tag_date` / `scrapped_date` are dates. */
export interface TagLabel {
  id: number;
  tag_number: string;
  state: TagState;
  label_state: string;
  source: string;
  tag_date: string | null;
  scrapped_date: string | null;
  asset: { id: number; name: string };
  asset_code: string;
  serial_number: string;
  replacement_reason: string | null;
  replacement_notes: string | null;
  requested_by: ApprovalRef | null;
  requested_at: string | null;
  /** WHO WAS ASKED. Not who clicked — that is `approved_by` / `rejected_by`. */
  approver: ApprovalRef | null;
  approved_by: ApprovalRef | null;
  approved_at: string | null;
  rejected_by: ApprovalRef | null;
  rejected_at: string | null;
  decision_reason: string | null;
  /** Which print of `tag_number` this record is: 0 for the first print,
   *  one more for each approved replacement (handoff 61). */
  reprint_count: number;
  /** On a voided print: when it was voided, and why (a
   *  `tag_replacement_reason` key). Null on a print in service. */
  voided_at: string | null;
  void_reason: string | null;
  replaces: TagPrintLink | null;
  replaced_by: TagPrintLink | null;
  /** Pending AND the caller may decide it (`_may_decide`, which refuses the
   *  requester). The server's answer, so a screen does not have to guess. */
  can_decide: boolean;
}

/** One end of the chain between two prints. Since handoff 61 both ends
 *  usually carry the same `tag_number` and differ only in `reprint_count`. */
export interface TagPrintLink { id: number; tag_number: string; reprint_count: number }

/** "the original print" / "reprint 2" — `reprint_count` in words, the same
 *  words the server's refusals use. */
export function printName(count: number | null | undefined): string {
  return count ? `reprint ${count}` : "the original print";
}

export const fetchTag = async (id: number): Promise<TagLabel> =>
  (await apiGet<TagLabel>(`/api/v1/tags/${id}`)).data;

export interface PendingTagReplacements {
  tags: TagLabel[];
  /** The server's count of EVERYTHING pending, not of this page. */
  totalEstimate: number | null;
  /** Non-null means the page below is not the whole queue. */
  nextCursor: string | null;
}

/** The 100 most recent tags in `pending`, WITH the server's own total —
 *  handoff 52 §2. This used to return `.data` alone, which threw the
 *  pagination block away: the station rendered one page as if it were the
 *  queue, and on a tenant with more than 100 pending (test19 held 214) the
 *  panel ended without saying whether it was the end. The panel now reads
 *  `totalEstimate`/`nextCursor` and says what it is showing. */
export const fetchPendingTagReplacements = async (): Promise<PendingTagReplacements> => {
  const res = await apiGet<TagLabel[]>("/api/v1/tags/pending-replacements", { limit: 100 });
  return {
    tags: res.data,
    totalEstimate: res.pagination?.total_estimate ?? null,
    nextCursor: res.pagination?.next_cursor ?? null,
  };
};

/**
 * Filters for `GET /api/v1/tags/replacements` — the SIBLING of
 * `pending-replacements`, not a widening of it (handoff 51 §1a). The base
 * domain is every label that has ever had a replacement requested, and
 * `state` is the LABEL's own lifecycle: `pending` is still waiting,
 * `scrapped` is a request approved (the number is dead and a successor was
 * minted), `active` is a label back in service — rejected, usually. The
 * route exists because `pending-replacements` can only ever answer "what is
 * pending", and the requester's question is "what happened to mine".
 */
export interface TagReplacementFilters {
  state?: TagState;
  /** Only labels NAMING the caller as the approver. A convenience, not a
   *  boundary — anyone eligible may decide any pending replacement. */
  waiting_on_me?: boolean;
  /** Labels the caller asked to replace, decided ones included. */
  raised_by_me?: boolean;
}

export interface TagReplacementsPage {
  tags: TagLabel[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

/**
 * One page of the replacement record, newest first. The same envelope and
 * the same boolean rule as `fetchApprovalsPage`: `waiting_on_me` and
 * `raised_by_me` are sent ONLY when true, because the server filters on
 * `is True` and an explicit `false` on every request is noise in the access
 * log for no gain. Rows are full `TagLabel`s with `can_decide` computed for
 * the calling token, so the queue screen reads the answer off the record
 * rather than re-implementing the refusal.
 */
export async function fetchTagReplacementsPage(
  cursor: string | undefined,
  f?: TagReplacementFilters,
): Promise<TagReplacementsPage> {
  if (!apiConfigured) return { tags: [], nextCursor: null, totalEstimate: 0 };
  const res = await apiGet<TagLabel[]>("/api/v1/tags/replacements", {
    state: f?.state,
    waiting_on_me: f?.waiting_on_me ? true : undefined,
    raised_by_me: f?.raised_by_me ? true : undefined,
    limit: 100,
    cursor,
  });
  return {
    tags: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

export interface TagReplacementRequest {
  /** One of `useEnum("tag_replacement_reason")`; anything else is a 400. */
  reason: string;
  notes?: string;
  /** `res.users` id of the person asked. Required; the server refuses the
   *  caller's own id. */
  approver_id: number;
}

export interface TagReplacementRaised {
  pending_approval: true;
  tag: TagLabel;
  asset: ApiAsset;
}

/** Ask for a replacement. Nothing happens to the label until the approver
 *  acts — the tag goes to `pending` and, by design, its NUMBER stops
 *  resolving on the lookup until the decision; the asset code still does.
 *  Only the three keys below: the route refuses any other with a 400. */
export const requestTagReplacement = async (tagId: number, body: TagReplacementRequest) => {
  const payload: TagReplacementRequest = { reason: body.reason, approver_id: body.approver_id };
  if (body.notes?.trim()) payload.notes = body.notes.trim();
  return (await apiPost<TagReplacementRaised>(
    `/api/v1/tags/${tagId}/request-replacement`, payload,
    { idempotencyKey: newIdempotencyKey() })).data;
};

export interface TagReplacementApproved {
  /** The voided print, now `scrapped`, with `voided_at` / `void_reason`. */
  tag: TagLabel;
  /** The REPRINT: the same `tag_number`, `reprint_count` one higher,
   *  `replaces` naming the voided print. Not printed yet — the affix route
   *  refuses it until a print of it is recorded (handoff 61). */
  new_tag: TagLabel;
  asset: ApiAsset;
}

export const approveTagReplacement = async (tagId: number, reason?: string) =>
  (await apiPost<TagReplacementApproved>(
    `/api/v1/tags/${tagId}/approve-replacement`,
    reason?.trim() ? { reason: reason.trim() } : {},
    { idempotencyKey: newIdempotencyKey() })).data;

export interface TagsPrintRecorded {
  recorded: TagLabel[];
  not_recorded: Array<{ id: number; tag_number: string; reason: string }>;
}

/** Record that the station printed these labels (`POST /api/v1/tags/printed`,
 *  `tagging:write`, handoff 61). The app renders labels in the browser and
 *  so never reaches the PDF funnel that records Odoo's own prints; without
 *  this a reprint printed from the app could never be confirmed on the
 *  asset. Label ids, not asset ids. */
export const recordTagsPrinted = async (tagIds: number[]) =>
  (await apiPost<TagsPrintRecorded>("/api/v1/tags/printed", { tag_ids: tagIds },
    { idempotencyKey: newIdempotencyKey() })).data;

/** `reason` is REQUIRED by the route (400 on a blank one): the tag goes
 *  back to `active` and the person who asked is told why. */
export const rejectTagReplacement = async (tagId: number, reason: string) =>
  (await apiPost<{ tag: TagLabel; asset: ApiAsset }>(
    `/api/v1/tags/${tagId}/reject-replacement`, { reason: reason.trim() },
    { idempotencyKey: newIdempotencyKey() })).data;

// ── Confirm a label affixed (handoff 39) ─────────────────────────────────
//
// `POST /api/v1/assets/<id>/tag-affixed` has existed since handoff 03 and is
// the only thing that makes an asset `is_tagged`: the number READ OFF the
// physical label is checked against the tag Cadra issued, and a mismatch is
// refused with a sentence naming both. Until this handoff nothing in the app
// called it. The control's whole value is that the number comes off the
// label in the person's hand, so NOTHING here hands the caller the expected
// number — not a default, not a suggestion.

/** `_serialize_tagging` in `myservice_api/controllers/v1_assets.py` — the
 *  `tagging` block on every asset payload. It reads the label PHYSICALLY on
 *  the asset (`physical_tag_id`), which is the active tag whenever there is
 *  one; `label_id` is the `nrs.asset.tag.label` id and is what to compare
 *  with the scan box's `tag_id`. `label_state` is `issued` → `printed` →
 *  `affixed`, or `scrapped`. `*_at` are ISO datetimes with no zone, in UTC. */
export interface AssetTagging {
  label_id: number | null;
  tag_number: string | null;
  label_state: string | null;
  is_tagged: boolean;
  printed_at: string | null;
  printed_by: ApprovalRef | null;
  affixed_at: string | null;
  affixed_by: ApprovalRef | null;
  affixed_by_name: string | null;
}

/** The `tagging` block alone, read fresh. The lookup payload carries the
 *  tag's `state` (active / pending / scrapped) but not its `label_state`,
 *  so the station reads this to know whether a label is still waiting to be
 *  confirmed and, once it is, who fitted it and when. */
export const fetchAssetTagging = async (assetId: number): Promise<AssetTagging> =>
  (await apiGet<{ tagging: AssetTagging }>(`/api/v1/assets/${assetId}`)).data.tagging;

export interface ConfirmAffixedBody {
  /** The number READ OFF the label on the asset. Never pre-filled. */
  tag_number: string;
  /** The manufacturer serial read off the asset, if legible. Checked against
   *  the record when sent; refused when the record has no serial to check. */
  serial_number?: string;
  /** Who fitted it — often not the signed-in user. */
  affixed_by_name?: string;
  /** Which symbology `tag_number` was read off, when the camera read it
   *  (handoff 54). Omitted for typed and keyboard-wedge entry: the client
   *  only claims a format it observed. Recorded beside a refused affix so
   *  an auditor can tell Cadra's label from a manufacturer's. */
  scanned_format?: string;
  /** Same, for `serial_number`. */
  serial_format?: string;
  /** Handoff 58: for a `tag_id` unit there is no manufacturer serial to
   *  check, so the tagger ticks that the item matches its description, make
   *  and colour. Required by the server for a `tag_id` unit (400 without it);
   *  sent only when ticked. */
  attributes_confirmed?: boolean;
}

export interface ConfirmAffixedResult {
  asset: ApiAsset;
  tagging: AssetTagging;
}

/** Record that the label is on the asset. Only the keys the route reads are
 *  sent, blanks omitted: since handoff 31 a key a route does not accept is a
 *  400 and nothing is written. A REPEAT confirmation is not an error — the
 *  server logs it, keeps the original record and answers normally with the
 *  original `affixed_at` — so a caller that needs to tell the two apart reads
 *  the block before it posts (`fetchAssetTagging`) rather than a clock. */
export const confirmTagAffixed = async (assetId: number, body: ConfirmAffixedBody) => {
  const payload: ConfirmAffixedBody = { tag_number: body.tag_number.trim() };
  if (body.serial_number?.trim()) payload.serial_number = body.serial_number.trim();
  if (body.affixed_by_name?.trim()) payload.affixed_by_name = body.affixed_by_name.trim();
  if (body.scanned_format) payload.scanned_format = body.scanned_format;
  if (body.serial_format && payload.serial_number) payload.serial_format = body.serial_format;
  if (body.attributes_confirmed) payload.attributes_confirmed = true;
  return (await apiPost<ConfirmAffixedResult>(
    `/api/v1/assets/${assetId}/tag-affixed`, payload,
    { idempotencyKey: newIdempotencyKey() })).data;
};

export async function fetchLocation(id: string): Promise<Location | null> {
  if (!apiConfigured) return getLocation(id) ?? null;
  try {
    const res = await apiGet<ApiLocation>(`/api/v1/locations/${id}`);
    return apiLocationToLocation(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

// Employee custodial assets — /api/v1/identity/employees/<id>/assets
export async function fetchEmployeeAssetsApi(employeeId: string): Promise<Asset[]> {
  if (!apiConfigured) {
    const emp = mockEmployees.find(e => e.id === employeeId);
    return emp ? getEmployeeAssets(emp.irNumber) : [];
  }
  const all: ApiAsset[] = [];
  let cursor: string | undefined;
  do {
    const res = await apiGet<ApiAsset[]>(
      `/api/v1/identity/employees/${employeeId}/assets`,
      { limit: 200, cursor },
    );
    all.push(...res.data);
    cursor = res.pagination?.next_cursor ?? undefined;
  } while (cursor);
  return all.map(apiAssetToAsset);
}

// Totals only — single page with limit=1 returns total_estimate cheaply.
export async function fetchTotals(): Promise<{ assets: number | null; locations: number | null; employees: number | null }> {
  if (!apiConfigured) {
    return { assets: allMockAssets.length, locations: mockLocations.length, employees: mockEmployees.length };
  }
  const [a, l, e] = await Promise.all([
    apiGet<ApiAsset[]>("/api/v1/assets", { limit: 1 }),
    apiGet<ApiLocation[]>("/api/v1/locations", { limit: 1 }),
    apiGet<ApiEmployee[]>("/api/v1/identity/employees", { limit: 1 }),
  ]);
  return {
    assets: a.pagination?.total_estimate ?? null,
    locations: l.pagination?.total_estimate ?? null,
    employees: e.pagination?.total_estimate ?? null,
  };
}

// ─── EMPLOYEES ────────────────────────────────────────────────────────────────
export interface EmployeeFilters {
  department?: string;
  zone?: string;
  status?: string;
  search?: string;
}

// Sync mock-only — kept for callers that haven't moved to react-query yet.
export function listEmployees(f?: EmployeeFilters): Employee[] {
  let r = mockEmployees;
  if (f?.department) r = r.filter((e) => e.department === f.department);
  if (f?.zone) r = r.filter((e) => e.zone === f.zone);
  if (f?.status) r = r.filter((e) => e.status === f.status);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.irNumber.toLowerCase().includes(q) ||
        e.department.toLowerCase().includes(q) ||
        e.title.toLowerCase().includes(q),
    );
  }
  return r;
}

// API-backed list. Falls back to mocks when no token is configured so the
// app stays usable for design/dev without staging credentials.
const STATUS_TO_SAP: Record<string, string> = {
  Active: "active",
  "On Leave": "on_leave",
  Suspended: "suspended",
  Inactive: "exited",
};

// API caps `limit` at MAX_PAGE_LIMIT=200.
export const API_PAGE_LIMIT = 200;

export interface EmployeesPage {
  employees: Employee[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

// Server-side filters only — q (search) and sap_status. Department/zone are
// display names; the API filters by FK ids which the frontend doesn't yet
// know, so those stay client-side (filter loaded rows).
export interface EmployeeServerFilters {
  search?: string;
  status?: string;
}

export async function fetchEmployeesPage(
  cursor: string | undefined,
  f?: EmployeeServerFilters,
): Promise<EmployeesPage> {
  if (!apiConfigured) {
    const all = listEmployees({ search: f?.search, status: f?.status });
    return { employees: all, nextCursor: null, totalEstimate: all.length };
  }
  const res = await apiGet<ApiEmployee[]>("/api/v1/identity/employees", {
    q: f?.search,
    sap_status: f?.status ? STATUS_TO_SAP[f.status] : undefined,
    limit: API_PAGE_LIMIT,
    cursor,
  });
  return {
    employees: res.data.map(apiEmployeeToEmployee),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

export function getEmployee(id: string): Employee | undefined {
  return mockEmployees.find((e) => e.id === id);
}

export async function fetchEmployee(id: string): Promise<Employee | null> {
  if (!apiConfigured) return getEmployee(id) ?? null;
  try {
    const res = await apiGet<ApiEmployee>(`/api/v1/identity/employees/${id}`);
    return apiEmployeeToEmployee(res.data);
  } catch (e) {
    // 404 -> not found, surface as null. Other errors propagate.
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}
export function getEmployeeAssets(irNumber: string): Asset[] {
  return allMockAssets.filter((a) => a.custodianIR === irNumber);
}

// ─── IDENTITY ─────────────────────────────────────────────────────────────────
export interface IdentityFilters {
  clearanceLevel?: string;
  zone?: string;
  search?: string;
}
export function listIdentityRecords(f?: IdentityFilters): IdentityRecord[] {
  let r = mockIdentityRecords;
  if (f?.clearanceLevel)
    r = r.filter((i) => i.clearanceLevel === f.clearanceLevel);
  if (f?.zone) r = r.filter((i) => i.zone === f.zone);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(
      (i) =>
        i.employeeName.toLowerCase().includes(q) ||
        i.irNumber.toLowerCase().includes(q) ||
        i.department.toLowerCase().includes(q),
    );
  }
  return r;
}

// ─── FLEET ────────────────────────────────────────────────────────────────────
export interface FleetFilters {
  vehicleType?: string;
  status?: string;
  zone?: string;
  isStaffBus?: boolean;
  search?: string;
}
export function listFleetVehicles(f?: FleetFilters): FleetVehicle[] {
  let r = mockFleetVehicles;
  if (f?.vehicleType) r = r.filter((v) => v.vehicleType === f.vehicleType);
  if (f?.status) r = r.filter((v) => v.status === f.status);
  if (f?.zone) r = r.filter((v) => v.zone === f.zone);
  if (f?.isStaffBus !== undefined)
    r = r.filter((v) => v.isStaffBus === f.isStaffBus);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(
      (v) =>
        v.make.toLowerCase().includes(q) ||
        v.model.toLowerCase().includes(q) ||
        v.regNo.toLowerCase().includes(q) ||
        (v.assignedDriverName ?? "").toLowerCase().includes(q),
    );
  }
  return r;
}
export function getFleetVehicle(id: string): FleetVehicle | undefined {
  return mockFleetVehicles.find((v) => v.id === id);
}
export function getFleetVehicleByAssetId(
  assetId: string,
): FleetVehicle | undefined {
  return mockFleetVehicles.find((v) => v.assetId === assetId);
}
export function getFleetStats() {
  const v = mockFleetVehicles;
  return {
    total: v.length,
    active: v.filter((x) => x.status === "Active").length,
    inMaintenance: v.filter((x) => x.status === "In Maintenance").length,
    grounded: v.filter((x) => x.status === "Grounded").length,
    buses: v.filter((x) => x.isStaffBus).length,
  };
}

// ── API-backed fleet (falls back to the mock helpers above when no session) ──
// The backend (fleet.vehicle) has fewer fields than the FleetVehicle view type,
// so NRS-specific fields it doesn't track (engine no, insurance/road-worthiness
// expiry, zone, fuel card) are mapped to empty defaults; vehicleType/status are
// derived best-effort from the model name and lifecycle state.
//
// `fuel_type` is NOT in that list and must never rejoin it. It is a real field
// on fleet.vehicle with nine values, and the derivation that used to stand here
// reported six of them as something else.
interface ApiFleetVehicle {
  id: number;
  name: string;
  license_plate: string;
  vin_sn: string;
  model: string;
  brand: string;
  model_year: string;
  color: string;
  fuel_type: string;
  odometer: number;
  seats: number;
  state: string;
  driver: { id: number; name: string } | null;
  home_location: { id: number; name: string } | null;
  is_staff_bus: boolean;
  maintenance_status: string;
  last_service_date: string;
  next_service_date: string;
  next_service_odometer: number;
}

function deriveVehicleType(a: ApiFleetVehicle): VehicleType {
  if (a.is_staff_bus) return "Bus";
  const s = `${a.brand} ${a.model} ${a.name}`.toLowerCase();
  if (/hiace|coaster|bus|sprinter/.test(s)) return "Bus";
  if (/hilux|pickup|pick-up|navara|ranger|amarok|d-max/.test(s)) return "Pickup";
  if (/truck|canter|tipper|lorry|dyna|actros/.test(s)) return "Truck";
  if (/land ?cruiser|prado|patrol|pajero|fortuner|rav4|4runner|highlander|suv/.test(s)) return "SUV";
  if (/van|transit|caravan/.test(s)) return "Van";
  if (/camry|corolla|accord|civic|passat|sonata|sedan|elantra/.test(s)) return "Sedan";
  return "Van";
}

function mapVehicleStatus(a: ApiFleetVehicle): VehicleStatus {
  const s = `${a.state} ${a.maintenance_status}`.toLowerCase();
  if (/decommiss|dispos|retire|inactive|sold/.test(s)) return "Decommissioned";
  if (/ground|down|off ?road|impound/.test(s)) return "Grounded";
  if (/mainten|repair|service|workshop|overdue|due/.test(s)) return "In Maintenance";
  return "Active";
}

// `mapFuelType` used to live here. It took the nine values of
// `fleet.vehicle.fuel_type` and squeezed them onto three invented display
// strings with a regex: anything matching /cng|lpg|gas$|electric|hybrid/ became
// "CNG", so `electric`, `lpg`, `full_hybrid` and both plug-in hybrids were all
// shown as CNG, and anything left over — `hydrogen` — became "Petrol". Nothing
// in the UI hinted that a grouping had happened. That is not a lossy display
// choice, it is the screen stating a fact about the vehicle that is false.
//
// There is no replacement mapper, because there was nothing to map: the key
// now travels through untouched and the pages render the MODEL's label for it
// via `useEnumLabel("fuel_type")`. `deriveVehicleType` and `mapVehicleStatus`
// above stay, because those two really are derived — the API has no field for
// either — whereas fuel type was sitting right there in the payload.

function apiFleetToVehicle(a: ApiFleetVehicle): FleetVehicle {
  return {
    id: String(a.id),
    assetId: "",
    assetTag: a.license_plate || String(a.id),
    make: a.brand || "",
    model: a.model || "",
    year: parseInt(a.model_year, 10) || 0,
    vehicleType: deriveVehicleType(a),
    regNo: a.license_plate || "",
    vin: a.vin_sn || "",
    engineNo: "",
    color: a.color || "",
    // The model's key, verbatim. Labelling happens at the display site.
    fuelType: a.fuel_type || "",
    tankCapacity: 0,
    currentOdometer: a.odometer || 0,
    status: mapVehicleStatus(a),
    assignedDriverId: a.driver ? String(a.driver.id) : undefined,
    assignedDriverName: a.driver?.name,
    zone: "",
    office: a.home_location?.name || "",
    lastServiceDate: a.last_service_date || "",
    nextServiceKm: a.next_service_odometer || 0,
    isStaffBus: a.is_staff_bus,
    seatingCapacity: a.seats || undefined,
    insuranceExpiry: "",
    roadWorthinessExpiry: "",
    department: "",
  };
}

export async function listFleetVehiclesApi(f?: FleetFilters): Promise<FleetVehicle[]> {
  if (!apiConfigured) return listFleetVehicles(f);
  const res = await apiGet<ApiFleetVehicle[]>("/api/v1/fleet", {
    q: f?.search || undefined,
    is_staff_bus: f?.isStaffBus,
    limit: 300,
  });
  let r = res.data.map(apiFleetToVehicle);
  // vehicleType / status / zone are derived client-side, so filter here.
  if (f?.vehicleType) r = r.filter((v) => v.vehicleType === f.vehicleType);
  if (f?.status) r = r.filter((v) => v.status === f.status);
  if (f?.zone) r = r.filter((v) => v.zone === f.zone);
  return r;
}

export async function getFleetVehicleApi(id: string): Promise<FleetVehicle | null> {
  if (!apiConfigured) return getFleetVehicle(id) ?? null;
  const res = await apiGet<ApiFleetVehicle>(`/api/v1/fleet/${encodeURIComponent(id)}`);
  return res.data ? apiFleetToVehicle(res.data) : null;
}

export async function getFleetStatsApi(): Promise<{
  total: number; active: number; inMaintenance: number; grounded: number; buses: number;
}> {
  if (!apiConfigured) return getFleetStats();
  const all = await listFleetVehiclesApi({});
  return {
    total: all.length,
    active: all.filter((x) => x.status === "Active").length,
    inMaintenance: all.filter((x) => x.status === "In Maintenance").length,
    grounded: all.filter((x) => x.status === "Grounded").length,
    buses: all.filter((x) => x.isStaffBus).length,
  };
}

// ─── FUEL ─────────────────────────────────────────────────────────────────────
export function listFuelCards(): FuelCard[] {
  return mockFuelCards;
}
export function getFuelCard(id: string): FuelCard | undefined {
  return mockFuelCards.find((f) => f.id === id);
}
export function listFuelTransactions(vehicleId?: string): FuelTransaction[] {
  return vehicleId
    ? mockFuelTransactions.filter((t) => t.vehicleId === vehicleId)
    : mockFuelTransactions;
}
export function getFuelStats() {
  const t = mockFuelTransactions;
  return {
    totalSpend: t.reduce((s, x) => s + x.totalCost, 0),
    totalLitres: t.reduce((s, x) => s + x.litres, 0),
    flaggedCount: t.filter((x) => x.status === "Flagged").length,
    pendingCount: t.filter((x) => x.status === "Pending Verification").length,
  };
}

// ─── STAFF BUS ────────────────────────────────────────────────────────────────
export function listBusRoutes(): BusRoute[] {
  return mockBusRoutes;
}
export function getBusRoute(id: string): BusRoute | undefined {
  return mockBusRoutes.find((r) => r.id === id);
}
export function listBusSchedules(f?: {
  date?: string;
  status?: string;
}): BusSchedule[] {
  let r = mockBusSchedules;
  if (f?.date) r = r.filter((s) => s.departureDate === f.date);
  if (f?.status) r = r.filter((s) => s.status === f.status);
  return r;
}
export function getBusSchedule(id: string): BusSchedule | undefined {
  return mockBusSchedules.find((s) => s.id === id);
}
export function listBookings(scheduleId?: string): BusBooking[] {
  return scheduleId
    ? mockBusBookings.filter((b) => b.scheduleId === scheduleId)
    : mockBusBookings;
}
export function getBusStats() {
  const today = mockBusSchedules.filter(
    (s) => s.departureDate === "2026-06-10",
  );
  return {
    todayTrips: today.length,
    activeTrips: today.filter((s) =>
      ["In Transit", "Boarding", "Departed"].includes(s.status),
    ).length,
    arrivedTrips: today.filter((s) => s.status === "Arrived").length,
    passengersToday: today.reduce((s, t) => s + t.bookedSeats, 0),
  };
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
export function getDashboardStats(): DashboardStats {
  return {
    totalAssets: 13150,
    itEquipment: 10259,
    fleetVehicles: 1619,
    furniture: 1272,
    locations: 1163,
    employees: 11385,
    reviewQueue: 847,
  };
}

// ─── SERVICE REQUESTS ────────────────────────────────────────────────────────

export interface RequestFilters {
  search?: string;
  stage_id?: number;
  type_id?: number;
  category_id?: number;
  user_id?: number;
  priority?: string;
  closed?: boolean;
  // A real filter since handoff 31 and not before. Until then the list route
  // looked for a model field called `location_id`, found none on Odoo 19 and
  // IGNORED the parameter — `?location_id=7` answered 200 with every request
  // (read against `test19`: 189 of 189). It now filters, and refuses a value
  // it cannot read. No page sends it yet.
  location_id?: number;
  asset_id?: number;
}

export type RequestInclude = "routes" | "messages" | "events";

export interface RequestsPage {
  requests: ServiceRequest[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchRequestsPage(
  cursor: string | undefined,
  f?: RequestFilters,
): Promise<RequestsPage> {
  if (!apiConfigured) return { requests: [], nextCursor: null, totalEstimate: 0 };
  const res = await apiGet<ApiRequest[]>("/api/v1/requests", {
    q: f?.search,
    stage_id: f?.stage_id,
    type_id: f?.type_id,
    category_id: f?.category_id,
    user_id: f?.user_id,
    priority: f?.priority,
    closed: f?.closed,
    location_id: f?.location_id,
    asset_id: f?.asset_id,
    limit: 200,
    cursor,
  });
  return {
    requests: res.data.map(apiRequestToRequest),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

export async function fetchRequest(id: string, includes?: RequestInclude[]): Promise<ServiceRequest | null> {
  if (!apiConfigured) return null;
  try {
    // Note: ?include=events currently 500s on staging — skip it until backend fix.
    const safe = includes?.filter(i => i !== "events");
    const res = await apiGet<ApiRequest>(`/api/v1/requests/${id}`, {
      include: safe?.length ? safe.join(",") : undefined,
    });
    return apiRequestToRequest(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

export async function fetchRequestByReference(ref: string, includes?: RequestInclude[]): Promise<ServiceRequest | null> {
  if (!apiConfigured) return null;
  try {
    const safe = includes?.filter(i => i !== "events");
    const res = await apiGet<ApiRequest>(`/api/v1/requests/by-reference/${encodeURIComponent(ref)}`, {
      include: safe?.length ? safe.join(",") : undefined,
    });
    return apiRequestToRequest(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}

// ─── REQUEST MUTATIONS ───────────────────────────────────────────────────────

/**
 * A subset of `_WRITABLE_FIELDS` in v1_requests.py. That route's filter
 * refuses two kinds of key: one that is not allow-listed, and one that is
 * allow-listed but has no field behind it on the database answering — so the
 * Python list alone does not say what a deployment accepts; the 400's
 * `details.writable` does. `stage_id` is the first kind — use
 * transitionRequest().
 *
 * `location_id` was the second kind until handoff 31, and nobody knew: the
 * controller looked for a model field of that name, the Odoo 19 model calls
 * it `generic_location_id`, and the key was dropped with a 201 for the life
 * of this app. The API now translates it (see RequestForm's header for the
 * whole story), and `test19` lists it as writable.
 */
export interface RequestWriteBody {
  type_id?: number;
  category_id?: number | null;
  priority?: string;
  impact?: string;
  urgency?: string;
  kanban_state?: "normal" | "done" | "blocked";
  request_text?: string;
  response_text?: string;
  author_id?: number | null;
  user_id?: number | null;
  partner_id?: number | null;
  service_id?: number | null;
  parent_id?: number | null;
  deadline_date?: string | null;
  tag_ids?: number[];
  location_id?: number | null;
  vehicle_id?: number | null;
  nrs_asset_id?: number | null;
}

export async function createRequest(body: RequestWriteBody): Promise<ServiceRequest> {
  const res = await apiPost<ApiRequest>("/api/v1/requests", body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiRequestToRequest(res.data);
}

export async function updateRequest(id: string, body: RequestWriteBody): Promise<ServiceRequest> {
  const res = await apiPatch<ApiRequest>(`/api/v1/requests/${id}`, body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiRequestToRequest(res.data);
}

export async function assignRequest(id: string, user_id: number | null): Promise<ServiceRequest> {
  const res = await apiPost<ApiRequest>(`/api/v1/requests/${id}/assign`, { user_id }, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiRequestToRequest(res.data);
}

export async function transitionRequest(
  id: string,
  by: { route_id: number } | { to_stage_id: number },
): Promise<ServiceRequest> {
  const res = await apiPost<ApiRequest>(`/api/v1/requests/${id}/transition`, by, {
    idempotencyKey: newIdempotencyKey(),
  });
  return apiRequestToRequest(res.data);
}

export async function commentOnRequest(id: string, body: string, internal = true): Promise<void> {
  await apiPost(`/api/v1/requests/${id}/comment`, { body, internal }, {
    idempotencyKey: newIdempotencyKey(),
  });
}

// ── Settings: depreciation (PRD §8.6) ─────────────────────────────────────

export interface CategoryPolicy {
  method: "none" | "straight_line" | "declining_balance" | "erp_managed";
  useful_life_months: number | null;
  declining_rate: number | null;
  salvage_rate: number | null;
}

// `FM_DOMAINS` stood here: a second copy of the FM domain set, identical byte
// for byte to `ASSET_DOMAINS` 630 lines above it, and claiming in its own
// comment to mirror the Selection on `nrs.asset.category`. It did, at the time
// somebody typed it. Both copies are now deleted in favour of the one live
// set — see the note where `ASSET_DOMAINS` used to be. The settings screen
// that filled its dropdown from this constant reads `useEnum("domain")`.

export interface AssetCategoryConfig {
  id: number;
  name: string;
  code: string | null;
  domain: string | null;
  description: string | null;
  sequence: number;
  asset_count: number;
  depreciating_count: number;
  pm_interval_days: number | null;
  depreciation: CategoryPolicy;
  /** Section 12 (handoff 58): how a unit of this class is told apart from
   *  its neighbours — by the manufacturer serial, by Cadra's tag and the
   *  item's attributes, or (not built) as a pool. Optional only because an
   *  older server does not publish it; the screen reads absent as `serial`,
   *  the model's default. */
  identification_mode?: IdentificationMode;
  /** The EFFECTIVE capture schema — the stored one, or the mode's default.
   *  What is read can be PATCHed back unchanged. */
  class_attributes_schema?: ClassAttributesSchema;
  /** SAP's four-digit asset class code (handoff 59 §1), or null when nobody
   *  has set it — and then SAP would reject the asset's master, so the
   *  register gates refuse to submit or approve it. Optional because an
   *  older server does not publish it. */
  sap_asset_class?: string | null;
  /** Only present on the response to a PATCH. */
  assets_recomputed?: number;
}

/** `nrs.asset.category.identification_mode` (handoff 58 §4). */
export type IdentificationMode = "serial" | "tag_id" | "record_only" | "pool";

/** The four modes, in the server's words. `record_only` since handoff 59 §2:
 *  a capitalised asset nobody can fix a label to. */
export const IDENTIFICATION_MODE_WORDS: Record<IdentificationMode, string> = {
  serial: "Serial (manufacturer serial number)",
  tag_id: "Tag ID (attributes, no serial)",
  record_only: "Identified by its SAP record — no physical label (land, buildings, software, works in progress)",
  pool: "Pool (not built yet — refused at receipt)",
};

/** The short form, for a table cell (the Candidates page's Mode column). */
export const IDENTIFICATION_MODE_SHORT: Record<IdentificationMode, string> = {
  serial: "Serial",
  tag_id: "Tag ID",
  record_only: "SAP record",
  pool: "Pool",
};

/** The closed set of `POST /assets` fields a class may make mandatory, in
 *  the order the screen lists them, with the screen's words for each. A name
 *  outside this set is refused by the server; the editor offers only these. */
export const CAPTURABLE_ATTRIBUTES = [
  { field: "name",         label: "Description" },
  { field: "make",         label: "Make or brand" },
  { field: "model_name",   label: "Model or catalogue reference" },
  { field: "manufacturer", label: "Manufacturer" },
  { field: "colour",       label: "Colour" },
  { field: "material",     label: "Material" },
  { field: "dimensions",   label: "Dimensions" },
  // Handoff 59: a `record_only` class's identity — title or plot number,
  // licence key, contract. Its default schema is description + this.
  { field: "record_reference", label: "Reference (title, plot, licence or contract)" },
] as const;
export type CapturableAttribute = typeof CAPTURABLE_ATTRIBUTES[number]["field"];

export interface ClassAttributesSchema {
  mandatory: CapturableAttribute[];
}

export interface DepreciationSettings {
  mode: "computed" | "erp_managed";
  proration: "whole_month" | "daily";
  declining_switches_to_straight_line: boolean;
  last_recompute: string | null;
  data_quality: {
    needs_start_date: number;
    missing_cost: number;
    not_configured: number;
  };
}

export const fetchAssetCategories = async () =>
  (await apiGet<AssetCategoryConfig[]>("/api/v1/asset-categories")).data;

/** Policy edits restate book value across the whole category, so the response
 *  carries how many assets were recomputed. */
/** Identity/classification fields, as opposed to the depreciation policy. */
export interface CategoryIdentity {
  name: string;
  code: string | null;
  domain: string | null;
  description: string | null;
  sequence: number;
  pm_interval_days: number | null;
}

/** How a class is identified (handoff 58 §4) — the two keys a
 *  `settings:classes` holder may PATCH and nothing else. */
export interface CategoryClassIdentification {
  identification_mode: IdentificationMode;
  class_attributes_schema: ClassAttributesSchema;
}

/** SAP's class code for a category (handoff 59 §1) — writable by the same
 *  two scopes as the identification mode. `null` (or "") clears it. */
export interface CategorySapClass {
  sap_asset_class: string | null;
}

/** The ten classes SAP's own asset master for NRS uses
 *  (`docs/reference/sap-asset-master-2026-10.md`). A HINT, never a closed
 *  list: NRS may hold classes the export did not happen to use, so the field
 *  takes any four digits. The names are read off SAP's descriptions and are
 *  NRS's to confirm. */
export const SAP_ASSET_CLASS_HINTS: { code: string; name: string }[] = [
  { code: "1000", name: "Motor vehicles" },
  { code: "2000", name: "Furniture & fittings" },
  { code: "3000", name: "ICT" },
  { code: "3500", name: "Software & licences" },
  { code: "4000", name: "Office equipment" },
  { code: "6000", name: "Land" },
  { code: "7000", name: "Plant & power" },
  { code: "8000", name: "Buildings & renovations" },
  { code: "9000", name: "Construction in progress" },
  { code: "9300", name: "Projects / works in progress" },
];

/** The server's rule, checked first so the screen says it before a 400 does. */
export const isSapAssetClass = (v: string) => /^\d{4}$/.test(v);

/**
 * Only the named keys, and only those that are set. For the three settings
 * writes below, whose screens build a body by EDITING AN OBJECT THEY WERE
 * GIVEN BY A GET. That is safe exactly as long as the GET publishes nothing
 * the PATCH refuses, which no one is watching: the day a read-only key joins
 * the response, the screen echoes it back and every Save on it is a 400. It
 * is how `building_id`, `floor_id` and `room_id` came to ride on every asset
 * edit (handoff 30), and how `method` did below. The body is assembled from
 * the route's own key list instead, so what is sent is decided here and not
 * by what the server happened to return.
 */
function pickSet<T extends object, K extends keyof T>(body: T, keys: readonly K[]): Partial<Pick<T, K>> {
  const out: Partial<Pick<T, K>> = {};
  for (const k of keys) if (body[k] !== undefined) out[k] = body[k];
  return out;
}

/** `_CATEGORY_IDENTITY_FIELDS` in v1_settings.py, less
 *  `verification_interval_days`, which no screen edits yet. */
const CATEGORY_IDENTITY_KEYS = [
  "name", "code", "domain", "description", "sequence", "pm_interval_days",
] as const;
/** The two Section 12 keys (handoff 58). Their own list, because they are
 *  the ONLY keys a `settings:classes`-only caller may send — any other key
 *  from that caller is a 403 — so the screen sends them alone for that
 *  person and alongside the identity keys for a `settings:write` holder. */
const CATEGORY_CLASS_KEYS = [
  "identification_mode", "class_attributes_schema", "sap_asset_class",
] as const;
/** `_CATEGORY_POLICY_FIELDS`, less the method — sent under its wire name. */
const CATEGORY_POLICY_NUMBER_KEYS = [
  "useful_life_months", "declining_rate", "salvage_rate",
] as const;

/**
 * The API READS the policy back as `depreciation.method` and only ACCEPTS it
 * as `depreciation_method`. This function used to send the screen's draft
 * verbatim — key `method` — so the API refused that one field, saved the three
 * numbers beside it, answered 200, and the Depreciation settings screen said
 * "policy saved". A category's depreciation method could never be changed
 * from that screen, and nothing said so: `_warnings.rejected_fields` was read
 * by nothing (handoff 30 §C). Found on the day the app began showing those
 * warnings. Proved against `test19` at the time: `{"method": …}` → 200
 * `rejected_fields: ["method"]`; `{"depreciation_method": …}` → 200, no
 * warning. Since handoff 31 the first of those is a 400 that saves nothing —
 * the same mistake would now fail loudly instead of half-working quietly.
 */
export const updateAssetCategory = async (
  id: number,
  body: Partial<CategoryPolicy & CategoryIdentity & CategoryClassIdentification & CategorySapClass>,
) => {
  const wire: Record<string, unknown> = {
    ...pickSet(body, CATEGORY_IDENTITY_KEYS),
    ...pickSet(body, CATEGORY_CLASS_KEYS),
    ...pickSet(body, CATEGORY_POLICY_NUMBER_KEYS),
  };
  if (body.method !== undefined) wire.depreciation_method = body.method;
  return (await apiPatch<AssetCategoryConfig>(`/api/v1/asset-categories/${id}`, wire)).data;
};

// POST is the one write route on this controller that does NOT refuse an
// unknown key — `create_category` filters the body and drops the rest with a
// 201 (v1_settings.py, read in handoff 31). Picked here all the same: what
// this app sends should not depend on which routes have been tightened yet.
export const createAssetCategory = async (body: Partial<CategoryIdentity>) =>
  (await apiPost<AssetCategoryConfig>("/api/v1/asset-categories",
    pickSet(body, CATEGORY_IDENTITY_KEYS), {
      idempotencyKey: newIdempotencyKey(),
    })).data;

/** Refused with 409 while the category still holds assets. */
export const deleteAssetCategory = async (id: number) =>
  (await apiDelete<{ deleted: boolean; id: number; name: string }>(
    `/api/v1/asset-categories/${id}`)).data;

export const fetchDepreciationSettings = async () =>
  (await apiGet<DepreciationSettings>("/api/v1/settings/depreciation")).data;

/** `_SETTINGS_WRITABLE` in v1_settings.py. `last_recompute` and `data_quality`
 *  are the server's output; `Partial<DepreciationSettings>` used to let a
 *  caller send them, and the route answers that with a 400. */
const DEPRECIATION_SETTINGS_KEYS = [
  "mode", "proration", "declining_switches_to_straight_line",
] as const;
export type DepreciationSettingsWrite =
  Partial<Pick<DepreciationSettings, typeof DEPRECIATION_SETTINGS_KEYS[number]>>;

export const updateDepreciationSettings = async (body: DepreciationSettingsWrite) =>
  (await apiPatch<DepreciationSettings>("/api/v1/settings/depreciation",
    pickSet(body, DEPRECIATION_SETTINGS_KEYS))).data;

export const recomputeDepreciation = async () =>
  (await apiPost<DepreciationSettings & { recomputed: number }>(
    "/api/v1/settings/depreciation/recompute", {})).data;

// ── Settings: branding ────────────────────────────────────────────────────

export interface TenantBranding {
  name: string;
  short_name: string;
  primary: string;
  primary_dark: string;
  /** data: URI, or "" to fall back to the bundled mark. */
  logo: string;
  /** The address invitations and password resets are sent from — the
   *  company record's email. "" when the company has none (handoff 45). */
  sender_email: string;
}

export const fetchBranding = async () =>
  (await apiGet<TenantBranding>("/api/v1/settings/branding")).data;

/** `name`, `sender_email` plus `_BRAND_PARAMS` in v1_settings.py — all six keys of
 *  `TenantBranding`, today. The Branding screen saves the object it was given
 *  by the GET, edited; that worked because the GET returns exactly these five
 *  and would stop working the day it returned a sixth. See `pickSet`. */
const BRANDING_KEYS = ["name", "short_name", "primary", "primary_dark", "logo", "sender_email"] as const;

export const updateBranding = async (body: Partial<TenantBranding>) =>
  (await apiPatch<TenantBranding>("/api/v1/settings/branding",
    pickSet(body, BRANDING_KEYS))).data;

// ── Settings: what this tenant's sidebar shows (handoff 48) ───────────────
//
// Presentation, not permission — `statement` says so and the Sidebar screen
// prints it. Keyed on the `key` each item carries in `lib/navigation.ts`.

export interface SidebarSwitch {
  key: string;
  /** This switch's own position. A locked switch is always true. */
  enabled: boolean;
  /** A row exists — somebody once set it. False = the default (on). */
  configured: boolean;
  locked: boolean;
  changed_by: { id: number; name: string } | null;
  changed_at: string | null;
}

export interface SidebarItemSwitch extends SidebarSwitch {
  /** Drawn on this tenant: its own switch AND its group's are on. */
  shown: boolean;
}

export interface SidebarSettings {
  statement: string;
  is_a_permission: false;
  default_when_unset: boolean;
  rule: string;
  locked_reason: string;
  parameter_prefix: string;
  groups: (SidebarSwitch & { items: SidebarItemSwitch[] })[];
  hidden_items: string[];
}

export const fetchSidebarSettings = async () =>
  (await apiGet<SidebarSettings>("/api/v1/settings/sidebar")).data;

/** Only the switches that change: `{items: {key: shown}, groups: {...}}`. */
export const updateSidebarSettings = async (body: {
  items?: Record<string, boolean>; groups?: Record<string, boolean>;
}) => (await apiPatch<SidebarSettings>("/api/v1/settings/sidebar", body)).data;

// ── Approvals: nobody moves an asset alone (handoff 35) ───────────────────
//
// One queue over `nrs.asset.change.request`. A move or a custody change on a
// tenant that requires approval is not an act any more, it is a REQUEST: the
// two asset routes above raise one and change nothing, and the change happens
// — or does not — when a second person decides here.
//
// Nothing in this block invents a rule. `can_decide`, `can_withdraw` and
// `premise_holds` are computed by the server per caller and per read, and the
// screens below only decline to OFFER what the server would refuse. The model
// remains the authority: a hidden button is a door closed on one screen, and
// report 30 found a disposed asset being un-disposed through a route nobody
// had looked at.

export type ApprovalState = "pending" | "approved" | "rejected" | "withdrawn";
export type ApprovalChangeType = "location" | "custody";

/**
 * One approval request, in full — every key `serialize_request` in
 * `myservice_api/controllers/v1_approvals.py` publishes, spelled the same way.
 *
 * Three groups of fields that are easy to confuse, and the API is careful
 * about all three, so this is too:
 *
 *   `approver`     WHO IS BEING ASKED. A nomination, sent by the requester.
 *   `decided_by`   WHO CLICKED. Taken from the bearer token, never a body
 *                  field — a requester who could name the decider could
 *                  appoint themselves an authority in the same breath.
 *   `from_*_name`  WHAT IT WAS WHEN ASKED, as a plain string copy. The `_id`
 *                  half can be emptied from outside the record (a location
 *                  renamed, an employee deleted); the string cannot, which is
 *                  why the queue shows the string and not the link's label.
 */
export interface ApprovalRequest {
  id: number;
  reference: string;
  state: ApprovalState;
  change_type: ApprovalChangeType;
  asset: ApprovalRef | null;
  asset_code: string | null;
  to_location: ApprovalRef | null;
  to_custodian: ApprovalRef | null;
  reason: string | null;
  from_location: ApprovalRef | null;
  from_custodian: ApprovalRef | null;
  from_location_name: string | null;
  from_custodian_name: string | null;
  to_location_name: string | null;
  to_custodian_name: string | null;
  from_state: string | null;
  requested_by: ApprovalRef | null;
  requested_by_name: string | null;
  requested_at: string | null;
  /** WHO IS BEING ASKED, now. `active` since handoff 45 (G.1(a)): false when
   *  that person's account has been deactivated, so the request is waiting
   *  on somebody who cannot sign in. Additive — `id`/`name` are unchanged. */
  approver: ApprovalApproverRef | null;
  /** Every time the request was re-pointed at somebody else, OLDEST FIRST.
   *  An append-only record on the server; `approver` is only who is asked
   *  NOW. Handoff 45 (G.1(b)). */
  renominations: ApprovalRenomination[];
  decided_by: ApprovalRef | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_reason: string | null;
  /** Computed fresh on every read, never stored: whether the world the
   *  request was raised about is still the world it would be applied to. */
  premise_holds: boolean;
  premise_broken_reason: string | null;
  movement_id: number | null;
  custody_id: number | null;
  transfer: { id: number; reference: string } | null;
  transfer_reference: string | null;
  /** Per CALLER. False on a request the caller raised themselves, and on one
   *  they could not have made the change for. */
  can_decide: boolean;
  can_withdraw: boolean;
  /** Per CALLER: true for the person who raised it, or an administrator,
   *  while it is pending. The model's own answer, so the button and the
   *  route's 403 agree. Handoff 45. */
  can_renominate: boolean;
}

/** The person a request is waiting on. See `ApprovalRequest.approver`. */
export interface ApprovalApproverRef extends ApprovalRef {
  active: boolean;
}

/**
 * One re-pointing of a request at a different approver — handoff 45, G.1(b).
 * `by` is the caller who did it, taken from their token; `from`/`to` carry
 * the names as they were when the row was written. The row cannot be edited
 * or deleted.
 */
export interface ApprovalRenomination {
  id: number;
  from: { id: number | null; name: string | null };
  to: { id: number | null; name: string | null };
  by: { id: number | null; name: string | null };
  at: string | null;
  reason: string | null;
}

/**
 * What `GET /api/v1/settings/approvals` says. READ-ONLY on the server, on
 * purpose and with an explanation: the people the rule constrains are exactly
 * the people who hold `settings:write`, so a PATCH twin would be a control
 * they could switch off, move the asset, and switch back on.
 *
 * `configured` is the key a screen needs and `required` cannot give it:
 * *nobody ever set this and it is getting the default* and *somebody
 * deliberately turned it on* are the same behaviour and very different facts.
 */
export interface ApprovalSettings {
  required: boolean;
  setting: "on" | "off" | null;
  configured: boolean;
  default_when_unset: boolean;
  parameter: string;
}

export const fetchApprovalSettings = async (): Promise<ApprovalSettings> =>
  (await apiGet<ApprovalSettings>("/api/v1/settings/approvals")).data;

/**
 * Who this caller may ask. The server already excludes the caller themselves
 * — `_check_approver_is_not_the_requester` refuses the nomination anyway, and
 * a picker offering a choice the model refuses is an answer that looks like
 * an answer.
 */
export const fetchApprovers = async (q?: string, limit = 10): Promise<ApprovalRef[]> =>
  (await apiGet<ApprovalRef[]>("/api/v1/approvals/approvers", { q, limit })).data;

export interface ApprovalFilters {
  state?: ApprovalState;
  change_type?: ApprovalChangeType;
  asset_id?: number;
  /** Only requests NAMING the caller as the approver. A convenience, not a
   *  boundary: anyone eligible may decide any pending request. */
  waiting_on_me?: boolean;
  raised_by_me?: boolean;
}

export interface ApprovalsPage {
  requests: ApprovalRequest[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

/**
 * `waiting_on_me` and `raised_by_me` are sent ONLY when true. The server reads
 * them with `parse_bool` and filters on `is True`, so `?waiting_on_me=false`
 * correctly means "do not filter" — but `buildUrl` in `lib/api.ts` drops
 * `undefined` and keeps `false`, and a URL carrying two explicit `false`s on
 * every request is noise in the access log for no gain.
 */
export async function fetchApprovalsPage(
  cursor: string | undefined,
  f?: ApprovalFilters,
): Promise<ApprovalsPage> {
  if (!apiConfigured) return { requests: [], nextCursor: null, totalEstimate: 0 };
  const res = await apiGet<ApprovalRequest[]>("/api/v1/approvals", {
    state: f?.state,
    change_type: f?.change_type,
    asset_id: f?.asset_id,
    waiting_on_me: f?.waiting_on_me ? true : undefined,
    raised_by_me: f?.raised_by_me ? true : undefined,
    limit: 100,
    cursor,
  });
  return {
    requests: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

/**
 * How many are waiting on the signed-in user, for the sidebar badge.
 *
 * `limit: 1` and the pagination total, which is the cheap-count idiom this
 * file already uses for every KPI (`countAssets` above). It is a count of the
 * CALLER's own domain and not of the returned window — `paginate` guarantees
 * that, and handoff 13 built the guarantee after a capped caller was told the
 * register held exactly as many rows as it had just been shown.
 *
 * Null rather than 0 when the server sends no total: a badge reading "0" and
 * a badge that could not be computed are different facts, and the sidebar
 * draws nothing for the second.
 *
 * BOTH kinds of waiting work since handoff 52 §1: the movement queue and the
 * pending tag replacements naming the caller as approver. The Approvals page
 * has shown the two side by side since handoff 51; the number beside the menu
 * item counted only the first (test19: 214 pending replacements, badge 0 of
 * them). Both routes are `assets:read` and both answer the cheap-count idiom
 * above. If EITHER total is missing — a failed call rejects the whole
 * Promise.all, a null total nulls the sum — the badge shows nothing rather
 * than half: "3" when the truth is "3 plus an unknown" is the same
 * under-report with a confident face.
 */
export async function fetchApprovalsWaitingCount(): Promise<number | null> {
  if (!apiConfigured) return null;
  const [moves, tags] = await Promise.all([
    apiGet<ApprovalRequest[]>("/api/v1/approvals", {
      state: "pending", waiting_on_me: true, limit: 1,
    }),
    apiGet<TagLabel[]>("/api/v1/tags/replacements", {
      state: "pending", waiting_on_me: true, limit: 1,
    }),
  ]);
  const movesTotal = moves.pagination?.total_estimate ?? null;
  const tagsTotal = tags.pagination?.total_estimate ?? null;
  if (movesTotal == null || tagsTotal == null) return null;
  return movesTotal + tagsTotal;
}

/**
 * The one request blocking this asset, or null.
 *
 * A database partial-unique index allows at most ONE pending request per
 * asset, so "the first of the list" is the whole answer rather than a
 * shortcut — but this still reads the list rather than asserting the index,
 * because an index is a fact about the database and this is a fact about the
 * response.
 */
export async function fetchAssetPendingApproval(assetId: string | number): Promise<ApprovalRequest | null> {
  if (!apiConfigured) return null;
  const res = await apiGet<ApprovalRequest[]>("/api/v1/approvals", {
    asset_id: assetId, state: "pending", limit: 1,
  });
  return res.data[0] ?? null;
}

/** What every decision route answers with: the request as it now stands, and
 *  the asset as it now stands. The asset is included on a REJECTION too, and
 *  that is not padding — the one thing the caller needs to know after any of
 *  these three calls is whether the asset moved, and the asset proves it
 *  rather than asking anybody to trust the verb. */
export interface ApprovalDecision {
  request: ApprovalRequest;
  asset: Asset;
}

async function decide(
  id: number,
  action: "approve" | "reject" | "withdraw",
  reason?: string,
): Promise<ApprovalDecision> {
  // `reason` and NOTHING else. All three routes refuse any other key with a
  // 400 (`refuse_unwritable`), and refuse `decided_by`/`approved_by`/`state`
  // with a sentence of their own — so an extra key here is not a dropped
  // field, it is a failed decision.
  const res = await apiPost<{ request: ApprovalRequest; asset: ApiAsset }>(
    `/api/v1/approvals/${id}/${action}`,
    reason ? { reason } : {},
    { idempotencyKey: newIdempotencyKey() },
  );
  return { request: res.data.request, asset: apiAssetToAsset(res.data.asset) };
}

export const approveChangeRequest  = (id: number, reason?: string) => decide(id, "approve", reason);
/** `reason` is REQUIRED by the route — it 400s on a blank one, because a
 *  rejection without one tells the person who asked nothing they can act on
 *  and they will simply ask again. */
export const rejectChangeRequest   = (id: number, reason: string)  => decide(id, "reject", reason);
export const withdrawChangeRequest = (id: number, reason?: string) => decide(id, "withdraw", reason);

/**
 * Ask somebody else — re-point a PENDING request at a different approver
 * (handoff 45, G.1(b)). Allowed to the person who raised it and to an
 * administrator; `can_renominate` on the row says which in advance.
 *
 * `approver_id` and `reason` and NOTHING else: the route refuses any other
 * key with a 400, and WHO re-pointed it is taken from the token. The reason
 * is REQUIRED and is kept on an append-only row. Nothing about the asset
 * changes, so only the approval queries need refreshing afterwards.
 */
export async function renominateChangeRequest(
  id: number,
  approverId: number,
  reason: string,
): Promise<{ request: ApprovalRequest; renomination: ApprovalRenomination }> {
  const res = await apiPost<{ request: ApprovalRequest; renomination: ApprovalRenomination }>(
    `/api/v1/approvals/${id}/renominate`,
    { approver_id: approverId, reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return res.data;
}

// ─── ADMINISTRATION — who has what (handoff 41) ──────────────────────────────
// Reads only. The three routes scope `admin`; the report scopes
// `identity:read`, which the admin wildcard covers. When there is no live
// session every fetcher answers empty rather than mock — there is no mock
// roster, and a page that invented one would be the "confident wrong answer
// about access" the handoff names as worse than no screen.

import type {
  AdminRole, AdminUser, AccessChangeReport, RoleChange,
} from "../types";

export async function fetchRoles(): Promise<AdminRole[]> {
  if (!apiConfigured) return [];
  const res = await apiGet<AdminRole[]>("/api/v1/roles");
  return res.data;
}

export interface UserFilters {
  /** Server-side search over name / login / email. */
  q?: string;
  /** Filters on EFFECTIVE membership — a role held by implication counts. */
  role?: string;
  /** Filters on DIRECT membership only. */
  role_direct?: string;
  /** `"true"` / `"false"`, or omitted for both. */
  active?: "true" | "false";
  is_api_client?: "true" | "false";
}

export interface UsersPage {
  users: AdminUser[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchUsersPage(
  cursor: string | undefined,
  f?: UserFilters,
): Promise<UsersPage> {
  if (!apiConfigured) return { users: [], nextCursor: null, totalEstimate: 0 };
  const res = await apiGet<AdminUser[]>("/api/v1/users", {
    q: f?.q || undefined,
    role: f?.role || undefined,
    role_direct: f?.role_direct || undefined,
    active: f?.active,
    is_api_client: f?.is_api_client,
    limit: 100,
    cursor,
  });
  return {
    users: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

/** 404s (as `CadraApiError`) for an id nobody has. */
export async function fetchUser(id: number | string): Promise<AdminUser> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<AdminUser>(`/api/v1/users/${id}`);
  return res.data;
}

export interface AccessChangesPage {
  report: AccessChangeReport;
  nextCursor: string | null;
  totalEstimate: number | null;
}

/**
 * One page of the access-changes report. A page is a window of ACCOUNTS in
 * ascending id — `events` and `roster` describe the same accounts — and
 * `summary` / `fidelity` describe the whole period on every page, so the
 * caller reads them off the first page and walks the cursor for the rows.
 * `from` and `to` are required by the route, `YYYY-MM-DD`, both inclusive.
 */
export async function fetchAccessChanges(
  from: string,
  to: string,
  cursor?: string,
): Promise<AccessChangesPage> {
  if (!apiConfigured) {
    throw new Error("No active session");
  }
  const res = await apiGet<AccessChangeReport>("/api/v1/reports/access-changes", {
    from, to, limit: 100, cursor,
  });
  return {
    report: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

// ─── ADMINISTRATION — the grant, and the refusal (handoff 42) ────────────────

/**
 * Grant and remove roles on a person: `POST /api/v1/users/<id>/roles`.
 *
 * `roles` is the FULL desired set of DIRECT roles among the GRANTABLE ones
 * (`AdminRole.grantable`) — the server computes the grants and the
 * revocations from it and leaves every role outside that set untouched, so
 * the caller never sends `system` and never has to. `dryRun` answers with the
 * same shape, `applied: false`, and writes nothing — and a change the server
 * would refuse is refused on the dry run too, in the same sentence.
 *
 * Every refusal arrives as a `CadraApiError` and is SHOWN, verbatim: the
 * self-grant ("Nobody grants themselves a role …"), the non-grantable role,
 * an unknown key (`400`, `details.allowed_values`). Nothing here pre-empts
 * the server's answer.
 *
 * A fresh idempotency key per call, as every other write in this file: a
 * retried apply replays the apply, and a dry run never stands in for one.
 */
export async function changeUserRoles(
  id: number | string,
  roles: string[],
  dryRun = false,
): Promise<RoleChange> {
  if (!apiConfigured) throw new Error("No active session");
  const body: { roles: string[]; dry_run?: boolean } = { roles };
  if (dryRun) body.dry_run = true;
  const res = await apiPost<RoleChange>(`/api/v1/users/${id}/roles`, body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return res.data;
}

// ─── ADMINISTRATION — the person, and the door (handoff 43) ──────────────────
// Four writes, every one answering with the user row as `GET /users/<id>`
// publishes it, so the panel can show the server's answer rather than its own
// guess. Every refusal arrives as a `CadraApiError` and is shown verbatim by
// the screen — nothing here pre-empts the server. A fresh idempotency key per
// call, as every other write in this file, and the `_warnings` toast comes
// for free through `apiPost`.

export interface CreateUserInput {
  name: string;
  email: string;
  /** The DIRECT roles to start with, among the GRANTABLE ones. Creating a
   *  person with roles IS granting roles: the handoff-42 guard judges the
   *  create, and a non-grantable key is refused with the account NOT made. */
  roles: string[];
  /** Default true on the server. `false` creates the account with no letter,
   *  to be invited later with `inviteUser`. */
  sendInvitation?: boolean;
}

/**
 * `POST /api/v1/users` — create a person and (by default) send them the
 * invitation. No password is typed anywhere: the letter carries a link the
 * person redeems to set their own. The create and the letter share one
 * savepoint on the server, so a letter that cannot be sent (`500
 * server_misconfigured`) leaves no account behind; a 409 `conflict` names
 * the account that already holds the address (`details.user_id`,
 * `details.active`).
 */
export async function createUser(input: CreateUserInput): Promise<AdminUser> {
  if (!apiConfigured) throw new Error("No active session");
  const body: { name: string; email: string; roles: string[]; send_invitation?: boolean } = {
    name: input.name,
    email: input.email,
    roles: input.roles,
  };
  // The server's default is `true`; the key is sent only when it is not, so
  // the body stays the minimum the route documents.
  if (input.sendInvitation === false) body.send_invitation = false;
  const res = await apiPost<AdminUser>("/api/v1/users", body, {
    idempotencyKey: newIdempotencyKey(),
  });
  return res.data;
}

/** The three action routes accept NO body key — "No body, or `{}`" — so `{}`
 *  is sent, which is what the route documents and what `api.post` in the
 *  browser suite sends too. */
async function userAction(id: number | string, action: "invite" | "deactivate" | "reactivate"): Promise<AdminUser> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiPost<AdminUser>(`/api/v1/users/${id}/${action}`, {}, {
    idempotencyKey: newIdempotencyKey(),
  });
  return res.data;
}

/** `POST /users/<id>/invite` — send the letter again (the first one went to
 *  spam). 409 for a deactivated account or one that has signed in already,
 *  400 for a credential or an account with no email, 500 if mail failed —
 *  and on that one "Nothing changed on the account." */
export const inviteUser     = (id: number | string) => userAction(id, "invite");
/** `POST /users/<id>/deactivate` — `active = False`. 403 on your own account,
 *  400 for a credential's user, 409 if already inactive or the last active
 *  system administrator. Roles and records stay; nothing is deleted. */
export const deactivateUser = (id: number | string) => userAction(id, "deactivate");
/** `POST /users/<id>/reactivate` — `active = True`. 409 if already active,
 *  400 for a credential. A cancelled invitation is NOT re-sent. */
export const reactivateUser = (id: number | string) => userAction(id, "reactivate");

// ─── AUDIT — the auditor's own screens (handoff 49) ──────────────────────────
//
// Four reads the server has answered for weeks with no page asking:
// configuration-changes, disposals, the register snapshot and the export.
// All four return the whole-period `summary`/`fidelity` on EVERY page, so a
// caller reads those off the first page and walks the cursor for rows only.
// A frontend token is uncapped (`record_cap()` is None for `aud=frontend`),
// so `_warnings.truncated` should never appear here — it is still passed
// through and shown, because "should never" is a bet, not a fact.

export interface ConfigurationChangesPage {
  report: ConfigurationChangeReport;
  nextCursor: string | null;
  totalEstimate: number | null;
  truncated: { cap: number; total: number; reason: string } | null;
}

/** One page of `GET /reports/configuration-changes`. `from`/`to` required,
 *  `YYYY-MM-DD`, both inclusive. Pages walk ascending parameter id. */
export async function fetchConfigurationChanges(
  from: string,
  to: string,
  cursor?: string,
): Promise<ConfigurationChangesPage> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<ConfigurationChangeReport>("/api/v1/reports/configuration-changes", {
    from, to, limit: 200, cursor,
  });
  return {
    report: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
    truncated: res._warnings?.truncated ?? null,
  };
}

export interface DisposalsReportPage {
  report: DisposalReport;
  nextCursor: string | null;
  totalEstimate: number | null;
  truncated: { cap: number; total: number; reason: string } | null;
}

/** One page of `GET /reports/disposals`. `from`/`to` required, both
 *  inclusive. `summary` and `unplaceable` describe the whole period on every
 *  page; `rows` pages by ascending asset id. */
export async function fetchDisposalsReport(
  from: string,
  to: string,
  cursor?: string,
): Promise<DisposalsReportPage> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<DisposalReport>("/api/v1/reports/disposals", {
    from, to, limit: 200, cursor,
  });
  return {
    report: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
    truncated: res._warnings?.truncated ?? null,
  };
}

export interface RegisterSnapshotPage {
  report: AssetRegisterSnapshot;
  nextCursor: string | null;
  totalEstimate: number | null;
  truncated: { cap: number; total: number; reason: string } | null;
}

/** One page of `GET /reports/asset-register`. `as_of` required; a future
 *  date is the server's 400, surfaced as thrown. The rows are rolled back to
 *  `as_of`; any FILTER the route takes selects on current values (the
 *  response's own `filters.note`), which is why this screen offers none. */
export async function fetchRegisterSnapshot(
  asOf: string,
  cursor?: string,
): Promise<RegisterSnapshotPage> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<AssetRegisterSnapshot>("/api/v1/reports/asset-register", {
    as_of: asOf, limit: 200, cursor,
  });
  return {
    report: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
    truncated: res._warnings?.truncated ?? null,
  };
}

/** What the register says about people who have LEFT and still hold assets
 *  (handoff 49 §4; measured as 87 assets / 59 people on the NRS register by
 *  reports 43 and 45, and nobody could see it outside a report). Derived
 *  entirely from `GET /identity/employees?active=false` — no new endpoint:
 *  each row already carries `assets.count` (assets still naming the person
 *  as custodian, disposed ones included) and `assets.has_pending_retrieval`. */
export interface DepartedHolders {
  /** Archived employees still named as custodian by at least one asset. */
  people: ApiEmployee[];
  /** Sum of their `assets.count`. */
  assetsHeld: number;
  /** How many of them have at least one asset flagged for retrieval. */
  withRetrievalFlagged: number;
  /** ALL archived employees seen, holders or not — the denominator. */
  departedSeen: number;
}

export async function fetchDepartedHolders(): Promise<DepartedHolders> {
  if (!apiConfigured) throw new Error("No active session");
  const people: ApiEmployee[] = [];
  let cursor: string | undefined;
  let seen = 0;
  // Walk every page: the answer is a count, and a count off a half-walked
  // list is the "zero without a denominator" shape CLAUDE.md warns about.
  for (;;) {
    const res = await apiGet<ApiEmployee[]>("/api/v1/identity/employees", {
      active: "false", limit: 500, cursor,
    });
    seen += res.data.length;
    people.push(...res.data.filter((e) => (e.assets?.count ?? 0) > 0));
    const next = res.pagination?.next_cursor;
    if (!next || res.data.length === 0) break;
    cursor = next;
  }
  return {
    people,
    assetsHeld: people.reduce((n, e) => n + (e.assets?.count ?? 0), 0),
    withRetrievalFlagged: people.filter((e) => e.assets?.has_pending_retrieval).length,
    departedSeen: seen,
  };
}

/** How many assets the register holds right now — the number the export
 *  screen puts beside the button so "download everything" has a size. */
export async function fetchRegisterTotal(): Promise<number | null> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<unknown[]>("/api/v1/assets", { limit: 1 });
  return res.pagination?.total_estimate ?? null;
}

// ─── RECEIPT GATES (handoff 57) ──────────────────────────────────────────────
//
// The gate machine lives on `nrs.asset` as one field, `register_state`
// (handoff 57); handoff 58 kept it there (evaluation §8), so these types and
// functions are extended, not rewritten.

/** `nrs.asset.register_state`. `registered` is the register; every other
 *  value is a received unit still passing its gates (a CANDIDATE). */
export type RegisterState =
  | "captured" | "vfm_pending" | "vfm_verified" | "vfm_approved" | "vfm_query"
  | "vfm_rejected" | "tag_requested" | "tag_issued" | "tagged"
  // Handoff 59 §2: a `record_only` unit skips both tagging gates and waits
  // here, on the Register Maker, with no label ever minted.
  | "reg_ready"
  | "reg_submitted" | "registered";

/** Whose move it is, computed by the server from the state. */
export type GateWaitingOn =
  | "store" | "iad" | "iad_approver" | "controller" | "tagging" | "maker" | "checker";

/** The URL slug of each gate route: `POST /api/v1/assets/<id>/gates/<slug>`. */
export type GateAction =
  | "submit" | "verify" | "approve" | "query" | "resubmit" | "reject"
  | "request-tagging" | "register" | "approve-registration" | "return-registration";

/** One action the caller's scopes earn for the record's current state.
 *  `can_fire` is the server's answer WITH the no-two-gates rule applied to
 *  this caller; when it is false, `refusal` is the sentence the server would
 *  answer with, and the app prints it instead of drawing a button. */
export interface GateAvailability {
  action: GateAction;
  can_fire: boolean;
  refusal: string | null;
  reason_required: boolean;
}

/** What the Register Maker submitted, as entered (handoff 60 §2d) — null
 *  until a submission. The checker's columns on the Candidates row read it.
 *  Not `sap.*`: that block is SAP's side (`sap.capitalisation_date` is SAP's
 *  own date, another field). */
export interface GateRegistration {
  sap_asset_code: string | null;
  cost: number | null;
  cost_centre: string;
  capitalisation_date: string | null;
  asset_class: { id: number; name: string; sap_asset_class: string | null } | null;
}

export interface AssetGates {
  waiting_on: GateWaitingOn | null;
  /** When the record entered its current state (UTC ISO). */
  state_since: string | null;
  available: GateAvailability[];
  /** Handoff 60. Optional because an older server does not publish it. */
  registration?: GateRegistration | null;
}

/** The gate half of an asset payload, plus what a candidate row shows. */
export interface CandidateRow {
  id: number;
  asset_code: string;
  name: string;
  serial_number: string | null;
  /** The issued tag's number, null until request-tagging mints one. */
  tag?: string | null;
  category: { id: number; name: string } | null;
  provenance?: {
    grn_reference: string | null;
    purchase_order_reference: string | null;
    purchase_vendor: string | null;
  } | null;
  register_state: RegisterState;
  gates: AssetGates;
  /** Only what the gates read: the cost the register dialog starts from
   *  (handoff 60 §2d). `serialize_asset` publishes the whole block. */
  financial?: { acquisition_cost?: number | null } | null;
  /** The mode the unit was RECEIVED under (handoff 58), fixed at receipt;
   *  null for anything received with the gates off or before 58. Optional
   *  because an older server does not publish it. */
  identification_mode?: Exclude<IdentificationMode, "pool"> | null;
  /** What a `record_only` unit is identified by (handoff 59) — title or
   *  plot number, licence key, contract. */
  record_reference?: string | null;
  /** The attributes a `tag_id` unit is identified by (handoff 58). */
  make?: string | null;
  model_name?: string | null;
  colour?: string | null;
  material?: string | null;
  dimensions?: string | null;
}

export interface CandidatesPage {
  rows: CandidateRow[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

/** `newest` (the server's default) or `oldest` — longest in its present
 *  state first, by `gates.state_since` (handoff 60 §2a). The walk direction
 *  is in the cursor: keep it the same across pages. */
export type CandidatesSort = "newest" | "oldest";

export interface CandidatesFilter {
  waitingOn?: GateWaitingOn;
  registerState?: RegisterState;
  /** Only the units waiting on an act THIS person may do — their gate's
   *  scope held and the no-two-gates rule not barring them (handoff 60). */
  waitingOnMe?: boolean;
  /** The server's search: name, asset code, tag, serial, GRN, PO… */
  q?: string;
  sort?: CandidatesSort;
}

/** `GET /api/v1/candidates` — every asset whose `register_state` is not
 *  `registered`. `candidates:read`. */
export async function fetchCandidatesPage(
  cursor: string | undefined,
  f: CandidatesFilter,
): Promise<CandidatesPage> {
  const res = await apiGet<CandidateRow[]>("/api/v1/candidates", {
    waiting_on: f.waitingOn,
    register_state: f.registerState,
    waiting_on_me: f.waitingOnMe ? "true" : undefined,
    q: f.q?.trim() || undefined,
    sort: f.sort,
    limit: 100,
    cursor,
  });
  return {
    rows: res.data,
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

/** The gate block of one asset, read fresh. The mapped `Asset` the asset page
 *  holds does not carry it, and the buttons must be the server's answer for
 *  THIS caller NOW, so it is its own query. */
export const fetchAssetGateState = async (assetId: number | string): Promise<CandidateRow> =>
  (await apiGet<CandidateRow>(`/api/v1/assets/${assetId}`)).data;

/** What the affix dialog needs to know about how a unit is identified, read
 *  off `GET /api/v1/assets/<id>`: the barcode lookup's payload carries the
 *  serial but neither the mode nor the attributes (handoff 58). */
export interface AssetIdentification {
  identification_mode: Exclude<IdentificationMode, "pool"> | null;
  name: string;
  make: string | null;
  colour: string | null;
}

export const fetchAssetIdentification = async (assetId: number): Promise<AssetIdentification> => {
  const a = (await apiGet<CandidateRow>(`/api/v1/assets/${assetId}`)).data;
  return {
    identification_mode: a.identification_mode ?? null,
    name: a.name,
    make: a.make ?? null,
    colour: a.colour ?? null,
  };
};

/** A verification's evidence, as the route takes it. */
export interface GateAttachment { name: string; mimetype: string; data: string }

export interface GateBody {
  notes?: string;
  reason?: string;
  response?: string;
  checklist?: { quantity: boolean; specification: boolean; condition: boolean; price: boolean };
  attachments?: GateAttachment[];
  sap_asset_code?: string;
  cost?: number;
  cost_centre?: string;
  capitalisation_date?: string;
  /** The category id — sent to CONFIRM the class; a different id corrects it. */
  asset_class?: number;
}

/** Fire one gate. Only the keys the action reads are sent, blanks omitted —
 *  a key a route does not accept is a 400 that writes nothing (handoff 31). */
export async function fireGate(
  assetId: number | string, action: GateAction, body: GateBody = {},
): Promise<CandidateRow> {
  const payload: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(body)) {
    if (v === undefined || v === null) continue;
    if (typeof v === "string" && !v.trim()) continue;
    payload[k] = typeof v === "string" ? v.trim() : v;
  }
  // No idempotency key: the gate routes do not honour one, and a key the
  // server ignores is a promise of exact replay nobody keeps. A repeat is
  // refused on state instead (409 invalid_state).
  return (await apiPost<CandidateRow>(
    `/api/v1/assets/${assetId}/gates/${action}`, payload)).data;
}

// ─── Batches (handoff 60 §2) ─────────────────────────────────────────────────
//
// A batch is N single-unit fires on the server, each checked and each with
// its own events; one refused unit never rolls the others back. The answer
// is a 200 listing every unit. A refusal of the WHOLE batch (a body it cannot
// read, units from more than one receipt, evidence that fails the rule, no
// cost centre) is an ordinary error envelope and nothing is written.

export type GateBatchAction =
  | "submit" | "verify" | "approve" | "request-tagging" | "approve-registration" | "register";

/** One unit's line in a batch answer. */
export interface GateBatchLine {
  /** `register` only: the number of the line as SENT, from 1. */
  line?: number;
  asset_id: number | null;
  asset_code: string | null;
  name: string | null;
  grn_reference: string | null;
  category: { id: number; name: string; sap_asset_class: string | null } | null;
  cost: number | null;
  sap_asset_code?: string | null;
  /** `would_fire` only on a dry run. */
  outcome: "fired" | "would_fire" | "refused";
  /** The status this unit alone would have answered. */
  status: number;
  code: string | null;
  /** The refusal, in the words a single fire uses. */
  message: string | null;
  details: Record<string, unknown> | null;
  register_state: RegisterState | null;
  /** The SAP class-digit warning (register / approve-registration). */
  warning?: string | null;
}

export interface GateBatchAnswer {
  action: GateBatchAction;
  dry_run: boolean;
  total: number;
  /** Fired — or that would fire, on a dry run. */
  fired: number;
  refused: number;
  results: GateBatchLine[];
  evidence?: { attachment_ids: number[]; files?: unknown };
}

/** The most units one batch takes (`BATCH_MAX` on the server). */
export const GATE_BATCH_MAX = 100;

export interface GateBatchVerifyBody {
  asset_ids: number[];
  checklist: { quantity: boolean; specification: boolean; condition: boolean; price: boolean };
  attachments: GateAttachment[];
  notes?: string;
  dry_run?: boolean;
}

export interface GateBatchIdsBody {
  asset_ids: number[];
  notes?: string;
  dry_run?: boolean;
}

export interface GateBatchRegisterLine {
  asset_code: string;
  sap_asset_code: string;
  /** Absent: the unit's own acquisition cost. */
  cost?: number;
}

export interface GateBatchRegisterBody {
  lines: GateBatchRegisterLine[];
  cost_centre: string;
  /** YYYY-MM-DD. */
  capitalisation_date: string;
  notes?: string;
  dry_run?: boolean;
}

/** `POST /api/v1/candidates/gates/<action>`. A blank `notes` is left out
 *  rather than sent empty. */
export async function fireGateBatch(action: "verify", body: GateBatchVerifyBody): Promise<GateBatchAnswer>;
export async function fireGateBatch(action: "submit" | "approve" | "request-tagging" | "approve-registration", body: GateBatchIdsBody): Promise<GateBatchAnswer>;
export async function fireGateBatch(action: "register", body: GateBatchRegisterBody): Promise<GateBatchAnswer>;
export async function fireGateBatch(
  action: GateBatchAction,
  body: GateBatchVerifyBody | GateBatchIdsBody | GateBatchRegisterBody,
): Promise<GateBatchAnswer> {
  const payload: Record<string, unknown> = { ...body };
  if (typeof payload.notes === "string" && payload.notes.trim()) payload.notes = payload.notes.trim();
  else delete payload.notes;
  if (!payload.dry_run) delete payload.dry_run;
  return (await apiPost<GateBatchAnswer>(`/api/v1/candidates/gates/${action}`, payload)).data;
}

/** Read a file the person picked into the route's attachment shape. */
export function fileToGateAttachment(file: File): Promise<GateAttachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(r.error ?? new Error("Could not read " + file.name));
    r.onload = () => {
      const url = String(r.result ?? "");
      resolve({
        name: file.name,
        mimetype: file.type || "application/octet-stream",
        data: url.slice(url.indexOf(",") + 1),
      });
    };
    r.readAsDataURL(file);
  });
}

/** Whether new receipts on this tenant start at the gates (`cadra.receipt.gated`,
 *  read from `GET /api/v1/settings`). `null` when the server does not say —
 *  an older server, or a caller who may not read settings — which the app
 *  treats as "do not claim either way". */
export async function fetchReceiptGated(): Promise<boolean | null> {
  try {
    const res = await apiGet<{ receipt_gated?: boolean }>("/api/v1/settings");
    return typeof res.data?.receipt_gated === "boolean" ? res.data.receipt_gated : null;
  } catch {
    return null;
  }
}

// ─── PLACEHOLDER SERIALS (handoff 59 §3) ─────────────────────────────────────
// SAP's register for NRS carries tens of thousands of "serials" that are not
// serials — `0`, `XXXX`, `4A12345FD`. A gated receipt refuses one as a
// placeholder, and the serial-uniqueness check ignores legacy assets that
// carry one, so a real serial is never refused because of them. The list is
// the tenant's (`cadra.serial_placeholders`); nothing here rewrites a serial.

export interface SerialPlaceholders {
  /** Matched case-insensitively, stripped, internal spaces collapsed. */
  exact: string[];
  /** Regular expressions, matched against the same normalised value. */
  patterns: string[];
  /** False while the tenant runs on the seeded list nobody has edited. */
  configured: boolean;
  /** The configuration parameter a change is recorded under. */
  parameter: string;
  /** The server's sentence about what the list does — shown as written. */
  statement: string;
  changed_by: { id: number; name: string } | null;
  changed_at: string | null;
  /** Measured, never cleaned: how many existing assets carry a placeholder. */
  legacy: {
    assets: number;
    with_serial: number;
    placeholders: number;
    top: { value: string; count: number }[];
  };
}

/** `settings:read`. */
export const fetchSerialPlaceholders = async (): Promise<SerialPlaceholders> =>
  (await apiGet<SerialPlaceholders>("/api/v1/settings/serial-placeholders")).data;

/** `settings:write`. Both lists are required — the PUT replaces the list
 *  whole — so the screen sends the full edited pair, never a delta. */
export const updateSerialPlaceholders = async (
  body: { exact: string[]; patterns: string[] },
): Promise<SerialPlaceholders> =>
  (await apiPut<SerialPlaceholders>("/api/v1/settings/serial-placeholders", {
    exact: body.exact, patterns: body.patterns,
  })).data;

// ─── ROLE EXCLUSIONS (handoff 58 §5 — Addendum A §4, rule 2) ────────────────
// Which two roles one person may not hold together. The table is enforced on
// the model under every writer of membership; these routes read and edit it.
// An existing pair is NOT revoked by a new exclusion — it is listed on
// `GET /settings/conflicting-grants` for the owner to decide.

/** The role keys an exclusion may name — the same keys `/roles` publishes.
 *  Used when `/roles` cannot be read (it scopes `admin`; this page scopes
 *  `settings:write`), so the add form still has something to offer. */
export const EXCLUDABLE_ROLE_KEYS = [
  "asset_user", "asset_officer", "asset_manager", "tag_issuing_unit",
  "iad_vfm_officer", "iad_vfm_approver", "asset_controller",
  "register_maker", "register_checker", "auditor",
  "audit_capturer", "audit_reviewer",
] as const;

export interface RoleRefKN { key: string; name: string }

export interface RoleExclusion {
  id: number;
  role_a: RoleRefKN;
  role_b: RoleRefKN;
  active: boolean;
  reason: string;
  /** Active people who hold BOTH roles now. */
  holders: number;
}

export interface ConflictingGrant {
  user: { id: number; name: string; login: string; active: boolean };
  pairs: { exclusion_id: number; role_a: RoleRefKN; role_b: RoleRefKN; reason: string }[];
}

export interface ConflictingGrants {
  rows: ConflictingGrant[];
  /** People, from `meta.total`; null when the server does not say. */
  total: number | null;
  /** The server's sentence (`meta.statement`), shown as written. */
  statement: string | null;
}

/** `settings:read` or `settings:write`. */
export const fetchRoleExclusions = async (): Promise<RoleExclusion[]> =>
  (await apiGet<RoleExclusion[]>("/api/v1/settings/role-exclusions")).data;

/** `settings:write`. 201 with the row. */
export const createRoleExclusion = async (
  body: { role_a: string; role_b: string; reason: string },
): Promise<RoleExclusion> =>
  (await apiPost<RoleExclusion>("/api/v1/settings/role-exclusions", {
    role_a: body.role_a, role_b: body.role_b, reason: body.reason.trim(),
  })).data;

/** `settings:write`. Only `active` and `reason` are accepted. */
export const updateRoleExclusion = async (
  id: number, body: { active?: boolean; reason?: string },
): Promise<RoleExclusion> => {
  const wire: Record<string, unknown> = {};
  if (body.active !== undefined) wire.active = body.active;
  if (body.reason !== undefined) wire.reason = body.reason.trim();
  return (await apiPatch<RoleExclusion>(`/api/v1/settings/role-exclusions/${id}`, wire)).data;
};

/** `settings:write`. Who already holds a pair the table forbids. */
export const fetchConflictingGrants = async (): Promise<ConflictingGrants> => {
  const res = await apiGet<ConflictingGrant[]>("/api/v1/settings/conflicting-grants");
  const meta = res.meta as unknown as { total?: unknown; statement?: unknown } | undefined;
  return {
    rows: res.data,
    total: typeof meta?.total === "number" ? meta.total : null,
    statement: typeof meta?.statement === "string" ? meta.statement : null,
  };
};
