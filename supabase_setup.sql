-- Run this SQL in your Supabase project → SQL Editor
-- Creates both tables needed by the app

-- Daily schedule snapshots
CREATE TABLE IF NOT EXISTS schedule_log (
  id         BIGSERIAL PRIMARY KEY,
  date       DATE        NOT NULL UNIQUE,
  payload    JSONB       NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- App users with roles
CREATE TABLE IF NOT EXISTS app_users (
  id            BIGSERIAL PRIMARY KEY,
  username      TEXT        NOT NULL UNIQUE,
  password_hash TEXT        NOT NULL,
  role          TEXT        NOT NULL DEFAULT 'housekeeper'
                            CHECK (role IN ('admin','rqs','housekeeper')),
  created_at    TIMESTAMPTZ DEFAULT now(),
  last_login    TIMESTAMPTZ
);

-- Auto-update updated_at on schedule_log
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_schedule_log_updated ON schedule_log;
CREATE TRIGGER trg_schedule_log_updated
  BEFORE UPDATE ON schedule_log
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- Text-keyed settings: standing roster, staff schedule weeks, in-app edits,
-- the stored workbook. These need a TEXT key -- schedule_full.date is a real
-- DATE column and rejects keys like 'roster' or 'staffweek_2026-08-23'.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_settings (
  key        TEXT        PRIMARY KEY,
  payload    JSONB       NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_app_settings_updated ON app_settings;
CREATE TRIGGER trg_app_settings_updated
  BEFORE UPDATE ON app_settings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Prefix lookups (staffweek_%) stay fast as weeks accumulate.
CREATE INDEX IF NOT EXISTS idx_app_settings_key_prefix
  ON app_settings (key text_pattern_ops);

-- Generated day schedules, keyed by a real calendar date.
CREATE TABLE IF NOT EXISTS schedule_full (
  id         BIGSERIAL   PRIMARY KEY,
  date       DATE        NOT NULL UNIQUE,
  payload    JSONB       NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_schedule_full_updated ON schedule_full;
CREATE TRIGGER trg_schedule_full_updated
  BEFORE UPDATE ON schedule_full
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Row-level security (optional but recommended)
-- ALTER TABLE schedule_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE app_users    ENABLE ROW LEVEL SECURITY;
