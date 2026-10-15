/**
 * Batches on the Candidates page (handoff 60 §2b, §2d).
 *
 * A batch is N single-unit gate fires ON THE SERVER: each unit is checked on
 * its own (the no-two-gates rule, the placeholder and SAP-class checks), each
 * gets its own events, and one refused unit never rolls the others back. So
 * nothing here decides what will pass — the dialogs send the selection, and
 * the answer is read back line by line, every refusal in the server's own
 * words. A refusal of the WHOLE batch (units from more than one receipt, a
 * missing cost centre) is an ordinary error, shown verbatim, and the dialog
 * stays open with everything the person entered — the evidence files too.
 *
 *   BatchVerifyDialog       IAD officer — one checklist and one evidence set
 *                           for the units of ONE receipt
 *   BatchApproveDialog      IAD approver (`approve`) and Register Checker
 *                           (`approve-registration`)
 *   PasteRegisterDialog     Register Maker — pasted `<asset code> <SAP code>
 *                           [cost]` lines, previewed (a dry run) before
 *                           anything fires
 *   BatchResultsDialog      every unit, fired or refused, after a batch
 *   RowEvidenceDialog       what IAD saw, from the approver's row
 */
import { useMemo, useState } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  fireGateBatch, fileToGateAttachment, GATE_BATCH_MAX,
  type CandidateRow, type GateBatchAction, type GateBatchAnswer, type GateBatchLine,
  type GateBatchRegisterLine,
} from "@/lib/dataProvider";
import type { CadraApiError } from "@/lib/api";
import { CANDIDATES_BADGE_KEY } from "@/lib/gateEvidence";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { GateEvidence } from "@/components/GateEvidence";
import { invalidateAssetQueries } from "@/components/AssetActionDialogs";
import {
  EvidencePicker, INPUT, LABEL, NO_CHECKS, VerifyChecklist, allFour,
  readMakerCarry, saveMakerCarry, type Checklist,
} from "@/components/GateActions";
import { cn } from "@/lib/utils";
import { AlertCircle, CheckCircle2, Loader2, XCircle } from "lucide-react";

// ─── Words ───────────────────────────────────────────────────────────────────

const DONE_WORDS: Record<GateBatchAction, string> = {
  "verify":               "verified",
  "approve":              "approved",
  "approve-registration": "put on the register",
  "register":             "submitted to the register",
};

const TITLE_WORDS: Record<GateBatchAction, string> = {
  "verify":               "Verify selected units",
  "approve":              "Approve selected units",
  "approve-registration": "Approve selected registrations",
  "register":             "Paste SAP codes",
};

/** "17 of 20 verified, 3 refused." — or, on a preview, what WOULD happen. */
export function batchSummary(a: Pick<GateBatchAnswer, "action" | "dry_run" | "total" | "fired" | "refused">): string {
  const done = DONE_WORDS[a.action];
  if (a.dry_run) {
    return `${a.fired} of ${a.total} would be ${done}, ${a.refused} would be refused. Nothing has been written yet.`;
  }
  return `${a.fired} of ${a.total} ${done}, ${a.refused} refused.`;
}

