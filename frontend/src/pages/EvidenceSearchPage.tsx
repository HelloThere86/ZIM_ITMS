// src/pages/EvidenceSearchPage.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Search,
  ChevronDown,
  FileDown,
  Eye,
  CalendarDays,
  MapPin,
  BadgeCheck,
  Shield,
  FileText,
  RefreshCw,
  Image as ImageIcon,
  Video,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { buildBackendAssetUrl } from "../services/api";
import {
  getEvidenceRecords,
  logEvidenceAccess,
  type EvidenceRecord,
  type EvidenceStatus,
} from "../services/evidenceSearch";

type StatusFilter = "All" | EvidenceStatus;

export function EvidenceSearchPage() {
  const [plateNumber, setPlateNumber] = useState("");
  const [intersection, setIntersection] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All");

  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const viewedRecordIdsRef = useRef<Set<string>>(new Set());

  async function loadEvidence(params?: {
    plateNumber?: string;
    intersection?: string;
    dateFrom?: string;
    dateTo?: string;
    status?: StatusFilter;
  }) {
    try {
      setError(null);
      if (!loading) setSearching(true);

      const data = await getEvidenceRecords(params ?? {});
      setRecords(data);

      if (data.length > 0) {
        setSelectedRecordId((prev) => {
          const stillExists = prev && data.some((item) => item.id === prev);
          return stillExists ? prev : data[0].id;
        });
      } else {
        setSelectedRecordId(null);
      }
    } catch (err) {
      console.error("Failed to load evidence records:", err);
      setError("Failed to load evidence records from backend.");
      setRecords([]);
      setSelectedRecordId(null);
    } finally {
      setLoading(false);
      setSearching(false);
    }
  }

  useEffect(() => {
    loadEvidence();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedRecord =
    records.find((record) => record.id === selectedRecordId) || null;

  const approvedCount = useMemo(
    () => records.filter((item) => item.status === "Approved").length,
    [records]
  );
  const flaggedCount = useMemo(
    () => records.filter((item) => item.status === "Flagged").length,
    [records]
  );
  const rejectedCount = useMemo(
    () => records.filter((item) => item.status === "Rejected").length,
    [records]
  );

  function handleSearch() {
    loadEvidence({
      plateNumber,
      intersection,
      dateFrom,
      dateTo,
      status: statusFilter,
    });
  }

  function handleReset() {
    setPlateNumber("");
    setIntersection("");
    setDateFrom("");
    setDateTo("");
    setStatusFilter("All");
    loadEvidence({});
  }

  function getStatusClasses(status: EvidenceStatus) {
    if (status === "Approved") {
      return "bg-green-100 text-green-800 border border-green-200";
    }
    if (status === "Flagged") {
      return "bg-yellow-100 text-yellow-800 border border-yellow-200";
    }
    return "bg-red-100 text-red-800 border border-red-200";
  }

  async function handleExportSelected() {
  if (!selectedRecord) return;

  const assetUrl =
    buildBackendAssetUrl(selectedRecord.videoUrl) ||
    buildBackendAssetUrl(selectedRecord.imageUrl);

  if (!assetUrl) {
    alert("No downloadable evidence file is available for this record yet.");
    return;
  }

  try {
    await logEvidenceAccess(
      selectedRecord.id,
      "Exported",
      `Evidence exported for ${selectedRecord.id}`
    );
  } catch (err) {
    console.error("Failed to log evidence export:", err);
  }

  const link = document.createElement("a");
  link.href = assetUrl;
  link.download = `${selectedRecord.id}_${selectedRecord.evidenceType.toLowerCase()}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

const previewVideoUrl = buildBackendAssetUrl(selectedRecord?.videoUrl);
const previewImageUrl = buildBackendAssetUrl(selectedRecord?.imageUrl);

  useEffect(() => {
  async function logView() {
    if (!selectedRecord) return;
    if (viewedRecordIdsRef.current.has(selectedRecord.id)) return;

    try {
      await logEvidenceAccess(
        selectedRecord.id,
        "Viewed",
        `Evidence preview opened for ${selectedRecord.id}`
      );
      viewedRecordIdsRef.current.add(selectedRecord.id);
    } catch (err) {
      console.error("Failed to log evidence view:", err);
    }
  }

  logView();
}, [selectedRecord]);

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Evidence Retrieval</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
            Evidence Search
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-gray-600">
            Search and retrieve evidence records for investigation, legal review, and court-ready
            documentation. This page supports traceability and controlled access to stored case data.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadEvidence({ plateNumber, intersection, dateFrom, dateTo, status: statusFilter })}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
            <p className="text-sm font-medium text-blue-900">Evidence Records</p>
            <p className="mt-1 text-2xl font-semibold text-blue-800">
              {loading ? "..." : records.length}
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
          label="Total Records"
          value={loading ? "..." : records.length.toString()}
          sublabel="Stored searchable evidence"
        />
        <StatCard
          label="Approved"
          value={loading ? "..." : approvedCount.toString()}
          sublabel="Ready for operational use"
        />
        <StatCard
          label="Flagged"
          value={loading ? "..." : flaggedCount.toString()}
          sublabel="Requires further review"
        />
        <StatCard
          label="Rejected"
          value={loading ? "..." : rejectedCount.toString()}
          sublabel="Not suitable for enforcement"
        />
      </section>

      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-200 px-6 py-5">
          <h2 className="text-lg font-semibold text-gray-900">Search Filters</h2>
          <p className="mt-1 text-sm text-gray-600">
            Locate records by plate number, intersection, date range, or case status.
          </p>
        </div>

        <div className="p-6 space-y-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                Plate Number
              </label>
              <input
                type="text"
                value={plateNumber}
                onChange={(e) => setPlateNumber(e.target.value)}
                placeholder="Enter plate number"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                Intersection
              </label>
              <div className="relative">
                <select
                  value={intersection}
                  onChange={(e) => setIntersection(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-gray-300 px-3 py-2 pr-10 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                >
                  <option value="">All intersections</option>
                  <option value="kirkman">Kirkman / Harare Drive</option>
                  <option value="samora">Samora Machel</option>
                  <option value="julius">Julius Nyerere Road</option>
                  <option value="borrowdale">Borrowdale Road / Harare Drive</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                From Date
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                To Date
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-gray-400"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">Status</label>
              <div className="relative">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                  className="w-full appearance-none rounded-lg border border-gray-300 px-3 py-2 pr-10 text-sm text-gray-900 outline-none transition focus:border-gray-400"
                >
                  <option value="All">All statuses</option>
                  <option value="Approved">Approved</option>
                  <option value="Flagged">Flagged</option>
                  <option value="Rejected">Rejected</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              </div>
            </div>

            <div className="md:col-span-1 xl:col-span-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-end">
              <button
                onClick={handleReset}
                disabled={searching}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
              >
                Reset Filters
              </button>

              <button
                onClick={handleSearch}
                disabled={searching}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-gray-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-900 disabled:opacity-50"
              >
                <Search className="h-4 w-4" />
                {searching ? "Searching..." : "Search Evidence"}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-5 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Search Results</h2>
              <p className="mt-1 text-sm text-gray-600">
                Matching records available for review and export.
              </p>
            </div>
            <div className="text-sm font-medium text-gray-500">
              {loading ? "..." : `${records.length} result${records.length === 1 ? "" : "s"}`}
            </div>
          </div>

          {loading ? (
            <div className="px-6 py-12 text-sm text-gray-500">Loading evidence records...</div>
          ) : records.length === 0 ? (
            <div className="px-6 py-12">
              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
                <p className="text-base font-medium text-gray-900">No evidence records found</p>
                <p className="mt-2 text-sm text-gray-600">
                  Adjust the filters and search again.
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Plate Number
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Intersection
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Date
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-600">
                      View
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-200 bg-white">
                  {records.map((record) => {
                    const isSelected = selectedRecordId === record.id;

                    return (
                      <tr
                        key={record.id}
                        onClick={() => setSelectedRecordId(record.id)}
                        className={`cursor-pointer transition ${
                          isSelected ? "bg-gray-50" : "hover:bg-gray-50"
                        }`}
                      >
                        <td className="px-6 py-4 text-sm font-medium text-gray-900">{record.id}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{record.plateNumber}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{record.intersection}</td>
                        <td className="px-6 py-4 text-sm text-gray-900">{record.date}</td>
                        <td className="px-6 py-4 text-sm">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                              record.status
                            )}`}
                          >
                            {record.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500">
                          <Eye className="h-4 w-4" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="border-t border-gray-200 px-6 py-4 flex justify-end">
            <button
              onClick={handleExportSelected}
              disabled={!selectedRecord}
              className="inline-flex items-center gap-2 rounded-lg bg-gray-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-900 disabled:opacity-50"
            >
              <FileDown className="h-4 w-4" />
              Export Selected Evidence
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Evidence Detail</h2>
            <p className="mt-1 text-sm text-gray-600">
              Selected record summary and evidence package preview.
            </p>
          </div>

          {!selectedRecord ? (
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
              <p className="text-sm font-medium text-gray-900">No record selected</p>
              <p className="mt-2 text-sm text-gray-600">
                Select an evidence record from the table to inspect it.
              </p>
            </div>
          ) : (
            <div className="mt-6 space-y-5">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Selected Record
                    </p>
                    <p className="mt-1 text-lg font-semibold text-gray-900">{selectedRecord.id}</p>
                  </div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusClasses(
                      selectedRecord.status
                    )}`}
                  >
                    {selectedRecord.status}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <BadgeCheck className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Plate Number
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedRecord.plateNumber}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <MapPin className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Intersection
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedRecord.intersection}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <CalendarDays className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Date
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedRecord.date}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <Shield className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Case Reference
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedRecord.caseReference}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-lg border border-gray-200 px-4 py-3">
                  <FileText className="mt-0.5 h-4 w-4 text-gray-500" />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                      Notes
                    </p>
                    <p className="text-sm font-medium text-gray-900">{selectedRecord.notes}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6">
                <div className="flex items-center gap-2">
                  {selectedRecord.evidenceType === "Video" ? (
                    <Video className="h-4 w-4 text-gray-600" />
                  ) : (
                    <ImageIcon className="h-4 w-4 text-gray-600" />
                  )}
                  <p className="text-sm font-semibold text-gray-900">Evidence Preview</p>
                </div>

                {previewVideoUrl ? (
                    <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white">
                        <video
                        src={previewVideoUrl}
                        controls
                        className="h-64 w-full bg-black object-contain"
                        />
                    </div>
                    ) : previewImageUrl ? (
                    <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white">
                        <img
                        src={previewImageUrl}
                        alt={`Evidence for ${selectedRecord.id}`}
                        className="h-64 w-full object-contain bg-gray-100"
                        />
                    </div>
                    ) : (
                    <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
                        <p className="text-sm text-gray-600">
                        No preview file is currently available for this record.
                        </p>
                    </div>
                    )}

                <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-wide text-gray-500">Evidence Type</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">
                    {selectedRecord.evidenceType}
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="text-sm font-semibold text-blue-900">Current status</p>
                <p className="mt-2 text-sm text-blue-800">
                  This page now loads live searchable evidence records from the backend and can
                  preview available image or video evidence files.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}