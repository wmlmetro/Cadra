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
import { apiConfigured, apiGet } from "./api";
import {
  apiEmployeeToEmployee, type ApiEmployee,
  apiAssetToAsset, type ApiAsset,
  apiLocationToLocation, type ApiLocation,
} from "./adapters";

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

export async function fetchAsset(id: string): Promise<Asset | null> {
  if (!apiConfigured) return getAsset(id) ?? null;
  try {
    const res = await apiGet<ApiAsset>(`/api/v1/assets/${id}`);
    return apiAssetToAsset(res.data);
  } catch (e) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code === "not_found") {
      return null;
    }
    throw e;
  }
}
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
