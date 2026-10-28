/**
 * Link to SAP (handoff 65) — the wire types and calls behind
 * `pages/SapLinks.tsx`.
 *
 * A link puts SAP's asset number, read from the SAP mirror (SAP's own
 * export), onto a Cadra asset that is already on the register. It changes
 * what Cadra tells SAP later, so it is maker-checker: a Register Maker
 * proposes (`register:make`), a Register Checker approves or returns
 * (`register:check`), and the server refuses one person doing both on one
 * asset. Nothing is sent to SAP by a link. The lists are `sap_mirror:read`.
 *
 * Mirrors `myservice_api/controllers/v1_sap_links.py`; the server decides
 * everything, and every refusal here is the server's sentence.
 */
import { apiGet, apiPost, type CadraPagination } from "@/lib/api";

/** A batch takes at most this many (the server's `BATCH_MAX`). */
export const SAP_LINK_BATCH_MAX = 100;

/** Every query on the page lives under this prefix, so one invalidation
 *  refreshes the three tabs. Not restored from the persisted cache
 *  (`App.tsx`): it is a queue somebody decides from. */
export const SAP_LINKS_KEY = ["sap-links"] as const;

export interface SapUserRef { id: number | null; name: string }

export interface SapLinkAssetBrief {
  id: number;
  asset_code: string | null;
  name: string | null;
  location: { id: number; name: string } | null;
}

export interface SapRecordBrief {
  id: number;
  asset_number: string;
  sub_number: string | null;
  class: string | null;
  description: string | null;
  description_2: string | null;
  old_tag: string | null;
  serial_number: string | null;
  office_code: string | null;
  capitalized_on: string | null;
}

export type SapLinkKind = "link" | "unlink";
export type SapLinkState = "proposed" | "approved" | "returned";

export interface SapLink {
  id: number;
  kind: SapLinkKind;
  state: SapLinkState;
  asset: SapLinkAssetBrief;
  sap: SapRecordBrief;
  sap_asset_number: string | null;
  reason_code: string | null;
  reason: string | null;
  note: string | null;
  proposed_by: SapUserRef | null;
  proposed_at: string | null;
  decided_by: SapUserRef | null;
  decided_at: string | null;
  return_reason: string | null;
  /** The caller holds `register:check` and the no-two-gates rule does not
   *  bar them. */
  can_decide: boolean;
  /** Handoff 70: `can_decide` is true only because the caller is an
   *  administrator under the tenant's override. */
  as_admin?: boolean;
  /** Why not, in words, when the rule bars them. */
  refusal: string | null;
}

// ── the maker's list ─────────────────────────────────────────────────────

export type CandidateStatus = "open" | "proposed" | "all";

export interface LinkCandidate {
  asset: SapLinkAssetBrief;
  sap: SapRecordBrief;
  reason_code: "old_tag_unique" | "serial_unique" | string;
  reason: string;
  /** The pending proposal, when there is one. */
  link: SapLink | null;
}

export interface LinkCandidatesPage {
  status: CandidateStatus;
  total: number;
  offset: number;
  limit: number;
  by_office: { office: string | null; assets: number }[];
  items: LinkCandidate[];
  sentence: string;
}

export async function fetchLinkCandidates(p: {
  office?: string; klass?: string; status?: CandidateStatus; limit?: number; offset?: number;
}): Promise<LinkCandidatesPage> {
  return (await apiGet<LinkCandidatesPage>("/api/v1/sap-links/candidates", {
    office: p.office || undefined,
    class: p.klass || undefined,
    status: p.status ?? "open",
    limit: p.limit ?? 100,
    offset: p.offset ?? 0,
  })).data;
}

// ── a batch's answer ─────────────────────────────────────────────────────

export type SapLinkAction = "propose" | "approve" | "return";

export interface SapLinkLine {
  asset_id: number | null;
  asset_code: string | null;
  link_id: number | null;
  sap_asset_number: string | null;
  outcome: "done" | "would_do" | "refused";
  status: number;
  code: string | null;
  message: string | null;
  details: Record<string, unknown> | null;
}

