import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import test, { after, before } from "node:test";
import { Pool } from "pg";
import type { ArtifactVerifierConfig } from "../src/config/env.js";
import { CatalogRegistrationService } from "../src/catalog/registration-service.js";
import { migrate } from "../src/database/migrator.js";
import { RESEARCH_JOB_REQUEST_VERSION } from "../src/research-jobs/contracts.js";
import { PythonResearchExecutionService } from "../src/research-jobs/execution-service.js";
import { TrustedResearchJobProcessor } from "../src/research-jobs/processor.js";
import { ResearchJobRepository } from "../src/research-jobs/repository.js";
import { ResearchJobWorker } from "../src/research-jobs/worker-service.js";
import { ArtifactVerifierService } from "../src/verification/artifact-verifier.js";
import { silentLogger } from "../src/logging/logger.js";

const databaseUrl = process.env["TEST_DATABASE_URL"];
const schema = `worker_${randomUUID().replaceAll("-", "")}`;
const admin = databaseUrl === undefined ? undefined : new Pool({ connectionString: databaseUrl });
const pool = databaseUrl === undefined ? undefined : new Pool({
  connectionString: databaseUrl, options: `-c search_path=${schema}`,
});
const RESEARCH_ROOT = resolve(process.cwd(), "..", "research");
const PYTHON = existsSync(resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe"))
  ? resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe") : "python";
const REVISION = spawnSync("git", ["rev-parse", "HEAD"], { cwd: RESEARCH_ROOT, encoding: "utf8" }).stdout.trim();
let verifierConfig: ArtifactVerifierConfig;
let datasetId: string;

function fakeExecutor(mode: "timeout" | "malformed"): ArtifactVerifierConfig {
  const root = mkdtempSync(join(tmpdir(), `tradepilot-executor-${mode}-`));
  const packageRoot = join(root, "src", "tradepilot", "execution");
  mkdirSync(packageRoot, { recursive: true });
  writeFileSync(join(root, "src", "tradepilot", "__init__.py"), "");
  writeFileSync(join(packageRoot, "__init__.py"), "");
  writeFileSync(join(packageRoot, "__main__.py"), mode === "timeout"
    ? "import time; time.sleep(10)\n" : "print('malformed-output')\n");
  return { ...verifierConfig, pythonWorkingDirectory: root, timeoutMs: mode === "timeout" ? 75 : 2_000 };
}

function request(key: string, strategy: "price_range_breakout" | "ema_rsi_trend_pullback" = "price_range_breakout") {
  return { contractVersion: RESEARCH_JOB_REQUEST_VERSION, idempotencyKey: key, datasetId,
    instrument: "EURUSD" as const, timeframe: "H1" as const, strategy: { name: strategy, version: "v1" as const } };
}

before(async () => {
  if (admin === undefined || pool === undefined) return;
  await admin.query(`CREATE SCHEMA ${schema}`);
  await migrate(pool, resolve(process.cwd(), "migrations"), "up");
  const root = mkdtempSync(join(tmpdir(), "tradepilot-worker-e2e-"));
  const data = join(root, "data"); const reports = join(root, "reports");
  mkdirSync(data); mkdirSync(reports);
  const fixture = spawnSync(PYTHON, [resolve(process.cwd(), "tests", "fixtures", "create-verifier-fixture.py"), data], {
    cwd: RESEARCH_ROOT, encoding: "utf8", env: { ...process.env, PYTHONPATH: resolve(RESEARCH_ROOT, "src") },
  });
  assert.equal(fixture.status, 0, fixture.stderr);
  datasetId = (JSON.parse(fixture.stdout) as { dataset_id: string }).dataset_id;
  verifierConfig = {
    pythonExecutable: PYTHON, pythonWorkingDirectory: RESEARCH_ROOT,
    schemaDirectory: resolve(RESEARCH_ROOT, "contracts"), datasetRoot: data, reportRoot: reports,
    timeoutMs: 5_000, maxInputBytes: 65_536, maxOutputBytes: 1_048_576,
    maxErrorBytes: 16_384, maxConcurrency: 1, maxPendingRequests: 2,
  };
  await new CatalogRegistrationService(new ArtifactVerifierService(verifierConfig), pool).registerDataset({
    kind: "dataset", artifact_id: datasetId, provider: "mock", instrument: "EURUSD", timeframe: "H1",
  });
});

test("retryable execution timeouts requeue then fail after retry exhaustion", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 2,
    leaseMs: 2_000, implementationRevision: REVISION,
  });
  await repository.submit("timeout-owner", request("timeout_retry_001"));
  const processor = new TrustedResearchJobProcessor(
    new PythonResearchExecutionService(fakeExecutor("timeout"), REVISION),
    new CatalogRegistrationService(new ArtifactVerifierService(verifierConfig), pool),
  );
  const worker = new ResearchJobWorker(repository, processor, silentLogger, 10, 100);
  await worker.runOnce();
  let stored = (await repository.list("timeout-owner", false))[0]!;
  assert.equal(stored.state, "QUEUED");
  assert.equal(stored.errorCode, "VERIFIER_TIMEOUT");
  await worker.runOnce();
  stored = (await repository.list("timeout-owner", false))[0]!;
  assert.equal(stored.state, "FAILED");
  assert.equal(stored.attemptCount, 2);
});

