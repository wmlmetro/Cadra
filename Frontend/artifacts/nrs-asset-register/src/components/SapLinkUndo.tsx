/**
 * "Propose undoing this link" — on an asset whose SAP number was linked from
 * SAP's export by two people (handoff 65 §1). An undo is the same two acts
 * as the link: the Register Maker proposes it here with a reason, and the
 * Register Checker approves or returns it on *Link to SAP → Waiting on the
 * checker*. Nothing changes on the asset until then; a link is never
 * deleted. Drawn only for a holder of `register:make`; the server decides.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import { apiPost, type CadraApiError } from "@/lib/api";
import { SAP_LINKS_KEY, type SapLink } from "@/lib/sapLinks";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";
import { AlertCircle, Loader2 } from "lucide-react";

export function SapLinkUndo({ assetId, sapNumber }: { assetId: string; sapNumber: string }) {
  const scopes = useScopes();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const m = useMutation<SapLink, CadraApiError>({
    mutationFn: async () => (await apiPost<SapLink>(
      `/api/v1/assets/${encodeURIComponent(assetId)}/sap-link/undo`, { reason: reason.trim() })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SAP_LINKS_KEY });
      invalidateAssetQueries(qc, assetId);
    },
  });
  if (!scopes.has(SCOPE.registerMake)) return null;
  const close = () => { if (!m.isPending) { setOpen(false); setReason(""); m.reset(); } };
  const ready = reason.trim().length > 0;

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} data-testid="button-sap-link-undo"
        className="mt-1 text-[11px] font-semibold text-primary hover:underline">
        Propose undoing this link
      </button>
      <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
        <DialogContent className="sm:max-w-lg" data-testid="sap-link-undo-dialog">
          <DialogHeader>
            <DialogTitle>Propose undoing the link to SAP asset {sapNumber}</DialogTitle>
            <DialogDescription>
              The Register Checker approves or returns it. Until they approve, the asset keeps its SAP
              number; the link is never deleted, and nothing is sent to SAP.
            </DialogDescription>
          </DialogHeader>
          {m.data ? (
            <p className="text-xs text-foreground" data-testid="sap-link-undo-done">
              Proposed. It is waiting on the Register Checker on{" "}
              <Link href="/sap-links?tab=checker" className="text-primary hover:underline">Link to SAP</Link>.
            </p>
          ) : (
            <div className="space-y-3">
              <div>
                <label htmlFor="sap-link-undo-reason" className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                  Reason (required)
                </label>
                <textarea id="sap-link-undo-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)}
                  className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  data-testid="input-sap-link-undo-reason" />
              </div>
              {m.error && (
                <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
                  <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                  <ApiErrorMessage err={m.error} />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <button type="button" onClick={close}
              className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
              {m.data ? "Close" : "Cancel"}
            </button>
            {!m.data && (
              <button type="button" disabled={!ready || m.isPending} onClick={() => m.mutate()}
                data-testid="button-sap-link-undo-send"
                className={cn("px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
                  ready && !m.isPending ? "bg-primary text-primary-foreground hover:bg-primary/90"
                                        : "bg-muted text-muted-foreground cursor-not-allowed")}>
                {m.isPending && <Loader2 size={12} className="animate-spin" />}
                Propose the undo
              </button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
