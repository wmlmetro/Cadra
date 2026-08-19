import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchAssetCategories, updateAssetCategory,
  fetchDepreciationSettings, updateDepreciationSettings, recomputeDepreciation,
  type AssetCategoryConfig, type CategoryPolicy, type DepreciationSettings as Settings,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  AlertCircle, Clock, RefreshCw, Info, Check, Loader2, CalendarX, Wallet, CircleSlash,
} from "lucide-react";
import { cn } from "@/lib/utils";
import BrandPill from "@/components/BrandPill";


const METHODS: { value: CategoryPolicy["method"]; label: string }[] = [
  { value: "none", label: "Not depreciated" },
  { value: "straight_line", label: "Straight line" },
  { value: "declining_balance", label: "Declining balance" },
  { value: "erp_managed", label: "ERP-managed" },
];

const inputCls =
  "w-full rounded-lg border border-border bg-background px-2 py-1 text-[12px] " +
  "focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40";

/** One editable row. Local draft state so a half-typed number never fires a
 *  request — policy changes restate every asset in the category. */
function CategoryRow({
  cat, disabled, onSave, saving,
}: {
  cat: AssetCategoryConfig;
  disabled: boolean;
  saving: boolean;
  onSave: (id: number, body: Partial<CategoryPolicy>) => void;
}) {
  const [draft, setDraft] = useState<CategoryPolicy>(cat.depreciation);
  useEffect(() => { setDraft(cat.depreciation); }, [cat.depreciation]);

  const dirty =
    draft.method !== cat.depreciation.method ||
    draft.useful_life_months !== cat.depreciation.useful_life_months ||
    draft.declining_rate !== cat.depreciation.declining_rate ||
    draft.salvage_rate !== cat.depreciation.salvage_rate;

  const num = (v: string) => (v === "" ? null : Number(v));
  const isDeclining = draft.method === "declining_balance";
  const computes = draft.method === "straight_line" || isDeclining;

  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2 pr-3">
        <div className="text-[12px] font-medium text-foreground">{cat.name}</div>
        <div className="text-[10px] text-muted-foreground">
          {cat.code ? `${cat.code} · ` : ""}{cat.asset_count.toLocaleString()} assets
        </div>
      </td>
      <td className="py-2 pr-2">
        <select
          className={inputCls} disabled={disabled} value={draft.method}
          onChange={e => setDraft({ ...draft, method: e.target.value as CategoryPolicy["method"] })}
        >
          {METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </td>
      <td className="py-2 pr-2">
        <input
          className={inputCls} type="number" min={0} disabled={disabled || !computes}
          value={draft.useful_life_months ?? ""} placeholder="—"
          onChange={e => setDraft({ ...draft, useful_life_months: num(e.target.value) })}
        />
      </td>
      <td className="py-2 pr-2">
        <input
          className={inputCls} type="number" min={0} max={100} step="0.1"
          disabled={disabled || !isDeclining}
          value={draft.declining_rate ?? ""} placeholder="—"
          onChange={e => setDraft({ ...draft, declining_rate: num(e.target.value) })}
        />
      </td>
      <td className="py-2 pr-2">
        <input
          className={inputCls} type="number" min={0} max={100} step="0.1"
          disabled={disabled || !computes}
          value={draft.salvage_rate ?? ""} placeholder="—"
          onChange={e => setDraft({ ...draft, salvage_rate: num(e.target.value) })}
        />
      </td>
      <td className="py-2 text-right">
        <button
          disabled={!dirty || disabled || saving}
          onClick={() => onSave(cat.id, draft)}
          data-testid={`save-category-${cat.id}`}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border",
            dirty && !disabled
              ? "border-primary text-primary hover:bg-primary/5"
              : "border-transparent text-muted-foreground/40 cursor-default",
          )}
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          Save
        </button>
      </td>
    </tr>
  );
}

