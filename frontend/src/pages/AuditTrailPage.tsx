// src/pages/AuditTrailPage.tsx
import { useEffect, useMemo, useState } from "react";
import {
  History,
  Search,
  Filter,
  ShieldCheck,
  Settings,
  ClipboardCheck,
  Eye,
  Database,
  User,
  Clock3,
  FileText,
  RefreshCw,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { getAuditLog, type AuditEntry, type AuditSeverity } from "../services/auditTrail";

type ActionFilter =
  | "All"
  | "Review Approved"
  | "Review Rejected"
  | "Evidence Accessed"
  | "Configuration Updated"
  | "System Sync"
  | "Record Created";

export function AuditTrailPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [actionFilter, setActionFilter] = useState<ActionFilter>("All");
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);

  async function loadAuditLog() {
    try {
      setLoading(true);
      setError(null);

      const data = await getAuditLog();
      setEntries(data);

      if (data.length > 0) {
        setSelectedEntryId((prev) => prev ?? data[0].id);
      }
    } catch (err) {
      console.error("Failed to load audit log:", err);
      setError("Failed to load audit trail from backend.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAuditLog();
  }, []);

  const filteredEntries = useMemo(() => {
    return entries.filter((entry) => {
      const matchesSearch =
        entry.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        entry.actor.toLowerCase().includes(searchTerm.toLowerCase()) ||
        entry.target.toLowerCase().includes(searchTerm.toLowerCase()) ||
        entry.summary.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesAction =
        actionFilter === "All" ? true : entry.actionType === actionFilter;

      return matchesSearch && matchesAction;
    });
  }, [entries, searchTerm, actionFilter]);

  const selectedEntry =
    filteredEntries.find((entry) => entry.id === selectedEntryId) ||
    entries.find((entry) => entry.id === selectedEntryId) ||
    null;

  const sensitiveCount = entries.filter((item) => item.severity === "Sensitive").length;
  const criticalCount = entries.filter((item) => item.severity === "Critical").length;
  const reviewActions = entries.filter(
    (item) => item.actionType === "Review Approved" || item.actionType === "Review Rejected"
  ).length;

  function getSeverityClasses(severity: AuditSeverity) {
    if (severity === "Normal") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (severity === "Sensitive") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  function getActionIcon(actionType: string) {
    if (actionType === "Review Approved" || actionType === "Review Rejected") {
      return <ClipboardCheck className="h-4 w-4 text-gray-700" />;
    }
    if (actionType === "Evidence Accessed") {
      return <Eye className="h-4 w-4 text-gray-700" />;
    }
    if (actionType === "Configuration Updated") {
      return <Settings className="h-4 w-4 text-gray-700" />;
    }
    if (actionType === "System Sync") {
      return <Database className="h-4 w-4 text-gray-700" />;
    }
    return <ShieldCheck className="h-4 w-4 text-gray-700" />;
  }

  function formatJsonBlock(value?: string | null) {
    if (!value) return "No value recorded.";

    try {
      const parsed = JSON.parse(value);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return value;
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Transparency & Accountability</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Audit Trail
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Track important system and user actions across enforcement, evidence access,
            configuration changes, and operational events. This page supports transparency,
            traceability, and defensibility.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadAuditLog}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
            <p className="text-sm font-medium text-blue-900">Logged Events</p>
            <p className="mt-1 text-2xl font-semibold text-blue-800">
              {loading ? "..." : entries.length}
            </p>
          </div>
        </div>
      </section>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-900">Backend issue</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Events"
          value={loading ? "..." : entries.length.toString()}
          sublabel="Tracked operational actions"
        />
        <StatCard
          label="Review Actions"
          value={loading ? "..." : reviewActions.toString()}
          sublabel="Human verification decisions"
        />
        <StatCard
          label="Sensitive Events"
          value={loading ? "..." : sensitiveCount.toString()}
          sublabel="Evidence and reviewer actions"
        />
        <StatCard
          label="Critical Events"
          value={loading ? "..." : criticalCount.toString()}
          sublabel="High-impact configuration changes"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Audit Events</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Search and filter logged system activity.
                </p>
              </div>

              <div className="flex flex-col gap-3 md:flex-row">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search by ID, actor, target, or summary"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm text-gray-900 outline-none transition focus:border-gray-400 md:w-80"
                  />
                </div>

                <div className="relative">
                  <Filter className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <select
                    value={actionFilter}
                    onChange={(e) => setActionFilter(e.target.value as ActionFilter)}
                    className="w-full appearance-none rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-8 text-sm text-gray-900 outline-none transition focus:border-gray-400 md:w-56"
                  >
                    <option value="All">All Actions</option>
                    <option value="Review Approved">Review Approved</option>
                    <option value="Review Rejected">Review Rejected</option>
                    <option value="Evidence Accessed">Evidence Accessed</option>
                    <option value="Configuration Updated">Configuration Updated</option>
                    <option value="System Sync">System Sync</option>
                    <option value="Record Created">Record Created</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="px-6 py-12 text-sm text-gray-500">Loading audit trail...</div>
          ) : filteredEntries.length === 0 ? (
            <div className="px-6 py-12">
              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
                <p className="text-base font-medium text-gray-900">No audit events found</p>
                <p className="mt-2 text-sm text-gray-600">
                  Try adjusting the search text or action filter.
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Event ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Timestamp
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Actor
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Action
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Target
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Severity
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 bg-white">
                  {filteredEntries.map((entry) => {
                    const isSelected = entry.id === selectedEntryId;

                    return (
                      <tr
                        key={entry.id}
                        onClick={() => setSelectedEntryId(entry.id)}
                        className={`cursor-pointer transition ${
                          isSelected ? "bg-gray-50" : "hover:bg-gray-50"
                        }`}
                      >
                        <td className="px-6 py-4 text-sm font-medium text-gray-900">{entry.id}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{entry.timestamp}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{entry.actor}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{entry.actionType}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{entry.target}</td>
                        <td className="px-6 py-4 text-sm">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getSeverityClasses(
                              entry.severity
                            )}`}
                          >
                            {entry.severity}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Event Detail</h2>
            <p className="mt-1 text-sm text-gray-600">
              Selected event summary and accountability context.
            </p>
          </div>

          {!selectedEntry ? (
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
              <p className="text-sm font-medium text-gray-900">No event selected</p>
              <p className="mt-2 text-sm text-gray-600">
                Select an audit event from the table to inspect it.
              </p>
            </div>
          ) : (
            <div className="mt-6 space-y-5">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Selected Event
                    </p>
                    <p className="mt-1 text-lg font-semibold text-gray-900">{selectedEntry.id}</p>
                  </div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getSeverityClasses(
                      selectedEntry.severity
                    )}`}
                  >
                    {selectedEntry.severity}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <Clock3 className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Timestamp
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedEntry.timestamp}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <User className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Actor
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedEntry.actor}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  {getActionIcon(selectedEntry.actionType)}
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Action Type
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedEntry.actionType}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <ShieldCheck className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Target
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedEntry.target}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <FileText className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Summary
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedEntry.summary}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  <div className="rounded-lg border border-gray-200 px-4 py-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Old Value
                    </p>
                    <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-gray-700">
                      {formatJsonBlock(selectedEntry.oldValue)}
                    </pre>
                  </div>

                  <div className="rounded-lg border border-gray-200 px-4 py-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      New Value
                    </p>
                    <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-gray-700">
                      {formatJsonBlock(selectedEntry.newValue)}
                    </pre>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="text-sm font-semibold text-blue-900">Why this matters</p>
                <p className="mt-2 text-sm text-blue-800">
                  Audit logging supports transparency, legal defensibility, reviewer accountability,
                  and controlled access to sensitive system actions.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <History className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Traceability</h2>
              <p className="mt-1 text-sm text-gray-600">
                Important system decisions and user actions are visible and reviewable.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <ShieldCheck className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Accountability</h2>
              <p className="mt-1 text-sm text-gray-600">
                Sensitive actions can be linked back to a user or a system process.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Database className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Live Backend Linkage</h2>
              <p className="mt-1 text-sm text-gray-600">
                This page now reflects backend audit records from review, config, evidence, and sync workflows.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
        <h2 className="text-sm font-semibold text-blue-900">Current status</h2>
        <p className="mt-2 text-sm text-blue-800">
          This page now loads real audit records from the backend. Review actions and configuration
          updates should appear here as soon as they are logged by backend workflows.
        </p>
      </section>
    </div>
  );
}