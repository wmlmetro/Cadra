import { useState, useEffect, useMemo } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { listIdentityRecords } from "@/lib/dataProvider";
import type { IdentityRecord } from "@/types";
import {
  Search, X, ChevronDown, ShieldCheck, ShieldOff, ShieldAlert,
  Fingerprint, CreditCard, CheckCircle2, AlertTriangle, XCircle, Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import MockDataBanner from "@/components/MockDataBanner";

const CLEARANCE_CFG: Record<IdentityRecord["clearanceLevel"], { bg: string; text: string; icon: typeof ShieldCheck }> = {
  "Full":    { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70", text: "text-green-700 dark:text-green-400",  icon: ShieldCheck },
  "Partial": { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70", text: "text-amber-700 dark:text-amber-400",  icon: ShieldAlert },
  "Pending": { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70",   text: "text-blue-700 dark:text-blue-400",    icon: Clock       },
  "Blocked": { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70",      text: "text-red-700 dark:text-red-400",      icon: ShieldOff   },
};
const VERIFY_CFG: Record<string, { icon: typeof CheckCircle2; className: string }> = {
  "Verified": { icon: CheckCircle2, className: "text-green-500" },
  "Pending":  { icon: Clock,        className: "text-blue-500"  },
  "Mismatch": { icon: AlertTriangle,className: "text-amber-500" },
  "Missing":  { icon: XCircle,      className: "text-red-400"   },
};
const BIOMETRIC_CFG: Record<string, { label: string; className: string }> = {
  "Enrolled":     { label: "Enrolled",     className: "text-green-600 dark:text-green-400" },
  "Partial":      { label: "Partial",      className: "text-amber-600 dark:text-amber-400" },
  "Not Enrolled": { label: "Not Enrolled", className: "text-red-500"                       },
};

function ClearanceBadge({ level }: { level: IdentityRecord["clearanceLevel"] }) {
  const c = CLEARANCE_CFG[level];
  const Icon = c.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", c.bg, c.text)}>
      <Icon size={11} />{level}
    </span>
  );
}

function VerifyDot({ status }: { status: string }) {
  const c = VERIFY_CFG[status] ?? VERIFY_CFG["Missing"];
  const Icon = c.icon;
  return <Icon size={13} className={c.className} />;
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
          <button className="w-full text-left px-3 py-2 text-xs hover:bg-accent" onClick={() => { onChange(""); setOpen(false); }}>All</button>
          {options.map(o => <button key={o} className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", value === o ? "font-semibold text-primary" : "text-muted-foreground")} onClick={() => { onChange(o); setOpen(false); }}>{o}</button>)}
        </div>
      </>}
    </div>
  );
}

export default function Identity() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [search, setSearch] = useState("");
  const [filterLevel, setFilterLevel] = useState("");
  const [filterZone, setFilterZone] = useState("");

  useEffect(() => {
    setTitle("Identity & Clearance");
    setSearchHandler(q => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const all = listIdentityRecords();
  const records = useMemo(() => listIdentityRecords({
    clearanceLevel: filterLevel || undefined,
    zone: filterZone || undefined,
    search: search || undefined,
  }), [search, filterLevel, filterZone]);

  const stats = useMemo(() => ({
    full:     all.filter(r => r.clearanceLevel === "Full").length,
    partial:  all.filter(r => r.clearanceLevel === "Partial").length,
    pending:  all.filter(r => r.clearanceLevel === "Pending").length,
    blocked:  all.filter(r => r.clearanceLevel === "Blocked").length,
    ninMissing:    all.filter(r => r.ninStatus    === "Missing" || r.ninStatus    === "Mismatch").length,
    bvnMissing:    all.filter(r => r.bvnStatus    === "Missing" || r.bvnStatus    === "Mismatch").length,
    bioNotEnrolled:all.filter(r => r.biometricStatus === "Not Enrolled").length,
    cardNotIssued: all.filter(r => r.accessCardStatus === "Not Issued" || r.accessCardStatus === "Lost").length,
  }), [all]);

  const zones = [...new Set(all.map(r => r.zone))];
  const clear = () => { setSearch(""); setFilterLevel(""); setFilterZone(""); };
  const hasFilter = !!(search || filterLevel || filterZone);

  return (
    <div className="flex flex-col h-full">
      <MockDataBanner reason="NIN/BVN/biometric fields are excluded from the API for privacy (PRD §10.8)." />
      {/* Summary cards */}
      <div className="px-5 py-4 border-b border-border bg-card">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          {[
            { label: "Full Clearance",    value: stats.full,    color: "text-green-600 dark:text-green-400", bg: "bg-green-500" },
            { label: "Partial Clearance", value: stats.partial, color: "text-amber-600 dark:text-amber-400", bg: "bg-amber-500" },
            { label: "Pending",           value: stats.pending, color: "text-blue-600 dark:text-blue-400",   bg: "bg-blue-500"  },
            { label: "Blocked",           value: stats.blocked, color: "text-red-600 dark:text-red-400",     bg: "bg-red-500"   },
          ].map(s => (
            <div key={s.label} className="bg-background border border-border/50 rounded-xl px-4 py-3 flex items-center gap-3">
              <div className={cn("w-2 h-8 rounded-full shrink-0", s.bg)} />
              <div>
                <p className={cn("text-[20px] font-extrabold leading-none tabular-nums", s.color)}>{s.value}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
              </div>
            </div>
          ))}
        </div>
        {/* Action items */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {[
            { icon: ShieldOff,   label: "NIN issues",     value: stats.ninMissing,    color: "text-red-500" },
            { icon: ShieldAlert, label: "BVN issues",     value: stats.bvnMissing,    color: "text-amber-500" },
            { icon: Fingerprint, label: "Bio not enrolled",value: stats.bioNotEnrolled,color: "text-orange-500" },
            { icon: CreditCard,  label: "No access card", value: stats.cardNotIssued, color: "text-purple-500" },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-muted/40 border border-border/50">
              <s.icon size={13} className={s.color} />
              <span className="text-[11px] text-muted-foreground">{s.label}</span>
              <span className={cn("ml-auto text-[13px] font-bold tabular-nums", s.color)}>{s.value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input type="search" placeholder="Search employees…" value={search} onChange={e => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 w-44" />
        </div>
        <FilterBtn label="Clearance" value={filterLevel} options={["Full", "Partial", "Pending", "Blocked"]} onChange={setFilterLevel} />
        <FilterBtn label="Zone" value={filterZone} options={zones} onChange={setFilterZone} />
        {hasFilter && <button onClick={clear} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5"><X size={12} /> Clear</button>}
        <p className="ml-auto text-xs text-muted-foreground"><span className="font-bold text-foreground">{records.length}</span> records</p>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full min-w-[800px]">
          <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
            <tr>
              {["Employee", "Department / Zone", "NIN", "BVN", "Biometrics", "Access Card", "Clearance"].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr key={r.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3">
                  <p className="text-[12px] font-semibold text-foreground">{r.employeeName}</p>
                  <p className="text-[10px] text-muted-foreground font-mono">{r.irNumber}</p>
                </td>
                <td className="px-4 py-3">
                  <p className="text-[12px] text-muted-foreground">{r.department}</p>
                  <p className="text-[10px] text-muted-foreground/60">{r.zone}</p>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <VerifyDot status={r.ninStatus} />
                    <span className="text-[12px] text-muted-foreground">{r.ninStatus}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <VerifyDot status={r.bvnStatus} />
                    <span className="text-[12px] text-muted-foreground">{r.bvnStatus}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={cn("text-[12px] font-medium", BIOMETRIC_CFG[r.biometricStatus]?.className)}>
                    {r.biometricStatus}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={cn("text-[12px]",
                    r.accessCardStatus === "Active" ? "text-green-600 dark:text-green-400 font-medium" :
                    r.accessCardStatus === "Lost"   ? "text-red-500 font-medium" : "text-muted-foreground"
                  )}>
                    {r.accessCard ?? r.accessCardStatus}
                  </span>
                </td>
                <td className="px-4 py-3"><ClearanceBadge level={r.clearanceLevel} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {records.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Fingerprint size={24} className="text-muted-foreground/30" />
            <p className="text-sm font-semibold text-foreground">No records found</p>
          </div>
        )}
      </div>
    </div>
  );
}
