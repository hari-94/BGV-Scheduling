"""
db.py — Supabase database wrapper
All reads/writes go through this module.
Tables (auto-created on first use):
  schedule_log  : daily schedule snapshots (shared across all users)
  app_users     : user accounts with roles
"""
# Guard against circular imports — this module must never import from
# cleaning_scheduler.py or auth.py at module level.
import os, json, hashlib, secrets, time as _time
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
    _SCHED_CACHE.pop(today, None)
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
    # One name per person, the full HotSOS form: a session that loaded the
    # roster before a rename would otherwise save the old spellings back.
    try:
        import staff_names
        table = staff_names.aliases()
        hk_roster = staff_names.canon_roster(hk_roster, table)
        insp_roster = staff_names.canon_roster(insp_roster, table)
    except Exception as ex:
        print(f"[db] save_roster: names not canonicalised: {ex}")
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
STAFF_FILEINFO_KEY  = "staffsched_fileinfo"

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
    _KEY_CACHE.pop(key, None)
    try:
        _client().table(SETTINGS_TABLE).upsert(
            {"key": key, "payload": json.dumps(obj, default=str)},
            on_conflict="key"
        ).execute()
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        raise

def _load_key_raw(key: str):
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
    _KEY_CACHE.pop(key, None)
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

#: A tiny marker that changes whenever any week is written or deleted -- by
#: this process or another (the office PC's roster sync writes weeks the Cloud
#: app has cached). Not "staffweek_..." or it would be read as a week.
WEEKS_VERSION_KEY = "weeks_version"


def _weeks_bump() -> None:
    try:
        _upsert_key(WEEKS_VERSION_KEY, {"v": secrets.token_hex(8), "at": clock.stamp()})
    except Exception as ex:
        print(f"[db] weeks version not bumped: {ex}")


def save_staff_week(week_key: str, week: dict) -> None:
    try:
        _upsert_key(STAFF_WEEK_PREFIX + week_key, week)
        _weeks_forget()          # the batch above is now a week out of date
        _weeks_bump()
    except Exception as ex:
        print(f"[db] save_staff_week error: {ex}")
        raise

#: Every stored week, read in one query and reused for a few seconds.
#:
#: The roster page asks for weeks one at a time and asks a great many times --
#: 175 separate reads on a cold load, measured -- and each one is its own round
#: trip to Supabase at about eighty milliseconds. That was eight of the page's
#: nine seconds. The rows are small and there are eighty of them, so fetching
#: the lot once and answering from that is both faster and less load on the
#: database. Any write here empties it, so a save is visible immediately.
_WEEKS = {"at": 0.0, "rows": None}
_WEEKS_TTL = 15.0

def _weeks_all(force: bool = False) -> dict:
    if (not force and _WEEKS["rows"] is not None
            and _time.time() - _WEEKS["at"] < _WEEKS_TTL):
        return _WEEKS["rows"]
    # Past the few seconds: ask the version marker (a few bytes) whether any
    # week changed, rather than downloading all of them (2.3 MB, 300 KB on the
    # wire) again. The Forecast page asked every 10 seconds while open --
    # ~70 MB an hour, enough to use up the free plan's monthly transfer.
    try:
        v = (_load_key(WEEKS_VERSION_KEY) or {}).get("v")
    except Exception:
        v = None
    if not force and _WEEKS["rows"] is not None and v and v == _WEEKS.get("v"):
        _WEEKS["at"] = _time.time()
        return _WEEKS["rows"]
    # Something changed. Ask which weeks (key and stamp only, a few KB), then
    # fetch just those: a save touches one or two of the ~90 weeks, and
    # downloading all of them each time (2.4 MB, ~600 KB on the wire) was
    # 15% of the month's data sent (Oct 2026).
    try:
        stamps = _week_stamps()
        old = _WEEKS.get("stamps") or {}
        have = _WEEKS["rows"] or {}
        changed = [k for k, t in stamps.items() if old.get(k) != t or k[len(STAFF_WEEK_PREFIX):] not in have]
        out = {wk: have[wk] for wk in (k[len(STAFF_WEEK_PREFIX):] for k in stamps) if wk in have}
        for i in range(0, len(changed), 40):
            for key, payload in _load_keys(changed[i:i + 40]).items():
                out[key[len(STAFF_WEEK_PREFIX):]] = payload
    except Exception as ex:
        print(f"[db] could not read the weeks: {ex}")
        return _WEEKS["rows"] or {}
    _WEEKS["rows"], _WEEKS["at"], _WEEKS["v"], _WEEKS["stamps"] = out, _time.time(), v, stamps
    return out


def _weeks_forget() -> None:
    # Check again on the next read; the delta read then fetches only the
    # weeks whose rows changed (or drops the ones that were deleted).
    _WEEKS["at"], _WEEKS["v"] = 0.0, None


