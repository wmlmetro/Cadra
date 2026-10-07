/**
 * Settings — Receipt gates (handoff 57).
 *
 * SCAFFOLDING, 7 October 2026. One switch, `cadra.receipt.gated`: when on, a
 * unit received from a goods receipt is a CANDIDATE, hidden from the
 * register, until Internal Audit, the tagging team and a maker-checker pair
 * have passed it. Tonight the gates ride on the asset record itself
 * (`register_state`); handoff 58 replaces that with a separate candidate
 * model, and this screen moves with it or goes.
 *
 * The sentence describing what the switch does comes from the server
 * (`statement`), so the screen and the API cannot describe it differently.
 * `settings:write`, as the server's PATCH is — which the Asset Manager holds,
 * so the person the gates constrain can switch them off. Every switch is a
 * row in Configuration changes; handoff 58 should take the switch off the API.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { apiGet, apiPatch, CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { Switch } from "@/components/ui/switch";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Check, Clock, Loader2, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ReceiptGateSetting {
  enabled: boolean;
  configured: boolean;
  default_when_unset: boolean;
  parameter: string;
  statement: string;
  candidates_in_flight: number | null;
  changed_by: { id: number; name: string } | null;
  changed_at: string | null;
}

export const RECEIPT_GATE_KEY = ["settings", "receipt-gate"] as const;

async function fetchReceiptGate(): Promise<ReceiptGateSetting> {
  const res = await apiGet<{ receipt_gated: boolean; receipt_gate: ReceiptGateSetting }>(
    "/api/v1/settings");
  return res.data.receipt_gate;
}

async function updateReceiptGate(enabled: boolean): Promise<ReceiptGateSetting> {
  return (await apiPatch<ReceiptGateSetting>("/api/v1/settings/receipt-gate", { enabled })).data;
}

function changedLine(s: ReceiptGateSetting): string {
  if (!s.configured) return "Nobody has set this on this tenant; it is off by default.";
  if (!s.changed_by || !s.changed_at) return "Set on this tenant.";
  const at = s.changed_at;
  const when = new Date(at.endsWith("Z") || at.includes("+") ? at : at.replace(" ", "T") + "Z");
  return `Last changed by ${s.changed_by.name}, ${when.toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  })}. Recorded in Configuration changes.`;
}

export default function ReceiptGateSettingsPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();
  const readOnly = !scopes.has(SCOPE.settingsWrite);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    setTitle("Settings — Receipt gates");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const setting = useQuery({
    queryKey: RECEIPT_GATE_KEY,
    queryFn: fetchReceiptGate,
    staleTime: 0,
  });

  const save = useMutation({
    mutationFn: updateReceiptGate,
    onSuccess: (d) => {
      qc.setQueryData(RECEIPT_GATE_KEY, d);
      // Everything that lists or counts assets answers differently now.
      qc.invalidateQueries();
      setNote(d.enabled
        ? "Receipt gates are on. The next unit received is a candidate, not an asset."
        : "Receipt gates are off. The next unit received goes straight into the register.");
    },
  });

  const err = (setting.error ?? save.error) as CadraApiError | null;
  const s = setting.data;

  if (setting.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading the receipt-gate setting…</p>
    </div>
  );

  return (
    <div className="p-6 space-y-5 max-w-[900px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground">Receipt gates</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Whether a received unit must pass Internal Audit, tagging and a
          maker-checker registration before it is an asset in the register.
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
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300" data-testid="receipt-gate-note">{note}</p>
        </div>
      )}

      {s && (
        <section className="bg-card border border-border rounded-2xl p-5 space-y-3"
                 data-testid="receipt-gate" data-enabled={s.enabled ? "true" : "false"}>
          <div className="flex items-start gap-3">
            <ShieldCheck size={18} className={cn("shrink-0 mt-0.5",
              s.enabled ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")} />
            <div className="flex-1 min-w-0 space-y-1">
              <h2 className="text-[13px] font-bold">
                Gate received units {s.enabled ? "— on" : "— off"}
              </h2>
              <p className="text-[12px] text-foreground" data-testid="receipt-gate-statement">
                {s.statement}
              </p>
              <p className="text-[11px] text-muted-foreground">{changedLine(s)}</p>
              {s.candidates_in_flight !== null && s.candidates_in_flight > 0 && (
                <p className="text-[11px] text-amber-800 dark:text-amber-300" data-testid="receipt-gate-in-flight">
                  {s.candidates_in_flight} candidate{s.candidates_in_flight === 1 ? " is" : "s are"} waiting
                  on a gate. Switching this off does not register {s.candidates_in_flight === 1 ? "it" : "them"}:
                  {s.candidates_in_flight === 1 ? " it stays" : " they stay"} out of the register until the gates are passed.
                </p>
              )}
            </div>
            {save.isPending
              ? <Loader2 size={16} className="animate-spin text-muted-foreground mt-0.5" />
              : <Switch
                  checked={s.enabled}
                  disabled={readOnly}
                  data-testid="receipt-gate-switch"
                  aria-label="Gate received units"
                  onCheckedChange={(v) => { setNote(null); save.mutate(v); }}
                />}
          </div>
        </section>
      )}

      {readOnly && (
        <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
          Changing this needs the settings role (Asset Manager or administrator).
        </p>
      )}
    </div>
  );
}
