-- Schema v2: the target data model (docs/DATA_MODEL.md).
--
-- Added beside the v1 tables of 0001 ("expand"). Each domain's code moves
-- onto these tables in its own night-time step, and the v1 table or settings
-- keys it replaces are dropped by a later migration once nothing reads them
-- ("contract"). Until then these tables are empty and nothing reads them.
--
-- Conventions
--   * STRICT tables: a value of the wrong type is an error, not a surprise.
--   * Times are UTC ISO-8601 with milliseconds ('2026-11-26T14:03:07.123Z'),
--     set by the application. Business dates are property-local 'YYYY-MM-DD'.
--   * Booleans are INTEGER 0/1 with a CHECK.
--   * JSON is used only for document-shaped data (a solver's plan, a job's
--     payload); every JSON column has CHECK (json_valid(...)).
--   * Vocabularies people see (roles, room statuses, services) are lookup
--     tables with English and Spanish labels: a new value is an INSERT, not a
--     table rebuild. Internal states (job status, sign-in outcome) are CHECKs.
--   * Every index is there for a named query; each costs a row written per
--     write, which the free plan counts.

-- ── reference ────────────────────────────────────────────────────────────────

CREATE TABLE properties (
  id          TEXT PRIMARY KEY,                    -- short code, 'gc8'
  name        TEXT NOT NULL,
  time_zone   TEXT NOT NULL,                       -- IANA, 'America/Denver'
  created_at  TEXT NOT NULL
) STRICT;

CREATE TABLE roles (
  code        TEXT PRIMARY KEY,                    -- permissions per role live in code
  label_en    TEXT NOT NULL,
  label_es    TEXT NOT NULL,
  sort        INTEGER NOT NULL
) STRICT;

CREATE TABLE room_statuses (
  code        TEXT PRIMARY KEY,                    -- roomstatus.py's vocabulary
  label_en    TEXT NOT NULL,
  label_es    TEXT NOT NULL,
  is_ready    INTEGER NOT NULL CHECK (is_ready IN (0, 1)),  -- hands the room to the RQS
  sort        INTEGER NOT NULL
) STRICT;

CREATE TABLE services (
  code        TEXT PRIMARY KEY,
  label_en    TEXT NOT NULL,
  label_es    TEXT NOT NULL,
  sort        INTEGER NOT NULL
) STRICT;

CREATE TABLE rooms (
  property_id TEXT    NOT NULL REFERENCES properties(id),
  code        TEXT    NOT NULL,                    -- '3240A': building, level, number, lock-off
  building    INTEGER NOT NULL,
  level       TEXT    NOT NULL,                    -- 'Plaza', 'Terrace', '1'..'5'
  room_type   TEXT,                                -- decides a Full Clean's minutes
  active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  PRIMARY KEY (property_id, code)
) STRICT, WITHOUT ROWID;

-- ── people and access ────────────────────────────────────────────────────────

-- One row per person, whatever the sheets call them. Every other table points
-- here by id, so a corrected spelling is one UPDATE.
CREATE TABLE people (
  id            INTEGER PRIMARY KEY,
  property_id   TEXT    NOT NULL REFERENCES properties(id),
  full_name     TEXT    NOT NULL,                  -- the name HotSOS knows
  hotsos_id     TEXT,
  job           TEXT    NOT NULL REFERENCES roles(code),
  language      TEXT    NOT NULL DEFAULT 'es' CHECK (language IN ('en', 'es')),
  on_roster     INTEGER NOT NULL DEFAULT 1 CHECK (on_roster IN (0, 1)),
  verified      INTEGER NOT NULL DEFAULT 1 CHECK (verified IN (0, 1)),  -- 0: created from an unmatched name
  left_at       TEXT,
  created_at    TEXT    NOT NULL,
  updated_at    TEXT    NOT NULL,
  UNIQUE (property_id, full_name)
) STRICT;
CREATE UNIQUE INDEX idx_people_hotsos ON people (property_id, hotsos_id) WHERE hotsos_id IS NOT NULL;

