import { useState } from "react";
import { useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, Activity, ShieldAlert,
  Inbox, Briefcase, ScanBarcode, Upload, RefreshCw,
  Wrench, Tag, ChevronDown, Monitor, TrendingDown, SlidersHorizontal,
  LogOut,
} from "lucide-react";
import { logout, getScope, getExpiry } from "@/lib/auth";
import { brandLogoSrc, getBrand } from "@/lib/brand";

const navGroups = [
  { label: "Dashboards", items: [
    { name: "Facility Command Center", path: "/",                     icon: LayoutDashboard },
    // Hidden for now (routes still work via direct URL):
    // { name: "FM Operations",           path: "/dashboards/fm",        icon: Activity        },
    { name: "Fleet Command",           path: "/dashboards/fleet",     icon: Car             },
    { name: "IT Assets Command",       path: "/dashboards/it",        icon: Monitor         },
    // { name: "Security Operations",     path: "/dashboards/security",  icon: ShieldAlert     },
  ]},
  // Service Desk group hidden in its entirety for now. Routes (/service-desk,
  // /service-desk/triage, /service-desk/new, /service-desk/:id) still resolve
  // via direct URL — only the sidebar entries are gone.
  { label: "Asset Register", items: [
    { name: "Dashboard",               path: "/assets",               icon: LayoutDashboard },
    { name: "All Assets",              path: "/assets/list",          icon: BookOpen        },
    { name: "+ New Asset",             path: "/assets/new",           icon: BookOpen        },
  ]},
  { label: "Operations", items: [
    { name: "Locations",               path: "/locations",            icon: MapPin         },
    { name: "+ New Location",          path: "/locations/new",        icon: MapPin         },
  ]},
  { label: "HR & Staff", items: [
    { name: "Employees",               path: "/hr/employees",         icon: Users          },
    { name: "SAP Sync",                path: "/hr/sap-sync",          icon: RefreshCw      },
    { name: "Bulk Import",             path: "/hr/import",            icon: Upload         },
    { name: "Identity (clearance)",    path: "/hr/identity",          icon: Fingerprint    },
  ]},
  { label: "Fleet & Transport", items: [
    { name: "Fleet",                   path: "/fleet",                icon: Car            },
    { name: "Staff Bus",               path: "/fleet/staff-bus",      icon: Bus            },
  ]},
  { label: "Reports", items: [
    { name: "Fleet Roster",            path: "/reports/fleet-roster",          icon: Car      },
    { name: "Asset Inventory",         path: "/reports/asset-inventory",       icon: BookOpen },
    { name: "Maintenance Readiness",   path: "/reports/maintenance-readiness", icon: Wrench   },
    { name: "Location Coverage",       path: "/reports/location-coverage",     icon: MapPin   },
    { name: "Tag Adoption",            path: "/reports/tag-adoption",          icon: Tag      },
    { name: "Depreciation",            path: "/reports/depreciation",          icon: TrendingDown },
  ]},
  { label: "Settings", items: [
    { name: "Depreciation",            path: "/settings/depreciation", icon: SlidersHorizontal },
  ]},
  { label: "Tools", items: [
    { name: "Barcode Station",         path: "/tools/barcode",        icon: ScanBarcode    },
  ]},
];

// localStorage key for per-group collapse state. Survives reloads so users
// don't have to re-collapse every time.
const COLLAPSE_STORAGE_KEY = "cadra.sidebar.collapsed";

function readCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function writeCollapsed(state: Record<string, boolean>) {
  try { localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(state)); } catch { /* noop */ }
}

function NrsLogoImg() {
  // Per-tenant logo + name, resolved at render time (applyBrand ran before mount).
  return (
    <img
      src={brandLogoSrc()}
      alt={getBrand().name}
      className="h-10 w-auto object-contain"
      draggable={false}
    />
  );
}

