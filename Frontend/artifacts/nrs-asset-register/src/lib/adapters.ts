/**
 * Adapters: map Cadra API response shapes -> frontend types.
 *
 * The frontend types were designed before the API existed, so a few fields
 * either aren't in the API yet (NIN, biometrics, access card — sensitive,
 * excluded by serializer) or come from different sources. Where the API
 * has no data we use sensible defaults that the UI already handles.
 */
import type {
  Employee, EmployeeStatus, EmploymentType,
  Asset, AssetLocation, Location as FrontLocation, ApprovalStatus,
  ServiceRequest, RequestPriority, RequestKanbanState, RequestStageRoute, RequestMessage,
  AssetDepreciation, DepreciationMethod, DepreciationState, DepreciationStartSource,
} from "../types";

// ─── API shape (from myservice_api/controllers/v1_identity.py:serialize_employee)
export interface ApiEmployee {
  id: number;
  ir_number: string | null;
  name: string;
  work_email: string | null;
  work_phone: string | null;
  job_title: string | null;
  department: { id: number; name: string } | null;
  grade_level: string | null;     // e.g. "GL 14"
  cost_centre: string | null;
  sap: {
    user_id: string | null;
    status: string | null;        // active|suspended|on_leave|transferred|exited
    department: string | null;
    manager_ir_number: string | null;
    last_sync: string | null;
    sync_status: string | null;
  };
  location: { id: number; name: string } | null;
  employment: {
    start_date: string | null;
    end_date: string | null;
  };
  assets: {
    count: number;
    has_pending_retrieval: boolean;
  };
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
  manager?: { id: number | null; ir_number: string | null; name: string | null } | null;
}

// ─── helpers ─────────────────────────────────────────────────────────

const SAP_TO_FRONTEND_STATUS: Record<string, EmployeeStatus> = {
  active: "Active",
  on_leave: "On Leave",
  suspended: "Suspended",
  transferred: "Active",
  exited: "Inactive",
};

// Deterministic avatar color from name (no random — same name -> same color).
const AVATAR_PALETTE = [
  "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
  "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
];

function avatarColorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(h) % AVATAR_PALETTE.length];
}

function parseGradeLevel(gl: string | null): number {
  if (!gl) return 0;
  const m = gl.match(/\d+/);
  return m ? Number(m[0]) : 0;
}

// ─── adapter ─────────────────────────────────────────────────────────

// Manager block is only present on single-employee GETs (include_manager=true);
// list responses omit it to avoid N+1.
interface ApiEmployeeExtras {
  manager?: { id: number | null; ir_number: string | null; name: string | null } | null;
  assets?: { count?: number; has_pending_retrieval?: boolean };
}

export function apiEmployeeToEmployee(e: ApiEmployee & ApiEmployeeExtras): Employee {
  const status: EmployeeStatus = e.active
    ? (SAP_TO_FRONTEND_STATUS[e.sap.status ?? ""] ?? "Active")
    : "Inactive";

  return {
    id: String(e.id),
    name: e.name,
    irNumber: e.ir_number ?? `#${e.id}`,
    department: e.department?.name ?? e.sap.department ?? "—",
    // API doesn't break out zone separately yet — derive nothing rather than guess.
    zone: "",
    office: e.location?.name ?? "",
    officeId: e.location?.id ?? undefined,
    title: e.job_title ?? "",
    gradeLevel: parseGradeLevel(e.grade_level),
    gradeLevelRaw: e.grade_level ?? undefined,
    costCentre: e.cost_centre ?? undefined,
    employmentType: "Permanent" as EmploymentType, // not on API yet
    status,
    gender: "Male", // not exposed (sensitive)
    phone: e.work_phone ?? "",
    email: e.work_email ?? "",
    nin: undefined, // never exposed by API
    joinDate: e.employment.start_date ?? "",
    employmentEndDate: e.employment.end_date ?? undefined,
    avatarColor: avatarColorFor(e.name),
    identityVerified: e.sap.sync_status === "synced",
    biometricEnrolled: false, // not exposed
    accessCardNo: undefined,  // not exposed
    manager: e.manager ? {
      id: e.manager.id ?? undefined,
      irNumber: e.manager.ir_number ?? undefined,
      name: e.manager.name ?? undefined,
    } : undefined,
    sap: {
      userId:     e.sap.user_id ?? undefined,
      status:     e.sap.status ?? undefined,
      syncStatus: e.sap.sync_status ?? undefined,
      lastSync:   e.sap.last_sync ?? undefined,
      managerIr:  e.sap.manager_ir_number ?? undefined,
    },
    custodialAssetCount: e.assets?.count,
    hasPendingRetrieval: e.assets?.has_pending_retrieval,
  };
}


