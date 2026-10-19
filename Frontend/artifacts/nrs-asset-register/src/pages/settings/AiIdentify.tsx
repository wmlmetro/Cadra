/**
 * Settings — Identify from photo (handoff 64, ruling R11).
 *
 * The tenant's switch `cadra.ai.identify` (off by default everywhere), who
 * the photo is sent to, the model, the timeout, the daily cap with TODAY's
 * count, and whether the SERVER holds a provider key — never the key itself,
 * which no route returns and none accepts. Since handoff 65 the key lives in
 * the server's environment (`CADRA_AI_API_KEY`), not in any database, so
 * there is nothing on this page to type it into: it is one key per server,
 * set by the owner. Every change is a row in Configuration changes.
 *
 * `settings:write` for the changes, as the server's PATCH is; `settings:read`
 * sees the page read-only.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { apiGet, apiPatch, CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { Switch } from "@/components/ui/switch";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Check, Clock, KeyRound, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AiIdentifySettings {
  enabled: boolean;
  provider: string;
  provider_label: string;
  providers: string[];
  model: string;
  timeout_seconds: number;
  daily_cap: number;
  effort: string;
  efforts: string[];
  key_placed: boolean;
  key_command: string;
  key_variable: string;
  database_class: string | null;
  today: { day: string; calls: number; remaining: number };
  notice: string;
  prompt_version: string;
}

const KEY = ["settings", "ai-identify"] as const;
const inputCls = "px-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";

export default function AiIdentifySettingsPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();
  const readOnly = !scopes.has(SCOPE.settingsWrite);
  const [note, setNote] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ model: string; timeout: string; cap: string; effort: string } | null>(null);

  useEffect(() => {
    setTitle("Settings — Identify from photo");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const setting = useQuery({
    queryKey: KEY,
    queryFn: async () => (await apiGet<AiIdentifySettings>("/api/v1/settings/ai-identify")).data,
    staleTime: 0,
  });
  const s = setting.data;
  useEffect(() => {
    if (s && !draft) setDraft({ model: s.model, timeout: String(s.timeout_seconds), cap: String(s.daily_cap), effort: s.effort });
  }, [s, draft]);

  const save = useMutation<AiIdentifySettings, CadraApiError, Record<string, unknown>>({
    mutationFn: async (body) => (await apiPatch<AiIdentifySettings>("/api/v1/settings/ai-identify", body)).data,
    onSuccess: (d, body) => {
      qc.setQueryData(KEY, d);
      qc.invalidateQueries({ queryKey: ["ai-identify-switch"] });
      setDraft({ model: d.model, timeout: String(d.timeout_seconds), cap: String(d.daily_cap), effort: d.effort });
      setNote("enabled" in body
        ? (d.enabled ? "Identify from photo is on. The button appears on Add asset and on each photo." : "Identify from photo is off. No screen shows the button.")
        : "Saved.");
    },
  });

  const err = (setting.error ?? save.error) as CadraApiError | null;

  if (setting.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading the identification settings…</p>
    </div>
  );

  return (
    <div className="p-6 space-y-5 max-w-[900px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground">Identify from photo</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Cadra's server asks a vision model what a photographed item is, and fills the asset form with
          suggestions a person accepts or changes. Nothing is written from a suggestion by itself.
        </p>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} stacked />
        </div>
      )}
      {note && !err && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/30 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Check size={14} className="text-emerald-600 dark:text-emerald-400" />
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300" data-testid="ai-settings-note">{note}</p>
        </div>
      )}

      {s && (
        <>
          <section className="bg-card border border-border rounded-2xl p-5 space-y-3"
                   data-testid="ai-settings" data-enabled={s.enabled ? "true" : "false"}>
            <div className="flex items-start gap-3">
              <Sparkles size={18} className={cn("shrink-0 mt-0.5", s.enabled ? "text-violet-600 dark:text-violet-400" : "text-muted-foreground")} />
              <div className="flex-1 min-w-0 space-y-1">
                <h2 className="text-[13px] font-bold">Identify from photo {s.enabled ? "— on" : "— off"}</h2>
                <p className="text-[12px] text-foreground">{s.notice}</p>
                <p className="text-[11px] text-muted-foreground">
                  Photos leave Cadra's servers when this is on. NRS's written acceptance names the provider before production photos are sent.
                </p>
              </div>
              {save.isPending
                ? <Loader2 size={16} className="animate-spin text-muted-foreground mt-0.5" />
                : <Switch checked={s.enabled} disabled={readOnly} data-testid="ai-settings-switch"
                          aria-label="Identify from photo"
                          onCheckedChange={(v) => { setNote(null); save.mutate({ enabled: v }); }} />}
            </div>
          </section>

          <section className="bg-card border border-border rounded-2xl p-5 space-y-2" data-testid="ai-settings-today">
            <h2 className="text-[13px] font-bold">Today ({s.today.day}, Lagos)</h2>
            <p className="text-[12px] text-foreground" data-testid="ai-settings-count">
              {s.today.calls} of {s.daily_cap} identifications used; {s.today.remaining} left.
            </p>
            <p className="text-[11px] text-muted-foreground">
              Every call counts, including one that failed. When the day's are used the button answers
              “fill the details by hand” until midnight in Lagos.
            </p>
          </section>

          <section className="bg-card border border-border rounded-2xl p-5 space-y-3">
            <h2 className="text-[13px] font-bold flex items-center gap-1.5"><KeyRound size={14} /> Provider key</h2>
            <p className="text-[12px] text-foreground" data-testid="ai-settings-key">
              {s.key_placed ? "This server holds a provider key." : "This server holds no provider key."}
            </p>
            <p className="text-[11px] text-muted-foreground">
              The key is the owner's and is set on the server, not here: it is{" "}
              <code className="font-mono">{s.key_variable}</code> in the server's environment, one key for every
              tenant on the server, kept in no database. It is never shown or typed on this page. Locally the owner
              sets it with <code className="font-mono">{s.key_command}</code>; on the cluster it is a key of the{" "}
              <code className="font-mono">cadra-odoo</code> secret.
            </p>
          </section>

          {draft && (
            <section className="bg-card border border-border rounded-2xl p-5 space-y-3">
              <h2 className="text-[13px] font-bold">Provider and limits</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Provider
                  <select className={inputCls} value={s.provider} disabled={readOnly}
                          onChange={e => { setNote(null); save.mutate({ provider: e.target.value }); }} data-testid="ai-settings-provider">
                    {s.providers.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Model
                  <input className={inputCls} value={draft.model} disabled={readOnly}
                         onChange={e => setDraft({ ...draft, model: e.target.value })} data-testid="ai-settings-model" />
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Timeout (seconds, 5–60)
                  <input className={inputCls} type="number" min={5} max={60} value={draft.timeout} disabled={readOnly}
                         onChange={e => setDraft({ ...draft, timeout: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Daily cap
                  <input className={inputCls} type="number" min={1} value={draft.cap} disabled={readOnly}
                         onChange={e => setDraft({ ...draft, cap: e.target.value })} data-testid="ai-settings-cap" />
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Effort
                  <select className={inputCls} value={draft.effort} disabled={readOnly}
                          onChange={e => setDraft({ ...draft, effort: e.target.value })}>
                    {s.efforts.map(x => <option key={x} value={x}>{x}</option>)}
                  </select>
                </label>
              </div>
              {!readOnly && (
                <button type="button"
                        onClick={() => { setNote(null); save.mutate({ model: draft.model.trim(), timeout_seconds: Number(draft.timeout), daily_cap: Number(draft.cap), effort: draft.effort }); }}
                        disabled={save.isPending}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-primary text-white text-xs font-semibold disabled:opacity-60"
                        data-testid="ai-settings-save">
                  Save
                </button>
              )}
              <p className="text-[10px] text-muted-foreground">Prompt version {s.prompt_version}.</p>
            </section>
          )}
        </>
      )}

      {readOnly && (
        <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
          Changing this needs the settings role (Asset Manager or administrator).
        </p>
      )}
    </div>
  );
}
