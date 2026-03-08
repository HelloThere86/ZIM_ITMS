// src/pages/FlaggedViolations.tsx
import { useState, useEffect } from "react";
import { StatCard } from "../components/StatCard";
import { AlignJustify, Grid, ChevronUp, Image, Video } from "lucide-react";

// This defines the "shape" of our data coming from the Python API
interface Violation {
  id: string;
  plateNumber: string;
  intersection: string;
  time: string;
  confidence: number;
  status: "Flagged" | "Approved" | "Rejected";
}

interface Stats {
  Flagged: number;
  Approved: number;
  Rejected: number;
}

export function FlaggedViolations() {
  const [selectedViolationId, setSelectedViolationId] = useState<string | null>(null);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [stats, setStats] = useState<Stats>({ Flagged: 0, Approved: 0, Rejected: 0 });

  useEffect(() => {
    // Fetch Table Data
    fetch("http://127.0.0.1:8000/api/violations")
      .then((res) => res.json())
      .then((data: Violation[]) => setViolations(data));

    // Fetch Stats
    fetch("http://127.0.0.1:8000/api/stats")
      .then((res) => res.json())
      .then((data: Stats) => setStats(data));
  }, []); // The empty array means this runs once when the page loads

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Flagged" value={stats.Flagged.toString()} sublabel="Total Violations" />
        <StatCard label="Approved" value={stats.Approved.toString()} sublabel="Traffic Violations" />
        <StatCard label="Rejected" value={stats.Rejected.toString()} sublabel="Traffic Violations" />
      </div>

      {/* Violations Table */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Flagged Violations</h2>
          {/* View toggle buttons */}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">Plate Number</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">Intersection</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">Time</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">Confidence</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {violations.map((violation) => (
                <tr
                  key={violation.id}
                  onClick={() => setSelectedViolationId(violation.id)}
                  className={`cursor-pointer hover:bg-gray-50 ${
                    selectedViolationId === violation.id ? "bg-gray-100" : ""
                  }`}
                >
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{violation.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{violation.plateNumber}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{violation.intersection}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{violation.time}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    <span className={`font-medium ${violation.confidence < 75 ? "text-gray-600" : "text-gray-900"}`}>{violation.confidence}%</span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                        violation.status === "Flagged" ? "bg-yellow-200 text-yellow-800" : "bg-green-200 text-green-800"
                      }`}>{violation.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Evidence Section - Placeholder for now */}
        {selectedViolationId && (
          <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
            <h3 className="text-md font-semibold mb-4">Evidence for {selectedViolationId}</h3>
            {/* We will add image/video display here later */}
          </div>
        )}
      </div>
    </div>
  );
}