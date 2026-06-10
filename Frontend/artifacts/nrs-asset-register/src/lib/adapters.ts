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

export function apiEmployeeToEmployee(e: ApiEmployee): Employee {
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
    title: e.job_title ?? "",
    gradeLevel: parseGradeLevel(e.grade_level),
    employmentType: "Permanent" as EmploymentType, // not on API yet
    status,
    gender: "Male", // not exposed (sensitive)
    phone: e.work_phone ?? "",
    email: e.work_email ?? "",
    nin: undefined, // never exposed by API
    joinDate: e.employment.start_date ?? "",
    avatarColor: avatarColorFor(e.name),
    identityVerified: e.sap.sync_status === "synced",
    biometricEnrolled: false, // not exposed
    accessCardNo: undefined,  // not exposed
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
  const office = a.location_hierarchy.building?.name
    ?? a.current_location?.name
    ?? "";
  const path = a.address_display
    ?? [a.location_hierarchy.building?.name, a.location_hierarchy.floor?.name, a.location_hierarchy.room?.name]
      .filter(Boolean).join(" / ");
  return { zone: "", state: "", office, path };
}

export function apiAssetToAsset(a: ApiAsset): Asset {
  return {
    id: String(a.id),
    name: a.name,
    assetTag: a.tag ?? a.asset_code,
    legacyCode: a.legacy_asset_code ?? "",
    category: bucketCategory(a.category?.name),
    subcategory: a.subcategory?.name ?? "",
    assetType: a.asset_type?.name ?? "",
    manufacturer: a.manufacturer ?? "",
    model: a.model ?? "",
    serial: a.serial_number ?? "",
    systemDomain: a.domain ?? undefined,
    condition: CONDITION_MAP[a.condition] ?? "Good",
    custodianName: a.current_custodian?.name ?? undefined,
    custodianIR: undefined,
    department: a.department ?? "",
    location: buildAssetLocation(a),
    status: deriveStatus(a),
    reviewFlags: a.is_verified ? [] : ["Not yet verified"],
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

export function apiLocationToLocation(l: ApiLocation): FrontLocation {
  return {
    id: String(l.id),
    name: l.name,
    locationType: mapLocationType(l.location_type),
    zoneCode: l.extras.zone_code ?? undefined,
    parent: l.parent_id ? String(l.parent_id) : undefined,
    street: l.address.street ?? undefined,
    street2: l.address.street2 ?? undefined,
    city: l.address.city ?? undefined,
    state: l.address.state?.name ?? undefined,
    country: l.address.country?.name ?? "Nigeria",
    active: l.active,
    childrenCount: l.child_count,
    // child_all_count counts every descendant — used by Locations card view.
    assetCount: undefined, // not on /locations payload; backfilled via /assets count if needed
    childStates: undefined,
    childOffices: undefined,
  };
}
