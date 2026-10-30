import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import type { ArtifactVerifierConfig } from "../src/config/env.js";
import { ARTIFACT_CONTRACT_VERSION, type ArtifactVerificationRequest } from "../src/verification/contracts.js";
import { ArtifactVerificationError } from "../src/verification/errors.js";
import { ArtifactVerifierService } from "../src/verification/artifact-verifier.js";

const SERVER_ROOT = process.cwd();
const RESEARCH_ROOT = resolve(SERVER_ROOT, "..", "research");
const SCHEMA_ROOT = resolve(RESEARCH_ROOT, "contracts");
const WINDOWS_PYTHON = resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe");
const UNIX_PYTHON = resolve(RESEARCH_ROOT, ".venv", "bin", "python");
const PYTHON = process.env["TRADEPILOT_TEST_PYTHON"]
  ?? (existsSync(WINDOWS_PYTHON) ? WINDOWS_PYTHON : existsSync(UNIX_PYTHON) ? UNIX_PYTHON : "python");

function config(overrides: Partial<ArtifactVerifierConfig> = {}): ArtifactVerifierConfig {
  const root = mkdtempSync(join(tmpdir(), "tradepilot-node-verifier-"));
  const datasets = join(root, "data");
  const reports = join(root, "reports");
  mkdirSync(datasets);
  mkdirSync(reports);
  return {
    pythonExecutable: PYTHON,
    pythonWorkingDirectory: RESEARCH_ROOT,
    schemaDirectory: SCHEMA_ROOT,
    datasetRoot: datasets,
    reportRoot: reports,
    timeoutMs: 5_000,
    maxInputBytes: 65_536,
    maxOutputBytes: 1_048_576,
    maxErrorBytes: 16_384,
    maxConcurrency: 2,
    ...overrides,
  };
}

function datasetRequest(id: string, requestId = "node-integration-1"): ArtifactVerificationRequest {
  return {
    contract_version: ARTIFACT_CONTRACT_VERSION,
    request_id: requestId,
    operation: "verify_artifact",
    artifact: {
      kind: "dataset",
      artifact_id: id,
      provider: "mock",
      instrument: "EURUSD",
      timeframe: "H1",
    },
  };
}

function createDataset(settings: ArtifactVerifierConfig): { dataset_id: string; parquet: string } {
  const script = resolve(SERVER_ROOT, "tests", "fixtures", "create-verifier-fixture.py");
  const result = spawnSync(PYTHON, [script, settings.datasetRoot], {
    cwd: RESEARCH_ROOT,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: `${resolve(RESEARCH_ROOT, "src")}` },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout) as { dataset_id: string; parquet: string };
}

function fakePythonModule(
  mode: "malformed" | "oversized" | "timeout" | "failure" | "environment",
): string {
  const root = mkdtempSync(join(tmpdir(), "tradepilot-fake-python-"));
  const packageRoot = join(root, "src", "tradepilot", "contracts");
  mkdirSync(packageRoot, { recursive: true });
  writeFileSync(join(root, "src", "tradepilot", "__init__.py"), "");
  writeFileSync(join(packageRoot, "__init__.py"), "");
  const behavior = {
    malformed: "print('not-json')",
    oversized: "print('x' * 2048)",
    timeout: "import time; time.sleep(10)",
    failure: "import sys; sys.exit(9)",
    environment: "import json, os; request=json.loads(payload); artifact={\"kind\":request[\"artifact\"][\"kind\"],\"artifact_id\":request[\"artifact\"][\"artifact_id\"]}; print(json.dumps({\"contract_version\":request[\"contract_version\"],\"request_id\":request[\"request_id\"],\"status\":\"VERIFIED\",\"artifact\":artifact,\"verification\":{\"database_url_present\":\"DATABASE_URL\" in os.environ}}))",
  }[mode];
  writeFileSync(join(packageRoot, "__main__.py"), `import sys\npayload=sys.stdin.buffer.read()\n${behavior}\n`);
  return root;
}

