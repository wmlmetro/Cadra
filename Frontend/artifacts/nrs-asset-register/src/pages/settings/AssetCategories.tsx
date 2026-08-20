import { useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchAssetCategories, updateAssetCategory, createAssetCategory, deleteAssetCategory,
  FM_DOMAINS, type AssetCategoryConfig, type CategoryIdentity,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import BrandPill from "@/components/BrandPill";
import {
  AlertCircle, Clock, Check, Loader2, Plus, Trash2, X, Info,
} from "lucide-react";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg border border-border bg-background px-2 py-1 text-[12px] " +
  "focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40";

/** One row, with a local draft so a half-typed value never fires a request. */
function Row({
  cat, busy, onSave, onDelete, saving, deleting,
}: {
  cat: AssetCategoryConfig;
  busy: boolean;
  saving: boolean;
  deleting: boolean;
  onSave: (id: number, body: Partial<CategoryIdentity>) => void;
  onDelete: (cat: AssetCategoryConfig) => void;
}) {
  const initial: CategoryIdentity = {
    name: cat.name,
    code: cat.code,
    domain: cat.domain,
    description: cat.description,
    sequence: cat.sequence,
    pm_interval_days: cat.pm_interval_days,
  };
  const [draft, setDraft] = useState<CategoryIdentity>(initial);
  useEffect(() => { setDraft(initial); /* eslint-disable-next-line */ }, [cat]);

  const dirty = (Object.keys(initial) as (keyof CategoryIdentity)[])
    .some(k => draft[k] !== initial[k]);

  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2 pr-2">
        <input className={inputCls} disabled={busy} value={draft.name}
               onChange={e => setDraft({ ...draft, name: e.target.value })} />
      </td>
      <td className="py-2 pr-2 w-24">
        <input className={inputCls} disabled={busy} value={draft.code ?? ""} placeholder="—"
               onChange={e => setDraft({ ...draft, code: e.target.value || null })} />
      </td>
      <td className="py-2 pr-2">
        <select className={inputCls} disabled={busy} value={draft.domain ?? ""}
                onChange={e => setDraft({ ...draft, domain: e.target.value || null })}>
          <option value="">—</option>
          {FM_DOMAINS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </td>
      <td className="py-2 pr-2 w-28">
        <input className={inputCls} type="number" min={0} disabled={busy}
               value={draft.pm_interval_days ?? ""} placeholder="—"
               onChange={e => setDraft({
                 ...draft,
                 pm_interval_days: e.target.value === "" ? null : Number(e.target.value),
               })} />
      </td>
      <td className="py-2 pr-2 text-right text-[12px] tabular-nums text-muted-foreground w-20">
        {cat.asset_count.toLocaleString()}
      </td>
      <td className="py-2 text-right whitespace-nowrap">
        <button
          disabled={!dirty || busy}
          onClick={() => onSave(cat.id, draft)}
          data-testid={`save-cat-${cat.id}`}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border mr-1",
            dirty && !busy
              ? "border-primary text-primary hover:bg-primary/5"
              : "border-transparent text-muted-foreground/40 cursor-default",
          )}
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          Save
        </button>
        <button
          disabled={busy || cat.asset_count > 0}
          onClick={() => onDelete(cat)}
          data-testid={`delete-cat-${cat.id}`}
          // Deleting a category that holds assets would orphan them; the API
          // refuses with 409 either way, but there is no point offering it.
          title={cat.asset_count > 0
            ? `Holds ${cat.asset_count} asset(s) — reassign them first`
            : "Delete this category"}
          className={cn(
            "inline-flex items-center px-2 py-1 rounded-lg text-[11px] border",
            cat.asset_count > 0 || busy
              ? "border-transparent text-muted-foreground/30 cursor-not-allowed"
              : "border-border text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30",
          )}
        >
          {deleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
        </button>
      </td>
    </tr>
  );
}

