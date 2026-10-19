/**
 * Reports — SAP coverage (handoff 63 §3): how much of SAP's register Cadra
 * holds, by class and by office.
 *
 * `GET /api/v1/reports/sap-coverage`, `sap_mirror:read`. Every count says
 * what it is a count of — the server sends a `definitions` sentence per
 * column and this page prints it under the table, word for word, rather
 * than inventing its own. A tenant whose mirror is empty is told that, not
 * shown a page of zeros as if Cadra held nothing.
 *
 * Handoff 65 §4: once assets are linked, each Cadra category carries
 * evidence — the SAP classes its linked assets actually have in SAP's
 * export. Shown per category, as the evidence for the proposed class
 * mapping NRS still has to confirm. Nothing here writes a category's SAP
 * class, and the page says so.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { apiGet, CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Clock, Scale } from "lucide-react";
import { cn } from "@/lib/utils";

interface ClassRow {
  class: string | null;
  sap_active: number;
  linked: number;
  linked_to_a_receipt_candidate: number;
  not_linked: number;
  sap_retired: number;
  cadra_assets: number;
  cadra_with_sap_number: number;
  cadra_sap_number_not_in_mirror: number;
  cadra_without_sap_number: number;
  held: string;
}
interface OfficeRow {
  office: string | null;
  sap_active: number;
  linked: number;
  not_linked: number;
  held: string;
}
/** One Cadra category's evidence (handoff 65 §4). */
interface ClassEvidenceRow {
  category: { id: number | null; name: string };
  configured_class: string | null;
  linked: number;
  via_link: number;
  sap_classes: { class: string | null; assets: number }[];
  /** null: the category has no SAP class configured to agree with. */
  agrees: boolean | null;
  sentence: string;
}

export interface SapCoverage {
  as_of: string;
  sentence: string;
  latest_import: { id: number; file_name: string; finished_at: string | null } | null;
  definitions: Record<string, string>;
  sap: { records_held: number; in_latest_export: number; not_in_latest_export: number; active_in_latest_export: number };
  totals: ClassRow;
  by_class: ClassRow[];
  by_office: OfficeRow[];
  reconcilable_today: {
    assets_without_sap_number: number;
    with_an_old_tag: number;
    by_unique_old_tag: number;
    by_unique_serial: number;
    total: number;
    sap_records: number;
    contested_sap_records: number;
    contested_assets: number;
    uncontested: number;
  };
  /** Absent on a server before handoff 65. */
  class_evidence?: ClassEvidenceRow[];
}

const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());

const CLASS_COLUMNS: [keyof ClassRow, string][] = [
  ["sap_active", "SAP active"],
  ["linked", "Linked"],
  ["not_linked", "Not linked"],
  ["held", "Held"],
  ["sap_retired", "SAP retired"],
  ["cadra_assets", "Cadra assets"],
  ["cadra_with_sap_number", "With SAP no."],
  ["cadra_sap_number_not_in_mirror", "SAP no. not in SAP"],
  ["cadra_without_sap_number", "No SAP no."],
];

