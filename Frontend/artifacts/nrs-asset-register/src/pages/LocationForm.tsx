/**
 * Location create/edit form. The set of FIELDS mirrors _WRITABLE_FIELDS in
 * myservice_api/controllers/v1_locations.py; the values `location_type` may
 * take are read from the model at runtime and are not restated here — see
 * hooks/useEnums.ts.
 *
 * Lat/lng are number inputs with a read-only NigeriaMap preview of the
 * typed coordinates. A click-to-pick map picker is a future enhancement.
 */
import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import RecordPicker from "@/components/RecordPicker";
import NigeriaMap, { type MapPinData } from "@/components/NigeriaMap";
import {
  createLocation, updateLocation, type LocationWriteBody,
} from "@/lib/dataProvider";
import { apiGet, CadraApiError } from "@/lib/api";
import type { ApiLocation } from "@/lib/adapters";
import { ArrowLeft, AlertCircle, Loader2, Save } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEnum } from "@/hooks/useEnums";
import { withCurrent } from "@/lib/enums";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import { useScopes, SCOPE } from "@/hooks/use-scopes";


type FormShape = {
  name: string;
  description: string;
  active: boolean;
  parent_id: number | null;
  location_type: string;
  street: string;
  street2: string;
  zip: string;
  city: string;
  state_id: number | null;
  country_id: number | null;
  zone_code: string;
  floor_number: string;
  building_id: number | null;
  latitude: string;
  longitude: string;
  /** The room code (handoff 61, R8). Sent only when it changed — see
   *  `codeChange` — so a save that does not touch it cannot regenerate it. */
  location_code: string;
};

const blank: FormShape = {
  name: "", description: "", active: true,
  parent_id: null, location_type: "",
  street: "", street2: "", zip: "", city: "",
  state_id: null, country_id: null,
  zone_code: "", floor_number: "", building_id: null,
  latitude: "", longitude: "",
  location_code: "",
};

/** What the save sends for the room code, or `undefined` to send nothing.
 *  On create, only a typed code (absent means the server generates one). On
 *  edit, only a CHANGE — and an emptied field is sent as `""`, which the
 *  server answers by generating the code again from the hierarchy. */
function codeChange(mode: "create" | "edit", typed: string, stored: string | null): string | undefined {
  const t = typed.trim();
  if (mode === "create") return t ? t : undefined;
  if (t.toUpperCase() === (stored ?? "")) return undefined;
  return t;
}

function toBody(f: FormShape): LocationWriteBody {
  const out: LocationWriteBody = { active: f.active };
  const assignIfSet = <K extends keyof LocationWriteBody>(k: K, v: LocationWriteBody[K]) => {
    if (v === "" || v === null || v === undefined) return;
    out[k] = v;
  };
  assignIfSet("name", f.name);
  assignIfSet("description", f.description);
  assignIfSet("parent_id", f.parent_id);
  assignIfSet("location_type", f.location_type);
  assignIfSet("street", f.street);
  assignIfSet("street2", f.street2);
  assignIfSet("zip", f.zip);
  assignIfSet("city", f.city);
  assignIfSet("state_id", f.state_id);
  assignIfSet("country_id", f.country_id);
  assignIfSet("zone_code", f.zone_code);
  assignIfSet("building_id", f.building_id);
  const parseNum = (s: string) => (s === "" ? null : Number(s));
  const fn = parseNum(f.floor_number);
  if (fn !== null && Number.isFinite(fn)) out.floor_number = fn;
  const lat = parseNum(f.latitude);
  if (lat !== null && Number.isFinite(lat)) out.latitude = lat;
  const lng = parseNum(f.longitude);
  if (lng !== null && Number.isFinite(lng)) out.longitude = lng;
  return out;
}

const searchLocations = async (q: string) => {
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", { q, limit: 10 });
  return res.data.map(l => ({
    id: l.id,
    label: l.name,
    sublabel: l.location_type ?? undefined,
  }));
};

const inputCls = "px-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";

