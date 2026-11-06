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


def config() -> dict:
    c = db._load_key(CFG_KEY) or {}
    return {"on": bool(c.get("on")), "users": list(c.get("users") or [])}


def enabled_for(username: str) -> bool:
    """Whether this user's inspections should flow to HotSOS right now."""
    c = config()
    return bool(c["on"] and username and username in c["users"])


def set_config(on: bool, users) -> None:
    db._upsert_key(CFG_KEY, {"on": bool(on), "users": sorted(set(users or []))})


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
