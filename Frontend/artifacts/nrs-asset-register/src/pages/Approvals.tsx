/**
 * The approval queue — *what is waiting on me* (handoff 35).
 *
 * A move or a custody change on a register that requires approval is not an
 * act any more, it is a REQUEST: `POST /assets/<id>/move` raises one and moves
 * nothing, and the change happens — or does not — when a second person decides
 * here. This is the only screen on which that second person exists.
 *
 * WHAT THIS SCREEN IS NOT ALLOWED TO DO
 * -------------------------------------
 * **Offer a button the server will refuse.** Three of the server's rules are
 * read off the record rather than re-implemented here, and every one of them
 * is computed FRESH on each read:
 *
 *   `can_decide`     false on a request the caller raised themselves, and on
 *                    one they could not have made the change for. Per caller.
 *   `can_withdraw`   only the requester, only while pending.
 *   `premise_holds`  whether the world the request was raised in still holds.
 *                    An asset moved or disposed of underneath a pending
 *                    request makes it unapprovable, and the server says what
 *                    changed. **Only meaningful on a PENDING row** — the model
 *                    returns `true` for every decided one rather than
 *                    re-judging closed history, so this file never reads it
 *                    without checking the state first.
 *
 *   `can_renominate` the requester or an administrator, while pending — who
 *                    may re-point the request at somebody else (handoff 45).
 *
 * The model remains the authority in every case; this only declines to offer.
 * A hidden button is a door closed on one screen, and report 30 found a
 * disposed asset being un-disposed through a route nobody had looked at.
 *
 * THE FOUR TABS, AND THE ONE THAT CANNOT BE SERVER-FILTERED
 * ---------------------------------------------------------
 * `GET /api/v1/approvals` takes ONE `state`. Three of the tabs want one state
 * or none; *Decided* wants "approved or rejected or withdrawn", which is three
 * and is not expressible. Rather than fire three requests and interleave three
 * cursors, that tab asks for every state and drops the pending rows in the
 * browser — and then says so, because a count taken over a client-filtered
 * page is not a count of the register and printing it as one is how
 * *"1,146 tracked moves"* got into a report. The row counter under that tab
 * names its denominator; a state picked explicitly goes back to the server.
 *
 * TWO KINDS IN THE SAME TABS, TWO QUERIES (handoff 51 §1b)
 * --------------------------------------------------------
 * Tag replacements are the SAME two-person pattern on the tag model's own
 * state machine, and until handoff 51 they were displayed only on a tagging
 * console an Asset Manager has no reason to open. They now share these tabs
 * — but as a second SECTION under the movement list, fed by
 * `GET /api/v1/tags/replacements` through its own infinite query, its own
 * cursor and its own count. Never interleaved: the two routes' cursors mean
 * nothing to each other, and a second source threaded behind one list is
 * the obvious way to break the single-`state` structure above by accident.
 *
 * The decided picker's outcomes map onto the label's own lifecycle —
 * approved → `scrapped` (the print is voided and, since handoff 61, the
 * label reprinted under the SAME number — before 61 a new number was minted),
 * rejected → `active` (back in service). "Withdrawn" has no tag meaning: a
 * tag replacement cannot be withdrawn, and the section says that in a
 * sentence rather than presenting an empty table as a fact about the world.
 * With no outcome picked the section fetches every state and drops the
 * pending rows in the browser, naming its denominator the same way the
 * movement counter does.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "wouter";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import RecordLink from "@/components/RecordLink";
import RecordPicker from "@/components/RecordPicker";
import {
  invalidateApprovalQueries, invalidateAssetQueries, useApprovalRequirement,
} from "@/components/AssetActionDialogs";
import {
  ApproveTagReplacementDialog, RejectTagReplacementDialog,
} from "@/components/TagReplacementDialogs";
import { CadraApiError, apiConfigured } from "@/lib/api";
import {
  approveChangeRequest, fetchApprovalsPage, fetchApprovers, fetchTagReplacementsPage,
  fetchWhoAmI, printName, rejectChangeRequest, renominateChangeRequest, withdrawChangeRequest,
  type ApprovalFilters, type ApprovalRef, type ApprovalRequest, type ApprovalState,
  type ApprovalsPage, type TagLabel, type TagReplacementFilters, type TagReplacementsPage,
} from "@/lib/dataProvider";
import { useEnumLabel } from "@/hooks/useEnums";
import { SCOPE, useScopes } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";
import {
  AlertCircle, ArrowRight, ArrowRightLeft, CheckCircle2, Clock, History, Inbox, MapPin,
  Undo2, User, UserX, XCircle,
} from "lucide-react";

// ─── small shared bits ─────────────────────────────────────────────────────

/**
 * The server's own timestamp, printed as the server wrote it.
 *
 * `2026-09-22T14:05:11` → `2026-09-22 14:05`. NOT converted to the browser's
 * zone, and that is the same choice `AssetHistoryTimeline` makes: every other
 * clock in this system — the disposal date, the Lagos day a warranty expires
 * on — is the server's, and a queue that showed *yesterday* for a request
 * raised an hour ago because the reader is west of Greenwich would be the
 * one-hour-a-night bug of handoff 30 in a new place.
 */
function stamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

const STATE_STYLE: Record<ApprovalState, string> = {
  pending:   "bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border-amber-200/70 dark:border-amber-800/30",
  approved:  "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 border-emerald-200/70 dark:border-emerald-800/30",
  rejected:  "bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 border-red-200/70 dark:border-red-800/30",
  withdrawn: "bg-muted text-muted-foreground border-border",
};

const STATE_WORD: Record<ApprovalState, string> = {
  pending: "Waiting", approved: "Approved", rejected: "Rejected", withdrawn: "Withdrawn",
};

