import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchBarcodeKpis,
  fetchBarcodeRecentTags,
  type BarcodeTag,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  AlertCircle, Clock, Tag, ShieldCheck, AlertTriangle, Trash2, HelpCircle,
  Package, RefreshCw, Search, ArrowUpRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function TagAdoptionReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Asset Tag Adoption Report");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis = useQuery({
    queryKey: ["report-tag-kpis"],
    queryFn: fetchBarcodeKpis,
    staleTime: 60_000,
  });
  const tags = useQuery({
    queryKey: ["report-tag-recent"],
    queryFn: () => fetchBarcodeRecentTags({ limit: 100 }),
    staleTime: 60_000,
  });

  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  const rows = useMemo<BarcodeTag[]>(() => {
    const list = tags.data ?? [];
    const q = search.trim().toLowerCase();
    return list.filter(t => {
      if (stateFilter && t.tag_state !== stateFilter) return false;
      if (!q) return true;
      return t.tag_number.toLowerCase().includes(q) ||
             t.asset_name.toLowerCase().includes(q) ||
             (t.location ?? "").toLowerCase().includes(q) ||
             (t.domain ?? "").toLowerCase().includes(q);
    });
  }, [tags.data, search, stateFilter]);

  const err = (kpis.error ?? tags.error) as CadraApiError | null;
  const refresh = () => { kpis.refetch(); tags.refetch(); };

  if (kpis.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading tag adoption…</p>
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
  const taggedPct = k.total_assets > 0
    ? Math.round((k.active_tags / k.total_assets) * 100)
    : 0;

  const tiles = [
    { label: "Total assets",         value: k.total_assets,         icon: Package,       color: "text-foreground" },
    { label: "Active tags",          value: k.active_tags,          icon: ShieldCheck,   color: "text-green-600 dark:text-green-400" },
    { label: "Pending replacement",  value: k.pending_replacement,  icon: AlertTriangle, color: "text-amber-600 dark:text-amber-400" },
    { label: "Scrapped",             value: k.scrapped_tags,        icon: Trash2,        color: "text-muted-foreground" },
    { label: "Untagged",             value: k.untagged,             icon: HelpCircle,    color: "text-red-600 dark:text-red-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <span className="inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider"
                style={{ background: "#E01F26", color: "white" }}>NRS</span>
          <div>
            <h1 className="text-xl font-bold text-foreground">Asset Tag Adoption Report</h1>
            <p className="text-xs text-muted-foreground mt-1">
              {taggedPct}% tagged · {k.untagged.toLocaleString()} untagged assets remain.
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn((kpis.isFetching || tags.isFetching) && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
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

      {/* Recent tags table */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
          <div className="flex items-center gap-2">
            <Tag size={14} className="text-primary" />
            <h2 className="text-[13px] font-bold">Recent tag activity</h2>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search tag, asset, location…"
                className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background w-64"
              />
            </div>
            <select
              value={stateFilter}
              onChange={e => setStateFilter(e.target.value)}
              className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background"
            >
              <option value="">All tag states</option>
              <option value="active">Active</option>
              <option value="pending_replacement">Pending replacement</option>
              <option value="scrapped">Scrapped</option>
            </select>
            <span className="text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{rows.length.toLocaleString()}</span>
            </span>
          </div>
        </div>

        {tags.isLoading ? (
          <p className="text-[12px] text-muted-foreground py-8 text-center inline-flex items-center justify-center gap-2 w-full">
            <Clock size={12} className="animate-pulse" /> Loading…
          </p>
        ) : rows.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-8 text-center">
            No recent tag activity matches the current filters.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead>
                <tr className="border-b border-border">
                  {["Tag", "Asset", "Domain", "Location", "Condition", "State", ""].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(t => (
                  <tr key={t.tag_id} className="border-b border-border/40 hover:bg-muted/20">
                    <td className="px-3 py-2 text-[12px] font-mono">{t.tag_number}</td>
                    <td className="px-3 py-2 text-[12px] font-semibold truncate max-w-[240px]">{t.asset_name}</td>
                    <td className="px-3 py-2 text-[12px] text-muted-foreground">{t.domain || "—"}</td>
                    <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">{t.location || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-2 text-[12px]">{t.condition || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-2">
                      <span className={cn(
                        "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border",
                        t.tag_state === "active"
                          ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
                          : t.tag_state === "pending_replacement"
                          ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 text-amber-700 dark:text-amber-400"
                          : "bg-muted border-border text-muted-foreground",
                      )}>{t.tag_state.replace("_", " ")}</span>
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => nav(`/assets/${t.asset_id}`)}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:opacity-80"
                      >
                        Open <ArrowUpRight size={10} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
