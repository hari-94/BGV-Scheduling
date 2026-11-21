"""
frontdesk.py — the front desk's board of today's rooms, and the marks the
desk puts on them (Hari, 21 Nov).

The desk sees every room on today's charts: what HotSOS says it is, who is
cleaning and inspecting it, when it was started, cleaned and inspected, and
when it should be ready. They put three things on a room:

  * a late checkout, with the time the guest leaves -- it reaches the
    housekeeper's phone and moves the room later in their route (daystart
    reads `late_checkout`). Writing it into the room's Notes on the day's
    GC8 Inspections tab too is agreed but not built: the tab is open in
    Excel Online all day, so it needs an Office Script flow like the ENG
    sheet's (SHEET_KEY_PREFIX is reserved for its record);
  * guest departed -- the room is free now, so nothing is waited for;
  * a note to housekeeping ("left a jacket", "needs a crib").

Each room's marks are one app_settings row, `fdmark_<date>_<ROOM>`, so two
people at the desk marking different rooms at once can't undo each other's
save. They are laid over the charts when read (`apply`), never written into
the schedule: the HotSOS mirror rewrites that every two minutes.

No Streamlit here, so it is testable alone.
"""
import datetime as _dt
import re
import uuid

import clock

PREFIX = "fdmark_"                  # + date + "_" + ROOM
SHEET_KEY_PREFIX = "fdsheet_"       # + date: {ROOM: text the office PC wrote to the sheet}
#: Rooms the team typed on today's GC8 Inspections tab with no housekeeper yet
#: -- an early departure, say -- which no chart holds: {date, at, rooms: [...]},
#: kept by the office PC's sheet pass (hotsos_agent.sync_sheet).
UNPLACED_KEY = "sheet_unplaced"
SOURCE = "Front Desk"

#: Late checkout times the desk picks from, 15 minutes apart. Checkout is
#: 10:00; the floor should be done by 15:30, so later than 6 PM is not a late
#: checkout but a stayover.
LATE_TIMES = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 15, 30, 45)
              if (h, m) > (10, 0) and (h, m) <= (18, 0)]

_ROOM = re.compile(r"^[1-9]\d{3}[A-Z]$")
_UNSTAFFED = ("No HK available", "Need Housekeeper")


def key(day: str, room: str) -> str:
    return f"{PREFIX}{day}_{str(room).strip().upper()}"


def _db():
    import db
    return db


def load(day: str = None) -> dict:
    """{ROOM: mark} for a day, read now. Pages don't call this: they read the
    marks off the shared floor (floor.today().marks), which is the one cache."""
    day = day or clock.today_iso()
    out = {}
    for row in _db()._like_keys(f"{PREFIX}{day}_", with_payload=True):
        p = row.get("payload")
        if isinstance(p, str):
            import json
            try:
                p = json.loads(p)
            except ValueError:
                p = None
        if isinstance(p, dict) and p.get("room"):
            out[str(p["room"]).upper()] = p
    return out


def _update(day: str, room: str, by: str, change) -> dict:
    """Read the room's row fresh, apply `change(mark)`, save it. A row left
    with nothing on it is deleted."""
    db = _db()
    room = str(room).strip().upper()
    if not _ROOM.match(room):
        raise ValueError(f"not a room: {room!r}")
    k = key(day, room)
    mark = db._load_key_raw(k) or {}
    if isinstance(mark, str):
        import json
        mark = json.loads(mark)
    mark = dict(mark or {}, room=room, date=day)
    what = change(mark)
    mark.setdefault("log", []).append({"what": what, "by": by, "at": clock.stamp()})
    mark["log"] = mark["log"][-30:]
    # Either write makes the shared floor stale (db._touches_floor).
    if not mark.get("late_out") and not mark.get("departed_at") and not mark.get("notes"):
        db._delete_key(k)
    else:
        db._upsert_key(k, mark)
    return mark


def set_late_out(day, room, hhmm, by):
    """A late checkout at `hhmm` (24-hour "13:00"), or None to remove it."""
    if hhmm is not None and hhmm not in LATE_TIMES:
        raise ValueError(f"late checkout time {hhmm!r} is not one of the offered times")

    def change(m):
        m["late_out"] = hhmm
        m["late_by"], m["late_at"] = (by, clock.stamp()) if hhmm else (None, None)
        return f"late out {hhmm}" if hhmm else "late out removed"
    return _update(day, room, by, change)


def set_departed(day, room, departed: bool, by):
    def change(m):
        m["departed_at"] = clock.stamp() if departed else None
        m["departed_by"] = by if departed else None
        return "departed" if departed else "departed undone"
    return _update(day, room, by, change)