-- "Camila O", "camila", "C. Ochoa" -> one person. Replaces staff_directory.
CREATE TABLE person_aliases (
  property_id TEXT    NOT NULL REFERENCES properties(id),
  alias       TEXT    NOT NULL COLLATE NOCASE,
  person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  approved_by TEXT,
  approved_at TEXT,
  PRIMARY KEY (property_id, alias)
) STRICT, WITHOUT ROWID;

CREATE TABLE accounts (
  id               INTEGER PRIMARY KEY,
  username         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  password_hash    TEXT    NOT NULL,               -- 'pbkdf2$<rounds>$<salt>$<hex>'; DATA_MODEL.md "Sign-in"
  role             TEXT    NOT NULL REFERENCES roles(code),
  person_id        INTEGER REFERENCES people(id) ON DELETE SET NULL,
  work_email       TEXT    UNIQUE COLLATE NOCASE,  -- Microsoft 365 sign-in, once IT agrees
  language         TEXT    CHECK (language IN ('en', 'es')),
  disabled_at      TEXT,
  created_at       TEXT    NOT NULL,
  last_sign_in_at  TEXT
) STRICT;

-- The cookie holds a random token; only its SHA-256 is stored.
-- last_seen_at is refreshed at most hourly: a write per request would be
-- the largest writer in the database.
CREATE TABLE sessions (
  token_hash    TEXT    PRIMARY KEY,
  account_id    INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at    TEXT    NOT NULL,
  expires_at    TEXT    NOT NULL,
  last_seen_at  TEXT    NOT NULL,
  client        TEXT    NOT NULL CHECK (client IN ('web', 'streamlit', 'agent'))
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_sessions_account ON sessions (account_id);
CREATE INDEX idx_sessions_expires ON sessions (expires_at);          -- nightly cleanup

-- Every attempt, good or bad: the Admin page's history and the lockout check.
CREATE TABLE sign_in_events (
  id          INTEGER PRIMARY KEY,
  username    TEXT    NOT NULL COLLATE NOCASE,
  account_id  INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  outcome     TEXT    NOT NULL CHECK (outcome IN ('ok', 'wrong_password', 'unknown_user', 'locked', 'disabled')),
  client      TEXT    NOT NULL CHECK (client IN ('web', 'streamlit')),
  at          TEXT    NOT NULL
) STRICT;
CREATE INDEX idx_sign_in_events_user ON sign_in_events (username, at);  -- recent failures
CREATE INDEX idx_sign_in_events_at ON sign_in_events (at);              -- history, retention

-- Small per-account state: "seen up to" markers, dismissed notes.
CREATE TABLE account_prefs (
  account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  key         TEXT    NOT NULL,                    -- 'seen.shift_changes', 'seen.notes', ...
  value       TEXT    NOT NULL CHECK (json_valid(value)),
  updated_at  TEXT    NOT NULL,
  PRIMARY KEY (account_id, key)
) STRICT, WITHOUT ROWID;

CREATE TABLE push_subscriptions (
  id          INTEGER PRIMARY KEY,
  account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  endpoint    TEXT    NOT NULL UNIQUE,
  p256dh      TEXT    NOT NULL,
  auth        TEXT    NOT NULL,
  created_at  TEXT    NOT NULL,
  last_ok_at  TEXT
) STRICT;
CREATE INDEX idx_push_subscriptions_account ON push_subscriptions (account_id);

-- ── staffing ─────────────────────────────────────────────────────────────────

-- One staff-schedule workbook read. The workbook itself is not stored.
CREATE TABLE sheet_imports (
  id               INTEGER PRIMARY KEY,
  property_id      TEXT    NOT NULL REFERENCES properties(id),
  file_name        TEXT    NOT NULL,
  file_hash        TEXT    NOT NULL,              -- SHA-256: an unchanged file is not re-read
  file_modified_at TEXT,
  imported_at      TEXT    NOT NULL,
  imported_by      TEXT    NOT NULL,
  summary          TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(summary))
) STRICT;

