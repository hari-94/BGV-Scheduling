"""
room_scores.py — a room-quality score the RQS fills in and the housekeeper sees.

The RQS signs a room off and marks points for each section of a rubric; the
score and its breakdown are stored per day in app_settings and shown on the
housekeeper's My Rooms. No HotSOS: the score lives in our app (HotSOS's own
inspection scoring is a separate, admin-configured template on another API
base). Pilot-gated until proven, like the HotSOS inspect push.

    RUBRIC_KEY  {"sections": [{"name", "max"}, ...]}      -- editable; a default
                                                             is used if unset
    CFG_KEY     {"on": bool, "users": [username, ...]}    -- who may score
    room_scores_<date>  {"rooms": {ROOM: {sections, total, max, note,
                                          by, by_name, at}}}

No Streamlit here.
"""
import clock
import db

RUBRIC_KEY = "score_rubric"
CFG_KEY = "score_pilot_cfg"

#: A sensible starting rubric; the RQS/admin can replace it in app_settings.
DEFAULT_SECTIONS = [
    {"name": "Bathroom", "max": 10},
    {"name": "Kitchen", "max": 10},
    {"name": "Bedroom / Living", "max": 10},
    {"name": "Floors (vacuum / mop)", "max": 10},
    {"name": "Dusting & surfaces", "max": 10},
    {"name": "Amenities & setup", "max": 10},
    {"name": "Trash & linens", "max": 10},
]


def _scores_key(date=None) -> str:
    return f"room_scores_{date or clock.today_iso()}"


def rubric() -> dict:
    """{"sections": [{"name","max"}], "max": total} -- stored or the default."""
    r = db._load_key(RUBRIC_KEY) or {}
    secs = r.get("sections") or DEFAULT_SECTIONS
    return {"sections": secs, "max": sum(int(s.get("max", 0) or 0) for s in secs)}


def config() -> dict:
    c = db._load_key(CFG_KEY) or {}
    return {"on": bool(c.get("on")), "users": list(c.get("users") or [])}


def enabled_for(username: str) -> bool:
    c = config()
    return bool(c["on"] and username and username in c["users"])


def set_config(on: bool, users) -> None:
    db._upsert_key(CFG_KEY, {"on": bool(on), "users": sorted(set(users or []))})


def scores_for(date=None) -> dict:
    return (db._load_key(_scores_key(date)) or {}).get("rooms") or {}


def score_of(room: str, date=None) -> dict:
    return scores_for(date).get(str(room or "").upper().strip()) or {}


def save_score(room: str, sections: dict, by="", by_name="", note="", date=None) -> dict:
    """Record (or replace) a room's score. `sections` is {name: points}."""
    room = str(room or "").upper().strip()
    if not room:
        return {}
    key = _scores_key(date)
    cur = db._load_key(key) or {}
    rooms = dict(cur.get("rooms") or {})
    rb = rubric()
    clean = {k: int(v or 0) for k, v in (sections or {}).items()}
    rooms[room] = {"sections": clean, "total": sum(clean.values()),
                   "max": rb["max"], "note": note or "",
                   "by": by or "", "by_name": by_name or "", "at": clock.stamp()}
    db._upsert_key(key, {"rooms": rooms})
    return rooms[room]
