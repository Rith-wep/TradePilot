import assert from "node:assert/strict";
import test from "node:test";
import request from "supertest";
import { createApp } from "../src/app.js";
import type { AppConfig } from "../src/config/env.js";
import type {
  CandidateReportCatalogView,
  CatalogPageRequest,
  CatalogReadStore,
  DatasetCatalogView,
  InstrumentCatalogView,
} from "../src/database/catalog-read-repository.js";
import { silentLogger } from "../src/logging/logger.js";

const verifiedAt = new Date("2026-01-03T00:00:00.000Z");
const ids = ["1".repeat(64), "2".repeat(64), "3".repeat(64)];

const instruments: readonly InstrumentCatalogView[] = ["EURUSD", "GBPUSD"].map((symbol) => ({
  symbol,
  baseCurrency: symbol.slice(0, 3),
  quoteCurrency: symbol.slice(3),
  pipSize: "0.0001",
  pricePrecision: 5,
  verifiedAt,
}));
const datasets: readonly DatasetCatalogView[] = ids.map((datasetId, index) => ({
  datasetId,
  canonicalChecksum: `${index + 4}`.repeat(64),
  instrument: index === 2 ? "GBPUSD" : "EURUSD",
  provider: "verified-fixture",
  timeframe: "H1",
  firstCandleOpen: new Date("2025-01-01T00:00:00.000Z"),
  lastCandleOpen: new Date("2025-01-02T00:00:00.000Z"),
  rowCount: "25",
  schemaVersion: "tradepilot-candles-v1",
  isSynthetic: index === 0,
  verifiedAt,
}));
const reports: readonly CandidateReportCatalogView[] = ids.map((reportId, index) => ({
  reportId,
  datasetId: datasets[index]?.datasetId ?? ids[0]!,
  strategyName: "Price Range Breakout",
  strategyVersion: "v1",
  configurationFingerprint: "a".repeat(64),
  schemaVersion: "tradepilot-candidate-report-v1",
  signalCount: index,
  datasetIsSynthetic: index === 0,
  verifiedAt,
}));

function select<T>(rows: readonly T[], request: CatalogPageRequest, key: (row: T) => string): readonly T[] {
  return rows.filter((row) => request.after === undefined || key(row) > request.after)
    .slice(0, request.limit + 1);
}

const catalog: CatalogReadStore = {
  async listInstruments(page) { return select(instruments, page, (item) => item.symbol); },
  async listDatasets(page) { return select(datasets, page, (item) => item.datasetId); },
  async listCandidateReports(page) { return select(reports, page, (item) => item.reportId); },
  async getInstrument(symbol) { return instruments.find((item) => item.symbol === symbol); },
  async getDataset(datasetId) { return datasets.find((item) => item.datasetId === datasetId); },
  async getCandidateReport(reportId) { return reports.find((item) => item.reportId === reportId); },
};
const unusedEvidence = {
  async list() { throw new Error("unused"); },
  async get() { throw new Error("unused"); },
};

