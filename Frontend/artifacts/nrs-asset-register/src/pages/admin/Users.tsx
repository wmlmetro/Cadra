/**
 * Users — who has what (handoff 41). READ ONLY, END TO END.
 *
 * Every control that would change something is ABSENT, not disabled. There
 * is no create, edit, remove, deactivate, invite, grant, revoke or reset here
 * and nothing greyed out standing in for one; the only inputs on the page
 * are the search box and the three filters. The mechanism is handoff 42,
 * deliberately separate, because an endpoint that writes `group_ids` is the
 * most dangerous surface this API could grow.
 *
 * THE ONE DISTINCTION THIS SCREEN MUST NOT BLUR
 * ---------------------------------------------
 * On Odoo 19 group implication is computed at read time and materialises no
 * rows, so "the roles somebody granted this person" and "the roles this
 * person effectively has" are different questions with different answers:
 * Asset Manager implies Asset User. The API publishes both, named so nobody
 * can confuse them, and this screen LEADS WITH THE DIRECT ONES — they are
 * what somebody actually did and what handoff 42 will act on — and draws an
 * implied role after them in a visibly lighter pill that says so in its
 * title. The role FILTER, by contrast, is on effective membership ("Can act
 * as"), because the question a filter answers is who can do a thing, and
 * the hint under the table says that is what it includes.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useRoute } from "wouter";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes } from "@/hooks/use-scopes";
import {
  fetchRoles, fetchUser, fetchUsersPage, type UserFilters, type UsersPage,
} from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { formatIsoDateTime } from "@/lib/utils";
import type { AdminRole, AdminUser } from "@/types";
import {
  AlertCircle, ChevronDown, Clock, History, KeyRound, Search, ShieldCheck, User as UserIcon, X,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── SCOPES IN PLAIN WORDS ────────────────────────────────────────────────────
/** The sixteen scopes `myservice_api/controllers/utils.py` knows, in words a
 *  person can read. An unknown scope prints as-is rather than being hidden —
 *  a scope this map has not heard of is still something the account can do. */
export const SCOPE_WORDS: Record<string, string> = {
  "assets:read":        "Read assets",
  "assets:write":       "Create and edit assets",
  "locations:read":     "Read locations",
  "locations:write":    "Create and edit locations",
  "requests:read":      "Read requests",
  "requests:write":     "Raise requests",
  "approvals:write":    "Approve and reject requests",
  "ingestion:write":    "Receive assets from Vendra (INT-03)",
  "integrations:write": "Run imports and integrations",
  "webhooks:admin":     "Manage webhooks",
  "dashboards:read":    "View dashboards",
  "identity:read":      "Read the staff roster",
  "tagging:write":      "Confirm a label is affixed",
  "settings:write":     "Change settings",
  "settings:read":      "Read the configuration log",
  "admin":              "Everything — system administrator",
};

export function scopeWords(scope: string): string {
  return SCOPE_WORDS[scope] ?? scope;
}

// ─── PILLS ────────────────────────────────────────────────────────────────────
const pillBase = "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-semibold border whitespace-nowrap";

function RolePill({ name, implied, via }: { name: string; implied?: boolean; via?: string[] }) {
  // `via` names the direct group(s) that imply this role — which may be a
  // group outside the role vocabulary (the administrator's Security Officer
  // comes through Security Administrator). The pill says so rather than leaving
  // a role on the row that nothing on the row explains.
  const viaText = via && via.length ? `via ${via.join(", ")}` : "via implication";
  return (
    <span
      data-testid={implied ? "role-pill-implied" : "role-pill-direct"}
      data-role={name}
      data-via={implied && via ? via.join("|") : undefined}
      title={implied ? `${name} — ${viaText}` : name}
      className={cn(
        pillBase,
        implied
          ? "bg-transparent border-dashed border-border text-muted-foreground/80 font-medium"
          : "bg-primary/10 border-primary/20 text-primary",
      )}
    >
      {name}{implied && <span className="ml-1 opacity-70 font-normal">· implied</span>}
    </span>
  );
}

