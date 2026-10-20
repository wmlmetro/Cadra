/**
 * Identify from photo (handoff 64 §3) — what both places share.
 *
 * - `useAiSwitch` — the tenant's switch. Off, or unread, draws nothing.
 * - `SuggestionFacts` — what the suggestion says beyond the fields: how sure
 *   it is, the two alternatives, the text read off the item, the SAP records
 *   it may be (or how many, for somebody who may not read them), and any
 *   value the server removed because the photo did not show it.
 * - `SizeBandLine` — the approximate size band (handoff 67, AI-FR-03), with
 *   the band's words; shown, never a field anything sends.
 * - `PhotoIdentifyPanel` — the asset's Photos tab: the suggestions BESIDE
 *   the current values, *Use this* per field, one save for the fields used.
 *   It never overwrites a value the person did not choose.
 *
 * The notice is said once on each screen: photograph the item, not people,
 * and who the photo is sent to.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles, X } from "lucide-react";
import { apiGet, apiPatch, newIdempotencyKey, type CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import { fetchAssetCategories } from "@/lib/dataProvider";
import { useEnum } from "@/hooks/useEnums";
import {
  FIELD_WORDS, SUGGESTED_FIELDS, TEXT_KIND_WORDS, fetchAiSwitch, identifyStoredPhoto,
  proposedValues, type AiSuggestion, type ScoredCategory, type SizeBand, type SuggestedField,
} from "@/lib/aiIdentify";

export function useAiSwitch() {
  const q = useQuery({ queryKey: ["ai-identify-switch"], queryFn: fetchAiSwitch, staleTime: 5 * 60_000 });
  return q.data?.enabled ? q.data : null;
}

function pct(c: number) {
  return `${Math.round(c * 100)}%`;
}

export function AiNotice({ text }: { text: string }) {
  return (
    <p className="text-[11px] text-muted-foreground" data-testid="ai-notice">{text}</p>
  );
}

/** "Approximate size: medium", with what medium means in words. A band
 *  the server did not choose says why, in its words. Not a field: nothing
 *  on the asset or the capture carries it (handoff 67, AI-FR-03). */
