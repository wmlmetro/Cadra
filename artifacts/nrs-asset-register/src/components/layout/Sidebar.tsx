import { useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, Globe, AppWindow, Settings,
} from "lucide-react";

const navGroups = [
  { label: "Dashboards",        items: [{ name: "Facility Command Center", path: "/",              icon: LayoutDashboard }] },
  { label: "Operations",        items: [{ name: "Locations",               path: "/locations",     icon: MapPin          }] },
  { label: "Fleet & Transport", items: [{ name: "Staff Bus",               path: "/fleet/staff-bus", icon: Bus           },
                                        { name: "Fleet",                   path: "/fleet",         icon: Car             }] },
  { label: "Asset Register",    items: [{ name: "Asset Register",          path: "/assets",        icon: BookOpen        }] },
  { label: "HR & Staff",        items: [{ name: "Identity",                path: "/hr/identity",   icon: Fingerprint     },
                                        { name: "Employees",               path: "/hr/employees",  icon: Users           }] },
  { label: "Administration",    items: [{ name: "Website",                 path: "/admin/website", icon: Globe           },
                                        { name: "Apps",                    path: "/admin/apps",    icon: AppWindow       },
                                        { name: "Settings",                path: "/admin/settings",icon: Settings        }] },
];

export default function Sidebar() {
  const [location, navigate] = useLocation();

  const isActive = (path: string) =>
    path === "/" ? location === "/" : location === path || location.startsWith(path + "/");

  return (
    <aside
      className="w-[220px] shrink-0 flex flex-col h-full select-none"
      style={{ background: "hsl(var(--sidebar))", borderRight: "1px solid hsl(var(--sidebar-border))" }}
    >
      {/* Brand */}
      <div className="h-[52px] px-4 flex items-center gap-3 shrink-0" style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}>
        <div
          className="w-8 h-8 rounded-[10px] flex items-center justify-center shrink-0 shadow-sm"
          style={{ background: "hsl(var(--sidebar-primary))" }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 2L16 6V12L9 16L2 12V6L9 2Z" fill="white" fillOpacity="0.22" />
            <path d="M9 4L14 7V11L9 14L4 11V7L9 4Z" fill="white" />
          </svg>
        </div>
        <div className="min-w-0">
          <p className="font-bold text-[13px] leading-tight" style={{ color: "hsl(var(--sidebar-foreground))" }}>NRS</p>
          <p className="text-[10px] font-medium" style={{ color: "hsl(var(--sidebar-foreground) / 0.45)" }}>Asset Register</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-3">
        {navGroups.map((group, gi) => (
          <div key={group.label} className={cn("mb-1.5", gi > 0 && "pt-1")}>
            <p
              className="px-2 pt-1.5 pb-1 text-[9px] font-bold uppercase tracking-[0.12em]"
              style={{ color: "hsl(var(--sidebar-foreground) / 0.32)" }}
            >
              {group.label}
            </p>
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.path);
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, "-")}`}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-2.5 py-[7px] mb-0.5 rounded-xl text-[13px] font-medium transition-all duration-150 text-left"
                  )}
                  style={
                    active
                      ? { background: "hsl(var(--sidebar-primary))", color: "white", boxShadow: "0 2px 10px hsl(var(--sidebar-primary) / 0.4)" }
                      : { color: "hsl(var(--sidebar-foreground) / 0.62)" }
                  }
                  onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.06)"; }}
                  onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLElement).style.background = ""; }}
                >
                  <Icon size={14} className="shrink-0" />
                  <span className="truncate">{item.name}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 shrink-0" style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}>
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl cursor-pointer transition-colors" style={{ color: "hsl(var(--sidebar-foreground))" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "")}
        >
          <div
            className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold"
            style={{ background: "hsl(var(--sidebar-primary) / 0.25)", color: "hsl(var(--sidebar-primary))" }}
          >
            A
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-semibold truncate leading-tight" style={{ color: "hsl(var(--sidebar-foreground))" }}>Admin User</p>
            <p className="text-[10px] truncate" style={{ color: "hsl(var(--sidebar-foreground) / 0.4)" }}>NRS Headquarters</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
