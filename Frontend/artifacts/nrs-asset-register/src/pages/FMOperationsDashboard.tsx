import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchFmDashboard, type FmDashboard } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  AlertCircle, Clock, Inbox, AlertTriangle, ArrowUpRight, CheckCircle2,
  RefreshCw, Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function FMOperationsDashboard() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("FM Operations Dashboard");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const { data, isLoading, error, refetch, isFetching } = useQuery<FmDashboard, CadraApiError>({
    queryKey: ["fm-dashboard"],
    queryFn: fetchFmDashboard,
    staleTime: 30_000,
  });

  const pins = useMemo<MapPinData[]>(() => {
    if (!data?.map_locations) return [];
    return data.map_locations
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
        count: l.open_requests || undefined,
      }));
  }, [data]);

  if (isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading FM Operations…</p>
    </div>
  );
  if (error) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{error.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{error.message}</p>
        </div>
      </div>
    </div>
  );
  if (!data) return null;

  const k = data.kpis;
  const tiles = [
    { label: "Open requests",  value: k.open,           icon: Inbox,         color: "text-red-600 dark:text-red-400"     },
    { label: "Overdue",        value: k.overdue,        icon: Clock,         color: "text-amber-600 dark:text-amber-400" },
    { label: "Escalated",      value: k.escalated,      icon: AlertTriangle, color: "text-orange-600 dark:text-orange-400" },
    { label: "In progress",    value: k.in_progress,    icon: Activity,      color: "text-blue-600 dark:text-blue-400"   },
    { label: "Resolved today", value: k.resolved_today, icon: CheckCircle2,  color: "text-green-600 dark:text-green-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">FM Operations Dashboard</h1>
          <p className="text-xs text-muted-foreground mt-1">Triage inbox, SLA by domain, and team workload across all NRS sites.</p>
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn(isFetching && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map(t => (
          <div key={t.label} className="bg-card border border-border/50 rounded-2xl px-4 py-4">
            <div className="flex items-center gap-1.5 mb-2">
              <t.icon size={12} className={t.color} />
              <p className={cn("text-[10px] font-semibold uppercase tracking-widest", t.color)}>{t.label}</p>
            </div>
            <p className={cn("text-[28px] font-extrabold leading-none tabular-nums", t.color)}>
              {t.value.toLocaleString()}
            </p>
          </div>
        ))}
      </div>

      {/* SLA table + Team workload */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">SLA status by domain</h2>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {["Domain", "Open", "Overdue", "Escalated", "SLA"].map(h => (
                  <th key={h} className="text-left px-2 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.sla_data.map(d => (
                <tr key={d.domain} className="border-b border-border/40">
                  <td className="px-2 py-2.5 text-[13px] font-semibold">{d.domain}</td>
                  <td className="px-2 py-2.5 text-[12px] text-foreground tabular-nums">{d.open}</td>
                  <td className="px-2 py-2.5 text-[12px] text-foreground tabular-nums">{d.overdue}</td>
                  <td className="px-2 py-2.5 text-[12px] text-foreground tabular-nums">{d.escalated}</td>
                  <td className={cn("px-2 py-2.5 text-[12px] font-bold tabular-nums",
                    d.sla_pct === 100 ? "text-green-600 dark:text-green-400" :
                    d.sla_pct >= 80 ? "text-amber-600 dark:text-amber-400" :
                    "text-red-600 dark:text-red-400",
                  )}>{d.sla_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">Team workload</h2>
          {(!data.team_workload || data.team_workload.length === 0) ? (
            <p className="text-[12px] text-muted-foreground py-4 text-center">No assigned work.</p>
          ) : (
            <ul className="space-y-2">
              {data.team_workload.map(t => (
                <li key={`${t.user_id}-${t.name}`} className="flex items-center justify-between gap-2 py-1.5 border-b border-border/40 last:border-0">
                  <span className="text-[12px] font-medium truncate">{t.name}</span>
                  <span className="text-[12px] font-bold tabular-nums">{t.assigned}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Recent open requests */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[13px] font-bold">Recent open requests</h2>
          <button onClick={() => nav("/service-desk")} className="text-[11px] font-semibold text-primary hover:opacity-80 inline-flex items-center gap-1">
            Open service desk <ArrowUpRight size={11} />
          </button>
        </div>
        {data.recent_requests.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">No recent requests.</p>
        ) : (
          <ul className="divide-y divide-border">
            {data.recent_requests.map(r => (
              <li key={r.id} className="py-2.5 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-mono font-semibold text-foreground truncate">{r.name}</p>
                  <p className="text-[11px] text-muted-foreground truncate">
                    {[r.category, r.location].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <span className={cn(
                  "shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                  r.is_overdue ? "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400"
                              : "bg-muted border-border text-muted-foreground",
                )}>
                  {r.stage}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Office locations map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">NRS Office Locations</h2>
        <NigeriaMap pins={pins} height={380} />
      </div>
    </div>
  );
}
