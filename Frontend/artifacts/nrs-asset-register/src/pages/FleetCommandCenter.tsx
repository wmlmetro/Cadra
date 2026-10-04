import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchFleetDashboard, fetchFleetMap, type FleetDashboard } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  AlertCircle, Clock, Car, Bus, Wrench, ShieldCheck, AlertTriangle,
  Calendar, RefreshCw, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEnumLabel } from "@/hooks/useEnums";

export default function FleetCommandCenter() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Fleet Command Center");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const fleet = useQuery<FleetDashboard, CadraApiError>({
    queryKey: ["fleet-dashboard"],
    queryFn: fetchFleetDashboard,
    staleTime: 60_000,
  });
  // `GET /fleet/map` since handoff 50 §2.1 — the vehicle rows left
  // `/dashboard/map`, which now carries locations only.
  const map = useQuery({
    queryKey: ["fleet-map"],
    queryFn: fetchFleetMap,
    staleTime: 60_000,
  });

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // `/fleet/dashboard` sends `fuel_type` as the raw selection key, and this
  // table used to print it — a row reading `plug_in_hybrid_diesel`. The label
  // is the model's own, read from /meta/enums.
  const fuelLabel = useEnumLabel("fuel_type");

  const vehicles = useMemo(() => {
    const r = fleet.data?.vehicles ?? [];
    return r.filter(v => {
      if (statusFilter && v.maint_status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return v.name.toLowerCase().includes(q) ||
               v.license.toLowerCase().includes(q) ||
               (v.driver ?? "").toLowerCase().includes(q);
      }
      return true;
    });
  }, [fleet.data, search, statusFilter]);

  const pins = useMemo<MapPinData[]>(() => {
    const list = map.data?.fleet ?? [];
    return list
      .filter(v => Number.isFinite(v.lat) && Number.isFinite(v.lng))
      .map(v => ({
        id: String(v.id),
        lat: v.lat,
        lng: v.lng,
        label: v.name,
        sublabel: [v.plate, v.driver].filter(Boolean).join(" · "),
      }));
  }, [map.data]);

  if (fleet.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading Fleet Command Center…</p>
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
  const tiles = [
    { label: "Total",                value: k.total,                icon: Car,            color: "text-foreground" },
    { label: "Active",               value: k.active,               icon: Car,            color: "text-green-600 dark:text-green-400" },
    { label: "Maintenance due",      value: k.due_soon,             icon: Wrench,         color: "text-amber-600 dark:text-amber-400" },
    { label: "Overdue",              value: k.overdue,              icon: AlertTriangle,  color: "text-red-600 dark:text-red-400" },
    { label: "OK",                   value: k.ok,                   icon: ShieldCheck,    color: "text-green-600 dark:text-green-400" },
    { label: "Staff buses",          value: k.staff_buses,          icon: Bus,            color: "text-blue-600 dark:text-blue-400" },
    { label: "Insurance expiring",   value: k.expiring_insurance,   icon: Calendar,       color: "text-amber-600 dark:text-amber-400" },
    { label: "Roadworthy expiring",  value: k.expiring_roadworthy,  icon: Calendar,       color: "text-amber-600 dark:text-amber-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">Fleet Command Center</h1>
          <p className="text-xs text-muted-foreground mt-1">
            {k.total.toLocaleString()} vehicles · {k.vendors} service vendors ({k.approved_vendors} approved)
          </p>
        </div>
        <button onClick={() => fleet.refetch()} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent">
          <RefreshCw size={12} className={cn(fleet.isFetching && "animate-spin")} /> Refresh
        </button>
      </div>

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

      {/* Fleet map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Vehicle deployment ({pins.length} vehicles plotted)</h2>
        <NigeriaMap pins={pins} height={360} />
      </div>

      {/* Fleet register table */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
          <h2 className="text-[13px] font-bold">Fleet register</h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search plate, name, driver…"
                className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background w-56"
              />
            </div>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background"
            >
              <option value="">All statuses</option>
              <option value="ok">OK</option>
              <option value="due_soon">Due soon</option>
              <option value="overdue">Overdue</option>
              <option value="no_schedule">No schedule</option>
            </select>
            <span className="text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{vehicles.length}</span> of {k.total.toLocaleString()}
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead>
              <tr className="border-b border-border">
                {["Vehicle", "Plate", "Driver", "Location", "Maintenance", "Fuel", "Odometer"].map(h => (
                  <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {vehicles.slice(0, 200).map(v => (
                <tr key={v.id} className="border-b border-border/40 hover:bg-muted/20">
                  <td className="px-3 py-2 text-[12px]">
                    <p className="font-semibold">{v.brand} {v.model}</p>
                    <p className="text-[10px] text-muted-foreground">{v.is_staff_bus ? "Staff bus" : "Vehicle"}</p>
                  </td>
                  <td className="px-3 py-2 text-[12px] font-mono">{v.license}</td>
                  <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">{v.driver}</td>
                  <td className="px-3 py-2 text-[12px] truncate max-w-[200px]">{v.location}</td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                      v.maint_status === "ok"          && "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400",
                      v.maint_status === "due_soon"    && "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 text-amber-700 dark:text-amber-400",
                      v.maint_status === "overdue"     && "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400",
                      v.maint_status === "no_schedule" && "bg-muted border-border text-muted-foreground",
                    )}>{v.maint_status.replace("_", " ")}</span>
                  </td>
                  <td className="px-3 py-2 text-[12px]">{fuelLabel(v.fuel_type)}</td>
                  <td className="px-3 py-2 text-[12px] tabular-nums">{v.odometer.toLocaleString()}</td>
                </tr>
              ))}
              {vehicles.length > 200 && (
                <tr><td colSpan={7} className="px-3 py-3 text-[11px] text-center text-muted-foreground italic">…showing first 200 of {vehicles.length.toLocaleString()}; refine filters to narrow.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
