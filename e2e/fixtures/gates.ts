import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { request as pwRequest, type APIRequestContext } from "@playwright/test";
import { ORIGIN } from "../config";
import type { ApiClient } from "./api";

/**
 * An asset ON THE REGISTER, whichever way the tenant's switch is set.
 *
 * Handoff 58 §2 — the browser suite's twin of `tests/gates.py`, the one
 * helper named in `docs/DECISIONS.md` (2026-10-12), and built the same way.
 * With the receipt gates on (`cadra.receipt.gated`), `POST /api/v1/assets`
 * answers a CANDIDATE: `captured`, no label, hidden from every list. A spec
 * that is ABOUT an asset already on the register therefore gets one by
 * walking it through the seven gates — over HTTP, as seven different people,
 * because the no-two-gates rule (Addendum A §4) refuses one person at the
 * second gate — exactly as a real unit gets there. With the switch off every
 * call here is a no-op and every spec sees what it always saw.
 *
 * The entry points, and only these:
 *
 *  - `receive(api, body)` — `POST /assets` as INT-03 makes it. With the gates
 *    on, the class's identification (Section 12: a serial and make/model for
 *    a `serial` class, the attributes for a `tag_id` one) is supplied when
 *    the spec did not, because a spec about something else must not fail at
 *    the door. Switch off: the body as given.
 *  - `onTheRegister(api, asset)` — drives the gates from wherever the unit is
 *    to `registered`; returns the asset as it now stands.
 *  - `readyToAffix(api, asset)` — drives it to `tag_issued`: a label issued
 *    and not yet on the unit, which is what a spec ABOUT affixing needs.
 *    Switch off, a new asset is already there.
 *  - `newRegisteredAsset(api, body)` — `receive` then `onTheRegister`, the
 *    usual fixture; `ApiClient.createAsset` is this.
 *
 * The seven people are the demo personas (`docs/api/.personas.<tenant>`,
 * handoffs 46/57): storekeeper submits, IAD officer verifies, IAD approver
 * approves, Asset Controller requests the tag, tagger affixes, Register Maker
 * registers, Register Checker approves. A tenant with the gates on and no
 * personas file FAILS saying so — never skips: a skip would turn a switch-on
 * run green by proving nothing.
 *
 * No persona password is ever printed: only keys and statuses reach a message.
 */

const TENANT = new URL(ORIGIN).hostname.split(".")[0];
const PERSONAS = process.env.E2E_PERSONAS
  ?? path.resolve(__dirname, `../../docs/api/.personas.${TENANT}`);

/** Persona key per gate, in the order the chain fires them. */
export const CREW = [
  ["submit", "storekeeper"],
  ["verify", "iad_officer"],
  ["approve", "iad_approver"],
  ["request-tagging", "asset_controller"],
  ["affix", "tagger"],
  ["register", "register_maker"],
  ["approve-registration", "register_checker"],
] as const;

/** The CREW index of the gate that moves a unit FROM each state. */
const FROM: Record<string, number> = {
  captured: 0, vfm_pending: 1, vfm_verified: 2, vfm_approved: 3,
  tag_requested: 4, tag_issued: 4, tagged: 5, reg_submitted: 6,
};

const uniq = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;

/** The tenant's switch, read NOW — specs turn it on and off. */
export async function receiptGated(api: ApiClient): Promise<boolean> {
  const s = await api.get<any>("/api/v1/settings");
  return s?.receipt_gated === true;
}

/** `{mode, mandatory}` for a category, from the published schema. */
async function classNeeds(api: ApiClient, categoryId: number) {
  const rows = await api.get<any[]>("/api/v1/asset-categories");
  const row = (rows ?? []).find((r) => Number(r.id) === Number(categoryId));
  return {
    mode: (row?.identification_mode as string) || "serial",
    mandatory: ((row?.class_attributes_schema?.mandatory as string[]) ?? []),
  };
}

/**
 * A class identified by SERIAL (Section 12) — for a spec that receives a unit
 * through the asset FORM, which has inputs for a serial, a make and a model
 * but none for a `tag_id` class's colour, material and dimensions. Category
 * 1 (the seed's first, as `tests/gates.py` uses) when it is one.
 */
export async function aSerialClass(api: ApiClient): Promise<number> {
  const rows = (await api.get<any[]>("/api/v1/asset-categories")) ?? [];
  const serial = rows.filter((r) => (r.identification_mode ?? "serial") === "serial");
  const one = serial.find((r) => Number(r.id) === 1) ?? serial[0];
  if (!one) throw new Error("no asset category on this tenant is identified by serial");
  return Number(one.id);
}

/**
 * The body `receive` sends, without sending it — for a spec that must make
 * the call itself (through the form, under an idempotency key, or expecting
 * a refusal). With the gates on, a body missing its serial is refused 400
 * `validation_failed` at the door, which is the same answer most refusal
 * specs assert, so a refusal spec sending a bare body would pass for the
 * wrong reason. Switch off: the body as given.
 */
export async function receiptBody(api: ApiClient, body: Record<string, any>) {
  const out: Record<string, any> = { ...body };
  if (!(await receiptGated(api))) return out;
  if (out.category_id == null) out.category_id = 1;
  const { mode, mandatory } = await classNeeds(api, out.category_id);
  if (mode === "serial" && !out.serial_number) out.serial_number = uniq("SN58E");
  for (const field of mandatory) if (!out[field]) out[field] = uniq(field).slice(0, 40);
  return out;
}

