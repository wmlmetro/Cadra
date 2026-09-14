import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchFleetDashboard, type FleetDashboard } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  AlertCircle, Clock, Car, Bus, Users, RefreshCw, Search, ArrowUpDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import BrandPill from "@/components/BrandPill";
import { useEnum } from "@/hooks/useEnums";
import { enumLabel } from "@/lib/enums";

// Sortable columns over the fleet vehicle roster. The "fuel" column maps to
// fuel_type because the backend doesn't expose per-vehicle fuel level — this
// report is a roster, not a fuel-status view. It shows the model's LABEL for
// the key the API sends; printing the key itself put `plug_in_hybrid_gasoline`
// in an auditor-facing report.
type SortKey = "license" | "name" | "driver" | "location" | "maint_status" | "fuel_type";

export default function FleetRosterReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();

  useEffect(() => {
    setTitle("Fleet Roster Report");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const fleet = useQuery<FleetDashboard, CadraApiError>({
    queryKey: ["report-fleet-roster"],
    queryFn: fetchFleetDashboard,
    staleTime: 60_000,
  });

  // `fuel_type` arrives as the raw selection key. The roster prints — and
  // sorts by — the model's label, so the Fuel column orders the way the reader
  // sees it rather than by a key they are never shown.
  const fuelOptions = useEnum("fuel_type");

  const [search, setSearch] = useState("");
  const [maintFilter, setMaintFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("license");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const rows = useMemo(() => {
    const all = fleet.data?.vehicles ?? [];
    const q = search.trim().toLowerCase();
    const filtered = all.filter(v => {
      if (maintFilter && v.maint_status !== maintFilter) return false;
      if (!q) return true;
      return v.license.toLowerCase().includes(q) ||
             v.name.toLowerCase().includes(q) ||
             (v.driver ?? "").toLowerCase().includes(q) ||
             (v.location ?? "").toLowerCase().includes(q);
    });
    const key = (v: FleetDashboard["vehicles"][number]) =>
      sortKey === "fuel_type"
        ? enumLabel(fuelOptions, v.fuel_type)
        : ((v[sortKey] ?? "") as string);
    const sorted = [...filtered].sort((a, b) => {
      const cmp = key(a).localeCompare(key(b));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [fleet.data, search, maintFilter, sortKey, sortDir, fuelOptions]);

  const driverCount = useMemo(() =>
    (fleet.data?.vehicles ?? []).filter(v => v.driver && v.driver.trim()).length,
    [fleet.data],
  );

  function toggleSort(k: SortKey) {
    if (k === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("asc"); }
  }

  if (fleet.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading Fleet Roster…</p>
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
    { label: "Total vehicles", value: k.total,       icon: Car,   color: "text-foreground" },
    { label: "With driver",    value: driverCount,   icon: Users, color: "text-green-600 dark:text-green-400" },
    { label: "Staff buses",    value: k.staff_buses, icon: Bus,   color: "text-blue-600 dark:text-blue-400" },
    { label: "Active",         value: k.active,      icon: Car,   color: "text-green-600 dark:text-green-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <BrandPill />
          <div>
            <h1 className="text-xl font-bold text-foreground">Fleet Roster Report</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Canonical roster of {k.total.toLocaleString()} NRS vehicles — who has what, where.
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
              {t.value.toLocaleString()}
            </p>
          </div>
        ))}
      </div>

      {/* Filters + table */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
          <h2 className="text-[13px] font-bold">Vehicle roster</h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search plate, driver, location…"
                className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background w-64"
              />
            </div>
            <select
              value={maintFilter}
              onChange={e => setMaintFilter(e.target.value)}
              className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background"
            >
              <option value="">All maint statuses</option>
              <option value="ok">OK</option>
              <option value="due_soon">Due soon</option>
              <option value="overdue">Overdue</option>
              <option value="no_schedule">No schedule</option>
            </select>
            <span className="text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span> of {k.total.toLocaleString()}
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px]">
            <thead>
              <tr className="border-b border-border">
                {([
                  ["license", "Plate"],
                  ["name", "Vehicle"],
                  ["driver", "Driver"],
                  ["location", "Location"],
                  ["maint_status", "Maint Status"],
                  ["fuel_type", "Fuel"],
                ] as Array<[SortKey, string]>).map(([key, label]) => (
                  <th key={key} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                    <button
                      onClick={() => toggleSort(key)}
                      className="inline-flex items-center gap-1 hover:text-foreground"
                    >
                      {label}
                      <ArrowUpDown size={9} className={cn("opacity-50", sortKey === key && "opacity-100 text-primary")} />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 300).map(v => (
                <tr key={v.id} className="border-b border-border/40 hover:bg-muted/20">
                  <td className="px-3 py-2 text-[12px] font-mono">{v.license}</td>
                  <td className="px-3 py-2 text-[12px]">
                    <p className="font-semibold">{v.brand} {v.model}</p>
                    <p className="text-[10px] text-muted-foreground">{v.is_staff_bus ? "Staff bus" : "Vehicle"}</p>
                  </td>
                  <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">{v.driver || <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2 text-[12px] truncate max-w-[200px]">{v.location || <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                      v.maint_status === "ok"          && "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400",
                      v.maint_status === "due_soon"    && "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 text-amber-700 dark:text-amber-400",
                      v.maint_status === "overdue"     && "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400",
                      v.maint_status === "no_schedule" && "bg-muted border-border text-muted-foreground",
                    )}>{v.maint_status.replace("_", " ")}</span>
                  </td>
                  <td className="px-3 py-2 text-[12px]">{enumLabel(fuelOptions, v.fuel_type) || <span className="text-muted-foreground">—</span>}</td>
                </tr>
              ))}
              {rows.length > 300 && (
                <tr>
                  <td colSpan={6} className="px-3 py-3 text-[11px] text-center text-muted-foreground italic">
                    …showing first 300 of {rows.length.toLocaleString()}; refine filters to narrow.
                  </td>
                </tr>
              )}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-[12px] text-center text-muted-foreground">
                    No vehicles match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