function KindPill({ u }: { u: AdminUser }) {
  if (u.kind !== "api_credential") return <span className="text-[11px] text-muted-foreground">Person</span>;
  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      <span data-testid="kind-pill-api" className={cn(pillBase, "bg-amber-50 border-amber-200/70 text-amber-700 dark:bg-amber-950/30 dark:border-amber-800/30 dark:text-amber-400")}>
        <KeyRound size={9} className="mr-1" />API credential
      </span>
      {u.api_client?.is_test_credential && (
        <span data-testid="kind-pill-test" className={cn(pillBase, "bg-muted border-border text-muted-foreground")}>test credential</span>
      )}
    </span>
  );
}

function ActivePill({ active }: { active: boolean }) {
  return (
    <span
      data-testid={active ? "active-pill" : "inactive-pill"}
      className={cn(pillBase, active
        ? "bg-green-50 border-green-200/60 text-green-700 dark:bg-green-950/30 dark:border-green-800/30 dark:text-green-400"
        : "bg-muted border-border text-muted-foreground")}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full mr-1", active ? "bg-green-500" : "bg-gray-400")} />
      {active ? "Active" : "Inactive"}
    </span>
  );
}

/** Direct roles first, then anything effective-but-not-direct, lighter. */
function splitRoles(u: AdminUser) {
  const direct = new Set(u.roles_direct.map(r => r.key));
  const implied = u.roles_effective.filter(r => !direct.has(r.key));
  return { direct: u.roles_direct, implied };
}

// ─── FILTER BUTTON ────────────────────────────────────────────────────────────
function FilterBtn({ label, value, options, onChange, testId }: {
  label: string; value: string; options: { value: string; label: string }[];
  onChange: (v: string) => void; testId: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find(o => o.value === value);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        data-testid={testId}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-all",
          value ? "bg-primary text-white border-primary shadow-sm" : "border-border text-muted-foreground hover:text-foreground bg-card")}
      >
        {current ? `${label}: ${current.label}` : label}
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && <>
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
        <div role="listbox" className="absolute top-full mt-1.5 left-0 z-50 bg-popover border border-border rounded-xl shadow-lg overflow-hidden min-w-[180px] py-1">
          <button role="option" aria-selected={!value} className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", !value && "font-semibold")} onClick={() => { onChange(""); setOpen(false); }}>All</button>
          {options.map(o => (
            <button key={o.value} role="option" aria-selected={value === o.value} data-testid={`${testId}-option`} data-value={o.value}
              className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent", value === o.value ? "font-semibold text-primary" : "text-muted-foreground")}
              onClick={() => { onChange(o.value); setOpen(false); }}>
              {o.label}
            </button>
          ))}
        </div>
      </>}
    </div>
  );
}

// ─── DETAIL PANEL ─────────────────────────────────────────────────────────────
function Section({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <section data-testid={testId} className="bg-card border border-border rounded-xl p-4">
      <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">{title}</h3>
      {children}
    </section>
  );
}

