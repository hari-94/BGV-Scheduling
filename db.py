"""
db.py — Supabase database wrapper
All reads/writes go through this module.
Tables (auto-created on first use):
  schedule_log  : daily schedule snapshots (shared across all users)
  app_users     : user accounts with roles
"""
# Guard against circular imports — this module must never import from
# cleaning_scheduler.py or auth.py at module level.
import os, json, hashlib, secrets
import clock
from datetime import datetime, date

# Ensure this module is fully initialized before any function is called.
# Streamlit sometimes partially loads modules during hot-reload; this flag
# lets callers detect and retry if needed.
_MODULE_READY = True

# ── Supabase client (lazy init) ───────────────────────────────────────────────
_sb = None

def _get_credentials():
    """
    Get Supabase credentials.
    Order: env vars → secrets.toml (multiple locations) → st.secrets (last resort).
    Never calls any Streamlit command — safe to call before set_page_config.
    """
    url, key = "", ""

    # Method 1: Environment variables (works everywhere)
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()

    # Method 2: Read secrets.toml directly (local dev + Streamlit Cloud)
    if not url:
        try:
            import pathlib
            candidates = [
                pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml",
                pathlib.Path.cwd() / ".streamlit" / "secrets.toml",
                pathlib.Path.home() / ".streamlit" / "secrets.toml",
            ]
            for p in candidates:
                if p.exists():
                    text = p.read_text(encoding="utf-8")
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith("SUPABASE_URL"):
                            url = line.split("=",1)[1].strip().strip('"\'')
                        elif line.startswith("SUPABASE_KEY"):
                            key = line.split("=",1)[1].strip().strip('"\'')
                    if url:
                        break
        except Exception as _e:
            pass

    # Method 3: st.secrets (Streamlit Cloud — only after set_page_config has run)
    if not url:
        try:
            import streamlit as _st
            url = str(_st.secrets.get("SUPABASE_URL","") or "").strip()
            key = str(_st.secrets.get("SUPABASE_KEY","") or "").strip()
        except Exception:
            pass

    return url, key


def _client():
    global _sb
    if _sb is None:
        from supabase import create_client
        url, key = _get_credentials()
        if not url or not key:
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_KEY.\n\n"
                "On Streamlit Cloud: go to your app → Settings → Secrets and add:\n"
                "  SUPABASE_URL = \"https://xxxx.supabase.co\"\n"
                "  SUPABASE_KEY = \"eyJ...\"\n\n"
                "Locally: add them to .streamlit/secrets.toml"
            )
        _sb = create_client(url, key)
    return _sb

# ════════════════════════════════════════════════════════════════════════════
#  FULL SCHEDULE  (complete groups + rooms, shared across all users)
# ════════════════════════════════════════════════════════════════════════════
def save_full_schedule(data: dict):
    """
    Save the complete schedule for today (groups, rooms, inspectors, HK roster).
    Upserts on date — one record per day.
    """
    today = clock.today_iso()
    payload = json.dumps(data, default=str)
    try:
        _client().table("schedule_full").upsert(
            {"date": today, "payload": payload},
            on_conflict="date"
        ).execute()
    except Exception as ex:
        print(f"[db] save_full_schedule error: {ex}")
        raise

def save_roster(hk_roster: dict, insp_roster: dict):
    """Persist the standing housekeeper + inspector rosters as a single settings
    record, independent of any day's schedule. This is what makes add/remove of
    staff STICK across sessions, reloads, and redeploys — instead of resetting to
    the hard-coded defaults. Stored in schedule_full under the fixed key 'roster'
    (reusing the existing table so no schema change is needed)."""
    try:
        _upsert_key("roster", {"hk_roster": hk_roster, "insp_roster": insp_roster})
    except Exception as ex:
        print(f"[db] save_roster error: {ex}")
        raise

def load_roster() -> dict | None:
    """Load the persisted standing rosters. Returns
    {'hk_roster':..., 'insp_roster':...} or None if none saved yet."""
    try:
        return _load_key("roster")
    except Exception as ex:
        print(f"[db] load_roster error: {ex}")
        return None

