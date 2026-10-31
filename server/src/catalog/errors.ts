export type CatalogRegistrationFailureKind =
  | "VERIFICATION_FAILED"
  | "INVALID_VERIFIED_METADATA"
  | "MISSING_DATASET"
  | "PROVENANCE_MISMATCH"
  | "METADATA_CONFLICT"
  | "DATABASE_FAILURE";

export class CatalogRegistrationError extends Error {
  public constructor(
    public readonly kind: CatalogRegistrationFailureKind,
    public readonly code: string,
    message: string,
    public readonly retryable: boolean,
  ) {
    super(message);
    this.name = "CatalogRegistrationError";
  }
}