def add_note(day, room, text, by):
    text = " ".join(str(text or "").split())[:240]
    if not text:
        raise ValueError("empty note")

    def change(m):
        m.setdefault("notes", []).append({"id": uuid.uuid4().hex[:10], "text": text,
                                          "by": by, "at": clock.stamp()})
        return f"note: {text}"
    return _update(day, room, by, change)


def remove_note(day, room, note_id, by):
    def change(m):
        gone = [n for n in m.get("notes") or [] if n.get("id") == note_id]
        m["notes"] = [n for n in m.get("notes") or [] if n.get("id") != note_id]
        return "note removed: " + (gone[0]["text"] if gone else note_id)
    return _update(day, room, by, change)


def keep_unplaced(rows, day: str = None):
    """The office PC's side: today's rooms on the sheet that no chart holds,
    saved only when they changed."""
    db = _db()
    day = day or clock.today_iso()
    old = db._load_key(UNPLACED_KEY) or {}
    if old.get("date") == day and old.get("rooms") == rows:
        return False
    db._upsert_key(UNPLACED_KEY, {"date": day, "at": clock.stamp(), "rooms": rows})
    return True


# ── reading them back ────────────────────────────────────────────────────────
def hhmm12(hhmm: str) -> str:
    """"13:00" -> "1:00 pm", the way daystart writes and reads a time."""
    h, m = (int(x) for x in str(hhmm).split(":"))
    return "%d:%02d %s" % (h % 12 or 12, m, "am" if h < 12 else "pm")


def late_text(hhmm: str) -> str:
    """The late checkout as a room's `late_checkout` carries it -- the same
    shape as the Arrival Report's ("Late Out: 10:30 am"), so daystart and the
    cards read it unchanged."""
    return f"Late Out: {hhmm12(hhmm)}"


def local_hhmm(iso) -> str:
    """An ISO timestamp as the property's clock, "1:05 pm"; "" if none."""
    if not iso:
        return ""
    try:
        t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        t = t.astimezone(clock.MTN)
        return hhmm12(f"{t.hour}:{t.minute:02d}")
    except (TypeError, ValueError):
        return ""


def _past(iso, now) -> str:
    """local_hhmm, but "" for a time still to come: for a Return Later room
    HotSOS's timeline carries when it *expects* the start (21 Nov: 1010B
    "started" 2:48 pm at 9:36 am), and the mirror stores it."""
    if not iso:
        return ""
    try:
        t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        if t > now + _dt.timedelta(minutes=2):
            return ""
    except (TypeError, ValueError):
        return ""
    return local_hhmm(iso)


def overlay_room(r: dict, m: dict) -> dict:
    """One room with the desk's marks on it. The Arrival Report's late
    checkout is kept as `late_checkout_report`."""
    r = dict(r)
    if m.get("late_out"):
        r["late_checkout_report"] = r.get("late_checkout") or ""
        r["late_checkout"] = late_text(m["late_out"])
        r["fd_late"] = m["late_out"]
    if m.get("departed_at"):
        # Gone: nothing to wait for, whatever the report or the desk said.
        r.setdefault("late_checkout_report", r.get("late_checkout") or "")
        r["late_checkout"] = ""
        r["fd_departed"] = m["departed_at"]
    notes = [str(n.get("text") or "") for n in m.get("notes") or [] if n.get("text")]
    if notes:
        r["fd_notes"] = notes
    return r


def apply(charts, marks):
    """Today's charts with the desk's marks laid over their rooms. The charts
    passed in are not changed."""
    if not marks:
        return charts
    out = []
    for g in charts or []:
        rooms = []
        for r in g.get("rooms") or []:
            m = marks.get(str(r.get("room", "")).strip().upper())
            rooms.append(overlay_room(r, m) if m else r)
        out.append(dict(g, rooms=rooms))
    return out


# ── the board ────────────────────────────────────────────────────────────────
_SVC_SHORT = {"Full Clean": "FC", "Full Clean (IH)": "IH", "Daily Service": "DS",
              "Dust n Vac": "D&V"}


def _person(name) -> str:
    s = " ".join(str(name or "").split())
    return "" if not s or s.startswith(_UNSTAFFED) or re.match(r"^Inspector \d", s) else s


def _report_late(r) -> str:
    """The Arrival Report's late checkout as the desk reads it: "12:00 pm",
    "time not given" for a bare "Late Out", or ""."""
    import daystart
    raw = r.get("late_checkout_report", r.get("late_checkout"))
    if not str(raw or "").strip():
        return ""
    at = daystart.late_out_at({"late_checkout": raw})
    return at.replace("am", " am").replace("pm", " pm") if at else "time not given"


def _added(r) -> bool:
    """Typed onto the day's tab after the build (app_sync.from_sheet)."""
    return bool(r.get("added_on_sheet")) or         str(r.get("notes") or "").strip().lower() == "added on the sheet"


