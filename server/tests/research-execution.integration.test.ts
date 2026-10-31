import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import type { ArtifactVerifierConfig } from "../src/config/env.js";
import { PythonResearchExecutionService, ResearchExecutionError } from "../src/research-jobs/execution-service.js";
import type { ClaimedResearchJob } from "../src/research-jobs/models.js";

const SERVER_ROOT = process.cwd();
const RESEARCH_ROOT = resolve(SERVER_ROOT, "..", "research");
const PYTHON = process.env["TRADEPILOT_TEST_PYTHON"]
  ?? (existsSync(resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe"))
    ? resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe") : "python");
const REVISION = spawnSync("git", ["rev-parse", "HEAD"], { cwd: RESEARCH_ROOT, encoding: "utf8" }).stdout.trim();

function fixture(): { config: ArtifactVerifierConfig; datasetId: string } {
  const root = mkdtempSync(join(tmpdir(), "tradepilot-execution-"));
  const data = join(root, "data");
  const reports = join(root, "reports");
  mkdirSync(data); mkdirSync(reports);
  const result = spawnSync(PYTHON, [resolve(SERVER_ROOT, "tests", "fixtures", "create-verifier-fixture.py"), data], {
    cwd: RESEARCH_ROOT, encoding: "utf8",
    env: { ...process.env, PYTHONPATH: resolve(RESEARCH_ROOT, "src") },
  });
  assert.equal(result.status, 0, result.stderr);
  return {
    datasetId: (JSON.parse(result.stdout) as { dataset_id: string }).dataset_id,
    config: {
      pythonExecutable: PYTHON, pythonWorkingDirectory: RESEARCH_ROOT,
      schemaDirectory: resolve(RESEARCH_ROOT, "contracts"), datasetRoot: data, reportRoot: reports,
      timeoutMs: 5_000, maxInputBytes: 65_536, maxOutputBytes: 1_048_576,
      maxErrorBytes: 16_384, maxConcurrency: 1, maxPendingRequests: 1,
    },
  };
}

function job(datasetId: string, strategyName: string): ClaimedResearchJob {
  const now = new Date();
  return {
    jobId: "123e4567-e89b-42d3-a456-426614174000", ownerSubject: "researcher",
    datasetId, instrument: "EURUSD", timeframe: "H1", strategyName, strategyVersion: "v1",
    state: "RUNNING", attemptCount: 1, maxAttempts: 3, leaseToken: "lease",
    leaseExpiresAt: new Date(now.getTime() + 60_000), errorCode: null,
    createdAt: now, updatedAt: now, startedAt: now, completedAt: null, resultReportId: null,
    implementationRevision: REVISION,
  };
}

test("controlled Python execution supports both approved strategies, zero candidates, and reuse", async () => {
  const generated = fixture();
  const service = new PythonResearchExecutionService(generated.config, REVISION);
  for (const strategy of ["price_range_breakout", "ema_rsi_trend_pullback"]) {
    const first = await service.execute(job(generated.datasetId, strategy));
    const repeated = await service.execute(job(generated.datasetId, strategy));
    assert.equal(first.reportId, repeated.reportId);
    assert.equal(first.signalCount, 0);
    assert.equal(repeated.reused, true);
  }
});

test("unsupported inputs and corrupt execution data fail closed", async () => {
  const generated = fixture();
  const service = new PythonResearchExecutionService(generated.config, REVISION);
  await assert.rejects(service.execute(job(generated.datasetId, "arbitrary")),
    (error) => error instanceof ResearchExecutionError && !error.retryable);
  await assert.rejects(service.execute(job("f".repeat(64), "price_range_breakout")),
    (error) => error instanceof ResearchExecutionError && error.code === "DATASET_NOT_FOUND");
  await assert.rejects(
    service.execute({ ...job(generated.datasetId, "price_range_breakout"), implementationRevision: "0".repeat(40) }),
    (error) => error instanceof ResearchExecutionError
      && error.code === "IMPLEMENTATION_REVISION_MISMATCH" && !error.retryable,
  );

  const fake = mkdtempSync(join(tmpdir(), "tradepilot-corrupt-executor-"));
  const packageRoot = join(fake, "src", "tradepilot", "execution");
  mkdirSync(packageRoot, { recursive: true });
  writeFileSync(join(fake, "src", "tradepilot", "__init__.py"), "");
  writeFileSync(join(packageRoot, "__init__.py"), "");
  writeFileSync(join(packageRoot, "__main__.py"), "print('corrupt-output')\n");
  const corrupt = new PythonResearchExecutionService({ ...generated.config, pythonWorkingDirectory: fake }, REVISION);
  await assert.rejects(corrupt.execute(job(generated.datasetId, "price_range_breakout")),
    (error) => error instanceof ResearchExecutionError && error.code === "INVALID_EXECUTION_OUTPUT");
});
