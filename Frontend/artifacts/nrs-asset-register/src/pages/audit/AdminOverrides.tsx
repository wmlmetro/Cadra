/**
 * Audit › Administrator overrides (handoff 70 §5) — a read-only view of
 * `GET /api/v1/reports/admin-overrides`: every act an administrator could
 * take only because the tenant's override lifted a two-person rule — a
 * receipt gate, a SAP link decision, a capture in a campaign that did not
 * name them, a review of their own capture or in a campaign that did not
 * name them a reviewer. An act that broke no rule (the administrator was
 * simply the first person at a gate) is not an override and is not listed;
 * that is the server's rule, not this page's.
 *
 * Newest first, the server's cursor 100 at a time, "Showing N of M" from its
 * own count. The period is two Lagos days, both inclusive — the server's
 * definition of a day. The CSV walks every page for the filters on screen,
 * so the file is the list, whole, not the part loaded.
 *
 * WHO MAY OPEN IT: whoever holds `settings:read`, what the server requires
 * — the Auditor, the Asset Manager and administrators.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { Download, Loader2, ShieldAlert } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import type { CadraApiError } from "@/lib/api";
import {
  ADMIN_OVERRIDE_KEY, ADMIN_OVERRIDES_REPORT_KEY, KIND_WORDS,
  adminOverridesCsv, fetchAdminOverride, fetchAdminOverrides, fetchAllAdminOverrides, lagosWhen, utcToLagosWhen,
  type AdminOverrideKind, type AdminOverrideRow, type AdminOverridesFilter, type AdminOverridesPage,
} from "@/lib/adminOverride";
import { lagosToday } from "@/lib/utils";
import { Btn, Empty, ErrorPanel, INPUT, Loading, PageHeader, Pill, n } from "./shared";

/** One page — the server's own default limit. */
const PAGE = 100;

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export default function AdminOverrides() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canRead = scopes.has(SCOPE.settingsRead);

  // No lower bound by default: the override is new, and the whole of its
  // history is the question. `until` is the LAGOS day, as the server's is.
  const [since, setSince] = useState("");
  const [until, setUntil] = useState(lagosToday);
  const [kind, setKind] = useState<"" | AdminOverrideKind>("");

  useEffect(() => {
    setTitle("Administrator overrides");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const validPeriod = (since === "" || DAY.test(since)) && (until === "" || DAY.test(until))
    && !(since && until && since > until);
  const filter: AdminOverridesFilter = useMemo(() => ({
    since: since || undefined, until: until || undefined, kind: kind || undefined,
  }), [since, until, kind]);

  // The switch, for the line at the top. Read by everybody who opens the
  // page; unreadable says nothing rather than guessing.
  const setting = useQuery({
    queryKey: ADMIN_OVERRIDE_KEY,
    queryFn: fetchAdminOverride,
    enabled: canRead,
    staleTime: 30_000,
    retry: false,
  });

  const report = useInfiniteQuery<AdminOverridesPage, CadraApiError>({
    queryKey: [...ADMIN_OVERRIDES_REPORT_KEY, filter],
    queryFn: ({ pageParam }) => fetchAdminOverrides(filter, pageParam as string | undefined, PAGE),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: canRead && validPeriod,
    staleTime: 30_000,
  });
  const rows = useMemo(() => (report.data?.pages ?? []).flatMap(p => p.rows), [report.data]);
  const total = report.data?.pages[0]?.totalEstimate ?? null;

  const download = useMutation<number, Error>({
    mutationFn: async () => {
      const all = await fetchAllAdminOverrides(filter);
      const url = URL.createObjectURL(new Blob([adminOverridesCsv(all)], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "admin-overrides.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1_000);
      return all.length;
    },
  });

  if (!canRead) return (
    <ScopeRefusal scope="settings:read" detail="The list of acts an administrator took alone under the override is read by the Auditor, the Asset Manager and system administrators." />
  );

  const s = setting.data;
  const remaining = total != null ? Math.max(total - rows.length, 0) : null;
  const nextN = remaining != null ? Math.min(PAGE, remaining) : PAGE;

  return (
    <div className="flex flex-col h-full" data-testid="admin-overrides-page">
      <PageHeader icon={<ShieldAlert size={15} />} title="Administrator overrides">
        Every act an administrator took alone because this tenant's override lifted a two-person rule: a receipt
        gate, a SAP link decision, an audit capture or review. What the rule would have said is on each row.
      </PageHeader>

      {s && (
        <p className="px-5 pt-3 text-[12px]" data-testid="admin-overrides-status-line" data-enabled={s.enabled ? "true" : "false"}>
          {s.enabled
            ? <span className="text-amber-800 dark:text-amber-300 font-semibold">On on this tenant since {utcToLagosWhen(s.since ?? s.changed_at)} (Lagos).</span>
            : <span className="text-muted-foreground">Off on this tenant; the list shows any acts from when it was on.</span>}
        </p>
      )}

      <div className="px-5 py-3 border-b border-border flex flex-wrap items-center gap-2.5">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          From
          <input type="date" value={since} max={until || undefined} onChange={e => setSince(e.target.value)}
                 className={INPUT} data-testid="input-overrides-since" />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          To
          <input type="date" value={until} min={since || undefined} onChange={e => setUntil(e.target.value)}
                 className={INPUT} data-testid="input-overrides-until" />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Kind
          <select value={kind} onChange={e => setKind(e.target.value as "" | AdminOverrideKind)}
                  className={INPUT} data-testid="input-overrides-kind">
            <option value="">All</option>
            <option value="gate">Receipt gates</option>
            <option value="audit">Audit</option>
          </select>
        </label>
        <span className="text-[11px] text-muted-foreground">Lagos days, both inclusive.</span>
        <div className="ml-auto flex items-center gap-2">
          {download.isSuccess && !download.isPending && (
            <span className="text-[11px] text-muted-foreground" data-testid="admin-overrides-downloaded">
              {n(download.data)} {download.data === 1 ? "row" : "rows"} in admin-overrides.csv.
            </span>
          )}
          <Btn kind="plain" testid="admin-overrides-download" pending={download.isPending}
               disabled={!validPeriod || report.isLoading} onClick={() => download.mutate()}>
            {!download.isPending && <Download size={12} />} Download CSV
          </Btn>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-5 py-3 space-y-3">
        {download.error && <ErrorPanel err={download.error as CadraApiError} testid="admin-overrides-download-error" />}
        {!validPeriod ? (
          <p className="text-xs text-red-700 dark:text-red-400" data-testid="period-invalid">
            The period ends before it starts, or a date is incomplete.
          </p>
        ) : report.isLoading ? (
          <Loading what="Reading the administrator overrides…" />
        ) : report.error ? (
          <ErrorPanel err={report.error} testid="admin-overrides-error" />
        ) : rows.length === 0 ? (
          <Empty testid="admin-overrides-empty">
            No administrator took an act alone under the override {since || until ? "in this period" : "on this tenant"}
            {kind ? ` (${kind === "gate" ? "receipt gates" : "audit"})` : ""}.
          </Empty>
        ) : (
          <>
            {total != null && (
              <p className="text-[11px] text-muted-foreground" data-testid="admin-overrides-count"
                 data-shown={rows.length} data-total={total}>
                Showing {n(rows.length)} of {n(total)}, newest first.
              </p>
            )}
            <table className="w-full min-w-[820px] text-xs" data-testid="admin-overrides-table">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground sticky top-0">
                <tr>
                  {["When (Lagos)", "Who", "Kind", "Act", "Asset or capture", "Rule lifted"].map(h => (
                    <th key={h} className="text-left font-semibold px-3 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => <OverrideRow key={`${r.at}-${r.kind}-${r.act}-${i}`} r={r} />)}
              </tbody>
            </table>
          </>
        )}
        {report.hasNextPage && (
          <div className="flex items-center gap-2">
            <Btn kind="plain" testid="button-overrides-next" pending={report.isFetchingNextPage}
                 onClick={() => report.fetchNextPage()}>Show the next {n(nextN)}</Btn>
            {remaining != null && <span className="text-[11px] text-muted-foreground">{n(remaining)} more after these.</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function OverrideRow({ r }: { r: AdminOverrideRow }) {
  return (
    <tr className="border-b border-border align-top" data-testid="admin-overrides-row" data-kind={r.kind} data-act={r.act}>
      <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground">{lagosWhen(r.at)}</td>
      <td className="px-3 py-2.5 text-foreground">{r.by?.name ?? "—"}</td>
      <td className="px-3 py-2.5"><Pill tone={r.kind === "gate" ? "blue" : "plain"}>{KIND_WORDS[r.kind] ?? r.kind}</Pill></td>
      <td className="px-3 py-2.5 text-foreground">{r.act_words || r.act}</td>
      <td className="px-3 py-2.5">
        {r.asset ? (
          <Link href={`/assets/${r.asset.id}`} className="font-semibold text-primary hover:underline">{r.asset.asset_code}</Link>
        ) : r.capture ? (
          <div className="space-y-0.5">
            <span className="font-mono">{r.capture.capture_id}</span>
            <div className="text-muted-foreground">{r.capture.campaign.name} · {r.capture.room.name}</div>
          </div>
        ) : "—"}
      </td>
      <td className="px-3 py-2.5 text-foreground max-w-sm">{r.override_of || "—"}</td>
    </tr>
  );
}
