/**
 * The app's navigation table, and the two questions asked of it: may this
 * person open that page, and which page do they land on after signing in.
 *
 * It lived inside `Sidebar.tsx` until handoff 46, when the landing rule
 * needed the same scopes the sidebar filters by. One table, read by both, so
 * the page a person lands on can never be one the sidebar does not offer them.
 */
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, ScanBarcode, Upload, RefreshCw,
  Wrench, Tag, Monitor, TrendingDown, SlidersHorizontal, Layers, Palette,
  Hourglass, ShieldCheck, History,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  /** Draws a live count beside the label. One value today; it is a named
   *  marker rather than a number on the item so the count stays a query and
   *  not a constant somebody forgets to update. */
  badge?: "approvals";
  /** The scope(s) the SERVER requires for what this page is for — all of
   *  them (a string is one). Required on every item since handoff 46: before
   *  it only the Administration entries carried one, so a Tag-Issuing Unit
   *  was offered Fleet, Staff Bus and every report and opened each on a
   *  refusal. The server still decides; this only stops drawing a door for
   *  somebody who cannot open it. */
  scope: string | string[];
}

export interface NavGroup { label: string; items: NavItem[] }

/** What `canOpen` needs: `useScopes()` and `currentScopes()` both fit. */
export interface ScopeCheck { has(scope: string): boolean }

// Every item declares the scope(s) the server requires for what the page is
// for. Hiding is a courtesy; the server's refusal is the permission (handoff
// 46), and a hidden page typed into the address bar must still be refused.
//
// Where a scope admits a page that is not the role's job, that is left as it
// is: `dashboards:read` admits Fleet, Staff Bus (and Security / FM, were they
// drawn) to every Asset User and Auditor, and `identity:read` admits Access
// changes to every Asset User. That is a finding about the role model,
// recorded in docs/handoffs/46-REPORT.md — not something to fix here by
// inventing a scope the server does not have.
export const ALL_NAV_GROUPS: NavGroup[] = [
  { label: "Dashboards", items: [
    // Four scopes because it reads four things: assets, locations, employees
    // and the dashboard aggregates (`fetchTotals` + `/dashboard/kpis`).
    { name: "Facility Command Center", path: "/",                     icon: LayoutDashboard, scope: ["assets:read", "locations:read", "identity:read", "dashboards:read"] },
    // Hidden for now (routes still work via direct URL). Would need
    // "dashboards:read", which every Asset User and Auditor holds:
    // { name: "FM Operations",           path: "/dashboards/fm",        icon: Activity,        scope: "dashboards:read" },
    { name: "Fleet Command",           path: "/dashboards/fleet",     icon: Car,             scope: "dashboards:read" },
    { name: "IT Assets Command",       path: "/dashboards/it",        icon: Monitor,         scope: ["assets:read", "dashboards:read"] },
    // Hidden for now; would need "dashboards:read", as FM Operations would:
    // { name: "Security Operations",     path: "/dashboards/security",  icon: ShieldAlert,     scope: "dashboards:read" },
  ]},
  // Service Desk group hidden in its entirety for now. Routes (/service-desk,
  // /service-desk/triage, /service-desk/new, /service-desk/:id) still resolve
  // via direct URL — only the sidebar entries are gone.
  { label: "Asset Register", items: [
    { name: "Dashboard",               path: "/assets",               icon: LayoutDashboard, scope: ["assets:read", "dashboards:read"] },
    { name: "All Assets",              path: "/assets/list",          icon: BookOpen,        scope: "assets:read" },
    // Under the register rather than in a group of its own: an approval here
    // is always about an asset, and a person who has just been asked to agree
    // to a move looks where the assets are. The badge is what makes it a
    // queue rather than a page — an approval nobody notices is a move that
    // never happens (handoff 35).
    { name: "Approvals",               path: "/approvals",            icon: Hourglass, badge: "approvals", scope: "assets:read" },
    { name: "+ New Asset",             path: "/assets/new",           icon: BookOpen,        scope: "assets:write" },
  ]},
  { label: "Operations", items: [
    { name: "Locations",               path: "/locations",            icon: MapPin,          scope: "locations:read" },
    { name: "+ New Location",          path: "/locations/new",        icon: MapPin,          scope: "locations:write" },
  ]},
  { label: "HR & Staff", items: [
    { name: "Employees",               path: "/hr/employees",         icon: Users,           scope: "identity:read" },
    { name: "SAP Sync",                path: "/hr/sap-sync",          icon: RefreshCw,       scope: "identity:read" },
    { name: "Bulk Import",             path: "/hr/import",            icon: Upload,          scope: "integrations:write" },
    { name: "Identity (clearance)",    path: "/hr/identity",          icon: Fingerprint,     scope: "identity:read" },
  ]},
  { label: "Fleet & Transport", items: [
    { name: "Fleet",                   path: "/fleet",                icon: Car,             scope: "dashboards:read" },
    { name: "Staff Bus",               path: "/fleet/staff-bus",      icon: Bus,             scope: "dashboards:read" },
  ]},
  { label: "Reports", items: [
    { name: "Fleet Roster",            path: "/reports/fleet-roster",          icon: Car,          scope: "dashboards:read" },
    { name: "Asset Inventory",         path: "/reports/asset-inventory",       icon: BookOpen,     scope: "dashboards:read" },
    { name: "Maintenance Readiness",   path: "/reports/maintenance-readiness", icon: Wrench,       scope: "dashboards:read" },
    { name: "Location Coverage",       path: "/reports/location-coverage",     icon: MapPin,       scope: ["dashboards:read", "locations:read"] },
    { name: "Tag Adoption",            path: "/reports/tag-adoption",          icon: Tag,          scope: "assets:read" },
    { name: "Depreciation",            path: "/reports/depreciation",          icon: TrendingDown, scope: "dashboards:read" },
  ]},
  // `settings:write`, not a read scope: these screens exist to CHANGE the
  // configuration. Their reads are served under `assets:read` because other
  // screens need the categories and the brand, so what is withheld from a
  // person without the write is the change, and the page is the change.
  { label: "Settings", items: [
    { name: "Asset Categories",        path: "/settings/categories",   icon: Layers,            scope: "settings:write" },
    { name: "Branding",                path: "/settings/branding",     icon: Palette,           scope: "settings:write" },
    { name: "Depreciation",            path: "/settings/depreciation", icon: SlidersHorizontal, scope: "settings:write" },
  ]},
  // Its own group since handoff 46, out from under Administration: the
  // report is served under `identity:read`, and reading it is the Auditor's
  // job, who is not a system administrator. The path is unchanged so
  // existing links (the Users page's filter chip) keep working.
  { label: "Audit", items: [
    { name: "Access changes",          path: "/admin/access-changes",  icon: History,     scope: "identity:read" },
  ]},
  // Who holds which role, and changing it (handoffs 41–43): administrators.
  { label: "Administration", items: [
    { name: "Users",                   path: "/admin/users",           icon: ShieldCheck, scope: "admin" },
  ]},
  { label: "Tools", items: [
    { name: "Barcode Station",         path: "/tools/barcode",        icon: ScanBarcode, scope: "assets:read" },
  ]},
];

