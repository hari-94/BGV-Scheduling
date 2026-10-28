"""
hotsos_agent.py — the office-PC half of the HotSOS push and the SSRS forecast.

Why a PC and not the app's server: both sources are inside the company. SSRS
(ssrsreports.grandtimber.com) signs in with the PC's Windows login, and the
inspections workbook is an organisation-only SharePoint link, read here from
its OneDrive-synced copy. Neither is reachable from a cloud host.

What it does, once started with `run`:
  * every 30 s, looks in app_settings for a request from the HotSOS page:
      - a push/preview: reads the day's tab, reads HotSOS, builds the plan,
        sends the assignments (push only), writes the result back;
      - a forecast refresh: see below.
  * every two hours from 08:00 to 20:00 (property time), and whenever the
    Forecast page asks, pulls
    the Housekeeping Dashboard from SSRS for today and the next 21 days and
    stores the headcount each day needs. Bookings change through the day, so
    the forecast is never more than two hours stale.
  * every 30 s, checks the SharePoint-synced staff Schedule.xlsx and, once it
    has changed and settled, imports it exactly as Roster Import's Save does.
    Today's attendance is re-applied only if the change touches today, so a
    roster fix made in the app this morning survives an edit to next week.
  * every minute, writes a heartbeat so the page can say whether the PC is up.

Nothing is ever pushed to HotSOS without somebody pressing the button.

Commands:
  python hotsos_agent.py setup        one-time: HotSOS login, workbook path
  python hotsos_agent.py forecast     pull SSRS now and store it
  python hotsos_agent.py roster       import the synced Schedule.xlsx now
  python hotsos_agent.py report       read GC8 Inspections for the Report page now
  python hotsos_agent.py preview [--date 2026-10-08]
  python hotsos_agent.py push    [--date 2026-10-08] [--only-room 3346E]
  python hotsos_agent.py run          the loop (Task Scheduler starts this)
  python hotsos_agent.py backup       on a second PC: Preview/Push only, and only
                                      while the office PC's heartbeat is stale
  python hotsos_agent.py teams [--test] [--date ...]   the 7:30 Teams notes now

The HotSOS password lives in Windows Credential Manager (via `keyring`), never
in a file. Supabase credentials come from .streamlit/secrets.toml as for the
app itself.
"""
import argparse
import datetime as _dt
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import clock                      # noqa: E402
import db                         # noqa: E402
import hotsos_sync as hs          # noqa: E402

CONFIG = Path.home() / ".bgv-agent" / "agent.json"
KEYRING_SERVICE = "BGV HotSOS"
SSRS = ("https://ssrsreports.grandtimber.com/ReportServer?/Operations/Housekeeping/"
        "Housekeeping%20Dashboard&rs:Format=EXCELOPENXML&Cleans=Both")
SITE_ID = 8                         # Grand Colorado on Peak 8
FORECAST_DAYS = 21
FORECAST_HOURS = set(range(8, 21, 2))           # 08, 10 ... 20, property time
POLL_SECONDS = 5           # a Preview, Push or "Load this day" waits at most this
NIGHT_POLL_SECONDS = 30    # 22:00-04:30, when nobody presses anything: a sixth of the reads
REQUEST_MAX_AGE = 10 * 60   # a press older than this is not run -- see run_loop


_EVENTS = []          # the last lines of the log, for the Health page
_ERRORS_RE = ("fail", "error", "traceback", "expired", "not readable", "missing")


