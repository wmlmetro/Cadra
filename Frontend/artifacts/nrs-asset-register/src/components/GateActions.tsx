/**
 * The receipt gates on one record: the banner that says a unit is not yet on
 * the register, and the buttons that move it on.
 *
 * SCAFFOLDING — 2026-10-07, handoff 57. The gate machine sits on `nrs.asset`
 * as one field (`register_state`) so tonight's demonstration reuses every
 * proven path unchanged. That design was ruled against for the real build
 * (docs/ADDENDUM-A-EVALUATION.md §4.6); handoff 58 replaces it with a
 * separate candidate model, and this file is rewritten against that model,
 * not extended.
 *
 * The buttons are the SERVER's answer, never a guess: `gates.available` lists
 * the actions the caller's scopes earn for the record's state, with the
 * no-two-gates rule already applied to this caller. An action with
 * `can_fire: false` is drawn as its sentence, not as a button — a button the
 * server would refuse is a button that lies.
 */
import { useMemo, useState } from "react";
import { Link } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  fetchAssetCategories, fireGate, fileToGateAttachment,
  type CandidateRow, type GateAction, type GateAvailability, type GateBody,
  type GateWaitingOn, type RegisterState,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import { cn, formatIsoDateTime, lagosToday } from "@/lib/utils";
import { AlertCircle, Inbox, Loader2, Paperclip, ScanBarcode, X } from "lucide-react";

// ─── Words ───────────────────────────────────────────────────────────────────

export const REGISTER_STATE_WORDS: Record<RegisterState, string> = {
  captured:      "Captured — received, not yet submitted to IAD",
  vfm_pending:   "Awaiting IAD verification",
  vfm_verified:  "Verified — awaiting IAD approval",
  vfm_approved:  "IAD approved — awaiting a tag request",
  vfm_query:     "Queried by IAD — awaiting the store's answer",
  vfm_rejected:  "Rejected by IAD",
  tag_requested: "Tag requested",
  tag_issued:    "Tag issued — awaiting the label on the asset",
  tagged:        "Tagged — awaiting submission to the register",
  reg_submitted: "Submitted — awaiting register approval",
  registered:    "On the register",
};

/** Short form, for a table cell. */
export const REGISTER_STATE_SHORT: Record<RegisterState, string> = {
  captured:      "Captured",
  vfm_pending:   "VfM pending",
  vfm_verified:  "VfM verified",
  vfm_approved:  "VfM approved",
  vfm_query:     "Queried",
  vfm_rejected:  "Rejected",
  tag_requested: "Tag requested",
  tag_issued:    "Tag issued",
  tagged:        "Tagged",
  reg_submitted: "Submitted",
  registered:    "Registered",
};

export const WAITING_ON_WORDS: Record<GateWaitingOn, string> = {
  store:        "Store",
  iad:          "IAD officer",
  iad_approver: "IAD approver",
  controller:   "Asset Controller",
  tagging:      "Tagging",
  maker:        "Register Maker",
  checker:      "Register Checker",
};

const ACTION_WORDS: Record<GateAction, string> = {
  "submit":               "Submit to IAD",
  "verify":               "Verify (value for money)",
  "approve":              "Approve (value for money)",
  "query":                "Query",
  "resubmit":             "Answer and resubmit",
  "reject":               "Reject",
  "request-tagging":      "Request tagging",
  "register":             "Submit to register",
  "approve-registration": "Approve registration",
  "return-registration":  "Return to maker",
};

/** What each dialog says the action does, before the person commits. */
const ACTION_SENTENCES: Record<GateAction, string> = {
  "submit":               "Sends this received unit to Internal Audit for value-for-money verification.",
  "verify":               "Records that you have sighted this unit against the order. All four checks and at least one piece of evidence are required.",
  "approve":              "Approves the verification. You cannot approve a unit you verified or received yourself.",
  "query":                "Sends the unit back to the store with your question. Nothing is lost; the store answers and resubmits.",
  "resubmit":             "Answers IAD's query and sends the unit back for verification.",
  "reject":               "Rejects this unit. It will not reach the register. This cannot be undone tonight.",
  "request-tagging":      "Asks the Tag-Issuing Unit for a label. The label is minted now and can then be printed and affixed at the Barcode Station.",
  "register":             "Submits this tagged unit to the register with its SAP asset code and cost. A different person approves it.",
  "approve-registration": "Puts this unit on the register and sends its asset master to SAP. You cannot approve a submission you made.",
  "return-registration":  "Sends the submission back to the Register Maker with your reason.",
};

