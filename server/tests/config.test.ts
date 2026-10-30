import assert from "node:assert/strict";
import test from "node:test";
import { ConfigurationError, loadConfig } from "../src/config/env.js";

test("configuration applies explicit defaults", () => {
  assert.deepEqual(loadConfig({}), {
    nodeEnv: "development",
    port: 3000,
    logLevel: "info",
  });
});

test("configuration validates environment, log level, and port", () => {
  assert.throws(() => loadConfig({ NODE_ENV: "staging" }), ConfigurationError);
  assert.throws(() => loadConfig({ LOG_LEVEL: "verbose" }), ConfigurationError);
  assert.throws(() => loadConfig({ PORT: "0" }), ConfigurationError);
  assert.throws(() => loadConfig({ PORT: "12.5" }), ConfigurationError);
  assert.throws(() => loadConfig({ PORT: "65536" }), ConfigurationError);
});
