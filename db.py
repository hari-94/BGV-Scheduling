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
    today = str(date.today())
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
    payload = json.dumps({"hk_roster": hk_roster, "insp_roster": insp_roster}, default=str)
    try:
        _client().table("schedule_full").upsert(
            {"date": "roster", "payload": payload},
            on_conflict="date"
        ).execute()
    except Exception as ex:
        print(f"[db] save_roster error: {ex}")
        raise

def load_roster() -> dict | None:
    """Load the persisted standing rosters. Returns
    {'hk_roster':..., 'insp_roster':...} or None if none saved yet."""
    try:
        r = (_client().table("schedule_full")
             .select("*")
             .eq("date", "roster")
             .limit(1)
             .execute())
        rows = r.data or []
        if not rows:
            return None
        payload = rows[0]["payload"]
        return json.loads(payload) if isinstance(payload, str) else payload
    except Exception as ex:
        print(f"[db] load_roster error: {ex}")
        return None

def load_full_schedule(date_str: str = None) -> dict | None:
    """
    Load the full schedule for a given date (defaults to today).
    Returns None if no schedule exists for that date.
    """
    if date_str is None:
        date_str = str(date.today())
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
             .eq("date", str(date.today()))
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
    today = snapshot.get("date", str(date.today()))
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
        date_str = str(date.today())
    try:
        r = (_client().table("room_status")
             .select("*")
             .eq("date", date_str)
             .execute())
        return {row["room"]: row for row in (r.data or [])}
    except Exception as ex:
        print(f"[db] get_room_statuses error: {ex}")
        return {}

def upsert_room_status(room: str, fields: dict, date_str: str = None):
    """
    Upsert a room's status record for today.
    fields can include: status, housekeeper, inspector, group_label,
    started_at, cleaned_at, inspected_at, marked_clean_at, notes,
    swapped_from, updated_by
    """
    if date_str is None:
        date_str = str(date.today())
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
        date_str = str(date.today())
    rows = [{"date": date_str, **r} for r in records]
    try:
        _client().table("room_status").upsert(
            rows, on_conflict="date,room"
        ).execute()
    except Exception as ex:
        print(f"[db] bulk_upsert_room_statuses error: {ex}")
        raise