def log(msg):
    print(f"[{clock.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)
    first = str(msg).strip().splitlines()[0][:300] if str(msg).strip() else ""
    if first:
        bad = any(w in first.lower() for w in _ERRORS_RE)
        _EVENTS.append({"at": clock.stamp(), "msg": first, "level": "error" if bad else "info"})
        del _EVENTS[:-80]


def _file_info(path):
    try:
        p = Path(path)
        if not p.exists():
            return {"exists": False}
        return {"exists": True, "modified": _dt.datetime.fromtimestamp(
            p.stat().st_mtime, clock.MTN).isoformat(timespec="seconds")}
    except Exception as ex:
        return {"exists": False, "error": str(ex)}


def report_health(cfg, started_at):
    """What the Health page shows about this PC: what it can see, what it
    last did, what it will do next. Written every minute with the heartbeat."""
    import daily_build
    wb_daily, arr = daily_paths(cfg) if cfg.get("workbook") else (None, None)
    today = clock.today()
    tomorrow = today + _dt.timedelta(days=1)
    reports = {}
    for d in (today, tomorrow):
        p = daily_build.find_arrival_report(arr, d) if arr else None
        reports[str(d)] = ({"name": p.name, **_file_info(p)} if p else None)
    now = clock.now()
    next_fc = next((now.replace(hour=h, minute=0, second=0, microsecond=0)
                    for h in sorted(FORECAST_HOURS) if h > now.hour), None)
    next_build = now.replace(hour=BUILD_HOUR, minute=0, second=0, microsecond=0)
    if now.hour >= BUILD_HOUR:
        next_build += _dt.timedelta(days=1)
    db._upsert_key(hs.HEALTH_KEY, {
        "at": clock.stamp(), "host": socket.gethostname(), "started_at": started_at,
        "set_up": bool(cfg.get("workbook")), "hotsos_user": bool(cfg.get("hotsos_user")),
        "files": {"GC8 Inspections 2026.xlsx": _file_info(cfg.get("workbook") or ""),
                  "GC8 Daily Schedule.xlsx": _file_info(wb_daily or ""),
                  "Schedule.xlsx": _file_info(cfg.get("staff_workbook") or ""),
                  "Arrival Reports folder": _file_info(arr or "")},
        "arrival_reports": reports,
        "next": {"forecast": next_fc.isoformat(timespec="minutes") if next_fc else None,
                 "build": next_build.isoformat(timespec="minutes")},
    })
    db._upsert_key(hs.EVENTS_KEY, {"events": _EVENTS[-80:]})


# ── config ───────────────────────────────────────────────────────────────────
def load_config(required=True):
    """The agent's settings. The loop runs without them -- the forecast needs
    only SSRS and Supabase -- and picks them up once setup has been run."""
    if not CONFIG.exists():
        if not required:
            return {}
        sys.exit(f"Not set up yet. Run:  python {Path(__file__).name} setup")
    return json.loads(CONFIG.read_text())


def _find_workbook(name="GC8 Inspections 2026.xlsx"):
    """The synced copy, wherever OneDrive put it (usually under the user's home,
    in a folder named after the organisation)."""
    home = Path.home()
    for top in home.iterdir():
        if not top.is_dir() or top.name.startswith("."):
            continue
        if not any(k in top.name for k in ("Grand", "OneDrive", "SharePoint", "Timber")):
            continue
        for p in top.rglob(name):
            return p
    return None


def setup():
    import getpass
    import keyring
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    user = input(f"HotSOS username [{cfg.get('hotsos_user', '')}]: ").strip() \
        or cfg.get("hotsos_user", "")
    pw = getpass.getpass("HotSOS password (hidden; Enter keeps the saved one): ")
    if pw:
        keyring.set_password(KEYRING_SERVICE, user, pw)
    found = _find_workbook()
    hint = cfg.get("workbook") or (str(found) if found else "")
    wb = input(f"Path to the synced 'GC8 Inspections' workbook [{hint}]: ").strip().strip('"') or hint
    found = _find_workbook("Schedule.xlsx")
    hint = cfg.get("staff_workbook") or (str(found) if found else "")
    sw = input(f"Path to the synced staff 'Schedule.xlsx' [{hint}]: ").strip().strip('"') or hint
    for label, path in (("inspections workbook", wb), ("Schedule.xlsx", sw)):
        if not path or not Path(path).exists():
            print(f"  ! The {label} isn't there yet. Sync the SharePoint library "
                  "first (SharePoint > Documents > Sync), then run setup again.")
    cfg.update(hotsos_user=user, workbook=wb, staff_workbook=sw,
               shift=cfg.get("shift", "AM"))
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    print(f"Saved {CONFIG}. Password is in Windows Credential Manager "
          f"under '{KEYRING_SERVICE}'.")


def _hotsos(cfg):
    import keyring
    from hotsos_client import HotSOS
    pw = keyring.get_password(KEYRING_SERVICE, cfg["hotsos_user"])
    if not pw:
        raise RuntimeError("No HotSOS password saved -- run setup.")
    return HotSOS(cfg["hotsos_user"], pw, shift=cfg.get("shift", "AM"))


# ── SSRS forecast ────────────────────────────────────────────────────────────
def pull_ssrs(start: _dt.date, end: _dt.date, tag: str = "") -> Path:
    """Export the Housekeeping Dashboard as .xlsx, signed in as this PC's user.
    PowerShell does the Windows sign-in, which Python's requests cannot do
    without an extra package."""
    out = Path(tempfile.gettempdir()) / f"hskp_dashboard{tag}_{start}_{end}.xlsx"
    url = f"{SSRS}&SiteID={SITE_ID}&StartDate={start:%m/%d/%Y}&EndDate={end:%m/%d/%Y}"
    ps = (f"$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '{url}' "
          f"-UseDefaultCredentials -OutFile '{out}' -TimeoutSec 600")
    # Hidden: the agent runs without a console (pythonw), so every PowerShell it
    # started got a window of its own -- a black window flashing on the office
    # PC for each of the forecast's 22 downloads (9 Oct).
    si = subprocess.STARTUPINFO() if hasattr(subprocess, "STARTUPINFO") else None
    if si is not None:
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                     # SW_HIDE
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-Command", ps], capture_output=True, text=True, timeout=700,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), startupinfo=si)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"SSRS export failed: {(r.stderr or r.stdout).strip()[:400]}")
    return out


def refresh_forecast():
    import forecast
    import staffing
    start = clock.today()
    end = start + _dt.timedelta(days=FORECAST_DAYS)
    path = pull_ssrs(start, end)
    # Parse from memory and delete the file: read_dashboard's read-only
    # workbook keeps the file open, and the next pull to the same name then
    # fails with "being used by another process" for as long as the agent runs.
    import io
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    parsed = forecast.read_dashboard(io.BytesIO(data))
    days = []
    for r in forecast.forecast(parsed["days"], staffing.estimate):
        est = r.get("estimate", r)
        days.append({k: r.get(k) for k in ("date", "rooms", "minutes", "checkouts",
                                            "dailies", "dustnvac", "pu_models")}
                    | {k: est.get(k) for k in ("hskp", "hskp_fc", "hskp_ds", "rqs")}
                    | {"method": "estimate"})
    # Keep the pull before this one, so the page can say what new bookings
    # changed since -- the number alone doesn't tell anyone it moved.
    prev = db._load_key(hs.FORECAST_KEY) or {}
    # Until this pull's simulation reaches a day, show that day's last
    # simulated numbers rather than the rough arithmetic.
    SIM = ("hskp", "hskp_fc", "hskp_ds", "rqs", "rqs_fc", "fc_rooms",
           "check_rooms", "check_minutes")
    old = {d["date"]: d for d in prev.get("days", []) if d.get("method") == "simulated"}
    for d in days:
        if d["date"] in old:
            d.update({k: old[d["date"]].get(k) for k in SIM}, method="simulated")
    rec = {"pulled_at": clock.stamp(), "start": str(start), "end": str(end),
           "days": days, "warnings": parsed.get("warnings", []),
           "previous": {"pulled_at": prev.get("pulled_at"), "days": prev.get("days", [])}}
    db._upsert_key(hs.FORECAST_KEY, rec)
    log(f"forecast stored: {len(days)} days {start}..{end}; simulating each day")

    # Each day the way the 5 AM build will see it (forecast_sim): that day's
    # own export, the Schedule page's parsing and packing.
    import forecast_sim
    import daily_build
    cfg = load_config(required=False)
    _, arr_folder = daily_paths(cfg) if cfg.get("workbook") else (None, None)
    done = 0
    for d in days:
        try:
            day = _dt.date.fromisoformat(d["date"])
            p = pull_ssrs(day, day, tag="_sim")
            raw = p.read_bytes()
            p.unlink(missing_ok=True)
            text, n = forecast_sim.room_text(raw)
            # The same rooms "Load this day" on the Schedule page wants: kept
            # so it can read them at once rather than ask this PC and wait.
            arr = daily_build.find_arrival_report(arr_folder, day) if arr_folder else None
            db._upsert_key(hs.ROOMS_CACHE_PREFIX + d["date"], {
                "date": d["date"], "room_text": text, "rooms": n,
                "pulled_at": clock.stamp(), "arrival": arr.name if arr else None,
                "arrival_text": daily_build.read_arrival_report(arr) if arr else ""})
            d.update(forecast_sim.simulate_text(text, n, day), method="simulated")
            done += 1
        except Exception as ex:
            log(f"forecast simulation {d['date']}: {type(ex).__name__}: {ex}")
        if done and done % 3 == 0:
            db._upsert_key(hs.FORECAST_KEY, rec)
    rec["simulated_at"] = clock.stamp()
    db._upsert_key(hs.FORECAST_KEY, rec)
    # Old day copies are archived to SharePoint and removed by the nightly
    # free-plan clean-up (freetier), not deleted here without a copy.
    try:
        import freetier
        freetier.flush("forecast", force=True)
    except Exception as ex:
        log(f"forecast usage not recorded: {ex}")
    log(f"forecast simulated: {done} of {len(days)} days")
    return days


def load_day_rooms(cfg, req):
    """A day's rooms (SSRS) and Arrival Report, for the Schedule page to run
    that day by hand. Read-only: nothing is built, written or pushed."""
    import importlib
    import io
    import daily_build
    res = {"id": req["id"], "date": req["date"], "by": req.get("by", ""),
           "status": "running", "started_at": clock.stamp()}
    db._upsert_key(hs.DAYLOAD_RESULT_KEY, res)
    try:
        daily_build = importlib.reload(daily_build)
        day = _dt.date.fromisoformat(req["date"])
        p = pull_ssrs(day, day, tag="_load")
        raw = p.read_bytes()
        p.unlink(missing_ok=True)
        (to_text,) = daily_build.borrow("excel_to_room_text")
        text, n, _ = to_text(io.BytesIO(raw))
        _, arr_folder = daily_paths(cfg)
        arr = daily_build.find_arrival_report(arr_folder, day) if arr_folder else None
        res.update(status="done", room_text=text, rooms=int(n),
                   arrival=arr.name if arr else None,
                   arrival_text=daily_build.read_arrival_report(arr) if arr else "",
                   pulled_at=clock.stamp())
        db._upsert_key(hs.ROOMS_CACHE_PREFIX + req["date"], {
            k: res[k] for k in ("room_text", "rooms", "arrival", "arrival_text", "pulled_at")}
            | {"date": req["date"]})
        log(f"day load {day} for {req.get('by')}: {n} rooms, arrival report "
            f"{'found' if arr else 'none'}")
    except Exception as ex:
        res.update(status="error", error=f"{type(ex).__name__}: {ex}")
        log(f"day load failed: {res['error']}")
    res["finished_at"] = clock.stamp()
    db._upsert_key(hs.DAYLOAD_RESULT_KEY, res)


# ── room status: HotSOS -> app (a read-only mirror) ──────────────────────────
STATUS_SYNC_SECONDS = 120
STATUS_HOURS = range(6, 20)            # property time; the floor's day and then some
_STATUS_HS = None                      # one signed-in HotSOS, kept between passes


def _status_session(cfg, fresh=False):
    global _STATUS_HS
    if fresh:
        _close_status_session()
    if _STATUS_HS is None:
        _STATUS_HS = _hotsos(cfg)
    return _STATUS_HS


def _close_status_session():
    global _STATUS_HS
    if _STATUS_HS is not None:
        try:
            _STATUS_HS.close()
        except Exception:
            pass
    _STATUS_HS = None


def _hs_time(ts):
    """A timeline time as stored ISO (property time), or None for a time
    HotSOS only projects. Its projections are worked out from 'now' to seven
    decimal places (13:04:56.4434337); what actually happened carries three
    at most (11:36:44.77)."""
    if not ts:
        return None
    s = str(ts)
    frac = s.split(".", 1)[1] if "." in s else ""
    if len(frac) >= 7:
        return None
    try:
        t = _dt.datetime.fromisoformat(s.split(".", 1)[0])
    except ValueError:
        return None
    return t.replace(tzinfo=clock.MTN).isoformat(timespec="seconds")


def sync_room_status(cfg):
    """Mirror HotSOS's room statuses onto today's charted rooms.

    The floor marks rooms in HotSOS; the app's own buttons are switched off
    (roomstatus.mirrored) so the two can't disagree. Each pass reads the room
    board (status, who holds the room) and the attendants' timeline (when a
    room was actually started and finished) and writes only the rooms whose
    mirror changed. The app's notes are its own and never touched."""
    import collections
    import roomstatus as rs
    import staff_names
    from hotsos_client import HotSOSError, _pick, _ROOM_CODE
    sched = db.load_full_schedule() or {}
    chart = {}
    for g in sched.get("groups_data") or []:
        for r in g.get("rooms") or []:
            chart[str(r.get("room", "")).upper()] = (str(r.get("room")), g.get("label", ""),
                                                     g.get("housekeeper") or "",
                                                     g.get("inspector") or "")
    if not chart:
        return {"at": clock.stamp(), "rooms": 0, "changed": 0, "why": "no schedule today"}

    def read(h):
        board = h._paged("/RoomAssignment", {"shift": h.shift, "includeCount": True,
                                             "filters": {}, "search": []},
                         {"takePerPage": 200})
        return board, h.timeline()
    try:
        board, tl = read(_status_session(cfg))
    except HotSOSError:                        # signed out overnight, say: once more
        board, tl = read(_status_session(cfg, fresh=True))

    when = {str(x["room"]).upper(): x for a in tl for x in (a.get("assignments") or [])
            if x.get("room") and not x.get("isBreak")}
    current = db.get_room_statuses() or {}
    # Once per pass: looked up per room, the directory was read ~380,000
    # times in October -- a quarter of everything the free plan counted.
    names = staff_names.aliases()
    rows, counts, unknown = [], collections.Counter(), set()
    for r in board:
        code = str(_pick(r, _ROOM_CODE, "room number")).upper().strip()
        if code not in chart:
            continue
        key, label, hk_chart, insp = chart[code]
        enum = str(r.get("serviceStatusEnum") or "")
        if enum and enum.upper() not in rs.HOTSOS:
            unknown.add(f"{enum} ({r.get('serviceStatus')})")
        st = rs.from_hotsos(enum, r.get("serviceStatus"))
        counts[st] += 1
        t = when.get(code) or {}
        old = current.get(key) or {}
        started, cleaned, inspected = (old.get("started_at"), old.get("cleaned_at"),
                                       old.get("inspected_at"))
        if st == rs.PENDING:
            started = cleaned = inspected = None
        else:
            started = _hs_time(t.get("start")) or started
            if st in rs.READY + (rs.INSPECTED,):
                cleaned = _hs_time(t.get("end")) or cleaned
            if st == rs.INSPECTED:
                inspected = inspected or clock.stamp()    # HotSOS gives no time for it
            elif st in rs.READY:
                inspected = None
        # HotSOS's labels carry stray spaces ("David  Serrano"); one spelling
        # per person, the app's.
        hk = staff_names.full(" ".join(str(r.get("assignedTo") or "").split()), names) or hk_chart
        row = {"room": key, "status": st, "started_at": started, "cleaned_at": cleaned,
               "inspected_at": inspected, "housekeeper": hk,
               "swapped_from": hk_chart if hk != hk_chart else None,
               "group_label": label, "inspector": insp, "updated_by": "HotSOS"}

        def same(a, b):
            # Times come back from the database in its own offset; compare
            # the moments, not the text.
            if a and b and "T" in str(a) and "T" in str(b):
                try:
                    return (_dt.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
                            == _dt.datetime.fromisoformat(str(b).replace("Z", "+00:00")))
                except ValueError:
                    pass
            return str(a or "") == str(b or "")
        if any(not same(row[k], old.get(k)) for k in row if k != "room"):
            rows.append(row)
    if rows:
        db.bulk_upsert_room_statuses(rows)
    rec = {"at": clock.stamp(), "rooms": sum(counts.values()), "changed": len(rows),
           "counts": dict(counts), "unknown": sorted(unknown)}
    if rows or unknown:
        log(f"room status: {len(rows)} changed of {rec['rooms']} "
            f"({', '.join(f'{k} {v}' for k, v in counts.most_common())})"
            + (f"; new HotSOS states {sorted(unknown)}" if unknown else ""))
    return rec


def reconcile_charts():
    """After the mirror: if HotSOS is the truth for today (pushed, or
    reconciled by hand) and nobody has generated a new schedule since, bring
    today's charts in line with who holds each room in HotSOS. A schedule
    generated after the push is newer than HotSOS -- left alone until it is
    pushed too."""
    import app_sync
    truth = db._load_key(hs.TRUTH_KEY) or {}
    if truth.get("date") != clock.today_iso():
        return None
    gen = (db.load_full_schedule() or {}).get("generated_at")
    if gen and _dt.datetime.fromisoformat(gen) > _dt.datetime.fromisoformat(truth["at"]):
        return "generated after the push; waiting for the next push"
    out = app_sync.from_hotsos(save=True)
    if out.get("changed"):
        log(f"charts reconciled to HotSOS: {len(out['renamed'])} chart(s) changed hands, "
            f"{len(out['moved'])} room(s) moved")
        return {"renamed": out["renamed"], "moved": out["moved"]}
    return None


SHEET_SYNC_SECONDS = 600
_SHEET_SEEN = {}


def sync_sheet(cfg):
    """What the team typed in today's tab since the push -- the RQS on each
    room, rooms added by hand -- carried into the app (app_sync.from_sheet;
    HP 22 Oct: RQS changed on 18 rooms after 8 and the app kept the 5 AM
    ones). Same rule as reconcile_charts: only once today is pushed and no
    schedule has been generated since. Read from the synced copy, and only
    when it changed since the last look; a copy that is mid-sync is tried
    again next time."""
    import app_sync
    path = cfg.get("workbook")
    if not path or not Path(path).exists():
        return None
    truth = db._load_key(hs.TRUTH_KEY) or {}
    if truth.get("date") != clock.today_iso():
        return None
    gen = (db.load_full_schedule() or {}).get("generated_at")
    if gen and _dt.datetime.fromisoformat(gen) > _dt.datetime.fromisoformat(truth["at"]):
        return None
    mtime = Path(path).stat().st_mtime
    if _SHEET_SEEN.get("mtime") == mtime and _SHEET_SEEN.get("day") == clock.today_iso():
        return None
    tab, rows = hs.read_workbook(path, clock.today())
    out = app_sync.from_sheet(rows, save=True)
    _SHEET_SEEN.update(mtime=mtime, day=clock.today_iso())
    if out.get("changed"):
        log(f"sheet -> app ({tab}): RQS on {len(out['rqs'])} room(s), "
            f"{len(out['split'])} chart(s) split, {len(out['added'])} room(s) added"
            + (f"; no housekeeper named, not placed: {', '.join(out['unplaced'])}"
               if out.get("unplaced") else ""))
    return out


# The mirror keeps one HotSOS browser signed in all day. Playwright allows one
# of those per thread: on the loop's own thread, the next Preview, Push or
# SharePoint read failed with "using Playwright Sync API inside the asyncio
# loop" (9 Oct). So the mirror has a thread of its own, and only it ever
# touches its session.
_MIRROR = None


_SYNC_HISTORY = []


def _mirror_loop():
    while True:
        try:
            cfg = load_config(required=False)
            if cfg.get("hotsos_user") and clock.now().hour in STATUS_HOURS:
                try:
                    rec = sync_room_status(cfg)
                    rec["reconciled"] = reconcile_charts()
                    # On this thread, after the reconcile, so the two never
                    # write today's charts at the same moment.
                    if time.time() - _SHEET_SEEN.get("at", 0) > SHEET_SYNC_SECONDS:
                        _SHEET_SEEN["at"] = time.time()
                        try:
                            rec["sheet"] = bool((sync_sheet(cfg) or {}).get("changed"))
                        except Exception as ex:
                            log(f"sheet -> app: {type(ex).__name__}: {ex}")
                except Exception as ex:
                    rec = {"at": clock.stamp(), "error": f"{type(ex).__name__}: {ex}"}
                    log(f"room status sync failed: {rec['error']}")
                    _close_status_session()
                _SYNC_HISTORY.append({"at": rec.get("at"), "changed": rec.get("changed", 0),
                                      "error": bool(rec.get("error"))})
                del _SYNC_HISTORY[:-90]
                rec["history"] = list(_SYNC_HISTORY)
                db._upsert_key(hs.STATUS_SYNC_KEY, rec)
            else:
                _close_status_session()    # no Chrome sitting signed in overnight
        except Exception as ex:            # never let the thread die
            log(f"mirror loop: {type(ex).__name__}: {ex}")
        time.sleep(STATUS_SYNC_SECONDS)


def start_mirror():
    global _MIRROR
    if _MIRROR is None or not _MIRROR.is_alive():
        import threading
        _MIRROR = threading.Thread(target=_mirror_loop, name="hotsos-mirror", daemon=True)
        _MIRROR.start()


_FORECAST_PROC = None


def start_forecast():
    """Run the forecast in its own process: simulating three weeks takes a
    few minutes, and a Push pressed meanwhile must not wait for it."""
    global _FORECAST_PROC
    if _FORECAST_PROC is not None and _FORECAST_PROC.poll() is None:
        log("forecast already running")
        return
    # Below normal priority: three weeks of chart-solving uses every core it
    # can, and a Preview pressed meanwhile took nine minutes (9 Oct 13:37).
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) |         getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    _FORECAST_PROC = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                       "forecast"], cwd=str(Path(__file__).resolve().parent),
                                      creationflags=flags)


