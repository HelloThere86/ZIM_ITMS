// src/services/evidenceSearch.ts

import { fetchJson, postJson } from "./api";

export type EvidenceStatus = "Approved" | "Flagged" | "Rejected";

export interface EvidenceRecord {
  id: string;
  plateNumber: string;
  intersection: string;
  date: string;
  status: EvidenceStatus;
  evidenceType: "Image" | "Video";
  caseReference: string;
  notes: string;
  imageUrl?: string | null;
  videoUrl?: string | null;
}

export interface EvidenceSearchParams {
  plateNumber?: string;
  intersection?: string;
  dateFrom?: string;
  dateTo?: string;
  status?: "All" | EvidenceStatus;
}

interface EvidenceAccessResponse {
  message: string;
  action: "Viewed" | "Exported";
}

export function getEvidenceRecords(
  params: EvidenceSearchParams = {}
): Promise<EvidenceRecord[]> {
  const searchParams = new URLSearchParams();

  if (params.plateNumber) searchParams.set("plateNumber", params.plateNumber);
  if (params.intersection) searchParams.set("intersection", params.intersection);
  if (params.dateFrom) searchParams.set("dateFrom", params.dateFrom);
  if (params.dateTo) searchParams.set("dateTo", params.dateTo);
  if (params.status && params.status !== "All") searchParams.set("status", params.status);

  const query = searchParams.toString();
  return fetchJson<EvidenceRecord[]>(`/evidence-search${query ? `?${query}` : ""}`);
}

export function logEvidenceAccess(
  violationId: string,
  action: "Viewed" | "Exported",
  note?: string
): Promise<EvidenceAccessResponse> {
  return postJson<EvidenceAccessResponse>(`/evidence-search/${violationId}/access`, {
    action,
    userId: null,
    note,
  });
}