import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchDepreciationReport } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid, Legend,
} from "recharts";
import {
  AlertCircle, Clock, Wallet, TrendingDown, Landmark, CalendarX, RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

// NRS brand red — matches the other reports.
const NRS_RED = "#E01F26";
const ACCUM_COLOUR = "#94a3b8";

const STATE_LABEL: Record<string, string> = {
  not_applicable: "Not depreciated",
  not_started: "Not started",
  depreciating: "Depreciating",
  fully_depreciated: "Fully depreciated",
  disposed: "Disposed",
  erp_managed: "ERP-managed",
};

const METHOD_LABEL: Record<string, string> = {
  none: "Not depreciated",
  straight_line: "Straight line",
  declining_balance: "Declining balance",
  erp_managed: "ERP-managed",
};

function money(v: number) {
  if (!v) return "0";
  if (Math.abs(v) >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}bn`;
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}m`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fullMoney(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function DepreciationReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Depreciation & Book Value");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const report = useQuery({
    queryKey: ["report-depreciation"],
    queryFn: () => fetchDepreciationReport(),
    staleTime: 60_000,
  });

  const categories = useMemo(
    () => (report.data?.by_category ?? []).slice(0, 20),
    [report.data],
  );

  const err = report.error as CadraApiError | null;
  const refresh = () => { report.refetch(); };

  if (report.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading depreciation…</p>
    </div>
  );
  if (err) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{err.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{err.message}</p>
        </div>
      </div>
    </div>
  );

  const t = report.data?.totals;
  const needsStartDate = report.data?.needs_start_date ?? 0;
  const missingCost = report.data?.missing_cost ?? 0;

  const tiles = [
    { label: "Depreciable cost", value: money(t?.depreciable_cost ?? 0), icon: Wallet, color: "text-foreground" },
    { label: "Accumulated", value: money(t?.accumulated_depreciation ?? 0), icon: TrendingDown, color: "text-amber-600 dark:text-amber-400" },
    { label: "Net book value", value: money(t?.current_book_value ?? 0), icon: Landmark, color: "text-green-600 dark:text-green-400" },
    { label: "Needs start date", value: needsStartDate.toLocaleString(), icon: CalendarX, color: needsStartDate ? "text-red-600 dark:text-red-400" : "text-muted-foreground" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <span className="inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider"
                style={{ background: NRS_RED, color: "white" }}>NRS</span>
          <div>
            <h1 className="text-xl font-bold text-foreground">Depreciation &amp; Book Value</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Written-down value across {(t?.asset_count ?? 0).toLocaleString()} assets.
              Operational reference only — not the financial book of record.
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn(report.isFetching && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {tiles.map(tile => (
          <div key={tile.label} className="bg-card border border-border/50 rounded-2xl px-4 py-4">
            <div className="flex items-center gap-1.5 mb-2">
              <tile.icon size={12} className={tile.color} />
              <p className={cn("text-[10px] font-semibold uppercase tracking-widest", tile.color)}>{tile.label}</p>
            </div>
            <p className={cn("font-extrabold leading-tight tabular-nums text-[26px]", tile.color)}>
              {tile.value}
            </p>
          </div>
        ))}
      </div>

      {/* Data-quality callout. Depreciation is only as good as its inputs, and
          right now the register has very little cost data — say so plainly
          rather than presenting empty totals as fact. */}
      {(needsStartDate > 0 || missingCost > 0) && (
        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200/70 dark:border-amber-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="text-[12px] text-amber-800 dark:text-amber-300 space-y-1">
            <p className="font-semibold">Figures below are incomplete</p>
            {missingCost > 0 && (
              <p>
                {missingCost.toLocaleString()} asset{missingCost === 1 ? " has" : "s have"} a
                depreciation method but no acquisition cost, so nothing can be written down.
              </p>
            )}
            {needsStartDate > 0 && (
              <p>
                {needsStartDate.toLocaleString()} asset{needsStartDate === 1 ? " has" : "s have"} an
                estimated start date inferred from when the record was created, not a real
                acquisition or purchase date.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Cost vs book value by category */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Cost vs net book value by category</h2>
        {categories.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-8 text-center">
            No category has a depreciation policy with costs attached yet.
          </p>
        ) : (
          <div style={{ width: "100%", height: 380 }}>
            <ResponsiveContainer>
              <BarChart data={categories} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  interval={0} angle={-30} textAnchor="end" height={70}
                />
                <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                       tickFormatter={money} />
                <Tooltip
                  formatter={(v: number) => fullMoney(v)}
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8, fontSize: 12,
                  }}
                  cursor={{ fill: "hsl(var(--muted))", opacity: 0.3 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="accumulated_depreciation" name="Accumulated" stackId="a" fill={ACCUM_COLOUR} />
                <Bar dataKey="current_book_value" name="Net book value" stackId="a" radius={[6, 6, 0, 0]}>
                  {categories.map((c, i) => <Cell key={c.id ?? i} fill={NRS_RED} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Breakdown counts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">Assets by depreciation status</h2>
          <dl className="space-y-1">
            {Object.entries(report.data?.by_state ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1.5 border-b border-border last:border-0">
                <dt className="text-[12px] text-muted-foreground">{STATE_LABEL[k] ?? k}</dt>
                <dd className="text-[12px] font-semibold tabular-nums">{v.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">Assets by method</h2>
          <dl className="space-y-1">
            {Object.entries(report.data?.by_method ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1.5 border-b border-border last:border-0">
                <dt className="text-[12px] text-muted-foreground">{METHOD_LABEL[k] ?? k}</dt>
                <dd className="text-[12px] font-semibold tabular-nums">{v.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {/* Per-category table */}
      <div className="bg-card border border-border rounded-2xl p-5 overflow-x-auto">
        <h2 className="text-[13px] font-bold mb-3">Category detail</h2>
        {categories.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-6 text-center">Nothing to show yet.</p>
        ) : (
          <table className="w-full text-[12px] min-w-[640px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2 font-medium">Category</th>
                <th className="py-2 font-medium text-right">Assets</th>
                <th className="py-2 font-medium text-right">Depreciable cost</th>
                <th className="py-2 font-medium text-right">Accumulated</th>
                <th className="py-2 font-medium text-right">Net book value</th>
              </tr>
            </thead>
            <tbody>
              {categories.map(c => (
                <tr key={c.id} className="border-b border-border last:border-0">
                  <td className="py-2">{c.name}</td>
                  <td className="py-2 text-right tabular-nums">{c.asset_count.toLocaleString()}</td>
                  <td className="py-2 text-right tabular-nums">{fullMoney(c.depreciable_cost)}</td>
                  <td className="py-2 text-right tabular-nums">{fullMoney(c.accumulated_depreciation)}</td>
                  <td className="py-2 text-right tabular-nums font-semibold">{fullMoney(c.current_book_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
