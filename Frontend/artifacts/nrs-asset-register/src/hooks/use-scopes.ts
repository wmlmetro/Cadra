import { useCallback, useEffect, useState } from "react";
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

  const isAdmin = scopes.some((s) => WILDCARDS.includes(s));
  const has = useCallback(
    (scope: string) => isAdmin || scopes.includes(scope),
    [scopes, isAdmin],
  );
  const hasAll = useCallback(
    (...wanted: string[]) => wanted.every((s) => isAdmin || scopes.includes(s)),
    [scopes, isAdmin],
  );

  return { has, hasAll, all: scopes, isAdmin };
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
  dashboardsRead: "dashboards:read",
  identityRead: "identity:read",
  /** The wildcard. Pages under Administration require it (handoff 41). */
  admin: "admin",
} as const;
