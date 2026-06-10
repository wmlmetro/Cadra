/**
 * Cadra API client — thin fetch wrapper around the v1 endpoints.
 *
 * Envelope:
 *   success: { data, meta, pagination? }
 *   error:   { error: { code, message, request_id, details } }
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? "";

export const apiConfigured = Boolean(API_TOKEN);

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

function requireToken() {
  if (!API_TOKEN) {
    throw new CadraApiError(
      "client_misconfigured",
      "VITE_API_TOKEN is not set — copy .env.example to .env.local and add a token.",
      0,
    );
  }
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
  requireToken();
  const res = await fetch(buildUrl(path, params), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      Accept: "application/json",
    },
  });
  return parseEnvelope<T>(res, path);
}

async function apiMutate<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  opts?: MutateOpts,
): Promise<CadraResponse<T>> {
  requireToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${API_TOKEN}`,
    Accept: "application/json",
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;

  const res = await fetch(buildUrl(path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return parseEnvelope<T>(res, path);
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
  requireToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${API_TOKEN}`,
    Accept: "application/json",
    // Do NOT set Content-Type — fetch sets the multipart boundary automatically.
  };
  if (opts?.idempotencyKey) headers["X-Idempotency-Key"] = opts.idempotencyKey;

  const res = await fetch(buildUrl(path), { method: "POST", headers, body: form });
  return parseEnvelope<T>(res, path);
}

/** Generate a stable idempotency key for a one-shot UI action. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
