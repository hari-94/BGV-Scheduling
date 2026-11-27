-- BGV Scheduling on Cloudflare D1 (SQLite): the tables of the Supabase
-- database it replaces, column for column, so db.py's queries keep their shape.
--
-- How values are stored:
--   * dates are 'YYYY-MM-DD' text; times are ISO-8601 text with an offset,
--     as Supabase returned them ('2026-11-26T09:00:17.901396+00:00').
--   * payload holds the JSON text of what Supabase's jsonb column held. db.py
--     writes json.dumps(obj) into it, so most payloads are a JSON *string* that
--     contains JSON; reading gives back exactly what Supabase gave back.
--   * a payload over 1 MB is stored as 'gz:' + base64(gzip(json text)):
--     D1 refuses any row over 2 MB (the staff schedule workbook copy is 2.1 MB).
--   * updated_at: Supabase set it with triggers. Here every write sets it
--     itself (db.py and the Worker both), because a trigger's second write
--     would double the rows-written count against the free plan's 100,000/day.
--
-- Indexes are kept to what queries need: each one adds a written row per write.

CREATE TABLE IF NOT EXISTS app_users (
  id            INTEGER PRIMARY KEY,
  username      TEXT    NOT NULL UNIQUE,
  password_hash TEXT    NOT NULL,
  role          TEXT    NOT NULL DEFAULT 'housekeeper'
                        CHECK (role IN ('admin','rqs','housekeeper','houseperson','frontdesk')),
  created_at    TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
  last_login    TEXT,
  display_name  TEXT
);

CREATE TABLE IF NOT EXISTS login_events (
  id            INTEGER PRIMARY KEY,
  username      TEXT    NOT NULL,
  display_name  TEXT,
  role          TEXT,
  ts            TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);
-- the Admin page lists the latest sign-ins; the nightly cleanup deletes by age
CREATE INDEX IF NOT EXISTS idx_login_events_ts ON login_events (ts);

CREATE TABLE IF NOT EXISTS room_status (
  id              INTEGER PRIMARY KEY,
  date            TEXT    NOT NULL,
  room            TEXT    NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'pending',
  group_label     TEXT,
  housekeeper     TEXT,
  inspector       TEXT,
  started_at      TEXT,
  cleaned_at      TEXT,
  inspected_at    TEXT,
  marked_clean_at TEXT,
  notes           TEXT,
  swapped_from    TEXT,
  updated_by      TEXT,
  updated_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
  UNIQUE (date, room)       -- the upsert key; also serves every "WHERE date = ?"
);

CREATE TABLE IF NOT EXISTS schedule_full (
  id          INTEGER PRIMARY KEY,
  date        TEXT    NOT NULL UNIQUE,
  payload     TEXT    NOT NULL,
  created_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
  updated_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);

CREATE TABLE IF NOT EXISTS schedule_log (
  id          INTEGER PRIMARY KEY,
  date        TEXT    NOT NULL UNIQUE,
  payload     TEXT    NOT NULL,
  created_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
  updated_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);

-- Text-keyed settings. The primary key's own index also serves prefix
-- lookups, written as a range (key >= 'staffweek_' AND key < 'staffweek`')
-- rather than LIKE, which SQLite won't run on an index here.
CREATE TABLE IF NOT EXISTS app_settings (
  key         TEXT    PRIMARY KEY,
  payload     TEXT    NOT NULL,
  updated_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
) WITHOUT ROWID;
