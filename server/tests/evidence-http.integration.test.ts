import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import request from "supertest";
import { createApp } from "../src/app.js";
import type { AppConfig, ArtifactVerifierConfig } from "../src/config/env.js";
import type { CandidateReportCatalogView, CatalogReadStore } from "../src/database/catalog-read-repository.js";
import { CandidateEvidenceService } from "../src/evidence/evidence-service.js";
import { silentLogger } from "../src/logging/logger.js";
import { TEST_AUTH_CONFIG, TEST_AUTHORIZATION, TEST_SECURITY_CONFIG, viewerTokenVerifier } from "./security-fixtures.js";

const SERVER_ROOT = process.cwd();
const RESEARCH_ROOT = resolve(SERVER_ROOT, "..", "research");
const WINDOWS_PYTHON = resolve(RESEARCH_ROOT, ".venv", "Scripts", "python.exe");
const UNIX_PYTHON = resolve(RESEARCH_ROOT, ".venv", "bin", "python");
const PYTHON = process.env["TRADEPILOT_TEST_PYTHON"]
  ?? (existsSync(WINDOWS_PYTHON) ? WINDOWS_PYTHON : existsSync(UNIX_PYTHON) ? UNIX_PYTHON : "python");

interface Fixture { readonly report_id: string; readonly report_path: string; readonly dataset_id: string; }

function fixture(empty = false): { stored: Fixture; verifier: ArtifactVerifierConfig } {
  const root = mkdtempSync(join(tmpdir(), "tradepilot-evidence-http-"));
  const data = join(root, "data");
  const reports = join(root, "reports");
  mkdirSync(data);
  mkdirSync(reports);
  const script = resolve(SERVER_ROOT, "tests", "fixtures", "create-verifier-fixture.py");
  const args = [script, data, reports, ...(empty ? ["empty"] : [])];
  const result = spawnSync(PYTHON, args, {
    cwd: RESEARCH_ROOT,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: resolve(RESEARCH_ROOT, "src") },
  });
  assert.equal(result.status, 0, result.stderr);
  return {
    stored: JSON.parse(result.stdout) as Fixture,
    verifier: {
      pythonExecutable: PYTHON,
      pythonWorkingDirectory: RESEARCH_ROOT,
      schemaDirectory: resolve(RESEARCH_ROOT, "contracts"),
      datasetRoot: data,
      reportRoot: reports,
      timeoutMs: 5_000,
      maxInputBytes: 65_536,
      maxOutputBytes: 1_048_576,
      maxErrorBytes: 16_384,
      maxConcurrency: 2,
      maxPendingRequests: 4,
    },
  };
}

function reportView(stored: Fixture, reportId = stored.report_id): CandidateReportCatalogView {
  return {
    reportId,
    datasetId: stored.dataset_id,
    strategyName: "Price Range Breakout",
    strategyVersion: "v1",
    configurationFingerprint: "a".repeat(64),
    schemaVersion: "tradepilot-candidate-report-v1",
    signalCount: 1,
    datasetIsSynthetic: true,
    verifiedAt: new Date("2026-01-03T00:00:00Z"),
  };
}

function catalog(item: CandidateReportCatalogView | undefined, fails = false): CatalogReadStore {
  return {
    async listInstruments() { return []; }, async listDatasets() { return []; },
    async listCandidateReports() { return item === undefined ? [] : [item]; },
    async getInstrument() { return undefined; }, async getDataset() { return undefined; },
    async getCandidateReport(reportId) {
      if (fails) throw new Error("database detail");
      return item?.reportId === reportId ? item : undefined;
    },
  };
}

function config(verifier: ArtifactVerifierConfig): AppConfig {
  return {
    nodeEnv: "test", host: "127.0.0.1", port: 3000, logLevel: "error",
    databaseUrl: "postgresql://unused", databaseConnectTimeoutMs: 100,
    databaseReadyTimeoutMs: 100, artifactVerifier: verifier,
    auth: TEST_AUTH_CONFIG, security: TEST_SECURITY_CONFIG,
  };
}

function app(generated: ReturnType<typeof fixture>, store = catalog(reportView(generated.stored))) {
  return createApp({
    config: config(generated.verifier), logger: silentLogger,
    database: { async check() { return true; } }, catalog: store,
    evidence: new CandidateEvidenceService(generated.verifier),
    tokenVerifier: viewerTokenVerifier,
  });
}

function api(target: ReturnType<typeof app>, path: string) {
  return request(target).get(path).set("authorization", TEST_AUTHORIZATION);
}

