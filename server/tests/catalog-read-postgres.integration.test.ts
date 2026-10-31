import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import test, { after, before } from "node:test";
import { Pool } from "pg";
import request from "supertest";
import { createApp } from "../src/app.js";
import type { AppConfig } from "../src/config/env.js";
import { CatalogRepository } from "../src/database/catalog-repository.js";
import { PostgresCatalogReader } from "../src/database/catalog-read-repository.js";
import { migrate } from "../src/database/migrator.js";
import { silentLogger } from "../src/logging/logger.js";

const databaseUrl = process.env["TEST_DATABASE_URL"];
const schema = `catalog_read_${randomUUID().replaceAll("-", "")}`;
const admin = databaseUrl === undefined ? undefined : new Pool({ connectionString: databaseUrl });
const pool = databaseUrl === undefined ? undefined : new Pool({
  connectionString: databaseUrl,
  options: `-c search_path=${schema}`,
});

const config: AppConfig = {
  nodeEnv: "test",
  host: "127.0.0.1",
  port: 3000,
  logLevel: "error",
  databaseUrl: databaseUrl ?? "postgresql://unused",
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

before(async () => {
  if (admin !== undefined && pool !== undefined) {
    await admin.query(`CREATE SCHEMA ${schema}`);
    await migrate(pool, resolve(process.cwd(), "migrations"), "up");
  }
});

after(async () => {
  if (pool !== undefined) await pool.end();
  if (admin !== undefined) {
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
    await admin.end();
  }
});

test("PostgreSQL catalog endpoints return only ordered verified public metadata", {
  skip: databaseUrl === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const catalog = new PostgresCatalogReader(pool);
  const app = createApp({
    config,
    logger: silentLogger,
    database: { async check() { return true; } },
    catalog,
  });
  const empty = await request(app).get("/api/v1/datasets").expect(200);
  assert.deepEqual(empty.body.data.items, []);

  const repository = new CatalogRepository(pool);
  await repository.insertInstrument({
    symbol: "EURUSD", baseCurrency: "EUR", quoteCurrency: "USD",
    pipSize: "0.0001", pricePrecision: 5,
  });
  const verifiedAt = new Date("2026-01-03T00:00:00.000Z");
  const datasetIds = ["1".repeat(64), "2".repeat(64)];
  for (const [index, datasetId] of datasetIds.entries()) {
    await repository.insertVerifiedDataset({
      datasetId,
      canonicalChecksum: `${index + 4}`.repeat(64),
      instrumentSymbol: "EURUSD",
      provider: "verified-fixture",
      timeframe: "H1",
      firstCandleOpen: new Date("2025-01-01T00:00:00.000Z"),
      lastCandleOpen: new Date("2025-01-02T00:00:00.000Z"),
      rowCount: "25",
      schemaVersion: "tradepilot-candles-v1",
      artifactKey: `private/datasets/${datasetId}`,
      isSynthetic: index === 0,
      integrityVerifiedAt: verifiedAt,
    });
    await repository.insertVerifiedCandidateReport({
      reportId: `${index + 7}`.repeat(64),
      datasetId,
      strategyName: "Price Range Breakout",
      strategyVersion: "v1",
      configurationFingerprint: "a".repeat(64),
      schemaVersion: "tradepilot-candidate-report-v1",
      signalCount: index,
      artifactKey: `private/reports/${index}`,
      integrityVerifiedAt: verifiedAt,
    });
  }

  const first = await request(app).get("/api/v1/datasets?limit=1").expect(200);
  assert.equal(first.body.data.items[0].datasetId, datasetIds[0]);
  assert.equal(first.body.data.items[0].rowCount, "25");
  assert.equal(first.body.data.items[0].verifiedAt, verifiedAt.toISOString());
  assert.equal(first.body.data.items[0].sourceClassification, "SYNTHETIC");
  assert.equal(first.text.includes("artifact_key"), false);
  assert.equal(first.text.includes("private/"), false);

  const second = await request(app)
    .get(`/api/v1/datasets?limit=1&cursor=${encodeURIComponent(first.body.data.nextCursor)}`)
    .expect(200);
  assert.equal(second.body.data.items[0].datasetId, datasetIds[1]);
  assert.equal(second.body.data.nextCursor, null);

  const instruments = await request(app).get("/api/v1/instruments/").expect(200);
  assert.equal(instruments.body.data.items[0].pipSize, "0.0001");
  assert.equal(instruments.body.data.items[0].verifiedAt, verifiedAt.toISOString());

  const reports = await request(app).get("/api/v1/candidate-reports/").expect(200);
  assert.equal(reports.body.data.items.length, 2);
  assert.equal(reports.body.data.items[0].liveSignal, false);
  assert.equal(reports.body.data.items[0].schemaVersion, "tradepilot-candidate-report-v1");
});
