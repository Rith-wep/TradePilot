export class ResearchJobError extends Error {
  public constructor(public readonly code: string, message: string, public readonly retryable = false) {
    super(message);
    this.name = "ResearchJobError";
  }
}

