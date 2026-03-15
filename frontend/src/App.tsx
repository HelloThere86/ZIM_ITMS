// src/App.tsx
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

import { Dashboard } from "./pages/Dashboard";
import { ViolationsPage } from "./pages/Violations";
import { TrafficResultsPage } from "./pages/TrafficResultsPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { EvidenceSearchPage } from "./pages/EvidenceSearchPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { AuditTrailPage } from "./pages/AuditTrailPage";
import { ConfigPage } from "./pages/ConfigPage";

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-gray-100 font-sans">
        <Sidebar />

        <main className="flex-1 overflow-y-auto">
          <div className="p-6 md:p-8">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/violations" element={<ViolationsPage />} />
              <Route path="/traffic-results" element={<TrafficResultsPage />} />
              <Route path="/review-queue" element={<ReviewQueuePage />} />
              <Route path="/evidence-search" element={<EvidenceSearchPage />} />
              <Route path="/system-health" element={<SystemHealthPage />} />
              <Route path="/audit-trail" element={<AuditTrailPage />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </Router>
  );
}

export default App;