import type { Pool, PoolClient, QueryResult } from "pg";

export interface QueryExecutor {
  query<R extends Record<string, unknown>>(text: string, values?: readonly unknown[]): Promise<QueryResult<R>>;
}

export interface InstrumentCatalogRecord {
  readonly symbol: string;
  readonly baseCurrency: string;
  readonly quoteCurrency: string;
  readonly pipSize: string;
  readonly pricePrecision: number;
}

export interface VerifiedDatasetCatalogRecord {
  readonly datasetId: string;
  readonly canonicalChecksum: string;
  readonly instrumentSymbol: string;
  readonly provider: string;
  readonly timeframe: string;
  readonly firstCandleOpen: Date;
  readonly lastCandleOpen: Date;
  readonly rowCount: string;
  readonly schemaVersion: string;
  readonly artifactKey: string;
  readonly isSynthetic: boolean;
  readonly integrityVerifiedAt: Date;
}

export interface VerifiedCandidateReportCatalogRecord {
  readonly reportId: string;
  readonly datasetId: string;
  readonly strategyName: string;
  readonly strategyVersion: string;
  readonly configurationFingerprint: string;
  readonly schemaVersion: string;
  readonly signalCount: number;
  readonly artifactKey: string;
  readonly integrityVerifiedAt: Date;
}

export class CatalogRepository {
  readonly #database: QueryExecutor;

  public constructor(database: Pool | PoolClient | QueryExecutor) {
    this.#database = database;
  }

