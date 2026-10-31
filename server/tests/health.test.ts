import assert from "node:assert/strict";
import test from "node:test";
import request from "supertest";
import { createApp } from "../src/app.js";
import { API_VERSION } from "../src/http/contracts/envelope.js";
import { silentLogger } from "../src/logging/logger.js";

const config = {
  nodeEnv: "test" as const,
  host: "127.0.0.1" as const,
  port: 3000,
  logLevel: "error" as const,
  databaseUrl: "postgresql://unused",
  databaseConnectTimeoutMs: 100,
  databaseReadyTimeoutMs: 100,
  artifactVerifier: {
    pythonExecutable: "python",
    pythonWorkingDirectory: "C:\\trusted\\research",
    schemaDirectory: "C:\\trusted\\research\\contracts",
    datasetRoot: "C:\\trusted\\research\\data",
    reportRoot: "C:\\trusted\\research\\reports",
    timeoutMs: 100,
    maxInputBytes: 65_536,
    maxOutputBytes: 1_048_576,
    maxErrorBytes: 16_384,
    maxConcurrency: 2,
    maxPendingRequests: 16,
  },
};

const emptyCatalog = {
  async listInstruments() { return []; },
  async listDatasets() { return []; },
  async listCandidateReports() { return []; },
  async getInstrument() { return undefined; },
  async getDataset() { return undefined; },
  async getCandidateReport() { return undefined; },
};
const emptyEvidence = {
  async list() { throw new Error("unused"); },
  async get() { throw new Error("unused"); },
};

function appWithDatabase(result: boolean) {
  return createApp({
    config, logger: silentLogger, database: { async check() { return result; } },
    catalog: emptyCatalog, evidence: emptyEvidence,
  });
}

const app = appWithDatabase(true);

test("liveness returns the versioned success envelope", async () => {
  const response = await request(app).get("/health/live").expect(200);
  assert.equal(response.body.apiVersion, API_VERSION);
  assert.equal(response.body.requestId, response.headers["x-request-id"]);
  assert.deepEqual(response.body.data, { status: "UP", service: "tradepilot-server" });
  assert.match(response.body.meta.generatedAt, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(response.headers["x-powered-by"], undefined);
});

test("readiness reports configuration and database readiness", async () => {
  const response = await request(app)
    .get("/health/ready")
    .set("x-request-id", "integration-test-1")
    .expect(200);
  assert.equal(response.body.requestId, "integration-test-1");
  assert.equal(response.headers["x-request-id"], "integration-test-1");
  assert.deepEqual(response.body.data, {
    status: "UP",
    service: "tradepilot-server",
    environment: "test",
    checks: [
      { name: "configuration", status: "UP" },
      { name: "database", status: "UP" },
    ],
  });
});

test("readiness fails closed when the database is unavailable", async () => {
  const response = await request(appWithDatabase(false)).get("/health/ready").expect(503);
  assert.equal(response.body.data.status, "DOWN");
  assert.deepEqual(response.body.data.checks, [
    { name: "configuration", status: "UP" },
    { name: "database", status: "DOWN" },
  ]);
});

test("liveness does not query the database", async () => {
  let checks = 0;
  const isolated = createApp({
    config,
    logger: silentLogger,
    database: { async check() { checks += 1; return false; } },
    catalog: emptyCatalog,
    evidence: emptyEvidence,
  });
  await request(isolated).get("/health/live").expect(200);
  assert.equal(checks, 0);
});

test("unsafe request IDs are replaced", async () => {
  const response = await request(app)
    .get("/health/live")
    .set("x-request-id", "unsafe request id")
    .expect(200);
  assert.notEqual(response.body.requestId, "unsafe request id");
  assert.match(response.body.requestId, /^[0-9a-f-]{36}$/);
});

test("unknown routes use the centralized versioned error envelope", async () => {
  const response = await request(app).get("/missing").expect(404);
  assert.equal(response.body.apiVersion, API_VERSION);
  assert.equal(response.body.requestId, response.headers["x-request-id"]);
  assert.deepEqual(response.body.error, {
    code: "RESOURCE_NOT_FOUND",
    message: "The requested resource was not found.",
    retryable: false,
  });
});

test("malformed JSON uses the centralized validation error envelope", async () => {
  const response = await request(app)
    .post("/health/live")
    .set("content-type", "application/json")
    .send('{"broken":')
    .expect(400);
  assert.equal(response.body.apiVersion, API_VERSION);
  assert.equal(response.body.requestId, response.headers["x-request-id"]);
  assert.deepEqual(response.body.error, {
    code: "VALIDATION_ERROR",
    message: "The request body must contain valid JSON.",
    retryable: false,
  });
});
