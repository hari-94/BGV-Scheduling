"""
report_timing.py — when each room was marked in HotSOS, for the Report
page's Timing tab: how each housekeeper's day ran (first start, every room's
start and done) and how long a finished room waited for its RQS.

The marks are the HotSOS mirror's (`room_status`, every two minutes, from
9 October): `started_at` and `cleaned_at` are HotSOS's own times off the
attendants' timeline; `inspected_at` is when the mirror first saw the room
inspected -- HotSOS gives no time for it -- so it is good to about two
minutes. The RQS is the app chart's inspector: HotSOS doesn't say who
inspected. Only rooms on the app's charts are mirrored.

What counts as not marking on time (HP, 18 Oct: "so we know if someone is
not marking in timely manner"):

  * started late -- the day's first room started after FIRST_START_LATE
    (carts roll at 10:00);
  * marked together -- start and done pressed within TOGETHER_MIN of each
    other on a room with real minutes: the room was marked after it was
    cleaned, not as it went. Three rooms in ten on 17 October;
  * left open -- done pressed more than LONG_OPEN times the room's minutes
    after its start: the done tap came long after the room was finished;
  * no done mark -- inspected with no done from the housekeeper;
  * waiting for the RQS -- done to inspected over WAIT_LATE minutes, on
    Full Clean rooms only (HP, 28 Oct): RQS 2's Daily Service and Dust n
    Vac round is left out of every RQS figure.

No Streamlit here.
"""
import collections
import datetime as _dt
import statistics

import clock

#: Raised when the page needs something this module didn't have before: the
#: page reloads an older copy a running app is still holding (CLAUDE.md).
VERSION = 3

FIRST_START_LATE = _dt.time(10, 30)
TOGETHER_MIN = 3           # start and done this close: marked after the fact
LONG_OPEN = 2.0            # done this many times the room's minutes after start
WAIT_SOON = 30             # minutes, done -> inspected: fine up to here
WAIT_LATE = 60             # and late past here
SINCE = _dt.date(2026, 10, 9)      # the mirror's first full day


def _t(stamp):
    if not stamp:
        return None
    try:
        return _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(clock.MTN)
    except ValueError:
        return None


def load(db, start, end):
    """(room_status rows, {iso: {room: (service, minutes)}}) for start..end."""
    rows, at = [], 0
    while True:
        page = (db._client().table("room_status")
                .select("date,room,status,group_label,housekeeper,inspector,"
                        "started_at,cleaned_at,inspected_at")
                .gte("date", start.isoformat()).lte("date", end.isoformat())
                .order("date").order("room").range(at, at + 999).execute().data or [])
        rows += page
        at += 1000
        if len(page) < 1000:
            break
    plan = {}
    for iso in sorted({r["date"] for r in rows}):
        s = db.load_full_schedule(iso) or {}
        plan[iso] = {str(r.get("room")): (str(r.get("service") or ""), int(float(r.get("time") or 0)))
                     for g in s.get("groups_data") or [] for r in g.get("rooms") or []}
    # Who inspected: the RQS the team typed on the sheet, as the 4 PM Report
    # sync read it, over the one the app planned at 5 AM. On 22 Oct the RQS
    # changed on 18 rooms after the push; through the day the office PC
    # carries such changes into the app (app_sync.from_sheet), and for any
    # day already synced the sheet itself is the record.
    typed = _sheet_rqs(db, {r["date"] for r in rows})
    for r in rows:
        name = typed.get((r["date"], str(r["room"])))
        if name:
            r["inspector"] = name
    return rows, plan


def _sheet_rqs(db, days):
    """{(iso, room): RQS full name} from the Report's synced day tabs."""
    import staff_names
    try:
        aliases = staff_names.aliases()
    except Exception:
        aliases = {}
    out = {}
    for month in sorted({d[:7] for d in days}):
        rec = db._load_key("report_days_" + month) or {}
        for iso, day in (rec.get("days") or {}).items():
            if iso not in days:
                continue
            for row in day.get("rows") or []:
                if len(row) < 4 or not row[3]:
                    continue
                first = str(row[3]).replace("+", "/").replace("&", "/").split("/")[0].strip()
                if not first or first.lower().replace(" ", "").startswith(("rqs", "inspector")):
                    continue
                out[(iso, str(row[0]))] = staff_names.resolve(first, aliases) or first
    return out


