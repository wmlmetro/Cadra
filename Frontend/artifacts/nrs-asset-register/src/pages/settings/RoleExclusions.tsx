/**
 * Settings — Role exclusions (handoff 58 §5, Addendum A §4 rule 2).
 *
 * Rule 1 (handoff 57) stops one person firing two gates on one unit. Rule 2
 * stops the wrong combination of roles being GRANTED in the first place:
 * two roles named here cannot be held by one person. The table is enforced
 * on the model under every writer of membership, so a refusal reaches the
 * Users page as a sentence naming both roles and this table.
 *
 * Two things this screen deliberately does not do:
 *
 *   - It revokes nothing. A person who already holds a pair this table
 *     forbids stays as they are; they are listed under *Conflicting grants*
 *     for the owner to decide. Switching an exclusion on is a rule about the
 *     next grant, not a sweep of the last ones.
 *   - It does not delete an exclusion. Switching one off keeps the row and
 *     its reason; every change is a row in Configuration changes.
 *
 * `settings:write` to change anything and to read the conflicting grants
 * (both are the server's gates); `settings:read` alone sees the table.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchRoleExclusions, createRoleExclusion, updateRoleExclusion, fetchConflictingGrants,
  fetchRoles, EXCLUDABLE_ROLE_KEYS,
  type RoleExclusion, type ConflictingGrants,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { Switch } from "@/components/ui/switch";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Check, Clock, Loader2, Plus, ShieldAlert, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg border border-border bg-background px-2 py-1 text-[12px] " +
  "focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40";

const EXCLUSIONS_KEY = ["settings", "role-exclusions"] as const;
const CONFLICTS_KEY = ["settings", "conflicting-grants"] as const;

function ErrorPanel({ err }: { err: CadraApiError }) {
  return (
    <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3" role="alert">
      <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <ApiErrorMessage err={err} stacked />
    </div>
  );
}

/** One exclusion, with a local draft of its reason so a half-typed sentence
 *  never fires a request. The switch saves at once, as the receipt gate's
 *  does: it is one decision, not an edit. */
