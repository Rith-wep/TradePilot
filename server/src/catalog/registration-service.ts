import { randomUUID } from "node:crypto";
import type { Pool, PoolClient } from "pg";
import {
  CatalogRepository,
  type InstrumentCatalogRecord,
  type VerifiedCandidateReportCatalogRecord,
  type VerifiedDatasetCatalogRecord,
} from "../database/catalog-repository.js";
import {
  ARTIFACT_CONTRACT_VERSION,
  type ArtifactVerificationRequest,
  type DatasetArtifactReference,
  type VerifiedArtifactResponse,
} from "../verification/contracts.js";
import { ArtifactVerificationError } from "../verification/errors.js";
import type { ArtifactVerifierService } from "../verification/artifact-verifier.js";
import { CatalogRegistrationError } from "./errors.js";

const SHA256 = /^[0-9a-f]{64}$/u;
const CURRENCY = /^[A-Z]{3}$/u;
const DECIMAL = /^(0|[1-9][0-9]*)(\.[0-9]+)?$/u;

export interface DatasetRegistrationRequest extends DatasetArtifactReference {}
export interface CandidateReportRegistrationRequest {
  readonly kind: "candidate_report";
  readonly artifact_id: string;
}
export interface CatalogRegistrationResult {
  readonly kind: "dataset" | "candidate_report";
  readonly artifactId: string;
  readonly disposition: "REGISTERED" | "EXISTING";
  readonly verifiedAt: Date;
}

function stringField(value: unknown, name: string, pattern?: RegExp): string {
  if (typeof value !== "string" || value.length === 0 || (pattern !== undefined && !pattern.test(value))) {
    throw new CatalogRegistrationError(
      "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
      `verified artifact metadata field ${name} is invalid`, false,
    );
  }
  return value;
}

function integerField(value: unknown, name: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) {
    throw new CatalogRegistrationError(
      "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
      `verified artifact metadata field ${name} is invalid`, false,
    );
  }
  return value;
}

function dateField(value: unknown, name: string): Date {
  const text = stringField(value, name);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/u.test(text)) {
    throw new CatalogRegistrationError(
      "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
      `verified artifact metadata field ${name} is invalid`, false,
    );
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    throw new CatalogRegistrationError(
      "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
      `verified artifact metadata field ${name} is invalid`, false,
    );
  }
  return parsed;
}

function sameInstrument(a: InstrumentCatalogRecord, b: InstrumentCatalogRecord): boolean {
  return a.symbol === b.symbol && a.baseCurrency === b.baseCurrency
    && a.quoteCurrency === b.quoteCurrency && a.pipSize === b.pipSize
    && a.pricePrecision === b.pricePrecision;
}

function sameDataset(a: VerifiedDatasetCatalogRecord, b: VerifiedDatasetCatalogRecord): boolean {
  return a.datasetId === b.datasetId && a.canonicalChecksum === b.canonicalChecksum
    && a.instrumentSymbol === b.instrumentSymbol && a.provider === b.provider
    && a.timeframe === b.timeframe && a.firstCandleOpen.getTime() === b.firstCandleOpen.getTime()
    && a.lastCandleOpen.getTime() === b.lastCandleOpen.getTime() && a.rowCount === b.rowCount
    && a.schemaVersion === b.schemaVersion && a.artifactKey === b.artifactKey
    && a.isSynthetic === b.isSynthetic;
}

function sameReport(
  a: VerifiedCandidateReportCatalogRecord,
  b: VerifiedCandidateReportCatalogRecord,
): boolean {
  return a.reportId === b.reportId && a.datasetId === b.datasetId
    && a.strategyName === b.strategyName && a.strategyVersion === b.strategyVersion
    && a.configurationFingerprint === b.configurationFingerprint
    && a.schemaVersion === b.schemaVersion && a.signalCount === b.signalCount
    && a.artifactKey === b.artifactKey;
}

export class CatalogRegistrationService {
  public constructor(
    private readonly verifier: ArtifactVerifierService,
    private readonly pool: Pool,
  ) {}