# ── staff schedule (Schedule.xlsx) ───────────────────────────────────────────
STATE = CONFIG.parent / "state.json"
SETTLE_SECONDS = 60      # OneDrive writes a file in pieces; wait until it's still


def _state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def sync_roster(path, force=False):
    """Import Schedule.xlsx if it changed since the last import -- the same
    save as Roster Import's button (roster_sync.save). Returns the result, or
    None when there was nothing to do."""
    import hashlib
    import roster_sync
    p = Path(path)
    if not p.exists():
        return None
    stat = p.stat()
    if not force and time.time() - stat.st_mtime < SETTLE_SECONDS:
        return None                     # still being written; next pass
    # The loop passes every few seconds; reading and hashing the whole file
    # each time is waste when it hasn't been touched.
    seen = (stat.st_mtime, stat.st_size)
    if not force and getattr(sync_roster, "seen", None) == seen:
        return None
    raw = p.read_bytes()                # raises if Excel holds it locked; retried
    digest = hashlib.sha256(raw).hexdigest()
    st = _state()
    if not force and st.get("roster_sha") == digest:
        sync_roster.seen = seen
        return None
    status = {"at": clock.stamp(), "file": p.name}
    try:
        out = roster_sync.save(raw, p.name, "SharePoint sync (office PC)",
                               reset_today="if_today_changed")
        d = out["diff"]
        status.update(saved=out["saved"], failed=out["failed"],
                      new_weeks=d["new_weeks"], changed_cells=d["n_changed_cells"],
                      today_changed=out["today_changed"])
        if not out["failed"]:
            st["roster_sha"] = digest
            STATE.write_text(json.dumps(st))
            sync_roster.seen = seen     # a failed import is retried next pass
        log(f"roster synced: {out['saved']} week(s), {d['n_changed_cells']} cell(s) "
            f"changed, today {'changed' if out['today_changed'] else 'unchanged'}")
    except Exception as ex:
        status["error"] = f"{type(ex).__name__}: {ex}"
        log(f"roster sync failed: {ex}")
    db._upsert_key(hs.ROSTER_STATUS_KEY, status)
    return status


