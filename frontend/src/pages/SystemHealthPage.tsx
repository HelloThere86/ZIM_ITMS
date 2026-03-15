// src/pages/SystemHealthPage.tsx
import { StatCard } from "../components/StatCard";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  HardDrive,
  Network,
  Server,
  Shield,
  WifiOff,
  Brain,
  Camera,
} from "lucide-react";

type ServiceStatus = "Healthy" | "Warning" | "Offline";

interface ServiceItem {
  name: string;
  description: string;
  status: ServiceStatus;
}

interface AlertItem {
  id: number;
  message: string;
  severity: "Critical" | "Warning" | "Info";
  time: string;
}

const chartData = [
  { name: "Tue", violations: 120 },
  { name: "Wed", violations: 160 },
  { name: "Thu", violations: 140 },
  { name: "Fri", violations: 180 },
  { name: "Sat", violations: 120 },
  { name: "Sun", violations: 90 },
];

const services: ServiceItem[] = [
  {
    name: "Backend API",
    description: "Core application and endpoint availability",
    status: "Healthy",
  },
  {
    name: "Database",
    description: "Violation records and evidence metadata storage",
    status: "Healthy",
  },
  {
    name: "CV Pipeline",
    description: "Vehicle detection, classification, and OCR processing",
    status: "Healthy",
  },
  {
    name: "Evidence Storage",
    description: "Local evidence file storage and retrieval layer",
    status: "Warning",
  },
  {
    name: "Network Sync",
    description: "Offline-first sync path to central systems",
    status: "Offline",
  },
  {
    name: "Traffic AI Model",
    description: "DQN controller availability and readiness",
    status: "Healthy",
  },
];

const alerts: AlertItem[] = [
  {
    id: 1,
    message: "Network sync unavailable. System operating in offline-first mode.",
    severity: "Warning",
    time: "08:14",
  },
  {
    id: 2,
    message: "Evidence storage nearing configured usage threshold.",
    severity: "Warning",
    time: "07:48",
  },
  {
    id: 3,
    message: "Traffic AI model loaded successfully.",
    severity: "Info",
    time: "07:30",
  },
];

