import { useEffect, useMemo, useState } from "react";
import { getScope } from "@/lib/auth";

/**
 * What the signed-in user is allowed to do, from the scopes the API minted
 * into their token.
 *
 * The server is the authority — every scoped endpoint returns 403 on its own.
 * This exists so the interface does not offer an action that is going to be
 * refused: an Auditor should not see a Dispose button at all, rather than see
 * it and get an error.
 *
 * `admin` and `*` are wildcards, matching require_jwt on the server.
 */

const WILDCARDS = ["admin", "*"];

function readScopes(): string[] {
  return (getScope() ?? "").split(" ").filter(Boolean);
}

export interface Scopes {
  /** True if the token carries this scope, or a wildcard. */
  has: (scope: string) => boolean;
  /** True if the token carries every one of these scopes. */
  hasAll: (...scopes: string[]) => boolean;
  /** Everything the token carries, for display and debugging. */
  all: string[];
  /** True when the token is a wildcard — a system administrator. */
  isAdmin: boolean;
}

/** The same answers as `useScopes`, for a list in hand. */
export function scopesOf(scopes: string[]): Scopes {
  const isAdmin = scopes.some((s) => WILDCARDS.includes(s));
  return {
    has: (scope: string) => isAdmin || scopes.includes(scope),
    hasAll: (...wanted: string[]) => wanted.every((s) => isAdmin || scopes.includes(s)),
    all: scopes,
    isAdmin,
  };
}

/**
 * The stored scopes NOW, outside React. For the moment straight after a
 * sign-in, when the page decides where to go before any component has
 * re-rendered on the new token (handoff 46's landing rule). Wildcards count
 * exactly as they do in `useScopes`.
 */
export function currentScopes(): Scopes {
  return scopesOf(readScopes());
}

export function useScopes(): Scopes {
  const [scopes, setScopes] = useState<string[]>(readScopes);

  useEffect(() => {
    // Scopes change on login, on logout, and on token refresh — refresh
    // re-derives them from the user's groups, so a role change lands here
    // within an access-token lifetime rather than at next sign-in.
    const sync = () => setScopes(readScopes());
    window.addEventListener("cadra:auth-changed", sync);
    return () => window.removeEventListener("cadra:auth-changed", sync);
  }, []);

  return useMemo(() => scopesOf(scopes), [scopes]);
}

/** Scope names, kept in step with myservice_api/controllers/utils.py —
 *  ALL of them, held there by `tests/test_scope_maps.py` (handoff 52 §6a):
 *  a scope renamed server-side used to fail here silently, in the one place
 *  that decides what a person sees. The map is complete even where the SPA
 *  never gates on an entry (`ingestion:write` is Vendra's, `webhooks:admin`
 *  an integration's), because "complete except where it isn't" is exactly
 *  the state the guard exists to refuse. */
export const SCOPE = {
  assetsRead: "assets:read",
  assetsWrite: "assets:write",
  locationsRead: "locations:read",
  locationsWrite: "locations:write",
  requestsRead: "requests:read",
  requestsWrite: "requests:write",
  approvalsWrite: "approvals:write",
  /** The asset register's own figures (KPIs, map, depreciation report). */
  dashboardsRead: "dashboards:read",
  /** The operational dashboards outside the register: fleet, staff bus,
   *  facilities, security. Split out of `dashboards:read` by handoff 47. */
  operationsRead: "operations:read",
  identityRead: "identity:read",
  /** The access-changes report — who granted whom which role. Split out of
   *  `identity:read` by handoff 47: the Auditor's, not every Asset User's. */
  accessRead: "access:read",
  /** The Tag-Issuing Unit's job: mint a label, request its replacement,
   *  confirm it affixed (three routes since handoff 47). */
  taggingWrite: "tagging:write",
  /** Categories, branding and the depreciation settings. */
  settingsWrite: "settings:write",
  /** Reading the configuration — the configuration-changes report (handoff
   *  49). Held by the Auditor and the Asset Manager; `settings:write` does
   *  not imply it on the token, the two are granted side by side. */
  settingsRead: "settings:read",
  /** Taking a copy of the register — both export routes (handoff 50 ruling
   *  1). The Auditor's alone (plus the `admin` wildcard): reading the
   *  register is not the same act as walking out with a file of it. Kept in
   *  step with myservice_api/controllers/utils.py, like every entry here. */
  exportRead: "export:read",
  /** The employee import and the SAP employee sync. */
  integrationsWrite: "integrations:write",
  /** INT-03 — Vendra's receipt hand-off. No SPA page gates on it; it is
   *  here so this map is the server's list, whole. */
  ingestionWrite: "ingestion:write",
  /** Webhook administration. No SPA page gates on it either. */
  webhooksAdmin: "webhooks:admin",
  /** The wildcard. Pages under Administration require it (handoff 41). */
  admin: "admin",
} as const;