function StatePill({ state }: { state: ApprovalState }) {
  return (
    <span
      className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg border", STATE_STYLE[state])}
      data-testid="approval-state-pill"
      data-state={state}
    >
      {STATE_WORD[state] ?? state}
    </span>
  );
}

/**
 * From → to, in words, with the "from" labelled for what it actually is.
 *
 * `from_location_name` is a STRING COPY taken when the request was raised, not
 * a live read — the record keeps it so that renaming a location or deleting an
 * employee cannot empty the premise it was judged against. On a PENDING row
 * whose `premise_holds` is true it is also what is true right now, because
 * that is precisely what the premise check asserts (`_premise_check`: the
 * asset's location, custodian and status all still match what was recorded).
 * When the premise has broken, or the row is decided, the label says *when
 * this was raised* instead — claiming "now" over a string taken days ago is
 * the kind of quiet untruth this screen exists to stop.
 */
function ChangeSummary({ r }: { r: ApprovalRequest }) {
  const live = r.state === "pending" && r.premise_holds;
  const isLocation = r.change_type === "location";
  const from = isLocation
    ? (r.from_location_name ?? r.from_location?.name ?? null)
    : (r.from_custodian_name ?? r.from_custodian?.name ?? null);
  const to = isLocation
    ? (r.to_location_name ?? r.to_location?.name ?? null)
    : (r.to_custodian_name ?? r.to_custodian?.name ?? null);
  return (
    <div className="flex items-center gap-2 flex-wrap text-[12px]" data-testid="approval-change">
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        {isLocation ? <MapPin size={11} /> : <User size={11} />}
        {isLocation ? "Location" : "Custodian"}
      </span>
      <span className="text-foreground" data-testid="approval-change-from">
        {from ?? <span className="italic text-muted-foreground">nobody / nowhere</span>}
      </span>
      <ArrowRight size={11} className="text-muted-foreground/60 shrink-0" />
      <span className="font-semibold text-foreground" data-testid="approval-change-to">
        {to ?? <span className="italic text-muted-foreground">—</span>}
      </span>
      <span className="text-[10px] text-muted-foreground/80">
        ({live ? "left-hand value is where it is now" : "left-hand value is as at the request"})
      </span>
    </div>
  );
}

// ─── the decision dialog ───────────────────────────────────────────────────

type DecisionMode = "approve" | "reject" | "withdraw";

const DECISION_COPY: Record<DecisionMode, {
  title: string;
  description: (r: ApprovalRequest) => string;
  label: string;
  reasonLabel: string;
  reasonRequired: boolean;
  placeholder: string;
  tone: string;
}> = {
  approve: {
    title: "Approve this change",
    description: (r) => r.change_type === "location"
      ? "Approving MOVES the asset, now. The move is written to the asset's movement record, which nobody can edit or delete afterwards, and your name is on the approval."
      : "Approving HANDS THE ASSET OVER, now. The change is written to the asset's chain of custody, which nobody can edit or delete afterwards, and your name is on the approval.",
    label: "Approve",
    reasonLabel: "Note (optional)",
    reasonRequired: false,
    placeholder: "e.g. Checked with the store — fine.",
    tone: "bg-emerald-600 hover:bg-emerald-700",
  },
  reject: {
    title: "Reject this change",
    description: () => "The asset stays exactly where it is and with whoever holds it. The person who asked sees your reason, so say something they can act on — a rejection without one only gets asked again.",
    label: "Reject",
    reasonLabel: "Why are you rejecting it?",
    // The route 400s on a blank one. The button is disabled before that, so
    // the requirement is visible rather than discovered.
    reasonRequired: true,
    placeholder: "Required — the person who asked reads this",
    tone: "bg-red-600 hover:bg-red-700",
  },
  withdraw: {
    title: "Withdraw your request",
    description: () => "Takes your own request back. Nothing about the asset changes, the approver stops seeing it in their queue, and the record of having asked stays.",
    label: "Withdraw",
    reasonLabel: "Note (optional)",
    reasonRequired: false,
    placeholder: "e.g. Asked the wrong person.",
    tone: "bg-slate-600 hover:bg-slate-700",
  },
};

