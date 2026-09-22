import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { ORIGIN, USER, PASS } from "../config";

/**
 * Thin REST client against the Cadra v1 API. Used by specs to discover REAL
 * record IDs/tags dynamically (so tests aren't brittle to seed data) and to
 * set up preconditions. Mirrors the SPA's own envelope handling.
 */
export class ApiClient {
  private constructor(
    private ctx: APIRequestContext,
    public token: string,
    public scope: string,
  ) {}

  static async login(): Promise<ApiClient> {
    const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
    const res = await ctx.post("/api/v1/auth/login", {
      data: { login: USER, password: PASS },
      headers: { "Content-Type": "application/json", Accept: "application/json" },
    });
    if (!res.ok()) {
      throw new Error(`API login failed: HTTP ${res.status()} — ${await res.text()}`);
    }
    const body = await res.json();
    const token = body?.data?.access_token;
    if (!token) throw new Error(`API login: no access_token in response`);
    return new ApiClient(ctx, token, body?.data?.scope ?? "");
  }

  /**
   * A SECOND identity, for the one thing one identity cannot test.
   *
   * Handoff 35 refuses self-approval in the model, so the user who raises a
   * request can never approve it — and this suite has exactly one login
   * (`admin`). Proving the approve journey therefore needs somebody else,
   * and there is no user-creation endpoint in the API to make one with.
   *
   * So it uses a SERVICE CREDENTIAL, which since handoff 08 has its own
   * `res.users` distinct from `admin`: the client-credentials pair issues a
   * token for that user, it raises the request naming `admin` as the
   * approver, and `admin` approves it in the browser. That is the real
   * journey — two people — rather than a simulation of it.
   *
   * **Defaults to nothing, never to something**, which is handoff 17's rule
   * and the reason this is not wired to `docs/api/.creds.test19` by default:
   * `ORIGIN` is env-overridable to any host, and a credential baked in next
   * to it is a production credential waiting for an environment variable.
   * Absent → null, and every spec that needs it skips with a reason naming
   * the variables.
   */
  static async forServiceCredential(): Promise<ApiClient | null> {
    const id = process.env.E2E_CLIENT_ID;
    const secret = process.env.E2E_CLIENT_SECRET;
    if (!id || !secret) return null;
    const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
    const res = await ctx.post("/api/v1/auth/token", {
      data: { client_id: id, client_secret: secret },
      headers: { "Content-Type": "application/json", Accept: "application/json" },
    });
    if (!res.ok()) return null;
    const body = await res.json();
    const token = body?.data?.access_token;
    if (!token) return null;
    return new ApiClient(ctx, token, body?.data?.scope ?? "");
  }

  private headers() {
    return { Authorization: `Bearer ${this.token}`, Accept: "application/json" };
  }

  // ── Approvals (handoff 35) ────────────────────────────────────────

  /**
   * Whether THIS tenant needs a second person to agree to a move.
   *
   * Asked of the server on every run rather than assumed, because the
   * answer differs per tenant and **absent means required** — so a tenant
   * nobody has configured (which is every tenant on this machine) answers
   * `true`. A spec that hard-coded either answer would pass on one tenant
   * and lie on the next.
   */
  async approvalRequired(): Promise<boolean> {
    const probe = await this.probe("/api/v1/settings/approvals");
    // Unreadable → treat as required, the same direction the server and the
    // front end both fail in. A spec that guessed "not required" here would
    // assert the asset moved and fail confusingly.
    if (!probe.ok) return true;
    return probe.body?.data?.required !== false;
  }

  /** Somebody this caller may ask to approve, or null. */
  async anApprover(): Promise<{ id: number; name: string } | null> {
    const list = await this.get<any[]>("/api/v1/approvals/approvers", { limit: 5 });
    return list?.[0] ?? null;
  }

  /** Whoever is holding this credential. Used to name the OTHER party. */
  async whoami(): Promise<any> {
    return this.get("/api/v1/auth/whoami");
  }

  /**
   * Move an asset FOR REAL on a tenant that requires approval: raise, then
   * approve as `approver`. Returns the request id.
   *
   * `approver` must be a different ApiClient — the model refuses
   * self-approval under sudo and as SUPERUSER, so there is no shortcut.
   */
  async moveWithApproval(assetId: number | string, toLocationId: number,
                         approver: ApiClient, approverUserId: number,
                         reason = "e2e") {
    const raised = await this.post(`/api/v1/assets/${assetId}/move`, {
      to_location_id: toLocationId, approver_id: approverUserId, reason,
    });
    if (!raised?.pending_approval) return null;       // tenant has it off
    await approver.post(`/api/v1/approvals/${raised.request.id}/approve`, {});
    return raised.request.id as number;
  }

  async transferCustodyWithApproval(assetId: number | string, toCustodianId: number,
                                    approver: ApiClient, approverUserId: number,
                                    reason = "e2e") {
    const raised = await this.post(`/api/v1/assets/${assetId}/transfer-custody`, {
      to_custodian_id: toCustodianId, approver_id: approverUserId, reason,
    });
    if (!raised?.pending_approval) return null;
    await approver.post(`/api/v1/approvals/${raised.request.id}/approve`, {});
    return raised.request.id as number;
  }

