/**
 * The page a letter's link opens — `/accept-invite?token=…` (an invitation)
 * and `/reset-password?token=…` (a reset). Handoff 45 §2.1: until now this
 * step was Odoo's `/web/signup`, the one page where a new officer decides
 * whether this is a real system.
 *
 * The token is inspected first, so a link that cannot be used says WHY
 * before anybody types a password — expired, already used, cancelled, or not
 * a link at all — each with a way forward. The password rules come from the
 * server (`password_rules`) and are checked here only so the button can say
 * what is missing; the server checks them again and its sentence is shown
 * verbatim if it refuses.
 */
import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { KeyRound, Loader2 } from "lucide-react";
import {
  AuthPageError, clearToken, hasLiveSession, inspectPasswordToken,
  redeemPasswordToken, type PasswordTokenStatus,
} from "@/lib/auth";
import { AuthError, AuthNotice, AuthShell, authButton, authInput, authLabel, authLink } from "@/components/auth/AuthShell";

function tokenFromUrl(): string {
  try { return new URLSearchParams(window.location.search).get("token") ?? ""; } catch { return ""; }
}

export default function SetPassword({ mode }: { mode: "invite" | "reset" }) {
  const [, nav] = useLocation();
  const [token] = useState(tokenFromUrl);
  const [status, setStatus] = useState<PasswordTokenStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [doneWithoutSignIn, setDoneWithoutSignIn] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    inspectPasswordToken(token)
      .then((s) => { if (live) setStatus(s); })
      .catch((e) => { if (live) setLoadError(e instanceof Error ? e.message : "This link could not be checked."); });
    return () => { live = false; };
  }, [token]);

  const kind = status?.kind ?? (mode === "reset" ? "reset" : "invitation");
  const title = kind === "reset" ? "Choose a new password" : "Set your password";
  const rules = status?.password_rules;
  const minLength = rules?.min_length ?? 1;

  // What is still missing, in words — the server says the same thing if it
  // gets that far (`_password_refusal`).
  let missing: string | null = null;
  if (!password.trim()) missing = "Choose a password.";
  else if (password.length < minLength) missing = `At least ${minLength} characters.`;
  else if (password !== confirm) missing = confirm ? "The two passwords do not match." : "Type the password again to confirm it.";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (missing) return;
    setError(null);
    setPending(true);
    try {
      // A browser still signed in as somebody else signs out first, so the
      // person this link belongs to never sees that session's cached data.
      if (hasLiveSession()) clearToken();
      const result = await redeemPasswordToken(token, password, confirm);
      if (result.signedIn) nav("/");
      else setDoneWithoutSignIn(result.login ?? "");
    } catch (e) {
      if (e instanceof AuthPageError && e.code === "conflict" && typeof e.details.state === "string") {
        // The link died while the page was open (used in another tab, a newer
        // letter): show its panel rather than a bare error.
        setStatus((s) => s && { ...s, state: e.details.state as PasswordTokenStatus["state"], message: e.message, next: (e.details.next as string) ?? s.next });
      } else {
        setError(e instanceof Error ? e.message : "Your password could not be set.");
      }
    } finally {
      setPending(false);
    }
  }

  if (loadError) {
    return (
      <AuthShell title={title}>
        <AuthError>{loadError}</AuthError>
        <div className="text-center"><Link href="/" className={authLink}>Go to sign in</Link></div>
      </AuthShell>
    );
  }

  if (!status) {
    return (
      <AuthShell title={title}>
        <div className="flex items-center justify-center gap-2 text-[12px] text-muted-foreground py-4" data-testid="token-checking">
          <Loader2 size={14} className="animate-spin" /> Checking your link…
        </div>
      </AuthShell>
    );
  }

  if (doneWithoutSignIn !== null) {
    return (
      <AuthShell title="Password set" subtitle={status.organisation}>
        <AuthNotice>Your password is set. Sign in with it{doneWithoutSignIn ? <> as <strong>{doneWithoutSignIn}</strong></> : null}.</AuthNotice>
        <div className="text-center"><Link href="/" className={authLink}>Go to sign in</Link></div>
      </AuthShell>
    );
  }

  if (status.state !== "outstanding") {
    return (
      <AuthShell title={title} subtitle={status.organisation}>
        <div data-testid={`token-state-${status.state}`} className="space-y-3">
          <AuthError>{status.message}</AuthError>
          {status.next && <p className="text-[12px] text-muted-foreground">{status.next}</p>}
        </div>
        <div className="flex items-center justify-center gap-4">
          <Link href="/" className={authLink}>Go to sign in</Link>
          <Link href="/forgot-password" className={authLink}>Forgot password?</Link>
        </div>
      </AuthShell>
    );
  }

  const enabled = !missing && !pending;
  return (
    <AuthShell
      title={title}
      subtitle={<>
        {status.organisation}
        {status.name && <><br /><span data-testid="token-person">For <strong className="text-foreground">{status.name}</strong>{status.login ? ` · signs in as ${status.login}` : ""}</span></>}
      </>}
    >
      <form onSubmit={onSubmit} className="space-y-4" data-testid="set-password-form">
        <div className="space-y-1.5">
          <label className={authLabel} htmlFor="new-password">New password</label>
          <div className="relative">
            <input
              id="new-password"
              type={show ? "text" : "password"}
              autoComplete="new-password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={authInput + " pr-16"}
            />
            <button type="button" onClick={() => setShow((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-muted-foreground hover:text-foreground px-1.5 py-0.5">
              {show ? "HIDE" : "SHOW"}
            </button>
          </div>
          {minLength > 1 && <p className="text-[11px] text-muted-foreground">At least {minLength} characters.</p>}
        </div>
        <div className="space-y-1.5">
          <label className={authLabel} htmlFor="confirm-password">Type it again</label>
          <input
            id="confirm-password"
            type={show ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={authInput}
          />
        </div>

        {error && <AuthError>{error}</AuthError>}
        {!error && missing && (password || confirm) && (
          <p className="text-[11px] text-muted-foreground" data-testid="password-missing">{missing}</p>
        )}

        <button type="submit" disabled={!enabled} className={authButton(enabled)}>
          {pending ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
          {kind === "reset" ? "Save new password and sign in" : "Set password and sign in"}
        </button>
        {status.expires_at && (
          <p className="text-[11px] text-muted-foreground text-center">
            This link is valid until {new Date(status.expires_at.replace(" ", "T") + "Z").toLocaleString()}.
          </p>
        )}
      </form>
    </AuthShell>
  );
}
