import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RecordPicker from "@/components/RecordPicker";
import { CadraApiError, apiGet } from "@/lib/api";
import {
  moveAsset, transferCustody, condemnAsset,
  type ApiAssetTransfer,
} from "@/lib/dataProvider";
import type { ApiLocation } from "@/lib/adapters";
import { AlertCircle, ArrowRightLeft, MapPin, Trash2, Loader2 } from "lucide-react";
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
      qc.invalidateQueries({ queryKey: ["asset", assetId] });
      qc.invalidateQueries({ queryKey: ["asset-history", assetId] });
      qc.invalidateQueries({ queryKey: ["assets"] });
      onOpenChange(false);
      setTarget(null);
      setReason("");
    },
  });
  const err = mutation.error as CadraApiError | null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
            onClick={() => onOpenChange(false)}
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
      qc.invalidateQueries({ queryKey: ["asset", assetId] });
      qc.invalidateQueries({ queryKey: ["asset-history", assetId] });
      qc.invalidateQueries({ queryKey: ["assets"] });
      qc.invalidateQueries({ queryKey: ["employee-assets"] });
      onOpenChange(false);
      setTarget(null);
      setReason("");
    },
  });
  const err = mutation.error as CadraApiError | null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
            onClick={() => onOpenChange(false)}
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
      qc.invalidateQueries({ queryKey: ["asset", assetId] });
      qc.invalidateQueries({ queryKey: ["asset-history", assetId] });
      qc.invalidateQueries({ queryKey: ["assets"] });
      onOpenChange(false);
      setReason("");
    },
  });
  const err = mutation.error as CadraApiError | null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
            <Trash2 size={16} /> Condemn / dispose asset
          </DialogTitle>
          <DialogDescription>
            Sets state to <span className="font-mono">disposed</span>. This asset will no longer appear in active workflows.
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
            onClick={() => onOpenChange(false)}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!reason.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
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

// Silence the unused-import warning when a single Asset transfer row is shown
// elsewhere (this type belongs to the dataProvider).
export type { ApiAssetTransfer };
