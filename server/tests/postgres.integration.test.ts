import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import test, { after, before } from "node:test";
import { Pool } from "pg";
import { CatalogRepository } from "../src/database/catalog-repository.js";
import { migrate } from "../src/database/migrator.js";

const databaseUrl = process.env["TEST_DATABASE_URL"];
const schema = `test_${randomUUID().replaceAll("-", "")}`;
const admin = databaseUrl === undefined ? undefined : new Pool({ connectionString: databaseUrl });
const pool = databaseUrl === undefined ? undefined : new Pool({
  connectionString: databaseUrl,
  options: `-c search_path=${schema}`,
});
const migrations = resolve(process.cwd(), "migrations");

before(async () => {
  if (admin !== undefined) {
    await admin.query(`CREATE SCHEMA ${schema}`);
  }
});

after(async () => {
  if (pool !== undefined) {
    await pool.end();
  }
  if (admin !== undefined) {
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
    await admin.end();
  }
});

test("migrations, constraints, and parameterized catalog access", { skip: databaseUrl === undefined }, async () => {
  assert.ok(pool !== undefined);
  assert.deepEqual(await migrate(pool, migrations, "up"), ["001", "002", "003", "004", "005"]);
  assert.deepEqual(await migrate(pool, migrations, "up"), []);

  const repository = new CatalogRepository(pool);
  await repository.insertInstrument({
    symbol: "EURUSD", baseCurrency: "EUR", quoteCurrency: "USD",
    pipSize: "0.0001", pricePrecision: 5,
  });
  const datasetId = "a".repeat(64);
  const checksum = "b".repeat(64);
  await repository.insertVerifiedDataset({
    datasetId,
    canonicalChecksum: checksum,
    instrumentSymbol: "EURUSD",
    provider: "verified-fixture",
    timeframe: "H1",
    firstCandleOpen: new Date("2025-01-01T00:00:00Z"),
    lastCandleOpen: new Date("2025-01-02T00:00:00Z"),
    rowCount: "25",
    schemaVersion: "tradepilot-candles-v1",
    artifactKey: `data/snapshots/${datasetId}`,
    isSynthetic: true,
    integrityVerifiedAt: new Date("2025-01-03T00:00:00Z"),
  });
  await repository.insertVerifiedCandidateReport({
    reportId: "c".repeat(64),
    datasetId,
    strategyName: "Price Range Breakout",
    strategyVersion: "v1",
    configurationFingerprint: "d".repeat(64),
    schemaVersion: "tradepilot-candidate-report-v1",
    signalCount: 0,
    artifactKey: `reports/${"c".repeat(64)}`,
    integrityVerifiedAt: new Date("2025-01-03T00:00:00Z"),
  });

  const stored = await repository.findDataset(datasetId);
  assert.ok(stored !== undefined);
  assert.equal(stored.datasetId, datasetId);
  assert.equal(stored.canonicalChecksum, checksum);
  assert.equal(stored.rowCount, "25");

  await assert.rejects(
    repository.insertVerifiedDataset({
      ...stored, datasetId: "invalid", artifactKey: "data/invalid",
    }),
    /datasets_id_format/,
  );
  await assert.rejects(
    repository.insertVerifiedCandidateReport({
      reportId: "e".repeat(64), datasetId: "f".repeat(64),
      strategyName: "strategy", strategyVersion: "v1",
      configurationFingerprint: "1".repeat(64), schemaVersion: "v1",
      signalCount: 0, artifactKey: "reports/missing-dataset",
      integrityVerifiedAt: new Date("2025-01-03T00:00:00Z"),
    }),
    /foreign key constraint/,
  );
  await assert.rejects(
    repository.insertInstrument({
      symbol: "EURUSD", baseCurrency: "EUR", quoteCurrency: "USD",
      pipSize: "0.0001", pricePrecision: 5,
    }),
    /duplicate key value/,
  );

  assert.deepEqual(await migrate(pool, migrations, "down"), ["005"]);
  assert.deepEqual(await migrate(pool, migrations, "down"), ["004"]);
  assert.deepEqual(await migrate(pool, migrations, "down"), ["003"]);
  assert.deepEqual(await migrate(pool, migrations, "down"), ["002"]);
  assert.deepEqual(await migrate(pool, migrations, "down"), ["001"]);
  const tables = await pool.query<{ name: string | null }>("SELECT to_regclass('datasets') AS name");
  assert.equal(tables.rows[0]?.name, null);
});
