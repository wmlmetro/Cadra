/**
 * Export — the whole register as a file (handoff 49 §3). A download, not a
 * table, and the handoff's words set the bar: "a silent click that may or
 * may not have worked is the worst outcome available here."
 *
 * WHAT THE BUTTON DOES
 * --------------------
 * One click fetches `GET /api/v1/assets/export.csv` with the session's
 * bearer token (a plain link cannot carry one — `lib/api.ts#apiGetRaw`) and
 * hands the browser the file the server names in `Content-Disposition`:
 * `nrs_assets.csv`, one row per asset, twelve columns (code, name, category,
 * condition, state, location, holder, IR number, department, assignment
 * date, retrieval flag, serial number). The JSON twin
 * (`GET /assets/export`) stays API-only: the CSV is the route built to be a
 * file — it alone carries a filename and the `X-Cadra-Truncated` header.
 *
 * WHAT THE PERSON SEES
 * --------------------
 * The register's size beside the button BEFORE clicking, a "Preparing…"
 * state while the server builds the body (it is not streamed — one response,
 * measured at seconds on an 11,951-asset tenant), and afterwards the row
 * count, size and elapsed time of what was saved — or the refusal, in words.
 * If the server truncated the export (an uncapped frontend session should
 * never see this; an API credential's cap is 100), the banner says cap and
 * total, because a file quietly missing most of the register is worse than
 * no file.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { fetchRegisterTotal } from "@/lib/dataProvider";
import { apiGetRaw, CadraApiError } from "@/lib/api";
import { AlertCircle, Clock, Download, FileCheck2 } from "lucide-react";
import { ScopeRefusal } from "@/components/ScopeRefusal";

const COLUMNS = [
  "Asset Code", "Name", "Category", "Condition", "State", "Location",
  "Assigned To", "IR Number", "Department", "Assignment Date",
  "Retrieval Flag", "Serial Number",
];

type DownloadState =
  | { phase: "idle" }
  | { phase: "preparing" }
  | { phase: "done"; filename: string; rows: number; bytes: number; ms: number; truncated: string | null }
  | { phase: "failed"; error: CadraApiError | Error };

const fmtBytes = (n: number) =>
  n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(0)} KB` : `${n} B`;

export default function ExportRegister() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const [state, setState] = useState<DownloadState>({ phase: "idle" });
  // Revoked on the next download or unmount, not immediately — Safari aborts
  // a click-through whose URL is already revoked.
  const objectUrl = useRef<string | null>(null);

  useEffect(() => {
    setTitle("Export");
    setSearchHandler(undefined);
    return () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); };
  }, [setTitle, setSearchHandler]);

  const total = useQuery<number | null, CadraApiError>({
    queryKey: ["register-total"],
    queryFn: fetchRegisterTotal,
    enabled: scopes.has(SCOPE.assetsRead),
    staleTime: 60_000,
  });

  if (!scopes.has(SCOPE.assetsRead)) return (
    <ScopeRefusal scope="assets:read" detail="The export is the register, every asset of it, as a file." />
  );

  const download = async () => {
    setState({ phase: "preparing" });
    const started = performance.now();
    try {
      const res = await apiGetRaw("/api/v1/assets/export.csv");
      const text = await res.text();
      const ms = Math.round(performance.now() - started);

      // `attachment; filename=nrs_assets.csv` — fall back to the known name
      // rather than to nothing.
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "nrs_assets.csv";
      const truncated = res.headers.get("X-Cadra-Truncated");

      // Data rows: lines minus the header, minus any trailing newline and
      // minus the truncation trailer a cut file ends with. The server writes
      // that trailer through csv.writer and the sentence contains commas, so
      // on the wire it is a QUOTED field — `"# TRUNCATED…` — not a bare `#`.
      const lines = text.split("\n").filter(l =>
        l.trim() !== "" && !l.startsWith("#") && !l.startsWith('"#'));
      const rows = Math.max(0, lines.length - 1);

      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
      objectUrl.current = url;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();

      setState({ phase: "done", filename, rows, bytes: text.length, ms, truncated });
    } catch (e) {
      setState({ phase: "failed", error: e instanceof Error ? e : new Error(String(e)) });
    }
  };

  return (
    <div className="flex flex-col h-full" data-testid="export-register-page">
      <div className="flex-1 overflow-auto p-4 sm:p-6">
        <div className="max-w-xl space-y-4">
          <div className="rounded-2xl border border-border bg-card p-5 space-y-3">
            <p className="text-[13px] text-foreground/90">
              Download the whole register as <span className="font-mono font-semibold">nrs_assets.csv</span> — one
              row per asset, {COLUMNS.length} columns, every state included (missing and disposed assets are rows
              like any other; an export that dropped them would hide exactly what an auditor is looking for).
            </p>
            <p className="text-[11px] text-muted-foreground">{COLUMNS.join(" · ")}</p>
            <p className="text-[12px] text-muted-foreground" data-testid="export-size">
              {total.isLoading ? "Counting the register…"
                : total.data != null ? <>This register holds <span className="font-bold text-foreground">{total.data.toLocaleString()}</span> assets right now.</>
                : "The register's size could not be read; the export will still carry everything."}
            </p>

            <button onClick={download} disabled={state.phase === "preparing"} data-testid="button-download-csv"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
              {state.phase === "preparing"
                ? <><Clock size={14} className="animate-pulse" /> Preparing the export…</>
                : <><Download size={14} /> Download CSV</>}
            </button>
            {state.phase === "preparing" && (
              <p className="text-[11px] text-muted-foreground" data-testid="export-preparing">
                The server is building the file in one piece — on a large register this takes a few seconds. The
                download starts by itself when it is ready.
              </p>
            )}
          </div>

          {state.phase === "done" && (
            <div className="rounded-2xl border border-green-200/60 dark:border-green-800/30 bg-green-50 dark:bg-green-950/30 p-4 flex items-start gap-3" data-testid="export-done">
              <FileCheck2 size={16} className="text-green-700 dark:text-green-400 shrink-0 mt-0.5" />
              <div className="text-[12px] text-green-800 dark:text-green-300">
                <p>
                  Saved <span className="font-mono font-semibold">{state.filename}</span> —{" "}
                  <span className="font-bold" data-testid="export-rows">{state.rows.toLocaleString()}</span> rows,{" "}
                  {fmtBytes(state.bytes)}, in {(state.ms / 1000).toFixed(1)}s.
                </p>
                {state.truncated && (
                  <p className="mt-1 text-amber-700 dark:text-amber-400" data-testid="export-truncated">
                    The server CUT this file: {state.truncated.replace("/", " of ")} rows. The missing rows are not
                    in the file — this session's credential is capped.
                  </p>
                )}
              </div>
            </div>
          )}

          {state.phase === "failed" && (
            <div className="rounded-2xl border border-red-200/70 dark:border-red-800/30 bg-red-50 dark:bg-red-950/30 p-4 flex items-start gap-3" data-testid="export-error">
              <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div className="text-[12px]">
                {state.error instanceof CadraApiError
                  ? <ApiErrorMessage err={state.error} stacked />
                  : <p>{state.error.message}</p>}
                <p className="text-[11px] mt-1 text-muted-foreground">Nothing was saved.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
