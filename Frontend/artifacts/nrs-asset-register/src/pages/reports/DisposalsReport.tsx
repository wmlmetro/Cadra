/**
 * Disposals — a read-only view of `GET /api/v1/reports/disposals` (handoff
 * 23, the gaps graded by handoff 16's findings machinery), given a page by
 * handoff 49. The only inputs are the two period dates.
 *
 * WHAT THE REPORT SAYS ABOUT ITSELF
 * ---------------------------------
 * `summary` describes the WHOLE period on every page — the totals, what each
 * record lacks (`findings`), whether SAP was told (INT-09), the methods and
 * the proceeds — so it renders above the table from page one while the rows
 * walk. `unplaceable` rows are disposed assets with NO date from any source:
 * they belong to every period and to none, ride on every page uncut by the
 * cursor, and get their own section so nobody mistakes them for rows OF the
 * period. A row's `date_source` says whether its date was recorded,
 * reconstructed or inferred from a state transition.
 *
 * WHO MAY OPEN IT
 * ---------------
 * Whoever holds `assets:read` — what the server route requires. That is
 * wider than the Auditor (every Asset User holds it); the scope is the
 * server's and the sidebar declares it (navigation.ts), per handoff 46's
 * rule against inventing scopes to hide pages.
 */
import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { fetchDisposalsReport, type DisposalsReportPage } from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { cn, formatIsoDate, formatIsoDateTime, lagosToday } from "@/lib/utils";
import type { DisposalReportRow } from "@/types";
import { AlertCircle, Clock, Trash2 } from "lucide-react";
import { ScopeRefusal } from "@/components/ScopeRefusal";

/** The findings enum (`DisposalReportRow` in `v1.py`), in words. Anything
 *  the server adds later prints as its key with the underscores dropped. */
const FINDING_WORDS: Record<string, string> = {
  no_authorising_reference:   "no authorising reference",
  no_approver:                "no approver",
  no_approval_date:           "no approval date",
  no_disposal_method:         "no method",
  no_disposal_date:           "no date",
  no_disposal_reason:         "no reason",
  no_proceeds_recorded:       "no proceeds recorded",
  disposal_date_reconstructed:"date reconstructed",
};
const findingWords = (f: string) => FINDING_WORDS[f] ?? f.replace(/_/g, " ");

const fmtMoney = (n: number, currency: string | null) =>
  `${(currency ?? "").trim() || "NGN"} ${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

function DisposalRows({ rows, testid }: { rows: DisposalReportRow[]; testid: string }) {
  return (
    <tbody>
      {rows.map((r) => (
        <tr key={r.asset_id} data-testid={testid} data-asset-id={r.asset_id} className="border-b border-border/50 align-top">
          <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground whitespace-nowrap">
            {r.disposal_date ? formatIsoDate(r.disposal_date) : "—"}
            {r.date_source !== "recorded" && r.date_source !== "none" && (
              <span className="ml-1 text-[10px] text-amber-700 dark:text-amber-400" title={`The register did not record this date; it was ${r.date_source === "reconstructed" ? "reconstructed from other evidence" : "inferred from the state change"}.`}>({r.date_source.replace(/_/g, " ")})</span>
            )}
          </td>
          <td className="px-3 sm:px-4 py-2.5 text-[12px]">
            <Link href={`/assets/${r.asset_id}`} className="text-foreground hover:text-primary" data-testid="disposal-asset-link">{r.name ?? r.asset_code ?? `#${r.asset_id}`}</Link>
            <span className="block text-[10px] font-mono text-muted-foreground">{r.asset_code ?? "—"}</span>
          </td>
          <td className="px-3 sm:px-4 py-2.5 text-[11px] text-foreground whitespace-nowrap">{r.disposal_method ?? <span className="text-muted-foreground">—</span>}</td>
          <td className="px-3 sm:px-4 py-2.5 text-[11px] text-foreground">
            {r.approved_by ?? <span className="text-muted-foreground">—</span>}
            {r.approved_at && <span className="block text-[10px] text-muted-foreground">{formatIsoDateTime(r.approved_at)}</span>}
          </td>
          <td className="px-3 sm:px-4 py-2.5 text-[11px] font-mono text-foreground whitespace-nowrap">{r.proceeds ? fmtMoney(r.proceeds, r.currency) : <span className="text-muted-foreground">—</span>}</td>
          <td className="px-3 sm:px-4 py-2.5 text-[11px] font-mono text-muted-foreground">{r.sap_asset_number ?? "—"}</td>
          <td className="px-3 sm:px-4 py-2.5">
            {r.findings.length === 0
              ? <span className="text-[11px] font-semibold px-2 py-0.5 rounded-lg border bg-green-50 border-green-200/60 text-green-700 dark:bg-green-950/30 dark:border-green-800/30 dark:text-green-400">clean</span>
              : <span className="flex flex-wrap gap-1">
                  {r.findings.map(f => (
                    <span key={f} data-testid="disposal-finding" data-finding={f} className="text-[10px] font-semibold px-1.5 py-0.5 rounded-lg border bg-amber-50 border-amber-200/60 text-amber-700 dark:bg-amber-950/30 dark:border-amber-800/30 dark:text-amber-400 whitespace-nowrap">
                      {findingWords(f)}
                    </span>
                  ))}
                </span>}
          </td>
        </tr>
      ))}
    </tbody>
  );
}

