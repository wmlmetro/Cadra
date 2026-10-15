/**
 * Candidates — received units that are not yet on the register.
 *
 * Handoff 57, kept by 58. A candidate is an `nrs.asset` whose
 * `register_state` is anything but `registered`; the register itself (every
 * list, count, report, export and the map) hides them by default, so this is
 * the one list that shows them.
 *
 * One list with a *waiting on* filter, not a queue per role (out of scope
 * tonight). The filter opens on the signed-in person's own gate, derived from
 * the scopes their roles give them, so an IAD approver opens on *waiting on
 * IAD approver* without choosing it.
 *
 * Handoff 60 §2 — seventy a day:
 *   - *Waiting on me* is the first tab and the default for anybody holding a
 *     gate: the server's `waiting_on_me`, which lists only units this person
 *     MAY act on (the no-two-gates rule applied). The plain gate tabs still
 *     list everything waiting at that gate, so a barred unit stays findable
 *     there, with its sentence.
 *   - Oldest first (`sort=oldest`, by the time the unit entered its present
 *     state), with the age on every row.
 *   - The search box at the top searches this list on the server (name,
 *     asset code, tag, serial, GRN, PO).
 *   - Checkboxes and a batch action on the IAD officer's, the IAD approver's
 *     and the Register Checker's tabs (`CandidateBatch.tsx`); a paste box on
 *     the Register Maker's; the approver opens what IAD saw from the row.
 *   - On the Tagging tab the asset code is NOT shown: the label's number is
 *     the asset code, and the tagger must read it off the label in hand.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "wouter";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchCandidatesPage, fetchReceiptGated, IDENTIFICATION_MODE_SHORT, GATE_BATCH_MAX,
  type CandidateRow, type CandidatesPage, type GateAction, type GateBatchAnswer, type GateWaitingOn,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import {
  GateActions, REGISTER_STATE_SHORT, REGISTER_STATE_WORDS, WAITING_ON_WORDS,
} from "@/components/GateActions";
import { useScopes, SCOPE, type Scopes } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";
import {
  BatchApproveDialog, BatchResultsDialog, BatchVerifyDialog, PasteRegisterDialog, RowEvidenceDialog,
  invalidateAfterBatch,
} from "@/components/CandidateBatch";
import { AlertCircle, ClipboardPaste, Clock, Inbox, Paperclip } from "lucide-react";

const WAITING_ON_ORDER: GateWaitingOn[] = [
  "store", "iad", "iad_approver", "controller", "tagging", "maker", "checker",
];

/**
 * The gate this person keeps. Most specific first: somebody holding a gate
 * scope is shown that gate even if they also hold `assets:write`. A wildcard
 * administrator holds every gate and is shown all of them — choosing one for
 * them would hide the rest.
 */
export function ownGate(scopes: Scopes): GateWaitingOn | "" {
  if (scopes.isAdmin) return "";
  if (scopes.has(SCOPE.registerCheck)) return "checker";
  if (scopes.has(SCOPE.registerMake)) return "maker";
  if (scopes.has(SCOPE.vfmApprove)) return "iad_approver";
  if (scopes.has(SCOPE.vfmVerify)) return "iad";
  if (scopes.has(SCOPE.taggingRequest)) return "controller";
  if (scopes.has(SCOPE.taggingWrite)) return "tagging";
  if (scopes.has(SCOPE.assetsWrite)) return "store";
  return "";
}

/** A tab: a gate, `""` for everybody, or `"mine"` — waiting on an act this
 *  person may do. */
type Filter = GateWaitingOn | "" | "mine";

/** Whether this person keeps any gate — then the page opens on *Waiting on
 *  me*. The gate scopes, and nothing else; the wildcard holds them all. */
function holdsAGate(scopes: Scopes): boolean {
  return [
    SCOPE.assetsWrite, SCOPE.vfmVerify, SCOPE.vfmApprove, SCOPE.taggingRequest,
    SCOPE.taggingWrite, SCOPE.registerMake, SCOPE.registerCheck,
  ].some(s => scopes.has(s));
}

