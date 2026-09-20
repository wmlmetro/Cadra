/**
 * Service Desk request create/edit form. Mirrors _WRITABLE_FIELDS in
 * myservice_api/controllers/v1_requests.py.
 *
 * type_id / category_id pickers stay as raw FK ids until the API exposes
 * request.type and request.category list endpoints (backend gap).
 */
import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import RecordPicker from "@/components/RecordPicker";
import { createRequest, updateRequest, fetchRequest, type RequestWriteBody } from "@/lib/dataProvider";
import { apiGet, CadraApiError } from "@/lib/api";
import { useEnum } from "@/hooks/useEnums";
import { ENUM_DEFAULT } from "@/lib/enums";
import type { ApiLocation } from "@/lib/adapters";
import { ArrowLeft, AlertCircle, Loader2, Save } from "lucide-react";
import { cn } from "@/lib/utils";

interface ApiAssetRef { id: number; name: string; tag: string | null }
interface ApiEmployeeRef { id: number; name: string; ir_number: string | null }

const searchLocations = async (q: string) => {
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", { q, limit: 10 });
  return res.data.map(l => ({ id: l.id, label: l.name }));
};
const searchAssets = async (q: string) => {
  const res = await apiGet<ApiAssetRef[]>("/api/v1/assets", { q, limit: 10 });
  return res.data.map(a => ({ id: a.id, label: a.name, sublabel: a.tag ?? undefined }));
};
const searchEmployees = async (q: string) => {
  const res = await apiGet<ApiEmployeeRef[]>("/api/v1/identity/employees", { q, limit: 10 });
  return res.data.map(e => ({ id: e.id, label: e.name, sublabel: e.ir_number ?? undefined }));
};

type FormShape = {
  type_id: string;
  category_id: string;
  priority: string;
  impact: string;
  urgency: string;
  request_text: string;
  response_text: string;
  deadline_date: string;
  user_id: number | null;
  location_id: number | null;
  vehicle_id: string;
  nrs_asset_id: number | null;
};

// The blank form starts on the MODEL's default priority, by value.
// It used to start on the literal "2" — chosen because it is the middle of
// five options — and "2" is High. The dropdown that shipped with it was
// labelled one step low, so the screen said "Normal" while the record was
// filed High, and nothing anywhere reported the discrepancy. A default is a
// value the model owns, not a position in a list this file maintains.
//
// No `?? ""` fallback: an unset `priority` would render this select with no
// matching option, so the browser would display the FIRST one — "Low" —
// while a form submitted untouched recorded the model's default, "Normal".
// That is the same defect one value along, so `ENUM_DEFAULT` is typed to
// guarantee the key instead (`satisfies`, not an annotation).
const blank: FormShape = {
  type_id: "", category_id: "",
  priority: ENUM_DEFAULT.priority, impact: "", urgency: "",
  request_text: "", response_text: "",
  deadline_date: "",
  user_id: null, location_id: null, vehicle_id: "", nrs_asset_id: null,
};

function toBody(f: FormShape): RequestWriteBody {
  const out: RequestWriteBody = {};
  const tid = Number(f.type_id);
  if (Number.isFinite(tid) && tid > 0) out.type_id = tid;
  const cid = Number(f.category_id);
  if (Number.isFinite(cid) && cid > 0) out.category_id = cid;
  if (f.priority) out.priority = f.priority;
  if (f.impact) out.impact = f.impact;
  if (f.urgency) out.urgency = f.urgency;
  if (f.request_text) out.request_text = f.request_text;
  if (f.response_text) out.response_text = f.response_text;
  if (f.deadline_date) out.deadline_date = f.deadline_date;
  if (f.user_id) out.user_id = f.user_id;
  if (f.location_id) out.location_id = f.location_id;
  if (f.nrs_asset_id) out.nrs_asset_id = f.nrs_asset_id;
  const vid = Number(f.vehicle_id);
  if (Number.isFinite(vid) && vid > 0) out.vehicle_id = vid;
  return out;
}

const inputCls = "px-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";

