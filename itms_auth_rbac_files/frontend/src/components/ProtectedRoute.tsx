// frontend/src/components/ProtectedRoute.tsx

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Loader2, ShieldX } from "lucide-react";
import { useAuth, type Role } from "../context/AuthContext";

interface ProtectedRouteProps {
  children: ReactNode;
  roles?: Role[];
  permission?: string;
}

export function ProtectedRoute({
  children,
  roles,
  permission,
}: ProtectedRouteProps) {
  const { user, loading, can } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const roleAllowed = !roles || roles.includes(user.role);
  const permissionAllowed = !permission || can(permission);

  if (!roleAllowed || !permissionAllowed) {
    return <AccessDenied />;
  }

  return <>{children}</>;
}

function AccessDenied() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center gap-4 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-50">
        <ShieldX className="h-7 w-7 text-red-500" />
      </div>

      <div>
        <h2 className="text-lg font-semibold text-gray-900">Access Denied</h2>
        <p className="mt-1 text-sm text-gray-500">
          You do not have permission to view this page.
          <br />
          Contact the System Administrator if this is incorrect.
        </p>
      </div>
    </div>
  );
}