/** The batch on each gate's tab (handoff 60 §2b, §2d). The maker's batch is
 *  the paste box, not a selection. */
const BATCH_FOR: Partial<Record<GateWaitingOn, "submit" | "verify" | "approve" | "request-tagging" | "approve-registration">> = {
  // Handoff 61 (ruling 5 on report 60): the two gates that were still two
  // clicks a unit. A selection may mix receipts for these two.
  store: "submit",
  iad: "verify",
  iad_approver: "approve",
  controller: "request-tagging",
  checker: "approve-registration",
};

/** "3 h", "2 d" — how long the unit has sat in its current state. The
 *  server's datetimes are UTC with no zone. */
function ageOf(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const t = Date.parse(iso.endsWith("Z") || iso.includes("+") ? iso : iso.replace(" ", "T") + "Z");
  if (Number.isNaN(t)) return "—";
  const mins = Math.max(0, Math.round((now - t) / 60_000));
  if (mins < 60) return `${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}

function initialFilter(scopes: Scopes): Filter {
  try {
    const q = new URLSearchParams(window.location.search).get("waiting_on");
    if (q === "" || q === "all") return "";
    if (q === "mine") return "mine";
    if (q && (WAITING_ON_ORDER as string[]).includes(q)) return q as GateWaitingOn;
  } catch { /* no window in a test renderer */ }
  return holdsAGate(scopes) ? "mine" : "";
}

export default function Candidates() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const [waitingOn, setWaitingOn] = useState<Filter>(() => initialFilter(scopes));
  const canRead = scopes.has(SCOPE.candidatesRead);
  const qc = useQueryClient();

  // The top bar's search box, on this list (handoff 60 §2a). Debounced a
  // little: every keystroke is a server search.
  // Starts from `?q=`, so Back from an asset opened here returns to the
  // same search — in the list AND in the box (the box is seeded with it).
  const [initialQ] = useState(() => {
    try { return new URLSearchParams(window.location.search).get("q") ?? ""; }
    catch { return ""; }
  });
  const [typed, setTyped] = useState(initialQ);
  const [search, setSearch] = useState(initialQ.trim());
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(typed.trim()), 250);
    return () => window.clearTimeout(t);
  }, [typed]);

  useEffect(() => {
    setTitle("Candidates");
    setSearchHandler((q) => setTyped(q), initialQ);
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler, initialQ]);

  const {
    data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery<CandidatesPage, CadraApiError>({
    // The filter, search and order are in the key: the API records the
    // domain and the walk direction in the cursor.
    queryKey: ["candidates", waitingOn, search, "oldest"],
    queryFn: ({ pageParam }) => fetchCandidatesPage(pageParam as string | undefined, {
      waitingOn: waitingOn && waitingOn !== "mine" ? waitingOn : undefined,
      waitingOnMe: waitingOn === "mine" || undefined,
      q: search || undefined,
      sort: "oldest",
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 15_000,
    enabled: canRead,
  });
  const rows = useMemo(() => (data?.pages ?? []).flatMap(p => p.rows), [data]);
  const total = data?.pages[0]?.totalEstimate ?? null;

  const gated = useQuery({
    queryKey: ["receipt-gated"],
    queryFn: fetchReceiptGated,
    staleTime: 5 * 60_000,
    enabled: canRead,
  });

  // A selection belongs to the list it was made on: a new tab or a new
  // search starts with none.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  useEffect(() => { setSelected(new Set()); }, [waitingOn, search]);
  const [batchOpen, setBatchOpen] = useState<"submit" | "verify" | "approve" | "request-tagging" | "approve-registration" | "paste" | null>(null);
  // The units a batch dialog acts on are taken WHEN IT OPENS: a refresh
  // behind it must not change what the person is confirming.
  const [batchRows, setBatchRows] = useState<CandidateRow[]>([]);
  const [answer, setAnswer] = useState<GateBatchAnswer | null>(null);
  const [evidenceFor, setEvidenceFor] = useState<CandidateRow | null>(null);

  // Re-render the ages once a minute; nothing is refetched by it.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(t);
  }, []);

  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    }, { root: scrollRef.current, rootMargin: "400px" });
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (!canRead) {
    return <ScopeRefusal scope={SCOPE.candidatesRead}
      detail="IAD, the Asset Controller, the Register Maker and Checker, Asset Users and Auditors hold it." />;
  }

  const mine = ownGate(scopes);
  // Whose gate this tab is: the tab's own, or on *Waiting on me* the
  // person's. The batch, the hidden code and the checker's columns follow it.
  const tabGate: GateWaitingOn | "" = waitingOn === "mine" ? mine : waitingOn;
  const batchAction = tabGate ? BATCH_FOR[tabGate] : undefined;
  const hideCodeOn = (r: CandidateRow) =>
    waitingOn === "tagging" || (waitingOn === "mine" && r.gates?.waiting_on === "tagging");
  const showChecker = tabGate === "checker";
  const showPaste = tabGate === "maker" && scopes.has(SCOPE.registerMake);
  const selectable = (r: CandidateRow) => !!batchAction
    && (r.gates?.available ?? []).some(a => a.action === (batchAction as GateAction) && a.can_fire);
  const selectableRows = rows.filter(selectable);
  const selectedRows = rows.filter(r => selected.has(r.id) && selectable(r));
  const allVisibleSelected = selectableRows.length > 0 && selectableRows.every(r => selected.has(r.id));
  const toggle = (id: number) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  /** One click selects every unit of a receipt that is shown and can be
   *  acted on — the selection one verification covers. */
  const selectReceipt = (grn: string) =>
    setSelected(new Set(selectableRows.filter(r => r.provenance?.grn_reference === grn).map(r => r.id)));
  const tabValue = waitingOn || "all";
  const openBatch = (which: "submit" | "verify" | "approve" | "request-tagging" | "approve-registration") => {
    setBatchRows(selectedRows);
    setBatchOpen(which);
  };
  const finished = (a: GateBatchAnswer) => {
    setBatchOpen(null);
    setSelected(new Set());
    setAnswer(a);
    invalidateAfterBatch(qc, a);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-border bg-card">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-[14px] font-bold text-foreground">Candidates</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Received units that are not yet on the register. A unit joins the register when
              IAD has verified and approved it, it is tagged, and a maker and a checker have registered it.
            </p>
          </div>
          {gated.data === false && (
            <div className="text-[11px] rounded-xl border px-3 py-2 bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-300 border-amber-200/70 dark:border-amber-800/30"
                 data-testid="receipt-gated-off">
              <span className="font-semibold">Receipt gating is switched OFF</span> on this register —
              new receipts go straight onto the register. Only units received while it was on are listed here.
            </div>
          )}
        </div>

        <div className="flex gap-1 mt-3 flex-wrap items-center" role="tablist" aria-label="Waiting on">
          <span className="text-[11px] text-muted-foreground mr-1">Waiting on</span>
          {([...(holdsAGate(scopes) ? ["mine" as const] : []), "", ...WAITING_ON_ORDER] as Filter[]).map(k => (
            <button
              key={k || "all"}
              role="tab"
              aria-selected={waitingOn === k}
              onClick={() => setWaitingOn(k)}
              data-testid={`filter-waiting-${k || "all"}`}
              title={k === "mine" ? "Only the units you may act on now" : undefined}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl border transition-colors",
                waitingOn === k
                  ? "bg-primary text-white border-primary"
                  : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {k === "mine" ? "Waiting on me" : k ? WAITING_ON_WORDS[k] : "Anybody"}
              {k && k !== "mine" && k === mine && <span className="ml-1 opacity-70">(you)</span>}
            </button>
          ))}
          <p className="ml-auto text-[11px] text-muted-foreground" data-testid="candidates-count">
            <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span>
            {total != null && <> of <span className="font-bold text-foreground">{total.toLocaleString()}</span></>}
            {search && <> matching “{search}”</>}
            <span className="ml-1">· oldest first</span>
          </p>
        </div>

        {(batchAction || showPaste) && (
          <div className="flex gap-2 mt-2 flex-wrap items-center" data-testid="batch-bar">
            {batchAction && (<>
              <span className="text-[11px] text-muted-foreground" data-testid="batch-selected-count">
                <span className="font-bold text-foreground">{selectedRows.length}</span> selected
              </span>
              {batchAction === "verify" && (
                <BatchButton testid="button-batch-verify" n={selectedRows.length} onClick={() => openBatch("verify")}>
                  Verify selected
                </BatchButton>
              )}
              {batchAction === "submit" && (
                <BatchButton testid="button-batch-submit" n={selectedRows.length} onClick={() => openBatch("submit")}>
                  Submit selected
                </BatchButton>
              )}
              {batchAction === "approve" && (
                <BatchButton testid="button-batch-approve" n={selectedRows.length} onClick={() => openBatch("approve")}>
                  Approve selected
                </BatchButton>
              )}
              {batchAction === "request-tagging" && (
                <BatchButton testid="button-batch-request-tagging" n={selectedRows.length}
                  onClick={() => openBatch("request-tagging")}>
                  Request tagging for selected
                </BatchButton>
              )}
              {batchAction === "approve-registration" && (
                <BatchButton testid="button-batch-approve-registration" n={selectedRows.length}
                  onClick={() => openBatch("approve-registration")}>
                  Approve selected
                </BatchButton>
              )}
              {selectedRows.length > 0 && (
                <button type="button" onClick={() => setSelected(new Set())}
                  className="text-[11px] text-muted-foreground hover:text-foreground" data-testid="button-clear-selection">
                  Clear
                </button>
              )}
              {selectedRows.length > GATE_BATCH_MAX && (
                <span className="text-[11px] text-amber-700 dark:text-amber-400">
                  A batch takes at most {GATE_BATCH_MAX} units.
                </span>
              )}
              <span className="text-[11px] text-muted-foreground">
                {batchAction === "verify"
                  ? "One verification covers one receipt: click a GRN to select its units, or type the GRN into the search box at the top."
                  : "Only units you may act on can be selected; a unit the rules bar you from says why in its row."}
              </span>
            </>)}
            {showPaste && (
              <button type="button" onClick={() => setBatchOpen("paste")} data-testid="button-paste-sap"
                className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 inline-flex items-center gap-1.5">
                <ClipboardPaste size={13} /> Paste SAP codes
              </button>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-start gap-2" data-testid="candidates-error">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={error} />
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
            <p className="text-sm text-muted-foreground">Loading candidates…</p>
          </div>
        ) : rows.length === 0 && !error ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 px-6 text-center" data-testid="candidates-empty">
            <Inbox size={24} className="text-muted-foreground/30" />
            <p className="text-sm font-semibold">
              {search
                ? `No unit on this tab matches “${search}”.`
                : waitingOn === "mine"
                  ? "Nothing is waiting on you."
                  : waitingOn ? `Nothing is waiting on the ${WAITING_ON_WORDS[waitingOn]}.` : "No received unit is waiting to join the register."}
            </p>
            {waitingOn && (
              <p className="text-xs text-muted-foreground max-w-md">
                Another gate may have units waiting — try <button className="text-primary font-semibold hover:underline" onClick={() => setWaitingOn("")}>Anybody</button>.
              </p>
            )}
          </div>
        ) : (
          <table className="w-full text-xs" data-testid="candidates-table">
            <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground sticky top-0">
              <tr>
                {batchAction && (
                  <th className="pl-5 pr-1 py-2 w-6">
                    <input
                      type="checkbox"
                      className="accent-primary"
                      aria-label="Select every unit shown that you may act on"
                      title="Select every unit shown that you may act on"
                      checked={allVisibleSelected}
                      disabled={selectableRows.length === 0}
                      onChange={e => setSelected(e.target.checked ? new Set(selectableRows.map(r => r.id)) : new Set())}
                      data-testid="select-all-visible"
                    />
                  </th>
                )}
                <th className={cn("text-left font-semibold py-2", batchAction ? "px-3" : "px-5")}>
                  Unit
                  {waitingOn === "tagging" && (
                    <span className="block normal-case tracking-normal font-normal" data-testid="unit-code-hidden">
                      code hidden — read it off the label
                    </span>
                  )}
                </th>
                <th className="text-left font-semibold px-3 py-2">State</th>
                <th className="text-left font-semibold px-3 py-2">Mode</th>
                <th className="text-left font-semibold px-3 py-2">PO</th>
                <th className="text-left font-semibold px-3 py-2">GRN</th>
                <th className="text-left font-semibold px-3 py-2">Serial / reference</th>
                {showChecker && (<>
                  <th className="text-left font-semibold px-3 py-2">SAP code</th>
                  <th className="text-right font-semibold px-3 py-2">Cost</th>
                  <th className="text-left font-semibold px-3 py-2">Cost centre</th>
                  <th className="text-left font-semibold px-3 py-2">Class</th>
                </>)}
                <th className="text-left font-semibold px-3 py-2" title="How long the unit has been in its present state. Oldest first.">
                  In state ↓
                </th>
                <th className="text-left font-semibold px-3 py-2">Waiting on</th>
                <th className="text-left font-semibold px-5 py-2">Your action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const canSelect = selectable(r);
                const hidden = hideCodeOn(r);
                const reg = r.gates?.registration;
                const grn = r.provenance?.grn_reference;
                // Back from the asset returns to this tab (the asset page
                // reads `from` and `tab`).
                const href = `/assets/${r.id}?from=candidates&tab=${encodeURIComponent(tabValue)}`
                  + (search ? `&q=${encodeURIComponent(search)}` : "");
                return (
                <tr key={r.id} className={cn("border-b border-border align-top", selected.has(r.id) && canSelect && "bg-primary/5")}
                    data-testid={`candidate-row-${r.id}`}
                    data-register-state={r.register_state}>
                  {batchAction && (
                    <td className="pl-5 pr-1 py-2.5 w-6">
                      {canSelect && (
                        <input
                          type="checkbox"
                          className="accent-primary"
                          aria-label={`Select ${hidden ? r.name : r.asset_code}`}
                          checked={selected.has(r.id)}
                          onChange={() => toggle(r.id)}
                          data-testid={`select-row-${r.id}`}
                        />
                      )}
                    </td>
                  )}
                  <td className={cn("py-2.5", batchAction ? "px-3" : "px-5")}>
                    {hidden ? (
                      // The tagger reads the code off the label in hand
                      // (handoff 60 §2c ruling): the row names the unit only.
                      <Link href={href} className="font-semibold text-primary hover:underline" data-testid="candidate-name-link">
                        {r.name}
                      </Link>
                    ) : (<>
                      <Link href={href} className="font-semibold text-primary hover:underline">
                        {r.asset_code}
                      </Link>
                      <div className="text-muted-foreground">{r.name}</div>
                    </>)}
                  </td>
                  <td className="px-3 py-2.5" title={REGISTER_STATE_WORDS[r.register_state]}>
                    <span className={cn(
                      "inline-block px-2 py-0.5 rounded-lg border text-[11px] font-semibold",
                      r.register_state === "vfm_rejected"
                        ? "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-800/40"
                        : r.register_state === "vfm_query"
                          ? "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40"
                          : "bg-muted text-foreground border-border",
                    )} data-testid="candidate-state">
                      {REGISTER_STATE_SHORT[r.register_state] ?? r.register_state}
                    </span>
                  </td>
                  {/* The mode the unit was RECEIVED under (handoff 58), fixed
                      on the unit; a dash for one received before 58, which
                      the server publishes as null rather than guessing. */}
                  <td className="px-3 py-2.5 text-muted-foreground" data-testid="candidate-mode">
                    {r.identification_mode ? IDENTIFICATION_MODE_SHORT[r.identification_mode] : "—"}
                  </td>
                  <td className="px-3 py-2.5">{r.provenance?.purchase_order_reference ?? "—"}</td>
                  <td className="px-3 py-2.5">
                    {grn && batchAction === "verify" && canSelect ? (
                      <button type="button" onClick={() => selectReceipt(grn)}
                        className="text-primary hover:underline text-left"
                        title="Select every unit of this receipt shown here that you may verify"
                        data-testid={`select-receipt-${r.id}`}>
                        {grn}
                      </button>
                    ) : (grn ?? "—")}
                  </td>
                  {/* A `record_only` unit has no serial (handoff 59): its
                      reference is what it is known by. */}
                  <td className="px-3 py-2.5">{r.serial_number || r.record_reference || "—"}</td>
                  {showChecker && (<>
                    <td className="px-3 py-2.5 font-mono" data-testid={`checker-sap-${r.id}`}>{reg?.sap_asset_code ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap" data-testid={`checker-cost-${r.id}`}>
                      {typeof reg?.cost === "number" ? `₦${reg.cost.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}
                    </td>
                    <td className="px-3 py-2.5" data-testid={`checker-cost-centre-${r.id}`}>{reg?.cost_centre ?? "—"}</td>
                    <td className="px-3 py-2.5" data-testid={`checker-class-${r.id}`}>
                      {reg?.asset_class ? (<>
                        {reg.asset_class.name}
                        <span className="block text-muted-foreground">
                          {reg.asset_class.sap_asset_class ? <>SAP class <span className="font-mono">{reg.asset_class.sap_asset_class}</span></> : "No SAP class"}
                        </span>
                      </>) : "—"}
                    </td>
                  </>)}
                  <td className="px-3 py-2.5 text-foreground font-semibold whitespace-nowrap" data-testid="candidate-age">{ageOf(r.gates?.state_since, now)}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap" data-testid="candidate-waiting">
                    {r.gates?.waiting_on ? WAITING_ON_WORDS[r.gates.waiting_on] : "—"}
                  </td>
                  <td className="px-5 py-2.5">
                    <GateActions row={r} compact />
                    {r.gates?.waiting_on === "iad_approver" && (
                      <button type="button" onClick={() => setEvidenceFor(r)}
                        className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                        data-testid={`button-row-evidence-${r.id}`}>
                        <Paperclip size={11} /> Evidence
                      </button>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} />
        {isFetchingNextPage && (
          <p className="py-4 text-center text-[11px] text-muted-foreground">Loading more…</p>
        )}
      </div>

      {batchOpen === "verify" && (
        <BatchVerifyDialog rows={batchRows} onClose={() => setBatchOpen(null)} onDone={finished} />
      )}
      {(batchOpen === "submit" || batchOpen === "approve" || batchOpen === "request-tagging"
        || batchOpen === "approve-registration") && (
        <BatchApproveDialog action={batchOpen} rows={batchRows} onClose={() => setBatchOpen(null)} onDone={finished} />
      )}
      {batchOpen === "paste" && <PasteRegisterDialog onClose={() => setBatchOpen(null)} />}
      {answer && <BatchResultsDialog answer={answer} onClose={() => setAnswer(null)} />}
      {evidenceFor && <RowEvidenceDialog row={evidenceFor} onClose={() => setEvidenceFor(null)} />}
    </div>
  );
}

/** "Verify selected (N)" — disabled with nothing selected. */
function BatchButton({ testid, n, onClick, children }: {
  testid: string; n: number; onClick: () => void; children: React.ReactNode;
}) {
  const ready = n > 0 && n <= GATE_BATCH_MAX;
  return (
    <button type="button" disabled={!ready} onClick={onClick} data-testid={testid}
      className={cn(
        "px-3 py-1.5 text-xs font-semibold rounded-xl transition-colors",
        ready ? "bg-primary text-primary-foreground hover:bg-primary/90" : "bg-muted text-muted-foreground cursor-not-allowed",
      )}>
      {children} ({n})
    </button>
  );
}
