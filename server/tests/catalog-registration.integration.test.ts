import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import test, { after, before } from "node:test";
import { Pool } from "pg";
import { CatalogRegistrationError } from "../src/catalog/errors.js";
import { CatalogRegistrationService } from "../src/catalog/registration-service.js";
import type { ArtifactVerifierConfig } from "../src/config/env.js";
import { migrate } from "../src/database/migrator.js";
import { ArtifactVerifierService } from "../src/verification/artifact-verifier.js";

const databaseUrl = process.env["TEST_DATABASE_URL"];
const schema = `registration_${randomUUID().replaceAll("-", "")}`;
const admin = databaseUrl === undefined ? undefined : new Pool({ connectionString: databaseUrl });
const pool = databaseUrl === undefined ? undefined : new Pool({
  connectionString: databaseUrl,
  options: `-c search_path=${schema}`,
  max: 8,
});
const SERVER_ROOT = process.cwd();
const RESEARCH_ROOT = resolve(SERVER_ROOT, "..", "research");
const WINDOWS_PYTHON = resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe");
const UNIX_PYTHON = resolve(RESEARCH_ROOT, ".venv", "bin", "python");
const PYTHON = process.env["TRADEPILOT_TEST_PYTHON"]
  ?? (existsSync(WINDOWS_PYTHON) ? WINDOWS_PYTHON : existsSync(UNIX_PYTHON) ? UNIX_PYTHON : "python");

interface Fixture {
  readonly dataset_id: string;
  readonly dataset_checksum: string;
  readonly report_id: string;
  readonly report_path: string;
}

before(async () => {
  if (admin !== undefined && pool !== undefined) {
    await admin.query(`CREATE SCHEMA ${schema}`);
    await migrate(pool, resolve(SERVER_ROOT, "migrations"), "up");
  }
});

after(async () => {
  if (pool !== undefined) await pool.end();
  if (admin !== undefined) {
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
    await admin.end();
  }
});

function fixture(): { settings: ArtifactVerifierConfig; stored: Fixture } {
  const root = mkdtempSync(join(tmpdir(), "tradepilot-registration-"));
  const data = join(root, "data");
  const reports = join(root, "reports");
  mkdirSync(data);
  mkdirSync(reports);
  const script = resolve(SERVER_ROOT, "tests", "fixtures", "create-verifier-fixture.py");
  const result = spawnSync(PYTHON, [script, data, reports], {
    cwd: RESEARCH_ROOT,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: resolve(RESEARCH_ROOT, "src") },
  });
  assert.equal(result.status, 0, result.stderr);
  return {
    settings: {
      pythonExecutable: PYTHON,
      pythonWorkingDirectory: RESEARCH_ROOT,
      schemaDirectory: resolve(RESEARCH_ROOT, "contracts"),
      datasetRoot: data,
      reportRoot: reports,
      timeoutMs: 5_000,
      maxInputBytes: 65_536,
      maxOutputBytes: 1_048_576,
      maxErrorBytes: 16_384,
      maxConcurrency: 4,
      maxPendingRequests: 8,
    },
    stored: JSON.parse(result.stdout) as Fixture,
  };
}

function datasetRequest(stored: Fixture) {
  return {
    kind: "dataset" as const,
    artifact_id: stored.dataset_id,
    provider: "mock",
    instrument: "EURUSD",
    timeframe: "H1",
  };
}

