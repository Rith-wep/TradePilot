ALTER TABLE research_job_events
  DROP CONSTRAINT research_job_events_type,
  ADD CONSTRAINT research_job_events_type CHECK (
    event_type IN ('SUBMITTED', 'CLAIMED', 'LEASE_RECOVERED', 'REQUEUED', 'SUCCEEDED', 'FAILED', 'CANCELLED')
  );
ALTER TABLE research_jobs DROP CONSTRAINT research_jobs_result_consistency;
ALTER TABLE research_jobs DROP COLUMN result_report_id;

