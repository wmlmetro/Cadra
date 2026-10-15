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
import { createAsset, updateAsset, fetchAssetCategories, type AssetWriteBody } from "@/lib/dataProvider";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import { apiGet, CadraApiError } from "@/lib/api";
import type { ApiLocation } from "@/lib/adapters";
import { ArrowLeft, AlertCircle, Loader2, Save } from "lucide-react";
import { cn, addMonthsIso, formatIsoDate } from "@/lib/utils";
import { useEnum } from "@/hooks/useEnums";
import { ENUM_DEFAULT, withCurrent } from "@/lib/enums";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import { useScopes, SCOPE } from "@/hooks/use-scopes";


type FormShape = {
  name: string;
  asset_tag: string;
  legacy_asset_code: string;
  serial_number: string;
  make: string;
  model_name: string;
  manufacturer: string;
  // Section 12 (handoff 58): what a unit with no manufacturer serial — a
  // `tag_id` class, furniture — is identified by at receipt.
  colour: string;
  material: string;
  dimensions: string;
  // Handoff 59 §2: what a `record_only` unit — land, a building, a licence —
  // is identified by instead of a serial: title or plot number, licence key,
  // contract.
  record_reference: string;
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
  // No building / floor / room. This form has never had an input for any of
  // them, and until handoff 30 it hydrated all three from
  // `location_hierarchy` and sent them back on every save — three fields the
  // user never saw, echoed into every PATCH. They left `_WRITABLE_FIELDS` in
  // that handoff, where the echo would have raised a warning on every edit of
  // every located asset. Since handoff 31 it would do worse: a key the route
  // does not accept is a 400, so every such edit would save nothing at all.
  // e2e/tests/18-rejected-fields.spec.ts holds this form's body to the live
  // allow-list for that reason.
  location_id: number | null;
  custodian_id: number | null;
  maintenance_vendor_id: number | null;
  currency_id: number | null;
  // dates
  purchase_date: string;
  acquisition_date: string;
  // Warranty (handoff 34). A DURATION and a start date, from which the server
  // derives the expiry — that is how a warranty is quoted, and a computed
  // date cannot be mistyped. `warranty_expiry` here is ONLY the fallback for
  // a warranty whose duration nobody knows; it is never loaded with a derived
  // date, and never sent while a duration is filled in.
  warranty_months: string;
  warranty_start_date: string;
  warrantor: string;
  warranty_reference: string;
  warranty_expiry: string;
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
  colour: "", material: "", dimensions: "", record_reference: "",
  asset_level: ENUM_DEFAULT.asset_level, domain: "", department: "",
  condition: ENUM_DEFAULT.condition, state: ENUM_DEFAULT.asset_state,
  category_id: null, subcategory_id: null, asset_type_id: null,
  parent_id: null,
  location_id: null, custodian_id: null, maintenance_vendor_id: null, currency_id: null,
  purchase_date: "", acquisition_date: "",
  warranty_months: "", warranty_start_date: "", warrantor: "", warranty_reference: "", warranty_expiry: "",
  purchase_value: "", replacement_cost: "", acquisition_cost: "", current_value: "",
  notes: "",
};

