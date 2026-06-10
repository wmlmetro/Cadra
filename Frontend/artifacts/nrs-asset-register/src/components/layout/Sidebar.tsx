import { useLocation } from "wouter";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, Activity, ShieldAlert,
  Inbox, Briefcase, ScanBarcode, Upload, RefreshCw,
} from "lucide-react";

const navGroups = [
  { label: "Dashboards", items: [
    { name: "Facility Command Center", path: "/",                     icon: LayoutDashboard },
    { name: "FM Operations",           path: "/dashboards/fm",        icon: Activity        },
    { name: "Fleet Command",           path: "/dashboards/fleet",     icon: Car             },
    { name: "Security Operations",     path: "/dashboards/security",  icon: ShieldAlert     },
  ]},
  { label: "Service Desk", items: [
    { name: "Triage Inbox",            path: "/service-desk/triage",  icon: Inbox          },
    { name: "All Requests",            path: "/service-desk",         icon: Briefcase      },
    { name: "+ New Request",           path: "/service-desk/new",     icon: Briefcase      },
  ]},
  { label: "Asset Register", items: [
    { name: "All Assets",              path: "/assets",               icon: BookOpen       },
    { name: "+ New Asset",             path: "/assets/new",           icon: BookOpen       },
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
  { label: "Tools", items: [
    { name: "Barcode Station",         path: "/tools/barcode",        icon: ScanBarcode    },
  ]},
];

const logoSrc = `${import.meta.env.BASE_URL}nrs-logo.png`;

function NrsLogoImg({ isDark }: { isDark: boolean }) {
  const img = (
    <img
      src={logoSrc}
      alt="Nigeria Revenue Service"
      className="h-7 w-auto object-contain"
      draggable={false}
    />
  );

  if (isDark) {
    return (
      <div
        className="inline-flex items-center rounded-lg px-2.5 py-1.5"
        style={{ background: "#FFFFFF" }}
      >
        {img}
      </div>
    );
  }
  return img;
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
        <NrsLogoImg isDark={isDark} />
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
                  className="nav-item-hover w-full flex items-center gap-2.5 px-2.5 py-[7px] mb-px rounded-xl text-[13px] font-medium transition-colors duration-100 text-left"
                  style={
                    active
                      ? {
                          background: "#E01F26",
                          color: "#FFFFFF",
                          boxShadow: "0 1px 6px rgba(224,31,38,0.28)",
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
        ))}
      </nav>

      {/* ── Footer / user ────────────────────────────────────────────────── */}
      <div
        className="p-3 shrink-0"
        style={{ borderTop: "0.5px solid hsl(var(--sidebar-border))" }}
      >
        <div
          className="flex items-center gap-2.5 px-2 py-2 rounded-xl cursor-pointer transition-colors"
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
            <p
              className="text-[12px] font-semibold truncate leading-tight"
              style={{ color: "hsl(var(--sidebar-foreground))" }}
            >
              Admin User
            </p>
            <p
              className="text-[10px] truncate"
              style={{ color: "hsl(var(--sidebar-foreground) / 0.45)" }}
            >
              NRS Headquarters
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
