"""
db.py — Supabase database wrapper
All reads/writes go through this module.
Tables (auto-created on first use):
  schedule_log  : daily schedule snapshots (shared across all users)
  app_users     : user accounts with roles
"""
import os, json, hashlib, secrets
from datetime import datetime, date

# ── Supabase client (lazy init) ───────────────────────────────────────────────
_sb = None

def _client():
    global _sb
    if _sb is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL","")
        key = os.environ.get("SUPABASE_KEY","")
        if not url or not key:
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_KEY environment variables.\n"
                "Add them to your .env file or Streamlit secrets.")
        _sb = create_client(url, key)
    return _sb

# ════════════════════════════════════════════════════════════════════════════
#  SCHEDULE LOG
# ════════════════════════════════════════════════════════════════════════════
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
    try:
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