function config(nodeEnv: AppConfig["nodeEnv"] = "test"): AppConfig {
  return {
    nodeEnv,
    host: "127.0.0.1",
    port: 3000,
    logLevel: "error",
    databaseUrl: "postgresql://unused",
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
}

function app(store: CatalogReadStore = catalog, nodeEnv: AppConfig["nodeEnv"] = "test") {
  return createApp({
    config: config(nodeEnv),
    logger: silentLogger,
    database: { async check() { return true; } },
    catalog: store,
    evidence: unusedEvidence,
  });
}

test("catalog collections support slash variants and safe historical classifications", async () => {
  const instrumentsResponse = await request(app()).get("/api/v1/instruments/").expect(200);
  assert.equal(instrumentsResponse.body.data.items.length, 2);
  assert.equal(instrumentsResponse.body.data.items[0].pipSize, "0.0001");

  const datasetResponse = await request(app()).get("/api/v1/datasets").expect(200);
  assert.equal(datasetResponse.body.data.items[0].sourceClassification, "SYNTHETIC");
  assert.equal(datasetResponse.body.data.items[1].dataClassification, "HISTORICAL");
  assert.equal(datasetResponse.body.data.items[0].rowCount, "25");
  assert.equal(datasetResponse.text.includes("artifactKey"), false);
  assert.equal(datasetResponse.text.includes("path"), false);

  const reportsResponse = await request(app()).get("/api/v1/candidate-reports/").expect(200);
  assert.equal(reportsResponse.body.data.items[0].liveSignal, false);
  assert.equal(reportsResponse.body.data.items[0].classification, "HISTORICAL_RESEARCH_CANDIDATES");
});

test("cursor pagination is deterministic and endpoint-specific", async () => {
  const first = await request(app()).get("/api/v1/datasets?limit=2").expect(200);
  assert.deepEqual(first.body.data.items.map((item: { datasetId: string }) => item.datasetId), ids.slice(0, 2));
  assert.equal(typeof first.body.data.nextCursor, "string");
  const second = await request(app())
    .get(`/api/v1/datasets?limit=2&cursor=${encodeURIComponent(first.body.data.nextCursor)}`)
    .expect(200);
  assert.deepEqual(second.body.data.items.map((item: { datasetId: string }) => item.datasetId), ids.slice(2));
  assert.equal(second.body.data.nextCursor, null);
  await request(app())
    .get(`/api/v1/candidate-reports?cursor=${encodeURIComponent(first.body.data.nextCursor)}`)
    .expect(400);
});

test("ID-based detail routes validate identifiers and return catalog metadata", async () => {
  const instrument = await request(app()).get("/api/v1/instruments/EURUSD").expect(200);
  assert.equal(instrument.body.data.pipSize, "0.0001");
  const dataset = await request(app()).get(`/api/v1/datasets/${ids[0]}`).expect(200);
  assert.equal(dataset.body.data.datasetId, ids[0]);
  assert.equal(dataset.body.data.dataClassification, "HISTORICAL");
  const report = await request(app()).get(`/api/v1/candidate-reports/${ids[0]}`).expect(200);
  assert.equal(report.body.data.liveSignal, false);
  await request(app()).get("/api/v1/instruments/eurusd").expect(400);
  await request(app()).get("/api/v1/datasets/not-an-id").expect(400);
  await request(app()).get(`/api/v1/datasets/${"f".repeat(64)}`).expect(404);
});

test("empty, invalid, missing, database-failure, and nonlocal cases fail safely", async () => {
  const empty: CatalogReadStore = {
    async listInstruments() { return []; },
    async listDatasets() { return []; },
    async listCandidateReports() { return []; },
    async getInstrument() { return undefined; },
    async getDataset() { return undefined; },
    async getCandidateReport() { return undefined; },
  };
  const emptyResponse = await request(app(empty)).get("/api/v1/datasets").expect(200);
  assert.deepEqual(emptyResponse.body.data, { items: [], nextCursor: null, historicalOnly: true });

  for (const query of ["limit=0", "limit=101", "limit=1.5", "unknown=x", "cursor=not-json"]) {
    const response = await request(app()).get(`/api/v1/datasets?${query}`).expect(400);
    assert.equal(response.body.error.code, "VALIDATION_ERROR");
  }
  await request(app()).get("/api/v1/datasets/missing").expect(400);

  const failed: CatalogReadStore = {
    async listInstruments() { throw new Error("database secret"); },
    async listDatasets() { throw new Error("database secret"); },
    async listCandidateReports() { throw new Error("database secret"); },
    async getInstrument() { throw new Error("database secret"); },
    async getDataset() { throw new Error("database secret"); },
    async getCandidateReport() { throw new Error("database secret"); },
  };
  const unavailable = await request(app(failed)).get("/api/v1/datasets").expect(503);
  assert.deepEqual(unavailable.body.error, {
    code: "CATALOG_UNAVAILABLE",
    message: "The research catalog is unavailable.",
    retryable: true,
  });
  assert.equal(unavailable.text.includes("database secret"), false);

  const disabled = await request(app(catalog, "production")).get("/api/v1/datasets").expect(503);
  assert.equal(disabled.body.error.code, "CATALOG_API_DISABLED");
});
