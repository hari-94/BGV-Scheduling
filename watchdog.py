"""
watchdog.py — the office PC watches its own jobs and raises the alarm.

Overnight checks used to run inside a Claude session on this PC. On 10 Oct
that session was signed out, the checks queued up unanswered, and an Arrival
Report the flow had skipped went unnoticed until morning. So the agent, which
runs around the clock anyway, does the checking itself:

  * every 10 minutes it looks at the same things the overnight monitor did
    (`problems`);
  * a problem it hasn't reported yet is written as a small text file to the
    synced SharePoint folder "App Alerts" beside the inspection workbooks; a
    Power Automate flow, in Microsoft's cloud, e-mails each new file to Hari.
    A problem still there 6 hours later is reported once more;
  * it also rewrites "App Alerts/heartbeat.txt" each pass, so a second flow
    can notice when the office PC itself has gone quiet -- the one failure
    the PC can't report.

Read-only apart from those files: it never fixes, pushes or edits anything.
"""
import datetime as _dt
import json

from pathlib import Path

import clock
import db
import hotsos_sync as hs

APP_HEALTH = "https://bgv-scheduling-qvt9nhbqqbusvbcpm7kidq.streamlit.app/~/+/_stcore/health"
STATE = Path.home() / ".bgv-agent" / "watchdog.json"
REMIND_HOURS = 6


def _t(s):
    try:
        x = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=clock.MTN)
    except Exception:
        return None


def _age_min(s):
    x = _t(s)
    return None if x is None else (clock.now() - x).total_seconds() / 60


def problems(cfg) -> list:
    """Everything that needs a person, as short sentences. Empty when fine."""
    import daily_build
    import freetier
    now, today = clock.now(), clock.today()
    out = []

    # the 5 AM build
    b = db._load_key("daily_build_status") or {}
    if (now.hour, now.minute) >= (5, 25):
        if b.get("date") != str(today):
            out.append("The 5 AM build hasn't run today — open Stats, or press Build on the HotSOS page.")
        elif b.get("status") == "error":
            out.append(f"The 5 AM build failed: {str(b.get('error'))[:160]}")
        elif str(b.get("big_tab", "")).startswith("error"):
            out.append(f"Today's tab couldn't be written to GC8 Inspections 2026.xlsx: {b['big_tab'][:120]}")
        elif not b.get("arrival") and now.hour < 12:
            out.append("Today's schedule was built without an Arrival Report (none saved last night). "
                       "Forward the front desk's e-mail to yourself with 'Arrival' in the subject, "
                       "then rebuild today from the HotSOS page if you need its late checkouts.")

    # tomorrow's Arrival Report, while there's still time to ask for it
    folder = Path(cfg["workbook"]).parent / "Arrival Reports" if cfg.get("workbook") else None
    if folder and (now.hour, now.minute) >= (21, 30):
        tomorrow = today + _dt.timedelta(days=1)
        if not daily_build.find_arrival_report(folder, tomorrow):
            out.append(f"No Arrival Report for tomorrow ({tomorrow:%a %b %d}) has arrived yet. Ask the front "
                       "desk to send it — any subject with 'Arrival' in it works.")

    # the HotSOS mirror, through the day
    s = db._load_key(getattr(hs, "STATUS_SYNC_KEY", "hotsos_status_sync")) or {}
    a = _age_min(s.get("at"))
    fails = 0
    for h in reversed(s.get("history") or []):
        if not h.get("error"):
            break
        fails += 1
    if 6 <= now.hour < 20 and (a is None or a > 15):
        out.append("HotSOS room statuses haven't been read for "
                   + (f"{a:.0f} minutes." if a is not None else "today."))
    if fails >= 3:
        out.append(f"HotSOS room-status reads failing ({fails} in a row): {str(s.get('error'))[:120]}")

    # the forecast, every two hours in the day
    fc = db._load_key(hs.FORECAST_KEY) or {}
    a = _age_min(fc.get("pulled_at"))
    if 9 <= now.hour <= 21 and (a is None or a > 200):
        out.append(f"The SSRS forecast hasn't refreshed for {a / 60:.1f} hours." if a else
                   "The SSRS forecast has never run.")

    # staff schedule import, HotSOS push
    rs = db._load_key(hs.ROSTER_STATUS_KEY) or {}
    if rs.get("error"):
        out.append(f"Schedule.xlsx couldn't be imported: {rs['error'][:140]}")
    cur = db._load_key(hs.RESULT_KEY) or {}
    if cur.get("status") == "error" and (_age_min(cur.get("finished_at")) or 999) < 60:
        out.append(f"HotSOS {cur.get('mode')} failed: {str(cur.get('error'))[:140]}")

    # the free plans
    ft = db._load_key(freetier.STATUS_KEY) or {}
    at = _t(ft.get("at"))
    if now.hour >= 3 and (at is None or at.astimezone(clock.MTN).date() != today):
        out.append("Last night's free-plan clean-up didn't run.")
    errs = (ft.get("cleanup") or {}).get("errors") or []
    if errs and at and at.astimezone(clock.MTN).date() == today:
        out.append("Clean-up problems: " + "; ".join(errs)[:160])
    dbmb = (ft.get("db_mb") or {}).get("total") or 0
    if dbmb > freetier.DB_LIMIT_MB * freetier.WARN:
        out.append(f"Database at {dbmb} MB of the 500 MB free plan.")
    try:
        pace = freetier.month_pace()
        if pace > freetier.EGRESS_LIMIT_MB * freetier.WARN:
            out.append(f"Data sent is on pace for {pace:,.0f} MB this month (free plan 5,120 MB).")
    except Exception:
        pass
    m = db._load_key(freetier.USAGE_PREFIX + "memory_app") or {}
    if m.get("day") == str(today) and (m.get("peak_mb") or 0) > 1500:
        out.append(f"The app's memory reached {m['peak_mb']:.0f} MB (Streamlit allows ~2,700 MB at most).")

    # the app itself
    try:
        import urllib.request
        with urllib.request.urlopen(APP_HEALTH, timeout=20) as r:
            if r.status != 200:
                out.append(f"The app answered {r.status} instead of 200.")
    except Exception as ex:
        out.append(f"The app isn't answering: {type(ex).__name__}")
    return out