export default function DepreciationSettingsPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const [savingId, setSavingId] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    setTitle("Settings — Depreciation");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const settings = useQuery({
    queryKey: ["depreciation-settings"],
    queryFn: fetchDepreciationSettings,
    staleTime: 30_000,
  });
  const categories = useQuery({
    queryKey: ["asset-categories"],
    queryFn: fetchAssetCategories,
    staleTime: 30_000,
    // Categories that actually hold assets first — a tenant typically uses a
    // handful of the ~28 shipped, and the empty ones are noise when you are
    // trying to correct a useful life that affects real figures.
    select: (cats) =>
      [...cats].sort((a, b) => b.asset_count - a.asset_count ||
                               a.name.localeCompare(b.name)),
  });

  /** Anything showing a book value is stale once a policy changes. Does NOT
   *  touch the settings query — its mutations write authoritative data straight
   *  into the cache, so re-fetching would only add a round trip. */
  const refreshDerived = () => {
    qc.invalidateQueries({ queryKey: ["asset-categories"] });
    qc.invalidateQueries({ queryKey: ["report-depreciation"] });
    qc.invalidateQueries({ queryKey: ["asset-depreciation"] });
  };

  const saveSettings = useMutation({
    mutationFn: (body: Partial<Settings>) => updateDepreciationSettings(body),
    // Optimistic: saving recomputes the whole register, which takes seconds on
    // a large tenant. A control that sits unchanged that long reads as broken.
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["depreciation-settings"] });
      const prev = qc.getQueryData<Settings>(["depreciation-settings"]);
      if (prev) qc.setQueryData<Settings>(["depreciation-settings"], { ...prev, ...body });
      return { prev };
    },
    onError: (_e, _body, ctx) => {
      // Put the control back where it was — the server rejected the change.
      if (ctx?.prev) qc.setQueryData(["depreciation-settings"], ctx.prev);
    },
    onSuccess: (data) => {
      qc.setQueryData(["depreciation-settings"], data);
      setNote("Settings saved — book values recomputed.");
      refreshDerived();
    },
  });

  const saveCategory = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<CategoryPolicy> }) =>
      updateAssetCategory(id, body),
    onSuccess: (d) => {
      setNote(`${d.name}: policy saved, ${(d.assets_recomputed ?? 0).toLocaleString()} assets recomputed.`);
      qc.invalidateQueries({ queryKey: ["depreciation-settings"] });
      refreshDerived();
    },
    onSettled: () => setSavingId(null),
  });

  const recompute = useMutation({
    mutationFn: recomputeDepreciation,
    onSuccess: (d) => {
      setNote(`Recomputed ${d.recomputed.toLocaleString()} assets.`);
      qc.setQueryData(["depreciation-settings"], d);
      refreshDerived();
    },
  });

  const err = (settings.error ?? categories.error ?? saveSettings.error ??
                saveCategory.error ?? recompute.error) as CadraApiError | null;

  if (settings.isLoading || categories.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading settings…</p>
    </div>
  );

  const s = settings.data;
  const erpManaged = s?.mode === "erp_managed";
  const dq = s?.data_quality;
  const busy = saveSettings.isPending || recompute.isPending;

  return (
    <div className="p-6 space-y-5 max-w-[1100px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <BrandPill />
          <div>
            <h1 className="text-xl font-bold text-foreground">Depreciation settings</h1>
            <p className="text-xs text-muted-foreground mt-1">
              How book values are calculated for this tenant. Changes here restate
              figures across the whole register.
            </p>
          </div>
        </div>
        <button
          onClick={() => recompute.mutate()}
          disabled={busy || erpManaged}
          data-testid="button-recompute"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent disabled:opacity-40"
        >
          <RefreshCw size={12} className={cn(recompute.isPending && "animate-spin")} />
          Recompute now
        </button>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{err.code}</p>
            <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{err.message}</p>
          </div>
        </div>
      )}
      {note && !err && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/30 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Check size={14} className="text-emerald-600 dark:text-emerald-400" />
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300">{note}</p>
        </div>
      )}

      {/* ── Who owns book values (PRD §8.6's two operating modes) ── */}
      <section className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-1">Who calculates book value</h2>
        <p className="text-[11px] text-muted-foreground mb-3">
          Set this to ERP-managed when an external system owns the figures. Cadra
          then stores what it is given and never calculates.
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          {([
            { v: "computed", t: "Cadra calculates", d: "Book values derived from the policies below." },
            { v: "erp_managed", t: "ERP-managed", d: "Figures supplied by your ERP; Cadra does not compute." },
          ] as const).map(o => (
            <button
              key={o.v}
              onClick={() => saveSettings.mutate({ mode: o.v })}
              disabled={busy}
              data-testid={`mode-${o.v}`}
              className={cn(
                "flex-1 text-left rounded-xl border px-4 py-3 transition-colors disabled:opacity-50",
                s?.mode === o.v
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent",
              )}
            >
              <div className="text-[12px] font-semibold">{o.t}</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">{o.d}</div>
            </button>
          ))}
        </div>
      </section>

      {erpManaged && (
        <div className="bg-sky-50 dark:bg-sky-950/20 border border-sky-200/70 dark:border-sky-800/30 rounded-2xl px-4 py-3 flex items-start gap-2">
          <Info size={14} className="text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-sky-800 dark:text-sky-300">
            This tenant is ERP-managed, so the calculation options and category
            policies below have no effect until you switch back.
          </p>
        </div>
      )}

      {/* ── Conventions ── */}
      <section className={cn("bg-card border border-border rounded-2xl p-5", erpManaged && "opacity-50")}>
        <h2 className="text-[13px] font-bold mb-3">Calculation conventions</h2>

        <label className="flex items-start gap-3 py-2 cursor-pointer">
          <input
            type="checkbox" className="mt-0.5" disabled={busy || erpManaged}
            data-testid="toggle-db-switch"
            checked={!!s?.declining_switches_to_straight_line}
            onChange={e => saveSettings.mutate({
              declining_switches_to_straight_line: e.target.checked,
            })}
          />
          <span>
            <span className="text-[12px] font-medium text-foreground">
              Declining balance switches to straight line
            </span>
            <span className="block text-[11px] text-muted-foreground mt-0.5">
              Charge the greater of the declining amount and straight line over the
              remaining life. Without this, the final period absorbs everything
              left — a charge that can be tens of times the one before it.
            </span>
          </span>
        </label>

        <div className="py-2">
          <span className="text-[12px] font-medium text-foreground">First period</span>
          <div className="flex gap-2 mt-1.5">
            {([
              { v: "whole_month", t: "Whole month" },
              { v: "daily", t: "Pro-rata by days" },
            ] as const).map(o => (
              <button
                key={o.v} disabled={busy || erpManaged}
                data-testid={`proration-${o.v}`}
                onClick={() => saveSettings.mutate({ proration: o.v })}
                className={cn(
                  "px-3 py-1.5 rounded-lg border text-[11px] font-medium disabled:opacity-50",
                  s?.proration === o.v
                    ? "border-primary text-primary bg-primary/5"
                    : "border-border text-muted-foreground hover:bg-accent",
                )}
              >
                {o.t}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1.5">
            Whether an asset acquired mid-month is charged a full month or only
            the days it was held.
          </p>
        </div>

        {s?.last_recompute && (
          <p className="text-[10px] text-muted-foreground mt-3 pt-3 border-t border-border">
            Last recomputed {s.last_recompute}
          </p>
        )}
      </section>

      {/* ── Data quality ── */}
      {dq && (dq.missing_cost > 0 || dq.needs_start_date > 0 || dq.not_configured > 0) && (
        <section className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-1">Data quality</h2>
          <p className="text-[11px] text-muted-foreground mb-3">
            Depreciation is only as good as what it is given.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { n: dq.missing_cost, icon: Wallet, label: "have a method but no acquisition cost, so nothing can be written down" },
              { n: dq.needs_start_date, icon: CalendarX, label: "have an estimated start date inferred from when the record was created" },
              { n: dq.not_configured, icon: CircleSlash, label: "have no depreciation policy at all" },
            ].map((x, i) => (
              <div key={i} className="rounded-xl border border-border px-3 py-3">
                <div className="flex items-center gap-1.5">
                  <x.icon size={12} className={x.n ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"} />
                  <span className={cn("text-[20px] font-extrabold tabular-nums",
                    x.n ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
                    {x.n.toLocaleString()}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">{x.label}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Category policy ── */}
      <section className={cn("bg-card border border-border rounded-2xl p-5", erpManaged && "opacity-50")}>
        <h2 className="text-[13px] font-bold mb-1">Policy by asset category</h2>
        <p className="text-[11px] text-muted-foreground mb-3">
          Every asset inherits its category's policy unless it has been overridden
          on the asset itself. Saving a row restates book value for every asset in
          that category.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2 text-[11px] font-medium">Category</th>
                <th className="py-2 text-[11px] font-medium">Method</th>
                <th className="py-2 text-[11px] font-medium">Life (months)</th>
                <th className="py-2 text-[11px] font-medium">Rate (%/yr)</th>
                <th className="py-2 text-[11px] font-medium">Salvage (%)</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {(categories.data ?? []).map(c => (
                <CategoryRow
                  key={c.id} cat={c} disabled={erpManaged || busy}
                  saving={savingId === c.id}
                  onSave={(id, body) => { setSavingId(id); saveCategory.mutate({ id, body }); }}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
