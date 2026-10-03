/**
 * Configuration changes — a read-only view of
 * `GET /api/v1/reports/configuration-changes` (handoff 23), given a page by
 * handoff 49. Nothing on this page changes anything; the only inputs are the
 * two period dates.
 *
 * WHAT THE REPORT SAYS ABOUT ITSELF
 * ---------------------------------
 * The report is LAST-WRITE-ONLY by its own admission: `ir.config_parameter`
 * keeps no history, so a key changed five times is one row showing the
 * fifth, and a deleted key leaves no tombstone. `summary.statement` and the
 * fidelity notes are rendered ABOVE the table for the same reason the
 * access-changes screen renders them there — an empty table and a record
 * that cannot say are different facts, and only the statement tells them
 * apart. A value whose key names a credential arrives `[redacted] sha256:…`
 * from the server; this screen never sees the secret, let alone shows it.
 *
 * WHO MAY OPEN IT
 * ---------------
 * Whoever holds `settings:read` — what the server route requires: the
 * Auditor, the Asset Manager and administrators.
 */
import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { fetchConfigurationChanges, type ConfigurationChangesPage } from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { cn, formatIsoDateTime, lagosToday } from "@/lib/utils";
import type { ConfigurationChangeRow } from "@/types";
import { AlertCircle, Clock, FileCog } from "lucide-react";
import { ScopeRefusal } from "@/components/ScopeRefusal";

/** An actor of `__system__` (uid 1, OdooBot) means a module install, a cron
 *  or the command line — a real change, but not somebody's decision. The
 *  report's own `system_actor` note says exactly this. */
function writerWords(by: { id: number; name: string } | null): string {
  if (!by) return "—";
  if (by.id === 1 || by.name === "__system__" || by.name === "OdooBot") return "system";
  return by.name;
}

