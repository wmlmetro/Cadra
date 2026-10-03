/**
 * Users — who has what (handoff 41), the grant and the refusal (42), and the
 * person and the door (43).
 *
 * Handoff 41 built this page READ ONLY, END TO END: no create, edit, remove,
 * deactivate, invite, grant, revoke or reset, and nothing greyed out standing
 * in for one. Handoff 42 added exactly ONE thing that writes — the *Change
 * roles* section of the detail panel (`ChangeRolesSection`). Handoff 43 adds
 * the person's lifecycle, by instruction, and nothing else on the page
 * changed: a *Create person* button on the toolbar (`CreatePersonDialog`), a
 * *Sign-in* section on a person's panel (`SignInSection`) with the invitation
 * in words, *Send / Re-send invitation*, *Deactivate* and *Reactivate* (the
 * last two through `ConfirmUserActionDialog`), and an "Invited" pill beside
 * Active on a row whose invitation is outstanding or expired and who has
 * never signed in. A credential's panel gets one sentence instead: its
 * sign-in and status are managed with the credential. The rules it keeps:
 *
 *   - NO PASSWORD IS TYPED ANYWHERE — not on create, not on re-send. The
 *     invitation is a letter from the person's own organisation with a link
 *     they redeem to set their own, and the create dialog says so;
 *   - NOTHING IS DELETED. Deactivating takes the sign-in away and leaves the
 *     roles, the records and the custody as they are; reactivating gives it
 *     back, and a cancelled invitation is NOT re-sent (the row says so);
 *   - EVERY refusal is the server's own sentence, verbatim, in a red panel —
 *     a taken email, a role the model will not grant on create, a letter
 *     that could not be sent, "You cannot deactivate your own account", the
 *     last administrator. Nothing is pre-empted on the screen, not even the
 *     viewer's own row;
 *   - what the server ANSWERED WITH is what the panel shows: every lifecycle
 *     route returns the user row, and the panel takes that over the list's
 *     copy until the list is re-read.
 *
 * Handoff 42's rules, kept as they were:
 *
 *   - a control only for a role the API says is GRANTABLE (`/roles`);
 *     `system` has no checkbox, so the sentence for a non-grantable role is
 *     not reachable from here;
 *   - what will change is shown BEFORE it is applied — the grants, the
 *     revocations, and both lists (held / can act as) before → after — from
 *     a dry run of the real route, so what is previewed is what the server
 *     will do and not what the screen guesses;
 *   - Apply is enabled only after a dry run that found something to change
 *     and only while the boxes still say what that dry run was asked;
 *   - EVERY refusal is the server's own sentence, verbatim, in a red panel
 *     as the tag dialog does it — nothing pre-empted, not even the
 *     viewer's own row: the server says "Nobody grants themselves a role"
 *     and the screen shows it;
 *   - no second audit: `access_recorder.py` records the grant with the
 *     person who clicked, and the spec reads that row back.
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
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes } from "@/hooks/use-scopes";
import {
  changeUserRoles, fetchRoles, fetchUser, fetchUsersPage, inviteUser, type UserFilters, type UsersPage,
} from "@/lib/dataProvider";
import { apiConfigured, CadraApiError } from "@/lib/api";
import { formatIsoDateTime } from "@/lib/utils";
import type { AdminRole, AdminRoleRef, AdminUser, RoleChange } from "@/types";
import {
  AlertCircle, CheckCircle2, ChevronDown, Clock, History, KeyRound, Search, ShieldCheck, User as UserIcon, X,
  Send, UserMinus, UserPlus, UserRoundCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConfirmUserActionDialog, CreatePersonDialog } from "@/components/admin/UserDialogs";
import { ScopeRefusal } from "@/components/ScopeRefusal";

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
  "dashboards:read":    "View the asset register's figures",
  "operations:read":    "View the fleet, staff bus, facilities and security dashboards",
  "identity:read":      "Read the staff roster",
  "access:read":        "Read the access record — who granted whom which role",
  "tagging:write":      "Issue, replace and confirm asset labels",
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

/**
 * Handoff 43: beside Active, for a person who was invited and has never
 * signed in — "Invited" while the link is live, "Invitation expired" after.
 * Nothing for `never`, `redeemed` or `cancelled`: the first is the ordinary
 * row, the second is a person who signs in, and the third is said on the
 * panel, where the deactivation that caused it is. `last_login_at` null is
 * part of the test on purpose — a person who has signed in is not "invited",
 * whatever the token says.
 */
