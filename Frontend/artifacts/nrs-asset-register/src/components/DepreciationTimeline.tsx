import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from "recharts";
import { ChevronDown, ChevronRight, Clock, AlertCircle } from "lucide-react";
import { fetchAssetDepreciation, type DepreciationPeriod } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import type { AssetDepreciation } from "@/types";
import { cn } from "@/lib/utils";

const BOOK_COLOUR = "#E01F26";   // NRS red — the value you still hold
const ACCUM_COLOUR = "#94a3b8";  // slate — the value written off

/** Compact axis money: 12.4m / 850k / 320. */
function shortMoney(v: number) {
  if (!v) return "0";
  if (Math.abs(v) >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}bn`;
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}m`;
  if (Math.abs(v) >= 1_000) return `${Math.round(v / 1_000)}k`;
  return String(Math.round(v));
}

function fullMoney(v: number, currency?: string) {
  const s = v.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${s}` : s;
}

interface YearRow {
  year: string;
  charge: number;
  accumulated: number;
  bookValue: number;
  isPast: boolean;
}

/** Roll the monthly board up to years — 120 monthly rows is unreadable, and
 *  "what was it worth at the end of 2024" is the question people actually ask. */
function toYears(periods: DepreciationPeriod[], today: string): YearRow[] {
  const byYear = new Map<string, YearRow>();
  for (const p of periods) {
    const year = p.period_end.slice(0, 4);
    const row = byYear.get(year) ?? {
      year, charge: 0, accumulated: 0, bookValue: 0, isPast: false,
    };
    row.charge += p.charge;
    // Last period of the year wins for the closing balances.
    row.accumulated = p.accumulated_depreciation;
    row.bookValue = p.book_value;
    row.isPast = p.period_end <= today;
    byYear.set(year, row);
  }
  return [...byYear.values()].map(r => ({ ...r, charge: Math.round(r.charge * 100) / 100 }));
}

export default function DepreciationTimeline({
  assetId,
  depreciation: d,
  currency,
}: {
  assetId: string;
  depreciation: AssetDepreciation;
  currency?: string;
}) {
  const [showTable, setShowTable] = useState(false);

  // Only computed methods have a board. 'none' has nothing to plot and
  // 'erp_managed' is owned by the tenant's ERP, which supplies a figure but no
  // schedule — so don't ask the API for one.
  const isComputed = d.method === "straight_line" || d.method === "declining_balance";

  const q = useQuery({
    queryKey: ["asset-depreciation", assetId],
    queryFn: () => fetchAssetDepreciation(assetId),
    enabled: isComputed,
    staleTime: 60_000,
  });

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const periods = q.data?.periods ?? [];

  const chartData = useMemo(
    () => periods.map(p => ({
      date: p.period_end,
      book: p.book_value,
      accum: p.accumulated_depreciation,
    })),
    [periods],
  );

  // Anchor the "today" marker to a real category value — a ReferenceLine on a
  // categorical axis has to match a data point exactly.
  //
  // Only drawn when today actually falls inside the schedule. An asset that
  // finished depreciating years ago would otherwise get a "today" marker pinned
  // to its final period, implying it is still running.
  const todayKey = useMemo(() => {
    if (!periods.length) return undefined;
    if (today > periods[periods.length - 1].period_end) return undefined;
    const past = periods.filter(p => p.period_end <= today);
    return past.length ? past[past.length - 1].period_end : undefined;
  }, [periods, today]);

  const years = useMemo(() => toYears(periods, today), [periods, today]);

  if (!isComputed) return null;

  if (q.isLoading) {
    return (
      <div className="mt-3 py-6 flex items-center justify-center gap-2 text-muted-foreground">
        <Clock size={14} className="animate-pulse" />
        <span className="text-[12px]">Loading schedule…</span>
      </div>
    );
  }

  if (q.error) {
    const err = q.error as CadraApiError;
    return (
      <div className="mt-3 flex items-start gap-2 text-[11px] text-red-700 dark:text-red-400
                      bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
        <AlertCircle size={13} className="shrink-0 mt-px" />
        <span>Could not load the schedule ({err.code}).</span>
      </div>
    );
  }

  if (!periods.length) {
    return (
      <p className="mt-3 text-[11px] text-muted-foreground">
        No schedule yet — this asset needs an acquisition cost and a useful life
        before its value can be tracked over time.
      </p>
    );
  }

  const salvage = d.salvageValue ?? 0;

  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between mb-1">
        <h4 className="text-[12px] font-semibold text-foreground">Value over time</h4>
        <span className="text-[10px] text-muted-foreground">
          {periods.length} monthly periods
        </span>
      </div>
      <p className="text-[11px] text-muted-foreground mb-3">
        The red line is what the asset is still worth, falling as it ages. The
        dashed grey line is how much has been written off. They always add up to
        the original cost.
      </p>

      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer>
          <ComposedChart data={chartData} margin={{ top: 5, right: 8, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="bookFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={BOOK_COLOUR} stopOpacity={0.75} />
                <stop offset="100%" stopColor={BOOK_COLOUR} stopOpacity={0.15} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              // One label per year rather than per month.
              tickFormatter={(v: string) => v.slice(0, 4)}
              interval={11}
              minTickGap={16}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              tickFormatter={shortMoney}
              width={52}
            />
            <Tooltip
              formatter={(v: number, name: string) => [
                fullMoney(v, currency),
                name === "book" ? "Net book value" : "Written off",
              ]}
              labelFormatter={(l: string) => `Period ending ${l}`}
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 8, fontSize: 12,
              }}
            />
            {/* Deliberately NOT stacked. Stacking makes book value the
                thickness of a band, which the eye has to measure; as its own
                curve you read the number straight off the axis. The two cross
                at the half-written-off point, which is the intuitive picture. */}
            <Area type="monotone" dataKey="book" name="book" strokeWidth={2}
                  stroke={BOOK_COLOUR} fill="url(#bookFill)" />
            <Line type="monotone" dataKey="accum" name="accum" dot={false}
                  stroke={ACCUM_COLOUR} strokeWidth={1.5} strokeDasharray="4 3" />
            {salvage > 0 && (
              <ReferenceLine
                y={salvage} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 4"
                label={{ value: "salvage", position: "insideBottomRight",
                         fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
              />
            )}
            {todayKey && (
              <ReferenceLine
                x={todayKey} stroke="hsl(var(--foreground))" strokeDasharray="3 3"
                label={{ value: "today", position: "top",
                         fontSize: 9, fill: "hsl(var(--foreground))" }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <button
        onClick={() => setShowTable(v => !v)}
        className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium
                   text-muted-foreground hover:text-foreground"
        data-testid="toggle-depreciation-schedule"
      >
        {showTable ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {showTable ? "Hide" : "Show"} year-by-year schedule
      </button>

      {showTable && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-[11px] min-w-[380px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-1.5 font-medium">Year</th>
                <th className="py-1.5 font-medium text-right">Charge</th>
                <th className="py-1.5 font-medium text-right">Written off</th>
                <th className="py-1.5 font-medium text-right">Book value</th>
              </tr>
            </thead>
            <tbody>
              {years.map(r => (
                <tr
                  key={r.year}
                  className={cn(
                    "border-b border-border last:border-0",
                    // Future periods are a projection, not history.
                    !r.isPast && "text-muted-foreground",
                  )}
                >
                  <td className="py-1.5">
                    {r.year}
                    {!r.isPast && <span className="ml-1 text-[9px]">(projected)</span>}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{fullMoney(r.charge)}</td>
                  <td className="py-1.5 text-right tabular-nums">{fullMoney(r.accumulated)}</td>
                  <td className="py-1.5 text-right tabular-nums font-semibold">
                    {fullMoney(r.bookValue)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
