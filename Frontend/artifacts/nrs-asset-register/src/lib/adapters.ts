/**
 * Adapters: map Cadra API response shapes -> frontend types.
 *
 * The frontend types were designed before the API existed, so a few fields
 * either aren't in the API yet (NIN, biometrics, access card — sensitive,
 * excluded by serializer) or come from different sources. Where the API
 * has no data we use sensible defaults that the UI already handles.
 */
import type { Employee, EmployeeStatus, EmploymentType } from "../types";

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
