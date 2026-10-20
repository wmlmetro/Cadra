/**
 * Cadra API client — thin fetch wrapper around the v1 endpoints.
 *
 * Envelope:
 *   success: { data, meta, pagination?, _warnings? }
 *   error:   { error: { code, message, request_id, details } }
 *
 * A SUCCESS can still carry `_warnings`. Every write goes through
 * `sendMutation` below, which is the one place that reads them and puts them
 * in front of the user; see there. A body field the route does not accept is
 * NOT one of them any more: since handoff 31 it is a `400 invalid_request`
 * whose `details.rejected_fields` names the keys, thrown like any other error
 * and spelled out by `components/ApiErrorMessage.tsx`.
 */

import { getToken, hasLiveSession, logout, refreshSession } from "./auth";
import { collectApiWarnings, showApiWarnings } from "./apiWarnings";

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

/**
 * What a 2xx says it did NOT do. The server writes this block in two places
 * and both are read (`collectApiWarnings`):
 *
 *   - INSIDE `data`, by the handler — `discarded_fields`, on a replayed
 *     workflow callback. `rejected_fields` and its `hint` lived here until
 *     handoff 31 and are gone from the type because they are gone from the
 *     server: that case is a 400 now, and its keys are on the ERROR, under
 *     `details`;
 *   - at the TOP of the envelope, by `ok()` — `truncated`, when the
 *     credential's record cap cut a list short. A list's `data` is an array
 *     and has nowhere to hang a block, which is why that one lives up here.
 *
 * Open-ended on purpose: a block this build has never heard of is still
 * typed, and still shown.
 */
export interface CadraWarnings {
  discarded_fields?: string[];
  truncated?: { cap: number; total: number; reason: string };
  [key: string]: unknown;
}

/** `data` of a write, as the handler may have annotated it. */
export type WithWarnings<T> = T & { _warnings?: CadraWarnings };

export interface CadraResponse<T> {
  data: T;
  meta: CadraMeta;
  pagination?: CadraPagination;
  _warnings?: CadraWarnings;
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
  /** Extra request headers — e.g. `X-Cadra-Device` on an audit capture
   *  (handoff 66), which names the device the capture was taken on. */
  headers?: Record<string, string>;
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

/**
 * An authenticated GET whose body is NOT the envelope — a file the caller
 * will read as a blob (handoff 49: `GET /api/v1/assets/export.csv`). A plain
 * `<a href>` cannot carry the bearer token, and `apiGet` would throw
 * `non_json_response` at a CSV, so this is the third shape: the same token
 * resolution and single 401-refresh-retry as `sendWithAuth`, but the raw
 * `Response` handed back for the caller to read headers
 * (`Content-Disposition`, `X-Cadra-Truncated`) and body itself. An error
 * STATUS is still parsed as the envelope so a refusal reads in words.
 */
export async function apiGetRaw(
  path: string,
  params?: Record<string, unknown>,
): Promise<Response> {
  const make = async (token: string) => fetch(buildUrl(path, params), {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  const token = await authToken();
  let res = await make(token);
  if (res.status === 401) {
    const refreshed = await refreshSession();
    if (refreshed) res = await make(refreshed);
  }
  if (!res.ok) {
    // A refusal is JSON even on this route; let the envelope parser turn it
    // into a CadraApiError (and log out on a 401 that survived the refresh).
    await parseEnvelope<unknown>(res, path);
    throw new CadraApiError("http_error", `HTTP ${res.status} from ${path}`, res.status);
  }
  return res;
}

/**
 * EVERY write goes through here — `apiMutate` and `apiUpload` both — and this
 * is where a success that carries a `_warnings` block is said out loud.
 *
 * It was built in handoff 30 for one block in particular. The API then
 * answered 200/201 to a write whose body named a field the route does not
 * accept: it dropped the field, applied the rest and listed what it dropped
 * under `data._warnings.rejected_fields`, which nothing in this app read.
 * `asset_tag` was typed into the Edit form, saved, answered 200 and left
 * unchanged, with no message (report 29). **That response no longer exists.**
 * Since handoff 31 the same body is a 400 and nothing is written, so it never
 * reaches the line below — `sendWithAuth` throws it, and the form that sent
 * it prints the fields (`components/ApiErrorMessage.tsx`). What still arrives
 * on a 2xx is listed in `lib/apiWarnings.tsx`.
 *
 * It stays HERE rather than at the call sites because there are some two
 * dozen of them, none of which sees the envelope — each unwraps `res.data`
 * through an adapter that keeps only the keys it knows, so `_warnings` is
 * gone before a page could look. A call site cannot forget what it is never
 * asked to do. Reads do not come through here: `_warnings.truncated` on a
 * list is a statement about the credential, not about anything the user just
 * did.
 */
async function sendMutation<T>(
  method: string,
  path: string,
  make: (token: string) => Promise<Response>,
): Promise<CadraResponse<T>> {
  const res = await sendWithAuth<T>(path, make);
  // Never allowed to turn a write that SUCCEEDED into a thrown error: the
  // caller would show a failure for a record that was saved.
  try {
    showApiWarnings(collectApiWarnings(res), { method, path });
  } catch (e) {
    console.error("could not show the API's warnings", e);
  }
  return res;
}

async function apiMutate<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  opts?: MutateOpts,
): Promise<CadraResponse<T>> {
  return sendMutation<T>(method, path, (token) => {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;
    if (opts?.headers) Object.assign(headers, opts.headers);

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

/** Multipart upload — used by the employee bulk-import endpoint. It does not
 *  go through `apiMutate` (the body is a form, not JSON), so it is sent
 *  through `sendMutation` by name: a write that bypassed the warnings would
 *  be the same silence, one function along. */
export async function apiUpload<T>(
  path: string,
  form: FormData,
  opts?: MutateOpts,
): Promise<CadraResponse<T>> {
  return sendMutation<T>("POST", path, (token) => {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      // Do NOT set Content-Type — fetch sets the multipart boundary automatically.
    };
    if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;
    if (opts?.headers) Object.assign(headers, opts.headers);

    return fetch(buildUrl(path), { method: "POST", headers, body: form });
  });
}

/** Generate a stable idempotency key for a one-shot UI action. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
