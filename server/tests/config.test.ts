import assert from "node:assert/strict";
import { resolve } from "node:path";
import test from "node:test";
import { ConfigurationError, loadConfig } from "../src/config/env.js";

const DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot";
const REQUIRED = {
  DATABASE_URL,
  OIDC_ISSUER: "https://identity.example.test",
  OIDC_AUDIENCE: "tradepilot-api",
  OIDC_JWKS_URL: "https://identity.example.test/.well-known/jwks.json",
  TRADEPILOT_IMPLEMENTATION_REVISION: "unknown",
};

test("configuration applies explicit defaults", () => {
  const researchRoot = resolve(process.cwd(), "..", "research");
  assert.deepEqual(loadConfig(REQUIRED), {
    nodeEnv: "development",
    host: "127.0.0.1",
    port: 3000,
    logLevel: "info",
    databaseUrl: DATABASE_URL,
    databaseConnectTimeoutMs: 3000,
    databaseReadyTimeoutMs: 1000,
    artifactVerifier: {
      pythonExecutable: "python",
      pythonWorkingDirectory: researchRoot,
      schemaDirectory: resolve(researchRoot, "contracts"),
      datasetRoot: resolve(researchRoot, "data"),
      reportRoot: resolve(researchRoot, "reports"),
      timeoutMs: 10_000,
      maxInputBytes: 65_536,
      maxOutputBytes: 1_048_576,
      maxErrorBytes: 16_384,
      maxConcurrency: 2,
      maxPendingRequests: 16,
    },
    auth: {
      issuer: "https://identity.example.test",
      audience: "tradepilot-api",
      jwksUrl: "https://identity.example.test/.well-known/jwks.json",
      algorithms: ["RS256"],
      rolesClaim: "roles",
      jwksTimeoutMs: 3000,
    },
    security: {
      corsAllowedOrigins: [], rateLimitWindowMs: 60_000,
      rateLimitMax: 120, requestBodyMaxBytes: 32_768,
    },
    researchJobs: {
      maxActivePerOwner: 3, maxQueueDepth: 100, maxAttempts: 3,
      leaseMs: 60_000, pollMs: 1_000, implementationRevision: "unknown",
    },
  });
});

test("configuration validates environment, log level, and port", () => {
  assert.throws(() => loadConfig({ ...REQUIRED, NODE_ENV: "staging" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, LOG_LEVEL: "verbose" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, PORT: "0" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, PORT: "12.5" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, PORT: "65536" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, HOST: "0.0.0.0" }), ConfigurationError);
  assert.throws(() => loadConfig({}), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL: "https://example.com" }), ConfigurationError);
  assert.throws(
    () => loadConfig({ ...REQUIRED, DATABASE_READY_TIMEOUT_MS: "0" }),
    ConfigurationError,
  );
  assert.throws(
    () => loadConfig({ ...REQUIRED, TRADEPILOT_VERIFIER_MAX_CONCURRENCY: "0" }),
    ConfigurationError,
  );
  assert.throws(
    () => loadConfig({ ...REQUIRED, TRADEPILOT_VERIFIER_MAX_PENDING_REQUESTS: "0" }),
    ConfigurationError,
  );
  assert.throws(() => loadConfig({ ...REQUIRED, OIDC_ISSUER: "http://issuer.test" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, OIDC_ALLOWED_ALGORITHMS: "HS256" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, CORS_ALLOWED_ORIGINS: "*" }), ConfigurationError);
  assert.throws(() => loadConfig({ ...REQUIRED, RESEARCH_JOB_MAX_ATTEMPTS: "11" }), ConfigurationError);
});
