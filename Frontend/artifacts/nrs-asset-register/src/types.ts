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
  /** `sap.code_source` — how that number got onto the record, as the
   *  model's key (`integration`, `import`, `manual`, `confirmed`,
   *  `linked_from_sap_mirror`). Absent when there is none. */
  sapCodeSource?: string;
  /** `sap.duplicate_flag` (handoff 65 §2): the Register Maker flagged this
   *  asset as one of a group that all point at ONE SAP record — a likely
   *  duplicate. A record for NRS; nothing was merged. Absent: no flag. */
  sapDuplicateFlag?: AssetSapDuplicateFlag;
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

// ─── ADMINISTRATION — who has what (handoff 41) ──────────────────────────────
// Shapes for `GET /api/v1/roles`, `GET /api/v1/users[/<id>]` and
// `GET /api/v1/reports/access-changes`. Handoff 41 wrote nothing back;
// handoff 42 added `POST /users/<id>/roles` (`RoleChange`) and handoff 43 the
// person's lifecycle — `POST /users`, `/invite`, `/deactivate`, `/reactivate`
// — every one of which answers with the same `AdminUser` row as a GET.

/** One of the eight roles the API publishes, in the API's own display order. */
export interface AdminRole {
  key: string;
  name: string;
  xmlid: string;
  scopes: string[];
  description: string | null;
  installed: boolean;
  /** Keys of the roles this one implies — on Odoo 19 implication is computed
   *  at read time and materialises no membership rows. */
  implies: string[];
  /** Whether `POST /users/<id>/roles` may grant or remove this role (handoff
   *  42): exactly four are — asset_user, asset_manager, tag_issuing_unit,
   *  auditor. `system` is never grantable over the API, by ruling. The screen
   *  draws a control for a grantable role only; the rest have none. */
  grantable: boolean;
}

/** `via` is on `roles_effective` only: the account's direct groups (any group, not only roles) that imply this one; empty when held directly. */
export interface AdminRoleRef { key: string; name: string; via?: string[] }

export interface AdminUserCredential {
  id: number;
  name: string;
  client_id: string;
  active: boolean;
  is_test_credential: boolean;
}

/**
 * The `invitation` block on every user row (handoff 43): one of five states,
 * each a sentence somebody can act on. Derived on the model from the stamps
 * `_action_reset_password` writes and the partner's live sign-up token:
 *
 *   never        no invitation has ever been sent
 *   outstanding  sent, the link still valid, not yet used
 *   expired      sent, the link past its validity, not used — send it again
 *   redeemed     sent, and the person has since set a password and signed in
 *   cancelled    sent, then voided without being used (a deactivation cancels
 *                the token; reactivating does NOT re-send it)
 *
 * `sent_at` and `expires_at` are naive UTC `isoformat()` strings like
 * `last_login_at`; `sends` counts every send, re-sends included.
 */
export interface AdminUserInvitation {
  state: "never" | "outstanding" | "expired" | "redeemed" | "cancelled";
  sent_at: string | null;
  sent_by: { id: number; name: string } | null;
  sends: number;
  expires_at: string | null;
}

export interface AdminUser {
  id: number;
  name: string;
  login: string;
  email: string | null;
  active: boolean;
  kind: "person" | "api_credential";
  api_client: AdminUserCredential | null;
  /** The roles somebody actually granted — what handoff 42 will act on. */
  roles_direct: AdminRoleRef[];
  /** Direct roles plus everything they imply. */
  roles_effective: AdminRoleRef[];
  scopes: string[];
  scopes_source: "roles" | "credential";
  last_login_at: string | null;
  created_at: string;
  /** Handoff 43. Always present; `state: "never"` for an account nobody has
   *  invited, a credential's user included. */
  invitation: AdminUserInvitation;
  /** Handoff 46, additive. True for an account a test or a demo seed
   *  created (the same derived self-label as handoff 26's fixtures); absent
   *  from an older server, which reads as "not said", not as false. */
  is_test_fixture?: boolean;
}

