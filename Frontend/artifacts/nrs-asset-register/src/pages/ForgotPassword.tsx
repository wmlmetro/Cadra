/**
 * "Forgot password?" — the link the sign-in page did not have (handoff 45
 * §2.1.4). Sends the tenant's own reset letter; the answer is the same
 * whether or not an account matched, so this page cannot be used to find out
 * who has one.
 */
import { useState } from "react";
import { Link } from "wouter";
import { Loader2, Mail } from "lucide-react";
import { requestPasswordReset } from "@/lib/auth";
import { useTurnstile } from "@/lib/useTurnstile";
import { AuthError, AuthNotice, AuthShell, authButton, authInput, authLabel, authLink } from "@/components/auth/AuthShell";

export default function ForgotPassword() {
  const [login, setLogin] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const challenge = useTurnstile();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const r = await requestPasswordReset(login.trim(), challenge.token || undefined);
      setSent(r.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The letter could not be requested.");
      challenge.reset();
    } finally {
      setPending(false);
    }
  }

  const enabled = !!login.trim() && !pending && !challenge.awaiting;
  return (
    <AuthShell title="Forgot your password?" subtitle="We will email you a link to choose a new one.">
      {sent ? (
        <>
          <AuthNotice>{sent}</AuthNotice>
          <div className="text-center"><Link href="/" className={authLink}>Back to sign in</Link></div>
        </>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" data-testid="forgot-password-form">
          <div className="space-y-1.5">
            <label className={authLabel} htmlFor="forgot-login">Username or email</label>
            <input id="forgot-login" type="text" autoFocus autoComplete="username"
              value={login} onChange={(e) => setLogin(e.target.value)} className={authInput}
              placeholder="The one you sign in with" />
          </div>
          {challenge.show && (
            <div className="flex flex-col items-center gap-2 py-2">
              <div ref={challenge.containerRef} />
              {challenge.broken && (
                <p className="text-xs text-muted-foreground text-center">
                  The security check could not load. You can still send the request, or reload the page to run it again.
                </p>
              )}
            </div>
          )}
          {error && <AuthError>{error}</AuthError>}
          <button type="submit" disabled={!enabled} className={authButton(enabled)}>
            {pending ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
            Send me a link
          </button>
          <div className="text-center"><Link href="/" className={authLink}>Back to sign in</Link></div>
        </form>
      )}
    </AuthShell>
  );
}
