import { useEffect } from "react";
import { useSearch, useLocation, Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { apiConfigured, apiGet } from "@/lib/api";
import { listEmployees, listAssets, listLocations } from "@/lib/dataProvider";
import { Users, Package, MapPin, Search as SearchIcon } from "lucide-react";

type Hit = { id: string; title: string; subtitle?: string; href: string };

const LIMIT = 12;

function useQ(): string {
  const search = useSearch();
  return new URLSearchParams(search).get("q")?.trim() ?? "";
}

// ── per-entity queries (API when signed in, mock list filtered otherwise) ──

function useEmployeeHits(q: string) {
  return useQuery({
    queryKey: ["gsearch", "employees", q],
    enabled: q.length > 0,
    queryFn: async (): Promise<Hit[]> => {
      if (!apiConfigured) {
        const ql = q.toLowerCase();
        return listEmployees()
          .filter((e) => e.name.toLowerCase().includes(ql) || e.irNumber.toLowerCase().includes(ql))
          .slice(0, LIMIT)
          .map((e) => ({ id: String(e.id), title: e.name, subtitle: e.irNumber ? `IR ${e.irNumber}` : undefined, href: `/hr/employees/${e.id}` }));
      }
      const res = await apiGet<Array<{ id: number; name: string; ir_number?: string }>>(
        "/api/v1/identity/employees", { q, limit: LIMIT });
      return res.data.map((e) => ({
        id: String(e.id), title: e.name,
        subtitle: e.ir_number ? `IR ${e.ir_number}` : undefined,
        href: `/hr/employees/${e.id}`,
      }));
    },
  });
}

function useAssetHits(q: string) {
  return useQuery({
    queryKey: ["gsearch", "assets", q],
    enabled: q.length > 0,
    queryFn: async (): Promise<Hit[]> => {
      if (!apiConfigured) {
        const ql = q.toLowerCase();
        return listAssets()
          .filter((a) => a.name.toLowerCase().includes(ql) || (a.assetTag ?? "").toLowerCase().includes(ql))
          .slice(0, LIMIT)
          .map((a) => ({ id: String(a.id), title: a.name, subtitle: a.assetTag || undefined, href: `/assets/${a.id}` }));
      }
      const res = await apiGet<Array<{ id: number; name: string; asset_tag?: string; asset_code?: string }>>(
        "/api/v1/assets", { q, limit: LIMIT });
      return res.data.map((a) => ({
        id: String(a.id), title: a.name,
        subtitle: a.asset_tag || a.asset_code || undefined,
        href: `/assets/${a.id}`,
      }));
    },
  });
}

function useLocationHits(q: string) {
  return useQuery({
    queryKey: ["gsearch", "locations", q],
    enabled: q.length > 0,
    queryFn: async (): Promise<Hit[]> => {
      if (!apiConfigured) {
        const ql = q.toLowerCase();
        return listLocations()
          .filter((l) => l.name.toLowerCase().includes(ql))
          .slice(0, LIMIT)
          .map((l) => ({ id: String(l.id), title: l.name, href: `/locations/${l.id}` }));
      }
      const res = await apiGet<Array<{ id: number; name: string }>>(
        "/api/v1/locations", { q, limit: LIMIT });
      return res.data.map((l) => ({ id: String(l.id), title: l.name, href: `/locations/${l.id}` }));
    },
  });
}

function Section({ icon, label, hits, loading }: {
  icon: React.ReactNode; label: string; hits: Hit[]; loading: boolean;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        <span>{label}</span>
        <span className="text-muted-foreground/60">{loading ? "…" : `(${hits.length})`}</span>
      </div>
      {!loading && hits.length === 0 ? (
        <p className="text-xs text-muted-foreground/60 px-1">No matches</p>
      ) : (
        <div className="rounded-xl border border-border divide-y divide-border/60 overflow-hidden">
          {hits.map((h) => (
            <Link key={h.id} href={h.href}
              className="flex items-center justify-between px-3 py-2.5 hover:bg-accent transition-colors">
              <span className="text-[13px] text-foreground truncate">{h.title}</span>
              {h.subtitle && <span className="text-[11px] font-mono text-muted-foreground shrink-0 ml-3">{h.subtitle}</span>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GlobalSearch() {
  const q = useQ();
  const { setTitle } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => { setTitle("Search"); }, [setTitle]);

  const emp = useEmployeeHits(q);
  const asset = useAssetHits(q);
  const loc = useLocationHits(q);

  const total = (emp.data?.length ?? 0) + (asset.data?.length ?? 0) + (loc.data?.length ?? 0);
  const anyLoading = emp.isFetching || asset.isFetching || loc.isFetching;

  if (!q) {
    return (
      <div className="p-10 text-center text-muted-foreground">
        <SearchIcon size={28} className="mx-auto mb-3 opacity-40" />
        <p className="text-sm">Type a name, IR number, asset tag or location and press Enter.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <p className="text-[13px] text-muted-foreground mb-5">
        Results for <span className="font-semibold text-foreground">“{q}”</span>
        {!anyLoading && <span> — {total} match{total === 1 ? "" : "es"}</span>}
      </p>

      <Section icon={<Users size={13} />}   label="Employees" hits={emp.data ?? []}   loading={emp.isFetching} />
      <Section icon={<Package size={13} />} label="Assets"    hits={asset.data ?? []} loading={asset.isFetching} />
      <Section icon={<MapPin size={13} />}  label="Locations" hits={loc.data ?? []}   loading={loc.isFetching} />

      {!anyLoading && total === 0 && (
        <div className="text-center text-muted-foreground py-6">
          <p className="text-sm">Nothing found for “{q}”.</p>
          <button onClick={() => nav("/hr/employees")} className="text-xs text-primary hover:underline mt-2">
            Browse employees instead
          </button>
        </div>
      )}
    </div>
  );
}
