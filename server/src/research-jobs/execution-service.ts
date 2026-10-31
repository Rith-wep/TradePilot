import { randomUUID } from "node:crypto";
import type { ArtifactVerifierConfig } from "../config/env.js";
import { ArtifactVerificationError } from "../verification/errors.js";
import { ControlledPythonRunner } from "../verification/controlled-python.js";
import type { ClaimedResearchJob } from "./models.js";

export const EXECUTION_CONTRACT_VERSION = "tradepilot-research-execution/v1" as const;

export class ResearchExecutionError extends Error {
  public constructor(public readonly code: string, public readonly retryable: boolean) {
    super("research execution failed");
    this.name = "ResearchExecutionError";
  }
}

export interface ResearchExecutionResult {
  readonly reportId: string;
  readonly signalCount: number;
  readonly reused: boolean;
}

export class PythonResearchExecutionService {
  private readonly runner: ControlledPythonRunner;
  public constructor(private readonly config: ArtifactVerifierConfig, private readonly runtimeRevision: string) {
    this.runner = new ControlledPythonRunner(config, "tradepilot.execution", [
      "--dataset-root", config.datasetRoot, "--report-root", config.reportRoot,
      "--source-root", config.pythonWorkingDirectory,
    ]);
  }

  public async execute(job: ClaimedResearchJob): Promise<ResearchExecutionResult> {
    if (job.implementationRevision !== this.runtimeRevision) {
      throw new ResearchExecutionError("IMPLEMENTATION_REVISION_MISMATCH", false);
    }
    const requestId = `research-job-${randomUUID()}`;
    const input = Buffer.from(JSON.stringify({
      contract_version: EXECUTION_CONTRACT_VERSION, request_id: requestId,
      dataset_id: job.datasetId, instrument: job.instrument, timeframe: job.timeframe,
      strategy: job.strategyName,
      implementation_revision: job.implementationRevision,
    }) + "\n", "utf8");
    let result;
    try { result = await this.runner.run(input); } catch (error) {
      if (error instanceof ArtifactVerificationError) {
        throw new ResearchExecutionError(error.code, error.retryable);
      }
      throw new ResearchExecutionError("EXECUTOR_FAILURE", true);
    }
    const lines = result.stdout.toString("utf8").split(/\r?\n/u).filter(Boolean);
    if (lines.length !== 1) throw new ResearchExecutionError("INVALID_EXECUTION_OUTPUT", false);
    let value: unknown;
    try { value = JSON.parse(lines[0]!); } catch { throw new ResearchExecutionError("INVALID_EXECUTION_OUTPUT", false); }
    if (typeof value !== "object" || value === null) throw new ResearchExecutionError("INVALID_EXECUTION_OUTPUT", false);
    const response = value as Record<string, unknown>;
    if (response["contract_version"] !== EXECUTION_CONTRACT_VERSION || response["request_id"] !== requestId) {
      throw new ResearchExecutionError("EXECUTION_PROTOCOL_MISMATCH", false);
    }
    if (response["status"] === "ERROR") {
      const error = response["error"] as Record<string, unknown> | undefined;
      const code = typeof error?.["code"] === "string" && /^[A-Z][A-Z0-9_]{1,99}$/u.test(error["code"])
        ? error["code"] : "RESEARCH_EXECUTION_FAILED";
      throw new ResearchExecutionError(code, error?.["retryable"] === true);
    }
    if (result.exitCode !== 0 || response["status"] !== "SUCCEEDED"
      || response["dataset_id"] !== job.datasetId
      || typeof response["report_id"] !== "string" || !/^[0-9a-f]{64}$/u.test(response["report_id"])
      || typeof response["signal_count"] !== "number" || !Number.isSafeInteger(response["signal_count"])
      || (response["reused"] !== true && response["reused"] !== false)) {
      throw new ResearchExecutionError("INVALID_EXECUTION_OUTPUT", false);
    }
    return { reportId: response["report_id"], signalCount: response["signal_count"], reused: response["reused"] };
  }
}

