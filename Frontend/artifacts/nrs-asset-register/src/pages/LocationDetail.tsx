import { useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import RecordLink from "@/components/RecordLink";
import {
  fetchLocation, fetchLocationAncestors, fetchLocationDescendantsPage,
  type LocationsPageMeta,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import type { Location } from "@/types";
import {
  ArrowLeft, MapPin, Edit3, AlertCircle, Clock, ChevronRight, Globe,
} from "lucide-react";

export default function LocationDetail() {
  const { id } = useParams<{ id: string }>();
  const [, nav] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();

  const { data: loc, isLoading, error } = useQuery<Location | null, CadraApiError>({
    queryKey: ["location", id],
    queryFn: () => fetchLocation(id ?? ""),
    enabled: !!id,
    staleTime: 60_000,
  });

  const { data: ancestors = [] } = useQuery<Location[]>({
    queryKey: ["location-ancestors", id],
    queryFn: () => fetchLocationAncestors(id ?? ""),
    enabled: !!id,
    staleTime: 5 * 60_000,
  });

  const desc = useInfiniteQuery<LocationsPageMeta>({
    queryKey: ["location-descendants", id],
    queryFn: ({ pageParam }) => fetchLocationDescendantsPage(id ?? "", pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: !!id,
    staleTime: 60_000,
  });

  useEffect(() => {
    setTitle(loc?.name ?? "Location");
    setSearchHandler(undefined);
  }, [loc, setTitle, setSearchHandler]);

  if (isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading location…</p>
    </div>
  );
  if (error) return (
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
  if (!loc) return <div className="p-8 text-center text-muted-foreground">Location not found.</div>;

  const descendants = (desc.data?.pages ?? []).flatMap(p => p.locations);
  const totalDesc = desc.data?.pages[0]?.totalEstimate ?? descendants.length;
  const pin: MapPinData[] = loc.coordinates
    ? [{ id: loc.id, lat: loc.coordinates.lat, lng: loc.coordinates.lng, label: loc.name }]
    : [];

  return (
    <div className="max-w-4xl mx-auto px-5 py-5 space-y-5">
      <button onClick={() => nav("/locations")} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft size={13} /> Back to locations
      </button>

      {/* Breadcrumb (ancestors) */}
      {ancestors.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap text-[12px]">
          <Globe size={11} className="text-muted-foreground/60" />
          {ancestors.map((a) => (
            <span key={a.id} className="inline-flex items-center gap-1">
              <RecordLink to={`/locations/${a.id}`}>{a.name}</RecordLink>
              <ChevronRight size={10} className="text-muted-foreground/40" />
            </span>
          ))}
          <span className="text-foreground font-semibold">{loc.name}</span>
        </div>
      )}

      {/* Hero */}
      <div className="bg-card border border-border rounded-2xl p-6 flex items-start gap-5">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center bg-primary/10 shrink-0">
          <MapPin size={20} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-[20px] font-extrabold text-foreground leading-tight">{loc.name}</h1>
              <p className="text-[12px] text-muted-foreground mt-1">
                {loc.locationType ?? "Location"}
                {loc.zoneCode && <span className="ml-2 font-mono">{loc.zoneCode}</span>}
              </p>
            </div>
            <button
              onClick={() => nav(`/locations/${id}/edit`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium hover:bg-accent"
            >
              <Edit3 size={12} /> Edit
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-[12px]">
            {loc.street && <div><span className="text-muted-foreground">Street: </span>{loc.street}</div>}
            {loc.street2 && <div><span className="text-muted-foreground">Street 2: </span>{loc.street2}</div>}
            {loc.city && <div><span className="text-muted-foreground">City: </span>{loc.city}</div>}
            {loc.zip && <div><span className="text-muted-foreground">ZIP: </span>{loc.zip}</div>}
            {loc.state && <div><span className="text-muted-foreground">State: </span>{loc.state}</div>}
            {loc.country && <div><span className="text-muted-foreground">Country: </span>{loc.country}</div>}
            {loc.floorNumber != null && <div><span className="text-muted-foreground">Floor: </span>{loc.floorNumber}</div>}
            {loc.coordinates && (
              <div className="font-mono">
                <span className="text-muted-foreground">Coords: </span>
                {loc.coordinates.lat.toFixed(4)}, {loc.coordinates.lng.toFixed(4)}
              </div>
            )}
            <div><span className="text-muted-foreground">Status: </span>{loc.active ? "Active" : "Inactive"}</div>
            {loc.childAllCount != null && (
              <div><span className="text-muted-foreground">Sub-locations: </span>{loc.childAllCount.toLocaleString()}</div>
            )}
            {loc.updatedAt && (
              <div><span className="text-muted-foreground">Updated: </span>{loc.updatedAt.slice(0, 10)}</div>
            )}
          </div>
          {loc.description && (
            <p className="mt-3 text-[12px] text-foreground whitespace-pre-wrap border-t border-border pt-3">
              {loc.description}
            </p>
          )}
        </div>
      </div>

      {/* Map */}
      {pin.length > 0 && <NigeriaMap pins={pin} height={280} center={[pin[0].lat, pin[0].lng]} zoom={12} />}

      {/* Descendants */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-[13px] font-bold">Descendants</h2>
            <p className="text-[11px] text-muted-foreground">All locations underneath this node ({totalDesc.toLocaleString()} total)</p>
          </div>
        </div>
        {descendants.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-6 text-center">No child locations.</p>
        ) : (
          <ul className="divide-y divide-border">
            {descendants.map(d => (
              <li key={d.id}>
                <button onClick={() => nav(`/locations/${d.id}`)} className="w-full text-left px-2 py-2 hover:bg-muted/30 flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-foreground truncate">{d.name}</p>
                    <p className="text-[11px] text-muted-foreground truncate">{d.locationType ?? "—"}</p>
                  </div>
                  <ChevronRight size={12} className="text-muted-foreground/50 shrink-0" />
                </button>
              </li>
            ))}
            {desc.hasNextPage && (
              <li className="py-2 text-center">
                <button onClick={() => desc.fetchNextPage()} className="text-xs text-primary hover:opacity-80">
                  {desc.isFetchingNextPage ? "Loading…" : "Load more"}
                </button>
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
