/**
 * Register snapshot — a read-only view of `GET /api/v1/reports/asset-register`
 * (handoff 23), given a page by handoff 49: the register AS OF a day, each
 * row rolled back through the append-only record.
 *
 * WHAT THE REPORT SAYS ABOUT ITSELF
 * ---------------------------------
 * The server rolls 35 fields back to `as_of` and gives today's value for the
 * rest; `fidelity` names which are which and since when the rolled-back ones
 * have been tracked, and a row that could not be fully placed carries its own
 * `_fidelity`. This screen offers NO filters on purpose: the route's filters
 * select on CURRENT values while the rows are rolled back (the response's
 * own `filters.note`), so a filtered snapshot reports a different population
 * from the one it selected — the kind of quiet lie this programme keeps
 * finding. One date in, the register out.
 *
 * WHO HAS LEFT, AND STILL HOLDS (handoff 49 §4)
 * ---------------------------------------------
 * Reports 43 and 45 measured 87 of 6,646 held assets on the NRS register
 * (6,644 when re-measured at build time — the 87/59 held exactly)
 * belonging to 59 people who have left, visible nowhere outside our reports.
 * The card below the fidelity block answers it from an endpoint that already
 * exists — `GET /identity/employees?active=false`, each row carrying
 * `assets.count` — so no route changed. It is measured NOW, not as of the
 * selected date: the employee record has no history to roll back. Shown only
 * to holders of `identity:read` (the Auditor is one), because that is what
 * the employees route requires.
 *
 * WHO MAY OPEN IT
 * ---------------
 * Whoever holds `assets:read` — what the server route requires.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import {
  fetchRegisterSnapshot, fetchDepartedHolders,
  type RegisterSnapshotPage, type DepartedHolders,
} from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { cn, formatIsoDate, lagosToday } from "@/lib/utils";
import { AlertCircle, Camera, ChevronDown, ChevronRight, Clock, UserX } from "lucide-react";
import { ScopeRefusal } from "@/components/ScopeRefusal";

// A null is a value the engine has not computed, not a zero — print the dash.
const fmtValue = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 2 });

export default function RegisterSnapshot() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();

  // The Lagos day — the server's "today" and the latest date the route
  // accepts (a future one is its 400).
  const [asOf, setAsOf] = useState(lagosToday);
  const [showDeparted, setShowDeparted] = useState(false);

  useEffect(() => {
    setTitle("Register snapshot");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(asOf) && asOf <= lagosToday();

  const report = useInfiniteQuery<RegisterSnapshotPage, CadraApiError>({
    queryKey: ["register-snapshot", asOf],
    queryFn: ({ pageParam }) => fetchRegisterSnapshot(asOf, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: scopes.has(SCOPE.assetsRead) && validDate,
    staleTime: 30_000,
  });
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = report;

  // §4's count. `identity:read` is the employees route's scope; without it
  // the card is simply absent — the snapshot is complete without it.
  const departed = useQuery<DepartedHolders, CadraApiError>({
    queryKey: ["departed-holders"],
    queryFn: fetchDepartedHolders,
    enabled: scopes.has(SCOPE.identityRead),
    staleTime: 60_000,
  });

  const first = report.data?.pages[0]?.report ?? null;
  const truncated = report.data?.pages[0]?.truncated ?? null;
  const total = report.data?.pages[0]?.totalEstimate ?? null;
  const rows = useMemo(
    () => (report.data?.pages ?? []).flatMap(p => p.report.assets),
    [report.data],
  );

  if (!scopes.has(SCOPE.assetsRead)) return (
    <ScopeRefusal scope="assets:read" detail="The register snapshot reads every asset as it stood on a day — what the register would have said had it been asked then." />
  );

  const error = report.error;

  return (
    <div className="flex flex-col h-full" data-testid="register-snapshot-page">
      {/* The one input: the day */}
      <div className="px-4 sm:px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          As of
          <input type="date" value={asOf} max={lagosToday()} onChange={e => setAsOf(e.target.value)} data-testid="input-as-of"
            className="px-2 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </label>
        <p className="text-[11px] text-muted-foreground">No filters, on purpose: the route's filters select on today's values while the rows are rolled back, so a filtered snapshot would not reconcile.</p>
        {total != null && (
          <p className="ml-auto text-xs text-muted-foreground" data-testid="snapshot-count">
            <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span> of <span className="font-bold text-foreground">{total.toLocaleString()}</span> assets loaded
          </p>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {!validDate ? (
          <p className="p-6 text-xs text-red-700 dark:text-red-400" data-testid="date-invalid">The date is incomplete, or in the future — the register cannot be rolled back to a day that has not happened.</p>
        ) : report.isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <Clock size={20} className="animate-pulse" />
            <p className="text-sm">Rolling the register back to {formatIsoDate(asOf)}…</p>
          </div>
        ) : error ? (
          <div className="p-6 max-w-xl">
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="register-snapshot-error">
              <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <ApiErrorMessage err={error} stacked />
                {!apiConfigured && <p className="text-[11px] mt-1">No active session.</p>}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* What the snapshot can and cannot claim */}
            {first && (
              <div className="px-4 sm:px-5 pt-4 pb-3 space-y-2" data-testid="report-summary">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span>As of <span className="font-semibold text-foreground">{formatIsoDate(first.as_of)}</span> (cutoff {first.cutoff} {first.cutoff_timezone})</span>
                  <span>·</span>
                  <span>{first.fidelity.rolled_back.length} fields rolled back{first.fidelity.tracked_from.since && <>, tracked since {formatIsoDate(first.fidelity.tracked_from.since.slice(0, 10))}</>}</span>
                  <span>·</span>
                  <span>{first.fidelity.as_of_today.length} fields given at today's value</span>
                  {first.omitted_asset_ids.length > 0 && (
                    <><span>·</span><span className="text-amber-700 dark:text-amber-400" data-testid="omitted-note">{first.omitted_asset_ids.length} asset(s) omitted — the record could not place them on this day</span></>
                  )}
                </div>
                {first.fidelity.notes?.deleted_assets && (
                  <p className="text-[11px] text-muted-foreground" data-testid="report-fidelity-note">{first.fidelity.notes.deleted_assets}</p>
                )}
                {truncated && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="report-truncated">
                    Truncated by the server at {truncated.cap.toLocaleString()} of {truncated.total.toLocaleString()} rows: {truncated.reason}
                  </p>
                )}
              </div>
            )}

            {/* Held by people who have left (handoff 49 §4) — measured NOW */}
            {scopes.has(SCOPE.identityRead) && departed.data && (
              <div className="mx-4 sm:mx-5 mb-3 rounded-2xl border border-border bg-card p-4" data-testid="departed-holders-card">
                <div className="flex items-start gap-3">
                  <UserX size={16} className={cn("shrink-0 mt-0.5", departed.data.assetsHeld > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground/50")} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] text-foreground/90" data-testid="departed-holders-sentence">
                      {departed.data.assetsHeld > 0 ? (
                        <>
                          <span className="font-bold">{departed.data.assetsHeld.toLocaleString()}</span> assets still name{" "}
                          <span className="font-bold">{departed.data.people.length.toLocaleString()}</span> people who have left as custodian —{" "}
                          {departed.data.withRetrievalFlagged === 0
                            ? <span className="font-semibold text-amber-700 dark:text-amber-400">none flagged for retrieval</span>
                            : <>{departed.data.withRetrievalFlagged.toLocaleString()} of them with retrieval flagged</>}
                          . ({departed.data.departedSeen.toLocaleString()} departed people on record in all.)
                        </>
                      ) : (
                        <>No assets name a departed person as custodian — of {departed.data.departedSeen.toLocaleString()} departed people on record.</>
                      )}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Measured now, from the employee record (`active = false`), not rolled back to the selected date — the employee record keeps no history to roll back. Counts include any disposed asset still naming the person.</p>
                    {departed.data.people.length > 0 && (
                      <button onClick={() => setShowDeparted(s => !s)} data-testid="button-departed-toggle"
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:opacity-80">
                        {showDeparted ? <ChevronDown size={12} /> : <ChevronRight size={12} />} {showDeparted ? "Hide" : "Show"} the {departed.data.people.length.toLocaleString()} people
                      </button>
                    )}
                    {showDeparted && departed.data.people.length > 0 && (
                      <ul className="mt-2 space-y-0.5" data-testid="departed-holders-list">
                        {[...departed.data.people].sort((a, b) => (b.assets?.count ?? 0) - (a.assets?.count ?? 0)).map(p => (
                          <li key={p.id} className="text-[11px] text-foreground flex flex-wrap items-baseline gap-x-2" data-testid="departed-holder-row">
                            <Link href={`/hr/employees/${p.id}`} className="font-medium hover:text-primary">{p.name}</Link>
                            {p.department?.name && <span className="text-muted-foreground">{p.department.name}</span>}
                            {p.employment?.end_date && <span className="text-muted-foreground">left {formatIsoDate(p.employment.end_date)}</span>}
                            <span className="font-mono">{(p.assets?.count ?? 0).toLocaleString()} asset(s)</span>
                            {p.assets?.has_pending_retrieval && <span className="text-amber-700 dark:text-amber-400">retrieval flagged</span>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            )}
            {scopes.has(SCOPE.identityRead) && departed.error && (
              <p className="mx-4 sm:mx-5 mb-3 text-[11px] text-muted-foreground" data-testid="departed-holders-error">Departed custodians could not be read: <ApiErrorMessage err={departed.error} /></p>
            )}

            {rows.length > 0 && (
              <table className="w-full min-w-[960px]" data-testid="snapshot-table">
                <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                  <tr>
                    {["Code", "Name", "Category", "Location", "Custodian", "State", "Condition", "Book value", "Verified"].map(h => (
                      <th key={h} className="text-left px-3 sm:px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => {
                    const unknown = a._fidelity?.unknown ?? [];
                    const cell = (field: string, v: ReactNode) =>
                      unknown.includes(field)
                        ? <span className="text-muted-foreground italic" title="The record cannot place this field on the selected day.">not recorded then</span>
                        : v ?? <span className="text-muted-foreground">—</span>;
                    return (
                      <tr key={a.id} data-testid="snapshot-row" data-asset-id={a.id} className="border-b border-border/50">
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] font-mono text-muted-foreground whitespace-nowrap">
                          <Link href={`/assets/${a.id}`} className="hover:text-primary" data-testid="snapshot-asset-link">{a.asset_code ?? `#${a.id}`}</Link>
                        </td>
                        <td className="px-3 sm:px-4 py-2.5 text-[12px] text-foreground">{cell("name", a.name)}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground">{cell("category_id", a.category_id?.name)}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground">{cell("location_id", a.location_id?.name)}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] text-foreground">
                          {cell("custodian_id", a.custodian_id?.name)}
                          {a.retrieval_flag && <span className="ml-1 text-[10px] font-semibold text-amber-700 dark:text-amber-400" data-testid="snapshot-retrieval-flag">retrieval</span>}
                        </td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px]">{cell("state", a.state && (
                          <span className={cn("font-semibold px-2 py-0.5 rounded-lg border whitespace-nowrap",
                            a.state === "active" ? "bg-green-50 border-green-200/60 text-green-700 dark:bg-green-950/30 dark:border-green-800/30 dark:text-green-400"
                            : a.state === "disposed" || a.state === "missing" ? "bg-red-50 border-red-200/60 text-red-700 dark:bg-red-950/30 dark:border-red-800/30 dark:text-red-400"
                            : "bg-muted border-border text-muted-foreground")}>
                            {a.state.replace(/_/g, " ")}
                          </span>
                        ))}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground">{cell("condition", a.condition?.replace(/_/g, " "))}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] font-mono text-foreground whitespace-nowrap">{a.value ? fmtValue(a.value.book_value) : "—"}</td>
                        <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground whitespace-nowrap">{cell("last_verified_date", a.last_verified_date && formatIsoDate(a.last_verified_date))}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {hasNextPage && (
              <div className="flex justify-center py-4">
                <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage} data-testid="button-load-more"
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-border bg-card text-foreground hover:bg-muted disabled:opacity-50">
                  {isFetchingNextPage ? "Loading…" : `Load more (${rows.length.toLocaleString()}${total != null ? ` of ${total.toLocaleString()}` : ""})`}
                </button>
              </div>
            )}

            {first && rows.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 gap-2" data-testid="snapshot-empty">
                <Camera size={24} className="text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground" data-testid="snapshot-empty-sentence">The register held no assets on {formatIsoDate(asOf)}.</p>
                <p className="text-[11px] text-muted-foreground max-w-md text-center">An empty register is the tenant's own answer — nothing here is illustrative.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