# ── the 5 AM build (daily_build.py) ──────────────────────────────────────────
BUILD_HOUR = 5


def daily_paths(cfg):
    """GC8 Daily Schedule.xlsx and the Arrival Reports folder sit beside the
    synced GC8 Inspections workbook, so they're in SharePoint without anyone
    doing anything."""
    base = Path(cfg["workbook"]).parent if cfg.get("workbook") else None
    wb = cfg.get("daily_workbook") or (str(base / "GC8 Daily Schedule.xlsx") if base else None)
    arr = cfg.get("arrival_folder") or (str(base / "Arrival Reports") if base else None)
    return wb, arr


def read_day(cfg, day):
    """The day's tab: the big GC8 Inspections workbook first -- the RQS have
    its link and make their changes there, and the build now writes each
    day's tab into it -- then the daily workbook, the build's own copy, for a
    day the big one has no tab for (its save was skipped, say).

    Read live from SharePoint at the moment of the press (sharepoint.fetch),
    so an edit made seconds ago in Excel Online is in -- the synced copy on
    this PC trails it by up to a minute. If SharePoint can't be reached the
    synced copy is used, and read_day.source says which it was and why.
    The big workbook is only downloaded (13 s, 3 MB) if the daily one has no
    tab for the day; whether it *also* has one is checked on the synced copy,
    which is only for the warning."""
    import io
    import sharepoint
    daily, _ = daily_paths(cfg)
    read_day.source, read_day.by, read_day.warning = "", "", ""
    found, last, why = [], None, ""
    for path in (cfg.get("workbook"), daily):
        if not path:
            continue
        name = Path(path).name
        if found:                                   # duplicate check only
            if Path(path).exists():
                try:
                    found.append((name,) + hs.read_workbook(path, day) + (None, "", "synced"))
                except LookupError:
                    pass
            continue
        data, info = sharepoint.fetch(name)
        try:
            if data is not None:
                t = _dt.datetime.fromisoformat(info["modified"].replace("Z", "+00:00"))
                found.append((name,) + hs.read_workbook(io.BytesIO(data), day)
                             + (t.astimezone(clock.MTN), info.get("by", ""), "live"))
            elif Path(path).exists():
                why = why or info.get("error", "")
                saved = _dt.datetime.fromtimestamp(Path(path).stat().st_mtime, clock.MTN)
                found.append((name,) + hs.read_workbook(path, day) + (saved, "", "synced"))
        except LookupError as ex:
            last = ex
    if not found:
        raise last or LookupError(f"No workbook with a tab for {day}")
    name, tab, rows, saved, by, source = found[0]
    read_day.saved_at = saved.isoformat(timespec="seconds")
    read_day.by = by
    read_day.source = ("live from SharePoint" if source == "live" else
                       "the synced copy on the office PC" + (f" (SharePoint: {why})" if why else ""))
    # Both files carry the day now, by design, and once the RQS work in the
    # big one the daily copy always differs. It only matters when somebody
    # edited the copy that isn't read -- the daily tab changed since the build
    # wrote it (its fingerprint, which the builder keeps): an edit in the
    # wrong file. The file's own save time says nothing; any rebuild of
    # another day's tab re-saves it.
    read_day.warning = ""
    if len(found) > 1 and found[0][2] != found[1][2] and daily and Path(daily).exists():
        try:
            import daily_build
            edited = daily_build.tab_edited(daily, day, _state().get("tabs", {}))
        except Exception:
            edited = False
        if edited:
            read_day.warning = (f"Someone edited {found[1][0]} ('{found[1][1]}'), which "
                                f"differs from {found[0][0]} ('{found[0][1]}'). Push uses "
                                f"{found[0][0]} -- make the changes there.")
    return f"{tab} ({name})", rows

BIG_QUIET_MINUTES = 10


def _big_guard(path):
    """May the build save the big workbook right now? Only if SharePoint
    answers, nobody has saved it in the last few minutes (someone may still
    be typing), and the synced copy here is not behind SharePoint -- saving
    an old copy would throw away whatever was typed online since."""
    if not path:
        return None

    def guard():
        import sharepoint
        data, info = sharepoint.fetch(Path(path).name)
        if data is None:
            return False, f"SharePoint not reachable: {info.get('error', '')}"
        sp = _dt.datetime.fromisoformat(info["modified"].replace("Z", "+00:00"))
        mins = (clock.now() - sp).total_seconds() / 60
        if mins < BIG_QUIET_MINUTES:
            return False, f"{info.get('by') or 'someone'} saved it {mins:.0f} min ago"
        local = _dt.datetime.fromtimestamp(Path(path).stat().st_mtime, _dt.timezone.utc)
        if (sp - local).total_seconds() > 120:
            return False, "the synced copy on the office PC is behind SharePoint"
        return True, ""
    return guard