  public async insertInstrument(record: InstrumentCatalogRecord): Promise<void> {
    await this.#database.query(
      `INSERT INTO instruments
        (symbol, base_currency, quote_currency, pip_size, price_precision)
       VALUES ($1, $2, $3, $4, $5)`,
      [record.symbol, record.baseCurrency, record.quoteCurrency, record.pipSize, record.pricePrecision],
    );
  }

  public async insertInstrumentIfAbsent(record: InstrumentCatalogRecord): Promise<boolean> {
    const result = await this.#database.query(
      `INSERT INTO instruments
        (symbol, base_currency, quote_currency, pip_size, price_precision)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (symbol) DO NOTHING
       RETURNING symbol`,
      [record.symbol, record.baseCurrency, record.quoteCurrency, record.pipSize, record.pricePrecision],
    );
    return (result.rowCount ?? 0) === 1;
  }

  public async insertVerifiedDataset(record: VerifiedDatasetCatalogRecord): Promise<void> {
    await this.#database.query(
      `INSERT INTO datasets
        (dataset_id, canonical_checksum, instrument_symbol, provider, timeframe,
         first_candle_open, last_candle_open, row_count, schema_version,
         artifact_key, is_synthetic, integrity_verified_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`,
      [
        record.datasetId, record.canonicalChecksum, record.instrumentSymbol,
        record.provider, record.timeframe, record.firstCandleOpen,
        record.lastCandleOpen, record.rowCount, record.schemaVersion,
        record.artifactKey, record.isSynthetic, record.integrityVerifiedAt,
      ],
    );
  }

  public async insertVerifiedDatasetIfAbsent(
    record: VerifiedDatasetCatalogRecord,
  ): Promise<boolean> {
    const result = await this.#database.query(
      `INSERT INTO datasets
        (dataset_id, canonical_checksum, instrument_symbol, provider, timeframe,
         first_candle_open, last_candle_open, row_count, schema_version,
         artifact_key, is_synthetic, integrity_verified_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
       ON CONFLICT (dataset_id) DO NOTHING
       RETURNING dataset_id`,
      [
        record.datasetId, record.canonicalChecksum, record.instrumentSymbol,
        record.provider, record.timeframe, record.firstCandleOpen,
        record.lastCandleOpen, record.rowCount, record.schemaVersion,
        record.artifactKey, record.isSynthetic, record.integrityVerifiedAt,
      ],
    );
    return (result.rowCount ?? 0) === 1;
  }

  public async insertVerifiedCandidateReport(record: VerifiedCandidateReportCatalogRecord): Promise<void> {
    await this.#database.query(
      `INSERT INTO candidate_reports
        (report_id, dataset_id, strategy_name, strategy_version,
         configuration_fingerprint, schema_version, signal_count,
         artifact_key, integrity_verified_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [
        record.reportId, record.datasetId, record.strategyName,
        record.strategyVersion, record.configurationFingerprint,
        record.schemaVersion, record.signalCount, record.artifactKey,
        record.integrityVerifiedAt,
      ],
    );
  }

  public async insertVerifiedCandidateReportIfAbsent(
    record: VerifiedCandidateReportCatalogRecord,
  ): Promise<boolean> {
    const result = await this.#database.query(
      `INSERT INTO candidate_reports
        (report_id, dataset_id, strategy_name, strategy_version,
         configuration_fingerprint, schema_version, signal_count,
         artifact_key, integrity_verified_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
       ON CONFLICT (report_id) DO NOTHING
       RETURNING report_id`,
      [
        record.reportId, record.datasetId, record.strategyName,
        record.strategyVersion, record.configurationFingerprint,
        record.schemaVersion, record.signalCount, record.artifactKey,
        record.integrityVerifiedAt,
      ],
    );
    return (result.rowCount ?? 0) === 1;
  }

  public async findInstrument(symbol: string): Promise<InstrumentCatalogRecord | undefined> {
    const result = await this.#database.query<{
      symbol: string; base_currency: string; quote_currency: string;
      pip_size: string; price_precision: number;
    }>(
      `SELECT symbol, base_currency, quote_currency, pip_size, price_precision
         FROM instruments WHERE symbol = $1`,
      [symbol],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      symbol: row.symbol,
      baseCurrency: row.base_currency,
      quoteCurrency: row.quote_currency,
      pipSize: row.pip_size,
      pricePrecision: row.price_precision,
    };
  }

  public async findDataset(datasetId: string): Promise<VerifiedDatasetCatalogRecord | undefined> {
    const result = await this.#database.query<{
      dataset_id: string;
      canonical_checksum: string;
      instrument_symbol: string;
      provider: string;
      timeframe: string;
      first_candle_open: Date;
      last_candle_open: Date;
      row_count: string;
      schema_version: string;
      artifact_key: string;
      is_synthetic: boolean;
      integrity_verified_at: Date;
    }>(
      `SELECT dataset_id, canonical_checksum, instrument_symbol, provider,
              timeframe, first_candle_open, last_candle_open, row_count,
              schema_version, artifact_key, is_synthetic, integrity_verified_at
         FROM datasets WHERE dataset_id = $1`,
      [datasetId],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      datasetId: row.dataset_id,
      canonicalChecksum: row.canonical_checksum,
      instrumentSymbol: row.instrument_symbol,
      provider: row.provider,
      timeframe: row.timeframe,
      firstCandleOpen: row.first_candle_open,
      lastCandleOpen: row.last_candle_open,
      rowCount: row.row_count,
      schemaVersion: row.schema_version,
      artifactKey: row.artifact_key,
      isSynthetic: row.is_synthetic,
      integrityVerifiedAt: row.integrity_verified_at,
    };
  }

  public async findCandidateReport(
    reportId: string,
  ): Promise<VerifiedCandidateReportCatalogRecord | undefined> {
    const result = await this.#database.query<{
      report_id: string; dataset_id: string; strategy_name: string;
      strategy_version: string; configuration_fingerprint: string;
      schema_version: string; signal_count: number; artifact_key: string;
      integrity_verified_at: Date;
    }>(
      `SELECT report_id, dataset_id, strategy_name, strategy_version,
              configuration_fingerprint, schema_version, signal_count,
              artifact_key, integrity_verified_at
         FROM candidate_reports WHERE report_id = $1`,
      [reportId],
    );
    const row = result.rows[0];
    return row === undefined ? undefined : {
      reportId: row.report_id,
      datasetId: row.dataset_id,
      strategyName: row.strategy_name,
      strategyVersion: row.strategy_version,
      configurationFingerprint: row.configuration_fingerprint,
      schemaVersion: row.schema_version,
      signalCount: row.signal_count,
      artifactKey: row.artifact_key,
      integrityVerifiedAt: row.integrity_verified_at,
    };
  }
}
