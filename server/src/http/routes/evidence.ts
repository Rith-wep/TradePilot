import { Router } from "express";
import type { CatalogReadStore } from "../../database/catalog-read-repository.js";
import type { CandidateEvidenceService } from "../../evidence/evidence-service.js";
import { ArtifactVerificationError } from "../../verification/errors.js";
import { successEnvelope } from "../contracts/envelope.js";
import { ApiError } from "../errors/api-error.js";
import { encodeCursor, parsePageQuery } from "../pagination/cursor.js";

const SHA256 = /^[0-9a-f]{64}$/u;
const EVIDENCE_ID = /^([0-9a-f]{64})\.[0-9]{8}\.[0-9a-f]{64}$/u;

function unavailable(error: unknown): never {
  if (error instanceof ArtifactVerificationError) {
    if (error.code === "EVIDENCE_NOT_FOUND" || error.code === "EVIDENCE_ID_MISMATCH") {
      throw new ApiError(404, "EVIDENCE_NOT_FOUND", "Candidate evidence was not found.");
    }
    throw new ApiError(409, "EVIDENCE_UNAVAILABLE", "Candidate evidence failed integrity verification.", error.retryable);
  }
  throw new ApiError(503, "CATALOG_UNAVAILABLE", "The research catalog is unavailable.", true);
}

export function evidenceRouter(
  catalog: CatalogReadStore,
  evidence: Pick<CandidateEvidenceService, "list" | "get">,
): Router {
  const router = Router();

  router.get("/candidate-reports/:reportId/candidates", async (req, res) => {
    const reportId = req.params["reportId"];
    if (reportId === undefined || !SHA256.test(reportId)) {
      throw new ApiError(400, "VALIDATION_ERROR", "reportId must be a lowercase SHA-256 identifier.");
    }
    const query = parsePageQuery(req.query, "report-candidates");
    let offset = 0;
    if (query.after !== undefined) {
      const [cursorReport, cursorOffset] = query.after.split(":");
      if (cursorReport !== reportId || cursorOffset === undefined) {
        throw new ApiError(400, "VALIDATION_ERROR", "cursor is invalid for this candidate report.");
      }
      offset = Number(cursorOffset);
    }
    try {
      const catalogReport = await catalog.getCandidateReport(reportId);
      if (catalogReport === undefined) {
        throw new ApiError(404, "RESOURCE_NOT_FOUND", "Candidate report was not found.");
      }
      const result = await evidence.list(reportId, offset, query.limit, req.requestId);
      res.json(successEnvelope(req.requestId, {
        items: result.candidates,
        nextCursor: result.next_offset === null
          ? null : encodeCursor("report-candidates", `${reportId}:${result.next_offset}`),
        totalCount: result.total_count,
        classification: "HISTORICAL_RESEARCH" as const,
        liveSignal: false as const,
      }));
    } catch (error) {
      if (error instanceof ApiError) throw error;
      unavailable(error);
    }
  });

  router.get("/evidence/:evidenceId", async (req, res) => {
    const evidenceId = req.params["evidenceId"];
    const match = evidenceId === undefined ? null : EVIDENCE_ID.exec(evidenceId);
    if (match === null || match[1] === undefined) {
      throw new ApiError(400, "VALIDATION_ERROR", "evidenceId is invalid.");
    }
    try {
      const catalogReport = await catalog.getCandidateReport(match[1]);
      if (catalogReport === undefined) {
        throw new ApiError(404, "RESOURCE_NOT_FOUND", "Candidate report was not found.");
      }
      const item = await evidence.get(evidenceId, req.requestId);
      res.json(successEnvelope(req.requestId, item));
    } catch (error) {
      if (error instanceof ApiError) throw error;
      unavailable(error);
    }
  });
  return router;
}