test("verified candidates and evidence are projected without canonical report access", async () => {
  const generated = fixture();
  const list = await api(app(generated), `/api/v1/candidate-reports/${generated.stored.report_id}/candidates/`)
    .expect(200);
  assert.equal(list.body.data.items.length, 1);
  const candidate = list.body.data.items[0];
  assert.equal(candidate.classification, "HISTORICAL_RESEARCH");
  assert.equal(candidate.liveSignal, false);
  assert.equal(candidate.strategy.name, "price_range_breakout");
  assert.equal(candidate.provenance.reportSchemaVersion, "tradepilot-candidate-report-v1");
  assert.equal(list.text.includes(generated.verifier.reportRoot), false);
  assert.equal(list.text.includes("report.json"), false);

  const detail = await api(app(generated), `/api/v1/evidence/${candidate.candidateEvidenceId}/`)
    .expect(200);
  assert.deepEqual(detail.body.data, candidate);

  const offsets: number[] = [];
  const pagedApp = createApp({
    config: config(generated.verifier), logger: silentLogger,
    database: { async check() { return true; } }, catalog: catalog(reportView(generated.stored)),
    evidence: {
      async list(reportId, offset) {
        offsets.push(offset);
        return {
          contract_version: "tradepilot-candidate-evidence/v1" as const,
          request_id: "mock", status: "OK" as const, operation: "list_candidates" as const,
          report_id: reportId, candidates: [candidate], next_offset: offset === 0 ? 1 : null,
          total_count: 2,
        };
      },
      async get() { return candidate; },
    },
    tokenVerifier: viewerTokenVerifier,
  });
  const firstPage = await api(pagedApp, `/api/v1/candidate-reports/${generated.stored.report_id}/candidates?limit=1`).expect(200);
  await api(pagedApp, `/api/v1/candidate-reports/${generated.stored.report_id}/candidates?limit=1&cursor=${encodeURIComponent(firstPage.body.data.nextCursor)}`)
    .expect(200);
  assert.deepEqual(offsets, [0, 1]);
});

test("empty, missing, corrupted, mismatched, oversized, and database failures fail closed", async () => {
  const empty = fixture(true);
  const emptyResponse = await api(app(empty), `/api/v1/candidate-reports/${empty.stored.report_id}/candidates`).expect(200);
  assert.deepEqual(emptyResponse.body.data.items, []);

  const missing = fixture();
  await api(app(missing, catalog(undefined)), `/api/v1/candidate-reports/${"f".repeat(64)}/candidates`).expect(404);
  const absentId = "f".repeat(64);
  const absentArtifact = await api(app(missing, catalog(reportView(missing.stored, absentId))), `/api/v1/candidate-reports/${absentId}/candidates`).expect(409);
  assert.equal(absentArtifact.body.error.code, "EVIDENCE_UNAVAILABLE");
  await api(app(missing, catalog(reportView(missing.stored))), `/api/v1/candidate-reports/${missing.stored.report_id}/candidates?limit=101`).expect(400);

  const corrupt = fixture();
  writeFileSync(corrupt.stored.report_path, "{}");
  const corruptResponse = await api(app(corrupt), `/api/v1/candidate-reports/${corrupt.stored.report_id}/candidates`).expect(409);
  assert.equal(corruptResponse.body.error.code, "EVIDENCE_UNAVAILABLE");
  assert.equal(corruptResponse.text.includes(corrupt.verifier.reportRoot), false);

  const mismatch = fixture();
  const wrongId = "e".repeat(64);
  cpSync(join(mismatch.verifier.reportRoot, mismatch.stored.report_id),
    join(mismatch.verifier.reportRoot, wrongId), { recursive: true });
  const mismatchResponse = await api(app(mismatch, catalog(reportView(mismatch.stored, wrongId))), `/api/v1/candidate-reports/${wrongId}/candidates`).expect(409);
  assert.equal(mismatchResponse.body.error.code, "EVIDENCE_UNAVAILABLE");

  const failed = fixture();
  const databaseFailure = await api(app(failed, catalog(reportView(failed.stored), true)), `/api/v1/candidate-reports/${failed.stored.report_id}/candidates`).expect(503);
  assert.equal(databaseFailure.body.error.code, "CATALOG_UNAVAILABLE");

  const oversized = fixture();
  const tinyConfig = { ...oversized.verifier, maxOutputBytes: 100 };
  const oversizedApp = createApp({
    config: config(tinyConfig), logger: silentLogger,
    database: { async check() { return true; } }, catalog: catalog(reportView(oversized.stored)),
    evidence: new CandidateEvidenceService(tinyConfig),
    tokenVerifier: viewerTokenVerifier,
  });
  const oversizedResponse = await api(oversizedApp, `/api/v1/candidate-reports/${oversized.stored.report_id}/candidates`).expect(409);
  assert.equal(oversizedResponse.body.error.code, "EVIDENCE_UNAVAILABLE");
});
