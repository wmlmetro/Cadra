import { useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchAssetCategories, updateAssetCategory, createAssetCategory, deleteAssetCategory,
  fetchSerialPlaceholders, updateSerialPlaceholders,
  CAPTURABLE_ATTRIBUTES, IDENTIFICATION_MODE_WORDS, SAP_ASSET_CLASS_HINTS, isSapAssetClass,
  type AssetCategoryConfig, type CategoryIdentity, type CategoryClassIdentification,
  type CategorySapClass, type CapturableAttribute, type IdentificationMode,
} from "@/lib/dataProvider";
// Both FM domain dropdowns on this screen were filled from `FM_DOMAINS`, a
// hand-written constant in dataProvider that had an identical twin 630 lines
// above it in the same file. The set is `nrs.asset.category.domain` and the
// server publishes it; read it rather than keeping a third copy.
import { useEnum } from "@/hooks/useEnums";
import { CadraApiError } from "@/lib/api";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import BrandPill from "@/components/BrandPill";
import {
  AlertCircle, Clock, Check, Loader2, Plus, Trash2, X, Info,
} from "lucide-react";
import { cn, formatIsoDateTime } from "@/lib/utils";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

const inputCls =
  "w-full rounded-lg border border-border bg-background px-2 py-1 text-[12px] " +
  "focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40";

/** Each mode's default schema, as the server applies it when a class has
 *  none stored (handoff 58 §4, AD-32). Used only to carry a row that was
 *  still on its old mode's default over to the new mode's default when the
 *  mode is changed in the draft — a list somebody had edited is left as
 *  they left it. The server, not this table, decides what is effective. */
const MODE_DEFAULT_ATTRIBUTES: Record<IdentificationMode, CapturableAttribute[]> = {
  serial: ["make", "model_name"],
  // Handoff 61 (ruling R9): make and model no longer mandatory by default.
  tag_id: ["name", "colour", "material", "dimensions"],
  // Handoff 59 §2: description, plus what the record is known by.
  record_only: ["name", "record_reference"],
  pool: [],
};

/** Everything a row's Save may send. */
type CategoryRowBody = Partial<CategoryIdentity & CategoryClassIdentification & CategorySapClass>;

/** The datalist the SAP class inputs share — a HINT: any four digits are
 *  accepted, because NRS may use classes SAP's export did not show. */
const SAP_HINTS_ID = "sap-asset-class-hints";

const MODES = Object.keys(IDENTIFICATION_MODE_WORDS) as IdentificationMode[];

/** The capturable set's order, so a ticked list compares and sends in one
 *  shape whatever order the boxes were clicked in. */
const ATTR_ORDER = CAPTURABLE_ATTRIBUTES.map(a => a.field) as CapturableAttribute[];
const ordered = (xs: readonly CapturableAttribute[]) => ATTR_ORDER.filter(f => xs.includes(f));
const sameList = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((x, i) => x === b[i]);

/** The class half of a row as the server published it. A server older than
 *  handoff 58 publishes neither key; read that as the model's default. */
function classOf(cat: AssetCategoryConfig): CategoryClassIdentification {
  const mode = cat.identification_mode ?? "serial";
  return {
    identification_mode: mode,
    class_attributes_schema: {
      mandatory: ordered(cat.class_attributes_schema?.mandatory ?? MODE_DEFAULT_ATTRIBUTES[mode]),
    },
  };
}

