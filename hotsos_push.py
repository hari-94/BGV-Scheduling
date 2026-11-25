"""
hotsos_push.py — the web app asks the office PC to mark a room inspected in
HotSOS.

Only the office-PC agent holds a HotSOS session, so a page cannot call HotSOS
itself. When the pilot is on and an allowed user marks a room Inspected in My
Rooms, the page drops a request here; hotsos_agent.push_inspections drains it
on its next mirror pass (about two minutes) and PATCHes the room to INSPECTED.

A pilot, off until switched on, and only for the usernames listed:

    CFG_KEY    {"on": bool, "users": ["hvardan@grandtimber.com", ...]}
    QUEUE_KEY  {"items": [{"room", "by", "at"}, ...], "log": [...]}

No Streamlit here.
"""
import clock
import db

CFG_KEY = "hotsos_inspect_cfg"
QUEUE_KEY = "hotsos_inspect_queue"


#: config() is asked once per room on My Rooms -- 119 database reads for a
#: manager's list, ~16 s (25 Nov). Kept for CFG_SECONDS; a change made here
#: is seen at once, one made elsewhere within that time.
CFG_SECONDS = 30
_CFG = {"at": 0.0, "val": None}


def config() -> dict:
    import time
    if _CFG["val"] is not None and time.time() - _CFG["at"] < CFG_SECONDS:
        return {"on": _CFG["val"]["on"], "users": list(_CFG["val"]["users"])}
    c = db._load_key(CFG_KEY) or {}
    val = {"on": bool(c.get("on")), "users": list(c.get("users") or [])}
    _CFG.update(at=time.time(), val=val)
    return {"on": val["on"], "users": list(val["users"])}


def enabled_for(username: str) -> bool:
    """Whether this user's inspections should flow to HotSOS right now."""
    c = config()
    return bool(c["on"] and username and username in c["users"])


def set_config(on: bool, users) -> None:
    db._upsert_key(CFG_KEY, {"on": bool(on), "users": sorted(set(users or []))})
    _CFG.update(at=0.0, val=None)


def enqueue_inspection(room: str, by: str) -> None:
    """Ask the agent to mark `room` INSPECTED in HotSOS. Idempotent per room:
    a room already waiting is not queued twice."""
    room = str(room or "").upper().strip()
    if not room:
        return
    q = db._load_key(QUEUE_KEY) or {}
    items = list(q.get("items") or [])
    if any(str(i.get("room", "")).upper().strip() == room for i in items):
        return
    items.append({"room": room, "by": by or "", "at": clock.stamp()})
    db._upsert_key(QUEUE_KEY, {"items": items, "log": list(q.get("log") or [])[-80:]})
