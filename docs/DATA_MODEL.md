# Data model — BGV Scheduling on Cloudflare D1

The database the suite moves to. The SQL is the source of truth
(`web/migrations/`); this page explains it. Design reasons are in
`docs/SYSTEM_REVIEW.md` §2.2 and §4.

## How it is laid out

Two generations of tables live side by side during the move:

- **v1** (`0001_init.sql`) — a column-for-column copy of the Supabase tables,
  so the live app can switch databases with nothing else changing.
- **v2** (`0002_schema_v2.sql`) — the target. Each domain moves onto it in
  its own step; the v1 table or `app_settings` keys it replaces are then
  dropped by a later migration.

```
 properties ─┬─ rooms
             ├─ people ─┬─ person_aliases
             │          ├─ shifts ── sheet_imports
             │          └─ accounts ─┬─ sessions
             │                       ├─ sign_in_events
             │                       ├─ account_prefs
             │                       └─ push_subscriptions
             ├─ day_plans ── assignments ──┐
             ├─ room_state ── room_events  ├─ (property, date, room)
             ├─ desk_marks · duties · blocked_rooms · day_rules
             ├─ inspections ── inspection_answers ── checklist_questions
             └─ ssrs_days · forecasts · prereg_lists · report_cache

 agents ── jobs · agent_events        settings · usage_daily · audit_log
 lookups: roles · room_statuses · services   (labels in English and Spanish)
```

## Conventions

| Rule | Why |
|---|---|
| `STRICT` tables | a wrong type is rejected, not stored |
| Times: UTC ISO-8601 with milliseconds, set by the application; business dates: property-local `YYYY-MM-DD` | one format everywhere; "today" means the property's day |
| `property_id` on everything property-scoped | a second property is data, not a rewrite |
| People are rows with ids; names are attributes | today a person is a name string in eight places, so a spelling change ripples everywhere |
| Lookups (roles, statuses, services) are tables with EN/ES labels | adding one is an `INSERT`; the labels are the UI's labels |
| JSON only for documents (a plan, a job payload), always `CHECK (json_valid(...))` | queryable data is in columns |
| Current state + append-only history (`room_state` + `room_events`) | fast reads and a full audit trail |
| Each index serves a named query; no others | every index is an extra row written, which the free plan counts |
| Prefix lookups are ranges (`k >= 'p' AND k < 'q'`), never `LIKE 'p%'` | measured: LIKE reads the whole table |
| Every result set is bounded (`LIMIT`, a date, a key) | the 5M rows-read limit is per day |

## The tables

| Domain | Table | What it holds | Written by | Kept |
|---|---|---|---|---|
| reference | `properties` | the property (`gc8`) and its time zone | migration | — |
| | `roles`, `room_statuses`, `services` | vocabularies with EN/ES labels | migration | — |
| | `rooms` | every room code: building, level, type | seed from `property_map.py` | — |
| people | `people` | one row per person: HotSOS name and id, job, language, on roster, left | Admin, roster sync | — |
| | `person_aliases` | spellings the sheets use → person | Staff names page | — |
| access | `accounts` | sign-in: username, password hash, role, person, work e-mail (M365 later) | Admin | — |
| | `sessions` | hashed session tokens, 30 days | sign-in | until expiry |
| | `sign_in_events` | every attempt and outcome; drives lockout and the Admin history | sign-in | 180 days |
| | `account_prefs` | "seen up to" markers, small per-account state | the app | — |
| | `push_subscriptions` | Web Push endpoints per account | the app | until refused |
| staffing | `sheet_imports` | each staff-schedule read: file, hash, who, summary (not the file) | office PC | 2 years |
| | `shifts` | a person's day: sheet value, manager override, effective value | import, managers | 2 years |
| | `shift_changes` | what changed between imports (the "your schedule changed" notice) | import | 90 days |
| the day | `day_plans` | each Generate/5 AM build as a new version; never edited | build, Generate | 1 year, then archive |
| | `assignments` | who has which room now (from the plan, then HotSOS and Reassign) | build, mirror, Reassign | 1 year |
| | `room_state` | a room's status now | mirror, phones | 1 year |
| | `room_events` | every status change, move, note and desk mark | same writers | 1 year |
| | `desk_marks` | departed / late checkout (with time) | front desk | 1 year |
| | `blocked_rooms`, `duties`, `day_rules` | blocks, weekend duties, a manager's rules for a day | managers | 1 year |
| | `checklist_questions`, `inspections`, `inspection_answers` | RQS scoring (docs/inspection-scoring.md) | RQS | 2 years |
| outside data | `ssrs_days` | the SSRS dashboard as read | office PC | 7 days |
| | `forecasts`, `prereg_lists` | SSRS forecast; the desk's Pre-Reg list (no guest names) | office PC | 30 days |
| | `report_cache` | derived report figures; always rebuildable | reports | rebuilt |
| operations | `agents` | each PC: role, key, version, heartbeat, status | agents | — |
| | `jobs` | queued work and its result (push, build, Generate, …) | app, agents | 90 days |
| | `agent_events` | an agent's log lines worth keeping | agents | 30 days |
| | `notifications_sent` | once-a-day sends (Teams notes, evening preview) | agents | 90 days |
| | `settings` | real configuration only | Admin | — |
| | `usage_daily` | requests, rows read and written per client per day | cron meter | 1 year |
| | `audit_log` | who changed what in Admin | the app | 2 years |

