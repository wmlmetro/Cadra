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

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
): Promise<CadraResponse<T>> {
  if (!API_TOKEN) {
    throw new CadraApiError(
      "client_misconfigured",
      "VITE_API_TOKEN is not set — copy .env.example to .env.local and add a token.",
      0,
    );
  }

  const res = await fetch(buildUrl(path, params), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      Accept: "application/json",
    },
  });

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
