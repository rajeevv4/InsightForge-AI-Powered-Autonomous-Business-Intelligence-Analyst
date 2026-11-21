-- ============================================================================
-- InsightForge - Read-Only Database Role Provisioning
-- Role: insightforge_ro
-- Scope: SELECT privileges exclusively on insightforge schema tables & views
-- ============================================================================

-- 1. Create Role if not already present
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE rolname = 'insightforge_ro') THEN
      CREATE ROLE insightforge_ro WITH LOGIN PASSWORD 'insightforge_ro_pass';
   END IF;
END
$do$;

-- 2. Grant Database connection
GRANT CONNECT ON DATABASE insightforge TO insightforge_ro;

-- 3. Grant schema usage
GRANT USAGE ON SCHEMA insightforge TO insightforge_ro;

-- 4. Grant SELECT on all existing tables and views in schema
GRANT SELECT ON ALL TABLES IN SCHEMA insightforge TO insightforge_ro;

-- 4b. Security Denylist: Explicitly revoke SELECT on internal audit & system tables
REVOKE SELECT ON TABLE insightforge.ai_audit_log FROM insightforge_ro;

-- 5. Automatically grant SELECT on future tables created in schema
ALTER DEFAULT PRIVILEGES IN SCHEMA insightforge GRANT SELECT ON TABLES TO insightforge_ro;

-- 6. Enforce statement execution timeout (5 seconds defense in depth)
ALTER ROLE insightforge_ro SET statement_timeout = '5s';
