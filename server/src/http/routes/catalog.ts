import { Router, type Request } from "express";
import type { AppConfig } from "../../config/env.js";
import type {
  CandidateReportCatalogView,
  CatalogReadStore,
  DatasetCatalogView,
  InstrumentCatalogView,
} from "../../database/catalog-read-repository.js";
import { successEnvelope } from "../contracts/envelope.js";
import { ApiError } from "../errors/api-error.js";
import { encodeCursor, parsePageQuery, type CursorKind } from "../pagination/cursor.js";

interface CatalogPage<T> {
  readonly items: readonly T[];
  readonly nextCursor: string | null;
  readonly historicalOnly: true;
}

const SHA256 = /^[0-9a-f]{64}$/u;
const SYMBOL = /^[A-Z]{6,12}$/u;

function instrumentItem(item: InstrumentCatalogView) {
  return {
    symbol: item.symbol, baseCurrency: item.baseCurrency, quoteCurrency: item.quoteCurrency,
    pipSize: item.pipSize, pricePrecision: item.pricePrecision,
    verifiedAt: item.verifiedAt.toISOString(), classification: "FOREX_INSTRUMENT" as const,
  };
}

function datasetItem(item: DatasetCatalogView) {
  return {
    datasetId: item.datasetId, canonicalChecksum: item.canonicalChecksum,
    instrument: item.instrument, provider: item.provider, timeframe: item.timeframe,
    firstCandleOpen: item.firstCandleOpen.toISOString(), lastCandleOpen: item.lastCandleOpen.toISOString(),
    rowCount: item.rowCount, schemaVersion: item.schemaVersion, verifiedAt: item.verifiedAt.toISOString(),
    dataClassification: "HISTORICAL" as const,
    sourceClassification: item.isSynthetic ? "SYNTHETIC" as const : "MARKET_DATA" as const,
  };
}

function reportItem(item: CandidateReportCatalogView) {
  return {
    reportId: item.reportId, datasetId: item.datasetId, strategyName: item.strategyName,
    strategyVersion: item.strategyVersion, configurationFingerprint: item.configurationFingerprint,
    schemaVersion: item.schemaVersion, signalCount: item.signalCount,
    verifiedAt: item.verifiedAt.toISOString(), classification: "HISTORICAL_RESEARCH_CANDIDATES" as const,
    sourceClassification: item.datasetIsSynthetic ? "SYNTHETIC" as const : "MARKET_DATA" as const,
    liveSignal: false as const,
  };
}

async function detail<T>(load: () => Promise<T | undefined>, label: string): Promise<T> {
  let item: T | undefined;
  try { item = await load(); } catch {
    throw new ApiError(503, "CATALOG_UNAVAILABLE", "The research catalog is unavailable.", true);
  }
  if (item === undefined) throw new ApiError(404, "RESOURCE_NOT_FOUND", `${label} was not found.`);
  return item;
}

function requireLocalCatalog(config: AppConfig): void {
  if (config.nodeEnv === "production") {
    throw new ApiError(
      503, "CATALOG_API_DISABLED",
      "Catalog APIs are disabled until authorization is implemented.", false,
    );
  }
}

async function page<T>(
  req: Request,
  kind: CursorKind,
  load: (after: string | undefined, limit: number) => Promise<readonly T[]>,
  cursorKey: (item: T) => string,
): Promise<CatalogPage<T>> {
  const query = parsePageQuery(req.query, kind);
  let rows: readonly T[];
  try {
    rows = await load(query.after, query.limit);
  } catch {
    throw new ApiError(503, "CATALOG_UNAVAILABLE", "The research catalog is unavailable.", true);
  }
  const hasMore = rows.length > query.limit;
  const items = hasMore ? rows.slice(0, query.limit) : rows;
  const last = items.at(-1);
  return {
    items,
    nextCursor: hasMore && last !== undefined ? encodeCursor(kind, cursorKey(last)) : null,
    historicalOnly: true,
  };
}

export function catalogRouter(config: AppConfig, catalog: CatalogReadStore): Router {
  const router = Router();
  router.use((_req, _res, next) => {
    try { requireLocalCatalog(config); next(); } catch (error) { next(error); }
  });

  router.get("/instruments", async (req, res) => {
    const result = await page(req, "instruments",
      (after, limit) => catalog.listInstruments({ after, limit }), (item) => item.symbol);
    res.json(successEnvelope(req.requestId, {
      ...result,
      items: result.items.map(instrumentItem),
    }));
  });

  router.get("/datasets", async (req, res) => {
    const result = await page(req, "datasets",
      (after, limit) => catalog.listDatasets({ after, limit }), (item) => item.datasetId);
    res.json(successEnvelope(req.requestId, {
      ...result,
      items: result.items.map(datasetItem),
    }));
  });

  router.get("/candidate-reports", async (req, res) => {
    const result = await page(req, "candidate-reports",
      (after, limit) => catalog.listCandidateReports({ after, limit }), (item) => item.reportId);
    res.json(successEnvelope(req.requestId, {
      ...result,
      items: result.items.map(reportItem),
    }));
  });

  router.get("/instruments/:symbol", async (req, res) => {
    const symbol = req.params["symbol"];
    if (symbol === undefined || !SYMBOL.test(symbol)) throw new ApiError(400, "VALIDATION_ERROR", "symbol is invalid.");
    res.json(successEnvelope(req.requestId, instrumentItem(await detail(() => catalog.getInstrument(symbol), "Instrument"))));
  });

  router.get("/datasets/:datasetId", async (req, res) => {
    const datasetId = req.params["datasetId"];
    if (datasetId === undefined || !SHA256.test(datasetId)) throw new ApiError(400, "VALIDATION_ERROR", "datasetId is invalid.");
    res.json(successEnvelope(req.requestId, datasetItem(await detail(() => catalog.getDataset(datasetId), "Dataset"))));
  });

  router.get("/candidate-reports/:reportId", async (req, res) => {
    const reportId = req.params["reportId"];
    if (reportId === undefined || !SHA256.test(reportId)) throw new ApiError(400, "VALIDATION_ERROR", "reportId is invalid.");
    res.json(successEnvelope(req.requestId, reportItem(await detail(() => catalog.getCandidateReport(reportId), "Candidate report"))));
  });

  return router;
}
