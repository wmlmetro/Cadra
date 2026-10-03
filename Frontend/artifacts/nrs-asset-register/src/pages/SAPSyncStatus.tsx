import { useEffect } from "react";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchSapSyncStatusCounts, fetchLatestSapSync } from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import {
  ShieldCheck, Clock, AlertCircle, CircleSlash, Upload, ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

export default function SAPSyncStatus() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  // Handoff 46: *Bulk import* opens a page whose one purpose is
  // `POST /integrations/employees/import`, which needs `integrations:write`.
  const scopes = useScopes();

  useEffect(() => {
    setTitle("SAP Sync Status");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const counts = useQuery<Awaited<ReturnType<typeof fetchSapSyncStatusCounts>>, CadraApiError>({
    queryKey: ["sap-sync-counts"],
    queryFn: fetchSapSyncStatusCounts,
    staleTime: 60_000,
  });

  const latestSync = useQuery<string | null, CadraApiError>({
    queryKey: ["sap-latest-sync"],
    queryFn: fetchLatestSapSync,
    staleTime: 60_000,
  });

  const c = counts.data ?? { synced: 0, pending: 0, error: 0, never: 0, total: 0 };
  const pct = (n: number) => c.total ? Math.round((n / c.total) * 100) : 0;

  const tiles = [
    { label: "Synced",  value: c.synced,  pct: pct(c.synced),  icon: ShieldCheck,  color: "text-green-600 dark:text-green-400",   bg: "bg-green-500" },
    { label: "Pending", value: c.pending, pct: pct(c.pending), icon: Clock,        color: "text-blue-600 dark:text-blue-400",     bg: "bg-blue-500"  },
    { label: "Error",   value: c.error,   pct: pct(c.error),   icon: AlertCircle,  color: "text-red-600 dark:text-red-400",       bg: "bg-red-500"   },
    { label: "Never",   value: c.never,   pct: pct(c.never),   icon: CircleSlash,  color: "text-muted-foreground",                bg: "bg-gray-400"  },
  ];

  return (
    <div className="p-6 space-y-6 max-w-[1100px] mx-auto">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">SAP Sync Status</h1>
          <p className="text-xs text-muted-foreground mt-1">
            SuccessFactors identity sync state across all employees.
            {latestSync.data && (
              <> Latest sync: <span className="font-mono">{latestSync.data}</span></>
            )}
          </p>
        </div>
        {scopes.has(SCOPE.integrationsWrite) && (
          <button
            onClick={() => nav("/hr/import")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
          >
            <Upload size={12} /> Bulk import
          </button>
        )}
      </div>

      {counts.error && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{counts.error.code}:</span> {counts.error.message}
            {!apiConfigured && " (set VITE_API_TOKEN in .env.local)"}
          </p>
        </div>
      )}

      {/* Breakdown tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map(t => (
          <button
            key={t.label}
            onClick={() => nav("/hr/employees")}
            className="bg-card border border-border/50 rounded-2xl px-4 py-4 flex items-center gap-3 hover:border-primary/30 hover:shadow-md transition-all text-left"
          >
            <div className={cn("w-2 h-12 rounded-full shrink-0", t.bg)} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <t.icon size={12} className={t.color} />
                <p className={cn("text-[11px] font-semibold uppercase tracking-wide", t.color)}>{t.label}</p>
              </div>
              <p className={cn("text-[22px] font-extrabold leading-none tabular-nums mt-1", t.color)}>
                {t.value.toLocaleString()}
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{t.pct}% of {c.total.toLocaleString()}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Health bar */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <p className="text-[13px] font-bold mb-3">Sync health</p>
        <div className="h-3 bg-muted rounded-full overflow-hidden flex">
          <div className="h-full bg-green-500" style={{ width: `${pct(c.synced)}%` }} title={`${c.synced} synced`} />
          <div className="h-full bg-blue-500"  style={{ width: `${pct(c.pending)}%` }} title={`${c.pending} pending`} />
          <div className="h-full bg-red-500"   style={{ width: `${pct(c.error)}%` }}   title={`${c.error} error`} />
          <div className="h-full bg-gray-400"  style={{ width: `${pct(c.never)}%` }}   title={`${c.never} never`} />
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
          <span><span className="inline-block w-2 h-2 rounded-full bg-green-500 align-middle mr-1" />Synced</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 align-middle mr-1" />Pending</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 align-middle mr-1" />Error</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-gray-400 align-middle mr-1" />Never</span>
        </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-5 flex items-start gap-3">
        <ShieldCheck size={16} className="text-muted-foreground/70 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-[13px] font-semibold text-foreground">Triggering a sync</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            Inbound sync arrives via <code className="font-mono">POST /api/v1/integrations/sap/employee-sync</code>
            {" "}from SuccessFactors. To onboard a one-off batch, use the bulk import
            wizard (above) which accepts an .xlsx nominal-roll file.
          </p>
          <button
            onClick={() => nav("/hr/employees")}
            className="mt-2 inline-flex items-center gap-1 text-[12px] font-semibold text-primary hover:opacity-80"
          >
            View all employees <ArrowRight size={11} />
          </button>
        </div>
      </div>
    </div>
  );
}
