import { fetchJson, postJson } from "./api";

export type ReviewStatus = "Pending" | "Approved" | "Rejected";
export type ConfidenceLevel = "High" | "Medium" | "Low";

export interface ReviewCase {
  id: string;
  plateNumber: string;
  intersection: string;
  time: string;
  confidence: number;
  confidenceLevel: ConfidenceLevel;
  reviewStatus: ReviewStatus;
  evidenceType: "Image" | "Video";
  notes: string;
  imageUrl?: string | null;
  videoUrl?: string | null;
}

interface ReviewDecisionResponse {
  message: string;
  status: ReviewStatus;
  plateNumber?: string;
}

export function getReviewQueue(): Promise<ReviewCase[]> {
  return fetchJson<ReviewCase[]>("/review-queue");
}

export function submitReviewDecision(
  violationId: string,
  decision: "Approved" | "Rejected",
  correctedPlateNumber?: string | null
): Promise<ReviewDecisionResponse> {
  return postJson<ReviewDecisionResponse>(`/review-queue/${violationId}/decision`, {
    decision,
    note: correctedPlateNumber
      ? `Officer selected/corrected plate: ${correctedPlateNumber}`
      : "",
    correctedPlateNumber: correctedPlateNumber || null,
  });
}
