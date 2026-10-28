import { useQuery } from "@tanstack/react-query";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { ADMIN_OVERRIDE_KEY, fetchAdminOverride, type AdminOverrideSetting } from "@/lib/adminOverride";

/**
 * Whether the signed-in person acts under the administrator override
 * (handoff 70): their token carries `admin` — which, for a person, comes from
 * exactly `base.group_system` — AND the tenant's switch is on.
 *
 * Only an administrator asks the server; anybody else is answered `false`
 * without a request, so with the switch off or for a non-administrator no
 * page draws anything differently. Unreadable means off: this decides what
 * is drawn, and the server decides every act.
 */
export function useAdminOverride(): { active: boolean; isSystemAdmin: boolean; setting: AdminOverrideSetting | null } {
  const scopes = useScopes();
  const isSystemAdmin = scopes.all.includes(SCOPE.admin);
  const { data } = useQuery({
    queryKey: ADMIN_OVERRIDE_KEY,
    queryFn: fetchAdminOverride,
    enabled: isSystemAdmin,
    staleTime: 60_000,
    retry: false,
  });
  const setting = isSystemAdmin ? (data ?? null) : null;
  return { active: isSystemAdmin && setting?.enabled === true, isSystemAdmin, setting };
}
