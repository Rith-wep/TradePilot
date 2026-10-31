DO $role_grants$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_api') THEN
    GRANT USAGE ON SCHEMA public TO tradepilot_api;
    GRANT SELECT ON instruments, datasets, candidate_reports TO tradepilot_api;
    GRANT SELECT, INSERT ON research_jobs TO tradepilot_api;
    GRANT INSERT ON research_job_events TO tradepilot_api;
    GRANT USAGE, SELECT ON SEQUENCE research_job_events_event_id_seq TO tradepilot_api;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_worker') THEN
    GRANT USAGE ON SCHEMA public TO tradepilot_worker;
    GRANT SELECT, INSERT ON instruments, datasets, candidate_reports TO tradepilot_worker;
    GRANT SELECT, UPDATE ON research_jobs TO tradepilot_worker;
    GRANT INSERT ON research_job_events TO tradepilot_worker;
    GRANT USAGE, SELECT ON SEQUENCE research_job_events_event_id_seq TO tradepilot_worker;
  END IF;
END
$role_grants$;
