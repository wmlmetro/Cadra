import { useState } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RecordPicker from "@/components/RecordPicker";
import { CadraApiError, apiGet } from "@/lib/api";
import {
  moveAsset, transferCustody, condemnAsset, markAssetMissing,
  type ApiAssetTransfer,
} from "@/lib/dataProvider";
import type { ApiLocation } from "@/lib/adapters";
import { AlertCircle, AlertTriangle, ArrowRightLeft, MapPin, Trash2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

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

export function AssetMoveDialog({ assetId, open, onOpenChange }: MoveProps) {
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
          <DialogTitle className="flex items-center gap-2"><MapPin size={16} /> Move asset</DialogTitle>
          <DialogDescription>
            {/* Three versions, and the history of them is the point. It said
                "creates an immutable transfer record" until handoff 27 — false:
                an asset manager can edit or delete a transfer. Handoff 27 said
                so, which was true and, from handoff 28, only half of it: the
                MOVE is now appended to the asset's movement record, which
                nobody can alter, and the transfer is the paperwork beside it.
                Two records of different worth, and the dialog names both. */}
            Updates the current location. The move is added to the asset's movement record, which cannot be edited or deleted afterwards. A transfer document is also created; that one can be edited later by an asset manager.
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
              <p className="text-[12px] text-red-700 dark:text-red-400">
                <span className="font-semibold">{err.code}:</span> {err.message}
              </p>
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
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Move asset"}
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
              <p className="text-[12px] text-red-700 dark:text-red-400">
                <span className="font-semibold">{err.code}:</span> {err.message}
              </p>
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
    mutationFn: () => condemnAsset(assetId, reason),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
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
                approve-disposal route, so nothing made here has an approver. */}
            Sets this asset's state to Disposed and its condition to Decommissioned, and records the reason. It stays on the register. A disposal made here carries no approver — approval is a separate step.
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
            />
          </div>
          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-red-700 dark:text-red-400">
                <span className="font-semibold">{err.code}:</span> {err.message}
              </p>
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
 * There is NO reason field, deliberately. `markAssetMissing` is
 * `PATCH {state: "missing"}` and the model has no field FOR a reason. An asset
 * has three free-text fields — `notes`, `verification_notes`, `disposal_reason`
 * — and each means something else; a missing-reason written into one would
 * overwrite what it holds and mislabel what was put there. A box that collects
 * a reason and keeps it nowhere true is worse than no box.
 */
export function MarkMissingDialog({ assetId, open, onOpenChange }: CondemnProps) {
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => markAssetMissing(assetId),
    onSuccess: () => {
      invalidateAssetQueries(qc, assetId);
      setOpen(false, true);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Nothing to clear but the last error — which must not greet the next open.
  const setOpen = (next: boolean, done = false) => {
    // A USER cannot close it while the request is in flight: closing resets
    // the mutation, which detaches it, and a REFUSAL would then be shown
    // nowhere. `done` is the success handler closing it — which runs while
    // `isPending` still reads true in this closure, so without it the guard
    // blocked the one close that must always happen. (It did, for one build:
    // every dialog stayed open after a successful save. Found by acting.)
    if (!next && mutation.isPending && !done) return;
    if (!next) mutation.reset();
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
            Sets this asset's state to Missing. It stays on the register and in its history. To reverse it, use Edit and set the state back.
          </DialogDescription>
        </DialogHeader>

        {err && (
          <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-700 dark:text-red-400">
              <span className="font-semibold">{err.code}:</span> {err.message}
            </p>
          </div>
        )}

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
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-missing"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              !mutation.isPending
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

// Silence the unused-import warning when a single Asset transfer row is shown
// elsewhere (this type belongs to the dataProvider).
export type { ApiAssetTransfer };