def run_build(cfg, day=None, by="5 AM", publish=True):
    """Build the day's schedule and write its tab. Never pushes to HotSOS."""
    import importlib
    import daily_build
    # The agent runs for weeks; a fix to the builder must reach the next 5 AM
    # run without anyone restarting it.
    daily_build = importlib.reload(daily_build)
    day = day or clock.today()
    # A later day is a look-ahead: built from that day's rooms and roster,
    # written as its tab, never saved to the app (which holds today only).
    ahead = day > clock.today()
    key = daily_build.BUILD_KEY + ("_ahead" if ahead else "")
    publish = publish and not ahead
    status = {"date": str(day), "by": by, "started_at": clock.stamp(), "status": "running",
              "ahead": ahead}
    db._upsert_key(key, status)
    try:
        if day < clock.today():
            raise ValueError(f"{day} has passed; only today or a later day can be built.")
        wb_path, arr_folder = daily_paths(cfg)
        if not wb_path:
            raise RuntimeError("Not set up: no GC8 Inspections workbook path (run setup).")
        path = pull_ssrs(day, day)
        ssrs = path.read_bytes()
        path.unlink(missing_ok=True)
        arr = daily_build.find_arrival_report(arr_folder, day) if arr_folder else None
        arrival = daily_build.read_arrival_report(arr) if arr else ""
        st = _state()
        tabs = st.setdefault("tabs", {})
        # The app's charts are replaced only if they're the 5 AM build's own (or
        # there are none yet). A schedule somebody generated or adjusted in the
        # app today is theirs; the build then only writes the sheet.
        sched = db.load_full_schedule() or {}
        mine = (not sched.get("groups_data") or sched.get("generated_by") == "auto-5am")             and not ahead
        status["app_saved"] = bool(publish and mine)
        if publish and not mine:
            log(f"build: app schedule by {sched.get('generated_by')} kept; writing the sheet only")
        out = daily_build.build(day, ssrs, arrival, wb_path, tabs,
                                publish=publish and mine,
                                big_path=cfg.get("workbook"),
                                guard=_big_guard(cfg.get("workbook")))
        STATE.write_text(json.dumps(st))
        status.update(out, status="done", arrival=arr.name if arr else None,
                      workbook=Path(wb_path).name)
        log(f"built {day}: {out['rooms']} rooms, {out['charts']} charts, tab {out['tab']} "
            f"{out['outcome']}; GC8 Inspections 2026: {out.get('big_tab')}; "
            f"arrival report {'found' if arr else 'MISSING'}")
    except Exception as ex:
        status.update(status="error", error=f"{type(ex).__name__}: {ex}")
        log(f"build failed: {traceback.format_exc()}")
    status["finished_at"] = clock.stamp()
    db._upsert_key(key, status)
    return status


# ── the Report page's numbers ────────────────────────────────────────────────
def sync_report(cfg, by="4 PM"):
    """Read every day tab of GC8 Inspections and store it for the Report page
    (report_data). Live from SharePoint, so a correction typed a minute ago
    is counted; the synced copy if SharePoint can't be reached. Only reads
    the workbook."""
    import importlib
    import io
    import report_data
    import sharepoint
    report_data = importlib.reload(report_data)     # a fix reaches the next sync
    path = cfg["workbook"]
    db._upsert_key(report_data.SYNC_KEY, dict(db._load_key(report_data.SYNC_KEY) or {},
                                              status="running", started_at=clock.stamp(),
                                              by=by))
    try:
        data, info = sharepoint.fetch(Path(path).name)
        if data is not None:
            src, source = io.BytesIO(data), "live from SharePoint"
            saved_at, saved_by = info.get("modified"), info.get("by", "")
        else:
            src = path
            source = "the synced copy on the office PC" + (
                f" (SharePoint: {info['error']})" if info.get("error") else "")
            saved_at = _dt.datetime.fromtimestamp(Path(path).stat().st_mtime,
                                                  clock.MTN).isoformat(timespec="seconds")
            saved_by = ""
        res = report_data.read_workbook(src, report_data.workbook_year(path), upto=clock.today())
        rec = report_data.store(db, res, clock.stamp(), by, source, saved_at, saved_by)
        log(f"report: {len(res['days'])} days read {source}; months changed: "
            f"{', '.join(rec['written']) or 'none'}")
        return rec
    except Exception as ex:
        log(f"report sync failed: {traceback.format_exc()}")
        rec = dict(db._load_key(report_data.SYNC_KEY) or {}, status="error",
                   error=f"{type(ex).__name__}: {ex}", failed_at=clock.stamp())
        db._upsert_key(report_data.SYNC_KEY, rec)
        return rec


_REPORT = {"thread": None}


def start_report(cfg, by) -> bool:
    """sync_report on its own thread; False if one is still running.

    Reading every tab takes seconds on a quiet PC and can take many minutes
    on a busy one -- on 14 Oct the PC had 0.2 GB free, the agent was paged
    out, and the first sync held the loop (and with it Push) for over ten
    minutes. The loop has to keep answering while it reads."""
    import threading
    t = _REPORT["thread"]
    if t is not None and t.is_alive():
        return False
    t = threading.Thread(target=sync_report, args=(cfg, by), name="report-sync", daemon=True)
    _REPORT["thread"] = t
    t.start()
    return True


# ── auto-push ────────────────────────────────────────────────────────────────
#: app_settings: {"daily": true, "days": ["2026-10-12", ...], "after": "05:30",
#: "set_by": ...}. Every day with "daily" (Hari, 15 Oct: push every morning,
#: changes are made by hand afterwards), otherwise on the days listed -- it
#: began as the days the manager was away. The morning's sheet goes to HotSOS
#: without anybody pressing Push; whoever is on can still change rooms in
#: HotSOS directly, and the app follows (the mirror reconciles).
AUTO_PUSH_KEY = "hotsos_auto_push"
AUTO_PUSH_GIVE_UP = 9          # no finished build by 9 AM: leave it to a person


def auto_push_due(now, plan, build, last, done_day):
    """Why the day's auto-push should or shouldn't be queued now:
    ("push", why), ("wait", why) or ("skip", why). No side effects."""
    today = str(now.date())
    if done_day == today:
        return "skip", "already handled today"
    if not plan.get("daily") and today not in (plan.get("days") or []):
        return "skip", "not an auto-push day"
    hh, mm = (int(x) for x in str(plan.get("after") or "05:30").split(":"))
    if (now.hour, now.minute) < (hh, mm):
        return "wait", f"before {hh:02d}:{mm:02d}"
    if last.get("mode") == "push" and last.get("date") == today:
        return "skip", f"pushed already by {last.get('by') or 'someone'}"
    if build.get("date") != today or build.get("status") != "done":
        if now.hour >= AUTO_PUSH_GIVE_UP:
            return "skip", f"no finished 5 AM build by {AUTO_PUSH_GIVE_UP}:00 ({build.get('status')})"
        return "wait", f"the 5 AM build is {build.get('status') or 'not started'}"
    return "push", "build done"


_auto_plan = {"read": 0.0, "plan": {}}


def _auto_push():
    """Queue the day's Push once, as an ordinary request -- so it runs,
    answers on the HotSOS page and is logged exactly like somebody pressing
    Push. Reads the agent's state fresh: the copy the loop holds is stale once
    a build has written its tab fingerprints.

    The loop comes round every few seconds, so the list of days is read at
    most every ten minutes, and the build and push records only on a listed
    day once it is time -- not three database reads a pass, all day."""
    import daily_build
    now = clock.now()
    state = _state()
    if state.get("auto_pushed") == str(now.date()):
        return
    if time.time() - _auto_plan["read"] > 600:
        _auto_plan.update(read=time.time(), plan=db._load_key(AUTO_PUSH_KEY) or {})
    plan = _auto_plan["plan"]
    verdict, why = auto_push_due(now, plan, {}, {}, None)
    if verdict == "wait" and why.startswith("before") or why == "not an auto-push day":
        return
    verdict, why = auto_push_due(now, plan,
                                 db._load_key(daily_build.BUILD_KEY) or {},
                                 db._load_key(hs.LAST_KEY) or {},
                                 state.get("auto_pushed"))
    if verdict == "wait" or why in ("already handled today", "not an auto-push day"):
        return
    state["auto_pushed"] = str(now.date())
    STATE.write_text(json.dumps(state))
    if verdict == "skip":
        log(f"auto-push {now.date()}: not sent -- {why}")
        return
    db._upsert_key(hs.REQUEST_KEY, {"id": uuid.uuid4().hex, "date": str(now.date()),
                                    "mode": "push", "by": "auto (5 AM build)",
                                    "at": clock.stamp()})
    log(f"auto-push {now.date()}: queued after the 5 AM build")


