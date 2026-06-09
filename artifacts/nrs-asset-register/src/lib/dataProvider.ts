/**
 * dataProvider — wraps the mock data layer.
 *
 * To switch to Odoo 17 JSON-RPC later, replace each function body with
 * a call to /web/dataset/call_kw targeting:
 *   - model 'nrs.asset'    for asset operations
 *   - model 'generic.location' for location operations
 *
 * Example:
 *   const resp = await fetch('/web/dataset/call_kw', {
 *     method: 'POST',
 *     headers: { 'Content-Type': 'application/json' },
 *     body: JSON.stringify({
 *       jsonrpc: '2.0', method: 'call', id: 1,
 *       params: { model: 'nrs.asset', method: 'search_read', args: [[]], kwargs: { fields: [...] } }
 *     })
 *   });
 */
import type { Asset, Location, Employee, DashboardStats } from '../types';
import { allMockAssets } from '../mock/assets';
import { mockLocations } from '../mock/locations';
import { mockEmployees } from '../mock/employees';

export interface AssetFilters {
  category?: string;
  status?: string;
  condition?: string;
  zone?: string;
  search?: string;
}

export function listAssets(filters?: AssetFilters): Asset[] {
  let results = allMockAssets;
  if (filters?.category) results = results.filter(a => a.category === filters.category);
  if (filters?.status) results = results.filter(a => a.status === filters.status);
  if (filters?.condition) results = results.filter(a => a.condition === filters.condition);
  if (filters?.zone) results = results.filter(a => a.location.zone === filters.zone);
  if (filters?.search) {
    const q = filters.search.toLowerCase();
    results = results.filter(a =>
      a.name.toLowerCase().includes(q) ||
      a.assetTag.toLowerCase().includes(q) ||
      a.legacyCode.toLowerCase().includes(q) ||
      (a.custodianName ?? '').toLowerCase().includes(q) ||
      a.department.toLowerCase().includes(q)
    );
  }
  return results;
}

export function getAsset(id: string): Asset | undefined {
  return allMockAssets.find(a => a.id === id);
}

export function listLocations(): Location[] {
  return mockLocations;
}

export function getLocation(id: string): Location | undefined {
  return mockLocations.find(l => l.id === id);
}

export function listEmployees(): Employee[] {
  return mockEmployees;
}

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

export function getReviewQueueAssets(): Asset[] {
  return allMockAssets.filter(a => a.status !== 'Cleared').slice(0, 8);
}

export function getAssetsByCategory() {
  return [
    { name: 'IT Equipment', value: 10259 },
    { name: 'Fleet / Vehicles', value: 1619 },
    { name: 'Furniture & Fittings', value: 1272 },
  ];
}

export function getAssetsByStatus() {
  return [
    { name: 'Cleared', value: 10842 },
    { name: 'Review — data quality', value: 985 },
    { name: 'Review — allottee not in nominal roll', value: 673 },
    { name: 'Review — VIN not verifiable', value: 418 },
    { name: 'Review — possible duplicate', value: 232 },
  ];
}