# ════════════════════════════════════════════════════════════════════════════
#  STAFF SCHEDULE  (the weekly Schedule.xlsx, parsed and stored week by week)
# ════════════════════════════════════════════════════════════════════════════
# Stored in schedule_full under reserved text keys, the same trick save_roster
# uses — no schema change needed. One row per week keeps each write small and
# lets a re-upload touch only the weeks that actually changed.
STAFF_META_KEY      = "staffsched_meta"
STAFF_OVERRIDE_KEY  = "staffsched_overrides"
STAFF_FILE_KEY      = "staffsched_file"
STAFF_AUTO_KEY      = "staffsched_autoapply"
STAFF_WEEK_PREFIX   = "staffweek_"

SETTINGS_TABLE = "app_settings"

class SettingsTableMissing(RuntimeError):
    """Raised when app_settings has not been created yet."""

def _is_missing_table(ex) -> bool:
    s = str(ex)
    return "app_settings" in s and ("schema cache" in s or "does not exist" in s)

def _upsert_key(key: str, obj) -> None:
    """Write a text-keyed settings row.

    NOT schedule_full — that table's `date` column is a real DATE, so a text
    key like "roster" or "staffweek_2026-08-23" is rejected outright.
    """
    try:
        _client().table(SETTINGS_TABLE).upsert(
            {"key": key, "payload": json.dumps(obj, default=str)},
            on_conflict="key"
        ).execute()
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        raise

def _load_key(key: str):
    try:
        r = (_client().table(SETTINGS_TABLE).select("*")
             .eq("key", key).limit(1).execute())
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        raise
    rows = r.data or []
    if not rows:
        return None
    payload = rows[0]["payload"]
    return json.loads(payload) if isinstance(payload, str) else payload

def _like_keys(prefix: str, with_payload: bool = False):
    """Rows whose key starts with `prefix`.

    Uses PostgREST's '*' wildcard, NOT a literal '%'. A raw '%' goes into the
    query string unescaped and Supabase's edge worker throws on it (HTTP 500,
    Cloudflare 1101) rather than running the query.

    The result is re-filtered in Python because SQL LIKE treats '_' as a
    single-character wildcard, and every prefix here contains one — so
    'staffweek_*' would also match a hypothetical 'staffweekX...' key.
    """
    try:
        r = (_client().table(SETTINGS_TABLE)
             .select("*" if with_payload else "key")
             .like("key", prefix + "*").execute())
        return [row for row in (r.data or [])
                if str(row.get("key", "")).startswith(prefix)]
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        raise

def _delete_key(key: str) -> None:
    try:
        _client().table(SETTINGS_TABLE).delete().eq("key", key).execute()
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        raise

# ASCII only: this string is print()ed to the console, and a Windows terminal
# on the cp1252 code page raises UnicodeEncodeError on characters like an arrow
# -- which would turn a handled error into a crash.
SETUP_HINT = (
    "The 'app_settings' table does not exist yet. Run migration_app_settings.sql "
    "in the Supabase SQL Editor to create it. Until then the staff schedule and "
    "the standing roster cannot be saved."
)

def settings_table_ready() -> bool:
    """True when app_settings exists — lets the UI say so once, clearly."""
    try:
        _client().table(SETTINGS_TABLE).select("key").limit(1).execute()
        return True
    except Exception:
        return False

def save_staff_meta(meta: dict) -> None:
    """Record who uploaded the workbook and when — drives the header stamp."""
    try:
        _upsert_key(STAFF_META_KEY, meta)
    except Exception as ex:
        print(f"[db] save_staff_meta error: {ex}")
        raise

def load_staff_meta() -> dict | None:
    try:
        return _load_key(STAFF_META_KEY)
    except Exception as ex:
        print(f"[db] load_staff_meta error: {ex}")
        return None

def save_staff_week(week_key: str, week: dict) -> None:
    try:
        _upsert_key(STAFF_WEEK_PREFIX + week_key, week)
    except Exception as ex:
        print(f"[db] save_staff_week error: {ex}")
        raise

