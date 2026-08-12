import { useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import BarcodeScanner from "@/components/BarcodeScanner";
import {
  fetchBarcodeKpis, fetchBarcodeRecentTags, lookupBarcode,
  ASSET_DOMAINS, domainLabel,
  type BarcodeTag, type BarcodeLookupHit,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { printLabels, LABEL_SIZES, type LabelData, type LabelSize } from "@/lib/labels";
import {
  ScanBarcode, AlertCircle, Tag, Package, AlertTriangle, XCircle,
  ArrowRight, Search, Printer, Keyboard, Camera, SearchX,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Mode = "type" | "camera";
type Notice = { kind: "error" | "warn"; text: string } | null;

export default function BarcodeStation() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();

  useEffect(() => {
    setTitle("Barcode Station");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const kpis   = useQuery({ queryKey: ["barcode-kpis"],   queryFn: fetchBarcodeKpis,   staleTime: 30_000 });
  const recent = useQuery({ queryKey: ["barcode-recent"], queryFn: () => fetchBarcodeRecentTags({ limit: 200 }), staleTime: 30_000 });

  const [mode, setMode] = useState<Mode>("type");
  const [query, setQuery] = useState("");
  const [size, setSize] = useState<LabelSize>("standard");
  const [domain, setDomain] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<Notice>(null);

  const lookup = useMutation({ mutationFn: (q: string) => lookupBarcode(q) });

  // `untagged` is derived server-side as total assets minus active tags, which
  // goes negative on any asset carrying more than one active tag. Floor it —
  // a negative count of untagged assets is meaningless to the user.
  const raw = kpis.data;
  const k = {
    total_assets: raw?.total_assets ?? 0,
    active_tags: raw?.active_tags ?? 0,
    pending_replacement: raw?.pending_replacement ?? 0,
    scrapped_tags: raw?.scrapped_tags ?? 0,
    untagged: Math.max(0, raw?.untagged ?? 0),
  };

  function runLookup(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setNotice(null);
    lookup.mutate(trimmed);
  }

  // A miss comes back as HTTP 200 with {found: false}, so "no result" has to be
  // read off the payload — it never lands in `lookup.error`.
  const result = lookup.data;
  const hit: BarcodeLookupHit | null = result && result.found ? result : null;
  const missed = Boolean(result && !result.found);
  const lookupErr = lookup.error as CadraApiError | null;

  const tags = recent.data ?? [];
  const visible = useMemo(
    () => (domain ? tags.filter((t) => t.domain === domain) : tags),
    [tags, domain],
  );

  // Only ever act on rows the current filter shows, so a stale selection from
  // another domain can't be printed by surprise.
  const visibleIds = useMemo(() => new Set(visible.map((t) => t.tag_id)), [visible]);
  const selectedVisible = useMemo(
    () => visible.filter((t) => selected.has(t.tag_id)),
    [visible, selected],
  );
  const allVisibleSelected = visible.length > 0 && selectedVisible.length === visible.length;

  function toggleRow(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }

  async function print(labels: LabelData[]) {
    setNotice(null);
    try {
      const res = await printLabels(labels, size);
      if (res.qrUnavailable) {
        setNotice({
          kind: "warn",
          text: "QR codes could not be loaded from the server, so labels printed with the Code128 barcode only.",
        });
      }
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Could not open the print view." });
    }
  }

  const printHit = () =>
    hit && print([{
      tag_number: hit.tag_number,
      asset_name: hit.asset_name,
      asset_code: hit.asset_code,
      location: hit.location,
      category: hit.category,
      custodian: hit.custodian,
    }]);

  const printSelected = () =>
    print(selectedVisible.map((t) => ({
      tag_number: t.tag_number,
      asset_name: t.asset_name,
      location: t.location,
    })));

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

      {notice && (
        <div className={cn(
          "rounded-2xl border p-3 flex items-start gap-2",
          notice.kind === "error"
            ? "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30"
            : "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",
        )}>
          <AlertCircle size={14} className={cn("shrink-0 mt-0.5", notice.kind === "error" ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400")} />
          <p className={cn("text-[12px]", notice.kind === "error" ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400")}>{notice.text}</p>
        </div>
      )}

      {/* Scan / lookup */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <ScanBarcode size={14} className="text-primary" />
            <h2 className="text-[13px] font-bold">Scan or type tag</h2>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-border p-0.5">
            <ModeButton active={mode === "type"}   onClick={() => setMode("type")}   icon={Keyboard} label="Type" />
            <ModeButton active={mode === "camera"} onClick={() => setMode("camera")} icon={Camera}   label="Camera" />
          </div>
        </div>

        {/* The input stays mounted in camera mode: handheld scanners emulate a
            keyboard, and a detected code is written straight into it. */}
        <form onSubmit={(e) => { e.preventDefault(); runLookup(query); }} className="flex gap-2">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
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
            {lookup.isPending ? "Looking up…" : "Lookup"}
          </button>
        </form>

        {mode === "camera" && (
          <BarcodeScanner onDetected={(value) => { setMode("type"); runLookup(value); }} />
        )}

        {lookupErr && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-700 dark:text-red-400">
              <span className="font-semibold">{lookupErr.code}:</span> {lookupErr.message}
            </p>
          </div>
        )}

        {missed && !lookupErr && (
          <div className="bg-muted/30 border border-border rounded-xl p-3 flex items-start gap-2">
            <SearchX size={14} className="text-muted-foreground shrink-0 mt-0.5" />
            <p className="text-[12px] text-muted-foreground">
              No active tag or asset matches <span className="font-mono font-semibold text-foreground">{query}</span>.
              Check the code, or search the register if the asset was never tagged.
            </p>
          </div>
        )}

        {hit && (
          <div className="bg-background border border-primary/30 rounded-xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[14px] font-bold text-foreground">{hit.asset_name}</p>
                <p className="text-[12px] text-muted-foreground font-mono">{hit.tag_number}</p>
              </div>
              <span className={cn(
                "shrink-0 inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-semibold border",
                hit.tag_state === "active"
                  ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
                  : "bg-muted border-border text-muted-foreground",
              )}>{hit.tag_state}</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-[11px]">
              <Field label="Asset code" value={hit.asset_code} mono />
              <Field label="Category"   value={hit.category} />
              <Field label="Domain"     value={domainLabel(hit.domain)} />
              <Field label="Location"   value={hit.location} />
              <Field label="Custodian"  value={hit.custodian} />
              <Field label="Condition"  value={hit.condition} />
              <Field label="Last service" value={hit.last_service_date} />
              <Field label="Next service" value={hit.next_service_date} />
              <Field label="SAP number"   value={hit.sap_asset_number} mono />
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                onClick={() => void printHit()}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-primary text-white text-xs font-semibold hover:opacity-90"
              >
                <Printer size={12} /> Print label
              </button>
              {hit.asset_id > 0 && (
                <button
                  onClick={() => nav(`/assets/${hit.asset_id}`)}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted/40"
                >
                  Open asset <ArrowRight size={11} />
                </button>
              )}
              <SizePicker value={size} onChange={setSize} />
            </div>
          </div>
        )}
      </div>

      {/* Tag inventory + batch print */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="text-[13px] font-bold">Recent tags</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {visible.length} shown{selectedVisible.length > 0 && ` · ${selectedVisible.length} selected`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="px-2 py-1.5 text-[11px] border border-border rounded-xl bg-background"
            >
              <option value="">All domains</option>
              {ASSET_DOMAINS.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
            <SizePicker value={size} onChange={setSize} />
            <button
              onClick={() => void printSelected()}
              disabled={selectedVisible.length === 0}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold",
                selectedVisible.length
                  ? "bg-primary text-white hover:opacity-90"
                  : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              <Printer size={12} />
              {selectedVisible.length ? `Print ${selectedVisible.length} label${selectedVisible.length > 1 ? "s" : ""}` : "Print labels"}
            </button>
          </div>
        </div>

        {recent.error && (
          <p className="text-[12px] text-red-700 dark:text-red-400 py-2">
            {(recent.error as CadraApiError).code}: {(recent.error as CadraApiError).message}
          </p>
        )}

        {visible.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">
            {tags.length === 0 ? "No recent tags." : "No tags in this domain."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-8 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all shown tags"
                      checked={allVisibleSelected}
                      onChange={toggleAll}
                      className="accent-primary cursor-pointer"
                    />
                  </th>
                  {["Tag", "Asset", "Domain", "Condition", "Location", "State"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((t) => (
                  <TagRow
                    key={t.tag_id}
                    tag={t}
                    checked={selected.has(t.tag_id)}
                    onToggle={() => toggleRow(t.tag_id)}
                    onOpen={() => nav(`/assets/${t.asset_id}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function TagRow({ tag, checked, onToggle, onOpen }: {
  tag: BarcodeTag; checked: boolean; onToggle: () => void; onOpen: () => void;
}) {
  return (
    <tr className={cn("border-b border-border/40 hover:bg-muted/20", checked && "bg-primary/5")}>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          aria-label={`Select ${tag.tag_number}`}
          checked={checked}
          onChange={onToggle}
          className="accent-primary cursor-pointer"
        />
      </td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] font-mono cursor-pointer">{tag.tag_number}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[200px] cursor-pointer">{tag.asset_name}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] text-muted-foreground cursor-pointer">{domainLabel(tag.domain)}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] cursor-pointer">{tag.condition}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[180px] cursor-pointer">{tag.location}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[11px] cursor-pointer">
        <span className={cn(
          "inline-flex items-center px-2 py-0.5 rounded-lg font-semibold border",
          tag.tag_state === "active"
            ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
            : "bg-muted border-border text-muted-foreground",
        )}>{tag.tag_state}</span>
      </td>
    </tr>
  );
}

function SizePicker({ value, onChange }: { value: LabelSize; onChange: (v: LabelSize) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as LabelSize)}
      title={LABEL_SIZES.find((s) => s.value === value)?.hint}
      aria-label="Label size"
      className="px-2 py-1.5 text-[11px] border border-border rounded-xl bg-background"
    >
      {LABEL_SIZES.map((s) => (
        <option key={s.value} value={s.value}>{s.label} — {s.hint.split(" — ")[0]}</option>
      ))}
    </select>
  );
}

function ModeButton({ active, onClick, icon: Icon, label }: {
  active: boolean; onClick: () => void; icon: typeof Tag; label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold",
        active ? "bg-primary text-white" : "text-muted-foreground hover:bg-muted/40",
      )}
    >
      <Icon size={11} /> {label}
    </button>
  );
}

function Field({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("text-foreground font-semibold truncate", mono && "font-mono")}>{value || "—"}</p>
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
