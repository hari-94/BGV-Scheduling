-- Run this once in Supabase → SQL Editor.
-- Creates the text-keyed settings table the app needs for the standing roster
-- and the weekly staff schedule. Safe to re-run.

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS app_settings (
  key        TEXT        PRIMARY KEY,
  payload    JSONB       NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_app_settings_updated ON app_settings;
CREATE TRIGGER trg_app_settings_updated
  BEFORE UPDATE ON app_settings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX IF NOT EXISTS idx_app_settings_key_prefix
  ON app_settings (key text_pattern_ops);

SELECT 'app_settings ready' AS status;
