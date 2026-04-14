// src/utils/reviewData.ts
export interface SimilarPlate {
  plate: string;
  score: number;
  distance: number;
  format: string;
}

export interface ReviewData {
  detectedClass?: string;
  ocrPlate?: string;
  registered?: boolean;
  registryStatus?: string;
  registryLookupMode?: string;
  ocrReliable?: boolean;
  ocrMethod?: string;
  ocrCount?: number;
  ocrWeight?: number;
  ocrPeakConfidence?: number;
  similarRegisteredPlates?: SimilarPlate[];
}

export function parseReviewData(reviewNote?: string | null): ReviewData | null {
  if (!reviewNote) return null;

  const marker = "ReviewData=";
  const index = reviewNote.indexOf(marker);

  if (index === -1) return null;

  const jsonPart = reviewNote.slice(index + marker.length).trim();

  try {
    return JSON.parse(jsonPart);
  } catch {
    return null;
  }
}