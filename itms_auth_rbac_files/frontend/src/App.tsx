// frontend/src/App.tsx

import type { ReactNode } from "react";
import {
  BrowserRouter as Router,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { AuthProvider, useAuth, type Role } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Sidebar } from "./components/Sidebar";

import { LoginPage } from "./pages/LoginPage";
import { Dashboard } from "./pages/Dashboard";
import { ViolationsPage } from "./pages/Violations";
import { TrafficResultsPage } from "./pages/TrafficResultsPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { EvidenceSearchPage } from "./pages/EvidenceSearchPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { AuditTrailPage } from "./pages/AuditTrailPage";
import { ConfigPage } from "./pages/ConfigPage";
import { UsersPage } from "./pages/UsersPage";

function RootRedirect() {
  const { user, loading } = useAuth();

  if (loading) return null;

  return <Navigate to={user ? "/dashboard" : "/login"} replace />;
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-100 font-sans">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">
        <div className="p-6 md:p-8">{children}</div>
      </main>
    </div>
  );
}

function ProtectedPage({
  children,
  permission,
  roles,
}: {
  children: ReactNode;
  permission?: string;
  roles?: Role[];
}) {
  return (
    <ProtectedRoute permission={permission} roles={roles}>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RootRedirect />} />

      {/* Any authenticated user with read access */}
      <Route
        path="/dashboard"
        element={
          <ProtectedPage permission="violations:read">
            <Dashboard />
          </ProtectedPage>
        }
      />

      <Route
        path="/violations"
        element={
          <ProtectedPage permission="violations:read">
            <ViolationsPage />
          </ProtectedPage>
        }
      />

      <Route
        path="/traffic-results"
        element={
          <ProtectedPage permission="results:read">
            <TrafficResultsPage />
          </ProtectedPage>
        }
      />

      <Route
        path="/evidence-search"
        element={
          <ProtectedPage permission="evidence:read">
            <EvidenceSearchPage />
          </ProtectedPage>
        }
      />

      <Route
        path="/system-health"
        element={
          <ProtectedPage permission="results:read">
            <SystemHealthPage />
          </ProtectedPage>
        }
      />

      {/* Supervisor/Admin */}
      <Route
        path="/review-queue"
        element={
          <ProtectedPage permission="violations:approve">
            <ReviewQueuePage />
          </ProtectedPage>
        }
      />

      <Route
        path="/audit-trail"
        element={
          <ProtectedPage permission="audit:read">
            <AuditTrailPage />
          </ProtectedPage>
        }
      />

      {/* Admin */}
      <Route
        path="/config"
        element={
          <ProtectedPage permission="settings:write">
            <ConfigPage />
          </ProtectedPage>
        }
      />

      <Route
        path="/users"
        element={
          <ProtectedPage permission="users:write" roles={["admin"]}>
            <UsersPage />
          </ProtectedPage>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}
