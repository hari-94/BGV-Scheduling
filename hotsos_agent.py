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
  python hotsos_agent.py preview [--date 2026-10-08]
  python hotsos_agent.py push    [--date 2026-10-08] [--only-room 3346E]
  python hotsos_agent.py run          the loop (Task Scheduler starts this)

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
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=700)
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
    # Past days' rooms are no use to anyone; keep a week for a look back.
    try:
        cutoff = (clock.today() - _dt.timedelta(days=7)).isoformat()
        for k in db._like_keys(hs.ROOMS_CACHE_PREFIX):
            key = k if isinstance(k, str) else k.get("key", "")
            if key and key[len(hs.ROOMS_CACHE_PREFIX):] < cutoff:
                db._delete_key(key)
    except Exception as ex:
        log(f"rooms cache cleanup: {ex}")
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
        hk = staff_names.full(" ".join(str(r.get("assignedTo") or "").split())) or hk_chart
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


# The mirror keeps one HotSOS browser signed in all day. Playwright allows one
# of those per thread: on the loop's own thread, the next Preview, Push or
# SharePoint read failed with "using Playwright Sync API inside the asyncio
# loop" (9 Oct). So the mirror has a thread of its own, and only it ever
# touches its session.
_MIRROR = None


def _mirror_loop():
    while True:
        try:
            cfg = load_config(required=False)
            if cfg.get("hotsos_user") and clock.now().hour in STATUS_HOURS:
                try:
                    rec = sync_room_status(cfg)
                    rec["reconciled"] = reconcile_charts()
                except Exception as ex:
                    rec = {"at": clock.stamp(), "error": f"{type(ex).__name__}: {ex}"}
                    log(f"room status sync failed: {rec['error']}")
                    _close_status_session()
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
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
    # Both files carry the day now, by design; it only matters when someone
    # changed the copy that isn't read.
    read_day.warning = (f"{found[1][0]} ('{found[1][1]}') differs from {found[0][0]} "
                        f"('{found[0][1]}'). Using {found[0][0]}; make the changes there."
                        if len(found) > 1 and found[0][2] != found[1][2] else "")
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
    done_fc = None
    last_slot = None
    last_beat = 0
    while True:
        try:
            if time.time() - last_beat > 60:
                db._upsert_key(hs.HEARTBEAT_KEY, {"at": clock.stamp(),
                                                  "host": socket.gethostname()})
                last_beat = time.time()
                try:
                    report_health(load_config(required=False), started_at)
                except Exception as ex:
                    print(f"health report failed: {ex}", flush=True)

            req = db._load_key(hs.REQUEST_KEY) or {}
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

            dreq = db._load_key(hs.DAYLOAD_REQUEST_KEY) or {}
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

            # The room-status mirror runs on its own thread (start_mirror).
            start_mirror()

            slot = (now.date(), now.hour)
            freq = db._load_key(hs.FORECAST_REQUEST_KEY) or {}
            asked = freq.get("id") and freq["id"] != done_fc
            if asked or (now.hour in FORECAST_HOURS and slot != last_slot):
                done_fc, last_slot = freq.get("id"), slot
                try:
                    start_forecast()
                except Exception as ex:
                    log(f"forecast failed to start: {ex}")
        except Exception as ex:          # never let one bad pass end the loop
            log(f"loop error: {ex}")
        time.sleep(POLL_SECONDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "forecast", "roster", "staff", "build",
                                    "preview", "push", "run"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--only-room", default=None)
    a = ap.parse_args()
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
    if a.cmd == "roster":
        print(sync_roster(load_config()["staff_workbook"], force=True))
        return
    if a.cmd == "run":
        # Under pythonw (how Task Scheduler starts it, so no window sits on the
        # desk all day) there is no console; write the log to a file instead.
        if sys.stdout is None or Path(sys.executable).stem.lower() == "pythonw":
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(CONFIG.parent / "agent.log", "a",
                                           encoding="utf-8", buffering=1)
        return run_loop()
    day = _dt.date.fromisoformat(a.date) if a.date else clock.today()
    _print_plan(run_push(load_config(), day, a.cmd, only_room=a.only_room, by="console"))


if __name__ == "__main__":
    main()
