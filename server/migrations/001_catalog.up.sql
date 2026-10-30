CREATE TABLE instruments (
  symbol varchar(12) PRIMARY KEY,
  base_currency char(3) NOT NULL,
  quote_currency char(3) NOT NULL,
  pip_size text NOT NULL,
  price_precision smallint NOT NULL,
  cataloged_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT instruments_symbol_format CHECK (symbol ~ '^[A-Z]{6,12}$'),
  CONSTRAINT instruments_base_currency_format CHECK (base_currency ~ '^[A-Z]{3}$'),
  CONSTRAINT instruments_quote_currency_format CHECK (quote_currency ~ '^[A-Z]{3}$'),
  CONSTRAINT instruments_distinct_currencies CHECK (base_currency <> quote_currency),
  CONSTRAINT instruments_pip_size_format CHECK (
    pip_size ~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$' AND pip_size::numeric > 0
  ),
  CONSTRAINT instruments_price_precision_range CHECK (price_precision BETWEEN 0 AND 12)
);

CREATE TABLE datasets (
  dataset_id char(64) PRIMARY KEY,
  canonical_checksum char(64) NOT NULL,
  instrument_symbol varchar(12) NOT NULL REFERENCES instruments(symbol),
  provider text NOT NULL,
  timeframe text NOT NULL,
  first_candle_open timestamptz NOT NULL,
  last_candle_open timestamptz NOT NULL,
  row_count bigint NOT NULL,
  schema_version text NOT NULL,
  artifact_key text NOT NULL UNIQUE,
  is_synthetic boolean NOT NULL,
  integrity_verified_at timestamptz NOT NULL,
  cataloged_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT datasets_id_format CHECK (dataset_id ~ '^[0-9a-f]{64}$'),
  CONSTRAINT datasets_checksum_format CHECK (canonical_checksum ~ '^[0-9a-f]{64}$'),
  CONSTRAINT datasets_provider_nonempty CHECK (length(provider) BETWEEN 1 AND 100),
  CONSTRAINT datasets_timeframe_format CHECK (timeframe ~ '^[A-Z][A-Z0-9]{0,15}$'),
  CONSTRAINT datasets_timestamp_order CHECK (first_candle_open <= last_candle_open),
  CONSTRAINT datasets_row_count_positive CHECK (row_count > 0),
  CONSTRAINT datasets_schema_nonempty CHECK (length(schema_version) BETWEEN 1 AND 200),
  CONSTRAINT datasets_artifact_key_safe CHECK (
    artifact_key ~ '^[A-Za-z0-9._/-]+$'
    AND artifact_key !~ '(^/|(^|/)\.\.(/|$)|//)'
  )
);

CREATE INDEX datasets_instrument_timeframe_idx
  ON datasets (instrument_symbol, timeframe, first_candle_open);

CREATE TABLE candidate_reports (
  report_id char(64) PRIMARY KEY,
  dataset_id char(64) NOT NULL REFERENCES datasets(dataset_id),
  strategy_name text NOT NULL,
  strategy_version text NOT NULL,
  configuration_fingerprint char(64) NOT NULL,
  schema_version text NOT NULL,
  signal_count integer NOT NULL,
  artifact_key text NOT NULL UNIQUE,
  integrity_verified_at timestamptz NOT NULL,
  cataloged_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT candidate_reports_id_format CHECK (report_id ~ '^[0-9a-f]{64}$'),
  CONSTRAINT candidate_reports_fingerprint_format CHECK (
    configuration_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT candidate_reports_strategy_name_nonempty CHECK (
    length(strategy_name) BETWEEN 1 AND 200
  ),
  CONSTRAINT candidate_reports_strategy_version_nonempty CHECK (
    length(strategy_version) BETWEEN 1 AND 200
  ),
  CONSTRAINT candidate_reports_schema_nonempty CHECK (length(schema_version) BETWEEN 1 AND 200),
  CONSTRAINT candidate_reports_signal_count_nonnegative CHECK (signal_count >= 0),
  CONSTRAINT candidate_reports_artifact_key_safe CHECK (
    artifact_key ~ '^[A-Za-z0-9._/-]+$'
    AND artifact_key !~ '(^/|(^|/)\.\.(/|$)|//)'
  )
);

CREATE INDEX candidate_reports_dataset_idx ON candidate_reports (dataset_id, report_id);
