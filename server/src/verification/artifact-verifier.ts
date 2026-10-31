import type { ArtifactVerifierConfig } from "../config/env.js";
import type {
  ArtifactContractErrorResponse,
  ArtifactVerificationRequest,
  ArtifactVerificationResponse,
  VerifiedArtifactResponse,
} from "./contracts.js";
import { ControlledPythonRunner } from "./controlled-python.js";
import { ArtifactVerificationError } from "./errors.js";
import { ArtifactContractValidator } from "./schema-validator.js";

export class ArtifactVerifierService {
  private readonly validator: ArtifactContractValidator;
  private readonly runner: ControlledPythonRunner;

  public constructor(private readonly config: ArtifactVerifierConfig) {
    this.validator = new ArtifactContractValidator(config.schemaDirectory);
    this.runner = new ControlledPythonRunner(config, "tradepilot.contracts", [
      "--dataset-root", config.datasetRoot, "--report-root", config.reportRoot,
    ]);
  }

  public async verify(request: ArtifactVerificationRequest): Promise<VerifiedArtifactResponse> {
    this.validator.assertRequest(request);
    const input = Buffer.from(`${JSON.stringify(request)}\n`, "utf8");
    if (input.byteLength > this.config.maxInputBytes) {
      throw new ArtifactVerificationError("INVALID_REQUEST", "REQUEST_TOO_LARGE", "artifact verification request is too large", false);
    }
    const result = await this.runner.run(input);
    let response: ArtifactVerificationResponse;
    try {
      response = this.parseResponse(result.stdout);
    } catch (error) {
      if (result.exitCode !== 0) {
        throw new ArtifactVerificationError("SUBPROCESS_FAILURE", "VERIFIER_EXIT_FAILURE", "artifact verifier failed", true);
      }
      throw error;
    }
    if (response.request_id !== request.request_id) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "REQUEST_ID_MISMATCH", "artifact verifier response mismatch", false);
    }
    if (response.status === "ERROR") throw this.contractError(response);
    if (result.exitCode !== 0) {
      throw new ArtifactVerificationError("SUBPROCESS_FAILURE", "VERIFIER_EXIT_FAILURE", "artifact verifier failed", true);
    }
    return response;
  }

  private parseResponse(output: Buffer): ArtifactVerificationResponse {
    const lines = output.toString("utf8").split(/\r?\n/u).filter((line) => line.length > 0);
    if (lines.length !== 1 || lines[0] === undefined) {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_STDOUT", "artifact verifier returned invalid output", false);
    }
    let value: unknown;
    try { value = JSON.parse(lines[0]); } catch {
      throw new ArtifactVerificationError("PROTOCOL_FAILURE", "INVALID_JSON_RESPONSE", "artifact verifier returned invalid JSON", false);
    }
    this.validator.assertResponse(value);
    return value;
  }

  private contractError(response: ArtifactContractErrorResponse): ArtifactVerificationError {
    return new ArtifactVerificationError("CONTRACT_FAILURE", response.error.code, "artifact verification failed", response.error.retryable);
  }
}
