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

export interface TrafficResults {
  baselineWaitingTime: number;
  dqnWaitingTime: number;
  improvementPercent: number;
  trainingEpisodes: number;
  trainingRewards: Array<{
    episode: number;
    reward: number;
  }>;
  notes?: string;
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