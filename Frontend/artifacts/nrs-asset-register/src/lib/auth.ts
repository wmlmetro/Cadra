/**
 * Cadra auth — JWT storage + lifecycle.
 *
 * Quickest viable login flow per the deployment plan:
 *  - Login page POSTs client_id + client_secret to /api/v1/auth/token
 *  - The resulting JWT is stashed in localStorage with its expiry
 *  - api.ts reads it via getToken() on every request
 *  - On a 401, clearToken() + emit "cadra:logout" so App.tsx can route to /login
 *
 * Refresh flow: login() and the access token come paired with an opaque,
 * rotating refresh token (30-day sliding window, stored server-side). When
 * the ~1h access token expires, refreshSession() silently exchanges the
 * refresh token for a fresh pair via POST /api/v1/auth/refresh, so the user
 * stays logged in. Only when the refresh token itself is gone/expired/revoked
 * are they sent back to the login page.
 */

const TOKEN_KEY      = "cadra.token";
const EXPIRY_KEY     = "cadra.tokenExpiresAt";
const SCOPE_KEY      = "cadra.tokenScope";
const REFRESH_KEY        = "cadra.refreshToken";
const REFRESH_EXPIRY_KEY = "cadra.refreshTokenExpiresAt";
// Sticky flag set on logout. Suppresses the dev .env.local token fallback
// so the user actually stays logged out — without this, hasLiveSession()
// would re-affirm a session from the env token on every page load and the
// login form would never appear.
const LOGGED_OUT_KEY = "cadra.loggedOut";

const LOGOUT_EVENT = "cadra:logout";
const AUTH_CHANGED_EVENT = "cadra:auth-changed";

function notifyAuthChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT));
  }
}

export interface StoredToken {
  token: string;
  expiresAt: number;  // epoch ms
  scope?: string;
}

function envToken(): string {
  // Dev-only fallback — keeps the existing .env.local flow working until the
  // login flow ships in prod. Returns "" when unset.
  return (import.meta.env.VITE_API_TOKEN ?? "") as string;
}

function envFallbackAllowed(): boolean {
  // The env token only seeds a session when the user hasn't explicitly
  // logged out. Once they do, this flag is sticky until the next successful
  // login() call clears it.
  try { return localStorage.getItem(LOGGED_OUT_KEY) === null; } catch { return true; }
}

export function getToken(): string | null {
  const stored = readStored();
  if (stored && stored.expiresAt > Date.now()) return stored.token;
  if (!envFallbackAllowed()) return null;
  const env = envToken();
  return env || null;
}

export function hasLiveSession(): boolean {
  const stored = readStored();
  if (stored && stored.expiresAt > Date.now()) return true;
  if (!envFallbackAllowed()) return false;
  return !!envToken();
}

export function getExpiry(): number | null {
  const stored = readStored();
  return stored?.expiresAt ?? null;
}

export function getScope(): string | null {
  return localStorage.getItem(SCOPE_KEY);
}

/** The raw refresh token, or null if absent or itself past expiry. */
export function getRefreshToken(): string | null {
  const t = localStorage.getItem(REFRESH_KEY);
  const exp = localStorage.getItem(REFRESH_EXPIRY_KEY);
  if (!t || !exp) return null;
  const expiresAt = Number(exp);
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return null;
  return t;
}

export function storeToken(
  { token, expiresIn, scope, refreshToken, refreshExpiresIn }:
  { token: string; expiresIn: number; scope?: string; refreshToken?: string; refreshExpiresIn?: number },
): StoredToken {
  const expiresAt = Date.now() + Math.max(0, expiresIn - 30) * 1000;  // 30s safety margin
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRY_KEY, String(expiresAt));
  if (scope) localStorage.setItem(SCOPE_KEY, scope);
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken);
    // No safety-margin shave here — the refresh endpoint is the authority on
    // whether the token is still live; this expiry is only a client-side hint
    // to avoid a doomed round-trip.
    localStorage.setItem(REFRESH_EXPIRY_KEY, String(Date.now() + (refreshExpiresIn ?? 0) * 1000));
  }
  // A successful login lifts the "explicitly logged out" guard so the dev
  // env fallback can apply again on subsequent reloads.
  localStorage.removeItem(LOGGED_OUT_KEY);
  notifyAuthChanged();
  return { token, expiresAt, scope };
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRY_KEY);
  localStorage.removeItem(SCOPE_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(REFRESH_EXPIRY_KEY);
  // Set the sticky logged-out marker so hasLiveSession()/getToken() stop
  // falling back to the dev env token until the next login.
  localStorage.setItem(LOGGED_OUT_KEY, "1");
  notifyAuthChanged();
}

