import { useState, useEffect, useMemo } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { listLocations, listAssets } from "@/lib/dataProvider";
import type { Location } from "@/types";
import { Globe, Building2, DoorOpen, Layers, Plus, ChevronRight, ChevronDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";

function LocationIcon({ type }: { type?: Location["locationType"] }) {
  if (type === "Zone") return <Globe size={14} className="text-blue-500" />;
  if (type === "State") return <Building2 size={14} className="text-emerald-500" />;
  if (type === "Office") return <DoorOpen size={14} className="text-amber-500" />;
  return <Layers size={14} className="text-purple-500" />;
}

function TreeNode({
  location,
  children,
  depth,
  onSelect,
  selectedId,
}: {
  location: Location;
  children: Location[];
  depth: number;
  onSelect: (l: Location) => void;
  selectedId: string | null;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = children.length > 0;
  const isSelected = selectedId === location.id;

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-2 py-1.5 px-2 rounded-lg cursor-pointer transition-colors group",
          isSelected ? "bg-primary/10 text-primary" : "hover:bg-accent"
        )}
        style={{ paddingLeft: `${(depth * 16) + 8}px` }}
        onClick={() => { onSelect(location); if (hasChildren) setOpen(!open); }}
        data-testid={`tree-node-${location.id}`}
      >
        {hasChildren ? (
          <button
            className="shrink-0 text-muted-foreground"
            onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}

        <LocationIcon type={location.locationType} />

        <span className="flex-1 text-sm text-foreground truncate font-medium">{location.name}</span>

        {location.locationType && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">{location.locationType}</span>
        )}

        {(location.childrenCount ?? 0) > 0 && (
          <span className="text-[10px] text-muted-foreground shrink-0">{location.childrenCount}</span>
        )}
      </div>

      {open && hasChildren && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              location={child}
              children={[]}
              depth={depth + 1}
              onSelect={onSelect}
              selectedId={selectedId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Locations() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [view, setView] = useState<"tree" | "list">("tree");
  const [selected, setSelected] = useState<Location | null>(null);
  const [search, setSearch] = useState("");

  const locations = listLocations();
  const allAssets = listAssets();

  useEffect(() => {
    setTitle("Locations");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // Build parent→children map
  const childrenOf = useMemo(() => {
    const map: Record<string, Location[]> = {};
    for (const loc of locations) {
      if (loc.parent) {
        if (!map[loc.parent]) map[loc.parent] = [];
        map[loc.parent].push(loc);
      }
    }
    return map;
  }, [locations]);

  const roots = useMemo(() => locations.filter((l) => !l.parent), [locations]);

  const filteredLocations = useMemo(() => {
    if (!search) return locations;
    const q = search.toLowerCase();
    return locations.filter(
      (l) =>
        l.name.toLowerCase().includes(q) ||
        (l.city ?? "").toLowerCase().includes(q) ||
        (l.state ?? "").toLowerCase().includes(q)
    );
  }, [locations, search]);

  // Count assets for a location
  const assetCountForLocation = (locName: string) =>
    allAssets.filter((a) => a.location.office === locName || a.location.state === locName || a.location.zone === locName).length;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex items-center gap-3">
        <div className="flex rounded-lg border border-border overflow-hidden shrink-0">
          {(["tree", "list"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "px-4 py-1.5 text-xs font-medium transition-colors",
                view === v ? "bg-primary text-white" : "text-muted-foreground hover:bg-accent"
              )}
              data-testid={`button-view-${v}`}
            >
              {v === "tree" ? "Tree" : "List"}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="search"
            placeholder="Search locations…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); if (view === "tree") setView("list"); }}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-lg bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring w-48"
            data-testid="input-location-search"
          />
        </div>

        <div className="ml-auto">
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors hover:opacity-90"
            style={{ background: "hsl(var(--primary))" }}
            data-testid="button-create-location"
            onClick={() => console.log("Create location")}
          >
            <Plus size={12} /> Create Location
          </button>
        </div>
      </div>

      {/* Body: two-pane for tree, table for list */}
      <div className="flex-1 overflow-hidden flex">
        {view === "tree" ? (
          <>
            {/* Tree */}
            <div className="w-80 border-r border-border overflow-y-auto p-3">
              {roots.map((root) => (
                <TreeNode
                  key={root.id}
                  location={root}
                  children={childrenOf[root.id] ?? []}
                  depth={0}
                  onSelect={setSelected}
                  selectedId={selected?.id ?? null}
                />
              ))}
            </div>

            {/* Detail panel */}
            <div className="flex-1 overflow-y-auto p-6">
              {selected ? (
                <div className="max-w-lg space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center">
                      <LocationIcon type={selected.locationType} />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">{selected.name}</h2>
                      {selected.locationType && (
                        <p className="text-xs text-muted-foreground">{selected.locationType}</p>
                      )}
                    </div>
                  </div>

                  <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                    {selected.zoneCode && (
                      <div className="flex py-2.5 border-b border-border">
                        <dt className="text-xs font-medium text-muted-foreground w-36">Zone Code</dt>
                        <dd className="text-xs text-foreground font-mono">{selected.zoneCode}</dd>
                      </div>
                    )}
                    {selected.parent && (
                      <div className="flex py-2.5 border-b border-border">
                        <dt className="text-xs font-medium text-muted-foreground w-36">Parent</dt>
                        <dd className="text-xs text-foreground">{selected.parent}</dd>
                      </div>
                    )}
                    {selected.street && (
                      <div className="flex py-2.5 border-b border-border">
                        <dt className="text-xs font-medium text-muted-foreground w-36">Street</dt>
                        <dd className="text-xs text-foreground">{selected.street}</dd>
                      </div>
                    )}
                    {selected.city && (
                      <div className="flex py-2.5 border-b border-border">
                        <dt className="text-xs font-medium text-muted-foreground w-36">City</dt>
                        <dd className="text-xs text-foreground">{selected.city}</dd>
                      </div>
                    )}
                    {selected.state && (
                      <div className="flex py-2.5 border-b border-border">
                        <dt className="text-xs font-medium text-muted-foreground w-36">State</dt>
                        <dd className="text-xs text-foreground">{selected.state}</dd>
                      </div>
                    )}
                    <div className="flex py-2.5 border-b border-border">
                      <dt className="text-xs font-medium text-muted-foreground w-36">Country</dt>
                      <dd className="text-xs text-foreground">{selected.country}</dd>
                    </div>
                    <div className="flex py-2.5 border-b border-border">
                      <dt className="text-xs font-medium text-muted-foreground w-36">Status</dt>
                      <dd>
                        <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", selected.active ? "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300" : "bg-muted text-muted-foreground")}>
                          {selected.active ? "Active" : "Inactive"}
                        </span>
                      </dd>
                    </div>
                    <div className="flex py-2.5">
                      <dt className="text-xs font-medium text-muted-foreground w-36">Assets</dt>
                      <dd className="text-xs text-foreground font-semibold">{assetCountForLocation(selected.name)}</dd>
                    </div>
                  </dl>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-center">
                  <div className="space-y-2">
                    <Globe size={32} className="mx-auto text-muted-foreground/40" />
                    <p className="text-sm text-muted-foreground">Select a location to view details</p>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm" data-testid="table-location-list">
              <thead className="sticky top-0 bg-card border-b border-border z-10">
                <tr>
                  {["Name", "Type", "Zone Code", "Parent", "Street", "City", "State", "Country", "Active"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredLocations.map((loc, i) => (
                  <tr
                    key={loc.id}
                    className={cn("border-b border-border cursor-pointer hover:bg-accent/40 transition-colors", i % 2 === 0 ? "bg-background/40" : "")}
                    onClick={() => { setSelected(loc); setView("tree"); }}
                    data-testid={`row-location-${loc.id}`}
                  >
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <LocationIcon type={loc.locationType} />
                        <span className="font-medium text-xs text-foreground">{loc.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.locationType ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground">{loc.zoneCode ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.parent ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.street ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.city ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.state ?? "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{loc.country}</td>
                    <td className="px-4 py-2.5">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-medium", loc.active ? "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300" : "bg-muted text-muted-foreground")}>
                        {loc.active ? "Active" : "Inactive"}
                      </span>
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
