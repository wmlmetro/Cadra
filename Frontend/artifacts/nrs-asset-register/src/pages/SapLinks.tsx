/**
 * Link to SAP — a register asset given its SAP number from SAP's own export,
 * by two people (handoff 65 §1–§2).
 *
 * Three tabs, drawn the way Candidates draws its own:
 *
 *   Confident matches       the Register Maker's list: every register asset
 *                           with no SAP number whose old tag (or, failing
 *                           that, real serial) points at exactly ONE active,
 *                           unlinked SAP record no other Cadra asset points
 *                           at. Select and *Propose selected*: a preview (a
 *                           dry run on the server) first, then the batch —
 *                           N single proposals, a line per asset.
 *   Waiting on the checker  the proposals (and undos) the Register Checker
 *                           approves or returns, singly or in a batch; a
 *                           return needs a reason. A row this person may not
 *                           decide (they proposed it) says why, verbatim.
 *   Contested               each SAP record two or more Cadra assets point
 *                           at, the assets side by side. The maker proposes
 *                           ONE of them, or flags the group as a likely
 *                           duplicate with a note — a record for NRS;
 *                           nothing is merged, retired or deleted.
 *
 * The lists are `sap_mirror:read`. Proposing and flagging are
 * `register:make`, deciding `register:check`; the controls are drawn only
 * for a holder, and the server refuses everybody else regardless. Nothing a
 * link does is sent to SAP: the master already exists there.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "wouter";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { fetchPictureObjectUrl } from "@/lib/assetPhotos";
import {
  SAP_LINKS_KEY, SAP_LINK_BATCH_MAX, decideLinks, fetchContested, fetchLinkCandidates, fetchSapLinksPage,
  flagContested, proposeContested, proposeLinks,
  type CandidateStatus, type ContestedGroup, type ContestedMember, type LinkCandidate, type SapLink,
  type SapLinkAction, type SapLinkBatchAnswer, type SapLinkLine, type SapRecordBrief,
} from "@/lib/sapLinks";
import { cn, formatIsoDate, formatIsoDateTime } from "@/lib/utils";
import {
  AlertCircle, CheckCircle2, Clock, Flag, Image as ImageIcon, Inbox, Link2, Loader2, XCircle,
} from "lucide-react";

type Tab = "confident" | "checker" | "contested";
const TABS: { key: Tab; label: string }[] = [
  { key: "confident", label: "Confident matches" },
  { key: "checker", label: "Waiting on the checker" },
  { key: "contested", label: "Contested" },
];

const INPUT = "px-2.5 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const TEXTAREA = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const LABEL = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";

const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
const when = (at: string | null | undefined) => (at ? formatIsoDateTime(at.replace(" ", "T")) : "—");

/** After any act: the three tabs, the coverage report, and every asset the
 *  act touched (its SAP number and history changed). */
function invalidateAfter(qc: QueryClient, assetIds: (number | null | undefined)[]) {
  qc.invalidateQueries({ queryKey: SAP_LINKS_KEY });
  qc.invalidateQueries({ queryKey: ["reports", "sap-coverage"] });
  for (const id of assetIds) if (id != null) invalidateAssetQueries(qc, String(id));
}

function initialTab(canCheck: boolean, canMake: boolean): Tab {
  try {
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q === "confident" || q === "checker" || q === "contested") return q;
  } catch { /* no window in a test renderer */ }
  return canCheck && !canMake ? "checker" : "confident";
}