export default function AdminConfigurationChanges() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();

  // The same default window as Access changes: the whole of the current era
  // in view without anybody typing a date. `to` is the LAGOS day — the
  // server's definition of today, not the browser's (report 29's one-hour-a-
  // night bug, and this is a screen about dates the server filtered on).
  const [from, setFrom] = useState("2026-01-01");
  const [to, setTo] = useState(lagosToday);

  useEffect(() => {
    setTitle("Configuration changes");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const validPeriod = /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to;

  const report = useInfiniteQuery<ConfigurationChangesPage, CadraApiError>({
    queryKey: ["configuration-changes", from, to],
    queryFn: ({ pageParam }) => fetchConfigurationChanges(from, to, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: scopes.has(SCOPE.settingsRead) && validPeriod,
    staleTime: 30_000,
  });
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = report;
  const pagesLoaded = report.data?.pages.length ?? 0;

  // Auto-walk: the population is the tenant's parameter table — dozens to a
  // few hundred rows — so every page, in order, until the cursor runs out.
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, pagesLoaded]);

  const first = report.data?.pages[0]?.report ?? null;
  const truncated = report.data?.pages[0]?.truncated ?? null;
  const totalParams = report.data?.pages[0]?.totalEstimate ?? first?.summary.parameters_in_period ?? null;

  // Last written first: the question an auditor opens this page with is
  // "what changed lately", and the server's order (ascending id) is for
  // paging, not reading.
  const rows = useMemo(() => {
    const all = (report.data?.pages ?? []).flatMap(p => p.report.parameters);
    return [...all].sort((a, b) => {
      const x = a.last_written_at ?? "", y = b.last_written_at ?? "";
      return x < y ? 1 : x > y ? -1 : a.key.localeCompare(b.key);
    });
  }, [report.data]);

  if (!scopes.has(SCOPE.settingsRead)) return (
    <ScopeRefusal scope="settings:read" detail="The record of this tenant's configuration — every recoverable parameter, who last wrote it and when — is read by the Auditor, the Asset Manager and system administrators." />
  );

  const walking = hasNextPage || isFetchingNextPage;
  const error = report.error;

  return (
    <div className="flex flex-col h-full" data-testid="configuration-changes-page">
      {/* Period */}
      <div className="px-4 sm:px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          From
          <input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} data-testid="input-period-from"
            className="px-2 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          To
          <input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} data-testid="input-period-to"
            className="px-2 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </label>
        <p className="ml-auto text-xs text-muted-foreground inline-flex items-center gap-1.5" data-testid="parameters-count">
          <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span> parameters
          {walking && totalParams != null && (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/70" data-testid="walk-progress">
              <Clock size={9} className="animate-pulse" /> reading {rows.length.toLocaleString()}/{totalParams.toLocaleString()}…
            </span>
          )}
        </p>
      </div>

      <div className="flex-1 overflow-auto">
        {!validPeriod ? (
          <p className="p-6 text-xs text-red-700 dark:text-red-400" data-testid="period-invalid">The period ends before it starts, or a date is incomplete.</p>
        ) : report.isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <Clock size={20} className="animate-pulse" />
            <p className="text-sm">Reading the configuration record…</p>
          </div>
        ) : error ? (
          <div className="p-6 max-w-xl">
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="configuration-changes-error">
              <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <ApiErrorMessage err={error} stacked />
                {!apiConfigured && <p className="text-[11px] mt-1">No active session.</p>}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* The report's own statement about what it can and cannot say */}
            {first && (
              <div className="px-4 sm:px-5 pt-4 pb-3 space-y-2" data-testid="report-summary">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span>
                    Precision: <span className="font-semibold uppercase text-foreground" data-testid="report-coverage">{first.summary.coverage}</span>
                  </span>
                  <span>·</span>
                  <span>{first.summary.parameters_in_period.toLocaleString()} parameters in the period</span>
                  <span>·</span>
                  <span>{first.summary.modified_after_create.toLocaleString()} modified after creation</span>
                  <span>·</span>
                  <span>{first.summary.modified_by_a_named_user.toLocaleString()} by a named user, {first.summary.modified_by_system.toLocaleString()} by the system</span>
                  <span>·</span>
                  <span>{first.summary.redacted_values.toLocaleString()} values redacted</span>
                </div>
                <p className="text-[12px] text-foreground/90" data-testid="report-statement">{first.summary.statement}</p>
                {first.fidelity.notes?.deleted_keys && (
                  <p className="text-[11px] text-muted-foreground" data-testid="report-fidelity-note">{first.fidelity.notes.deleted_keys}</p>
                )}
                {truncated && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="report-truncated">
                    Truncated by the server at {truncated.cap.toLocaleString()} of {truncated.total.toLocaleString()} rows: {truncated.reason}
                  </p>
                )}
              </div>
            )}

            <table className="w-full min-w-[720px]" data-testid="parameters-table">
              <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                <tr>
                  {["Key", "Current value", "Changed", "Last written", "By whom", "Created"].map(h => (
                    <th key={h} className="text-left px-3 sm:px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p: ConfigurationChangeRow) => (
                  <tr key={p.id} data-testid="parameter-row" data-param-key={p.key} className="border-b border-border/50 align-top">
                    <td className="px-3 sm:px-4 py-2.5 text-[12px] font-mono text-foreground break-all">{p.key}</td>
                    <td className="px-3 sm:px-4 py-2.5 text-[11px] max-w-[22rem]">
                      {p.value_is_redacted
                        ? <span className="font-mono text-muted-foreground" data-testid="value-redacted" title="The key names a credential; the server replaced the value with a hash so deployments can be compared without revealing it.">{p.current_value}</span>
                        : <span className="font-mono text-foreground break-all">{p.current_value}</span>}
                    </td>
                    <td className="px-3 sm:px-4 py-2.5">
                      <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-lg border whitespace-nowrap",
                        p.changed_after_create
                          ? "bg-amber-50 border-amber-200/60 text-amber-700 dark:bg-amber-950/30 dark:border-amber-800/30 dark:text-amber-400"
                          : "bg-muted border-border text-muted-foreground")}>
                        {p.changed_after_create ? "after creation" : "never"}
                      </span>
                    </td>
                    <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground whitespace-nowrap">{formatIsoDateTime(p.last_written_at)}</td>
                    <td className="px-3 sm:px-4 py-2.5 text-[12px] text-foreground" data-testid="parameter-writer">{writerWords(p.last_written_by)}</td>
                    <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground whitespace-nowrap">{formatIsoDateTime(p.created_at)} — {writerWords(p.created_by)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && !walking && (
              <div className="flex flex-col items-center justify-center py-16 gap-2" data-testid="parameters-empty">
                <FileCog size={24} className="text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">No configuration parameters in the period.</p>
                <p className="text-[11px] text-muted-foreground max-w-md text-center">The report is a lower bound — a parameter deleted since the period leaves no tombstone, and the statement above says what else it cannot see.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
