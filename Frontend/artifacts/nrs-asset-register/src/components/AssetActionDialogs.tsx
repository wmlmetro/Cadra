import { useState } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RecordPicker from "@/components/RecordPicker";
import { CadraApiError, apiGet } from "@/lib/api";
import {
  moveAsset, transferCustody, condemnAsset, markAssetMissing, markAssetFound,
  type ApiAssetTransfer,
} from "@/lib/dataProvider";
import type { ApiLocation } from "@/lib/adapters";
import { AlertCircle, AlertTriangle, ArrowRightLeft, MapPin, SearchCheck, Trash2, Loader2 } from "lucide-react";
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

  const mutation = useMutation({
    mutationFn: () => moveAsset(assetId, target!.id, reason || undefined),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      // A move changes the per-location figures the two maps plot.
      qc.invalidateQueries({ queryKey: ["dashboard-map"] });
      setOpen(false, true);
    },
  });
  const err = mutation.error as CadraApiError | null;

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
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><MapPin size={16} /> {placed ? "Move asset" : "Place asset"}</DialogTitle>
          <DialogDescription>
            {/* Three versions, and the history of them is the point. It said
                "creates an immutable transfer record" until handoff 27 — false:
                an asset manager can edit or delete a transfer. Handoff 27 said
                so, which was true and, from handoff 28, only half of it: the
                MOVE is now appended to the asset's movement record, which
                nobody can alter, and the transfer is the paperwork beside it.
                Two records of different worth, and the dialog names both. */}
            {placed
              ? "Updates the current location. The move is added to the asset's movement record, which cannot be edited or deleted afterwards. A transfer document is also created; that one can be edited later by an asset manager."
              : "This asset has no location yet. Placing it is added to its movement record, which cannot be edited or deleted afterwards. No transfer document is created — there is nowhere it is being transferred from."}
          </DialogDescription>
        </DialogHeader>

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
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Reason (optional)</label>
            <textarea
              rows={2}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="e.g. Floor reorganisation"
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
            disabled={!target || mutation.isPending}
            onClick={() => mutation.mutate()}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              target && !mutation.isPending
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : placed ? "Move asset" : "Place asset"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Transfer-custody dialog ──────────────────────────────────────────────

export function CustodyTransferDialog({ assetId, open, onOpenChange }: MoveProps) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<{ id: number; label: string } | null>(null);
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => transferCustody(assetId, target!.id, reason || undefined),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      qc.invalidateQueries({ queryKey: ["employee-assets"] });
      setOpen(false, true);
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
      setTarget(null);
      setReason("");
      mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ArrowRightLeft size={16} /> Transfer custody</DialogTitle>
          <DialogDescription>
            Assigns this asset to a different employee. The change is added to the asset's chain of custody, which cannot be edited or deleted afterwards.
          </DialogDescription>
        </DialogHeader>

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
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Reason (optional)</label>
            <textarea
              rows={2}
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="e.g. Department reassignment"
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
            disabled={!target || mutation.isPending}
            onClick={() => mutation.mutate()}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              target && !mutation.isPending
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Transfer custody"}
          </button>
        </DialogFooter>
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
