/**
 * What IAD saw when it verified this unit (handoff 60 §2b).
 *
 * Until handoff 60 the IAD approver approved blind: the checklist and the
 * photographs went into the verify event and nothing in the app read them
 * back. This reads `GET /api/v1/assets/<id>/evidence` and shows each
 * verification, newest first — who, when, the four checks, the notes and
 * the files.
 *
 * A file is opened through the bearer token (`openGateEvidenceFile`): the
 * app has no Odoo session, so a plain link to the API would be refused.
 *
 * `hideWhenEmpty` is for the places where a unit with no verification is the
 * ordinary case (a unit nobody has verified yet, or a register asset that
 * never passed the gates): there the panel draws nothing rather than a
 * sentence on every page. Where a verification is expected — the approver's
 * view — the empty state is said in words.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, FileText, Image as ImageIcon, Loader2, Paperclip, X } from "lucide-react";
import type { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { formatIsoDateTime } from "@/lib/utils";
import {
  fetchGateEvidence, openGateEvidenceFile,
  type GateChecklist, type GateEvidenceAnswer, type GateEvidenceFile,
} from "@/lib/gateEvidence";

// The words IAD ticked in the verify dialog (GateActions `CHECKLIST`), so
// the approver reads what was attested, not a paraphrase of it.
const CHECKS: { key: keyof GateChecklist; words: string }[] = [
  { key: "quantity", words: "Quantity matches the order" },
  { key: "specification", words: "Specification matches the order" },
  { key: "condition", words: "Condition is acceptable" },
  { key: "price", words: "Price matches the order" },
];

function sizeWords(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileButton({ file }: { file: GateEvidenceFile }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<CadraApiError | null>(null);
  const isImage = !!file.mimetype?.startsWith("image/");
  const Icon = isImage ? ImageIcon : FileText;
  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      await openGateEvidenceFile(file);
    } catch (e) {
      setError(e as CadraApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <li>
      <button
        type="button"
        onClick={open}
        disabled={busy}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-border text-xs text-foreground hover:bg-accent disabled:opacity-60"
        data-testid={`gate-evidence-file-${file.id}`}
        title={isImage || file.mimetype === "application/pdf" ? "Open in a new tab" : "Download"}
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Icon size={12} />}
        <span className="truncate max-w-[16rem]">{file.name || "Evidence file"}</span>
        {file.size > 0 && <span className="text-muted-foreground">{sizeWords(file.size)}</span>}
      </button>
      {error && <div className="mt-1"><ApiErrorMessage err={error} /></div>}
    </li>
  );
}

export function GateEvidence({ assetId, hideWhenEmpty = false }: {
  assetId: string | number;
  hideWhenEmpty?: boolean;
}) {
  const { data, isLoading, error } = useQuery<GateEvidenceAnswer, CadraApiError>({
    queryKey: ["gate-evidence", String(assetId)],
    queryFn: () => fetchGateEvidence(assetId),
    enabled: assetId !== "" && assetId != null,
    staleTime: 30_000,
    retry: false,
  });

  const verifications = data?.verifications ?? [];
  if (hideWhenEmpty && (isLoading || error || verifications.length === 0)) return null;

  return (
    <section
      className="bg-card border border-card-border rounded-xl p-4"
      data-testid="gate-evidence"
      aria-label="Verification evidence"
    >
      <h3 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
        <Paperclip size={13} /> What IAD saw when it verified this unit
      </h3>

      {isLoading && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Loader2 size={12} className="animate-spin" /> Reading the verification…
        </p>
      )}

      {error && <ApiErrorMessage err={error} />}

      {!isLoading && !error && verifications.length === 0 && (
        <p className="text-xs text-muted-foreground" data-testid="gate-evidence-empty">
          No verification recorded for this unit yet.
        </p>
      )}

      {verifications.length > 0 && (
        <ol className="space-y-3">
          {verifications.map((v, i) => (
            <li
              key={v.event_id}
              className={i > 0 ? "pt-3 border-t border-border" : undefined}
              data-testid={`gate-evidence-verification-${v.event_id}`}
            >
              <p className="text-xs text-foreground">
                Checked for Internal Audit by <span className="font-semibold">{v.actor_name ?? "a person the record does not name"}</span>
                {v.occurred_at && <> on {formatIsoDateTime(v.occurred_at.replace(" ", "T"))}</>}
                {i === 0 && verifications.length > 1 && (
                  <span className="text-muted-foreground"> — the latest of {verifications.length}</span>
                )}
              </p>

              {v.checklist ? (
                <ul className="mt-1.5 grid sm:grid-cols-2 gap-x-4 gap-y-0.5">
                  {CHECKS.map(c => {
                    const ticked = v.checklist?.[c.key] === true;
                    return (
                      <li
                        key={c.key}
                        className="text-xs flex items-center gap-1.5"
                        data-check={c.key}
                        data-ticked={ticked ? "true" : "false"}
                      >
                        {ticked
                          ? <Check size={12} className="text-green-600 dark:text-green-400" />
                          : <X size={12} className="text-red-600 dark:text-red-400" />}
                        <span className={ticked ? "text-foreground" : "text-red-700 dark:text-red-400"}>
                          {c.words}{!ticked && " — not confirmed"}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="mt-1.5 text-xs text-muted-foreground">No checklist was recorded with this verification.</p>
              )}

              {v.notes && (
                <p className="mt-1.5 text-xs text-foreground whitespace-pre-wrap">
                  <span className="text-muted-foreground">Notes: </span>{v.notes}
                </p>
              )}

              {v.files.length > 0 ? (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {v.files.map(f => <FileButton key={f.id} file={f} />)}
                </ul>
              ) : (
                <p className="mt-1.5 text-xs text-muted-foreground">No files were attached to this verification.</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default GateEvidence;
