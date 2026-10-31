import assert from "node:assert/strict";
import { resolve } from "node:path";
import test from "node:test";
import { ConfigurationError, loadConfig } from "../src/config/env.js";

const DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot";

test("configuration applies explicit defaults", () => {
  const researchRoot = resolve(process.cwd(), "..", "research");
  assert.deepEqual(loadConfig({ DATABASE_URL }), {
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
  });
});

test("configuration validates environment, log level, and port", () => {
  assert.throws(() => loadConfig({ DATABASE_URL, NODE_ENV: "staging" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, LOG_LEVEL: "verbose" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "0" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "12.5" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "65536" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, HOST: "0.0.0.0" }), ConfigurationError);
  assert.throws(() => loadConfig({}), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL: "https://example.com" }), ConfigurationError);
  assert.throws(
    () => loadConfig({ DATABASE_URL, DATABASE_READY_TIMEOUT_MS: "0" }),
    ConfigurationError,
  );
  assert.throws(
    () => loadConfig({ DATABASE_URL, TRADEPILOT_VERIFIER_MAX_CONCURRENCY: "0" }),
    ConfigurationError,
  );
  assert.throws(
    () => loadConfig({ DATABASE_URL, TRADEPILOT_VERIFIER_MAX_PENDING_REQUESTS: "0" }),
    ConfigurationError,
  );
});