test("malformed execution output is permanent and transitions directly to failed", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 3,
    leaseMs: 2_000, implementationRevision: REVISION,
  });
  await repository.submit("malformed-owner", request("malformed_output_001"));
  const processor = new TrustedResearchJobProcessor(
    new PythonResearchExecutionService(fakeExecutor("malformed"), REVISION),
    new CatalogRegistrationService(new ArtifactVerifierService(verifierConfig), pool),
  );
  await new ResearchJobWorker(repository, processor, silentLogger, 10, 100).runOnce();
  const stored = (await repository.list("malformed-owner", false))[0]!;
  assert.equal(stored.state, "FAILED");
  assert.equal(stored.errorCode, "INVALID_EXECUTION_OUTPUT");
  assert.equal(stored.attemptCount, 1);
});

test("actual heartbeat timer prevents premature lease recovery", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const preparationRepository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 2,
    leaseMs: 5_000, implementationRevision: REVISION,
  });
  const repository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 2,
    leaseMs: 100, implementationRevision: REVISION,
  });
  await preparationRepository.submit("heartbeat-prep", request("heartbeat_prep_001"));
  const preparation = await preparationRepository.claim();
  assert.ok(preparation !== undefined);
  const prepared = await new TrustedResearchJobProcessor(
    new PythonResearchExecutionService(verifierConfig, REVISION),
    new CatalogRegistrationService(new ArtifactVerifierService(verifierConfig), pool),
  ).process(preparation);
  await preparationRepository.succeed(preparation.jobId, preparation.leaseToken, prepared.reportId);
  await repository.submit("heartbeat-owner", request("heartbeat_timer_001"));
  const worker = new ResearchJobWorker(repository, {
    async process() {
      await new Promise<void>((resolveDelay) => setTimeout(resolveDelay, 250));
      return { reportId: prepared.reportId };
    },
  }, silentLogger, 10, 20);
  const running = worker.runOnce();
  await new Promise<void>((resolveDelay) => setTimeout(resolveDelay, 160));
  assert.equal(await repository.claim(), undefined);
  await running;
  assert.equal((await repository.list("heartbeat-owner", false))[0]?.state, "SUCCEEDED");
});