export interface SapLinkBatchAnswer {
  action: SapLinkAction;
  dry_run: boolean;
  total: number;
  done: number;
  refused: number;
  results: SapLinkLine[];
}

export async function proposeLinks(body: {
  asset_ids: number[]; note?: string; dry_run?: boolean;
}): Promise<SapLinkBatchAnswer> {
  const payload: Record<string, unknown> = { asset_ids: body.asset_ids };
  if (body.note && body.note.trim()) payload.note = body.note.trim();
  if (body.dry_run) payload.dry_run = true;
  return (await apiPost<SapLinkBatchAnswer>("/api/v1/sap-links/propose", payload)).data;
}

export async function decideLinks(approve: boolean, body: {
  link_ids: number[]; reason?: string;
}): Promise<SapLinkBatchAnswer> {
  const payload: Record<string, unknown> = { link_ids: body.link_ids };
  if (!approve) payload.reason = (body.reason ?? "").trim();
  return (await apiPost<SapLinkBatchAnswer>(
    approve ? "/api/v1/sap-links/approve" : "/api/v1/sap-links/return", payload)).data;
}

// ── the checker's queue ──────────────────────────────────────────────────

export interface SapLinksPage {
  rows: SapLink[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export async function fetchSapLinksPage(
  cursor: string | undefined, p: { state?: SapLinkState | "all"; kind?: SapLinkKind } = {},
): Promise<SapLinksPage> {
  const res = await apiGet<SapLink[]>("/api/v1/sap-links", {
    state: p.state ?? "proposed",
    kind: p.kind,
    cursor,
    limit: 100,
  });
  const pg: CadraPagination | undefined = res.pagination;
  return {
    rows: res.data ?? [],
    nextCursor: pg?.next_cursor ?? null,
    totalEstimate: pg?.total_estimate ?? null,
  };
}

// ── §2: the contested list ───────────────────────────────────────────────

export interface ContestedFlag {
  sap_asset_number: string | null;
  note: string | null;
  flagged_by: SapUserRef | null;
  flagged_at: string | null;
}

export interface ContestedMember extends SapLinkAssetBrief {
  old_tag: string | null;
  serial_number: string | null;
  custodian: { id: number; name: string } | null;
  created_at: string | null;
  matched_by: "old_tag" | "serial" | string;
  photos: { count: number; latest: { id: number; url: string }[] };
  duplicate_flag: ContestedFlag | null;
}

export interface ContestedGroup {
  sap: SapRecordBrief;
  assets: ContestedMember[];
  flagged: boolean;
  link: SapLink | null;
}

export interface ContestedPage {
  total_groups: number;
  total_assets: number;
  offset: number;
  limit: number;
  by_office: { office: string | null; groups: number; assets: number; flagged: number }[];
  items: ContestedGroup[];
  sentence: string;
}

export async function fetchContested(p: {
  office?: string; flagged?: "true" | "false"; limit?: number; offset?: number;
}): Promise<ContestedPage> {
  return (await apiGet<ContestedPage>("/api/v1/sap-links/contested", {
    office: p.office || undefined,
    flagged: p.flagged,
    limit: p.limit ?? 50,
    offset: p.offset ?? 0,
  })).data;
}

export async function proposeContested(sapId: number, assetId: number, note?: string): Promise<SapLink> {
  const payload: Record<string, unknown> = { asset_id: assetId };
  if (note && note.trim()) payload.note = note.trim();
  return (await apiPost<SapLink>(`/api/v1/sap-links/contested/${sapId}/propose`, payload)).data;
}

export interface FlagAnswer {
  sap: SapRecordBrief;
  assets: (SapLinkAssetBrief & { duplicate_flag: ContestedFlag | null })[];
  sentence: string;
}

export async function flagContested(sapId: number, note: string): Promise<FlagAnswer> {
  return (await apiPost<FlagAnswer>(`/api/v1/sap-links/contested/${sapId}/flag`, { note: note.trim() })).data;
}
