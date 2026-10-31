import type { QueryExecutor } from "./catalog-repository.js";

export interface CatalogPageRequest {
  readonly after: string | undefined;
  readonly limit: number;
}

export interface InstrumentCatalogView {
  readonly symbol: string;
  readonly baseCurrency: string;
  readonly quoteCurrency: string;
  readonly pipSize: string;
  readonly pricePrecision: number;
  readonly verifiedAt: Date;
}

export interface DatasetCatalogView {
  readonly datasetId: string;
  readonly canonicalChecksum: string;
  readonly instrument: string;
  readonly provider: string;
  readonly timeframe: string;
  readonly firstCandleOpen: Date;
  readonly lastCandleOpen: Date;
  readonly rowCount: string;
  readonly schemaVersion: string;
  readonly isSynthetic: boolean;
  readonly verifiedAt: Date;
}

export interface CandidateReportCatalogView {
  readonly reportId: string;
  readonly datasetId: string;
  readonly strategyName: string;
  readonly strategyVersion: string;
  readonly configurationFingerprint: string;
  readonly schemaVersion: string;
  readonly signalCount: number;
  readonly datasetIsSynthetic: boolean;
  readonly verifiedAt: Date;
}

export interface CatalogReadStore {
  listInstruments(request: CatalogPageRequest): Promise<readonly InstrumentCatalogView[]>;
  listDatasets(request: CatalogPageRequest): Promise<readonly DatasetCatalogView[]>;
  listCandidateReports(request: CatalogPageRequest): Promise<readonly CandidateReportCatalogView[]>;
  getInstrument(symbol: string): Promise<InstrumentCatalogView | undefined>;
  getDataset(datasetId: string): Promise<DatasetCatalogView | undefined>;
  getCandidateReport(reportId: string): Promise<CandidateReportCatalogView | undefined>;
}

export class PostgresCatalogReader implements CatalogReadStore {
  public constructor(private readonly database: QueryExecutor) {}

  public async listInstruments(
    request: CatalogPageRequest,
  ): Promise<readonly InstrumentCatalogView[]> {
    const result = await this.database.query<{
      symbol: string; base_currency: string; quote_currency: string;
      pip_size: string; price_precision: number; verified_at: Date;
    }>(
      `SELECT i.symbol, i.base_currency, i.quote_currency, i.pip_size,
              i.price_precision, max(d.integrity_verified_at) AS verified_at
         FROM instruments i
         JOIN datasets d ON d.instrument_symbol = i.symbol
        WHERE ($1::text IS NULL OR i.symbol > $1)
        GROUP BY i.symbol, i.base_currency, i.quote_currency, i.pip_size, i.price_precision
        ORDER BY i.symbol ASC
        LIMIT $2`,
      [request.after ?? null, request.limit + 1],
    );
    return result.rows.map((row) => ({
      symbol: row.symbol,
      baseCurrency: row.base_currency,
      quoteCurrency: row.quote_currency,
      pipSize: row.pip_size,
      pricePrecision: row.price_precision,
      verifiedAt: row.verified_at,
    }));
  }

  public async listDatasets(request: CatalogPageRequest): Promise<readonly DatasetCatalogView[]> {
    const result = await this.database.query<{
      dataset_id: string; canonical_checksum: string; instrument_symbol: string;
      provider: string; timeframe: string; first_candle_open: Date;
      last_candle_open: Date; row_count: string; schema_version: string;
      is_synthetic: boolean; integrity_verified_at: Date;
    }>(
      `SELECT dataset_id, canonical_checksum, instrument_symbol, provider, timeframe,
              first_candle_open, last_candle_open, row_count, schema_version,
              is_synthetic, integrity_verified_at
         FROM datasets
        WHERE ($1::text IS NULL OR dataset_id > $1)
        ORDER BY dataset_id ASC
        LIMIT $2`,
      [request.after ?? null, request.limit + 1],
    );
    return result.rows.map((row) => ({
      datasetId: row.dataset_id,
      canonicalChecksum: row.canonical_checksum,
      instrument: row.instrument_symbol,
      provider: row.provider,
      timeframe: row.timeframe,
      firstCandleOpen: row.first_candle_open,
      lastCandleOpen: row.last_candle_open,
      rowCount: row.row_count,
      schemaVersion: row.schema_version,
      isSynthetic: row.is_synthetic,
      verifiedAt: row.integrity_verified_at,
    }));
  }