/** The order the buttons are drawn in — forward first, then the side doors. */
const ACTION_ORDER: GateAction[] = [
  "submit", "resubmit", "verify", "approve", "request-tagging", "register",
  "approve-registration", "query", "return-registration", "reject",
];

const DESTRUCTIVE = new Set<GateAction>(["reject", "query", "return-registration"]);

// ─── Banner ──────────────────────────────────────────────────────────────────

/** Shown on a candidate's asset page so nobody mistakes it for a register
 *  asset. Draws nothing for a registered one. */
export function CandidateBanner({ row }: { row: Pick<CandidateRow, "register_state" | "gates"> }) {
  if (!row.register_state || row.register_state === "registered") return null;
  const rejected = row.register_state === "vfm_rejected";
  const waiting = row.gates?.waiting_on;
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-2xl border p-4",
        rejected
          ? "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30"
          : "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",
      )}
      data-testid="candidate-banner"
    >
      <Inbox size={18} className={cn("shrink-0 mt-0.5", rejected ? "text-red-600" : "text-amber-600")} />
      <div className="text-xs space-y-1">
        <p className="font-semibold text-foreground">
          Not on the register — this is a received unit still passing its gates.
        </p>
        <p className="text-muted-foreground">
          <span data-testid="candidate-banner-state">{REGISTER_STATE_WORDS[row.register_state]}</span>
          {waiting && (
            <> · waiting on <span className="font-semibold text-foreground" data-testid="candidate-banner-waiting">{WAITING_ON_WORDS[waiting]}</span></>
          )}
          {row.gates?.state_since && <> · since {formatIsoDateTime(row.gates.state_since)}</>}
        </p>
        {row.register_state === "tag_issued" && (
          <p className="text-muted-foreground">
            Print the label and confirm it affixed at the{" "}
            <Link href="/tools/barcode" className="text-primary font-semibold hover:underline">
              <ScanBarcode size={11} className="inline -mt-0.5" /> Barcode Station
            </Link>
            ; the unit moves to <em>Tagged</em> when the label is confirmed.
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Actions ─────────────────────────────────────────────────────────────────

export function invalidateGateQueries(qc: ReturnType<typeof useQueryClient>, assetId: number | string) {
  qc.invalidateQueries({ queryKey: ["asset-gates", String(assetId)] });
  qc.invalidateQueries({ queryKey: ["candidates"] });
  invalidateAssetQueries(qc, String(assetId));
}

interface GateActionsProps {
  row: CandidateRow;
  /** Smaller buttons and refusals in one line, for a table row. */
  compact?: boolean;
}

/** The buttons the server says this person may press on this record now,
 *  and, for the ones their role earns but the no-two-gates rule refuses, the
 *  sentence instead. */
export function GateActions({ row, compact }: GateActionsProps) {
  // The action's availability is captured WHEN THE DIALOG OPENS, not looked
  // up on each render: a refresh that drops the action (somebody else moved
  // the unit) must not take the dialog, and the refusal in it, away.
  const [open, setOpen] = useState<GateAvailability | null>(null);
  const available = useMemo(() => {
    const list = row.gates?.available ?? [];
    return [...list].sort((a, b) => ACTION_ORDER.indexOf(a.action) - ACTION_ORDER.indexOf(b.action));
  }, [row.gates?.available]);
  const firable = available.filter(a => a.can_fire);
  const refused = available.filter(a => !a.can_fire && a.refusal);
  // Two actions refused for the same reason (approve and reject, say, both
  // refused to the verifier) print one sentence, not two.
  const refusals = Array.from(new Set(refused.map(a => a.refusal as string)));

  if (firable.length === 0 && refusals.length === 0) return null;

  return (
    <div className={cn("flex flex-col gap-2", compact && "gap-1")} data-testid={`gate-actions-${row.id}`}>
      {firable.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {firable.map(a => (
            <button
              key={a.action}
              type="button"
              onClick={() => setOpen(a)}
              data-testid={`gate-${a.action}`}
              className={cn(
                "font-semibold rounded-xl transition-colors",
                compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-xs",
                DESTRUCTIVE.has(a.action)
                  ? "border border-border text-foreground hover:bg-muted"
                  : "bg-primary text-primary-foreground hover:bg-primary/90",
              )}
            >
              {ACTION_WORDS[a.action]}
            </button>
          ))}
        </div>
      )}
      {refusals.map(r => (
        <p key={r} className="text-[11px] text-muted-foreground flex items-start gap-1.5" data-testid="gate-refusal">
          <AlertCircle size={12} className="shrink-0 mt-0.5" /> {r}
        </p>
      ))}
      {open && (
        <GateDialog
          row={row}
          action={open.action}
          spec={open}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

// ─── Dialog ──────────────────────────────────────────────────────────────────

const CHECKLIST = [
  ["quantity", "Quantity matches the order"],
  ["specification", "Specification matches the order"],
  ["condition", "Condition is acceptable"],
  ["price", "Price matches the order"],
] as const;

type ChecklistKey = typeof CHECKLIST[number][0];

const INPUT = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const LABEL = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";

function GateDialog({ row, action, spec, onClose }: {
  row: CandidateRow; action: GateAction; spec: GateAvailability; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [checks, setChecks] = useState<Record<ChecklistKey, boolean>>(
    { quantity: false, specification: false, condition: false, price: false });
  const [files, setFiles] = useState<File[]>([]);
  const [sapCode, setSapCode] = useState("");
  const [cost, setCost] = useState("");
  const [costCentre, setCostCentre] = useState("");
  const [capDate, setCapDate] = useState(lagosToday());
  const [assetClass, setAssetClass] = useState<number | null>(row.category?.id ?? null);

  const isReason = action === "query" || action === "reject" || action === "return-registration";
  const isResponse = action === "resubmit";
  const isVerify = action === "verify";
  const isRegister = action === "register";
  const needsText = isReason || isResponse || spec.reason_required;

  const categories = useQuery({
    queryKey: ["asset-categories"],
    queryFn: fetchAssetCategories,
    enabled: isRegister,
    staleTime: 10 * 60_000,
  });

  // What is missing, in words, BEFORE the server is asked — the dialog says
  // so first; the server still refuses if it is sent anyway.
  const missing: string[] = [];
  if (needsText && !reason.trim()) missing.push(isResponse ? "your answer to the query" : "a reason");
  if (isVerify) {
    if (!CHECKLIST.every(([k]) => checks[k])) missing.push("all four checks");
    if (files.length === 0) missing.push("at least one piece of evidence");
  }
  if (isRegister) {
    if (!sapCode.trim()) missing.push("the SAP asset code");
    if (!(Number(cost) > 0)) missing.push("the cost");
    if (!costCentre.trim()) missing.push("the cost centre");
    if (!capDate) missing.push("the capitalisation date");
    if (!assetClass) missing.push("the asset class");
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const body: GateBody = {};
      if (isReason) body.reason = reason;
      else if (isResponse) body.response = reason;
      else if (notes.trim()) body.notes = notes;
      if (isVerify) {
        body.checklist = { ...checks };
        body.attachments = await Promise.all(files.map(fileToGateAttachment));
      }
      if (isRegister) {
        body.sap_asset_code = sapCode;
        body.cost = Number(cost);
        body.cost_centre = costCentre;
        body.capitalisation_date = capDate;
        body.asset_class = assetClass ?? undefined;
      }
      return fireGate(row.id, action, body);
    },
    onSuccess: () => {
      invalidateGateQueries(qc, row.id);
      close(true);
    },
  });
  const err = mutation.error as CadraApiError | null;

  // Never closable mid-flight: closing detaches the mutation and a refusal
  // would then be shown nowhere (see MarkMissingDialog). A 409 means what is
  // drawn behind the dialog is stale — the unit moved, or the rule refused —
  // but it is refreshed on CLOSE, not on the error: refreshing while the
  // dialog is open can remove the row (and the dialog with it) from a
  // filtered list before the person has read the refusal.
  const close = (done = false) => {
    if (mutation.isPending && !done) return;
    if (!done && err?.status === 409) invalidateGateQueries(qc, row.id);
    onClose();
  };

  const ready = missing.length === 0 && !mutation.isPending;

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid={`dialog-gate-${action}`}>
        <DialogHeader>
          <DialogTitle>{ACTION_WORDS[action]}</DialogTitle>
          <DialogDescription>
            <span className="font-semibold text-foreground">{row.asset_code}</span> · {row.name}
            <br />
            {ACTION_SENTENCES[action]}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {isVerify && (
            <>
              <fieldset className="space-y-2" data-testid="verify-checklist">
                <legend className={LABEL}>Checks</legend>
                {CHECKLIST.map(([k, words]) => (
                  <label key={k} className="flex items-center gap-2 text-xs text-foreground">
                    <input
                      type="checkbox"
                      checked={checks[k]}
                      onChange={e => setChecks(c => ({ ...c, [k]: e.target.checked }))}
                      data-testid={`check-${k}`}
                    />
                    {words}
                  </label>
                ))}
              </fieldset>
              <div>
                <span className={LABEL}>Evidence</span>
                <label className="mt-1.5 flex items-center gap-2 text-xs text-primary font-semibold cursor-pointer">
                  <Paperclip size={13} /> Attach a photo or document
                  <input
                    type="file"
                    multiple
                    className="sr-only"
                    onChange={e => {
                      const picked = Array.from(e.target.files ?? []);
                      setFiles(f => [...f, ...picked]);
                      e.target.value = "";
                    }}
                    data-testid="input-evidence"
                  />
                </label>
                {files.length > 0 && (
                  <ul className="mt-1.5 space-y-1">
                    {files.map((f, i) => (
                      <li key={`${f.name}-${i}`} className="flex items-center gap-2 text-[11px] text-muted-foreground">
                        <Paperclip size={11} /> {f.name}
                        <button
                          type="button"
                          onClick={() => setFiles(fs => fs.filter((_, j) => j !== i))}
                          className="hover:text-foreground"
                          aria-label={`Remove ${f.name}`}
                        >
                          <X size={11} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}

          {isRegister && (
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label htmlFor="gate-sap" className={LABEL}>SAP asset code</label>
                <input id="gate-sap" value={sapCode} onChange={e => setSapCode(e.target.value)}
                  className={INPUT} placeholder="As SAP issued it" data-testid="input-sap-asset-code" />
              </div>
              <div>
                <label htmlFor="gate-cost" className={LABEL}>Cost (₦)</label>
                <input id="gate-cost" type="number" min="0" step="0.01" value={cost}
                  onChange={e => setCost(e.target.value)} className={INPUT} data-testid="input-cost" />
              </div>
              <div>
                <label htmlFor="gate-cc" className={LABEL}>Cost centre</label>
                <input id="gate-cc" value={costCentre} onChange={e => setCostCentre(e.target.value)}
                  className={INPUT} data-testid="input-cost-centre" />
              </div>
              <div>
                <label htmlFor="gate-capdate" className={LABEL}>Capitalisation date</label>
                <input id="gate-capdate" type="date" value={capDate} onChange={e => setCapDate(e.target.value)}
                  className={INPUT} data-testid="input-capitalisation-date" />
              </div>
              <div>
                <label htmlFor="gate-class" className={LABEL}>Asset class</label>
                <select
                  id="gate-class"
                  value={assetClass ?? ""}
                  onChange={e => setAssetClass(e.target.value ? Number(e.target.value) : null)}
                  className={INPUT}
                  data-testid="input-asset-class"
                >
                  <option value="">Choose…</option>
                  {/* The unit's own class is offered even before (or without)
                      the category list, so confirming it never waits on a read. */}
                  {row.category && !(categories.data ?? []).some(c => c.id === row.category!.id) && (
                    <option value={row.category.id}>{row.category.name}</option>
                  )}
                  {(categories.data ?? []).map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Confirm the class Vendra gave it, or correct it.
                </p>
              </div>
            </div>
          )}

          {needsText ? (
            <div>
              <label htmlFor="gate-reason" className={LABEL}>
                {isResponse ? "Your answer to IAD's query" : "Reason"}
              </label>
              <textarea id="gate-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)}
                className={INPUT} placeholder="Required" data-testid="input-gate-reason" />
            </div>
          ) : (
            <div>
              <label htmlFor="gate-notes" className={LABEL}>Notes (optional)</label>
              <textarea id="gate-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
                className={INPUT} data-testid="input-gate-notes" />
            </div>
          )}

          {missing.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="gate-missing">
              Still needed: {missing.join(", ")}.
            </p>
          )}

          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3"
                 data-testid="gate-error">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={err} />
            </div>
          )}
        </div>

        <DialogFooter>
          <button type="button" onClick={() => close()}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            type="button"
            disabled={!ready}
            onClick={() => mutation.mutate()}
            data-testid="button-confirm-gate"
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
              ready ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {mutation.isPending && <Loader2 size={12} className="animate-spin" />}
            {ACTION_WORDS[action]}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
