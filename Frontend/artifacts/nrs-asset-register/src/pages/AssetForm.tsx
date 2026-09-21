/**
 * Asset create/edit form. Used by both AssetCreate (/assets/new) and AssetEdit
 * (/assets/:id/edit).
 *
 * The set of FIELDS here mirrors the _WRITABLE_FIELDS allow-list in
 * myservice_api/controllers/v1_assets.py. The set of VALUES each enum field may
 * hold is no longer mirrored here at all: `useEnum` reads it from the live Odoo
 * Selection via GET /api/v1/meta/enums. Three hand-written copies used to sit at
 * the top of this file and two of them were wrong — `LEVELS` had no `group`, so
 * opening a group-level asset showed a select with no matching option and
 * demoted the record to `asset` the moment anybody touched the dropdown, and
 * `domain` was not a select at all but a free-text box advertising `nrs.fcs`,
 * which is not one of the model's eight values and is not even the right shape.
 *
 * Note on category/subcategory/asset-type pickers: the API does not yet expose
 * list endpoints for these FK lookups, so the form takes integer FK ids directly
 * (advanced users / API-aware) rather than searchable names. Captured as a
 * backend gap; this page upgrades to typeahead pickers once those land.
 */
import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import RecordPicker from "@/components/RecordPicker";
import { fetchAsset, createAsset, updateAsset, type AssetWriteBody } from "@/lib/dataProvider";
import { apiGet, CadraApiError } from "@/lib/api";
import type { ApiLocation } from "@/lib/adapters";
import { ArrowLeft, AlertCircle, Loader2, Save } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEnum } from "@/hooks/useEnums";
import { ENUM_DEFAULT, withCurrent } from "@/lib/enums";


type FormShape = {
  name: string;
  asset_tag: string;
  legacy_asset_code: string;
  serial_number: string;
  make: string;
  model_name: string;
  manufacturer: string;
  asset_level: string;
  domain: string;
  department: string;
  // Deliberately `string`, not a union. The set these two draw from lives in
  // the Odoo model and is read at runtime, so a compile-time union here could
  // only ever restate a stale guess about it — which is what the deleted
  // `typeof CONDITIONS[number]` was.
  condition: string;
  state: string;
  // FK ids — stored as numbers when present
  category_id: number | null;
  subcategory_id: number | null;
  asset_type_id: number | null;
  parent_id: number | null;
  building_id: number | null;
  floor_id: number | null;
  room_id: number | null;
  location_id: number | null;
  custodian_id: number | null;
  maintenance_vendor_id: number | null;
  currency_id: number | null;
  // dates
  purchase_date: string;
  warranty_expiry: string;
  acquisition_date: string;
  // numbers
  purchase_value: string;
  replacement_cost: string;
  acquisition_cost: string;
  current_value: string;
  notes: string;
};

// The model's own defaults, by VALUE, out of ENUM_DEFAULT — not restated here
// and not taken as "the first option in the list". `?? ""` is the unset case,
// which toBody drops so the server applies whatever it considers default.
const blank: FormShape = {
  name: "", asset_tag: "", legacy_asset_code: "", serial_number: "",
  make: "", model_name: "", manufacturer: "",
  asset_level: ENUM_DEFAULT.asset_level, domain: "", department: "",
  condition: ENUM_DEFAULT.condition, state: ENUM_DEFAULT.asset_state,
  category_id: null, subcategory_id: null, asset_type_id: null,
  parent_id: null, building_id: null, floor_id: null, room_id: null,
  location_id: null, custodian_id: null, maintenance_vendor_id: null, currency_id: null,
  purchase_date: "", warranty_expiry: "", acquisition_date: "",
  purchase_value: "", replacement_cost: "", acquisition_cost: "", current_value: "",
  notes: "",
};