test("child environment excludes backend credentials", async () => {
  const fakeRoot = fakePythonModule("environment");
  const prior = process.env["DATABASE_URL"];
  process.env["DATABASE_URL"] = "postgresql://secret:secret@private/database";
  try {
    const settings = config({ pythonWorkingDirectory: fakeRoot });
    const response = await new ArtifactVerifierService(settings).verify(
      datasetRequest("a".repeat(64), "node-environment"),
    );
    assert.equal(response.verification["database_url_present"], false);
  } finally {
    if (prior === undefined) delete process.env["DATABASE_URL"];
    else process.env["DATABASE_URL"] = prior;
  }
});

test("valid artifact is verified through the real Python contract without Decimal loss", async () => {
  const settings = config();
  const stored = createDataset(settings);
  const response = await new ArtifactVerifierService(settings).verify(datasetRequest(stored.dataset_id));
  assert.equal(response.status, "VERIFIED");
  assert.equal(response.artifact.artifact_id, stored.dataset_id);
  assert.equal(response.verification["pip_size"], "0.0001");
});

test("missing and corrupted artifacts map to safe typed contract errors", async () => {
  const settings = config();
  const service = new ArtifactVerifierService(settings);
  await assert.rejects(
    service.verify(datasetRequest("a".repeat(64))),
    (error: unknown) => error instanceof ArtifactVerificationError
      && error.kind === "CONTRACT_FAILURE" && error.code === "ARTIFACT_NOT_FOUND",
  );

  const stored = createDataset(settings);
  const bytes = Buffer.from(readFileSync(stored.parquet));
  bytes[Math.floor(bytes.length / 2)] = (bytes[Math.floor(bytes.length / 2)] ?? 0) ^ 0xff;
  writeFileSync(stored.parquet, bytes);
  await assert.rejects(
    service.verify(datasetRequest(stored.dataset_id, "node-corrupt-1")),
    (error: unknown) => error instanceof ArtifactVerificationError
      && error.kind === "CONTRACT_FAILURE" && error.code === "ARTIFACT_VERIFICATION_FAILED"
      && !error.message.includes(settings.datasetRoot),
  );
});

test("request schema and input bound fail before spawning Python", async () => {
  const settings = config({ maxInputBytes: 100 });
  const service = new ArtifactVerifierService(settings);
  await assert.rejects(
    service.verify(datasetRequest("a".repeat(64))),
    (error: unknown) => error instanceof ArtifactVerificationError
      && error.code === "REQUEST_TOO_LARGE",
  );
  const invalid = { ...datasetRequest("a".repeat(64)), unexpected: true };
  await assert.rejects(
    service.verify(invalid as ArtifactVerificationRequest),
    (error: unknown) => error instanceof ArtifactVerificationError
      && error.code === "INVALID_REQUEST",
  );
});

for (const [mode, expectedCode] of [
  ["malformed", "INVALID_JSON_RESPONSE"],
  ["oversized", "STDOUT_LIMIT_EXCEEDED"],
  ["timeout", "VERIFIER_TIMEOUT"],
  ["failure", "VERIFIER_EXIT_FAILURE"],
] as const) {
  test(`${mode} subprocess behavior fails closed`, async () => {
    const fakeRoot = fakePythonModule(mode);
    const settings = config({
      pythonWorkingDirectory: fakeRoot,
      timeoutMs: mode === "timeout" ? 100 : 2_000,
      maxOutputBytes: 256,
    });
    await assert.rejects(
      new ArtifactVerifierService(settings).verify(datasetRequest("a".repeat(64), `node-${mode}`)),
      (error: unknown) => error instanceof ArtifactVerificationError && error.code === expectedCode,
    );
  });
}

test("configured concurrency bound queues excess verifier processes", async () => {
  const fakeRoot = fakePythonModule("timeout");
  const settings = config({ pythonWorkingDirectory: fakeRoot, timeoutMs: 75, maxConcurrency: 1 });
  const service = new ArtifactVerifierService(settings);
  const started = Date.now();
  const results = await Promise.allSettled([
    service.verify(datasetRequest("a".repeat(64), "queue-1")),
    service.verify(datasetRequest("a".repeat(64), "queue-2")),
  ]);
  assert.equal(results.every((result) => result.status === "rejected"), true);
  assert.ok(Date.now() - started >= 120);
});