def _alerts_dir(cfg) -> Path:
    return Path(cfg["workbook"]).parent / "App Alerts"


def heartbeat(cfg):
    """The file a cloud flow watches to know this PC is alive."""
    d = _alerts_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    (d / "heartbeat.txt").write_text(f"BGV office PC agent alive at {clock.stamp()}\n", encoding="utf-8")


def run(cfg) -> list:
    """One pass: heartbeat, check, and write an alert file for anything new
    (or 6 hours old and still there). Returns what was alerted."""
    if not cfg.get("workbook"):
        return []
    heartbeat(cfg)
    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {}
    seen = state.get("seen", {})
    now = clock.now()
    current = problems(cfg)
    send = []
    for p in current:
        key = p[:60]
        last = _t(seen.get(key))
        if last is None or (now - last).total_seconds() > REMIND_HOURS * 3600:
            send.append(p)
            seen[key] = clock.stamp()
    # forget what's cleared, so it alerts again if it comes back
    keys = {p[:60] for p in current}
    seen = {k: v for k, v in seen.items() if k in keys}
    STATE.write_text(json.dumps({"seen": seen, "last_run": clock.stamp(),
                                 "current": current}))
    if send:
        d = _alerts_dir(cfg)
        body = (f"BGV Peak 8 — {len(send)} thing{'s need' if len(send) != 1 else ' needs'} a look "
                f"({now:%a %b %d, %I:%M %p}):\n\n" + "\n".join(f"• {p}" for p in send)
                + "\n\nStats: https://bgv-scheduling-qvt9nhbqqbusvbcpm7kidq.streamlit.app/Stats\n")
        (d / f"BGV alert {now:%Y-%m-%d %H%M}.txt").write_text(body, encoding="utf-8")
    db._upsert_key("watchdog_status", {"at": clock.stamp(), "current": current, "alerted": send})
    return send