// Drop empty strings + null FK ids before POSTing — let the server keep its
// defaults rather than wiping fields with empty values.
function toBody(f: FormShape): AssetWriteBody {
  const out: AssetWriteBody = {};
  const assignIfSet = <K extends keyof AssetWriteBody>(key: K, val: AssetWriteBody[K]) => {
    if (val === "" || val === null || val === undefined) return;
    out[key] = val;
  };
  assignIfSet("name", f.name);
  // `asset_tag` is NOT sent, on create or on edit. The server leaves it out of
  // `_WRITABLE_FIELDS` on purpose (`v1_assets.py`: a client able to write it
  // can walk the record away from the sticker on the asset), and both POST and
  // PATCH run the body through the same `_filter_writable`. So it was dropped
  // and named in `_warnings.rejected_fields`, which nothing here reads: typing
  // a tag gave a 200, no change and no message. Cadra mints the tag itself
  // when the asset is created; the input below is read-only and says so.
  assignIfSet("legacy_asset_code", f.legacy_asset_code);
  assignIfSet("serial_number", f.serial_number);
  assignIfSet("make", f.make);
  assignIfSet("model_name", f.model_name);
  assignIfSet("manufacturer", f.manufacturer);
  assignIfSet("asset_level", f.asset_level);
  assignIfSet("domain", f.domain);
  assignIfSet("department", f.department);
  // Posted through assignIfSet like everything else now that their defaults
  // come from ENUM_DEFAULT rather than a literal: if that map ever loses a key
  // the field arrives here as "", and "" is not a member of either Selection —
  // the server would refuse the whole write.
  //
  // The two casts that used to sit here are gone: `AssetWriteBody` narrowed
  // `condition` and `state` to hand-written unions, and that narrowing has
  // been widened to the model's keys, so there is nothing left to cast past.
  assignIfSet("condition", f.condition);
  assignIfSet("state", f.state);
  assignIfSet("category_id", f.category_id);
  assignIfSet("subcategory_id", f.subcategory_id);
  assignIfSet("asset_type_id", f.asset_type_id);
  assignIfSet("parent_id", f.parent_id);
  assignIfSet("building_id", f.building_id);
  assignIfSet("floor_id", f.floor_id);
  assignIfSet("room_id", f.room_id);
  assignIfSet("location_id", f.location_id);
  assignIfSet("custodian_id", f.custodian_id);
  assignIfSet("maintenance_vendor_id", f.maintenance_vendor_id);
  assignIfSet("currency_id", f.currency_id);
  assignIfSet("purchase_date", f.purchase_date);
  assignIfSet("warranty_expiry", f.warranty_expiry);
  assignIfSet("acquisition_date", f.acquisition_date);
  assignIfSet("notes", f.notes);
  // Numbers come from text inputs — parse and skip if NaN.
  const parseNum = (s: string) => (s === "" ? null : Number(s));
  for (const k of ["purchase_value", "replacement_cost", "acquisition_cost", "current_value"] as const) {
    const v = parseNum(f[k]);
    if (v !== null && Number.isFinite(v)) out[k] = v;
  }
  return out;
}

// ─── Pickers (typeahead via API search) ───────────────────────────────────

interface ApiEmployeeRef { id: number; name: string; ir_number: string | null; job_title: string | null; }

const searchLocations = async (q: string) => {
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", { q, limit: 10 });
  return res.data.map(l => ({
    id: l.id,
    label: l.name,
    sublabel: [l.address?.city, l.address?.state?.name].filter(Boolean).join(" · ") || undefined,
  }));
};

const searchEmployees = async (q: string) => {
  const res = await apiGet<ApiEmployeeRef[]>("/api/v1/identity/employees", { q, limit: 10 });
  return res.data.map(e => ({
    id: e.id,
    label: e.name,
    sublabel: [e.ir_number, e.job_title].filter(Boolean).join(" · ") || undefined,
  }));
};

// ─── form layout helpers ──────────────────────────────────────────────────

