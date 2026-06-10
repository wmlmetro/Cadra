import { useState, useEffect, useMemo, useRef } from "react";
import { useLocation } from "wouter";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchEmployee, fetchEmployeeAssetsApi, fetchEmployeesPage, type EmployeesPage } from "@/lib/dataProvider";
import type { Asset } from "@/types";
import { useQuery } from "@tanstack/react-query";
import { apiConfigured, CadraApiError } from "@/lib/api";
import type { Employee } from "@/types";
import {
  Search, X, ChevronDown, Users, UserCheck, UserX, Clock,
  MapPin, Briefcase, Phone, Mail, ShieldCheck, ShieldOff,
  LayoutGrid, List, AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const DEPARTMENTS = ["Tax Operations", "Executive Management", "Human Resources", "Field Operations", "Tax Audit", "Transport", "ICT", "Finance", "Legal", "Compliance", "Administration"];
const ZONES = ["NRS Headquarters", "North Central", "North East", "North West", "South East", "South South", "South West"];
const STATUSES: Employee["status"][] = ["Active", "On Leave", "Inactive", "Suspended"];
const GRADE_RANGES = ["GL 1–6", "GL 7–10", "GL 11–14", "GL 15–17"];

const STATUS_CFG: Record<Employee["status"], { bg: string; text: string; dot: string }> = {
  "Active":    { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30", text: "text-green-700 dark:text-green-400", dot: "bg-green-500" },
  "On Leave":  { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 dark:border-blue-800/30",   text: "text-blue-700 dark:text-blue-400",   dot: "bg-blue-500"  },
  "Inactive":  { bg: "bg-muted/60 border-border",                                                    text: "text-muted-foreground",              dot: "bg-gray-400"  },
  "Suspended": { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30",        text: "text-red-700 dark:text-red-400",     dot: "bg-red-500"   },
};

function StatusBadge({ status }: { status: Employee["status"] }) {
  const c = STATUS_CFG[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", c.bg, c.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", c.dot)} />
      {status}
    </span>
  );
}

function Avatar({ emp }: { emp: Employee }) {
  const initials = emp.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div
      className="w-10 h-10 rounded-2xl flex items-center justify-center text-[13px] font-bold text-white shrink-0 shadow-sm"
      style={{ background: emp.avatarColor }}
    >
      {initials}
    </div>
  );
}

function EmpCard({ emp, onClick }: { emp: Employee; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className="bg-card border border-border rounded-2xl p-4 cursor-pointer hover:shadow-md hover:-translate-y-0.5 hover:border-primary/20 transition-all duration-150 flex flex-col gap-3 group"
    >
      <div className="flex items-start gap-3">
        <Avatar emp={emp} />
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-[13px] text-foreground truncate group-hover:text-primary transition-colors">{emp.name}</p>
          <p className="text-[11px] text-muted-foreground font-mono">{emp.irNumber}</p>
        </div>
        <StatusBadge status={emp.status} />
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Briefcase size={10} className="shrink-0 text-muted-foreground/50" />
          <span className="truncate">{emp.title}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Users size={10} className="shrink-0 text-muted-foreground/50" />
          <span className="truncate">{emp.department}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <MapPin size={10} className="shrink-0 text-muted-foreground/50" />
          <span className="truncate">{emp.office}</span>
        </div>
      </div>
      <div className="pt-2.5 border-t border-border/60 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">GL-{emp.gradeLevel} · {emp.employmentType}</span>
        <div className="flex items-center gap-1.5">
          {emp.identityVerified
            ? <ShieldCheck size={12} className="text-green-500" />
            : <ShieldOff size={12} className="text-amber-500" />
          }
        </div>
      </div>
    </div>
  );
}

function FilterBtn({ label, value, options, onChange }: { label: string; value: string; options: readonly string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-all",
          value ? "bg-primary text-white border-primary shadow-sm" : "border-border text-muted-foreground hover:text-foreground bg-card")}
      >
        {value || label}
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && <>
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
        <div className="absolute top-full mt-1.5 left-0 z-50 bg-popover border border-border rounded-xl shadow-lg overflow-hidden min-w-[180px] py-1">
          <button className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", !value && "font-semibold")} onClick={() => { onChange(""); setOpen(false); }}>All {label}s</button>
          {options.map(o => (
            <button key={o} className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", value === o ? "font-semibold text-primary" : "text-muted-foreground")} onClick={() => { onChange(o); setOpen(false); }}>{o}</button>
          ))}
        </div>
      </>}
    </div>
  );
}

