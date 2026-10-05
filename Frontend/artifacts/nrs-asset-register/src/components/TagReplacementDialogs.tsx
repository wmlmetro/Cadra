import { useState } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RecordPicker from "@/components/RecordPicker";
import { CadraApiError } from "@/lib/api";
import {
  fetchApprovers, requestTagReplacement, approveTagReplacement, rejectTagReplacement,
  type ApprovalRef, type TagReplacementRaised, type TagReplacementApproved, type TagLabel,
} from "@/lib/dataProvider";
import { useEnum } from "@/hooks/useEnums";
import { AlertCircle, Check, Loader2, RefreshCw, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";

/**
 * Replacing a faded tag — the three dialogs (handoff 38).
 *
 * Modelled on `MarkMissingDialog` in `AssetActionDialogs.tsx`: the same
 * `Dialog`, the same error panel, the same rule that a USER cannot close the
 * dialog while the request is in flight (closing resets the mutation and a
 * refusal would then be shown nowhere) while the success handler may.
 *
 * It is a two-person flow on the tag model's own state machine: the request
 * names an approver and moves the label to `pending`; the approver — who the
 * model refuses to let be the requester — scraps it and mints the new number,
 * or sends it back to `active` with a reason. Nothing here decides anything;
 * the decider is the token on the call.
 */

/** Every query a tag write can change: the station's tiles and tables, the
 *  pending list, any fetched tag — and the asset's history, which the
 *  station's generate path already invalidates when a tag is issued. Since
 *  handoff 51 the Approvals queue lists replacements too, so its own query
 *  is on the list: a decision taken from either screen must leave both
 *  telling the truth. And since handoff 52 §1 the sidebar badge counts
 *  pending replacements beside movement requests, so deciding one must
 *  refresh the badge too — the movement dialogs' `invalidateApprovalQueries`
 *  has always done this for its half. */
export function invalidateTagQueries(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ["barcode-kpis"] });
  qc.invalidateQueries({ queryKey: ["barcode-recent"] });
  qc.invalidateQueries({ queryKey: ["tag-pending"] });
  qc.invalidateQueries({ queryKey: ["tag"] });
  qc.invalidateQueries({ queryKey: ["asset-history"] });
  qc.invalidateQueries({ queryKey: ["tag-replacements"] });
  qc.invalidateQueries({ queryKey: ["approval-count"] });
}

/** The approver picker's search — a copy of `searchApprovers` in
 *  `AssetActionDialogs.tsx`, which is not exported. `res.users`, NOT
 *  `hr.employee`; the endpoint already drops the caller from its answer. */
async function searchApprovers(q: string) {
  const users = await fetchApprovers(q, 10);
  return users.map(u => ({ id: u.id, label: u.name }));
}

const inputCls = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const labelCls = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";
const cancelCls = "px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground";

function ErrorPanel({ err }: { err: CadraApiError }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
      <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <ApiErrorMessage err={err} />
    </div>
  );
}

// ─── Request ────────────────────────────────────────────────────────────────

interface RequestProps {
  tagId: number;
  tagNumber: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the server's answer after the request is raised. */
  onRaised?: (res: TagReplacementRaised) => void;
}

