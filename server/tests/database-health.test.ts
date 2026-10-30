import assert from "node:assert/strict";
import test from "node:test";
import { PostgresDatabase } from "../src/database/database.js";

test("database connectivity failure returns false within the configured bound", async () => {
  const database = new PostgresDatabase({
    connectionString: "postgresql://invalid:invalid@127.0.0.1:1/invalid",
    connectionTimeoutMillis: 100,
    max: 1,
  }, 100);
  const started = Date.now();
  try {
    assert.equal(await database.check(), false);
    assert.ok(Date.now() - started < 2_000);
  } finally {
    await database.close();
  }
});