export default function SapLinks() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canRead = scopes.has(SCOPE.sapMirrorRead);
  const canMake = scopes.has(SCOPE.registerMake);
  const canCheck = scopes.has(SCOPE.registerCheck);
  const [tab, setTab] = useState<Tab>(() => initialTab(canCheck, canMake));

  useEffect(() => {
    setTitle("Link to SAP");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  if (!canRead) {
    return <ScopeRefusal scope={SCOPE.sapMirrorRead}
      detail="The Asset Controller, the Register Maker and Checker, and Auditors hold it." />;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-border bg-card">
        <h1 className="text-[14px] font-bold text-foreground flex items-center gap-2">
          <Link2 size={15} /> Link to SAP
        </h1>
        <p className="text-[11px] text-muted-foreground mt-0.5 max-w-3xl">
          Give a register asset its SAP asset number from SAP's own export, where the match is certain.
          A Register Maker proposes, a Register Checker approves — one person cannot do both on one asset.
          Nothing is sent to SAP: the asset already exists there.
        </p>
        <div className="flex gap-1 mt-3 flex-wrap items-center" role="tablist" aria-label="Link to SAP">
          {TABS.map(t => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              data-testid={`sap-links-tab-${t.key}`}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl border transition-colors",
                tab === t.key
                  ? "bg-primary text-white border-primary"
                  : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === "confident" && <ConfidentTab canMake={canMake} />}
        {tab === "checker" && <CheckerTab canCheck={canCheck} />}
        {tab === "contested" && <ContestedTab canMake={canMake} />}
      </div>
    </div>
  );
}

// ─── shared pieces ───────────────────────────────────────────────────────────

function ErrorPanel({ err, testid = "sap-links-error" }: { err: CadraApiError; testid?: string }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3"
         data-testid={testid}>
      <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <ApiErrorMessage err={err} />
    </div>
  );
}

function Loading({ what }: { what: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
      <p className="text-sm text-muted-foreground">{what}</p>
    </div>
  );
}

function Empty({ children, testid }: { children: React.ReactNode; testid: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 px-6 text-center" data-testid={testid}>
      <Inbox size={24} className="text-muted-foreground/30" />
      <p className="text-sm font-semibold">{children}</p>
    </div>
  );
}

function AssetCell({ a }: { a: { id: number; asset_code: string | null; name: string | null; location: { name: string } | null } }) {
  return (
    <>
      <Link href={`/assets/${a.id}`} className="font-semibold text-primary hover:underline" data-testid={`asset-link-${a.id}`}>
        {a.asset_code ?? `Asset ${a.id}`}
      </Link>
      {a.name && <div className="text-muted-foreground">{a.name}</div>}
      <div className="text-muted-foreground">{a.location?.name ?? "No location"}</div>
    </>
  );
}

function SapCell({ s }: { s: SapRecordBrief }) {
  return (
    <>
      <div className="font-mono font-semibold text-foreground">
        {s.asset_number}{s.sub_number && s.sub_number !== "0" ? `-${s.sub_number}` : ""}
      </div>
      <div className="text-muted-foreground">
        Class <span className="font-mono">{s.class ?? "—"}</span>
        {s.office_code && <> · office <span className="font-mono">{s.office_code}</span></>}
      </div>
      {s.description && <div className="text-foreground">{s.description}{s.description_2 ? ` · ${s.description_2}` : ""}</div>}
      <div className="text-muted-foreground">
        Capitalised {s.capitalized_on ? formatIsoDate(s.capitalized_on) : "—"}
        {s.old_tag && <> · old tag <span className="font-mono">{s.old_tag}</span></>}
      </div>
    </>
  );
}

function SelectionButton({ testid, n: count, onClick, children }: {
  testid: string; n: number; onClick: () => void; children: React.ReactNode;
}) {
  const ready = count > 0 && count <= SAP_LINK_BATCH_MAX;
  return (
    <button type="button" disabled={!ready} onClick={onClick} data-testid={testid}
      className={cn(
        "px-3 py-1.5 text-xs font-semibold rounded-xl transition-colors",
        ready ? "bg-primary text-primary-foreground hover:bg-primary/90" : "bg-muted text-muted-foreground cursor-not-allowed",
      )}>
      {children} ({count})
    </button>
  );
}

function SendButton({ ready, pending, onClick, children, testid }: {
  ready: boolean; pending: boolean; onClick: () => void; children: React.ReactNode; testid: string;
}) {
  return (
    <button type="button" disabled={!ready || pending} onClick={onClick} data-testid={testid}
      className={cn(
        "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
        ready && !pending ? "bg-primary text-primary-foreground hover:bg-primary/90"
                          : "bg-muted text-muted-foreground cursor-not-allowed",
      )}>
      {pending && <Loader2 size={12} className="animate-spin" />}
      {children}
    </button>
  );
}

const DONE_WORDS: Record<SapLinkAction, string> = {
  propose: "proposed — waiting on the Register Checker",
  approve: "approved — the SAP number is on the asset",
  return: "returned to the Register Maker",
};
const WOULD_WORDS: Record<SapLinkAction, string> = {
  propose: "would be proposed",
  approve: "would be approved",
  return: "would be returned",
};

function summary(a: SapLinkBatchAnswer): string {
  const verb = { propose: "proposed", approve: "approved", return: "returned" }[a.action];
  if (a.dry_run) {
    return `${a.done} of ${a.total} would be ${verb}, ${a.refused} would be refused. Nothing has been written yet.`;
  }
  return `${a.done} of ${a.total} ${verb}, ${a.refused} refused.`;
}

function ResultLines({ answer, testidPrefix }: { answer: SapLinkBatchAnswer; testidPrefix: string }) {
  return (
    <ul className="max-h-72 overflow-y-auto rounded-xl border border-border divide-y divide-border" data-testid={`${testidPrefix}-lines`}>
      {answer.results.map((l: SapLinkLine, i) => {
        const ok = l.outcome !== "refused";
        const key = answer.action === "propose" ? (l.asset_id ?? `x${i}`) : (l.link_id ?? `x${i}`);
        return (
          <li key={`${key}-${i}`} className="px-3 py-2 text-[11px] flex items-start gap-2"
              data-testid={`${testidPrefix}-line-${key}`} data-outcome={l.outcome}>
            {ok
              ? <CheckCircle2 size={13} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
              : <XCircle size={13} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />}
            <p className="min-w-0">
              <span className="font-semibold text-foreground">{l.asset_code ?? (l.asset_id != null ? `Asset ${l.asset_id}` : `Proposal ${l.link_id ?? "?"}`)}</span>
              {l.sap_asset_number && <span className="text-muted-foreground"> → SAP <span className="font-mono">{l.sap_asset_number}</span></span>}
              {" — "}
              {ok
                ? <span className="text-foreground">{l.outcome === "would_do" ? WOULD_WORDS[answer.action] : DONE_WORDS[answer.action]}</span>
                : <span className="text-red-700 dark:text-red-400" data-testid="sap-link-line-message">{l.message ?? "Refused."}</span>}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

/** The server's answer to a batch that was sent for real. */
function ResultsDialog({ answer, onClose }: { answer: SapLinkBatchAnswer; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="sap-link-results" data-action={answer.action}>
        <DialogHeader>
          <DialogTitle>{answer.action === "approve" ? "Approved" : answer.action === "return" ? "Returned" : "Proposed"} — the answer</DialogTitle>
          <DialogDescription data-testid="sap-link-results-summary">{summary(answer)}</DialogDescription>
        </DialogHeader>
        <ResultLines answer={answer} testidPrefix="sap-link-result" />
        <DialogFooter>
          <button type="button" onClick={onClose} data-testid="button-close-sap-link-results"
            className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">
            Close
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Confident matches ───────────────────────────────────────────────────────

const PAGE = 100;

function ConfidentTab({ canMake }: { canMake: boolean }) {
  const qc = useQueryClient();
  const [office, setOffice] = useState("");
  const [klassTyped, setKlassTyped] = useState("");
  const [klass, setKlass] = useState("");
  const [status, setStatus] = useState<CandidateStatus>("open");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const t = window.setTimeout(() => setKlass(klassTyped.trim()), 300);
    return () => window.clearTimeout(t);
  }, [klassTyped]);
  useEffect(() => { setOffset(0); }, [office, klass, status]);

  const q = useQuery<Awaited<ReturnType<typeof fetchLinkCandidates>>, CadraApiError>({
    queryKey: [...SAP_LINKS_KEY, "candidates", office, klass, status, offset],
    queryFn: () => fetchLinkCandidates({ office, klass, status, offset, limit: PAGE }),
    staleTime: 15_000,
  });
  const items = q.data?.items ?? [];

  // A selection belongs to the list it was made on.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  useEffect(() => { setSelected(new Set()); }, [office, klass, status, offset]);
  const selectable = (r: LinkCandidate) => canMake && !r.link;
  const selectableRows = items.filter(selectable);
  const selectedRows = items.filter(r => selected.has(r.asset.id) && selectable(r));
  const allSelected = selectableRows.length > 0 && selectableRows.every(r => selected.has(r.asset.id));
  const toggle = (id: number) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const [proposing, setProposing] = useState<LinkCandidate[] | null>(null);

  // The office list is the server's, counted before the office filter.
  const offices = q.data?.by_office ?? [];

  return (
    <div>
      <div className="px-5 py-3 border-b border-border space-y-2">
        <div className="flex flex-wrap gap-2 items-center">
          <label className="text-[11px] text-muted-foreground" htmlFor="sap-links-office">Office</label>
          <select id="sap-links-office" value={office} onChange={e => setOffice(e.target.value)}
                  className={INPUT} data-testid="sap-links-office">
            <option value="">Every office</option>
            {offices.map(o => (
              <option key={o.office ?? "none"} value={o.office ?? ""} disabled={!o.office}>
                {o.office ?? "no office"} ({n(o.assets)})
              </option>
            ))}
            {/* Keep a chosen office selectable when it has dropped off the list. */}
            {office && !offices.some(o => o.office === office) && <option value={office}>{office}</option>}
          </select>
          <label className="text-[11px] text-muted-foreground ml-2" htmlFor="sap-links-class">SAP class</label>
          <input id="sap-links-class" value={klassTyped} onChange={e => setKlassTyped(e.target.value)}
                 placeholder="e.g. 3000" className={cn(INPUT, "w-24 font-mono")} data-testid="sap-links-class" />
          <label className="text-[11px] text-muted-foreground ml-2" htmlFor="sap-links-status">Show</label>
          <select id="sap-links-status" value={status} onChange={e => setStatus(e.target.value as CandidateStatus)}
                  className={INPUT} data-testid="sap-links-status">
            <option value="open">Not yet proposed</option>
            <option value="proposed">Proposed, waiting on the checker</option>
            <option value="all">All</option>
          </select>
        </div>
        {q.data && (
          <p className="text-[12px] text-foreground" data-testid="sap-links-sentence">{q.data.sentence}</p>
        )}
        {canMake ? (
          <div className="flex gap-2 flex-wrap items-center" data-testid="sap-links-batch-bar">
            <span className="text-[11px] text-muted-foreground" data-testid="sap-links-selected-count">
              <span className="font-bold text-foreground">{selectedRows.length}</span> selected
            </span>
            <SelectionButton testid="button-propose-selected" n={selectedRows.length}
              onClick={() => setProposing(selectedRows)}>
              Propose selected
            </SelectionButton>
            {selectedRows.length > 0 && (
              <button type="button" onClick={() => setSelected(new Set())}
                className="text-[11px] text-muted-foreground hover:text-foreground">Clear</button>
            )}
            {selectedRows.length > SAP_LINK_BATCH_MAX && (
              <span className="text-[11px] text-amber-700 dark:text-amber-400">
                A batch takes at most {SAP_LINK_BATCH_MAX}.
              </span>
            )}
            <span className="text-[11px] text-muted-foreground">
              A proposal goes to the Register Checker; nothing is written to the asset until they approve.
            </span>
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground" data-testid="sap-links-read-only">
            Proposing a link is the Register Maker's act (<span className="font-mono">register:make</span>); you can read the list.
          </p>
        )}
      </div>

      {q.error && <div className="px-5 py-2"><ErrorPanel err={q.error} /></div>}

      {q.isLoading ? <Loading what="Matching the register against SAP's export…" /> : items.length === 0 && !q.error ? (
        <Empty testid="sap-links-empty">
          {status === "open" ? "No asset has a confident match that is not already proposed." : "Nothing to show for this filter."}
        </Empty>
      ) : (
        <table className="w-full text-xs" data-testid="sap-links-candidates">
          <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground sticky top-0">
            <tr>
              {canMake && (
                <th className="pl-5 pr-1 py-2 w-6">
                  <input type="checkbox" className="accent-primary"
                    aria-label="Select every asset shown that is not yet proposed"
                    checked={allSelected} disabled={selectableRows.length === 0}
                    onChange={e => setSelected(e.target.checked ? new Set(selectableRows.map(r => r.asset.id)) : new Set())}
                    data-testid="select-all-candidates" />
                </th>
              )}
              <th className={cn("text-left font-semibold py-2", canMake ? "px-3" : "px-5")}>Cadra asset</th>
              <th className="text-left font-semibold px-3 py-2">SAP record</th>
              <th className="text-left font-semibold px-5 py-2">Why</th>
            </tr>
          </thead>
          <tbody>
            {items.map(r => (
              <tr key={r.asset.id} className={cn("border-b border-border align-top", selected.has(r.asset.id) && "bg-primary/5")}
                  data-testid={`sap-candidate-row-${r.asset.id}`}>
                {canMake && (
                  <td className="pl-5 pr-1 py-2.5 w-6">
                    {selectable(r) && (
                      <input type="checkbox" className="accent-primary"
                        aria-label={`Select ${r.asset.asset_code ?? r.asset.id}`}
                        checked={selected.has(r.asset.id)} onChange={() => toggle(r.asset.id)}
                        data-testid={`select-candidate-${r.asset.id}`} />
                    )}
                  </td>
                )}
                <td className={cn("py-2.5", canMake ? "px-3" : "px-5")}><AssetCell a={r.asset} /></td>
                <td className="px-3 py-2.5"><SapCell s={r.sap} /></td>
                <td className="px-5 py-2.5">
                  <span className="inline-block px-2 py-0.5 rounded-lg border text-[11px] font-semibold bg-muted text-foreground border-border">
                    {r.reason}
                  </span>
                  {r.link && (
                    <p className="mt-1 text-[11px] text-amber-800 dark:text-amber-300" data-testid={`candidate-proposed-${r.asset.id}`}>
                      Proposed — waiting on the Register Checker
                      {r.link.proposed_by && <span className="text-muted-foreground"> (by {r.link.proposed_by.name}, {when(r.link.proposed_at)})</span>}
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {q.data && q.data.total > PAGE && (
        <div className="px-5 py-3 flex items-center gap-3 text-[11px] text-muted-foreground">
          <span>
            {n(offset + 1)}–{n(Math.min(offset + PAGE, q.data.total))} of {n(q.data.total)}
          </span>
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="px-2 py-1 rounded-lg border border-border disabled:opacity-40">Previous</button>
          <button type="button" disabled={offset + PAGE >= q.data.total} onClick={() => setOffset(offset + PAGE)}
            className="px-2 py-1 rounded-lg border border-border disabled:opacity-40">Next</button>
        </div>
      )}

      {proposing && (
        <ProposeDialog rows={proposing} onClose={(answer) => {
          setProposing(null);
          if (answer) {
            setSelected(new Set());
            invalidateAfter(qc, answer.results.map(l => l.asset_id));
          }
        }} />
      )}
    </div>
  );
}

/**
 * Preview first: the dialog opens by asking the server what WOULD happen (a
 * dry run, every proposal made and rolled back), then *Propose N* sends the
 * same list for real and shows the answer in place of the preview.
 */
function ProposeDialog({ rows, onClose }: {
  rows: LinkCandidate[]; onClose: (sent: SapLinkBatchAnswer | null) => void;
}) {
  const ids = useMemo(() => rows.map(r => r.asset.id), [rows]);
  const [note, setNote] = useState("");
  const preview = useMutation<SapLinkBatchAnswer, CadraApiError>({
    mutationFn: () => proposeLinks({ asset_ids: ids, note, dry_run: true }),
  });
  const send = useMutation<SapLinkBatchAnswer, CadraApiError>({
    mutationFn: () => proposeLinks({ asset_ids: ids, note }),
  });
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    preview.mutate();
  }, [preview]);
  const busy = preview.isPending || send.isPending;
  const close = () => { if (!busy) onClose(send.data ?? null); };
  const wouldDo = preview.data?.done ?? 0;
  const answer = send.data ?? preview.data;

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="propose-dialog"
                     data-phase={send.data ? "sent" : preview.data ? "preview" : "loading"}>
        <DialogHeader>
          <DialogTitle>{send.data ? "Proposed — the answer" : "Propose links to SAP"}</DialogTitle>
          <DialogDescription data-testid="propose-summary">
            {answer ? summary(answer) : `Asking the server what would happen to ${rows.length} ${rows.length === 1 ? "asset" : "assets"}…`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {preview.isPending && (
            <p className="text-[11px] text-muted-foreground flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> Checking each asset…</p>
          )}
          {answer && <ResultLines answer={answer} testidPrefix="propose" />}
          {!send.data && preview.data && (
            <div>
              <label htmlFor="propose-note" className={LABEL}>Note for the checker (optional)</label>
              <textarea id="propose-note" rows={2} value={note} onChange={e => setNote(e.target.value)}
                className={TEXTAREA} data-testid="input-propose-note" />
            </div>
          )}
          {preview.error && <ErrorPanel err={preview.error} testid="propose-error" />}
          {send.error && <ErrorPanel err={send.error} testid="propose-error" />}
        </div>

        <DialogFooter>
          <button type="button" onClick={close} data-testid="button-propose-close"
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            {send.data ? "Close" : "Cancel"}
          </button>
          {!send.data && (
            <SendButton testid="button-propose-send" ready={wouldDo > 0} pending={send.isPending}
              onClick={() => send.mutate()}>
              Propose {wouldDo}
            </SendButton>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Waiting on the checker ──────────────────────────────────────────────────

const KIND_WORDS: Record<string, string> = { link: "Link", unlink: "Undo" };

function CheckerTab({ canCheck }: { canCheck: boolean }) {
  const qc = useQueryClient();
  const {
    data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: [...SAP_LINKS_KEY, "proposed"],
    queryFn: ({ pageParam }) => fetchSapLinksPage(pageParam as string | undefined, { state: "proposed" }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 15_000,
  });
  const rows = useMemo(() => (data?.pages ?? []).flatMap(p => p.rows), [data]);
  const total = data?.pages[0]?.totalEstimate ?? null;

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const selectable = (l: SapLink) => canCheck && l.can_decide;
  const selectableRows = rows.filter(selectable);
  const selectedRows = rows.filter(l => selected.has(l.id) && selectable(l));
  const allSelected = selectableRows.length > 0 && selectableRows.every(l => selected.has(l.id));
  const toggle = (id: number) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const [deciding, setDeciding] = useState<{ approve: boolean; rows: SapLink[] } | null>(null);
  const [answer, setAnswer] = useState<SapLinkBatchAnswer | null>(null);

  const finished = (a: SapLinkBatchAnswer, decided: SapLink[]) => {
    setDeciding(null);
    setSelected(new Set());
    setAnswer(a);
    invalidateAfter(qc, decided.map(l => l.asset.id));
  };

  return (
    <div>
      <div className="px-5 py-3 border-b border-border space-y-2">
        {!isLoading && (
          <p className="text-[12px] text-foreground" data-testid="sap-links-checker-count">
            <span className="font-bold">{rows.length.toLocaleString()}</span>
            {total != null && <> of <span className="font-bold">{total.toLocaleString()}</span></>} proposals waiting on the Register Checker, oldest first.
          </p>
        )}
        {canCheck ? (
          <div className="flex gap-2 flex-wrap items-center" data-testid="sap-links-checker-bar">
            <span className="text-[11px] text-muted-foreground">
              <span className="font-bold text-foreground">{selectedRows.length}</span> selected
            </span>
            <SelectionButton testid="button-approve-selected" n={selectedRows.length}
              onClick={() => setDeciding({ approve: true, rows: selectedRows })}>
              Approve selected
            </SelectionButton>
            <SelectionButton testid="button-return-selected" n={selectedRows.length}
              onClick={() => setDeciding({ approve: false, rows: selectedRows })}>
              Return selected
            </SelectionButton>
            <span className="text-[11px] text-muted-foreground">
              Only proposals you may decide can be selected; one you proposed says why in its row.
            </span>
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground" data-testid="sap-links-checker-read-only">
            Deciding a link is the Register Checker's act (<span className="font-mono">register:check</span>); you can read the queue.
          </p>
        )}
      </div>

      {error && <div className="px-5 py-2"><ErrorPanel err={error as CadraApiError} /></div>}

      {isLoading ? <Loading what="Loading the proposals…" /> : rows.length === 0 && !error ? (
        <Empty testid="sap-links-checker-empty">Nothing is waiting on the Register Checker.</Empty>
      ) : (
        <table className="w-full text-xs" data-testid="sap-links-proposals">
          <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground sticky top-0">
            <tr>
              {canCheck && (
                <th className="pl-5 pr-1 py-2 w-6">
                  <input type="checkbox" className="accent-primary"
                    aria-label="Select every proposal shown that you may decide"
                    checked={allSelected} disabled={selectableRows.length === 0}
                    onChange={e => setSelected(e.target.checked ? new Set(selectableRows.map(l => l.id)) : new Set())}
                    data-testid="select-all-links" />
                </th>
              )}
              <th className={cn("text-left font-semibold py-2", canCheck ? "px-3" : "px-5")}>Kind</th>
              <th className="text-left font-semibold px-3 py-2">Cadra asset</th>
              <th className="text-left font-semibold px-3 py-2">SAP record</th>
              <th className="text-left font-semibold px-3 py-2">Why</th>
              <th className="text-left font-semibold px-3 py-2">Proposed</th>
              <th className="text-left font-semibold px-5 py-2">Your decision</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(l => (
              <tr key={l.id} className={cn("border-b border-border align-top", selected.has(l.id) && "bg-primary/5")}
                  data-testid={`sap-link-row-${l.id}`} data-asset-id={l.asset.id}>
                {canCheck && (
                  <td className="pl-5 pr-1 py-2.5 w-6">
                    {selectable(l) && (
                      <input type="checkbox" className="accent-primary"
                        aria-label={`Select ${l.asset.asset_code ?? l.asset.id}`}
                        checked={selected.has(l.id)} onChange={() => toggle(l.id)}
                        data-testid={`select-link-${l.id}`} />
                    )}
                  </td>
                )}
                <td className={cn("py-2.5", canCheck ? "px-3" : "px-5")}>
                  <span className={cn("inline-block px-2 py-0.5 rounded-lg border text-[11px] font-semibold",
                    l.kind === "unlink"
                      ? "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40"
                      : "bg-muted text-foreground border-border")}>
                    {KIND_WORDS[l.kind] ?? l.kind}
                  </span>
                </td>
                <td className="px-3 py-2.5"><AssetCell a={l.asset} /></td>
                <td className="px-3 py-2.5"><SapCell s={l.sap} /></td>
                <td className="px-3 py-2.5">
                  {l.reason ?? "—"}
                  {l.note && <p className="text-muted-foreground mt-0.5">Note: {l.note}</p>}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  {l.proposed_by?.name ?? "—"}
                  <div className="text-muted-foreground">{when(l.proposed_at)}</div>
                </td>
                <td className="px-5 py-2.5">
                  {canCheck && l.can_decide ? (
                    <div className="flex gap-1.5">
                      <button type="button" onClick={() => setDeciding({ approve: true, rows: [l] })}
                        data-testid={`button-approve-link-${l.id}`}
                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
                        Approve
                      </button>
                      <button type="button" onClick={() => setDeciding({ approve: false, rows: [l] })}
                        data-testid={`button-return-link-${l.id}`}
                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg border border-border text-foreground hover:bg-accent">
                        Return
                      </button>
                    </div>
                  ) : l.refusal ? (
                    <p className="text-[11px] text-amber-800 dark:text-amber-300 max-w-xs" data-testid={`link-refusal-${l.id}`}>{l.refusal}</p>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {hasNextPage && (
        <div className="px-5 py-3">
          <button type="button" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}
            className="text-[11px] font-semibold text-primary hover:underline">
            {isFetchingNextPage ? "Loading more…" : "Load more"}
          </button>
        </div>
      )}

      {deciding && (
        <DecideDialog approve={deciding.approve} rows={deciding.rows}
          onClose={() => setDeciding(null)} onDone={(a) => finished(a, deciding.rows)} />
      )}
      {answer && <ResultsDialog answer={answer} onClose={() => setAnswer(null)} />}
    </div>
  );
}

function DecideDialog({ approve, rows, onClose, onDone }: {
  approve: boolean; rows: SapLink[]; onClose: () => void; onDone: (a: SapLinkBatchAnswer) => void;
}) {
  const [reason, setReason] = useState("");
  const m = useMutation<SapLinkBatchAnswer, CadraApiError>({
    mutationFn: () => decideLinks(approve, { link_ids: rows.map(l => l.id), reason }),
    onSuccess: onDone,
  });
  const close = () => { if (!m.isPending) onClose(); };
  const ready = rows.length > 0 && rows.length <= SAP_LINK_BATCH_MAX && (approve || reason.trim().length > 0);
  const many = rows.length === 1 ? "proposal" : "proposals";

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="decide-dialog" data-approve={String(approve)}>
        <DialogHeader>
          <DialogTitle>{approve ? `Approve ${rows.length} ${many}` : `Return ${rows.length} ${many}`}</DialogTitle>
          <DialogDescription>
            {approve
              ? "Each approved link writes SAP's asset number onto the Cadra asset, recorded as linked from SAP's export by two people. An approved undo takes the number off. Nothing is sent to SAP."
              : "A returned proposal goes back to the Register Maker with your reason. The asset is left as it is."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <ul className="max-h-48 overflow-y-auto rounded-xl border border-border divide-y divide-border text-[11px]" data-testid="decide-units">
            {rows.map(l => (
              <li key={l.id} className="px-3 py-1.5 flex items-center gap-2">
                <span className="font-semibold text-foreground">{l.asset.asset_code ?? `Asset ${l.asset.id}`}</span>
                <span className="text-muted-foreground">{KIND_WORDS[l.kind] ?? l.kind}</span>
                <span className="ml-auto font-mono text-muted-foreground">SAP {l.sap.asset_number}</span>
              </li>
            ))}
          </ul>
          {!approve && (
            <div>
              <label htmlFor="return-reason" className={LABEL}>Reason (required)</label>
              <textarea id="return-reason" rows={2} value={reason} onChange={e => setReason(e.target.value)}
                className={TEXTAREA} data-testid="input-return-reason"
                placeholder="Say why, in words — the maker reads this." />
            </div>
          )}
          {m.error && <ErrorPanel err={m.error} testid="decide-error" />}
        </div>
        <DialogFooter>
          <button type="button" onClick={close}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <SendButton testid="button-decide-send" ready={ready} pending={m.isPending} onClick={() => m.mutate()}>
            {approve ? "Approve" : "Return"} {rows.length}
          </SendButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Contested ───────────────────────────────────────────────────────────────

const CONTESTED_PAGE = 50;

function ContestedTab({ canMake }: { canMake: boolean }) {
  const [office, setOffice] = useState("");
  const [flagged, setFlagged] = useState<"" | "true" | "false">("");
  const [offset, setOffset] = useState(0);
  const [allOffices, setAllOffices] = useState(false);
  useEffect(() => { setOffset(0); }, [office, flagged]);

  const q = useQuery<Awaited<ReturnType<typeof fetchContested>>, CadraApiError>({
    queryKey: [...SAP_LINKS_KEY, "contested", office, flagged, offset],
    queryFn: () => fetchContested({ office, flagged: flagged || undefined, offset, limit: CONTESTED_PAGE }),
    staleTime: 15_000,
  });
  const d = q.data;
  const offices = d?.by_office ?? [];
  const shownOffices = allOffices ? offices : offices.slice(0, 10);

  return (
    <div className="p-5 space-y-4">
      {q.error && <ErrorPanel err={q.error} />}
      {q.isLoading && <Loading what="Finding SAP records more than one Cadra asset points at…" />}
      {d && (
        <>
          <p className="text-[12px] text-foreground" data-testid="sap-contested-sentence">{d.sentence}</p>

          {offices.length > 0 && (
            <div className="glass-card rounded-2xl p-4 overflow-x-auto">
              <p className="text-sm font-semibold mb-2">By office</p>
              <table className="w-full text-[12px] max-w-xl" data-testid="sap-contested-by-office">
                <thead><tr className="text-left text-muted-foreground">
                  <th className="py-1 pr-3">Office</th>
                  <th className="py-1 pr-3 text-right">SAP records</th>
                  <th className="py-1 pr-3 text-right">Cadra assets</th>
                  <th className="py-1 pr-3 text-right">Flagged</th>
                </tr></thead>
                <tbody>
                  {shownOffices.map(o => (
                    <tr key={o.office ?? "none"} className="border-t border-border/50">
                      <td className="py-1 pr-3 font-medium">
                        {o.office ? (
                          <button type="button" className="text-primary hover:underline font-mono" onClick={() => setOffice(o.office ?? "")}>
                            {o.office}
                          </button>
                        ) : "no office"}
                      </td>
                      <td className="py-1 pr-3 text-right">{n(o.groups)}</td>
                      <td className="py-1 pr-3 text-right">{n(o.assets)}</td>
                      <td className="py-1 pr-3 text-right">{n(o.flagged)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {offices.length > shownOffices.length && (
                <button type="button" onClick={() => setAllOffices(true)} className="mt-2 text-[12px] underline">
                  Show all {n(offices.length)}
                </button>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2 items-center">
            <label className="text-[11px] text-muted-foreground" htmlFor="sap-contested-office">Office</label>
            <select id="sap-contested-office" value={office} onChange={e => setOffice(e.target.value)}
                    className={INPUT} data-testid="sap-contested-office">
              <option value="">Every office</option>
              {offices.filter(o => o.office).map(o => (
                <option key={o.office!} value={o.office!}>{o.office} ({n(o.groups)})</option>
              ))}
            </select>
            <label className="text-[11px] text-muted-foreground ml-2" htmlFor="sap-contested-flagged">Show</label>
            <select id="sap-contested-flagged" value={flagged} onChange={e => setFlagged(e.target.value as "" | "true" | "false")}
                    className={INPUT} data-testid="sap-contested-flagged">
              <option value="">Flagged or not</option>
              <option value="false">Not flagged</option>
              <option value="true">Flagged as a likely duplicate</option>
            </select>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {n(d.total_groups)} SAP records, {n(d.total_assets)} Cadra assets on this filter
            </span>
          </div>

          {d.items.length === 0 ? (
            <Empty testid="sap-contested-empty">No SAP record on this filter is pointed at by more than one Cadra asset.</Empty>
          ) : (
            <div className="space-y-4">
              {d.items.map(g => <ContestedCard key={g.sap.id} group={g} canMake={canMake} />)}
            </div>
          )}

          {d.total_groups > CONTESTED_PAGE && (
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span>{n(offset + 1)}–{n(Math.min(offset + CONTESTED_PAGE, d.total_groups))} of {n(d.total_groups)}</span>
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - CONTESTED_PAGE))}
                className="px-2 py-1 rounded-lg border border-border disabled:opacity-40">Previous</button>
              <button type="button" disabled={offset + CONTESTED_PAGE >= d.total_groups} onClick={() => setOffset(offset + CONTESTED_PAGE)}
                className="px-2 py-1 rounded-lg border border-border disabled:opacity-40">Next</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ContestedCard({ group, canMake }: { group: ContestedGroup; canMake: boolean }) {
  const qc = useQueryClient();
  const [proposeFor, setProposeFor] = useState<ContestedMember | null>(null);
  const [flagging, setFlagging] = useState(false);
  const flag = group.assets.find(a => a.duplicate_flag)?.duplicate_flag ?? null;
  const pending = group.link;
  const after = () => invalidateAfter(qc, group.assets.map(a => a.id));

  return (
    <div className="glass-card rounded-2xl p-4 space-y-3" data-testid={`contested-group-${group.sap.id}`}
         data-flagged={String(group.flagged)}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="text-xs"><SapCell s={group.sap} /></div>
        <div className="flex gap-2 items-start">
          {canMake && !group.flagged && (
            <button type="button" onClick={() => setFlagging(true)} data-testid={`button-flag-${group.sap.id}`}
              className="px-2.5 py-1 text-[11px] font-semibold rounded-lg border border-amber-300 text-amber-800 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/30 inline-flex items-center gap-1">
              <Flag size={11} /> Flag as likely duplicate
            </button>
          )}
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        {group.assets.length} Cadra assets point at this SAP record. One of them may be proposed for the link; the
        others are left unlinked. Nothing is merged, retired or deleted.
      </p>

      {group.flagged && flag && (
        <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2"
             data-testid={`contested-flag-${group.sap.id}`}>
          <Flag size={12} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-800 dark:text-amber-300">
            <span className="font-semibold">Flagged as a likely duplicate</span>
            {flag.note && <>: {flag.note}</>} (by {flag.flagged_by?.name ?? "—"}, {when(flag.flagged_at)})
          </p>
        </div>
      )}

      {pending && (
        <p className="text-[12px] text-amber-800 dark:text-amber-300" data-testid={`contested-pending-${group.sap.id}`}>
          Proposed for <span className="font-semibold">{pending.asset.asset_code ?? `asset ${pending.asset.id}`}</span> by {pending.proposed_by?.name ?? "—"}, {when(pending.proposed_at)} — waiting on the Register Checker.
        </p>
      )}

      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(220px, 1fr))` }}>
        {group.assets.map(a => (
          <div key={a.id} className="rounded-xl border border-border p-3 text-xs space-y-1.5 bg-card"
               data-testid={`contested-asset-${a.id}`}>
            <AssetCell a={a} />
            <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px]">
              <dt className="text-muted-foreground">Custodian</dt><dd>{a.custodian?.name ?? "—"}</dd>
              <dt className="text-muted-foreground">Created</dt><dd>{when(a.created_at)}</dd>
              <dt className="text-muted-foreground">Old tag</dt><dd className="font-mono break-all">{a.old_tag ?? "—"}</dd>
              <dt className="text-muted-foreground">Serial</dt><dd className="font-mono break-all">{a.serial_number ?? "—"}</dd>
              <dt className="text-muted-foreground">Matched by</dt><dd>{a.matched_by === "serial" ? "serial" : "old tag"}</dd>
            </dl>
            <div className="flex gap-1.5 flex-wrap items-center">
              {a.photos.latest.map(p => <Thumb key={p.id} url={p.url} />)}
              {a.photos.count === 0 && <span className="text-[11px] text-muted-foreground">No photos</span>}
              {a.photos.count > a.photos.latest.length && (
                <Link href={`/assets/${a.id}`} className="text-[11px] text-primary hover:underline">
                  +{a.photos.count - a.photos.latest.length} more
                </Link>
              )}
            </div>
            {canMake && !pending && (
              <button type="button" onClick={() => setProposeFor(a)} data-testid={`button-propose-contested-${a.id}`}
                className="mt-1 px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
                Propose this one
              </button>
            )}
          </div>
        ))}
      </div>

      {proposeFor && (
        <NoteDialog
          testid="propose-contested-dialog"
          title={`Propose ${proposeFor.asset_code ?? `asset ${proposeFor.id}`} for SAP asset ${group.sap.asset_number}`}
          description="The Register Checker approves or returns it. The other assets in this group are left unlinked."
          noteLabel="Note for the checker (optional)"
          required={false}
          verb="Propose"
          send={(note) => proposeContested(group.sap.id, proposeFor.id, note)}
          onClose={(done) => { setProposeFor(null); if (done) after(); }}
        />
      )}
      {flagging && (
        <NoteDialog
          testid="flag-group-dialog"
          title={`Flag SAP asset ${group.sap.asset_number}'s group as a likely duplicate`}
          description="A record for NRS on each of these assets. Nothing is merged, retired or deleted, and no SAP number is written."
          noteLabel="Note (required)"
          required
          verb="Flag"
          send={(note) => flagContested(group.sap.id, note)}
          onClose={(done) => { setFlagging(false); if (done) after(); }}
        />
      )}
    </div>
  );
}

function NoteDialog<T>({ testid, title, description, noteLabel, required, verb, send, onClose }: {
  testid: string; title: string; description: string; noteLabel: string; required: boolean; verb: string;
  send: (note: string) => Promise<T>; onClose: (done: boolean) => void;
}) {
  const [note, setNote] = useState("");
  const m = useMutation<T, CadraApiError>({
    mutationFn: () => send(note),
    onSuccess: () => onClose(true),
  });
  const close = () => { if (!m.isPending) onClose(false); };
  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-lg" data-testid={testid}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label htmlFor={`${testid}-note`} className={LABEL}>{noteLabel}</label>
            <textarea id={`${testid}-note`} rows={3} value={note} onChange={e => setNote(e.target.value)}
              className={TEXTAREA} data-testid={`${testid}-note`} />
          </div>
          {m.error && <ErrorPanel err={m.error} testid={`${testid}-error`} />}
        </div>
        <DialogFooter>
          <button type="button" onClick={close}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">Cancel</button>
          <SendButton testid={`${testid}-send`} ready={!required || note.trim().length > 0} pending={m.isPending}
            onClick={() => m.mutate()}>
            {verb}
          </SendButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A photo's thumbnail. The bytes need the bearer token, so an `<img src>`
 *  to the API cannot be used: fetched once as an object URL, let go on
 *  unmount (as `AssetPhotos` does). */
function Thumb({ url }: { url: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    let made: string | null = null;
    fetchPictureObjectUrl({ url, mimetype: null })
      .then((u) => { made = u; if (live) setSrc(u); else URL.revokeObjectURL(u); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [url]);
  return (
    <div className="w-14 h-14 rounded-lg border border-border bg-muted flex items-center justify-center overflow-hidden"
         data-testid="contested-photo">
      {src ? <img src={src} alt="" className="w-full h-full object-cover" />
        : failed ? <ImageIcon size={14} className="text-muted-foreground/50" />
        : <Loader2 size={12} className="animate-spin text-muted-foreground/50" />}
    </div>
  );
}
