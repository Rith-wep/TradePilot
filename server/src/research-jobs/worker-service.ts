import type { Logger } from "../logging/logger.js";
import type { ClaimedResearchJob } from "./models.js";
import type { ResearchJobRepository } from "./repository.js";

export interface ResearchJobProcessor {
  process(job: ClaimedResearchJob): Promise<void>;
}

export class ResearchJobWorker {
  private stopped = false;
  public constructor(
    private readonly repository: ResearchJobRepository,
    private readonly processor: ResearchJobProcessor,
    private readonly logger: Logger,
    private readonly pollMs: number,
  ) {}

  public stop(): void { this.stopped = true; }

  public async run(): Promise<void> {
    while (!this.stopped) {
      const claimed = await this.repository.claim();
      if (claimed === undefined) {
        await new Promise<void>((resolve) => setTimeout(resolve, this.pollMs));
        continue;
      }
      try {
        await this.processor.process(claimed);
        await this.repository.succeed(claimed.jobId, claimed.leaseToken);
      } catch {
        await this.repository.fail(claimed.jobId, claimed.leaseToken, "PROCESSOR_FAILURE", true);
        this.logger.log("error", "research_job_processor_failed", { jobId: claimed.jobId });
      }
    }
  }
}

