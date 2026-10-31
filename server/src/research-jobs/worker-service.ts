import type { Logger } from "../logging/logger.js";
import type { ClaimedResearchJob } from "./models.js";
import type { ResearchJobRepository } from "./repository.js";
import { ResearchJobError } from "./errors.js";

export interface ResearchJobProcessor {
  process(job: ClaimedResearchJob): Promise<ResearchJobProcessResult>;
}
export interface ResearchJobProcessResult { readonly reportId: string; }
interface ClassifiedFailure extends Error { readonly code: string; readonly retryable: boolean; }
function classified(error: unknown): error is ClassifiedFailure {
  return error instanceof Error && "code" in error && "retryable" in error
    && typeof (error as ClassifiedFailure).code === "string"
    && typeof (error as ClassifiedFailure).retryable === "boolean";
}

export class ResearchJobWorker {
  private stopped = false;
  public constructor(
    private readonly repository: ResearchJobRepository,
    private readonly processor: ResearchJobProcessor,
    private readonly logger: Logger,
    private readonly pollMs: number,
    private readonly heartbeatMs: number = Math.max(25, Math.floor(pollMs / 2)),
  ) {}

  public stop(): void { this.stopped = true; }

  public async run(): Promise<void> {
    while (!this.stopped) {
      if (!await this.runOnce()) {
        await new Promise<void>((resolve) => setTimeout(resolve, this.pollMs));
      }
    }
  }

  public async runOnce(): Promise<boolean> {
      const claimed = await this.repository.claim();
      if (claimed === undefined) return false;
      let leaseLost = false;
      let heartbeatRunning = false;
      const heartbeat = setInterval(() => {
        if (heartbeatRunning || leaseLost) return;
        heartbeatRunning = true;
        void this.repository.renew(claimed.jobId, claimed.leaseToken)
          .catch(() => { leaseLost = true; })
          .finally(() => { heartbeatRunning = false; });
      }, this.heartbeatMs);
      try {
        const result = await this.processor.process(claimed);
        if (leaseLost) throw Object.assign(new Error("lease lost"), { code: "LEASE_LOST", retryable: true });
        await this.repository.succeed(claimed.jobId, claimed.leaseToken, result.reportId);
      } catch (error) {
        if (!leaseLost) {
          const code = classified(error) && /^[A-Z][A-Z0-9_]{1,99}$/u.test(error.code)
            ? error.code : "RESEARCH_PROCESSOR_FAILURE";
          const retryable = classified(error) ? error.retryable : true;
          try {
            await this.repository.fail(claimed.jobId, claimed.leaseToken, code, retryable);
          } catch (failure) {
            if (!(failure instanceof ResearchJobError)
              || !["LEASE_LOST", "INVALID_JOB_TRANSITION"].includes(failure.code)) throw failure;
            leaseLost = true;
          }
        }
        this.logger.log("error", "research_job_processor_failed", {
          jobId: claimed.jobId, code: classified(error) ? error.code : "RESEARCH_PROCESSOR_FAILURE",
        });
      } finally {
        clearInterval(heartbeat);
      }
      return true;
  }
}

