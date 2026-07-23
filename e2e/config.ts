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

/** Seed/admin login used for authenticated flows. */
export const USER = process.env.E2E_USER ?? "admin";
export const PASS = process.env.E2E_PASS ?? "admin";

/** Storage-state file produced by global-setup and reused by every spec. */
export const STORAGE_STATE = ".auth/jaiz.json";

/** Build an absolute in-app path, e.g. appPath("/assets/list") -> "/app/assets/list". */
export function appPath(path: string): string {
  if (path === "/" || path === "") return `${APP_BASE}/`;
  return `${APP_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
