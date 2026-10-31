import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { loadConfig } from "../config/env.js";
import { createDatabase } from "../database/database.js";
import { ArtifactVerifierService } from "../verification/artifact-verifier.js";
import { CatalogRegistrationService } from "../catalog/registration-service.js";

interface SmokeState { token: string; jobId: string; datasetId: string }
const statePath = "/smoke-state/state.json";
const api = "http://api:3000/api/v1";

async function json(url: string, token: string, init: RequestInit = {}): Promise<Record<string, unknown>> {
  const response = await fetch(url, { ...init, headers: {
    authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers ?? {}),
  } });
  const body = await response.json() as Record<string, unknown>;
  if (!response.ok) throw new Error(`smoke HTTP ${response.status}: ${JSON.stringify(body)}`);
  return body;
}

function data(body: Record<string, unknown>): Record<string, unknown> {
  const value = body["data"];
  if (typeof value !== "object" || value === null) throw new Error("missing API data envelope");
  return value as Record<string, unknown>;
}

async function token(): Promise<string> {
  const response = await fetch("https://oidc:8443/token");
  if (!response.ok) throw new Error("OIDC token request failed");
  const body = await response.json() as { access_token?: unknown };
  if (typeof body.access_token !== "string") throw new Error("OIDC token is missing");
  return body.access_token;
}

async function seedSubmit(): Promise<void> {
  const config = loadConfig();
  const fixture = spawnSync(config.artifactVerifier.pythonExecutable, [
    "/app/server/tests/fixtures/create-verifier-fixture.py", config.artifactVerifier.datasetRoot,
  ], { cwd: "/app/research", encoding: "utf8", env: { ...process.env, PYTHONPATH: "/app/research/src:/app/research/tests" } });
  if (fixture.status !== 0) throw new Error(`fixture creation failed: ${fixture.stderr}`);
  const datasetId = (JSON.parse(fixture.stdout) as { dataset_id: string }).dataset_id;
  const database = createDatabase(config);
  try {
    await new CatalogRegistrationService(
      new ArtifactVerifierService(config.artifactVerifier), database.pool,
    ).registerDataset({ kind: "dataset", artifact_id: datasetId, provider: "mock", instrument: "EURUSD", timeframe: "H1" });
  } finally { await database.close(); }
  const accessToken = await token();
  const submitted = data(await json(`${api}/research-jobs`, accessToken, {
    method: "POST", body: JSON.stringify({
      contractVersion: "tradepilot-research-job-request/v1", idempotencyKey: "docker_smoke_primary_001",
      datasetId, instrument: "EURUSD", timeframe: "H1",
      strategy: { name: "price_range_breakout", version: "v1" },
    }),
  }));
  if (typeof submitted["jobId"] !== "string") throw new Error("job ID is missing");
  writeFileSync(statePath, JSON.stringify({ token: accessToken, jobId: submitted["jobId"], datasetId } satisfies SmokeState));
  process.stdout.write(`${JSON.stringify({ phase: "submitted", jobId: submitted["jobId"], datasetId })}\n`);
}

function state(): SmokeState { return JSON.parse(readFileSync(statePath, "utf8")) as SmokeState; }

async function waitFor(expected: readonly string[], timeoutMs: number): Promise<Record<string, unknown>> {
  const saved = state(); const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = data(await json(`${api}/research-jobs/${saved.jobId}`, saved.token));
    if (expected.includes(String(job["state"]))) return job;
    await new Promise<void>((done) => setTimeout(done, 100));
  }
  throw new Error(`job did not reach ${expected.join("/")}`);
}

async function verify(): Promise<void> {
  const saved = state();
  const completed = await waitFor(["SUCCEEDED"], 60_000);
  const reportId = completed["resultReportId"];
  if (typeof reportId !== "string") throw new Error("successful job has no report ID");
  const candidates = data(await json(`${api}/candidate-reports/${reportId}/candidates?limit=10`, saved.token));
  if (candidates["classification"] !== "HISTORICAL_RESEARCH" || candidates["liveSignal"] !== false) {
    throw new Error("historical evidence classification is unsafe");
  }
  const repeated = data(await json(`${api}/research-jobs`, saved.token, {
    method: "POST", body: JSON.stringify({
      contractVersion: "tradepilot-research-job-request/v1", idempotencyKey: "docker_smoke_reuse_001",
      datasetId: saved.datasetId, instrument: "EURUSD", timeframe: "H1",
      strategy: { name: "price_range_breakout", version: "v1" },
    }),
  }));
  const secondId = repeated["jobId"];
  if (typeof secondId !== "string") throw new Error("reuse job ID is missing");
  const original = { ...saved, jobId: secondId }; writeFileSync(statePath, JSON.stringify(original));
  const second = await waitFor(["SUCCEEDED"], 60_000);
  if (second["resultReportId"] !== reportId) throw new Error("immutable report was not reused");
  process.stdout.write(`${JSON.stringify({ phase: "verified", reportId, candidateCount: candidates["totalCount"] })}\n`);
}

const mode = process.argv[2];
if (mode === "seed-submit") await seedSubmit();
else if (mode === "wait-running") {
  const job = await waitFor(["RUNNING", "SUCCEEDED"], 20_000);
  if (job["state"] !== "RUNNING") throw new Error("job completed before lease-recovery interruption");
  process.stdout.write(`${JSON.stringify({ phase: "running", jobId: job["jobId"] })}\n`);
} else if (mode === "verify") await verify();
else throw new Error("usage: smoke <seed-submit|wait-running|verify>");
