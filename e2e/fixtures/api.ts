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

  private headers() {
    return { Authorization: `Bearer ${this.token}`, Accept: "application/json" };
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
