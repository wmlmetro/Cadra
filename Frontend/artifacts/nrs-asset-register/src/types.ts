export type ApprovalStatus =
  | "Cleared"
  | "Review — data quality"
  | "Review — allottee not in nominal roll"
  | "Review — VIN not verifiable"
  | "Review — possible duplicate";

export interface AssetLocation {
  zone: string;
  state: string;
  office: string;
  path: string;
  // FK ids exposed by the API. Populated when present so the asset detail
  // page can render clickable links into LocationDetail.
  locationId?: number;
  buildingId?: number;
  floorId?: number;
  roomId?: number;
}

export type DepreciationMethod =
  | "none"
  | "straight_line"
  | "declining_balance"
  | "erp_managed";

export type DepreciationState =
  | "not_applicable"
  | "not_started"
  | "depreciating"
  | "fully_depreciated"
  | "disposed"
  | "erp_managed";

/** Where the depreciation start date came from. "created" means it was
 *  inferred from the import timestamp, not a real business date. */
export type DepreciationStartSource =
  | "acquisition"
  | "purchase"
  | "created"
  | "manual";

export interface AssetDepreciation {
  method: DepreciationMethod;
  usefulLifeMonths?: number;
  decliningRate?: number;
  salvageValue?: number;
  depreciableCost?: number;
  startDate?: string;
  startDateSource?: DepreciationStartSource;
  startDateIsEstimated: boolean;
  accumulatedDepreciation?: number;
  currentBookValue?: number;
  state: DepreciationState;
  endDate?: string;
  usesCategoryPolicy: boolean;
}

export interface AssetFinancials {
  currency?: string;
  purchaseValue?: number;
  replacementCost?: number;
  acquisitionCost?: number;
  /** Legacy hand-entered figure. Superseded by depreciation.currentBookValue. */
  currentValue?: number;
  depreciation?: AssetDepreciation;
}

export interface AssetKeyDates {
  purchaseDate?: string;
  warrantyExpiry?: string;
  acquisitionDate?: string;
  disposalDate?: string;
  lastVerifiedDate?: string;
  nextServiceDate?: string;
}

export interface Asset {
  id: string;
  name: string;
  assetTag: string;
  assetCode?: string;
  legacyCode: string;
  category: "IT Equipment" | "Fleet / Vehicles" | "Furniture & Fittings";
  subcategory: string;
  assetType: string;
  manufacturer: string;
  model: string;
  serial: string;
  systemDomain?: string;
  registrationNo?: string;
  engineNo?: string;
  condition: "Good" | "Fair" | "Poor" | "Faulty";
  lifecycleState?: "active" | "in_repair" | "disposed" | "transferred" | "missing";
  isVerified?: boolean;
  custodianId?: number;
  custodianName?: string;
  custodianIR?: string;
  parentAssetId?: number;
  department: string;
  location: AssetLocation;
  status: ApprovalStatus;
  reviewFlags: string[];
  custodianScore?: number;
  imageUrl?: string;
  financials?: AssetFinancials;
  keyDates?: AssetKeyDates;
  maintenanceVendor?: string;
  notes?: string;
  pmCount?: number;
  requestCount?: number;
  parentAssetName?: string;
  childCount?: number;
}

export interface Location {
  id: string;
  name: string;
  description?: string;
  locationType?: "Zone" | "State" | "Office" | "Floor" | "Room";
  zoneCode?: string;
  parent?: string;
  street?: string;
  street2?: string;
  city?: string;
  state?: string;
  country: string;
  zip?: string;
  floorNumber?: number;
  active: boolean;
  childrenCount?: number;
  childAllCount?: number; // total descendants at any depth
  assetCount?: number;
  childStates?: number;
  childOffices?: number;
  coordinates?: { lat: number; lng: number };
  updatedAt?: string;
}

// ─── EMPLOYEE ─────────────────────────────────────────────────────────────────
export type EmployeeStatus = "Active" | "Inactive" | "On Leave" | "Suspended";
export type EmploymentType = "Permanent" | "Contract" | "Secondment";

export interface EmployeeManager {
  id?: number;
  irNumber?: string;
  name?: string;
}

export interface SapMeta {
  userId?: string;
  status?: string;        // active|suspended|on_leave|transferred|exited
  syncStatus?: string;    // synced|pending|error|never
  lastSync?: string;
  managerIr?: string;
}

export interface Employee {
  id: string;
  name: string;
  irNumber: string;
  department: string;
  zone: string;
  office: string;
  officeId?: number;
  title: string;
  gradeLevel: number;
  gradeLevelRaw?: string;
  costCentre?: string;
  employmentType: EmploymentType;
  status: EmployeeStatus;
  gender: "Male" | "Female";
  phone: string;
  email: string;
  nin?: string;
  joinDate: string;
  employmentEndDate?: string;
  avatarColor: string;
  identityVerified: boolean;
  biometricEnrolled: boolean;
  accessCardNo?: string;
  manager?: EmployeeManager;
  sap?: SapMeta;
  custodialAssetCount?: number;
  hasPendingRetrieval?: boolean;
}

// ─── IDENTITY ─────────────────────────────────────────────────────────────────
export type VerificationStatus = "Verified" | "Pending" | "Mismatch" | "Missing";
export type BiometricStatus = "Enrolled" | "Partial" | "Not Enrolled";
export type ClearanceLevel = "Full" | "Partial" | "Pending" | "Blocked";

