import { useState, useEffect, useMemo } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  listBusRoutes, listBusSchedules, listBookings,
  listFuelCards, listFuelTransactions, getFuelStats, getBusStats,
} from "@/lib/dataProvider";
import type { BusSchedule, BusBooking, FuelTransaction } from "@/types";
import {
  Bus, MapPin, Clock, Users, Fuel, ChevronDown, X,
  CheckCircle2, AlertTriangle, XCircle, Camera, CreditCard,
  Navigation, Zap, TrendingUp, Calendar, Search, ArrowRight,
  RefreshCw, ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── STATUS CONFIG ────────────────────────────────────────────────────────────
const SCHED_CFG: Record<BusSchedule["status"], { bg: string; text: string; dot: string }> = {
  "Scheduled":  { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70",    text: "text-blue-700 dark:text-blue-400",   dot: "bg-blue-500"  },
  "Boarding":   { bg: "bg-purple-50 dark:bg-purple-950/30 border-purple-200/70",text:"text-purple-700 dark:text-purple-400",dot: "bg-purple-500"},
  "Departed":   { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70",  text: "text-amber-700 dark:text-amber-400", dot: "bg-amber-500" },
  "In Transit": { bg: "bg-orange-50 dark:bg-orange-950/30 border-orange-200/70",text:"text-orange-700 dark:text-orange-400",dot:"bg-orange-500"},
  "Arrived":    { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70",  text: "text-green-700 dark:text-green-400", dot: "bg-green-500" },
  "Cancelled":  { bg: "bg-muted/60 border-border",                             text: "text-muted-foreground",              dot: "bg-gray-400"  },
};
const BOOKING_CFG: Record<BusBooking["status"], { bg: string; text: string }> = {
  "Confirmed":  { bg: "bg-blue-100 dark:bg-blue-900/30",   text: "text-blue-700 dark:text-blue-400"   },
  "Checked In": { bg: "bg-purple-100 dark:bg-purple-900/30",text:"text-purple-700 dark:text-purple-400"},
  "Boarded":    { bg: "bg-green-100 dark:bg-green-900/30", text: "text-green-700 dark:text-green-400" },
  "No Show":    { bg: "bg-red-100 dark:bg-red-900/30",     text: "text-red-700 dark:text-red-400"     },
  "Cancelled":  { bg: "bg-muted/60",                       text: "text-muted-foreground"              },
};
const FUEL_STATUS_CFG: Record<FuelTransaction["status"], { bg: string; text: string }> = {
  "Approved":             { bg: "bg-green-100 dark:bg-green-900/30", text: "text-green-700 dark:text-green-400" },
  "Pending Verification": { bg: "bg-amber-100 dark:bg-amber-900/30", text: "text-amber-700 dark:text-amber-400" },
  "Flagged":              { bg: "bg-red-100 dark:bg-red-900/30",     text: "text-red-700 dark:text-red-400"     },
  "Rejected":             { bg: "bg-muted/60",                       text: "text-muted-foreground"              },
};

function SchedBadge({ status }: { status: BusSchedule["status"] }) {
  const c = SCHED_CFG[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", c.bg, c.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", c.dot)} />{status}
    </span>
  );
}

// ─── SEAT MAP ─────────────────────────────────────────────────────────────────
function SeatMap({ schedule, bookings }: { schedule: BusSchedule; bookings: BusBooking[] }) {
  const bookedSeats = new Set(bookings.filter(b => b.status !== "Cancelled").map(b => b.seatNo));
  const seats = Array.from({ length: schedule.totalSeats }, (_, i) => i + 1);
  return (
    <div className="bg-card border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[12px] font-bold text-foreground">Seat Map — {schedule.vehicleName}</p>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-primary/20 border border-primary/30 inline-block" /> Booked</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-muted border border-border inline-block" /> Available</span>
        </div>
      </div>
      {/* Driver row */}
      <div className="flex justify-center mb-2">
        <div className="w-8 h-7 rounded-lg bg-muted/60 border border-border flex items-center justify-center text-[9px] font-bold text-muted-foreground">DRV</div>
      </div>
      {/* Seats grid — 2+2 pattern */}
      <div className="grid gap-1.5" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        {seats.map((seat, i) => {
          const booked = bookedSeats.has(seat);
          const booking = bookings.find(b => b.seatNo === seat && b.status !== "Cancelled");
          const isAisle = (i % 4) === 1;
          return (
            <div key={seat} className={cn("relative group", isAisle && "mr-2")}>
              <div className={cn(
                "h-8 rounded-lg flex items-center justify-center text-[10px] font-bold border cursor-pointer transition-all",
                booked ? "bg-primary/15 border-primary/30 text-primary" : "bg-muted/40 border-border text-muted-foreground hover:bg-muted hover:border-border/80"
              )}>
                {seat}
              </div>
              {booked && booking && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block z-20 bg-popover border border-border rounded-xl px-3 py-2 shadow-lg min-w-[160px]">
                  <p className="text-[11px] font-semibold text-foreground truncate">{booking.passengerName}</p>
                  <p className="text-[10px] text-muted-foreground">{booking.department}</p>
                  <span className={cn("mt-1 inline-block text-[9px] font-bold px-1.5 py-0.5 rounded", BOOKING_CFG[booking.status].bg, BOOKING_CFG[booking.status].text)}>{booking.status}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
        <span><span className="font-bold text-foreground">{schedule.bookedSeats}</span> booked</span>
        <span><span className="font-bold text-foreground">{schedule.totalSeats - schedule.bookedSeats}</span> available</span>
        <span><span className="font-bold text-primary">{schedule.checkedIn}</span> checked in</span>
      </div>
    </div>
  );
}

// ─── TRIP CARD ────────────────────────────────────────────────────────────────
function TripCard({ s, onClick, active }: { s: BusSchedule; onClick: () => void; active: boolean }) {
  const occupancy = Math.round((s.bookedSeats / s.totalSeats) * 100);
  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-card border rounded-2xl p-4 cursor-pointer transition-all duration-150 hover:shadow-md",
        active ? "border-primary/40 ring-1 ring-primary/20" : "border-border hover:border-primary/20"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <p className="text-[13px] font-bold text-foreground">{s.routeCode}</p>
          <p className="text-[11px] text-muted-foreground">{s.routeName}</p>
        </div>
        <SchedBadge status={s.status} />
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground mb-2">
        <Clock size={10} className="shrink-0" />
        <span>{s.departureTime} → {s.estimatedArrival}</span>
        <span className="text-muted-foreground/50">·</span>
        <Calendar size={10} className="shrink-0" />
        <span>{s.departureDate}</span>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground mb-3">
        <Bus size={10} className="shrink-0" />
        <span className="truncate">{s.vehicleName} · {s.driverName}</span>
      </div>
      {/* Occupancy bar */}
      <div>
        <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
          <span>Occupancy</span>
          <span className="font-bold text-foreground">{s.bookedSeats}/{s.totalSeats} ({occupancy}%)</span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${occupancy}%` }} />
        </div>
      </div>
    </div>
  );
}

// ─── FUEL MANAGEMENT ─────────────────────────────────────────────────────────
function FuelManagement() {
  const cards = listFuelCards();
  const txns = listFuelTransactions();
  const fuelStats = getFuelStats();
  const flagged = txns.filter(t => t.status === "Flagged");
  const pending = txns.filter(t => t.status === "Pending Verification");

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Monthly Spend",   value: `₦${(fuelStats.totalSpend / 1000).toFixed(0)}k`,  color: "text-foreground",                               icon: CreditCard  },
          { label: "Total Litres",    value: `${fuelStats.totalLitres}L`,                       color: "text-blue-600 dark:text-blue-400",               icon: Fuel        },
          { label: "Flagged Txns",    value: fuelStats.flaggedCount,                            color: "text-red-600 dark:text-red-400",                 icon: AlertTriangle },
          { label: "Pending Review",  value: fuelStats.pendingCount,                            color: "text-amber-600 dark:text-amber-400",             icon: RefreshCw   },
        ].map(s => (
          <div key={s.label} className="bg-card border border-border rounded-2xl px-4 py-3 flex items-center gap-3">
            <s.icon size={16} className={s.color} />
            <div>
              <p className={cn("text-[20px] font-extrabold leading-none", s.color)}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* WhatsApp fuel reporting callout */}
      <div className="bg-gradient-to-r from-green-600 to-green-500 rounded-2xl p-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-[13px] font-bold text-white">WhatsApp Fuel Reporting</p>
          <p className="text-[11px] text-green-100 mt-0.5">Drivers submit meter photos & odometer readings via WhatsApp bot. Auto-verified against trip data.</p>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 bg-white/20 hover:bg-white/30 transition-colors px-3 py-1.5 rounded-xl cursor-pointer">
          <span className="text-[11px] font-semibold text-white">Configure</span>
          <ArrowRight size={11} className="text-white" />
        </div>
      </div>

      {/* Flagged transactions */}
      {flagged.length > 0 && (
        <div className="bg-card border border-red-200/60 dark:border-red-800/30 rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-red-200/60 dark:border-red-800/30 flex items-center gap-2.5 bg-red-50/50 dark:bg-red-950/20">
            <ShieldAlert size={14} className="text-red-500 shrink-0" />
            <p className="text-[12px] font-bold text-red-700 dark:text-red-400">{flagged.length} Flagged Transaction{flagged.length > 1 ? "s" : ""} — Requires Review</p>
          </div>
          {flagged.map(t => (
            <div key={t.id} className="px-5 py-3 border-b border-border/50 last:border-0 flex items-start justify-between gap-4 flex-wrap">
              <div>
                <p className="text-[12px] font-semibold text-foreground">{t.vehicleName} · {t.regNo}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{t.driverName} · {t.date} {t.time} · {t.station}, {t.locationName}</p>
                <p className="text-[11px] text-red-600 dark:text-red-400 mt-1 flex items-center gap-1"><AlertTriangle size={10} />{t.flagReason}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-[13px] font-bold text-foreground">₦{t.totalCost.toLocaleString()}</p>
                <p className="text-[11px] text-muted-foreground">{t.litres}L @ ₦{t.pricePerLitre}/L</p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  {t.hasMeterPhoto ? <span className="text-[10px] text-green-600 dark:text-green-400 font-semibold flex items-center gap-1"><Camera size={9} /> Photo</span> : <span className="text-[10px] text-red-500 font-semibold flex items-center gap-1"><XCircle size={9} /> No photo</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pending transactions */}
      {pending.length > 0 && (
        <div className="bg-card border border-amber-200/60 dark:border-amber-800/30 rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-amber-200/60 dark:border-amber-800/30 bg-amber-50/50 dark:bg-amber-950/20">
            <p className="text-[12px] font-bold text-amber-700 dark:text-amber-400">{pending.length} Pending Verification</p>
          </div>
          {pending.map(t => (
            <div key={t.id} className="px-5 py-3 border-b border-border/50 last:border-0 flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p className="text-[12px] font-semibold text-foreground">{t.vehicleName} · {t.driverName}</p>
                <p className="text-[11px] text-muted-foreground">{t.date} · {t.station}</p>
              </div>
              <div className="flex items-center gap-3">
                <p className="text-[13px] font-bold">₦{t.totalCost.toLocaleString()}</p>
                {t.hasMeterPhoto ? <span className="text-[10px] text-green-600 dark:text-green-400 font-semibold flex items-center gap-1"><Camera size={9} /> Photo uploaded</span> : <span className="text-[10px] text-amber-600 dark:text-amber-400 font-semibold flex items-center gap-1"><Camera size={9} /> Awaiting photo</span>}
                <button className="text-[11px] font-semibold text-primary hover:opacity-80 px-2 py-1 rounded-lg border border-primary/30 hover:bg-primary/5 transition-colors">Approve</button>
                <button className="text-[11px] font-semibold text-red-500 hover:opacity-80 px-2 py-1 rounded-lg border border-red-200 dark:border-red-800/40 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors">Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* All transactions table */}
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between">
          <p className="text-[13px] font-bold text-foreground">All Fuel Transactions</p>
          <p className="text-[11px] text-muted-foreground">{txns.length} records</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead className="border-b border-border">
              <tr>{["Date/Time", "Vehicle", "Driver", "Station", "Litres", "Total", "Meter", "Status"].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {txns.map(t => (
                <tr key={t.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3"><p className="text-[12px]">{t.date}</p><p className="text-[10px] text-muted-foreground">{t.time}</p></td>
                  <td className="px-4 py-3"><p className="text-[12px] font-semibold">{t.regNo}</p><p className="text-[10px] text-muted-foreground truncate max-w-[120px]">{t.vehicleName}</p></td>
                  <td className="px-4 py-3 text-[12px] text-muted-foreground">{t.driverName}</td>
                  <td className="px-4 py-3"><p className="text-[12px]">{t.station}</p><p className="text-[10px] text-muted-foreground">{t.locationName}</p></td>
                  <td className="px-4 py-3 text-[12px] font-mono">{t.litres}L</td>
                  <td className="px-4 py-3 text-[12px] font-mono font-semibold">₦{t.totalCost.toLocaleString()}</td>
                  <td className="px-4 py-3">{t.hasMeterPhoto ? <CheckCircle2 size={14} className="text-green-500" /> : <XCircle size={14} className="text-red-400" />}</td>
                  <td className="px-4 py-3">
                    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", FUEL_STATUS_CFG[t.status].bg, FUEL_STATUS_CFG[t.status].text)}>{t.status}</span>
                    {t.flagReason && <p className="text-[9px] text-red-500 mt-0.5 max-w-[160px] leading-snug">{t.flagReason.split("—")[0]}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
type Tab = "schedule" | "bookings" | "routes" | "fuel";

export default function StaffBus() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [tab, setTab] = useState<Tab>("schedule");
  const [selectedSched, setSelectedSched] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState<"today" | "upcoming" | "all">("today");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setTitle("Staff Bus");
    setSearchHandler(q => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const busStats = getBusStats();
  const routes = listBusRoutes();

  const schedules = useMemo(() => {
    let r = listBusSchedules();
    if (dateFilter === "today")    r = r.filter(s => s.departureDate === "2026-06-10");
    if (dateFilter === "upcoming") r = r.filter(s => s.departureDate > "2026-06-10");
    if (search) { const q = search.toLowerCase(); r = r.filter(s => s.routeName.toLowerCase().includes(q) || s.driverName.toLowerCase().includes(q) || s.vehicleName.toLowerCase().includes(q)); }
    return r;
  }, [dateFilter, search]);

  const selected = selectedSched ? listBusSchedules().find(s => s.id === selectedSched) : null;
  const selectedBookings = selected ? listBookings(selected.id) : [];

  const TABS: { id: Tab; label: string; icon: typeof Bus }[] = [
    { id: "schedule", label: "Schedule",  icon: Calendar  },
    { id: "bookings", label: "Bookings",  icon: Users     },
    { id: "routes",   label: "Routes",    icon: Navigation},
    { id: "fuel",     label: "Fuel Mgmt", icon: Fuel      },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* KPI strip */}
      <div className="px-5 py-3 border-b border-border bg-card grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Today's Trips",    value: busStats.todayTrips,      color: "text-foreground",                       icon: Bus        },
          { label: "Active / En Route",value: busStats.activeTrips,     color: "text-orange-600 dark:text-orange-400",  icon: Zap        },
          { label: "Arrived Today",    value: busStats.arrivedTrips,    color: "text-green-600 dark:text-green-400",    icon: CheckCircle2},
          { label: "Passengers Today", value: busStats.passengersToday, color: "text-blue-600 dark:text-blue-400",      icon: Users      },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50">
            <s.icon size={14} className={s.color} />
            <div>
              <p className={cn("text-[18px] font-extrabold leading-none tabular-nums", s.color)}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="px-5 border-b border-border bg-card flex items-center gap-0.5">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} className={cn("flex items-center gap-2 px-4 py-3 text-[13px] font-medium border-b-2 -mb-px transition-colors", tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}>
            <t.icon size={13} />{t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5">

        {/* ── SCHEDULE TAB ─────────────────────────────────────────────────── */}
        {tab === "schedule" && (
          <div className={cn("flex gap-5", selected ? "flex-col xl:flex-row" : "flex-col")}>
            <div className={cn("flex flex-col gap-4", selected ? "xl:w-[340px] shrink-0" : "w-full")}>
              {/* Date filter + search */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex rounded-xl border border-border bg-muted/40 p-0.5 gap-0.5">
                  {(["today", "upcoming", "all"] as const).map(d => (
                    <button key={d} onClick={() => setDateFilter(d)} className={cn("px-3 py-1.5 text-[11px] font-medium rounded-lg capitalize transition-all", dateFilter === d ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>{d}</button>
                  ))}
                </div>
                <div className="relative">
                  <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
                  <input type="search" placeholder="Search trips…" value={search} onChange={e => setSearch(e.target.value)} className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20 w-36" />
                </div>
                {selected && <button onClick={() => setSelectedSched(null)} className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><X size={12} /> Close</button>}
              </div>

              <div className={cn("space-y-3", selected ? "" : "grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 space-y-0")}>
                {schedules.map(s => (
                  <TripCard key={s.id} s={s} onClick={() => setSelectedSched(s.id === selectedSched ? null : s.id)} active={s.id === selectedSched} />
                ))}
                {schedules.length === 0 && (
                  <div className="col-span-full text-center py-16 text-muted-foreground">
                    <Bus size={28} className="mx-auto mb-3 opacity-30" />
                    <p className="text-sm font-semibold">No trips found</p>
                  </div>
                )}
              </div>
            </div>

            {/* Detail panel */}
            {selected && (
              <div className="flex-1 space-y-4">
                <div className="bg-card border border-border rounded-2xl p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="text-[15px] font-extrabold text-foreground">{selected.routeName}</p>
                      <p className="text-[12px] text-muted-foreground">{selected.vehicleName} · {selected.driverName}</p>
                    </div>
                    <SchedBadge status={selected.status} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    {[
                      ["Departure", `${selected.departureDate} · ${selected.departureTime}`],
                      ["Est. Arrival", selected.estimatedArrival],
                      ["Booked", `${selected.bookedSeats} / ${selected.totalSeats}`],
                      ["Checked In", String(selected.checkedIn)],
                    ].map(([k, v]) => (
                      <div key={k} className="bg-background border border-border/50 rounded-xl px-3 py-2">
                        <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">{k}</p>
                        <p className="text-[13px] font-semibold text-foreground mt-0.5">{v}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <SeatMap schedule={selected} bookings={selectedBookings} />
                {/* Manifest */}
                <div className="bg-card border border-border rounded-2xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                    <p className="text-[12px] font-bold text-foreground">Passenger Manifest</p>
                    <span className="text-[11px] text-muted-foreground">{selectedBookings.filter(b => b.status !== "Cancelled").length} passengers</span>
                  </div>
                  <div className="max-h-[300px] overflow-y-auto">
                    {selectedBookings.filter(b => b.status !== "Cancelled").map(b => (
                      <div key={b.id} className="px-4 py-2.5 border-b border-border/50 last:border-0 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground">{b.seatNo}</div>
                          <div>
                            <p className="text-[12px] font-semibold text-foreground">{b.passengerName}</p>
                            <p className="text-[10px] text-muted-foreground">{b.passengerIR} · {b.department}</p>
                          </div>
                        </div>
                        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", BOOKING_CFG[b.status].bg, BOOKING_CFG[b.status].text)}>{b.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── BOOKINGS TAB ────────────────────────────────────────────────── */}
        {tab === "bookings" && (
          <div className="bg-card border border-border rounded-2xl overflow-hidden">
            <div className="px-5 py-3 border-b border-border flex items-center justify-between">
              <p className="text-[13px] font-bold text-foreground">All Bookings</p>
              <span className="text-[11px] text-muted-foreground">{listBookings().length} total</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead className="border-b border-border bg-muted/30">
                  <tr>{["Passenger", "Route / Date", "Seat", "Purpose", "Status"].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {listBookings().slice(0, 40).map(b => {
                    const sched = listBusSchedules().find(s => s.id === b.scheduleId);
                    return (
                      <tr key={b.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-3"><p className="text-[12px] font-semibold">{b.passengerName}</p><p className="text-[10px] text-muted-foreground">{b.passengerIR} · {b.department}</p></td>
                        <td className="px-4 py-3"><p className="text-[12px]">{sched?.routeName ?? "—"}</p><p className="text-[10px] text-muted-foreground">{sched?.departureDate} {sched?.departureTime}</p></td>
                        <td className="px-4 py-3 text-[12px] font-mono font-bold">{b.seatNo}</td>
                        <td className="px-4 py-3 text-[12px] text-muted-foreground">{b.purpose}</td>
                        <td className="px-4 py-3"><span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", BOOKING_CFG[b.status].bg, BOOKING_CFG[b.status].text)}>{b.status}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── ROUTES TAB ──────────────────────────────────────────────────── */}
        {tab === "routes" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {routes.map(r => (
              <div key={r.id} className={cn("bg-card border rounded-2xl p-4 flex flex-col gap-3", r.active ? "border-border" : "border-border/40 opacity-60")}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-[13px] font-bold text-foreground">{r.code}</p>
                    <p className="text-[11px] text-muted-foreground">{r.name}</p>
                  </div>
                  <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", r.active ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400" : "bg-muted text-muted-foreground")}>
                    {r.active ? "Active" : "Inactive"}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[12px]">
                  <MapPin size={11} className="text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground truncate">{r.origin}</span>
                  <ArrowRight size={10} className="text-muted-foreground/50 shrink-0" />
                  <span className="text-muted-foreground truncate">{r.destination}</span>
                </div>
                {r.stops.length > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span className="text-[10px] font-semibold">Stops:</span>
                    {r.stops.map((s, i) => <span key={i}>{s}{i < r.stops.length - 1 ? " ·" : ""}</span>)}
                  </div>
                )}
                <div className="flex items-center gap-4 pt-2 border-t border-border/60 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1"><TrendingUp size={10} />{r.distanceKm} km</span>
                  <span className="flex items-center gap-1"><Clock size={10} />{r.estimatedDuration}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── FUEL TAB ────────────────────────────────────────────────────── */}
        {tab === "fuel" && <FuelManagement />}
      </div>
    </div>
  );
}
