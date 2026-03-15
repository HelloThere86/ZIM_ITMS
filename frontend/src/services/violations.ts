// src/services/violations.ts
import { fetchJson, postJson } from "./api";

export interface Violation {
  id: string;
  plateNumber: string;
  intersection: string;
  time: string;
  confidence: number;
  status: "Flagged" | "Approved" | "Rejected";
}

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

export interface SendSmsResponse {
  ok: boolean;
  status: "Sent" | "Skipped" | "Failed";
  message: string;
  recipientPhone: string | null;
  notificationId: number | null;
}

export function getViolations(): Promise<Violation[]> {
  return fetchJson<Violation[]>("/violations");
}

export function getStats(): Promise<Stats> {
  return fetchJson<Stats>("/stats");
}

export function getSmsNotifications(): Promise<SmsNotification[]> {
  return fetchJson<SmsNotification[]>("/notifications/sms");
}

export function sendViolationSms(violationId: string): Promise<SendSmsResponse> {
  return postJson<SendSmsResponse>(`/violations/${violationId}/send-sms`, {});
}