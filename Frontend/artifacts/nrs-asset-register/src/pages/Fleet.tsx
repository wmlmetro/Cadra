import { useState, useEffect, useMemo } from "react";
import { useLocation } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  listFleetVehicles, getFleetVehicle, getAsset,
  listFuelTransactions, getFleetStats,
} from "@/lib/dataProvider";
import type { FleetVehicle } from "@/types";
import {
  Car, Bus, Truck, Search, X, ChevronDown,
  MapPin, User, Fuel, ArrowUpRight, Wrench,
  ShieldAlert, Calendar, Gauge, ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_CFG: Record<FleetVehicle["status"], { bg: string; text: string; dot: string }> = {
  "Active":           { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70",  text: "text-green-700 dark:text-green-400",  dot: "bg-green-500"  },
  "In Maintenance":   { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70",  text: "text-amber-700 dark:text-amber-400",  dot: "bg-amber-500"  },
  "Grounded":         { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70",        text: "text-red-700 dark:text-red-400",      dot: "bg-red-500"    },
  "Decommissioned":   { bg: "bg-muted/60 border-border",                             text: "text-muted-foreground",               dot: "bg-gray-400"   },
};

function VehicleIcon({ type, size = 16 }: { type: FleetVehicle["vehicleType"]; size?: number }) {
  const Icon = type === "Bus" ? Bus : type === "Truck" ? Truck : Car;
  return <Icon size={size} />;
}

function StatusBadge({ status }: { status: FleetVehicle["status"] }) {
  const c = STATUS_CFG[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", c.bg, c.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", c.dot)} />{status}
    </span>
  );
}

function serviceHealth(v: FleetVehicle): "good" | "warning" | "overdue" {
  const diff = v.nextServiceKm - v.currentOdometer;
  if (diff < 0) return "overdue";
  if (diff < 5000) return "warning";
  return "good";
}

function VehicleCard({ v, onClick }: { v: FleetVehicle; onClick: () => void }) {
  const health = serviceHealth(v);
  return (
    <div onClick={onClick} className="bg-card border border-border rounded-2xl p-4 cursor-pointer hover:shadow-md hover:-translate-y-0.5 hover:border-primary/20 transition-all duration-150 flex flex-col gap-3 group">
      <div className="flex items-start gap-3">
        <div className={cn("w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 border",
          v.vehicleType === "Bus" ? "bg-blue-50 dark:bg-blue-950/40 border-blue-100 dark:border-blue-900/40 text-blue-500"
          : v.vehicleType === "Pickup" || v.vehicleType === "Truck" ? "bg-amber-50 dark:bg-amber-950/40 border-amber-100 dark:border-amber-900/40 text-amber-500"
          : "bg-green-50 dark:bg-green-950/40 border-green-100 dark:border-green-900/40 text-green-500"
        )}>
          <VehicleIcon type={v.vehicleType} size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-[13px] text-foreground truncate group-hover:text-primary transition-colors">{v.make} {v.model}</p>
          <p className="text-[11px] text-muted-foreground font-mono">{v.regNo}</p>
        </div>
        <StatusBadge status={v.status} />
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <User size={10} className="shrink-0 opacity-60" />
          <span className="truncate">{v.assignedDriverName ?? "Unassigned"}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <MapPin size={10} className="shrink-0 opacity-60" />
          <span className="truncate">{v.office}, {v.zone}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Gauge size={10} className="shrink-0 opacity-60" />
          <span>{v.currentOdometer.toLocaleString()} km</span>
        </div>
      </div>
      <div className="pt-2.5 border-t border-border/60 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">{v.year} · {v.fuelType}</span>
        <div className={cn("flex items-center gap-1 text-[10px] font-semibold",
          health === "good" ? "text-green-600 dark:text-green-400" : health === "warning" ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"
        )}>
          <Wrench size={10} />
          {health === "good" ? `${(v.nextServiceKm - v.currentOdometer).toLocaleString()} km to service` : health === "warning" ? "Service soon" : "Service overdue"}
        </div>
      </div>
    </div>
  );
}

function FilterBtn({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-all", value ? "bg-primary text-white border-primary shadow-sm" : "border-border text-muted-foreground hover:text-foreground bg-card")}>
        {value || label}<ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && <>
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
        <div className="absolute top-full mt-1.5 left-0 z-50 bg-popover border border-border rounded-xl shadow-lg overflow-hidden min-w-[160px] py-1">
          <button className="w-full text-left px-3 py-2 text-xs hover:bg-accent" onClick={() => { onChange(""); setOpen(false); }}>All {label}s</button>
          {options.map(o => <button key={o} className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", value === o ? "font-semibold text-primary" : "text-muted-foreground")} onClick={() => { onChange(o); setOpen(false); }}>{o}</button>)}
        </div>
      </>}
    </div>
  );
}

export default function Fleet() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Fleet Management");
    setSearchHandler(q => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const stats = getFleetStats();
  const vehicles = useMemo(() => listFleetVehicles({
    vehicleType: filterType as FleetVehicle["vehicleType"] || undefined,
    status: filterStatus as FleetVehicle["status"] || undefined,
    search: search || undefined,
  }), [search, filterType, filterStatus]);

  const hasFilter = !!(search || filterType || filterStatus);
  const serviceAlerts = vehicles.filter(v => serviceHealth(v) !== "good");

  return (
    <div className="flex flex-col h-full">
      {/* KPI */}
      <div className="px-5 py-3 border-b border-border bg-card grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total Vehicles",  value: stats.total,         color: "text-foreground"                                },
          { label: "Active",          value: stats.active,        color: "text-green-600 dark:text-green-400"             },
          { label: "In Maintenance",  value: stats.inMaintenance, color: "text-amber-600 dark:text-amber-400"             },
          { label: "Staff Buses",     value: stats.buses,         color: "text-blue-600 dark:text-blue-400"               },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50">
            <Car size={14} className={s.color} />
            <div>
              <p className={cn("text-[18px] font-extrabold leading-none tabular-nums", s.color)}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Service alerts banner */}
      {serviceAlerts.length > 0 && (
        <div className="px-5 py-2.5 bg-amber-50 dark:bg-amber-950/20 border-b border-amber-200/60 dark:border-amber-800/30 flex items-center gap-2.5">
          <ShieldAlert size={14} className="text-amber-600 shrink-0" />
          <p className="text-[12px] text-amber-700 dark:text-amber-400 font-medium">
            <span className="font-bold">{serviceAlerts.length}</span> {serviceAlerts.length === 1 ? "vehicle requires" : "vehicles require"} servicing attention
          </p>
        </div>
      )}

      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input type="search" placeholder="Search vehicles…" value={search} onChange={e => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 w-44" />
        </div>
        <FilterBtn label="Type"   value={filterType}   options={["SUV", "Pickup", "Bus", "Van", "Truck", "Sedan"]} onChange={setFilterType}   />
        <FilterBtn label="Status" value={filterStatus} options={["Active", "In Maintenance", "Grounded", "Decommissioned"]} onChange={setFilterStatus} />
        {hasFilter && <button onClick={() => { setSearch(""); setFilterType(""); setFilterStatus(""); }} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5"><X size={12} /> Clear</button>}
        <p className="ml-auto text-xs text-muted-foreground"><span className="font-bold text-foreground">{vehicles.length}</span> vehicles</p>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-5" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "12px", alignContent: "start" }}>
        {vehicles.map(v => <VehicleCard key={v.id} v={v} onClick={() => nav(`/fleet/${v.id}`)} />)}
        {vehicles.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center py-20 gap-3">
            <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center"><Car size={20} className="text-muted-foreground/40" /></div>
            <p className="text-sm font-semibold">No vehicles found</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── FLEET VEHICLE DETAIL ────────────────────────────────────────────────────
export function FleetDetail({ params }: { params: { id: string } }) {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  const [tab, setTab] = useState<"details" | "fuel" | "docs">("details");

  const v = getFleetVehicle(params.id);
  const asset = v ? getAsset(v.assetId) : undefined;
  const fuelTxns = v ? listFuelTransactions(v.id) : [];
  const health = v ? serviceHealth(v) : "good";

  useEffect(() => {
    setTitle(v ? `${v.make} ${v.model}` : "Vehicle");
    setSearchHandler(undefined);
  }, [v, setTitle, setSearchHandler]);

  if (!v) return <div className="p-8 text-center text-muted-foreground">Vehicle not found.</div>;

  const TABS = ["details", "fuel", "docs"] as const;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <button onClick={() => nav("/fleet")} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">← Back to Fleet</button>

      {/* Hero */}
      <div className="bg-card border border-border rounded-2xl p-5 flex items-start gap-4 flex-wrap">
        <div className={cn("w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border",
          v.vehicleType === "Bus" ? "bg-blue-50 dark:bg-blue-950/40 border-blue-100 text-blue-500"
          : "bg-green-50 dark:bg-green-950/40 border-green-100 text-green-500"
        )}>
          <VehicleIcon type={v.vehicleType} size={26} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h1 className="text-[20px] font-extrabold text-foreground">{v.make} {v.model} <span className="text-muted-foreground font-normal text-[14px]">{v.year}</span></h1>
              <p className="text-[13px] font-mono text-muted-foreground mt-0.5">{v.regNo} · {v.vin}</p>
            </div>
            <StatusBadge status={v.status} />
          </div>
          <div className="mt-3 flex flex-wrap gap-4">
            <span className="text-[12px] text-muted-foreground flex items-center gap-1.5"><User size={12} />{v.assignedDriverName ?? "Unassigned"}</span>
            <span className="text-[12px] text-muted-foreground flex items-center gap-1.5"><MapPin size={12} />{v.office}</span>
            <span className="text-[12px] text-muted-foreground flex items-center gap-1.5"><Gauge size={12} />{v.currentOdometer.toLocaleString()} km</span>
            <span className="text-[12px] text-muted-foreground flex items-center gap-1.5"><Fuel size={12} />{v.fuelType} · {v.tankCapacity}L tank</span>
          </div>
        </div>
      </div>

      {/* Asset record link */}
      {asset && (
        <button
          onClick={() => nav(`/assets/${asset.id}`)}
          className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-primary/30 bg-primary/5 hover:bg-primary/10 transition-colors group"
        >
          <div className="flex items-center gap-2.5 text-[13px] font-semibold text-primary">
            <ArrowUpRight size={15} />
            View Asset Register Record — {asset.assetTag}
          </div>
          <ExternalLink size={13} className="text-primary/60 group-hover:text-primary transition-colors" />
        </button>
      )}

      {/* Service health */}
      <div className={cn("flex items-center gap-3 px-4 py-3 rounded-xl border text-[12px] font-medium",
        health === "good"    ? "bg-green-50 dark:bg-green-950/20 border-green-200/50 text-green-700 dark:text-green-400" :
        health === "warning" ? "bg-amber-50 dark:bg-amber-950/20 border-amber-200/50 text-amber-700 dark:text-amber-400" :
        "bg-red-50 dark:bg-red-950/20 border-red-200/50 text-red-700 dark:text-red-400"
      )}>
        <Wrench size={14} />
        {health === "good"
          ? `Next service at ${v.nextServiceKm.toLocaleString()} km — ${(v.nextServiceKm - v.currentOdometer).toLocaleString()} km remaining`
          : health === "warning"
          ? `Service due soon — ${(v.nextServiceKm - v.currentOdometer).toLocaleString()} km remaining`
          : `Service overdue — last service ${v.lastServiceDate}`
        }
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 border-b border-border">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} className={cn("px-4 py-2.5 text-[13px] font-medium capitalize border-b-2 -mb-px transition-colors", tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}>{t}</button>
        ))}
      </div>

      {tab === "details" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            ["Asset Tag",        v.assetTag],
            ["VIN",              v.vin],
            ["Engine No",        v.engineNo],
            ["Color",            v.color],
            ["Fuel Type",        v.fuelType],
            ["Tank Capacity",    `${v.tankCapacity}L`],
            ["Seating",          v.seatingCapacity ? `${v.seatingCapacity} seats` : "—"],
            ["Department",       v.department],
            ["Insurance Expiry", v.insuranceExpiry],
            ["Roadworthiness",   v.roadWorthinessExpiry],
            ["Fuel Card",        v.fuelCardId ?? "None"],
            ["Last Service",     v.lastServiceDate],
          ].map(([k, val]) => (
            <div key={k} className="bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{k}</span>
              <span className="text-[13px] font-medium text-foreground font-mono">{val}</span>
            </div>
          ))}
        </div>
      )}

      {tab === "fuel" && (
        <div className="space-y-3">
          {fuelTxns.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground"><Fuel size={24} className="mx-auto mb-2 opacity-30" /><p className="text-sm">No fuel transactions found</p></div>
          ) : (
            <div className="bg-card border border-border rounded-2xl overflow-hidden">
              <table className="w-full">
                <thead className="border-b border-border">
                  <tr>
                    {["Date", "Station", "Litres", "Cost", "Odometer", "Status"].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fuelTxns.map(t => (
                    <tr key={t.id} className="border-b border-border/50">
                      <td className="px-4 py-3 text-[12px]">{t.date}</td>
                      <td className="px-4 py-3 text-[12px]">{t.station}</td>
                      <td className="px-4 py-3 text-[12px] font-mono">{t.litres}L</td>
                      <td className="px-4 py-3 text-[12px] font-mono">₦{t.totalCost.toLocaleString()}</td>
                      <td className="px-4 py-3 text-[12px] font-mono">{t.odometerReading.toLocaleString()}</td>
                      <td className="px-4 py-3">
                        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg",
                          t.status === "Approved" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" :
                          t.status === "Flagged" ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" :
                          "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                        )}>{t.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "docs" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            { doc: "Certificate of Road Worthiness", expiry: v.roadWorthinessExpiry },
            { doc: "Third-Party Insurance",           expiry: v.insuranceExpiry      },
            { doc: "Vehicle License",                 expiry: v.insuranceExpiry      },
          ].map(d => {
            const expired = new Date(d.expiry) < new Date();
            return (
              <div key={d.doc} className={cn("bg-card border rounded-xl px-4 py-3 flex items-center justify-between", expired ? "border-red-200/70 dark:border-red-800/30" : "border-border")}>
                <div>
                  <p className="text-[12px] font-semibold text-foreground">{d.doc}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Expires {d.expiry}</p>
                </div>
                <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", expired ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400")}>
                  {expired ? "Expired" : "Valid"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
