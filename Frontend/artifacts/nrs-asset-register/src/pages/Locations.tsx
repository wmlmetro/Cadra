import { useState, useEffect, useMemo } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { listLocations } from "@/lib/dataProvider";
import type { Location } from "@/types";
import {
  Globe, Building2, MapPin, Layers, DoorOpen,
  ChevronRight, ChevronDown, Search, LayoutGrid, List, Network,
  X, Package, ChevronRight as Chevron,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── ICON + TILE CONFIG ───────────────────────────────────────────────────────
type LocType = Location["locationType"];

function typeConfig(t: LocType) {
  switch (t) {
    case "Zone":   return { Icon: Globe,     tile: "bg-[var(--nrs-red-subtle)] border-red-200/60 dark:bg-red-950/30 dark:border-red-800/30",     icon: "text-[#E01F26] dark:text-red-400"   };
    case "State":  return { Icon: Building2, tile: "bg-blue-50 border-blue-100 dark:bg-blue-950/30 dark:border-blue-800/30",                      icon: "text-blue-500 dark:text-blue-400"   };
    case "Office": return { Icon: MapPin,    tile: "bg-amber-50 border-amber-100 dark:bg-amber-950/30 dark:border-amber-800/30",                  icon: "text-amber-500 dark:text-amber-400" };
    case "Floor":  return { Icon: Layers,    tile: "bg-purple-50 border-purple-100 dark:bg-purple-950/30 dark:border-purple-800/30",              icon: "text-purple-500 dark:text-purple-400"};
    default:       return { Icon: DoorOpen,  tile: "bg-muted border-border",                                                                      icon: "text-muted-foreground"              };
  }
}

function TypeIcon({ type, size = 14 }: { type: LocType; size?: number }) {
  const { Icon, icon } = typeConfig(type);
  return <Icon size={size} className={icon} />;
}

// ─── PARENT PATH ─────────────────────────────────────────────────────────────
function buildParentPath(loc: Location, all: Location[]): string {
  if (!loc.parent) return "";
  const parent = all.find(l => l.id === loc.parent);
  if (!parent) return "";
  if (!parent.parent) return parent.name;
  const gp = all.find(l => l.id === parent.parent);
  return gp ? `${gp.name} / ${parent.name}` : parent.name;
}

// ─── LOCATION CARD ────────────────────────────────────────────────────────────
function LocationCard({ loc, allLocations, onClick }: { loc: Location; allLocations: Location[]; onClick: () => void }) {
  const cfg = typeConfig(loc.locationType);
  const parentPath = buildParentPath(loc, allLocations);
  const isZone  = loc.locationType === "Zone";
  const isState = loc.locationType === "State";

  return (
    <div
      onClick={onClick}
      className="bg-card border border-border rounded-2xl p-4 cursor-pointer group hover:shadow-md hover:-translate-y-0.5 hover:border-primary/20 transition-all duration-150 flex flex-col gap-3"
      style={{ boxShadow: "0 1px 2px rgba(16,24,40,.04)" }}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-2">
        <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border", cfg.tile)}>
          <cfg.Icon size={17} className={cfg.icon} />
        </div>
        {/* Active pill */}
        <span className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-semibold shrink-0",
          loc.active ? "bg-green-50 border border-green-200/60 text-green-700 dark:bg-green-950/30 dark:border-green-800/30 dark:text-green-400"
                     : "bg-muted border border-border text-muted-foreground"
        )}>
          <span className={cn("w-1.5 h-1.5 rounded-full", loc.active ? "bg-green-500" : "bg-gray-400")} />
          {loc.active ? "Active" : "Inactive"}
        </span>
      </div>

      {/* Name */}
      <div>
        <p className="font-bold text-[13px] text-foreground leading-snug group-hover:text-primary transition-colors">{loc.name}</p>
        {/* Type + zone code pills */}
        <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
          {loc.locationType && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border/60">
              {loc.locationType}
            </span>
          )}
          {loc.zoneCode && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border/60 font-mono">
              {loc.zoneCode}
            </span>
          )}
        </div>
      </div>

      {/* Parent path */}
      {parentPath && (
        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <ChevronRight size={10} className="text-muted-foreground/50 shrink-0" />
          <span className="truncate">{parentPath}</span>
        </div>
      )}

      {/* Address */}
      {(loc.street || loc.city) && (
        <p className="text-[11px] text-muted-foreground/70 truncate">
          {[loc.street, loc.city].filter(Boolean).join(" · ")}
        </p>
      )}

      {/* Zone structural counts */}
      {isZone && (loc.childStates || loc.childOffices) && (
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          {loc.childStates  && <span className="flex items-center gap-1"><Building2 size={10} />{loc.childStates} state{loc.childStates !== 1 ? "s" : ""}</span>}
          {loc.childOffices && <span className="flex items-center gap-1"><MapPin size={10} />{loc.childOffices} office{loc.childOffices !== 1 ? "s" : ""}</span>}
        </div>
      )}
      {isState && loc.childOffices && (
        <p className="text-[11px] text-muted-foreground flex items-center gap-1">
          <MapPin size={10} />{loc.childOffices} office{loc.childOffices !== 1 ? "s" : ""}
        </p>
      )}

      {/* Footer */}
      <div className="pt-2.5 border-t border-border/60 flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-muted-foreground bg-muted/60 border border-border/40 px-2 py-0.5 rounded-lg">
          <Package size={10} />
          {(loc.assetCount ?? 0).toLocaleString()} asset{(loc.assetCount ?? 0) !== 1 ? "s" : ""}
        </span>
        <Chevron size={13} className="text-muted-foreground/40 group-hover:text-primary/60 group-hover:translate-x-0.5 transition-all" />
      </div>
    </div>
  );
}

