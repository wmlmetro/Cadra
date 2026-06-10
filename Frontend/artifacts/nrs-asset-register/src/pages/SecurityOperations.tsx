import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchSecurityKpis, fetchSecurityMap, fetchSecurityRecent,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  AlertCircle, Clock, ShieldAlert, Users, ArrowDown, ArrowUp, AlertTriangle, RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function SecurityOperations() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Security Operations");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis   = useQuery({ queryKey: ["security-kpis"],   queryFn: fetchSecurityKpis,   staleTime: 30_000 });
  const map    = useQuery({ queryKey: ["security-map"],    queryFn: fetchSecurityMap,    staleTime: 60_000 });
  const recent = useQuery({ queryKey: ["security-recent"], queryFn: fetchSecurityRecent, staleTime: 30_000 });

  const pins = useMemo<MapPinData[]>(() => {
    const list = map.data?.locations ?? [];
    return list
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
        count: l.open_incidents || undefined,
      }));
  }, [map.data]);

  const err = (kpis.error ?? map.error ?? recent.error) as CadraApiError | null;

  if (kpis.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading Security Operations…</p>
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
  if (!kpis.data) return null;

  const k = kpis.data;

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">Security Operations</h1>
          <p className="text-xs text-muted-foreground mt-1">Incidents, guard deployment, and access control across all sites.</p>
        </div>
        <button onClick={() => { kpis.refetch(); map.refetch(); recent.refetch(); }} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent">
          <RefreshCw size={12} className={cn((kpis.isFetching || map.isFetching || recent.isFetching) && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* Three KPI groups */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2"><ShieldAlert size={14} className="text-red-500" /><p className="text-[12px] font-bold uppercase tracking-wider">Incidents</p></div>
          <div className="grid grid-cols-2 gap-3">
            <KpiCell label="Open"      value={k.incidents.open}     color="text-red-600 dark:text-red-400" />
            <KpiCell label="Critical"  value={k.incidents.critical} color="text-red-600 dark:text-red-400" />
            <KpiCell label="High"      value={k.incidents.high}     color="text-amber-600 dark:text-amber-400" />
            <KpiCell label="Today"     value={k.incidents.today}    color="text-foreground" />
            <KpiCell label="This week" value={k.incidents.this_week} color="text-foreground" />
          </div>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2"><Users size={14} className="text-blue-500" /><p className="text-[12px] font-bold uppercase tracking-wider">Guards</p></div>
          <div className="grid grid-cols-2 gap-3">
            <KpiCell label="Total"   value={k.guards.total}   color="text-foreground" />
            <KpiCell label="On duty" value={k.guards.on_duty} color="text-green-600 dark:text-green-400" />
          </div>
        </div>
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2"><ArrowDown size={14} className="text-green-500" /><p className="text-[12px] font-bold uppercase tracking-wider">Access today</p></div>
          <div className="grid grid-cols-2 gap-3">
            <KpiCell label="Entered" value={k.access.today_in}  icon={ArrowDown}      color="text-green-600 dark:text-green-400" />
            <KpiCell label="Exited"  value={k.access.today_out} icon={ArrowUp}        color="text-blue-600 dark:text-blue-400" />
            <KpiCell label="Flagged" value={k.access.flagged}   icon={AlertTriangle}  color="text-red-600 dark:text-red-400" />
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Site coverage ({pins.length} sites)</h2>
        <NigeriaMap pins={pins} height={380} />
      </div>

      {/* Recent incidents */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Recent incidents</h2>
        {(recent.data ?? []).length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">No recent incidents.</p>
        ) : (
          <ul className="divide-y divide-border">
            {(recent.data ?? []).map(r => (
              <li key={r.id} className="py-2.5 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-mono font-semibold truncate">{r.name}</p>
                  <p className="text-[11px] text-muted-foreground truncate">{r.location}</p>
                </div>
                <span className={cn(
                  "shrink-0 inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                  r.severity === "critical" && "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400",
                  r.severity === "high"     && "bg-orange-50 dark:bg-orange-950/30 border-orange-200/70 text-orange-700 dark:text-orange-400",
                  !["critical", "high"].includes(r.severity) && "bg-muted border-border text-muted-foreground",
                )}>{r.severity || r.stage}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function KpiCell({ label, value, color, icon: Icon }: { label: string; value: number; color: string; icon?: typeof ShieldAlert }) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        {Icon && <Icon size={10} className={color} />}
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      </div>
      <p className={cn("text-[20px] font-extrabold leading-none tabular-nums mt-1", color)}>{value.toLocaleString()}</p>
    </div>
  );
}