function InvitationPill({ u }: { u: AdminUser }) {
  const state = u.invitation?.state;
  if (u.last_login_at || (state !== "outstanding" && state !== "expired")) return null;
  return (
    <span
      data-testid="invitation-pill"
      data-state={state}
      title={u.invitation.sent_at ? `Invitation sent ${formatIsoDateTime(u.invitation.sent_at)}` : undefined}
      className={cn(pillBase, state === "outstanding"
        ? "bg-amber-50 border-amber-200/70 text-amber-700 dark:bg-amber-950/30 dark:border-amber-800/30 dark:text-amber-400"
        : "bg-muted border-border text-muted-foreground")}
    >
      {state === "outstanding" ? "Invited" : "Invitation expired"}
    </span>
  );
}

/**
 * Handoff 46: an account a test or a demo seed created, from the server's
 * derived `is_test_fixture` — never from the name. The demo personas have
 * realistic names on purpose, and on a client tenant they sit beside real
 * staff, so the name is exactly what cannot tell them apart. Nothing for a
 * real person, and nothing when the server has not said (an older server).
 */
function FixturePill({ u }: { u: AdminUser }) {
  if (u.is_test_fixture !== true) return null;
  return (
    <span
      data-testid="user-fixture-badge"
      title="Created by a test or demo seed — not a real person"
      className={cn(pillBase, "bg-violet-50 border-violet-200/70 text-violet-700 dark:bg-violet-950/30 dark:border-violet-800/30 dark:text-violet-400")}
    >
      Demo / test account
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

// ─── CHANGE ROLES (handoff 42) ────────────────────────────────────────────────
/** The checked set as one string, so "has anything changed since the preview"
 *  is one comparison. Sorted: order is not a change. */
function sig(keys: Iterable<string>) { return Array.from(keys).sort().join(","); }

function RoleNames({ refs, roles, empty }: { refs: AdminRoleRef[]; roles: AdminRole[]; empty: string }) {
  if (refs.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  // A ref carries its own name; fall back to the vocabulary, then the key,
  // so a role the vocabulary has not heard of is still printed, not hidden.
  const name = (r: AdminRoleRef) => r.name || roles.find(x => x.key === r.key)?.name || r.key;
  return <>{refs.map(name).join(", ")}</>;
}

function keysToNames(keys: string[], roles: AdminRole[]) {
  return keys.map(k => roles.find(r => r.key === k)?.name ?? k);
}

function BeforeAfter({ label, testId, before, after, roles }: {
  label: string; testId: string; before: AdminRoleRef[]; after: AdminRoleRef[]; roles: AdminRole[];
}) {
  return (
    <div
      className="text-[12px]"
      data-testid={testId}
      data-before={before.map(r => r.key).join("|")}
      data-after={after.map(r => r.key).join("|")}
    >
      <span className="text-muted-foreground">{label}: </span>
      <span className="text-foreground"><RoleNames refs={before} roles={roles} empty="none" /></span>
      <span className="text-muted-foreground mx-1.5">→</span>
      <span className="text-foreground font-semibold"><RoleNames refs={after} roles={roles} empty="none" /></span>
    </div>
  );
}

/**
 * The one writing control on the page. `roles` is the vocabulary from
 * `/roles`; only the grantable ones get a checkbox. The initial state of the
 * boxes is the person's DIRECT roles among them — what somebody actually
 * granted — never the effective ones, because the route acts on direct
 * membership and a box ticked for an implied role would "revoke" a thing
 * the person never directly held.
 */
function ChangeRolesSection({ user, roles, onApplied }: {
  user: AdminUser; roles: AdminRole[]; onApplied: (u: AdminUser) => void;
}) {
  const qc = useQueryClient();
  const grantable = useMemo(() => roles.filter(r => r.grantable), [roles]);
  const grantableKeys = useMemo(() => new Set(grantable.map(r => r.key)), [grantable]);
  const initial = useMemo(
    () => new Set(user.roles_direct.map(r => r.key).filter(k => grantableKeys.has(k))),
    [user.roles_direct, grantableKeys],
  );
  const initialSig = sig(initial);

  const [checked, setChecked] = useState<Set<string>>(initial);
  // The dry run's answer, pinned to the boxes it was asked about: Apply is
  // live only while `forSig` still equals what is ticked now.
  const [preview, setPreview] = useState<{ result: RoleChange; forSig: string } | null>(null);
  const [applied, setApplied] = useState<RoleChange | null>(null);
  const [err, setErr] = useState<CadraApiError | null>(null);

  // Reset to the record whenever what the person DIRECTLY holds changes —
  // another row opened, or this one re-read after an apply. Not on every
  // refetch: a background re-read that found the same roles must not throw
  // away half-ticked boxes.
  useEffect(() => {
    setChecked(new Set(initial));
    setPreview(null);
    setErr(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id, initialSig]);

  const currentSig = sig(checked);
  const desired = () => grantable.map(r => r.key).filter(k => checked.has(k));

  const previewMut = useMutation<RoleChange, CadraApiError, string>({
    mutationFn: () => changeUserRoles(user.id, desired(), true),
    onMutate: () => { setErr(null); setApplied(null); },
    onSuccess: (result, forSig) => setPreview({ result, forSig }),
    onError: (e) => { setPreview(null); setErr(e); },
  });
  const applyMut = useMutation<RoleChange, CadraApiError>({
    mutationFn: () => changeUserRoles(user.id, desired(), false),
    onMutate: () => setErr(null),
    onSuccess: (result) => {
      setPreview(null);
      setApplied(result);
      onApplied(result.user);
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["user"] });
      qc.invalidateQueries({ queryKey: ["access-changes"] });
    },
    onError: (e) => { setPreview(null); setErr(e); },
  });
  const busy = previewMut.isPending || applyMut.isPending;

  const toggle = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
    // A changed box makes the last answer — preview or refusal — about
    // something else. Apply goes dark by the signature; the panels go too.
    setErr(null);
    setApplied(null);
  };

  const previewCurrent = preview && preview.forSig === currentSig ? preview.result : null;
  const previewHasChange = !!previewCurrent && (previewCurrent.granted.length > 0 || previewCurrent.revoked.length > 0);
  const canApply = previewHasChange && !busy;

  // "Asset Manager also confers Asset User" — one line per ticked role that
  // implies something, so what the person will be ABLE to do is on the
  // screen before Preview is pressed, and the dry run then confirms it.
  const implications = grantable
    .filter(r => checked.has(r.key) && r.implies.length > 0)
    .map(r => ({ role: r, confers: keysToNames(r.implies, roles) }));

  if (user.kind === "api_credential") {
    return (
      <Section title="Change roles" testId="user-section-change-roles">
        <p className="text-[12px] text-muted-foreground" data-testid="roles-follow-scopes">
          A credential's roles follow its scopes and are not changed here.
        </p>
      </Section>
    );
  }

  return (
    <Section title="Change roles" testId="user-section-change-roles">
      {grantable.length === 0 ? (
        <p className="text-[12px] text-muted-foreground" data-testid="roles-none-grantable">
          No role can be granted over the API.
        </p>
      ) : (
        <ul className="space-y-1.5" data-testid="role-checkboxes">
          {grantable.map(r => (
            <li key={r.key} className="flex items-start gap-2">
              <input
                type="checkbox"
                id={`role-${r.key}`}
                data-testid="role-checkbox"
                data-role={r.key}
                checked={checked.has(r.key)}
                disabled={busy}
                onChange={() => toggle(r.key)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-[hsl(var(--primary))]"
              />
              <label htmlFor={`role-${r.key}`} className="text-[12px] text-foreground cursor-pointer leading-snug">
                <span className="font-medium">{r.name}</span>
                {r.description && <span className="block text-[11px] text-muted-foreground">{r.description}</span>}
              </label>
            </li>
          ))}
        </ul>
      )}

      {implications.length > 0 && (
        <ul className="mt-2 space-y-0.5" data-testid="role-implications">
          {implications.map(({ role, confers }) => (
            <li key={role.key} className="text-[11px] text-muted-foreground" data-testid="role-implication-note" data-role={role.key}>
              {role.name} also confers {confers.join(", ")}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          data-testid="button-preview-roles"
          disabled={busy || grantable.length === 0}
          onClick={() => previewMut.mutate(currentSig)}
          className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-border hover:bg-muted/40 disabled:opacity-50"
        >
          {previewMut.isPending ? "Previewing…" : "Preview"}
        </button>
        <button
          type="button"
          data-testid="button-apply-roles"
          disabled={!canApply}
          onClick={() => applyMut.mutate()}
          className="px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90 disabled:opacity-50"
        >
          {applyMut.isPending ? "Applying…" : "Apply"}
        </button>
      </div>

      {previewCurrent && (
        <div className="mt-3 bg-muted/30 border border-border rounded-xl p-3 space-y-1.5" data-testid="roles-preview" data-applied={String(previewCurrent.applied)}>
          {!previewHasChange ? (
            <p className="text-[12px] text-foreground" data-testid="roles-preview-nochange">No change.</p>
          ) : (
            <>
              <p className="text-[12px]" data-testid="roles-preview-grant" data-keys={previewCurrent.granted.join("|")}>
                <span className="text-muted-foreground">Will grant: </span>
                <span className="text-foreground font-semibold">{previewCurrent.granted.length ? keysToNames(previewCurrent.granted, roles).join(", ") : "nothing"}</span>
              </p>
              <p className="text-[12px]" data-testid="roles-preview-revoke" data-keys={previewCurrent.revoked.join("|")}>
                <span className="text-muted-foreground">Will revoke: </span>
                <span className="text-foreground font-semibold">{previewCurrent.revoked.length ? keysToNames(previewCurrent.revoked, roles).join(", ") : "nothing"}</span>
              </p>
              <BeforeAfter label="Roles held" testId="roles-preview-direct" roles={roles}
                before={previewCurrent.before.roles_direct} after={previewCurrent.after.roles_direct} />
              <BeforeAfter label="Can act as (with implication)" testId="roles-preview-effective" roles={roles}
                before={previewCurrent.before.roles_effective} after={previewCurrent.after.roles_effective} />
              <p className="text-[11px] text-muted-foreground pt-0.5">Nothing has been changed yet. Apply makes it so.</p>
            </>
          )}
        </div>
      )}

      {err && (
        <div className="mt-3 flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="roles-refusal" role="alert">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} />
        </div>
      )}

      {applied && (
        <div className="mt-3 flex items-start gap-2 bg-green-50 dark:bg-green-950/30 border border-green-200/60 dark:border-green-800/30 rounded-xl p-3" data-testid="roles-applied" role="status"
          data-granted={applied.granted.join("|")} data-revoked={applied.revoked.join("|")}>
          <CheckCircle2 size={14} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
          <div className="text-[12px] text-green-700 dark:text-green-400">
            <p className="font-semibold">Applied.</p>
            {applied.granted.length > 0 && <p>Granted: {keysToNames(applied.granted, roles).join(", ")}</p>}
            {applied.revoked.length > 0 && <p>Revoked: {keysToNames(applied.revoked, roles).join(", ")}</p>}
          </div>
        </div>
      )}
    </Section>
  );
}

// ─── SIGN-IN (handoff 43) ─────────────────────────────────────────────────────

/** The invitation in words — one sentence per state, each something the
 *  administrator can act on. `sent_by` is named when the server knows it. */
function invitationWords(u: AdminUser): string {
  const inv = u.invitation;
  const by = inv.sent_by ? ` by ${inv.sent_by.name}` : "";
  const sent = inv.sent_at ? formatIsoDateTime(inv.sent_at) : "";
  switch (inv.state) {
    case "never":
      return "No invitation has been sent.";
    case "outstanding":
      return `Invitation sent ${sent}${by} · valid until ${inv.expires_at ? formatIsoDateTime(inv.expires_at) : "—"}`;
    case "expired":
      return `Invitation sent ${sent}${by} · expired ${inv.expires_at ? formatIsoDateTime(inv.expires_at) : ""} — send it again`;
    case "redeemed":
      return `Invitation redeemed; signed in ${u.last_login_at ? formatIsoDateTime(u.last_login_at) : ""}`;
    case "cancelled":
      return "Invitation cancelled (not used)";
    default:
      return `Invitation: ${String(inv.state)}`;
  }
}

/**
 * The person's door: the invitation line, *Send / Re-send invitation*, and
 * *Deactivate* / *Reactivate*. A credential's user has none of it — its
 * sign-in is its client secret and its status is the credential's — and says
 * so in one sentence.
 *
 * *Re-send* is offered only when it can succeed: the account is active, has
 * an email, and has not signed in (the route answers 409 for `redeemed` —
 * "a password reset is theirs to ask for from the sign-in page"). The other
 * refusals — a credential's user, the viewer's own account, the last
 * administrator, a state that changed under us — are the server's to make
 * and are shown here verbatim, not pre-empted.
 */
function SignInSection({ user, onApplied }: { user: AdminUser; onApplied: (u: AdminUser) => void }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<"deactivate" | "reactivate" | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [err, setErr] = useState<CadraApiError | null>(null);

  // Another row opened: its answers are not this row's.
  useEffect(() => { setSentTo(null); setErr(null); setConfirm(null); }, [user.id]);

  const inviteMut = useMutation<AdminUser, CadraApiError>({
    mutationFn: () => inviteUser(user.id),
    onMutate: () => { setErr(null); setSentTo(null); },
    onSuccess: (row) => {
      setSentTo(row.email ?? user.email);
      onApplied(row);
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["user"] });
      qc.invalidateQueries({ queryKey: ["access-changes"] });
    },
    onError: (e) => {
      setErr(e);
      // The row behind the button is out of date — re-read it.
      if (e.status === 409) {
        qc.invalidateQueries({ queryKey: ["users"] });
        qc.invalidateQueries({ queryKey: ["user"] });
      }
    },
  });

  if (user.kind === "api_credential") {
    return (
      <Section title="Sign-in" testId="user-section-signin">
        <p className="text-[12px] text-muted-foreground" data-testid="lifecycle-follows-credential">
          Sign-in and status are managed with the credential, not here.
        </p>
      </Section>
    );
  }

  const inv = user.invitation;
  // Not after a sign-in either: the server answers 409 for somebody who has
  // signed in, whatever `invitation.state` says (a reset is theirs to ask for).
  const canInvite = user.active && inv.state !== "redeemed" && !user.last_login_at && !!user.email;
  const busy = inviteMut.isPending;

  return (
    <Section title="Sign-in" testId="user-section-signin">
      <p className="text-[12px] text-foreground" data-testid="user-invitation" data-state={inv.state} data-sends={inv.sends}>
        {invitationWords(user)}
        {inv.sends > 1 && <span className="text-muted-foreground"> · Sent {inv.sends} times</span>}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {canInvite && (
          <button
            type="button"
            data-testid="button-resend-invitation"
            disabled={busy}
            onClick={() => inviteMut.mutate()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-border hover:bg-muted/40 disabled:opacity-50"
          >
            <Send size={12} />
            {busy ? "Sending…" : inv.state === "never" ? "Send invitation" : "Re-send invitation"}
          </button>
        )}
        {user.active ? (
          <button
            type="button"
            data-testid="button-deactivate-user"
            disabled={busy}
            onClick={() => setConfirm("deactivate")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-red-200/70 dark:border-red-800/30 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-50"
          >
            <UserMinus size={12} /> Deactivate
          </button>
        ) : (
          <button
            type="button"
            data-testid="button-reactivate-user"
            disabled={busy}
            onClick={() => setConfirm("reactivate")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90 disabled:opacity-50"
          >
            <UserRoundCheck size={12} /> Reactivate
          </button>
        )}
      </div>

      {sentTo && (
        <div className="mt-3 flex items-start gap-2 bg-green-50 dark:bg-green-950/30 border border-green-200/60 dark:border-green-800/30 rounded-xl p-3" data-testid="invitation-sent" role="status">
          <CheckCircle2 size={14} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-green-700 dark:text-green-400">Invitation sent just now to <span className="font-semibold">{sentTo}</span></p>
        </div>
      )}

      {err && (
        <div className="mt-3 flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="user-action-refusal" role="alert">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} />
        </div>
      )}

      {confirm && (
        <ConfirmUserActionDialog
          user={user}
          action={confirm}
          open
          onOpenChange={(open) => { if (!open) setConfirm(null); }}
          onApplied={(row) => { setSentTo(null); setErr(null); onApplied(row); }}
        />
      )}
    </Section>
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

function DetailPanel({ user: fromList, roles, onClose }: { user: AdminUser; roles: AdminRole[]; onClose: () => void }) {
  // After an apply the route answers with the user as it now is; the panel
  // shows THAT until the list's re-read (invalidated at the same moment)
  // delivers a new row object, which drops the override.
  const [applied, setApplied] = useState<AdminUser | null>(null);
  useEffect(() => { setApplied(null); }, [fromList]);
  const user = applied && applied.id === fromList.id ? applied : fromList;
  const { direct, implied } = splitRoles(user);
  const isCredential = user.kind === "api_credential";
  return (
    <div className="space-y-3" data-testid="user-detail" data-user-id={user.id} data-login={user.login}>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center border shrink-0 bg-muted border-border">
          {isCredential ? <KeyRound size={18} className="text-amber-600 dark:text-amber-400" /> : <UserIcon size={18} className="text-muted-foreground" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <h2 className="text-[15px] font-bold text-foreground truncate min-w-0" data-testid="user-detail-name">{user.name}</h2>
            <span className="shrink-0"><FixturePill u={user} /></span>
          </div>
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

      <SignInSection user={user} onApplied={setApplied} />

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

      <ChangeRolesSection user={user} roles={roles} onApplied={setApplied} />

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
/** The generic `ScopeRefusal` since handoff 46, keeping this page's testid
 *  and its sentence about who holds the scope. */
export function AdminScopeRefusal() {
  return (
    <ScopeRefusal
      scope="admin"
      testId="admin-scope-refusal"
      detail="Who holds which role is read by system administrators only."
    />
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
  const [creating, setCreating] = useState(false);

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
        <button
          type="button"
          onClick={() => setCreating(true)}
          data-testid="button-create-user"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-primary text-white hover:opacity-90"
        >
          <UserPlus size={12} /> Create person
        </button>
      </div>

      {/* Handoff 43. Rendered in a Radix portal, so its inputs are OUTSIDE
          `admin-users-page` — the absence proof in `41-….spec.ts` counts on
          that. On success the new row is selected, so the panel shows what
          the server made and the invitation line beside it. */}
      <CreatePersonDialog
        open={creating}
        onOpenChange={setCreating}
        roles={rolesQuery.data ?? []}
        onCreated={(u) => select(u.id)}
      />

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
                            <p className="text-[12px] font-semibold text-foreground inline-flex items-center gap-1.5 flex-wrap">{u.name}<FixturePill u={u} /></p>
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
                          <td className="px-3 sm:px-4 py-2.5">
                            <span className="inline-flex items-center gap-1 flex-wrap">
                              <ActivePill active={u.active} />
                              <InvitationPill u={u} />
                            </span>
                          </td>
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
              <DetailPanel user={selected} roles={rolesQuery.data ?? []} onClose={() => select(null)} />
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