def load_staff_week(week_key: str) -> dict | None:
    try:
        return _load_key(STAFF_WEEK_PREFIX + week_key)
    except Exception as ex:
        print(f"[db] load_staff_week error: {ex}")
        return None

def load_staff_weeks() -> dict:
    """Every stored week, keyed by its Sunday ISO date."""
    try:
        out = {}
        for row in _like_keys(STAFF_WEEK_PREFIX, with_payload=True):
            payload = row["payload"]
            out[row["key"][len(STAFF_WEEK_PREFIX):]] = (
                json.loads(payload) if isinstance(payload, str) else payload)
        return out
    except Exception as ex:
        print(f"[db] load_staff_weeks error: {ex}")
        return {}

def staff_week_keys() -> list:
    """Just the stored week ids — cheaper than pulling every payload."""
    try:
        return sorted(row["key"][len(STAFF_WEEK_PREFIX):]
                      for row in _like_keys(STAFF_WEEK_PREFIX))
    except Exception as ex:
        print(f"[db] staff_week_keys error: {ex}")
        return []

def delete_staff_week(week_key: str) -> None:
    try:
        _delete_key(STAFF_WEEK_PREFIX + week_key)
    except Exception as ex:
        print(f"[db] delete_staff_week error: {ex}")

def save_staff_overrides(overrides: dict) -> None:
    """In-app cell edits, keyed 'week|name|date'. These outrank the workbook."""
    try:
        _upsert_key(STAFF_OVERRIDE_KEY, overrides)
    except Exception as ex:
        print(f"[db] save_staff_overrides error: {ex}")
        raise

def load_staff_overrides() -> dict:
    try:
        return _load_key(STAFF_OVERRIDE_KEY) or {}
    except Exception as ex:
        print(f"[db] load_staff_overrides error: {ex}")
        return {}

def save_staff_file(data: bytes, file_name: str = "") -> None:
    """Keep the uploaded workbook itself, so exporting edits back to Excel never
    depends on someone having re-uploaded the file in this session.

    Base64 inside the JSON payload — the table only stores text. Read on demand
    (export only), never on page load, so the size costs nothing day to day.
    """
    import base64
    try:
        _upsert_key(STAFF_FILE_KEY, {
            "file_name": file_name,
            "size": len(data),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "b64": base64.b64encode(data).decode("ascii"),
        })
    except Exception as ex:
        print(f"[db] save_staff_file error: {ex}")
        raise

def load_staff_file() -> tuple[bytes, dict] | tuple[None, dict]:
    """Return (workbook_bytes, info). Bytes are None when nothing is stored."""
    import base64
    try:
        rec = _load_key(STAFF_FILE_KEY)
        if not rec or not rec.get("b64"):
            return None, {}
        info = {k: v for k, v in rec.items() if k != "b64"}
        return base64.b64decode(rec["b64"]), info
    except Exception as ex:
        print(f"[db] load_staff_file error: {ex}")
        return None, {}

def staff_file_info() -> dict:
    """Just the metadata about the stored workbook — avoids pulling the blob."""
    try:
        rec = _load_key(STAFF_FILE_KEY) or {}
        return {k: v for k, v in rec.items() if k != "b64"}
    except Exception as ex:
        print(f"[db] staff_file_info error: {ex}")
        return {}

def save_custom_options(opts: dict) -> None:
    """Extra dropdown choices a manager typed in, keyed by role."""
    try:
        _upsert_key("staffsched_options", opts)
    except Exception as ex:
        print(f"[db] save_custom_options error: {ex}")
        raise

def load_custom_options() -> dict:
    try:
        return _load_key("staffsched_options") or {}
    except Exception as ex:
        print(f"[db] load_custom_options error: {ex}")
        return {}

def save_session(token_hash: str, rec: dict) -> None:
    """Store a signed-in session. Only the token's hash is ever written."""
    _upsert_key(f"session_{token_hash}", rec)

