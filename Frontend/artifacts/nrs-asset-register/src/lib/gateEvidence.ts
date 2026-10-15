/**
 * Handoff 60 — the reads that sit beside the receipt gates and belong to no
 * one screen: the per-person Candidates badge, and what IAD saw when it
 * verified a unit.
 *
 * Kept out of `dataProvider.ts` on purpose (it is being edited for the
 * batch gate routes in the same handoff); these are reads only.
 */
import { apiConfigured, apiGet, apiGetRaw } from "./api";

/**
 * How many received units are waiting on an act THIS person may do — the
 * number beside *Candidates* in the sidebar.
 *
 * `waiting_on_me=true` is the server's answer, not a sum this app builds: it
 * counts a unit only when the person holds the scope of the gate it is
 * waiting on AND the no-two-gates rule does not bar them from it, so the
 * badge never counts work they could not do. `limit: 1` and the pagination
 * total — the same cheap count the approvals badge uses.
 *
 * Null, not 0, when the server sends no total: "could not be counted" is a
 * different fact from "nothing waiting", and the sidebar draws nothing for
 * either. With the receipt gates switched off there are no candidates and
 * the server says 0; nothing here special-cases that.
 */
export async function fetchCandidatesWaitingCount(): Promise<number | null> {
  if (!apiConfigured) return null;
  const res = await apiGet<unknown[]>("/api/v1/candidates", {
    waiting_on_me: true, limit: 1,
  });
  return res.pagination?.total_estimate ?? null;
}

/** The query key the badge is cached under. Every place that fires a gate
 *  invalidates THIS key, so the number moves the moment the work does. It is
 *  also excluded from the persisted cache (`App.tsx`): a badge restored from
 *  yesterday's localStorage would be a confident wrong number. */
export const CANDIDATES_BADGE_KEY = ["candidates-badge"] as const;

/** The four things IAD ticks before verifying (`checklist` on the verify
 *  routes). Any of them may be missing on an older record. */
export interface GateChecklist {
  quantity?: boolean;
  specification?: boolean;
  condition?: boolean;
  price?: boolean;
}

export interface GateEvidenceFile {
  id: number;
  name: string;
  mimetype: string | null;
  size: number;
  /** `/api/v1/assets/<id>/evidence/<file id>` — needs the bearer token, so
   *  it is fetched with `apiGetRaw`, never put in an `<a href>`. */
  url: string;
}

export interface GateVerification {
  event_id: number;
  /** UTC, `YYYY-MM-DD HH:MM:SS`, no zone. */
  occurred_at: string | null;
  actor_name: string | null;
  checklist: GateChecklist | null;
  notes: string | null;
  files: GateEvidenceFile[];
}

export interface GateEvidenceAnswer {
  asset_id: number;
  /** Whether the caller holds `evidence:read` (handoff 61, ruling 1 on
   *  report 60). False: `verifications` is empty and `count` is all the
   *  caller is told. */
  readable: boolean;
  /** Evidence files across every verification — given to readers and
   *  non-readers alike. */
  count: number;
  /** Newest first. Empty for a non-reader. */
  verifications: GateVerification[];
}

/** `GET /api/v1/assets/<id>/evidence` (`candidates:read`; the files
 *  themselves to `evidence:read` only, since handoff 61). */
export async function fetchGateEvidence(assetId: string | number): Promise<GateEvidenceAnswer> {
  const res = await apiGet<GateEvidenceAnswer>(
    `/api/v1/assets/${encodeURIComponent(String(assetId))}/evidence`);
  return {
    asset_id: res.data?.asset_id ?? Number(assetId),
    // Absent on a server from before handoff 61, which served the files to
    // every `candidates:read` holder: readable, as it then was.
    readable: res.data?.readable !== false,
    count: typeof res.data?.count === "number" ? res.data.count : 0,
    verifications: Array.isArray(res.data?.verifications) ? res.data.verifications : [],
  };
}

/** Kinds a browser shows in a tab of its own; anything else is saved. */
function opensInTab(mimetype: string | null): boolean {
  if (!mimetype) return false;
  return mimetype.startsWith("image/") || mimetype === "application/pdf"
    || mimetype.startsWith("text/plain");
}

/**
 * Open one evidence file. The app holds a bearer token and no Odoo session,
 * so the file is fetched with the token, turned into a blob and handed to
 * the browser as an object URL: an image or a PDF in a new tab, anything
 * else downloaded under its own name. A refusal throws the server's
 * `CadraApiError`, for the caller to print verbatim.
 *
 * The tab is opened BEFORE the fetch and pointed at the file after it: a
 * window opened after an `await` is no longer the click's, and a pop-up
 * blocker stops it.
 */
export async function openGateEvidenceFile(file: GateEvidenceFile): Promise<void> {
  const inTab = opensInTab(file.mimetype);
  const tab = inTab ? window.open("", "_blank") : null;
  try {
    const res = await apiGetRaw(file.url);
    const raw = await res.blob();
    const type = file.mimetype || res.headers.get("Content-Type") || raw.type
      || "application/octet-stream";
    const blob = raw.type === type ? raw : new Blob([raw], { type });
    const url = URL.createObjectURL(blob);
    // Long enough for the new tab to have read it, then let it go.
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    if (tab) {
      tab.location.href = url;
      return;
    }
    const a = document.createElement("a");
    a.href = url;
    if (inTab) {
      // The pop-up was blocked: open it from a link instead.
      a.target = "_blank";
      a.rel = "noopener";
    } else {
      a.download = file.name || "evidence";
    }
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (e) {
    tab?.close();
    throw e;
  }
}