function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: 1 | 2 }) {
  return (
    <div className={cn("flex flex-col gap-1.5", span === 2 && "sm:col-span-2")}>
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}
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

export default function RequestForm({ mode }: { mode: "create" | "edit" }) {
  const params = useParams<{ id: string }>();
  const id = mode === "edit" ? params.id : undefined;
  const [, nav] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();

  // The priority set is read from the model via GET /api/v1/meta/enums rather
  // than declared here; see lib/enums.ts for why the local copy had to go.
  const priorityOpts = useEnum("priority");

  const [form, setForm] = useState<FormShape>(blank);
  const set = <K extends keyof FormShape>(k: K, v: FormShape[K]) => setForm(s => ({ ...s, [k]: v }));

  const [locPick, setLocPick] = useState<{ id: number; label: string } | null>(null);
  const [assetPick, setAssetPick] = useState<{ id: number; label: string } | null>(null);
  const [userPick, setUserPick] = useState<{ id: number; label: string } | null>(null);

  const existing = useQuery({
    queryKey: ["request", id],
    queryFn: () => fetchRequest(id ?? ""),
    enabled: mode === "edit" && !!id,
    staleTime: 0,
  });

  useEffect(() => {
    if (mode === "create") {
      setTitle("New Request");
    } else if (existing.data) {
      const r = existing.data;
      setForm({
        type_id: r.typeId ? String(r.typeId) : "",
        category_id: r.categoryId ? String(r.categoryId) : "",
        priority: r.priority,
        impact: r.impact ?? "",
        urgency: r.urgency ?? "",
        request_text: r.requestText,
        response_text: r.responseText ?? "",
        deadline_date: r.deadline ?? "",
        user_id: r.assignee?.id ?? null,
        location_id: null,
        vehicle_id: "",
        nrs_asset_id: null,
      });
      if (r.assignee) setUserPick({ id: r.assignee.id, label: r.assignee.name });
      setTitle(`Edit · ${r.reference}`);
    }
    setSearchHandler(undefined);
  }, [mode, existing.data, setTitle, setSearchHandler]);

  useEffect(() => { set("location_id", locPick?.id ?? null); }, [locPick]);
  useEffect(() => { set("nrs_asset_id", assetPick?.id ?? null); }, [assetPick]);
  useEffect(() => { set("user_id", userPick?.id ?? null); }, [userPick]);

  const mutation = useMutation({
    mutationFn: () => mode === "edit"
      ? updateRequest(id!, toBody(form))
      : createRequest(toBody(form)),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["requests"] });
      qc.invalidateQueries({ queryKey: ["request", r.id] });
      qc.invalidateQueries({ queryKey: ["fm-dashboard"] });
      // A request raised against an asset is an event in that asset's
      // history. Which asset is not known here, so every cached history goes.
      qc.invalidateQueries({ queryKey: ["asset-history"] });
      nav(`/service-desk/${r.id}`);
    },
  });
  const err = mutation.error as CadraApiError | null;

  const requiredOK = mode === "edit" || (form.type_id && form.request_text.trim());

  return (
    <div className="max-w-4xl mx-auto px-5 py-5 space-y-5">
      <button onClick={() => nav(mode === "edit" && id ? `/service-desk/${id}` : "/service-desk")} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft size={13} /> {mode === "edit" ? "Back to request" : "Back to Service Desk"}
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{mode === "create" ? "New service request" : "Edit request"}</h1>
        <div className="flex gap-2">
          <button onClick={() => nav(mode === "edit" && id ? `/service-desk/${id}` : "/service-desk")} className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !requiredOK}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl",
              requiredOK && !mutation.isPending
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {mode === "edit" ? "Save changes" : "Create request"}
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

      <Section title="Classification" sub="Request type and category pickers will use FK ids until the API exposes list endpoints.">
        <Field label="Type id *">
          <input className={inputCls} type="number" value={form.type_id} onChange={e => set("type_id", e.target.value)} placeholder="e.g. 1 (Incident)" disabled={mode === "edit"} />
        </Field>
        <Field label="Category id">
          <input className={inputCls} type="number" value={form.category_id} onChange={e => set("category_id", e.target.value)} />
        </Field>
        <Field label="Priority">
          <select className={inputCls} value={form.priority} onChange={e => set("priority", e.target.value)}>
            {priorityOpts.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Deadline">
          <input className={inputCls} type="date" value={form.deadline_date} onChange={e => set("deadline_date", e.target.value)} />
        </Field>
        <Field label="Impact">
          <input className={inputCls} value={form.impact} onChange={e => set("impact", e.target.value)} placeholder="1–4" />
        </Field>
        <Field label="Urgency">
          <input className={inputCls} value={form.urgency} onChange={e => set("urgency", e.target.value)} placeholder="1–4" />
        </Field>
      </Section>

      <Section title="Body">
        <Field label="Request text (HTML allowed) *" span={2}>
          <textarea
            className={inputCls}
            rows={5}
            value={form.request_text}
            onChange={e => set("request_text", e.target.value)}
            placeholder="Describe the issue or task in detail"
          />
        </Field>
        {mode === "edit" && (
          <Field label="Response text" span={2}>
            <textarea
              className={inputCls}
              rows={3}
              value={form.response_text}
              onChange={e => set("response_text", e.target.value)}
            />
          </Field>
        )}
      </Section>

      <Section title="Assignment & links">
        <Field label="Assignee (user)" span={2}>
          <RecordPicker value={userPick} onChange={setUserPick} search={searchEmployees} queryKey="form-req-user" placeholder="Search…" />
        </Field>
        <Field label="Location" span={2}>
          <RecordPicker value={locPick} onChange={setLocPick} search={searchLocations} queryKey="form-req-loc" placeholder="Search…" />
        </Field>
        <Field label="Linked asset" span={2}>
          <RecordPicker value={assetPick} onChange={setAssetPick} search={searchAssets} queryKey="form-req-asset" placeholder="Search…" />
        </Field>
        <Field label="Vehicle id">
          <input className={inputCls} type="number" value={form.vehicle_id} onChange={e => set("vehicle_id", e.target.value)} />
        </Field>
      </Section>
    </div>
  );
}
