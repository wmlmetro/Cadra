/**
 * Access changes — a read-only view of `GET /api/v1/reports/access-changes`
 * (handoff 23, the forward record from handoff 24), opened under
 * Administration by handoff 41. Nothing on this page changes anything; the
 * only inputs are the two period dates and the user filter chip.
 *
 * HOW THE PAGES ARE WALKED
 * ------------------------
 * The report pages by ascending ACCOUNT ID — `events` and `roster` on a page
 * describe the same window of accounts, and `summary`/`fidelity` describe
 * the whole period on every page. A person filtered by `?user_id=` can
 * therefore sit on any page, so this screen auto-walks every page of the
 * period (the same stream Locations uses) and only then filters events in
 * the browser. The counter says how far the walk has got so a reader never
 * takes a half-walked table for the whole period.
 *
 * WHAT THE REPORT SAYS ABOUT ITSELF
 * ---------------------------------
 * `summary.statement` and `summary.coverage` are rendered ABOVE the table
 * on purpose: the model's own docstring says to read the statement before
 * the events, because on a tenant whose record has not begun an empty
 * table and "nothing happened" are different facts and only the statement
 * tells them apart.
 *
 * WHO MAY OPEN IT
 * ---------------
 * Since handoff 46, whoever holds `identity:read` — what the server route
 * requires — not `admin`. Reading the access record is the Auditor's job, and
 * the Auditor is not a system administrator: the screen refused the one role
 * it is for while the API answered that role 200. Two things on the page are
 * still administrators' only, because their routes are `admin`: the name in
 * the user filter chip (`GET /users/<id>`) and the link from a row to the
 * Users page. Without `admin` the chip shows the id and the row the login.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes } from "@/hooks/use-scopes";
import { fetchAccessChanges, fetchUser, type AccessChangesPage } from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { formatIsoDateTime } from "@/lib/utils";
import type { AccessChangeEvent, AdminUser } from "@/types";
import { AlertCircle, Clock, History, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScopeRefusal } from "@/components/ScopeRefusal";

/** The events the model emits (`access_change_report` in `audit_access.py`
 *  and the `event` selection in `access_change.py`), in words. Anything else
 *  prints as-is. */
const EVENT_WORDS: Record<string, string> = {
  account_created:  "Account created",
  account_modified: "Account modified",
  granted:          "Role granted",
  removed:          "Role removed",
  implied_added:    "Implication added",
  implied_removed:  "Implication removed",
  deactivated:      "Account deactivated",
  reactivated:      "Account reactivated",
};
const eventWords = (e: string) => EVENT_WORDS[e] ?? e;

/** `__system__` is `SYSTEM_ACTOR` in `access_change.py:134`; the model also
 *  marks such rows `attributable: false`. Either reads as "system". */
function actorWords(e: AccessChangeEvent): string {
  if (e.attributable === false) return "system";
  if (!e.actor) return "—";
  if (e.actor.name === "__system__") return "system";
  return e.actor.name;
}

/** Where the evidence came from, from the `evidence` string the model
 *  writes: a `res_users.*` column or a row of the append-only record. */
function sourceWords(e: AccessChangeEvent): string {
  if (e.evidence.startsWith("myservice_api_access_change")) return "Access record";
  if (e.evidence.startsWith("res_users")) return e.precision === "last_write_only" ? "User record (last write only)" : "User record";
  return e.evidence;
}

const todayIso = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

