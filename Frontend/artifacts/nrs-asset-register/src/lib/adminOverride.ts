/**
 * The administrator override (handoff 70) — one tenant switch,
 * `cadra.admin_override`, under which a system administrator may act at a
 * step a two-person rule would otherwise keep them from: fire every receipt
 * gate, decide a SAP link, capture in any open campaign and review any
 * capture, their own included. The rules on WHAT is true (the affix check,
 * the device, the code, the five-day window) are not lifted.
 *
 * The server decides every act. What the app does with this is draw: a
 * button the override made firable says so ("Approve (as administrator)"),
 * and the audit dropdowns list every open campaign rather than only those
 * naming the person. With the switch off, or for anybody who is not an
 * administrator, nothing here changes any page.
 */
import { apiGet, apiPatch, apiConfigured } from "@/lib/api";

export interface AdminOverrideSetting {
  enabled: boolean;
  configured: boolean;
  default_when_unset: false;
  parameter: string;
  /** What the switch does, in the server's words — shown verbatim. */
  statement: string;
  /** When it was switched on, while it is on; null when off. */
  since: string | null;
  changed_by: { id: number; name: string } | null;
  changed_at: string | null;
}

/** Its own first key segment, so `App.tsx` can keep it out of the
 *  persisted cache: whether an administrator may act alone is a question
 *  about NOW, like `whoami`. */
export const ADMIN_OVERRIDE_KEY = ["admin-override"] as const;
export const ADMIN_OVERRIDES_REPORT_KEY = ["admin-overrides"] as const;

/** The block from `GET /api/v1/settings`; null when the server does not
 *  publish it (an older server), which the app reads as off. */
export async function fetchAdminOverride(): Promise<AdminOverrideSetting | null> {
  const res = await apiGet<{ admin_override?: AdminOverrideSetting }>("/api/v1/settings");
  return res.data?.admin_override ?? null;
}

/** `admin` only on the server — a `settings:write` holder is refused. */
export async function updateAdminOverride(enabled: boolean): Promise<AdminOverrideSetting> {
  return (await apiPatch<AdminOverrideSetting>("/api/v1/settings/admin-override", { enabled })).data;
}

// ── the report ───────────────────────────────────────────────────────────

export type AdminOverrideKind = "gate" | "audit";

export interface AdminOverrideRow {
  /** Lagos time, with its offset. */
  at: string;
  kind: AdminOverrideKind;
  act: string;
  act_words: string;
  by: { id: number | null; name: string } | null;
  asset: { id: number; asset_code: string } | null;
  capture: {
    id: number; capture_id: string;
    campaign: { id: number; name: string };
    room: { id: number; name: string };
  } | null;
  /** Codes of the audit rules lifted (`not_a_capturer`, `own_capture`,
   *  `not_a_reviewer`); empty for a gate. */
  rules: string[];
  /** What the rule would have said, in words. */
  override_of: string;
}

export interface AdminOverridesFilter {
  since?: string;
  until?: string;
  kind?: AdminOverrideKind;
}

export interface AdminOverridesPage {
  rows: AdminOverrideRow[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

/** One page of `GET /reports/admin-overrides`, newest first. `since` and
 *  `until` are Lagos days, both inclusive. */
export async function fetchAdminOverrides(
  filter: AdminOverridesFilter,
  cursor?: string,
  limit = 100,
): Promise<AdminOverridesPage> {
  if (!apiConfigured) throw new Error("No active session");
  const res = await apiGet<AdminOverrideRow[]>("/api/v1/reports/admin-overrides", {
    since: filter.since, until: filter.until, kind: filter.kind, limit, cursor,
  });
  return {
    rows: res.data ?? [],
    nextCursor: res.pagination?.next_cursor ?? null,
    totalEstimate: res.pagination?.total_estimate ?? null,
  };
}

/** Every page for the filter, in the server's order — for the CSV. */
export async function fetchAllAdminOverrides(filter: AdminOverridesFilter): Promise<AdminOverrideRow[]> {
  const out: AdminOverrideRow[] = [];
  let cursor: string | undefined;
  // A cursor that does not move would loop for ever; the server's never
  // repeats, and this stops if one ever did.
  const seen = new Set<string>();
  for (;;) {
    const page = await fetchAdminOverrides(filter, cursor, 200);
    out.push(...page.rows);
    if (!page.nextCursor || seen.has(page.nextCursor)) break;
    seen.add(page.nextCursor);
    cursor = page.nextCursor;
  }
  return out;
}

export const KIND_WORDS: Record<AdminOverrideKind, string> = {
  gate: "Receipt gate",
  audit: "Audit",
};

/** `2026-10-20T14:05:00+01:00` → `20 Oct 2026, 14:05` — the Lagos clock
 *  the server already put on it, never the viewer's zone. */
export function lagosWhen(at: string | null | undefined): string {
  if (!at) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(at);
  if (!m) return at;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]} ${m[1]}, ${m[4]}:${m[5]}`;
}

/** A UTC instant (the settings block's `since`, naive or zoned) on the Lagos
 *  clock: Lagos is UTC+1 all year, no daylight saving. */
export function utcToLagosWhen(at: string | null | undefined): string {
  if (!at) return "—";
  const iso = at.replace(" ", "T");
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const t = Date.parse(zoned);
  if (Number.isNaN(t)) return at;
  return lagosWhen(new Date(t + 3600_000).toISOString().replace("Z", "+01:00"));
}

const CSV_HEADER = ["When (Lagos)", "Who", "Kind", "Act", "Asset", "Capture", "Campaign", "Room", "Rule lifted"];

function csvCell(v: string): string {
  return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

/** The table's columns, one row per act. */
export function adminOverridesCsv(rows: AdminOverrideRow[]): string {
  const lines = [CSV_HEADER.join(",")];
  for (const r of rows) {
    lines.push([
      lagosWhen(r.at), r.by?.name ?? "", KIND_WORDS[r.kind] ?? r.kind, r.act_words || r.act,
      r.asset?.asset_code ?? "", r.capture?.capture_id ?? "", r.capture?.campaign.name ?? "",
      r.capture?.room.name ?? "", r.override_of,
    ].map(csvCell).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}