// ─── ASSET ───────────────────────────────────────────────────────────

export interface ApiRef { id: number; name: string }

export interface ApiAsset {
  id: number;
  asset_code: string;
  tag: string | null;
  legacy_asset_code: string | null;
  name: string;
  serial_number: string | null;
  make: string | null;
  model: string | null;
  manufacturer: string | null;
  category: ApiRef | null;
  subcategory: ApiRef | null;
  asset_type: ApiRef | null;
  asset_level: string | null;
  domain: string | null;
  parent_asset: ApiRef | null;
  child_count: number;
  current_location: ApiRef | null;
  location_hierarchy: {
    building: ApiRef | null;
    floor: ApiRef | null;
    room: ApiRef | null;
  };
  floor_room: string | null;
  address_display: string | null;
  coordinates: { latitude_display: string | null; longitude_display: string | null } | null;
  current_custodian: ApiRef | null;
  department: string | null;
  condition: "new" | "good" | "fair" | "poor" | "damaged";
  state: "active" | "in_repair" | "disposed" | "transferred" | "missing";
  is_verified: boolean;
  notes: string | null;
}

// The frontend's category enum has 3 buckets; the API has many real
// categories. Map by keyword; everything else falls into Furniture as the
// catch-all. Lossy on purpose — see TODO in commit body.
function bucketCategory(name: string | null | undefined): Asset["category"] {
  const n = (name ?? "").toLowerCase();
  if (/it|laptop|computer|server|network|monitor|printer|phone|tablet|ict/.test(n)) return "IT Equipment";
  if (/vehicle|fleet|car|bus|truck|van|suv|sedan/.test(n)) return "Fleet / Vehicles";
  return "Furniture & Fittings";
}

const CONDITION_MAP: Record<ApiAsset["condition"], Asset["condition"]> = {
  new: "Good", good: "Good", fair: "Fair", poor: "Poor", damaged: "Faulty",
};

// Backend `state` is lifecycle; frontend `status` is data-quality review queue.
// Active+verified = Cleared; active+unverified is the only "review" we can
// derive from current API data.
function deriveStatus(a: ApiAsset): ApprovalStatus {
  if (a.state === "active" && !a.is_verified) return "Review — data quality";
  return "Cleared";
}

function buildAssetLocation(a: ApiAsset): AssetLocation {
  // location_hierarchy can be absent for some payloads (e.g. locations with no
  // building ancestry) — guard it so mapping never throws.
  const lh = a.location_hierarchy ?? { building: null, floor: null, room: null };
  const office = lh.building?.name
    ?? a.current_location?.name
    ?? "";
  const path = a.address_display
    ?? [lh.building?.name, lh.floor?.name, lh.room?.name]
      .filter(Boolean).join(" / ");
  // Prefer the most specific location id available (room > floor > building >
  // current_location). The asset detail page uses this for the clickable link;
  // the FK pickers in the edit form still consume them individually.
  const locationId =
    lh.room?.id
    ?? lh.floor?.id
    ?? lh.building?.id
    ?? a.current_location?.id
    ?? undefined;
  return {
    zone: "", state: "", office, path,
    locationId: locationId ?? undefined,
    buildingId: lh.building?.id ?? undefined,
    floorId:    lh.floor?.id ?? undefined,
    roomId:     lh.room?.id ?? undefined,
  };
}

/** The `financial.depreciation` block (PRD §8.6). Mirrors
 *  `_serialize_depreciation` in myservice_api/controllers/v1_assets.py. */
export interface ApiAssetDepreciation {
  method: DepreciationMethod;
  useful_life_months: number | null;
  declining_rate: number | null;
  salvage_value: number | null;
  depreciable_cost: number | null;
  start_date: string | null;
  start_date_source: DepreciationStartSource | null;
  start_date_is_estimated: boolean;
  accumulated_depreciation: number | null;
  current_book_value: number | null;
  state: DepreciationState;
  end_date: string | null;
  uses_category_policy: boolean;
}

// Extra ApiAsset fields the serializer surfaces but my initial adapter dropped.
// Kept on a separate type so the original list payload (which omits them) still
// satisfies ApiAsset.
interface ApiAssetExtras {
  financial?: {
    currency: ApiRef | null;
    purchase_value: number | null;
    replacement_cost: number | null;
    acquisition_cost: number | null;
    current_value: number | null;
    depreciation?: ApiAssetDepreciation;
  };
  dates?: {
    purchase_date: string | null;
    warranty_expiry: string | null;
    acquisition_date: string | null;
    disposal_date: string | null;
    last_verified_date: string | null;
    next_service_date: string | null;
  };
  maintenance_vendor?: ApiRef | null;
  notes?: string | null;
  pm_count?: number;
  request_count?: number;
}

