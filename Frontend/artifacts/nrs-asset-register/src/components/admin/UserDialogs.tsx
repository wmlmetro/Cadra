/**
 * The person, and the door (handoff 43) — the three dialogs the Users page
 * opens: create a person, deactivate, reactivate.
 *
 * Built exactly as `CondemnAssetDialog` (`AssetActionDialogs.tsx`) is: a
 * Radix `Dialog` in a portal, a mutation, and EVERY refusal the server's own
 * sentence verbatim in a red panel inside the dialog — the dialog stays open
 * with what was typed still in it, so the person can fix the one thing the
 * server named and press the button again. Nothing is pre-empted here: not a
 * taken email (409), not a non-grantable role (403, the model's sentence),
 * not an undeliverable letter (500), not "your own account" (403).
 *
 * Two rules this file keeps, by instruction:
 *
 *   - NO PASSWORD IS TYPED ANYWHERE. A person is created with a name, an
 *     email and the roles they start with; the invitation is a letter from
 *     their own organisation carrying a link they redeem to set their own.
 *     The one checkbox is whether to send that letter now.
 *   - NOTHING IS DELETED. Deactivating takes the sign-in away and leaves the
 *     roles, the records and the custody as they are; reactivating gives it
 *     back. The dialogs say so in words before the button.
 *
 * On success each dialog closes, the Users page's three query keys are
 * invalidated, and the user row the server ANSWERED WITH is handed up, so the
 * panel shows the server's state and not the screen's guess.
 */
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import type { CadraApiError } from "@/lib/api";
import { createUser, deactivateUser, reactivateUser } from "@/lib/dataProvider";
import type { AdminRole, AdminUser } from "@/types";
import { AlertCircle, Loader2, MailPlus, UserMinus, UserPlus, UserRoundCheck } from "lucide-react";
import { cn } from "@/lib/utils";

/** The three keys every write on the Users page invalidates — the roster,
 *  the single-row read, and the access-changes report that records it. */
function invalidateUserQueries(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["users"] });
  qc.invalidateQueries({ queryKey: ["user"] });
  qc.invalidateQueries({ queryKey: ["access-changes"] });
}

const refusalPanel = "flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3";
const inputClass = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const labelClass = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";

// ─── Create a person ──────────────────────────────────────────────────────────

interface CreateProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The vocabulary from `/roles`; only the GRANTABLE ones get a checkbox,
   *  so the model's sentence for `system` is not reachable from here. */
  roles: AdminRole[];
  /** The row the server answered with — the page selects it. */
  onCreated: (user: AdminUser) => void;
}

