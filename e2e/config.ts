/**
 * Shared configuration for the Cadra E2E suite.
 *
 * The SPA is served at  <ORIGIN>/app/   (nginx static bundle)
 * The REST API lives at  <ORIGIN>/api/v1/*   (proxied to Odoo)
 *
 * Default target is the local Jaiz tenant. Override with env vars to point at
 * gtb / staging / a remote host without touching code.
 */

export const ORIGIN =
  process.env.E2E_ORIGIN ?? "http://jaizbankplc.localhost:8069";

/** SPA base path (wouter base). The static bundle is built with BASE_PATH=/app/. */
export const APP_BASE = process.env.E2E_APP_BASE ?? "/app";

/**
 * Seed/admin login used for authenticated flows.
 *
 * The default pair is `admin`/`admin` and it survives ONLY while the origin is
 * local. `ORIGIN` above is env-overridable to any host, so a default credential
 * next to it is a production credential waiting for an environment variable:
 * point `E2E_ORIGIN` at staging, forget `E2E_PASS`, and this suite tries the
 * tenant's admin account with a password published in this repository — and,
 * on the run where it works, drives a real tenant.
 *
 * The rule from handoff 17 is that a credential may default to nothing and
 * never to something. This is the dev-tooling exception the handoff allowed,
 * and the exception is scoped to the case that makes it harmless: a localhost
 * origin, where `admin`/`admin` is what bootstrap created and there is nothing
 * to protect. Anywhere else the variable is required, and the refusal names it.
 */
function isLocalOrigin(origin: string): boolean {
  let host: string;
  try {
    host = new URL(origin).hostname.toLowerCase();
  } catch {
    // An origin we cannot parse is an origin we cannot vouch for.
    return false;
  }
  // `jaizbankplc.localhost` is the local multi-tenant spelling (host-based
  // dbfilter), so the suffix match is the rule and not a convenience — but it
  // must be a LABEL boundary: `localhost.example.com` and `notlocalhost` are
  // not local, and a bare `endsWith("localhost")` says they are.
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host === "[::1]"
  );
}

function credential(name: string, value: string | undefined): string {
  if (value) return value;
  if (isLocalOrigin(ORIGIN)) return "admin";
  throw new Error(
    `${name} is not set and E2E_ORIGIN is ${ORIGIN}, which is not local. ` +
      `The admin/admin default exists for a localhost tenant only — set ` +
      `${name} (and E2E_USER/E2E_PASS as a pair) for a remote target.`,
  );
}

export const USER = credential("E2E_USER", process.env.E2E_USER);
export const PASS = credential("E2E_PASS", process.env.E2E_PASS);

/** Storage-state file produced by global-setup and reused by every spec. */
export const STORAGE_STATE = ".auth/jaiz.json";

/** Build an absolute in-app path, e.g. appPath("/assets/list") -> "/app/assets/list". */
export function appPath(path: string): string {
  if (path === "/" || path === "") return `${APP_BASE}/`;
  return `${APP_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
