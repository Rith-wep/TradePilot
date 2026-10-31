ALTER TABLE research_jobs
  ADD COLUMN implementation_revision varchar(40) NOT NULL DEFAULT 'unknown',
  ADD CONSTRAINT research_jobs_revision CHECK (
    implementation_revision = 'unknown' OR implementation_revision ~ '^[0-9a-f]{40}$'
  );
