-- ==============================================================================
-- InsightForge Level 6: Dataset Semantic Layer Metadata Schema
-- ==============================================================================
-- Admin-only table in schema insightforge; NOT readable by insightforge_ro.
-- Idempotent creation script.

CREATE SCHEMA IF NOT EXISTS insightforge;

CREATE TABLE IF NOT EXISTS insightforge.dataset_semantic (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES insightforge.datasets(id) ON DELETE CASCADE UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    semantic_model JSONB NOT NULL DEFAULT '{}'::jsonb,
    starter_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dataset_semantic_dataset ON insightforge.dataset_semantic(dataset_id);

-- Security & Isolation: Explicitly REVOKE ALL permissions on semantic metadata from insightforge_ro
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'insightforge_ro') THEN
        REVOKE ALL ON insightforge.dataset_semantic FROM insightforge_ro;
    END IF;
END $$;
