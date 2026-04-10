// src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  ShieldAlert,
  BarChart3,
  ClipboardCheck,
  Search,
  Activity,
  Receipt,
  Settings,
} from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/violations", icon: ShieldAlert, label: "Violations" },
  { to: "/traffic-results", icon: BarChart3, label: "Traffic Results" },
  { to: "/review-queue", icon: ClipboardCheck, label: "Review Queue" },
  { to: "/evidence-search", icon: Search, label: "Evidence Search" },
  { to: "/fine-schedule", icon: Receipt, label: "Fine Schedule" },
  { to: "/system-health", icon: Activity, label: "System Health" },
  { to: "/audit-trail", icon: Receipt, label: "Audit Trail" },
  { to: "/config", icon: Settings, label: "Config" },
];

export function Sidebar() {
  return (
    <aside className="w-64 flex-shrink-0 bg-gray-900 text-gray-300 flex flex-col border-r border-gray-800">
      <div className="h-16 flex items-center px-6 border-b border-gray-800">
        <div>
          <h1 className="text-white font-bold text-xl leading-none">ITMS</h1>
          <p className="text-xs text-gray-400 mt-1">Traffic Control & Enforcement</p>
        </div>
      </div>

      <nav className="flex-grow px-3 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center px-4 py-3 mt-1 text-sm rounded-lg transition-colors duration-200 ${
                isActive
                  ? "bg-gray-800 text-white border border-gray-700"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            <span className="ml-3">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-gray-800">
        <div className="rounded-lg bg-gray-800 border border-gray-700 px-3 py-3">
          <p className="text-xs text-gray-400">System Mode</p>
          <p className="text-sm font-medium text-white mt-1">Offline-First Monitoring</p>
        </div>
      </div>
    </aside>
  );
}