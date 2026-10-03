import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSidebarSettings } from "@/lib/dataProvider";
import { API_BASE } from "@/lib/api";

/** The query key the sidebar and the Sidebar settings screen share, so a
 *  save repaints the sidebar at once. */
export const SIDEBAR_SETTINGS_KEY = ["sidebar-settings"] as const;

const NONE: ReadonlySet<string> = new Set();

/**
 * The item keys THIS TENANT has switched off (handoff 48) — the second axis
 * beside the person's scopes.
 *
 * Hides nothing until the answer arrives, and nothing when it cannot be had:
 * this is presentation, and a server that predates the route (a frontend
 * rolled out ahead of its backend answers 404) must leave the sidebar as it
 * was, not empty it. `retry: false` because it is chrome on every screen.
 */
export function useTenantHidden(): ReadonlySet<string> {
  const { data } = useQuery({
    queryKey: SIDEBAR_SETTINGS_KEY,
    queryFn: fetchSidebarSettings,
    staleTime: 60_000,
    // The sidebar is mounted for the whole session and never remounts on
    // navigation, so a stale answer would otherwise stand until a reload.
    refetchInterval: 5 * 60_000,
    retry: false,
  });
  return useMemo(
    () => (data?.hidden_items ? new Set(data.hidden_items) : NONE),
    [data],
  );
}

/** The item keys this tenant hides, read with a token that is not stored
 *  yet — for `login()`'s `beforeStore`, so the landing page is decided
 *  before the app renders (handoff 48). Unreadable means nothing hidden: a
 *  landing page is presentation, and failing to read a presentation setting
 *  must not stop anybody getting in. */
export async function tenantHiddenWith(accessToken: string): Promise<Set<string>> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/sidebar`, {
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
    });
    if (!res.ok) return new Set();
    const body = await res.json();
    return new Set<string>(body?.data?.hidden_items ?? []);
  } catch {
    return new Set();
  }
}
