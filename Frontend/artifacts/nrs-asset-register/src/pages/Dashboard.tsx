import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { useLocation } from "wouter";
import {
  getDashboardStats, getReviewQueueAssets,
  getAssetsByCategory, getAssetsByStatus,
  fetchTotals, fetchAssetsPage, fetchDashboardKpis, fetchDashboardMap,
  fetchAssetStatusCounts, fetchWhoAmI,
} from "@/lib/dataProvider";
import { apiConfigured, type CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import AssetStatusPills from "@/components/AssetStatusPills";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import type { TooltipProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import {
  Monitor, MapPin, Users, AlertTriangle,
  ArrowUpRight, TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

const CAT_COLORS = ["hsl(var(--chart-1))", "hsl(var(--chart-2))", "hsl(var(--chart-3))"];
const STATUS_COLORS: Record<string, string> = {
  "Cleared": "#22c55e",
  "Review — data quality": "#f59e0b",
  // Orange, as its pill is (`StatusPill`): a different finding from the amber
  // one beside it, and not the red kept for a missing asset.
  "Review — no SAP code": "#f97316",
  // Neutral, like its pill: it is the absence of a verdict, not a third one.
  "Not in service": "#94a3b8",
};

function StatCard({
  label, value, sub, trend, accent, icon: Icon, onClick,
}: {
  label: string;
  value: string;
  sub?: string;
  trend?: string;
  accent?: string;
  icon: React.ElementType;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "relative bg-card rounded-2xl border border-border p-6 overflow-hidden group",
        "transition-all duration-200",
        onClick && "cursor-pointer hover:shadow-lg hover:-translate-y-0.5 hover:border-border/80"
      )}
    >
      {/* Accent stripe */}
      {accent && (
        <div
          className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl"
          style={{ background: accent }}
        />
      )}

      {/* Background glow */}
      <div
        className="absolute -right-6 -top-6 w-24 h-24 rounded-full opacity-[0.06] pointer-events-none"
        style={{ background: accent || "hsl(var(--primary))" }}
      />

      <div className="relative">
        <div className="flex items-start justify-between mb-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{label}</p>
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: `${accent || "hsl(var(--primary))"}18` }}
          >
            <Icon size={14} style={{ color: accent || "hsl(var(--primary))" }} />
          </div>
        </div>

        <p className="text-4xl font-bold tracking-tight text-foreground tabular-nums leading-none mb-1">
          {value}
        </p>

        {trend && (
          <div className="flex items-center gap-1 mt-2">
            <TrendingUp size={11} className="text-emerald-500" />
            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold">{trend}</span>
          </div>
        )}

        {sub && (
          <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">{sub}</p>
        )}
      </div>
    </div>
  );
}