// ─── TREE NODE ────────────────────────────────────────────────────────────────
function TreeNode({ location, children, depth, onSelect, selectedId }: {
  location: Location; children: Location[]; depth: number;
  onSelect: (l: Location) => void; selectedId: string | null;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = children.length > 0;
  const isSelected = selectedId === location.id;

  return (
    <div>
      <div
        className={cn("flex items-center gap-2 py-1.5 px-2 rounded-xl cursor-pointer transition-colors group", isSelected ? "bg-primary/10 text-primary" : "hover:bg-accent")}
        style={{ paddingLeft: `${(depth * 16) + 8}px` }}
        onClick={() => { onSelect(location); if (hasChildren) setOpen(!open); }}
      >
        {hasChildren
          ? <button className="shrink-0 text-muted-foreground" onClick={e => { e.stopPropagation(); setOpen(!open); }}>{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</button>
          : <span className="w-3 shrink-0" />
        }
        <TypeIcon type={location.locationType} size={13} />
        <span className="flex-1 text-[13px] text-foreground truncate font-medium">{location.name}</span>
        {location.locationType && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">{location.locationType}</span>
        )}
        {(location.childrenCount ?? 0) > 0 && (
          <span className="text-[10px] text-muted-foreground shrink-0">{location.childrenCount}</span>
        )}
      </div>
      {open && hasChildren && (
        <div>{children.map(child => (
          <TreeNode key={child.id} location={child} children={[]} depth={depth + 1} onSelect={onSelect} selectedId={selectedId} />
        ))}</div>
      )}
    </div>
  );
}

// ─── DETAIL PANEL ────────────────────────────────────────────────────────────
function DetailPanel({ loc, allLocations }: { loc: Location; allLocations: Location[] }) {
  const parentPath = buildParentPath(loc, allLocations);
  const cfg = typeConfig(loc.locationType);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center border", cfg.tile)}>
          <cfg.Icon size={18} className={cfg.icon} />
        </div>
        <div>
          <h2 className="text-[15px] font-bold text-foreground">{loc.name}</h2>
          {parentPath && <p className="text-[11px] text-muted-foreground mt-0.5">{parentPath}</p>}
        </div>
      </div>

      <dl className="bg-card border border-border rounded-xl overflow-hidden">
        {[
          ["Zone Code",     loc.zoneCode],
          ["Type",          loc.locationType],
          ["Street",        loc.street],
          ["City",          loc.city],
          ["State",         loc.state],
          ["Country",       loc.country],
          ["Assets",        loc.assetCount != null ? `${loc.assetCount.toLocaleString()} assets` : null],
          ["Offices",       loc.childOffices != null ? `${loc.childOffices} offices` : null],
          ["Child States",  loc.childStates  != null ? `${loc.childStates} states`  : null],
          ["Status",        loc.active ? "Active" : "Inactive"],
        ].filter(([, v]) => v != null).map(([k, v]) => (
          <div key={k as string} className="flex items-center px-4 py-2.5 border-b border-border/60 last:border-0">
            <dt className="text-[11px] font-semibold text-muted-foreground w-32 uppercase tracking-wide shrink-0">{k}</dt>
            <dd className={cn("text-[13px] font-medium", k === "Status" ? (loc.active ? "text-green-600 dark:text-green-400" : "text-muted-foreground") : "text-foreground")}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ─── FILTER BUTTON ────────────────────────────────────────────────────────────
function FilterBtn({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-all", value ? "bg-primary text-white border-primary shadow-sm" : "border-border text-muted-foreground hover:text-foreground bg-card")}>
        {value || label}<ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && <>
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
        <div className="absolute top-full mt-1.5 left-0 z-50 bg-popover border border-border rounded-xl shadow-lg overflow-hidden min-w-[150px] py-1">
          <button className="w-full text-left px-3 py-2 text-xs hover:bg-accent" onClick={() => { onChange(""); setOpen(false); }}>All</button>
          {options.map(o => <button key={o} className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", value === o ? "font-semibold text-primary" : "text-muted-foreground")} onClick={() => { onChange(o); setOpen(false); }}>{o}</button>)}
        </div>
      </>}
    </div>
  );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
type View    = "tree" | "cards" | "list";
type GroupBy = "zone" | "type";

export default function Locations() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [view, setView] = useState<View>("cards");
  const [groupBy, setGroupBy] = useState<GroupBy>("zone");
  const [selected, setSelected] = useState<Location | null>(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterZone, setFilterZone] = useState("");
  const [filterActive, setFilterActive] = useState("");

  useEffect(() => {
    setTitle("Locations");
    setSearchHandler(q => setSearch(q));
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const allLocations = listLocations();

  // parent→children map
  const childrenOf = useMemo(() => {
    const map: Record<string, Location[]> = {};
    for (const loc of allLocations) {
      if (loc.parent) {
        if (!map[loc.parent]) map[loc.parent] = [];
        map[loc.parent].push(loc);
      }
    }
    return map;
  }, [allLocations]);

  const roots = useMemo(() => allLocations.filter(l => !l.parent), [allLocations]);

  // Zone name lookup for non-zone items
  const zoneNameFor = useMemo(() => {
    const map: Record<string, string> = {};
    for (const loc of allLocations) {
      if (loc.locationType === "Zone") map[loc.id] = loc.name;
    }
    // For states/offices, traverse up to zone
    function getZone(l: Location): string {
      if (!l.parent) return l.name;
      const parent = allLocations.find(x => x.id === l.parent);
      return parent ? getZone(parent) : "";
    }
    for (const loc of allLocations) {
      if (loc.locationType !== "Zone") map[loc.id] = getZone(loc);
    }
    return map;
  }, [allLocations]);

  // Filtered for cards/list
  const filtered = useMemo(() => {
    let r = allLocations;
    if (filterType) r = r.filter(l => l.locationType === filterType);
    if (filterZone) r = r.filter(l => l.locationType === "Zone" ? l.name === filterZone : zoneNameFor[l.id] === filterZone);
    if (filterActive === "Active")   r = r.filter(l =>  l.active);
    if (filterActive === "Inactive") r = r.filter(l => !l.active);
    if (search) {
      const q = search.toLowerCase();
      r = r.filter(l => l.name.toLowerCase().includes(q) || (l.city ?? "").toLowerCase().includes(q) || (l.state ?? "").toLowerCase().includes(q));
    }
    return r;
  }, [allLocations, filterType, filterZone, filterActive, search, zoneNameFor]);

  const zones = useMemo(() => allLocations.filter(l => l.locationType === "Zone"), [allLocations]);
  const zoneNames = zones.map(z => z.name);
  const hasFilter = !!(search || filterType || filterZone || filterActive);
  const clear = () => { setSearch(""); setFilterType(""); setFilterZone(""); setFilterActive(""); };

  // KPI totals
  const kpi = useMemo(() => ({
    zones:   allLocations.filter(l => l.locationType === "Zone").length,
    states:  allLocations.filter(l => l.locationType === "State").length,
    offices: allLocations.filter(l => l.locationType === "Office").length,
    assets:  allLocations.filter(l => l.locationType === "Zone").reduce((s, z) => s + (z.assetCount ?? 0), 0),
  }), [allLocations]);

  const VIEWS: { id: View; icon: typeof LayoutGrid; label: string }[] = [
    { id: "tree",  icon: Network,    label: "Tree"  },
    { id: "cards", icon: LayoutGrid, label: "Cards" },
    { id: "list",  icon: List,       label: "List"  },
  ];

  // ── CARDS grouped by zone ─────────────────────────────────────────────────
  const cardsByZone = useMemo(() => {
    if (groupBy !== "zone") return null;
    return zones.map(zone => {
      const items = filtered.filter(l => l.id !== zone.id && zoneNameFor[l.id] === zone.name);
      const showZone = filtered.some(l => l.id === zone.id);
      if (!showZone && items.length === 0) return null;
      return { zone, items: showZone ? [zone, ...items] : items };
    }).filter(Boolean) as { zone: Location; items: Location[] }[];
  }, [filtered, zones, groupBy, zoneNameFor]);

  const cardsByType = useMemo(() => {
    if (groupBy !== "type") return null;
    const types: LocType[] = ["Zone", "State", "Office", "Floor", "Room"];
    return types.map(t => {
      const items = filtered.filter(l => l.locationType === t);
      return items.length ? { type: t, items } : null;
    }).filter(Boolean) as { type: LocType; items: Location[] }[];
  }, [filtered, groupBy]);

  return (
    <div className="flex flex-col h-full">
      {/* KPI strip */}
      <div className="px-5 py-3 border-b border-border bg-card grid grid-cols-4 gap-3">
        {[
          { label: "Zones",      value: kpi.zones,   icon: Globe,     color: "text-[#E01F26]"                          },
          { label: "States",     value: kpi.states,  icon: Building2, color: "text-blue-600 dark:text-blue-400"        },
          { label: "Offices",    value: kpi.offices, icon: MapPin,    color: "text-amber-600 dark:text-amber-400"      },
          { label: "Total Assets",value: kpi.assets.toLocaleString(), icon: Package, color: "text-muted-foreground"   },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-background border border-border/50">
            <s.icon size={14} className={s.color} />
            <div>
              <p className={cn("text-[18px] font-extrabold leading-none tabular-nums", s.color)}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        {/* View toggle */}
        <div className="flex rounded-xl border border-border bg-muted/40 p-0.5 gap-0.5 shrink-0">
          {VIEWS.map(v => (
            <button key={v.id} onClick={() => setView(v.id)} className={cn("flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg transition-all", view === v.id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
              <v.icon size={12} />{v.label}
            </button>
          ))}
        </div>

        {/* Group by (cards only) */}
        {view === "cards" && (
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Group:</span>
            {(["zone", "type"] as const).map(g => (
              <button key={g} onClick={() => setGroupBy(g)} className={cn("px-2.5 py-1.5 text-[11px] font-medium rounded-lg border transition-all capitalize", groupBy === g ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:text-foreground bg-card")}>{g}</button>
            ))}
          </div>
        )}

        <div className="w-px h-5 bg-border shrink-0" />

        <div className="relative">
          <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input type="search" placeholder="Search locations…" value={search} onChange={e => setSearch(e.target.value)}
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 w-44" />
        </div>

        <FilterBtn label="Type"   value={filterType}   options={["Zone", "State", "Office"]} onChange={setFilterType}   />
        <FilterBtn label="Zone"   value={filterZone}   options={zoneNames}                   onChange={setFilterZone}   />
        <FilterBtn label="Status" value={filterActive} options={["Active", "Inactive"]}      onChange={setFilterActive} />
        {hasFilter && <button onClick={clear} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5"><X size={12} /> Clear</button>}
        <p className="ml-auto text-xs text-muted-foreground"><span className="font-bold text-foreground">{filtered.length}</span> locations</p>
      </div>

      {/* ── BODY ────────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden flex">

        {/* TREE VIEW */}
        {view === "tree" && (
          <>
            <div className="w-72 border-r border-border overflow-y-auto p-3 shrink-0">
              {roots.map(root => (
                <TreeNode key={root.id} location={root} children={childrenOf[root.id] ?? []} depth={0} onSelect={setSelected} selectedId={selected?.id ?? null} />
              ))}
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {selected
                ? <div className="max-w-lg"><DetailPanel loc={selected} allLocations={allLocations} /></div>
                : (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
                    <Globe size={32} className="opacity-30" />
                    <p className="text-sm font-medium">Select a location to view details</p>
                  </div>
                )
              }
            </div>
          </>
        )}

        {/* CARDS VIEW */}
        {view === "cards" && (
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {groupBy === "zone" && cardsByZone && cardsByZone.map(({ zone, items }) => (
              <div key={zone.id}>
                <div className="flex items-center gap-2.5 mb-3">
                  <Globe size={13} className="text-[#E01F26]" />
                  <h3 className="text-[12px] font-extrabold text-foreground uppercase tracking-wide">{zone.name}</h3>
                  <span className="text-[11px] font-semibold text-muted-foreground">{zone.zoneCode}</span>
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-[11px] text-muted-foreground">{items.length} location{items.length !== 1 ? "s" : ""}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "12px" }}>
                  {items.map(loc => (
                    <LocationCard key={loc.id} loc={loc} allLocations={allLocations}
                      onClick={() => { setSelected(loc); if (window.innerWidth < 1024) setView("tree"); }} />
                  ))}
                </div>
              </div>
            ))}

            {groupBy === "type" && cardsByType && cardsByType.map(({ type, items }) => (
              <div key={type as string}>
                <div className="flex items-center gap-2.5 mb-3">
                  <TypeIcon type={type} size={12} />
                  <h3 className="text-[12px] font-extrabold text-foreground uppercase tracking-wide">{type}s</h3>
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-[11px] text-muted-foreground">{items.length}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "12px" }}>
                  {items.map(loc => (
                    <LocationCard key={loc.id} loc={loc} allLocations={allLocations} onClick={() => setSelected(loc)} />
                  ))}
                </div>
              </div>
            ))}

            {filtered.length === 0 && (
              <div className="flex flex-col items-center justify-center py-24 gap-3">
                <Globe size={28} className="text-muted-foreground/30" />
                <p className="text-sm font-semibold">No locations match your filters</p>
                <button onClick={clear} className="text-xs text-primary hover:opacity-80">Clear filters</button>
              </div>
            )}
          </div>
        )}

        {/* LIST VIEW */}
        {view === "list" && (
          <div className="flex-1 overflow-auto">
            <table className="w-full min-w-[800px]">
              <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                <tr>
                  {["Name", "Type", "Zone / State", "City", "Assets", "Status"].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(loc => (
                  <tr key={loc.id} onClick={() => { setSelected(loc); setView("tree"); }} className="border-b border-border/50 cursor-pointer hover:bg-muted/20 transition-colors group">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center border shrink-0", typeConfig(loc.locationType).tile)}>
                          <TypeIcon type={loc.locationType} size={12} />
                        </div>
                        <span className="text-[12px] font-semibold text-foreground group-hover:text-primary transition-colors">{loc.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3"><span className="text-[11px] text-muted-foreground">{loc.locationType ?? "—"}</span></td>
                    <td className="px-4 py-3"><span className="text-[12px] text-muted-foreground">{zoneNameFor[loc.id] || "—"}</span></td>
                    <td className="px-4 py-3"><span className="text-[12px] text-muted-foreground">{loc.city ?? "—"}</span></td>
                    <td className="px-4 py-3">
                      {loc.assetCount != null
                        ? <span className="text-[12px] font-semibold text-foreground">{loc.assetCount.toLocaleString()}</span>
                        : <span className="text-muted-foreground">—</span>
                      }
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg", loc.active ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400" : "bg-muted text-muted-foreground")}>
                        {loc.active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 gap-2">
                <Globe size={24} className="text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">No locations found</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