export default function AdminAccessChanges() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const [path, nav] = useLocation();
  const searchStr = useSearch();

  // The forward record began in September 2026 (handoff 24); the default
  // window opens on the first of that year so a tenant's whole record is in
  // view without anybody typing a date.
  const [from, setFrom] = useState("2026-01-01");
  const [to, setTo] = useState(todayIso);

  useEffect(() => {
    setTitle("Access changes");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // The user filter lives in the URL — the Users page links here with it.
  const userId = useMemo(() => {
    const raw = new URLSearchParams(searchStr).get("user_id");
    const n = raw ? Number(raw) : NaN;
    return Number.isInteger(n) && n > 0 ? n : null;
  }, [searchStr]);
  const clearUser = () => nav(path, { replace: true });

  const userQuery = useQuery<AdminUser, CadraApiError>({
    queryKey: ["user", userId],
    queryFn: () => fetchUser(userId as number),
    // `GET /users/<id>` is `admin`; anybody else would get a 403 drawn as
    // "(not found)".
    enabled: scopes.isAdmin && userId != null,
    staleTime: 30_000,
  });

  const validPeriod = /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to;

  const report = useInfiniteQuery<AccessChangesPage, CadraApiError>({
    queryKey: ["access-changes", from, to],
    queryFn: ({ pageParam }) => fetchAccessChanges(from, to, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: scopes.has("identity:read") && validPeriod,
    staleTime: 30_000,
  });
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = report;
  const pagesLoaded = report.data?.pages.length ?? 0;

  // Auto-walk: every page, in order, until the cursor runs out.
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, pagesLoaded]);

  const first = report.data?.pages[0]?.report ?? null;
  const allEvents = useMemo(
    () => (report.data?.pages ?? []).flatMap(p => p.report.events),
    [report.data],
  );
  const accountsSeen = useMemo(
    () => (report.data?.pages ?? []).reduce((n, p) => n + p.report.roster.length, 0),
    [report.data],
  );
  const totalAccounts = report.data?.pages[0]?.totalEstimate ?? first?.summary.accounts ?? null;

  // Newest first for reading; the API's order is by account id for paging.
  const events = useMemo(() => {
    const rows = userId == null ? allEvents : allEvents.filter(e => e.user_id === userId);
    return [...rows].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  }, [allEvents, userId]);

  if (!scopes.has("identity:read")) return (
    <ScopeRefusal scope="identity:read" detail="The access record is read by the roles that read the staff roster — the Auditor among them." />
  );

  const walking = hasNextPage || isFetchingNextPage;
  const error = report.error;

  return (
    <div className="flex flex-col h-full" data-testid="admin-access-changes-page">
      {/* Period + user filter */}
      <div className="px-4 sm:px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          From
          <input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} data-testid="input-period-from"
            className="px-2 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          To
          <input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} data-testid="input-period-to"
            className="px-2 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </label>
        {userId != null && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs font-medium bg-primary/10 border border-primary/20 text-primary" data-testid="user-filter-chip" data-user-id={userId}>
            User:&nbsp;
            {userQuery.data
              ? <><span className="font-semibold">{userQuery.data.name}</span><span className="font-mono opacity-80" data-testid="user-filter-login">{userQuery.data.login}</span></>
              : userQuery.error ? <span className="font-mono">#{userId} (not found)</span>
              : <span className="font-mono">#{userId}</span>}
            <button onClick={clearUser} className="ml-1 inline-flex items-center gap-0.5 hover:opacity-80" title="All users" data-testid="button-clear-user">
              <X size={11} /> All users
            </button>
          </span>
        )}
        <p className="ml-auto text-xs text-muted-foreground inline-flex items-center gap-1.5" data-testid="events-count">
          <span className="font-bold text-foreground">{events.length.toLocaleString()}</span> events
          {userId != null && allEvents.length !== events.length && <> of {allEvents.length.toLocaleString()} in the period</>}
          {walking && totalAccounts != null && (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/70" data-testid="walk-progress">
              <Clock size={9} className="animate-pulse" /> reading {accountsSeen.toLocaleString()}/{totalAccounts.toLocaleString()} accounts…
            </span>
          )}
        </p>
      </div>

      <div className="flex-1 overflow-auto">
        {!validPeriod ? (
          <p className="p-6 text-xs text-red-700 dark:text-red-400" data-testid="period-invalid">The period ends before it starts, or a date is incomplete.</p>
        ) : report.isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
            <Clock size={20} className="animate-pulse" />
            <p className="text-sm">Reading the access record…</p>
          </div>
        ) : error ? (
          <div className="p-6 max-w-xl">
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="access-changes-error">
              <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <ApiErrorMessage err={error} stacked />
                {!apiConfigured && <p className="text-[11px] mt-1">No active session.</p>}
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* The report's own statement about what it can and cannot say */}
            {first && (
              <div className="px-4 sm:px-5 pt-4 pb-3 space-y-2" data-testid="report-summary">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span>
                    Coverage: <span className={cn("font-semibold uppercase", first.summary.coverage === "none" ? "text-red-600 dark:text-red-400" : "text-foreground")} data-testid="report-coverage">{first.summary.coverage}</span>
                  </span>
                  <span>·</span>
                  <span>{first.summary.accounts.toLocaleString()} accounts, {first.summary.accounts_active.toLocaleString()} active</span>
                  <span>·</span>
                  <span>{first.summary.events_in_period.toLocaleString()} events in the period</span>
                  <span>·</span>
                  <span>{first.summary.group_changes_in_period.toLocaleString()} role changes recorded
                    {first.summary.group_changes_not_shown > 0 && <> ({first.summary.group_changes_not_shown} for accounts no longer on the roster, not shown)</>}
                  </span>
                  {first.summary.account_state_changes_in_period != null && (
                    <>
                      <span>·</span>
                      <span data-testid="report-account-state">
                        {first.summary.account_state_changes_in_period.toLocaleString()} deactivations / reactivations recorded
                        {first.summary.account_state_changes_not_shown > 0 && <> ({first.summary.account_state_changes_not_shown} for accounts no longer on the roster, not shown)</>}
                        {first.summary.account_state_coverage && first.summary.account_state_coverage !== first.summary.coverage && (
                          <> (coverage: <span className={cn("font-semibold uppercase", first.summary.account_state_coverage === "none" ? "text-red-600 dark:text-red-400" : "text-foreground")} data-testid="report-account-state-coverage">{first.summary.account_state_coverage}</span>)</>
                        )}
                      </span>
                    </>
                  )}
                  {first.fidelity.record_starts_at
                    ? <><span>·</span><span>record begins {formatIsoDateTime(first.fidelity.record_starts_at)}</span></>
                    : <><span>·</span><span>the record has not begun on this tenant</span></>}
                </div>
                <p className="text-[12px] text-foreground/90" data-testid="report-statement">{first.summary.statement}</p>
                {first.fidelity.notes?.record_start && (
                  <p className="text-[11px] text-muted-foreground" data-testid="report-fidelity-note">{first.fidelity.notes.record_start}</p>
                )}
                {first.fidelity.notes?.account_state && (
                  <p className="text-[11px] text-muted-foreground" data-testid="report-fidelity-account-state-note">{first.fidelity.notes.account_state}</p>
                )}
              </div>
            )}

            <table className="w-full min-w-[640px]" data-testid="events-table">
              <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                <tr>
                  {["When", "Event", "User", "Group", "By whom", "Source"].map(h => (
                    <th key={h} className="text-left px-3 sm:px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {events.map((e, i) => (
                  <tr key={`${e.evidence}-${e.at}-${i}`} data-testid="event-row" data-event={e.event} data-login={e.login} data-user-id={e.user_id} className="border-b border-border/50">
                    <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground whitespace-nowrap">{formatIsoDateTime(e.at)}</td>
                    <td className="px-3 sm:px-4 py-2.5">
                      <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-lg border",
                        e.event === "granted" || e.event === "reactivated" ? "bg-green-50 border-green-200/60 text-green-700 dark:bg-green-950/30 dark:border-green-800/30 dark:text-green-400"
                        : e.event === "removed" || e.event === "deactivated" ? "bg-red-50 border-red-200/60 text-red-700 dark:bg-red-950/30 dark:border-red-800/30 dark:text-red-400"
                        : "bg-muted border-border text-muted-foreground")}>
                        {eventWords(e.event)}
                      </span>
                    </td>
                    <td className="px-3 sm:px-4 py-2.5 text-[12px] font-mono text-foreground">
                      {scopes.isAdmin
                        ? <Link href={`/admin/users/${e.user_id}`} className="hover:text-primary" data-testid="event-user-link">{e.login}</Link>
                        : <span data-testid="event-user-login">{e.login}</span>}
                    </td>
                    <td className="px-3 sm:px-4 py-2.5 text-[12px] text-foreground" data-testid="event-group">{e.group ?? <span className="text-muted-foreground">{e.event === "deactivated" || e.event === "reactivated" ? "whole account" : "—"}</span>}</td>
                    <td className="px-3 sm:px-4 py-2.5 text-[12px] text-foreground" data-testid="event-actor">{actorWords(e)}</td>
                    <td className="px-3 sm:px-4 py-2.5 text-[11px] text-muted-foreground" title={e.evidence}>{sourceWords(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.length === 0 && !walking && (
              <div className="flex flex-col items-center justify-center py-16 gap-2" data-testid="events-empty">
                <History size={24} className="text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                  {userId != null ? "No access events for this person in the period." : "No access events in the period."}
                </p>
                <p className="text-[11px] text-muted-foreground max-w-md text-center">Read the statement above before concluding nothing happened — an empty table and a record that has not begun are different facts.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