# ── push / preview ───────────────────────────────────────────────────────────
def run_push(cfg, day: _dt.date, mode: str, only_room=None, req_id=None, by=""):
    """Build the plan for `day` and, for mode 'push', send it. Returns the
    result dict that is stored for the page."""
    res = {"id": req_id or uuid.uuid4().hex, "date": str(day), "mode": mode, "by": by,
           "status": "running", "started_at": clock.stamp()}
    # Only a run the page asked for answers on the page. A console run used to
    # write here too, and replaced the answer to a push someone was waiting on.
    store = req_id is not None
    if store:
        db._upsert_key(hs.RESULT_KEY, res)
    h = None
    try:
        import staff_names
        if mode != "staff":
            tab, rows = read_day(cfg, day)
            res["tab"] = tab
            res["sheet_saved_at"] = getattr(read_day, "saved_at", None)
            import rule23
            _sheet = [{"Room": r["room"], "Service": r["service"], "HSKP": r["hskp"],
                       "RQS": r.get("rqs", "")} for r in rows]
            res["rule23"] = {"HSKP": rule23.violations(_sheet, "HSKP"),
                             "RQS": rule23.violations(_sheet, "RQS")}
            res["sheet_by"] = getattr(read_day, "by", "")
            res["sheet_source"] = getattr(read_day, "source", "")
            if read_day.warning:
                res["warning"] = read_day.warning
            if only_room:
                rows = [r for r in rows if r["room"] == only_room.upper()]
        h = _hotsos(cfg)
        attendants = h.attendants()
        # HotSOS's own list is the directory's source of full names; keep it
        # fresh every time we're signed in anyway.
        db._upsert_key(staff_names.ATTENDANTS_KEY, {"pulled_at": clock.stamp(),
                                                   "attendants": attendants})
        if mode == "staff":
            res.update(status="done", attendants=[a["label"] for a in attendants])
            return res
        # The approved directory first; the older per-push name table still
        # counts for anything it doesn't cover.
        names = dict(db._load_key(hs.NAMES_KEY) or {}, **staff_names.aliases())
        plan = hs.build_plan(rows, h.rooms(), attendants, names)
        res.update(plan=plan, attendants=[a["label"] for a in attendants],
                   **hs.summary(plan))
        if mode == "push":
            sent, errors = 0, []
            for pid, gids in hs.batches(plan).items():
                st, body = h.assign(gids, pid)
                who = next(l["hotsos_name"] for l in plan if l["person_id"] == pid)
                ok = st in (200, 204, 207)
                for l in plan:
                    if l["person_id"] == pid and l["gid"] in gids:
                        l["outcome"] = "sent" if ok else f"HTTP {st}"
                if ok:
                    sent += len(gids)
                    if st == 207:   # partly done: HotSOS lists what it refused
                        errors.append(f"{who}: some rooms refused: {str(body)[:300]}")
                else:
                    errors.append(f"{who}: HTTP {st}: {str(body)[:300]}")
                log(f"  {who}: {len(gids)} rooms -> HTTP {st}")
            res.update(sent=sent, errors=errors)
            # The sheet is final and HotSOS has it: make the app's charts (what
            # the phones show) say the same. Only for today -- the app holds
            # one day's schedule.
            if day == clock.today():
                if sent:
                    db._upsert_key(hs.TRUTH_KEY, {"date": str(day), "at": clock.stamp(),
                                                  "by": f"push by {by}"})
                try:
                    import app_sync
                    app = app_sync.apply(plan)
                    res["app"] = {"renamed": len(app.get("renamed", [])),
                                  "moved": len(app.get("moved", [])),
                                  "inspectors": len(app.get("inspectors", [])),
                                  "changed": app.get("changed", False),
                                  "why": app.get("why", "")}
                    log(f"  app charts: {res['app']}")
                except Exception as ex:
                    res.setdefault("errors", []).append(f"App charts not updated: {ex}")
                # The Engineering team's daily sheet (RQS-ENG-Runners tab):
                # the day's RQS rooms and AM housepersons, queued for the
                # "BGV ENG sheet" flow to write in Excel Online. Today only:
                # that sheet is the day's, and a push ahead must not replace it.
                # On every push, not only one that moved rooms: an RQS swap on
                # the sheet changes nothing in HotSOS but does change this.
                if not only_room and cfg.get("backup"):
                    res["eng_sheet"] = "not queued: sent by the backup PC, which has no synced SharePoint folder"
                elif not only_room:
                    try:
                        import importlib
                        import eng_sheet
                        eng_sheet = importlib.reload(eng_sheet)   # a fix reaches the next push
                        f = eng_sheet.publish(Path(cfg["workbook"]).parent, day, rows)
                        res["eng_sheet"] = f.name
                        log(f"  ENG sheet values queued: {f.name}")
                    except Exception as ex:
                        res["eng_sheet"] = f"not queued: {type(ex).__name__}: {ex}"
                        log(f"  ENG sheet not queued: {ex}")
        res["status"] = "done" if not res.get("errors") else "done with errors"
    except Exception as ex:
        res.update(status="error", error=f"{type(ex).__name__}: {ex}")
        log(traceback.format_exc())
    finally:
        if h:
            h.close()
        res["finished_at"] = clock.stamp()
        if store:
            db._upsert_key(hs.RESULT_KEY, res)
            # The page keeps showing the last finished plan while a new one
            # runs or fails, so the result doesn't vanish on every press.
            if mode in ("preview", "push") and res.get("plan") is not None:
                db._upsert_key(hs.LAST_KEY, res)
    return res


def _print_plan(res):
    print(f"\n{res['mode'].upper()} {res['date']}  tab={res.get('tab')}  status={res['status']}")
    if res.get("error"):
        print("  ERROR:", res["error"])
    for l in res.get("plan", []):
        print(f"  {l['room']:6} {l['service'][:14]:14} {l['who'][:14]:14} -> "
              f"{l['hotsos_name'][:20]:20} {l['action']:24} now: {l['current']} "
              f"{l.get('outcome', '')}")
    print("  counts:", res.get("counts"), " unmatched:", res.get("unmatched_names"))
    for e in res.get("errors", []):
        print("  !", e)