function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: 1 | 2 }) {
  return (
    <div className={cn("flex flex-col gap-1.5", span === 2 && "sm:col-span-2")}>
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "px-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
      <div>
        <h2 className="text-[13px] font-bold text-foreground">{title}</h2>
        {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">{children}</div>
    </div>
  );
}

// ─── main form ────────────────────────────────────────────────────────────

interface Props {
  mode: "create" | "edit";
}

export default function AssetForm({ mode }: Props) {
  const params = useParams<{ id: string }>();
  const id = mode === "edit" ? params.id : undefined;
  const [, nav] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();

  const [form, setForm] = useState<FormShape>(blank);
  const set = <K extends keyof FormShape>(k: K, v: FormShape[K]) => setForm(s => ({ ...s, [k]: v }));

  // Read once, here. These are hooks, so they cannot be called from inside the
  // .map()s that consume them further down. `state` is published as
  // "asset_state" — a bare "state" key would collide with the several other
  // models in the schema that have a field of that name.
  const levelOptions     = useEnum("asset_level");
  const domainOptions    = useEnum("domain");
  const conditionOptions = useEnum("condition");
  const stateOptions     = useEnum("asset_state");

  // Selected-pickers state (display + id)
  const [locPick, setLocPick] = useState<{ id: number; label: string } | null>(null);
  const [custPick, setCustPick] = useState<{ id: number; label: string } | null>(null);

  // Load existing asset for edit mode using the raw ApiAsset so we can hydrate
  // the FK ids (the mapped Asset type strips them).
  const existing = useQuery({
    queryKey: ["asset-raw", id],
    queryFn: async () => {
      const res = await apiGet<Record<string, unknown>>(`/api/v1/assets/${id}`);
      return res.data;
    },
    enabled: mode === "edit" && !!id,
    // THIS FORM NEVER HYDRATES FROM A CACHED COPY. It sends `state` and
    // `condition` on every save, so a stale copy is not untidy, it is
    // destructive: acted in handoff 29 — open Edit once, mark the asset
    // missing, open Edit again, and the State select read *Active*; saving
    // any field would have written `active` back with a 200 and un-missed
    // the asset. And the Mark-missing dialog SENDS people here to reverse it.
    // `gcTime: 0` drops the copy when the form closes, `"always"` refetches
    // whatever is left, and the effect below waits for THAT fetch.
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
  });

  useEffect(() => {
    if (mode === "create") {
      setTitle("New Asset");
    } else if (existing.data && existing.isFetchedAfterMount) {
      const e = existing.data as Record<string, unknown>;
      const ref = (v: unknown) => (v && typeof v === "object" && "id" in v ? (v as { id: number }).id : null);
      const refName = (v: unknown) => (v && typeof v === "object" && "name" in v ? (v as { id: number; name: string }) : null);
      setForm({
        name: (e.name as string) ?? "",
        asset_tag: (e.tag as string) ?? "",
        legacy_asset_code: (e.legacy_asset_code as string) ?? "",
        serial_number: (e.serial_number as string) ?? "",
        make: (e.make as string) ?? "",
        model_name: (e.model as string) ?? "",
        manufacturer: (e.manufacturer as string) ?? "",
        // Taken verbatim. A stored value this build does not recognise is kept
        // rather than coerced to a default — withCurrent() puts it in the
        // select so the user can save the record back untouched.
        asset_level: (e.asset_level as string) ?? ENUM_DEFAULT.asset_level,
        domain: (e.domain as string) ?? "",
        department: (e.department as string) ?? "",
        condition: (e.condition as string) ?? ENUM_DEFAULT.condition,
        state: (e.state as string) ?? ENUM_DEFAULT.asset_state,
        category_id: ref(e.category),
        subcategory_id: ref(e.subcategory),
        asset_type_id: ref(e.asset_type),
        parent_id: ref(e.parent_asset),
        building_id: ref((e.location_hierarchy as Record<string, unknown> | null)?.building),
        floor_id: ref((e.location_hierarchy as Record<string, unknown> | null)?.floor),
        room_id: ref((e.location_hierarchy as Record<string, unknown> | null)?.room),
        location_id: ref(e.current_location),
        custodian_id: ref(e.current_custodian),
        maintenance_vendor_id: ref(e.maintenance_vendor),
        currency_id: ref((e.financial as Record<string, unknown> | null)?.currency),
        purchase_date: ((e.dates as Record<string, string | null> | null)?.purchase_date) ?? "",
        warranty_expiry: ((e.dates as Record<string, string | null> | null)?.warranty_expiry) ?? "",
        acquisition_date: ((e.dates as Record<string, string | null> | null)?.acquisition_date) ?? "",
        purchase_value: String(((e.financial as Record<string, unknown> | null)?.purchase_value) ?? ""),
        replacement_cost: String(((e.financial as Record<string, unknown> | null)?.replacement_cost) ?? ""),
        acquisition_cost: String(((e.financial as Record<string, unknown> | null)?.acquisition_cost) ?? ""),
        current_value: String(((e.financial as Record<string, unknown> | null)?.current_value) ?? ""),
        notes: (e.notes as string) ?? "",
      });
      const loc = refName(e.current_location);
      const cust = refName(e.current_custodian);
      if (loc) setLocPick({ id: loc.id, label: loc.name });
      if (cust) setCustPick({ id: cust.id, label: cust.name });
      setTitle(`Edit · ${e.name as string}`);
    }
    setSearchHandler(undefined);
  }, [mode, existing.data, existing.isFetchedAfterMount, setTitle, setSearchHandler]);

  const mutation = useMutation({
    mutationFn: () => mode === "edit" ? updateAsset(id!, toBody(form)) : createAsset(toBody(form)),
    onSuccess: (asset) => {
      qc.invalidateQueries({ queryKey: ["assets"] });
      qc.invalidateQueries({ queryKey: ["asset", asset.id] });
      qc.invalidateQueries({ queryKey: ["asset-history", asset.id] });
      qc.invalidateQueries({ queryKey: ["asset-raw", asset.id] });
      nav(`/assets/${asset.id}`);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Keep picker state in sync with the underlying form FK ids.
  useEffect(() => { set("location_id", locPick?.id ?? null); }, [locPick]);
  useEffect(() => { set("custodian_id", custPick?.id ?? null); }, [custPick]);

  const heading = mode === "create" ? "New asset" : "Edit asset";

  return (
    <div className="max-w-4xl mx-auto px-5 py-5 space-y-5">
      <button
        onClick={() => nav(mode === "edit" && id ? `/assets/${id}` : "/assets")}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={13} /> {mode === "edit" ? "Back to asset" : "Back to register"}
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{heading}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => nav(mode === "edit" && id ? `/assets/${id}` : "/assets")}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.name.trim()}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl",
              form.name.trim() && !mutation.isPending
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {mode === "edit" ? "Save changes" : "Create asset"}
          </button>
        </div>
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

      <Section title="Identity" sub="Tags and basic identifiers">
        <Field label="Name" span={2}>
          <input className={inputCls} value={form.name} onChange={e => set("name", e.target.value)} required />
        </Field>
        <Field label="Asset tag">
          <input
            className={cn(inputCls, "bg-muted/50 text-muted-foreground cursor-not-allowed")}
            value={form.asset_tag}
            readOnly
            aria-readonly="true"
            placeholder={mode === "create" ? "Issued when the asset is saved" : "No tag issued"}
            data-testid="input-asset-tag"
          />
          <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-asset-tag">
            {mode === "create"
              ? "Cadra issues the tag when the asset is saved. It cannot be typed here, so the register cannot drift from the sticker on the asset."
              : "A tag changes only through tag replacement, so the register cannot drift from the sticker on the asset."}
          </p>
        </Field>
        <Field label="Legacy code">
          <input className={inputCls} value={form.legacy_asset_code} onChange={e => set("legacy_asset_code", e.target.value)} />
        </Field>
        <Field label="Serial number">
          <input className={inputCls} value={form.serial_number} onChange={e => set("serial_number", e.target.value)} />
        </Field>
        <Field label="Manufacturer">
          <input className={inputCls} value={form.manufacturer} onChange={e => set("manufacturer", e.target.value)} />
        </Field>
        <Field label="Make">
          <input className={inputCls} value={form.make} onChange={e => set("make", e.target.value)} />
        </Field>
        <Field label="Model">
          <input className={inputCls} value={form.model_name} onChange={e => set("model_name", e.target.value)} />
        </Field>
      </Section>

      <Section title="Classification" sub="FK ids only for now — picker endpoints not yet in API">
        <Field label="Category id">
          <input className={inputCls} type="number" value={form.category_id ?? ""} onChange={e => set("category_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Subcategory id">
          <input className={inputCls} type="number" value={form.subcategory_id ?? ""} onChange={e => set("subcategory_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Asset type id">
          <input className={inputCls} type="number" value={form.asset_type_id ?? ""} onChange={e => set("asset_type_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Asset level">
          <select className={inputCls} value={form.asset_level} onChange={e => set("asset_level", e.target.value)}>
            {withCurrent(levelOptions, form.asset_level).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Domain">
          {/* Was a text input. `domain` is a Selection related onto
              nrs.asset.category.domain with eight members, so every free-text
              entry that was not one of the eight was refused by the server —
              including the one the placeholder suggested. The blank entry is
              real: the field has no model default and an uncategorised asset
              legitimately has none. */}
          <select className={inputCls} value={form.domain} onChange={e => set("domain", e.target.value)}>
            <option value="">— None —</option>
            {withCurrent(domainOptions, form.domain).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Department">
          <input className={inputCls} value={form.department} onChange={e => set("department", e.target.value)} placeholder="e.g. Tax Operations" />
        </Field>
        <Field label="Parent asset id">
          <input className={inputCls} type="number" value={form.parent_id ?? ""} onChange={e => set("parent_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </Section>

      <Section title="Location & custody">
        <Field label="Current location" span={2}>
          <RecordPicker value={locPick} onChange={setLocPick} search={searchLocations} queryKey="form-locations" placeholder="Search locations…" />
        </Field>
        <Field label="Current custodian" span={2}>
          <RecordPicker value={custPick} onChange={setCustPick} search={searchEmployees} queryKey="form-employees" placeholder="Search employees…" />
        </Field>
      </Section>

      <Section title="Condition & state">
        <Field label="Condition">
          <select className={inputCls} value={form.condition} onChange={e => set("condition", e.target.value)}>
            {withCurrent(conditionOptions, form.condition).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="State">
          {/* These two matched the model's values, but displayed the raw keys:
              "in_repair" where the model says "Under Repair". The label is the
              model's now, along with the set. */}
          <select className={inputCls} value={form.state} onChange={e => set("state", e.target.value)}>
            {withCurrent(stateOptions, form.state).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
      </Section>

      <Section title="Financials & dates">
        <Field label="Currency id">
          <input className={inputCls} type="number" value={form.currency_id ?? ""} onChange={e => set("currency_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Purchase value">
          <input className={inputCls} type="number" step="0.01" value={form.purchase_value} onChange={e => set("purchase_value", e.target.value)} />
        </Field>
        <Field label="Replacement cost">
          <input className={inputCls} type="number" step="0.01" value={form.replacement_cost} onChange={e => set("replacement_cost", e.target.value)} />
        </Field>
        <Field label="Acquisition cost">
          <input className={inputCls} type="number" step="0.01" value={form.acquisition_cost} onChange={e => set("acquisition_cost", e.target.value)} />
        </Field>
        <Field label="Current value">
          <input className={inputCls} type="number" step="0.01" value={form.current_value} onChange={e => set("current_value", e.target.value)} />
        </Field>
        <Field label="Purchase date">
          <input className={inputCls} type="date" value={form.purchase_date} onChange={e => set("purchase_date", e.target.value)} />
        </Field>
        <Field label="Warranty expiry">
          <input className={inputCls} type="date" value={form.warranty_expiry} onChange={e => set("warranty_expiry", e.target.value)} />
        </Field>
        <Field label="Acquisition date">
          <input className={inputCls} type="date" value={form.acquisition_date} onChange={e => set("acquisition_date", e.target.value)} />
        </Field>
        <Field label="Maintenance vendor id">
          <input className={inputCls} type="number" value={form.maintenance_vendor_id ?? ""} onChange={e => set("maintenance_vendor_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </Section>

      <Section title="Notes">
        <Field label="Internal notes" span={2}>
          <textarea className={inputCls} rows={4} value={form.notes} onChange={e => set("notes", e.target.value)} />
        </Field>
      </Section>
    </div>
  );
}
