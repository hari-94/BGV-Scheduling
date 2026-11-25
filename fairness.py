"""
fairness.py -- who gets rooms first, by the rooms they have had (Hari, 25 Nov).

The scheduler handed charts out in the staff sheet's order: each chart took
the next housekeeper in its building's list, each RQS round the next
inspector, so whoever sat at the bottom was the one left free whenever there
were more people than work -- the same people, day after day. Over the four
weeks to 24 Nov Miguel Castor was on the schedule 21 days and inspected on 5;
Mayra, Grace, Alejandro and Sayra were free on 10-11 days of 18-19.

Now both lists are put in order of need before anything is handed out: the
fewest rooms over the last four weeks first (rooms cleaned for a
housekeeper, rooms inspected for an RQS). They get charts first, and the
biggest ones (the scheduler hands the bigger charts and rounds out first);
whoever has had the most is the one left free. RQS 1 and RQS 2 keep their
fixed roles -- the order only decides among the others.

The counts are the Report's own (report_data: the GC8 Inspections tabs as
the team left them, synced at 4 PM, names matched to the staff schedule), so
the Fair share view that shows them and the build that uses them cannot
disagree. Each build records the order it used (`KEY`), with every person's
numbers, so a free day can be checked against the figures that decided it.

No Streamlit.
"""
import datetime as _dt

WINDOW_DAYS = 28
KEY = "fair_share"            # app_settings: {"days": {iso: the order a build used}}
SWITCH_KEY = "fair_share_on"  # {"on": false} turns the ordering off
KEEP_DAYS = 21                # recorded days kept


def enabled() -> bool:
    import db
    try:
        return (db._load_key(SWITCH_KEY) or {}).get("on", True) is not False
    except Exception:
        return True


def ledger(end=None, window=WINDOW_DAYS):
    """The last `window` synced days up to `end` (ISO, inclusive), per person:
    {"from", "to", "people": {name: {"role", "sched", "busy", "free", "rooms"}}}.

    sched = days the staff schedule had them working in their team (a
            housekeeper's room or Daily Service days; an RQS's days on)
    busy  = days they had rooms (cleaned / inspected)
    free  = sched - busy: on the schedule, no rooms
    rooms = rooms cleaned (housekeeper) or inspected (RQS)
    The role is the Report's: the team the schedule had them in most."""
    import db
    import report_data as rd
    import roster_import as ri
    staff_names = _names()
    days = rd.load_days(db)
    if not days:
        return {"from": None, "to": None, "people": {}}
    last = max(days)
    to = min(end, last) if end else last
    frm = (_dt.date.fromisoformat(to) - _dt.timedelta(days=window - 1)).isoformat()
    sub = {d: v for d, v in days.items() if frm <= d <= to}
    roster, visiting = rd.roster_days(db.load_staff_weeks(), db.load_staff_overrides(), frm, to)
    directory = rd.Directory(list(roster), [a["label"] for a in staff_names.attendants()],
                             staff_names.aliases(), db._load_key(rd.NAMES_KEY) or {},
                             ri.NAME_ALIASES)
    res = rd.build(sub, roster, visiting, directory)
    people = {}
    for p, info in (res.get("people") or {}).items():
        role = info.get("role")
        if role not in ("hk", "rqs"):
            continue
        t = rd.tally((res.get("days") or {}).get(p, {}), frm, to, role)
        if role == "hk":
            sched = t.get("main", 0) + t.get("ds_days", 0)
            busy, rooms = t.get("days_clean", 0), t.get("cleaned", 0)
        else:
            sched, busy, rooms = t.get("sched", 0), t.get("days_in", 0), t.get("in", 0)
        people[p] = {"role": role, "sched": sched, "busy": busy,
                     "free": max(0, sched - busy), "rooms": rooms}
    return {"from": frm, "to": to, "people": people}


def _names():
    """staff_names as it is on disk: the office PC's agent and the web app run
    for days, and `canon` is newer than a copy loaded before 25 Nov."""
    import fresh
    import staff_names
    fresh.latest("staff_names")
    import staff_names as sn
    return sn


def lookup(name, led, table=None, attendant_list=None) -> dict:
    """A person's ledger row by any spelling of their name, or {} (new: no rooms yet)."""
    staff_names = _names()
    people = (led or {}).get("people") or {}
    if name in people:
        return people[name]
    full = staff_names.canon(name, table, attendant_list)
    low = {k.lower(): v for k, v in people.items()}
    return people.get(full) or low.get(full.lower()) or low.get(str(name).lower()) or {}


def need_key(rec) -> tuple:
    """Fewest rooms first; then the more free days; then the fewer days with rooms."""
    return (rec.get("rooms", 0), -rec.get("free", 0), rec.get("busy", 0))


def need_order(names, led, table=None, attendant_list=None) -> list:
    """`names` in the order they should get rooms. Stable: people level on all
    three keep the order they came in (the sheet's)."""
    if table is None or attendant_list is None:
        try:
            staff_names = _names()
            table = staff_names.aliases() if table is None else table
            attendant_list = staff_names.attendants() if attendant_list is None else attendant_list
        except Exception:
            table, attendant_list = table or {}, attendant_list or []
    return sorted(list(names), key=lambda n: need_key(lookup(n, led, table, attendant_list)))


def snapshot(day, led, hk_order, rqs_order, table=None, attendant_list=None, notes=None) -> dict:
    """The order a build used and each person's numbers, ready to record.
    `notes` {name: why} carries what the order doesn't decide -- RQS 1 and
    RQS 2's own roles, light duty -- so a free day can be read correctly."""
    notes = notes or {}

    def rows(names):
        out = []
        for i, n in enumerate(names, 1):
            r = lookup(n, led, table, attendant_list)
            out.append({"rank": i, "name": n, "rooms": r.get("rooms", 0), "free": r.get("free", 0),
                        "busy": r.get("busy", 0), "sched": r.get("sched", 0), "new": not r,
                        "note": notes.get(n, "")})
        return out
    import clock
    return {"day": str(day), "at": clock.stamp(), "from": (led or {}).get("from"),
            "to": (led or {}).get("to"), "window": WINDOW_DAYS,
            "hk": rows(hk_order), "rqs": rows(rqs_order)}


def record(snap) -> None:
    """Keep the snapshot under its day; the last KEEP_DAYS days are kept."""
    import db
    rec = db._load_key(KEY) or {}
    days = dict(rec.get("days") or {})
    days[snap["day"]] = snap
    for d in sorted(days)[:-KEEP_DAYS]:
        days.pop(d, None)
    db._upsert_key(KEY, {"days": days})


def recorded(day=None):
    """The snapshot recorded for `day` (ISO), or the latest one."""
    import db
    days = (db._load_key(KEY) or {}).get("days") or {}
    if day:
        return days.get(str(day))
    return days[max(days)] if days else None
