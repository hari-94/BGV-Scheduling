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
POLL_SECONDS = 30
REQUEST_MAX_AGE = 10 * 60   # a press older than this is not run -- see run_loop


def log(msg):
    print(f"[{clock.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


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
def pull_ssrs(start: _dt.date, end: _dt.date) -> Path:
    """Export the Housekeeping Dashboard as .xlsx, signed in as this PC's user.
    PowerShell does the Windows sign-in, which Python's requests cannot do
    without an extra package."""
    out = Path(tempfile.gettempdir()) / f"hskp_dashboard_{start}_{end}.xlsx"
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
                    | {k: est.get(k) for k in ("hskp", "hskp_fc", "hskp_ds", "rqs")})
    # Keep the pull before this one, so the page can say what new bookings
    # changed since -- the number alone doesn't tell anyone it moved.
    prev = db._load_key(hs.FORECAST_KEY) or {}
    db._upsert_key(hs.FORECAST_KEY, {
        "pulled_at": clock.stamp(), "start": str(start), "end": str(end),
        "days": days, "warnings": parsed.get("warnings", []),
        "previous": {"pulled_at": prev.get("pulled_at"), "days": prev.get("days", [])}})
    log(f"forecast stored: {len(days)} days {start}..{end}")
    return days


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
    if not force and time.time() - p.stat().st_mtime < SETTLE_SECONDS:
        return None                     # still being written; next pass
    raw = p.read_bytes()                # raises if Excel holds it locked; retried
    digest = hashlib.sha256(raw).hexdigest()
    st = _state()
    if not force and st.get("roster_sha") == digest:
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
        log(f"roster synced: {out['saved']} week(s), {d['n_changed_cells']} cell(s) "
            f"changed, today {'changed' if out['today_changed'] else 'unchanged'}")
    except Exception as ex:
        status["error"] = f"{type(ex).__name__}: {ex}"
        log(f"roster sync failed: {ex}")
    db._upsert_key(hs.ROSTER_STATUS_KEY, status)
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
            tab, rows = hs.read_workbook(cfg["workbook"], day)
            res["tab"] = tab
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
    log(f"agent up on {socket.gethostname()}; workbook {cfg.get('workbook') or '(not set up)'}")
    done_req = (db._load_key(hs.RESULT_KEY) or {}).get("id")
    done_fc = None
    last_slot = None
    last_beat = 0
    while True:
        try:
            if time.time() - last_beat > 60:
                db._upsert_key(hs.HEARTBEAT_KEY, {"at": clock.stamp(),
                                                  "host": socket.gethostname()})
                last_beat = time.time()

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
                run_push(cfg, _dt.date.fromisoformat(req["date"]), req.get("mode", "preview"),
                         req_id=req["id"], by=req.get("by", ""))

            cfg = load_config(required=False)
            if cfg.get("staff_workbook"):
                try:
                    sync_roster(cfg["staff_workbook"])
                except OSError as ex:      # open in Excel / mid-sync: next pass
                    log(f"Schedule.xlsx not readable yet: {ex}")

            now = clock.now()
            slot = (now.date(), now.hour)
            freq = db._load_key(hs.FORECAST_REQUEST_KEY) or {}
            asked = freq.get("id") and freq["id"] != done_fc
            if asked or (now.hour in FORECAST_HOURS and slot != last_slot):
                done_fc, last_slot = freq.get("id"), slot
                try:
                    refresh_forecast()
                except Exception as ex:
                    log(f"forecast failed: {ex}")
        except Exception as ex:          # never let one bad pass end the loop
            log(f"loop error: {ex}")
        time.sleep(POLL_SECONDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "forecast", "roster", "staff", "preview", "push", "run"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--only-room", default=None)
    a = ap.parse_args()
    if a.cmd == "setup":
        return setup()
    if a.cmd == "forecast":
        for d in refresh_forecast():
            print(d)
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