export default function AssetCategoriesPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const [note, setNote] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [draftNew, setDraftNew] = useState<Partial<CategoryIdentity>>({ name: "" });

  useEffect(() => {
    setTitle("Settings — Asset Categories");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const categories = useQuery({
    queryKey: ["asset-categories"],
    queryFn: fetchAssetCategories,
    staleTime: 30_000,
    // Busiest first — a tenant uses a handful of the ~29 shipped.
    select: (cats) => [...cats].sort(
      (a, b) => b.asset_count - a.asset_count || a.name.localeCompare(b.name)),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["asset-categories"] });
    // The register groups by category, so its labels may have moved.
    qc.invalidateQueries({ queryKey: ["report-depreciation"] });
  };

  const save = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<CategoryIdentity> }) =>
      updateAssetCategory(id, body),
    onSuccess: (d) => { setNote(`Saved ${d.name}.`); refresh(); },
    onSettled: () => setSavingId(null),
  });

  const create = useMutation({
    mutationFn: (body: Partial<CategoryIdentity>) => createAssetCategory(body),
    onSuccess: (d) => {
      setNote(`Created ${d.name}.`);
      setAdding(false); setDraftNew({ name: "" }); refresh();
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteAssetCategory(id),
    onSuccess: (d) => { setNote(`Deleted ${d.name}.`); refresh(); },
    onSettled: () => setDeletingId(null),
  });

  const err = (categories.error ?? save.error ?? create.error ?? remove.error) as CadraApiError | null;
  const busy = create.isPending || save.isPending || remove.isPending;

  const totals = useMemo(() => {
    const c = categories.data ?? [];
    return { count: c.length, inUse: c.filter(x => x.asset_count > 0).length };
  }, [categories.data]);

  if (categories.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading categories…</p>
    </div>
  );

  return (
    <div className="p-6 space-y-5 max-w-[1100px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <BrandPill />
          <div>
            <h1 className="text-xl font-bold text-foreground">Asset categories</h1>
            <p className="text-xs text-muted-foreground mt-1">
              The classification every asset hangs off. {totals.count} categories,
              {" "}{totals.inUse} in use.
            </p>
          </div>
        </div>
        <button
          onClick={() => setAdding(v => !v)}
          disabled={busy}
          data-testid="button-add-category"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent disabled:opacity-40"
        >
          {adding ? <X size={12} /> : <Plus size={12} />} {adding ? "Cancel" : "New category"}
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

      <div className="bg-sky-50 dark:bg-sky-950/20 border border-sky-200/70 dark:border-sky-800/30 rounded-2xl px-4 py-3 flex items-start gap-2">
        <Info size={14} className="text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-sky-800 dark:text-sky-300">
          Depreciation policy lives on{" "}
          <Link href="/settings/depreciation" className="underline font-medium">
            Settings → Depreciation
          </Link>
          , so a useful life is only ever edited in one place.
        </p>
      </div>

      {adding && (
        <section className="bg-card border border-border rounded-2xl p-5">
          <h2 className="text-[13px] font-bold mb-3">New category</h2>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-[11px] text-muted-foreground">Name</label>
              <input className={inputCls} autoFocus value={draftNew.name ?? ""}
                     data-testid="new-category-name"
                     onChange={e => setDraftNew({ ...draftNew, name: e.target.value })} />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground">Code</label>
              <input className={inputCls} value={draftNew.code ?? ""}
                     onChange={e => setDraftNew({ ...draftNew, code: e.target.value || null })} />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground">FM domain</label>
              <select className={inputCls} value={draftNew.domain ?? ""}
                      onChange={e => setDraftNew({ ...draftNew, domain: e.target.value || null })}>
                <option value="">—</option>
                {FM_DOMAINS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground">PM interval (days)</label>
              <input className={inputCls} type="number" min={0}
                     value={draftNew.pm_interval_days ?? ""}
                     onChange={e => setDraftNew({
                       ...draftNew,
                       pm_interval_days: e.target.value === "" ? null : Number(e.target.value),
                     })} />
            </div>
          </div>
          <button
            className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-primary text-primary hover:bg-primary/5 disabled:opacity-40"
            disabled={!draftNew.name?.trim() || busy}
            data-testid="submit-new-category"
            onClick={() => create.mutate(draftNew)}
          >
            {create.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            Create
          </button>
        </section>
      )}

      <section className="bg-card border border-border rounded-2xl p-5 overflow-x-auto">
        <table className="w-full min-w-[820px]">
          <thead>
            <tr className="text-left text-muted-foreground border-b border-border">
              <th className="py-2 text-[11px] font-medium">Name</th>
              <th className="py-2 text-[11px] font-medium">Code</th>
              <th className="py-2 text-[11px] font-medium">FM domain</th>
              <th className="py-2 text-[11px] font-medium">PM interval (days)</th>
              <th className="py-2 text-[11px] font-medium text-right">Assets</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {(categories.data ?? []).map(c => (
              <Row
                key={c.id} cat={c} busy={busy}
                saving={savingId === c.id}
                deleting={deletingId === c.id}
                onSave={(id, body) => { setSavingId(id); save.mutate({ id, body }); }}
                onDelete={(cat) => {
                  if (!window.confirm(`Delete "${cat.name}"? This cannot be undone.`)) return;
                  setDeletingId(cat.id);
                  remove.mutate(cat.id);
                }}
              />
            ))}
          </tbody>
        </table>
        <p className="text-[10px] text-muted-foreground mt-3">
          A category holding assets cannot be deleted — reassign them first.
        </p>
      </section>
    </div>
  );
}
