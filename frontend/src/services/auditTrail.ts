// src/services/auditTrail.ts

import { fetchJson } from "./api";

export type AuditSeverity = "Normal" | "Sensitive" | "Critical";

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actionType: string;
  target: string;
  summary: string;
  severity: AuditSeverity;
  oldValue?: string | null;
  newValue?: string | null;
}

export function getAuditLog(): Promise<AuditEntry[]> {
  return fetchJson<AuditEntry[]>("/audit-log");
}