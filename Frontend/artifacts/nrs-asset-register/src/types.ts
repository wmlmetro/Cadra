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
}

export interface Asset {
  id: string;
  name: string;
  assetTag: string;
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
  locationType?: "Zone" | "State" | "Office" | "Floor" | "Room";
  zoneCode?: string;
  parent?: string;
  street?: string;
  street2?: string;
  city?: string;
  state?: string;
  country: string;
  active: boolean;
  childrenCount?: number;
  assetCount?: number;    // assets at/under this node
  childStates?: number;   // zone-level rollup
  childOffices?: number;  // zone/state-level rollup
  coordinates?: { lat: number; lng: number };
}

// ─── EMPLOYEE ─────────────────────────────────────────────────────────────────
export type EmployeeStatus = "Active" | "Inactive" | "On Leave" | "Suspended";
export type EmploymentType = "Permanent" | "Contract" | "Secondment";

export interface Employee {
  id: string;
  name: string;
  irNumber: string;
  department: string;
  zone: string;
  office: string;
  title: string;
  gradeLevel: number;
  employmentType: EmploymentType;
  status: EmployeeStatus;
  gender: "Male" | "Female";
  phone: string;
  email: string;
  nin?: string;
  joinDate: string;
  avatarColor: string;
  identityVerified: boolean;
  biometricEnrolled: boolean;
  accessCardNo?: string;
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
