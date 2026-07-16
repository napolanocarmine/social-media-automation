-- Social Media Automation — Schema Postgres iniziale
-- Migrazione da SQLite (store.py) a Neon Postgres
-- Eseguire con: psql "$DATABASE_URL_UNPOOLED" -f docs/sql/001_initial_schema.sql

BEGIN;

-- ============================================================================
-- images
-- ============================================================================
CREATE TABLE IF NOT EXISTS images (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    path            TEXT NOT NULL UNIQUE,          -- Blob URL (processed principale)
    original_path   TEXT,                           -- Blob URL originale Drive
    generated_image_path TEXT,                      -- Blob URL output AI edit

    -- Render flags per piattaforma/formato
    render_ig           BOOLEAN NOT NULL DEFAULT FALSE,
    render_fb           BOOLEAN NOT NULL DEFAULT FALSE,
    render_ig_story     BOOLEAN NOT NULL DEFAULT FALSE,
    render_fb_story     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Validazione e approvazione
    is_valid_by_quality_evaluation  BOOLEAN,        -- NULL = non valutato
    quality_predicted_class         TEXT,
    quality_predicted_confidence    REAL,
    is_valid_for_publication        BOOLEAN,        -- NULL = pending, TRUE = approved, FALSE = rejected
    vision_eval_pass                BOOLEAN,
    vision_eval_reason              TEXT,

    -- Story AI output
    copy_json       JSONB,
    retouch_json    JSONB,
    visual_score    REAL,
    visual_status   TEXT,
    editing_required BOOLEAN,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_images_approval
    ON images (is_valid_for_publication, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_images_path
    ON images (path);

-- ============================================================================
-- planning_events
-- ============================================================================
CREATE TABLE IF NOT EXISTS planning_events (
    id              SERIAL PRIMARY KEY,
    image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,                  -- 'instagram' | 'facebook'
    event_type      TEXT NOT NULL,                  -- 'planned' | 'rescheduled' | 'published' | 'failed' | 'cancelled'
    scheduled_for   TIMESTAMPTZ,
    external_id     TEXT,                           -- ID post Meta (se pubblicato)
    detail          TEXT,                           -- Caption o JSON detail
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planning_events_due
    ON planning_events (scheduled_for, event_type, platform);

CREATE INDEX IF NOT EXISTS idx_planning_events_image
    ON planning_events (image_id, platform, created_at DESC);

-- ============================================================================
-- story_schedule_rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS story_schedule_rules (
    id              SERIAL PRIMARY KEY,
    image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    schedule_mode   TEXT NOT NULL,                  -- 'once' | 'weekly'
    scheduled_for   TIMESTAMPTZ,                    -- Per mode 'once'
    weekday         INTEGER,                        -- 0=lun … 6=dom (per mode 'weekly')
    time_local      TEXT,                           -- 'HH:MM' (per mode 'weekly')
    timezone        TEXT NOT NULL DEFAULT 'Europe/Rome',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    detail          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_story_schedule_rules_active_mode
    ON story_schedule_rules (active, schedule_mode);

-- ============================================================================
-- story_schedule_occurrences
-- ============================================================================
CREATE TABLE IF NOT EXISTS story_schedule_occurrences (
    id              SERIAL PRIMARY KEY,
    rule_id         INTEGER NOT NULL REFERENCES story_schedule_rules(id) ON DELETE CASCADE,
    occurrence_date TEXT NOT NULL,                  -- ISO date della occorrenza
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_id, occurrence_date)
);

-- ============================================================================
-- batches
-- ============================================================================
CREATE TABLE IF NOT EXISTS batches (
    id              SERIAL PRIMARY KEY,
    status          TEXT NOT NULL,                  -- 'running' | 'completed' | 'failed' | 'stopped'
    category        TEXT,
    platform        TEXT,
    media_format    TEXT,                           -- 'post' | 'story'
    requested_count INTEGER NOT NULL DEFAULT 1,
    completed_count INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    last_error      TEXT,
    note            TEXT,
    stop_requested_at TIMESTAMPTZ,
    stop_reason     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_batches_status_created_at
    ON batches (status, created_at DESC);

-- ============================================================================
-- batch_items
-- ============================================================================
CREATE TABLE IF NOT EXISTS batch_items (
    id              SERIAL PRIMARY KEY,
    batch_id        INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    item_index      INTEGER NOT NULL,
    status          TEXT NOT NULL,                  -- 'queued' | 'running' | 'completed' | 'failed'
    source_asset_id TEXT,
    source_asset_name TEXT,
    business_category TEXT,
    template_id     TEXT,
    image_id        INTEGER REFERENCES images(id) ON DELETE SET NULL,
    rendered_file   TEXT,                           -- Blob URL (deprecato: usare image_id)
    media_format    TEXT,
    error_message   TEXT,
    payload_json    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, item_index)
);

CREATE INDEX IF NOT EXISTS idx_batch_items_batch_status
    ON batch_items (batch_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_batch_items_queued
    ON batch_items (status, created_at ASC)
    WHERE status = 'queued';

-- ============================================================================
-- metadata
-- ============================================================================
CREATE TABLE IF NOT EXISTS metadata (
    id              SERIAL PRIMARY KEY,
    image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    platform        TEXT,
    template_id     TEXT,
    template_dimensions_source TEXT,
    canvas_width    INTEGER,
    canvas_height   INTEGER,
    export_width    INTEGER,
    export_height   INTEGER,
    image_fit       TEXT,
    asset_id        TEXT,
    design_id       TEXT,
    source_file     TEXT,
    output_file     TEXT,
    mode            TEXT,
    note            TEXT,
    metadata_json   JSONB NOT NULL,
    source_asset_id TEXT,
    source_asset_name TEXT,
    business_category TEXT,
    media_format    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metadata_image
    ON metadata (image_id, created_at DESC);

-- ============================================================================
-- oauth_tokens (nuovo — per OAuth web su Vercel)
-- ============================================================================
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id              SERIAL PRIMARY KEY,
    provider        TEXT NOT NULL UNIQUE,           -- 'google_drive' | 'meta'
    refresh_token   TEXT NOT NULL,
    access_token    TEXT,
    expires_at      TIMESTAMPTZ,
    scopes          TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- cron_runs (nuovo — audit dispatch)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cron_runs (
    id              SERIAL PRIMARY KEY,
    run_type        TEXT NOT NULL DEFAULT 'dispatch',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    published_count INTEGER DEFAULT 0,
    failed_count    INTEGER DEFAULT 0,
    skipped_count   INTEGER DEFAULT 0,
    error           TEXT,
    vercel_deployment_id TEXT,
    detail          JSONB
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_type_started
    ON cron_runs (run_type, started_at DESC);

-- ============================================================================
-- Trigger: updated_at automatico su images e batches
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_images_updated_at
    BEFORE UPDATE ON images
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_batches_updated_at
    BEFORE UPDATE ON batches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- ============================================================================
-- Note post-migrazione
-- ============================================================================
-- 1. images.path contiene Blob URL, non path locali
-- 2. batch_items.status include 'queued' (nuovo per Vercel queue)
-- 3. batches.runner_pid RIMOSSO (non serve con queue)
-- 4. copy_json e retouch_json sono JSONB (non TEXT)
-- 5. julianday() sostituito da confronti TIMESTAMPTZ nativi
-- 6. INSERT OR IGNORE → ON CONFLICT DO NOTHING
-- 7. INSERT OR REPLACE → ON CONFLICT DO UPDATE