/** `POST /api/v1/assets`, filled in for the gates when they are on. */
export async function receive(api: ApiClient, body: Record<string, any>): Promise<any> {
  return api.post("/api/v1/assets", await receiptBody(api, body));
}

// ── the crew ──────────────────────────────────────────────────────────────

type Persona = { key: string; login: string; password: string };
type Session = { ctx: APIRequestContext; token: string };
const sessions = new Map<string, Session>();

function persona(key: string): Persona {
  if (!existsSync(PERSONAS)) {
    throw new Error(
      `The receipt gates are ON on ${TENANT} and ${PERSONAS} does not exist, so nothing can ` +
      `walk a unit through them: the chain needs seven different people. Seed the demo ` +
      `personas (scripts/demo_personas.sh ${TENANT} seed) or turn the switch off.`);
  }
  for (const line of readFileSync(PERSONAS, "utf8").split("\n")) {
    if (!line.trim() || line.startsWith("#")) continue;
    const [k, login, password] = line.trim().split(/\s+/);
    if (k === key && login && password) return { key: k, login, password };
  }
  throw new Error(`${PERSONAS} has no \`${key}\` persona — the gates need one.`);
}

async function session(key: string): Promise<Session> {
  const cached = sessions.get(key);
  if (cached) return cached;
  const p = persona(key);
  const ctx = await pwRequest.newContext({ baseURL: ORIGIN, ignoreHTTPSErrors: true });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { login: p.login, password: p.password },
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  if (!res.ok()) {
    throw new Error(`persona ${key} could not sign in: HTTP ${res.status()} ${(await res.text()).slice(0, 300)}`);
  }
  const token = (await res.json())?.data?.access_token;
  if (!token) throw new Error(`persona ${key} sign-in returned no access_token`);
  const s = { ctx, token };
  sessions.set(key, s);
  return s;
}

/** A persona's own bearer token — for a spec that signs a persona into the
 *  browser or calls as one. Never logged. */
export async function personaToken(key: string): Promise<string> {
  return (await session(key)).token;
}

async function asPersona(key: string, method: "GET" | "POST", p: string, data?: unknown) {
  const s = await session(key);
  const res = await s.ctx.fetch(`/api/v1${p}`, {
    method,
    headers: { Authorization: `Bearer ${s.token}`, Accept: "application/json", "Content-Type": "application/json" },
    data: method === "POST" ? (data ?? {}) : undefined,
  });
  return { status: res.status(), body: await res.json().catch(() => null) };
}

const today = () => new Date().toISOString().slice(0, 10);

async function fire(api: ApiClient, asset: any, action: string, key: string, until: string) {
  const id = asset.id;
  let res;
  if (action === "affix") {
    const body: Record<string, unknown> = { tag_number: asset?.tagging?.tag_number };
    if (asset.identification_mode === "tag_id") body.attributes_confirmed = true;
    else if (asset.serial_number) body.serial_number = asset.serial_number;
    res = await asPersona(key, "POST", `/assets/${id}/tag-affixed`, body);
  } else {
    let body: Record<string, unknown> = {};
    if (action === "verify") {
      body = {
        checklist: { quantity: true, specification: true, condition: true, price: true },
        attachments: [{ name: "sighted.txt", mimetype: "text/plain", data: Buffer.from("sighted").toString("base64") }],
      };
    } else if (action === "register") {
      // The unit's OWN cost when it has one: the Register Maker's figure is
      // written onto `acquisition_cost`, and a spec that created an asset at
      // a cost must not find the walk has restated it.
      const own = Number(asset?.financial?.acquisition_cost ?? 0);
      body = {
        sap_asset_code: uniq("SAP58E").slice(0, 30),
        cost: own > 0 ? own : 1000,
        cost_centre: "CC-58",
        capitalisation_date: today(),
        asset_class: asset?.category?.id ?? asset?.category_id ?? 1,
      };
    }
    res = await asPersona(key, "POST", `/assets/${id}/gates/${action}`, body);
  }
  if (res.status !== 200) {
    throw new Error(
      `gate ${action} as ${key} on asset ${id} (walking to ${until}): HTTP ${res.status} ` +
      JSON.stringify(res.body?.error ?? res.body).slice(0, 400));
  }
  return api.get<any>(`/api/v1/assets/${id}`);
}

async function walk(api: ApiClient, asset: any, until: string) {
  const state = asset?.register_state ?? "registered";
  if (state === "registered" || state === until) return asset;
  if (!(state in FROM)) throw new Error(`cannot walk a unit at "${state}" to ${until}`);
  for (const [action, key] of CREW.slice(FROM[state])) {
    asset = await fire(api, asset, action, key, until);
    if (asset.register_state === until) return asset;
  }
  if (asset.register_state !== until) throw new Error(`walk ended at ${asset.register_state}, not ${until}`);
  return asset;
}

/** The asset, registered. A no-op for a registered asset (switch off). */
export async function onTheRegister(api: ApiClient, asset: any): Promise<any> {
  return walk(api, asset, "registered");
}

/** The asset with a label issued and not yet affixed. A no-op for a
 *  registered asset (switch off: its label is issued at creation). */
export async function readyToAffix(api: ApiClient, asset: any): Promise<any> {
  if (asset?.register_state == null || asset.register_state === "registered") return asset;
  return walk(api, asset, "tag_issued");
}

/** `receive` then `onTheRegister` — the usual fixture. */
export async function newRegisteredAsset(api: ApiClient, body: Record<string, any>): Promise<any> {
  return onTheRegister(api, await receive(api, body));
}