  public async listCandidateReports(
    request: CatalogPageRequest,
  ): Promise<readonly CandidateReportCatalogView[]> {
    const result = await this.database.query<{
      report_id: string; dataset_id: string; strategy_name: string;
      strategy_version: string; configuration_fingerprint: string;
      schema_version: string; signal_count: number; is_synthetic: boolean;
      integrity_verified_at: Date;
    }>(
      `SELECT r.report_id, r.dataset_id, r.strategy_name, r.strategy_version,
              r.configuration_fingerprint, r.schema_version, r.signal_count,
              d.is_synthetic, r.integrity_verified_at
         FROM candidate_reports r
         JOIN datasets d ON d.dataset_id = r.dataset_id
        WHERE ($1::text IS NULL OR r.report_id > $1)
        ORDER BY r.report_id ASC
        LIMIT $2`,
      [request.after ?? null, request.limit + 1],
    );
    return result.rows.map((row) => ({
      reportId: row.report_id,
      datasetId: row.dataset_id,
      strategyName: row.strategy_name,
      strategyVersion: row.strategy_version,
      configurationFingerprint: row.configuration_fingerprint,
      schemaVersion: row.schema_version,
      signalCount: row.signal_count,
      datasetIsSynthetic: row.is_synthetic,
      verifiedAt: row.integrity_verified_at,
    }));
  }

  public async getInstrument(symbol: string): Promise<InstrumentCatalogView | undefined> {
    const result = await this.database.query<{
      symbol: string; base_currency: string; quote_currency: string;
      pip_size: string; price_precision: number; verified_at: Date;
    }>(
      `SELECT i.symbol, i.base_currency, i.quote_currency, i.pip_size,
              i.price_precision, max(d.integrity_verified_at) AS verified_at
         FROM instruments i JOIN datasets d ON d.instrument_symbol = i.symbol
        WHERE i.symbol = $1
        GROUP BY i.symbol, i.base_currency, i.quote_currency, i.pip_size, i.price_precision`,
      [symbol],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      symbol: row.symbol, baseCurrency: row.base_currency, quoteCurrency: row.quote_currency,
      pipSize: row.pip_size, pricePrecision: row.price_precision, verifiedAt: row.verified_at,
    };
  }

  public async getDataset(datasetId: string): Promise<DatasetCatalogView | undefined> {
    const result = await this.database.query<{
      dataset_id: string; canonical_checksum: string; instrument_symbol: string;
      provider: string; timeframe: string; first_candle_open: Date;
      last_candle_open: Date; row_count: string; schema_version: string;
      is_synthetic: boolean; integrity_verified_at: Date;
    }>(
      `SELECT dataset_id, canonical_checksum, instrument_symbol, provider, timeframe,
              first_candle_open, last_candle_open, row_count, schema_version,
              is_synthetic, integrity_verified_at
         FROM datasets WHERE dataset_id = $1`,
      [datasetId],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      datasetId: row.dataset_id, canonicalChecksum: row.canonical_checksum,
      instrument: row.instrument_symbol, provider: row.provider, timeframe: row.timeframe,
      firstCandleOpen: row.first_candle_open, lastCandleOpen: row.last_candle_open,
      rowCount: row.row_count, schemaVersion: row.schema_version,
      isSynthetic: row.is_synthetic, verifiedAt: row.integrity_verified_at,
    };
  }

  public async getCandidateReport(reportId: string): Promise<CandidateReportCatalogView | undefined> {
    const result = await this.database.query<{
      report_id: string; dataset_id: string; strategy_name: string; strategy_version: string;
      configuration_fingerprint: string; schema_version: string; signal_count: number;
      is_synthetic: boolean; integrity_verified_at: Date;
    }>(
      `SELECT r.report_id, r.dataset_id, r.strategy_name, r.strategy_version,
              r.configuration_fingerprint, r.schema_version, r.signal_count,
              d.is_synthetic, r.integrity_verified_at
         FROM candidate_reports r JOIN datasets d ON d.dataset_id = r.dataset_id
        WHERE r.report_id = $1`,
      [reportId],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      reportId: row.report_id, datasetId: row.dataset_id,
      strategyName: row.strategy_name, strategyVersion: row.strategy_version,
      configurationFingerprint: row.configuration_fingerprint,
      schemaVersion: row.schema_version, signalCount: row.signal_count,
      datasetIsSynthetic: row.is_synthetic, verifiedAt: row.integrity_verified_at,
    };
  }
}
