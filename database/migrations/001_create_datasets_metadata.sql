-- ==============================================================================
-- InsightForge Level 5: Dataset Workspace Metadata Schema
-- ==============================================================================
-- Admin-only tables in schema insightforge; NOT readable by insightforge_ro.
-- Idempotent creation script.

CREATE SCHEMA IF NOT EXISTS insightforge;

-- 1. Datasets Master Table
CREATE TABLE IF NOT EXISTS insightforge.datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    owner_token_hash VARCHAR(64) NOT NULL,
    schema_name VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'ready',
    share_samples BOOLEAN NOT NULL DEFAULT FALSE,
    source_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_datasets_owner ON insightforge.datasets(owner_token_hash);
CREATE INDEX IF NOT EXISTS idx_datasets_schema ON insightforge.datasets(schema_name);
CREATE INDEX IF NOT EXISTS idx_datasets_expires_at ON insightforge.datasets(expires_at);

-- 2. Dataset Tables
CREATE TABLE IF NOT EXISTS insightforge.dataset_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES insightforge.datasets(id) ON DELETE CASCADE,
    original_name VARCHAR(255) NOT NULL,
    safe_name VARCHAR(63) NOT NULL,
    row_count BIGINT DEFAULT 0,
    column_count INT DEFAULT 0,
    candidate_pk VARCHAR(63),
    candidate_time_column VARCHAR(63),
    quality_findings JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dataset_tables_dataset ON insightforge.dataset_tables(dataset_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_tables_unique_safe ON insightforge.dataset_tables(dataset_id, safe_name);

-- 3. Dataset Columns
CREATE TABLE IF NOT EXISTS insightforge.dataset_columns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID NOT NULL REFERENCES insightforge.dataset_tables(id) ON DELETE CASCADE,
    original_name VARCHAR(255) NOT NULL,
    safe_name VARCHAR(63) NOT NULL,
    pg_type VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    null_pct NUMERIC(5, 2) DEFAULT 0.0,
    distinct_count BIGINT DEFAULT 0,
    min_val TEXT,
    max_val TEXT,
    stats JSONB DEFAULT '{}'::jsonb,
    user_description TEXT
);

CREATE INDEX IF NOT EXISTS idx_dataset_columns_table ON insightforge.dataset_columns(table_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_columns_unique_safe ON insightforge.dataset_columns(table_id, safe_name);

-- 4. Dataset Relationships
CREATE TABLE IF NOT EXISTS insightforge.dataset_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES insightforge.datasets(id) ON DELETE CASCADE,
    parent_table VARCHAR(63) NOT NULL,
    parent_column VARCHAR(63) NOT NULL,
    child_table VARCHAR(63) NOT NULL,
    child_column VARCHAR(63) NOT NULL,
    cardinality VARCHAR(16) NOT NULL,
    confidence NUMERIC(4, 3) DEFAULT 0.0,
    confirmed BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_dataset_relationships_dataset ON insightforge.dataset_relationships(dataset_id);

-- 5. Security & Isolation: Explicitly REVOKE ALL permissions on metadata from insightforge_ro
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'insightforge_ro') THEN
        REVOKE ALL ON insightforge.datasets FROM insightforge_ro;
        REVOKE ALL ON insightforge.dataset_tables FROM insightforge_ro;
        REVOKE ALL ON insightforge.dataset_columns FROM insightforge_ro;
        REVOKE ALL ON insightforge.dataset_relationships FROM insightforge_ro;
    END IF;
END $$;

-- 6. Register Olist as built-in demo dataset "olist-demo"
INSERT INTO insightforge.datasets (
    id,
    name,
    owner_token_hash,
    schema_name,
    status,
    share_samples,
    source_files,
    size_bytes,
    created_at,
    expires_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Olist Brazilian E-Commerce',
    'SYSTEM_DEMO_DATASET',
    'insightforge',
    'ready',
    FALSE,
    '["customers.csv", "orders.csv", "order_items.csv", "products.csv", "sellers.csv", "order_payments.csv", "order_reviews.csv"]'::jsonb,
    115000000,
    NOW(),
    NULL
)
ON CONFLICT (schema_name) DO UPDATE SET
    name = EXCLUDED.name,
    status = 'ready',
    expires_at = NULL;