export interface IdentityRecord {
  id: string;
  employeeId: string;
  employeeName: string;
  irNumber: string;
  department: string;
  zone: string;
  nin?: string;
  ninStatus: VerificationStatus;
  bvn?: string;
  bvnStatus: VerificationStatus;
  biometricStatus: BiometricStatus;
  accessCard?: string;
  accessCardStatus: "Active" | "Inactive" | "Lost" | "Not Issued";
  lastVerified?: string;
  clearanceLevel: ClearanceLevel;
}

// ─── FLEET ────────────────────────────────────────────────────────────────────
export type VehicleType = "SUV" | "Sedan" | "Pickup" | "Bus" | "Van" | "Truck";
export type VehicleStatus = "Active" | "In Maintenance" | "Grounded" | "Decommissioned";
export type FuelType = "Petrol" | "Diesel" | "CNG";

export interface FleetVehicle {
  id: string;
  assetId: string;
  assetTag: string;
  make: string;
  model: string;
  year: number;
  vehicleType: VehicleType;
  regNo: string;
  vin: string;
  engineNo: string;
  color: string;
  fuelType: FuelType;
  tankCapacity: number;
  currentOdometer: number;
  status: VehicleStatus;
  assignedDriverId?: string;
  assignedDriverName?: string;
  zone: string;
  office: string;
  fuelCardId?: string;
  lastServiceDate: string;
  nextServiceKm: number;
  isStaffBus: boolean;
  routeId?: string;
  seatingCapacity?: number;
  insuranceExpiry: string;
  roadWorthinessExpiry: string;
  department: string;
}

// ─── FUEL ─────────────────────────────────────────────────────────────────────
export type FuelTxnStatus = "Approved" | "Pending Verification" | "Flagged" | "Rejected";

export interface FuelCard {
  id: string;
  cardNo: string;
  vehicleId: string;
  vehicleName: string;
  regNo: string;
  assignedDriverName?: string;
  monthlyLimit: number;
  monthlySpend: number;
  status: "Active" | "Suspended" | "Expired";
  issueDate: string;
  expiryDate: string;
}

export interface FuelTransaction {
  id: string;
  fuelCardId: string;
  vehicleId: string;
  vehicleName: string;
  regNo: string;
  driverName: string;
  date: string;
  time: string;
  station: string;
  locationName: string;
  litres: number;
  pricePerLitre: number;
  totalCost: number;
  odometerReading: number;
  fuelType: FuelType;
  status: FuelTxnStatus;
  flagReason?: string;
  hasMeterPhoto: boolean;
  verifiedBy?: string;
}

// ─── STAFF BUS ────────────────────────────────────────────────────────────────
export interface BusRoute {
  id: string;
  code: string;
  name: string;
  origin: string;
  destination: string;
  distanceKm: number;
  estimatedDuration: string;
  stops: string[];
  vehicleId?: string;
  active: boolean;
}

export type ScheduleStatus = "Scheduled" | "Boarding" | "Departed" | "In Transit" | "Arrived" | "Cancelled";

export interface BusSchedule {
  id: string;
  routeId: string;
  routeCode: string;
  routeName: string;
  vehicleId: string;
  vehicleRegNo: string;
  vehicleName: string;
  driverName: string;
  departureDate: string;
  departureTime: string;
  estimatedArrival: string;
  totalSeats: number;
  bookedSeats: number;
  checkedIn: number;
  status: ScheduleStatus;
  direction: "Outbound" | "Return";
}

export type BookingStatus = "Confirmed" | "Checked In" | "Boarded" | "No Show" | "Cancelled";

export interface BusBooking {
  id: string;
  scheduleId: string;
  passengerName: string;
  passengerIR: string;
  department: string;
  zone: string;
  seatNo: number;
  status: BookingStatus;
  bookedAt: string;
  purpose: string;
  checkinTime?: string;
  boardingTime?: string;
}

// ─── SERVICE DESK REQUEST ─────────────────────────────────────────────────────

export type RequestPriority = "0" | "1" | "2" | "3" | "4";
export type RequestKanbanState = "normal" | "done" | "blocked";

export interface RequestStageRoute {
  id: number;
  name: string;
  to_stage_id: number;
  to_stage_name: string;
}

export interface RequestMessage {
  id: number;
  date: string;
  author: { id: number; name: string } | null;
  subject: string | null;
  body_html: string | null;
  is_internal?: boolean;
}

export interface ServiceRequest {
  id: string;
  reference: string;
  typeName: string;
  typeId: number | null;
  categoryName: string | null;
  categoryId: number | null;
  stageName: string;
  stageId: number | null;
  stageCode: string | null;
  stageClosed: boolean;
  kanbanState: RequestKanbanState;
  priority: RequestPriority;
  impact: string | null;
  urgency: string | null;
  subject: string;
  requestText: string;
  responseText: string | null;
  author: { id: number; name: string } | null;
  assignee: { id: number; name: string } | null;
  partner: { id: number; name: string } | null;
  service: { id: number; name: string } | null;
  parentId: number | null;
  tags: Array<{ id: number; name: string }>;
  deadline: string | null;
  createdAt: string;
  updatedAt?: string;
  assignedAt?: string;
  movedAt?: string;
  closedAt?: string;
  location: { id: number; name: string } | null;
  asset:    { id: number; name: string } | null;
  vehicle:  { id: number; name: string } | null;
  // Optional embedded collections (via ?include=)
  routes?: RequestStageRoute[];
  messages?: RequestMessage[];
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
export interface DashboardStats {
  totalAssets: number;
  itEquipment: number;
  fleetVehicles: number;
  furniture: number;
  locations: number;
  employees: number;
  reviewQueue: number;
}