/** True when the session holds every scope `required` names (a wildcard
 *  holds them all — that is `has`'s job, not this function's). */
export function canOpen(scopes: ScopeCheck, required: string | string[]): boolean {
  const wanted = Array.isArray(required) ? required : [required];
  return wanted.every((s) => scopes.has(s));
}

/** The scope(s) the table declares for exactly this path, or null when the
 *  path is not in the table. */
export function requiredScopesFor(path: string): string | string[] | null {
  for (const g of ALL_NAV_GROUPS) {
    for (const it of g.items) {
      if (it.path === path) return it.scope;
    }
  }
  return null;
}

/** Where a person goes after signing in, best first. */
const LANDING_ORDER = ["/assets", "/assets/list", "/locations", "/hr/employees", "/dashboards/fleet"];

/** The page shown when the session holds no scope that opens any of them. */
export const NO_ACCESS_PATH = "/no-access";

/**
 * The page somebody lands on after signing in.
 *
 * The owner asked for the asset register's dashboard rather than `/`. The
 * rule is "the best page this person can actually open", not "the asset
 * dashboard", because a Tag-Issuing Unit alone holds `tagging:write` and
 * nothing else — sent to `/assets`, the first thing a tagger would see after
 * signing in is a refusal. Judged from the same table as the sidebar, so
 * there is no second copy of which scope opens which page.
 */
export function landingPath(scopes: ScopeCheck): string {
  for (const path of LANDING_ORDER) {
    const required = requiredScopesFor(path);
    if (required != null && canOpen(scopes, required)) return path;
  }
  return NO_ACCESS_PATH;
}
