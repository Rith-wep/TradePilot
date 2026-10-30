import assert from "node:assert/strict";
import test from "node:test";
import request from "supertest";
import { createApp } from "../src/app.js";
import { API_VERSION } from "../src/http/contracts/envelope.js";
import { silentLogger } from "../src/logging/logger.js";

const app = createApp({
  config: { nodeEnv: "test", port: 3000, logLevel: "error" },
  logger: silentLogger,
});

test("liveness returns the versioned success envelope", async () => {
  const response = await request(app).get("/health/live").expect(200);
  assert.equal(response.body.apiVersion, API_VERSION);
  assert.equal(response.body.requestId, response.headers["x-request-id"]);
  assert.deepEqual(response.body.data, { status: "UP", service: "tradepilot-server" });
  assert.match(response.body.meta.generatedAt, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(response.headers["x-powered-by"], undefined);
});

test("readiness reports only implemented configuration readiness", async () => {
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
    checks: [{ name: "configuration", status: "UP" }],
  });
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
