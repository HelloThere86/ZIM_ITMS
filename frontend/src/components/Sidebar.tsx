// src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import { Grid, Flag, Search, Activity, Receipt, Settings } from "lucide-react";

const navItems = [
  { to: "/", icon: Grid, label: "Dashboard" },
  { to: "/flagged-violations", icon: Flag, label: "Flagged Violations" },
  { to: "/evidence-search", icon: Search, label: "Evidence Search" },
  { to: "/system-health", icon: Activity, label: "System Health" },
  { to: "/audit-trail", icon: Receipt, label: "Audit Trail" },
  { to: "/config", icon: Settings, label: "Config" },
];

export function Sidebar() {
  return (
    <aside className="w-64 flex-shrink-0 bg-gray-800 text-gray-300 flex flex-col">
      <div className="h-16 flex items-center justify-center text-white font-bold text-xl border-b border-gray-700">
        ITMS
      </div>
      <nav className="flex-grow px-4 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center px-4 py-2 mt-2 text-sm rounded transition-colors duration-200 hover:bg-gray-700 hover:text-white ${
                isActive ? "bg-gray-900 text-white" : ""
              }`
            }
          >
            <item.icon className="w-5 h-5" />
            <span className="ml-3">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}