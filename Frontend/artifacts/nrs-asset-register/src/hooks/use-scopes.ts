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

/** Scope names, kept in step with myservice_api/controllers/utils.py. */
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
  /** The employee import and the SAP employee sync. */
  integrationsWrite: "integrations:write",
  /** The wildcard. Pages under Administration require it (handoff 41). */
  admin: "admin",
} as const;
