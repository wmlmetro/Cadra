import { useState, useEffect, useMemo } from "react";
import { useLocation } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { listAssets } from "@/lib/dataProvider";
import type { Asset } from "@/types";
import StatusPill from "@/components/StatusPill";
import ConditionBadge from "@/components/ConditionBadge";
import {
  Monitor, Car, Sofa, MapPin, User, Search, X,
  LayoutGrid, List, Map, SlidersHorizontal, ChevronDown,
} from "lucide-react";
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  flexRender, type SortingState, type ColumnDef,
} from "@tanstack/react-table";
import { cn } from "@/lib/utils";

const CATEGORIES = ["IT Equipment", "Fleet / Vehicles", "Furniture & Fittings"] as const;
const STATUSES = [
  "Cleared",
  "Review — data quality",
  "Review — allottee not in nominal roll",
  "Review — VIN not verifiable",
  "Review — possible duplicate",
] as const;
const CONDITIONS = ["Good", "Fair", "Poor", "Faulty"] as const;
const GROUP_BY_OPTIONS = ["None", "By Category", "By Zone", "By Status"] as const;

function CategoryIcon({ category, size = 18 }: { category: Asset["category"]; size?: number }) {
  if (category === "IT Equipment") return <Monitor size={size} className="text-blue-500" />;
  if (category === "Fleet / Vehicles") return <Car size={size} className="text-emerald-500" />;
  return <Sofa size={size} className="text-amber-500" />;
}