function DetailPanel({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const { direct, implied } = splitRoles(user);
  const isCredential = user.kind === "api_credential";
  return (
    <div className="space-y-3" data-testid="user-detail" data-user-id={user.id} data-login={user.login}>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center border shrink-0 bg-muted border-border">
          {isCredential ? <KeyRound size={18} className="text-amber-600 dark:text-amber-400" /> : <UserIcon size={18} className="text-muted-foreground" />}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-[15px] font-bold text-foreground truncate" data-testid="user-detail-name">{user.name}</h2>
          <p className="text-[11px] text-muted-foreground font-mono truncate" data-testid="user-detail-login">{user.login}</p>
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <ActivePill active={user.active} />
            <KindPill u={user} />
          </div>
        </div>
        <button onClick={onClose} aria-label="Close" title="Close" className="shrink-0 p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent">
          <X size={14} />
        </button>
      </div>

      <Section title="Identity" testId="user-section-identity">
        <dl className="text-[12px] space-y-1.5">
          <div className="flex gap-3"><dt className="w-24 shrink-0 text-muted-foreground">Email</dt><dd className="text-foreground break-all">{user.email ?? <span className="text-muted-foreground">—</span>}</dd></div>
          <div className="flex gap-3"><dt className="w-24 shrink-0 text-muted-foreground">Last sign-in</dt><dd className="text-foreground" data-testid="user-last-login">{user.last_login_at ? formatIsoDateTime(user.last_login_at) : <span className="text-muted-foreground">Never</span>}</dd></div>
          <div className="flex gap-3"><dt className="w-24 shrink-0 text-muted-foreground">Created</dt><dd className="text-foreground" data-testid="user-created">{formatIsoDateTime(user.created_at)}</dd></div>
          {isCredential && user.api_client && (
            <>
              <div className="flex gap-3"><dt className="w-24 shrink-0 text-muted-foreground">Credential</dt><dd className="text-foreground">{user.api_client.name}</dd></div>
              <div className="flex gap-3"><dt className="w-24 shrink-0 text-muted-foreground">Client id</dt><dd className="text-foreground font-mono break-all" data-testid="user-client-id">{user.api_client.client_id}</dd></div>
            </>
          )}
        </dl>
      </Section>

      <Section title="Roles held" testId="user-section-roles-direct">
        {direct.length === 0
          ? <p className="text-[12px] text-muted-foreground">No roles held.</p>
          : <div className="flex flex-wrap gap-1.5">{direct.map(r => <RolePill key={r.key} name={r.name} />)}</div>}
      </Section>

      <Section title="Also holds via implication" testId="user-section-roles-implied">
        {implied.length === 0
          ? <p className="text-[12px] text-muted-foreground">Nothing beyond the roles held.</p>
          : <ul className="space-y-1">{implied.map(r => (
              <li key={r.key} className="flex flex-wrap items-center gap-1.5 text-[12px]" data-testid="implied-role" data-role={r.name}>
                <RolePill name={r.name} implied via={r.via} />
                <span className="text-muted-foreground">{r.via && r.via.length ? <>via {r.via.join(", ")}</> : "via implication"}</span>
              </li>
            ))}</ul>}
      </Section>

      <Section title="What this account can do" testId="user-section-scopes">
        {isCredential && (
          <p className="text-[11px] text-muted-foreground mb-2" data-testid="user-scopes-source">
            Scopes come from the credential, not from roles
            {user.api_client && <> — <span className="text-foreground">{user.api_client.name}</span> (<span className="font-mono">{user.api_client.client_id}</span>)</>}.
          </p>
        )}
        {user.scopes.length === 0
          ? <p className="text-[12px] text-muted-foreground">Nothing — this account holds no scope.</p>
          : (
            <ul className="text-[12px] space-y-1" data-testid="user-scopes-list">
              {user.scopes.map(s => (
                <li key={s} data-scope={s} className="flex items-baseline gap-2">
                  <span className="text-foreground">{scopeWords(s)}</span>
                  <span className="font-mono text-[10px] text-muted-foreground/70">{s}</span>
                </li>
              ))}
            </ul>
          )}
      </Section>

      <Link
        href={`/admin/access-changes?user_id=${user.id}`}
        data-testid="link-access-changes"
        className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-primary hover:opacity-80"
      >
        <History size={13} /> Access changes for this person →
      </Link>
    </div>
  );
}

// ─── REFUSAL ──────────────────────────────────────────────────────────────────
export function AdminScopeRefusal() {
  return (
    <div className="p-8 max-w-xl mx-auto" data-testid="admin-scope-refusal">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">This page needs the admin scope</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">
            Your session does not hold it. Who holds which role is read by system administrators only.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
export default function AdminUsers() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const [, nav] = useLocation();
  const [, params] = useRoute("/admin/users/:id");
  const deepLinkId = params?.id ? Number(params.id) : null;

  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterKind, setFilterKind] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(deepLinkId);

  useEffect(() => {
    setTitle("Users");
    setSearchHandler(v => { setSearch(v); setQ(v); });
    return () => setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // 250ms debounce before the query key changes: the search goes to the
  // server, and a request per keystroke on a roster is noise in the access log.
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  // The URL is the source of the selection when it names one.
  useEffect(() => { if (deepLinkId != null) setSelectedId(deepLinkId); }, [deepLinkId]);

  const filters = useMemo<UserFilters>(() => ({
    q: q.trim() || undefined,
    role: filterRole || undefined,
    active: filterActive === "active" ? "true" : filterActive === "inactive" ? "false" : undefined,
    is_api_client: filterKind === "api" ? "true" : filterKind === "people" ? "false" : undefined,
  }), [q, filterRole, filterActive, filterKind]);

  const rolesQuery = useQuery<AdminRole[], CadraApiError>({
    queryKey: ["roles"],
    queryFn: fetchRoles,
    enabled: scopes.isAdmin,
    staleTime: 5 * 60_000,
  });

  const usersQuery = useInfiniteQuery<UsersPage, CadraApiError>({
    queryKey: ["users", filters],
    queryFn: ({ pageParam }) => fetchUsersPage(pageParam as string | undefined, filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: scopes.isAdmin,
    staleTime: 30_000,
  });
  const users = useMemo(() => (usersQuery.data?.pages ?? []).flatMap(p => p.users), [usersQuery.data]);
  const total = usersQuery.data?.pages[0]?.totalEstimate ?? null;

  // The selected row from the list when it is loaded; otherwise (a deep link
  // to somebody off the first page, or filtered out) fetched on its own.
  const inList = users.find(u => u.id === selectedId) ?? null;
  const userQuery = useQuery<AdminUser, CadraApiError>({
    queryKey: ["user", selectedId],
    queryFn: () => fetchUser(selectedId as number),
    enabled: scopes.isAdmin && selectedId != null && !inList,
    staleTime: 30_000,
  });
  const selected = inList ?? (userQuery.data?.id === selectedId ? userQuery.data : null);

  const select = (id: number | null) => {
    setSelectedId(id);
    nav(id == null ? "/admin/users" : `/admin/users/${id}`, { replace: true });
  };

  const hasFilter = !!(search || filterRole || filterActive || filterKind);
  const clear = () => { setSearch(""); setQ(""); setFilterRole(""); setFilterActive(""); setFilterKind(""); };

  if (!scopes.isAdmin) return <AdminScopeRefusal />;

  const roleOptions = (rolesQuery.data ?? []).map(r => ({ value: r.key, label: r.name }));
  const error = usersQuery.error;

  return (
    <div className="flex flex-col h-full" data-testid="admin-users-page">
      {/* Toolbar */}
      <div className="px-4 sm:px-5 py-3 border-b border-border bg-card flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
          <input
            type="search"
            placeholder="Search name, login, email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") setQ(search); }}
            data-testid="input-user-search"
            className="pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20 w-52"
          />
        </div>
        <FilterBtn label="Can act as" value={filterRole} options={roleOptions} onChange={setFilterRole} testId="filter-role" />
        <FilterBtn label="Status" value={filterActive} options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]} onChange={setFilterActive} testId="filter-status" />
        <FilterBtn label="Kind" value={filterKind} options={[{ value: "people", label: "People" }, { value: "api", label: "API credentials" }]} onChange={setFilterKind} testId="filter-kind" />
        {hasFilter && <button onClick={clear} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1.5" data-testid="button-clear-filters"><X size={12} /> Clear</button>}
        <p className="ml-auto text-xs text-muted-foreground" data-testid="users-count">
          <span className="font-bold text-foreground">{users.length.toLocaleString()}</span>
          {total != null && <> of <span className="font-bold text-foreground">{total.toLocaleString()}</span></>} accounts
        </p>
      </div>

      {/* Body: table, with the panel beside it on a wide screen and under it on a phone */}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden">
        <div className="flex-1 min-w-0 lg:overflow-auto">
          {usersQuery.isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <Clock size={20} className="animate-pulse" />
              <p className="text-sm">Loading users…</p>
            </div>
          ) : error ? (
            <div className="p-6 max-w-xl">
              <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" data-testid="users-error">
                <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                <div>
                  <ApiErrorMessage err={error} stacked />
                  {!apiConfigured && <p className="text-[11px] mt-1">No active session.</p>}
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full" data-testid="users-table">
                  <thead className="sticky top-0 bg-card/90 backdrop-blur z-10 border-b border-border">
                    <tr>
                      {["Name", "Email", "Roles", "Kind", "Active", "Last sign-in"].map((h, i) => (
                        <th key={h} className={cn("text-left px-3 sm:px-4 py-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest", i === 1 && "hidden md:table-cell", i === 5 && "hidden sm:table-cell")}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => {
                      const { direct, implied } = splitRoles(u);
                      const active = selectedId === u.id;
                      return (
                        <tr
                          key={u.id}
                          onClick={() => select(u.id)}
                          data-testid="user-row"
                          data-user-id={u.id}
                          data-login={u.login}
                          data-active={u.active ? "true" : "false"}
                          aria-selected={active}
                          className={cn("border-b border-border/50 cursor-pointer transition-colors",
                            active ? "bg-primary/5" : "hover:bg-muted/20",
                            !u.active && "opacity-60")}
                        >
                          <td className="px-3 sm:px-4 py-2.5">
                            <p className="text-[12px] font-semibold text-foreground">{u.name}</p>
                            <p className="text-[10px] text-muted-foreground font-mono">{u.login}</p>
                          </td>
                          <td className="px-3 sm:px-4 py-2.5 hidden md:table-cell"><span className="block text-[12px] text-muted-foreground whitespace-nowrap max-w-[16rem] truncate" title={u.email ?? undefined}>{u.email ?? "—"}</span></td>
                          <td className="px-3 sm:px-4 py-2.5">
                            <div className="flex flex-wrap gap-1" data-testid="user-row-roles">
                              {direct.map(r => <RolePill key={r.key} name={r.name} />)}
                              {implied.map(r => <RolePill key={r.key} name={r.name} implied via={r.via} />)}
                              {direct.length === 0 && implied.length === 0 && <span className="text-[11px] text-muted-foreground">—</span>}
                            </div>
                          </td>
                          <td className="px-3 sm:px-4 py-2.5"><KindPill u={u} /></td>
                          <td className="px-3 sm:px-4 py-2.5"><ActivePill active={u.active} /></td>
                          <td className="px-3 sm:px-4 py-2.5 hidden sm:table-cell"><span className="text-[11px] text-muted-foreground whitespace-nowrap">{u.last_login_at ? formatIsoDateTime(u.last_login_at) : "Never"}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {users.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 gap-2" data-testid="users-empty">
                  <ShieldCheck size={24} className="text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">No accounts match.</p>
                  {hasFilter && <button onClick={clear} className="text-xs text-primary hover:opacity-80">Clear filters</button>}
                </div>
              )}
              <div className="px-4 py-3 flex flex-wrap items-center gap-3">
                <p className="text-[11px] text-muted-foreground" data-testid="role-filter-hint">
                  Roles are listed as granted first; a lighter pill is held through another role.
                  The <em>Can act as</em> filter includes roles held by implication.
                </p>
                {usersQuery.hasNextPage && (
                  <button onClick={() => usersQuery.fetchNextPage()} disabled={usersQuery.isFetchingNextPage} className="ml-auto text-xs text-primary hover:opacity-80 disabled:opacity-50" data-testid="button-load-more-users">
                    {usersQuery.isFetchingNextPage ? "Loading more…" : "Load more"}
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        {selectedId != null && (
          <aside className="lg:w-[380px] lg:shrink-0 border-t lg:border-t-0 lg:border-l border-border lg:overflow-y-auto p-4 sm:p-5 bg-background" data-testid="user-detail-panel">
            {selected ? (
              <DetailPanel user={selected} onClose={() => select(null)} />
            ) : userQuery.error ? (
              <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4" data-testid="user-detail-error">
                <ApiErrorMessage err={userQuery.error} stacked />
              </div>
            ) : (
              <div className="flex items-center gap-2 text-muted-foreground text-xs"><Clock size={12} className="animate-pulse" /> Loading…</div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