export default function DisposalsReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();

  // The current Lagos year by default: "what left the register this year" is
  // the question the period exists for, and the Lagos day is the server's
  // definition of today.
  const [from, setFrom] = useState(() => `${lagosToday().slice(0, 4)}-01-01`);
  const [to, setTo] = useState(lagosToday);

  useEffect(() => {
    setTitle("Disposals");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const validPeriod = /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to;

  const report = useInfiniteQuery<DisposalsReportPage, CadraApiError>({
    queryKey: ["disposals-report", from, to],
    queryFn: ({ pageParam }) => fetchDisposalsReport(from, to, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: scopes.has(SCOPE.assetsRead) && validPeriod,
    staleTime: 30_000,
  });
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = report;

  const first = report.data?.pages[0]?.report ?? null;
  const truncated = report.data?.pages[0]?.truncated ?? null;
  const summary = first?.summary ?? null;
  const rows = useMemo(
    () => (report.data?.pages ?? []).flatMap(p => p.report.rows),
    [report.data],
  );
  const unplaceable = first?.unplaceable ?? [];

  if (!scopes.has(SCOPE.assetsRead)) return (
    <ScopeRefusal scope="assets:read" detail="The disposals report reads the register — what left it, by whose approval, by what method and for what proceeds." />
  );

  const error = report.error;

  return (
    <div className="flex flex-col h-full" data-testid="disposals-report-page">
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
        {summary && (
          <p className="ml-auto text-xs text-muted-foreground" data-testid="disposals-count">
            <span className="font-bold text-foreground">{summary.total.toLocaleString()}</span> disposals in the period
            {summary.unplaceable > 0 && <> · <span className="font-semibold text-amber-700 dark:text-amber-400">{summary.unplaceable.toLocaleString()}</span> more with no date at all</>}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {!validPeriod ? (
          <p className="p-6 text-xs text-red-700 dark:text-red-400" data-testid="period-invalid">The period ends before it starts, or a date is incomplete.</p>
        ) : report.isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <Clock size={20} className="animate-pulse" />
            <p className="text-sm">Reading the disposals record…</p>
          </div>
        ) : error ? (
          <div className="p-6 max-w-xl">
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="disposals-report-error">
              <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <ApiErrorMessage err={error} stacked />
                {!apiConfigured && <p className="text-[11px] mt-1">No active session.</p>}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Whole-period summary — the same on every page of the walk */}
            {summary && summary.total > 0 && (
              <div className="px-4 sm:px-5 pt-4 pb-3 space-y-2" data-testid="report-summary">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span><span className="font-semibold text-foreground">{summary.clean.toLocaleString()}</span> clean of {summary.total.toLocaleString()}</span>
                  {Object.entries(summary.by_method).map(([m, n]) => (
                    <span key={m}>· {m.replace(/_/g, " ")}: <span className="font-semibold text-foreground">{n.toLocaleString()}</span></span>
                  ))}
                  {Object.entries(summary.proceeds_by_currency).map(([c, n]) => (
                    <span key={c}>· proceeds: <span className="font-semibold text-foreground">{fmtMoney(n, c)}</span></span>
                  ))}
                </div>
                {Object.keys(summary.findings).length > 0 && (
                  <div className="flex flex-wrap gap-1" data-testid="summary-findings">
                    {Object.entries(summary.findings).map(([f, n]) => (
                      <span key={f} className="text-[10px] font-semibold px-1.5 py-0.5 rounded-lg border bg-amber-50 border-amber-200/60 text-amber-700 dark:bg-amber-950/30 dark:border-amber-800/30 dark:text-amber-400">
                        {findingWords(f)}: {n.toLocaleString()}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-[12px] text-foreground/90" data-testid="report-sap-statement">{summary.sap_coverage.statement}</p>
                {truncated && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="report-truncated">
                    Truncated by the server at {truncated.cap.toLocaleString()} of {truncated.total.toLocaleString()} rows: {truncated.reason}
                  </p>
                )}
              </div>
            )}

            {/* Disposed with no date from any source — on every page, never cut */}
            {unplaceable.length > 0 && (
              <div className="px-4 sm:px-5 pt-2 pb-1" data-testid="unplaceable-section">
                <p className="text-[11px] font-bold text-amber-700 dark:text-amber-400 uppercase tracking-widest">No date at all — in every period and in none</p>
                <table className="w-full min-w-[840px]">
                  <DisposalRows rows={unplaceable} testid="unplaceable-row" />
                </table>
              </div>
            )}

            {rows.length > 0 && (
              <table className="w-full min-w-[840px]" data-testid="disposals-table">
                <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                  <tr>
                    {["Disposed", "Asset", "Method", "Approved by", "Proceeds", "SAP asset", "Record"].map(h => (
                      <th key={h} className="text-left px-3 sm:px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                    ))}
                  </tr>
                </thead>
                <DisposalRows rows={rows} testid="disposal-row" />
              </table>
            )}

            {hasNextPage && (
              <div className="flex justify-center py-4">
                <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage} data-testid="button-load-more"
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-border bg-card text-foreground hover:bg-muted disabled:opacity-50">
                  {isFetchingNextPage ? "Loading…" : `Load more (${rows.length.toLocaleString()} of ${(summary?.total ?? 0).toLocaleString()})`}
                </button>
              </div>
            )}

            {summary && summary.total === 0 && (
              unplaceable.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-2" data-testid="disposals-empty">
                  <Trash2 size={24} className="text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground" data-testid="disposals-empty-sentence">
                    No disposals recorded between {formatIsoDate(from)} and {formatIsoDate(to)}.
                  </p>
                  <p className="text-[11px] text-muted-foreground max-w-md text-center">Nothing left this register in the period — and nothing here is illustrative: an empty report is the tenant's own answer.</p>
                </div>
              ) : (
                <p className="px-4 sm:px-5 py-4 text-sm text-muted-foreground" data-testid="disposals-empty-sentence">
                  No DATED disposals between {formatIsoDate(from)} and {formatIsoDate(to)} — the rows above carry no date and so sit outside every period.
                </p>
              )
            )}
          </>
        )}
      </div>
    </div>
  );
}
