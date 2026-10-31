export type ResearchJobState = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export interface ResearchJob {
  readonly jobId: string;
  readonly ownerSubject: string;
  readonly datasetId: string;
  readonly instrument: string;
  readonly timeframe: string;
  readonly strategyName: string;
  readonly strategyVersion: string;
  readonly state: ResearchJobState;
  readonly attemptCount: number;
  readonly maxAttempts: number;
  readonly leaseExpiresAt: Date | null;
  readonly errorCode: string | null;
  readonly createdAt: Date;
  readonly updatedAt: Date;
  readonly startedAt: Date | null;
  readonly completedAt: Date | null;
}

export interface ClaimedResearchJob extends ResearchJob {
  readonly state: "RUNNING";
  readonly leaseToken: string;
  readonly leaseExpiresAt: Date;
}