def load_session(token_hash: str) -> dict | None:
    return _load_key(f"session_{token_hash}")

def delete_session(token_hash: str) -> None:
    try:
        _delete_key(f"session_{token_hash}")
    except Exception as ex:
        print(f"[db] delete_session error: {ex}")

def save_note_seen(username: str, seen: dict) -> None:
    """Remember which notes this person has read, as {room: the words}."""
    try:
        _upsert_key(f"noteseen_{username}", {"seen": seen})
    except Exception as ex:
        print(f"[db] save_note_seen error: {ex}")

def load_note_seen(username: str) -> dict:
    try:
        return (_load_key(f"noteseen_{username}") or {}).get("seen") or {}
    except Exception as ex:
        print(f"[db] load_note_seen error: {ex}")
        return {}

def save_user_lang(username: str, code: str) -> None:
    """Remember which language someone reads the app in."""
    try:
        _upsert_key(f"lang_{username}", {"lang": code})
    except Exception as ex:
        print(f"[db] save_user_lang error: {ex}")

def load_user_lang(username: str) -> str | None:
    try:
        rec = _load_key(f"lang_{username}") or {}
        return rec.get("lang")
    except Exception as ex:
        print(f"[db] load_user_lang error: {ex}")
        return None

def load_autoapply() -> dict:
    """Which date's roster has already been auto-applied from the schedule."""
    try:
        return _load_key(STAFF_AUTO_KEY) or {}
    except Exception as ex:
        print(f"[db] load_autoapply error: {ex}")
        return {}

def save_autoapply(info: dict) -> None:
    try:
        _upsert_key(STAFF_AUTO_KEY, info)
    except Exception as ex:
        print(f"[db] save_autoapply error: {ex}")

def load_full_schedule(date_str: str = None) -> dict | None:
    """
    Load the full schedule for a given date (defaults to today).
    Returns None if no schedule exists for that date.
    """
    if date_str is None:
        date_str = clock.today_iso()
    try:
        r = (_client().table("schedule_full")
             .select("*")
             .eq("date", date_str)
             .limit(1)
             .execute())
        rows = r.data or []
        if not rows:
            return None
        payload = rows[0]["payload"]
        return json.loads(payload) if isinstance(payload, str) else payload
    except Exception as ex:
        print(f"[db] load_full_schedule error: {ex}")
        return None

def schedule_exists_today() -> bool:
    """Check if a full schedule already exists for today."""
    try:
        r = (_client().table("schedule_full")
             .select("date")
             .eq("date", clock.today_iso())
             .limit(1)
             .execute())
        return bool(r.data)
    except Exception:
        return False
def load_log() -> list:
    """Return all daily snapshots sorted by date desc."""
    try:
        r = _client().table("schedule_log").select("*").order("date", desc=True).execute()
        rows = r.data or []
        # payload column is stored as JSON text
        return [json.loads(row["payload"]) if isinstance(row["payload"],str)
                else row["payload"] for row in rows]
    except Exception as ex:
        print(f"[db] load_log error: {ex}")
        return []

def save_snapshot(snapshot: dict):
    """Upsert today's snapshot (keyed on date)."""
    today = snapshot.get("date", clock.today_iso())
    payload = json.dumps(snapshot)
    try:
        _client().table("schedule_log").upsert(
            {"date": today, "payload": payload},
            on_conflict="date"
        ).execute()
    except Exception as ex:
        print(f"[db] save_snapshot error: {ex}")

def delete_snapshot(date_str: str):
    try:
        _client().table("schedule_log").delete().eq("date", date_str).execute()
    except Exception as ex:
        print(f"[db] delete_snapshot error: {ex}")

