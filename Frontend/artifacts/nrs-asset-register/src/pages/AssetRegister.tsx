import { useState, useEffect, useMemo, useRef } from "react";
import { useLocation, useSearch } from "wouter";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchAssetsPage, fetchAllLocations, type AssetsPage,
  WARRANTY_VIEWS, WARRANTY_SOON_DAYS, parseWarrantyFilter, warrantySoonWindow,
  type WarrantyFilter,
} from "@/lib/dataProvider";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import { apiConfigured, CadraApiError } from "@/lib/api";
import type { ApprovalStatus, Asset } from "@/types";
import AssetStatusPills from "@/components/AssetStatusPills";
import ConditionBadge from "@/components/ConditionBadge";
import {
  Monitor, Car, Sofa, MapPin, User, Search, X,
  LayoutGrid, List, SlidersHorizontal, ChevronDown,
  ArrowUpDown, ArrowUp, ArrowDown, Map as MapIcon, Clock, AlertCircle,
} from "lucide-react";
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  flexRender, type SortingState, type ColumnDef,
} from "@tanstack/react-table";
import { cn, formatIsoDate } from "@/lib/utils";
import { useEnum, useEnumLabel } from "@/hooks/useEnums";

const CATEGORIES = ["IT Equipment", "Fleet / Vehicles", "Furniture & Fittings"] as const;
// Three more used to be offered here — allottee not in nominal roll, VIN not
// verifiable, possible duplicate. The back end models none of them, so each
// always answered zero rows and said nothing about why. "Not in service" is
// every asset that is not active: missing, disposed, under repair, transferred.
//
// "Review — no SAP code" (handoff 30) is NOT a fourth of those. It is the
// server's `sap_reconciliation_state = exception`, a stored compute measured
// on real rows before it was wired, and choosing it asks the SERVER for them
// (`statusToServerFilter`) — a filter over the 200 rows already on screen
// would have answered zero on most tenants, with the findings further down a
// walk nobody had made, which is the same silence by another route.
const STATUSES = [
  "Cleared",
  "Review — data quality",
  "Review — no SAP code",
  "Not in service",
] as const satisfies readonly ApprovalStatus[];
// There is no CONDITIONS list here. It read ["Good", "Fair", "Poor",
// "Decommissioned"] — four of the model's five `nrs.asset.condition` values,
// missing `new`, so the Condition filter could not offer New at all and the
// 282 assets stored that way (204 jaizbankplc, 54 nrs19, 24 cadra19) were
// unreachable through this toolbar by any selection the user could make. The
// options now come from `useEnum("condition")`, which reads the Selection off
// the model at request time.
const GROUP_BY_OPTIONS = ["None", "By Category", "By Zone", "By Status"] as const;

const CATEGORY_CONFIG = {
  "IT Equipment":       { icon: Monitor,  bg: "bg-blue-50 dark:bg-blue-950/40",    icon_color: "text-blue-500",    border: "border-blue-100 dark:border-blue-900/40"  },
  "Fleet / Vehicles":   { icon: Car,      bg: "bg-emerald-50 dark:bg-emerald-950/40", icon_color: "text-emerald-500", border: "border-emerald-100 dark:border-emerald-900/40" },
  "Furniture & Fittings": { icon: Sofa,  bg: "bg-amber-50 dark:bg-amber-950/40",   icon_color: "text-amber-500",   border: "border-amber-100 dark:border-amber-900/40"  },
} as const;