function CardView({ assets, onSelect }: { assets: Asset[]; onSelect: (id: string) => void }) {
  return (
    <div
      className="p-5"
      style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem" }}
    >
      {assets.map((asset) => (
        <div
          key={asset.id}
          className="bg-card border border-card-border rounded-xl overflow-hidden cursor-pointer transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md"
          onClick={() => onSelect(asset.id)}
          data-testid={`card-asset-${asset.id}`}
        >
          {/* Card header */}
          <div className={cn(
            "h-16 flex items-center justify-center",
            asset.category === "IT Equipment" ? "bg-blue-50 dark:bg-blue-950/40" :
            asset.category === "Fleet / Vehicles" ? "bg-emerald-50 dark:bg-emerald-950/40" :
            "bg-amber-50 dark:bg-amber-950/40"
          )}>
            <CategoryIcon category={asset.category} size={28} />
          </div>

          {/* Card body */}
          <div className="p-3 space-y-2">
            <div>
              <p className="text-xs font-semibold text-foreground leading-snug line-clamp-2">{asset.name}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">
                {asset.assetTag || asset.legacyCode}
              </p>
            </div>

            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <User size={10} className="shrink-0" />
              <span className="truncate">
                {asset.custodianName ?? `Pool · ${asset.department}`}
              </span>
            </div>

            <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground">
              <MapPin size={10} className="shrink-0 mt-px" />
              <span className="line-clamp-1">{asset.location.office}, {asset.location.state}</span>
            </div>

            <div className="pt-1">
              <StatusPill status={asset.status} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ListView({ assets, onSelect }: { assets: Asset[]; onSelect: (id: string) => void }) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo<ColumnDef<Asset>[]>(() => [
    {
      accessorKey: "name",
      header: "Asset Name",
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-foreground text-xs">{row.original.name}</p>
          <p className="text-[10px] text-muted-foreground font-mono">{row.original.assetTag || row.original.legacyCode}</p>
        </div>
      ),
    },
    { accessorKey: "category", header: "Category", cell: ({ getValue }) => <span className="text-xs text-foreground">{getValue() as string}</span> },
    { accessorKey: "subcategory", header: "Subcategory", cell: ({ getValue }) => <span className="text-xs text-muted-foreground">{getValue() as string}</span> },
    {
      accessorKey: "custodianName",
      header: "Custodian",
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.custodianName ?? `Pool · ${row.original.department}`}</span>,
    },
    {
      accessorKey: "location",
      header: "Location",
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.location.office}</span>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusPill status={row.original.status} />,
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
      <table className="w-full text-sm" data-testid="table-asset-list">
        <thead className="sticky top-0 bg-card z-10 border-b border-border">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <span className="flex items-center gap-1">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
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
              className={cn(
                "border-b border-border cursor-pointer transition-colors hover:bg-accent/50",
                i % 2 === 0 ? "bg-background/40" : ""
              )}
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

export default function AssetRegister() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, setLocation] = useLocation();

  const [view, setView] = useState<"kanban" | "list" | "map">("kanban");
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCondition, setFilterCondition] = useState("");
  const [groupBy, setGroupBy] = useState("None");

  useEffect(() => {
    setTitle("Asset Register");
    setSearchHandler((q) => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const assets = useMemo(() =>
    listAssets({
      category: filterCategory || undefined,
      status: filterStatus || undefined,
      condition: filterCondition || undefined,
      search: search || undefined,
    }),
    [search, filterCategory, filterStatus, filterCondition]
  );

  const hasFilters = !!(search || filterCategory || filterStatus || filterCondition);

  const clearFilters = () => {
    setSearch(""); setFilterCategory(""); setFilterStatus(""); setFilterCondition("");
  };

  const handleSelect = (id: string) => setLocation(`/assets/${id}`);

  // Grouping logic
  const grouped = useMemo(() => {
    if (groupBy === "None") return [{ label: "", items: assets }];
    return Object.entries(
      assets.reduce<Record<string, Asset[]>>((acc, a) => {
        const key =
          groupBy === "By Category" ? a.category :
          groupBy === "By Zone" ? a.location.zone :
          a.status;
        if (!acc[key]) acc[key] = [];
        acc[key].push(a);
        return acc;
      }, {})
    ).map(([label, items]) => ({ label, items }));
  }, [assets, groupBy]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-3">
        {/* View switcher */}
        <div className="flex rounded-lg border border-border overflow-hidden shrink-0">
          {(["kanban", "list", "map"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                view === v ? "bg-primary text-white" : "text-muted-foreground hover:bg-accent"
              )}
              data-testid={`button-view-${v}`}
            >
              {v === "kanban" ? <LayoutGrid size={13} /> : v === "list" ? <List size={13} /> : <Map size={13} />}
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="search"
            placeholder="Search assets…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-lg bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring w-44"
            data-testid="input-asset-search"
          />
        </div>

        {/* Filter chips */}
        <FilterChip
          label="Category"
          value={filterCategory}
          options={["", ...CATEGORIES]}
          onChange={setFilterCategory}
        />
        <FilterChip
          label="Status"
          value={filterStatus}
          options={["", ...STATUSES]}
          onChange={setFilterStatus}
        />
        <FilterChip
          label="Condition"
          value={filterCondition}
          options={["", ...CONDITIONS]}
          onChange={setFilterCondition}
        />

        {/* Group by */}
        <div className="ml-auto flex items-center gap-2">
          <SlidersHorizontal size={13} className="text-muted-foreground" />
          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
            className="text-xs border border-border rounded-lg px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            data-testid="select-group-by"
          >
            {GROUP_BY_OPTIONS.map((o) => <option key={o}>{o}</option>)}
          </select>
        </div>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-clear-filters"
          >
            <X size={12} /> Clear
          </button>
        )}
      </div>

      {/* Count bar */}
      <div className="px-5 py-2 border-b border-border bg-background flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{assets.length.toLocaleString()}</span> assets
          {hasFilters && " (filtered)"}
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {view === "map" ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
            <div className="text-center space-y-2">
              <Map size={32} className="mx-auto opacity-40" />
              <p>Map view coming soon</p>
            </div>
          </div>
        ) : (
          grouped.map(({ label, items }) => (
            <div key={label || "all"}>
              {label && (
                <div className="px-5 py-2 bg-muted/40 border-b border-border">
                  <p className="text-xs font-semibold text-muted-foreground">{label} <span className="text-foreground">({items.length})</span></p>
                </div>
              )}
              {view === "kanban"
                ? <CardView assets={items} onSelect={handleSelect} />
                : <ListView assets={items} onSelect={handleSelect} />
              }
            </div>
          ))
        )}
        {assets.length === 0 && (
          <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
            <div className="text-center space-y-2">
              <Search size={32} className="mx-auto opacity-40" />
              <p>No assets match your filters</p>
              {hasFilters && (
                <button onClick={clearFilters} className="text-primary text-xs hover:underline">Clear filters</button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterChip({
  label, value, options, onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "appearance-none text-xs border rounded-lg pl-2.5 pr-6 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring cursor-pointer transition-colors",
          value
            ? "border-primary text-primary font-medium"
            : "border-border text-muted-foreground"
        )}
        data-testid={`filter-${label.toLowerCase()}`}
      >
        <option value="">{label}</option>
        {options.filter(Boolean).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground" />
    </div>
  );
}
