import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchDashboardKpis,
  fetchAllLocations,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  AlertCircle, Clock, MapPin, MapPinOff, CheckCircle2, RefreshCw, Search,
  ChevronLeft, ChevronRight, ArrowUpRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

export default function LocationCoverageReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Location Coverage Report");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis = useQuery({
    queryKey: ["report-coverage-kpis"],
    queryFn: fetchDashboardKpis,
    staleTime: 60_000,
  });
  const locs = useQuery({
    queryKey: ["report-coverage-locations"],
    queryFn: fetchAllLocations,
    staleTime: 5 * 60_000,
  });

  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  // Mapped pins (locations with coords) — for the map. Unmapped (no coords)
  // are the punch list shown in the table below.
  const mappedPins = useMemo<MapPinData[]>(() => {
    return (locs.data ?? [])
      .filter(l => l.coordinates && Number.isFinite(l.coordinates.lat) && Number.isFinite(l.coordinates.lng))
      .map(l => ({
        id: l.id,
        lat: l.coordinates!.lat,
        lng: l.coordinates!.lng,
        label: l.name,
        sublabel: l.state || l.city || undefined,
      }));
  }, [locs.data]);

  const unmappedAll = useMemo(() => {
    const list = (locs.data ?? []).filter(l => !l.coordinates);
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(l =>
      l.name.toLowerCase().includes(q) ||
      (l.state ?? "").toLowerCase().includes(q) ||
      (l.city ?? "").toLowerCase().includes(q) ||
      (l.locationType ?? "").toLowerCase().includes(q),
    );
  }, [locs.data, search]);

  const unmappedPage = useMemo(() => {
    const start = page * PAGE_SIZE;
    return unmappedAll.slice(start, start + PAGE_SIZE);
  }, [unmappedAll, page]);

  const totalPages = Math.max(1, Math.ceil(unmappedAll.length / PAGE_SIZE));

  const err = (kpis.error ?? locs.error) as CadraApiError | null;
  const refresh = () => { kpis.refetch(); locs.refetch(); };

  if (kpis.isLoading || locs.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading location coverage…</p>
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

  // Prefer API-reported counts; fall back to client-computed if absent.
  const total = kpis.data?.locations?.total ?? (locs.data?.length ?? 0);
  const mapped = kpis.data?.locations?.mapped ?? mappedPins.length;
  const unmapped = Math.max(0, total - mapped);
  const mappedPct = total > 0 ? Math.round((mapped / total) * 100) : 0;
  const unmappedPct = total > 0 ? Math.round((unmapped / total) * 100) : 0;

  const tiles = [
    { label: "Total locations", value: total.toLocaleString(),    icon: MapPin,      color: "text-foreground" },
    { label: "Mapped",          value: `${mapped.toLocaleString()} (${mappedPct}%)`,    icon: CheckCircle2, color: "text-green-600 dark:text-green-400" },
    { label: "Unmapped",        value: `${unmapped.toLocaleString()} (${unmappedPct}%)`, icon: MapPinOff,    color: "text-amber-600 dark:text-amber-400" },
    { label: "Sites on map",    value: mappedPins.length.toLocaleString(), icon: MapPin, color: "text-blue-600 dark:text-blue-400" },
  ];

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Brand strip */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <span className="inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider"
                style={{ background: "#E01F26", color: "white" }}>NRS</span>
          <div>
            <h1 className="text-xl font-bold text-foreground">Location Coverage Report</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Geocoding punch list — {unmapped.toLocaleString()} of {total.toLocaleString()} sites still need coordinates.
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
        >
          <RefreshCw size={12} className={cn((kpis.isFetching || locs.isFetching) && "animate-spin")} /> Refresh
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
            <p className={cn(
              "font-extrabold leading-none tabular-nums",
              typeof t.value === "string" && t.value.length > 8 ? "text-[18px]" : "text-[26px]",
              t.color,
            )}>
              {t.value}
            </p>
          </div>
        ))}
      </div>

      {/* Map */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Mapped sites ({mappedPins.length.toLocaleString()})</h2>
        <NigeriaMap pins={mappedPins} height={400} />
      </div>

      {/* Unmapped list */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
          <h2 className="text-[13px] font-bold">Unmapped locations — geocoding punch list</h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
              <input
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(0); }}
                placeholder="Search name, state, city, type…"
                className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background w-64"
              />
            </div>
            <span className="text-xs text-muted-foreground">
              <span className="font-bold text-foreground">{unmappedAll.length.toLocaleString()}</span> unmapped
            </span>
          </div>
        </div>

        {unmappedAll.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-8 text-center">
            All locations are mapped. Nothing to do here.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-border">
                    {["Name", "Type", "City", "State", "Action"].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {unmappedPage.map(l => (
                    <tr key={l.id} className="border-b border-border/40 hover:bg-muted/20">
                      <td className="px-3 py-2 text-[12px] font-semibold truncate max-w-[260px]">{l.name}</td>
                      <td className="px-3 py-2 text-[12px] text-muted-foreground">{l.locationType ?? "—"}</td>
                      <td className="px-3 py-2 text-[12px] truncate max-w-[140px]">{l.city ?? <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2 text-[12px] truncate max-w-[140px]">{l.state ?? <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => nav(`/locations/${l.id}/edit`)}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:opacity-80"
                        >
                          Add coordinates <ArrowUpRight size={10} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/40">
              <span className="text-[11px] text-muted-foreground tabular-nums">
                Page {page + 1} of {totalPages} · showing {unmappedPage.length} of {unmappedAll.length.toLocaleString()}
              </span>
              <div className="flex items-center gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-lg border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={11} /> Prev
                </button>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-lg border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next <ChevronRight size={11} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
