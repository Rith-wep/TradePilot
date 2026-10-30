export type ArtifactVerificationFailureKind =
  | "INVALID_REQUEST"
  | "CONTRACT_FAILURE"
  | "TIMEOUT"
  | "CAPACITY"
  | "SUBPROCESS_FAILURE"
  | "PROTOCOL_FAILURE";

export class ArtifactVerificationError extends Error {
  public constructor(
    public readonly kind: ArtifactVerificationFailureKind,
    public readonly code: string,
    message: string,
    public readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ArtifactVerificationError";
  }
}