const money = (n: number | null | undefined) =>
  typeof n === "number" ? `₦${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—";

/** After any batch: the list, every asset page's gate block, the person's
 *  badge and the evidence the approver reads. */
export function invalidateAfterBatch(qc: QueryClient, answer: GateBatchAnswer | null) {
  qc.invalidateQueries({ queryKey: ["candidates"] });
  qc.invalidateQueries({ queryKey: ["asset-gates"] });
  qc.invalidateQueries({ queryKey: CANDIDATES_BADGE_KEY });
  qc.invalidateQueries({ queryKey: ["gate-evidence"] });
  for (const l of answer?.results ?? []) {
    if (l.outcome === "fired" && l.asset_id != null) invalidateAssetQueries(qc, String(l.asset_id));
  }
}

/** The distinct receipts (GRNs) among some units; a unit with none counts as
 *  its own "no GRN" receipt, as the server counts it. */
function receiptsOf(rows: CandidateRow[]): string[] {
  return Array.from(new Set(rows.map(r => r.provenance?.grn_reference || "(no GRN)")));
}

function UnitList({ rows }: { rows: CandidateRow[] }) {
  return (
    <ul className="max-h-40 overflow-y-auto rounded-xl border border-border divide-y divide-border text-[11px]"
        data-testid="batch-units">
      {rows.map(r => (
        <li key={r.id} className="px-3 py-1.5 flex items-center gap-2">
          <span className="font-semibold text-foreground">{r.asset_code}</span>
          <span className="text-muted-foreground truncate">{r.name}</span>
          {r.provenance?.grn_reference && (
            <span className="ml-auto text-muted-foreground whitespace-nowrap">{r.provenance.grn_reference}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function ErrorPanel({ err }: { err: CadraApiError }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3"
         data-testid="batch-error">
      <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <ApiErrorMessage err={err} />
    </div>
  );
}

function SubmitButton({ ready, pending, onClick, children, testid = "button-batch-submit" }: {
  ready: boolean; pending: boolean; onClick: () => void; children: React.ReactNode; testid?: string;
}) {
  return (
    <button
      type="button"
      disabled={!ready || pending}
      onClick={onClick}
      data-testid={testid}
      className={cn(
        "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
        ready && !pending ? "bg-primary text-primary-foreground hover:bg-primary/90"
                          : "bg-muted text-muted-foreground cursor-not-allowed",
      )}
    >
      {pending && <Loader2 size={12} className="animate-spin" />}
      {children}
    </button>
  );
}

// ─── Verify ──────────────────────────────────────────────────────────────────

export function BatchVerifyDialog({ rows, onClose, onDone }: {
  rows: CandidateRow[]; onClose: () => void; onDone: (a: GateBatchAnswer) => void;
}) {
  const [checks, setChecks] = useState<Checklist>(NO_CHECKS);
  const [files, setFiles] = useState<File[]>([]);
  const [notes, setNotes] = useState("");
  const receipts = useMemo(() => receiptsOf(rows), [rows]);

  const mutation = useMutation<GateBatchAnswer, CadraApiError>({
    mutationFn: async () => fireGateBatch("verify", {
      asset_ids: rows.map(r => r.id),
      checklist: { ...checks },
      attachments: await Promise.all(files.map(fileToGateAttachment)),
      notes,
    }),
    onSuccess: onDone,
  });

  const missing: string[] = [];
  if (!allFour(checks)) missing.push("all four checks");
  if (files.length === 0) missing.push("at least one piece of evidence");
  if (rows.length > GATE_BATCH_MAX) missing.push(`at most ${GATE_BATCH_MAX} units in one batch`);

  const close = () => { if (!mutation.isPending) onClose(); };

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="batch-dialog" data-action="verify">
        <DialogHeader>
          <DialogTitle>{TITLE_WORDS.verify}</DialogTitle>
          <DialogDescription>
            Records that you have sighted these {rows.length} units against the order. One set of checks and
            evidence covers them all; each unit is verified on its own record, and a unit the rules refuse
            is listed with the reason while the others go ahead.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <UnitList rows={rows} />
          {receipts.length > 1 && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-start gap-1.5" data-testid="batch-receipts-hint">
              <AlertCircle size={12} className="shrink-0 mt-0.5" />
              These units come from {receipts.length} receipts ({receipts.slice(0, 3).join(", ")}
              {receipts.length > 3 ? "…" : ""}). One verification covers one receipt — type a GRN into the
              search box at the top to list one delivery, then select it.
            </p>
          )}
          <VerifyChecklist checks={checks} onChange={setChecks} />
          <EvidencePicker files={files} onChange={setFiles} />
          <div>
            <label htmlFor="batch-notes" className={LABEL}>Notes (optional)</label>
            <textarea id="batch-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              className={INPUT} data-testid="input-batch-notes" />
          </div>
          {missing.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="gate-missing">
              Still needed: {missing.join(", ")}.
            </p>
          )}
          {mutation.error && <ErrorPanel err={mutation.error} />}
        </div>

        <DialogFooter>
          <button type="button" onClick={close}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <SubmitButton ready={missing.length === 0} pending={mutation.isPending} onClick={() => mutation.mutate()}>
            Verify {rows.length} {rows.length === 1 ? "unit" : "units"}
          </SubmitButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Approve (IAD approver) / approve registration (Register Checker) ───────

export function BatchApproveDialog({ action, rows, onClose, onDone }: {
  action: "approve" | "approve-registration";
  rows: CandidateRow[]; onClose: () => void; onDone: (a: GateBatchAnswer) => void;
}) {
  const [notes, setNotes] = useState("");
  const mutation = useMutation<GateBatchAnswer, CadraApiError>({
    mutationFn: () => fireGateBatch(action, { asset_ids: rows.map(r => r.id), notes }),
    onSuccess: onDone,
  });
  const close = () => { if (!mutation.isPending) onClose(); };
  const tooMany = rows.length > GATE_BATCH_MAX;
  const isCheck = action === "approve-registration";

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="batch-dialog" data-action={action}>
        <DialogHeader>
          <DialogTitle>{TITLE_WORDS[action]}</DialogTitle>
          <DialogDescription>
            {isCheck
              ? <>Puts these {rows.length} units on the register and sends each one's asset master to SAP. A
                  submission you made yourself is refused, with the reason; the rest go ahead.</>
              : <>Approves the verification of these {rows.length} units, each on its own record. A unit you
                  verified or received yourself is refused, with the reason; the rest go ahead.</>}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {isCheck ? (
            <div className="max-h-56 overflow-y-auto rounded-xl border border-border">
              <table className="w-full text-[11px]" data-testid="batch-units">
                <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground sticky top-0">
                  <tr>
                    <th className="text-left font-semibold px-3 py-1.5">Unit</th>
                    <th className="text-left font-semibold px-3 py-1.5">SAP code</th>
                    <th className="text-right font-semibold px-3 py-1.5">Cost</th>
                    <th className="text-left font-semibold px-3 py-1.5">Cost centre</th>
                    <th className="text-left font-semibold px-3 py-1.5">Class</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const g = r.gates?.registration;
                    return (
                      <tr key={r.id} className="border-t border-border">
                        <td className="px-3 py-1.5 font-semibold">{r.asset_code}</td>
                        <td className="px-3 py-1.5 font-mono">{g?.sap_asset_code ?? "—"}</td>
                        <td className="px-3 py-1.5 text-right">{money(g?.cost)}</td>
                        <td className="px-3 py-1.5">{g?.cost_centre ?? "—"}</td>
                        <td className="px-3 py-1.5">
                          {g?.asset_class ? <>{g.asset_class.name}{g.asset_class.sap_asset_class && <span className="text-muted-foreground"> · {g.asset_class.sap_asset_class}</span>}</> : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <UnitList rows={rows} />
          )}
          <div>
            <label htmlFor="batch-notes" className={LABEL}>Notes (optional)</label>
            <textarea id="batch-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              className={INPUT} data-testid="input-batch-notes" />
          </div>
          {tooMany && (
            <p className="text-[11px] text-muted-foreground" data-testid="gate-missing">
              A batch takes at most {GATE_BATCH_MAX} units; {rows.length} are selected.
            </p>
          )}
          {mutation.error && <ErrorPanel err={mutation.error} />}
        </div>

        <DialogFooter>
          <button type="button" onClick={close}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <SubmitButton ready={!tooMany} pending={mutation.isPending} onClick={() => mutation.mutate()}>
            Approve {rows.length} {rows.length === 1 ? "unit" : "units"}
          </SubmitButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Results ─────────────────────────────────────────────────────────────────

function ResultLine({ line, action, testid }: { line: GateBatchLine; action: GateBatchAction; testid: string }) {
  const ok = line.outcome !== "refused";
  return (
    <li className="px-3 py-2 text-[11px] flex items-start gap-2" data-testid={testid} data-outcome={line.outcome}>
      {ok
        ? <CheckCircle2 size={13} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
        : <XCircle size={13} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />}
      <div className="min-w-0">
        <p>
          <span className="font-semibold text-foreground">{line.asset_code ?? `Unit ${line.asset_id ?? "?"}`}</span>
          {line.name && <span className="text-muted-foreground"> · {line.name}</span>}
          {" — "}
          {ok
            ? <span className="text-foreground">{line.outcome === "would_fire" ? `would be ${DONE_WORDS[action]}` : DONE_WORDS[action]}</span>
            : <span className="text-red-700 dark:text-red-400" data-testid="batch-result-message">{line.message ?? "Refused."}</span>}
        </p>
        {line.warning && (
          <p className="mt-0.5 text-amber-700 dark:text-amber-400" data-testid="batch-result-warning">{line.warning}</p>
        )}
      </div>
    </li>
  );
}

export function BatchResultsDialog({ answer, onClose }: { answer: GateBatchAnswer; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="batch-results">
        <DialogHeader>
          <DialogTitle>{TITLE_WORDS[answer.action]} — the answer</DialogTitle>
          <DialogDescription data-testid="batch-results-summary">{batchSummary(answer)}</DialogDescription>
        </DialogHeader>
        <ul className="rounded-xl border border-border divide-y divide-border">
          {answer.results.map((l, i) => (
            <ResultLine key={`${l.asset_id ?? "x"}-${i}`} line={l} action={answer.action}
              testid={`batch-result-${l.asset_id ?? `line-${l.line ?? i + 1}`}`} />
          ))}
        </ul>
        <DialogFooter>
          <button type="button" onClick={onClose} data-testid="button-close-batch-results"
            className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">
            Close
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Paste SAP codes (Register Maker) ────────────────────────────────────────

interface ParsedLine {
  /** The line's number in the box, from 1 — what the person sees. */
  textLine: number;
  raw: string;
  line?: GateBatchRegisterLine;
  /** Why the line was not understood; set instead of `line`. */
  problem?: string;
}

/** `<asset code> <SAP code> [cost]`, split on spaces, tabs or commas (a
 *  spreadsheet's columns paste as tabs). A cost written with thousands
 *  separators (`125,000`) splits into groups of three and is joined back. */
export function parsePastedLines(text: string): ParsedLine[] {
  const out: ParsedLine[] = [];
  text.split(/\r?\n/).forEach((raw, i) => {
    if (!raw.trim()) return;
    let parts = raw.trim().split(/[\s,;]+/).filter(Boolean);
    if (parts.length > 3 && parts.slice(3).every(p => /^\d{3}(\.\d+)?$/.test(p))) {
      parts = [parts[0], parts[1], parts.slice(2).join("")];
    }
    const textLine = i + 1;
    if (parts.length < 2 || parts.length > 3) {
      out.push({ textLine, raw, problem: "Not understood: a line is an asset code, a SAP code and, if you want, a cost." });
      return;
    }
    const [asset_code, sap_asset_code, costText] = parts;
    const line: GateBatchRegisterLine = { asset_code, sap_asset_code };
    if (costText !== undefined) {
      const cost = Number(costText.replace(/^₦/, ""));
      if (!Number.isFinite(cost) || cost <= 0) {
        out.push({ textLine, raw, problem: `Not understood: the cost “${costText}” is not a number above zero.` });
        return;
      }
      line.cost = cost;
    }
    out.push({ textLine, raw, line });
  });
  return out;
}

export function PasteRegisterDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [carry] = useState(readMakerCarry);
  const [costCentre, setCostCentre] = useState(carry.cost_centre);
  const [capDate, setCapDate] = useState(carry.capitalisation_date);
  const [notes, setNotes] = useState("");
  // The last answer and the exact body it answered: a preview is only good
  // for the paste it previewed.
  const [answer, setAnswer] = useState<{ key: string; data: GateBatchAnswer } | null>(null);

  const parsed = useMemo(() => parsePastedLines(text), [text]);
  const sendable = parsed.filter(p => p.line);
  const body = { lines: sendable.map(p => p.line!), cost_centre: costCentre.trim(), capitalisation_date: capDate, notes };
  const key = JSON.stringify(body);

  const mutation = useMutation<{ key: string; data: GateBatchAnswer }, CadraApiError, boolean>({
    mutationFn: async (dryRun) => ({ key, data: await fireGateBatch("register", { ...body, dry_run: dryRun }) }),
    onSuccess: (res) => {
      setAnswer(res);
      if (!res.data.dry_run) {
        invalidateAfterBatch(qc, res.data);
        if (res.data.fired > 0) saveMakerCarry({ cost_centre: costCentre, capitalisation_date: capDate });
      }
    },
  });

  const missing: string[] = [];
  if (sendable.length === 0) missing.push("at least one line");
  if (sendable.length > GATE_BATCH_MAX) missing.push(`at most ${GATE_BATCH_MAX} lines in one batch (${sendable.length} pasted)`);
  if (!costCentre.trim()) missing.push("the cost centre");
  if (!capDate) missing.push("the capitalisation date");

  const fresh = answer && answer.key === key ? answer.data : null;
  const previewed = fresh?.dry_run === true;
  const submitted = fresh?.dry_run === false;
  // The server numbers the lines it was SENT; the person reads the box's.
  const byLine = new Map<number, GateBatchLine>();
  if (fresh) {
    for (const l of fresh.results) {
      const p = sendable[(l.line ?? 0) - 1];
      if (p) byLine.set(p.textLine, l);
    }
  }
  const close = () => { if (!mutation.isPending) onClose(); };

  return (
    <Dialog open onOpenChange={(next) => { if (!next) close(); }}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="batch-dialog" data-action="register">
        <DialogHeader>
          <DialogTitle>{TITLE_WORDS.register}</DialogTitle>
          <DialogDescription>
            One unit per line: its asset code, the SAP asset code SAP issued, and — if it differs from the
            cost the unit was received at — its cost. Spaces, tabs (a spreadsheet's columns) or commas between
            them. <span className="font-semibold text-foreground">Preview</span> checks every line and writes
            nothing; then each line is submitted on its own, and a line the rules refuse is listed with the
            reason while the others go ahead. The class is the unit's own.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label htmlFor="paste-sap" className={LABEL}>Lines</label>
            <textarea id="paste-sap" rows={7} value={text} onChange={e => setText(e.target.value)}
              className={cn(INPUT, "font-mono")} spellCheck={false}
              placeholder={"NRS-AST-055101\t3NNNNNNNNNN\nNRS-AST-055102\t3NNNNNNNNNN\t125000"}
              data-testid="input-paste-sap" />
            <p className="mt-1 text-[11px] text-muted-foreground" data-testid="paste-count">
              {sendable.length} {sendable.length === 1 ? "line" : "lines"} read
              {parsed.length > sendable.length && <>, {parsed.length - sendable.length} not understood (listed below)</>}.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="paste-cc" className={LABEL}>Cost centre — every line</label>
              <input id="paste-cc" value={costCentre} onChange={e => setCostCentre(e.target.value)}
                className={INPUT} data-testid="input-cost-centre" />
            </div>
            <div>
              <label htmlFor="paste-capdate" className={LABEL}>Capitalisation date — every line</label>
              <input id="paste-capdate" type="date" value={capDate} onChange={e => setCapDate(e.target.value)}
                className={INPUT} data-testid="input-capitalisation-date" />
            </div>
          </div>
          <div>
            <label htmlFor="paste-notes" className={LABEL}>Notes (optional)</label>
            <textarea id="paste-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              className={INPUT} data-testid="input-batch-notes" />
          </div>

          {missing.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="gate-missing">
              Still needed: {missing.join(", ")}.
            </p>
          )}
          {answer && !fresh && !mutation.isPending && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400" data-testid="paste-stale">
              Changed since the last answer — preview again before submitting.
            </p>
          )}
          {fresh && (
            <p className={cn("text-[12px] font-semibold", submitted ? "text-foreground" : "text-muted-foreground")}
               data-testid={submitted ? "batch-results-summary" : "paste-preview-summary"}>
              {batchSummary(fresh)}
            </p>
          )}
          {mutation.error && <ErrorPanel err={mutation.error} />}

          {parsed.length > 0 && (
            <div className="rounded-xl border border-border overflow-x-auto" data-testid={submitted ? "batch-results" : "paste-preview"}>
              <table className="w-full text-[11px]">
                <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left font-semibold px-3 py-1.5">#</th>
                    <th className="text-left font-semibold px-3 py-1.5">Asset code</th>
                    <th className="text-left font-semibold px-3 py-1.5">SAP code</th>
                    <th className="text-left font-semibold px-3 py-1.5">Unit</th>
                    <th className="text-left font-semibold px-3 py-1.5">Class</th>
                    <th className="text-right font-semibold px-3 py-1.5">Cost</th>
                    <th className="text-left font-semibold px-3 py-1.5">{submitted ? "Result" : "Preview"}</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.map(p => {
                    const r = byLine.get(p.textLine);
                    const refused = r?.outcome === "refused";
                    return (
                      <tr key={p.textLine} className="border-t border-border align-top"
                          data-testid={`paste-line-${p.textLine}`}
                          data-outcome={p.problem ? "not_understood" : r?.outcome ?? "unchecked"}
                          {...(r?.asset_id != null && submitted ? { "data-asset-id": r.asset_id } : {})}>
                        <td className="px-3 py-1.5 text-muted-foreground">{p.textLine}</td>
                        {p.problem ? (
                          <td colSpan={6} className="px-3 py-1.5">
                            <span className="font-mono text-muted-foreground">{p.raw.trim()}</span>
                            <span className="block text-red-700 dark:text-red-400">{p.problem}</span>
                          </td>
                        ) : (<>
                          <td className="px-3 py-1.5 font-semibold">{p.line!.asset_code}</td>
                          <td className="px-3 py-1.5 font-mono">{p.line!.sap_asset_code}</td>
                          <td className="px-3 py-1.5">
                            {!r ? <span className="text-muted-foreground">—</span>
                              : r.asset_id == null ? <span className="text-red-700 dark:text-red-400">Not found</span>
                              : <>{r.name ?? "—"}{r.grn_reference && <span className="block text-muted-foreground">{r.grn_reference}</span>}</>}
                          </td>
                          <td className="px-3 py-1.5">
                            {r?.category
                              ? <>{r.category.name}
                                  <span className="block text-muted-foreground">
                                    {r.category.sap_asset_class ? <>SAP class <span className="font-mono">{r.category.sap_asset_class}</span></> : "No SAP class"}
                                  </span></>
                              : "—"}
                          </td>
                          <td className="px-3 py-1.5 text-right whitespace-nowrap">
                            {money(p.line!.cost ?? r?.cost ?? null)}
                            {p.line!.cost == null && r && <span className="block text-muted-foreground">as received</span>}
                          </td>
                          <td className="px-3 py-1.5">
                            {!r ? <span className="text-muted-foreground">Not checked yet</span>
                              : refused ? <span className="text-red-700 dark:text-red-400" data-testid="batch-result-message">{r.message ?? "Refused."}</span>
                              : <span className="text-green-700 dark:text-green-400 font-semibold">
                                  {r.outcome === "would_fire" ? "Ready to submit" : "Submitted"}
                                </span>}
                            {r?.warning && (
                              <span className="block text-amber-700 dark:text-amber-400" data-testid="batch-result-warning">{r.warning}</span>
                            )}
                          </td>
                        </>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <DialogFooter>
          {submitted ? (<>
            <button type="button" onClick={() => { setText(""); setAnswer(null); mutation.reset(); }}
              data-testid="button-paste-more"
              className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
              Paste more
            </button>
            <button type="button" onClick={close} data-testid="button-close-batch-results"
              className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90">
              Close
            </button>
          </>) : (<>
            <button type="button" onClick={close}
              className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
              Cancel
            </button>
            <SubmitButton testid="button-paste-preview" ready={missing.length === 0}
              pending={mutation.isPending && mutation.variables === true} onClick={() => mutation.mutate(true)}>
              Preview
            </SubmitButton>
            <SubmitButton testid="button-paste-submit" ready={missing.length === 0 && previewed}
              pending={mutation.isPending && mutation.variables === false} onClick={() => mutation.mutate(false)}>
              Submit {sendable.length} {sendable.length === 1 ? "line" : "lines"}
            </SubmitButton>
          </>)}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Evidence, from the approver's row ───────────────────────────────────────

/** What IAD saw, opened from a Candidates row so the approver need not leave
 *  the list. The panel is the asset page's own (`GateEvidence`), so the two
 *  places cannot disagree. */
export function RowEvidenceDialog({ row, onClose }: { row: CandidateRow; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="row-evidence-dialog">
        <DialogHeader>
          <DialogTitle>Evidence</DialogTitle>
          <DialogDescription>
            <span className="font-semibold text-foreground">{row.asset_code}</span> · {row.name}
            {row.provenance?.grn_reference && <> · {row.provenance.grn_reference}</>}
          </DialogDescription>
        </DialogHeader>
        <GateEvidence assetId={row.id} />
        <DialogFooter>
          <button type="button" onClick={onClose}
            className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-border text-foreground hover:bg-muted">
            Close
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
