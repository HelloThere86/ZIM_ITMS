import {
  Activity,
  BarChart3,
  ClipboardCheck,
  LayoutDashboard,
  Receipt,
  Search,
  Settings,
  ShieldAlert,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth, type Role } from "../context/AuthContext";
import { AuthUserPanel } from "./AuthUserPanel";

interface NavItem {
  to: string;
  icon: typeof LayoutDashboard;
  label: string;
  permission?: string;
  roles?: Role[];
}

const navItems: NavItem[] = [
  {
    to: "/dashboard",
    icon: LayoutDashboard,
    label: "Dashboard",
    permission: "violations:read",
  },
  {
    to: "/violations",
    icon: ShieldAlert,
    label: "Violations",
    permission: "violations:read",
  },
  {
    to: "/traffic-results",
    icon: BarChart3,
    label: "Traffic Results",
    permission: "results:read",
  },
  {
    to: "/review-queue",
    icon: ClipboardCheck,
    label: "Review Queue",
    permission: "violations:approve",
  },
  {
    to: "/evidence-search",
    icon: Search,
    label: "Evidence Search",
    permission: "evidence:read",
  },
  {
    to: "/fine-schedule",
    icon: Receipt,
    label: "Fine Schedule",
    permission: "fines:read",
  },
  {
    to: "/system-health",
    icon: Activity,
    label: "System Health",
    roles: ["admin", "supervisor"],
  },
  {
    to: "/audit-trail",
    icon: Receipt,
    label: "Audit Trail",
    permission: "audit:read",
  },
  {
    to: "/config",
    icon: Settings,
    label: "Config",
    permission: "settings:write",
  },
  {
    to: "/users",
    icon: Users,
    label: "Users",
    roles: ["admin"],
    permission: "users:write",
  },
];

export function Sidebar() {
  const { can, hasRole } = useAuth();

  const visibleNavItems = navItems.filter((item) => {
    const permissionAllowed = !item.permission || can(item.permission);
    const roleAllowed = !item.roles || hasRole(...item.roles);
    return permissionAllowed && roleAllowed;
  });

  return (
    <aside className="flex h-screen w-64 flex-shrink-0 flex-col border-r border-gray-800 bg-gray-900 text-gray-300">
      <div className="flex h-16 items-center border-b border-gray-800 px-6">
        <div>
          <h1 className="text-xl font-bold leading-none text-white">ITMS</h1>
          <p className="mt-1 text-xs text-gray-400">
            Traffic Control &amp; Enforcement
          </p>
        </div>
      </div>

      <nav className="flex-grow px-3 py-4">
        {visibleNavItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `mt-1 flex items-center rounded-lg px-4 py-3 text-sm transition-colors duration-200 ${
                isActive
                  ? "border border-gray-700 bg-gray-800 text-white"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <item.icon className="h-5 w-5 flex-shrink-0" />
            <span className="ml-3">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-800 px-4 py-4">
        <div className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-3">
          <p className="text-xs text-gray-400">System Mode</p>
          <p className="mt-1 text-sm font-medium text-white">
            Offline-First Monitoring
          </p>
        </div>
      </div>

      <AuthUserPanel />
    </aside>
  );
}
