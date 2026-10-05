/**
 * The app's navigation table, and the two questions asked of it: may this
 * person open that page, and which page do they land on after signing in.
 *
 * It lived inside `Sidebar.tsx` until handoff 46, when the landing rule
 * needed the same scopes the sidebar filters by. One table, read by both, so
 * the page a person lands on can never be one the sidebar does not offer them.
 */
import {
  LayoutDashboard, MapPin, Car, BookOpen,
  Users, ScanBarcode, Upload, RefreshCw,
  Wrench, Tag, Monitor, TrendingDown, SlidersHorizontal, Layers, Palette,
  Hourglass, ShieldCheck, History, PanelLeft,
  FileCog, Trash2, Camera, Download,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  /** What this item IS, for the per-tenant switch (handoff 48): the key
   *  `PATCH /api/v1/settings/sidebar` names and a tenant's stored row is
   *  filed under. Declared here and in `SIDEBAR_GROUPS`
   *  (`myservice_api/controllers/v1_sidebar.py`), never derived — the label
   *  is reworded, the path re-routed and the scope re-ruled (handoff 47),
   *  and a key that followed any of them would switch an item a tenant had
   *  turned off back on the day it changed. Change it only by retiring the
   *  old one; `tests/test_sidebar_catalog.py` holds the two tables to it. */
  key: string;
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

export interface NavGroup {
  /** The group's switch, on the same terms as `NavItem.key`. */
  key: string;
  label: string;
  items: NavItem[];
}

/** What `canOpen` needs: `useScopes()` and `currentScopes()` both fit. */
export interface ScopeCheck { has(scope: string): boolean }

// Every item declares the scope(s) the server requires for what the page is
// for. Hiding is a courtesy; the server's refusal is the permission (handoff
// 46), and a hidden page typed into the address bar must still be refused.
//
// Where a scope admits a page that is not the role's job, that is a finding
// for the Architect, not something to fix here by inventing a scope the
// server does not have. Handoff 46 recorded two such findings and handoff 47
// ruled on both: the fleet screens now take `operations:read` (split out of
// `dashboards:read`, so an Asset User reading the register's figures is not
// also shown the fleet) and Access changes takes `access:read` (split out of
// `identity:read`, so the employee picker does not open the access record).
export const ALL_NAV_GROUPS: NavGroup[] = [
  { key: "dashboards", label: "Dashboards", items: [
    // Four scopes because it reads four things: assets, locations, employees
    // and the dashboard aggregates (`fetchTotals` + `/dashboard/kpis`).
    { key: "facility_command_center", name: "Facility Command Center", path: "/",                     icon: LayoutDashboard, scope: ["assets:read", "locations:read", "identity:read", "dashboards:read"] },
    // Hidden for now (routes still work via direct URL). Would take
    // "operations:read", the fleet/FM/security scope (handoff 47):
    // { name: "FM Operations",           path: "/dashboards/fm",        icon: Activity,        scope: "operations:read" },
    { key: "fleet_command",           name: "Fleet Command",           path: "/dashboards/fleet",     icon: Car,             scope: "operations:read" },
    { key: "it_assets_command",       name: "IT Assets Command",       path: "/dashboards/it",        icon: Monitor,         scope: ["assets:read", "dashboards:read"] },
    // Hidden for now; would take "operations:read", as FM Operations would:
    // { name: "Security Operations",     path: "/dashboards/security",  icon: ShieldAlert,     scope: "operations:read" },
  ]},
  // Service Desk group hidden in its entirety for now. Routes (/service-desk,
  // /service-desk/triage, /service-desk/new, /service-desk/:id) still resolve
  // via direct URL — only the sidebar entries are gone.
  { key: "asset_register", label: "Asset Register", items: [
    { key: "asset_dashboard",         name: "Dashboard",               path: "/assets",               icon: LayoutDashboard, scope: ["assets:read", "dashboards:read"] },
    { key: "all_assets",              name: "All Assets",              path: "/assets/list",          icon: BookOpen,        scope: "assets:read" },
    // Under the register rather than in a group of its own: an approval here
    // is always about an asset, and a person who has just been asked to agree
    // to a move looks where the assets are. The badge is what makes it a
    // queue rather than a page — an approval nobody notices is a move that
    // never happens (handoff 35).
    { key: "approvals",               name: "Approvals",               path: "/approvals",            icon: Hourglass, badge: "approvals", scope: "assets:read" },
    { key: "new_asset",               name: "+ New Asset",             path: "/assets/new",           icon: BookOpen,        scope: "assets:write" },
  ]},
  { key: "operations", label: "Operations", items: [
    { key: "locations",               name: "Locations",               path: "/locations",            icon: MapPin,          scope: "locations:read" },
    { key: "new_location",            name: "+ New Location",          path: "/locations/new",        icon: MapPin,          scope: "locations:write" },
  ]},
  { key: "hr_staff", label: "HR & Staff", items: [
    { key: "employees",               name: "Employees",               path: "/hr/employees",         icon: Users,           scope: "identity:read" },
    { key: "sap_sync",                name: "SAP Sync",                path: "/hr/sap-sync",          icon: RefreshCw,       scope: "identity:read" },
    { key: "bulk_import",             name: "Bulk Import",             path: "/hr/import",            icon: Upload,          scope: "integrations:write" },
    // Identity (clearance) left the menu in handoff 47 (§1b): the page
    // renders sample data built into the app and asks the server nothing,
    // so every new client was shown invented clearance records. The route
    // (/hr/identity) still serves, the key is retired in SIDEBAR_RETIRED,
    // and NRS is owed a real clearance screen (docs/GO-LIVE.md §25) — the
    // back office already has the mechanism (report 43 §G.2).
  ]},
  { key: "fleet_transport", label: "Fleet & Transport", items: [
    { key: "fleet",                   name: "Fleet",                   path: "/fleet",                icon: Car,             scope: "operations:read" },
    // Staff Bus left the menu in handoff 47 (§1b): it renders built-in
    // sample data and asks the server nothing. Route still serves; key
    // retired in SIDEBAR_RETIRED.
  ]},
  { key: "reports", label: "Reports", items: [
    { key: "fleet_roster",            name: "Fleet Roster",            path: "/reports/fleet-roster",          icon: Car,          scope: "operations:read" },
    { key: "asset_inventory",         name: "Asset Inventory",         path: "/reports/asset-inventory",       icon: BookOpen,     scope: "dashboards:read" },
    { key: "maintenance_readiness",   name: "Maintenance Readiness",   path: "/reports/maintenance-readiness", icon: Wrench,       scope: "operations:read" },
    { key: "location_coverage",       name: "Location Coverage",       path: "/reports/location-coverage",     icon: MapPin,       scope: ["dashboards:read", "locations:read"] },
    { key: "tag_adoption",            name: "Tag Adoption",            path: "/reports/tag-adoption",          icon: Tag,          scope: "assets:read" },
    { key: "depreciation_report",     name: "Depreciation",            path: "/reports/depreciation",          icon: TrendingDown, scope: "dashboards:read" },
  ]},
  // `settings:write`, not a read scope: these screens exist to CHANGE the
  // configuration. Their reads are served under `assets:read` because other
  // screens need the categories and the brand, so what is withheld from a
  // person without the write is the change, and the page is the change.
  { key: "settings", label: "Settings", items: [
    { key: "asset_categories",        name: "Asset Categories",        path: "/settings/categories",   icon: Layers,            scope: "settings:write" },
    { key: "branding",                name: "Branding",                path: "/settings/branding",     icon: Palette,           scope: "settings:write" },
    { key: "depreciation_settings",   name: "Depreciation",            path: "/settings/depreciation", icon: SlidersHorizontal, scope: "settings:write" },
    // Which of these items this tenant shows (handoff 48). `admin`, as the
    // server's PATCH is. The one item that cannot be switched off, with its
    // group: it is where they are switched back on.
    { key: "sidebar_settings",        name: "Sidebar",                 path: "/settings/sidebar",      icon: PanelLeft,         scope: "admin" },
  ]},
  // Its own group since handoff 46, out from under Administration: reading
  // the access record is the Auditor's job, who is not a system
  // administrator. `access:read` since handoff 47 — under `identity:read`
  // every Asset User was drawn the record of who granted whom which role.
  // The path is unchanged so existing links (the Users page's filter chip)
  // keep working.
  // The auditor's four other screens (handoff 49): the server has answered
  // these reports to her scopes for weeks with no page asking. Two carry
  // `assets:read` because that is what the SERVER requires — so they are
  // also drawn for every Asset User, which is a role-model observation for
  // the Architect, not a reason to invent a scope (the rule above). The
  // export stopped being one of them: handoff 50 ruling 1 gave BOTH export
  // routes their own `export:read` (the Auditor's, plus the wildcard),
  // because taking a copy of the whole register is a different act from
  // reading it. The KEY stays `register_export` — a key is never renamed
  // when an item is re-scoped (the rule on `NavItem.key`).
  { key: "audit", label: "Audit", items: [
    { key: "access_changes",          name: "Access changes",          path: "/admin/access-changes",  icon: History,     scope: "access:read" },
    { key: "configuration_changes",   name: "Configuration changes",   path: "/admin/configuration-changes", icon: FileCog, scope: "settings:read" },
    { key: "disposals_report",        name: "Disposals",               path: "/reports/disposals",     icon: Trash2,      scope: "assets:read" },
    { key: "register_snapshot",       name: "Register snapshot",       path: "/reports/asset-register", icon: Camera,     scope: "assets:read" },
    { key: "register_export",         name: "Export",                  path: "/reports/export",        icon: Download,    scope: "export:read" },
  ]},
  // Who holds which role, and changing it (handoffs 41–43): administrators.
  { key: "administration", label: "Administration", items: [
    { key: "users",                   name: "Users",                   path: "/admin/users",           icon: ShieldCheck, scope: "admin" },
  ]},
  { key: "tools", label: "Tools", items: [
    { key: "barcode_station",         name: "Barcode Station",         path: "/tools/barcode",        icon: ScanBarcode, scope: "assets:read" },
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

/** Whether THIS TENANT draws an item — the second axis (handoff 48), the
 *  first being `canOpen`. `hidden` is the server's `hidden_items`; an empty
 *  set (not yet read, or unreadable) hides nothing, because this is
 *  presentation and the safe side of it is to show. Never a permission:
 *  nothing calls this to decide whether a page may render. */
export function tenantShows(hidden: ReadonlySet<string>, key: string): boolean {
  return !hidden.has(key);
}

/** The items a person is drawn on this tenant: their role opens it AND the
 *  tenant shows it. Groups left empty are dropped. One function, so the
 *  sidebar and anything that counts what it draws cannot disagree. */
export function drawnGroups(scopes: ScopeCheck, hidden: ReadonlySet<string>): NavGroup[] {
  return ALL_NAV_GROUPS
    .map(g => ({ ...g, items: g.items.filter(it =>
      canOpen(scopes, it.scope) && tenantShows(hidden, it.key)) }))
    .filter(g => g.items.length > 0);
}

/** The table's item for exactly this path, or null. */
function itemFor(path: string): NavItem | null {
  for (const g of ALL_NAV_GROUPS) {
    for (const it of g.items) {
      if (it.path === path) return it;
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
export function landingPath(
  scopes: ScopeCheck, hidden: ReadonlySet<string> = new Set(),
): string {
  // First a page the role opens AND the tenant shows. Failing that, a page
  // the role opens that the tenant has switched off — landing on a page the
  // sidebar does not draw is odd, but `/no-access` would tell somebody their
  // role opens nothing, which is false, and the tenant's switch is not a
  // permission (handoff 48).
  for (const respectTenant of [true, false]) {
    for (const path of LANDING_ORDER) {
      const item = itemFor(path);
      if (item && canOpen(scopes, item.scope)
          && (!respectTenant || tenantShows(hidden, item.key))) return path;
    }
  }
  return NO_ACCESS_PATH;
}