// Drop empty strings + null FK ids before POSTing — let the server keep its
// defaults rather than wiping fields with empty values.
//
// `terminal` is a DISPOSED asset. Its state, location and custodian are left
// out of the body altogether: the model refuses a change to any of the three
// (handoff 30 §B), the form does not let them be changed, and a field that
// cannot change has no business in a PATCH. Re-sending the same values would
// also be accepted — this is the narrower of two correct bodies, not a
// workaround.
//
// `original` is the form as it was hydrated in edit mode. The warranty keys
// are the one place this form CLEARS a value: dropping an empty field keeps
// the server's copy, which for a warranty would make one impossible to take
// off. So a warranty field that was filled when the form opened and is empty
// now is sent as `null`; one that was empty and still is, is not sent at all.
//
// `recordOnly` is a unit of a `record_only` class (handoff 59): it has no
// serial, and the server refuses a receipt that carries one, so a serial typed
// before the class was chosen is not sent.
function toBody(f: FormShape, terminal = false, original?: FormShape | null, recordOnly = false): AssetWriteBody {
  const out: AssetWriteBody = {};
  const assignIfSet = <K extends keyof AssetWriteBody>(key: K, val: AssetWriteBody[K]) => {
    if (val === "" || val === null || val === undefined) return;
    out[key] = val;
  };
  assignIfSet("name", f.name);
  // `asset_tag` is NOT sent, on create or on edit. The server leaves it out of
  // `_WRITABLE_FIELDS` on purpose (`v1_assets.py`: a client able to write it
  // can walk the record away from the sticker on the asset), and both POST and
  // PATCH run the body through the same `_filter_writable`. It used to be
  // dropped and named in `_warnings.rejected_fields`, which at the time
  // NOTHING read: typing a tag gave a 200, no change and no message. Since
  // handoff 31 sending it would be a 400 that refuses the WHOLE save, over a
  // field the user was never able to type — and `AssetWriteBody` no longer
  // declares it, so this function could not send it if it tried. Cadra mints
  // the tag itself when the asset is created; the input below is read-only
  // and says so.
  assignIfSet("legacy_asset_code", f.legacy_asset_code);
  if (!recordOnly) assignIfSet("serial_number", f.serial_number);
  assignIfSet("make", f.make);
  assignIfSet("model_name", f.model_name);
  assignIfSet("manufacturer", f.manufacturer);
  assignIfSet("colour", f.colour);
  assignIfSet("material", f.material);
  assignIfSet("dimensions", f.dimensions);
  assignIfSet("record_reference", f.record_reference.trim());
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
  if (!terminal) assignIfSet("state", f.state);
  assignIfSet("category_id", f.category_id);
  assignIfSet("subcategory_id", f.subcategory_id);
  assignIfSet("asset_type_id", f.asset_type_id);
  assignIfSet("parent_id", f.parent_id);
  if (!terminal) {
    assignIfSet("location_id", f.location_id);
    assignIfSet("custodian_id", f.custodian_id);
  }
  assignIfSet("maintenance_vendor_id", f.maintenance_vendor_id);
  assignIfSet("currency_id", f.currency_id);
  assignIfSet("purchase_date", f.purchase_date);
  assignIfSet("acquisition_date", f.acquisition_date);
  // Warranty. A filled field is sent; a field emptied since the form opened
  // is sent as null so it actually clears.
  const assignOrClear = <K extends keyof AssetWriteBody>(
    key: K, formKey: keyof FormShape, val: AssetWriteBody[K],
  ) => {
    if (val !== "" && val !== null && val !== undefined) out[key] = val;
    else if (original && original[formKey] !== "") out[key] = null as AssetWriteBody[K];
  };
  const months = f.warranty_months.trim() === "" ? null : Number(f.warranty_months);
  assignOrClear("warranty_months", "warranty_months", months);
  assignOrClear("warranty_start_date", "warranty_start_date", f.warranty_start_date);
  assignOrClear("warrantor", "warrantor", f.warrantor.trim());
  assignOrClear("warranty_reference", "warranty_reference", f.warranty_reference.trim());
  // `warranty_expiry` is NOT named while a duration is being given: the
  // server derives it from months + start and refuses one that disagrees, and
  // emptying months + start in a write that does not name it clears the
  // derived date too. Only with no duration at all is the bare date sent.
  if (f.warranty_months.trim() === "" && f.warranty_start_date === "") {
    assignOrClear("warranty_expiry", "warranty_expiry", f.warranty_expiry);
  }
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
  const scopes = useScopes();

  const [form, setForm] = useState<FormShape>(blank);
  // The form as the server sent it, for `toBody` to tell a cleared warranty
  // field from one that was never filled. Null in create mode.
  const [original, setOriginal] = useState<FormShape | null>(null);
  // The warranty start was filled in from the purchase date, not typed. Said
  // beside the field until somebody changes it.
  const [startFromPurchase, setStartFromPurchase] = useState(false);
  // The expiry-date-only input is secondary, and folded away unless the
  // record already holds a bare date.
  const [showExpiryOnly, setShowExpiryOnly] = useState(false);
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
      // The warranty block when the server sends one; the bare
      // `dates.warranty_expiry` from a server that predates it. A derived
      // expiry is NOT put in the expiry-only input — it is the answer to the
      // duration above it, and would otherwise be sent back as a second,
      // competing statement of the same date.
      const w = (e.warranty as Record<string, string | number | null> | null | undefined) ?? null;
      const wMonths = w?.warranty_months != null ? String(w.warranty_months) : "";
      const wStart = (w?.warranty_start_date as string | null) ?? "";
      const wExpiryOnly = w
        ? (wMonths || wStart ? "" : ((w.warranty_expiry as string | null) ?? ""))
        : (((e.dates as Record<string, string | null> | null)?.warranty_expiry) ?? "");
      const hydrated: FormShape = {
        name: (e.name as string) ?? "",
        asset_tag: (e.tag as string) ?? "",
        legacy_asset_code: (e.legacy_asset_code as string) ?? "",
        serial_number: (e.serial_number as string) ?? "",
        make: (e.make as string) ?? "",
        model_name: (e.model as string) ?? "",
        manufacturer: (e.manufacturer as string) ?? "",
        colour: (e.colour as string) ?? "",
        material: (e.material as string) ?? "",
        dimensions: (e.dimensions as string) ?? "",
        record_reference: (e.record_reference as string) ?? "",
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
        location_id: ref(e.current_location),
        custodian_id: ref(e.current_custodian),
        maintenance_vendor_id: ref(e.maintenance_vendor),
        currency_id: ref((e.financial as Record<string, unknown> | null)?.currency),
        purchase_date: ((e.dates as Record<string, string | null> | null)?.purchase_date) ?? "",
        warranty_months: wMonths,
        warranty_start_date: wStart,
        warrantor: (w?.warrantor as string | null) ?? "",
        warranty_reference: (w?.warranty_reference as string | null) ?? "",
        warranty_expiry: wExpiryOnly,
        acquisition_date: ((e.dates as Record<string, string | null> | null)?.acquisition_date) ?? "",
        purchase_value: String(((e.financial as Record<string, unknown> | null)?.purchase_value) ?? ""),
        replacement_cost: String(((e.financial as Record<string, unknown> | null)?.replacement_cost) ?? ""),
        acquisition_cost: String(((e.financial as Record<string, unknown> | null)?.acquisition_cost) ?? ""),
        current_value: String(((e.financial as Record<string, unknown> | null)?.current_value) ?? ""),
        notes: (e.notes as string) ?? "",
      };
      setForm(hydrated);
      setOriginal(hydrated);
      setShowExpiryOnly(!!wExpiryOnly);
      const loc = refName(e.current_location);
      const cust = refName(e.current_custodian);
      if (loc) setLocPick({ id: loc.id, label: loc.name });
      if (cust) setCustPick({ id: cust.id, label: cust.name });
      setTitle(`Edit · ${e.name as string}`);
    }
    setSearchHandler(undefined);
  }, [mode, existing.data, existing.isFetchedAfterMount, setTitle, setSearchHandler]);

  // DISPOSED IS TERMINAL — read off the RECORD as the server just sent it, not
  // off the select, which the user can move. The rule is the model's
  // (`nrs.asset.write` refuses a change of status, location or custodian on a
  // disposed asset, for every writer); this form only declines to OFFER what
  // would be refused, and says why beside each control. Were it ever wrong —
  // a record disposed of by somebody else between load and save — the
  // server's own sentence lands in the error panel below, as any refusal does.
  const isDisposed = mode === "edit"
    && existing.isFetchedAfterMount
    && (existing.data as Record<string, unknown> | undefined)?.state === "disposed";

  // How the chosen class is identified (handoff 59): a `record_only` class
  // has no serial — the field is withdrawn and the reference required. Read
  // from the category list; while it is unread nothing is withdrawn, and the
  // server's refusal still lands in the panel below.
  const categories = useQuery({
    queryKey: ["asset-categories"],
    queryFn: fetchAssetCategories,
    staleTime: 10 * 60_000,
  });
  const chosenCategory = (categories.data ?? []).find(c => c.id === form.category_id);
  const recordOnly = chosenCategory?.identification_mode === "record_only";
  const referenceMissing = recordOnly && mode === "create" && !form.record_reference.trim();

  const mutation = useMutation({
    mutationFn: () => mode === "edit"
      ? updateAsset(id!, toBody(form, isDisposed, original, recordOnly))
      : createAsset(toBody(form, false, null, recordOnly)),
    onSuccess: (asset) => {
      // The shared list, not a shorter one of this form's own. This form can
      // change `state` — it is how a missing asset is put back — so a save
      // here moves the register's counts and the dashboard's as surely as
      // Mark missing does, and its own list refreshed neither.
      invalidateAssetQueries(qc, asset.id);
      nav(`/assets/${asset.id}`);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Keep picker state in sync with the underlying form FK ids.
  useEffect(() => { set("location_id", locPick?.id ?? null); }, [locPick]);
  useEffect(() => { set("custodian_id", custPick?.id ?? null); }, [custPick]);

  const heading = mode === "create" ? "New asset" : "Edit asset";

  // ─── warranty, as the storekeeper reads it ───
  const monthsNum = form.warranty_months.trim() === "" ? null : Number(form.warranty_months);
  const monthsValid = monthsNum !== null && Number.isInteger(monthsNum) && monthsNum >= 1 && monthsNum <= 600;
  const hasDuration = form.warranty_months.trim() !== "" || form.warranty_start_date !== "";
  // Calendar months, clamped to the month's end — the server's own
  // arithmetic, so the date shown is the date it will store.
  const computedExpiry = monthsValid && form.warranty_start_date
    ? addMonthsIso(form.warranty_start_date, monthsNum!)
    : null;
  const setWarrantyMonths = (v: string) => {
    // Offer the purchase date as the start — VISIBLY, in the field, with a
    // line saying where it came from. Never sent without being shown.
    if (v.trim() !== "" && form.warranty_start_date === "" && form.purchase_date) {
      setStartFromPurchase(true);
      setForm(s => ({ ...s, warranty_months: v, warranty_start_date: s.purchase_date }));
    } else {
      set("warranty_months", v);
    }
  };

  // Handoff 46: this page's one purpose is `POST /assets` or
  // `PATCH /assets/<id>`, both `assets:write`. Reached by URL without it, the
  // page says so instead of drawing a form whose save the server refuses.
  // After every hook, so the hook order never depends on the token.
  if (!scopes.has(SCOPE.assetsWrite)) {
    return <ScopeRefusal scope={SCOPE.assetsWrite} detail="Registering and editing assets is done by the people who hold it — an Asset Manager among them." />;
  }

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
            disabled={mutation.isPending || !form.name.trim() || referenceMissing}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl",
              form.name.trim() && !referenceMissing && !mutation.isPending
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
          {/* Which fields, in words, when the save was refused for naming one
              the API does not accept — see ApiErrorMessage. */}
          <ApiErrorMessage err={err} stacked />
        </div>
      )}

      {isDisposed && (
        <div
          className="bg-slate-100 dark:bg-slate-800/60 border border-slate-300/80 dark:border-slate-600/60 rounded-2xl p-4"
          data-testid="form-disposed-notice"
          role="note"
        >
          <p className="text-[12px] text-slate-800 dark:text-slate-200">
            <span className="font-semibold">This asset has been disposed of, and disposal is the end of an asset's record.</span>{" "}
            Its state, location and custodian are fixed as they were when it was disposed of, so they are shown here and cannot be changed.
            Everything else on this form can still be corrected.
          </p>
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
          <input
            className={cn(inputCls, recordOnly && "bg-muted/50 text-muted-foreground cursor-not-allowed")}
            value={recordOnly ? "" : form.serial_number}
            onChange={e => set("serial_number", e.target.value)}
            disabled={recordOnly}
            placeholder={recordOnly ? "None — identified by its record" : undefined}
            data-testid="input-serial-number"
          />
          {recordOnly && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-serial-record-only">
              {chosenCategory!.name} is identified by its SAP record, not by a serial or a label, so no serial is taken.
              Give its reference instead.
            </p>
          )}
        </Field>
        <Field label={recordOnly ? "Reference (required)" : "Reference"}>
          <input className={inputCls} value={form.record_reference} onChange={e => set("record_reference", e.target.value)}
                 placeholder="Title or plot number, licence key, contract" data-testid="input-reference" />
          {referenceMissing && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-reference-required">
              Required for {chosenCategory!.name}: it is what this asset is known by.
            </p>
          )}
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
        {/* Section 12 (handoff 58): mandatory at a gated receipt for a class
            identified by tag and attributes — the categories screen says
            which. */}
        <Field label="Colour">
          <input className={inputCls} data-testid="input-colour" value={form.colour} onChange={e => set("colour", e.target.value)} />
        </Field>
        <Field label="Material">
          <input className={inputCls} data-testid="input-material" value={form.material} onChange={e => set("material", e.target.value)} />
        </Field>
        <Field label="Dimensions">
          <input className={inputCls} data-testid="input-dimensions" value={form.dimensions} onChange={e => set("dimensions", e.target.value)} />
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
          <RecordPicker value={locPick} onChange={setLocPick} search={searchLocations} queryKey="form-locations"
                        placeholder={isDisposed ? "No location recorded" : "Search locations…"} disabled={isDisposed} />
          {isDisposed && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-disposed-location">
              A disposed asset cannot be moved. Its record keeps the location it was disposed of from.
            </p>
          )}
        </Field>
        <Field label="Current custodian" span={2}>
          <RecordPicker value={custPick} onChange={setCustPick} search={searchEmployees} queryKey="form-employees"
                        placeholder={isDisposed ? "No custodian recorded" : "Search employees…"} disabled={isDisposed} />
          {isDisposed && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-disposed-custodian">
              A disposed asset cannot change custodian. Its record keeps whoever held it when it was disposed of.
            </p>
          )}
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
          {/* On a disposed asset the ONLY option is the one it holds, and the
              select is off. Offering the other four would be offering four
              saves the server refuses. */}
          <select
            className={cn(inputCls, isDisposed && "bg-muted/50 text-muted-foreground cursor-not-allowed")}
            value={form.state}
            onChange={e => set("state", e.target.value)}
            disabled={isDisposed}
            data-testid="select-asset-state"
          >
            {withCurrent(stateOptions, form.state)
              .filter(o => !isDisposed || o.value === form.state)
              // Editing a LIVE asset does not offer "Disposed". Since handoff
              // 30 disposal is terminal, so this option had become a one-way
              // door in a dropdown: no confirmation and no reason. (It also
              // left no disposal date, a PATCH being a plain write; since
              // handoff 31 the model dates a disposal and sets the condition
              // through ANY door — `_stamp_disposal` — so that half is cured
              // on the server. The missing reason and the mis-click are not,
              // and they are why this stays off.) Until handoff 30 a
              // mis-click was undone from this same select. Disposal has a
              // door of its own, Condemn, which asks why. Registering an
              // asset that is ALREADY gone is a different act and is still
              // offered on create — where the model stamps no date, because
              // it was not disposed of today.
              .filter(o => mode !== "edit" || isDisposed || o.value !== "disposed")
              .map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {isDisposed && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-disposed-state">
              A disposed asset's state cannot be changed — it cannot be marked missing, put under repair or returned to service.
            </p>
          )}
          {mode === "edit" && !isDisposed && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-dispose-elsewhere">
              To dispose of this asset use Condemn on its page. It asks for a reason, and it cannot be undone.
            </p>
          )}
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
        <Field label="Acquisition date">
          <input className={inputCls} type="date" value={form.acquisition_date} onChange={e => set("acquisition_date", e.target.value)} />
        </Field>
        <Field label="Maintenance vendor id">
          <input className={inputCls} type="number" value={form.maintenance_vendor_id ?? ""} onChange={e => set("maintenance_vendor_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </Section>

      <Section title="Warranty" sub="Optional. Most assets have none, and that is recorded as no warranty — not as expired.">
        <Field label="Duration (months)">
          <input className={inputCls} type="number" min={1} max={600} step={1} inputMode="numeric"
                 value={form.warranty_months} onChange={e => setWarrantyMonths(e.target.value)}
                 placeholder="e.g. 24" data-testid="input-warranty-months" />
          {form.warranty_months.trim() !== "" && !monthsValid && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-warranty-months">
              A whole number of months, from 1 to 600.
            </p>
          )}
        </Field>
        <Field label="Start date">
          <input className={inputCls} type="date" value={form.warranty_start_date}
                 onChange={e => { setStartFromPurchase(false); set("warranty_start_date", e.target.value); }}
                 data-testid="input-warranty-start" />
          {startFromPurchase && form.warranty_start_date && form.warranty_start_date === form.purchase_date && (
            <p className="text-[10px] text-muted-foreground leading-snug" data-testid="hint-warranty-start-from-purchase">
              Filled in from the purchase date. Change it if the certificate gives another start.
            </p>
          )}
        </Field>
        <Field label="Who honours it">
          <input className={inputCls} value={form.warrantor} onChange={e => set("warrantor", e.target.value)}
                 placeholder="e.g. Dell Nigeria Ltd" data-testid="input-warrantor" />
        </Field>
        <Field label="Certificate / document reference">
          <input className={inputCls} value={form.warranty_reference} onChange={e => set("warranty_reference", e.target.value)}
                 placeholder="e.g. WC-88812" data-testid="input-warranty-reference" />
        </Field>
        {/* The answer AND its working — the sentence the asset page will
            print, computed here the way the server computes it. */}
        {computedExpiry && (
          <div className="sm:col-span-2 rounded-xl border border-border bg-muted/40 px-3 py-2" data-testid="warranty-computed-expiry">
            <p className="text-xs text-foreground">
              Expires <span className="font-semibold">{formatIsoDate(computedExpiry)}</span> — {monthsNum} months from {formatIsoDate(form.warranty_start_date)}
            </p>
          </div>
        )}
        {hasDuration && !computedExpiry && monthsValid !== (form.warranty_start_date !== "") && (
          <p className="sm:col-span-2 text-[10px] text-muted-foreground leading-snug" data-testid="hint-warranty-pair">
            A duration and a start date go together: enter both, or clear both.
          </p>
        )}
        {!hasDuration && (
          showExpiryOnly ? (
            <Field label="Expiry date only (no duration known)">
              <input className={inputCls} type="date" value={form.warranty_expiry}
                     onChange={e => set("warranty_expiry", e.target.value)} data-testid="input-warranty-expiry-only" />
              <p className="text-[10px] text-muted-foreground leading-snug">
                For a warranty whose length nobody knows. The asset page will say the date was entered on its own, with nothing to check it against.
              </p>
            </Field>
          ) : (
            <div className="sm:col-span-2">
              <button type="button" onClick={() => setShowExpiryOnly(true)}
                      className="text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
                      data-testid="button-warranty-expiry-only">
                No duration known? Enter the expiry date only
              </button>
            </div>
          )
        )}
      </Section>

      <Section title="Notes">
        <Field label="Internal notes" span={2}>
          <textarea className={inputCls} rows={4} value={form.notes} onChange={e => set("notes", e.target.value)} />
        </Field>
      </Section>
    </div>
  );
}
