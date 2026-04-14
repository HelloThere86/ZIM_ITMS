// src/services/dashboard.ts
import { fetchJson } from "./api";

export interface Stats {
  Flagged: number;
  Approved: number;
  Rejected: number;
}

export interface SmsNotification {
  id: number;
  violationId: string;
  recipientPhone: string | null;
  messageText: string | null;
  status: "Queued" | "Sent" | "Failed" | "Skipped";
  provider: string | null;
  providerMessageId: string | null;
  errorMessage: string | null;
  createdAt: string | null;
  sentAt: string | null;
}

export interface ModelResult {
  avgWaitPerStep: number;
  avgQueuePerStep: number;
  throughput: number;
  runs: number;
}

export interface TrafficResults {
  models: Record<string, ModelResult>;
  baselineWaitingTime?: number | null;
  dqnWaitingTime?: number | null;
  improvementPercent?: number | null;
  bestModelKey?: string | null;
  trainingEpisodes?: number | null;
  trainingRewards?: Array<{
    episode: number;
    reward: number;
  }>;
  notes?: string | null;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actionType: string;
  target: string;
  summary: string;
  severity: "Normal" | "Sensitive" | "Critical";
  oldValue?: string | null;
  newValue?: string | null;
}

export function getDashboardStats(): Promise<Stats> {
  return fetchJson<Stats>("/stats");
}

export function getDashboardSmsNotifications(): Promise<SmsNotification[]> {
  return fetchJson<SmsNotification[]>("/notifications/sms");
}

export function getDashboardTrafficResults(): Promise<TrafficResults> {
  return fetchJson<TrafficResults>("/traffic-results");
}

export function getDashboardAuditLog(): Promise<AuditEntry[]> {
  return fetchJson<AuditEntry[]>("/audit-log");
}