/** One row, with a local draft so a half-typed value never fires a request. */
function Row({
  cat, busy, identityLocked, classLocked, fullEdit, onSave, onDelete, saving, deleting,
}: {
  cat: AssetCategoryConfig;
  busy: boolean;
  /** No `settings:write` (handoff 46): the name, code, domain and interval
   *  are disabled. */
  identityLocked: boolean;
  /** Neither `settings:write` nor `settings:classes` (handoff 58): the
   *  identification mode and the mandatory attributes are disabled too, and
   *  Save is not drawn. */
  classLocked: boolean;
  /** `settings:write`: Delete is drawn. A `settings:classes`-only person
   *  changes how a class is identified and nothing else about it. */
  fullEdit: boolean;
  saving: boolean;
  deleting: boolean;
  onSave: (id: number, body: CategoryRowBody) => void;
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
  const initialClass = classOf(cat);
  const [draft, setDraft] = useState<CategoryIdentity>(initial);
  const [classDraft, setClassDraft] = useState<CategoryClassIdentification>(initialClass);
  // SAP's class code (handoff 59 §1), as typed. "" is no class.
  const initialSap = cat.sap_asset_class ?? "";
  const [sapDraft, setSapDraft] = useState(initialSap);
  useEffect(() => {
    setDraft(initial);
    setClassDraft(initialClass);
    setSapDraft(initialSap);
    /* eslint-disable-next-line */
  }, [cat]);
  const domains = useEnum("domain");

  const identityDirty = (Object.keys(initial) as (keyof CategoryIdentity)[])
    .some(k => draft[k] !== initial[k]);
  const classDirty =
    classDraft.identification_mode !== initialClass.identification_mode
    || !sameList(classDraft.class_attributes_schema.mandatory,
                 initialClass.class_attributes_schema.mandatory);
  const sapTyped = sapDraft.trim();
  const sapDirty = sapTyped !== initialSap;
  const sapValid = sapTyped === "" || isSapAssetClass(sapTyped);
  const dirty = (identityDirty && !identityLocked)
    || ((classDirty || sapDirty) && !classLocked);

  const mandatory = classDraft.class_attributes_schema.mandatory;
  const setMode = (mode: IdentificationMode) => setClassDraft(prev => ({
    identification_mode: mode,
    class_attributes_schema: {
      // Still on the old mode's default → the new mode's default; edited →
      // kept. Either way the boxes show what will be sent before Save.
      mandatory: sameList(prev.class_attributes_schema.mandatory,
                          MODE_DEFAULT_ATTRIBUTES[prev.identification_mode])
        ? [...MODE_DEFAULT_ATTRIBUTES[mode]]
        : prev.class_attributes_schema.mandatory,
    },
  }));
  const toggleAttr = (field: CapturableAttribute) => setClassDraft(prev => {
    const cur = prev.class_attributes_schema.mandatory;
    return {
      ...prev,
      class_attributes_schema: {
        mandatory: ordered(cur.includes(field) ? cur.filter(f => f !== field) : [...cur, field]),
      },
    };
  });

  // What Save sends. The identity keys go only from a `settings:write`
  // holder (any other key from a `settings:classes`-only caller is a 403
  // naming `settings:write`); the two class keys only when they changed, so
  // an edit of a name alone sends what it sent before handoff 58.
  const body = (): CategoryRowBody => ({
    ...(identityLocked ? {} : draft),
    ...(classDirty && !classLocked ? classDraft : {}),
    // Cleared → null, which the server takes as "no class".
    ...(sapDirty && !classLocked ? { sap_asset_class: sapTyped || null } : {}),
  });

  return (
    <tr className="border-b border-border last:border-0 align-top">
      <td className="py-2 pr-2">
        <input className={inputCls} disabled={busy || identityLocked} value={draft.name}
               onChange={e => setDraft({ ...draft, name: e.target.value })} />
      </td>
      <td className="py-2 pr-2 w-24">
        <input className={inputCls} disabled={busy || identityLocked} value={draft.code ?? ""} placeholder="—"
               onChange={e => setDraft({ ...draft, code: e.target.value || null })} />
      </td>
      <td className="py-2 pr-2">
        <select className={inputCls} disabled={busy || identityLocked} value={draft.domain ?? ""}
                onChange={e => setDraft({ ...draft, domain: e.target.value || null })}>
          <option value="">—</option>
          {domains.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </td>
      <td className="py-2 pr-2 w-28">
        <input className={inputCls} type="number" min={0} disabled={busy || identityLocked}
               value={draft.pm_interval_days ?? ""} placeholder="—"
               onChange={e => setDraft({
                 ...draft,
                 pm_interval_days: e.target.value === "" ? null : Number(e.target.value),
               })} />
      </td>
      <td className="py-2 pr-2 w-44">
        <select className={inputCls} disabled={busy || classLocked}
                value={classDraft.identification_mode}
                data-testid={`select-identification-mode-${cat.id}`}
                aria-label={`How ${cat.name} is identified`}
                onChange={e => setMode(e.target.value as IdentificationMode)}>
          {MODES.map(m => <option key={m} value={m}>{IDENTIFICATION_MODE_WORDS[m]}</option>)}
        </select>
      </td>
      <td className="py-2 pr-2 w-24">
        <input
          className={cn(inputCls, "font-mono", !sapValid && "border-red-400 focus:ring-red-400")}
          disabled={busy || classLocked}
          value={sapDraft}
          placeholder="—"
          inputMode="numeric"
          maxLength={4}
          list={SAP_HINTS_ID}
          data-testid={`input-sap-class-${cat.id}`}
          aria-label={`SAP asset class of ${cat.name}`}
          aria-invalid={!sapValid}
          onChange={e => setSapDraft(e.target.value)}
        />
        {!sapValid && (
          <p className="text-[10px] text-red-600 dark:text-red-400 mt-1" data-testid={`sap-class-invalid-${cat.id}`}>
            Four digits, for example 3000.
          </p>
        )}
        {sapValid && sapTyped === "" && (
          // What a blank costs, beside the blank: the register gates refuse
          // to submit or approve a unit of this class until it is set.
          <p className="text-[10px] text-amber-700 dark:text-amber-400 mt-1" data-testid={`sap-class-missing-${cat.id}`}>
            Not set — cannot be registered.
          </p>
        )}
      </td>
      <td className="py-2 pr-2 w-64">
        <fieldset disabled={busy || classLocked} className="flex flex-wrap gap-x-3 gap-y-1 disabled:opacity-40"
                  aria-label={`Attributes a receipt of ${cat.name} must carry`}>
          {CAPTURABLE_ATTRIBUTES.map(({ field, label }) => (
            <label key={field} className="inline-flex items-center gap-1 text-[11px] text-foreground whitespace-nowrap cursor-pointer">
              <input
                type="checkbox"
                checked={mandatory.includes(field)}
                onChange={() => toggleAttr(field)}
                data-testid={`attr-${field}-${cat.id}`}
                className="h-3 w-3 rounded border-border accent-[hsl(var(--primary))]"
              />
              {label}
            </label>
          ))}
        </fieldset>
        {mandatory.length === 0 && (
          <p className="text-[10px] text-muted-foreground mt-1">None — a receipt need carry no attribute.</p>
        )}
      </td>
      <td className="py-2 pr-2 text-right text-[12px] tabular-nums text-muted-foreground w-20">
        {cat.asset_count.toLocaleString()}
      </td>
      <td className="py-2 text-right whitespace-nowrap">
        {!classLocked && (<>
        <button
          disabled={!dirty || busy || !sapValid}
          onClick={() => onSave(cat.id, body())}
          data-testid={`save-cat-${cat.id}`}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border mr-1",
            dirty && !busy && sapValid
              ? "border-primary text-primary hover:bg-primary/5"
              : "border-transparent text-muted-foreground/40 cursor-default",
          )}
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          Save
        </button>
        {fullEdit && (
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
        )}
        </>)}
      </td>
    </tr>
  );
}

