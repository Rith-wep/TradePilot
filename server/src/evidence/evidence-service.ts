import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Ajv2020, type AnySchema, type ValidateFunction } from "ajv/dist/2020.js";
import type { ArtifactVerifierConfig } from "../config/env.js";
import { ControlledPythonRunner } from "../verification/controlled-python.js";
import { ArtifactVerificationError } from "../verification/errors.js";
import type {
  CandidateEvidence,
  EvidenceRequest,
  EvidenceResponse,
  GetEvidenceRequest,
  ListEvidenceRequest,
} from "./contracts.js";
import { EVIDENCE_CONTRACT_VERSION } from "./contracts.js";

export class CandidateEvidenceService {
  private readonly requestValidator: ValidateFunction;
  private readonly responseValidator: ValidateFunction;
  private readonly runner: ControlledPythonRunner;

  public constructor(private readonly config: ArtifactVerifierConfig) {
    const ajv = new Ajv2020({ allErrors: true, strict: true });
    this.requestValidator = ajv.compile(this.schema("candidate-evidence-v1.request.schema.json"));
    this.responseValidator = ajv.compile(this.schema("candidate-evidence-v1.response.schema.json"));
    this.runner = new ControlledPythonRunner(config, "tradepilot.contracts.evidence_cli", [
      "--report-root", config.reportRoot,
    ]);
  }

  public async list(reportId: string, offset: number, limit: number, requestId: string) {
    const request: ListEvidenceRequest = {
      contract_version: EVIDENCE_CONTRACT_VERSION,
      request_id: requestId,
      operation: "list_candidates",
      report_id: reportId,
      offset,
      limit,
    };
    const response = await this.execute(request);
    if (response.status !== "OK" || response.operation !== "list_candidates"
      || response.report_id !== reportId
      || response.candidates.some((item) => item.reportId !== reportId)) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_RESPONSE", "candidate evidence response is invalid", false);
    }
    return response;
  }

  public async get(evidenceId: string, requestId: string): Promise<CandidateEvidence> {
    const request: GetEvidenceRequest = {
      contract_version: EVIDENCE_CONTRACT_VERSION,
      request_id: requestId,
      operation: "get_evidence",
      evidence_id: evidenceId,
    };
    const response = await this.execute(request);
    if (response.status !== "OK" || response.operation !== "get_evidence"
      || response.evidence.candidateEvidenceId !== evidenceId) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_RESPONSE", "candidate evidence response is invalid", false);
    }
    return response.evidence;
  }

  private async execute(request: EvidenceRequest): Promise<EvidenceResponse> {
    if (!this.requestValidator(request)) {
      throw new ArtifactVerificationError("INVALID_REQUEST", "INVALID_REQUEST", "candidate evidence request is invalid", false);
    }
    const input = Buffer.from(`${JSON.stringify(request)}\n`, "utf8");
    if (input.byteLength > this.config.maxInputBytes) {
      throw new ArtifactVerificationError("INVALID_REQUEST", "REQUEST_TOO_LARGE", "candidate evidence request is too large", false);
    }
    const result = await this.runner.run(input);
    let response: unknown;
    try {
      const lines = result.stdout.toString("utf8").split(/\r?\n/u).filter((line) => line.length > 0);
      if (lines.length !== 1 || lines[0] === undefined) throw new Error("invalid stdout");
      response = JSON.parse(lines[0]);
    } catch {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_JSON_RESPONSE", "candidate evidence response is invalid", false);
    }
    if (!this.responseValidator(response)) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_RESPONSE", "candidate evidence response is invalid", false);
    }
    const typed = response as EvidenceResponse;
    if (typed.request_id !== request.request_id) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "REQUEST_ID_MISMATCH", "candidate evidence response mismatch", false);
    }
    if (typed.status === "ERROR") {
      throw new ArtifactVerificationError("CONTRACT_FAILURE", typed.error.code, "candidate evidence is unavailable", typed.error.retryable);
    }
    if (result.exitCode !== 0) {
      throw new ArtifactVerificationError("SUBPROCESS_FAILURE", "VERIFIER_EXIT_FAILURE", "candidate evidence process failed", true);
    }
    return typed;
  }

  private schema(name: string): AnySchema {
    try {
      return JSON.parse(readFileSync(join(this.config.schemaDirectory, name), "utf8")) as AnySchema;
    } catch {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "SCHEMA_UNAVAILABLE", "candidate evidence schema is unavailable", false);
    }
  }
}
