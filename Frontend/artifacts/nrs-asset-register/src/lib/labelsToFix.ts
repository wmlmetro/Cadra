/**
 * "Labels to fix" — the station's list of gated units whose label has been
 * minted (at `request-tagging`) and not yet confirmed on the asset (handoff
 * 60 §2c). It reads the Candidates queue, `waiting_on=tagging`, oldest first,
 * so the tagger prints and fits the units that have waited longest.
 *
 * Its own file because the station is not the Candidates page and the
 * fetcher in `dataProvider.ts` sends neither `sort` nor `limit` choices; the
 * server contract is the same route (`GET /api/v1/candidates`,
 * `candidates:read`), with `sort=oldest` added by handoff 60.
 */

import { apiGet } from "./api";

/** The slice of the asset payload (`serialize_asset`) the panel reads. */
export interface LabelToFixRow {
  id: number;
  asset_code: string;
  name: string;
  /** DEPRECATED on the server (the tag NUMBER); read only as a fallback for
   *  `tagging.tag_number`, which is the label actually on the record. */
  tag?: string | null;
  category: { id: number; name: string } | null;
  current_location: { id: number; name: string } | null;
  floor_room: string | null;
  provenance?: { grn_reference: string | null } | null;
  register_state: string;
  tagging: {
    label_id: number | null;
    tag_number: string | null;
    label_state: string | null;
  } | null;
  gates: { waiting_on: string | null; state_since: string | null } | null;
}

export interface LabelsToFixPage {
  rows: LabelToFixRow[];
  /** The server's count of everything waiting, not just the page shown. */
  totalEstimate: number | null;
  /** Whether there is more than this one page. */
  more: boolean;
}

/** The panel shows one page, the oldest; the rest is on Candidates. */
export const LABELS_TO_FIX_LIMIT = 100;

/** `q` narrows the queue on the server — a GRN, a PO, a name (the
 *  Candidates search). Without it a fresh delivery sits behind any backlog
 *  older than it (found by spec 60: 6 of a new GRN's 20 on screen). */
export async function fetchLabelsToFix(q?: string): Promise<LabelsToFixPage> {
  const res = await apiGet<LabelToFixRow[]>("/api/v1/candidates", {
    waiting_on: "tagging",
    sort: "oldest",
    limit: LABELS_TO_FIX_LIMIT,
    q: q?.trim() || undefined,
  });
  return {
    rows: res.data ?? [],
    totalEstimate: res.pagination?.total_estimate ?? null,
    more: res.pagination?.next_cursor != null,
  };
}

/** The number to print on the label: the label on record, else the asset's
 *  tag field. Null when no label has been minted — nothing to print. */
export function labelNumberOf(r: LabelToFixRow): string | null {
  return r.tagging?.tag_number || r.tag || null;
}

/** "3 h", "2 d" — how long the unit has waited on tagging. The server's
 *  datetimes are UTC with no zone. The same reading as the Candidates
 *  page's ages, which is a page and does not export it. */
export function ageOf(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const t = Date.parse(iso.endsWith("Z") || iso.includes("+") ? iso : iso.replace(" ", "T") + "Z");
  if (Number.isNaN(t)) return "—";
  const mins = Math.max(0, Math.round((now - t) / 60_000));
  if (mins < 60) return `${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}
