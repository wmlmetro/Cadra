/**
 * Cadra API client — thin fetch wrapper around the v1 endpoints.
 *
 * Envelope:
 *   success: { data, meta, pagination? }
 *   error:   { error: { code, message, request_id, details } }
 */

import { getToken, hasLiveSession, logout, refreshSession } from "./auth";

/** Origin the Cadra API lives on. Empty string = same origin as the SPA, which
 *  is how it is deployed (the ingress routes /app to the SPA and everything
 *  else to Odoo). Exported so non-`/api` Odoo routes — e.g. the public
 *  `/report/barcode` image endpoint used by label printing — can be built too. */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/**
 * Live-bound flag: true when there's a stored JWT or the dev env fallback.
 * Recomputed on the `cadra:auth-changed` event so importers (which see ES
 * module live bindings) always read the current value after login/logout.
 */
export let apiConfigured = hasLiveSession();

if (typeof window !== "undefined") {
  window.addEventListener("cadra:auth-changed", () => {
    apiConfigured = hasLiveSession();
  });
}

export interface CadraMeta {
  request_id: string;
  timestamp: string;
  version: string;
}

export interface CadraPagination {
  next_cursor: string | null;
  previous_cursor: string | null;
  total_estimate: number | null;
}

export interface CadraResponse<T> {
  data: T;
  meta: CadraMeta;
  pagination?: CadraPagination;
}

export class CadraApiError extends Error {
  code: string;
  status: number;
  requestId?: string;
  details?: unknown;

  constructor(code: string, message: string, status: number, requestId?: string, details?: unknown) {
    super(message);
    this.name = "CadraApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

/**
 * Resolve a usable access token. If the stored one is missing/expired, try a
 * silent refresh first so an idle-but-refreshable session doesn't surface as
 * "please sign in". Throws only when there's genuinely nothing to use.
 */
async function authToken(): Promise<string> {
  let t = getToken();
  if (!t) t = await refreshSession();
  if (!t) {
    throw new CadraApiError(
      "unauthenticated",
      "No active session — please sign in.",
      0,
    );
  }
  return t;
}

/**
 * Run an authenticated request, transparently refreshing on a 401. `make`
 * builds the fetch from a token so we can call it again with a rotated token.
 * A single retry: if the refreshed token is also rejected, the 401 falls
 * through to parseEnvelope, which logs the user out.
 */
async function sendWithAuth<T>(
  path: string,
  make: (token: string) => Promise<Response>,
): Promise<CadraResponse<T>> {
  const token = await authToken();
  let res = await make(token);
  if (res.status === 401) {
    const refreshed = await refreshSession();
    if (refreshed) res = await make(refreshed);
  }
  return parseEnvelope<T>(res, path);
}

function buildUrl(path: string, params?: Record<string, unknown>): string {
  const url = `${API_BASE}${path}`;
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

async function parseEnvelope<T>(res: Response, path: string): Promise<CadraResponse<T>> {
  // Cadra always replies JSON, even for errors. The HTTP status reflects the
  // intent; some Odoo-layer errors come back as 200 with an `error` body too.
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    throw new CadraApiError(
      "non_json_response",
      `HTTP ${res.status}: non-JSON response from ${path}`,
      res.status,
    );
  }

  // Any 401 means the server rejected our token — clear it and bounce the user
  // back to the login screen. The auth helper emits "cadra:logout" which
  // App.tsx listens for.
  if (res.status === 401) logout();

  if (body && typeof body === "object" && "error" in body) {
    const e = (body as { error: { code: string; message: string; request_id?: string; details?: unknown } }).error;
    throw new CadraApiError(e.code, e.message, res.status, e.request_id, e.details);
  }

  if (!res.ok) {
    throw new CadraApiError("http_error", `HTTP ${res.status} from ${path}`, res.status);
  }

  return body as CadraResponse<T>;
}

interface MutateOpts {
  /** Idempotency key for safe retries. Same key + endpoint within 24h returns cached response. */
  idempotencyKey?: string;
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
): Promise<CadraResponse<T>> {
  return sendWithAuth<T>(path, (token) => fetch(buildUrl(path, params), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  }));
}

async function apiMutate<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  opts?: MutateOpts,
): Promise<CadraResponse<T>> {
  return sendWithAuth<T>(path, (token) => {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;

    return fetch(buildUrl(path), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  });
}

export const apiPost   = <T>(path: string, body?: unknown, opts?: MutateOpts) => apiMutate<T>("POST",   path, body, opts);
export const apiPatch  = <T>(path: string, body?: unknown, opts?: MutateOpts) => apiMutate<T>("PATCH",  path, body, opts);
export const apiPut    = <T>(path: string, body?: unknown, opts?: MutateOpts) => apiMutate<T>("PUT",    path, body, opts);
export const apiDelete = <T>(path: string, opts?: MutateOpts)                 => apiMutate<T>("DELETE", path, undefined, opts);

/** Multipart upload — used by the employee bulk-import endpoint. */
export async function apiUpload<T>(
  path: string,
  form: FormData,
  opts?: MutateOpts,
): Promise<CadraResponse<T>> {
  return sendWithAuth<T>(path, (token) => {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      // Do NOT set Content-Type — fetch sets the multipart boundary automatically.
    };
    if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;

    return fetch(buildUrl(path), { method: "POST", headers, body: form });
  });
}

/** Generate a stable idempotency key for a one-shot UI action. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