  public async registerDataset(request: DatasetRegistrationRequest): Promise<CatalogRegistrationResult> {
    const verifiedAt = new Date();
    const response = await this.verify({
      contract_version: ARTIFACT_CONTRACT_VERSION,
      request_id: `catalog-dataset-${randomUUID()}`,
      operation: "verify_artifact",
      artifact: request,
    });
    const metadata = response.verification;
    const datasetId = stringField(metadata["dataset_id"], "dataset_id", SHA256);
    const provider = stringField(metadata["provider"], "provider");
    const instrument = stringField(metadata["instrument"], "instrument", /^[A-Z]{6,12}$/u);
    const timeframe = stringField(metadata["timeframe"], "timeframe", /^[A-Z][A-Z0-9]{0,15}$/u);
    if (datasetId !== request.artifact_id || provider !== request.provider
      || instrument !== request.instrument || timeframe !== request.timeframe) {
      throw new CatalogRegistrationError(
        "PROVENANCE_MISMATCH", "VERIFIED_PROVENANCE_MISMATCH",
        "verified dataset provenance does not match its locator", false,
      );
    }
    const baseCurrency = stringField(metadata["base_currency"], "base_currency", CURRENCY);
    const quoteCurrency = stringField(metadata["quote_currency"], "quote_currency", CURRENCY);
    const pipSize = stringField(metadata["pip_size"], "pip_size", DECIMAL);
    const pricePrecision = integerField(metadata["price_precision"], "price_precision", 0);
    if (baseCurrency === quoteCurrency || instrument !== `${baseCurrency}${quoteCurrency}`) {
      throw new CatalogRegistrationError(
        "PROVENANCE_MISMATCH", "INSTRUMENT_PROVENANCE_MISMATCH",
        "verified instrument provenance is inconsistent", false,
      );
    }
    if (typeof metadata["is_synthetic"] !== "boolean") {
      throw new CatalogRegistrationError(
        "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
        "verified artifact metadata field is_synthetic is invalid", false,
      );
    }
    const first = dateField(metadata["first_timestamp"], "first_timestamp");
    const last = dateField(metadata["last_timestamp"], "last_timestamp");
    if (first.getTime() > last.getTime()) {
      throw new CatalogRegistrationError(
        "INVALID_VERIFIED_METADATA", "INVALID_VERIFIED_METADATA",
        "verified dataset timestamp range is invalid", false,
      );
    }
    const instrumentRecord: InstrumentCatalogRecord = {
      symbol: instrument, baseCurrency, quoteCurrency, pipSize, pricePrecision,
    };
    const datasetRecord: VerifiedDatasetCatalogRecord = {
      datasetId,
      canonicalChecksum: stringField(metadata["dataset_checksum"], "dataset_checksum", SHA256),
      instrumentSymbol: instrument,
      provider,
      timeframe,
      firstCandleOpen: first,
      lastCandleOpen: last,
      rowCount: String(integerField(metadata["row_count"], "row_count", 1)),
      schemaVersion: stringField(metadata["schema_version"], "schema_version"),
      artifactKey: `datasets/${provider}/${instrument}/${timeframe}/snapshots/${datasetId}`,
      isSynthetic: metadata["is_synthetic"],
      integrityVerifiedAt: verifiedAt,
    };
    const inserted = await this.transaction(async (repository) => {
      await repository.insertInstrumentIfAbsent(instrumentRecord);
      const storedInstrument = await repository.findInstrument(instrument);
      if (storedInstrument === undefined || !sameInstrument(storedInstrument, instrumentRecord)) {
        this.conflict("instrument");
      }
      const created = await repository.insertVerifiedDatasetIfAbsent(datasetRecord);
      const stored = await repository.findDataset(datasetId);
      if (stored === undefined || !sameDataset(stored, datasetRecord)) this.conflict("dataset");
      return created;
    });
    return { kind: "dataset", artifactId: datasetId, disposition: inserted ? "REGISTERED" : "EXISTING", verifiedAt };
  }

