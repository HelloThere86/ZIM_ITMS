// src/App.tsx
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { FlaggedViolations } from "./pages/FlaggedViolations";

// Create placeholder components for the other pages so the links work
const Placeholder = ({ pageName }: { pageName: string }) => <h1 className="text-3xl font-bold">{pageName}</h1>;

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-gray-100 font-sans">
        <Sidebar />
        <main className="flex-1 p-8 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/flagged-violations" element={<FlaggedViolations />} />
            <Route path="/evidence-search" element={<Placeholder pageName="Evidence Search" />} />
            <Route path="/system-health" element={<Placeholder pageName="System Health" />} />
            <Route path="/audit-trail" element={<Placeholder pageName="Audit Trail" />} />
            <Route path="/config" element={<Placeholder pageName="Config" />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
export default App;