  /** GET an enveloped endpoint; returns the `data` payload. */
  async get<T = any>(path: string, params?: Record<string, string | number>): Promise<T> {
    const res = await this.ctx.get(path, { headers: this.headers(), params: params as any });
    const body = await res.json().catch(() => ({}));
    if (!res.ok()) {
      throw new Error(`GET ${path} → HTTP ${res.status()}: ${JSON.stringify(body).slice(0, 200)}`);
    }
    return (body?.data ?? body) as T;
  }

  /** Raw GET returning {status, body} — for probing endpoints without throwing. */
  async probe(path: string, params?: Record<string, string | number>) {
    const res = await this.ctx.get(path, { headers: this.headers(), params: params as any });
    const body = await res.json().catch(() => null);
    return { status: res.status(), ok: res.ok(), body };
  }

  async post<T = any>(path: string, data: unknown, idempotencyKey?: string): Promise<T> {
    const headers: Record<string, string> = { ...this.headers(), "Content-Type": "application/json" };
    if (idempotencyKey) headers["X-Idempotency-Key"] = idempotencyKey;
    const res = await this.ctx.post(path, { headers, data });
    const body = await res.json().catch(() => ({}));
    if (!res.ok()) {
      throw new Error(`POST ${path} → HTTP ${res.status()}: ${JSON.stringify(body).slice(0, 200)}`);
    }
    return (body?.data ?? body) as T;
  }

  async patch<T = any>(path: string, data: unknown): Promise<T> {
    const headers: Record<string, string> = { ...this.headers(), "Content-Type": "application/json" };
    const res = await this.ctx.patch(path, { headers, data });
    const body = await res.json().catch(() => ({}));
    if (!res.ok()) {
      throw new Error(`PATCH ${path} → HTTP ${res.status()}: ${JSON.stringify(body).slice(0, 200)}`);
    }
    return (body?.data ?? body) as T;
  }

  /** Raw DELETE returning {status, body} — for CLEANUP in a `finally`, where
   *  throwing would replace the failure the test is about with this one. */
  async delete(path: string) {
    const res = await this.ctx.delete(path, { headers: this.headers() });
    const body = await res.json().catch(() => null);
    return { status: res.status(), ok: res.ok(), body };
  }

  // ── Discovery helpers ──────────────────────────────────────────────────────

  async brand(): Promise<any> {
    const res = await this.ctx.get("/api/v1/brand");
    const body = await res.json();
    return body?.data ?? body;
  }

  async assets(limit = 20): Promise<any[]> {
    const data = await this.get<any[]>("/api/v1/assets", { limit });
    return Array.isArray(data) ? data : [];
  }

  async firstAsset(): Promise<any | null> {
    const list = await this.assets(1);
    return list[0] ?? null;
  }

  /**
   * A valid nrs.asset.category id, discovered from existing data. Creating an
   * asset requires category_id (the API rejects name-only with 400), and there
   * is no category list endpoint, so we borrow one from a seeded asset.
   */
  async firstCategoryId(): Promise<number | null> {
    const list = await this.assets(20);
    for (const a of list) {
      const cid = a?.category?.id ?? a?.category_id;
      if (Number.isFinite(Number(cid))) return Number(cid);
    }
    return null;
  }

  /** Create a minimal valid asset (name + required category_id). */
  async createAsset(name: string, extra: Record<string, unknown> = {}): Promise<any> {
    const category_id = await this.firstCategoryId();
    return this.post("/api/v1/assets", { name, category_id, ...extra });
  }

  /** First asset that carries a scannable tag — needed by the barcode specs. */
  async firstAssetWithTag(): Promise<any | null> {
    const list = await this.assets(50);
    return list.find((a) => a.asset_tag || a.asset_code) ?? null;
  }

  async locations(limit = 20): Promise<any[]> {
    const data = await this.get<any[]>("/api/v1/locations", { limit });
    return Array.isArray(data) ? data : [];
  }

  async firstLocation(): Promise<any | null> {
    const list = await this.locations(1);
    return list[0] ?? null;
  }

  /** Two distinct locations — needed to exercise the asset "move" flow. */
  async twoLocations(): Promise<any[]> {
    const list = await this.locations(10);
    return list.slice(0, 2);
  }

  /**
   * Two distinct building-type locations (real branches). The move flow's
   * response mapper only handles locations that carry a building hierarchy —
   * see the reported adapters.ts bug — so tests move between buildings.
   */
  async twoBuildings(): Promise<any[]> {
    const list = await this.locations(60);
    const buildings = list.filter((l) => l.location_type === "building");
    return buildings.slice(0, 2);
  }

  async employees(limit = 20): Promise<any[]> {
    const data = await this.get<any[]>("/api/v1/identity/employees", { limit });
    return Array.isArray(data) ? data : [];
  }

  async firstEmployee(): Promise<any | null> {
    const list = await this.employees(1);
    return list[0] ?? null;
  }

  async requests(limit = 20): Promise<any[]> {
    const data = await this.get<any[]>("/api/v1/requests", { limit });
    return Array.isArray(data) ? data : [];
  }

  async firstRequest(): Promise<any | null> {
    const list = await this.requests(1);
    return list[0] ?? null;
  }

  async dispose() {
    await this.ctx.dispose();
  }
}