-- A person's day: what the sheet says, and what a manager set over it.
CREATE TABLE shifts (
  property_id    TEXT    NOT NULL REFERENCES properties(id),
  date           TEXT    NOT NULL,
  person_id      INTEGER NOT NULL REFERENCES people(id),
  code           TEXT    NOT NULL,                -- effective: the override if set, else the sheet
  kind           TEXT    NOT NULL CHECK (kind IN ('work', 'off', 'vto', 'sick', 'late_notice', 'other')),
  sheet_code     TEXT,
  import_id      INTEGER REFERENCES sheet_imports(id),
  override_code  TEXT,
  override_by    TEXT,
  override_at    TEXT,
  PRIMARY KEY (property_id, date, person_id)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_shifts_person ON shifts (person_id, date);           -- My Home: one person's weeks

-- What changed between two imports: the "your schedule changed" notice.
CREATE TABLE shift_changes (
  id          INTEGER PRIMARY KEY,
  property_id TEXT    NOT NULL REFERENCES properties(id),
  date        TEXT    NOT NULL,
  person_id   INTEGER NOT NULL REFERENCES people(id),
  old_code    TEXT,
  new_code    TEXT,
  import_id   INTEGER REFERENCES sheet_imports(id),
  at          TEXT    NOT NULL
) STRICT;
CREATE INDEX idx_shift_changes_person ON shift_changes (person_id, at);

-- ── the day ──────────────────────────────────────────────────────────────────

-- Each Generate or 5 AM build is a new version; the plan is never edited.
-- Replaces schedule_full and schedule_log (which held the same thing twice).
CREATE TABLE day_plans (
  id           INTEGER PRIMARY KEY,
  property_id  TEXT    NOT NULL REFERENCES properties(id),
  date         TEXT    NOT NULL,
  version      INTEGER NOT NULL,
  is_current   INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
  made_by      TEXT    NOT NULL,                  -- 'auto-5am' or a username
  made_at      TEXT    NOT NULL,
  solver       TEXT,                              -- 'fcsolve' | 'heuristic'
  plan         TEXT    NOT NULL CHECK (json_valid(plan)),
  UNIQUE (property_id, date, version)
) STRICT;
CREATE UNIQUE INDEX idx_day_plans_current ON day_plans (property_id, date) WHERE is_current = 1;

-- Who has which room right now. Starts from the plan; kept in line with
-- HotSOS and with Reassign. A room with no housekeeper is "unplaced".
CREATE TABLE assignments (
  property_id     TEXT    NOT NULL REFERENCES properties(id),
  date            TEXT    NOT NULL,
  room            TEXT    NOT NULL,
  chart           TEXT    NOT NULL,               -- 'FC-A', 'DS-3', 'DV'
  service         TEXT    NOT NULL REFERENCES services(code),
  housekeeper_id  INTEGER REFERENCES people(id),
  inspector_id    INTEGER REFERENCES people(id),
  position        INTEGER,                        -- order on the chart
  minutes         INTEGER,
  plan_id         INTEGER REFERENCES day_plans(id),
  updated_at      TEXT    NOT NULL,
  updated_by      TEXT    NOT NULL,
  PRIMARY KEY (property_id, date, room)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_assignments_housekeeper ON assignments (housekeeper_id, date);  -- My Rooms
CREATE INDEX idx_assignments_inspector ON assignments (inspector_id, date);      -- an RQS's team

-- A room's state now. Its history is in room_events.
CREATE TABLE room_state (
  property_id      TEXT NOT NULL REFERENCES properties(id),
  date             TEXT NOT NULL,
  room             TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending' REFERENCES room_statuses(code),
  started_at       TEXT,
  cleaned_at       TEXT,
  inspected_at     TEXT,
  marked_clean_at  TEXT,
  notes            TEXT,
  source           TEXT NOT NULL CHECK (source IN ('hotsos', 'app')),
  updated_by       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  PRIMARY KEY (property_id, date, room)
) STRICT, WITHOUT ROWID;
-- "has anything changed today?" reads one row instead of the whole day
CREATE INDEX idx_room_state_changed ON room_state (property_id, date, updated_at);

-- Append-only: every status change, move, note and desk mark, with who and when.
CREATE TABLE room_events (
  id          INTEGER PRIMARY KEY,
  property_id TEXT NOT NULL REFERENCES properties(id),
  date        TEXT NOT NULL,
  room        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('status', 'assignment', 'note', 'desk_mark', 'inspection')),
  old_value   TEXT,
  new_value   TEXT,
  actor       TEXT NOT NULL,                      -- a username, 'hotsos', or an agent id
  at          TEXT NOT NULL
) STRICT;
CREATE INDEX idx_room_events_room ON room_events (property_id, date, room, at);

-- The front desk's marks on a room for a day.
CREATE TABLE desk_marks (
  property_id  TEXT NOT NULL REFERENCES properties(id),
  date         TEXT NOT NULL,
  room         TEXT NOT NULL,
  mark         TEXT NOT NULL CHECK (mark IN ('departed', 'late_checkout')),
  time         TEXT,                              -- late checkout: 'HH:MM' the guest leaves
  marked_by    TEXT NOT NULL,
  marked_at    TEXT NOT NULL,
  PRIMARY KEY (property_id, date, room, mark)
) STRICT, WITHOUT ROWID;

CREATE TABLE blocked_rooms (
  id          INTEGER PRIMARY KEY,
  property_id TEXT NOT NULL REFERENCES properties(id),
  room        TEXT NOT NULL,
  from_date   TEXT NOT NULL,
  to_date     TEXT NOT NULL,
  reason      TEXT,
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  CHECK (to_date >= from_date)
) STRICT;
CREATE INDEX idx_blocked_rooms_dates ON blocked_rooms (property_id, to_date);

-- Weekend duties (carpet, stripping) per room and day.
CREATE TABLE duties (
  property_id TEXT    NOT NULL REFERENCES properties(id),
  date        TEXT    NOT NULL,
  room        TEXT    NOT NULL,
  duty        TEXT    NOT NULL,
  person_id   INTEGER REFERENCES people(id),
  done_at     TEXT,
  done_by     TEXT,
  PRIMARY KEY (property_id, date, room, duty)
) STRICT, WITHOUT ROWID;

-- A manager's rules for one day: borrowing, inspector swaps, light duty.
CREATE TABLE day_rules (
  property_id TEXT NOT NULL REFERENCES properties(id),
  date        TEXT NOT NULL,
  rules       TEXT NOT NULL CHECK (json_valid(rules)),
  set_by      TEXT NOT NULL,
  set_at      TEXT NOT NULL,
  PRIMARY KEY (property_id, date)
) STRICT, WITHOUT ROWID;

-- RQS inspections and their answers (docs/inspection-scoring.md).
CREATE TABLE checklist_questions (
  id          INTEGER PRIMARY KEY,
  property_id TEXT    NOT NULL REFERENCES properties(id),
  list        TEXT    NOT NULL,                   -- 'studio' | 'suite'
  position    INTEGER NOT NULL,
  text_en     TEXT    NOT NULL,
  text_es     TEXT    NOT NULL,
  answer      TEXT    NOT NULL CHECK (answer IN ('yes_no', 'grade_1_5')),
  active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
) STRICT;

CREATE TABLE inspections (
  id              INTEGER PRIMARY KEY,
  property_id     TEXT    NOT NULL REFERENCES properties(id),
  date            TEXT    NOT NULL,
  room            TEXT    NOT NULL,
  inspector_id    INTEGER NOT NULL REFERENCES people(id),
  housekeeper_id  INTEGER REFERENCES people(id),
  score           REAL,
  note            TEXT,
  hotsos_order_id TEXT,
  submitted_at    TEXT    NOT NULL
) STRICT;
CREATE INDEX idx_inspections_housekeeper ON inspections (housekeeper_id, date);

CREATE TABLE inspection_answers (
  inspection_id INTEGER NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
  question_id   INTEGER NOT NULL REFERENCES checklist_questions(id),
  value         INTEGER NOT NULL,
  PRIMARY KEY (inspection_id, question_id)
) STRICT, WITHOUT ROWID;

-- ── outside data ─────────────────────────────────────────────────────────────

-- The SSRS Housekeeping Dashboard as read for a day (kept 7 days).
CREATE TABLE ssrs_days (
  property_id  TEXT    NOT NULL REFERENCES properties(id),
  date         TEXT    NOT NULL,
  rooms        INTEGER NOT NULL,
  room_text    TEXT    NOT NULL,
  arrival_text TEXT,
  pulled_at    TEXT    NOT NULL,
  PRIMARY KEY (property_id, date)
) STRICT, WITHOUT ROWID;

CREATE TABLE forecasts (
  id          INTEGER PRIMARY KEY,
  property_id TEXT NOT NULL REFERENCES properties(id),
  pulled_at   TEXT NOT NULL,
  days        TEXT NOT NULL CHECK (json_valid(days))
) STRICT;

-- The desk's Pre-Reg list as read (guest names and phones are never stored).
CREATE TABLE prereg_lists (
  property_id        TEXT    NOT NULL REFERENCES properties(id),
  date               TEXT    NOT NULL,
  rooms              TEXT    NOT NULL CHECK (json_valid(rooms)),
  carried            INTEGER NOT NULL CHECK (carried IN (0, 1)),
  source_modified_at TEXT,
  read_at            TEXT    NOT NULL,
  PRIMARY KEY (property_id, date)
) STRICT, WITHOUT ROWID;

-- Derived figures kept so reports open quickly; always rebuildable.
CREATE TABLE report_cache (
  property_id TEXT NOT NULL REFERENCES properties(id),
  name        TEXT NOT NULL,                      -- 'days:2026-11', 'fair_share'
  data        TEXT NOT NULL CHECK (json_valid(data)),
  built_at    TEXT NOT NULL,
  PRIMARY KEY (property_id, name)
) STRICT, WITHOUT ROWID;

-- ── operations ───────────────────────────────────────────────────────────────

CREATE TABLE agents (
  id            TEXT PRIMARY KEY,                 -- host name, 'GC8HSKP26-03'
  role          TEXT NOT NULL CHECK (role IN ('office', 'backup', 'cloud')),
  public_key    TEXT,                             -- seals service passwords for this PC
  version       TEXT,
  last_seen_at  TEXT,                             -- the heartbeat
  status        TEXT CHECK (status IS NULL OR json_valid(status)),
  updated_at    TEXT NOT NULL
) STRICT, WITHOUT ROWID;

-- Work for an agent (or the cloud runner): replaces the *_request/*_result
-- settings keys. queued -> running -> done | failed | cancelled.
CREATE TABLE jobs (
  id            INTEGER PRIMARY KEY,
  kind          TEXT    NOT NULL CHECK (kind IN ('daily_build', 'generate', 'hotsos_push', 'hotsos_preview',
                                                  'hotsos_inspect', 'day_rooms', 'report_sync',
                                                  'ssrs_forecast', 'seal_credential')),
  property_id   TEXT    REFERENCES properties(id),
  for_date      TEXT,
  payload       TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(payload)),
  status        TEXT    NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  target_agent  TEXT    REFERENCES agents(id),    -- NULL: any agent that can
  requested_by  TEXT    NOT NULL,
  requested_at  TEXT    NOT NULL,
  claimed_by    TEXT    REFERENCES agents(id),
  claimed_at    TEXT,
  finished_at   TEXT,
  result        TEXT    CHECK (result IS NULL OR json_valid(result)),
  error         TEXT,
  attempts      INTEGER NOT NULL DEFAULT 0
) STRICT;
CREATE INDEX idx_jobs_open ON jobs (kind, requested_at) WHERE status IN ('queued', 'running');
CREATE INDEX idx_jobs_recent ON jobs (kind, for_date);

CREATE TABLE agent_events (
  id        INTEGER PRIMARY KEY,
  agent_id  TEXT NOT NULL REFERENCES agents(id),
  level     TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error')),
  message   TEXT NOT NULL,
  at        TEXT NOT NULL
) STRICT;
CREATE INDEX idx_agent_events_at ON agent_events (agent_id, at);

-- Sends that must happen once a day (Teams notes, the evening preview).
CREATE TABLE notifications_sent (
  property_id TEXT NOT NULL REFERENCES properties(id),
  kind        TEXT NOT NULL,
  date        TEXT NOT NULL,
  sent_at     TEXT NOT NULL,
  detail      TEXT CHECK (detail IS NULL OR json_valid(detail)),
  PRIMARY KEY (property_id, kind, date)
) STRICT, WITHOUT ROWID;

-- Real configuration only. property_id '*' = applies to every property.
CREATE TABLE settings (
  property_id TEXT NOT NULL DEFAULT '*',
  key         TEXT NOT NULL,
  value       TEXT NOT NULL CHECK (json_valid(value)),
  updated_by  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  PRIMARY KEY (property_id, key)
) STRICT, WITHOUT ROWID;

-- Daily usage per client against the free plan (the cron meter writes it).
CREATE TABLE usage_daily (
  date          TEXT    NOT NULL,                 -- UTC day, as Cloudflare counts it
  source        TEXT    NOT NULL,                 -- 'worker', 'agent:GC8HSKP26-03', 'd1', ...
  requests      INTEGER NOT NULL DEFAULT 0,
  rows_read     INTEGER NOT NULL DEFAULT 0,
  rows_written  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, source)
) STRICT, WITHOUT ROWID;

-- Who changed what, for anything an admin does.
CREATE TABLE audit_log (
  id       INTEGER PRIMARY KEY,
  at       TEXT NOT NULL,
  actor    TEXT NOT NULL,
  action   TEXT NOT NULL,                         -- 'account.role', 'settings.set', 'day_plan.publish', ...
  target   TEXT,
  detail   TEXT CHECK (detail IS NULL OR json_valid(detail))
) STRICT;
CREATE INDEX idx_audit_log_at ON audit_log (at);

-- ── reference rows ───────────────────────────────────────────────────────────

INSERT INTO properties (id, name, time_zone, created_at) VALUES
  ('gc8', 'Grand Colorado on Peak 8', 'America/Denver', '2026-11-26T00:00:00.000Z');

INSERT INTO roles (code, label_en, label_es, sort) VALUES
  ('admin',       'Admin',        'Administrador',    1),
  ('rqs',         'RQS',          'RQS',              2),
  ('housekeeper', 'Housekeeper',  'Camarista',        3),
  ('houseperson', 'Houseperson',  'Houseperson',      4),
  ('frontdesk',   'Front desk',   'Recepción',        5);

INSERT INTO room_statuses (code, label_en, label_es, is_ready, sort) VALUES
  ('pending',          'Not started',        'Sin empezar',          0,  1),
  ('cleaning_started', 'Cleaning',           'Limpiando',            0,  2),
  ('cleaning_done',    'Cleaned',            'Limpio',               1,  3),
  ('to_be_inspected',  'To be inspected',    'Por inspeccionar',     1,  4),
  ('occupied_cleaned', 'Occupied, cleaned',  'Ocupado, limpio',      1,  5),
  ('inspected',        'Inspected',          'Inspeccionado',        0,  6),
  ('already_clean',    'Already clean',      'Ya limpio',            0,  7),
  ('dnd',              'Do not disturb',     'No molestar',          0,  8),
  ('return_later',     'Return later',       'Volver más tarde',     0,  9),
  ('service_refused',  'Service refused',    'Servicio rechazado',   0, 10),
  ('help',             'Needs help',         'Necesita ayuda',       0, 11);

INSERT INTO services (code, label_en, label_es, sort) VALUES
  ('full_clean',     'Full Clean',       'Limpieza completa',     1),
  ('full_clean_ih',  'Full Clean (IH)',  'Limpieza completa (IH)', 2),
  ('daily_service',  'Daily Service',    'Servicio diario',       3),
  ('dust_vac',       'Dust n Vac',       'Sacudir y aspirar',     4),
  ('stayover',       'Stayover',         'Estadía',               5);