# ── the loop ─────────────────────────────────────────────────────────────────
def run_loop():
    cfg = load_config(required=False)
    started_at = clock.stamp()
    log(f"agent up on {socket.gethostname()}; workbook {cfg.get('workbook') or '(not set up)'}")
    done_req = (db._load_key(hs.RESULT_KEY) or {}).get("id")
    done_day = (db._load_key(hs.DAYLOAD_RESULT_KEY) or {}).get("id")
    last_watch = 0
    # The last Refresh request is still on record at start-up; treating it as
    # new started another forecast on every restart (two at once, 9 Oct).
    done_fc = (db._load_key(hs.FORECAST_REQUEST_KEY) or {}).get("id")
    import report_data as rdm
    done_rep = (db._load_key(rdm.REQUEST_KEY) or {}).get("id")
    last_rep = 0
    last_slot = None
    last_beat = 0
    last_cred = _register("office")
    last_teams = 0
    _LOOP_PASS[0] = time.time()
    start_beat()
    while True:
        try:
            _LOOP_PASS[0] = time.time()
            last_cred = _cred_poll(last_cred, every=120)
            if time.time() - last_beat > 60:
                last_beat = time.time()
                try:
                    report_health(load_config(required=False), started_at)
                except Exception as ex:
                    print(f"health report failed: {ex}", flush=True)

            # Every button the pages can press, in one read: these were four
            # separate reads every 5 s -- 15% of October's data sent.
            asks = db._load_keys([hs.REQUEST_KEY, hs.DAYLOAD_REQUEST_KEY,
                                  hs.FORECAST_REQUEST_KEY, rdm.REQUEST_KEY])
            req = asks.get(hs.REQUEST_KEY) or {}
            if req.get("id") and req["id"] != done_req:
                done_req = req["id"]
                # A Push must happen when it was pressed or not at all: after
                # an outage the agent once ran an hour-old Push against a sheet
                # that had changed since.
                try:
                    age = (clock.now() - _dt.datetime.fromisoformat(req["at"])).total_seconds()
                except Exception:
                    age = 0
                if age > REQUEST_MAX_AGE:
                    log(f"{req.get('mode')} from {req.get('at')} expired ({int(age // 60)} min old)")
                    db._upsert_key(hs.RESULT_KEY, {
                        "id": req["id"], "date": req.get("date"), "mode": req.get("mode"),
                        "by": req.get("by", ""), "status": "error", "finished_at": clock.stamp(),
                        "error": f"Not run: the office PC got this {int(age // 60)} minutes after "
                                 "it was pressed (offline?). Press it again."})
                    continue
                log(f"{req.get('mode')} for {req.get('date')} requested by {req.get('by')}")
                cfg = load_config(required=False)    # pick up a re-run of setup
                # The loop runs for days; re-read the sheet logic so a fix to it
                # takes effect on the next press, not the next reboot.
                import importlib
                importlib.reload(hs)
                if not cfg.get("workbook"):
                    db._upsert_key(hs.RESULT_KEY, {
                        "id": req["id"], "date": req.get("date"), "mode": req.get("mode"),
                        "by": req.get("by", ""), "status": "error",
                        "finished_at": clock.stamp(),
                        "error": "The office PC isn't set up for HotSOS yet -- run "
                                 "'python hotsos_agent.py setup' on it."})
                    continue
                if req.get("mode") == "build":
                    run_build(cfg, _dt.date.fromisoformat(req["date"]), by=req.get("by", ""))
                    db._upsert_key(hs.RESULT_KEY, {"id": req["id"], "mode": "build",
                                                   "date": req["date"], "status": "done",
                                                   "finished_at": clock.stamp()})
                    continue
                run_push(cfg, _dt.date.fromisoformat(req["date"]), req.get("mode", "preview"),
                         req_id=req["id"], by=req.get("by", ""))

            dreq = asks.get(hs.DAYLOAD_REQUEST_KEY) or {}
            if dreq.get("id") and dreq["id"] != done_day:
                done_day = dreq["id"]
                try:
                    age = (clock.now() - _dt.datetime.fromisoformat(dreq["at"])).total_seconds()
                except Exception:
                    age = 0
                if age <= REQUEST_MAX_AGE:
                    load_day_rooms(load_config(required=False), dreq)

            cfg = load_config(required=False)
            if cfg.get("staff_workbook"):
                try:
                    sync_roster(cfg["staff_workbook"])
                except OSError as ex:      # open in Excel / mid-sync: next pass
                    log(f"Schedule.xlsx not readable yet: {ex}")

            now = clock.now()
            st_ = _state()
            if now.hour == BUILD_HOUR and st_.get("built") != str(now.date()) and cfg.get("workbook"):
                st_["built"] = str(now.date())
                STATE.write_text(json.dumps(st_))
                run_build(cfg)

            # Days somebody asked for: the morning's sheet to HotSOS by itself.
            try:
                _auto_push()
            except Exception as ex:
                log(f"auto-push: {type(ex).__name__}: {ex}")

            # 7:30: the Arrival Report's notes to the two Teams chats.
            try:
                last_teams = _teams_tick(cfg, last_teams)
            except Exception as ex:
                last_teams = time.time()
                log(f"teams notes: {type(ex).__name__}: {ex}")

            # The room-status mirror runs on its own thread (start_mirror).
            start_mirror()

            # Free plan: this process's reads, and at 2 AM the clean-up --
            # old data copied to SharePoint ("App Archive"), checked, removed.
            try:
                import freetier
                freetier.flush("agent")
                if now.hour == 2 and st_.get("freetier_day") != str(now.date()) \
                        and cfg.get("workbook"):
                    st_["freetier_day"] = str(now.date())
                    STATE.write_text(json.dumps(st_))
                    rec = freetier.nightly(Path(cfg["workbook"]).parent / "App Archive")
                    d = (rec.get("cleanup") or {}).get("deleted") or {}
                    log(f"free plan: database {rec['db_mb']['total']} MB, this month "
                        f"{rec['egress_mb'].get('total', 0)} MB sent; cleaned "
                        f"{', '.join(f'{v} {k}' for k, v in d.items() if v) or 'nothing'}")
            except Exception as ex:
                log(f"free plan job: {type(ex).__name__}: {ex}")

            # The Report page's numbers: GC8 Inspections read at 4 PM, once the
            # day's rooms are in, or when somebody presses Sync on the page.
            # Asked about every 30 seconds, not every pass, and read on a
            # thread of its own (start_report). One still running: next time.
            if time.time() - last_rep > 30 and cfg.get("workbook"):
                last_rep = time.time()
                try:
                    rreq = asks.get(rdm.REQUEST_KEY) or {}
                    asked = rreq.get("id") and rreq["id"] != done_rep
                    due = now.hour == rdm.SYNC_HOUR and _state().get("report_day") != str(now.date())
                    if (asked or due) and start_report(
                            cfg, (rreq.get("by") or "the page") if asked and not due else "4 PM"):
                        done_rep = rreq.get("id")
                        if due:
                            st2 = _state()           # fresh: the build may have written it
                            st2["report_day"] = str(now.date())
                            STATE.write_text(json.dumps(st2))
                except Exception as ex:
                    log(f"report sync: {type(ex).__name__}: {ex}")

            # The watchdog: every 10 minutes, its own checks; anything new goes
            # to SharePoint's "App Alerts" for the cloud flow to e-mail. Doesn't
            # depend on anybody's session being signed in.
            if time.time() - last_watch > 600:
                last_watch = time.time()
                try:
                    import agent_watch
                    sent = agent_watch.run(cfg)
                    if sent:
                        log("alert sent: " + " | ".join(x[:80] for x in sent))
                except Exception as ex:
                    log(f"watchdog: {type(ex).__name__}: {ex}")

            slot = (now.date(), now.hour)
            freq = asks.get(hs.FORECAST_REQUEST_KEY) or {}
            asked = freq.get("id") and freq["id"] != done_fc
            if asked or (now.hour in FORECAST_HOURS and slot != last_slot):
                done_fc, last_slot = freq.get("id"), slot
                try:
                    start_forecast()
                except Exception as ex:
                    log(f"forecast failed to start: {ex}")
        except Exception as ex:          # never let one bad pass end the loop
            log(f"loop error: {ex}")
        time.sleep(_poll_seconds())


def _poll_seconds(now=None):
    """How long the loop sleeps: 5 s by day, 30 s overnight. The 5 AM build
    and every timed job key off the clock, not this pace."""
    now = now or clock.now()
    hm = (now.hour, now.minute)
    return NIGHT_POLL_SECONDS if hm >= (22, 0) or hm < (4, 30) else POLL_SECONDS


# ── the heartbeat, on a thread of its own ────────────────────────────────────
# It used to be written by the loop, so a 5 AM build -- three or four minutes
# of the loop doing nothing else -- read as the office PC going silent, and the
# backup PC stood in for two minutes on 19 and 20 Oct. The beat now comes from
# its own thread, as long as the loop has come round in the last 15 minutes:
# a build doesn't stop it, a loop that is truly stuck still does.
BEAT_SECONDS = 60
LOOP_STUCK_SECONDS = 15 * 60
_LOOP_PASS = [0.0]
_BEAT = None


def _beat_loop():
    while True:
        try:
            if time.time() - _LOOP_PASS[0] < LOOP_STUCK_SECONDS:
                db._upsert_key(hs.HEARTBEAT_KEY, {"at": clock.stamp(),
                                                  "host": socket.gethostname()})
        except Exception as ex:
            print(f"heartbeat failed: {ex}", flush=True)
        time.sleep(BEAT_SECONDS)


def start_beat():
    global _BEAT
    if _BEAT is None or not _BEAT.is_alive():
        import threading
        _BEAT = threading.Thread(target=_beat_loop, name="heartbeat", daemon=True)
        _BEAT.start()


# ── passwords changed on the Admin page (credentials.py) ─────────────────────
def _register(role):
    try:
        import credentials
        credentials.register(role)
    except Exception as ex:
        log(f"credentials: could not publish this PC's key: {type(ex).__name__}: {ex}")
    return 0


def _cred_poll(last, every=120):
    """Look for a password change from the Admin page every `every` seconds;
    returns when it last ran."""
    if time.time() - last < every:
        return last
    try:
        import credentials
        credentials.agent_poll(CONFIG, KEYRING_SERVICE, log)
    except Exception as ex:
        log(f"credentials: {type(ex).__name__}: {ex}")
    return time.time()


# ── 7:30 AM: the Arrival Report's notes to the two Teams chats (teams_notes) ──
def teams_morning(cfg, day=None, test=False, by="7:30 AM"):
    """Send (or finish sending) the day's two Teams messages. Returns the record."""
    import teams_notes as tn
    day = day or clock.today()
    _, arr = daily_paths(cfg) if cfg.get("workbook") else (None, None)
    before = {} if test else (db._load_key(tn.SENT_KEY) or {})
    if before.get("date") != str(day):
        before = {}
    rec = tn.run_morning(day, lambda d: read_day(cfg, d), arr, test=test, already=before, log=log)
    rec.update(at=clock.stamp(), host=socket.gethostname(), by=by)
    if not test:
        db._upsert_key(tn.SENT_KEY, rec)
    return rec


