/**
 * `status` is a DATA-QUALITY fact, and it only means anything for an asset in
 * service: active and verified is "Cleared", active and unverified is in the
 * review queue. LIFECYCLE is a different fact and lives on `lifecycleState`
 * (the model's `state` key). An asset that is not active has no data-quality
 * verdict at all, and must never inherit "Cleared" — a missing asset and a
 * condemned one both rendered a green "Cleared" pill for exactly that reason,
 * because the derivation only ever asked "is it unverified?" and fell through.
 * "Not in service" is the absence of a verdict, said out loud.
 *
 * "Review — no SAP code" (handoff 30) is the second review status, and it is
 * a different KIND of finding from the first. The asset has a tag physically
 * on it, finance has no SAP asset number for it, and no posting to SAP is on
 * its way: the server's `sap.reconciliation_state = "exception"`. Nobody in
 * the field clears it by visiting the asset — it is cleared when finance books
 * it. The wording is for somebody who is not an accountant; the detail page
 * spells the sentence out under Review Flags. Where it ranks against "Review
 * — data quality", and why, is in `deriveStatus` (lib/adapters.ts).
 *
 * Three members were removed with it: "allottee not in nominal roll", "VIN not
 * verifiable" and "possible duplicate". The back end models none of them —
 * there is no nominal-roll check, no VIN field on an asset and no duplicate
 * detection — so they were mock-era values no real record could ever carry,
 * offered in a filter that always answered zero rows.
 */
export type ApprovalStatus =
  | "Cleared"
  | "Review — data quality"
  | "Review — no SAP code"
  | "Not in service";

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

/**
 * The `warranty` block (handoff 34): a fact about a CONTRACT, not about the
 * asset. Nothing here feeds `status`, `lifecycleState`, a pill or a count of
 * working stock — an asset out of warranty is exactly as in service as it was
 * the day before.
 *
 * Every key but `status` is optional and an absent key is an absent fact.
 */
export interface AssetWarranty {
  /** `under_warranty` / `expired` / `none` — the server's verdict, the
   *  model's key (`useEnumLabel("warranty_status")` for the words). `none`
   *  means no expiry is recorded, which is the ordinary case and is never
   *  shown as, or counted with, `expired`. */
  status: string;
  /** The Lagos date the status was judged against. */
  statusAsOf?: string;
  expiry?: string;
  startDate?: string;
  months?: number;
  /** WHO HONOURS IT — the name as recorded, not a link to anything. */
  warrantor?: string;
  /** Certificate or document number, as given. */
  reference?: string;
  /** How the expiry was arrived at, in the server's sentence — "24 months
   *  from 2026-03-12", or that it was entered as a bare date. */
  basis?: string;
}

