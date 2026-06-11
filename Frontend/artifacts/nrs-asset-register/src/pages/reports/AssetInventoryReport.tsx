import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchDashboardKpis, fetchDashboardMap } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
} from "recharts";
import {
  AlertCircle, Clock, Package, BookOpen, TrendingUp, TrendingDown, RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

// NRS brand red — used for the bar chart so the report matches the rest of the
// dashboard surface.
const NRS_RED = "#E01F26";

export default function AssetInventoryReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Asset Inventory by Category");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis = useQuery({
    queryKey: ["report-inventory-kpis"],
    queryFn: fetchDashboardKpis,
    staleTime: 60_000,
  });
  const map = useQuery({
    queryKey: ["report-inventory-map"],
    queryFn: fetchDashboardMap,
    staleTime: 60_000,
  });

  const categories = useMemo(() => {
    const c = kpis.data?.assets?.categories ?? [];
    return [...c].sort((a, b) => b.count - a.count);
  }, [kpis.data]);

  const totalAssets = kpis.data?.assets?.total ?? 0;
  const top = categories[0];
  const bottom = categories[categories.length - 1];

  const pins = useMemo<MapPinData[]>(() => {
    return (map.data?.locations ?? [])
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
        count: l.open_requests || undefined,
      }));
  }, [map.data]);

  const err = (kpis.error ?? map.error) as CadraApiError | null;

  const refresh = () => { kpis.refetch(); map.refetch(); };

  if (kpis.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading inventory…</p>
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

  const tiles = [
    { label: "Total assets",   value: totalAssets.toLocaleString(),                       icon: Package,      color: "text-foreground" },
    { label: "Categories",     value: categories.length.toLocaleString(),                 icon: BookOpen,     color: "text-blue-600 dark:text-blue-400" },
    { label: "Top category",   value: top    ? `${top.name} · ${top.count.toLocaleString()}` : "—",      icon: TrendingUp,   color: "text-green-600 dark:text-green-400" },
    { label: "Smallest",       value: bottom ? `${bottom.name} · ${bottom.count.toLocaleString()}` : "—", icon: TrendingDown, color: "text-amber-600 dark:text-amber-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <span className="inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider"
                style={{ background: NRS_RED, color: "white" }}>NRS</span>
          <div>
            <h1 className="text-xl font-bold text-foreground">Asset Inventory by Category</h1>
            <p className="text-xs text-muted-foreground mt-1">
              At-a-glance composition of {totalAssets.toLocaleString()} assets across {categories.length} categories.
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn((kpis.isFetching || map.isFetching) && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {tiles.map(t => (
          <div key={t.label} className="bg-card border border-border/50 rounded-2xl px-4 py-4">
            <div className="flex items-center gap-1.5 mb-2">
              <t.icon size={12} className={t.color} />
              <p className={cn("text-[10px] font-semibold uppercase tracking-widest", t.color)}>{t.label}</p>
            </div>
            <p className={cn(
              "font-extrabold leading-tight tabular-nums",
              typeof t.value === "string" && t.value.length > 14 ? "text-[14px]" : "text-[26px]",
              t.color,
            )}>
              {t.value}
            </p>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Assets by category</h2>
        {categories.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-8 text-center">
            No category data available from the API.
          </p>
        ) : (
          <div style={{ width: "100%", height: 380 }}>
            <ResponsiveContainer>
              <BarChart
                data={categories}
                margin={{ top: 10, right: 20, left: 0, bottom: 60 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  interval={0}
                  angle={-30}
                  textAnchor="end"
                  height={70}
                />
                <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  cursor={{ fill: "hsl(var(--muted))", opacity: 0.3 }}
                />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {categories.map((c, i) => (
                    <Cell key={c.id ?? c.name ?? i} fill={NRS_RED} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Coverage map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Asset locations ({pins.length} mapped sites)</h2>
        <NigeriaMap pins={pins} height={380} />
      </div>
    </div>
  );
}
