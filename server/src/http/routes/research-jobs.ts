import { Router } from "express";
import { authorize } from "../../auth/middleware.js";
import type { ResearchJob } from "../../research-jobs/models.js";
import { JobRequestValidationError, parseResearchJobRequest } from "../../research-jobs/contracts.js";
import { ResearchJobError } from "../../research-jobs/errors.js";
import type { ResearchJobStore } from "../../research-jobs/repository.js";
import { successEnvelope } from "../contracts/envelope.js";
import { ApiError } from "../errors/api-error.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;

function item(job: ResearchJob) {
  return {
    jobId: job.jobId, datasetId: job.datasetId, instrument: job.instrument,
    timeframe: job.timeframe, strategy: { name: job.strategyName, version: job.strategyVersion },
    state: job.state, attemptCount: job.attemptCount, maxAttempts: job.maxAttempts,
    errorCode: job.errorCode, createdAt: job.createdAt.toISOString(),
    updatedAt: job.updatedAt.toISOString(), startedAt: job.startedAt?.toISOString() ?? null,
    completedAt: job.completedAt?.toISOString() ?? null,
  };
}

function mapError(error: unknown): never {
  if (error instanceof JobRequestValidationError) throw new ApiError(400, "VALIDATION_ERROR", error.message);
  if (error instanceof ResearchJobError) {
    if (error.code === "DATASET_NOT_VERIFIED") throw new ApiError(409, error.code, error.message);
    if (error.code === "DATASET_PROVENANCE_MISMATCH" || error.code === "IDEMPOTENCY_CONFLICT") {
      throw new ApiError(409, error.code, error.message);
    }
    if (error.code === "ACTIVE_JOB_LIMIT" || error.code === "QUEUE_FULL") {
      throw new ApiError(429, error.code, error.message, true);
    }
  }
  throw new ApiError(503, "RESEARCH_QUEUE_UNAVAILABLE", "The research-job queue is unavailable.", true);
}

export function researchJobsRouter(repository: ResearchJobStore): Router {
  const router = Router();
  router.post("/research-jobs", authorize("researcher"), async (req, res) => {
    try {
      const request = parseResearchJobRequest(req.body);
      const result = await repository.submit(req.principal!.subject, request);
      res.status(202).json(successEnvelope(req.requestId, {
        ...item(result.job), submission: result.created ? "CREATED" : "EXISTING",
      }));
    } catch (error) { mapError(error); }
  });
  router.get("/research-jobs", async (req, res) => {
    if (Object.keys(req.query).length !== 0) throw new ApiError(400, "VALIDATION_ERROR", "Query parameters are not supported.");
    try {
      const admin = req.principal!.roles.includes("admin");
      const jobs = await repository.list(req.principal!.subject, admin);
      res.json(successEnvelope(req.requestId, { items: jobs.map(item) }));
    } catch (error) { mapError(error); }
  });
  router.get("/research-jobs/:jobId", async (req, res) => {
    const jobId = req.params["jobId"];
    if (jobId === undefined || !UUID.test(jobId)) throw new ApiError(400, "VALIDATION_ERROR", "jobId is invalid.");
    try {
      const found = await repository.get(jobId, req.principal!.subject, req.principal!.roles.includes("admin"));
      if (found === undefined) throw new ApiError(404, "RESOURCE_NOT_FOUND", "Research job was not found.");
      res.json(successEnvelope(req.requestId, item(found)));
    } catch (error) {
      if (error instanceof ApiError) throw error;
      mapError(error);
    }
  });
  return router;
}

