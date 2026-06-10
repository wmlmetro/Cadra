import type {
  Asset,
  Location,
  Employee,
  DashboardStats,
  FleetVehicle,
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
import { apiConfigured, apiGet, apiPost, apiPatch, apiUpload, newIdempotencyKey } from "./api";
import {
  apiEmployeeToEmployee, type ApiEmployee,
  apiAssetToAsset, type ApiAsset,
  apiLocationToLocation, type ApiLocation,
  apiRequestToRequest, type ApiRequest,
} from "./adapters";
import type { ServiceRequest } from "../types";

// ─── ASSETS ───────────────────────────────────────────────────────────────────
export interface AssetFilters {
  category?: string;
  status?: string;
  condition?: string;
  zone?: string;
  search?: string;
}
export function listAssets(f?: AssetFilters): Asset[] {
  let r = allMockAssets;
  if (f?.category) r = r.filter((a) => a.category === f.category);
  if (f?.status) r = r.filter((a) => a.status === f.status);
  if (f?.condition) r = r.filter((a) => a.condition === f.condition);
  if (f?.zone) r = r.filter((a) => a.location.zone === f.zone);
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

// Frontend filter values mapped to backend enum values.
const CONDITION_TO_API: Record<string, string> = {
  Good: "good", Fair: "fair", Poor: "poor", Faulty: "damaged",
};

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
  // Frontend status maps to backend is_verified: only "Review — data quality"
  // has a real backend filter today (unverified = review-queue). Other review
  // statuses are mock-only review-queue concepts that the API doesn't model.
  const isVerifiedFilter =
    f?.status === "Cleared" ? true :
    f?.status === "Review — data quality" ? false :
    undefined;
  const res = await apiGet<ApiAsset[]>("/api/v1/assets", {
    q: f?.search,
    condition: f?.condition ? CONDITION_TO_API[f.condition] : undefined,
    is_verified: isVerifiedFilter,
    limit: 200,
    cursor,
  });
  return {
    assets: res.data.map(apiAssetToAsset),
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
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

/** Body shape mirrors _WRITABLE_FIELDS in myservice_api/controllers/v1_assets.py. */
export interface AssetWriteBody {
  name?: string;
  asset_tag?: string | null;
  legacy_asset_code?: string | null;
  serial_number?: string | null;
  make?: string | null;
  model_name?: string | null;
  manufacturer?: string | null;
  category_id?: number | null;
  subcategory_id?: number | null;
  asset_type_id?: number | null;
  asset_level?: string | null;
  domain?: string | null;
  parent_id?: number | null;
  building_id?: number | null;
  floor_id?: number | null;
  room_id?: number | null;
  location_id?: number | null;
  custodian_id?: number | null;
  department?: string | null;
  condition?: "new" | "good" | "fair" | "poor" | "damaged";
  state?: "active" | "in_repair" | "disposed" | "transferred" | "missing";
  currency_id?: number | null;
  purchase_date?: string | null;
  warranty_expiry?: string | null;
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

export async function moveAsset(id: string, to_location_id: number, reason?: string): Promise<Asset> {
  const res = await apiPost<ApiAsset>(
    `/api/v1/assets/${id}/move`,
    { to_location_id, reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data);
}

export async function transferCustody(id: string, to_custodian_id: number, reason?: string): Promise<Asset> {
  const res = await apiPost<ApiAsset>(
    `/api/v1/assets/${id}/transfer-custody`,
    { to_custodian_id, reason },
    { idempotencyKey: newIdempotencyKey() },
  );
  return apiAssetToAsset(res.data);
}

// ─── ASSET COUNTS (cheap dashboard primitives) ───────────────────────────────

/** Single count via limit=1 + total_estimate. */
async function countAssets(params: Record<string, unknown>): Promise<number> {
  if (!apiConfigured) return 0;
  const res = await apiGet<ApiAsset[]>("/api/v1/assets", { ...params, limit: 1 });
  return res.pagination?.total_estimate ?? 0;
}

export interface AssetRegisterCounts {
  total: number;
  active: number;
  inRepair: number;
  disposed: number;
  unverified: number;
  verified: number;
}

/**
 * Asset Register dashboard top strip. Runs five count queries in parallel —
 * each is a single limit=1 call so this is cheap. PM-overdue is deliberately
 * not here: the API doesn't yet expose a maintenance.due/overdue count for
 * assets (backend gap noted in the deployment plan).
 */
export async function fetchAssetRegisterCounts(): Promise<AssetRegisterCounts> {
  if (!apiConfigured) {
    return { total: 0, active: 0, inRepair: 0, disposed: 0, unverified: 0, verified: 0 };
  }
  const [total, active, inRepair, disposed, unverified] = await Promise.all([
    countAssets({}),
    countAssets({ state: "active" }),
    countAssets({ state: "in_repair" }),
    countAssets({ state: "disposed" }),
    countAssets({ is_verified: false }),
  ]);
  return { total, active, inRepair, disposed, unverified, verified: Math.max(0, total - unverified) };
}

// Convenience PATCHes — the Odoo asset form has "Mark Verified / Mark Missing /
// Condemn" as one-click buttons. Same endpoint, different bodies.
export const markAssetVerified = (id: string) =>
  updateAsset(id, { last_verified_date: new Date().toISOString().slice(0, 10) });

export const markAssetMissing = (id: string) =>
  updateAsset(id, { state: "missing" });

export const condemnAsset = (id: string, disposal_reason: string) =>
  updateAsset(id, {
    state: "disposed",
    disposal_date: new Date().toISOString().slice(0, 10),
    disposal_reason,
  });
export function getAssetsByCategory() {
  return [
    { name: "IT Equipment", value: 10259 },
    { name: "Fleet / Vehicles", value: 1619 },
    { name: "Furniture & Fittings", value: 1272 },
  ];
}
export function getAssetsByStatus() {
  return [
    { name: "Cleared", value: 10842 },
    { name: "Review — data quality", value: 985 },
    { name: "Review — allottee not in nominal roll", value: 673 },
    { name: "Review — VIN not verifiable", value: 418 },
    { name: "Review — possible duplicate", value: 232 },
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
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", {
    q: search,
    limit: 200,
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
export interface DashboardMap {
  locations: DashboardMapLocation[];
  fleet: DashboardMapFleet[];
  recent_requests: Array<{
    id: number; name: string; stage: string; location: string;
    priority: string; create_date: string;
  }>;
}

export const fetchDashboardKpis = async () =>
  (await apiGet<DashboardKpis>("/api/v1/dashboard/kpis")).data;
export const fetchDashboardMap = async () =>
  (await apiGet<DashboardMap>("/api/v1/dashboard/map")).data;

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
export const fetchBarcodeKpis       = async () => (await apiGet<BarcodeKpis>("/api/v1/barcode/kpis")).data;
export const fetchBarcodeRecentTags = async (params?: { domain_filter?: string; limit?: number }) =>
  (await apiGet<BarcodeTag[]>("/api/v1/barcode/recent-tags", params)).data;
export const lookupBarcode = async (query: string) =>
  (await apiGet<BarcodeTag | { tag: BarcodeTag | null; asset: ApiAsset | null }>(`/api/v1/barcode/lookup`, { query })).data;

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

/** Mirrors _WRITABLE_FIELDS in v1_requests.py. stage_id is intentionally excluded
 *  — use transitionRequest() instead. */
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
