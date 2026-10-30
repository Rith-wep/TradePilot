export const ARTIFACT_CONTRACT_VERSION = "tradepilot-artifact-verification/v1" as const;

export interface DatasetArtifactReference {
  readonly kind: "dataset";
  readonly artifact_id: string;
  readonly provider: string;
  readonly instrument: string;
  readonly timeframe: string;
}

export interface CandidateReportArtifactReference {
  readonly kind: "candidate_report";
  readonly artifact_id: string;
}

export interface ArtifactVerificationRequest {
  readonly contract_version: typeof ARTIFACT_CONTRACT_VERSION;
  readonly request_id: string;
  readonly operation: "verify_artifact";
  readonly artifact: DatasetArtifactReference | CandidateReportArtifactReference;
}

export interface VerifiedArtifactResponse {
  readonly contract_version: typeof ARTIFACT_CONTRACT_VERSION;
  readonly request_id: string;
  readonly status: "VERIFIED";
  readonly artifact: {
    readonly kind: "dataset" | "candidate_report";
    readonly artifact_id: string;
  };
  readonly verification: Readonly<Record<string, unknown>>;
}

export interface ArtifactContractErrorResponse {
  readonly contract_version: typeof ARTIFACT_CONTRACT_VERSION;
  readonly request_id: string;
  readonly status: "ERROR";
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly retryable: boolean;
    readonly details?: unknown;
  };
}

export type ArtifactVerificationResponse =
  | VerifiedArtifactResponse
  | ArtifactContractErrorResponse;
