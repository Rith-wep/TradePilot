import type { CatalogRegistrationResult, CandidateReportRegistrationRequest } from "../catalog/registration-service.js";
import { CatalogRegistrationError } from "../catalog/errors.js";
import type { ClaimedResearchJob } from "./models.js";
import type { ResearchJobProcessor, ResearchJobProcessResult } from "./worker-service.js";
import { PythonResearchExecutionService, ResearchExecutionError } from "./execution-service.js";

export class TrustedResearchJobProcessor implements ResearchJobProcessor {
  public constructor(
    private readonly execution: PythonResearchExecutionService,
    private readonly catalog: CandidateReportRegistrar,
  ) {}

  public async process(job: ClaimedResearchJob): Promise<ResearchJobProcessResult> {
    try {
      const executed = await this.execution.execute(job);
      const registered = await this.catalog.registerCandidateReport({
        kind: "candidate_report", artifact_id: executed.reportId,
      });
      if (registered.artifactId !== executed.reportId) throw new ResearchExecutionError("CATALOG_ID_MISMATCH", false);
      return { reportId: executed.reportId };
    } catch (error) {
      if (error instanceof ResearchExecutionError) throw error;
      if (error instanceof CatalogRegistrationError) {
        throw new ResearchExecutionError(error.code, error.retryable);
      }
      throw new ResearchExecutionError("RESEARCH_PROCESSOR_FAILURE", true);
    }
  }
}

export interface CandidateReportRegistrar {
  registerCandidateReport(request: CandidateReportRegistrationRequest): Promise<CatalogRegistrationResult>;
}