/** One row of `data.events` on the access-changes report. The first six
 *  keys are on every event; `group`/`attributable` only on the events read
 *  from the forward record — the two membership events (`granted`/`removed`)
 *  and, since handoff 45, an account switched off or on
 *  (`deactivated`/`reactivated`), whose `group` is `null`. */
export interface AccessChangeEvent {
  event: "account_created" | "account_modified" | "granted" | "removed"
    | "deactivated" | "reactivated" | string;
  precision: "exact" | "last_write_only" | string;
  at: string;
  actor: { id: number | null; name: string } | null;
  user_id: number;
  login: string;
  evidence: string;
  groups_now: string[];
  group?: string | null;
  attributable?: boolean;
}

export interface AccessChangeRosterRow {
  user_id: number;
  login: string;
  name: string;
  active: boolean;
  is_api_client: boolean;
  api_scopes: string[];
  groups: string[];
  created_at: string | null;
  created_by: { id: number; name: string } | null;
  last_modified_at: string | null;
  last_modified_by: { id: number; name: string } | null;
}

export interface AccessChangeSummary {
  accounts: number;
  accounts_active: number;
  events_in_period: number;
  group_changes_in_period: number;
  implication_changes_in_period: number;
  group_changes_not_shown: number;
  /** Handoff 45: deactivations and reactivations — their own count, never in
   *  the group or implication counts, and their own boundary. */
  account_state_changes_in_period: number;
  account_state_changes_not_shown: number;
  account_state_coverage: string;
  coverage: string;
  statement: string;
}

export interface AccessChangeFidelity {
  recoverable: string[];
  not_recoverable: string[];
  groups_field: string | null;
  groups_field_tracked: boolean;
  membership_audit_columns: string[];
  tracking_rows: number;
  logging_rows: number;
  record_starts_at: string | null;
  record_rows: number;
  /** When deactivations/reactivations began to be recorded here (handoff
   *  45) — the earliest such row, `null` until the first. */
  account_state_record_starts_at: string | null;
  account_state_record_rows: number;
  notes: Record<string, string>;
}

export interface AccessChangeReport {
  period: { date_from: string; date_to: string; inclusive: string };
  summary: AccessChangeSummary;
  fidelity: AccessChangeFidelity;
  events: AccessChangeEvent[];
  roster: AccessChangeRosterRow[];
}

// ─── ADMINISTRATION — the grant, and the refusal (handoff 42) ────────────────

/**
 * `data` of `POST /api/v1/users/<id>/roles`, for a dry run and for the real
 * thing alike — the only difference is `applied`. `roles` sent is the FULL
 * desired set of DIRECT roles among the grantable ones; whatever the account
 * holds outside those four is left as it is. `before`/`after` carry the two
 * lists the user row carries, because direct and effective are different
 * questions on Odoo 19 and a grant of Asset Manager silently confers Asset
 * User. `granted`/`revoked` are role keys.
 */
export interface RoleChange {
  user: AdminUser;
  before: { roles_direct: AdminRoleRef[]; roles_effective: AdminRoleRef[] };
  after: { roles_direct: AdminRoleRef[]; roles_effective: AdminRoleRef[] };
  granted: string[];
  revoked: string[];
  applied: boolean;
}

// ─── AUDIT — the auditor's own screens (handoff 49) ──────────────────────────

/** One parameter row of the configuration-changes report. The report is
 *  last-write-only by its own admission: `ir.config_parameter` keeps no
 *  history, so a key changed five times is one row showing the fifth.
 *  `current_value` is `[redacted] sha256:…` when the KEY names a credential. */
export interface ConfigurationChangeRow {
  id: number;
  key: string;
  current_value: string;
  value_is_redacted: boolean;
  changed_after_create: boolean;
  created_at: string | null;
  created_by: { id: number; name: string } | null;
  last_written_at: string | null;
  last_written_by: { id: number; name: string } | null;
  evidence: string;
  precision: "last_write_only" | string;
}

