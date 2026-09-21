import { useEffect, useState, useMemo } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  fetchAssetRegisterCounts,
  fetchDashboardKpis,
  fetchDashboardMap,
  fetchBarcodeRecentTags,
  lookupBarcode,
  type BarcodeTag,
} from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import {
  AlertCircle, AlertTriangle, ArrowRight, ChevronRight, Clock, Package,
  RefreshCw, ScanBarcode, ShieldAlert, ShieldCheck, Trash2,
  Wrench, ListChecks, Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import BrandPill from "@/components/BrandPill";

// There were four filter tabs over the map — All / Active / Repair /
// Unverified — setting a `pinFilter` that nothing read. They could not have
// been wired: the pins are LOCATIONS from `/dashboard/map` (id, name,
// coordinates, open requests) and carry neither an asset state nor a
// verification flag, so there is nothing on a pin to filter by. Four tabs that
// changed their own highlight and nothing else are gone.

export default function AssetRegisterDashboard() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Asset Register");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const counts = useQuery({
    queryKey: ["asset-register-counts"],
    queryFn: fetchAssetRegisterCounts,
    staleTime: 60_000,
  });

  const mapData = useQuery({
    queryKey: ["dashboard-map"],
    queryFn: fetchDashboardMap,
    staleTime: 60_000,
  });

  const recent = useQuery({
    queryKey: ["asset-recent-tags"],
    queryFn: () => fetchBarcodeRecentTags({ limit: 5 }),
    staleTime: 60_000,
  });

  // The /dashboard/kpis payload now carries an `assets.categories` array
  // (added in the dashboard model). Older API builds omit it; we render the
  // panel only when the field is present so the page stays valid against
  // either version.
  const kpis = useQuery({
    queryKey: ["dashboard-kpis"],
    queryFn: fetchDashboardKpis,
    staleTime: 60_000,
  });
  const categories = kpis.data?.assets?.categories ?? [];
  const categoryMax = categories.reduce((m, c) => Math.max(m, c.count), 0) || 1;

  const pins = useMemo<MapPinData[]>(() => {
    return (mapData.data?.locations ?? [])
      .filter(l => Number.isFinite(l.lat) && Number.isFinite(l.lng))
      .map(l => ({
        id: String(l.id),
        lat: l.lat,
        lng: l.lng,
        label: l.name,
        sublabel: l.state || undefined,
        count: l.open_requests || undefined,
      }));
  }, [mapData.data]);

  const err = (counts.error ?? mapData.error ?? recent.error) as CadraApiError | null;

  const refreshAll = () => {
    return Promise.all([
      counts.refetch(),
      mapData.refetch(),
      recent.refetch(),
      kpis.refetch(),
    ]);
  };

  const lastUpdated = counts.dataUpdatedAt
    ? new Date(counts.dataUpdatedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : "—";

  // `null`, not 0, until the counts are in: `Kpi` draws null as "—". A strip
  // reading *Missing 0 · Condemned 0* over a request that failed is a false
  // statement about the register; "—" is a true one about the screen.
  const c = counts.data ?? { total: null, active: null, inRepair: null, disposed: null, missing: null, unverified: null, verified: null };

  return (
    <div className="p-5 space-y-5 max-w-[1440px] mx-auto">
      {/* ─── Brand strip ────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <BrandPill />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[20px] font-extrabold text-foreground">Asset Register</h1>
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              NRS Facilities Management · staging.app.cadra.ng · Last updated: {lastUpdated}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refreshAll}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <RefreshCw size={12} className={cn((counts.isFetching || mapData.isFetching || recent.isFetching || kpis.isFetching) && "animate-spin")} /> Refresh
          </button>
          <button
            onClick={() => nav("/assets/list")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <ListChecks size={12} /> All Assets
          </button>
          <button
            onClick={() => nav("/assets/new")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
          >
            <Plus size={12} /> New Asset
          </button>
        </div>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-3 flex items-start gap-3">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{err.code}:</span> {err.message}
            {!apiConfigured && " (set VITE_API_TOKEN in .env.local)"}
          </p>
        </div>
      )}

      {/* ─── KPI strip ────────────────────────────────────────────────────
          "On register", not "Total Assets": the figure includes every disposed
          and missing asset — it is the register, not the stock. "Active,
          unverified" because that is now what it counts (it used to count
          missing and disposed assets too, under a label that did not say so).
          "Missing" replaces a "PM Overdue" tile that was permanently "—" — no
          endpoint exists to fill it — and closes the gap nothing explained:
          Total − Active − Under Repair − Condemned did not come to zero. It
          still need not: the model has a transferred state with no tile. */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="asset-kpi-strip">
        <Kpi label="On register"        value={c.total}      icon={Package}       color="text-foreground"                       highlight />
        <Kpi label="Active"             value={c.active}     icon={ShieldCheck}   color="text-green-600 dark:text-green-400"   />
        <Kpi label="Under Repair"       value={c.inRepair}   icon={Wrench}        color="text-amber-600 dark:text-amber-400"   />
        <Kpi label="Active, unverified" value={c.unverified} icon={ShieldAlert}   color="text-orange-600 dark:text-orange-400" />
        <Kpi label="Missing"            value={c.missing}    icon={AlertTriangle} color="text-red-600 dark:text-red-400"       />
        <Kpi label="Condemned"          value={c.disposed}   icon={Trash2}        color="text-muted-foreground"                />
      </div>

      {/* ─── Main grid: map + sidebar ───────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Asset locations map */}
        <section className="lg:col-span-2 bg-card border border-border rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="text-[13px] font-bold">Asset Locations</h2>
          </div>
          <NigeriaMap pins={pins} height={360} />
          <p className="text-[10px] text-muted-foreground">
            {pins.length} distinct sites · pins reflect locations with API-mapped coordinates
          </p>
        </section>

        {/* Right sidebar */}
        <aside className="space-y-4">
          <BarcodeStation />
          <RecentlyAdded
            data={recent.data ?? []}
            loading={recent.isLoading}
            onOpen={(assetId) => nav(`/assets/${assetId}`)}
          />
          <SidebarCard
            title="PM Due (14 days)"
            empty="No upcoming PM schedules"
            sub="API endpoint pending."
          />
        </aside>
      </div>

      {/* ─── Asset Categories breakdown ────────────────────────────────── */}
      {categories.length > 0 && (
        <section className="bg-card border border-border rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[13px] font-bold">Asset Categories</h2>
            <span className="text-[11px] text-muted-foreground">
              {categories.length} {categories.length === 1 ? "category" : "categories"}
            </span>
          </div>
          <ul className="space-y-2.5">
            {categories.map(cat => {
              const pct = (cat.count / categoryMax) * 100;
              return (
                <li key={cat.id ?? cat.name} className="flex items-center gap-3">
                  <span className="text-[12px] font-medium text-foreground w-44 shrink-0 truncate">
                    {cat.name}
                  </span>
                  <div className="flex-1 h-2 bg-muted/40 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.max(2, pct)}%`, background: "var(--nrs-red)" }}
                      title={`${cat.count.toLocaleString()} assets`}
                    />
                  </div>
                  <span className="text-[12px] font-bold text-foreground tabular-nums w-16 text-right shrink-0">
                    {cat.count.toLocaleString()}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

// ─── KPI tile ──────────────────────────────────────────────────────────

function Kpi({
  label, value, icon: Icon, color, note, highlight,
}: {
  label: string; value: number | null; icon: typeof Package;
  color: string; note?: string; highlight?: boolean;
}) {
  return (
    <div className={cn(
      "bg-card border rounded-2xl px-4 py-4",
      highlight ? "border-primary/30" : "border-border/50",
    )}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={11} className={color} />
        <p className={cn("text-[10px] font-semibold uppercase tracking-widest", color)}>{label}</p>
      </div>
      <p className={cn("text-[26px] font-extrabold leading-none tabular-nums", color)}>
        {value === null ? (note ?? "—") : value.toLocaleString()}
      </p>
    </div>
  );
}

// ─── Sidebar cards ─────────────────────────────────────────────────────

function SidebarCard({ title, children, empty, sub }: {
  title: string;
  children?: React.ReactNode;
  empty?: string;
  sub?: string;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
        <h3 className="text-[12px] font-bold">{title}</h3>
      </div>
      {children ?? (
        <div className="py-4 text-center">
          <p className="text-[12px] text-muted-foreground">{empty}</p>
          {sub && <p className="text-[10px] text-muted-foreground/70 mt-1">{sub}</p>}
        </div>
      )}
    </div>
  );
}

function BarcodeStation() {
  const [, nav] = useLocation();
  const [query, setQuery] = useState("");
  const lookup = useMutation({
    mutationFn: (q: string) => lookupBarcode(q),
    onSuccess: (result) => {
      // A miss is a 200 with {found: false}, not a rejected request.
      if (!result?.found || !result.asset_id) return;
      nav(`/assets/${result.asset_id}`);
      setQuery("");
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) lookup.mutate(query.trim());
  }

  const err = lookup.error as CadraApiError | null;

  return (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-2">
      <div className="flex items-center gap-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
        <h3 className="text-[12px] font-bold inline-flex items-center gap-1.5">
          <ScanBarcode size={12} /> Barcode Station
        </h3>
      </div>
      <form onSubmit={onSubmit}>
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Scan or type tag / asset code…"
          className="w-full px-3 py-2 text-xs border border-border rounded-xl bg-background placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </form>
      {lookup.isPending && (
        <p className="text-[10px] text-muted-foreground inline-flex items-center gap-1">
          <Clock size={10} className="animate-pulse" /> Looking up…
        </p>
      )}
      {err && (
        <p className="text-[11px] text-red-600 dark:text-red-400">
          <span className="font-semibold">{err.code}:</span> {err.message}
        </p>
      )}
      {!err && lookup.data && !lookup.data.found && (
        <p className="text-[11px] text-muted-foreground">No active tag or asset matches that code.</p>
      )}
      <button
        type="button"
        onClick={() => nav("/tools/barcode")}
        className="text-[10px] text-primary hover:opacity-80 inline-flex items-center gap-1"
      >
        Open Barcode Station <ArrowRight size={9} />
      </button>
    </div>
  );
}

function RecentlyAdded({
  data, loading, onOpen,
}: {
  data: BarcodeTag[];
  loading: boolean;
  onOpen: (assetId: number) => void;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
          <h3 className="text-[12px] font-bold">Recently Added</h3>
        </div>
        {data.length > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums">{data.length}</span>
        )}
      </div>
      {loading ? (
        <p className="text-[11px] text-muted-foreground py-3 text-center">Loading…</p>
      ) : data.length === 0 ? (
        <p className="text-[12px] text-muted-foreground py-3 text-center">No recent tags.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.slice(0, 5).map(t => (
            <li key={t.tag_id}>
              <button
                onClick={() => onOpen(t.asset_id)}
                className="w-full text-left py-2 px-1 hover:bg-muted/30 rounded-lg flex items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-foreground truncate">{t.asset_name}</p>
                  <p className="text-[10px] text-muted-foreground font-mono truncate">
                    {t.tag_number} · {t.location || "—"}
                  </p>
                </div>
                <span className={cn(
                  "shrink-0 text-[9px] font-semibold px-1.5 py-0.5 rounded border",
                  t.tag_state === "active"
                    ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
                    : "bg-muted border-border text-muted-foreground",
                )}>
                  {t.tag_state}
                </span>
                <ChevronRight size={11} className="text-muted-foreground/40 shrink-0" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
