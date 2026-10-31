import { randomUUID } from "node:crypto";
import type { Pool, PoolClient } from "pg";
import type { ResearchJobRequest } from "./contracts.js";
import { requestFingerprint } from "./contracts.js";
import { ResearchJobError } from "./errors.js";
import type { ClaimedResearchJob, ResearchJob, ResearchJobState } from "./models.js";

interface JobRow {
  job_id: string; owner_subject: string; dataset_id: string; instrument_symbol: string;
  timeframe: string; strategy_name: string; strategy_version: string; state: ResearchJobState;
  attempt_count: number; max_attempts: number; lease_token: string | null;
  lease_expires_at: Date | null; error_code: string | null; created_at: Date; updated_at: Date;
  started_at: Date | null; completed_at: Date | null; request_fingerprint: string;
  result_report_id: string | null;
  implementation_revision: string;
}

function job(row: JobRow): ResearchJob {
  return {
    jobId: row.job_id, ownerSubject: row.owner_subject, datasetId: row.dataset_id,
    instrument: row.instrument_symbol, timeframe: row.timeframe,
    strategyName: row.strategy_name, strategyVersion: row.strategy_version,
    state: row.state, attemptCount: row.attempt_count, maxAttempts: row.max_attempts,
    leaseExpiresAt: row.lease_expires_at, errorCode: row.error_code,
    createdAt: row.created_at, updatedAt: row.updated_at,
    startedAt: row.started_at, completedAt: row.completed_at,
    resultReportId: row.result_report_id,
    implementationRevision: row.implementation_revision,
  };
}

const SELECT = `SELECT job_id, owner_subject, dataset_id, instrument_symbol, timeframe,
 strategy_name, strategy_version, state, attempt_count, max_attempts, lease_token,
 lease_expires_at, error_code, created_at, updated_at, started_at, completed_at, result_report_id,
 implementation_revision,
 request_fingerprint FROM research_jobs`;

export interface QueueLimits {
  readonly maxActivePerOwner: number;
  readonly maxQueueDepth: number;
  readonly maxAttempts: number;
  readonly leaseMs: number;
  readonly implementationRevision: string;
}
export interface ResearchJobStore {
  submit(owner: string, request: ResearchJobRequest): Promise<{ job: ResearchJob; created: boolean }>;
  list(owner: string, isAdmin: boolean, limit?: number): Promise<readonly ResearchJob[]>;
  get(jobId: string, owner: string, isAdmin: boolean): Promise<ResearchJob | undefined>;
}

export class ResearchJobRepository implements ResearchJobStore {
  public constructor(private readonly pool: Pool, private readonly limits: QueueLimits) {}

