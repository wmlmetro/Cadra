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
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "wouter";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchCandidatesPage, fetchReceiptGated, IDENTIFICATION_MODE_SHORT,
  type CandidatesPage, type GateWaitingOn,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import {
  GateActions, REGISTER_STATE_SHORT, REGISTER_STATE_WORDS, WAITING_ON_WORDS,
} from "@/components/GateActions";
import { useScopes, SCOPE, type Scopes } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";
import { AlertCircle, Clock, Inbox } from "lucide-react";

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

function initialFilter(scopes: Scopes): GateWaitingOn | "" {
  try {
    const q = new URLSearchParams(window.location.search).get("waiting_on");
    if (q === "" || q === "all") return "";
    if (q && (WAITING_ON_ORDER as string[]).includes(q)) return q as GateWaitingOn;
  } catch { /* no window in a test renderer */ }
  return ownGate(scopes);
}

export default function Candidates() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const [waitingOn, setWaitingOn] = useState<GateWaitingOn | "">(() => initialFilter(scopes));
  const canRead = scopes.has(SCOPE.candidatesRead);

  useEffect(() => {
    setTitle("Candidates");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const {
    data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery<CandidatesPage, CadraApiError>({
    // The filter is in the key: the API records the domain in the cursor.
    queryKey: ["candidates", waitingOn],
    queryFn: ({ pageParam }) => fetchCandidatesPage(
      pageParam as string | undefined, { waitingOn: waitingOn || undefined }),
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
          {(["", ...WAITING_ON_ORDER] as const).map(k => (
            <button
              key={k || "all"}
              role="tab"
              aria-selected={waitingOn === k}
              onClick={() => setWaitingOn(k)}
              data-testid={`filter-waiting-${k || "all"}`}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl border transition-colors",
                waitingOn === k
                  ? "bg-primary text-white border-primary"
                  : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {k ? WAITING_ON_WORDS[k] : "Anybody"}
              {k && k === mine && <span className="ml-1 opacity-70">(you)</span>}
            </button>
          ))}
          <p className="ml-auto text-[11px] text-muted-foreground" data-testid="candidates-count">
            <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span>
            {total != null && <> of <span className="font-bold text-foreground">{total.toLocaleString()}</span></>}
          </p>
        </div>
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
              {waitingOn ? `Nothing is waiting on the ${WAITING_ON_WORDS[waitingOn]}.` : "No received unit is waiting to join the register."}
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
                <th className="text-left font-semibold px-5 py-2">Unit</th>
                <th className="text-left font-semibold px-3 py-2">State</th>
                <th className="text-left font-semibold px-3 py-2">Mode</th>
                <th className="text-left font-semibold px-3 py-2">PO</th>
                <th className="text-left font-semibold px-3 py-2">GRN</th>
                <th className="text-left font-semibold px-3 py-2">Serial / reference</th>
                <th className="text-left font-semibold px-3 py-2">In state</th>
                <th className="text-left font-semibold px-3 py-2">Waiting on</th>
                <th className="text-left font-semibold px-5 py-2">Your action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b border-border align-top" data-testid={`candidate-row-${r.id}`}
                    data-register-state={r.register_state}>
                  <td className="px-5 py-2.5">
                    <Link href={`/assets/${r.id}`} className="font-semibold text-primary hover:underline">
                      {r.asset_code}
                    </Link>
                    <div className="text-muted-foreground">{r.name}</div>
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
                  <td className="px-3 py-2.5">{r.provenance?.grn_reference ?? "—"}</td>
                  {/* A `record_only` unit has no serial (handoff 59): its
                      reference is what it is known by. */}
                  <td className="px-3 py-2.5">{r.serial_number || r.reference || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground whitespace-nowrap">{ageOf(r.gates?.state_since, now)}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap" data-testid="candidate-waiting">
                    {r.gates?.waiting_on ? WAITING_ON_WORDS[r.gates.waiting_on] : "—"}
                  </td>
                  <td className="px-5 py-2.5">
                    <GateActions row={r} compact />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} />
        {isFetchingNextPage && (
          <p className="py-4 text-center text-[11px] text-muted-foreground">Loading more…</p>
        )}
      </div>
    </div>
  );
}
