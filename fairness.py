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

WINDOW_DAYS = 365            # the whole year (Hari, 25 Nov: "to be fair")
#: A housekeeper's room is worth its work (Hari, 25 Nov): a Full Clean (or a
#: deep clean) is ~94 min on the charts, a Daily Service ~28. Dust n Vac is
#: left out -- housekeepers rarely have it. An RQS counts Full Clean (and deep
#: clean) inspections only -- report_data's "in" is exactly those.
HK_POINTS = {"fc": 3.0, "ds": 1.0}


def points(slot_or_tally, role) -> float:
    """The work in a day's slot (or a tally): points for a housekeeper, Full
    Clean inspections for an RQS."""
    def n(k):
        v = slot_or_tally.get(k, 0)
        return len(v) if isinstance(v, (list, tuple)) else (v or 0)
    if role == "rqs":
        return float(n("in"))
    return sum(w * n(k) for k, w in HK_POINTS.items())
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
    {"from", "to", "people": {name: {"role", "sched", "busy", "free", "rooms", "rate"}}}.

    sched = days the staff schedule had them working in their team (a
            housekeeper's room or Daily Service days; an RQS's days on)
    busy  = days they had rooms (cleaned / inspected)
    free  = sched - busy: on the schedule, no rooms
    rooms = rooms cleaned (housekeeper) or inspected (RQS)
    mix   = {"fc", "ds"}: rooms of each kind (an RQS: {"fc": inspected})
    points= HK_POINTS over the mix (an RQS: Full Clean inspections)
    rate  = points (an RQS: FC inspections) per day they had rooms -- the
            Rooms view's "rooms per day", every day the same: what decides the
            order. None for someone with no rooms yet.
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
        by_day = (res.get("days") or {}).get(p, {})
        if role == "hk":
            sched = t.get("main", 0) + t.get("ds_days", 0)
            rooms = t.get("cleaned", 0)
            busy = t.get("days_clean", 0)
            mix = {"fc": t.get("fc", 0), "ds": t.get("ds", 0)}
        else:
            sched, busy, rooms = t.get("sched", 0), t.get("days_in", 0), t.get("in", 0)
            mix = {"fc": t.get("in", 0)}
        # Days they could have had rooms (free_to_work): the count the rate is
        # made on, and the "had rooms on N of M days" the page shows.
        sched = sum(1 for iso, sl in by_day.items() if frm <= iso <= to and free_to_work(sl, role))
        people[p] = {"role": role, "sched": sched, "busy": busy,
                     "free": max(0, sched - busy), "rooms": rooms, "mix": mix,
                     "points": round(points(t, role), 1),
                     "rate": _weighted_rate((res.get("days") or {}).get(p, {}), frm, to, role)}
    return {"from": frm, "to": to, "people": people}


def free_to_work(slot, role) -> bool:
    """Was this a day they could have had rooms? On the schedule in their team
    for ordinary work -- not a project / other-work day, and for an RQS not an
    RQS 1 or RQS 2 day, whose rounds are set by role (Hari, 25 Nov: his 48
    other-work and 13 RQS 1 days read as days "left without rooms", and his
    10.6 rooms per inspecting day came out 6.9). Any day they did have rooms
    counts too, whatever the sheet said (a first name alone on an older sheet
    matched no row, and Janelly read as 33 rooms in one day)."""
    import report_data as rd
    import roster_import as ri
    if points(slot, role) > 0:
        return True
    mine = [e for e in slot.get("sched", ()) if e[0] == role and e[2] in rd.WORKED]
    if not mine or not {e[2] for e in mine} & {"working", "daily_service"}:
        return False
    if role == "rqs" and any(ri.rqs_roles(e[3]) for e in mine):
        return False
    return True


def _weighted_rate(by_day, frm, to, role):
    """Work per day they had rooms -- the Rooms view's own "rooms per day"
    (Hari, 25 Nov: "just use this value"; his 1,282 rooms over 121 days =
    10.6). Every day counts the same. Days on with no rooms don't lower it;
    they only break ties (need_key)."""
    total = days = 0.0
    for iso, slot in by_day.items():
        if not (frm <= iso <= to):
            continue
        n = points(slot, role)
        if n > 0:
            total += n
            days += 1
    return round(total / days, 2) if days else None


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
    got = people.get(full) or low.get(full.lower()) or low.get(str(name).lower())
    if got:
        return got
    # A first name alone ("Erick", from a sheet before the full names) that
    # only one person in the window has.
    first = str(name).strip().split(" ")[0].lower()
    if first and len(str(name).split()) == 1:
        hits = [v for k, v in people.items() if k.split(" ")[0].lower() == first]
        if len(hits) == 1:
            return hits[0]
    return {}


def need_key(rec) -> tuple:
    """The fewest rooms per day on first (recent days weighted more); then
    the larger share of days left free; then the fewer rooms in the year.
    Somebody with no days on yet (new) counts as 0: first."""
    rate = rec.get("rate")
    if rate is None:
        rate = 0.0 if not rec.get("sched") else rec.get("rooms", 0) / rec["sched"]
    sched = rec.get("sched", 0) or 0
    free_share = (rec.get("free", 0) / sched) if sched else 0.0
    return (rate, -free_share, rec.get("rooms", 0))


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
                        "rate": r.get("rate"), "mix": r.get("mix") or {}, "points": r.get("points"),
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
