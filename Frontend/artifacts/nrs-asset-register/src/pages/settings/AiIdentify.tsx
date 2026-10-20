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
 *
 * Since handoff 67 (AI-NFR-08) the page also says how the suggestions were
 * used: made, identified, used in a save or a capture, and accepted
 * unchanged, by class, by site (the audit campaign's location) and by
 * model, over the last 30 days (7 or 90 on request), from
 * `nrs.ai.suggestion`. Every number says what it counts — the server's own
 * definitions are printed under the tables, verbatim.
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

/** One provider this tenant may choose (handoff 68). */
export interface AiProviderOption {
  value: string;
  label: string;
  /** The model it is asked with on this tenant. */
  model: string;
  default_model: string;
  needs_key: boolean;
  /** Whether the SERVER holds its key — never the key. Null for the stand-in. */
  key_placed: boolean | null;
  key_variable: string | null;
  key_command: string | null;
}

export interface AiIdentifySettings {
  enabled: boolean;
  provider: string;
  provider_label: string;
  providers: string[];
  provider_options?: AiProviderOption[];
  keys?: Record<string, { placed: boolean; variable: string; command: string }>;
  model: string;
  default_model?: string;
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

/** One row of the acceptance dashboard (`GET /settings/ai-identify/acceptance`). */
export interface AcceptanceRow {
  key: string;
  label: string;
  /** On a by-model row: the provider that answered (handoff 68). */
  provider?: string;
  made: number;
  identified: number;
  used: number;
  accepted_unchanged: number;
  /** 0..1, or null when nothing was used. */
  share_accepted_unchanged: number | null;
}

export interface Acceptance {
  window: { days: number; from: string; to: string; timezone: string };
  totals: Omit<AcceptanceRow, "key" | "label">;
  by_category: AcceptanceRow[];
  by_site: AcceptanceRow[];
  by_provider?: AcceptanceRow[];
  by_model: AcceptanceRow[];
  definitions: Record<string, string>;
}

const ACCEPTANCE_DAYS = [7, 30, 90] as const;

/** The order and the words the definitions are printed under. */
const DEFINITION_WORDS: [string, string][] = [
  ["made", "Made"], ["identified", "Identified"], ["used", "Used"],
  ["accepted_unchanged", "Accepted unchanged"], ["share_accepted_unchanged", "Share"],
  ["by_category", "By class"], ["by_site", "By site"], ["by_provider", "By provider"], ["by_model", "By model"],
];
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
  // The form follows the SERVER's values whenever they change, not only on
  // first paint: the page paints from the restored cache and then refetches
  // (handoff 52), and since handoff 68 the model is the configured
  // provider's — a draft taken once from the restored copy showed one
  // provider's model under the other's name after a reload (spec 68).
  const [draftOf, setDraftOf] = useState<string | null>(null);
  useEffect(() => {
    if (!s) return;
    const of = JSON.stringify([s.provider, s.model, s.timeout_seconds, s.daily_cap, s.effort]);
    if (of !== draftOf) {
      setDraft({ model: s.model, timeout: String(s.timeout_seconds), cap: String(s.daily_cap), effort: s.effort });
      setDraftOf(of);
    }
  }, [s, draftOf]);

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
            <h2 className="text-[13px] font-bold flex items-center gap-1.5"><KeyRound size={14} /> Provider keys</h2>
            <p className="text-[12px] text-foreground" data-testid="ai-settings-key">
              {s.key_placed ? `This server holds ${s.provider_label}'s key.` : `This server holds no key for ${s.provider_label}.`}
            </p>
            {s.provider_options && (
              <ul className="text-[12px] space-y-1" data-testid="ai-settings-keys">
                {s.provider_options.filter(o => o.needs_key).map(o => (
                  <li key={o.value} className="flex flex-wrap items-baseline gap-x-2" data-testid={`ai-settings-key-${o.value}`}
                      data-placed={o.key_placed ? "true" : "false"}>
                    <span className="font-semibold">{o.label}</span>
                    <span className={o.key_placed ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}>
                      {o.key_placed ? "key present" : "key absent"}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      <code className="font-mono">{o.key_variable}</code>
                      {o.key_command && <> · locally <code className="font-mono">{o.key_command}</code></>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] text-muted-foreground">
              A key is the owner's and is set on the server, not here: each provider has its own variable in the
              server's environment, one key for every tenant on the server, kept in no database. It is never shown or
              typed on this page. On the cluster each is a key of the <code className="font-mono">cadra-odoo</code> secret.
            </p>
          </section>

          {draft && (
            <section className="bg-card border border-border rounded-2xl p-5 space-y-3">
              <h2 className="text-[13px] font-bold">Provider and limits</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Provider
                  <select className={inputCls} value={s.provider} disabled={readOnly}
                          onChange={e => { setNote(null); save.mutate({ provider: e.target.value }); }} data-testid="ai-settings-provider">
                    {(s.provider_options ?? s.providers.map(p => ({ value: p, label: p } as AiProviderOption))).map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">Model
                  <input className={inputCls} value={draft.model} disabled={readOnly}
                         onChange={e => setDraft({ ...draft, model: e.target.value })} data-testid="ai-settings-model" />
                  {s.default_model && (
                    <span className="text-[10px]" data-testid="ai-settings-default-model">
                      {s.provider_label}'s default: <code className="font-mono">{s.default_model}</code>. Each provider keeps its own model.
                    </span>
                  )}
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

      {s && <AcceptanceDashboard />}

      {readOnly && (
        <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
          Changing this needs the settings role (Asset Manager or administrator).
        </p>
      )}
    </div>
  );
}

function share(v: number | null) {
  return v == null
    ? <span title="nothing used yet">—</span>
    : `${Math.round(v * 100)}%`;
}

/**
 * How suggestions were used (handoff 67, AI-NFR-08). Read-only, under
 * `settings:read`, as the page. The numbers are the server's; this only
 * lays them out and prints what each one counts.
 */
function AcceptanceDashboard() {
  const [days, setDays] = useState<number>(30);
  const q = useQuery<Acceptance, CadraApiError>({
    queryKey: ["ai-identify-acceptance", days],
    queryFn: async () => (await apiGet<Acceptance>("/api/v1/settings/ai-identify/acceptance", { days })).data,
    staleTime: 60_000,
  });
  const a = q.data;
  const t = a?.totals;
  return (
    <section className="bg-card border border-border rounded-2xl p-5 space-y-3" data-testid="ai-acceptance">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <h2 className="text-[13px] font-bold">How suggestions were used — last {days} days</h2>
        <select className={inputCls} value={days} onChange={e => setDays(Number(e.target.value))}
                aria-label="Days" data-testid="ai-acceptance-days">
          {ACCEPTANCE_DAYS.map(d => <option key={d} value={d}>Last {d} days</option>)}
        </select>
      </div>
      {q.isLoading && (
        <p className="text-[12px] text-muted-foreground flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Counting…</p>
      )}
      {q.error && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={q.error} />
        </div>
      )}
      {a && t && (
        <>
          <p className="text-[11px] text-muted-foreground" data-testid="ai-acceptance-window">
            {a.window.from} to {a.window.to}, days in {a.window.timezone === "Africa/Lagos" ? "Lagos" : a.window.timezone}.
          </p>
          <p className="text-[12px] text-foreground" data-testid="ai-acceptance-totals">
            <span className="font-semibold">{t.made}</span> made · <span className="font-semibold">{t.identified}</span> identified ·{" "}
            <span className="font-semibold">{t.used}</span> used · <span className="font-semibold">{t.accepted_unchanged}</span> accepted
            unchanged · share {share(t.share_accepted_unchanged)}
          </p>
          <AcceptanceTable title="By class" rows={a.by_category} testid="ai-acceptance-by-category" />
          <AcceptanceTable title="By site" rows={a.by_site} testid="ai-acceptance-by-site" />
          {a.by_provider && <AcceptanceTable title="By provider" rows={a.by_provider} testid="ai-acceptance-by-provider" />}
          <AcceptanceTable title="By model" rows={a.by_model} testid="ai-acceptance-by-model" />
          <dl className="text-[11px] text-muted-foreground space-y-1 border-t border-border pt-3" data-testid="ai-acceptance-definitions">
            {DEFINITION_WORDS.filter(([k]) => a.definitions?.[k]).map(([k, w]) => (
              <div key={k} className="flex gap-1.5">
                <dt className="font-semibold text-foreground shrink-0">{w}:</dt>
                <dd data-testid={`ai-acceptance-definition-${k}`}>{a.definitions[k]}</dd>
              </div>
            ))}
            {Object.keys(a.definitions ?? {}).filter(k => !DEFINITION_WORDS.some(([d]) => d === k)).map(k => (
              <div key={k} className="flex gap-1.5">
                <dt className="font-semibold text-foreground shrink-0">{k}:</dt>
                <dd data-testid={`ai-acceptance-definition-${k}`}>{a.definitions[k]}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}

function AcceptanceTable({ title, rows, testid }: { title: string; rows: AcceptanceRow[]; testid: string }) {
  return (
    <div className="space-y-1">
      <h3 className="text-[12px] font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-[11px] text-muted-foreground" data-testid={`${testid}-empty`}>No suggestion was made in this window.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[520px]" data-testid={testid}>
            <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr className="border-b border-border">
                <th className="text-left py-1 pr-3">{title.replace(/^By /, "")}</th>
                {["Made", "Identified", "Used", "Accepted unchanged", "Share"].map(h => (
                  <th key={h} className="text-right py-1 pl-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.key} className="border-b border-border" data-testid={`${testid}-row-${r.key}`}>
                  <td className="py-1 pr-3">{r.provider ? <><span className="text-muted-foreground">{r.provider} · </span>{r.label}</> : r.label}</td>
                  <td className="text-right pl-3 tabular-nums">{r.made}</td>
                  <td className="text-right pl-3 tabular-nums">{r.identified}</td>
                  <td className="text-right pl-3 tabular-nums">{r.used}</td>
                  <td className="text-right pl-3 tabular-nums">{r.accepted_unchanged}</td>
                  <td className="text-right pl-3 tabular-nums">{share(r.share_accepted_unchanged)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