test("verified registration is idempotent, transactional, and fails closed", {
  skip: databaseUrl === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const generated = fixture();
  const service = new CatalogRegistrationService(
    new ArtifactVerifierService(generated.settings), pool,
  );

  await assert.rejects(
    service.registerCandidateReport({
      kind: "candidate_report", artifact_id: generated.stored.report_id,
    }),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "VERIFIED_DATASET_REQUIRED",
  );

  const first = await service.registerDataset(datasetRequest(generated.stored));
  const duplicate = await service.registerDataset(datasetRequest(generated.stored));
  assert.equal(first.disposition, "REGISTERED");
  assert.equal(duplicate.disposition, "EXISTING");
  const datasetRow = await pool.query<{
    canonical_checksum: string; artifact_key: string; pip_size: string;
  }>(
    `SELECT d.canonical_checksum, d.artifact_key, i.pip_size
       FROM datasets d JOIN instruments i ON i.symbol = d.instrument_symbol
      WHERE d.dataset_id = $1`,
    [generated.stored.dataset_id],
  );
  assert.equal(datasetRow.rows[0]?.canonical_checksum, generated.stored.dataset_checksum);
  assert.equal(
    datasetRow.rows[0]?.artifact_key,
    `datasets/mock/EURUSD/H1/snapshots/${generated.stored.dataset_id}`,
  );
  assert.equal(datasetRow.rows[0]?.pip_size, "0.0001");

  const report = await service.registerCandidateReport({
    kind: "candidate_report", artifact_id: generated.stored.report_id,
  });
  const reportAgain = await service.registerCandidateReport({
    kind: "candidate_report", artifact_id: generated.stored.report_id,
  });
  assert.equal(report.disposition, "REGISTERED");
  assert.equal(reportAgain.disposition, "EXISTING");

  await assert.rejects(
    service.registerDataset({ ...datasetRequest(generated.stored), artifact_id: "f".repeat(64) }),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "ARTIFACT_NOT_FOUND",
  );

  await pool.query("UPDATE datasets SET provider = 'conflicting-provider' WHERE dataset_id = $1", [
    generated.stored.dataset_id,
  ]);
  await assert.rejects(
    service.registerDataset(datasetRequest(generated.stored)),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "IMMUTABLE_METADATA_CONFLICT",
  );
  await pool.query("UPDATE datasets SET provider = 'mock' WHERE dataset_id = $1", [
    generated.stored.dataset_id,
  ]);

  await pool.query("UPDATE candidate_reports SET strategy_name = 'conflict' WHERE report_id = $1", [
    generated.stored.report_id,
  ]);
  await assert.rejects(
    service.registerCandidateReport({
      kind: "candidate_report", artifact_id: generated.stored.report_id,
    }),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "IMMUTABLE_METADATA_CONFLICT",
  );

  const corrupt = fixture();
  const parquet = join(
    corrupt.settings.datasetRoot, "mock", "EURUSD", "H1", "snapshots",
    corrupt.stored.dataset_id, "candles.parquet",
  );
  const bytes = Buffer.from(readFileSync(parquet));
  bytes[Math.floor(bytes.length / 2)] = (bytes[Math.floor(bytes.length / 2)] ?? 0) ^ 0xff;
  writeFileSync(parquet, bytes);
  await assert.rejects(
    new CatalogRegistrationService(new ArtifactVerifierService(corrupt.settings), pool)
      .registerDataset(datasetRequest(corrupt.stored)),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "ARTIFACT_VERIFICATION_FAILED",
  );

  const mismatch = fixture();
  const wrongId = "e".repeat(64);
  cpSync(
    join(mismatch.settings.datasetRoot, "mock", "EURUSD", "H1", "snapshots", mismatch.stored.dataset_id),
    join(mismatch.settings.datasetRoot, "mock", "EURUSD", "H1", "snapshots", wrongId),
    { recursive: true },
  );
  await assert.rejects(
    new CatalogRegistrationService(new ArtifactVerifierService(mismatch.settings), pool)
      .registerDataset({ ...datasetRequest(mismatch.stored), artifact_id: wrongId }),
    (error: unknown) => error instanceof CatalogRegistrationError
      && error.code === "ARTIFACT_ID_MISMATCH",
  );
  await pool.query("DELETE FROM candidate_reports WHERE report_id = $1", [generated.stored.report_id]);
  await pool.query("DELETE FROM datasets WHERE dataset_id = $1", [generated.stored.dataset_id]);
  await pool.query("DELETE FROM instruments WHERE symbol = 'EURUSD'");
});

test("concurrent identical registration publishes one immutable row", {
  skip: databaseUrl === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const generated = fixture();
  const service = new CatalogRegistrationService(
    new ArtifactVerifierService(generated.settings), pool,
  );
  const results = await Promise.all([
    service.registerDataset(datasetRequest(generated.stored)),
    service.registerDataset(datasetRequest(generated.stored)),
  ]);
  assert.deepEqual(results.map((item) => item.disposition).sort(), ["EXISTING", "REGISTERED"]);
  const count = await pool.query<{ count: string }>(
    "SELECT count(*) FROM datasets WHERE dataset_id = $1", [generated.stored.dataset_id],
  );
  assert.equal(count.rows[0]?.count, "1");
});