function AssetCard({ asset, onClick }: { asset: Asset; onClick: () => void }) {
  const cfg = CATEGORY_CONFIG[asset.category];
  const Icon = cfg.icon;
  // Anything not "Cleared" used to go amber, and a missing or disposed asset
  // WAS "Cleared", so it wore the same plain border as healthy stock. A
  // missing asset is red — on a wall of cards it is the one that should not
  // look like the others. Everything else out of service (disposed, under
  // repair, transferred) is a heavier slate: set apart, without the alarm.
  // The two review findings keep the colours of their pills: amber for data
  // quality, orange for an asset finance has not booked.
  const borderCls =
    asset.status === "Cleared" ? "border-border" :
    asset.lifecycleState === "missing" ? "border-red-300/80 dark:border-red-800/50" :
    asset.status === "Not in service" ? "border-slate-400/70 dark:border-slate-600/60" :
    asset.status === "Review — no SAP code" ? "border-orange-300/80 dark:border-orange-800/40" :
    "border-amber-200/70 dark:border-amber-800/30";

  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-card border rounded-2xl p-4 cursor-pointer transition-all duration-150 group flex flex-col gap-3",
        "hover:shadow-md hover:-translate-y-0.5 hover:border-primary/30",
        borderCls
      )}
      data-testid={`card-asset-${asset.id}`}
    >
      {/* Header: icon + name + condition */}
      <div className="flex items-start gap-3">
        <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border", cfg.bg, cfg.border)}>
          <Icon size={17} className={cfg.icon_color} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-[13px] text-foreground leading-snug line-clamp-2 group-hover:text-primary transition-colors">
            {asset.name}
          </p>
          <p className="text-[10px] text-muted-foreground font-mono mt-0.5 truncate">
            {asset.assetTag || asset.legacyCode}
          </p>
        </div>
        <ConditionBadge condition={asset.condition} />
      </div>

      {/* Meta: custodian + location */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <User size={10} className="shrink-0 text-muted-foreground/60" />
          <span className="truncate">
            {asset.custodianName ?? <span className="italic">Pool — {asset.department}</span>}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <MapPin size={10} className="shrink-0 text-muted-foreground/60" />
          <span className="truncate">{asset.location.office}, {asset.location.state}</span>
        </div>
      </div>

      {/* Footer: status */}
      <div className="pt-2.5 border-t border-border/60 flex items-center justify-between gap-2">
        <AssetStatusPills status={asset.status} lifecycleState={asset.lifecycleState} />
        <span className="text-[10px] text-muted-foreground/60 font-mono shrink-0">
          {asset.id.split("-").slice(0, 2).join("-")}
        </span>
      </div>
    </div>
  );
}

function EmptyState({ onClear }: { onClear: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
      <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center">
        <Search size={22} className="text-muted-foreground/50" />
      </div>
      <div>
        <p className="text-sm font-semibold text-foreground">No assets found</p>
        <p className="text-xs text-muted-foreground mt-1">Try adjusting your filters or search query</p>
      </div>
      <button
        onClick={onClear}
        className="mt-1 text-xs font-semibold text-primary hover:opacity-80 transition-opacity"
      >
        Clear all filters
      </button>
    </div>
  );
}

function CardView({ assets, onSelect }: { assets: Asset[]; onSelect: (id: string) => void }) {
  return (
    <div className="p-5" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "12px" }}>
      {assets.map((asset) => (
        <AssetCard key={asset.id} asset={asset} onClick={() => onSelect(asset.id)} />
      ))}
    </div>
  );
}

function SortIcon({ state }: { state: false | "asc" | "desc" }) {
  if (state === "asc") return <ArrowUp size={11} className="text-primary" />;
  if (state === "desc") return <ArrowDown size={11} className="text-primary" />;
  return <ArrowUpDown size={11} className="opacity-30 group-hover:opacity-60 transition-opacity" />;
}