export default function SapCoverageReport() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [office, setOffice] = useState("");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setTitle("Reports — SAP coverage");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const q = useQuery({
    queryKey: ["reports", "sap-coverage"],
    queryFn: async () => (await apiGet<SapCoverage>("/api/v1/reports/sap-coverage")).data,
    staleTime: 0,
  });

  const offices = useMemo(() => {
    const rows = q.data?.by_office ?? [];
    const term = office.trim().toUpperCase();
    return term ? rows.filter((r) => (r.office ?? "no office").toUpperCase().includes(term)) : rows;
  }, [q.data, office]);

  if (q.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Counting SAP's register against Cadra's…</p>
    </div>
  );
  if (q.error) return (
    <div className="p-6 max-w-[900px] mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <ApiErrorMessage err={q.error as CadraApiError} stacked />
      </div>
    </div>
  );
  const d = q.data!;
  const r = d.reconcilable_today;
  const shown = showAll ? offices : offices.slice(0, 50);

  return (
    <div className="p-6 space-y-5 max-w-[1200px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground flex items-center gap-2"><Scale size={18} /> SAP coverage</h1>
        <p className="text-xs text-muted-foreground mt-1">
          How much of SAP's asset register Cadra holds. SAP's side is the
          latest import of SAP's export
          {d.latest_import ? <> (import {d.latest_import.id}, {d.latest_import.file_name})</> : null}
          ; <Link href="/settings/sap-asset-master" className="underline">SAP asset master</Link> holds the imports.
        </p>
      </div>

      <p className="glass-card rounded-2xl p-4 text-sm text-foreground" data-testid="sap-coverage-sentence">{d.sentence}</p>

      {d.sap.records_held > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="glass-card rounded-2xl p-4"><p className="text-[11px] text-muted-foreground">SAP's active assets</p><p className="text-xl font-bold" data-testid="cov-sap-active">{n(d.totals.sap_active)}</p></div>
            <div className="glass-card rounded-2xl p-4"><p className="text-[11px] text-muted-foreground">Of those, linked to a Cadra asset</p><p className="text-xl font-bold" data-testid="cov-linked">{n(d.totals.linked)}</p><p className="text-[11px] text-muted-foreground">{d.totals.held}</p></div>
            <div className="glass-card rounded-2xl p-4"><p className="text-[11px] text-muted-foreground">Cadra assets with no SAP number</p><p className="text-xl font-bold">{n(d.totals.cadra_without_sap_number)}</p><p className="text-[11px] text-muted-foreground">of {n(d.totals.cadra_assets)} on the register</p></div>
            <div className="glass-card rounded-2xl p-4"><p className="text-[11px] text-muted-foreground">Could be linked with confidence today</p><p className="text-xl font-bold" data-testid="cov-uncontested">{n(r.uncontested)}</p><p className="text-[11px] text-muted-foreground">of {n(r.assets_without_sap_number)} with no SAP number</p></div>
          </div>

          <div className="glass-card rounded-2xl p-4 overflow-x-auto">
            <p className="text-sm font-semibold mb-2">By SAP class</p>
            <table className="w-full text-[12px]" data-testid="cov-by-class">
              <thead><tr className="text-left text-muted-foreground">
                <th className="py-1 pr-3">Class</th>
                {CLASS_COLUMNS.map(([k, l]) => <th key={k} className="py-1 pr-3 text-right">{l}</th>)}
              </tr></thead>
              <tbody>
                {d.by_class.map((row) => (
                  <tr key={row.class ?? "none"} className="border-t border-border/50">
                    <td className="py-1 pr-3 font-medium">{row.class ?? "no SAP class"}</td>
                    {CLASS_COLUMNS.map(([k]) => <td key={k} className="py-1 pr-3 text-right">{typeof row[k] === "number" ? n(row[k] as number) : String(row[k])}</td>)}
                  </tr>
                ))}
                <tr className="border-t-2 border-border font-semibold">
                  <td className="py-1 pr-3">All</td>
                  {CLASS_COLUMNS.map(([k]) => <td key={k} className="py-1 pr-3 text-right">{typeof d.totals[k] === "number" ? n(d.totals[k] as number) : String(d.totals[k])}</td>)}
                </tr>
              </tbody>
            </table>
          </div>

          <div className="glass-card rounded-2xl p-4 overflow-x-auto">
            <div className="flex items-center justify-between gap-3 mb-2">
              <p className="text-sm font-semibold">By office — {n(d.by_office.length)} offices</p>
              <input value={office} onChange={(e) => setOffice(e.target.value)} placeholder="Office code"
                     className="text-[12px] border border-border rounded-lg px-2 py-1 bg-background" />
            </div>
            <table className="w-full text-[12px]" data-testid="cov-by-office">
              <thead><tr className="text-left text-muted-foreground">
                <th className="py-1 pr-3">Office</th><th className="py-1 pr-3 text-right">SAP active</th>
                <th className="py-1 pr-3 text-right">Linked</th><th className="py-1 pr-3 text-right">Not linked</th>
                <th className="py-1 pr-3 text-right">Held</th>
              </tr></thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.office ?? "none"} className="border-t border-border/50">
                    <td className="py-1 pr-3 font-medium">{row.office ?? "no office"}</td>
                    <td className="py-1 pr-3 text-right">{n(row.sap_active)}</td>
                    <td className="py-1 pr-3 text-right">{n(row.linked)}</td>
                    <td className="py-1 pr-3 text-right">{n(row.not_linked)}</td>
                    <td className="py-1 pr-3 text-right">{row.held}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {offices.length > shown.length && (
              <button type="button" onClick={() => setShowAll(true)} className="mt-2 text-[12px] underline">
                Show all {n(offices.length)}
              </button>
            )}
          </div>

          <div className="glass-card rounded-2xl p-4 text-[12px] space-y-1" data-testid="cov-reconcilable">
            <p className="text-sm font-semibold">What could be linked today</p>
            <p>
              Of {n(r.assets_without_sap_number)} Cadra assets with no SAP number ({n(r.with_an_old_tag)} carrying an old tag),
              the matcher ranks {n(r.total)} first — {n(r.by_unique_old_tag)} by a unique old tag, {n(r.by_unique_serial)} by a unique serial —
              onto {n(r.sap_records)} SAP records. {n(r.contested_assets)} of them point at a SAP record another Cadra asset also points at
              ({n(r.contested_sap_records)} records), which leaves {n(r.uncontested)} that could be linked with confidence.
            </p>
          </div>
        </>
      )}

      {d.class_evidence && (
        <div className="glass-card rounded-2xl p-4 overflow-x-auto space-y-2" data-testid="cov-class-evidence">
          <p className="text-sm font-semibold">What the links say about the class mapping</p>
          <p className="text-[12px] text-muted-foreground">
            For each Cadra category, the SAP classes its linked assets carry in SAP's own export. This is
            evidence for the proposed mapping, which NRS confirms. <span className="font-semibold text-foreground">Nothing
            here changes a category's SAP class</span> — that is set on the categories screen.
          </p>
          {d.class_evidence.length === 0 ? (
            <p className="text-[12px] text-muted-foreground" data-testid="cov-class-evidence-empty">
              No register asset carries a SAP number that names a record in the mirror yet, so there is no evidence to show.
            </p>
          ) : (
            <table className="w-full text-[12px]">
              <thead><tr className="text-left text-muted-foreground">
                <th className="py-1 pr-3">Category</th>
                <th className="py-1 pr-3">Configured class</th>
                <th className="py-1 pr-3 text-right">Linked</th>
                <th className="py-1 pr-3 text-right">Via Link to SAP</th>
                <th className="py-1 pr-3">SAP classes (most first)</th>
              </tr></thead>
              <tbody>
                {d.class_evidence.map((row) => (
                  <tr key={row.category.id ?? "none"}
                      className={cn("border-t border-border/50 align-top", row.agrees === false && "bg-amber-50/60 dark:bg-amber-950/20")}
                      data-testid="cov-class-evidence-row" data-agrees={row.agrees === null ? "none" : String(row.agrees)}>
                    <td className="py-1 pr-3 font-medium">{row.category.name}</td>
                    <td className="py-1 pr-3 font-mono">{row.configured_class ?? <span className="font-sans text-muted-foreground">none</span>}</td>
                    <td className="py-1 pr-3 text-right">{n(row.linked)}</td>
                    <td className="py-1 pr-3 text-right">{n(row.via_link)}</td>
                    <td className="py-1 pr-3">
                      <span className="font-mono">
                        {row.sap_classes.map((c) => `${c.class ?? "(none)"}: ${n(c.assets)}`).join(" · ")}
                      </span>
                      {row.agrees === false && (
                        <span className="ml-2 text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40">
                          differs from configured
                        </span>
                      )}
                      <span className="block text-[11px] text-muted-foreground">{row.sentence}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {d.definitions.class_evidence && (
            <p className="text-[11px] text-muted-foreground">{d.definitions.class_evidence}</p>
          )}
        </div>
      )}

      <div className="text-[11px] text-muted-foreground space-y-1" data-testid="cov-definitions">
        <p className="font-semibold">What each count counts</p>
        {Object.entries(d.definitions).map(([k, v]) => (
          <p key={k}><span className="font-mono">{k}</span> — {v}</p>
        ))}
      </div>
    </div>
  );
}
