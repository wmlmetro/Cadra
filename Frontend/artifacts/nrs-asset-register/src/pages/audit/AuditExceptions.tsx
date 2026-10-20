/**
 * Audit exceptions (handoff 66 §5, §6) — the items found in neither
 * register, after a reviewer accepted them. The Asset Controller's
 * (`audit:manage`).
 *
 * Each one carries the code the capturer printed and fixed to the item, so
 * the physical label must be accounted for either way:
 *
 *   Register as new  an asset whose label (the capture's code) is already
 *                    on it, waiting on the Register Maker — the normal maker
 *                    and checker gates, and SAP's master at the checker's
 *                    approval, because SAP does not hold it;
 *   Void             with a reason, which voids the code.
 *
 * Open ones first; the decided ones can be shown for the record.
 */
import { useEffect, useState } from "react";
import { Link } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import type { CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import {
  AUDIT_KEY, IDENTITY_FIELDS, fetchCaptures, registerException, voidException,
  type AuditCapture, type IdentityField,
} from "@/lib/auditCapture";
import {
  Btn, Empty, ErrorPanel, INPUT, Loading, PageHeader, Photo, Pill, TEXTAREA, invalidateAudit, n, when,
} from "./shared";

type Show = "open" | "registered" | "voided";

export default function AuditExceptions() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canManage = scopes.has(SCOPE.auditManage);
  const [show, setShow] = useState<Show>("open");

  useEffect(() => {
    setTitle("Audit exceptions");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const q = useQuery({
    queryKey: [...AUDIT_KEY, "exceptions", show],
    queryFn: () => fetchCaptures({ outcome: "in_neither", state: "accepted", exception_state: show, limit: 100 }),
    enabled: canManage,
  });

  if (!canManage) {
    return <ScopeRefusal scope={SCOPE.auditManage} detail="The Asset Controller holds it." />;
  }
  const rows = q.data?.rows ?? [];

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={<AlertTriangle size={15} />} title="Audit exceptions">
        Items an audit found in neither Cadra's register nor SAP's, accepted by a reviewer. Each carries the code
        printed for it: register it as new — through the Register Maker and Checker — or void it with a reason, which
        voids its code. Either way the label is accounted for.
      </PageHeader>
      <div className="px-5 py-3 border-b border-border flex gap-2 items-center">
        <label className="text-[11px] text-muted-foreground" htmlFor="exceptions-show">Show</label>
        <select id="exceptions-show" className={INPUT} value={show} onChange={e => setShow(e.target.value as Show)} data-testid="exceptions-show">
          <option value="open">Open</option>
          <option value="registered">Registered as new</option>
          <option value="voided">Voided</option>
        </select>
        {q.data && <span className="text-[11px] text-muted-foreground" data-testid="exceptions-count">{n(q.data.totalEstimate ?? rows.length)} {show}</span>}
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
        {q.error && <ErrorPanel err={q.error as CadraApiError} />}
        {q.isLoading ? <Loading what="Reading the exceptions…" /> : rows.length === 0 && !q.error ? (
          <Empty testid="exceptions-empty">{show === "open" ? "No exception is waiting on you." : `No exception was ${show === "registered" ? "registered as new" : "voided"}.`}</Empty>
        ) : rows.map(c => <ExceptionCard key={c.capture_id} c={c} />)}
      </div>
    </div>
  );
}

function ExceptionCard({ c }: { c: AuditCapture }) {
  const qc = useQueryClient();
  // Section 12 asks the class's serial and attributes of a unit going to the
  // register; what the capture lacks is completed here (prefilled from it).
  const [identity, setIdentity] = useState<Partial<Record<IdentityField, string>>>(() =>
    Object.fromEntries(IDENTITY_FIELDS.map(k => [k, typeof c.fields?.[k] === "string" ? String(c.fields[k]) : ""])));
  const reg = useMutation<AuditCapture, CadraApiError>({
    mutationFn: () => registerException(c.capture_id, identity), onSuccess: () => invalidateAudit(qc),
  });
  const [voiding, setVoiding] = useState(false);
  return (
    <div className="rounded-2xl border border-border bg-card p-3 flex gap-3 flex-wrap" data-testid={`exception-${c.capture_id}`}
         data-exception-state={c.exception_state ?? ""}>
      <div className="flex gap-2">{c.photos.slice(0, 2).map(p => <Photo key={p.id} url={p.url} size="sm" />)}</div>
      <div className="flex-1 min-w-0 space-y-1 text-[12px]">
        <p>
          <span className="font-semibold">{c.name ?? "—"}</span>
          {c.category && <span className="text-muted-foreground"> · {c.category.name}</span>}
          {c.condition && <span className="text-muted-foreground"> · {c.condition}</span>}
        </p>
        <p>Code <span className="font-mono font-semibold" data-testid="exception-code">{c.code ?? "—"}</span> · {c.location.name} · {c.campaign.name}</p>
        <p className="text-muted-foreground">
          Captured by {c.captured_by?.name ?? "—"}, {when(c.captured_at)} · accepted by {c.reviewed_by?.name ?? "—"}, {when(c.reviewed_at)}
        </p>
        {c.exception_state === "registered" && c.result_asset && (
          <p className="text-green-800 dark:text-green-300" data-testid="exception-registered">
            Registered as <Link href={`/assets/${c.result_asset.id}`} className="font-semibold hover:underline">{c.result_asset.asset_code}</Link>
            {" "}({c.result_asset.register_state}) by {c.exception_resolved_by?.name ?? "—"}, {when(c.exception_resolved_at)} — waiting on the Register Maker.
          </p>
        )}
        {c.exception_state === "voided" && (
          <p className="text-muted-foreground" data-testid="exception-voided">
            <Pill tone="red">Voided</Pill> by {c.exception_resolved_by?.name ?? "—"}, {when(c.exception_resolved_at)}: {c.exception_void_reason}
          </p>
        )}
        {c.exception_state === "open" && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1" data-testid={`exception-identity-${c.capture_id}`}>
            {IDENTITY_FIELDS.map(k => (
              <label key={k} className="text-[11px] text-muted-foreground flex flex-col gap-0.5">
                {IDENTITY_WORDS[k]}
                <input className={INPUT} value={identity[k] ?? ""} data-testid={`exception-${k}`}
                       onChange={e => setIdentity(v => ({ ...v, [k]: e.target.value }))} />
              </label>
            ))}
          </div>
        )}
        {c.exception_state === "open" && (
          <div className="flex gap-2 pt-1">
            <Btn testid={`button-register-new-${c.capture_id}`} pending={reg.isPending} onClick={() => reg.mutate()}>Register as new</Btn>
            <Btn kind="plain" testid={`button-void-${c.capture_id}`} onClick={() => setVoiding(true)}>Void</Btn>
          </div>
        )}
        {reg.error && <ErrorPanel err={reg.error} testid="register-new-error" />}
      </div>
      {voiding && <VoidDialog c={c} onClose={() => setVoiding(false)} />}
    </div>
  );
}

const IDENTITY_WORDS: Record<IdentityField, string> = {
  serial_number: "Serial number", make: "Make", model_name: "Model",
  colour: "Colour", material: "Material", dimensions: "Dimensions",
};

function VoidDialog({ c, onClose }: { c: AuditCapture; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const m = useMutation<AuditCapture, CadraApiError>({
    mutationFn: () => voidException(c.capture_id, reason),
    onSuccess: () => { invalidateAudit(qc); onClose(); },
  });
  return (
    <Dialog open onOpenChange={(next) => { if (!next && !m.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-md" data-testid="void-dialog">
        <DialogHeader>
          <DialogTitle>Void {c.name ?? "this exception"}</DialogTitle>
          <DialogDescription>Code {c.code} is voided with it and never issued again. Say why.</DialogDescription>
        </DialogHeader>
        <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} className={TEXTAREA}
                  data-testid="input-void-reason" aria-label="Reason" />
        {m.error && <ErrorPanel err={m.error} testid="void-error" />}
        <DialogFooter>
          <Btn kind="plain" onClick={onClose}>Cancel</Btn>
          <Btn kind="danger" testid="button-void-send" disabled={!reason.trim()} pending={m.isPending} onClick={() => m.mutate()}>Void it</Btn>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
