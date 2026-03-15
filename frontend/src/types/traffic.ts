// src/types/traffic.ts

export interface TrainingRewardPoint {
  episode: number;
  reward: number;
}

export interface TrafficResults {
  baselineWaitingTime: number;
  dqnWaitingTime: number;
  improvementPercent: number;
  trainingEpisodes: number;
  trainingRewards: TrainingRewardPoint[];
  notes: string;
}