import { useState } from "react";
import { Link, useLocation } from "wouter";
import { login } from "@/lib/auth";
import { Loader2, ShieldCheck, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { brandLogoSrc, getBrand } from "@/lib/brand";
import { useTurnstile } from "@/lib/useTurnstile";
import { currentScopes } from "@/hooks/use-scopes";
import { landingPath } from "@/lib/navigation";
import { tenantHiddenWith } from "@/hooks/use-tenant-sidebar";

export default function Login() {
  const [, nav] = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Turnstile lives in a hook since handoff 45, shared with "Forgot password?".
  const challenge = useTurnstile();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      // Which pages this tenant shows is read with the new token BEFORE it
      // is stored (handoff 48): storing it swaps this page for the app, and
      // a navigation that waited on a request after that rendered `/` first
      // — the command centre and its four reads, or for a tagger alone a
      // second /no-access (caught by the handoff 46 spec).
      let hidden: Set<string> = new Set();
      await login(username.trim(), password, challenge.token || undefined,
        async (t) => { hidden = await tenantHiddenWith(t); });
      // App.tsx auth-gate listens for the auth-changed event and re-renders
      // into the authenticated shell. Where to: the best page this person can
      // open, from the scopes login() has just stored (handoff 46) — not `/`,
      // which a tagger alone would open on a refusal.
      // And preferably one this tenant shows (handoff 48).
      nav(landingPath(currentScopes(), hidden));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      challenge.reset();
    } finally {
      setPending(false);
    }
  }

  // Gate on the challenge only while the widget is healthy and still working
  // — the normal "solving in progress" case. A widget that failed outright
  // must not become a lockout: the API is the real gate, so let the request
  // through and let it answer. On a tenant with no secret configured that
  // login simply succeeds; on one with a secret it is refused with a reason,
  // which beats a disabled button that never explains itself.
  const isSubmitDisabled = !username.trim() || !password || pending || challenge.awaiting;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <img src={brandLogoSrc()} alt={getBrand().name} className="h-16 w-auto" draggable={false} />
          <div className="text-center">
            <h1 className="text-[18px] font-bold text-foreground">Sign in to Cadra</h1>
            <p className="text-[12px] text-muted-foreground mt-1">Use your Cadra credentials</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Username</label>
            <input
              type="text"
              autoFocus
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              className="w-full px-3 py-2 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="Your Cadra username"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 pr-16 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <button
                type="button"
                onClick={() => setShowPassword(s => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-muted-foreground hover:text-foreground px-1.5 py-0.5"
              >
                {showPassword ? "HIDE" : "SHOW"}
              </button>
            </div>
          </div>

          {challenge.show && (
            <div className="flex flex-col items-center gap-2 py-2">
              <div ref={challenge.containerRef} />
              {challenge.broken && (
                <p className="text-xs text-muted-foreground text-center">
                  The security check could not load. You can still try to sign in,
                  or reload the page to run it again.
                </p>
              )}
            </div>
          )}

          {error && (
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-red-700 dark:text-red-400 break-all">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitDisabled}
            className={cn(
              "w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl",
              !isSubmitDisabled
                ? "bg-primary text-white hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {pending ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
            Sign in
          </button>

          <div className="text-center">
            <Link
              href="/forgot-password"
              className="text-[12px] font-semibold text-primary hover:underline"
              data-testid="link-forgot-password"
            >
              Forgot password?
            </Link>
          </div>

          <p className="text-[11px] text-muted-foreground text-center">
            Your session is held in this browser only and expires after 1 hour.
          </p>
        </form>
      </div>
    </div>
  );
}