def _teams_tick(cfg, last):
    """From the loop, every 5 minutes between 7:30 and 11: send if not sent.
    One PC sends: whichever finds the day's record not yet 'sent' -- the
    backup only ever runs this while it is standing in."""
    if time.time() - last < 300:
        return last
    import teams_notes as tn
    now = clock.now()
    today = str(now.date())
    if not cfg.get("workbook"):
        return time.time()
    if (now.hour, now.minute) < tn.SEND_AT:
        # Look again in 30 s, not 5 minutes: a five-minute step from wherever
        # the agent happened to start could land at 7:29 and send at 7:34
        # (16 October, after a 7:19 restart).
        return time.time() - 270
    st = _state()
    if st.get("teams_day") == today:
        return time.time()
    sent = db._load_key(tn.SENT_KEY) or {}
    if sent.get("date") == today and sent.get("status") in ("sent", "gave up"):
        st["teams_day"] = today
        STATE.write_text(json.dumps(st))
        return time.time()
    if now.hour >= tn.GIVE_UP_HOUR:
        db._upsert_key(tn.SENT_KEY, dict(sent if sent.get("date") == today else {"date": today},
                                         status="gave up", at=clock.stamp(),
                                         host=socket.gethostname()))
        log(f"teams notes {today}: not sent by {tn.GIVE_UP_HOUR}:00 -- {sent.get('why') or sent.get('results')}")
        st["teams_day"] = today
        STATE.write_text(json.dumps(st))
        return time.time()
    rec = teams_morning(cfg)
    if rec["status"] == "sent":
        st["teams_day"] = today
        STATE.write_text(json.dumps(st))
        log(f"teams notes {today}: sent ({rec.get('report')}, {rec.get('tab')})")
    elif rec["status"] == "waiting":
        log(f"teams notes {today}: waiting -- {rec.get('why')}")
    return time.time()


# ── backup: a second PC that stands in for the office PC ─────────────────────
STANDBY_SECONDS = 3 * 60     # the office PC's heartbeat older than this: stand in
STANDBY_POLL_SECONDS = 60    # how often a standing-by backup looks at the heartbeat


def _beat_age(beat):
    try:
        return (clock.now() - _dt.datetime.fromisoformat(beat["at"])).total_seconds()
    except Exception:
        return float("inf")


def run_backup():
    """Answer the HotSOS page's Preview and Push, but only while the office PC
    is down. HotSOS and SharePoint are both reachable from outside the office;
    SSRS is not, so the 5 AM build, the forecast, the roster import and the
    rest of run_loop stay the office PC's alone.

    Only one PC may answer a press, or a Push goes out twice. So this waits
    for the office PC's heartbeat to go stale, and while it stands in it
    writes the heartbeat under its own name (the page then reads "online").
    The office PC's first beat on its return carries the other name, and this
    goes quiet again. A press whose id is already in the result -- answered by
    either PC -- is never run a second time."""
    me = socket.gethostname()
    log(f"backup agent up on {me}; standing by while the office PC is online")
    done_req = (db._load_key(hs.RESULT_KEY) or {}).get("id")
    active, last_beat, last_teams = False, 0, 0
    last_cred = _register("backup")
    while True:
        try:
            # This PC's reads count against the same free plan; it used to be
            # the one process the meter didn't see.
            try:
                import freetier
                freetier.flush("backup")
            except Exception:
                pass
            # Standing by or not: a password changed on the Admin page must
            # reach this PC before it is needed, not when it takes over.
            last_cred = _cred_poll(last_cred, every=60 if active else 300)
            # The heartbeat and the latest press in one read.
            got = db._load_keys([hs.HEARTBEAT_KEY, hs.REQUEST_KEY])
            beat = got.get(hs.HEARTBEAT_KEY) or {}
            age = _beat_age(beat)
            if beat.get("host") != me and age <= STANDBY_SECONDS:
                if active:
                    log(f"office PC {beat.get('host')} is back; standing by")
                    active = False
                time.sleep(STANDBY_POLL_SECONDS)
                continue
            if not active:
                log(f"office PC {beat.get('host') or '?'} silent "
                    f"{'since ever' if age == float('inf') else f'{age / 60:.0f} min'}; "
                    "standing in for HotSOS")
                active, last_beat = True, 0
            if time.time() - last_beat > 60:
                db._upsert_key(hs.HEARTBEAT_KEY, {"at": clock.stamp(), "host": me,
                                                  "backup": True})
                last_beat = time.time()

            # Standing in, so the 7:30 Teams notes are this PC's too.
            try:
                last_teams = _teams_tick(load_config(required=False), last_teams)
            except Exception as ex:
                last_teams = time.time()
                log(f"teams notes: {type(ex).__name__}: {ex}")

            req = got.get(hs.REQUEST_KEY) or {}
            if not req.get("id") or req["id"] == done_req:
                time.sleep(POLL_SECONDS)
                continue
            done_req = req["id"]
            if (db._load_key(hs.RESULT_KEY) or {}).get("id") == req["id"]:
                continue                            # the office PC answered it
            fail = None
            if _beat_age(req) > REQUEST_MAX_AGE:
                fail = (f"Not run: the backup PC got this {int(_beat_age(req) // 60)} minutes "
                        "after it was pressed. Press it again.")
            elif req.get("mode") == "build":
                fail = ("The office PC is offline, and building the sheet needs SSRS, which "
                        "only the office network reaches. Preview and Push still work.")
            cfg = load_config(required=False)
            if not fail and not cfg.get("workbook"):
                fail = "The backup PC isn't set up -- run 'python hotsos_agent.py setup' on it."
            if fail:
                log(f"{req.get('mode')} from {req.get('at')}: {fail}")
                db._upsert_key(hs.RESULT_KEY, {
                    "id": req["id"], "date": req.get("date"), "mode": req.get("mode"),
                    "by": req.get("by", ""), "status": "error",
                    "finished_at": clock.stamp(), "error": fail})
                continue
            log(f"{req.get('mode')} for {req.get('date')} requested by {req.get('by')} (backup)")
            import importlib
            importlib.reload(hs)
            run_push(dict(cfg, backup=True), _dt.date.fromisoformat(req["date"]),
                     req.get("mode", "preview"), req_id=req["id"], by=req.get("by", ""))
        except Exception as ex:          # never let one bad pass end the loop
            log(f"backup loop error: {ex}")
            time.sleep(POLL_SECONDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "forecast", "roster", "staff", "build",
                                    "preview", "push", "run", "report", "backup", "teams"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--only-room", default=None)
    ap.add_argument("--test", action="store_true",
                    help="teams: send both messages to the test chat only")
    a = ap.parse_args()
    if a.cmd == "teams":
        rec = teams_morning(load_config(), _dt.date.fromisoformat(a.date) if a.date else None,
                            test=a.test, by="console")
        print({k: rec.get(k) for k in ("status", "why", "report", "tab", "results")})
        return
    if a.cmd == "setup":
        return setup()
    if a.cmd == "forecast":
        if sys.stdout is None or Path(sys.executable).stem.lower() == "pythonw":
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(CONFIG.parent / "agent.log", "a",
                                           encoding="utf-8", buffering=1)
        try:
            days = refresh_forecast()
            print(f"{len(days)} days stored")
        except Exception as ex:
            log(f"forecast failed: {type(ex).__name__}: {ex}")
        return
    if a.cmd == "build":
        print(run_build(load_config(), _dt.date.fromisoformat(a.date) if a.date else None,
                        by="console"))
        return
    if a.cmd == "report":
        rec = sync_report(load_config(), by="console")
        print({k: rec.get(k) for k in ("status", "source", "written", "error")})
        return
    if a.cmd == "roster":
        print(sync_roster(load_config()["staff_workbook"], force=True))
        return
    if a.cmd in ("run", "backup"):
        # Under pythonw (how Task Scheduler starts it, so no window sits on the
        # desk all day) there is no console; write the log to a file instead.
        if sys.stdout is None or Path(sys.executable).stem.lower() == "pythonw":
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(CONFIG.parent / "agent.log", "a",
                                           encoding="utf-8", buffering=1)
        return run_loop() if a.cmd == "run" else run_backup()
    day = _dt.date.fromisoformat(a.date) if a.date else clock.today()
    _print_plan(run_push(load_config(), day, a.cmd, only_room=a.only_room, by="console"))


if __name__ == "__main__":
    main()
