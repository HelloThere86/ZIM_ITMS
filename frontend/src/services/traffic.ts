// src/services/traffic.ts

import { fetchJson } from "./api";
import type { TrafficResults } from "../types/traffic";

export function getTrafficResults(): Promise<TrafficResults> {
  return fetchJson<TrafficResults>("/traffic-results");
}