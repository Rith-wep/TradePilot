import assert from "node:assert/strict";
import test from "node:test";
import { ConfigurationError, loadConfig } from "../src/config/env.js";

const DATABASE_URL = "postgresql://tradepilot:tradepilot@localhost:54329/tradepilot";

test("configuration applies explicit defaults", () => {
  assert.deepEqual(loadConfig({ DATABASE_URL }), {
    nodeEnv: "development",
    port: 3000,
    logLevel: "info",
    databaseUrl: DATABASE_URL,
    databaseConnectTimeoutMs: 3000,
    databaseReadyTimeoutMs: 1000,
  });
});

test("configuration validates environment, log level, and port", () => {
  assert.throws(() => loadConfig({ DATABASE_URL, NODE_ENV: "staging" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, LOG_LEVEL: "verbose" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "0" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "12.5" }), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL, PORT: "65536" }), ConfigurationError);
  assert.throws(() => loadConfig({}), ConfigurationError);
  assert.throws(() => loadConfig({ DATABASE_URL: "https://example.com" }), ConfigurationError);
  assert.throws(
    () => loadConfig({ DATABASE_URL, DATABASE_READY_TIMEOUT_MS: "0" }),
    ConfigurationError,
  );
});
