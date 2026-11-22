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

-- 2. Grant Database connection dynamically on current database
DO
$do$
BEGIN
   EXECUTE format('GRANT CONNECT ON DATABASE %I TO insightforge_ro', current_database());
END
$do$;

-- 3. Grant schema usage
GRANT USAGE ON SCHEMA insightforge TO insightforge_ro;

-- 4. Grant SELECT on all existing tables and views in schema
GRANT SELECT ON ALL TABLES IN SCHEMA insightforge TO insightforge_ro;

-- 4a. Ensure the AI audit table exists before revoking on it (it is otherwise only
--     auto-created by the app at runtime, which made this script fail on a fresh DB).
CREATE TABLE IF NOT EXISTS insightforge.ai_audit_log (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    intent VARCHAR(100),
    generated_sql TEXT,
    latency_ms DOUBLE PRECISION NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_audit_log_timestamp
    ON insightforge.ai_audit_log (timestamp DESC);

-- 4b. Security Denylist: revoke ALL on internal audit & workspace metadata tables.
--     Step 4 grants SELECT on every table, so this must run after it regardless of
--     whether the dataset migrations were applied before or after this script.
DO
$do$
DECLARE
   t TEXT;
BEGIN
   FOREACH t IN ARRAY ARRAY['ai_audit_log', 'datasets', 'dataset_tables', 'dataset_columns',
                            'dataset_relationships', 'dataset_semantic'] LOOP
      IF to_regclass('insightforge.' || t) IS NOT NULL THEN
         EXECUTE format('REVOKE ALL ON TABLE insightforge.%I FROM insightforge_ro', t);
      END IF;
   END LOOP;
END
$do$;

-- 5. Automatically grant SELECT on future tables created in schema
ALTER DEFAULT PRIVILEGES IN SCHEMA insightforge GRANT SELECT ON TABLES TO insightforge_ro;

-- 6. Enforce statement execution timeout (5 seconds defense in depth) and default schema
ALTER ROLE insightforge_ro SET statement_timeout = '5s';
ALTER ROLE insightforge_ro SET search_path TO insightforge, public;
