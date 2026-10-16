"""
duties.py — the weekend's carpet and stripping rooms, for the housepersons who
do them, and whether each is done.

The 5 AM build fills the sheet's Carpet and Stripping columns (weekend_duties)
and keeps the same assignment here for the day. A houseperson signs in, sees
the rooms under their name on My Rooms and marks each one Done -- or Reset, to
take a mistaken tap back. RQS and managers see the list read-only.

None of this touches anything else: not the room's cleaning status, not
HotSOS, not the inspections. It lives in its own app_settings rows:

    duties_<date>               {"date", "at", "rooms": {room: {"carpet": name,
                                                                "stripping": name}}}
    dutydone_<date>_<username>  {"name", "done": {"<room>|<duty>": stamp}}

One row per person for what they have done, so two housepersons tapping at
the same moment never overwrite each other. No Streamlit here.
"""
import clock
import db

ASSIGN_PREFIX = "duties_"
DONE_PREFIX = "dutydone_"
DUTIES = ("carpet", "stripping")
_COLUMN = {"carpet": "Carpet", "stripping": "Stripping"}


def _key(day_iso, user=""):
    return f"{DONE_PREFIX}{day_iso}_{user}" if user else f"{ASSIGN_PREFIX}{day_iso}"


# ── the day's assignment ─────────────────────────────────────────────────────
def from_frame(frame):
    """{room: {duty: name}} from a sheet frame's Carpet / Stripping columns."""
    rooms = {}
    if frame is None or getattr(frame, "empty", True) or "Room" not in frame.columns:
        return rooms
    for duty, col in _COLUMN.items():
        if col not in frame.columns:
            continue
        for room, who in zip(frame["Room"], frame[col]):
            room, who = str(room or "").strip().upper(), str(who or "").strip()
            if room and who and who.lower() != "nan":
                rooms.setdefault(room, {})[duty] = who
    return rooms


def save(day_iso, frame):
    """Keep the day's carpet and stripping rooms. A day without any leaves no
    row behind (an earlier build's would otherwise linger)."""
    rooms = from_frame(frame)
    if rooms:
        db._upsert_key(_key(day_iso), {"date": day_iso, "at": clock.stamp(), "rooms": rooms})
    else:
        db._delete_key(_key(day_iso))
    return rooms


def assigned(day_iso) -> dict:
    return (db._load_key(_key(day_iso)) or {}).get("rooms") or {}


def people(rooms) -> list:
    """Every name with a carpet or stripping room."""
    return sorted({who for r in rooms.values() for who in r.values() if who})


def mine(rooms, name) -> list:
    """[(room, duty)] for `name` (a name as the sheet writes it), in room order."""
    return sorted((room, duty) for room, r in rooms.items() for duty, who in r.items() if who == name)


# ── done or not ──────────────────────────────────────────────────────────────
def done_by(day_iso, user) -> dict:
    """{"<room>|<duty>": stamp} that `user` has marked done today."""
    return (db._load_key(_key(day_iso, user)) or {}).get("done") or {}


def mark(day_iso, user, name, room, duty, done=True):
    """Done, or back to not started (Reset)."""
    rec = db._load_key(_key(day_iso, user)) or {}
    got = dict(rec.get("done") or {})
    k = f"{room}|{duty}"
    if done:
        got[k] = clock.stamp()
    else:
        got.pop(k, None)
    db._upsert_key(_key(day_iso, user), {"name": name, "done": got})
    return got


def housepersons(day_iso) -> list:
    """Names the staff schedule has on `day_iso` outside the housekeeper and
    RQS groups -- the housepersons. My Rooms uses it to tell a houseperson
    with nothing today so, instead of asking them to pick a housekeeper."""
    import roster_import as ri
    try:
        wk = ri.find_week_key(db.staff_week_keys(), day_iso)
        week = db.load_staff_week(wk) if wk else None
        if not week:
            return []
        eff, _ = ri.apply_overrides(week, db.load_staff_overrides() or {}, wk)
        return sorted({str(p["name"]).split(" · ")[0].strip() for p in ri.week_to_people(eff, day_iso)
                       if p.get("group") not in ("hk", "rqs") and p.get("name")})
    except Exception as ex:
        print(f"[duties] housepersons not read: {ex}")
        return []


def all_done(day_iso) -> dict:
    """{(room, duty): (name, stamp)} across everyone, for the RQS / manager list."""
    out = {}
    for row in db._like_keys(f"{DONE_PREFIX}{day_iso}_", with_payload=True):
        p = row.get("payload")
        if isinstance(p, str):
            import json
            p = json.loads(p)
        for k, stamp in ((p or {}).get("done") or {}).items():
            room, _, duty = k.partition("|")
            out[(room, duty)] = ((p or {}).get("name", ""), stamp)
    return out