function ListView({ assets, onSelect }: { assets: Asset[]; onSelect: (id: string) => void }) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo<ColumnDef<Asset>[]>(() => [
    {
      accessorKey: "name",
      header: "Asset",
      size: 260,
      cell: ({ row }) => {
        const cfg = CATEGORY_CONFIG[row.original.category];
        const Icon = cfg.icon;
        return (
          <div className="flex items-center gap-3">
            <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border", cfg.bg, cfg.border)}>
              <Icon size={13} className={cfg.icon_color} />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-[12px] text-foreground group-hover:text-primary transition-colors truncate">{row.original.name}</p>
              <p className="text-[10px] text-muted-foreground font-mono">{row.original.assetTag || row.original.legacyCode}</p>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "subcategory",
      header: "Type",
      cell: ({ getValue }) => <span className="text-[12px] text-muted-foreground">{getValue() as string}</span>,
    },
    {
      accessorKey: "custodianName",
      header: "Custodian",
      cell: ({ row }) => (
        <span className="text-[12px] text-muted-foreground">
          {row.original.custodianName ?? <span className="italic text-muted-foreground/60">Pool</span>}
        </span>
      ),
    },
    {
      accessorKey: "location",
      header: "Location",
      cell: ({ row }) => (
        <div>
          <p className="text-[12px] text-muted-foreground">{row.original.location.office}</p>
          <p className="text-[10px] text-muted-foreground/60">{row.original.location.zone}</p>
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <AssetStatusPills status={row.original.status} lifecycleState={row.original.lifecycleState} />,
    },
    {
      accessorKey: "condition",
      header: "Condition",
      cell: ({ row }) => <ConditionBadge condition={row.original.condition} />,
    },
  ], []);

  const table = useReactTable({
    data: assets,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full" data-testid="table-asset-list">
        <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest cursor-pointer group whitespace-nowrap"
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <span className="flex items-center gap-1.5">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    <SortIcon state={header.column.getIsSorted()} />
                  </span>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, i) => (
            <tr
              key={row.id}
              className="border-b border-border/50 cursor-pointer transition-colors hover:bg-muted/30 group"
              onClick={() => onSelect(row.original.id)}
              data-testid={`row-asset-${row.original.id}`}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Custom dropdown component replacing native <select>
function FilterDropdown({
  label, value, options, onChange, labelOf, allLabel,
}: {
  label: string;
  /** The no-filter entry. Defaults to "All <label>s", which reads wrongly for
   *  a label that is not a countable noun ("All Warrantys"). */
  allLabel?: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
  /** Renders an option for display while `onChange` still hands back the raw
   *  option. Category and Status are their own display strings and pass this
   *  by; Condition's options are model keys (`good`, `decommissioned`) whose
   *  labels belong to the model, so it passes `useEnumLabel("condition")`. */
  labelOf?: (v: string) => string;
}) {
  const show = labelOf ?? ((v: string) => v);
  const [open, setOpen] = useState(false);
  const active = !!value;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-all",
          active
            ? "bg-primary text-white border-primary shadow-sm"
            : "border-border text-muted-foreground hover:text-foreground hover:border-border/80 bg-card"
        )}
        data-testid={`filter-${label.toLowerCase()}`}
      >
        {/* The WHOLE label. This cut at " —", which was tidy while one status
            began "Review —" and is ambiguous now that two do: both would have
            read "Review" on the button, with nothing to say which was on. */}
        {active ? show(value) : label}
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute top-full mt-1.5 left-0 z-50 bg-popover border border-border rounded-xl shadow-lg overflow-hidden min-w-[200px] py-1">
            <button
              className={cn("w-full text-left px-3 py-2 text-xs transition-colors hover:bg-accent", !value && "font-semibold text-foreground")}
              onClick={() => { onChange(""); setOpen(false); }}
            >
              {allLabel ?? `All ${label}s`}
            </button>
            {options.filter(Boolean).map((o) => (
              <button
                key={o}
                className={cn("w-full text-left px-3 py-2 text-xs transition-colors hover:bg-accent", value === o ? "font-semibold text-primary" : "text-muted-foreground")}
                onClick={() => { onChange(o); setOpen(false); }}
              >
                {show(o)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function AssetRegister() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [path, setNavLocation] = useLocation();
  const searchStr = useSearch();

  const [view, setView] = useState<"kanban" | "list" | "map">("kanban");
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  // A `nrs.asset.condition` key, or "" for no filter. It used to be narrowed to
  // the display union to keep the display->API condition map compile-checked;
  // that map is gone, and the narrowing it justified is what hid `new` from
  // this dropdown in the first place.
  const [filterCondition, setFilterCondition] = useState<string>("");
  const [groupBy, setGroupBy] = useState("None");
  // Register-wide order, served by the API, NOT a filter — it is deliberately
  // absent from `hasFilters`/`clearFilters`, because "clear filters" should
  // not silently reorder the list. Newest-first by default: an asset that has
  // just arrived from Vendra used to land on the last page of the walk.
  //
  // Distinct from the column-header sorting further up this file, which
  // reorders only the rows already fetched. That one cannot reach a row the
  // walk has not loaded yet; this one is the order the register is READ in.
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  // The model's own condition Selection, live off /api/v1/meta/enums, with the
  // seed in lib/enums.ts as the first-paint fallback. All five values, `new`
  // included.
  const conditionOptions = useEnum("condition");
  const conditionLabelOf = useEnumLabel("condition");
  // The warranty view lives in the URL (`?warranty=expiring`), not in state:
  // the dashboard's warranty tiles link here with it, and the number on a
  // tile is only honest if clicking it opens exactly the query it counted.
  // Anything that is not one of the four views reads as no filter.
  const filterWarranty = parseWarrantyFilter(new URLSearchParams(searchStr).get("warranty"));
  const setFilterWarranty = (v: string) => {
    const qs = new URLSearchParams(searchStr);
    if (v) qs.set("warranty", v); else qs.delete("warranty");
    const q = qs.toString();
    setNavLocation(`${path}${q ? `?${q}` : ""}`, { replace: true });
  };
  const warrantyStatusLabel = useEnumLabel("warranty_status");
  const warrantyLabelOf = (v: string) =>
    v === "expiring" ? `Expiring within ${WARRANTY_SOON_DAYS} days` : warrantyStatusLabel(v);
  const soonWindow = filterWarranty === "expiring" ? warrantySoonWindow() : null;

  useEffect(() => {
    setTitle("Asset Register");
    setSearchHandler((q) => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // Server-side: search, condition and — since handoff 30 — STATUS, wherever
  // the server can express it (`statusToServerFilter` in dataProvider: every
  // status but "Not in service"). It was client-side only, so choosing a
  // status narrowed the 200 rows already loaded under a register-wide count;
  // a rare status — an SAP exception is 34 rows of `nrs19` — would mostly
  // have answered "No assets found" while the rows sat further down the walk.
  //
  // The client-side pass below STILL runs for status, and has to: "Cleared"
  // and "Review — data quality" come back from the server including the
  // active assets that are SAP exceptions (the API has no "not"), and those
  // wear the exception's pill. Dropping them here keeps every row in
  // agreement with the filter it is shown under. The count beside it is the
  // server's, so under those two statuses it can run ahead of the rows by
  // however many exceptions it includes; under "no SAP code" it is exact.
  //
  // Category stays client-side only: the frontend's category is a 3-bucket
  // projection of the many real DB categories, not a native API filter, so it
  // narrows ONLY the rows already loaded (GO-LIVE §13.5.8). So does "Not in
  // service".
  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<AssetsPage, CadraApiError>({
    // `sortOrder` is in the key on purpose: the API records the walk
    // direction inside the cursor and answers 400 to a cursor replayed
    // against the other direction. A changed key starts a fresh query with
    // `initialPageParam: undefined` — no cursor — which is exactly the
    // restart that contract requires. Dropping it from the key would send
    // the held cursor into the opposite walk and 400 the page.
    // `filterStatus` is in the key for the same reason: it changes what the
    // server is asked, so it must start a fresh walk from page one.
    // `filterWarranty` likewise: it is a server filter (`warrantyToServerFilter`),
    // exact on the server, with no narrowing after the fetch.
    queryKey: ["assets", { search, filterCondition, filterStatus, filterWarranty, sortOrder }],
    queryFn: ({ pageParam }) => fetchAssetsPage(pageParam as string | undefined, {
      search: search || undefined,
      condition: filterCondition || undefined,
      status: filterStatus || undefined,
      warranty: (filterWarranty || undefined) as WarrantyFilter | undefined,
      sort: sortOrder,
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 60_000,
  });

  const allLoaded = useMemo(() => (data?.pages ?? []).flatMap(p => p.assets), [data]);
  const assets = useMemo(() => {
    let r = allLoaded;
    if (filterCategory) r = r.filter(a => a.category === filterCategory);
    if (filterStatus)   r = r.filter(a => a.status === filterStatus);
    return r;
  }, [allLoaded, filterCategory, filterStatus]);
  const totalEstimate = data?.pages[0]?.totalEstimate ?? allLoaded.length;

  // Auto-load on scroll.
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    }, { root: scrollRef.current ?? null, rootMargin: "200px" });
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Map view — load location pins only when the user opens the map tab.
  const { data: mapLocations = [] } = useQuery({
    queryKey: ["assetregister", "map-locations"],
    queryFn: fetchAllLocations,
    enabled: view === "map",
    staleTime: 5 * 60_000,
  });
  const mapPins = useMemo<MapPinData[]>(() => {
    const byCoord = new Map<string, MapPinData>();
    for (const l of mapLocations) {
      if (!l.coordinates) continue;
      const key = `${l.coordinates.lat.toFixed(4)},${l.coordinates.lng.toFixed(4)}`;
      if (byCoord.has(key)) continue;
      byCoord.set(key, {
        id: l.id,
        lat: l.coordinates.lat,
        lng: l.coordinates.lng,
        label: l.name,
        sublabel: [l.state, l.country].filter(Boolean).join(" · "),
      });
    }
    return Array.from(byCoord.values());
  }, [mapLocations]);

  const hasFilters = !!(search || filterCategory || filterStatus || filterCondition || filterWarranty);

  const clearFilters = () => {
    setSearch(""); setFilterCategory(""); setFilterStatus(""); setFilterCondition("");
    if (filterWarranty) setFilterWarranty("");
  };

  const handleSelect = (id: string) => setNavLocation(`/assets/${id}`);

  const grouped = useMemo(() => {
    if (groupBy === "None") return [{ label: "", items: assets }];
    return Object.entries(
      assets.reduce<Record<string, Asset[]>>((acc, a) => {
        const key = groupBy === "By Category" ? a.category : groupBy === "By Zone" ? a.location.zone : a.status;
        if (!acc[key]) acc[key] = [];
        acc[key].push(a);
        return acc;
      }, {})
    ).map(([label, items]) => ({ label, items }));
  }, [assets, groupBy]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        {/* View switcher */}
        <div className="flex rounded-xl border border-border overflow-hidden bg-muted/40 p-0.5 gap-0.5 shrink-0">
          {(["kanban", "list", "map"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all",
                view === v
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
              data-testid={`button-view-${v}`}
            >
              {v === "kanban" ? <LayoutGrid size={13} /> : v === "list" ? <List size={13} /> : <MapIcon size={13} />}
              <span className="capitalize">{v}</span>
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="w-px h-5 bg-border shrink-0" />

        {/* Search */}
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input
            type="search"
            placeholder="Search assets…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all w-44"
            data-testid="input-asset-search"
          />
        </div>

        {/* Filters */}
        <FilterDropdown label="Category" value={filterCategory} options={CATEGORIES} onChange={setFilterCategory} />
        <FilterDropdown label="Status" value={filterStatus} options={STATUSES} onChange={setFilterStatus} />
        <FilterDropdown label="Condition" value={filterCondition}
                        options={conditionOptions.map((o) => o.value)}
                        labelOf={conditionLabelOf}
                        onChange={setFilterCondition} />
        {/* A contract, not a condition: this filter narrows the register by
            what is recorded about a warranty and says nothing about whether
            the asset is in service. */}
        <FilterDropdown label="Warranty" value={filterWarranty}
                        allLabel="Any warranty"
                        options={WARRANTY_VIEWS}
                        labelOf={warrantyLabelOf}
                        onChange={setFilterWarranty} />

        <button
          onClick={() => setSortOrder(sortOrder === "newest" ? "oldest" : "newest")}
          title={sortOrder === "newest"
            ? "Newest first — most recently created asset at the top"
            : "Oldest first — the order the register was built in"}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-border bg-card text-foreground hover:border-primary/30 hover:shadow-sm transition-all"
          data-testid="button-sort-order"
        >
          {sortOrder === "newest" ? <ArrowDown size={13} /> : <ArrowUp size={13} />}
          {sortOrder === "newest" ? "Newest first" : "Oldest first"}
        </button>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1.5"
            data-testid="button-clear-filters"
          >
            <X size={12} /> Clear
          </button>
        )}

        {/* New asset — pushed right */}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setNavLocation("/assets/new")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
            data-testid="button-new-asset"
          >
            + New Asset
          </button>
          <SlidersHorizontal size={12} className="text-muted-foreground/60" />
          <span className="text-xs text-muted-foreground">Group:</span>
          <div className="relative">
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value)}
              className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 appearance-none pr-6 cursor-pointer"
              data-testid="select-group-by"
            >
              {GROUP_BY_OPTIONS.map((o) => <option key={o}>{o}</option>)}
            </select>
            <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground/60" />
          </div>
        </div>
      </div>

      {/* Count bar */}
      <div className="px-5 py-2 border-b border-border/50 bg-background/60 flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          <span className="font-bold text-foreground tabular-nums">{assets.length.toLocaleString()}</span> of{" "}
          <span className="font-bold text-foreground tabular-nums" data-testid="register-total">{totalEstimate.toLocaleString()}</span> assets
          {hasFilters && <span className="ml-1 text-primary/80">(filtered)</span>}
        </p>
        {hasFilters && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {filterCategory && <FilterTag label={filterCategory} onRemove={() => setFilterCategory("")} />}
            {filterStatus && <FilterTag label={filterStatus} onRemove={() => setFilterStatus("")} />}
            {filterCondition && <FilterTag label={conditionLabelOf(filterCondition)} onRemove={() => setFilterCondition("")} />}
            {filterWarranty && <FilterTag label={`Warranty: ${warrantyLabelOf(filterWarranty)}`} onRemove={() => setFilterWarranty("")} />}
          </div>
        )}
        {/* The window is NAMED, not implied. "Expiring soon" means nothing a
            person can check; two dates do. Lagos dates, because that is the
            day the server judged against — a UTC date is a day behind for an
            hour every night. */}
        {soonWindow && (
          <p className="text-[11px] text-muted-foreground" data-testid="warranty-window">
            Warranty expires within {WARRANTY_SOON_DAYS} days — between{" "}
            <span className="font-semibold text-foreground">{formatIsoDate(soonWindow.from)}</span> and{" "}
            <span className="font-semibold text-foreground">{formatIsoDate(soonWindow.to)}</span> (Lagos dates)
          </p>
        )}
      </div>

      {/* API error banner */}
      {error && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-center gap-2">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0" />
          <p className="text-[11px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{error.code}:</span> {error.message}
            {!apiConfigured && " (set VITE_API_TOKEN in .env.local)"}
          </p>
        </div>
      )}

      {/* Content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && assets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
            <p className="text-sm text-muted-foreground">Loading assets…</p>
          </div>
        ) : view === "map" ? (
          <div className="p-5 space-y-3">
            <p className="text-xs text-muted-foreground">
              <span className="font-bold text-foreground tabular-nums">{mapPins.length}</span> distinct sites
              {mapPins.length === 0 && " — loading locations…"}
            </p>
            <NigeriaMap pins={mapPins} height={520} />
          </div>
        ) : assets.length === 0 ? (
          <EmptyState onClear={clearFilters} />
        ) : (
          grouped.map(({ label, items }) => (
            <div key={label || "all"}>
              {label && (
                <div className="sticky top-0 z-10 px-5 py-2.5 bg-muted/60 backdrop-blur border-b border-border/50 flex items-center gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
                  <span className="text-[11px] font-semibold text-foreground tabular-nums">{items.length}</span>
                </div>
              )}
              {view === "kanban"
                ? <CardView assets={items} onSelect={handleSelect} />
                : <ListView assets={items} onSelect={handleSelect} />
              }
            </div>
          ))
        )}

        {hasNextPage && (
          <div ref={sentinelRef} className="flex items-center justify-center py-5">
            {isFetchingNextPage ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock size={12} className="animate-pulse" /> Loading more…
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

function FilterTag({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-primary/10 text-primary text-[10px] font-semibold">
      {label}
      <button onClick={onRemove} className="hover:text-primary/60 transition-colors ml-0.5">
        <X size={9} />
      </button>
    </span>
  );
}
