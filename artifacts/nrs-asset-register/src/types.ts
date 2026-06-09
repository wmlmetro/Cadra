export type ApprovalStatus =
  | 'Cleared'
  | 'Review — data quality'
  | 'Review — allottee not in nominal roll'
  | 'Review — VIN not verifiable'
  | 'Review — possible duplicate';

export interface AssetLocation {
  zone: string;
  state: string;
  office: string;
  path: string;
}

export interface Asset {
  id: string;
  name: string;
  assetTag: string;
  legacyCode: string;
  category: 'IT Equipment' | 'Fleet / Vehicles' | 'Furniture & Fittings';
  subcategory: string;
  assetType: string;
  manufacturer: string;
  model: string;
  serial: string;
  systemDomain?: string;
  registrationNo?: string;
  engineNo?: string;
  condition: 'Good' | 'Fair' | 'Poor' | 'Faulty';
  custodianName?: string;
  custodianIR?: string;
  department: string;
  location: AssetLocation;
  status: ApprovalStatus;
  reviewFlags: string[];
  custodianScore?: number;
  imageUrl?: string;
}

export interface Location {
  id: string;
  name: string;
  locationType?: 'Zone' | 'State' | 'Office' | 'Floor' | 'Room';
  zoneCode?: string;
  parent?: string;
  street?: string;
  street2?: string;
  city?: string;
  state?: string;
  country: string;
  active: boolean;
  childrenCount?: number;
}

export interface Employee {
  id: string;
  name: string;
  irNumber: string;
  department: string;
  location: string;
  title: string;
}

export interface DashboardStats {
  totalAssets: number;
  itEquipment: number;
  fleetVehicles: number;
  furniture: number;
  locations: number;
  employees: number;
  reviewQueue: number;
}
