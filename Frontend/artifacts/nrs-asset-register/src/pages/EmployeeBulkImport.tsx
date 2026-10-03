import { useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  submitEmployeeImport, fetchImportJobStatus, type ImportJobStatus,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  Upload, FileSpreadsheet, AlertCircle, CheckCircle2, Clock, RotateCcw, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

export default function EmployeeBulkImport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  const qc = useQueryClient();
  const scopes = useScopes();
  const fileRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);

  useEffect(() => {
    setTitle("Employee Bulk Import");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const submit = useMutation({
    mutationFn: () => submitEmployeeImport(file!, sheet || undefined),
    onSuccess: (job) => {
      setJobId(job.job_id);
    },
  });

  // Poll the job status every 2s until done/error.
  const status = useQuery<ImportJobStatus, CadraApiError>({
    queryKey: ["import-job", jobId],
    queryFn: () => fetchImportJobStatus(jobId!),
    enabled: jobId !== null,
    refetchInterval: (q) => {
      const s = q.state.data?.state;
      return s === "done" || s === "error" ? false : 2_000;
    },
    refetchIntervalInBackground: false,
  });

  // When the job completes, refresh the SAP sync counts since employees
  // landed.
  useEffect(() => {
    const s = status.data?.state;
    if (s === "done" || s === "error") {
      qc.invalidateQueries({ queryKey: ["sap-sync-counts"] });
      qc.invalidateQueries({ queryKey: ["employees"] });
    }
  }, [status.data?.state, qc]);

  const reset = () => {
    setFile(null);
    setSheet("");
    setJobId(null);
    submit.reset();
    if (fileRef.current) fileRef.current.value = "";
  };

  const submitErr = submit.error as CadraApiError | null;
  const job = status.data;
  const pct = job?.rows_total && job.rows_processed != null
    ? Math.round((job.rows_processed / job.rows_total) * 100)
    : null;

  // Handoff 46: the upload is `POST /integrations/employees/import`, which
  // needs `integrations:write`. Reached by URL without it, the page says so
  // instead of offering a file picker whose upload the server refuses.
  if (!scopes.has(SCOPE.integrationsWrite)) {
    return <ScopeRefusal scope={SCOPE.integrationsWrite} />;
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Employee bulk import</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Upload an .xlsx nominal roll. Processing is async — the server returns a job id
          and we poll <code className="font-mono">/api/v1/integrations/employees/import/&lt;job_id&gt;</code> every 2 seconds until done.
        </p>
      </div>

      {/* Step 1 — file picker */}
      <div className={cn(
        "bg-card border rounded-2xl p-5 space-y-3",
        jobId ? "border-border opacity-60" : "border-border",
      )}>
        <div className="flex items-center gap-2">
          <span className={cn(
            "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold",
            jobId ? "bg-green-500 text-white" : "bg-primary text-white",
          )}>1</span>
          <p className="text-[13px] font-bold">Choose file</p>
        </div>

        <label className={cn(
          "flex flex-col items-center justify-center gap-2 py-8 border-2 border-dashed rounded-xl cursor-pointer",
          file ? "border-primary/40 bg-primary/5" : "border-border/70 hover:border-primary/30 hover:bg-muted/30",
          jobId && "cursor-not-allowed",
        )}>
          <FileSpreadsheet size={28} className={file ? "text-primary" : "text-muted-foreground/40"} />
          {file ? (
            <>
              <p className="text-[13px] font-semibold text-foreground">{file.name}</p>
              <p className="text-[11px] text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
            </>
          ) : (
            <>
              <p className="text-[13px] font-medium text-foreground">Click to select .xlsx file</p>
              <p className="text-[11px] text-muted-foreground">Accepts SAP nominal-roll exports</p>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            disabled={!!jobId}
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Sheet (optional)</label>
            <input
              type="text"
              value={sheet}
              onChange={e => setSheet(e.target.value)}
              disabled={!!jobId}
              placeholder="Default sheet"
              className="mt-1 w-full px-3 py-1.5 text-xs border border-border rounded-xl bg-background"
            />
          </div>
          <button
            onClick={() => submit.mutate()}
            disabled={!file || submit.isPending || !!jobId}
            className={cn(
              "inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl",
              file && !submit.isPending && !jobId
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {submit.isPending ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            Submit
          </button>
        </div>

        {submitErr && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-700 dark:text-red-400">
              <span className="font-semibold">{submitErr.code}:</span> {submitErr.message}
            </p>
          </div>
        )}
      </div>

      {/* Step 2 — job status */}
      {jobId && (
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold bg-primary text-white">2</span>
            <p className="text-[13px] font-bold">Job #{jobId}</p>
            <span className={cn(
              "ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-semibold border",
              job?.state === "done"    && "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400",
              job?.state === "error"   && "bg-red-50 dark:bg-red-950/30 border-red-200/70 text-red-700 dark:text-red-400",
              (!job || job.state === "queued" || job.state === "running") && "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 text-blue-700 dark:text-blue-400",
            )}>
              {job?.state === "done"  ? <CheckCircle2 size={11} /> :
               job?.state === "error" ? <AlertCircle  size={11} /> :
                                        <Clock size={11} className="animate-pulse" />}
              {job?.state ?? "submitting"}
            </span>
          </div>

          {pct !== null && (
            <>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
              </div>
              <p className="text-[11px] text-muted-foreground">
                {job?.rows_processed?.toLocaleString() ?? 0} of {job?.rows_total?.toLocaleString() ?? "?"} rows · {pct}%
              </p>
            </>
          )}

          {job && (job.rows_created != null || job.rows_updated != null || job.rows_failed != null) && (
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border">
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground uppercase">Created</p>
                <p className="text-[18px] font-extrabold text-green-600 dark:text-green-400 tabular-nums">{job.rows_created ?? 0}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground uppercase">Updated</p>
                <p className="text-[18px] font-extrabold text-blue-600 dark:text-blue-400 tabular-nums">{job.rows_updated ?? 0}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground uppercase">Failed</p>
                <p className="text-[18px] font-extrabold text-red-600 dark:text-red-400 tabular-nums">{job.rows_failed ?? 0}</p>
              </div>
            </div>
          )}

          {job?.errors && job.errors.length > 0 && (
            <div className="space-y-1.5 pt-2 border-t border-border">
              <p className="text-[11px] font-semibold text-muted-foreground uppercase">Errors ({job.errors.length})</p>
              <div className="max-h-40 overflow-auto space-y-1">
                {job.errors.slice(0, 50).map((e, i) => (
                  <div key={i} className="text-[11px] text-red-700 dark:text-red-400 px-2 py-1 rounded bg-red-50 dark:bg-red-950/30">
                    Row {e.row}{e.field ? ` · ${e.field}` : ""}: {e.message}
                  </div>
                ))}
                {job.errors.length > 50 && (
                  <p className="text-[10px] text-muted-foreground italic">…and {job.errors.length - 50} more.</p>
                )}
              </div>
            </div>
          )}

          {(job?.state === "done" || job?.state === "error") && (
            <div className="flex gap-2 pt-2">
              <button onClick={reset} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent">
                <RotateCcw size={12} /> Import another file
              </button>
              <button onClick={() => nav("/hr/employees")} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90">
                View employees
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
