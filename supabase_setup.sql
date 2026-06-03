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

-- Row-level security (optional but recommended)
-- ALTER TABLE schedule_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE app_users    ENABLE ROW LEVEL SECURITY;
