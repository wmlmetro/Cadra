import type {
  Asset, Location, Employee, DashboardStats,
  FleetVehicle, FuelCard, FuelTransaction,
  BusRoute, BusSchedule, BusBooking, IdentityRecord,
} from "../types";
import { allMockAssets } from "../mock/assets";
import { mockLocations } from "../mock/locations";
import { mockEmployees } from "../mock/employees";
import { mockFleetVehicles, mockFuelCards, mockFuelTransactions } from "../mock/fleet";
import { mockBusRoutes, mockBusSchedules, mockBusBookings } from "../mock/staffBus";
import { mockIdentityRecords } from "../mock/identity";

// ─── ASSETS ───────────────────────────────────────────────────────────────────
export interface AssetFilters { category?: string; status?: string; condition?: string; zone?: string; search?: string; }
export function listAssets(f?: AssetFilters): Asset[] {
  let r = allMockAssets;
  if (f?.category)  r = r.filter(a => a.category  === f.category);
  if (f?.status)    r = r.filter(a => a.status    === f.status);
  if (f?.condition) r = r.filter(a => a.condition === f.condition);
  if (f?.zone)      r = r.filter(a => a.location.zone === f.zone);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(a => a.name.toLowerCase().includes(q) || a.assetTag.toLowerCase().includes(q) || a.legacyCode.toLowerCase().includes(q) || (a.custodianName ?? "").toLowerCase().includes(q) || a.department.toLowerCase().includes(q));
  }
  return r;
}
export function getAsset(id: string): Asset | undefined { return allMockAssets.find(a => a.id === id); }
export function getAssetsByCategory() { return [{ name: "IT Equipment", value: 10259 }, { name: "Fleet / Vehicles", value: 1619 }, { name: "Furniture & Fittings", value: 1272 }]; }
export function getAssetsByStatus() { return [{ name: "Cleared", value: 10842 }, { name: "Review — data quality", value: 985 }, { name: "Review — allottee not in nominal roll", value: 673 }, { name: "Review — VIN not verifiable", value: 418 }, { name: "Review — possible duplicate", value: 232 }]; }
export function getReviewQueueAssets(): Asset[] { return allMockAssets.filter(a => a.status !== "Cleared").slice(0, 8); }

// ─── LOCATIONS ────────────────────────────────────────────────────────────────
export function listLocations(): Location[] { return mockLocations; }
export function getLocation(id: string): Location | undefined { return mockLocations.find(l => l.id === id); }

// ─── EMPLOYEES ────────────────────────────────────────────────────────────────
export interface EmployeeFilters { department?: string; zone?: string; status?: string; search?: string; }
export function listEmployees(f?: EmployeeFilters): Employee[] {
  let r = mockEmployees;
  if (f?.department) r = r.filter(e => e.department === f.department);
  if (f?.zone)       r = r.filter(e => e.zone       === f.zone);
  if (f?.status)     r = r.filter(e => e.status     === f.status);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(e => e.name.toLowerCase().includes(q) || e.irNumber.toLowerCase().includes(q) || e.department.toLowerCase().includes(q) || e.title.toLowerCase().includes(q));
  }
  return r;
}
export function getEmployee(id: string): Employee | undefined { return mockEmployees.find(e => e.id === id); }
export function getEmployeeAssets(irNumber: string): Asset[] { return allMockAssets.filter(a => a.custodianIR === irNumber); }

// ─── IDENTITY ─────────────────────────────────────────────────────────────────
export interface IdentityFilters { clearanceLevel?: string; zone?: string; search?: string; }
export function listIdentityRecords(f?: IdentityFilters): IdentityRecord[] {
  let r = mockIdentityRecords;
  if (f?.clearanceLevel) r = r.filter(i => i.clearanceLevel === f.clearanceLevel);
  if (f?.zone)           r = r.filter(i => i.zone           === f.zone);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(i => i.employeeName.toLowerCase().includes(q) || i.irNumber.toLowerCase().includes(q) || i.department.toLowerCase().includes(q));
  }
  return r;
}

