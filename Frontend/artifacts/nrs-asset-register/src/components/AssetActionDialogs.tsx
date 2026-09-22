import { useState } from "react";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useLocation } from "wouter";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RecordPicker from "@/components/RecordPicker";
import { CadraApiError, apiGet } from "@/lib/api";
import {
  moveAsset, transferCustody, condemnAsset, markAssetMissing, markAssetFound,
  fetchApprovalSettings, fetchApprovers,
  type ApiAssetTransfer, type ApprovalRef, type ApprovalSettings,
  type AssetChangeResult, type RaisedApprovalRequest,
} from "@/lib/dataProvider";
import type { ApiLocation } from "@/lib/adapters";
import {
  AlertCircle, AlertTriangle, ArrowRightLeft, MapPin, SearchCheck, Trash2, Loader2,
  UserCheck, Hourglass,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";

interface ApiEmployeeRef {
  id: number;
  name: string;
  ir_number: string | null;
  job_title: string | null;
}

// ─── shared search helpers ─────────────────────────────────────────────────

async function searchLocations(q: string) {
  const res = await apiGet<ApiLocation[]>("/api/v1/locations", { q, limit: 10 });
  return res.data.map(l => ({
    id: l.id,
    label: l.name,
    sublabel: [l.address?.city, l.address?.state?.name].filter(Boolean).join(" · ") || undefined,
  }));
}

async function searchEmployees(q: string) {
  const res = await apiGet<ApiEmployeeRef[]>("/api/v1/identity/employees", { q, limit: 10 });
  return res.data.map(e => ({
    id: e.id,
    label: e.name,
    sublabel: [e.ir_number, e.job_title].filter(Boolean).join(" · ") || undefined,
  }));
}

/** The approver picker's search. `res.users`, NOT `hr.employee` — the two are
 *  different tables and only the first can hold a credential that decides
 *  anything. The endpoint already drops the caller from its own answer. */
async function searchApprovers(q: string) {
  const users = await fetchApprovers(q, 10);
  return users.map(u => ({ id: u.id, label: u.name }));
}

// ─── Nobody moves an asset alone (handoff 35) ──────────────────────────────

/**
 * Whether this register requires a second person to agree before an asset is
 * moved or handed to somebody else.
 *
 * **Unknown means REQUIRED**, which is the server's own rule read from the
 * other side (`approval_policy.REQUIRED_WHEN_UNSET`): absent, unreadable or
 * unrecognised, the safe direction is the one that asks for a second person.
 * Here the stake is a sentence rather than a write — the model refuses the
 * change whatever this says — so the cost of being wrong in this direction is
 * a dialog that asks for an approver on a tenant that did not need one, and
 * the cost the other way is a dialog that promises a move the server will not
 * make.
 *
 * `loading` is exposed separately and the dialogs DISABLE their submit button
 * while it is true, rather than defaulting to "required" on screen and
 * flipping a moment later. A button whose words change under the cursor is
 * how somebody presses the one they did not read.
 *
 * Ten minutes of `staleTime`: this is a setting an administrator changes in
 * the database perhaps once in the life of a tenant, and it is read by every
 * Move dialog on every asset page.
 */
export function useApprovalRequirement() {
  const q = useQuery<ApprovalSettings, CadraApiError>({
    queryKey: ["approval-settings"],
    queryFn: fetchApprovalSettings,
    staleTime: 10 * 60_000,
  });
  return {
    /** True while nothing is known yet — see the docstring. */
    loading: q.isLoading,
    required: q.data?.required ?? true,
    /** Null until the setting has been read. `settings.configured` tells a
     *  screen the difference between "nobody ever set this" and "somebody
     *  turned it on", which `required` alone cannot. */
    settings: q.data ?? null,
    /** The read itself failed — a 403 for a credential without `settings:read`,
     *  or a server that predates the route. We are treating it as REQUIRED,
     *  and the dialog says so rather than quietly assuming. */
    unreadable: q.isError,
  };
}

/**
 * Everything the approval queue puts out of date, in one place, for the same
 * reason `invalidateAssetQueries` exists: the lists disagreed when each caller
 * carried its own.
 *
 * Four prefixes, and every one of them is a PREFIX match:
 *   `approvals`          the queue, under every tab and filter
 *   `approval-count`     the sidebar badge
 *   `asset-approvals`    the pending-request banner on an asset page
 *   `approval-settings`  the switch itself — not changed by any of these
 *                        actions, but a decision is the moment a screen would
 *                        notice an administrator having thrown it, and the
 *                        read is one cheap call behind a ten-minute staleTime.
 *
 * Deciding a request is also an event in the ASSET's life — an approval moves
 * it — so every caller here calls `invalidateAssetQueries` beside this one.
 * They are two functions and not one because raising a request changes NO
 * asset, and folding them together would have the Move dialog refetch the
 * register, every KPI and both maps to report a move that did not happen.
 */
export function invalidateApprovalQueries(qc: QueryClient, assetId?: string | number) {
  qc.invalidateQueries({ queryKey: ["approvals"] });
  qc.invalidateQueries({ queryKey: ["approval-count"] });
  qc.invalidateQueries({ queryKey: ["approval-settings"] });
  if (assetId === undefined) qc.invalidateQueries({ queryKey: ["asset-approvals"] });
  else qc.invalidateQueries({ queryKey: ["asset-approvals", String(assetId)] });
}

/** `details.approvers` of a `400` that refused the write for want of an
 *  approver. The server sends the candidates WITH the refusal so a client can
 *  recover in one round trip instead of asking what it should have asked
 *  first — and this reads them, so a dialog that got the setting wrong (a
 *  403 on `/settings/approvals`, a switch thrown between the two calls) still
 *  ends with the user choosing a name rather than reading a 400. */
function approvalRefusal(err: CadraApiError | null | undefined): ApprovalRef[] | null {
  const d = err?.details;
  if (!d || typeof d !== "object") return null;
  const det = d as { approval_required?: unknown; approvers?: unknown };
  if (det.approval_required !== true) return null;
  const list = Array.isArray(det.approvers) ? det.approvers : [];
  return list.filter((u): u is ApprovalRef =>
    !!u && typeof u === "object" && typeof (u as ApprovalRef).id === "number");
}

interface PendingConflict {
  id: number;
  reference: string;
  change_type: string;
  requested_by: ApprovalRef | null;
  approver: ApprovalRef | null;
}

/** `details.pending_request` of the `409` raised when something is already
 *  waiting on this asset. A partial-unique index in the database is the
 *  authority; this exists because the index answers with an IntegrityError
 *  that takes the whole transaction with it, and somebody who pressed Move
 *  deserves the reference number of the request in their way. */
function pendingConflict(err: CadraApiError | null | undefined): PendingConflict | null {
  const d = err?.details;
  if (!d || typeof d !== "object") return null;
  const p = (d as { pending_request?: unknown }).pending_request;
  if (!p || typeof p !== "object") return null;
  const r = p as PendingConflict;
  return typeof r.reference === "string" ? r : null;
}

/** The blocking request, named, with a way to go and look at it. Shown INSIDE
 *  the dialog that was refused — the person is standing at the button they
 *  just pressed, and the answer belongs beside it. */
function PendingConflictNotice({ conflict }: { conflict: PendingConflict }) {
  // `useLocation`'s navigate, not wouter's `<Link>`: every link in this app
  // is a button that calls `nav()` (see `components/RecordLink.tsx`), and one
  // anchor among them would be the only element in the dialog that a
  // middle-click opens in a tab with the base path missing.
  const [, nav] = useLocation();
  return (
    <div
      className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3"
      data-testid="approval-pending-conflict"
      role="alert"
    >
      <Hourglass size={14} className="text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" />
      <div className="text-[12px] text-amber-800 dark:text-amber-300">
        <p>
          <span className="font-semibold font-mono">{conflict.reference}</span> is already waiting
          for approval on this asset
          {conflict.requested_by ? <> — {conflict.requested_by.name} asked</> : null}
          {conflict.approver ? <> {conflict.approver.name}</> : null}.
          Nothing new can be requested until that one is decided or withdrawn.
        </p>
        <button
          type="button"
          onClick={() => nav("/approvals")}
          className="inline-block mt-1.5 font-semibold underline underline-offset-2"
          data-testid="link-pending-conflict-queue"
        >
          Open the approvals queue
        </button>
      </div>
    </div>
  );
}

/**
 * The approver field, and the sentence that has to be on the screen.
 *
 * *"A storekeeper who thinks they have moved something and has not is the
 * defect this programme is named after"* — the handoff's words, and the
 * reason this block is not a quiet extra dropdown. It says, above the
 * picker, that the asset stays exactly where it is until somebody agrees.
 */
function ApproverField({
  value, onChange, disabled, candidates, action,
}: {
  value: ApprovalRef | null;
  onChange: (v: ApprovalRef | null) => void;
  disabled?: boolean;
  /** Names the server handed back with a refusal, when it did. Shown as a
   *  hint under the picker — the picker itself searches the live endpoint. */
  candidates: ApprovalRef[] | null;
  action: "move" | "custody";
}) {
  return (
    <div data-testid="approver-field">
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
        Who are you asking to approve this?
      </label>
      <p className="text-[11px] text-muted-foreground mt-1">
        {action === "move"
          ? "This asset does NOT move until they approve it. Until then it stays exactly where it is, and the register goes on showing its current location."
          : "This asset is NOT handed over until they approve it. Until then it stays with its current custodian, and the register goes on showing them."}
        {" "}You cannot approve your own request — that is the point of one.
      </p>
      <div className="mt-1.5">
        <RecordPicker
          value={value ? { id: value.id, label: value.name } : null}
          onChange={opt => onChange(opt ? { id: opt.id, name: opt.label } : null)}
          search={searchApprovers}
          queryKey="picker-approvers"
          placeholder="Search people who can approve…"
          disabled={disabled}
        />
      </div>
      {candidates && candidates.length > 0 && !value && (
        <p className="text-[11px] text-muted-foreground mt-1.5" data-testid="approver-candidates">
          Can approve this: {candidates.map(c => c.name).join(", ")}
        </p>
      )}
      {candidates && candidates.length === 0 && (
        <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1.5" data-testid="approver-candidates-empty">
          The server named nobody who can approve this. Somebody other than you
          needs the Asset Manager group before this change can be requested.
        </p>
      )}
    </div>
  );
}

/**
 * What the dialog shows INSTEAD of closing, once a request has been raised.
 *
 * It does not close and it does not raise a toast. A toast is for a message
 * that has to outlive the page (`lib/apiWarnings.tsx` says why); this one has
 * to be read before the person walks away believing they moved something, so
 * it takes the place of the form, names the reference and the person asked,
 * and makes them press Done.
 */
function RaisedConfirmation({
  request, action, onDone,
}: { request: RaisedApprovalRequest | null; action: "move" | "custody"; onDone: () => void }) {
  const [, nav] = useLocation();
  const target = action === "move" ? request?.to_location : request?.to_custodian;
  return (
    <>
      <div
        className="flex items-start gap-2 bg-blue-50 dark:bg-blue-950/30 border border-blue-200/70 dark:border-blue-800/30 rounded-xl p-3"
        data-testid="approval-raised"
        role="status"
      >
        <Hourglass size={14} className="text-blue-700 dark:text-blue-400 shrink-0 mt-0.5" />
        <div className="text-[12px] text-blue-900 dark:text-blue-200 space-y-1.5">
          <p>
            <span className="font-semibold">Approval requested — nothing has changed yet.</span>
          </p>
          {/* A missing `request` is a server defect, not a reason to imply
              the move happened — see `readAssetChange`, which deliberately
              branches on `pending_approval` alone. The panel still renders
              and still says the asset has not moved; what it cannot do is
              name the reference. */}
          <p data-testid="approval-raised-reference">
            {request ? (
              <>
                <span className="font-mono font-semibold">{request.reference}</span> is now waiting on{" "}
                <span className="font-semibold">{request.approver?.name ?? "the person you named"}</span>.
                {target ? (
                  action === "move"
                    ? <> The asset will move to <span className="font-semibold">{target.name}</span> only when they approve it.</>
                    : <> The asset passes to <span className="font-semibold">{target.name}</span> only when they approve it.</>
                ) : null}
              </>
            ) : (
              <>The request was accepted, but the server did not return its
              reference. Find it in the approvals queue before raising
              another — this asset can only have one request waiting.</>
            )}
          </p>
          <p className="opacity-90">
            {action === "move"
              ? "Until then this asset is still at its current location, and that is what the register says."
              : "Until then this asset is still with its current custodian, and that is what the register says."}
          </p>
          <button
            type="button"
            onClick={() => nav("/approvals")}
            className="inline-block font-semibold underline underline-offset-2"
            data-testid="link-raised-queue"
          >
            Track it in the approvals queue
          </button>
        </div>
      </div>
      <DialogFooter>
        <button
          type="button"
          onClick={onDone}
          className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
          data-testid="button-approval-raised-done"
        >
          Done
        </button>
      </DialogFooter>
    </>
  );
}

/** While `/settings/approvals` is still in flight. The submit button is
 *  disabled behind this rather than guessing at the wording. */
function ApprovalCheckNotice({ unreadable }: { unreadable: boolean }) {
  return unreadable ? (
    <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="approval-setting-unreadable">
      This sign-in cannot read whether approval is required here, so it is being
      treated as required — the safe direction. Name an approver below.
    </p>
  ) : (
    <p className="text-[11px] text-muted-foreground" data-testid="approval-setting-loading">
      Checking whether this register needs a second person to approve the change…
    </p>
  );
}

// ─── what an action on an asset makes stale ────────────────────────────────

/**
 * Everything a change to one asset puts out of date, in one place.
 *
 * Each action used to carry its own list, and the lists disagreed: the three
 * dialogs refreshed the asset, its history and the register list; Verify and
 * Mark missing refreshed the first two only; and NOTHING refreshed a count. The
 * global `staleTime` is five minutes over a persisted cache, so marking an
 * asset missing left the register list calling it active and every KPI strip a
 * figure short, for as long as that — the screen saying something the record
 * had stopped saying.
 *
 * Every key here is a PREFIX match — `["assets"]` covers every search and
 * sort of the register list, `["dashboard"]` the home dashboard's totals,
 * KPIs, review queue and status breakdown.
 *
 * **Invalidating is only half of it.** It REFETCHES a query that is on screen
 * and merely FLAGS one that is not — and at the moment of any action here the
 * user is on the asset's page, so the list and every count are off screen.
 * What brings them up to date is `refetchOnMount: true` in `App.tsx`. This
 * docstring's first version claimed the cure without that; the app then had
 * `refetchOnMount: false`, and the dashboard went on showing *Missing: 8*
 * over a database holding 9. Caught by the verification pass, proved by
 * acting, and held by an e2e spec that goes list → asset → act → Back.
 */
export function invalidateAssetQueries(qc: QueryClient, assetId: string | undefined) {
  qc.invalidateQueries({ queryKey: ["asset", assetId] });
  qc.invalidateQueries({ queryKey: ["asset-raw", assetId] });
  qc.invalidateQueries({ queryKey: ["asset-history", assetId] });
  qc.invalidateQueries({ queryKey: ["assets"] });
  qc.invalidateQueries({ queryKey: ["asset-register-counts"] });
  // The warranty tiles (handoff 34). The edit form is what changes a
  // warranty, and it lands the user back here through this same function.
  qc.invalidateQueries({ queryKey: ["asset-warranty-counts"] });
  qc.invalidateQueries({ queryKey: ["it-assets-dashboard"] });
  qc.invalidateQueries({ queryKey: ["dashboard-kpis"] });
  qc.invalidateQueries({ queryKey: ["dashboard"] });
}

// ─── Move dialog ──────────────────────────────────────────────────────────

interface MoveProps {
  assetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** `placed` is whether the asset HAS a location now. An asset with none is
 *  PLACED rather than moved: the server creates no transfer document for a
 *  journey from nowhere (a transfer needs both ends), and the dialog must not
 *  promise one. Until this was handled, moving such an asset failed outright
 *  with "Required field missing: from_location_id". */
export function AssetMoveDialog({ assetId, open, onOpenChange, placed = true }: MoveProps & { placed?: boolean }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<{ id: number; label: string } | null>(null);
  const [reason, setReason] = useState("");
  const [approver, setApprover] = useState<ApprovalRef | null>(null);
  /** Set from a REFUSAL, not from the setting: the server said approval is
   *  required and handed back who may be asked. Kept in state rather than
   *  derived from `mutation.error` because it has to be readable BEFORE the
   *  mutation is declared — the submit button's enabled-ness depends on it. */
  const [forcedApprovers, setForcedApprovers] = useState<ApprovalRef[] | null>(null);
  /** The request this dialog raised, if it raised one. Its presence replaces
   *  the whole form — see `RaisedConfirmation`. */
  const [raised, setRaised] = useState<RaisedApprovalRequest | null>(null);
  // SEPARATE from `raised`, because `raised` may legitimately be null on a
  // response that said `pending_approval: true` and carried no request. The
  // panel must still appear — the one thing that must never happen is the
  // dialog closing as though the asset moved.
  const [pendingRaised, setPendingRaised] = useState(false);

  const approval = useApprovalRequirement();
  const needsApprover = approval.required || forcedApprovers !== null;

  const mutation = useMutation<AssetChangeResult, CadraApiError>({
    // `approver.id` goes only when an approver is actually wanted. On a
    // tenant with the switch off, `/move` reads `to_location_id` and `reason`
    // and nothing else — sending a key a route does not want is the class of
    // defect handoff 31 closed, and it is not this dialog's job to reopen it.
    mutationFn: () => moveAsset(
      assetId, target!.id, reason || undefined,
      needsApprover ? approver?.id : undefined,
    ),
    onSuccess: (res) => {
      if (res.pendingApproval) {
        // NOTHING about the asset changed, so nothing about the asset is
        // stale: invalidating the register, the counts and both maps here
        // would make this screen refetch the world to report a move that did
        // not happen. Only the approval queue and this asset's banner moved.
        invalidateApprovalQueries(qc, assetId);
        setRaised(res.request);
        setPendingRaised(true);
        return;
      }
      invalidateAssetQueries(qc, assetId);
      // A move changes the per-location figures the two maps plot.
      qc.invalidateQueries({ queryKey: ["dashboard-map"] });
      // And the queue: a tenant with the switch OFF can still be holding
      // requests raised while it was on, and one of them may be about this
      // asset. Cheap, and the banner would otherwise outlive the move.
      invalidateApprovalQueries(qc, assetId);
      setOpen(false, true);
    },
    onError: (e) => {
      // Two refusals this dialog can act on rather than merely print.
      const candidates = approvalRefusal(e);
      // The setting said no approver was needed and the server disagrees —
      // a 403 on `/settings/approvals`, or the switch thrown between the two
      // calls. Reveal the picker with the names the refusal carried, so the
      // person finishes the job instead of reading a 400 about a field.
      if (candidates) setForcedApprovers(candidates);
      // 409: something is already waiting on this asset. The banner on the
      // page behind this dialog does not know that yet.
      if (pendingConflict(e)) invalidateApprovalQueries(qc, assetId);
    },
  });
  const err = mutation.error as CadraApiError | null;
  const conflict = pendingConflict(err);

  // Every way of closing — Cancel, Escape, the overlay, success — clears the
  // form. Cancel used to close and nothing else, so a cancelled Move reopened
  // with the last location still selected and the last error still showing.
  const setOpen = (next: boolean, done = false) => {
    // A USER cannot close it while the request is in flight: closing resets
    // the mutation, which detaches it, and a REFUSAL would then be shown
    // nowhere. `done` is the success handler closing it — which runs while
    // `isPending` still reads true in this closure, so without it the guard
    // blocked the one close that must always happen. (It did, for one build:
    // every dialog stayed open after a successful save. Found by acting.)
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setTarget(null);
      setReason("");
      setApprover(null);
      setForcedApprovers(null);
      setRaised(null);
      setPendingRaised(false);
      mutation.reset();
    }
    onOpenChange(next);
  };

  // Two words for the same act, and which one is on the button is the whole
  // point of this handoff. "Move asset" DID move the asset; on a register
  // that requires approval it does not, and a button that says it does is
  // the defect the programme is named after.
  const verb = placed ? "move" : "place";
  const submitLabel = needsApprover
    ? (placed ? "Request approval to move" : "Request approval to place")
    : (placed ? "Move asset" : "Place asset");
  const canSubmit = !!target && !mutation.isPending && !approval.loading
    && (!needsApprover || !!approver);

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-move">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {needsApprover ? <UserCheck size={16} /> : <MapPin size={16} />}{" "}
            {needsApprover
              ? (placed ? "Request a move" : "Request a placement")
              : (placed ? "Move asset" : "Place asset")}
          </DialogTitle>
          <DialogDescription>
            {/* Four versions now, and the history of them is the point. It
                said "creates an immutable transfer record" until handoff 27 —
                false: an asset manager can edit or delete a transfer. Handoff
                27 said so, which was true and, from handoff 28, only half of
                it: the MOVE is appended to the asset's movement record, which
                nobody can alter, and the transfer is the paperwork beside it.
                Handoff 35 adds the fourth, and it is not a refinement of the
                other three — on a register requiring approval this button
                moves NOTHING, and the sentence has to say that first, in the
                first clause, before any of the record-keeping. */}
            {needsApprover
              ? (placed
                  ? "This does NOT move the asset. It asks somebody else to agree to the move; the asset stays where it is until they do, and the register goes on showing its current location."
                  : "This does NOT place the asset. It asks somebody else to agree; the asset stays without a location until they do.")
              : (placed
                  ? "Updates the current location. The move is added to the asset's movement record, which cannot be edited or deleted afterwards. A transfer document is also created; that one can be edited later by an asset manager."
                  : "This asset has no location yet. Placing it is added to its movement record, which cannot be edited or deleted afterwards. No transfer document is created — there is nowhere it is being transferred from.")}
          </DialogDescription>
        </DialogHeader>

        {pendingRaised ? (
          <RaisedConfirmation request={raised} action="move" onDone={() => setOpen(false, true)} />
        ) : (
          <>
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">New location</label>
                <div className="mt-1.5">
                  <RecordPicker
                    value={target}
                    onChange={setTarget}
                    search={searchLocations}
                    queryKey="picker-locations"
                    placeholder="Search locations…"
                  />
                </div>
              </div>

              {(approval.loading || approval.unreadable) && (
                <ApprovalCheckNotice unreadable={approval.unreadable} />
              )}
              {needsApprover && !approval.loading && (
                <ApproverField
                  value={approver}
                  onChange={setApprover}
                  disabled={mutation.isPending}
                  candidates={forcedApprovers}
                  action="move"
                />
              )}

              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                  Reason (optional)
                </label>
                <textarea
                  rows={2}
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder={needsApprover ? "e.g. Floor reorganisation — the approver reads this" : "e.g. Floor reorganisation"}
                  data-testid="input-move-reason"
                />
              </div>

              {/* The 409 gets its own panel with the blocking reference in it.
                  `ApiErrorMessage` would print the server's sentence, which is
                  good, and nothing a person can click, which is not. */}
              {conflict ? (
                <PendingConflictNotice conflict={conflict} />
              ) : err && (
                <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="move-error">
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
                disabled={!canSubmit}
                onClick={() => mutation.mutate()}
                data-testid="button-confirm-move"
                title={needsApprover && !approver
                  ? `Name who you are asking to approve this ${verb}`
                  : undefined}
                className={cn(
                  "px-3 py-1.5 text-xs font-semibold rounded-xl",
                  canSubmit
                    ? "bg-primary text-white hover:opacity-90"
                    : "bg-muted text-muted-foreground cursor-not-allowed",
                )}
              >
                {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : submitLabel}
              </button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Transfer-custody dialog ──────────────────────────────────────────────

export function CustodyTransferDialog({ assetId, open, onOpenChange }: MoveProps) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<{ id: number; label: string } | null>(null);
  const [reason, setReason] = useState("");
  const [approver, setApprover] = useState<ApprovalRef | null>(null);
  const [forcedApprovers, setForcedApprovers] = useState<ApprovalRef[] | null>(null);
  const [raised, setRaised] = useState<RaisedApprovalRequest | null>(null);
  // SEPARATE from `raised`, because `raised` may legitimately be null on a
  // response that said `pending_approval: true` and carried no request. The
  // panel must still appear — the one thing that must never happen is the
  // dialog closing as though the asset moved.
  const [pendingRaised, setPendingRaised] = useState(false);

  // The whole approval block below is the twin of `AssetMoveDialog`'s and is
  // commented there. It is duplicated rather than abstracted because the two
  // dialogs already duplicate their close handler, their error panel and
  // their mutation shape, and the pieces that ARE shared — the picker, the
  // confirmation, the two refusal readers — are the four components above.
  const approval = useApprovalRequirement();
  const needsApprover = approval.required || forcedApprovers !== null;

  const mutation = useMutation<AssetChangeResult, CadraApiError>({
    mutationFn: () => transferCustody(
      assetId, target!.id, reason || undefined,
      needsApprover ? approver?.id : undefined,
    ),
    onSuccess: (res) => {
      if (res.pendingApproval) {
        // Nothing changed hands. See `AssetMoveDialog`.
        invalidateApprovalQueries(qc, assetId);
        setRaised(res.request);
        setPendingRaised(true);
        return;
      }
      invalidateAssetQueries(qc, assetId);
      qc.invalidateQueries({ queryKey: ["employee-assets"] });
      invalidateApprovalQueries(qc, assetId);
      setOpen(false, true);
    },
    onError: (e) => {
      const candidates = approvalRefusal(e);
      if (candidates) setForcedApprovers(candidates);
      if (pendingConflict(e)) invalidateApprovalQueries(qc, assetId);
    },
  });
  const err = mutation.error as CadraApiError | null;
  const conflict = pendingConflict(err);

  // Reset on every close — see `AssetMoveDialog`.
  const setOpen = (next: boolean, done = false) => {
    // A USER cannot close it while the request is in flight: closing resets
    // the mutation, which detaches it, and a REFUSAL would then be shown
    // nowhere. `done` is the success handler closing it — which runs while
    // `isPending` still reads true in this closure, so without it the guard
    // blocked the one close that must always happen. (It did, for one build:
    // every dialog stayed open after a successful save. Found by acting.)
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setTarget(null);
      setReason("");
      setApprover(null);
      setForcedApprovers(null);
      setRaised(null);
      setPendingRaised(false);
      mutation.reset();
    }
    onOpenChange(next);
  };

  const submitLabel = needsApprover ? "Request approval to transfer" : "Transfer custody";
  const canSubmit = !!target && !mutation.isPending && !approval.loading
    && (!needsApprover || !!approver);

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-transfer-custody">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {needsApprover ? <UserCheck size={16} /> : <ArrowRightLeft size={16} />}{" "}
            {needsApprover ? "Request a custody transfer" : "Transfer custody"}
          </DialogTitle>
          <DialogDescription>
            {needsApprover
              ? "This does NOT hand the asset over. It asks somebody else to agree to the change of custodian; the asset stays with whoever holds it until they do, and the register goes on showing them."
              : "Assigns this asset to a different employee. The change is added to the asset's chain of custody, which cannot be edited or deleted afterwards."}
          </DialogDescription>
        </DialogHeader>

        {pendingRaised ? (
          <RaisedConfirmation request={raised} action="custody" onDone={() => setOpen(false, true)} />
        ) : (
          <>
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">New custodian</label>
                <div className="mt-1.5">
                  <RecordPicker
                    value={target}
                    onChange={setTarget}
                    search={searchEmployees}
                    queryKey="picker-employees"
                    placeholder="Search employees…"
                  />
                </div>
              </div>

              {(approval.loading || approval.unreadable) && (
                <ApprovalCheckNotice unreadable={approval.unreadable} />
              )}
              {needsApprover && !approval.loading && (
                <ApproverField
                  value={approver}
                  onChange={setApprover}
                  disabled={mutation.isPending}
                  candidates={forcedApprovers}
                  action="custody"
                />
              )}

              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Reason (optional)</label>
                <textarea
                  rows={2}
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder={needsApprover ? "e.g. Department reassignment — the approver reads this" : "e.g. Department reassignment"}
                  data-testid="input-custody-reason"
                />
              </div>

              {conflict ? (
                <PendingConflictNotice conflict={conflict} />
              ) : err && (
                <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="custody-error">
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
                disabled={!canSubmit}
                onClick={() => mutation.mutate()}
                data-testid="button-confirm-transfer-custody"
                title={needsApprover && !approver
                  ? "Name who you are asking to approve this transfer"
                  : undefined}
                className={cn(
                  "px-3 py-1.5 text-xs font-semibold rounded-xl",
                  canSubmit
                    ? "bg-primary text-white hover:opacity-90"
                    : "bg-muted text-muted-foreground cursor-not-allowed",
                )}
              >
                {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : submitLabel}
              </button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Condemn / Dispose dialog ─────────────────────────────────────────────

interface CondemnProps {
  assetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CondemnAssetDialog({ assetId, open, onOpenChange }: CondemnProps) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => condemnAsset(assetId, reason.trim()),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      setOpen(false, true);
    },
    // A 409 means the page behind this dialog is out of date — somebody else
    // disposed of the asset first. The dialog stays open on the server's
    // sentence; the page is refetched so that closing it lands on the truth.
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateAssetQueries(qc, assetId);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Reset on every close — see `AssetMoveDialog`.
  const setOpen = (next: boolean, done = false) => {
    // A USER cannot close it while the request is in flight: closing resets
    // the mutation, which detaches it, and a REFUSAL would then be shown
    // nowhere. `done` is the success handler closing it — which runs while
    // `isPending` still reads true in this closure, so without it the guard
    // blocked the one close that must always happen. (It did, for one build:
    // every dialog stayed open after a successful save. Found by acting.)
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-condemn">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
            <Trash2 size={16} /> Condemn / dispose asset
          </DialogTitle>
          <DialogDescription>
            {/* It said "This asset will no longer appear in active workflows."
                Not true of this app: a disposed asset is still in the register
                list and in every Total. And it named one of the two fields the
                action writes. The last sentence is there because it is the
                part an auditor asks about — this app never calls the
                approve-disposal route, so nothing made here has an approver.
                "Cannot be undone" is new in handoff 30 and is the model's
                rule: nothing leaves `disposed`, by any route. */}
            Sets this asset's state to Disposed and its condition to Decommissioned, dates the disposal today, and records the reason and who did it. It stays on the register. This cannot be undone: a disposed asset cannot be returned to service, moved or marked missing. A disposal made here carries no approver — approval is a separate step.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Disposal reason</label>
            <textarea
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="Required — explains why this asset is being condemned"
              data-testid="input-condemn-reason"
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
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
            disabled={!reason.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-condemn"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              reason.trim() && !mutation.isPending
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Condemn"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Mark-missing dialog ──────────────────────────────────────────────────

/**
 * Replaces a bare `window.confirm` — the browser's own dialog, unstyled, outside the
 * app's focus handling, invisible to anything that renders an error, and
 * carrying a sentence that was not true ("you can move/verify it again later":
 * neither Move nor Verify changes `state`).
 *
 * The reason is REQUIRED, and until handoff 30 there was no box for one. That
 * was deliberate then: marking missing was `PATCH {state: "missing"}`, the
 * model had no field for a reason, and a box that collects a reason and keeps
 * it nowhere true is worse than no box. It has somewhere true now.
 * `POST /assets/<id>/mark-missing` writes it to the asset's append-only
 * `status_changed` event — with who said it and when — and refuses a blank
 * one. It is evidence rather than a note: an asset that cannot be found may
 * be a loss, and *why* is the first question anybody asks.
 *
 * What the description says about reversing it is two different answers and
 * both are the model's. MISSING is not terminal — a missing asset that turns
 * up is ordinary, and *Mark found* puts it back (`MarkFoundDialog`, below).
 * Until handoff 31 this said "use Edit and set the state back", which worked
 * and recorded nothing about where the asset had been. DISPOSED is terminal:
 * that is said here because this is the last screen on which the two look
 * alike.
 */
export function MarkMissingDialog({ assetId, open, onOpenChange }: CondemnProps) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => markAssetMissing(assetId, reason.trim()),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      setOpen(false, true);
    },
    // 409: already missing, or disposed — either way this page is stale. See
    // `CondemnAssetDialog`.
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateAssetQueries(qc, assetId);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Reset on every close — see `AssetMoveDialog`.
  const setOpen = (next: boolean, done = false) => {
    // A USER cannot close it while the request is in flight: closing resets
    // the mutation, which detaches it, and a REFUSAL would then be shown
    // nowhere. `done` is the success handler closing it — which runs while
    // `isPending` still reads true in this closure, so without it the guard
    // blocked the one close that must always happen. (It did, for one build:
    // every dialog stayed open after a successful save. Found by acting.)
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-mark-missing">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
            <AlertTriangle size={16} /> Mark asset as missing
          </DialogTitle>
          <DialogDescription>
            Sets this asset's state to Missing. It stays on the register. The reason you give is kept in the asset's history with your name and the time, and cannot be edited or deleted afterwards. If the asset turns up, use Mark found on this page and say where — unlike a disposal, this can be reversed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label
              htmlFor="mark-missing-reason"
              className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
            >
              Why is it missing?
            </label>
            <textarea
              id="mark-missing-reason"
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="Required — where it was looked for, when it was last seen, who reported it"
              data-testid="input-missing-reason"
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
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
            disabled={!reason.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-missing"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              reason.trim() && !mutation.isPending
                ? "bg-amber-600 text-white hover:bg-amber-700"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Mark as missing"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Mark-found dialog ────────────────────────────────────────────────────

/**
 * The way back from MISSING, and the twin of the dialog above on purpose: the
 * same box, the same required sentence, the same append-only record.
 *
 * *Where it turned up* is as much an audit fact as *why it went*. Until
 * handoff 31 the only way back was Edit → State → Active, a PATCH, which has
 * nowhere to put a sentence — an asset reappeared having recorded nothing
 * about the most interesting event in its life. `POST /assets/<id>/mark-found`
 * requires the reason and writes it to the asset's `status_changed` event,
 * beside the one that says why it went missing.
 *
 * It sets the state to Active and does NOT verify the asset, and the
 * description says so: whoever found it may not be whoever checks it, and a
 * person who assumed otherwise would leave it unverified believing it was.
 *
 * Offered on a missing asset and on nothing else (`AssetDetail`). If this
 * copy of the asset is stale and it is no longer missing, the server answers
 * 409 and its sentence is printed here.
 */
export function MarkFoundDialog({ assetId, open, onOpenChange }: CondemnProps) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => markAssetFound(assetId, reason.trim()),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      setOpen(false, true);
    },
    // 409: it is not missing any more — somebody else found it, or disposed of
    // it. Either way this page is stale. See `CondemnAssetDialog`.
    onError: (e) => {
      if ((e as CadraApiError).status === 409) invalidateAssetQueries(qc, assetId);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Reset on every close — see `AssetMoveDialog`, including why the success
  // handler passes `done`: without it this dialog would stay open after a
  // successful save, as all four did for one build.
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
      <DialogContent className="sm:max-w-md" data-testid="dialog-mark-found">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
            <SearchCheck size={16} /> Mark asset as found
          </DialogTitle>
          <DialogDescription>
            Sets this asset's state back to Active. What you write here is kept in the asset's history with your name and the time, beside the reason it went missing, and cannot be edited or deleted afterwards. This does not verify the asset — use Mark verified once somebody has checked it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label
              htmlFor="mark-found-reason"
              className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
            >
              Where did it turn up?
            </label>
            <textarea
              id="mark-found-reason"
              rows={3}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="Required — where it was found, who found it, what state it was in"
              data-testid="input-found-reason"
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="mark-found-error">
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
            disabled={!reason.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-found"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              reason.trim() && !mutation.isPending
                ? "bg-emerald-600 text-white hover:bg-emerald-700"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Mark as found"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Silence the unused-import warning when a single Asset transfer row is shown
// elsewhere (this type belongs to the dataProvider).
export type { ApiAssetTransfer };