  public async registerCandidateReport(
    request: CandidateReportRegistrationRequest,
  ): Promise<CatalogRegistrationResult> {
    const verifiedAt = new Date();
    const response = await this.verify({
      contract_version: ARTIFACT_CONTRACT_VERSION,
      request_id: `catalog-report-${randomUUID()}`,
      operation: "verify_artifact",
      artifact: request,
    });
    const metadata = response.verification;
    const reportId = stringField(metadata["report_id"], "report_id", SHA256);
    if (reportId !== request.artifact_id) {
      throw new CatalogRegistrationError(
        "PROVENANCE_MISMATCH", "VERIFIED_PROVENANCE_MISMATCH",
        "verified report identity does not match its request", false,
      );
    }
    const datasetId = stringField(metadata["dataset_id"], "dataset_id", SHA256);
    const datasetChecksum = stringField(metadata["dataset_checksum"], "dataset_checksum", SHA256);
    const instrument = stringField(metadata["instrument"], "instrument", /^[A-Z]{6,12}$/u);
    const timeframe = stringField(metadata["timeframe"], "timeframe", /^[A-Z][A-Z0-9]{0,15}$/u);
    const record: VerifiedCandidateReportCatalogRecord = {
      reportId,
      datasetId,
      strategyName: stringField(metadata["strategy_name"], "strategy_name"),
      strategyVersion: stringField(metadata["strategy_version"], "strategy_version"),
      configurationFingerprint: stringField(
        metadata["configuration_fingerprint"], "configuration_fingerprint", SHA256,
      ),
      schemaVersion: stringField(metadata["schema_version"], "schema_version"),
      signalCount: integerField(metadata["signal_count"], "signal_count", 0),
      artifactKey: `candidate-reports/${reportId}`,
      integrityVerifiedAt: verifiedAt,
    };
    const inserted = await this.transaction(async (repository) => {
      const dataset = await repository.findDataset(datasetId);
      if (dataset === undefined) {
        throw new CatalogRegistrationError(
          "MISSING_DATASET", "VERIFIED_DATASET_REQUIRED",
          "the report dataset must be registered first", false,
        );
      }
      if (dataset.canonicalChecksum !== datasetChecksum
        || dataset.instrumentSymbol !== instrument || dataset.timeframe !== timeframe) {
        throw new CatalogRegistrationError(
          "PROVENANCE_MISMATCH", "DATASET_CHECKSUM_MISMATCH",
          "candidate report dataset provenance is inconsistent", false,
        );
      }
      const created = await repository.insertVerifiedCandidateReportIfAbsent(record);
      const stored = await repository.findCandidateReport(reportId);
      if (stored === undefined || !sameReport(stored, record)) this.conflict("candidate report");
      return created;
    });
    return {
      kind: "candidate_report", artifactId: reportId,
      disposition: inserted ? "REGISTERED" : "EXISTING", verifiedAt,
    };
  }

  private async verify(request: ArtifactVerificationRequest): Promise<VerifiedArtifactResponse> {
    try {
      return await this.verifier.verify(request);
    } catch (error) {
      if (error instanceof ArtifactVerificationError) {
        throw new CatalogRegistrationError(
          "VERIFICATION_FAILED", error.code, "artifact verification failed", error.retryable,
        );
      }
      throw error;
    }
  }

  private async transaction<T>(work: (repository: CatalogRepository) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const result = await work(new CatalogRepository(client));
      await client.query("COMMIT");
      return result;
    } catch (error) {
      await this.rollback(client);
      if (error instanceof CatalogRegistrationError) throw error;
      throw new CatalogRegistrationError(
        "DATABASE_FAILURE", "CATALOG_DATABASE_FAILURE", "catalog registration failed", true,
      );
    } finally {
      client.release();
    }
  }

  private async rollback(client: PoolClient): Promise<void> {
    try { await client.query("ROLLBACK"); } catch { /* original failure is authoritative */ }
  }

  private conflict(subject: string): never {
    throw new CatalogRegistrationError(
      "METADATA_CONFLICT", "IMMUTABLE_METADATA_CONFLICT",
      `existing ${subject} metadata conflicts with verified content`, false,
    );
  }
}
