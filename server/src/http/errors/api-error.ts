export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly details: readonly unknown[] | undefined;

  public constructor(
    status: number,
    code: string,
    message: string,
    retryable = false,
    details?: readonly unknown[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }
}