test("corrupt report before registration can never succeed", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 1,
    leaseMs: 5_000, implementationRevision: REVISION,
  });
  await repository.submit("corrupt-owner", request("corrupt_report_001"));
  const isolatedReportRoot = mkdtempSync(join(tmpdir(), "tradepilot-corrupt-report-"));
  const isolatedConfig = { ...verifierConfig, reportRoot: isolatedReportRoot };
  const registration = new CatalogRegistrationService(new ArtifactVerifierService(isolatedConfig), pool);
  const processor = new TrustedResearchJobProcessor(new PythonResearchExecutionService(isolatedConfig, REVISION), {
    async registerCandidateReport(candidate) {
      writeFileSync(join(isolatedReportRoot, candidate.artifact_id, "report.json"), "{}");
      return registration.registerCandidateReport(candidate);
    },
  });
  await new ResearchJobWorker(repository, processor, silentLogger, 10, 100).runOnce();
  const stored = (await repository.list("corrupt-owner", false))[0]!;
  assert.equal(stored.state, "FAILED");
  assert.equal(stored.resultReportId, null);
});

test("lost lease rejection is a normal worker outcome", { skip: pool === undefined }, async () => {
  assert.ok(pool !== undefined);
  const repository = new ResearchJobRepository(pool, {
    maxActivePerOwner: 2, maxQueueDepth: 20, maxAttempts: 2,
    leaseMs: 50, implementationRevision: REVISION,
  });
  await repository.submit("lost-lease-owner", request("lost_lease_001"));
  const worker = new ResearchJobWorker(repository, {
    async process() {
      await new Promise<void>((resolveDelay) => setTimeout(resolveDelay, 100));
      throw Object.assign(new Error("permanent"), { code: "PERMANENT_TEST", retryable: false });
    },
  }, silentLogger, 10, 1_000);
  assert.equal(await worker.runOnce(), true);
  const recovered = await repository.claim();
  assert.ok(recovered !== undefined);
  await repository.fail(recovered.jobId, recovered.leaseToken, "PERMANENT_TEST", false);
});
after(async () => {
  if (pool !== undefined) await pool.end();
  if (admin !== undefined) { await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`); await admin.end(); }
});

test("worker executes, verifies, registers, and crash-retries immutable reports", {
  skip: pool === undefined,
}, async () => {
  assert.ok(pool !== undefined);
  const limits = { maxActivePerOwner: 3, maxQueueDepth: 10, maxAttempts: 3, leaseMs: 60_000, pollMs: 100, implementationRevision: REVISION };
  const repository = new ResearchJobRepository(pool, limits);
  const processor = new TrustedResearchJobProcessor(
    new PythonResearchExecutionService(verifierConfig, REVISION),
    new CatalogRegistrationService(new ArtifactVerifierService(verifierConfig), pool),
  );
  const submit = (key: string, strategy: "price_range_breakout" | "ema_rsi_trend_pullback") =>
    repository.submit("e2e-owner", {
      contractVersion: RESEARCH_JOB_REQUEST_VERSION, idempotencyKey: key, datasetId,
      instrument: "EURUSD", timeframe: "H1", strategy: { name: strategy, version: "v1" },
    });

  await submit("breakout_e2e_001", "price_range_breakout");
  const breakout = await repository.claim();
  assert.ok(breakout !== undefined);
  const breakoutResult = await processor.process(breakout);
  await repository.succeed(breakout.jobId, breakout.leaseToken, breakoutResult.reportId);
  assert.equal((await repository.get(breakout.jobId, "e2e-owner", false))?.resultReportId, breakoutResult.reportId);

  await submit("pullback_crash_001", "ema_rsi_trend_pullback");
  const crashed = await repository.claim();
  assert.ok(crashed !== undefined);
  const publishedBeforeCrash = await processor.process(crashed);
  await pool.query("UPDATE research_jobs SET lease_expires_at=now()-interval '1 second' WHERE job_id=$1", [crashed.jobId]);
  const recovered = await repository.claim();
  assert.ok(recovered !== undefined);
  const repeated = await processor.process(recovered);
  assert.equal(repeated.reportId, publishedBeforeCrash.reportId);
  await repository.succeed(recovered.jobId, recovered.leaseToken, repeated.reportId);
  const reports = await pool.query<{ report_id: string }>("SELECT report_id FROM candidate_reports ORDER BY report_id");
  assert.equal(new Set(reports.rows.map((row) => row.report_id)).size, 2);
});
