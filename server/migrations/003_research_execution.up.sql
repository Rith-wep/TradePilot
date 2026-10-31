ALTER TABLE research_jobs
  ADD COLUMN result_report_id char(64) REFERENCES candidate_reports(report_id),
  ADD CONSTRAINT research_jobs_result_consistency CHECK (
    (state = 'SUCCEEDED' AND result_report_id IS NOT NULL)
    OR (state <> 'SUCCEEDED' AND result_report_id IS NULL)
  );

ALTER TABLE research_job_events
  DROP CONSTRAINT research_job_events_type,
  ADD CONSTRAINT research_job_events_type CHECK (
    event_type IN (
      'SUBMITTED', 'CLAIMED', 'LEASE_RENEWED', 'LEASE_RECOVERED',
      'REQUEUED', 'SUCCEEDED', 'FAILED', 'CANCELLED'
    )
  );