// ─── FLEET ────────────────────────────────────────────────────────────────────
export interface FleetFilters { vehicleType?: string; status?: string; zone?: string; isStaffBus?: boolean; search?: string; }
export function listFleetVehicles(f?: FleetFilters): FleetVehicle[] {
  let r = mockFleetVehicles;
  if (f?.vehicleType)              r = r.filter(v => v.vehicleType === f.vehicleType);
  if (f?.status)                   r = r.filter(v => v.status      === f.status);
  if (f?.zone)                     r = r.filter(v => v.zone        === f.zone);
  if (f?.isStaffBus !== undefined) r = r.filter(v => v.isStaffBus  === f.isStaffBus);
  if (f?.search) {
    const q = f.search.toLowerCase();
    r = r.filter(v => v.make.toLowerCase().includes(q) || v.model.toLowerCase().includes(q) || v.regNo.toLowerCase().includes(q) || (v.assignedDriverName ?? "").toLowerCase().includes(q));
  }
  return r;
}
export function getFleetVehicle(id: string): FleetVehicle | undefined { return mockFleetVehicles.find(v => v.id === id); }
export function getFleetVehicleByAssetId(assetId: string): FleetVehicle | undefined { return mockFleetVehicles.find(v => v.assetId === assetId); }
export function getFleetStats() {
  const v = mockFleetVehicles;
  return {
    total: v.length,
    active: v.filter(x => x.status === "Active").length,
    inMaintenance: v.filter(x => x.status === "In Maintenance").length,
    grounded: v.filter(x => x.status === "Grounded").length,
    buses: v.filter(x => x.isStaffBus).length,
  };
}

// ─── FUEL ─────────────────────────────────────────────────────────────────────
export function listFuelCards(): FuelCard[] { return mockFuelCards; }
export function getFuelCard(id: string): FuelCard | undefined { return mockFuelCards.find(f => f.id === id); }
export function listFuelTransactions(vehicleId?: string): FuelTransaction[] {
  return vehicleId ? mockFuelTransactions.filter(t => t.vehicleId === vehicleId) : mockFuelTransactions;
}
export function getFuelStats() {
  const t = mockFuelTransactions;
  return {
    totalSpend:   t.reduce((s, x) => s + x.totalCost, 0),
    totalLitres:  t.reduce((s, x) => s + x.litres, 0),
    flaggedCount: t.filter(x => x.status === "Flagged").length,
    pendingCount: t.filter(x => x.status === "Pending Verification").length,
  };
}

// ─── STAFF BUS ────────────────────────────────────────────────────────────────
export function listBusRoutes(): BusRoute[] { return mockBusRoutes; }
export function getBusRoute(id: string): BusRoute | undefined { return mockBusRoutes.find(r => r.id === id); }
export function listBusSchedules(f?: { date?: string; status?: string }): BusSchedule[] {
  let r = mockBusSchedules;
  if (f?.date)   r = r.filter(s => s.departureDate === f.date);
  if (f?.status) r = r.filter(s => s.status        === f.status);
  return r;
}
export function getBusSchedule(id: string): BusSchedule | undefined { return mockBusSchedules.find(s => s.id === id); }
export function listBookings(scheduleId?: string): BusBooking[] {
  return scheduleId ? mockBusBookings.filter(b => b.scheduleId === scheduleId) : mockBusBookings;
}
export function getBusStats() {
  const today = mockBusSchedules.filter(s => s.departureDate === "2026-06-10");
  return {
    todayTrips:       today.length,
    activeTrips:      today.filter(s => ["In Transit", "Boarding", "Departed"].includes(s.status)).length,
    arrivedTrips:     today.filter(s => s.status === "Arrived").length,
    passengersToday:  today.reduce((s, t) => s + t.bookedSeats, 0),
  };
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
export function getDashboardStats(): DashboardStats {
  return { totalAssets: 13150, itEquipment: 10259, fleetVehicles: 1619, furniture: 1272, locations: 1163, employees: 11385, reviewQueue: 847 };
}