Retention is enforced by the nightly cron, which archives before it deletes
where the table says "then archive".

## Where today's data goes

`app_settings` holds 86 kinds of rows. Each one's new home:

| Today (v1) | v2 |
|---|---|
| `app_users`, `account_links`, `account_roles` | `accounts` (+ `people` link) |
| `session_<hash>` (302 rows) | `sessions` |
| `login_events`, the lockout counters | `sign_in_events` |
| `lang_<user>`, `staffchg_seen_<user>`, `noteseen_<user>`, `mq_<user>` | `accounts.language`, `account_prefs` |
| `staff_directory`, `hotsos_names`, `hotsos_attendants`, `staff_left`, `roster` | `people`, `person_aliases` |
| `staffweek_<date>` (95 weeks, 2.7 MB), `staffsched_overrides` | `shifts` |
| `staffsched_file` (2.1 MB workbook), `staffsched_fileinfo`, `staffsched_meta`, `weeks_version`, `staffsched_autoapply` | `sheet_imports` (+ `settings`) |
| `staff_changes` | `shift_changes` |
| `schedule_full` and `schedule_log` (the same plan twice) | `day_plans` |
| the plan's charts, `sheet_unplaced` | `assignments` (unplaced = no housekeeper) |
| `room_status` | `room_state` + `room_events` |
| `fdmark_<date>_<room>`, `fdsheet_<date>` | `desk_marks` + `room_events` |
| `blocked_rooms`, `duties_<date>`, `dutydone_*`, `borrow_off`, `light_duty` | `blocked_rooms`, `duties`, `day_rules` |
| `room_scores_<date>`, `score_pilot_cfg` | `inspections`, `inspection_answers`, `settings` |
| `ssrs_rooms_<date>`, `ssrs_forecast`, `prereg` | `ssrs_days`, `forecasts`, `prereg_lists` |
| `report_days_<month>`, `fair_share` | `report_cache` |
| `hotsos_push_request` / `_result`, `day_rooms_request` / `_result`, `report_sync_request`, `ssrs_forecast_request`, `cred_req_<pc>`, `daily_build_status`, `hotsos_inspect_queue`, `hotsos_last_result` | `jobs` |
| `hotsos_agent_heartbeat`, `agent_pubkey_<pc>`, `agent_health`, `watchdog_status`, `roster_sync_status`, `hotsos_status_sync`, `cred_status_*` | `agents` (+ `status` JSON) |
| `agent_events` | `agent_events` |
| `teams_notes_sent`, `evening_preview_sent` | `notifications_sent` |
| `usage_<month>_<source>`, `usage_memory_app`, `freetier_status` | `usage_daily` |
| `teams_webhooks`, `hotsos_inspect_cfg`, `hotsos_auto_push`, `fc_mode`, `room_status_source`, `sheet_follow`, `report_sync`, `arrival_fetch`, `gh_watchdog`, `hotsos_truth_since` | `settings` |
| test leftovers (`lang___pwtest_es__`, `noteseen_verifyuser`) | dropped |

## Moving a domain onto v2

Each domain (accounts and sessions first) follows the same night-time steps:

1. A migration script copies the domain's v1 rows into v2 and checks counts.
2. `db.py`'s functions for that domain read and write v2 (the Worker already
   does); the v1 rows are left untouched.
3. Both PCs pull and restart; Streamlit restarts.
4. After two weeks clean, a migration drops the v1 table or keys.

Undo at step 2–3: revert the commit; the v1 rows never stopped being valid
for that window, and anything written to v2 is copied back by the same
script run in reverse.

## Sign-in

Passwords stay as today's `pbkdf2$200000$<salt>$<hex>`. A Worker can't run
200,000 PBKDF2 rounds (it caps at 100,000, with 10 ms of CPU), so the browser
derives the key with the account's salt and rounds (fetched first; an unknown
user gets a stable fake salt so the answer doesn't reveal who exists), and
the Worker compares the result in constant time. Lockout and history come from
`sign_in_events`. Once Streamlit is off, the stored value becomes
SHA-256(derived key), so a copy of the table is no longer enough to sign in.

## Backups

- **D1 Time Travel**: restore to any minute of the last 7 days
  (`wrangler d1 time-travel restore bgv --timestamp=...`).
- **Nightly export**: the cron exports tables past their retention to the
  App Archive before deleting them; a weekly full export goes there too.

## Checking a query's cost

```bash
npx wrangler d1 execute bgv --remote --command "EXPLAIN QUERY PLAN <sql>"
```

A plan line `SCAN <table>` on anything but a lookup table is a bug to fix
with an index or a narrower `WHERE`. `meta.rows_read` in any query's result
gives the exact cost.
