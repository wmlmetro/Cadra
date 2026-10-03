import { useState, useEffect, useMemo, useRef } from "react";
import { useLocation } from "wouter";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchRequestsPage, type RequestsPage, type RequestFilters } from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { useEnum, useEnumLabel } from "@/hooks/useEnums";
import {
  Search, X, Inbox, Clock, AlertCircle,
  ArrowUpRight, ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

// PRIORITY_LABEL used to be declared here as
// {"0":"Low","1":"Normal","2":"Normal","3":"High","4":"Urgent"} — two entries
// reading "Normal", and 2/3/4 all naming the wrong level. The model is
// 0=Low, 1=Normal, 2=High, 3=Critical, 4=Very Urgent. Labels now come from
// the model via GET /api/v1/meta/enums (useEnumLabel below); a local copy of
// a set the back end owns is exactly what drifted, silently, in five places.

// The COLOURS stay local, because severity styling is this front end's own
// choice and not something the API publishes. What was wrong about them was
// the severity they encoded: "2" was painted the same calm blue as "1" while
// it is in fact High, so the one badge on the list that should pull the eye
// did not. Re-keyed to the model's real scale.
const PRIORITY_COLOR: Record<string, string> = {
  // Low — recedes; nothing to act on.
  "0": "text-muted-foreground border-border bg-muted",
  // Normal — the resting state of most of the desk.
  "1": "text-blue-700 dark:text-blue-400 border-blue-200/70 bg-blue-50 dark:bg-blue-950/30",
  // High.
  "2": "text-amber-700 dark:text-amber-400 border-amber-200/70 bg-amber-50 dark:bg-amber-950/30",
  // Critical.
  "3": "text-red-700 dark:text-red-400 border-red-200/70 bg-red-50 dark:bg-red-950/30",
  // Very Urgent — the top of the scale, and it has to be tellable apart from
  // Critical at a glance, so it carries the heavier weight and the ring.
  "4": "text-red-800 dark:text-red-300 border-red-400 dark:border-red-700 bg-red-100 dark:bg-red-900/50 ring-1 ring-red-400/60 font-extrabold",
};

// An unknown key falls back to the muted style, not to "2". A value the model
// gains before this build would otherwise be painted High on no evidence.
const PRIORITY_COLOR_UNKNOWN = "text-muted-foreground border-border bg-muted";

const STAGE_COLOR: Record<string, string> = {
  draft:        "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300",
  new:          "bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400",
  assigned:     "bg-purple-50 dark:bg-purple-950/30 text-purple-700 dark:text-purple-400",
  in_progress:  "bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400",
  resolved:     "bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400",
  closed:       "bg-muted text-muted-foreground",
  rejected:     "bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400",
};

export interface RequestsListProps {
  /** Optional pre-set filters that the user can't change. Used by TriageInbox/MyJobs. */
  presetFilters?: RequestFilters;
  /** Page title + header */
  title?: string;
  subtitle?: string;
}

export default function RequestsList({
  presetFilters,
  title = "All Requests",
  subtitle = "Every service request across the desk",
}: RequestsListProps = {}) {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  // Handoff 46: *New Request* opens a form whose one purpose is
  // `POST /requests`, which needs `requests:write`.
  const scopes = useScopes();
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [closedFilter, setClosedFilter] = useState<"open" | "closed" | "">("open");

  // Both are hooks and must be called here, at the top of the component — the
  // badge below renders inside a .map() and uses the returned lookup function,
  // never the hook itself.
  const priorityOpts = useEnum("priority");
  const priorityLabel = useEnumLabel("priority");

  useEffect(() => {
    setTitle(title);
    setSearchHandler(q => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler, title]);

  const filters: RequestFilters = useMemo(() => ({
    ...presetFilters,
    search: search || undefined,
    priority: priority || undefined,
    closed: closedFilter === "" ? undefined : closedFilter === "closed",
  }), [presetFilters, search, priority, closedFilter]);

  const {
    data, isLoading, error,
    fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery<RequestsPage, CadraApiError>({
    queryKey: ["requests", filters],
    queryFn: ({ pageParam }) => fetchRequestsPage(pageParam as string | undefined, filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 30_000,
  });

  const requests = useMemo(() => (data?.pages ?? []).flatMap(p => p.requests), [data]);
  const total = data?.pages[0]?.totalEstimate ?? requests.length;

  // Infinite-scroll sentinel
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    }, { root: scrollRef.current ?? null, rootMargin: "200px" });
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const clearFilters = () => { setSearch(""); setPriority(""); setClosedFilter("open"); };
  const hasFilter = !!(search || priority || closedFilter !== "open");

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-border bg-card flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-[14px] font-bold text-foreground">{title}</h1>
          <p className="text-[11px] text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        {scopes.has(SCOPE.requestsWrite) && (
          <button
            onClick={() => nav("/service-desk/new")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
          >
            + New Request
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Reference, subject, body…"
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background w-56"
          />
        </div>
        <select value={priority} onChange={e => setPriority(e.target.value)} className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background">
          <option value="">Any priority</option>
          {/* Model order, ascending, as the Selection declares it. The old list
              was hand-sorted Urgent-first on top of labels that were wrong. */}
          {priorityOpts.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={closedFilter} onChange={e => setClosedFilter(e.target.value as typeof closedFilter)} className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background">
          <option value="open">Open only</option>
          <option value="closed">Closed only</option>
          <option value="">All</option>
        </select>
        {hasFilter && (
          <button onClick={clearFilters} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5">
            <X size={12} /> Clear
          </button>
        )}
        <p className="ml-auto text-xs text-muted-foreground">
          <span className="font-bold text-foreground">{requests.length.toLocaleString()}</span> of <span className="font-bold text-foreground">{total.toLocaleString()}</span> requests
        </p>
      </div>

      {error && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-center gap-2">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0" />
          <p className="text-[11px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{error.code}:</span> {error.message}
            {!apiConfigured && " (set VITE_API_TOKEN in .env.local)"}
          </p>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && requests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
            <p className="text-sm text-muted-foreground">Loading requests…</p>
          </div>
        ) : requests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Inbox size={24} className="text-muted-foreground/30" />
            <p className="text-sm font-semibold">No requests match these filters.</p>
            {hasFilter && <button onClick={clearFilters} className="text-xs text-primary hover:opacity-80">Clear filters</button>}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {requests.map(r => (
              <li key={r.id}>
                <button
                  onClick={() => nav(`/service-desk/${r.id}`)}
                  className="w-full text-left px-5 py-3 hover:bg-muted/30 flex items-center gap-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[12px] font-mono font-semibold text-foreground">{r.reference}</span>
                      <span className={cn(
                        "text-[10px] font-semibold px-2 py-0.5 rounded-lg",
                        STAGE_COLOR[r.stageCode ?? ""] ?? "bg-muted text-muted-foreground",
                      )}>{r.stageName}</span>
                      <span className={cn(
                        "text-[10px] font-bold px-2 py-0.5 rounded-lg border",
                        PRIORITY_COLOR[r.priority] ?? PRIORITY_COLOR_UNKNOWN,
                      )}>{priorityLabel(r.priority) || "—"}</span>
                      {r.assignee && (
                        <span className="text-[10px] text-muted-foreground">→ {r.assignee.name}</span>
                      )}
                    </div>
                    <p
                      className="text-[12px] text-muted-foreground mt-0.5 truncate"
                      dangerouslySetInnerHTML={{ __html: r.subject || r.requestText.slice(0, 200) }}
                    />
                  </div>
                  <ArrowUpRight size={12} className="text-muted-foreground/40 shrink-0" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {hasNextPage && (
          <div ref={sentinelRef} className="py-5 text-center">
            {isFetchingNextPage ? (
              <div className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <Clock size={12} className="animate-pulse" /> Loading more…
              </div>
            ) : (
              <button onClick={() => fetchNextPage()} className="text-xs text-primary hover:opacity-80">Load more</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function TriageInbox() {
  return <RequestsList
    title="Triage Inbox"
    subtitle="Unassigned + open requests, prioritized by SLA"
    presetFilters={{ closed: false }}
  />;
}