function DecisionDialog({
  request, mode, open, onOpenChange,
}: {
  request: ApprovalRequest;
  mode: DecisionMode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const copy = DECISION_COPY[mode];

  const mutation = useMutation({
    mutationFn: () => {
      if (mode === "approve") return approveChangeRequest(request.id, reason.trim() || undefined);
      if (mode === "reject") return rejectChangeRequest(request.id, reason.trim());
      return withdrawChangeRequest(request.id, reason.trim() || undefined);
    },
    onSuccess: () => {
      // BOTH, and in this order of reasoning: the queue changed for every
      // outcome, and the ASSET changed for exactly one of them — an approval
      // moves it. The asset list is invalidated on a rejection too, which
      // refetches a little for nothing; the alternative is a branch that has
      // to stay right, and an approval that failed to refresh the register
      // would leave the asset page showing the old location with a green
      // "Approved" beside it.
      invalidateApprovalQueries(qc, request.asset?.id);
      invalidateAssetQueries(qc, request.asset ? String(request.asset.id) : undefined);
      qc.invalidateQueries({ queryKey: ["dashboard-map"] });
      qc.invalidateQueries({ queryKey: ["employee-assets"] });
      setOpen(false, true);
    },
    // A 409 means this screen is out of date — somebody decided it first, or
    // the premise broke under it. The dialog stays open on the server's
    // sentence and the list behind it is refetched, so closing lands on the
    // truth. Same shape as `CondemnAssetDialog`.
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateApprovalQueries(qc, request.asset?.id);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Reset on every close — see `AssetActionDialogs`, including why the success
  // handler passes `done`: `isPending` still reads true in that closure.
  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  const ready = !mutation.isPending && (!copy.reasonRequired || !!reason.trim());

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid={`dialog-approval-${mode}`}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {mode === "approve" ? <CheckCircle2 size={16} />
              : mode === "reject" ? <XCircle size={16} />
              : <Undo2 size={16} />}
            {copy.title}
          </DialogTitle>
          <DialogDescription>{copy.description(request)}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="rounded-xl border border-border bg-muted/30 px-3 py-2.5">
            <p className="text-[11px] font-mono font-semibold text-foreground">{request.reference}</p>
            <p className="text-[12px] text-foreground mt-0.5">{request.asset?.name ?? "—"}</p>
            <div className="mt-1.5"><ChangeSummary r={request} /></div>
          </div>
          <div>
            <label
              htmlFor={`approval-reason-${mode}`}
              className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
            >
              {copy.reasonLabel}
            </label>
            <textarea
              id={`approval-reason-${mode}`}
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder={copy.placeholder}
              data-testid={`input-approval-${mode}-reason`}
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="approval-decision-error">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={err} />
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!ready}
            onClick={() => mutation.mutate()}
            data-testid={`button-confirm-approval-${mode}`}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl text-white",
              ready ? copy.tone : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Clock size={12} className="animate-pulse" /> : copy.label}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── ask someone else (handoff 45, G.1(b)) ──────────────────────────────────

/**
 * Re-point a pending request at a different approver.
 *
 * WHY THIS EXISTS. Deactivating an account is never blocked — cutting
 * somebody off happens the moment it is decided, and a queue must never be
 * able to hold an account open. So a request left waiting on somebody who has
 * left is fixed FORWARD, here, by the person who raised it or an
 * administrator. The server records who did it, when, from whom, to whom and
 * why on a row nobody can edit, and the row shows that history.
 *
 * The picker is the same search the Move dialog uses (`GET /approvals/
 * approvers`, which already drops the caller). Two more names are dropped
 * here because the server refuses them — the person who raised the request
 * and the person already asked — and a picker offering a refused choice is an
 * answer that looks like an answer. The server still checks everything.
 */
function RenominateDialog({
  request, open, onOpenChange,
}: {
  request: ApprovalRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<ApprovalRef | null>(null);
  const [reason, setReason] = useState("");
  const inactive = request.approver?.active === false;

  const excluded = new Set<number>(
    [request.requested_by?.id, request.approver?.id].filter((x): x is number => typeof x === "number"),
  );
  const search = async (q: string) => {
    const users = await fetchApprovers(q, 10);
    return users.filter(u => !excluded.has(u.id)).map(u => ({ id: u.id, label: u.name }));
  };

  const mutation = useMutation({
    mutationFn: () => renominateChangeRequest(request.id, target!.id, reason.trim()),
    // Nothing about the ASSET changes, so only the approval queries are
    // refreshed — the queue, the badge, and the asset page's pending banner.
    onSuccess: () => {
      invalidateApprovalQueries(qc, request.asset?.id);
      setOpen(false, true);
    },
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateApprovalQueries(qc, request.asset?.id);
    },
  });
  const err = mutation.error as CadraApiError | null;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setTarget(null);
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  const ready = !mutation.isPending && !!target && !!reason.trim();

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-approval-renominate">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft size={16} /> Ask someone else
          </DialogTitle>
          <DialogDescription>
            {inactive
              ? `${request.approver?.name ?? "The approver"} cannot sign in — their account has been deactivated — so nobody is going to answer this request where it is. Choose somebody else to ask.`
              : "Send this request to a different approver. It stays pending, nothing about the asset changes, and the person you choose sees it in their queue."}
            {" "}Your name, the time and your reason are recorded on the request, and that record cannot be changed afterwards.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="rounded-xl border border-border bg-muted/30 px-3 py-2.5">
            <p className="text-[11px] font-mono font-semibold text-foreground">{request.reference}</p>
            <p className="text-[12px] text-foreground mt-0.5">{request.asset?.name ?? "—"}</p>
            <p className="text-[11px] text-muted-foreground mt-1">
              Waiting on <span className="font-semibold text-foreground">{request.approver?.name ?? "—"}</span>
              {inactive && <span className="text-red-700 dark:text-red-400"> — cannot sign in</span>}
            </p>
          </div>
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
              Who should be asked instead?
            </label>
            <p className="text-[11px] text-muted-foreground mt-1">
              Only people who could have made this change themselves are listed. The person who raised
              the request cannot be asked, and nor can somebody whose account is deactivated.
            </p>
            <div className="mt-1.5" data-testid="renominate-approver-field">
              <RecordPicker
                value={target ? { id: target.id, label: target.name } : null}
                onChange={opt => setTarget(opt ? { id: opt.id, name: opt.label } : null)}
                search={search}
                queryKey={`picker-renominate-${request.id}`}
                placeholder="Search people who can approve…"
                disabled={mutation.isPending}
              />
            </div>
          </div>
          <div>
            <label
              htmlFor={`approval-renominate-reason-${request.id}`}
              className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
            >
              Why are you asking someone else?
            </label>
            <textarea
              id={`approval-renominate-reason-${request.id}`}
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="Required — e.g. The approver has left the service."
              data-testid="input-approval-renominate-reason"
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="approval-renominate-error">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={err} />
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!ready}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-approval-renominate"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl text-white",
              ready ? "bg-primary hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Clock size={12} className="animate-pulse" /> : "Ask them instead"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Who this request has been re-pointed at before, oldest first. The server
 * keeps it on an append-only row; `approver` only ever says who is asked NOW,
 * so without this a reader could not tell that somebody else was asked first,
 * or who changed it.
 */
function RenominationHistory({ r }: { r: ApprovalRequest }) {
  const trail = r.renominations ?? [];
  if (trail.length === 0) return null;
  return (
    <ul className="space-y-0.5" data-testid="approval-renominations">
      {trail.map(n => (
        <li key={n.id} className="flex items-start gap-1.5 text-[11px] text-muted-foreground" data-testid="approval-renomination">
          <History size={11} className="shrink-0 mt-0.5" />
          <span>
            Re-pointed from <span className="font-semibold text-foreground">{n.from.name ?? "—"}</span>
            {" "}to <span className="font-semibold text-foreground">{n.to.name ?? "—"}</span>
            {" "}by <span className="font-semibold text-foreground">{n.by.name ?? "—"}</span>
            {" "}on {stamp(n.at)}
            {n.reason && <> — “{n.reason}”</>}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ─── one row ───────────────────────────────────────────────────────────────

function ApprovalRow({ r }: { r: ApprovalRequest }) {
  const scopes = useScopes();
  const [mode, setMode] = useState<DecisionMode | null>(null);
  const [renominating, setRenominating] = useState(false);

  const pending = r.state === "pending";
  // `premise_holds` is only computed for a pending row; the model answers
  // `true` for every decided one rather than re-judging closed history, so
  // reading it without this guard would paint an old rejection as applicable.
  const broken = pending && !r.premise_holds;
  // The server decides; these only stop the interface offering a refusal.
  // The scope check is the second half of the same idea — `approvals:write`
  // is what the two decision routes require, and an Auditor holds none of it.
  const mayDecide = pending && r.can_decide && !broken && scopes.has(SCOPE.approvalsWrite);
  const mayWithdraw = pending && r.can_withdraw && scopes.has(SCOPE.assetsWrite);
  // `assets:write` is what the route requires — the same scope as raising a
  // request. `can_renominate` is the server's answer per caller.
  const mayRenominate = pending && r.can_renominate && scopes.has(SCOPE.assetsWrite);
  // G.1(a): the person it is waiting on has had their account deactivated.
  // Only said of a PENDING row — on a decided one nobody is waiting.
  const approverGone = pending && r.approver?.active === false;

  return (
    <li className="px-5 py-3.5" data-testid="approval-row" data-reference={r.reference} data-state={r.state}>
      <div className="flex items-start gap-3 flex-wrap">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] font-mono font-semibold text-foreground">{r.reference}</span>
            <StatePill state={r.state} />
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border">
              {r.change_type === "location" ? "Move" : "Custody"}
            </span>
            {r.asset && (
              <RecordLink to={`/assets/${r.asset.id}`} subtle>
                <span className="text-[12px] font-semibold">{r.asset.name}</span>
              </RecordLink>
            )}
            {r.asset_code && <span className="text-[11px] font-mono text-muted-foreground">{r.asset_code}</span>}
          </div>

          <ChangeSummary r={r} />

          {/* WHO ASKED and WHO WAS ASKED, never folded together. The name is
              read from the string copy first: `requested_by_name` survives the
              user record being archived or renamed, which the link does not. */}
          <p className="text-[11px] text-muted-foreground" data-testid="approval-who">
            Asked by <span className="font-semibold text-foreground">
              {r.requested_by_name ?? r.requested_by?.name ?? "—"}
            </span>
            {" "}on {stamp(r.requested_at)}
            {r.approver && <>
              {" · "}{pending ? "waiting on" : "asked"}{" "}
              <span className="font-semibold text-foreground">{r.approver.name}</span>
              {approverGone && (
                <span className="font-semibold text-red-700 dark:text-red-400" data-testid="approval-approver-inactive">
                  {" "}— {r.approver.name} cannot sign in
                </span>
              )}
            </>}
          </p>

          <RenominationHistory r={r} />

          {/* WHY NOBODY IS GOING TO ANSWER THIS. Not a tooltip, for the reason
              the premise note below gives. Anyone eligible can still decide
              it, which is said, because the queue is not stuck for them. */}
          {approverGone && (
            <div
              className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-2.5 mt-1"
              data-testid="approval-approver-cannot-sign-in"
              role="note"
            >
              <UserX size={13} className="text-red-700 dark:text-red-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-red-800 dark:text-red-300">
                <span className="font-semibold">The approver cannot sign in.</span>{" "}
                {r.approver?.name}'s account has been deactivated, so this request will wait for ever
                where it is.{" "}
                {mayRenominate
                  ? "Ask someone else to approve it."
                  : `${r.requested_by_name ?? r.requested_by?.name ?? "The person who raised it"}, or an administrator, can ask someone else.`}
                {" "}Anybody else able to approve it can still decide it now.
              </p>
            </div>
          )}

          {r.reason && (
            <p className="text-[12px] text-foreground/90" data-testid="approval-reason">
              <span className="text-muted-foreground">Reason given: </span>{r.reason}
            </p>
          )}

          {/* The decision, once there is one. `decided_by` is WHO CLICKED and
              is a different field from `approver` on purpose — the person
              asked and the person who answered need not be the same, because
              anyone eligible may decide any pending request. */}
          {!pending && (
            <p className="text-[11px] text-muted-foreground" data-testid="approval-decision">
              {STATE_WORD[r.state]} by <span className="font-semibold text-foreground">
                {r.decided_by_name ?? r.decided_by?.name ?? "—"}
              </span>
              {" "}on {stamp(r.decided_at)}
              {r.decision_reason && <> — “{r.decision_reason}”</>}
            </p>
          )}

          {/* WHY THERE IS NO APPROVE BUTTON. Not a tooltip: this app is shown
              to the client on a tablet, where nothing is ever hovered. */}
          {broken && (
            <div
              className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-2.5 mt-1"
              data-testid="approval-premise-broken"
              role="note"
            >
              <AlertCircle size={13} className="text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                <span className="font-semibold">This can no longer be approved.</span>{" "}
                {r.premise_broken_reason ?? "The asset has changed since this was raised."}{" "}
                Reject it, or raise a new request if the change is still wanted.
              </p>
            </div>
          )}
          {pending && !broken && !r.can_decide && (
            <p className="text-[11px] text-muted-foreground italic" data-testid="approval-not-yours">
              {r.can_withdraw
                ? "You raised this one, so you cannot approve it — that is the point of an approval."
                : "This is not yours to decide: an approver has to be somebody who could have made the change themselves."}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
          {mayDecide && (
            <>
              <button
                type="button"
                onClick={() => setMode("approve")}
                data-testid="button-approve"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-200/70 dark:border-emerald-800/30 text-xs font-semibold text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
              >
                <CheckCircle2 size={12} /> Approve
              </button>
              <button
                type="button"
                onClick={() => setMode("reject")}
                data-testid="button-reject"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200/70 dark:border-red-800/30 text-xs font-semibold text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
              >
                <XCircle size={12} /> Reject
              </button>
            </>
          )}
          {/* Rejecting is still open when the premise has broken: the request
              is dead either way and somebody has to close it, and the route
              allows it. Only APPROVE is withheld. */}
          {pending && broken && r.can_decide && scopes.has(SCOPE.approvalsWrite) && (
            <button
              type="button"
              onClick={() => setMode("reject")}
              data-testid="button-reject"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200/70 dark:border-red-800/30 text-xs font-semibold text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
            >
              <XCircle size={12} /> Reject
            </button>
          )}
          {mayRenominate && (
            <button
              type="button"
              onClick={() => setRenominating(true)}
              data-testid="button-renominate"
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium",
                approverGone
                  ? "border-red-200/70 dark:border-red-800/30 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 font-semibold"
                  : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <ArrowRightLeft size={12} /> Ask someone else
            </button>
          )}
          {mayWithdraw && (
            <button
              type="button"
              onClick={() => setMode("withdraw")}
              data-testid="button-withdraw"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Undo2 size={12} /> Withdraw
            </button>
          )}
        </div>
      </div>

      {renominating && (
        <RenominateDialog
          request={r}
          open
          onOpenChange={(next) => { if (!next) setRenominating(false); }}
        />
      )}
      {mode && (
        <DecisionDialog
          request={r}
          mode={mode}
          open
          onOpenChange={(next) => { if (!next) setMode(null); }}
        />
      )}
    </li>
  );
}

// ─── one tag-replacement row (handoff 51 §1b) ──────────────────────────────

/**
 * The label's lifecycle in words a person reads without the state machine in
 * hand. `scrapped` IS the approval — the print is voided and the label
 * reprinted (under the same number since handoff 61) — and `active` after a
 * request is usually a rejection, but the
 * record is the authority: a row with no `rejected_by` is only "active
 * again", because claiming "rejected" over a field that does not say so is
 * the quiet untruth this screen exists to stop.
 */
function replacementStateWord(t: TagLabel): string {
  if (t.state === "pending") return "Waiting";
  if (t.state === "scrapped") return "Approved — replaced";
  return t.rejected_by ? "Rejected" : "Active again";
}

function replacementStateStyle(t: TagLabel): string {
  if (t.state === "pending") return STATE_STYLE.pending;
  if (t.state === "scrapped") return STATE_STYLE.approved;
  return t.rejected_by ? STATE_STYLE.rejected : STATE_STYLE.withdrawn;
}

function ReplacementRow({ t, meId }: { t: TagLabel; meId: number | null | undefined }) {
  const scopes = useScopes();
  const reasonLabelOf = useEnumLabel("tag_replacement_reason");
  const [deciding, setDeciding] = useState<"approve" | "reject" | null>(null);

  const pending = t.state === "pending";
  // The same pair `ApprovalRow` reads: `can_decide` is the server's answer
  // about THIS label per caller, the scope is the session's answer about
  // every label. Both have to be yes, or the button is one the decision
  // routes would refuse.
  const mayDecide = pending && t.can_decide && scopes.has(SCOPE.approvalsWrite);
  // `can_decide: false` does not say WHY it is not yours, and the two
  // reasons deserve different sentences. The requester is recognised by
  // comparing `requested_by` with the shared `whoami` query; when that id
  // has not arrived the row falls back to the general sentence rather than
  // claiming an authorship it cannot show.
  const mine = meId != null && t.requested_by?.id === meId;

  return (
    <li className="px-5 py-3.5" data-testid="replacement-row" data-tag={t.tag_number} data-state={t.state}>
      <div className="flex items-start gap-3 flex-wrap">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] font-mono font-semibold text-foreground">{t.tag_number}</span>
            <span
              className={cn("text-[10px] font-bold px-2 py-0.5 rounded-lg border", replacementStateStyle(t))}
              data-testid="replacement-state-pill"
              data-state={t.state}
            >
              {replacementStateWord(t)}
            </span>
            {/* The kind, said on the row — two kinds share these tabs now,
                and a row that does not say which it is reads as the other. */}
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border">
              Tag replacement
            </span>
            {t.asset && (
              <RecordLink to={`/assets/${t.asset.id}`} subtle>
                <span className="text-[12px] font-semibold">{t.asset.name}</span>
              </RecordLink>
            )}
            {t.asset_code && <span className="text-[11px] font-mono text-muted-foreground">{t.asset_code}</span>}
            {/* Which print of the number this row is (handoff 61): two
                prints of one number carry the same tag number and differ
                only in this. Shown for a reprint; the original says nothing. */}
            {t.reprint_count > 0 && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border" data-testid="replacement-print">
                {printName(t.reprint_count)}
              </span>
            )}
          </div>

          {/* WHO ASKED and WHO WAS ASKED, never folded together — the same
              sentence shape as the movement rows above. */}
          <p className="text-[11px] text-muted-foreground" data-testid="replacement-who">
            Asked by <span className="font-semibold text-foreground">{t.requested_by?.name ?? "—"}</span>
            {" "}on {stamp(t.requested_at)}
            {t.approver && <>
              {" · "}{pending ? "waiting on" : "asked"}{" "}
              <span className="font-semibold text-foreground">{t.approver.name}</span>
            </>}
          </p>

          <p className="text-[12px] text-foreground/90" data-testid="replacement-reason">
            <span className="text-muted-foreground">Reason given: </span>
            {reasonLabelOf(t.replacement_reason)}
            {t.replacement_notes && <> — {t.replacement_notes}</>}
          </p>

          {/* The decision, once there is one. `approved_by` / `rejected_by`
              is WHO CLICKED, a different field from `approver` on purpose —
              anyone eligible may decide any pending replacement. A scrapped
              row also names its successor: since handoff 61 the reprint
              under the SAME number, said with its count, because the number
              alone would not tell the two prints apart; a replacement made
              before 61 names the different number it was given. */}
          {t.state === "scrapped" && (
            <p className="text-[11px] text-muted-foreground" data-testid="replacement-decision">
              Approved by <span className="font-semibold text-foreground">{t.approved_by?.name ?? "—"}</span>
              {" "}on {stamp(t.approved_at)}
              {t.decision_reason && <> — “{t.decision_reason}”</>}
              {t.replaced_by && (t.replaced_by.tag_number === t.tag_number ? <>
                {" · "}{printName(t.reprint_count)} voided{t.voided_at && <> on {stamp(t.voided_at)}</>};
                {" "}replaced by{" "}
                <span className="font-semibold text-foreground" data-testid="replacement-reprint">
                  {printName(t.replaced_by.reprint_count)} under the same number
                </span>
              </> : <>
                {" · "}replaced by{" "}
                <span className="font-mono font-semibold text-foreground">{t.replaced_by.tag_number}</span>
              </>)}
            </p>
          )}
          {t.state === "active" && t.rejected_by && (
            <p className="text-[11px] text-muted-foreground" data-testid="replacement-decision">
              Rejected by <span className="font-semibold text-foreground">{t.rejected_by.name}</span>
              {" "}on {stamp(t.rejected_at)}
              {t.decision_reason && <> — “{t.decision_reason}”</>}
            </p>
          )}

          {pending && !t.can_decide && (
            <p className="text-[11px] text-muted-foreground italic" data-testid="replacement-not-yours">
              {mine
                ? "You asked for this replacement, so you cannot decide it — ask an approver to reject it, or let it stand."
                : "Not yours to decide — an approver must hold the Asset Manager role."}
            </p>
          )}
        </div>

        {mayDecide && (
          <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
            <button
              type="button"
              onClick={() => setDeciding("approve")}
              data-testid="button-approve-replacement"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-200/70 dark:border-emerald-800/30 text-xs font-semibold text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
            >
              <CheckCircle2 size={12} /> Approve
            </button>
            <button
              type="button"
              onClick={() => setDeciding("reject")}
              data-testid="button-reject-replacement"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200/70 dark:border-red-800/30 text-xs font-semibold text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
            >
              <XCircle size={12} /> Reject
            </button>
          </div>
        )}
      </div>

      {/* The station's own dialogs, unchanged — their success handler runs
          `invalidateTagQueries`, which now refetches this queue too. */}
      {deciding === "approve" && (
        <ApproveTagReplacementDialog tag={t} open onOpenChange={(next) => { if (!next) setDeciding(null); }} />
      )}
      {deciding === "reject" && (
        <RejectTagReplacementDialog tag={t} open onOpenChange={(next) => { if (!next) setDeciding(null); }} />
      )}
    </li>
  );
}

// ─── the page ──────────────────────────────────────────────────────────────

type TabKey = "waiting" | "pending" | "mine" | "decided";

const TABS: { key: TabKey; label: string; hint: string }[] = [
  { key: "waiting", label: "Waiting on me", hint: "Pending requests that name you as the approver" },
  { key: "pending", label: "All pending",   hint: "Everything waiting on anybody" },
  { key: "mine",    label: "Raised by me",  hint: "What you asked for, and what happened to it" },
  { key: "decided", label: "Decided",       hint: "Approved, rejected and withdrawn" },
];

/** The three states a request can end in. Used only by the *Decided* tab's
 *  narrowing select — the list route takes one `state` at a time. */
const DECIDED_STATES: ApprovalState[] = ["approved", "rejected", "withdrawn"];

export default function Approvals() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  const [tab, setTab] = useState<TabKey>("waiting");
  /** Empty string = "any outcome", which the server cannot express. See the
   *  file docstring. */
  const [decidedState, setDecidedState] = useState<"" | ApprovalState>("");
  const approval = useApprovalRequirement();

  useEffect(() => {
    setTitle("Approvals");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const filters: ApprovalFilters = useMemo(() => {
    if (tab === "waiting") return { waiting_on_me: true, state: "pending" };
    if (tab === "pending") return { state: "pending" };
    if (tab === "mine") return { raised_by_me: true };
    return decidedState ? { state: decidedState } : {};
  }, [tab, decidedState]);

  /** True when the rows that come back have to be narrowed in the browser. */
  const clientFiltered = tab === "decided" && !decidedState;

  const {
    data, isLoading, error,
    fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery<ApprovalsPage, CadraApiError>({
    // `filters` is in the key, so switching tabs restarts the cursor walk —
    // the API records the direction and the domain in the cursor and refuses
    // one replayed against another.
    queryKey: ["approvals", filters],
    queryFn: ({ pageParam }) => fetchApprovalsPage(pageParam as string | undefined, filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 30_000,
  });

  const loaded = useMemo(() => (data?.pages ?? []).flatMap(p => p.requests), [data]);
  const rows = useMemo(
    () => (clientFiltered ? loaded.filter(r => r.state !== "pending") : loaded),
    [loaded, clientFiltered],
  );
  const total = data?.pages[0]?.totalEstimate ?? null;

  /**
   * The tag-replacement section's own filters (handoff 51 §1b). The same
   * tab means the same question, translated onto the label's lifecycle —
   * and `null` means the question has no tag answer at all: a replacement
   * cannot be withdrawn, so the *Decided → Withdrawn* view says that in a
   * sentence instead of running a query that can only come back empty.
   */
  const tagFilters: TagReplacementFilters | null = useMemo(() => {
    if (tab === "waiting") return { waiting_on_me: true, state: "pending" };
    if (tab === "pending") return { state: "pending" };
    if (tab === "mine") return { raised_by_me: true };
    if (decidedState === "approved") return { state: "scrapped" };
    if (decidedState === "rejected") return { state: "active" };
    if (decidedState === "withdrawn") return null;
    return {}; // any outcome: every state, pending dropped in the browser
  }, [tab, decidedState]);

  /** Mirrors `clientFiltered` for the tag section — same tab, same rule. */
  const tagClientFiltered = tab === "decided" && !decidedState;

  // A SECOND query with a SECOND cursor, never interleaved into the one
  // above — see the file docstring for why that is a rule and not a style.
  const tagQuery = useInfiniteQuery<TagReplacementsPage, CadraApiError>({
    queryKey: ["tag-replacements", tagFilters],
    queryFn: ({ pageParam }) => fetchTagReplacementsPage(pageParam as string | undefined, tagFilters ?? undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    staleTime: 30_000,
    enabled: tagFilters !== null,
  });
  const tagLoaded = useMemo(() => (tagQuery.data?.pages ?? []).flatMap(p => p.tags), [tagQuery.data]);
  const tagRows = useMemo(
    () => (tagClientFiltered ? tagLoaded.filter(t => t.state !== "pending") : tagLoaded),
    [tagLoaded, tagClientFiltered],
  );
  const tagTotal = tagQuery.data?.pages[0]?.totalEstimate ?? null;

  // The same query the top bar and the sidebar hold. `ReplacementRow` needs
  // it to tell the requester's own pending row from somebody else's — the
  // tag record carries no `can_withdraw` to read that off, the way the
  // movement rows do.
  const { data: me } = useQuery({
    queryKey: ["whoami"],
    queryFn: fetchWhoAmI,
    staleTime: 30 * 60_000,
    retry: false,
  });

  // Infinite-scroll sentinel — the same shape as `RequestsList`.
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    }, { root: scrollRef.current ?? null, rootMargin: "200px" });
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const activeTab = TABS.find(t => t.key === tab)!;

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-border bg-card">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-[14px] font-bold text-foreground">Approvals</h1>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Moves, custody changes and tag replacements waiting for a second person.
              Nothing on this list has happened yet.
            </p>
          </div>
          {/* WHETHER THE CONTROL IS EVEN ON, said on the screen that exists
              because of it. `configured` is the fact `required` cannot give:
              an administrator who has never set this is getting the default,
              and that is worth knowing before anybody concludes the queue is
              empty because nothing is happening. */}
          {approval.settings && (
            <div
              className={cn(
                "text-[11px] px-2.5 py-1.5 rounded-xl border",
                approval.settings.required
                  ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-300 border-emerald-200/70 dark:border-emerald-800/30"
                  : "bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-300 border-amber-200/70 dark:border-amber-800/30",
              )}
              data-testid="approval-setting-banner"
              data-required={approval.settings.required ? "true" : "false"}
            >
              {approval.settings.required ? (
                <>
                  <span className="font-semibold">Approval is required</span> on this register
                  {!approval.settings.configured && " (nobody has set the switch, so it is on by default)"}.
                </>
              ) : (
                <>
                  <span className="font-semibold">Approval is switched OFF</span> on this register —
                  moves and custody changes take effect immediately. Only requests raised
                  while it was on are listed here.
                </>
              )}
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-3 flex-wrap" role="tablist" aria-label="Approval views">
          {TABS.map(t => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              data-testid={`tab-approvals-${t.key}`}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl border transition-colors",
                tab === t.key
                  ? "bg-primary text-white border-primary"
                  : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
          {tab === "decided" && (
            <select
              value={decidedState}
              onChange={e => setDecidedState(e.target.value as "" | ApprovalState)}
              data-testid="select-decided-state"
              className="text-xs border border-border rounded-xl px-2.5 py-1.5 bg-background"
            >
              <option value="">Any outcome</option>
              {DECIDED_STATES.map(s => (
                <option key={s} value={s}>{STATE_WORD[s]}</option>
              ))}
            </select>
          )}
          <p className="ml-auto text-[11px] text-muted-foreground self-center" data-testid="approval-count">
            {/* THE DENOMINATOR, every time, and a different one per tab.
                `total_estimate` is the server's count of the caller's whole
                domain — which on the *Decided/Any outcome* tab is a count of
                EVERY request including the pending ones, because that is the
                domain that was asked for. Printing it beside a
                browser-narrowed list as though it were the number of decided
                requests would be exactly the shape that put "1,146 tracked
                moves" into a report. */}
            {clientFiltered
              ? <>{rows.length.toLocaleString()} decided, out of {loaded.length.toLocaleString()} loaded{total != null && <> of {total.toLocaleString()} in every state</>}</>
              : <><span className="font-bold text-foreground">{rows.length.toLocaleString()}</span>{total != null && <> of <span className="font-bold text-foreground">{total.toLocaleString()}</span></>}</>}
          </p>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5">{activeTab.hint}</p>
      </div>

      {error && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-start gap-2" data-testid="approvals-error">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div>
            <ApiErrorMessage err={error} />
            {!apiConfigured && (
              <p className="text-[11px] text-red-700 dark:text-red-400 mt-0.5">No active session.</p>
            )}
          </div>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {/* Two kinds, two SECTIONS, each under a heading saying which it is
            (handoff 51 §1b). The movement list keeps its structure, its
            query and its cursor exactly as they were. */}
        <h2 className="px-5 pt-4 pb-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Moves and custody changes
        </h2>
        {isLoading && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
            <p className="text-sm text-muted-foreground">Loading approvals…</p>
          </div>
        ) : rows.length === 0 ? (
          // An empty queue says which emptiness it is. "No results" over a
          // filtered view reads as "nothing is happening", and a person who
          // draws that conclusion from the wrong tab stops looking.
          <div className="flex flex-col items-center justify-center py-20 gap-3 px-6 text-center" data-testid="approvals-empty">
            <Inbox size={24} className="text-muted-foreground/30" />
            <p className="text-sm font-semibold">
              {tab === "waiting" ? "Nothing is waiting on you."
                : tab === "pending" ? "Nothing is waiting on anybody."
                : tab === "mine" ? "You have not asked for any moves or custody changes."
                : "Nothing has been decided yet."}
            </p>
            <p className="text-xs text-muted-foreground max-w-md">
              {tab === "waiting"
                ? "Requests naming you as the approver appear here. Somebody else's queue may not be empty — try All pending."
                : "A move or a custody change started from an asset's page becomes a request here, when this register requires approval."}
            </p>
            {tab !== "pending" && (
              <button
                onClick={() => setTab("pending")}
                className="text-xs text-primary hover:opacity-80"
                data-testid="button-see-all-pending"
              >
                See everything pending
              </button>
            )}
            <button
              onClick={() => nav("/assets/list")}
              className="text-xs text-muted-foreground hover:text-foreground"
              data-testid="button-empty-to-register"
            >
              Back to the asset register
            </button>
          </div>
        ) : (
          <ul className="divide-y divide-border" data-testid="approvals-list">
            {rows.map(r => <ApprovalRow key={r.id} r={r} />)}
          </ul>
        )}

        {hasNextPage && (
          <div ref={sentinelRef} className="py-5 text-center">
            {isFetchingNextPage ? (
              <div className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <Clock size={12} className="animate-pulse" /> Loading more…
              </div>
            ) : (
              <button onClick={() => fetchNextPage()} className="text-xs text-primary hover:opacity-80" data-testid="button-load-more-approvals">
                Load more
              </button>
            )}
          </div>
        )}

        {/* ── Tag replacements (handoff 51 §1b) ─────────────────────────── */}
        <div className="border-t border-border mt-2">
          <div className="px-5 pt-4 pb-1 flex items-center justify-between gap-3 flex-wrap">
            <h2 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              Tag replacements
            </h2>
            {tagFilters !== null && (
              <p className="text-[11px] text-muted-foreground" data-testid="replacement-count">
                {/* The same honesty rule as the movement counter above:
                    `total_estimate` on the any-outcome view counts EVERY
                    state including pending, because that is the domain that
                    was asked for, so the denominator is named. */}
                {tagClientFiltered
                  ? <>{tagRows.length.toLocaleString()} decided, out of {tagLoaded.length.toLocaleString()} loaded{tagTotal != null && <> of {tagTotal.toLocaleString()} in every state</>}</>
                  : <><span className="font-bold text-foreground">{tagRows.length.toLocaleString()}</span>{tagTotal != null && <> of <span className="font-bold text-foreground">{tagTotal.toLocaleString()}</span></>}</>}
              </p>
            )}
          </div>

          {tagFilters === null ? (
            // *Decided → Withdrawn*. An empty table here would read as "no
            // withdrawn replacements yet", which implies one could exist.
            <p className="px-5 py-4 text-[11px] text-muted-foreground italic" data-testid="replacements-withdrawn-note">
              A tag replacement cannot be withdrawn — it is approved or rejected, nothing
              else — so there is nothing this outcome could list.
            </p>
          ) : tagQuery.error ? (
            <div className="px-5 py-2 bg-red-50 dark:bg-red-950/30 border-b border-red-200/70 dark:border-red-800/30 flex items-start gap-2" data-testid="replacements-error">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={tagQuery.error} />
            </div>
          ) : tagQuery.isLoading && tagRows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <Clock size={16} className="text-muted-foreground/40 animate-pulse" />
              <p className="text-sm text-muted-foreground">Loading tag replacements…</p>
            </div>
          ) : tagRows.length === 0 ? (
            // Report 49's rule, unchanged: an empty section says it is
            // empty, and says WHICH emptiness, never a stopped spinner.
            <div className="flex flex-col items-center justify-center py-10 gap-2 px-6 text-center" data-testid="replacements-empty">
              <Inbox size={20} className="text-muted-foreground/30" />
              <p className="text-sm font-semibold">
                {tab === "waiting" ? "No tag replacements are waiting on you."
                  : tab === "pending" ? "No tag replacements are waiting on anybody."
                  : tab === "mine" ? "You have not asked for any tag replacements."
                  : "No tag replacement has been decided yet."}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-border" data-testid="replacements-list">
              {tagRows.map(t => <ReplacementRow key={t.id} t={t} meId={me?.id} />)}
            </ul>
          )}

          {tagFilters !== null && tagQuery.hasNextPage && (
            <div className="py-5 text-center">
              {tagQuery.isFetchingNextPage ? (
                <div className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock size={12} className="animate-pulse" /> Loading more…
                </div>
              ) : (
                <button
                  onClick={() => tagQuery.fetchNextPage()}
                  className="text-xs text-primary hover:opacity-80"
                  data-testid="button-load-more-replacements"
                >
                  Load more
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
