import assert from "node:assert/strict";
import test from "node:test";
import request from "supertest";
import { createApp } from "../src/app.js";
import type { AuthRole } from "../src/config/env.js";
import type { ResearchJob } from "../src/research-jobs/models.js";
import type { ResearchJobStore } from "../src/research-jobs/repository.js";
import { silentLogger } from "../src/logging/logger.js";
import { TEST_AUTH_CONFIG, TEST_RESEARCH_JOBS_CONFIG, TEST_SECURITY_CONFIG } from "./security-fixtures.js";

const now = new Date("2026-01-01T00:00:00Z");
const stored: ResearchJob = {
  jobId: "123e4567-e89b-42d3-a456-426614174000", ownerSubject: "alice",
  datasetId: "a".repeat(64), instrument: "EURUSD", timeframe: "H1",
  strategyName: "price_range_breakout", strategyVersion: "v1", state: "QUEUED",
  attemptCount: 0, maxAttempts: 3, leaseExpiresAt: null, errorCode: null,
  createdAt: now, updatedAt: now, startedAt: null, completedAt: null,
  resultReportId: null,
  implementationRevision: "unknown",
};
const store: ResearchJobStore = {
  async submit(owner) { return { job: { ...stored, ownerSubject: owner }, created: true }; },
  async list(owner, admin) { return admin || owner === stored.ownerSubject ? [stored] : []; },
  async get(jobId, owner, admin) {
    return jobId === stored.jobId && (admin || owner === stored.ownerSubject) ? stored : undefined;
  },
};

function app(role: AuthRole, subject = "alice") {
  return createApp({
    config: {
      nodeEnv: "test", host: "127.0.0.1", port: 3000, logLevel: "error",
      databaseUrl: "postgresql://unused", databaseConnectTimeoutMs: 100, databaseReadyTimeoutMs: 100,
      artifactVerifier: { pythonExecutable: "python", pythonWorkingDirectory: "C:\\trusted",
        schemaDirectory: "C:\\trusted", datasetRoot: "C:\\trusted", reportRoot: "C:\\trusted",
        timeoutMs: 100, maxInputBytes: 1000, maxOutputBytes: 1000, maxErrorBytes: 1000,
        maxConcurrency: 1, maxPendingRequests: 1 },
      auth: TEST_AUTH_CONFIG, security: TEST_SECURITY_CONFIG, researchJobs: TEST_RESEARCH_JOBS_CONFIG,
    },
    logger: silentLogger, database: { async check() { return true; } },
    catalog: { async listInstruments() { return []; }, async listDatasets() { return []; },
      async listCandidateReports() { return []; }, async getInstrument() { return undefined; },
      async getDataset() { return undefined; }, async getCandidateReport() { return undefined; } },
    evidence: { async list() { throw new Error(); }, async get() { throw new Error(); } },
    tokenVerifier: { async verify() {
      return { subject, issuer: TEST_AUTH_CONFIG.issuer, audience: [TEST_AUTH_CONFIG.audience],
        roles: [role], tokenId: "job-test" };
    } },
    researchJobs: store,
  });
}
const auth = "Bearer test.test.test";
const body = {
  contractVersion: "tradepilot-research-job-request/v1", idempotencyKey: "request_001",
  datasetId: "a".repeat(64), instrument: "EURUSD", timeframe: "H1",
  strategy: { name: "price_range_breakout", version: "v1" },
};

test("job submission requires researcher and returns 202", async () => {
  await request(app("viewer")).post("/api/v1/research-jobs").set("authorization", auth).send(body).expect(403);
  const accepted = await request(app("researcher")).post("/api/v1/research-jobs")
    .set("authorization", auth).send(body).expect(202);
  assert.equal(accepted.body.data.state, "QUEUED");
  assert.equal(accepted.body.data.submission, "CREATED");
  await request(app("admin")).post("/api/v1/research-jobs").set("authorization", auth)
    .send({ ...body, command: "arbitrary" }).expect(400);
});

test("job reads enforce owner-or-admin access", async () => {
  await request(app("viewer", "bob")).get(`/api/v1/research-jobs/${stored.jobId}`)
    .set("authorization", auth).expect(404);
  await request(app("viewer", "alice")).get("/api/v1/research-jobs/")
    .set("authorization", auth).expect(200);
  const admin = await request(app("admin", "root")).get(`/api/v1/research-jobs/${stored.jobId}`)
    .set("authorization", auth).expect(200);
  assert.equal(admin.body.data.jobId, stored.jobId);
});