function ExclusionRow({
  ex, readOnly, busy, saving, onPatch,
}: {
  ex: RoleExclusion;
  readOnly: boolean;
  busy: boolean;
  saving: boolean;
  onPatch: (id: number, body: { active?: boolean; reason?: string }) => void;
}) {
  const [reason, setReason] = useState(ex.reason);
  useEffect(() => { setReason(ex.reason); }, [ex.reason]);
  const dirty = reason.trim() !== ex.reason.trim();

  return (
    <tr className={cn("border-b border-border last:border-0 align-top", !ex.active && "text-muted-foreground")}
        data-testid={`exclusion-row-${ex.id}`} data-active={ex.active ? "true" : "false"}>
      <td className="py-2 pr-2 text-[12px] font-medium whitespace-nowrap" data-role={ex.role_a.key}>{ex.role_a.name}</td>
      <td className="py-2 pr-2 text-[12px] font-medium whitespace-nowrap" data-role={ex.role_b.key}>{ex.role_b.name}</td>
      <td className="py-2 pr-2 min-w-[260px]">
        {readOnly ? (
          <p className="text-[12px]">{ex.reason || "—"}</p>
        ) : (
          <div className="flex items-center gap-1.5">
            <input className={inputCls} value={reason} disabled={busy}
                   aria-label={`Why ${ex.role_a.name} and ${ex.role_b.name} are excluded`}
                   data-testid={`exclusion-reason-${ex.id}`}
                   onChange={e => setReason(e.target.value)} />
            <button
              type="button"
              disabled={!dirty || !reason.trim() || busy}
              onClick={() => onPatch(ex.id, { reason })}
              data-testid={`exclusion-save-reason-${ex.id}`}
              className={cn(
                "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border shrink-0",
                dirty && reason.trim() && !busy
                  ? "border-primary text-primary hover:bg-primary/5"
                  : "border-transparent text-muted-foreground/40 cursor-default",
              )}
            >
              {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
              Save
            </button>
          </div>
        )}
      </td>
      <td className="py-2 pr-2 text-right text-[12px] tabular-nums w-20" data-testid={`exclusion-holders-${ex.id}`}>
        {ex.holders.toLocaleString()}
      </td>
      <td className="py-2 text-right w-16">
        <Switch
          checked={ex.active}
          disabled={readOnly || busy}
          data-testid={`exclusion-toggle-${ex.id}`}
          aria-label={`${ex.role_a.name} with ${ex.role_b.name} — ${ex.active ? "in force" : "switched off"}`}
          onCheckedChange={(v) => onPatch(ex.id, { active: v })}
        />
      </td>
    </tr>
  );
}

function ConflictingGrantsSection({ data }: { data: ConflictingGrants }) {
  return (
    <section className="bg-card border border-border rounded-2xl p-5 space-y-3" data-testid="conflicting-grants"
             data-total={data.total ?? ""}>
      <div className="flex items-start gap-2">
        <ShieldAlert size={16} className={cn("shrink-0 mt-0.5",
          data.rows.length ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")} />
        <div>
          <h2 className="text-[13px] font-bold">Conflicting grants</h2>
          {/* The server's sentence, as written: it says how many, that
              nothing has been revoked, and whose decision it is. */}
          {data.statement && (
            <p className="text-[12px] text-foreground mt-0.5" data-testid="conflicting-grants-statement">
              {data.statement}
            </p>
          )}
        </div>
      </div>
      {data.rows.length === 0 ? (
        <p className="text-[12px] text-muted-foreground" data-testid="conflicting-grants-empty">
          Nobody holds a combination of roles this table forbids.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {data.rows.map(g => (
            <li key={g.user.id} className="py-2.5" data-testid={`conflict-row-${g.user.id}`}>
              <p className="text-[12px]">
                <span className="font-semibold text-foreground">{g.user.name}</span>
                <span className="text-muted-foreground"> · {g.user.login}</span>
                {!g.user.active && <span className="text-muted-foreground"> · deactivated</span>}
              </p>
              <ul className="mt-1 space-y-0.5">
                {g.pairs.map(p => (
                  <li key={p.exclusion_id} className="text-[11px] text-muted-foreground"
                      data-testid="conflict-pair" data-exclusion={p.exclusion_id}>
                    Holds <span className="text-foreground font-medium">{p.role_a.name}</span> and{" "}
                    <span className="text-foreground font-medium">{p.role_b.name}</span>
                    {p.reason ? ` — ${p.reason}` : ""}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function RoleExclusionsPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();
  const canWrite = scopes.has(SCOPE.settingsWrite);
  const canRead = canWrite || scopes.has(SCOPE.settingsRead);
  const [note, setNote] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [roleA, setRoleA] = useState("");
  const [roleB, setRoleB] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    setTitle("Settings — Role exclusions");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const exclusions = useQuery<RoleExclusion[], CadraApiError>({
    queryKey: EXCLUSIONS_KEY,
    queryFn: fetchRoleExclusions,
    enabled: canRead,
    staleTime: 0,
  });
  const conflicts = useQuery<ConflictingGrants, CadraApiError>({
    queryKey: CONFLICTS_KEY,
    queryFn: fetchConflictingGrants,
    enabled: canWrite,
    staleTime: 0,
  });
  // The role vocabulary. `/roles` scopes `admin`; somebody holding only
  // `settings:write` cannot read it, so the names also come from the table's
  // own rows and, failing both, the key is shown as it is.
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: fetchRoles,
    enabled: scopes.isAdmin,
    staleTime: 5 * 60_000,
  });
  const roleOptions = useMemo(() => {
    const names = new Map<string, string>();
    for (const ex of exclusions.data ?? []) {
      names.set(ex.role_a.key, ex.role_a.name);
      names.set(ex.role_b.key, ex.role_b.name);
    }
    for (const r of roles.data ?? []) names.set(r.key, r.name);
    return EXCLUDABLE_ROLE_KEYS.map(key => ({ key, name: names.get(key) ?? key }));
  }, [exclusions.data, roles.data]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: EXCLUSIONS_KEY });
    qc.invalidateQueries({ queryKey: CONFLICTS_KEY });
  };

  const patch = useMutation<RoleExclusion, CadraApiError, { id: number; body: { active?: boolean; reason?: string } }>({
    mutationFn: ({ id, body }) => updateRoleExclusion(id, body),
    onMutate: () => { setNote(null); create.reset(); },
    onSuccess: (d, { body }) => {
      const pair = `${d.role_a.name} with ${d.role_b.name}`;
      setNote(body.active === undefined
        ? `Reason saved for ${pair}.`
        : d.active
          ? `${pair} is excluded again. Nothing already granted was revoked.`
          : `${pair} is no longer excluded.`);
      refresh();
    },
    onSettled: () => setSavingId(null),
  });

  const create = useMutation<RoleExclusion, CadraApiError, void>({
    mutationFn: () => createRoleExclusion({ role_a: roleA, role_b: roleB, reason }),
    onMutate: () => { setNote(null); patch.reset(); },
    onSuccess: (d) => {
      setNote(`${d.role_a.name} and ${d.role_b.name} can no longer be granted to one person. Nothing already granted was revoked.`);
      setRoleA(""); setRoleB(""); setReason("");
      refresh();
    },
  });

  const busy = patch.isPending || create.isPending;
  const loadErr = (exclusions.error ?? conflicts.error) as CadraApiError | null;
  const addReady = !!roleA && !!roleB && roleA !== roleB && !!reason.trim() && !busy;

  if (!canRead) return (
    <div className="p-6 max-w-[900px] mx-auto">
      <h1 className="text-xl font-bold text-foreground">Role exclusions</h1>
      <p className="text-[12px] text-muted-foreground mt-2" data-testid="settings-read-only">
        Reading this needs the settings:read or settings:write scope.
      </p>
    </div>
  );

  if (exclusions.isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading role exclusions…</p>
    </div>
  );

  const rows = exclusions.data ?? [];

  return (
    <div className="p-6 space-y-5 max-w-[1000px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground">Role exclusions</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Pairs of roles one person may not hold together. A grant that would create one is
          refused, naming both roles and the reason. Switching an exclusion on revokes nothing
          already granted.
        </p>
      </div>

      {loadErr && <ErrorPanel err={loadErr} />}
      {patch.error && <ErrorPanel err={patch.error} />}
      {note && !patch.error && !create.error && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/30 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Check size={14} className="text-emerald-600 dark:text-emerald-400" />
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300" data-testid="role-exclusions-note">{note}</p>
        </div>
      )}

      <section className="bg-card border border-border rounded-2xl p-5 overflow-x-auto" data-testid="role-exclusions">
        {rows.length === 0 ? (
          <p className="text-[12px] text-muted-foreground" data-testid="role-exclusions-empty">
            No exclusions are set on this tenant: any two roles may be granted to one person.
          </p>
        ) : (
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2 text-[11px] font-medium">Role</th>
                <th className="py-2 text-[11px] font-medium">Cannot be held with</th>
                <th className="py-2 text-[11px] font-medium">Reason</th>
                <th className="py-2 text-[11px] font-medium text-right" title="Active people who hold both roles now">
                  <span className="inline-flex items-center gap-1"><Users size={11} /> Hold both</span>
                </th>
                <th className="py-2 text-[11px] font-medium text-right">In force</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(ex => (
                <ExclusionRow
                  key={ex.id} ex={ex} readOnly={!canWrite} busy={busy}
                  saving={savingId === ex.id && patch.isPending}
                  onPatch={(id, body) => { setSavingId(id); patch.mutate({ id, body }); }}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>

      {canWrite ? (
        <section className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <h2 className="text-[13px] font-bold">Add exclusion</h2>
          <form
            onSubmit={(e) => { e.preventDefault(); if (addReady) create.mutate(); }}
            className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_2fr_auto] gap-3 items-end"
          >
            <div>
              <label htmlFor="exclusion-role-a" className="text-[11px] text-muted-foreground">Role</label>
              <select id="exclusion-role-a" className={inputCls} value={roleA} disabled={busy}
                      data-testid="select-exclusion-role-a"
                      onChange={e => setRoleA(e.target.value)}>
                <option value="">—</option>
                {roleOptions.map(r => <option key={r.key} value={r.key}>{r.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="exclusion-role-b" className="text-[11px] text-muted-foreground">Cannot be held with</label>
              <select id="exclusion-role-b" className={inputCls} value={roleB} disabled={busy}
                      data-testid="select-exclusion-role-b"
                      onChange={e => setRoleB(e.target.value)}>
                <option value="">—</option>
                {roleOptions.filter(r => r.key !== roleA).map(r => <option key={r.key} value={r.key}>{r.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="exclusion-reason" className="text-[11px] text-muted-foreground">Reason</label>
              <input id="exclusion-reason" className={inputCls} value={reason} disabled={busy}
                     placeholder="Why one person must not hold both"
                     data-testid="input-exclusion-reason"
                     onChange={e => setReason(e.target.value)} />
            </div>
            <button
              type="submit"
              disabled={!addReady}
              data-testid="button-add-exclusion"
              className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-primary text-primary hover:bg-primary/5 disabled:opacity-40"
            >
              {create.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              Add exclusion
            </button>
          </form>
          <p className="text-[10px] text-muted-foreground">
            Adding one refuses the next grant of the pair; anybody who holds both already is listed
            under Conflicting grants below, not revoked.
          </p>
          {create.error && <ErrorPanel err={create.error} />}
        </section>
      ) : (
        <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
          Changing this, and seeing who already holds a forbidden pair, needs the settings:write scope.
        </p>
      )}

      {canWrite && conflicts.isLoading && (
        <p className="text-[12px] text-muted-foreground inline-flex items-center gap-2">
          <Loader2 size={12} className="animate-spin" /> Reading who holds a forbidden pair…
        </p>
      )}
      {canWrite && conflicts.data && <ConflictingGrantsSection data={conflicts.data} />}
    </div>
  );
}
