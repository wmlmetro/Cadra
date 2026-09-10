import { useEffect, useMemo } from "react";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import RecordLink from "@/components/RecordLink";
import {
  fetchITAssetsDashboard, fetchDashboardMap,
  type CategoryDashboardData,
} from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import {
  AlertCircle, Clock, RefreshCw, Monitor, ShieldCheck,
  Wrench, ShieldAlert, Trash2, Sparkles, CheckCircle2, AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const CONDITION_COLORS: Record<string, string> = {
  new:     "#22c55e",
  good:    "#10b981",
  fair:    "#f59e0b",
  poor:    "#f97316",
  decommissioned: "#ef4444",
};

export default function ITAssetsCommand() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("IT Assets Command");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const itDash = useQuery<CategoryDashboardData | null, CadraApiError>({
    queryKey: ["it-assets-dashboard"],
    queryFn: fetchITAssetsDashboard,
    staleTime: 60_000,
  });

  // Pins are the global office locations — sites where IT assets live.
  // A per-category map endpoint would be cleaner; this reuses what we have.
  const map = useQuery({
    queryKey: ["dashboard-map"],
    queryFn: fetchDashboardMap,
    staleTime: 60_000,
  });
  const pins = useMemo<MapPinData[]>(() => {
    return (map.data?.locations ?? [])
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
      }));
  }, [map.data]);

  if (itDash.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading IT Assets Command…</p>
    </div>
  );
  if (itDash.error) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{itDash.error.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{itDash.error.message}</p>
          {!apiConfigured && <p className="text-[11px] text-red-700 dark:text-red-400 mt-1">Set VITE_API_TOKEN in .env.local.</p>}
        </div>
      </div>
    </div>
  );
  if (!itDash.data) return (
    <div className="p-8 max-w-md mx-auto text-center">
      <Monitor size={28} className="text-muted-foreground/40 mx-auto mb-3" />
      <p className="text-sm font-semibold text-foreground">No IT category found</p>
      <p className="text-xs text-muted-foreground mt-1">
        The asset-category breakdown didn't include a matching "IT" category. Check that the backend dashboard payload
        emits one before re-running.
      </p>
    </div>
  );

  const d = itDash.data;
  const verifiedShare = d.total ? Math.max(0, d.total - d.unverified) : 0;
  const tiles = [
    { label: "Total IT",      value: d.total,                    icon: Monitor,        color: "text-foreground" },
    { label: "Active",        value: d.active,                   icon: CheckCircle2,   color: "text-green-600 dark:text-green-400" },
    { label: "Under repair",  value: d.inRepair,                 icon: Wrench,         color: "text-amber-600 dark:text-amber-400" },
    { label: "Unverified",    value: d.unverified,               icon: ShieldAlert,    color: "text-red-600 dark:text-red-400" },
    { label: "Verified",      value: verifiedShare,              icon: ShieldCheck,    color: "text-green-600 dark:text-green-400" },
    { label: "New",           value: d.byCondition.new,          icon: Sparkles,       color: "text-emerald-600 dark:text-emerald-400" },
    // Decommissioned assets are retired, not awaiting service, so they are not
    // counted here. Until the condition filter was corrected this sum's second
    // term was always 0, so the number on screen is unchanged.
    { label: "Needs service", value: d.byCondition.poor, icon: AlertTriangle, color: "text-orange-600 dark:text-orange-400" },
    { label: "Disposed",      value: d.disposed,                 icon: Trash2,         color: "text-muted-foreground" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">IT Assets Command</h1>
          <p className="text-xs text-muted-foreground mt-1">
            {d.total.toLocaleString()} {d.categoryName} records · {verifiedShare.toLocaleString()} verified · {d.unverified.toLocaleString()} pending
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { itDash.refetch(); map.refetch(); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <RefreshCw size={12} className={cn((itDash.isFetching || map.isFetching) && "animate-spin")} /> Refresh
          </button>
          <button
            onClick={() => nav("/assets/list")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            Open Asset Register →
          </button>
        </div>
      </div>

      {/* KPI tile strip — mirrors Fleet Command's 8-tile layout */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        {tiles.map(t => (
          <div key={t.label} className="bg-card border border-border/50 rounded-2xl px-3 py-3">
            <div className="flex items-center gap-1.5 mb-1.5">
              <t.icon size={11} className={t.color} />
              <p className={cn("text-[10px] font-semibold uppercase tracking-wide", t.color)}>{t.label}</p>
            </div>
            <p className={cn("text-[20px] font-extrabold leading-none tabular-nums", t.color)}>
              {t.value.toLocaleString()}
            </p>
          </div>
        ))}
      </div>

      {/* Map + Condition breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">IT asset sites ({pins.length} locations)</h2>
          <NigeriaMap pins={pins} height={360} />
        </div>
        <div className="bg-card border border-border rounded-2xl p-5 flex flex-col">
          <h2 className="text-[13px] font-bold mb-3">Condition breakdown</h2>
          <ConditionBars data={d.byCondition} total={d.total} />
          <p className="text-[10px] text-muted-foreground mt-auto pt-3">
            Counts from <code className="font-mono">/api/v1/assets?category_id={d.categoryId}&condition=…</code>
          </p>
        </div>
      </div>

      {/* Recent IT assets */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[13px] font-bold">Recent IT assets</h2>
          <span className="text-[11px] text-muted-foreground">{d.recent.length} most recent</span>
        </div>
        {d.recent.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-6 text-center">No IT assets returned by the API.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead>
                <tr className="border-b border-border">
                  {["Asset", "Tag", "Sub-category", "Office", "Condition", "Custodian"].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.recent.map(a => (
                  <tr key={a.id} onClick={() => nav(`/assets/${a.id}`)} className="border-b border-border/40 hover:bg-muted/20 cursor-pointer">
                    <td className="px-3 py-2 text-[12px] font-semibold text-foreground truncate max-w-[260px]">{a.name}</td>
                    <td className="px-3 py-2 text-[11px] font-mono text-muted-foreground">{a.assetTag || "—"}</td>
                    <td className="px-3 py-2 text-[12px] text-muted-foreground">{a.subcategory || a.assetType || "—"}</td>
                    <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">
                      {a.location.office
                        ? <RecordLink to={`/locations/${a.location.locationId}`} enabled={!!a.location.locationId} subtle>{a.location.office}</RecordLink>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn(
                        "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                        a.condition === "Good" && "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400",
                        a.condition === "Fair" && "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 text-amber-700 dark:text-amber-400",
                        a.condition === "Poor" && "bg-orange-50 dark:bg-orange-950/30 border-orange-200/70 text-orange-700 dark:text-orange-400",
                        a.condition === "Decommissioned" && "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400",
                      )}>{a.condition}</span>
                    </td>
                    <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">
                      {a.custodianName
                        ? <RecordLink to={`/hr/employees/${a.custodianId}`} enabled={!!a.custodianId} subtle>{a.custodianName}</RecordLink>
                        : <span className="text-muted-foreground">Unassigned</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Condition bars (no recharts dep — keeps the page in the light bundle) ──

function ConditionBars({ data, total }: { data: CategoryDashboardData["byCondition"]; total: number }) {
  const rows = [
    { key: "new",     label: "New",     value: data.new },
    { key: "good",    label: "Good",    value: data.good },
    { key: "fair",    label: "Fair",    value: data.fair },
    { key: "poor",    label: "Poor",    value: data.poor },
    { key: "decommissioned", label: "Decommissioned", value: data.decommissioned },
  ];
  const max = Math.max(1, ...rows.map(r => r.value));
  return (
    <ul className="space-y-2.5">
      {rows.map(r => {
        const pct = (r.value / max) * 100;
        const share = total ? Math.round((r.value / total) * 1000) / 10 : 0;
        return (
          <li key={r.key} className="flex items-center gap-3">
            <span className="text-[12px] font-medium text-foreground w-28 shrink-0">{r.label}</span>
            <div className="flex-1 h-2 bg-muted/40 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${Math.max(2, pct)}%`, background: CONDITION_COLORS[r.key] }}
                title={`${r.value.toLocaleString()} (${share}%)`}
              />
            </div>
            <span className="text-[12px] font-bold tabular-nums w-16 text-right shrink-0">{r.value.toLocaleString()}</span>
            <span className="text-[10px] text-muted-foreground tabular-nums w-10 text-right shrink-0">{share}%</span>
          </li>
        );
      })}
    </ul>
  );
}
