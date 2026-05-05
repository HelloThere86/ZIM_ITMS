// frontend/src/components/AuthUserPanel.tsx
// Add this inside your Sidebar near the bottom if you do not want to manually edit much.

import { LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export function AuthUserPanel() {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <div className="mt-auto border-t border-gray-700 p-4">
      <p className="text-xs text-gray-400">Signed in as</p>
      <p className="mt-1 truncate text-sm font-medium text-white">
        {user.full_name}
      </p>
      <p className="mt-0.5 text-xs text-gray-400">{user.role_label}</p>

      <button
        type="button"
        onClick={logout}
        className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-800 px-3 py-2 text-sm text-white transition hover:bg-gray-700"
      >
        <LogOut className="h-4 w-4" />
        Logout
      </button>
    </div>
  );
}
