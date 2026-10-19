/**
 * Settings — SAP asset master (handoff 63 §1).
 *
 * The System Administrator uploads SAP's asset-master export — the .XLSX as
 * SAP produced it — and the server reads it in the background into the SAP
 * mirror: a read-only copy of SAP's register, NOT the asset register. The
 * header row is checked on upload (a missing column is refused there and
 * then, in words); the rest is read in passes, so this page polls the run
 * while it is queued or running. The uploaded file is not kept once the run
 * ends.
 *
 * Importing is `settings:write` held by a system administrator (`admin`),
 * as the server's POST is; the run history is `sap_mirror:read`.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { apiGet, apiUpload, CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Check, Clock, Database, Loader2, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SapImportRun {
  id: number;
  state: "queued" | "running" | "done" | "failed";
  file_name: string;
  file_size: number;
  file_kept: boolean;
  uploaded_by: { id: number; name: string } | null;
  uploaded_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  cpu_seconds: number;
  ticks: number;
  peak_memory_mb: number;
  progress: { sheet_bytes: number; read_bytes: number; percent: number };
  rows_read: number;
  created: number;
  updated: number;
  unchanged: number;
  refused: number;
  refused_reasons: { reason: string; rows: number }[];
  marked_not_in_latest_export: number;
  message: string | null;
}

export const SAP_IMPORTS_KEY = ["sap-assets", "imports"] as const;

async function fetchRuns(): Promise<SapImportRun[]> {
  return (await apiGet<SapImportRun[]>("/api/v1/sap-assets/imports", { limit: 20 })).data;
}

const n = (v: number) => v.toLocaleString();

function when(at: string | null): string {
  if (!at) return "—";
  return new Date(at).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function mb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function RunCard({ run }: { run: SapImportRun }) {
  const live = run.state === "queued" || run.state === "running";
  return (
    <div className="glass-card rounded-2xl p-4 space-y-3" data-testid="sap-import-run" data-state={run.state}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{run.file_name}</p>
          <p className="text-[11px] text-muted-foreground">
            Import {run.id} · {mb(run.file_size)} · uploaded by {run.uploaded_by?.name ?? "—"}, {when(run.uploaded_at)}
          </p>
        </div>
        <span className={cn(
          "text-[10px] font-semibold px-2 py-0.5 rounded-lg border whitespace-nowrap",
          run.state === "done" && "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-800/40",
          run.state === "failed" && "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-800/40",
          live && "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40",
        )}>{run.state}</span>
      </div>
      {live && (
        <div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary transition-all" style={{ width: `${run.progress.percent}%` }} />
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {run.progress.percent}% of the sheet read · {n(run.rows_read)} rows so far
          </p>
        </div>
      )}
      {run.message && (
        <p className="text-[12px] text-red-700 dark:text-red-300">{run.message}</p>
      )}
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 text-[12px]">
        <div><dt className="text-muted-foreground">Rows read</dt><dd className="font-semibold" data-testid="run-rows-read">{n(run.rows_read)}</dd></div>
        <div><dt className="text-muted-foreground">Created</dt><dd className="font-semibold" data-testid="run-created">{n(run.created)}</dd></div>
        <div><dt className="text-muted-foreground">Updated</dt><dd className="font-semibold">{n(run.updated)}</dd></div>
        <div><dt className="text-muted-foreground">Unchanged</dt><dd className="font-semibold" data-testid="run-unchanged">{n(run.unchanged)}</dd></div>
        <div><dt className="text-muted-foreground">Refused</dt><dd className="font-semibold" data-testid="run-refused">{n(run.refused)}</dd></div>
        <div><dt className="text-muted-foreground">No longer in SAP's export</dt><dd className="font-semibold">{n(run.marked_not_in_latest_export)}</dd></div>
      </dl>
      {run.refused_reasons.length > 0 && (
        <div className="text-[12px]">
          <p className="text-muted-foreground">Refused rows, by reason (the rows themselves are not kept):</p>
          <ul className="list-disc ml-5">
            {run.refused_reasons.map((r) => (
              <li key={r.reason}>{n(r.rows)} — {r.reason}</li>
            ))}
          </ul>
        </div>
      )}
      {!live && (
        <p className="text-[11px] text-muted-foreground">
          {run.duration_seconds != null && <>Took {run.duration_seconds.toFixed(0)} s in {run.ticks} pass{run.ticks === 1 ? "" : "es"} ({run.cpu_seconds.toFixed(0)} s of CPU, peak memory {run.peak_memory_mb} MB). </>}
          {run.file_kept ? "The uploaded file is still stored." : "The uploaded file was not kept."}
        </p>
      )}
    </div>
  );
}

export default function SapAssetMasterPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();
  const canImport = scopes.hasAll(SCOPE.settingsWrite, SCOPE.admin);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    setTitle("Settings — SAP asset master");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const runs = useQuery({
    queryKey: SAP_IMPORTS_KEY,
    queryFn: fetchRuns,
    staleTime: 0,
    // Poll while a run is reading; stop once nothing is.
    refetchInterval: (q) => (q.state.data ?? []).some(
      (r) => r.state === "queued" || r.state === "running") ? 3000 : false,
  });

  const upload = useMutation({
    mutationFn: async (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return (await apiUpload<SapImportRun>("/api/v1/sap-assets/imports", form)).data;
    },
    onSuccess: () => {
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      qc.invalidateQueries({ queryKey: SAP_IMPORTS_KEY });
      qc.invalidateQueries({ queryKey: ["reports", "sap-coverage"] });
    },
  });

  const err = (runs.error ?? upload.error) as CadraApiError | null;
  const list = runs.data ?? [];
  const busy = list.some((r) => r.state === "queued" || r.state === "running");

  return (
    <div className="p-6 space-y-5 max-w-[900px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
          <Database size={18} /> SAP asset master
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          A read-only copy of SAP's fixed-asset register, loaded from SAP's own
          export. It is not the asset register: nothing here appears in a list,
          count, report or export of assets. Cadra uses it to say which SAP
          record an item is, and how much of SAP's register Cadra
          holds (<Link href="/reports/sap-coverage" className="underline">SAP coverage</Link>).
        </p>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="sap-import-error">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} stacked />
        </div>
      )}

      <div className="glass-card rounded-2xl p-4 space-y-3">
        <p className="text-sm font-semibold text-foreground">Import an export</p>
        {canImport ? (
          <>
            <p className="text-[12px] text-muted-foreground">
              Upload the .XLSX as SAP produced it. Columns are found by their
              header; a missing one is refused before anything is read.
              Records are matched on asset number and sub-number; a record
              missing from the new export is marked, never deleted. The file
              is not kept once the import ends.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <input ref={fileRef} type="file" accept=".xlsx,.XLSX"
                     data-testid="sap-import-file"
                     onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                     className="text-[12px]" />
              <button type="button"
                      data-testid="sap-import-submit"
                      disabled={!file || upload.isPending || busy}
                      onClick={() => file && upload.mutate(file)}
                      className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-xl bg-primary text-primary-foreground disabled:opacity-50">
                {upload.isPending ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                Import
              </button>
            </div>
            {busy && (
              <p className="text-[11px] text-muted-foreground">An import is reading now; one runs at a time.</p>
            )}
            {upload.isSuccess && (
              <p className="text-[12px] text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5" data-testid="sap-import-queued">
                <Check size={13} /> Uploaded. The header is right; the rows are being read below.
              </p>
            )}
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground" data-testid="sap-import-not-allowed">
            Importing SAP's asset master is the system administrator's act.
            You can read the imports below.
          </p>
        )}
      </div>

      <div className="space-y-3">
        <p className="text-sm font-semibold text-foreground">Imports</p>
        {runs.isLoading && (
          <p className="text-[12px] text-muted-foreground flex items-center gap-2"><Clock size={13} className="animate-pulse" /> Loading the imports…</p>
        )}
        {!runs.isLoading && list.length === 0 && (
          <p className="text-[12px] text-muted-foreground" data-testid="sap-imports-empty">
            No export of SAP's asset master has been imported on this tenant.
          </p>
        )}
        {list.map((r) => <RunCard key={r.id} run={r} />)}
      </div>
    </div>
  );
}
