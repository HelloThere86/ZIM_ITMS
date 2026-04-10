// src/types/traffic.ts

export interface ModelResult {
  avgWaitPerStep:  number;   // lane-sum wait / steps — comparable across all algorithms
  avgQueuePerStep: number;
  throughput:      number;
  runs:            number;   // how many eval runs were averaged
}

export interface TrafficResults {
  // Keyed by algorithm: "fixed_timer" | "individual_dqn" | "coop_dqn" | "qmix"
  models: Record<string, ModelResult>;

  // Optional training reward curve (episode → reward) for the chart
  trainingRewards: { episode: number; reward: number }[];

  // Optional notes field from backend
  notes?: string;

  // Legacy fields — kept for backwards compatibility if your backend still sends them
  baselineWaitingTime?: number;
  dqnWaitingTime?:      number;
  improvementPercent?:  number;
  trainingEpisodes?:    number;
}