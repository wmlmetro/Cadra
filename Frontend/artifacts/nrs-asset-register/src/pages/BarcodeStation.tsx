import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchBarcodeKpis, fetchBarcodeRecentTags, lookupBarcode, type BarcodeTag,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  ScanBarcode, AlertCircle, Tag, Package, AlertTriangle, XCircle,
  ArrowRight, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function BarcodeStation() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Barcode Station");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis   = useQuery({ queryKey: ["barcode-kpis"],   queryFn: fetchBarcodeKpis,   staleTime: 30_000 });
  const recent = useQuery({ queryKey: ["barcode-recent"], queryFn: () => fetchBarcodeRecentTags({ limit: 50 }), staleTime: 30_000 });

  const [query, setQuery] = useState("");
  const lookup = useMutation({
    mutationFn: (q: string) => lookupBarcode(q),
  });

  const k = kpis.data ?? { total_assets: 0, active_tags: 0, pending_replacement: 0, scrapped_tags: 0, untagged: 0 };

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) lookup.mutate(query.trim());
  }

  // The lookup endpoint returns either a flat BarcodeTag or
  // {tag, asset} — handle both.
  const lookupResult = lookup.data;
  const lookupTag: BarcodeTag | null =
    !lookupResult ? null :
    "tag_id" in lookupResult ? lookupResult :
    (lookupResult.tag ?? null);
  const lookupAssetId: number | null =
    !lookupResult ? null :
    "tag_id" in lookupResult ? lookupResult.asset_id :
    (lookupResult.asset?.id ?? null);
  const lookupErr = lookup.error as CadraApiError | null;

  return (
    <div className="p-6 space-y-5 max-w-[1100px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground">Barcode Station</h1>
        <p className="text-xs text-muted-foreground mt-1">Asset tag lookup, batch printing, and tag inventory.</p>
      </div>

      {kpis.error && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{(kpis.error as CadraApiError).code}:</span> {(kpis.error as CadraApiError).message}
          </p>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KpiTile label="Total assets"        value={k.total_assets}        icon={Package}        color="text-foreground" />
        <KpiTile label="Active tags"         value={k.active_tags}         icon={Tag}            color="text-green-600 dark:text-green-400" />
        <KpiTile label="Pending replacement" value={k.pending_replacement} icon={AlertTriangle}  color="text-amber-600 dark:text-amber-400" />
        <KpiTile label="Scrapped"            value={k.scrapped_tags}       icon={XCircle}        color="text-red-600 dark:text-red-400" />
        <KpiTile label="Untagged"            value={k.untagged}            icon={Tag}            color="text-muted-foreground" />
      </div>

      {/* Scan / lookup */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <div className="flex items-center gap-2">
          <ScanBarcode size={14} className="text-primary" />
          <h2 className="text-[13px] font-bold">Scan or type tag</h2>
        </div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="e.g. NRS-LT-00422"
              className="w-full pl-7 pr-3 py-2 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || lookup.isPending}
            className={cn(
              "px-4 py-2 text-xs font-semibold rounded-xl",
              query.trim() && !lookup.isPending ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            Lookup
          </button>
        </form>

        {lookupErr && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-700 dark:text-red-400">
              <span className="font-semibold">{lookupErr.code}:</span> {lookupErr.message}
            </p>
          </div>
        )}

        {lookupTag && (
          <div className="bg-background border border-primary/30 rounded-xl p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[14px] font-bold text-foreground">{lookupTag.asset_name}</p>
                <p className="text-[12px] text-muted-foreground font-mono">{lookupTag.tag_number}</p>
                <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                  <span>State: <span className="text-foreground font-semibold">{lookupTag.tag_state}</span></span>
                  <span>Condition: <span className="text-foreground font-semibold">{lookupTag.condition}</span></span>
                  <span>Location: <span className="text-foreground font-semibold">{lookupTag.location}</span></span>
                  <span>Domain: <span className="text-foreground font-semibold">{lookupTag.domain}</span></span>
                </div>
              </div>
              {lookupAssetId && (
                <button onClick={() => nav(`/assets/${lookupAssetId}`)} className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:opacity-80">
                  Open asset <ArrowRight size={11} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Recently scanned/printed */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Recent tags</h2>
        {!recent.data || recent.data.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">No recent tags.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-border">
                  {["Tag", "Asset", "Domain", "Condition", "Location", "State"].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.data.map(t => (
                  <tr key={t.tag_id} onClick={() => nav(`/assets/${t.asset_id}`)} className="border-b border-border/40 hover:bg-muted/20 cursor-pointer">
                    <td className="px-3 py-2 text-[12px] font-mono">{t.tag_number}</td>
                    <td className="px-3 py-2 text-[12px] truncate max-w-[200px]">{t.asset_name}</td>
                    <td className="px-3 py-2 text-[12px] text-muted-foreground">{t.domain}</td>
                    <td className="px-3 py-2 text-[12px]">{t.condition}</td>
                    <td className="px-3 py-2 text-[12px] truncate max-w-[180px]">{t.location}</td>
                    <td className="px-3 py-2 text-[11px]">
                      <span className={cn(
                        "inline-flex items-center px-2 py-0.5 rounded-lg font-semibold border",
                        t.tag_state === "active" && "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400",
                        t.tag_state !== "active" && "bg-muted border-border text-muted-foreground",
                      )}>{t.tag_state}</span>
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

function KpiTile({ label, value, icon: Icon, color }: { label: string; value: number; icon: typeof Tag; color: string }) {
  return (
    <div className="bg-card border border-border/50 rounded-2xl px-4 py-4">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={12} className={color} />
        <p className={cn("text-[10px] font-semibold uppercase tracking-widest", color)}>{label}</p>
      </div>
      <p className={cn("text-[22px] font-extrabold leading-none tabular-nums", color)}>{value.toLocaleString()}</p>
    </div>
  );
}