def load_staff_week(week_key: str) -> dict | None:
    return _weeks_all().get(week_key)

def load_staff_weeks() -> dict:
    """Every stored week, keyed by its Sunday ISO date."""
    return dict(_weeks_all())

def staff_week_keys() -> list:
    """Just the stored week ids — cheaper than pulling every payload."""
    return sorted(_weeks_all())

def delete_staff_week(week_key: str) -> None:
    try:
        _delete_key(STAFF_WEEK_PREFIX + week_key)
        _weeks_forget()
        _weeks_bump()
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
    info = {
        "file_name": file_name,
        "size": len(data),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        _upsert_key(STAFF_FILE_KEY, dict(info, b64=base64.b64encode(data).decode("ascii")))
        # The same three facts again, on their own, so anything that only wants
        # the name and the date does not drag the workbook across the wire.
        _upsert_key(STAFF_FILEINFO_KEY, info)
        _FILE["rec"] = None
    except Exception as ex:
        print(f"[db] save_staff_file error: {ex}")
        raise

#: The stored workbook, held for a minute after it is read.
#:
#: It is a base64 blob and the real one is 1.8 MB. The roster page asked for it
#: five times a load -- three of those only wanted the file's name -- so nine
#: megabytes crossed the wire to print one line of text.
_FILE = {"at": 0.0, "rec": None}
_FILE_TTL = 60.0


def _file_rec():
    if _FILE["rec"] is not None and _time.time() - _FILE["at"] < _FILE_TTL:
        return _FILE["rec"]
    try:
        rec = _load_key(STAFF_FILE_KEY) or {}
    except Exception as ex:
        print(f"[db] load_staff_file error: {ex}")
        return _FILE["rec"] or {}
    _FILE["rec"], _FILE["at"] = rec, _time.time()
    return rec


def load_staff_file() -> tuple[bytes, dict] | tuple[None, dict]:
    """Return (workbook_bytes, info). Bytes are None when nothing is stored."""
    import base64
    rec = _file_rec()
    if not rec or not rec.get("b64"):
        return None, {}
    info = {k: v for k, v in rec.items() if k != "b64"}
    try:
        return base64.b64decode(rec["b64"]), info
    except Exception as ex:
        print(f"[db] could not decode the stored workbook: {ex}")
        return None, info

def staff_file_info() -> dict:
    """Just the metadata about the stored workbook — really without the blob.

    It used to say that and then read the whole record anyway. The three facts
    are written to their own key now; a workbook stored before that falls back
    to the big record once and writes the small one on its way past.
    """
    try:
        info = _load_key(STAFF_FILEINFO_KEY)
        if info:
            return info
    except Exception as ex:
        print(f"[db] staff_file_info error: {ex}")
    rec = _file_rec() or {}
    info = {k: v for k, v in rec.items() if k != "b64"}
    if info:
        try:
            _upsert_key(STAFF_FILEINFO_KEY, info)
        except Exception:
            pass
    return info

FC_MODE_KEY = "fc_mode"

def save_fc_mode(mode: str) -> None:
    """Remember how the day should be split. Shared, not per person — the
    schedule is one schedule, so the choice belongs to the property."""
    try:
        _upsert_key(FC_MODE_KEY, {"mode": mode})
    except Exception as ex:
        print(f"[db] save_fc_mode error: {ex}")

def load_fc_mode() -> str:
    try:
        rec = _load_key(FC_MODE_KEY) or {}
        return str(rec.get("mode", "") or "")
    except Exception as ex:
        print(f"[db] load_fc_mode error: {ex}")
        return ""

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

def _load_full_schedule_raw(date_str: str = None) -> dict | None:
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
ROLES = ["admin", "rqs", "housekeeper", "houseperson"]

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

def verify_password(username: str, password: str) -> bool:
    """Is this the person's current password? Nothing is written.

    Deliberately not `authenticate`: that stamps last_login, which is right for
    a sign-in and wrong for confirming who you are before changing something.
    Using it here would show a password change as a sign-in on the activity
    report.
    """
    user = get_user(username)
    if not user:
        return False
    return _check_pw(password, user.get("password_hash", ""))

def delete_other_sessions(username: str, keep_hash: str = "") -> int:
    """End this person's sessions everywhere except the browser asking.

    Changing a password has to reach the other devices, or somebody who
    changed theirs because it was known is no safer than before. Returns how
    many were ended, for the message.
    """
    uname = (username or "").strip().lower()
    if not uname:
        return 0
    try:
        r = (_client().table(SETTINGS_TABLE).select("key,payload")
             .like("key", "session_%").execute())
    except Exception as ex:
        print(f"[db] could not list sessions: {ex}")
        return 0
    gone = 0
    for row in (r.data or []):
        key = row.get("key", "")
        if key == f"session_{keep_hash}":
            continue
        payload = row.get("payload")
        try:
            rec = json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            continue
        if (rec or {}).get("username", "").strip().lower() != uname:
            continue
        try:
            _delete_key(key)
            gone += 1
        except Exception as ex:
            print(f"[db] could not end session {key}: {ex}")
    return gone

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
def _get_room_statuses_raw(date_str: str = None) -> dict:
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

def load_schedule_history() -> list:
    """Every stored day's charts: [{"date": ..., "groups_data": [...]}, ...].

    The dashboard used to read only the snapshot log, which records what was
    *assigned* — rooms and minutes per person — and nothing about the rooms
    themselves. Everything worth charting (service, building, room minutes,
    late checkouts, who inspected what) is in the schedule itself, so it is
    read whole and aggregated in the page.
    """
    try:
        r = (_client().table("schedule_full")
             .select("date,payload")
             .order("date", desc=True)
             .execute())
        out = []
        for row in (r.data or []):
            p = row.get("payload")
            if isinstance(p, str):
                p = json.loads(p)
            gs = (p or {}).get("groups_data") or []
            if gs:
                out.append({"date": row["date"], "groups_data": gs})
        return out
    except Exception as ex:
        print(f"[db] load_schedule_history error: {ex}")
        return []

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
    _STATUS_CACHE.pop(date_str, None)
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
    _STATUS_CACHE.pop(date_str, None)
    try:
        _client().table("room_status").upsert(
            rows, on_conflict="date,room"
        ).execute()
    except Exception as ex:
        print(f"[db] bulk_upsert_room_statuses error: {ex}")
        raise


# ── read only what changed ─────────────────────────────────────────────────────
# The free plan counts every byte Supabase sends (5 GB a month). Most of it went
# on re-reading things that had not changed: the office agent's status mirror
# downloaded the whole day's schedule and every room's status every two
# minutes, and pages that poll did the same every few seconds. All three
# tables stamp updated_at on every write (a trigger -- supabase_setup.sql for
# schedule_full and app_settings; room_status checked against its own rows,
# 39 of 40), so a read first asks for the stamp -- a few bytes -- and
# downloads only when it moved. A write from this process drops its copy, so
# whoever saved sees the save at once.
import copy as _copy

_SCHED_CACHE = {}    # date -> (stamp, schedule)
_STATUS_CACHE = {}   # date -> (stamp, statuses, fetched at)
_KEY_CACHE = {}      # key -> (stamp, payload)
#: room_status is re-read in full at least this often whatever the stamp says,
#: so a write path that ever skipped the trigger could not hide a change for
#: longer than this.
STATUS_RECHECK_SECONDS = 300
#: Days kept per cache. The Report page's Timing tab and the Daily Service
#: picker read past days one by one; a year of them must not pile up in the
#: app's 690 MB.
CACHE_DAYS = 8


def _keep(cache, key, value):
    cache.pop(key, None)
    cache[key] = value                  # most recently used last
    while len(cache) > CACHE_DAYS:
        cache.pop(next(iter(cache)))


#: Settings records large enough, and read often enough, to be worth a stamp
#: check first. Small records are cheaper to just read.
CACHED_KEYS = {"hotsos_last_result", "hotsos_push_result", "ssrs_forecast",
               "hotsos_attendants", "staffsched_file", "roster", "staff_overrides"}


def _stamp_schedule(date_str):
    r = _client().table("schedule_full").select("updated_at").eq("date", date_str).limit(1).execute()
    return (r.data or [{}])[0].get("updated_at") if r.data else None


def _stamp_room_status(date_str):
    r = (_client().table("room_status").select("updated_at", count="exact")
         .eq("date", date_str).order("updated_at", desc=True).limit(1).execute())
    return [r.count, (r.data[0].get("updated_at") if r.data else None)]


def _stamp_key(key: str):
    r = _client().table(SETTINGS_TABLE).select("updated_at").eq("key", key).limit(1).execute()
    return r.data[0].get("updated_at") if r.data else None


def _week_stamps() -> dict:
    """{staffweek_<date>: updated_at} for every stored week -- no payloads."""
    r = (_client().table(SETTINGS_TABLE).select("key,updated_at")
         .like("key", STAFF_WEEK_PREFIX + "*").execute())
    return {row["key"]: row.get("updated_at") for row in (r.data or [])
            if str(row.get("key", "")).startswith(STAFF_WEEK_PREFIX)}


def _load_keys(keys) -> dict:
    """{key: payload} for several settings records in one round trip."""
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        return {}
    r = _client().table(SETTINGS_TABLE).select("key,payload").in_("key", keys).execute()
    out = {}
    for row in r.data or []:
        p = row.get("payload")
        out[row["key"]] = json.loads(p) if isinstance(p, str) else p
    return out


def load_full_schedule(date_str: str = None) -> dict | None:
    """The day's schedule (today by default), downloaded only when it changed."""
    date_str = date_str or clock.today_iso()
    try:
        stamp = _stamp_schedule(date_str)
    except Exception as ex:
        print(f"[db] schedule stamp error: {ex}")
        return _load_full_schedule_raw(date_str)
    if stamp is None:
        _SCHED_CACHE.pop(date_str, None)
        return None
    hit = _SCHED_CACHE.get(date_str)
    if hit and hit[0] == stamp:
        return _copy.deepcopy(hit[1])
    data = _load_full_schedule_raw(date_str)
    if data is not None:
        _keep(_SCHED_CACHE, date_str, (stamp, data))
    return _copy.deepcopy(data)


def get_room_statuses(date_str: str = None) -> dict:
    """Every room's status for a day, downloaded only when a row changed."""
    date_str = date_str or clock.today_iso()
    try:
        stamp = _stamp_room_status(date_str)
    except Exception as ex:
        print(f"[db] room status stamp error: {ex}")
        return _get_room_statuses_raw(date_str)
    hit = _STATUS_CACHE.get(date_str)
    if hit and hit[0] == stamp and _time.time() - hit[2] < STATUS_RECHECK_SECONDS:
        return _copy.deepcopy(hit[1])
    data = _get_room_statuses_raw(date_str)
    _keep(_STATUS_CACHE, date_str, (stamp, data, _time.time()))
    return _copy.deepcopy(data)


def _load_key(key: str):
    if key not in CACHED_KEYS:
        return _load_key_raw(key)
    try:
        stamp = _stamp_key(key)
    except Exception as ex:
        if _is_missing_table(ex):
            raise SettingsTableMissing(SETUP_HINT) from ex
        return _load_key_raw(key)
    if stamp is None:
        _KEY_CACHE.pop(key, None)
        return None
    hit = _KEY_CACHE.get(key)
    if hit and hit[0] == stamp:
        return _copy.deepcopy(hit[1])
    val = _load_key_raw(key)
    _KEY_CACHE[key] = (stamp, val)
    return _copy.deepcopy(val)


# ── one retry for a dropped connection ─────────────────────────────────────────
# Supabase sometimes closes a kept-alive connection under us ("Server
# disconnected", 9 Oct 14:29 -- it failed the agent's loop and the HotSOS
# mirror's pass at the same instant). Asking again once on a fresh
# connection is all it takes; anything else is a real error and is raised.
_TRANSIENT = ("RemoteProtocolError", "ConnectError", "ReadError", "ReadTimeout",
              "ConnectTimeout", "WriteError", "PoolTimeout")


def _retrying(fn):
    import functools

    @functools.wraps(fn)
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as ex:
            if type(ex).__name__ not in _TRANSIENT and not any(
                    t in str(ex) for t in ("Server disconnected", "Connection reset")):
                raise
            _time.sleep(1.0)
            return fn(*a, **k)
    return run


for _name in ("_upsert_key", "_delete_key", "save_full_schedule", "bulk_upsert_room_statuses",
              "upsert_room_status"):
    globals()[_name] = _retrying(globals()[_name])


# ── free-plan meter ───────────────────────────────────────────────────────────
# Every function above that reads over the network reports what it got back
# to freetier's meter (an estimate of the egress the free plan counts). Wrapped
# here, at the bottom, so nothing above has to know.
def _metered(fn):
    import functools
    fn = _retrying(fn)

    @functools.wraps(fn)
    def run(*a, **k):
        out = fn(*a, **k)
        try:
            import freetier
            # The key too, for settings reads: which record is read most.
            # Same names as before the stamp checks, so the Stats page's
            # history lines up: _load_key_raw counts as _load_key, and so on.
            base = fn.__name__.removesuffix("_raw").replace("_get_room", "get_room")                 .replace("_load_full", "load_full")
            arg = a[0] if a else None
            if isinstance(arg, (list, tuple)):
                arg = arg[0] if arg else ""
            name = base + (f":{str(arg)[:24]}" if arg is not None and base in
                           ("_load_key", "_like_keys", "_stamp_key", "_load_keys") else "")
            freetier.count(out, name)
        except Exception:
            pass
        return out
    return run


for _name in ("_load_key_raw", "_like_keys", "all_known_rooms", "_get_room_statuses_raw",
              "get_user", "_load_full_schedule_raw", "load_log", "load_login_events",
              "load_schedule_history", "load_users", "_stamp_schedule", "_stamp_room_status",
              "_stamp_key", "_week_stamps", "_load_keys"):
    globals()[_name] = _metered(globals()[_name])
del _name
