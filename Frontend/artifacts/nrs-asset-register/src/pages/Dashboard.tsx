import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { useLocation } from "wouter";
import {
  getDashboardStats, getReviewQueueAssets,
  getAssetsByCategory, getAssetsByStatus,
  fetchTotals, fetchAssetsPage, fetchDashboardKpis, fetchDashboardMap,
} from "@/lib/dataProvider";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import StatusPill from "@/components/StatusPill";
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
  "Review — allottee not in nominal roll": "#f97316",
  "Review — VIN not verifiable": "#eab308",
  "Review — possible duplicate": "#a855f7",
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
  const cleared = data[0];
  const pct = ((cleared.value / total) * 100).toFixed(0);

  return (
    <div className="flex items-center justify-center py-4">
      <div className="relative" style={{ width: 148, height: 148, flexShrink: 0 }}>
        <div
          className="w-full h-full rounded-full"
          style={{ background: gradient }}
        />
        {/* inner mask */}
        <div
          className="absolute inset-0 rounded-full bg-card flex flex-col items-center justify-center"
          style={{ margin: "26px" }}
        >
          <span className="text-[22px] font-extrabold text-foreground leading-none tabular-nums">{pct}%</span>
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
  // Real totals from the API (cheap — uses total_estimate). Category breakdown
  // and statusData stay on mocks until backend ships an aggregate endpoint.
  const { data: totals } = useQuery({
    queryKey: ["dashboard", "totals"],
    queryFn: fetchTotals,
    staleTime: 60_000,
  });
  // Review queue sample = first page of unverified assets.
  const { data: reviewPage } = useQuery({
    queryKey: ["dashboard", "review-queue"],
    queryFn: () => fetchAssetsPage(undefined, { status: "Review — data quality" }),
    staleTime: 60_000,
  });
  // Server-aggregated KPIs — replaces hardcoded fleet/locations/requests
  // counts. Cheap single round-trip via /api/v1/dashboard/kpis.
  const { data: realKpis } = useQuery({
    queryKey: ["dashboard", "kpis"],
    queryFn: fetchDashboardKpis,
    staleTime: 30_000,
  });

  const stats = {
    ...mockStats,
    totalAssets:   totals?.assets             ?? mockStats.totalAssets,
    locations:     realKpis?.locations.total  ?? totals?.locations  ?? mockStats.locations,
    employees:     totals?.employees          ?? mockStats.employees,
    fleetVehicles: realKpis?.fleet.total      ?? mockStats.fleetVehicles,
    reviewQueue:   realKpis?.requests.open    ?? reviewPage?.totalEstimate ?? mockStats.reviewQueue,
  };
  const reviewAssets = reviewPage?.assets.slice(0, 8) ?? getReviewQueueAssets();
  const categoryData = getAssetsByCategory();   // mock — no API aggregate
  const statusData = getAssetsByStatus();       // mock — no API aggregate

  // Map pins from /api/v1/dashboard/map.locations — already deduped & geocoded
  // server-side, way cheaper than walking every Location record.
  const { data: mapData } = useQuery({
    queryKey: ["dashboard", "map"],
    queryFn: fetchDashboardMap,
    staleTime: 60_000,
  });
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

  useEffect(() => {
    setTitle("Facility Command Center");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const now = new Date();
  const dateStr = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="p-6 space-y-6 max-w-[1440px] mx-auto">

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">{greeting}, Admin</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{dateStr} — Asset Register overview</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800/40 rounded-xl">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[11px] font-semibold text-green-700 dark:text-green-400">All systems operational</span>
          </div>
        </div>
      </div>

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
              {stats.totalAssets.toLocaleString()}
            </p>
            <div className="flex gap-4 mt-3 pt-3 border-t border-border">
              <div>
                <p className="text-[10px] uppercase tracking-wider font-medium text-blue-500">IT</p>
                <p className="text-sm font-bold text-foreground tabular-nums">{stats.itEquipment.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider font-medium text-emerald-500">Fleet</p>
                <p className="text-sm font-bold text-foreground tabular-nums">{stats.fleetVehicles.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider font-medium text-amber-500">Furn.</p>
                <p className="text-sm font-bold text-foreground tabular-nums">{stats.furniture.toLocaleString()}</p>
              </div>
            </div>
          </div>
        </div>

        <StatCard
          label="Locations"
          value={stats.locations.toLocaleString()}
          sub="7 zones · 38 states · 857 offices"
          accent="#3b82f6"
          icon={MapPin}
          onClick={() => setLocation("/locations")}
        />
        <StatCard
          label="Employees"
          value={stats.employees.toLocaleString()}
          sub="Registered across all zones"
          accent="#10b981"
          icon={Users}
        />

        {/* Review Queue — highlighted */}
        <div
          className="relative bg-amber-50 dark:bg-amber-950/20 rounded-2xl border border-amber-200 dark:border-amber-800/40 p-6 overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5"
          onClick={() => {}}
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
              {stats.reviewQueue.toLocaleString()}
            </p>
            <p className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-800/40 text-[11px] text-amber-700/70 dark:text-amber-500/80 leading-relaxed">
              Assets pending data quality review
            </p>
          </div>
        </div>
      </div>

      {/* NRS Office Locations map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <SectionHeader
          title="NRS Office Locations"
          sub={`${officePins.length} distinct sites across Nigeria`}
        />
        <NigeriaMap pins={officePins} height={380} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Bar chart */}
        <div className="bg-card border border-border rounded-2xl p-5 lg:col-span-3">
          <SectionHeader
            title="Assets by Category"
            sub="Breakdown across three primary asset classes"
          />
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
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
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
          <SectionHeader
            title="Approval Breakdown"
            sub={`${statusData[0].value.toLocaleString()} of ${stats.totalAssets.toLocaleString()} cleared`}
          />

          <CSSDonut data={statusData} total={stats.totalAssets} />

          <div className="space-y-2 mt-3">
            {statusData.map((d) => {
              const pct = ((d.value / stats.totalAssets) * 100).toFixed(1);
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
            <p className="text-[11px] text-muted-foreground mt-0.5">Assets flagged for data quality review</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-muted-foreground">
              Showing {reviewAssets.length} of{" "}
              <span className="font-semibold text-amber-600 dark:text-amber-400">{stats.reviewQueue.toLocaleString()}</span>
            </span>
            <button
              onClick={() => setLocation("/assets")}
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
                  <td className="px-4 py-3.5"><StatusPill status={asset.status} /></td>
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