export interface AssetProvenance {
  /** `nrs.asset.import_source` — the MODEL's key (`vendra`, `sap`, …), and
   *  deliberately `string`: the set is the server's, `/meta/enums` does not
   *  publish it, and so no label map for it exists here. It is printed as
   *  the key it is. */
  importSource?: string;
  importDate?: string;
  importRef?: string;
  grnReference?: string;
  purchaseOrderReference?: string;
  purchaseVendor?: string;
  /** `created_at`, an ISO instant, and `created_by.name`. */
  registeredAt?: string;
  registeredBy?: string;
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
  /**
   * The FM domain — `nrs.asset.domain`, an eight-value Selection
   * (building / plant / plumbing / fleet / security / it / furniture /
   * other). Render its LABEL with `useEnumLabel("domain")`, never the key.
   *
   * This replaced `systemDomain` in handoff 25 (C1). That field was declared
   * here and rendered as "System Domain" on IT assets, but nothing on
   * `nrs.asset` backed it: the adapter quietly filled it from `domain`, so on
   * a live tenant the row read `it` — the raw FM key — for every IT asset,
   * while the mock filled it with network identifiers like "ABJ-HQ-MST-233"
   * and made the page look right in development. A field with no backing
   * column does not get a row.
   */
  fmDomain?: string;
  registrationNo?: string;
  engineNo?: string;
  /**
   * `nrs.asset.condition` — the MODEL's key, verbatim: `new`, `good`, `fair`,
   * `poor`, `decommissioned`. Not a display string, and deliberately not a
   * union.
   *
   * It used to be the four-member union `"Good" | "Fair" | "Poor" |
   * "Decommissioned"`, which is one value short of the set the model owns, and
   * the adapter closed the gap by mapping `new` onto `"Good"`. So an asset
   * stored as `condition=new` was labelled Good in the table and then left out
   * of the results when the user filtered Condition = Good, because that filter
   * sends `condition=good`. 204 assets on `jaizbankplc`, 54 on `nrs19` and 24
   * on `cadra19` were invisible to the register's own Good filter while the
   * same table called them Good. Nothing on screen said so.
   *
   * `string`, not a five-member union, is the point. A compile-time union over
   * a server-owned set is the mechanism that rotted; widening it by one value
   * rebuilds the mechanism a year further from the next change. The set lives
   * in `lib/enums.ts`/`useEnum("condition")`, which reads it from the model at
   * request time, and the label is rendered at the edges with
   * `useEnumLabel("condition")`.
   */
  condition: string;
  /** `nrs.asset.state`, as the model's key. A union here would be a third
   *  opinion about a Selection the server owns — see `condition` above. */
  lifecycleState?: string;
  isVerified?: boolean;
  /** `sap.reconciliation_state`, as the model's key: `not_tagged`, `pending`,
   *  `reconciled` or `exception`. `string` for the reason `condition` is.
   *  Absent on a mock row and on a payload from a server that does not send
   *  the `sap` block — and absent is not "exception". */
  sapReconciliationState?: string;
  /** `sap.asset_number` — finance's half of the dual code. */
  sapAssetNumber?: string;
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
  /** Absent when the server predates handoff 34 and sends no `warranty`
   *  block. Absent is NOT `none`: an older server has not said whether a
   *  warranty is recorded, so the page falls back to `keyDates.warrantyExpiry`
   *  alone and draws no verdict. */
  warranty?: AssetWarranty;
  /** `last_verified_by.name` — WHO verified, which the date cannot say.
   *  Read-only: written only by `POST /assets/<id>/verify`, from the acting
   *  user. Absent means NOBODY IS RECORDED, not that nobody checked — every
   *  verification this app made before handoff 28 was a PATCH of a date and
   *  named no one. The page says so beside the date rather than hiding the
   *  row. */
  verifiedBy?: string;
  /** Where the record came from, as the record says it. Every key is
   *  optional and an absent key is an absent fact: the Provenance tab prints
   *  what is here and nothing else. */
  provenance?: AssetProvenance;
  maintenanceVendor?: string;
  notes?: string;
  pmCount?: number;
  requestCount?: number;
  parentAssetName?: string;
  childCount?: number;
}

/** One tracked field change on a history event. `old`/`new` arrive as the
 *  record holds them — a selection as its LABEL, a many2one as its name — so
 *  they are printed, never looked up. */
export interface AssetHistoryChange {
  label: string;
  old: string | number | boolean | null;
  new: string | number | boolean | null;
}

