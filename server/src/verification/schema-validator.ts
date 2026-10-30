import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Ajv2020, type AnySchema, type ValidateFunction } from "ajv/dist/2020.js";
import type {
  ArtifactVerificationRequest,
  ArtifactVerificationResponse,
} from "./contracts.js";
import { ArtifactVerificationError } from "./errors.js";

function loadSchema(schemaDirectory: string, filename: string): AnySchema {
  try {
    return JSON.parse(readFileSync(join(schemaDirectory, filename), "utf8")) as AnySchema;
  } catch {
    throw new ArtifactVerificationError(
      "PROTOCOL_FAILURE",
      "SCHEMA_UNAVAILABLE",
      "artifact verification schema is unavailable",
      false,
    );
  }
}

export class ArtifactContractValidator {
  private readonly requestValidator: ValidateFunction;
  private readonly responseValidator: ValidateFunction;

  public constructor(schemaDirectory: string) {
    const ajv = new Ajv2020({ allErrors: true, strict: true });
    this.requestValidator = ajv.compile(loadSchema(
      schemaDirectory, "artifact-verification-v1.request.schema.json",
    ));
    this.responseValidator = ajv.compile(loadSchema(
      schemaDirectory, "artifact-verification-v1.response.schema.json",
    ));
  }

  public assertRequest(value: unknown): asserts value is ArtifactVerificationRequest {
    if (!this.requestValidator(value)) {
      throw new ArtifactVerificationError(
        "INVALID_REQUEST", "INVALID_REQUEST", "artifact verification request is invalid", false,
      );
    }
  }

  public assertResponse(value: unknown): asserts value is ArtifactVerificationResponse {
    if (!this.responseValidator(value)) {
      throw new ArtifactVerificationError(
        "PROTOCOL_FAILURE", "INVALID_RESPONSE", "artifact verifier returned an invalid response", false,
      );
    }
  }
}
