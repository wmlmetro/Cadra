/**
 * Cadra auth — JWT storage + lifecycle.
 *
 * Quickest viable login flow per the deployment plan:
 *  - Login page POSTs client_id + client_secret to /api/v1/auth/token
 *  - The resulting JWT is stashed in localStorage with its expiry
 *  - api.ts reads it via getToken() on every request
 *  - On a 401, clearToken() + emit "cadra:logout" so App.tsx can route to /login
 *
 * No refresh flow yet: tokens expire after 1h; once they do, the user is
 * sent back to the login page. Silent re-auth via stored credentials is a
 * follow-up — encrypted-at-rest secrets need a real plan.
 */

const TOKEN_KEY  = "cadra.token";
const EXPIRY_KEY = "cadra.tokenExpiresAt";
const SCOPE_KEY  = "cadra.tokenScope";

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

export function getToken(): string | null {
  const stored = readStored();
  if (stored && stored.expiresAt > Date.now()) return stored.token;
  const env = envToken();
  return env || null;
}

export function hasLiveSession(): boolean {
  const stored = readStored();
  if (stored && stored.expiresAt > Date.now()) return true;
  return !!envToken();
}

export function getExpiry(): number | null {
  const stored = readStored();
  return stored?.expiresAt ?? null;
}

export function getScope(): string | null {
  return localStorage.getItem(SCOPE_KEY);
}

export function storeToken({ token, expiresIn, scope }: { token: string; expiresIn: number; scope?: string }): StoredToken {
  const expiresAt = Date.now() + Math.max(0, expiresIn - 30) * 1000;  // 30s safety margin
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRY_KEY, String(expiresAt));
  if (scope) localStorage.setItem(SCOPE_KEY, scope);
  notifyAuthChanged();
  return { token, expiresAt, scope };
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRY_KEY);
  localStorage.removeItem(SCOPE_KEY);
  notifyAuthChanged();
}

/** Wipe the token and notify the app shell (App.tsx listens for this). */
export function logout(): void {
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
  data: { token_type: string; access_token: string; expires_in: number; scope: string };
}

/**
 * Hits POST /api/v1/auth/token directly (bypasses apiPost so we don't need a
 * token to fetch a token). Same-origin in production behind /app/; in dev
 * it goes through the Vite proxy.
 */
export async function login(client_id: string, client_secret: string): Promise<StoredToken> {
  const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
  const res = await fetch(`${base}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ client_id, client_secret }),
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
  });
}