/** One line of `GET /api/v1/assets/<id>/history`. */
export interface AssetHistoryEvent {
  id: string;
  /** The server's event type. `string`, not a union: the set is the server's
   *  and it is OPEN — a type this build has never heard of still renders,
   *  from `title` and `summary`, which the server supplies for that reason. */
  type: string;
  title: string;
  summary: string;
  /** A bare date (`2026-09-05`) when `atIsDayOnly`, an ISO instant otherwise. */
  at: string;
  atIsDayOnly: boolean;
  /** The name as the record holds it. `null` means the record names NOBODY,
   *  and it stays `null` all the way to the screen — never "System", never a
   *  neighbouring field. Explicitly nullable rather than optional so that
   *  "blank" is a value somebody had to handle. */
  actorName: string | null;
  /** An evidence grade key (`append_only`, `chatter`, …). Also `string`: the
   *  grades and their meanings are published in the same response. */
  evidence: string;
  /** Recovered after the fact from the message log, not recorded when it
   *  happened. Said on the row. */
  reconstructed: boolean;
  /** Custody links and location movements — how the row came to exist
   *  (`api`, `tracking_backfill`, `test`, …). */
  source?: string;
  /** Why, in the words of whoever recorded it — a custody link, a transfer,
   *  or (handoff 30) a change of status: the reason given when an asset was
   *  marked missing or condemned rides on its `status_changed` event. */
  reason?: string;
  transferReference?: string;
  /** A maintenance request's reference (`SR-0042`). Present only for a
   *  sign-in that may read service requests. */
  requestReference?: string;
  /** The server HELD THE REFERENCE BACK from this sign-in. Distinct from a
   *  request that has none, and the row says which. */
  requestReferenceWithheld?: boolean;
  changes?: AssetHistoryChange[];
}

export interface AssetHistory {
  summary: {
    events: number;
    /** 0 means nothing is recorded beyond registration — which the screen
     *  says in the server's words rather than by showing less. */
    eventsAfterRegistration: number;
    reconstructedEvents: number;
    statement: string;
  };
  /** Where the custody record begins, and whether the asset was already held
   *  by somebody the chain never saw arrive. */
  custody: {
    statement: string;
    custodianHeldBeforeFirstLink: boolean;
  };
  /** Where the location record begins — the same question as `custody`,
   *  asked of the append-only movement record. Absent when the server
   *  predates that record; the screen then says nothing about it rather than
   *  guessing. */
  location?: {
    statement: string;
    locatedBeforeFirstMovement: boolean;
  };
  /** From when each KIND of event — a verification, a change of status, a
   *  change to the GRN / PO / SAP number — has a record nobody can alter, in
   *  the server's sentences and the server's order. Before that instant such
   *  an event is a message-log line and is graded as one. Empty from a server
   *  that predates `nrs.asset.event`; the screen then says nothing about it. */
  eventRecording: { event: string; statement: string }[];
  /** Every grade with the server's own sentence about what it is worth, in
   *  the SERVER'S ORDER — strongest first, which is an order a `Record`
   *  would not promise to keep. The legend prints it as sent. */
  evidenceGrades: { grade: string; meaning: string }[];
  /** grade → meaning, derived from the list above, for the pill's tooltip. */
  evidenceMeanings: Record<string, string>;
  notRecorded: { event: string; statement: string }[];
  verification: string;
  events: AssetHistoryEvent[];
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
/**
 * A `fleet.vehicle.fuel_type` KEY, exactly as the model stores it — `diesel`,
 * `gasoline`, `full_hybrid`, `plug_in_hybrid_diesel`, `plug_in_hybrid_gasoline`,
 * `cng`, `lpg`, `hydrogen`, `electric`.
 *
 * This used to be the union `"Petrol" | "Diesel" | "CNG"`: three display
 * strings, none of which was a model key, standing in for nine model values.
 * `mapFuelType` in dataProvider squeezed the nine onto the three with a regex,
 * so `electric`, `lpg`, `full_hybrid` and both plug-in hybrids all reached the
 * screen as **CNG**, and `hydrogen` as **Petrol**. A fleet manager reading the
 * fuel type off that screen was told something untrue about the vehicle.
 *
 * It is deliberately `string` and not a new nine-member union. A compile-time
 * union over a set the SERVER owns is exactly the mechanism that rotted here —
 * the model gains a value, the union does not, and nothing says so. The live
 * set comes from `useEnum("fuel_type")`; the guarded seed is `ENUM_SEED` in
 * `lib/enums.ts`. Render the model's label with `useEnumLabel("fuel_type")` —
 * never the bare key, and never a grouping of our own invention.
 */
export type FuelType = string;

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