function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: 1 | 2 }) {
  return (
    <div className={cn("flex flex-col gap-1.5", span === 2 && "sm:col-span-2")}>
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
      <h2 className="text-[13px] font-bold text-foreground">{title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">{children}</div>
    </div>
  );
}

interface Props { mode: "create" | "edit" }

export default function LocationForm({ mode }: Props) {
  const params = useParams<{ id: string }>();
  const id = mode === "edit" ? params.id : undefined;
  const [, nav] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();

  const [form, setForm] = useState<FormShape>(blank);
  const set = <K extends keyof FormShape>(k: K, v: FormShape[K]) => setForm(s => ({ ...s, [k]: v }));
  // A hook, so it is read here and not inside the .map() that consumes it.
  const typeOptions = useEnum("location_type");
  const [parentPick, setParentPick] = useState<{ id: number; label: string } | null>(null);

  const existing = useQuery({
    queryKey: ["location-raw", id],
    queryFn: async () => {
      const res = await apiGet<ApiLocation & { location_code?: string | null }>(`/api/v1/locations/${id}`);
      return res.data;
    },
    enabled: mode === "edit" && !!id,
    staleTime: 0,
  });

  useEffect(() => {
    if (mode === "create") {
      setTitle("New Location");
    } else if (existing.data) {
      const l = existing.data;
      setForm({
        name: l.name ?? "",
        description: l.description ?? "",
        active: l.active,
        parent_id: l.parent_id ?? null,
        // Verbatim, and no fallback value: `location_type` has no model
        // default and an unset one is a real state. A stored value this build
        // does not recognise survives to withCurrent() below rather than being
        // quietly dropped on the floor.
        location_type: l.location_type ?? "",
        street: l.address?.street ?? "",
        street2: l.address?.street2 ?? "",
        zip: l.address?.zip ?? "",
        city: l.address?.city ?? "",
        state_id: l.address?.state?.id ?? null,
        country_id: l.address?.country?.id ?? null,
        zone_code: l.extras?.zone_code ?? "",
        floor_number: l.extras?.floor_number != null ? String(l.extras.floor_number) : "",
        building_id: l.extras?.building_id ?? null,
        latitude: "",
        longitude: "",
        location_code: l.location_code ?? "",
      });
      const coords = (l as ApiLocation & { coordinates?: { latitude: number | null; longitude: number | null } | null }).coordinates;
      if (coords) {
        setForm(s => ({
          ...s,
          latitude: coords.latitude != null ? String(coords.latitude) : "",
          longitude: coords.longitude != null ? String(coords.longitude) : "",
        }));
      }
      setTitle(`Edit · ${l.name}`);
    }
    setSearchHandler(undefined);
  }, [mode, existing.data, setTitle, setSearchHandler]);

  useEffect(() => { set("parent_id", parentPick?.id ?? null); }, [parentPick]);

  const storedCode = existing.data?.location_code ?? null;
  const mutation = useMutation({
    mutationFn: () => {
      const body: LocationWriteBody & { location_code?: string } = toBody(form);
      const code = codeChange(mode, form.location_code, storedCode);
      if (code !== undefined) body.location_code = code;
      return mode === "edit" ? updateLocation(id!, body) : createLocation(body);
    },
    onSuccess: (loc) => {
      qc.invalidateQueries({ queryKey: ["locations"] });
      qc.invalidateQueries({ queryKey: ["location", loc.id] });
      qc.invalidateQueries({ queryKey: ["location-raw", loc.id] });
      qc.invalidateQueries({ queryKey: ["location-code", loc.id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      nav(`/locations/${loc.id}`);
    },
  });
  const err = mutation.error as CadraApiError | null;

  const lat = Number(form.latitude);
  const lng = Number(form.longitude);
  const previewPin: MapPinData[] = Number.isFinite(lat) && Number.isFinite(lng) && form.latitude !== "" && form.longitude !== ""
    ? [{ id: "preview", lat, lng, label: form.name || "New location" }]
    : [];

  // Handoff 46: `POST /locations` and `PATCH /locations/<id>` need
  // `locations:write`. Reached by URL without it, the page says so instead
  // of drawing a form whose save the server refuses. After every hook.
  if (!scopes.has(SCOPE.locationsWrite)) {
    return <ScopeRefusal scope={SCOPE.locationsWrite} />;
  }

  return (
    <div className="max-w-4xl mx-auto px-5 py-5 space-y-5">
      <button onClick={() => nav(mode === "edit" && id ? `/locations/${id}` : "/locations")} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft size={13} /> {mode === "edit" ? "Back to location" : "Back to locations"}
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{mode === "create" ? "New location" : "Edit location"}</h1>
        <div className="flex gap-2">
          <button onClick={() => nav(mode === "edit" && id ? `/locations/${id}` : "/locations")} className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
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
            {mode === "edit" ? "Save changes" : "Create location"}
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

      <Section title="Identity">
        <Field label="Name" span={2}>
          <input className={inputCls} value={form.name} onChange={e => set("name", e.target.value)} required />
        </Field>
        <Field label="Description" span={2}>
          <textarea className={inputCls} rows={2} value={form.description} onChange={e => set("description", e.target.value)} />
        </Field>
        <Field label="Type">
          {/* The set is generic.location.location_type, read from the model via
              GET /api/v1/meta/enums. The hard-coded list this replaces offered
              `state` and `office`, which the model has never had — picking
              either and saving raised — and omitted `wing`, which it does have.
              The omission was the worse half: an existing wing loaded into a
              select with no matching option, rendered blank, and could not be
              saved back without changing its own type. The blank entry below is
              genuine, though: the field has no model default and may be unset. */}
          <select className={inputCls} value={form.location_type} onChange={e => set("location_type", e.target.value)}>
            <option value="">— None —</option>
            {withCurrent(typeOptions, form.location_type).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Zone code">
          <input className={inputCls} value={form.zone_code} onChange={e => set("zone_code", e.target.value)} placeholder="e.g. NW-01" />
        </Field>
        <Field label="Room code" span={2}>
          {/* Handoff 61 (R8). What the room label carries. The server
              refuses a code another location holds, in words; the panel
              above prints its sentence. */}
          <input
            className={cn(inputCls, "font-mono")}
            value={form.location_code}
            onChange={e => set("location_code", e.target.value)}
            placeholder={mode === "create" ? "Leave empty to generate it — e.g. LOC-HQ-F10-MTG1" : "Leave empty to generate it again"}
            data-testid="location-code-input"
            maxLength={24}
          />
          <span className="text-[11px] text-muted-foreground">
            Begins LOC-; letters, digits and hyphens. {mode === "create"
              ? "Left empty, it is generated from the zone codes of this location and the ones above it."
              : "Changing it means any label already printed for this room stops scanning. Empty it to generate it again from the zone codes."}
          </span>
        </Field>
        <Field label="Active" span={2}>
          <label className="inline-flex items-center gap-2 text-xs">
            <input type="checkbox" checked={form.active} onChange={e => set("active", e.target.checked)} />
            {form.active ? "Active" : "Archived"}
          </label>
        </Field>
      </Section>

      <Section title="Hierarchy">
        <Field label="Parent location" span={2}>
          <RecordPicker value={parentPick} onChange={setParentPick} search={searchLocations} queryKey="form-location-parents" placeholder="Search parent…" />
        </Field>
        <Field label="Building id">
          <input className={inputCls} type="number" value={form.building_id ?? ""} onChange={e => set("building_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Floor number">
          <input className={inputCls} type="number" value={form.floor_number} onChange={e => set("floor_number", e.target.value)} />
        </Field>
      </Section>

      <Section title="Address">
        <Field label="Street" span={2}>
          <input className={inputCls} value={form.street} onChange={e => set("street", e.target.value)} />
        </Field>
        <Field label="Street 2" span={2}>
          <input className={inputCls} value={form.street2} onChange={e => set("street2", e.target.value)} />
        </Field>
        <Field label="City">
          <input className={inputCls} value={form.city} onChange={e => set("city", e.target.value)} />
        </Field>
        <Field label="ZIP / Postal">
          <input className={inputCls} value={form.zip} onChange={e => set("zip", e.target.value)} />
        </Field>
        <Field label="State id">
          <input className={inputCls} type="number" value={form.state_id ?? ""} onChange={e => set("state_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Country id">
          <input className={inputCls} type="number" value={form.country_id ?? ""} onChange={e => set("country_id", e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </Section>

      <Section title="Coordinates">
        <Field label="Latitude">
          <input className={inputCls} type="number" step="0.0001" value={form.latitude} onChange={e => set("latitude", e.target.value)} placeholder="e.g. 9.0820" />
        </Field>
        <Field label="Longitude">
          <input className={inputCls} type="number" step="0.0001" value={form.longitude} onChange={e => set("longitude", e.target.value)} placeholder="e.g. 8.6753" />
        </Field>
      </Section>

      {previewPin.length > 0 && (
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <h2 className="text-[13px] font-bold">Coordinate preview</h2>
          <NigeriaMap pins={previewPin} height={300} center={[previewPin[0].lat, previewPin[0].lng]} zoom={11} />
        </div>
      )}
    </div>
  );
}