def board(charts, statuses, marks, now=None, unplaced=()) -> list:
    """One row per room on today's charts, for the desk's table. `charts` are
    as assignments.todays_charts gives them (rooms under who holds them now),
    without the marks laid over; `statuses` is db.get_room_statuses();
    `unplaced` are rooms on today's tab that no chart holds yet (`unplaced()`)."""
    import daystart
    import roomstatus as rs
    now = now or clock.now()
    charts = apply(charts, marks)
    rows, seen = [], set()
    for g in charts or []:
        svc = g.get("service_type") or ""
        held = bool(g.get("verify_group"))
        for r in g.get("rooms") or []:
            room = str(r.get("room", "")).strip().upper()
            if not room or room in seen:
                continue
            seen.add(room)
            rec = statuses.get(str(r.get("room", "")).strip()) or statuses.get(room) or {}
            st = rs.normalise(rec.get("status"))
            label, short, dot, bg, ink = rs._meta(st)
            m = marks.get(room) or {}
            raw_late = r.get("late_checkout_report", r.get("late_checkout"))
            rep = daystart.release_minute({"late_checkout": raw_late}) if raw_late else None
            notes = [x for x in (str(r.get("notes") or "").strip(),)
                     if x and x.lower() not in ("nan", "added on the sheet")]
            rows.append({
                "room": room,
                "svc": _SVC_SHORT.get(svc, svc[:3]),
                "service": svc,
                "held": held,
                "added": _added(r),
                "unassigned": False,
                "status": st, "label": label, "short": short,
                "dot": dot, "bg": bg, "ink": ink,
                "hk": _person(rec.get("housekeeper")) or _person(g.get("housekeeper")),
                "rqs": _person(g.get("inspector")) or _person(rec.get("inspector")),
                "started": _past(rec.get("started_at"), now),
                "cleaned": _past(rec.get("cleaned_at"), now),
                "inspected": _past(rec.get("inspected_at"), now),
                "late_out": hhmm12(m["late_out"]) if m.get("late_out") else "",
                "late_out_value": m.get("late_out") or "",
                # The Arrival Report's late checkout, captured by itself; the
                # desk's own (late_out) wins where both exist.
                "late_report": _report_late(r),
                "late_report_value": (f"{rep // 60:02d}:{rep % 60:02d}" if rep is not None else ""),
                "departed": local_hhmm(m.get("departed_at")),
                "departed_by": m.get("departed_by") or "",
                "arriving": str(r.get("arriving") or "").strip(),
                "guest": str(r.get("guest") or "").strip(),
                "early": "early" in " ".join(str(r.get(k) or "") for k in ("notes", "res_type")).lower(),
                "notes": notes,
                "fd_notes": [{"id": n.get("id"), "text": n.get("text"), "by": n.get("by") or "",
                              "at": local_hhmm(n.get("at"))} for n in m.get("notes") or []],
            })
    # On the sheet, but nobody to clean it yet: no chart holds it.
    for u in unplaced or ():
        room = str(u.get("room") or "").strip().upper()
        if not _ROOM.match(room) or room in seen:
            continue
        seen.add(room)
        rec = statuses.get(room) or {}
        st = rs.normalise(rec.get("status"))
        label, short, dot, bg, ink = rs._meta(st)
        m = marks.get(room) or {}
        svc = _service_name(u.get("service"))
        rows.append({
            "room": room, "svc": _SVC_SHORT.get(svc, svc[:3]), "service": svc,
            "held": False, "added": True, "unassigned": True,
            "status": st, "label": label, "short": short, "dot": dot, "bg": bg, "ink": ink,
            "hk": "", "rqs": _person(u.get("rqs")),
            "started": _past(rec.get("started_at"), now), "cleaned": _past(rec.get("cleaned_at"), now),
            "inspected": _past(rec.get("inspected_at"), now),
            "late_out": hhmm12(m["late_out"]) if m.get("late_out") else "",
            "late_out_value": m.get("late_out") or "", "late_report": "", "late_report_value": "",
            "departed": local_hhmm(m.get("departed_at")), "departed_by": m.get("departed_by") or "",
            "arriving": str(u.get("arriving") or "").strip(), "guest": str(u.get("guest") or "").strip(),
            "early": False,
            "notes": [x for x in (str(u.get("notes") or "").strip(),) if x],
            "fd_notes": [{"id": n.get("id"), "text": n.get("text"), "by": n.get("by") or "",
                          "at": local_hhmm(n.get("at"))} for n in m.get("notes") or []],
        })
    rows.sort(key=lambda x: x["room"])
    return rows


def _service_name(raw) -> str:
    """The sheet's Service cell as the app's service name."""
    s = str(raw or "").lower()
    if "dust" in s:
        return "Dust n Vac"
    if "daily" in s or "stay" in s:
        return "Daily Service"
    if "ih" in s or "in house" in s or "in-house" in s:
        return "Full Clean (IH)"
    return "Full Clean"
