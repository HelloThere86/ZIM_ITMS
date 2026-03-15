// src/pages/Dashboard.tsx
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Activity,
  AlertTriangle,
  CheckCircle2,
  Shield,
  BarChart3,
  ClipboardCheck,
  Search,
  Smartphone,
  Clock3,
  RefreshCw,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import {
  getDashboardAuditLog,
  getDashboardSmsNotifications,
  getDashboardStats,
  getDashboardTrafficResults,
  type AuditEntry,
  type SmsNotification,
  type Stats,
  type TrafficResults,
} from "../services/dashboard";

type SystemStatus = "Online" | "Degraded" | "Offline";

export function Dashboard() {
  const [stats, setStats] = useState<Stats>({ Flagged: 0, Approved: 0, Rejected: 0 });
  const [smsNotifications, setSmsNotifications] = useState<SmsNotification[]>([]);
  const [trafficResults, setTrafficResults] = useState<TrafficResults | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  async function loadDashboardData() {
    try {
      setPageError(null);

      const [statsData, smsData, trafficData, auditData] = await Promise.all([
        getDashboardStats(),
        getDashboardSmsNotifications(),
        getDashboardTrafficResults(),
        getDashboardAuditLog(),
      ]);

      setStats(statsData);
      setSmsNotifications(smsData);
      setTrafficResults(trafficData);
      setAuditEntries(auditData.slice(0, 5));
    } catch (error) {
      console.error("Error fetching dashboard data:", error);
      setPageError("Failed to load one or more dashboard sections from the backend.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboardData();
  }, []);

  const totalCases = stats.Flagged + stats.Approved + stats.Rejected;
  const pendingReviews = stats.Flagged;
  const processedCases = stats.Approved + stats.Rejected;

  const smsSentCount = useMemo(
    () => smsNotifications.filter((item) => item.status === "Sent").length,
    [smsNotifications]
  );

  const smsSkippedCount = useMemo(
    () => smsNotifications.filter((item) => item.status === "Skipped").length,
    [smsNotifications]
  );

  const smsFailedCount = useMemo(
    () => smsNotifications.filter((item) => item.status === "Failed").length,
    [smsNotifications]
  );

  const recentNotification = smsNotifications[0] ?? null;

  const systemStatus: SystemStatus = pageError
    ? "Degraded"
    : trafficResults
    ? "Online"
    : "Degraded";

  function getSystemStatusClasses(status: SystemStatus) {
    if (status === "Online") {
      return "bg-green-100 text-green-700 border-green-200";
    }
    if (status === "Degraded") {
      return "bg-yellow-100 text-yellow-700 border-yellow-200";
    }
    return "bg-red-100 text-red-700 border-red-200";
  }

  function getAuditSeverityClasses(severity: AuditEntry["severity"]) {
    if (severity === "Critical") {
      return "bg-red-100 text-red-700 border-red-200";
    }
    if (severity === "Sensitive") {
      return "bg-yellow-100 text-yellow-700 border-yellow-200";
    }
    return "bg-green-100 text-green-700 border-green-200";
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Intelligent Traffic Management System</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Dashboard Overview
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            This dashboard summarizes live violation processing, review activity, notification flow,
            audit activity, and traffic optimization performance across the ITMS platform.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadDashboardData}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>

          <div
            className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${getSystemStatusClasses(
              systemStatus
            )}`}
          >
            <Activity className="h-4 w-4" />
            System Status: {systemStatus}
          </div>
        </div>
      </section>

      {pageError && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-900">Backend issue</p>
          <p className="mt-1 text-sm text-red-800">{pageError}</p>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <StatCard
          label="Total Violations"
          value={loading ? "..." : totalCases.toString()}
          sublabel="All captured violation records"
        />
        <StatCard
          label="Pending Review"
          value={loading ? "..." : pendingReviews.toString()}
          sublabel="Cases awaiting human verification"
        />
        <StatCard
          label="Processed Cases"
          value={loading ? "..." : processedCases.toString()}
          sublabel="Approved and rejected cases combined"
        />
        <StatCard
          label="SMS Sent"
          value={loading ? "..." : smsSentCount.toString()}
          sublabel="Notifications successfully sent"
        />
        <StatCard
          label="SMS Skipped"
          value={loading ? "..." : smsSkippedCount.toString()}
          sublabel="Ineligible or duplicate notifications"
        />
        <StatCard
          label="DQN Improvement"
          value={
            loading || !trafficResults
              ? "..."
              : `${trafficResults.improvementPercent.toFixed(2)}%`
          }
          sublabel="Baseline vs DQN waiting time comparison"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Operations Summary</h2>
              <p className="mt-1 text-sm text-gray-600">
                High-level view of case handling and current workflow pressure.
              </p>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-yellow-100 p-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-yellow-800">Flagged Cases</p>
                  <p className="text-2xl font-semibold text-yellow-900">{stats.Flagged}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-yellow-700">
                Cases currently waiting for review or final decision.
              </p>
            </div>

            <div className="rounded-xl border border-green-200 bg-green-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-100 p-2">
                  <CheckCircle2 className="h-5 w-5 text-green-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-green-800">Approved Cases</p>
                  <p className="text-2xl font-semibold text-green-900">{stats.Approved}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-green-700">
                Cases confirmed by the system or through human review.
              </p>
            </div>

            <div className="rounded-xl border border-red-200 bg-red-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-red-100 p-2">
                  <Shield className="h-5 w-5 text-red-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-red-800">Rejected Cases</p>
                  <p className="text-2xl font-semibold text-red-900">{stats.Rejected}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-red-700">
                Cases dismissed after review, exception handling, or evidence issues.
              </p>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-green-200 bg-green-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-100 p-2">
                  <Smartphone className="h-5 w-5 text-green-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-green-800">SMS Sent</p>
                  <p className="text-2xl font-semibold text-green-900">{smsSentCount}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-green-700">
                Enforcement notices successfully delivered through the mock SMS flow.
              </p>
            </div>

            <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-yellow-100 p-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-yellow-800">SMS Skipped</p>
                  <p className="text-2xl font-semibold text-yellow-900">{smsSkippedCount}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-yellow-700">
                Exempt, duplicate, or otherwise ineligible notifications.
              </p>
            </div>

            <div className="rounded-xl border border-red-200 bg-red-50 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-red-100 p-2">
                  <Shield className="h-5 w-5 text-red-700" />
                </div>
                <div>
                  <p className="text-sm font-medium text-red-800">SMS Failed</p>
                  <p className="text-2xl font-semibold text-red-900">{smsFailedCount}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-red-700">
                Notifications that could not be delivered due to missing driver contact data.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">System Snapshot</h2>
          <p className="mt-1 text-sm text-gray-600">
            Quick operational view of the current ITMS environment.
          </p>

          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Backend API</span>
              <span className="text-sm font-medium text-green-700">Connected</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Database</span>
              <span className="text-sm font-medium text-green-700">Connected</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">CV Pipeline</span>
              <span className="text-sm font-medium text-green-700">Active</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Traffic AI</span>
              <span className="text-sm font-medium text-green-700">
                {trafficResults ? "Results Loaded" : "Unavailable"}
              </span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Recent SMS</span>
              <span className="text-sm font-medium text-gray-900">
                {recentNotification?.status ?? "None"}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Traffic AI Snapshot</h2>
          <p className="mt-1 text-sm text-gray-600">
            Current simulation evaluation summary from the DQN results export.
          </p>

          {!trafficResults ? (
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6 text-sm text-gray-600">
              Traffic results are not available yet.
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-gray-200 px-4 py-4">
                <p className="text-xs uppercase tracking-wide text-gray-500">Baseline Wait</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900">
                  {trafficResults.baselineWaitingTime}
                </p>
              </div>

              <div className="rounded-lg border border-gray-200 px-4 py-4">
                <p className="text-xs uppercase tracking-wide text-gray-500">DQN Wait</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900">
                  {trafficResults.dqnWaitingTime}
                </p>
              </div>

              <div className="rounded-lg border border-gray-200 px-4 py-4">
                <p className="text-xs uppercase tracking-wide text-gray-500">Improvement</p>
                <p className="mt-2 text-2xl font-semibold text-gray-900">
                  {trafficResults.improvementPercent.toFixed(2)}%
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Recent Audit Activity</h2>
          <p className="mt-1 text-sm text-gray-600">
            Most recent sensitive and operational events across the platform.
          </p>

          <div className="mt-6 space-y-3">
            {auditEntries.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6 text-sm text-gray-600">
                No recent audit activity available.
              </div>
            ) : (
              auditEntries.map((entry) => (
                <div
                  key={entry.id}
                  className="rounded-lg border border-gray-200 px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-gray-900">{entry.actionType}</p>
                      <p className="mt-1 text-sm text-gray-600">{entry.summary}</p>
                    </div>
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${getAuditSeverityClasses(
                        entry.severity
                      )}`}
                    >
                      {entry.severity}
                    </span>
                  </div>

                  <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                    <span>{entry.actor}</span>
                    <span>{entry.target}</span>
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="h-3.5 w-3.5" />
                      {entry.timestamp}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">System Workflow</h2>
          <p className="mt-1 text-sm text-gray-600">
            Current product story from detection to enforcement and optimization.
          </p>

          <div className="mt-6 space-y-4">
            <div className="rounded-lg border border-gray-200 px-4 py-4">
              <p className="text-sm font-semibold text-gray-900">1. Violation Detection</p>
              <p className="mt-1 text-sm text-gray-600">
                Camera feed is processed through vehicle detection, classification, OCR, evidence
                capture, and database logging.
              </p>
            </div>

            <div className="rounded-lg border border-gray-200 px-4 py-4">
              <p className="text-sm font-semibold text-gray-900">2. Enforcement Decision</p>
              <p className="mt-1 text-sm text-gray-600">
                Cases are auto-approved when eligible, or routed for human review when confidence
                or policy requires intervention.
              </p>
            </div>

            <div className="rounded-lg border border-gray-200 px-4 py-4">
              <p className="text-sm font-semibold text-gray-900">3. Notification + Optimization</p>
              <p className="mt-1 text-sm text-gray-600">
                Eligible violations trigger SMS workflow while the DQN subsystem evaluates signal
                optimization performance separately in simulation.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Quick Access</h2>
          <p className="mt-1 text-sm text-gray-600">
            Use these shortcuts to move through the most important demo flows.
          </p>

          <div className="mt-6 grid grid-cols-1 gap-4">
            <Link
              to="/violations"
              className="group rounded-xl border border-gray-200 p-4 transition-all hover:border-gray-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="rounded-lg bg-gray-100 p-2">
                    <AlertTriangle className="h-5 w-5 text-gray-700" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Violations</h3>
                    <p className="mt-1 text-sm text-gray-600">
                      Review captured violation records and SMS actions.
                    </p>
                  </div>
                </div>
                <ArrowRight className="mt-0.5 h-5 w-5 text-gray-400 transition-transform group-hover:translate-x-1 group-hover:text-gray-600" />
              </div>
            </Link>

            <Link
              to="/traffic-results"
              className="group rounded-xl border border-gray-200 p-4 transition-all hover:border-gray-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="rounded-lg bg-gray-100 p-2">
                    <BarChart3 className="h-5 w-5 text-gray-700" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Traffic Results</h3>
                    <p className="mt-1 text-sm text-gray-600">
                      Present baseline vs DQN metrics and evaluation outputs.
                    </p>
                  </div>
                </div>
                <ArrowRight className="mt-0.5 h-5 w-5 text-gray-400 transition-transform group-hover:translate-x-1 group-hover:text-gray-600" />
              </div>
            </Link>

            <Link
              to="/review-queue"
              className="group rounded-xl border border-gray-200 p-4 transition-all hover:border-gray-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="rounded-lg bg-gray-100 p-2">
                    <ClipboardCheck className="h-5 w-5 text-gray-700" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Review Queue</h3>
                    <p className="mt-1 text-sm text-gray-600">
                      Handle pending cases, confidence checks, and reviewer decisions.
                    </p>
                  </div>
                </div>
                <ArrowRight className="mt-0.5 h-5 w-5 text-gray-400 transition-transform group-hover:translate-x-1 group-hover:text-gray-600" />
              </div>
            </Link>

            <Link
              to="/evidence-search"
              className="group rounded-xl border border-gray-200 p-4 transition-all hover:border-gray-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="rounded-lg bg-gray-100 p-2">
                    <Search className="h-5 w-5 text-gray-700" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Evidence Search</h3>
                    <p className="mt-1 text-sm text-gray-600">
                      Retrieve case evidence by identifier, plate, date, or location.
                    </p>
                  </div>
                </div>
                <ArrowRight className="mt-0.5 h-5 w-5 text-gray-400 transition-transform group-hover:translate-x-1 group-hover:text-gray-600" />
              </div>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}