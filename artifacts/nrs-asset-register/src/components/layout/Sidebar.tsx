import { useLocation } from "wouter";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, Globe, AppWindow, Settings,
} from "lucide-react";

const navGroups = [
  { label: "Dashboards",        items: [{ name: "Facility Command Center", path: "/",               icon: LayoutDashboard }] },
  { label: "Operations",        items: [{ name: "Locations",               path: "/locations",      icon: MapPin          }] },
  { label: "Fleet & Transport", items: [{ name: "Staff Bus",               path: "/fleet/staff-bus", icon: Bus            },
                                        { name: "Fleet",                   path: "/fleet",          icon: Car             }] },
  { label: "Asset Register",    items: [{ name: "Asset Register",          path: "/assets",         icon: BookOpen        }] },
  { label: "HR & Staff",        items: [{ name: "Identity",                path: "/hr/identity",    icon: Fingerprint     },
                                        { name: "Employees",               path: "/hr/employees",   icon: Users           }] },
  { label: "Administration",    items: [{ name: "Website",                 path: "/admin/website",  icon: Globe           },
                                        { name: "Apps",                    path: "/admin/apps",     icon: AppWindow       },
                                        { name: "Settings",                path: "/admin/settings", icon: Settings        }] },
];

function NrsLogo({ isDark }: { isDark: boolean }) {
  const lockup = (
    <div className="flex items-center gap-2 min-w-0">
      {/* Emblem — hexagon mark */}
      <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden>
        <path d="M15 2L27 8.5V21.5L15 28L3 21.5V8.5L15 2Z" fill="#E01F26" />
        <path d="M15 6.5L23 11V19L15 23.5L7 19V11L15 6.5Z" fill="white" fillOpacity="0.18" />
        <text x="15" y="18.5" textAnchor="middle" fontSize="9" fontWeight="700" fill="white" fontFamily="Inter,sans-serif">NRS</text>
      </svg>
      {/* Wordmark */}
      <div className="leading-none">
        <p className="text-[11px] font-extrabold tracking-[0.06em] uppercase" style={{ color: "#7E8083" }}>NRS</p>
        <p className="text-[8px] font-bold tracking-[0.04em] uppercase" style={{ color: "#E01F26", letterSpacing: "0.04em" }}>Nigeria Revenue Service</p>
      </div>
    </div>
  );

  if (isDark) {
    return (
      <div className="inline-flex rounded-lg px-2.5 py-1.5" style={{ background: "#FFFFFF" }}>
        {lockup}
      </div>
    );
  }
  return lockup;
}

export default function Sidebar() {
  const [location, navigate] = useLocation();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const isActive = (path: string) =>
    path === "/" ? location === "/" : location === path || location.startsWith(path + "/");

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
        <NrsLogo isDark={isDark} />
      </div>

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-2 px-2.5" aria-label="Primary navigation">
        {navGroups.map((group, gi) => (
          <div key={group.label} className={cn("mb-0.5", gi > 0 && "mt-3")}>
            {/* Section label */}
            <p
              className="px-2 pt-1 pb-1 text-[10px] font-bold uppercase select-none"
              style={{ color: "#9CA3AF", letterSpacing: "0.07em" }}
            >
              {group.label}
            </p>

            {/* Nav items */}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.path);
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, "-")}`}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "nav-item-hover nav-item-active w-full flex items-center gap-2.5 px-2.5 py-[7px] mb-px rounded-xl text-[13px] font-medium transition-colors duration-100 text-left",
                    active && "nav-item-active"
                  )}
                  style={
                    active
                      ? {
                          background: "#E01F26",
                          color: "#FFFFFF",
                          boxShadow: "0 1px 6px rgba(224,31,38,0.30)",
                        }
                      : { color: "hsl(var(--sidebar-foreground))" }
                  }
                >
                  <Icon
                    size={14}
                    className="shrink-0"
                    style={{ color: active ? "#FFFFFF" : "hsl(var(--sidebar-foreground) / 0.6)" }}
                  />
                  <span className="truncate">{item.name}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* ── Footer / user ────────────────────────────────────────────────── */}
      <div
        className="p-3 shrink-0"
        style={{ borderTop: "0.5px solid hsl(var(--sidebar-border))" }}
      >
        <div
          className="flex items-center gap-2.5 px-2 py-2 rounded-xl cursor-pointer transition-colors"
          style={{ color: "hsl(var(--sidebar-foreground))" }}
          onMouseEnter={e => (e.currentTarget.style.background = "hsl(var(--sidebar-accent))")}
          onMouseLeave={e => (e.currentTarget.style.background = "")}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold text-white"
            style={{ background: "#E01F26" }}
          >
            A
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-semibold truncate leading-tight" style={{ color: "hsl(var(--sidebar-foreground))" }}>
              Admin User
            </p>
            <p className="text-[10px] truncate" style={{ color: "hsl(var(--sidebar-foreground) / 0.45)" }}>
              NRS Headquarters
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
