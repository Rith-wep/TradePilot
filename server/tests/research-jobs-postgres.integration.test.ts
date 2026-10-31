import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import test, { after, before, beforeEach } from "node:test";
import { Pool } from "pg";
import { CatalogRepository } from "../src/database/catalog-repository.js";
import { migrate } from "../src/database/migrator.js";
import { RESEARCH_JOB_REQUEST_VERSION, type ResearchJobRequest } from "../src/research-jobs/contracts.js";
import { ResearchJobError } from "../src/research-jobs/errors.js";
import { ResearchJobRepository } from "../src/research-jobs/repository.js";

const databaseUrl = process.env["TEST_DATABASE_URL"];
const schema = `jobs_${randomUUID().replaceAll("-", "")}`;
const admin = databaseUrl === undefined ? undefined : new Pool({ connectionString: databaseUrl });
const pool = databaseUrl === undefined ? undefined : new Pool({
  connectionString: databaseUrl, options: `-c search_path=${schema}`,
});
const datasetId = "a".repeat(64);
const limits = { leaseMs: 100, maxActivePerOwner: 3, maxQueueDepth: 100, maxAttempts: 3, pollMs: 1 };

before(async () => {
  if (admin !== undefined && pool !== undefined) {
    await admin.query(`CREATE SCHEMA ${schema}`);
    await migrate(pool, resolve(process.cwd(), "migrations"), "up");
    const catalog = new CatalogRepository(pool);
    await catalog.insertInstrument({
      symbol: "EURUSD", baseCurrency: "EUR", quoteCurrency: "USD",
      pipSize: "0.0001", pricePrecision: 5,
    });
    await catalog.insertVerifiedDataset({
      datasetId, canonicalChecksum: "b".repeat(64), instrumentSymbol: "EURUSD",
      provider: "fixture", timeframe: "H1", firstCandleOpen: new Date("2025-01-01T00:00:00Z"),
      lastCandleOpen: new Date("2025-01-02T00:00:00Z"), rowCount: "25",
      schemaVersion: "v1", artifactKey: `data/${datasetId}`, isSynthetic: true,
      integrityVerifiedAt: new Date("2025-01-03T00:00:00Z"),
    });
  }
});
after(async () => {
  if (pool !== undefined) await pool.end();
  if (admin !== undefined) {
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
    await admin.end();
  }
});
beforeEach(async () => {
  if (pool !== undefined) await pool.query("TRUNCATE research_job_events, research_jobs RESTART IDENTITY");
});

function request(key = "request_key_001"): ResearchJobRequest {
  return {
    contractVersion: RESEARCH_JOB_REQUEST_VERSION, idempotencyKey: key, datasetId,
    instrument: "EURUSD", timeframe: "H1",
    strategy: { name: "price_range_breakout", version: "v1" },
  };
}

test("submission is idempotent and validates dataset provenance and queue limits", {
  skip: pool === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, { ...limits, maxActivePerOwner: 1 });
  const first = await repository.submit("owner-a", request());
  const duplicate = await repository.submit("owner-a", request());
  assert.equal(first.created, true);
  assert.equal(duplicate.created, false);
  assert.equal(first.job.jobId, duplicate.job.jobId);
  await assert.rejects(
    repository.submit("owner-a", request("request_key_002")),
    (error) => error instanceof ResearchJobError && error.code === "ACTIVE_JOB_LIMIT",
  );
  await assert.rejects(
    repository.submit("owner-a", {
      ...request(), strategy: { name: "ema_rsi_trend_pullback", version: "v1" },
    }),
    (error) => error instanceof ResearchJobError && error.code === "IDEMPOTENCY_CONFLICT",
  );
  await assert.rejects(
    repository.submit("owner-b", { ...request("missing_dataset"), datasetId: "f".repeat(64) }),
    (error) => error instanceof ResearchJobError && error.code === "DATASET_NOT_VERIFIED",
  );
});

test("SKIP LOCKED claim, lease recovery, bounded retry, and transitions are durable", {
  skip: pool === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, limits);
  await repository.submit("worker-owner", request("worker_job_001"));
  const [first, competing] = await Promise.all([repository.claim(), repository.claim()]);
  assert.ok(first !== undefined);
  assert.equal(competing, undefined);
  await pool.query(
    "UPDATE research_jobs SET lease_expires_at=now()-interval '1 second' WHERE job_id=$1",
    [first.jobId],
  );
  const recovered = await repository.claim();
  assert.ok(recovered !== undefined);
  assert.equal(recovered.jobId, first.jobId);
  assert.equal(recovered.attemptCount, 2);
  await assert.rejects(
    repository.succeed(first.jobId, first.leaseToken),
    (error) => error instanceof ResearchJobError && error.code === "INVALID_JOB_TRANSITION",
  );
  await repository.fail(recovered.jobId, recovered.leaseToken, "TRANSIENT_FAILURE", true);
  const retry = await repository.claim();
  assert.ok(retry !== undefined);
  await repository.succeed(retry.jobId, retry.leaseToken);
  assert.equal((await repository.get(retry.jobId, "worker-owner", false))?.state, "SUCCEEDED");
  assert.equal(await repository.get(retry.jobId, "different-owner", false), undefined);
  assert.equal((await repository.get(retry.jobId, "admin", true))?.jobId, retry.jobId);
  const events = await pool.query<{ event_type: string }>(
    "SELECT event_type FROM research_job_events WHERE job_id=$1 ORDER BY event_id", [retry.jobId],
  );
  assert.deepEqual(events.rows.map((row) => row.event_type), [
    "SUBMITTED", "CLAIMED", "LEASE_RECOVERED", "CLAIMED", "REQUEUED", "CLAIMED", "SUCCEEDED",
  ]);
});

test("concurrent duplicate submissions publish one job", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, limits);
  const results = await Promise.all([
    repository.submit("concurrent-owner", request("concurrent_001")),
    repository.submit("concurrent-owner", request("concurrent_001")),
  ]);
  assert.equal(new Set(results.map((result) => result.job.jobId)).size, 1);
});
