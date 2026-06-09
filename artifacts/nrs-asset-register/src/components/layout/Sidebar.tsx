import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, MapPin, Bus, Car, BookOpen,
  Fingerprint, Users, Globe, AppWindow, Settings,
} from "lucide-react";

const navGroups = [
  {
    label: "Dashboards",
    items: [{ name: "Facility Command Center", path: "/", icon: LayoutDashboard }],
  },
  {
    label: "Operations",
    items: [{ name: "Locations", path: "/locations", icon: MapPin }],
  },
  {
    label: "Fleet & Transport",
    items: [
      { name: "Staff Bus", path: "/fleet/staff-bus", icon: Bus },
      { name: "Fleet", path: "/fleet", icon: Car },
    ],
  },
  {
    label: "Asset Register",
    items: [{ name: "Asset Register", path: "/assets", icon: BookOpen }],
  },
  {
    label: "HR & Staff",
    items: [
      { name: "Identity", path: "/hr/identity", icon: Fingerprint },
      { name: "Employees", path: "/hr/employees", icon: Users },
    ],
  },
  {
    label: "Administration",
    items: [
      { name: "Website", path: "/admin/website", icon: Globe },
      { name: "Apps", path: "/admin/apps", icon: AppWindow },
      { name: "Settings", path: "/admin/settings", icon: Settings },
    ],
  },
];

export default function Sidebar() {
  const [location] = useLocation();

  const isActive = (path: string) =>
    path === "/"
      ? location === "/"
      : location === path || location.startsWith(path + "/");

  return (
    <aside className="w-60 shrink-0 flex flex-col h-full" style={{ background: "hsl(var(--sidebar))", borderRight: "1px solid hsl(var(--sidebar-border))" }}>
      {/* Logo bar */}
      <div className="px-4 py-4 flex items-center gap-3" style={{ borderBottom: "1px solid hsl(var(--sidebar-border))" }}>
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "hsl(var(--sidebar-primary))" }}>
          <span className="text-white font-bold text-xs tracking-tight">NRS</span>
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-sm leading-tight" style={{ color: "hsl(var(--sidebar-foreground))" }}>Nigeria Revenue</p>
          <p className="text-xs" style={{ color: "hsl(var(--sidebar-foreground) / 0.5)" }}>Service</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-3">
            <p
              className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "hsl(var(--sidebar-foreground) / 0.4)" }}
            >
              {group.label}
            </p>
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.path);
              return (
                <Link key={item.path} href={item.path} asChild>
                  <a
                    data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, "-")}`}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer",
                      active
                        ? "text-white"
                        : "hover:opacity-80"
                    )}
                    style={
                      active
                        ? { background: "hsl(var(--sidebar-primary))", color: "white" }
                        : { color: "hsl(var(--sidebar-foreground) / 0.7)" }
                    }
                  >
                    <Icon size={15} className="shrink-0" />
                    <span className="truncate">{item.name}</span>
                  </a>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="p-3" style={{ borderTop: "1px solid hsl(var(--sidebar-border))" }}>
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold"
            style={{ background: "hsl(var(--sidebar-primary) / 0.2)", color: "hsl(var(--sidebar-primary))" }}
          >
            AU
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold truncate" style={{ color: "hsl(var(--sidebar-foreground))" }}>Admin User</p>
            <p className="text-[10px] truncate" style={{ color: "hsl(var(--sidebar-foreground) / 0.5)" }}>NRS Headquarters</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