# ════════════════════════════════════════════════════════════════════════════
#  USAGE / LOGIN TRACKING
#  Records who signs in and when, so admins can see who is using the app.
#  Requires a `login_events` table (see supabase_setup.sql).
# ════════════════════════════════════════════════════════════════════════════
def log_login(username: str, display_name: str = "", role: str = ""):
    """Record a login event with a UTC timestamp. Best-effort — never blocks the
    login if the write fails (e.g. table missing or DB unreachable)."""
    from datetime import datetime, timezone
    try:
        _client().table("login_events").insert({
            "username":     username,
            "display_name": display_name or username,
            "role":         role,
            "ts":           datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as ex:
        print(f"[db] log_login error: {ex}")

def load_login_events(limit: int = 200) -> list:
    """Return the most recent login events, newest first."""
    try:
        r = (_client().table("login_events")
             .select("*")
             .order("ts", desc=True)
             .limit(limit)
             .execute())
        return r.data or []
    except Exception as ex:
        print(f"[db] load_login_events error: {ex}")
        return []

def login_summary(limit: int = 1000) -> list:
    """Per-user rollup: total logins and the most recent login time. Newest
    activity first. Computed from the recent event rows."""
    events = load_login_events(limit)
    by_user = {}
    for e in events:
        u = e.get("username", "?")
        rec = by_user.setdefault(u, {
            "username":     u,
            "display_name": e.get("display_name") or u,
            "role":         e.get("role", ""),
            "count":        0,
            "last_ts":      "",
        })
        rec["count"] += 1
        ts = e.get("ts", "")
        if ts > rec["last_ts"]:
            rec["last_ts"] = ts
            rec["display_name"] = e.get("display_name") or u
            rec["role"] = e.get("role", rec["role"])
    return sorted(by_user.values(), key=lambda r: r["last_ts"], reverse=True)

# ════════════════════════════════════════════════════════════════════════════
#  USER MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════
ROLES = ["admin", "rqs", "housekeeper"]

def _hash_pw(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

def _check_pw(password: str, stored: str) -> bool:
    """
    Verify password against stored hash.
    Supports two formats:
      1. Plain sha256 hex (from seed SQL): 64-char hex string
      2. Salted format (from create_user): "salt:sha256(salt+pw)"
    """
    if not stored:
        return False
    try:
        # Format 1: plain sha256 (no colon, 64 hex chars) — used by seed SQL
        if ":" not in stored or len(stored) == 64:
            import hashlib as _hl
            return _hl.sha256(password.encode()).hexdigest() == stored
        # Format 2: salted "salt:hash"
        salt, h = stored.split(":", 1)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == h
    except Exception:
        return False

def load_users() -> list:
    """Return all users (without password hashes)."""
    try:
        r = _client().table("app_users").select("id,username,role,created_at,last_login").execute()
        return r.data or []
    except Exception as ex:
        print(f"[db] load_users error: {ex}")
        return []

def get_user(username: str) -> dict | None:
    """Return full user row including password_hash."""
    try:
        r = (_client().table("app_users")
             .select("*")
             .eq("username", username.strip().lower())
             .execute())
        rows = r.data or []
        return rows[0] if rows else None
    except Exception as ex:
        print(f"[db] get_user error: {ex}")
        return None

def create_user(username: str, password: str, role: str) -> tuple[bool, str]:
    """Create a new user. Returns (success, message)."""
    uname = username.strip().lower()
    if not uname:
        return False, "Username cannot be empty."
    if role not in ROLES:
        return False, f"Role must be one of: {', '.join(ROLES)}"
    if get_user(uname):
        return False, f"User '{uname}' already exists."
    pw_hash = _hash_pw(password)
    try:
        _client().table("app_users").insert({
            "username":     uname,
            "password_hash":pw_hash,
            "role":         role,
            "created_at":   datetime.utcnow().isoformat(),
        }).execute()
        return True, f"User '{uname}' created with role '{role}'."
    except Exception as ex:
        return False, str(ex)

def authenticate(username: str, password: str) -> dict | None:
    """Verify credentials. Returns user dict on success, None on failure."""
    user = get_user(username)
    if not user:
        return None
    if not _check_pw(password, user.get("password_hash","")):
        return None
    # update last_login
    try:
        _client().table("app_users").update(
            {"last_login": datetime.utcnow().isoformat()}
        ).eq("username", user["username"]).execute()
    except Exception:
        pass
    return user

def update_password(username: str, new_password: str) -> tuple[bool, str]:
    uname = username.strip().lower()
    pw_hash = _hash_pw(new_password)
    try:
        _client().table("app_users").update(
            {"password_hash": pw_hash}
        ).eq("username", uname).execute()
        return True, "Password updated."
    except Exception as ex:
        return False, str(ex)

def update_role(username: str, new_role: str) -> tuple[bool, str]:
    if new_role not in ROLES:
        return False, f"Invalid role. Choose: {', '.join(ROLES)}"
    try:
        _client().table("app_users").update(
            {"role": new_role}
        ).eq("username", username.strip().lower()).execute()
        return True, f"Role updated to '{new_role}'."
    except Exception as ex:
        return False, str(ex)

def delete_user(username: str) -> tuple[bool, str]:
    try:
        _client().table("app_users").delete().eq("username", username.strip().lower()).execute()
        return True, f"User '{username}' deleted."
    except Exception as ex:
        return False, str(ex)

def ensure_admin_exists():
    """Create a default admin if no users exist yet."""
    try:
        r = _client().table("app_users").select("id").limit(1).execute()
        if not (r.data or []):
            ok, msg = create_user("admin", "admin1234", "admin")
            if ok:
                print("[db] Default admin created. Username: admin | Password: admin1234")
    except Exception as ex:
        print(f"[db] ensure_admin_exists error: {ex}")

# ════════════════════════════════════════════════════════════════════════════
#  ROOM STATUS  (live tracking — cleaning/inspection progress per room)
# ════════════════════════════════════════════════════════════════════════════
def get_room_statuses(date_str: str = None) -> dict:
    """
    Load all room statuses for a given date.
    Returns dict keyed by room number: {room: status_record}
    """
    if date_str is None:
        date_str = clock.today_iso()
    try:
        r = (_client().table("room_status")
             .select("*")
             .eq("date", date_str)
             .execute())
        return {row["room"]: row for row in (r.data or [])}
    except Exception as ex:
        print(f"[db] get_room_statuses error: {ex}")
        return {}

def all_known_rooms() -> list:
    """Every room code that has ever appeared on a chart.

    The property has no room table — the inventory is whatever the morning
    sheets have carried. Reading every stored day is the only way to get the
    whole building, and it is stable enough to cache for an hour: 245 rooms,
    unchanged across all the days on record.
    """
    try:
        r = _client().table("schedule_full").select("payload").execute()
        rooms = set()
        for row in (r.data or []):
            p = row.get("payload")
            if isinstance(p, str):
                p = json.loads(p)
            for g in ((p or {}).get("groups_data") or []):
                for rm in (g.get("rooms") or []):
                    code = str(rm.get("room", "")).strip().upper()
                    if code:
                        rooms.add(code)
        return sorted(rooms)
    except Exception as ex:
        print(f"[db] all_known_rooms error: {ex}")
        return []

def upsert_room_status(room: str, fields: dict, date_str: str = None):
    """
    Upsert a room's status record for today.
    fields can include: status, housekeeper, inspector, group_label,
    started_at, cleaned_at, inspected_at, marked_clean_at, notes,
    swapped_from, updated_by
    """
    if date_str is None:
        date_str = clock.today_iso()
    record = {"date": date_str, "room": room, **fields}
    try:
        _client().table("room_status").upsert(
            record, on_conflict="date,room"
        ).execute()
    except Exception as ex:
        print(f"[db] upsert_room_status error: {ex}")
        raise

def bulk_upsert_room_statuses(records: list, date_str: str = None):
    """
    Bulk upsert a list of room status records.
    Each record must have at least 'room' key.
    """
    if date_str is None:
        date_str = clock.today_iso()
    rows = [{"date": date_str, **r} for r in records]
    try:
        _client().table("room_status").upsert(
            rows, on_conflict="date,room"
        ).execute()
    except Exception as ex:
        print(f"[db] bulk_upsert_room_statuses error: {ex}")
        raise