export function SizeBandLine({ band }: { band: SizeBand | undefined }) {
  if (!band) return null;
  const all = Object.entries(band.definitions ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n");
  return (
    <p className="text-[11px] text-muted-foreground" data-testid="ai-size-band" data-band={band.value ?? ""}
       title={all || band.definition}>
      {band.label}:{" "}
      <span className="font-semibold text-foreground">{band.value ?? "not judged"}</span>
      {band.definition ? <> — {band.definition}</> : null}
    </p>
  );
}

export function SuggestionFacts({ s, onPickCategory }: {
  s: AiSuggestion; onPickCategory?: (c: ScoredCategory) => void;
}) {
  const sap = s.sap_candidates;
  return (
    <div className="space-y-2 text-[11px]" data-testid="ai-suggestion-facts">
      <p className="text-foreground">
        Looks like <span className="font-semibold">{s.category.name ?? `class ${s.category.id}`}</span>{" "}
        ({pct(s.category.confidence)} sure)
        {s.condition.note ? <> · condition note: “{s.condition.note}”</> : null}
      </p>
      <SizeBandLine band={s.size_band} />
      {s.category.alternatives.length > 0 && (
        <p className="text-muted-foreground" data-testid="ai-alternatives">
          Or perhaps:{" "}
          {s.category.alternatives.map((a, i) => (
            <span key={a.id}>
              {i > 0 && ", "}
              {onPickCategory ? (
                <button type="button" className="underline text-foreground" onClick={() => onPickCategory(a)}
                        data-testid={`ai-alternative-${a.id}`}>
                  {a.name ?? `class ${a.id}`}
                </button>
              ) : (a.name ?? `class ${a.id}`)}
              {" "}({pct(a.confidence)})
            </span>
          ))}
        </p>
      )}
      <div data-testid="ai-text-read">
        <p className="font-medium text-muted-foreground">Text read off the item</p>
        {s.text_read.length === 0
          ? <p className="text-muted-foreground">None could be read.</p>
          : (
            <ul className="list-disc pl-4">
              {s.text_read.map((t, i) => (
                <li key={i}><span className="font-mono text-foreground">{t.text}</span> — {TEXT_KIND_WORDS[t.looks_like] ?? t.looks_like}</li>
              ))}
            </ul>
          )}
      </div>
      <div data-testid="ai-sap-candidates">
        <p className="font-medium text-muted-foreground">Which SAP record it may be</p>
        {sap.items === null ? (
          <p className="text-muted-foreground" data-testid="ai-sap-count-only">{sap.note}</p>
        ) : sap.items.length === 0 ? (
          <p className="text-muted-foreground">{sap.note ?? "No SAP record matched."}</p>
        ) : (
          <>
            <ul className="space-y-1">
              {sap.items.map((c) => (
                <li key={c.id} className="rounded-lg border border-border px-2 py-1" data-testid={`ai-sap-${c.id}`}>
                  <span className="font-mono text-foreground">{c.asset_number}</span>
                  {c.description ? <> · {c.description}</> : null}
                  {c.old_tag ? <> · old tag {c.old_tag}</> : null}
                  <span className="block text-muted-foreground">{c.reason}</span>
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground">
              For reference: the SAP number is set at registration by the Register Maker, or by SAP itself — never from here.
            </p>
          </>
        )}
      </div>
      {s.notes.length > 0 && (
        <ul className="text-amber-800 dark:text-amber-300 list-disc pl-4" data-testid="ai-notes">
          {s.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}

/** What a field reads as for a person: a class by name, a condition by its
 *  label, anything else as typed. */
function useShown() {
  const categories = useQuery({ queryKey: ["asset-categories"], queryFn: fetchAssetCategories, staleTime: 10 * 60_000 });
  const conditions = useEnum("condition");
  return (field: SuggestedField, value: unknown): string => {
    if (value === null || value === undefined || value === "") return "—";
    if (field === "category_id") {
      const c = (categories.data ?? []).find(x => x.id === Number(value));
      return c ? c.name : `class ${value}`;
    }
    if (field === "condition") return conditions.find(o => o.value === value)?.label ?? String(value);
    return String(value);
  };
}

/** The asset's current value of a field, from its raw API row. */
function currentOf(raw: Record<string, unknown> | undefined, field: SuggestedField): unknown {
  if (!raw) return undefined;
  if (field === "category_id") {
    const c = raw.category as { id?: number } | null | undefined;
    return c?.id ?? null;
  }
  if (field === "model_name") return raw.model ?? raw.model_name ?? null;
  return raw[field] ?? null;
}

export function PhotoIdentifyPanel({ assetId, photoId, onClose }: {
  assetId: string | number; photoId: number; onClose: () => void;
}) {
  const qc = useQueryClient();
  const shown = useShown();
  const ai = useAiSwitch();
  const [chosen, setChosen] = useState<Set<SuggestedField>>(new Set());
  const asset = useQuery({
    queryKey: ["asset-raw-identify", String(assetId)],
    queryFn: async () => (await apiGet<Record<string, unknown>>(`/api/v1/assets/${assetId}`)).data,
    staleTime: 0, gcTime: 0, refetchOnMount: "always",
  });
  const identify = useMutation<AiSuggestion, CadraApiError>({
    mutationFn: () => identifyStoredPhoto(photoId),
  });
  const suggestion = identify.data;
  const proposed = suggestion ? proposedValues(suggestion) : {};
  const fields = SUGGESTED_FIELDS.filter(f => f in proposed);
  // A field the asset ALREADY holds as suggested is shown "Same" and offers
  // no choice, so it is neither used nor ignored: it is left out of the
  // save's `ignored`, and the server records it `accepted` with
  // `already_held` (handoff 65 §0a.3 — it was recorded `ignored`). The
  // comparison is the server's `_norm`: trimmed, case-folded.
  const isSame = (f: SuggestedField) =>
    String(currentOf(asset.data, f) ?? "").trim().toLowerCase() === String(proposed[f] ?? "").trim().toLowerCase();

  const save = useMutation<unknown, CadraApiError>({
    mutationFn: async () => {
      const body: Record<string, unknown> = {};
      for (const f of chosen) body[f] = proposed[f];
      body.ai_suggestion = {
        id: suggestion!.suggestion_id,
        ignored: fields.filter(f => !chosen.has(f) && !isSame(f)),
      };
      return apiPatch(`/api/v1/assets/${assetId}`, body, { idempotencyKey: newIdempotencyKey() });
    },
    onSuccess: () => {
      invalidateAssetQueries(qc, String(assetId));
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "asset-history" });
      onClose();
    },
  });

  return (
    <div className="mt-2 rounded-xl border border-violet-300/70 dark:border-violet-700/50 bg-violet-50/60 dark:bg-violet-950/20 p-3 space-y-3"
         data-testid={`ai-photo-panel-${photoId}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <Sparkles size={13} /> Identify from this photo
        </p>
        <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground"
                aria-label="Close" data-testid="ai-photo-close">
          <X size={13} />
        </button>
      </div>
      {ai && <AiNotice text={ai.notice} />}
      {!suggestion && (
        <button
          type="button"
          onClick={() => identify.mutate()}
          disabled={identify.isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs disabled:opacity-60"
          data-testid="ai-photo-identify"
        >
          {identify.isPending ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          {identify.isPending ? "Reading the photo…" : "Identify"}
        </button>
      )}
      {identify.error && <ApiErrorMessage err={identify.error} />}
      {suggestion && (
        <>
          {fields.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">The photo proposed nothing to fill.</p>
          ) : (
            <table className="w-full text-[11px]" data-testid="ai-photo-compare">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="py-1 pr-2 font-medium">Field</th>
                  <th className="py-1 pr-2 font-medium">Now</th>
                  <th className="py-1 pr-2 font-medium">Suggested</th>
                  <th className="py-1 font-medium" />
                </tr>
              </thead>
              <tbody>
                {fields.map(f => {
                  const now = currentOf(asset.data, f);
                  const same = isSame(f);
                  const on = chosen.has(f);
                  return (
                    <tr key={f} className="border-t border-border/60" data-testid={`ai-compare-${f}`}>
                      <td className="py-1 pr-2 text-muted-foreground">{FIELD_WORDS[f]}</td>
                      <td className="py-1 pr-2 text-foreground" data-testid={`ai-now-${f}`}>{shown(f, now)}</td>
                      <td className="py-1 pr-2 text-foreground font-medium" data-testid={`ai-suggested-${f}`}>{shown(f, proposed[f])}</td>
                      <td className="py-1 text-right">
                        {same ? (
                          <span className="text-muted-foreground">Same</span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setChosen(prev => {
                              const next = new Set(prev);
                              if (next.has(f)) next.delete(f); else next.add(f);
                              return next;
                            })}
                            className={on
                              ? "px-2 py-0.5 rounded-md bg-primary text-primary-foreground"
                              : "px-2 py-0.5 rounded-md border border-border text-foreground"}
                            aria-pressed={on}
                            data-testid={`ai-use-${f}`}
                          >
                            {on ? "Using this" : "Use this"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <SuggestionFacts s={suggestion} />
          {save.error && <ApiErrorMessage err={save.error} />}
          <div className="flex gap-2 items-center">
            <button
              type="button"
              onClick={() => save.mutate()}
              disabled={save.isPending || chosen.size === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs disabled:opacity-60"
              data-testid="ai-photo-save"
            >
              {save.isPending && <Loader2 size={13} className="animate-spin" />}
              {chosen.size === 0 ? "Choose a field to use" : `Save ${chosen.size} field${chosen.size === 1 ? "" : "s"}`}
            </button>
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-xs text-muted-foreground"
                    data-testid="ai-photo-cancel">
              Cancel
            </button>
            <p className="text-[10px] text-muted-foreground">Only the fields marked “Using this” are changed.</p>
          </div>
        </>
      )}
    </div>
  );
}