export function SystemHealthPage() {
  const healthyCount = services.filter((service) => service.status === "Healthy").length;
  const warningCount = services.filter((service) => service.status === "Warning").length;
  const offlineCount = services.filter((service) => service.status === "Offline").length;
  const maxViolations = Math.max(...chartData.map((item) => item.violations));

  function getStatusClasses(status: ServiceStatus) {
    if (status === "Healthy") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (status === "Warning") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  function getAlertClasses(severity: AlertItem["severity"]) {
    if (severity === "Critical") {
      return "bg-red-100 text-red-800 border border-red-200";
    }
    if (severity === "Warning") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-blue-100 text-blue-800 border border-blue-200";
  }

  function getServiceIcon(name: string) {
    if (name === "Backend API") return <Server className="h-5 w-5 text-gray-700" />;
    if (name === "Database") return <Database className="h-5 w-5 text-gray-700" />;
    if (name === "CV Pipeline") return <Camera className="h-5 w-5 text-gray-700" />;
    if (name === "Evidence Storage") return <HardDrive className="h-5 w-5 text-gray-700" />;
    if (name === "Network Sync") return <Network className="h-5 w-5 text-gray-700" />;
    return <Brain className="h-5 w-5 text-gray-700" />;
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Operational Monitoring</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            System Health
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Monitor the operational state of the ITMS platform, including backend availability,
            storage readiness, CV pipeline health, model status, and offline-first sync behavior.
          </p>
        </div>

        <div className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3">
          <p className="text-sm font-medium text-yellow-900">Current Mode</p>
          <p className="mt-1 text-lg font-semibold text-yellow-800">Offline-First Active</p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Healthy Services"
          value={healthyCount.toString()}
          sublabel="Components operating normally"
        />
        <StatCard
          label="Warnings"
          value={warningCount.toString()}
          sublabel="Components needing attention"
        />
        <StatCard
          label="Offline Services"
          value={offlineCount.toString()}
          sublabel="Unavailable or disconnected"
        />
        <StatCard
          label="System Posture"
          value="Stable"
          sublabel="Degraded but operational"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Activity className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Service Status Overview</h2>
              <p className="mt-1 text-sm text-gray-600">
                Current health state of major platform components.
              </p>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            {services.map((service) => (
              <div
                key={service.name}
                className="rounded-xl border border-gray-200 p-4 transition hover:border-gray-300"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex gap-3">
                    <div className="rounded-lg bg-gray-100 p-2">{getServiceIcon(service.name)}</div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">{service.name}</h3>
                      <p className="mt-1 text-sm text-gray-600">{service.description}</p>
                    </div>
                  </div>

                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                      service.status
                    )}`}
                  >
                    {service.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Shield className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Runtime Snapshot</h2>
              <p className="mt-1 text-sm text-gray-600">
                Quick operational indicators from the current system state.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Backend Connection</span>
              <span className="text-sm font-medium text-green-700">Connected</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Database Access</span>
              <span className="text-sm font-medium text-green-700">Available</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">CV Module</span>
              <span className="text-sm font-medium text-green-700">Running</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Evidence Storage</span>
              <span className="text-sm font-medium text-yellow-700">Near Limit</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">Network Sync</span>
              <span className="text-sm font-medium text-red-700">Offline</span>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <span className="text-sm text-gray-600">DQN Model</span>
              <span className="text-sm font-medium text-green-700">Loaded</span>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Activity className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Violation Throughput Trend</h2>
              <p className="mt-1 text-sm text-gray-600">
                Recent processed traffic violation volume across the current monitoring window.
              </p>
            </div>
          </div>

          <div className="mt-8">
            <div className="flex h-72 items-end gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4">
              {chartData.map((item) => {
                const height = `${(item.violations / maxViolations) * 100}%`;

                return (
                  <div key={item.name} className="flex flex-1 flex-col items-center justify-end">
                    <div
                      className="w-full rounded-t-md bg-gray-800 transition-all"
                      style={{ height }}
                      title={`${item.name}: ${item.violations}`}
                    />
                    <p className="mt-2 text-xs text-gray-500">{item.name}</p>
                    <p className="text-[10px] text-gray-400">{item.violations}</p>
                  </div>
                );
              })}
            </div>
          </div>

          <p className="mt-4 text-sm text-gray-600">
            This chart is currently frontend demo data. Later it should reflect backend
            monitoring or database-derived operational metrics.
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <AlertTriangle className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Alerts</h2>
              <p className="mt-1 text-sm text-gray-600">
                Important operational notices and degraded-state indicators.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            {alerts.map((alert) => (
              <div key={alert.id} className="rounded-xl border border-gray-200 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex gap-3">
                    <div className="rounded-lg bg-gray-100 p-2">
                      {alert.severity === "Critical" ? (
                        <WifiOff className="h-4 w-4 text-red-700" />
                      ) : alert.severity === "Warning" ? (
                        <AlertTriangle className="h-4 w-4 text-yellow-700" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 text-blue-700" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{alert.message}</p>
                      <p className="mt-1 text-xs text-gray-500">Logged at {alert.time}</p>
                    </div>
                  </div>

                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getAlertClasses(
                      alert.severity
                    )}`}
                  >
                    {alert.severity}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Server className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Backend Resilience</h2>
              <p className="mt-1 text-sm text-gray-600">
                The core application remains operational even with sync disruption.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <HardDrive className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Offline-First Readiness</h2>
              <p className="mt-1 text-sm text-gray-600">
                Local storage and local processing remain central to the product architecture.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-gray-100 p-2">
              <Brain className="h-5 w-5 text-gray-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Model Operational Status</h2>
              <p className="mt-1 text-sm text-gray-600">
                The traffic AI component is represented as an active system module, not a hidden prototype.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
        <h2 className="text-sm font-semibold text-blue-900">Implementation note</h2>
        <p className="mt-2 text-sm text-blue-800">
          This page is presentation-ready from a frontend perspective. The next step is to connect
          real backend service checks, sync state, storage metrics, and alert logs so these values
          reflect live operational data instead of curated demo values.
        </p>
      </section>
    </div>
  );
}