export function CreatePersonDialog({ open, onOpenChange, roles, onCreated }: CreateProps) {
  const qc = useQueryClient();
  const grantable = useMemo(() => roles.filter(r => r.grantable), [roles]);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [sendNow, setSendNow] = useState(true);

  const mutation = useMutation<AdminUser, CadraApiError>({
    mutationFn: () => createUser({
      name: name.trim(),
      email: email.trim(),
      roles: grantable.map(r => r.key).filter(k => checked.has(k)),
      sendInvitation: sendNow,
    }),
    onSuccess: (user) => {
      invalidateUserQueries(qc);
      setOpen(false, true);
      onCreated(user);
    },
  });
  const err = mutation.error;

  // Reset on every close — see `CondemnAssetDialog`. A USER cannot close it
  // while the request is in flight; `done` is the success handler closing it.
  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setName("");
      setEmail("");
      setChecked(new Set());
      setSendNow(true);
      mutation.reset();
    }
    onOpenChange(next);
  };

  // A changed field makes the last refusal about something else, so the
  // panel goes when anything is edited — the Condemn dialog keeps its
  // sentence until close because its one field IS the thing refused; here a
  // 409 on the email is answered by editing the email.
  const clearRefusal = () => { if (mutation.isError) mutation.reset(); };

  const toggle = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
    clearRefusal();
  };

  const canSubmit = !!name.trim() && !!email.trim() && !mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      {/* Scrolls inside the viewport: since handoff 57 there are ten
          grantable roles, and the list pushed the dialog past a 720px-tall
          screen with Create below its bottom edge and nothing to scroll —
          the person could fill the form and not submit it (found by spec 43
          in handoff 58's run). */}
      <DialogContent className="sm:max-w-md max-h-[calc(100vh-2rem)] overflow-y-auto" data-testid="dialog-create-user">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus size={16} className="text-primary" /> Create person
          </DialogTitle>
          <DialogDescription>
            {/* The one sentence about the password, where the person reads
                it before typing anything: there is no password field because
                there is no password to type. */}
            They receive an email from this organisation with a link to set their password; no password is typed here.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(e) => { e.preventDefault(); if (canSubmit) mutation.mutate(); }}
        >
          <div>
            <label htmlFor="create-user-name" className={labelClass}>Name</label>
            <input
              id="create-user-name"
              type="text"
              autoComplete="off"
              value={name}
              onChange={e => { setName(e.target.value); clearRefusal(); }}
              disabled={mutation.isPending}
              className={inputClass}
              placeholder="As it will appear on records"
              data-testid="input-create-name"
            />
          </div>
          <div>
            <label htmlFor="create-user-email" className={labelClass}>Email</label>
            <input
              id="create-user-email"
              type="email"
              autoComplete="off"
              value={email}
              onChange={e => { setEmail(e.target.value); clearRefusal(); }}
              disabled={mutation.isPending}
              className={inputClass}
              placeholder="Also their sign-in name"
              data-testid="input-create-email"
            />
          </div>

          <div>
            <p className={labelClass}>Roles to start with</p>
            {grantable.length === 0 ? (
              <p className="mt-1.5 text-[12px] text-muted-foreground" data-testid="create-roles-none-grantable">
                No role can be granted over the API; the person starts with none.
              </p>
            ) : (
              <ul className="mt-1.5 space-y-1.5" data-testid="create-role-checkboxes">
                {grantable.map(r => (
                  <li key={r.key} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      id={`create-role-${r.key}`}
                      data-testid="create-role-checkbox"
                      data-role={r.key}
                      checked={checked.has(r.key)}
                      disabled={mutation.isPending}
                      onChange={() => toggle(r.key)}
                      className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-[hsl(var(--primary))]"
                    />
                    <label htmlFor={`create-role-${r.key}`} className="text-[12px] text-foreground cursor-pointer leading-snug">
                      <span className="font-medium">{r.name}</span>
                      {r.description && <span className="block text-[11px] text-muted-foreground">{r.description}</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <label className="flex items-start gap-2 pt-1 cursor-pointer">
            <input
              type="checkbox"
              checked={sendNow}
              disabled={mutation.isPending}
              onChange={e => { setSendNow(e.target.checked); clearRefusal(); }}
              className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-[hsl(var(--primary))]"
              data-testid="checkbox-send-invitation"
            />
            <span className="text-[12px] text-foreground leading-snug">
              <span className="font-medium">Send the invitation now</span>
              <span className="block text-[11px] text-muted-foreground">
                Unticked, the account is created with no letter; it can be sent later from the person's row.
              </span>
            </span>
          </label>

          {err && (
            <div className={refusalPanel} data-testid="create-user-refusal" role="alert">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={err} />
            </div>
          )}

          <DialogFooter>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              data-testid="button-confirm-create"
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
                canSubmit ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              {mutation.isPending
                ? <Loader2 size={12} className="animate-spin" />
                : sendNow ? <><MailPlus size={12} /> Create and invite</> : "Create"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Deactivate / Reactivate ──────────────────────────────────────────────────

interface ConfirmProps {
  user: AdminUser;
  action: "deactivate" | "reactivate";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The row the server answered with. */
  onApplied: (user: AdminUser) => void;
}

/**
 * One dialog for both doors, because they are the same shape: one or two
 * sentences saying what happens, Cancel, and a confirm button. The server
 * decides whether it may happen — your own account, a credential's user, the
 * last administrator, already in that state — and its sentence is shown here,
 * verbatim, with the dialog left open.
 */
export function ConfirmUserActionDialog({ user, action, open, onOpenChange, onApplied }: ConfirmProps) {
  const qc = useQueryClient();
  const deactivating = action === "deactivate";

  const mutation = useMutation<AdminUser, CadraApiError>({
    mutationFn: () => (deactivating ? deactivateUser(user.id) : reactivateUser(user.id)),
    onSuccess: (row) => {
      invalidateUserQueries(qc);
      setOpen(false, true);
      onApplied(row);
    },
    // A 409 means the row behind this dialog is out of date — somebody else
    // changed the account first. The dialog stays open on the server's
    // sentence; the row is refetched so that closing it lands on the truth.
    onError: (e) => { if (e.status === 409) invalidateUserQueries(qc); },
  });
  const err = mutation.error;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) mutation.reset();
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      <DialogContent className="sm:max-w-md" data-testid={deactivating ? "dialog-deactivate-user" : "dialog-reactivate-user"}>
        <DialogHeader>
          <DialogTitle className={cn("flex items-center gap-2", deactivating ? "text-red-600 dark:text-red-400" : "text-foreground")}>
            {deactivating ? <UserMinus size={16} /> : <UserRoundCheck size={16} className="text-primary" />}
            {deactivating ? "Deactivate" : "Reactivate"} {user.name}
          </DialogTitle>
          <DialogDescription>
            {deactivating
              ? <>{user.name} will no longer be able to sign in. Their roles and records stay as they are; nothing is deleted.</>
              : <>{user.name} will be able to sign in again with their existing password; a cancelled invitation is not re-sent.</>}
          </DialogDescription>
        </DialogHeader>

        {err && (
          <div className={refusalPanel} data-testid="user-action-refusal" role="alert">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <ApiErrorMessage err={err} />
          </div>
        )}

        <DialogFooter>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid={deactivating ? "button-confirm-deactivate" : "button-confirm-reactivate"}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-xl",
              mutation.isPending
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : deactivating ? "bg-red-600 text-white hover:bg-red-700" : "bg-primary text-white hover:opacity-90",
            )}
          >
            {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : deactivating ? "Deactivate" : "Reactivate"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
