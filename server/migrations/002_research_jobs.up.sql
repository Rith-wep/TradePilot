CREATE TABLE research_jobs (
  job_id uuid PRIMARY KEY,
  owner_subject varchar(200) NOT NULL,
  idempotency_key varchar(100) NOT NULL,
  request_version text NOT NULL,
  request_fingerprint char(64) NOT NULL,
  dataset_id char(64) NOT NULL REFERENCES datasets(dataset_id),
  instrument_symbol varchar(12) NOT NULL,
  timeframe text NOT NULL,
  strategy_name text NOT NULL,
  strategy_version text NOT NULL,
  state text NOT NULL DEFAULT 'QUEUED',
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL,
  lease_token uuid,
  lease_expires_at timestamptz,
  error_code varchar(100),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  UNIQUE (owner_subject, idempotency_key),
  CONSTRAINT research_jobs_owner CHECK (length(owner_subject) BETWEEN 1 AND 200),
  CONSTRAINT research_jobs_idempotency CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,100}$'),
  CONSTRAINT research_jobs_request_version CHECK (request_version = 'tradepilot-research-job-request/v1'),
  CONSTRAINT research_jobs_fingerprint CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT research_jobs_instrument CHECK (instrument_symbol IN ('EURUSD', 'GBPUSD')),
  CONSTRAINT research_jobs_timeframe CHECK (timeframe = 'H1'),
  CONSTRAINT research_jobs_strategy CHECK (
    (strategy_name = 'price_range_breakout' AND strategy_version = 'v1')
    OR (strategy_name = 'ema_rsi_trend_pullback' AND strategy_version = 'v1')
  ),
  CONSTRAINT research_jobs_state CHECK (state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
  CONSTRAINT research_jobs_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10 AND attempt_count <= max_attempts),
  CONSTRAINT research_jobs_lease_consistency CHECK (
    (state = 'RUNNING' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (state <> 'RUNNING' AND lease_token IS NULL AND lease_expires_at IS NULL)
  ),
  CONSTRAINT research_jobs_error_code CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{1,99}$')
);

CREATE INDEX research_jobs_claim_idx ON research_jobs (state, lease_expires_at, created_at, job_id);
CREATE INDEX research_jobs_owner_idx ON research_jobs (owner_subject, created_at DESC, job_id DESC);

CREATE TABLE research_job_events (
  event_id bigserial PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES research_jobs(job_id) ON DELETE RESTRICT,
  event_type text NOT NULL,
  from_state text,
  to_state text NOT NULL,
  attempt integer NOT NULL,
  error_code varchar(100),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT research_job_events_type CHECK (
    event_type IN ('SUBMITTED', 'CLAIMED', 'LEASE_RECOVERED', 'REQUEUED', 'SUCCEEDED', 'FAILED', 'CANCELLED')
  ),
  CONSTRAINT research_job_events_states CHECK (
    (from_state IS NULL OR from_state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'))
    AND to_state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
  ),
  CONSTRAINT research_job_events_attempt CHECK (attempt >= 0),
  CONSTRAINT research_job_events_error CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{1,99}$')
);

CREATE INDEX research_job_events_job_idx ON research_job_events (job_id, event_id);

