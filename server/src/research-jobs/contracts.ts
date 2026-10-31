import { createHash } from "node:crypto";

export const RESEARCH_JOB_REQUEST_VERSION = "tradepilot-research-job-request/v1" as const;
export const RESEARCH_JOB_INSTRUMENTS = ["EURUSD", "GBPUSD"] as const;
export const RESEARCH_JOB_TIMEFRAMES = ["H1"] as const;
export const RESEARCH_JOB_STRATEGIES = ["price_range_breakout", "ema_rsi_trend_pullback"] as const;
export type ResearchJobInstrument = typeof RESEARCH_JOB_INSTRUMENTS[number];
export type ResearchJobStrategy = typeof RESEARCH_JOB_STRATEGIES[number];

export interface ResearchJobRequest {
  readonly contractVersion: typeof RESEARCH_JOB_REQUEST_VERSION;
  readonly idempotencyKey: string;
  readonly datasetId: string;
  readonly instrument: ResearchJobInstrument;
  readonly timeframe: "H1";
  readonly strategy: { readonly name: ResearchJobStrategy; readonly version: "v1" };
}

const SHA256 = /^[0-9a-f]{64}$/u;
const IDEMPOTENCY = /^[A-Za-z0-9_-]{8,100}$/u;

export class JobRequestValidationError extends Error {}

export function parseResearchJobRequest(value: unknown): ResearchJobRequest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new JobRequestValidationError("body must be an object");
  const body = value as Record<string, unknown>;
  const allowed = ["contractVersion", "idempotencyKey", "datasetId", "instrument", "timeframe", "strategy"];
  if (Object.keys(body).some((key) => !allowed.includes(key))) throw new JobRequestValidationError("unknown request field");
  const strategy = body["strategy"];
  if (typeof strategy !== "object" || strategy === null || Array.isArray(strategy)) throw new JobRequestValidationError("strategy is invalid");
  const strategyRecord = strategy as Record<string, unknown>;
  if (Object.keys(strategyRecord).some((key) => !["name", "version"].includes(key))) throw new JobRequestValidationError("unknown strategy field");
  if (body["contractVersion"] !== RESEARCH_JOB_REQUEST_VERSION
    || typeof body["idempotencyKey"] !== "string" || !IDEMPOTENCY.test(body["idempotencyKey"])
    || typeof body["datasetId"] !== "string" || !SHA256.test(body["datasetId"])
    || !RESEARCH_JOB_INSTRUMENTS.includes(body["instrument"] as ResearchJobInstrument)
    || body["timeframe"] !== "H1"
    || !RESEARCH_JOB_STRATEGIES.includes(strategyRecord["name"] as ResearchJobStrategy)
    || strategyRecord["version"] !== "v1") {
    throw new JobRequestValidationError("request does not match the supported research-job contract");
  }
  return Object.freeze({
    contractVersion: RESEARCH_JOB_REQUEST_VERSION,
    idempotencyKey: body["idempotencyKey"],
    datasetId: body["datasetId"],
    instrument: body["instrument"] as ResearchJobInstrument,
    timeframe: "H1",
    strategy: Object.freeze({ name: strategyRecord["name"] as ResearchJobStrategy, version: "v1" }),
  });
}

export function requestFingerprint(request: ResearchJobRequest): string {
  const canonical = JSON.stringify({
    contractVersion: request.contractVersion, datasetId: request.datasetId,
    instrument: request.instrument, timeframe: request.timeframe,
    strategy: { name: request.strategy.name, version: request.strategy.version },
  });
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