/** Wipe the token and notify the app shell (App.tsx listens for this). */
export function logout(): void {
  // Best-effort server-side revocation so the refresh-token family is killed
  // immediately rather than lingering until its 30-day expiry. Fire-and-forget:
  // we never block logout on the network, and a failure is harmless.
  const rt = localStorage.getItem(REFRESH_KEY);
  if (rt) {
    const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
    void fetch(`${base}/api/v1/auth/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
      keepalive: true,
    }).catch(() => { /* logout proceeds regardless */ });
  }
  clearToken();
  window.dispatchEvent(new CustomEvent(LOGOUT_EVENT));
}

export function onLogout(handler: () => void): () => void {
  const fn = () => handler();
  window.addEventListener(LOGOUT_EVENT, fn);
  return () => window.removeEventListener(LOGOUT_EVENT, fn);
}

function readStored(): StoredToken | null {
  const token = localStorage.getItem(TOKEN_KEY);
  const exp   = localStorage.getItem(EXPIRY_KEY);
  if (!token || !exp) return null;
  const expiresAt = Number(exp);
  if (!Number.isFinite(expiresAt)) return null;
  return { token, expiresAt, scope: localStorage.getItem(SCOPE_KEY) ?? undefined };
}

// ─── Login API call ─────────────────────────────────────────────────────────

interface TokenResponse {
  data: {
    token_type: string;
    access_token: string;
    expires_in: number;
    scope: string;
    refresh_token?: string;
    refresh_token_expires_in?: number;
  };
}

/**
 * Hits POST /api/v1/auth/login directly (bypasses apiPost so we don't need a
 * token to fetch a token). Same-origin in production behind /app/; in dev
 * it goes through the Vite proxy.
 *
 * Uses the OAuth2 password-grant endpoint that validates the user's Odoo
 * res.users credentials — the same login + password they'd use at the
 * Odoo web UI. M2M consumers (SAP sync, smoke-test client, ...) still use
 * POST /api/v1/auth/token with client_id/secret; we never call that from
 * the React frontend.
 */
export async function login(loginName: string, password: string, turnstileToken?: string): Promise<StoredToken> {
  const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ login: loginName, password, turnstile_token: turnstileToken }),
  });
  let body: unknown = null;
  try { body = await res.json(); } catch { /* below check handles */ }
  if (!res.ok || !body || typeof body !== "object") {
    const errBody = body as { error?: { code?: string; message?: string } } | null;
    const code = errBody?.error?.code ?? "auth_failed";
    const msg  = errBody?.error?.message ?? `Login failed (HTTP ${res.status})`;
    throw new Error(`${code}: ${msg}`);
  }
  const tr = body as TokenResponse;
  if (!tr.data?.access_token) throw new Error("auth_malformed: response missing access_token");
  return storeToken({
    token: tr.data.access_token,
    expiresIn: tr.data.expires_in ?? 3600,
    scope: tr.data.scope,
    refreshToken: tr.data.refresh_token,
    refreshExpiresIn: tr.data.refresh_token_expires_in,
  });
}

// ─── Silent refresh ──────────────────────────────────────────────────────────

// Dedupes concurrent refreshes: if N requests 401 at once (or fire while the
// access token is already expired), they all await the same single round-trip
// instead of stampeding /auth/refresh and rotating the token N times — which,
// because of reuse-detection, would otherwise nuke the whole family.
let refreshInFlight: Promise<string | null> | null = null;

/**
 * Exchange the stored refresh token for a fresh access+refresh pair.
 * Returns the new access token on success, or null if there's nothing to
 * refresh or the refresh was rejected. A definitive rejection (the refresh
 * token is expired/revoked/replayed) triggers logout() so the app routes to
 * the login screen; transient network errors leave the session intact.
 */
export function refreshSession(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const rt = getRefreshToken();
    if (!rt) return null;  // nothing to refresh — caller decides what to do
    try {
      const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
      const res = await fetch(`${base}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        // 401 => the refresh token is dead; the session is over.
        if (res.status === 401) logout();
        return null;
      }
      const body = (await res.json().catch(() => null)) as TokenResponse | null;
      const at = body?.data?.access_token;
      if (!at) return null;
      storeToken({
        token: at,
        expiresIn: body!.data.expires_in ?? 3600,
        scope: body!.data.scope,
        refreshToken: body!.data.refresh_token,
        refreshExpiresIn: body!.data.refresh_token_expires_in,
      });
      return at;
    } catch {
      // Network blip — keep the session so the caller can surface the error
      // and a later request can retry the refresh.
      return null;
    }
  })();

  return refreshInFlight.finally(() => { refreshInFlight = null; });
}
