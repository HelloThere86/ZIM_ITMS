import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Search,
  Shield,
  Filter,
  Eye,
  MapPin,
  Clock3,
  BadgePercent,
  Smartphone,
  Send,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { PaginationControls } from "../components/PaginationControls";
import { buildBackendAssetUrl } from "../services/api";
import {
  getSmsNotifications,
  getStats,
  getViolations,
  sendViolationSms,
  type SmsNotification,
  type Stats,
  type Violation,
} from "../services/violations";
import { useAuth } from "../context/AuthContext";

type StatusFilter = "All" | "Flagged" | "Approved" | "Rejected";
type SmsDisplayStatus = "Not Sent" | "Sent" | "Skipped" | "Failed" | "Queued";

const ITEMS_PER_PAGE = 10;

export function ViolationsPage() {
  const { can } = useAuth();
  const [selectedViolationId, setSelectedViolationId] = useState<string | null>(null);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [stats, setStats] = useState<Stats>({ Flagged: 0, Approved: 0, Rejected: 0 });
  const [smsNotifications, setSmsNotifications] = useState<SmsNotification[]>([]);

  const [loading, setLoading] = useState(true);
  const [smsSending, setSmsSending] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [smsMessage, setSmsMessage] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");
  const [currentPage, setCurrentPage] = useState(1);
  const canSeeSms = can("sms:send");

  async function loadData() {
    try {
      setPageError(null);

      const [violationsResult, statsResult, smsResult] = await Promise.allSettled([
        getViolations(),
        getStats(),
        canSeeSms
          ? getSmsNotifications()
          : Promise.resolve([] as SmsNotification[]),
      ]);

      const errors: string[] = [];
      let violationsData: Violation[] = [];

      if (violationsResult.status === "fulfilled") {
        violationsData = violationsResult.value;
        setViolations(violationsData);
      } else {
        errors.push("violations");
        setViolations([]);
      }

      if (statsResult.status === "fulfilled") {
        setStats(statsResult.value);
      } else {
        errors.push("violation stats");
        setStats({ Flagged: 0, Approved: 0, Rejected: 0 });
      }

      if (smsResult.status === "fulfilled") {
        setSmsNotifications(smsResult.value);
      } else {
        setSmsNotifications([]);
        if (canSeeSms) {
          errors.push("sms notifications");
        }
      }

      setSelectedViolationId((prev) => {
        const stillExists = prev && violationsData.some((item) => item.id === prev);
        return stillExists ? prev : violationsData[0]?.id ?? null;
      });

      if (errors.length > 0) {
        setPageError(`Failed to load ${errors.join(", ")} from backend.`);
      }
    } catch (error) {
      console.error("Error loading violations page data:", error);
      setPageError("Failed to load violations or SMS data from backend.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const filteredViolations = useMemo(() => {
    return violations.filter((violation) => {
      const matchesSearch =
        violation.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        violation.plateNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
        violation.intersection.toLowerCase().includes(searchTerm.toLowerCase()) ||
        violation.time.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus =
        statusFilter === "All" ? true : violation.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [violations, searchTerm, statusFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredViolations.length / ITEMS_PER_PAGE));

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const paginatedViolations = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredViolations.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [filteredViolations, currentPage]);

  useEffect(() => {
    if (filteredViolations.length === 0) {
      setSelectedViolationId(null);
      return;
    }

    const selectedStillExists = selectedViolationId
      ? filteredViolations.some((violation) => violation.id === selectedViolationId)
      : false;

    if (!selectedStillExists) {
      setSelectedViolationId(filteredViolations[0].id);
    }
  }, [filteredViolations, selectedViolationId]);

  const selectedViolation =
    filteredViolations.find((violation) => violation.id === selectedViolationId) ||
    violations.find((violation) => violation.id === selectedViolationId) ||
    null;

  const latestSmsForSelected = useMemo(() => {
    if (!selectedViolation) return null;
    return (
      smsNotifications.find((item) => item.violationId === selectedViolation.id) || null
    );
  }, [selectedViolation, smsNotifications]);

  const totalCases = stats.Flagged + stats.Approved + stats.Rejected;

  const previewVideoUrl = buildBackendAssetUrl(selectedViolation?.videoUrl);
  const previewImageUrl = buildBackendAssetUrl(selectedViolation?.imageUrl);

  function getStatusClasses(status: Violation["status"]) {
    if (status === "Flagged") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    if (status === "Approved") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  function getConfidenceClasses(confidence: number) {
    if (confidence >= 90) {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (confidence >= 75) {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  function getConfidenceLabel(confidence: number) {
    if (confidence >= 90) return "High";
    if (confidence >= 75) return "Medium";
    return "Low";
  }

  function getSmsStatusClasses(status: SmsDisplayStatus) {
    if (status === "Sent") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (status === "Skipped") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    if (status === "Failed") {
      return "bg-red-100 text-red-800 border border-red-200";
    }
    if (status === "Queued") {
      return "bg-blue-100 text-blue-800 border border-blue-200";
    }
    return "bg-gray-100 text-gray-700 border border-gray-200";
  }

  function getCurrentSmsStatus(): SmsDisplayStatus {
    if (!latestSmsForSelected) return "Not Sent";
    return latestSmsForSelected.status;
  }

  async function handleSendSms() {
    if (!selectedViolation) return;

    try {
      setSmsSending(true);
      setSmsMessage(null);
      setPageError(null);

      const result = await sendViolationSms(selectedViolation.id);
      setSmsMessage(result.message);

      const smsData = await getSmsNotifications();
      setSmsNotifications(smsData);
    } catch (error) {
      console.error("Failed to send SMS:", error);
      setPageError("Failed to send SMS notification.");
    } finally {
      setSmsSending(false);
    }
  }

  const currentSmsStatus = getCurrentSmsStatus();

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Enforcement Monitoring</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Violations
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Review captured traffic violations flowing from the detection pipeline into the
            backend database. This page supports operational visibility, case inspection,
            and notification action.
          </p>
        </div>

        <div className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3">
          <p className="text-sm font-medium text-yellow-900">Pending Reviews</p>
          <p className="mt-1 text-2xl font-semibold text-yellow-800">{stats.Flagged}</p>
        </div>
      </section>

      {pageError && (
        <section className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-900">Backend issue</p>
          <p className="mt-1 text-sm text-red-800">{pageError}</p>
        </section>
      )}

      {canSeeSms && smsMessage && (
        <section className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm font-semibold text-blue-900">SMS result</p>
          <p className="mt-1 text-sm text-red-800">{smsMessage}</p>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Cases"
          value={loading ? "..." : totalCases.toString()}
          sublabel="All recorded violations"
        />
        <StatCard
          label="Flagged"
          value={loading ? "..." : stats.Flagged.toString()}
          sublabel="Awaiting review or action"
        />
        <StatCard
          label="Approved"
          value={loading ? "..." : stats.Approved.toString()}
          sublabel="Confirmed violations"
        />
        <StatCard
          label="Rejected"
          value={loading ? "..." : stats.Rejected.toString()}
          sublabel="Dismissed or invalid cases"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Violation Records</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Search, filter, and inspect records captured by the enforcement pipeline.
                </p>
              </div>

              <div className="flex flex-col gap-3 md:flex-row">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search by ID, plate, location, or time"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm text-gray-900 outline-none transition focus:border-gray-400 md:w-80"
                  />
                </div>

                <div className="relative">
                  <Filter className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                    className="w-full appearance-none rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-8 text-sm text-gray-900 outline-none transition focus:border-gray-400 md:w-44"
                  >
                    <option value="All">All Statuses</option>
                    <option value="Flagged">Flagged</option>
                    <option value="Approved">Approved</option>
                    <option value="Rejected">Rejected</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="px-6 py-10 text-sm text-gray-500">Loading violation records...</div>
          ) : filteredViolations.length === 0 ? (
            <div className="px-6 py-12">
              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
                <p className="text-base font-medium text-gray-900">No matching violations found</p>
                <p className="mt-2 text-sm text-gray-600">
                  Try adjusting the search text or selected status filter.
                </p>
              </div>
            </div>
          ) : (
            <>
              <PaginationControls
                currentPage={currentPage}
                totalPages={totalPages}
                totalItems={filteredViolations.length}
                itemsPerPage={ITEMS_PER_PAGE}
                label="violations"
                onPrevious={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                onNext={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              />

              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead className="border-b border-gray-200 bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Case ID
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Plate Number
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Intersection
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Time
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Confidence
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                        Status
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-gray-200 bg-white">
                    {paginatedViolations.map((violation) => {
                      const isSelected = selectedViolationId === violation.id;

                      return (
                        <tr
                          key={violation.id}
                          onClick={() => {
                            setSelectedViolationId(violation.id);
                            setSmsMessage(null);
                          }}
                          className={`cursor-pointer transition ${
                            isSelected ? "bg-gray-50" : "hover:bg-gray-50"
                          }`}
                        >
                          <td className="px-6 py-4 text-sm font-medium text-gray-900">
                            {violation.id}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-900">
                            {violation.plateNumber}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-900">
                            {violation.intersection}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-900">{violation.time}</td>
                          <td className="px-6 py-4 text-sm">
                            <span
                              className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${getConfidenceClasses(
                                violation.confidence
                              )}`}
                            >
                              {violation.confidence}% · {getConfidenceLabel(violation.confidence)}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm">
                            <span
                              className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                                violation.status
                              )}`}
                            >
                              {violation.status}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Case Detail</h2>
            <p className="mt-1 text-sm text-gray-600">
              Selected record summary, evidence context, and notification controls.
            </p>
          </div>

          {!selectedViolation ? (
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
              <p className="text-sm font-medium text-gray-900">No case selected</p>
              <p className="mt-2 text-sm text-gray-600">
                Select a violation record from the table to inspect it.
              </p>
            </div>
          ) : (
            <div className="mt-6 space-y-5">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Selected Case
                    </p>
                    <p className="mt-1 text-lg font-semibold text-gray-900">
                      {selectedViolation.id}
                    </p>
                  </div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                      selectedViolation.status
                    )}`}
                  >
                    {selectedViolation.status}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <Eye className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Plate Number
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedViolation.plateNumber}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <MapPin className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Intersection
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedViolation.intersection}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <Clock3 className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Timestamp
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedViolation.time}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <BadgePercent className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Confidence
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedViolation.confidence}% ({getConfidenceLabel(selectedViolation.confidence)})
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
                  <BadgePercent className="mt-0.5 h-4 w-4 text-blue-600" />
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-blue-500">
                      Applicable Fine
                    </p>
                    <p className="text-sm font-bold text-blue-900">USD $30.00</p>
                  </div>
                </div>
              </div>

              {canSeeSms && (
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <div className="flex items-start gap-3">
                    <Smartphone className="mt-0.5 h-4 w-4 text-gray-500" />
                    <div className="w-full">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">SMS Notification</p>
                          <p className="mt-1 text-sm text-gray-600">
                            Send a violation notice to the registered vehicle owner when eligible.
                          </p>
                        </div>

                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getSmsStatusClasses(
                            currentSmsStatus
                          )}`}
                        >
                          {currentSmsStatus}
                        </span>
                      </div>

                      <div className="mt-4 space-y-2 text-sm text-gray-700">
                        <p>
                          <span className="font-medium text-gray-900">Recipient:</span>{" "}
                          {latestSmsForSelected?.recipientPhone ?? "Not available yet"}
                        </p>
                        <p>
                          <span className="font-medium text-gray-900">Provider:</span>{" "}
                          {latestSmsForSelected?.provider ?? "MockSMS / none yet"}
                        </p>

                        <div className="mt-3 rounded-md border border-gray-200 bg-white p-3 shadow-sm">
                          <p className="mb-1 text-[10px] font-bold uppercase text-gray-400">
                            Generated SMS Message Content:
                          </p>
                          <p className="text-xs italic leading-relaxed text-gray-600">
                            {latestSmsForSelected?.messageText ||
                              "Awaiting system sync to generate message..."}
                          </p>
                        </div>

                        <p className="mt-2">
                          <span className="font-medium text-gray-900">Latest Result:</span>{" "}
                          {latestSmsForSelected?.errorMessage || "Validated for transmission."}
                        </p>
                      </div>

                      <div className="mt-4">
                        <button
                          onClick={handleSendSms}
                          disabled={smsSending}
                          className="inline-flex items-center gap-2 rounded-lg bg-gray-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-900 disabled:opacity-50"
                        >
                          <Send className="h-4 w-4" />
                          {smsSending ? "Sending..." : "Send SMS Notice"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-gray-600" />
                  <p className="text-sm font-semibold text-gray-900">Evidence Preview</p>
                </div>

                {previewVideoUrl ? (
                  <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-inner">
                    <video
                      src={previewVideoUrl}
                      controls
                      className="h-48 w-full bg-black object-contain"
                    />
                  </div>
                ) : previewImageUrl ? (
                  <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-inner">
                    <img
                      src={previewImageUrl}
                      alt="Violation Snapshot"
                      className="h-48 w-full bg-gray-100 object-contain"
                    />
                  </div>
                ) : (
                  <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
                    <p className="text-xs italic text-gray-500">
                      No digital evidence file is currently available for this record.
                    </p>
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 text-blue-700" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900">Current status</p>
                    <p className="mt-1 text-sm text-blue-800">
                      Violations are now linked to SMS notification actions, and each send attempt
                      should appear in the audit trail and notification log.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