export function apiDepreciationToDepreciation(
  d: ApiAssetDepreciation | undefined,
): AssetDepreciation | undefined {
  if (!d) return undefined;
  const n = (v: number | null) => (typeof v === "number" ? v : undefined);
  return {
    method: d.method,
    usefulLifeMonths: n(d.useful_life_months),
    decliningRate: n(d.declining_rate),
    salvageValue: n(d.salvage_value),
    depreciableCost: n(d.depreciable_cost),
    startDate: d.start_date ?? undefined,
    startDateSource: d.start_date_source ?? undefined,
    startDateIsEstimated: !!d.start_date_is_estimated,
    accumulatedDepreciation: n(d.accumulated_depreciation),
    currentBookValue: n(d.current_book_value),
    state: d.state,
    endDate: d.end_date ?? undefined,
    usesCategoryPolicy: !!d.uses_category_policy,
  };
}

export function apiAssetToAsset(a: ApiAsset & ApiAssetExtras): Asset {
  const f = a.financial;
  const d = a.dates;
  const num = (v: number | null | undefined) => (typeof v === "number" ? v : undefined);
  const str = (v: string | null | undefined) => (v ? v : undefined);
  return {
    id: String(a.id),
    name: a.name,
    assetTag: a.tag ?? a.asset_code,
    assetCode: a.asset_code,
    legacyCode: a.legacy_asset_code ?? "",
    category: bucketCategory(a.category?.name),
    subcategory: a.subcategory?.name ?? "",
    assetType: a.asset_type?.name ?? "",
    manufacturer: a.manufacturer ?? "",
    model: a.model ?? "",
    serial: a.serial_number ?? "",
    systemDomain: a.domain ?? undefined,
    condition: CONDITION_MAP[a.condition] ?? "Good",
    lifecycleState: a.state,
    isVerified: a.is_verified,
    custodianId: a.current_custodian?.id ?? undefined,
    custodianName: a.current_custodian?.name ?? undefined,
    custodianIR: undefined,
    department: a.department ?? "",
    location: buildAssetLocation(a),
    status: deriveStatus(a),
    reviewFlags: a.is_verified ? [] : ["Not yet verified"],
    parentAssetId:   a.parent_asset?.id ?? undefined,
    parentAssetName: a.parent_asset?.name,
    childCount: a.child_count || undefined,
    financials: (f && (f.currency || f.purchase_value || f.replacement_cost || f.acquisition_cost || f.current_value || f.depreciation)) ? {
      currency: f.currency?.name,
      purchaseValue:    num(f.purchase_value),
      replacementCost:  num(f.replacement_cost),
      acquisitionCost:  num(f.acquisition_cost),
      currentValue:     num(f.current_value),
      depreciation:     apiDepreciationToDepreciation(f.depreciation),
    } : undefined,
    keyDates: d ? {
      purchaseDate:     str(d.purchase_date),
      warrantyExpiry:   str(d.warranty_expiry),
      acquisitionDate:  str(d.acquisition_date),
      disposalDate:     str(d.disposal_date),
      lastVerifiedDate: str(d.last_verified_date),
      nextServiceDate:  str(d.next_service_date),
    } : undefined,
    maintenanceVendor: a.maintenance_vendor?.name,
    notes: a.notes ?? undefined,
    pmCount:      a.pm_count,
    requestCount: a.request_count,
  };
}


// ─── LOCATION ────────────────────────────────────────────────────────

type FrontLocationType = NonNullable<FrontLocation["locationType"]>;

export interface ApiLocation {
  id: number;
  name: string;
  type: ApiRef | null;
  location_type: string | null;  // e.g. "zone", "state", "office", "floor", "room"
  description: string | null;
  parent_id: number | null;
  parent_path: string | null;
  active: boolean;
  address: {
    street: string | null;
    street2: string | null;
    zip: string | null;
    city: string | null;
    state: ApiRef | null;
    country: ApiRef | null;
  };
  extras: { zone_code: string | null; floor_number: number | null; building_id: number | null };
  child_count: number;
  child_all_count: number;
}

function mapLocationType(t: string | null): FrontLocationType | undefined {
  if (!t) return undefined;
  const k = t.toLowerCase();
  if (k.includes("zone")) return "Zone";
  if (k.includes("state")) return "State";
  if (k.includes("office") || k.includes("building")) return "Office";
  if (k.includes("floor")) return "Floor";
  if (k.includes("room")) return "Room";
  return undefined;
}