function MiniStatRow({ items }: { items: { label: string; value: string; color: string }[] }) {
  return (
    <div className="flex gap-4 mt-3 pt-3 border-t border-border">
      {items.map((item) => (
        <div key={item.label}>
          <p className="text-[10px] uppercase tracking-wider font-medium" style={{ color: item.color }}>{item.label}</p>
          <p className="text-sm font-bold text-foreground tabular-nums">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ title, sub, action, onAction }: { title: string; sub?: string; action?: string; onAction?: () => void }) {
  return (
    <div className="flex items-end justify-between mb-5">
      <div>
        <h2 className="text-sm font-bold text-foreground">{title}</h2>
        {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
      </div>
      {action && (
        <button
          onClick={onAction}
          className="flex items-center gap-1 text-xs font-semibold text-primary hover:opacity-80 transition-opacity"
        >
          {action} <ArrowUpRight size={12} />
        </button>
      )}
    </div>
  );
}

const CustomBarTooltip = ({ active, payload, label }: TooltipProps<ValueType, NameType>) => {
  if (!active || !payload?.length) return null;
  const value = payload[0].value;
  const valueText = typeof value === "number" ? value.toLocaleString() : String(value ?? "");
  return (
    <div className="bg-popover border border-border rounded-xl px-3 py-2 shadow-lg text-xs">
      <p className="font-semibold text-foreground mb-1">{label}</p>
      <p className="text-muted-foreground">
        <span className="font-bold text-foreground">{valueText}</span> assets
      </p>
    </div>
  );
};

function CSSDonut({ data, total }: { data: { name: string; value: number }[]; total: number }) {
  let cursor = 0;
  const stops = data.map((d) => {
    const start = (cursor / total) * 360;
    cursor += d.value;
    const end = (cursor / total) * 360;
    return `${STATUS_COLORS[d.name] ?? "#94a3b8"} ${start.toFixed(1)}deg ${end.toFixed(1)}deg`;
  });
  const gradient = `conic-gradient(from -90deg, ${stops.join(", ")})`;
  // No slices yet (the counts are still loading) or an empty register: say
  // nothing rather than divide by zero and print "NaN%".
  const cleared = data[0];
  const pct = cleared && total > 0 ? `${((cleared.value / total) * 100).toFixed(0)}%` : "—";

  return (
    <div className="flex items-center justify-center py-4">
      <div className="relative" style={{ width: 148, height: 148, flexShrink: 0 }}>
        <div
          className="w-full h-full rounded-full"
          style={{ background: total > 0 && data.length > 0 ? gradient : "hsl(var(--muted))" }}
        />
        {/* inner mask */}
        <div
          className="absolute inset-0 rounded-full bg-card flex flex-col items-center justify-center"
          style={{ margin: "26px" }}
        >
          <span className="text-[22px] font-extrabold text-foreground leading-none tabular-nums">{pct}</span>
          <span className="text-[9px] text-muted-foreground uppercase tracking-wider mt-0.5 font-semibold">Cleared</span>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, setLocation] = useLocation();

  const mockStats = getDashboardStats();
  // Real totals from the API (cheap — uses total_estimate).
  const totalsQ = useQuery<Awaited<ReturnType<typeof fetchTotals>>, CadraApiError>({
    queryKey: ["dashboard", "totals"],
    queryFn: fetchTotals,
    staleTime: 60_000,
  });
  const totals = totalsQ.data;
  // Review queue sample = first page of ACTIVE, unverified assets. The status
  // filter carries `state=active` (see `statusToServerFilter`), so a missing
  // or disposed asset cannot be listed here as awaiting review — and this
  // page's `total_estimate` is the size of the queue, read off the same
  // request. The card and the table both say "Active assets not yet
  // verified", and that is exactly what the request asks for — so an asset
  // that is unverified AND an SAP exception is listed here, correctly, wearing
  // the exception's pill (`deriveStatus` ranks it first).
  const reviewQ = useQuery<Awaited<ReturnType<typeof fetchAssetsPage>>, CadraApiError>({
    queryKey: ["dashboard", "review-queue"],
    queryFn: () => fetchAssetsPage(undefined, { status: "Review — data quality" }),
    staleTime: 60_000,
  });
  const reviewPage = reviewQ.data;
  // Server-aggregated KPIs — replaces hardcoded fleet/locations/requests
  // counts. Cheap single round-trip via /api/v1/dashboard/kpis. Not asked
  // without a session: it has no mock branch of its own.
  const kpisQ = useQuery<Awaited<ReturnType<typeof fetchDashboardKpis>>, CadraApiError>({
    queryKey: ["dashboard", "kpis"],
    queryFn: fetchDashboardKpis,
    staleTime: 30_000,
    enabled: apiConfigured,
  });
  const realKpis = kpisQ.data;

  // With a session, a tile shows the server's number, "…" while it is being
  // asked, and "—" once the asking failed — NEVER the mock figure. Every tile
  // here used to fall back to `mockStats`, so a refused read (a role without
  // `identity:read`, say) rendered as 13,150 assets: the instrument reporting
  // success while measuring nothing (handoff 46). The refusal is said once,
  // in the banner below the header. Mock numbers remain for the no-session
  // demo build only, which is the one place nobody can mistake them for a
  // measurement.
  const tile = (live: number | null | undefined, loading: boolean, mock: number): string => {
    if (!apiConfigured) return mock.toLocaleString();
    if (live != null) return live.toLocaleString();
    return loading ? "…" : "—";
  };
  const stats = {
    totalAssets: tile(totals?.assets, totalsQ.isLoading, mockStats.totalAssets),
    locations:   tile(realKpis?.locations.total ?? totals?.locations, totalsQ.isLoading || kpisQ.isLoading, mockStats.locations),
    employees:   tile(totals?.employees, totalsQ.isLoading, mockStats.employees),
  };
  // The card says "Assets pending data quality review" and the table says
  // "Showing 8 of N". N was `realKpis.requests.open` — OPEN SERVICE-DESK
  // TICKETS, a count of a different kind of thing. It is now the number both
  // sentences describe, from the same response as the rows, so the two cannot
  // disagree. Null while it loads: with an API configured the mock figure is
  // never shown in its place.
  const reviewQueue: number | null =
    reviewPage?.totalEstimate ?? (apiConfigured ? null : mockStats.reviewQueue);
  const reviewQueueText = reviewQueue != null ? reviewQueue.toLocaleString()
    : apiConfigured && reviewQ.isLoading ? "…" : "—";
  // Mock rows ONLY when there is no API. With one, an unloaded or failed
  // queue is an empty table — the first version listed invented assets under
  // the live heading for as long as the request took, or for ever if it failed.
  const reviewAssets = reviewPage?.assets.slice(0, 8)
    ?? (apiConfigured ? [] : getReviewQueueAssets());
  // Real per-tenant asset-category breakdown from /api/v1/dashboard/kpis
  // (assets.categories, sorted desc). Top 3 to match the palette/legend.
  // Mock categories ONLY with no session: with one, a failed or empty
  // breakdown is an empty chart, not three invented bars (handoff 46).
  const categoryData = !apiConfigured
    ? getAssetsByCategory()
    : (realKpis?.assets?.categories ?? []).slice(0, 3).map(c => ({ name: c.name, value: c.count }));
  // The status breakdown, from REAL counts. This plotted five hard-coded mock
  // numbers (10,842 / 985 / …) as percentages of the LIVE total — invented
  // figures beside real ones, on the first screen a client sees. Four slices
  // that PARTITION the register, in `deriveStatus`'s order — an active asset
  // that is both an SAP exception and unverified is an exception, so it is
  // taken out of the data-quality slice rather than drawn twice:
  //   Review — no SAP code   = active-exception
  //   Review — data quality  = active-unverified − active-unverified-exception
  //   Cleared                = active − the two above
  //   Not in service         = total − active
  // The exception slice is drawn only when it is not zero: on a tenant where
  // nothing has been tagged it is a structural zero, and a permanent "0" in a
  // legend reads as a check that was run and passed.
  // Mock mode keeps mock numbers. With an API configured and no counts yet,
  // there are NO slices — never the mock ones.
  const statusQ = useQuery<Awaited<ReturnType<typeof fetchAssetStatusCounts>>, CadraApiError>({
    queryKey: ["dashboard", "status-counts"],
    queryFn: fetchAssetStatusCounts,
    staleTime: 60_000,
    enabled: apiConfigured,
  });
  const statusCounts = statusQ.data;
  const statusCountsFailed = statusQ.isError;
  const statusData: { name: string; value: number }[] =
    !apiConfigured ? getAssetsByStatus() :
    statusCounts ? (() => {
      const c = statusCounts;
      const dataQuality = Math.max(0, c.activeUnverified - c.activeUnverifiedException);
      return [
        // "Cleared" stays FIRST: the header under the title reads slice 0.
        { name: "Cleared", value: Math.max(0, c.active - c.activeException - dataQuality) },
        { name: "Review — data quality", value: dataQuality },
        ...(c.activeException > 0 ? [{ name: "Review — no SAP code", value: c.activeException }] : []),
        { name: "Not in service", value: Math.max(0, c.total - c.active) },
      ];
    })() : [];
  // The slices' own sum, not `stats.totalAssets`: that comes from a different
  // request at a different moment, and a percentage of somebody else's total
  // is how a donut comes to 97% or 104%.
  const statusTotal = statusData.reduce((n, d) => n + d.value, 0);

  // Map pins from /api/v1/dashboard/map.locations — already deduped & geocoded
  // server-side, way cheaper than walking every Location record.
  const mapQ = useQuery<Awaited<ReturnType<typeof fetchDashboardMap>>, CadraApiError>({
    queryKey: ["dashboard", "map"],
    queryFn: fetchDashboardMap,
    staleTime: 60_000,
    enabled: apiConfigured,
  });
  const mapData = mapQ.data;
  const officePins = useMemo<MapPinData[]>(() => {
    return (mapData?.locations ?? [])
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
        count: l.open_requests || undefined,
      }));
  }, [mapData]);

  // The first refusal among the page's reads, said once. One banner rather
  // than one per card: the cause is nearly always the same (a scope the
  // session lacks), and the server's sentence names it.
  const firstError: CadraApiError | null = apiConfigured
    ? (totalsQ.error ?? kpisQ.error ?? reviewQ.error ?? statusQ.error ?? mapQ.error ?? null)
    : null;

  useEffect(() => {
    setTitle("Facility Command Center");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const now = new Date();
  const dateStr = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  // The person signed in, from the same query the top bar holds — not
  // "Admin" for everybody. Handoff 46's demo signs in as a Store Officer
  // and an auditor; a greeting that calls each of them Admin says the
  // opposite of the sidebar beside it. No name read, no name printed.
  const { data: me } = useQuery({
    queryKey: ["whoami"],
    queryFn: fetchWhoAmI,
    staleTime: 30 * 60_000,
    retry: false,
  });
  const firstName = me?.name?.trim().split(/\s+/)[0];

  return (
    <div className="p-6 space-y-6 max-w-[1440px] mx-auto">

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">{firstName ? `${greeting}, ${firstName}` : greeting}</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{dateStr} — Asset Register overview</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800/40 rounded-xl">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[11px] font-semibold text-green-700 dark:text-green-400">All systems operational</span>
          </div>
        </div>
      </div>

      {firstError && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="dashboard-error" role="alert">
          <AlertTriangle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div>
            <ApiErrorMessage err={firstError} stacked />
            <p className="text-[11px] text-red-700/80 dark:text-red-400/80 mt-1">
              A figure that could not be read is shown as —, not as a number.
            </p>
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Total Assets */}
        <div
          className="relative bg-card rounded-2xl border border-border p-6 overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 col-span-2 xl:col-span-1"
          onClick={() => setLocation("/assets")}
          data-testid="card-total-assets"
        >
          <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl" style={{ background: "hsl(var(--primary))" }} />
          <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full opacity-[0.06] pointer-events-none" style={{ background: "hsl(var(--primary))" }} />
          <div className="relative">
            <div className="flex items-start justify-between mb-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Total Assets</p>
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "hsl(var(--primary) / 0.1)" }}>
                <Monitor size={14} style={{ color: "hsl(var(--primary))" }} />
              </div>
            </div>
            <p className="text-4xl font-bold tracking-tight text-foreground tabular-nums leading-none">
              {stats.totalAssets}
            </p>
            {/* Top-3 real asset categories (per-tenant) from the kpis payload. */}
            <div className="flex gap-4 mt-3 pt-3 border-t border-border">
              {categoryData.slice(0, 3).map((c, i) => (
                <div key={c.name}>
                  <p
                    className={`text-[10px] uppercase tracking-wider font-medium ${["text-blue-500", "text-emerald-500", "text-amber-500"][i]}`}
                    title={c.name}
                  >
                    {c.name.length > 10 ? c.name.slice(0, 9) + "…" : c.name}
                  </p>
                  <p className="text-sm font-bold text-foreground tabular-nums">{c.value.toLocaleString()}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <StatCard
          label="Locations"
          value={stats.locations}
          // The breakdown under the count is mock text; with a session it is
          // not drawn rather than drawn beside a real total (handoff 46).
          sub={apiConfigured ? undefined : "7 zones · 38 states · 857 offices"}
          accent="#3b82f6"
          icon={MapPin}
          onClick={() => setLocation("/locations")}
        />
        <StatCard
          label="Employees"
          value={stats.employees}
          sub="Registered across all zones"
          accent="#10b981"
          icon={Users}
        />

        {/* Review Queue — highlighted */}
        <div
          className="relative bg-amber-50 dark:bg-amber-950/20 rounded-2xl border border-amber-200 dark:border-amber-800/40 p-6 overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5"
          // Was `onClick={() => {}}` under a pointer cursor and a hover lift —
          // a control that promised something and did nothing.
          onClick={() => setLocation("/assets/list")}
          data-testid="card-review-queue"
        >
          <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl bg-amber-500" />
          <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full opacity-[0.08] pointer-events-none bg-amber-500" />
          <div className="relative">
            <div className="flex items-start justify-between mb-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-500">Review Queue</p>
              <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-amber-500/15">
                <AlertTriangle size={14} className="text-amber-600 dark:text-amber-500" />
              </div>
            </div>
            <p className="text-4xl font-bold tracking-tight text-amber-700 dark:text-amber-400 tabular-nums leading-none">
              {reviewQueueText}
            </p>
            <p className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-800/40 text-[11px] text-amber-700/70 dark:text-amber-500/80 leading-relaxed">
              Active assets not yet verified
            </p>
          </div>
        </div>
      </div>

      {/* NRS Office Locations map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <SectionHeader
          title="NRS Office Locations"
          sub={apiConfigured && !mapData
            ? (mapQ.isError ? "The sites could not be read" : "Reading the sites…")
            : `${officePins.length} distinct sites across Nigeria`}
        />
        <NigeriaMap pins={officePins} height={380} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Bar chart */}
        <div className="bg-card border border-border rounded-2xl p-5 lg:col-span-3">
          <SectionHeader
            title="Assets by Category"
            sub="Top asset categories by count"
          />
          {categoryData.length === 0 ? (
            // Only reachable with a session: the no-session build always has
            // its mock categories. Said in words, not drawn as empty axes.
            <div className="h-[220px] flex items-center justify-center text-[12px] text-muted-foreground" data-testid="category-chart-empty">
              {kpisQ.isLoading ? "Counting…" : kpisQ.isError ? "The categories could not be read" : "No categories in the register"}
            </div>
          ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={categoryData} barSize={52} barGap={12}>
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))", fontFamily: "inherit" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))", fontFamily: "inherit" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))}
                width={28}
              />
              <Tooltip content={<CustomBarTooltip />} cursor={{ fill: "hsl(var(--muted) / 0.5)", radius: 6 }} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {categoryData.map((_, i) => (
                  <Cell key={i} fill={CAT_COLORS[i]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          )}

          {/* Mini category legend */}
          <div className="flex gap-6 mt-1 pt-4 border-t border-border">
            {categoryData.map((d, i) => (
              <div key={d.name} className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: CAT_COLORS[i] }} />
                <span className="text-[11px] text-muted-foreground">{d.name.split(" /")[0]} <span className="font-semibold text-foreground">{d.value.toLocaleString()}</span></span>
              </div>
            ))}
          </div>
        </div>

        {/* Approval breakdown — CSS conic-gradient donut */}
        <div className="bg-card border border-border rounded-2xl p-5 lg:col-span-2 flex flex-col">
          {/* Was "Approval Breakdown". Nothing here is an approval. */}
          <SectionHeader
            title="Status Breakdown"
            sub={
              statusData.length > 0
                ? `${statusData[0].value.toLocaleString()} of ${statusTotal.toLocaleString()} cleared`
                : statusCountsFailed ? "The counts could not be read" : "Counting…"
            }
          />

          <CSSDonut data={statusData} total={statusTotal} />

          <div className="space-y-2 mt-3">
            {statusData.map((d) => {
              const pct = statusTotal > 0 ? ((d.value / statusTotal) * 100).toFixed(1) : "0.0";
              return (
                <div key={d.name} className="flex items-center gap-2.5">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: STATUS_COLORS[d.name] }} />
                  <span className="flex-1 text-[11px] text-muted-foreground truncate">{d.name}</span>
                  <span className="text-[11px] font-semibold text-foreground tabular-nums">{d.value.toLocaleString()}</span>
                  <span className="text-[10px] text-muted-foreground w-9 text-right tabular-nums">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Review Queue */}
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-foreground">Review Queue</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">Active assets not yet verified</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-muted-foreground">
              Showing {reviewAssets.length} of{" "}
              <span className="font-semibold text-amber-600 dark:text-amber-400">{reviewQueueText}</span>
            </span>
            <button
              onClick={() => setLocation("/assets/list")}
              className="flex items-center gap-1 text-xs font-semibold text-primary hover:opacity-80 transition-opacity"
            >
              View all <ArrowUpRight size={12} />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full" data-testid="table-review-queue">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Asset</th>
                <th className="text-left px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Category</th>
                <th className="text-left px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Status</th>
                <th className="text-left px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Custodian</th>
                <th className="text-left px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Location</th>
              </tr>
            </thead>
            <tbody>
              {reviewAssets.map((asset, i) => (
                <tr
                  key={asset.id}
                  className="border-b border-border/60 last:border-0 hover:bg-muted/30 transition-colors group"
                  data-testid={`row-review-${asset.id}`}
                >
                  <td className="px-6 py-3.5">
                    <div>
                      <p className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">{asset.name}</p>
                      <p className="text-[10px] text-muted-foreground font-mono mt-0.5">{asset.assetTag || asset.legacyCode}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className="text-xs text-muted-foreground">{asset.category.split(" /")[0]}</span>
                  </td>
                  <td className="px-4 py-3.5"><AssetStatusPills status={asset.status} lifecycleState={asset.lifecycleState} /></td>
                  <td className="px-4 py-3.5 text-xs text-muted-foreground">{asset.custodianName ?? `Pool · ${asset.department}`}</td>
                  <td className="px-4 py-3.5 text-xs text-muted-foreground max-w-[160px] truncate">{asset.location.office}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