export function RequestTagReplacementDialog({ tagId, tagNumber, open, onOpenChange, onRaised }: RequestProps) {
  const qc = useQueryClient();
  const reasons = useEnum("tag_replacement_reason");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [approver, setApprover] = useState<ApprovalRef | null>(null);

  const mutation = useMutation({
    mutationFn: () => requestTagReplacement(tagId, {
      reason, notes, approver_id: approver!.id,
    }),
    onSuccess: (res) => {
      invalidateTagQueries(qc);
      setOpen(false, true);
      onRaised?.(res);
    },
    // 409: the tag is no longer active — somebody else already asked, or it
    // was scrapped. Either way the screen is stale.
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateTagQueries(qc);
    },
  });
  const err = mutation.error as CadraApiError | null;
  const ready = Boolean(reason) && approver !== null;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      setNotes("");
      setApprover(null);
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-replace-tag">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw size={16} className="text-primary" /> Replace tag {tagNumber}
          </DialogTitle>
          <DialogDescription>
            Asks somebody else to approve a new label for this asset. Until they decide, nothing is scrapped or minted: the label is marked as pending replacement, and its number stops resolving on the scan box while the asset code still does. On approval the old number is scrapped and never reissued, a new number is minted, and the two are linked so the history survives.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label htmlFor="replace-reason" className={labelCls}>Why is it being replaced?</label>
            <select
              id="replace-reason"
              value={reason}
              onChange={e => setReason(e.target.value)}
              className={inputCls}
              data-testid="input-replace-reason"
            >
              <option value="">Choose a reason…</option>
              {reasons.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="replace-notes" className={labelCls}>Notes</label>
            <textarea
              id="replace-notes"
              rows={2}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              className={inputCls}
              placeholder="Optional — what the auditor saw, where the label is"
              data-testid="input-replace-notes"
            />
          </div>

          <div data-testid="replace-approver-field">
            <label className={labelCls}>Who are you asking to approve this?</label>
            <p className="text-[11px] text-muted-foreground mt-1">
              You cannot approve your own request — that is the point of one.
            </p>
            <div className="mt-1.5">
              <RecordPicker
                value={approver ? { id: approver.id, label: approver.name } : null}
                onChange={opt => setApprover(opt ? { id: opt.id, name: opt.label } : null)}
                search={searchApprovers}
                queryKey="picker-approvers"
                placeholder="Search people who can approve…"
                disabled={mutation.isPending}
              />
            </div>
          </div>

          {err && <ErrorPanel err={err} />}
        </div>

        <DialogFooter>
          <button type="button" onClick={() => setOpen(false)} className={cancelCls}>Cancel</button>
          <button
            type="button"
            disabled={!ready || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-replace"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              ready && !mutation.isPending
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Request replacement"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Approve ────────────────────────────────────────────────────────────────

interface DecideProps {
  tag: TagLabel;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ApproveTagReplacementDialog({ tag, open, onOpenChange, onApproved }: DecideProps & {
  onApproved?: (res: TagReplacementApproved) => void;
}) {
  const qc = useQueryClient();
  const reasonLabel = useEnum("tag_replacement_reason");
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => approveTagReplacement(tag.id, reason),
    onSuccess: (res) => {
      invalidateTagQueries(qc);
      setOpen(false, true);
      onApproved?.(res);
    },
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateTagQueries(qc);
    },
  });
  const err = mutation.error as CadraApiError | null;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  const why = reasonLabel.find(r => r.value === tag.replacement_reason)?.label ?? tag.replacement_reason ?? "—";

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-approve-replacement">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-green-700 dark:text-green-400">
            <Check size={16} /> Approve replacement of {tag.tag_number}
          </DialogTitle>
          <DialogDescription>
            Scraps this label and mints a new number for {tag.asset.name}. The old number is never reissued. Your name and the time are recorded as the decision.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
            <dt className="text-muted-foreground">Reason</dt>
            <dd className="font-semibold">{why}</dd>
            {tag.replacement_notes && (<>
              <dt className="text-muted-foreground">Notes</dt>
              <dd>{tag.replacement_notes}</dd>
            </>)}
            <dt className="text-muted-foreground">Requested by</dt>
            <dd>{tag.requested_by?.name ?? "—"}</dd>
          </dl>
          <div>
            <label htmlFor="approve-replacement-reason" className={labelCls}>Note (optional)</label>
            <textarea
              id="approve-replacement-reason"
              rows={2}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className={inputCls}
              placeholder="Anything the record should carry about this decision"
              data-testid="input-approve-replacement-reason"
            />
          </div>
          {err && <ErrorPanel err={err} />}
        </div>

        <DialogFooter>
          <button type="button" onClick={() => setOpen(false)} className={cancelCls}>Cancel</button>
          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-approve-replacement"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              !mutation.isPending
                ? "bg-green-600 text-white hover:bg-green-700"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Approve and mint new tag"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Reject ─────────────────────────────────────────────────────────────────

export function RejectTagReplacementDialog({ tag, open, onOpenChange, onRejected }: DecideProps & {
  onRejected?: () => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => rejectTagReplacement(tag.id, reason.trim()),
    onSuccess: () => {
      invalidateTagQueries(qc);
      setOpen(false, true);
      onRejected?.();
    },
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateTagQueries(qc);
    },
  });
  const err = mutation.error as CadraApiError | null;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-reject-replacement">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-700 dark:text-red-400">
            <XCircle size={16} /> Reject replacement of {tag.tag_number}
          </DialogTitle>
          <DialogDescription>
            The label goes back to active and keeps its number. {tag.requested_by?.name ?? "The person who asked"} is told why, so a reason is required.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label htmlFor="reject-replacement-reason" className={labelCls}>Why not?</label>
            <textarea
              id="reject-replacement-reason"
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className={inputCls}
              placeholder="Required — what the requester should do instead"
              data-testid="input-reject-reason"
            />
          </div>
          {err && <ErrorPanel err={err} />}
        </div>

        <DialogFooter>
          <button type="button" onClick={() => setOpen(false)} className={cancelCls}>Cancel</button>
          <button
            type="button"
            disabled={!reason.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-reject-replacement"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              reason.trim() && !mutation.isPending
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Reject"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
