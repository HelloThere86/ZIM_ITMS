// src/pages/Dashboard.tsx
import { useState, useEffect } from "react";
import { StatCard } from "../components/StatCard";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

interface Stats {
  Flagged: number;
  Approved: number;
  Rejected: number;
}

export function Dashboard() {
  const [stats, setStats] = useState<Stats>({ Flagged: 0, Approved: 0, Rejected: 0 });

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/stats")
      .then((res) => res.json())
      .then((data: Stats) => setStats(data))
      .catch((err) => console.error("Error fetching stats:", err));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Dashboard Overview</h1>
        
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <StatCard label="Flagged" value={stats.Flagged.toString()} sublabel="Total Violations" />
          <StatCard label="Approved" value={stats.Approved.toString()} sublabel="Traffic Violations" />
          <StatCard label="Rejected" value={stats.Rejected.toString()} sublabel="Total" />
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Link to="/flagged-violations" className="bg-white rounded-lg p-6 border border-gray-200 hover:border-gray-300 transition-all hover:shadow-md group">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-semibold text-gray-900">Flagged Violations</h3>
              <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-gray-600 group-hover:translate-x-1 transition-all" />
            </div>
            <p className="text-sm text-gray-600">Review and process flagged traffic violations</p>
            <div className="mt-4 text-3xl font-semibold text-gray-700">{stats.Flagged}</div>
          </Link>
          
          {/* Other links can be added here following the same pattern */}
        </div>
      </div>
    </div>
  );
}