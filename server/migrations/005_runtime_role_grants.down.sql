DO $role_grants$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_api') THEN
    REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM tradepilot_api;
    REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM tradepilot_api;
    REVOKE USAGE ON SCHEMA public FROM tradepilot_api;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradepilot_worker') THEN
    REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM tradepilot_worker;
    REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM tradepilot_worker;
    REVOKE USAGE ON SCHEMA public FROM tradepilot_worker;
  END IF;
END
$role_grants$;