export interface ConfigurationChangeSummary {
  parameters_in_period: number;
  modified_after_create: number;
  modified_by_a_named_user: number;
  modified_by_system: number;
  redacted_values: number;
  coverage: string;
  statement: string;
}

export interface ConfigurationChangeReport {
  period: { date_from: string; date_to: string; inclusive: string };
  summary: ConfigurationChangeSummary;
  fidelity: {
    recoverable: string[];
    not_recoverable: string[];
    tracked: boolean;
    tracking_rows: number;
    transient_settings_rows: number;
    notes: Record<string, string>;
  };
  parameters: ConfigurationChangeRow[];
}

/** One disposal on the disposals report. `findings` names what the record
 *  LACKS (`no_approver`, `no_disposal_method`, …) — an empty list is a clean
 *  record. A row whose `disposal_date` the register never held is in
 *  `unplaceable`, not `rows`, and `date_source` says where a date came from. */
export interface DisposalReportRow {
  asset_id: number;
  name: string | null;
  asset_code: string | null;
  sap_asset_number: string | null;
  disposal_date: string | null;
  date_source: "recorded" | "reconstructed" | "state_transition" | "none" | string;
  disposal_method: string | null;
  sap_disposal_type: string | null;
  disposal_reference: string | null;
  approved_by_id: number | null;
  approved_by: string | null;
  approved_at: string | null;
  proceeds: number;
  currency: string | null;
  disposal_reason: string | null;
  condition_at_disposal: string | null;
  findings: string[];
}

export interface DisposalReportSummary {
  total: number;
  unplaceable: number;
  clean: number;
  findings: Record<string, number>;
  sap_coverage: {
    total: number;
    with_sap_asset_number: number;
    without_sap_asset_number: number;
    coverage: string;
    statement: string;
  };
  by_method: Record<string, number>;
  proceeds_by_currency: Record<string, number>;
}

export interface DisposalReport {
  period: { date_from: string; date_to: string; inclusive: string };
  summary: DisposalReportSummary;
  /** Disposed assets with NO disposal date from any source — they belong to
   *  every period and to none, so they ride on every page, never cut by the
   *  cursor. */
  unplaceable: DisposalReportRow[];
  rows: DisposalReportRow[];
}

/** One asset on the register snapshot. The server rolls 35 fields back to
 *  `as_of` and says per-row (`_fidelity`) which of them it could not place;
 *  the full field list is long and this screen shows a column selection, so
 *  the row type names what the screen reads and leaves the rest indexed. */
export interface AssetSnapshotRow {
  id: number;
  name: string | null;
  asset_code: string | null;
  active_tag_number: string | null;
  category_id: { id: number; name: string } | null;
  location_id: { id: number; name: string } | null;
  custodian_id: { id: number; name: string } | null;
  department: string | null;
  serial_number: string | null;
  state: string | null;
  condition: string | null;
  retrieval_flag: boolean;
  last_verified_date: string | null;
  sap_asset_number: string | null;
  /** Nulls are values the depreciation engine has not computed — not zeros. */
  value: { accumulated_depreciation: number | null; book_value: number | null; state: string } | null;
  /** Which of this row's fields the snapshot could NOT place on `as_of`
   *  (`unknown`) or could only give today's value for. Absent when clean. */
  _fidelity?: Record<string, string[]>;
  _changed_since?: string[];
  [key: string]: unknown;
}

export interface AssetRegisterSnapshot {
  as_of: string;
  cutoff: string;
  cutoff_timezone: string;
  fidelity: {
    rolled_back: string[];
    as_of_today: string[];
    not_recoverable: string[];
    tracked_from: { fields: string[]; since: string | null };
    notes: Record<string, string>;
  };
  filters: {
    query_parameters_supplied: string[];
    evaluated_as_of: string;
    note: string;
  };
  omitted_asset_ids: number[];
  assets: AssetSnapshotRow[];
}

/** `sap.duplicate_flag` on an asset (handoff 65 §2), as the server sends it. */
export interface AssetSapDuplicateFlag {
  sapAssetNumber?: string;
  note?: string;
  flaggedBy?: string;
  flaggedAt?: string;
}
