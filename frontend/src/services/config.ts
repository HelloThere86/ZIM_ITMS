// src/services/config.ts

import { fetchJson, putJson } from "./api";

export interface ConfigItem {
  key: string;
  value: string;
  updatedAt?: string | null;
  updatedBy?: number | null;
  updatedByName?: string | null;
}

interface UpdateConfigResponse {
  message: string;
}

export function getConfig(): Promise<ConfigItem[]> {
  return fetchJson<ConfigItem[]>("/config");
}

export function updateConfig(
  key: string,
  value: string,
  note?: string
): Promise<UpdateConfigResponse> {
  return putJson<UpdateConfigResponse>(`/config/${key}`, {
    configValue: value,
    note: note ?? `Configuration '${key}' updated from frontend`,
  });
}
