import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchFleetDashboard, type FleetDashboard } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  AlertCircle, Clock, Wrench, ShieldCheck, AlertTriangle, HelpCircle, RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import BrandPill from "@/components/BrandPill";

// Donut palette — mirrors the badge colors used in FleetCommandCenter so
// "overdue" stays red, "due_soon" amber, "ok" green, "no_schedule" grey.
const STATE_COLORS: Record<string, string> = {
  // Status semantics, NOT brand: green/amber/red/grey read as good/warning/bad.
  // Deliberately fixed rather than following the tenant colour — on GTB orange,
  // "overdue" would be indistinguishable from "due soon".
  ok: "#22c55e",
  due_soon: "#f59e0b",
  overdue: "#E01F26",
  no_schedule: "#94a3b8",
};

const STATE_LABEL: Record<string, string> = {
  ok: "On schedule",
  due_soon: "Due in 30 days",
  overdue: "Overdue",
  no_schedule: "Never scheduled",
};

export default function MaintenanceReadinessReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Maintenance Readiness Report");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const fleet = useQuery<FleetDashboard, CadraApiError>({
    queryKey: ["report-maint-readiness"],
    queryFn: fetchFleetDashboard,
    staleTime: 60_000,
  });

  // The fleet/dashboard payload doesn't expose `no_schedule` as a kpi; it's
  // implicit (total - ok - due_soon - overdue). We also re-derive from the
  // per-vehicle list as a cross-check so the donut shows the same number the
  // table below would.
  const noSchedule = useMemo(() => {
    const list = fleet.data?.vehicles ?? [];
    return list.filter(v => v.maint_status === "no_schedule").length;
  }, [fleet.data]);

  const donutData = useMemo(() => {
    const k = fleet.data?.kpis;
    if (!k) return [];
    return [
      { key: "ok",          name: STATE_LABEL.ok,          value: k.ok },
      { key: "due_soon",    name: STATE_LABEL.due_soon,    value: k.due_soon },
      { key: "overdue",     name: STATE_LABEL.overdue,     value: k.overdue },
      { key: "no_schedule", name: STATE_LABEL.no_schedule, value: noSchedule },
    ].filter(d => d.value > 0);
  }, [fleet.data, noSchedule]);

  const overdueRows = useMemo(() => {
    return (fleet.data?.vehicles ?? []).filter(v => v.maint_status === "overdue");
  }, [fleet.data]);

  if (fleet.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading maintenance readiness…</p>
    </div>
  );
  if (fleet.error) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{fleet.error.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{fleet.error.message}</p>
        </div>
      </div>
    </div>
  );
  if (!fleet.data) return null;

  const k = fleet.data.kpis;
  const pctOk = k.total > 0 ? Math.round((k.ok / k.total) * 100) : 0;

  const tiles = [
    { label: "% on schedule",      value: `${pctOk}%`,                 icon: ShieldCheck,   color: "text-green-600 dark:text-green-400" },
    { label: "Overdue",            value: k.overdue.toLocaleString(),  icon: AlertTriangle, color: "text-red-600 dark:text-red-400" },
    { label: "Due in 30 days",     value: k.due_soon.toLocaleString(), icon: Wrench,        color: "text-amber-600 dark:text-amber-400" },
    { label: "Never scheduled",    value: noSchedule.toLocaleString(), icon: HelpCircle, color: "text-muted-foreground" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <BrandPill />
          <div>
            <h1 className="text-xl font-bold text-foreground">Maintenance Readiness Report</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Preventive-maintenance health across {k.total.toLocaleString()} vehicles.
            </p>
          </div>
        </div>
        <button
          onClick={() => fleet.refetch()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn(fleet.isFetching && "animate-spin")} /> Refresh
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
            <p className={cn("text-[28px] font-extrabold leading-none tabular-nums", t.color)}>
              {t.value}
            </p>
          </div>
        ))}
      </div>

      {/* Donut + overdue table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">Maintenance state mix</h2>
          {donutData.length === 0 ? (
            <p className="text-[12px] text-muted-foreground py-8 text-center">No fleet data.</p>
          ) : (
            <div style={{ width: "100%", height: 320 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={donutData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                  >
                    {donutData.map(d => (
                      <Cell key={d.key} fill={STATE_COLORS[d.key]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Legend
                    iconSize={10}
                    wrapperStyle={{ fontSize: 11 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 bg-card border border-border rounded-2xl p-5">
          <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
            <h2 className="text-[13px] font-bold">Overdue vehicles</h2>
            <span className="text-xs text-muted-foreground">
              <span className="font-bold text-red-600 dark:text-red-400">{overdueRows.length.toLocaleString()}</span> requiring action
            </span>
          </div>
          {overdueRows.length === 0 ? (
            <p className="text-[12px] text-muted-foreground py-8 text-center">
              No overdue vehicles. Fleet is fully on-schedule.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-border">
                    {["Plate", "Vehicle", "Driver", "Location", "Next Service"].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {overdueRows.slice(0, 200).map(v => (
                    <tr key={v.id} className="border-b border-border/40 hover:bg-muted/20">
                      <td className="px-3 py-2 text-[12px] font-mono">{v.license}</td>
                      <td className="px-3 py-2 text-[12px] font-semibold">{v.brand} {v.model}</td>
                      <td className="px-3 py-2 text-[12px] truncate max-w-[160px]">{v.driver || <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2 text-[12px] truncate max-w-[200px]">{v.location || <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2 text-[12px] tabular-nums">{v.next_service || <span className="text-muted-foreground">—</span>}</td>
                    </tr>
                  ))}
                  {overdueRows.length > 200 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-3 text-[11px] text-center text-muted-foreground italic">
                        …showing first 200 of {overdueRows.length.toLocaleString()}.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