  public async submit(owner: string, request: ResearchJobRequest): Promise<{ job: ResearchJob; created: boolean }> {
    const client = await this.pool.connect();
    const fingerprint = requestFingerprint(request);
    try {
      await client.query("BEGIN");
      await client.query("SELECT pg_advisory_xact_lock(hashtext('tradepilot-research-job-submit'))");
      const existing = await client.query<JobRow>(`${SELECT} WHERE owner_subject = $1 AND idempotency_key = $2 FOR UPDATE`, [owner, request.idempotencyKey]);
      const prior = existing.rows[0];
      if (prior !== undefined) {
        if (prior.request_fingerprint !== fingerprint) throw new ResearchJobError("IDEMPOTENCY_CONFLICT", "The idempotency key is already bound to a different request.");
        await client.query("COMMIT");
        return { job: job(prior), created: false };
      }
      const dataset = await client.query<{ instrument_symbol: string; timeframe: string }>(
        "SELECT instrument_symbol, timeframe FROM datasets WHERE dataset_id = $1", [request.datasetId],
      );
      const verified = dataset.rows[0];
      if (verified === undefined) throw new ResearchJobError("DATASET_NOT_VERIFIED", "The dataset is not present in the verified catalog.");
      if (verified.instrument_symbol !== request.instrument || verified.timeframe !== request.timeframe) {
        throw new ResearchJobError("DATASET_PROVENANCE_MISMATCH", "The request does not match verified dataset provenance.");
      }
      const active = await client.query<{ count: string }>(
        "SELECT count(*)::text AS count FROM research_jobs WHERE owner_subject = $1 AND state IN ('QUEUED','RUNNING')", [owner],
      );
      if (Number(active.rows[0]?.count ?? "0") >= this.limits.maxActivePerOwner) {
        throw new ResearchJobError("ACTIVE_JOB_LIMIT", "The active research-job limit has been reached.", true);
      }
      const depth = await client.query<{ count: string }>(
        "SELECT count(*)::text AS count FROM research_jobs WHERE state IN ('QUEUED','RUNNING')",
      );
      if (Number(depth.rows[0]?.count ?? "0") >= this.limits.maxQueueDepth) {
        throw new ResearchJobError("QUEUE_FULL", "The research-job queue is full.", true);
      }
      const jobId = randomUUID();
      const inserted = await client.query<JobRow>(
        `INSERT INTO research_jobs
         (job_id, owner_subject, idempotency_key, request_version, request_fingerprint,
          dataset_id, instrument_symbol, timeframe, strategy_name, strategy_version, max_attempts,
          implementation_revision)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *, request_fingerprint`,
        [jobId, owner, request.idempotencyKey, request.contractVersion, fingerprint,
          request.datasetId, request.instrument, request.timeframe, request.strategy.name,
          request.strategy.version, this.limits.maxAttempts, this.limits.implementationRevision],
      );
      await client.query(
        "INSERT INTO research_job_events (job_id,event_type,from_state,to_state,attempt) VALUES ($1,'SUBMITTED',NULL,'QUEUED',0)", [jobId],
      );
      await client.query("COMMIT");
      return { job: job(inserted.rows[0]!), created: true };
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally { client.release(); }
  }

  public async list(owner: string, isAdmin: boolean, limit = 100): Promise<readonly ResearchJob[]> {
    const result = isAdmin
      ? await this.pool.query<JobRow>(`${SELECT} ORDER BY created_at DESC, job_id DESC LIMIT $1`, [limit])
      : await this.pool.query<JobRow>(`${SELECT} WHERE owner_subject=$1 ORDER BY created_at DESC, job_id DESC LIMIT $2`, [owner, limit]);
    return result.rows.map(job);
  }

  public async get(jobId: string, owner: string, isAdmin: boolean): Promise<ResearchJob | undefined> {
    const result = isAdmin
      ? await this.pool.query<JobRow>(`${SELECT} WHERE job_id=$1`, [jobId])
      : await this.pool.query<JobRow>(`${SELECT} WHERE job_id=$1 AND owner_subject=$2`, [jobId, owner]);
    const row = result.rows[0];
    return row === undefined ? undefined : job(row);
  }

  public async claim(): Promise<ClaimedResearchJob | undefined> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const selected = await client.query<JobRow>(
        `${SELECT} WHERE state='QUEUED' OR (state='RUNNING' AND lease_expires_at <= now())
          ORDER BY CASE WHEN state='RUNNING' THEN 0 ELSE 1 END, created_at, job_id
          FOR UPDATE SKIP LOCKED LIMIT 1`,
      );
      const row = selected.rows[0];
      if (row === undefined) { await client.query("COMMIT"); return undefined; }
      if (row.state === "RUNNING") {
        await this.event(client, row.job_id, "LEASE_RECOVERED", "RUNNING", "QUEUED", row.attempt_count, "LEASE_EXPIRED");
        if (row.attempt_count >= row.max_attempts) {
          await client.query(
            "UPDATE research_jobs SET state='FAILED',lease_token=NULL,lease_expires_at=NULL,error_code='RETRY_EXHAUSTED',completed_at=now(),updated_at=now() WHERE job_id=$1", [row.job_id],
          );
          await this.event(client, row.job_id, "FAILED", "QUEUED", "FAILED", row.attempt_count, "RETRY_EXHAUSTED");
          await client.query("COMMIT");
          return undefined;
        }
      }
      const leaseToken = randomUUID();
      const updated = await client.query<JobRow>(
        `UPDATE research_jobs SET state='RUNNING',attempt_count=attempt_count+1,
         lease_token=$2,lease_expires_at=now()+($3::text || ' milliseconds')::interval,
         error_code=NULL,started_at=coalesce(started_at,now()),updated_at=now()
         WHERE job_id=$1 RETURNING *, request_fingerprint`,
        [row.job_id, leaseToken, this.limits.leaseMs],
      );
      const claimed = updated.rows[0]!;
      await this.event(client, row.job_id, "CLAIMED", row.state === "RUNNING" ? "QUEUED" : "QUEUED", "RUNNING", claimed.attempt_count, null);
      await client.query("COMMIT");
      return { ...job(claimed), state: "RUNNING", leaseToken, leaseExpiresAt: claimed.lease_expires_at! };
    } catch (error) { await client.query("ROLLBACK"); throw error; } finally { client.release(); }
  }

  public async renew(jobId: string, leaseToken: string): Promise<void> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const result = await client.query<{ attempt_count: number }>(
        `UPDATE research_jobs SET lease_expires_at=now()+($3::text || ' milliseconds')::interval,
         updated_at=now() WHERE job_id=$1 AND state='RUNNING' AND lease_token=$2
         AND lease_expires_at > now() RETURNING attempt_count`,
        [jobId, leaseToken, this.limits.leaseMs],
      );
      if (result.rowCount !== 1) throw new ResearchJobError("LEASE_LOST", "The job lease is no longer valid.");
      await this.event(client, jobId, "LEASE_RENEWED", "RUNNING", "RUNNING", result.rows[0]!.attempt_count, null);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally { client.release(); }
  }

  public async succeed(jobId: string, leaseToken: string, reportId: string): Promise<void> {
    if (!/^[0-9a-f]{64}$/u.test(reportId)) throw new ResearchJobError("INVALID_REPORT_ID", "Result report ID is invalid.");
    await this.transition(jobId, leaseToken, false, null, reportId);
  }

  public async fail(jobId: string, leaseToken: string, errorCode: string, retryable: boolean): Promise<void> {
    if (!/^[A-Z][A-Z0-9_]{1,99}$/u.test(errorCode)) throw new ResearchJobError("INVALID_ERROR_CODE", "Worker error code is invalid.");
    await this.transition(jobId, leaseToken, retryable, errorCode, null);
  }

  private async transition(jobId: string, leaseToken: string, retryable: boolean, errorCode: string | null, reportId: string | null): Promise<void> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const current = await client.query<JobRow>(`${SELECT} WHERE job_id=$1 FOR UPDATE`, [jobId]);
      const row = current.rows[0];
      if (row === undefined || row.state !== "RUNNING" || row.lease_token !== leaseToken
        || row.lease_expires_at === null || row.lease_expires_at.getTime() <= Date.now()) {
        throw new ResearchJobError("INVALID_JOB_TRANSITION", "The job lease is no longer valid.");
      }
      const requeue = errorCode !== null && retryable && row.attempt_count < row.max_attempts;
      const state: ResearchJobState = errorCode === null ? "SUCCEEDED" : requeue ? "QUEUED" : "FAILED";
      await client.query(
        `UPDATE research_jobs SET state=$2,lease_token=NULL,lease_expires_at=NULL,error_code=$3,result_report_id=$4,
         completed_at=CASE WHEN $2 IN ('SUCCEEDED','FAILED') THEN now() ELSE NULL END,updated_at=now()
         WHERE job_id=$1`, [jobId, state, errorCode, reportId],
      );
      await this.event(client, jobId, errorCode === null ? "SUCCEEDED" : requeue ? "REQUEUED" : "FAILED",
        "RUNNING", state, row.attempt_count, errorCode);
      await client.query("COMMIT");
    } catch (error) { await client.query("ROLLBACK"); throw error; } finally { client.release(); }
  }

  private async event(client: PoolClient, jobId: string, type: string, from: ResearchJobState | null,
    to: ResearchJobState, attempt: number, errorCode: string | null): Promise<void> {
    await client.query(
      "INSERT INTO research_job_events (job_id,event_type,from_state,to_state,attempt,error_code) VALUES ($1,$2,$3,$4,$5,$6)",
      [jobId, type, from, to, attempt, errorCode],
    );
  }
}