/** One value per line, blanks and repeats dropped, order kept. */
const linesOf = (text: string) =>
  Array.from(new Set(text.split("\n").map(l => l.trim()).filter(Boolean)));

/**
 * The tenant's placeholder serials (handoff 59 §3) — `0`, `XXXX`,
 * `4A12345FD`: values SAP's register carries where a serial should be. A
 * gated receipt refuses one as a placeholder, and the serial-uniqueness check
 * ignores legacy assets that carry one. Lives here because the class settings
 * do; no sidebar item of its own (a nav item is a published key).
 *
 * Editable with `settings:write`, read-only with `settings:read`; the PUT
 * replaces both lists whole and lands on the configuration record as
 * `cadra.serial_placeholders`. Nothing here rewrites a serial already stored:
 * the legacy figure is a measurement, and cleaning it is NRS's call.
 */
function SerialPlaceholdersSection({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["serial-placeholders"],
    queryFn: fetchSerialPlaceholders,
    staleTime: 30_000,
  });
  const [exactText, setExactText] = useState("");
  const [patternText, setPatternText] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!list.data) return;
    setExactText(list.data.exact.join("\n"));
    setPatternText(list.data.patterns.join("\n"));
  }, [list.data]);

  const exact = linesOf(exactText);
  const patterns = linesOf(patternText);
  const dirty = !!list.data && (
    !sameList(exact, list.data.exact) || !sameList(patterns, list.data.patterns));

  const save = useMutation({
    mutationFn: () => updateSerialPlaceholders({ exact, patterns }),
    onSuccess: (d) => {
      qc.setQueryData(["serial-placeholders"], d);
      setSaved(true);
    },
  });
  const err = (list.error ?? save.error) as CadraApiError | null;
  const d = list.data;

  return (
    <section className="bg-card border border-border rounded-2xl p-5 space-y-3" data-testid="serial-placeholders">
      <div>
        <h2 className="text-[13px] font-bold">Placeholder serials</h2>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          Values that stand where a serial number should be. A receipt carrying one is refused, and an existing
          asset carrying one never makes a real serial look like a duplicate.
        </p>
      </div>

      {list.isLoading && <p className="text-[11px] text-muted-foreground">Loading…</p>}
      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2"
             data-testid="serial-placeholders-error">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} stacked />
        </div>
      )}

      {d && (<>
        {/* The server's own sentence, as written. */}
        <p className="text-[12px] text-foreground" data-testid="serial-placeholders-statement">{d.statement}</p>
        <p className="text-[11px] text-muted-foreground" data-testid="serial-placeholders-changed">
          {d.changed_at
            ? <>Last changed {formatIsoDateTime(d.changed_at)}{d.changed_by ? <> by <span className="font-medium text-foreground">{d.changed_by.name}</span></> : null}.</>
            : d.configured ? "Changed, with no record of who or when." : "The seeded list — nobody has changed it on this tenant."}
          {" "}Recorded on the configuration record as <span className="font-mono">{d.parameter}</span>.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="placeholders-exact" className="text-[11px] text-muted-foreground">
              Exact values (one per line; case, spacing and surrounding blanks ignored)
            </label>
            <textarea id="placeholders-exact" rows={8}
              className={cn(inputCls, "font-mono")} disabled={!canEdit || save.isPending}
              value={exactText} onChange={e => { setSaved(false); setExactText(e.target.value); }}
              data-testid="input-placeholders-exact" />
          </div>
          <div>
            <label htmlFor="placeholders-patterns" className="text-[11px] text-muted-foreground">
              Patterns (one regular expression per line, e.g. ^X+$)
            </label>
            <textarea id="placeholders-patterns" rows={8}
              className={cn(inputCls, "font-mono")} disabled={!canEdit || save.isPending}
              value={patternText} onChange={e => { setSaved(false); setPatternText(e.target.value); }}
              data-testid="input-placeholders-patterns" />
          </div>
        </div>

        {canEdit ? (
          <div className="flex items-center gap-3">
            <button
              disabled={!dirty || save.isPending}
              onClick={() => save.mutate()}
              data-testid="button-save-placeholders"
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border",
                dirty && !save.isPending
                  ? "border-primary text-primary hover:bg-primary/5"
                  : "border-border text-muted-foreground/50 cursor-default",
              )}
            >
              {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Save placeholder list
            </button>
            {saved && !dirty && (
              <span className="text-[11px] text-emerald-700 dark:text-emerald-400" data-testid="placeholders-saved">Saved.</span>
            )}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground" data-testid="placeholders-read-only">
            Changing this list needs the settings:write scope.
          </p>
        )}

        {/* Measured, never cleaned (§3): what the register already holds. */}
        <div className="rounded-xl border border-border bg-muted/30 px-3 py-2" data-testid="serial-placeholders-legacy">
          <p className="text-[12px] text-foreground">
            <span className="font-semibold tabular-nums">{d.legacy.placeholders.toLocaleString()}</span> of{" "}
            <span className="tabular-nums">{d.legacy.with_serial.toLocaleString()}</span> assets with a serial carry a
            placeholder ({d.legacy.assets.toLocaleString()} assets in all). Nothing here changes them.
          </p>
          {d.legacy.top.length > 0 && (
            <p className="text-[11px] text-muted-foreground mt-1">
              Most common:{" "}
              {d.legacy.top.map((t, i) => (
                <span key={t.value}>{i > 0 && " · "}<span className="font-mono">{t.value}</span> ×{t.count.toLocaleString()}</span>
              ))}
            </p>
          )}
        </div>
      </>)}
    </section>
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
  const domains = useEnum("domain");
  // Handoff 46: creating, saving and deleting a category are `settings:write`
  // routes. Somebody who reaches this page without that scope sees the
  // categories, every field disabled, and one sentence where *New category*
  // would be — not three controls the server refuses.
  const scopes = useScopes();
  const readOnly = !scopes.has(SCOPE.settingsWrite);
  // Handoff 58: how a class is identified is also the Asset Controller's
  // (`settings:classes`), who may change those two columns and nothing else.
  const classLocked = readOnly && !scopes.has(SCOPE.settingsClasses);
  // Handoff 59 §3: the placeholder list is read with `settings:read` and
  // changed with `settings:write`; somebody with neither is not shown it.
  const placeholdersVisible = scopes.has(SCOPE.settingsRead) || !readOnly;

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
    mutationFn: ({ id, body }: { id: number; body: CategoryRowBody }) =>
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
    onSuccess: (d) => { setNote(`Deleted ${d.name}.`); refresh(); setDeleteOpen(false); },
    onSettled: () => setDeletingId(null),
  });
  const removeErr = remove.error as CadraApiError | null;

  // Deleting a category asked through `window.confirm` — the browser's own
  // dialog, which could show neither the pending state nor the server's
  // refusal. (The server refuses a category that holds assets. From THIS page
  // that is rare — the delete button is disabled whenever the count shown is
  // above zero — so the refusal is reached only when that count is stale; it
  // is drawn in the dialog when it happens.) `deleteTarget` outlives `deleteOpen` on purpose: the dialog fades
  // out after it closes, and clearing the name first blanks it mid-fade.
  const [deleteTarget, setDeleteTarget] = useState<AssetCategoryConfig | null>(null);
  const [deleteOpen, setDeleteOpenRaw] = useState(false);
  const setDeleteOpen = (next: boolean) => {
    // The refusal belongs to the attempt, not to the next category opened.
    if (!next) remove.reset();
    setDeleteOpenRaw(next);
  };

  // `remove.error` is shown inside the delete dialog, where the attempt was
  // made, and not a second time on the page behind it.
  const err = (categories.error ?? save.error ?? create.error) as CadraApiError | null;
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
        {readOnly ? (
          <p className="text-[11px] text-muted-foreground max-w-xs text-right" data-testid="settings-read-only">
            {classLocked
              ? "Changing this needs the settings:write scope."
              : "You can change how a class is identified, its SAP asset class and what a receipt of it must carry. Everything else here needs the settings:write scope."}
          </p>
        ) : (
          <button
            onClick={() => setAdding(v => !v)}
            disabled={busy}
            data-testid="button-add-category"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent disabled:opacity-40"
          >
            {adding ? <X size={12} /> : <Plus size={12} />} {adding ? "Cancel" : "New category"}
          </button>
        )}
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          {/* Which fields, in words, when the save was refused for naming one
              the API does not accept — see ApiErrorMessage. */}
          <ApiErrorMessage err={err} stacked />
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

      {!readOnly && adding && (
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
                {domains.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
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
        {/* AD-31: the mode a unit is RECEIVED under is fixed on the unit, so
            a change here never re-reads one already in the building. */}
        <p className="text-[11px] text-muted-foreground mb-3" data-testid="identification-note">
          <span className="font-medium text-foreground">Identification and mandatory attributes:</span>{" "}
          Changes apply to units received from now on; units already received keep the mode they arrived with.
        </p>
        {/* Handoff 59 §1. The hint is SAP's export, not a closed list. */}
        <p className="text-[11px] text-muted-foreground mb-3" data-testid="sap-class-note">
          <span className="font-medium text-foreground">SAP asset class:</span>{" "}
          SAP's four-digit code for the class. A unit whose class has none cannot be submitted to or approved onto
          the register, because SAP would reject its asset master. The classes SAP's own register for NRS uses:{" "}
          {SAP_ASSET_CLASS_HINTS.map((h, i) => (
            <span key={h.code}>{i > 0 && " · "}<span className="font-mono">{h.code}</span> {h.name}</span>
          ))}
          . The names are read off SAP's descriptions and need NRS to confirm; any four-digit code is accepted.
        </p>
        <datalist id={SAP_HINTS_ID}>
          {SAP_ASSET_CLASS_HINTS.map(h => <option key={h.code} value={h.code}>{h.name}</option>)}
        </datalist>
        <table className="w-full min-w-[1280px]">
          <thead>
            <tr className="text-left text-muted-foreground border-b border-border">
              <th className="py-2 text-[11px] font-medium">Name</th>
              <th className="py-2 text-[11px] font-medium">Code</th>
              <th className="py-2 text-[11px] font-medium">FM domain</th>
              <th className="py-2 text-[11px] font-medium">PM interval (days)</th>
              <th className="py-2 text-[11px] font-medium">Identification</th>
              <th className="py-2 text-[11px] font-medium">SAP class</th>
              <th className="py-2 text-[11px] font-medium">Mandatory attributes</th>
              <th className="py-2 text-[11px] font-medium text-right">Assets</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {(categories.data ?? []).map(c => (
              <Row
                key={c.id} cat={c} busy={busy}
                identityLocked={readOnly} classLocked={classLocked} fullEdit={!readOnly}
                saving={savingId === c.id}
                deleting={deletingId === c.id}
                onSave={(id, body) => { setSavingId(id); save.mutate({ id, body }); }}
                onDelete={(cat) => { setDeleteTarget(cat); setDeleteOpen(true); }}
              />
            ))}
          </tbody>
        </table>
        {!readOnly && (
          <p className="text-[10px] text-muted-foreground mt-3">
            A category holding assets cannot be deleted — reassign them first.
          </p>
        )}
      </section>

      {placeholdersVisible && <SerialPlaceholdersSection canEdit={!readOnly} />}

      <Dialog open={deleteOpen} onOpenChange={(next) => { if (!next && remove.isPending) return; setDeleteOpen(next); }}>
        <DialogContent className="sm:max-w-md" data-testid="dialog-delete-category">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
              <Trash2 size={16} /> Delete category
            </DialogTitle>
            <DialogDescription>
              Delete <span className="font-semibold text-foreground">"{deleteTarget?.name}"</span>? This cannot be undone.
            </DialogDescription>
          </DialogHeader>

          {removeErr && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-red-700 dark:text-red-400">
                <span className="font-semibold">{removeErr.code}:</span> {removeErr.message}
              </p>
            </div>
          )}

          <DialogFooter>
            <button
              type="button"
              onClick={() => setDeleteOpen(false)}
              className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!deleteTarget || remove.isPending}
              onClick={() => {
                if (!deleteTarget) return;
                setDeletingId(deleteTarget.id);
                remove.mutate(deleteTarget.id);
              }}
              data-testid="button-confirm-delete-category"
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl",
                deleteTarget && !remove.isPending
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              {remove.isPending ? <Loader2 size={12} className="animate-spin" /> : "Delete category"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
