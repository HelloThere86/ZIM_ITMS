// src/pages/ReviewQueuePage.tsx
import { useEffect, useMemo, useState } from "react";
import {
  ClipboardCheck,
  Search,
  Filter,
  Eye,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock3,
  FileText,
  UserCheck,
  RefreshCw,
  Image as ImageIcon,
  Video,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { buildBackendAssetUrl } from "../services/api";
import {
  getReviewQueue,
  submitReviewDecision,
  type ReviewCase,
  type ReviewStatus,
  type ConfidenceLevel,
} from "../services/reviewQueue";

type StatusFilter = "All" | ReviewStatus;

export function ReviewQueuePage() {
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  useEffect(() => {
    async function loadCases() {
      try {
        setLoading(true);
        setError(null);

        const data = await getReviewQueue();
        setCases(data);

        if (data.length > 0 && !selectedCaseId) {
          setSelectedCaseId(data[0].id);
        }
      } catch (err) {
        console.error("Failed to load review queue:", err);
        setError("Failed to load review queue from backend.");
      } finally {
        setLoading(false);
      }
    }

    loadCases();
  }, [selectedCaseId]);

  const filteredCases = useMemo(() => {
    return cases.filter((item) => {
      const matchesSearch =
        item.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.plateNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.intersection.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.time.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus =
        statusFilter === "All" ? true : item.reviewStatus === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [cases, searchTerm, statusFilter]);

  const selectedCase =
    filteredCases.find((item) => item.id === selectedCaseId) ||
    cases.find((item) => item.id === selectedCaseId) ||
    null;

  useEffect(() => {
    setReviewNote(selectedCase?.notes ?? "");
  }, [selectedCase?.id, selectedCase?.notes]);

  const pendingCount = cases.filter((item) => item.reviewStatus === "Pending").length;
  const approvedCount = cases.filter((item) => item.reviewStatus === "Approved").length;
  const rejectedCount = cases.filter((item) => item.reviewStatus === "Rejected").length;

  function getStatusClasses(status: ReviewStatus) {
    if (status === "Pending") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    if (status === "Approved") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  function getConfidenceClasses(level: ConfidenceLevel) {
    if (level === "High") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (level === "Medium") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  async function handleDecision(nextStatus: "Approved" | "Rejected") {
    if (!selectedCase) return;

    try {
      setSaving(true);
      setError(null);

      const noteToSend =
        reviewNote.trim() || `Manual frontend review marked this case as ${nextStatus}.`;

      await submitReviewDecision(selectedCase.id, nextStatus, noteToSend);

      setCases((prev) =>
        prev.map((item) =>
          item.id === selectedCase.id
            ? {
                ...item,
                reviewStatus: nextStatus,
                notes: noteToSend,
              }
            : item
        )
      );
    } catch (err) {
      console.error("Failed to submit review decision:", err);
      setError("Failed to save review decision.");
    } finally {
      setSaving(false);
    }
  }

  const imageUrl = buildBackendAssetUrl(selectedCase?.imageUrl ?? null);
  const videoUrl = buildBackendAssetUrl(selectedCase?.videoUrl ?? null);

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Human Verification</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Review Queue
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            This page supports semi-automated enforcement by routing uncertain or sensitive
            cases to a reviewer before final action is taken.
          </p>
        </div>

        <div className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3">
          <p className="text-sm font-medium text-yellow-900">Awaiting Review</p>
          <p className="mt-1 text-2xl font-semibold text-yellow-800">{pendingCount}</p>
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
          label="Total Review Cases"
          value={loading ? "..." : cases.length.toString()}
          sublabel="Cases surfaced for human verification"
        />
        <StatCard
          label="Pending"
          value={loading ? "..." : pendingCount.toString()}
          sublabel="Awaiting human decision"
        />
        <StatCard
          label="Approved"
          value={loading ? "..." : approvedCount.toString()}
          sublabel="Confirmed after review"
        />
        <StatCard
          label="Rejected"
          value={loading ? "..." : rejectedCount.toString()}
          sublabel="Dismissed after review"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Queued Cases</h2>
                <p className="mt-1 text-sm text-gray-600">
                  Search and filter the cases currently exposed for manual verification.
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
                    <option value="Pending">Pending</option>
                    <option value="Approved">Approved</option>
                    <option value="Rejected">Rejected</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="px-6 py-12 text-sm text-gray-500">Loading review queue...</div>
          ) : filteredCases.length === 0 ? (
            <div className="px-6 py-12">
              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
                <p className="text-base font-medium text-gray-900">No matching review cases found</p>
                <p className="mt-2 text-sm text-gray-600">
                  Adjust the search or filter to see more results.
                </p>
              </div>
            </div>
          ) : (
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
                      Confidence
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Status
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 bg-white">
                  {filteredCases.map((item) => {
                    const isSelected = item.id === selectedCaseId;

                    return (
                      <tr
                        key={item.id}
                        onClick={() => setSelectedCaseId(item.id)}
                        className={`cursor-pointer transition ${
                          isSelected ? "bg-gray-50" : "hover:bg-gray-50"
                        }`}
                      >
                        <td className="px-6 py-4 text-sm font-medium text-gray-900">{item.id}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{item.plateNumber}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{item.intersection}</td>
                        <td className="px-6 py-4 text-sm">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getConfidenceClasses(
                              item.confidenceLevel
                            )}`}
                          >
                            {item.confidence}% · {item.confidenceLevel}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                              item.reviewStatus
                            )}`}
                          >
                            {item.reviewStatus}
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
            <h2 className="text-lg font-semibold text-gray-900">Case Review Detail</h2>
            <p className="mt-1 text-sm text-gray-600">
              Selected case summary, reviewer context, and manual action controls.
            </p>
          </div>

          {!selectedCase ? (
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
              <p className="text-sm font-medium text-gray-900">No case selected</p>
              <p className="mt-2 text-sm text-gray-600">
                Select a case from the queue to inspect and act on it.
              </p>
            </div>
          ) : (
            <div className="mt-6 space-y-5">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Selected Review Case
                    </p>
                    <p className="mt-1 text-lg font-semibold text-gray-900">{selectedCase.id}</p>
                  </div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                      selectedCase.reviewStatus
                    )}`}
                  >
                    {selectedCase.reviewStatus}
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
                    <p className="text-sm font-medium text-gray-900">{selectedCase.plateNumber}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <Clock3 className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Time
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedCase.time}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Confidence
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedCase.confidence}% ({selectedCase.confidenceLevel})
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <FileText className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Reviewer Note
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedCase.notes}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <UserCheck className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Evidence Type
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedCase.evidenceType}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6">
                <p className="text-sm font-semibold text-gray-900">Evidence Preview</p>
                <p className="mt-2 text-sm text-gray-600">
                  This area is reserved for image or video evidence rendering once backend evidence
                  URLs are wired into the review queue.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <button
                  onClick={() => handleDecision("Approved")}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-800 transition hover:bg-green-100"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  Approve Case
                </button>

                <button
                  onClick={() => handleDecision("Rejected")}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800 transition hover:bg-red-100"
                >
                  <XCircle className="h-4 w-4" />
                  Reject Case
                </button>
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="text-sm font-semibold text-blue-900">Next backend step</p>
                <p className="mt-2 text-sm text-blue-800">
                  Replace mock review cases with live backend review records, store reviewer
                  decisions, and log each review action into the audit trail.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-gray-100 p-2">
            <ClipboardCheck className="h-5 w-5 text-gray-700" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Why This Page Matters</h2>
            <p className="mt-1 text-sm text-gray-600">
              This page supports the transparency and fairness story of the project.
            </p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-gray-200 p-4">
            <p className="text-sm font-medium text-gray-900">Human Oversight</p>
            <p className="mt-2 text-sm text-gray-600">
              Low-confidence cases are not enforced blindly.
            </p>
          </div>

          <div className="rounded-lg border border-gray-200 p-4">
            <p className="text-sm font-medium text-gray-900">Operational Control</p>
            <p className="mt-2 text-sm text-gray-600">
              Review actions can be tracked and justified.
            </p>
          </div>

          <div className="rounded-lg border border-gray-200 p-4">
            <p className="text-sm font-medium text-gray-900">Audit Readiness</p>
            <p className="mt-2 text-sm text-gray-600">
              Reviewer decisions can later feed directly into the audit log.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}