interface ApiLocationCoords {
  coordinates?: { latitude: number | null; longitude: number | null } | null;
}

// Extra ApiLocation fields the serializer surfaces but the list-time payload
// often omits. Kept separate so list rows still satisfy ApiLocation.
interface ApiLocationExtras {
  updated_at?: string | null;
}

export function apiLocationToLocation(l: ApiLocation & ApiLocationCoords & ApiLocationExtras): FrontLocation {
  const lat = l.coordinates?.latitude;
  const lng = l.coordinates?.longitude;
  return {
    id: String(l.id),
    name: l.name,
    description: l.description ?? undefined,
    locationType: mapLocationType(l.location_type),
    zoneCode: l.extras.zone_code ?? undefined,
    parent: l.parent_id ? String(l.parent_id) : undefined,
    street: l.address.street ?? undefined,
    street2: l.address.street2 ?? undefined,
    city: l.address.city ?? undefined,
    state: l.address.state?.name ?? undefined,
    country: l.address.country?.name ?? "Nigeria",
    zip: l.address.zip ?? undefined,
    floorNumber: l.extras.floor_number ?? undefined,
    active: l.active,
    childrenCount: l.child_count,
    childAllCount: l.child_all_count,
    assetCount: undefined,
    childStates: undefined,
    childOffices: undefined,
    coordinates: (typeof lat === "number" && typeof lng === "number") ? { lat, lng } : undefined,
    updatedAt: l.updated_at ?? undefined,
  };
}


// ─── SERVICE REQUEST ─────────────────────────────────────────────────────

export interface ApiRequestStage {
  id: number;
  name: string;
  code: string | null;
  type_code: string | null;
  closed: boolean;
}

export interface ApiRequest {
  id: number;
  reference: string;
  type: ApiRef | null;
  category: ApiRef | null;
  stage: ApiRequestStage;
  kanban_state: RequestKanbanState;
  priority: string;
  impact: string | null;
  urgency: string | null;
  active: boolean;
  subject: string;
  request_text: string;
  response_text: string | null;
  author: ApiRef | null;
  assignee: ApiRef | null;
  partner: ApiRef | null;
  service: ApiRef | null;
  parent_id: number | null;
  tags: ApiRef[];
  deadline_date: string | null;
  dates: {
    created: string | null;
    assigned: string | null;
    moved: string | null;
    closed: string | null;
  };
  location: ApiRef | null;
  vehicle: ApiRef | null;
  asset: ApiRef | null;
  created_at: string;
  updated_at: string;
  routes?: Array<{ id: number; name: string; stage_to: ApiRef }>;
  messages?: Array<{
    id: number; date: string;
    author: ApiRef | null;
    subject: string | null;
    body_html: string | null;
    is_internal?: boolean;
  }>;
}

export function apiRequestToRequest(r: ApiRequest): ServiceRequest {
  const routes: RequestStageRoute[] | undefined = r.routes?.map(rt => ({
    id: rt.id,
    name: rt.name,
    to_stage_id: rt.stage_to.id,
    to_stage_name: rt.stage_to.name,
  }));
  const messages: RequestMessage[] | undefined = r.messages?.map(m => ({
    id: m.id,
    date: m.date,
    author: m.author,
    subject: m.subject,
    body_html: m.body_html,
    is_internal: m.is_internal,
  }));
  return {
    id: String(r.id),
    reference: r.reference,
    typeName: r.type?.name ?? "—",
    typeId: r.type?.id ?? null,
    categoryName: r.category?.name ?? null,
    categoryId: r.category?.id ?? null,
    stageName: r.stage.name,
    stageId: r.stage.id,
    stageCode: r.stage.code,
    stageClosed: r.stage.closed,
    kanbanState: r.kanban_state,
    priority: (r.priority as RequestPriority) ?? "2",
    impact: r.impact,
    urgency: r.urgency,
    subject: r.subject,
    requestText: r.request_text,
    responseText: r.response_text,
    author: r.author,
    assignee: r.assignee,
    partner: r.partner,
    service: r.service,
    parentId: r.parent_id,
    tags: r.tags ?? [],
    deadline: r.deadline_date,
    createdAt: r.dates?.created ?? r.created_at,
    updatedAt: r.updated_at,
    assignedAt: r.dates?.assigned ?? undefined,
    movedAt:    r.dates?.moved ?? undefined,
    closedAt:   r.dates?.closed ?? undefined,
    location: r.location,
    asset:    r.asset,
    vehicle:  r.vehicle,
    routes,
    messages,
  };
}