export default function Employees() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  const [view, setView] = useState<"grid" | "list">("grid");
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const [zone, setZone] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setTitle("Employees");
    setSearchHandler((q) => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // Server-side filters (q + sap_status) go in the queryKey so a new search
  // resets pagination. Dept/zone stay client-side because the API filters by
  // FK ids the frontend doesn't yet know — they only narrow the loaded rows.
  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<EmployeesPage, CadraApiError>({
    queryKey: ["employees", { status, search }],
    queryFn: ({ pageParam }) => fetchEmployeesPage(pageParam as string | undefined, {
      status: status || undefined,
      search: search || undefined,
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    staleTime: 60_000,
  });

  const allLoaded = useMemo(
    () => (data?.pages ?? []).flatMap(p => p.employees),
    [data],
  );
  const employees = useMemo(() => {
    let r = allLoaded;
    if (dept) r = r.filter(e => e.department === dept);
    if (zone) r = r.filter(e => e.zone === zone);
    return r;
  }, [allLoaded, dept, zone]);

  // Total comes from the server's first-page total_estimate (cheap), so the
  // KPI never has to walk every page. Granular breakdowns (active/on-leave/
  // unverified) would need either a backend aggregate endpoint or N small
  // status-filtered counts — deferred until the API exposes /stats.
  const total = data?.pages[0]?.totalEstimate ?? allLoaded.length;

  // Auto-load next page when the sentinel scrolls into view.
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const root = scrollRef.current ?? null;
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    }, { root, rootMargin: "200px" });
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const hasFilter = !!(search || dept || zone || status);
  const clear = () => { setSearch(""); setDept(""); setZone(""); setStatus(""); };

  return (
    <div className="flex flex-col h-full">
      {/* KPI strip — total is the server total_estimate (cheap); loaded is
          how much of it has streamed in so far. */}
      <div className="px-5 py-3 border-b border-border bg-card grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50">
          <Users size={14} className="text-foreground" />
          <div>
            <p className="text-[18px] font-extrabold leading-none tabular-nums text-foreground">{total.toLocaleString()}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Total Staff</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50">
          <UserCheck size={14} className="text-green-600 dark:text-green-400" />
          <div>
            <p className="text-[18px] font-extrabold leading-none tabular-nums text-green-600 dark:text-green-400">{allLoaded.length.toLocaleString()}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Loaded</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50 col-span-2 sm:col-span-1">
          <Clock size={14} className="text-blue-600 dark:text-blue-400" />
          <div className="flex-1">
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 transition-all" style={{ width: `${total ? Math.min(100, (allLoaded.length / total) * 100) : 0}%` }} />
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">{total ? Math.round((allLoaded.length / total) * 100) : 0}% loaded</p>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        {/* View toggle */}
        <div className="flex rounded-xl border border-border overflow-hidden bg-muted/40 p-0.5 gap-0.5 shrink-0">
          {(["grid", "list"] as const).map(v => (
            <button key={v} onClick={() => setView(v)} className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all", view === v ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
              {v === "grid" ? <LayoutGrid size={13} /> : <List size={13} />}
              <span className="capitalize">{v}</span>
            </button>
          ))}
        </div>
        <div className="w-px h-5 bg-border shrink-0" />
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input type="search" placeholder="Search staff…" value={search} onChange={e => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 w-44" />
        </div>
        <FilterBtn label="Department" value={dept}   options={DEPARTMENTS} onChange={setDept}   />
        <FilterBtn label="Zone"       value={zone}   options={ZONES}       onChange={setZone}   />
        <FilterBtn label="Status"     value={status} options={STATUSES}    onChange={setStatus} />
        {hasFilter && <button onClick={clear} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5"><X size={12} /> Clear</button>}
        <p className="ml-auto text-xs text-muted-foreground"><span className="font-bold text-foreground">{employees.length}</span> staff</p>
      </div>

      {/* API status banner */}
      {error && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-center gap-2">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0" />
          <p className="text-[11px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{error.code}:</span> {error.message}
            {!apiConfigured && " (set VITE_API_TOKEN in .env.local to use the live API)"}
          </p>
        </div>
      )}

      {/* Content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && employees.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
            <p className="text-sm text-muted-foreground">Loading employees…</p>
          </div>
        ) : view === "grid" ? (
          <div className="p-5" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "12px" }}>
            {employees.map(e => <EmpCard key={e.id} emp={e} onClick={() => nav(`/hr/employees/${e.id}`)} />)}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
              <tr>
                {["Employee", "Department", "Zone / Office", "Grade", "Status", "Identity"].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map(e => (
                <tr key={e.id} onClick={() => nav(`/hr/employees/${e.id}`)} className="border-b border-border/50 cursor-pointer hover:bg-muted/30 group">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar emp={e} />
                      <div>
                        <p className="font-semibold text-[12px] group-hover:text-primary transition-colors">{e.name}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{e.irNumber}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3"><div><p className="text-[12px]">{e.title}</p><p className="text-[10px] text-muted-foreground">{e.department}</p></div></td>
                  <td className="px-4 py-3"><div><p className="text-[12px]">{e.zone}</p><p className="text-[10px] text-muted-foreground truncate max-w-[160px]">{e.office}</p></div></td>
                  <td className="px-4 py-3"><span className="text-[12px] text-muted-foreground">GL-{e.gradeLevel}</span></td>
                  <td className="px-4 py-3"><StatusBadge status={e.status} /></td>
                  <td className="px-4 py-3">
                    {e.identityVerified
                      ? <span className="inline-flex items-center gap-1 text-[11px] text-green-600 dark:text-green-400 font-semibold"><ShieldCheck size={12} /> Verified</span>
                      : <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400 font-semibold"><ShieldOff size={12} /> Pending</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {employees.length === 0 && !isLoading && !error && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center"><Users size={20} className="text-muted-foreground/40" /></div>
            <p className="text-sm font-semibold">No employees found</p>
            <button onClick={clear} className="text-xs text-primary hover:opacity-80">Clear filters</button>
          </div>
        )}

        {/* Infinite-scroll sentinel: triggers fetchNextPage when visible. */}
        {hasNextPage && (
          <div ref={sentinelRef} className="flex items-center justify-center py-5">
            {isFetchingNextPage ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock size={12} className="animate-pulse" />
                Loading more…
              </div>
            ) : (
              <button onClick={() => fetchNextPage()} className="text-xs text-primary hover:opacity-80">
                Load more
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function EmployeeDetail({ params }: { params: { id: string } }) {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  const [tab, setTab] = useState<"overview" | "assets" | "identity">("overview");

  const { data: emp, isLoading, error } = useQuery<Employee | null, CadraApiError>({
    queryKey: ["employee", params.id],
    queryFn: () => fetchEmployee(params.id),
    staleTime: 60_000,
  });

  useEffect(() => {
    setTitle(emp?.name ?? "Employee");
    setSearchHandler(undefined);
  }, [emp, setTitle, setSearchHandler]);

  if (isLoading) {
    return (
      <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
        <Clock size={20} className="animate-pulse" />
        <p className="text-sm">Loading employee…</p>
      </div>
    );
  }
  if (error) {
    return (
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
  }
  if (!emp) return <div className="p-8 text-center text-muted-foreground">Employee not found.</div>;

  const initials = emp.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  const TABS = ["overview", "assets", "identity"] as const;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <button onClick={() => nav("/hr/employees")} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
        <span className="text-[10px]">←</span> Back to Employees
      </button>

      {/* Hero */}
      <div className="bg-card border border-border rounded-2xl p-6 flex items-start gap-5">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-[22px] font-extrabold text-white shadow-sm shrink-0" style={{ background: emp.avatarColor }}>
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-[20px] font-extrabold text-foreground leading-tight">{emp.name}</h1>
              <p className="text-[13px] text-muted-foreground mt-1">{emp.title} · {emp.department}</p>
              <p className="text-[12px] text-muted-foreground mt-0.5 font-mono">{emp.irNumber}</p>
            </div>
            <StatusBadge status={emp.status} />
          </div>
          <div className="mt-4 flex flex-wrap gap-4">
            <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground"><MapPin size={12} />{emp.office}, {emp.zone}</div>
            <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground"><Phone size={12} />{emp.phone}</div>
            <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground"><Mail size={12} />{emp.email}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 border-b border-border">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("px-4 py-2.5 text-[13px] font-medium capitalize transition-colors border-b-2 -mb-px", tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}
          >{t}</button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            ["IR Number", emp.irNumber],
            ["Grade Level", `GL-${emp.gradeLevel}`],
            ["Employment Type", emp.employmentType],
            ["Gender", emp.gender],
            ["Join Date", emp.joinDate],
            ["Access Card", emp.accessCardNo ?? "Not Issued"],
            ["Biometric", emp.biometricEnrolled ? "Enrolled" : "Not Enrolled"],
            ["Zone", emp.zone],
          ].map(([k, v]) => (
            <div key={k} className="bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{k}</span>
              <span className="text-[13px] font-medium text-foreground">{v}</span>
            </div>
          ))}
        </div>
      )}
      {tab === "assets" && <EmployeeAssetsTab employeeId={emp.id} nav={(p: string) => nav(p)} ir={emp.irNumber} />}
      {tab === "identity" && (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-3">
          {[
            ["NIN",           emp.nin ?? "Not provided",   emp.identityVerified ? "Verified" : "Pending"],
            ["Biometrics",    emp.biometricEnrolled ? "Enrolled" : "Not Enrolled", emp.biometricEnrolled ? "OK" : "Action needed"],
            ["Access Card",   emp.accessCardNo ?? "Not Issued", emp.accessCardNo ? "Active" : "Not Issued"],
          ].map(([k, v, s]) => (
            <div key={k} className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0">
              <span className="text-[12px] font-semibold text-muted-foreground">{k}</span>
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-foreground font-mono">{v}</span>
                <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded-lg", s === "Verified" || s === "OK" || s === "Active" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400")}>{s}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EmployeeAssetsTab({ employeeId, nav, ir }: { employeeId: string; nav: (path: string) => void; ir: string }) {
  const { data: assets = [], isLoading, error } = useQuery<Asset[], CadraApiError>({
    queryKey: ["employee-assets", employeeId],
    queryFn: () => fetchEmployeeAssetsApi(employeeId),
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-2xl p-6 flex flex-col items-center gap-2 text-muted-foreground">
        <Clock size={18} className="animate-pulse" />
        <p className="text-xs">Loading custodial assets…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-red-700 dark:text-red-400">
          <span className="font-semibold">{error.code}:</span> {error.message}
        </p>
      </div>
    );
  }
  if (assets.length === 0) {
    return (
      <div className="bg-card border border-border rounded-2xl p-6 text-center text-muted-foreground">
        <Briefcase size={28} className="mx-auto mb-3 opacity-30" />
        <p className="text-sm font-semibold">No custodial assets</p>
        <p className="text-xs mt-1">{ir} is not the current custodian of any asset.</p>
      </div>
    );
  }
  return (
    <div className="bg-card border border-border rounded-2xl divide-y divide-border">
      {assets.map(a => (
        <button
          key={a.id}
          onClick={() => nav(`/assets/${a.id}`)}
          className="w-full text-left px-4 py-3 hover:bg-muted/30 flex items-center justify-between gap-3"
        >
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-foreground truncate">{a.name}</p>
            <p className="text-[11px] text-muted-foreground font-mono truncate">{a.assetTag}</p>
          </div>
          <span className="text-[11px] text-muted-foreground shrink-0">{a.category}</span>
        </button>
      ))}
    </div>
  );
}