def rooms(rows, plan, now=None):
    """One record per room and day, with its times in minutes and its flags."""
    now = now or clock.now()
    out = []
    for r in rows:
        svc, std = (plan.get(r["date"]) or {}).get(str(r["room"]), ("", 0))
        start, done, insp = _t(r.get("started_at")), _t(r.get("cleaned_at")), _t(r.get("inspected_at"))
        dur = round((done - start).total_seconds() / 60) if start and done else None
        wait = round((insp - done).total_seconds() / 60) if done and insp else None
        waiting = (round((now - done).total_seconds() / 60)
                   if done and not insp and r["date"] == now.date().isoformat() else None)
        timed = std > 0 and "dust" not in svc.lower()
        out.append({
            "date": r["date"], "room": str(r["room"]), "hk": str(r.get("housekeeper") or ""),
            "rqs": str(r.get("inspector") or ""), "status": str(r.get("status") or ""),
            "service": svc, "std": std, "start": start, "done": done, "inspected": insp,
            "dur": dur, "wait": wait, "waiting": waiting,
            "together": bool(timed and dur is not None and dur < TOGETHER_MIN),
            "left_open": bool(timed and dur is not None and dur > LONG_OPEN * std),
            "no_done": bool(insp and not done),
        })
    return out


def _hhmm(t):
    return f"{t:%I:%M}".lstrip("0") + ("am" if t.hour < 12 else "pm") if t else ""


def _mins(t):
    return t.hour * 60 + t.minute if t else None


def _clock(m):
    """Minutes after midnight as a time of day, for an average first start."""
    if m is None:
        return ""
    return _hhmm(_dt.time(int(m) // 60, int(m) % 60))


def housekeepers(recs):
    """Per housekeeper, over the days in `recs`."""
    by = collections.defaultdict(list)
    for x in recs:
        if x["hk"]:
            by[x["hk"]].append(x)
    out = []
    for name, xs in by.items():
        days = collections.defaultdict(list)
        for x in xs:
            days[x["date"]].append(x)
        firsts = [min(s for s in (y["start"] for y in d) if s) for d in days.values()
                  if any(y["start"] for y in d)]
        lasts = [max(s for s in (y["done"] for y in d) if s) for d in days.values()
                 if any(y["done"] for y in d)]
        timed = [x for x in xs if x["std"] > 0 and "dust" not in x["service"].lower()]
        marked = [x for x in timed if x["dur"] is not None]
        pace = [x["dur"] / x["std"] for x in marked if not x["together"]]
        out.append({
            "name": name, "days": len(days), "rooms": len(xs),
            "done": sum(1 for x in xs if x["done"] or x["inspected"]),
            "first": min(firsts) if len(days) == 1 and firsts else None,
            "last": max(lasts) if len(days) == 1 and lasts else None,
            "first_avg": statistics.mean(_mins(f) for f in firsts) if firsts else None,
            "late_starts": sum(1 for f in firsts if f.time() > FIRST_START_LATE),
            "together": sum(1 for x in xs if x["together"]),
            "left_open": sum(1 for x in xs if x["left_open"]),
            "no_done": sum(1 for x in xs if x["no_done"]),
            "timed": len(timed),
            "pace": statistics.median(pace) if pace else None,
        })
    for p in out:
        p["flags"] = p["together"] + p["left_open"] + p["no_done"] + p["late_starts"]
    return sorted(out, key=lambda p: (-p["flags"], p["name"]))


def full_clean(x) -> bool:
    """A Full Clean room ("Full Clean", "Full Clean (IH)")."""
    return x["service"].lower().startswith("full clean")


def inspectors(recs):
    """Per RQS: how long their finished Full Clean rooms waited to be
    inspected. Full Clean only (HP, 28 Oct): the Daily Service and Dust n Vac
    round is RQS 2's, property-wide by design, and its waits put RQS 2 beside
    the Full Clean inspectors as though it were the same job."""
    by = collections.defaultdict(list)
    for x in recs:
        # "Inspector 3" is a chart nobody was found for, not a person.
        if (x["rqs"] and not x["rqs"].startswith("Inspector ") and full_clean(x)
                and (x["done"] or x["inspected"])):
            by[x["rqs"]].append(x)
    out = []
    for name, xs in by.items():
        waits = [x["wait"] for x in xs if x["wait"] is not None]
        still = [x["waiting"] for x in xs if x["waiting"] is not None]
        out.append({
            "name": name, "days": len({x["date"] for x in xs}), "ready": len(xs),
            "inspected": sum(1 for x in xs if x["inspected"]),
            "median": statistics.median(waits) if waits else None,
            "longest": max(waits) if waits else None,
            "late": sum(1 for w in waits if w > WAIT_LATE),
            "waiting": len(still), "waiting_longest": max(still) if still else None,
            "last": max((x["inspected"] for x in xs if x["inspected"]), default=None),
        })
    return sorted(out, key=lambda p: (-(p["median"] or 0), p["name"]))