export default function Sidebar() {
  const [location, navigate] = useLocation();

  // Pick the single best-matching nav item rather than highlighting every
  // ancestor. "Best" = the longest path that is a prefix of the current URL.
  // That keeps "All Requests" (/service-desk) lit on /service-desk/123 but
  // hands off to "Triage Inbox" (/service-desk/triage) when we're there.
  const activePath = (() => {
    let best = "";
    for (const g of navGroups) {
      for (const it of g.items) {
        const p = it.path;
        const matches = p === "/" ? location === "/" : (location === p || location.startsWith(p + "/"));
        if (matches && p.length > best.length) best = p;
      }
    }
    return best;
  })();
  const isActive = (path: string) => path === activePath;

  // Which group contains the active item? That group is force-expanded so
  // the user can always see where they are.
  const activeGroup = navGroups.find(g => g.items.some(i => i.path === activePath))?.label ?? null;

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => readCollapsed());
  const toggleGroup = (label: string) => {
    setCollapsed(prev => {
      const next = { ...prev, [label]: !prev[label] };
      writeCollapsed(next);
      return next;
    });
  };

  return (
    <aside
      className="w-[220px] shrink-0 flex flex-col h-full select-none"
      style={{
        background: "hsl(var(--sidebar))",
        borderRight: "0.5px solid hsl(var(--sidebar-border))",
      }}
    >
      {/* ── Logo ─────────────────────────────────────────────────────────── */}
      <div
        className="h-[56px] px-4 flex items-center shrink-0"
        style={{ borderBottom: "0.5px solid hsl(var(--sidebar-border))" }}
      >
        <NrsLogoImg />
      </div>

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-2 px-2.5" aria-label="Primary navigation">
        {navGroups.map((group, gi) => {
          // The active group is always open regardless of the user's saved
          // preference — never hide where they currently are.
          const isOpen = group.label === activeGroup || !collapsed[group.label];
          const groupId = `nav-group-${group.label.toLowerCase().replace(/\s+/g, "-")}`;
          return (
            <div key={group.label} className={cn("mb-0.5", gi > 0 && "mt-3")}>
              {/* Collapsible section header */}
              <button
                onClick={() => toggleGroup(group.label)}
                aria-expanded={isOpen}
                aria-controls={groupId}
                className="w-full group flex items-center gap-1.5 px-2 pt-1 pb-1 rounded-md hover:bg-[hsl(var(--sidebar-accent))] transition-colors text-left"
              >
                <ChevronDown
                  size={10}
                  className={cn(
                    "shrink-0 transition-transform duration-150",
                    !isOpen && "-rotate-90",
                  )}
                  style={{ color: "#9CA3AF" }}
                />
                <span
                  className="flex-1 text-[10px] font-bold uppercase select-none truncate"
                  style={{ color: "#9CA3AF", letterSpacing: "0.07em" }}
                >
                  {group.label}
                </span>
              </button>

              {/* Nav items — hidden when collapsed (unless this is the active group) */}
              {isOpen && (
                <div id={groupId}>
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active = isActive(item.path);
                    return (
                      <button
                        key={item.path}
                        onClick={() => navigate(item.path)}
                        data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, "-")}`}
                        aria-current={active ? "page" : undefined}
                        className="nav-item-hover w-full flex items-center gap-2.5 px-2.5 py-[7px] mb-px rounded-xl text-[13px] font-medium transition-colors duration-100 text-left"
                        style={
                          active
                            ? {
                                // Per-tenant brand colour (was hardcoded NRS red).
                                background: getBrand().primary,
                                color: "#FFFFFF",
                                boxShadow: `0 1px 6px ${getBrand().primary}47`,
                              }
                            : { color: "hsl(var(--sidebar-foreground))" }
                        }
                      >
                        <Icon
                          size={14}
                          className="shrink-0"
                          style={{ color: active ? "#FFFFFF" : "hsl(var(--sidebar-foreground) / 0.55)" }}
                        />
                        <span className="truncate">{item.name}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* ── Footer / session ─────────────────────────────────────────────── */}
      <div
        className="p-3 shrink-0"
        style={{ borderTop: "0.5px solid hsl(var(--sidebar-border))" }}
      >
        <SessionChip />
      </div>
    </aside>
  );
}

function SessionChip() {
  const expiry = getExpiry();
  const scope  = getScope() ?? "*";
  const expiresIn = expiry ? Math.max(0, Math.round((expiry - Date.now()) / 60_000)) : null;

  return (
    <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold text-white"
        style={{ background: getBrand().primary }}
      >
        A
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold truncate leading-tight" style={{ color: "hsl(var(--sidebar-foreground))" }}>
          Signed in
        </p>
        <p className="text-[10px] truncate" style={{ color: "hsl(var(--sidebar-foreground) / 0.45)" }}>
          {scope === "*" ? "admin scope" : `scope: ${scope}`}{expiresIn != null && ` · ${expiresIn}m left`}
        </p>
      </div>
      <button
        onClick={() => logout()}
        title="Sign out"
        aria-label="Sign out"
        className="shrink-0 p-1.5 rounded-lg hover:bg-[hsl(var(--sidebar-accent))]"
        style={{ color: "hsl(var(--sidebar-foreground) / 0.6)" }}
      >
        <LogOut size={13} />
      </button>
    </div>
  );
}
