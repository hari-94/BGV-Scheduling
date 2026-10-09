"""
ds_pick.py — who does Daily Service on a day the staff sheet names nobody.

The staff schedule marks a Daily Service person with "Daily service" in
their cell. When nobody's cell says so, the Schedule page used to hand the
Daily Service chart to whoever was left over after the Full Clean charts --
on 9 October that was Alejandro at 5 AM and somebody else on a Generate by
hand an hour later. Leftover is luck, not a rule.

The manager's rule: the first choice is someone working that day who has not
done Daily Service yet that week. "Done Daily Service" is read from what
actually happened -- each earlier day's stored schedule (which a Push brings
in line with the final sheet) -- and from the staff sheet's own "Daily
service" cells. Ties go to an RQS covering housekeeping (the day's flexible
person), then to whoever has done it least that week, then by name.

When this leaves Full Clean short, the page's borrowing (Dust and Vac, then
projects -- daily_build.borrowable) fills in, with its alerts. No Streamlit.
"""
import datetime as _dt

import db
import roster_import as ri
import staff_names


def week_start(day: _dt.date) -> _dt.date:
    """The Sunday that starts `day`'s week -- how Schedule.xlsx is laid out."""
    return day - _dt.timedelta(days=(day.weekday() + 1) % 7)


def ds_days_this_week(day: _dt.date) -> dict:
    """{full name: days on Daily Service} from the start of `day`'s week up
    to the day before it."""
    table = staff_names.aliases()
    seen = {}
    d = week_start(day)
    eff = None
    try:                                   # one staff week covers all these days
        wk = ri.find_week_key(db.staff_week_keys(), d.isoformat())
        week = db.load_staff_week(wk) if wk else None
        if week:
            eff, _ = ri.apply_overrides(week, db.load_staff_overrides() or {}, wk)
    except Exception:
        eff = None
    while d < day:
        iso = d.isoformat()
        names = set()
        try:
            sched = db.load_full_schedule(iso) or {}
        except Exception:
            sched = {}
        for g in sched.get("groups_data") or []:
            hk = str(g.get("housekeeper") or "")
            if g.get("service_type") == "Daily Service" and hk                     and not hk.startswith(("No HK", "Need Housekeeper")):
                names.add(staff_names.full(hk, table))
        if eff and iso in eff.get("dates", []):
            for p in ri.week_to_people(eff, iso):
                if "daily service" in str(p["raw"]).lower():
                    names.add(staff_names.full(p["name"], table))
        for n in names:
            seen[n] = seen.get(n, 0) + 1
        d += _dt.timedelta(days=1)
    return seen


def pick(n: int, present: list, day: _dt.date, covering=()) -> tuple:
    """(names, {name: why}) -- `n` people for the day's Daily Service charts,
    from `present` (the day's working housekeepers, RQS covering included)."""
    if n <= 0 or not present:
        return [], {}
    done = ds_days_this_week(day)
    table = staff_names.aliases()
    full = {p: staff_names.full(p, table) for p in present}
    cover = set(covering)

    def key(p):
        return (done.get(full[p], 0) > 0,          # not done it this week first
                p not in cover,                    # then an RQS covering HSKP
                done.get(full[p], 0),              # then the fewest days of it
                p.lower())
    chosen = sorted(present, key=key)[:n]
    why = {}
    for p in chosen:
        k = done.get(full[p], 0)
        why[p] = ("no Daily Service yet this week" if not k else
                  f"fewest Daily Service days this week ({k})")
        if p in cover:
            why[p] += "; RQS covering housekeeping"
    return chosen, why
