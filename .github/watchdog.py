"""The office PC's outside alarm. GitHub Actions runs it every 30 minutes
(.github/workflows/watchdog.yml).

The office PC reports its own problems (agent_watch), so it can't report the
one that matters most: itself gone quiet. On 12 Nov a Windows Update reboot
at 00:34 stopped everything, and nobody knew until a sign-in at 08:45. From
outside, this reads the database and posts to Hari's own Teams chat (the
`test` webhook) when:
  * the office PC's heartbeat (written every minute) is over 20 minutes old,
    or the backup PC is writing it instead;
  * by 5:45 the 5 AM build hasn't finished today, or failed, or hung;
  * the app hasn't answered two runs in a row.
A problem is posted once, again after 6 hours if it's still there, and a
line follows when it clears. What was posted is kept under `gh_watchdog`.

The repo is public, and so are its run logs: this prints counts only --
never a name, a room, a message or a URL. Standard library only.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
OFFICE = "GC8HSKP26-03"
QUIET_MIN = 20           # the heartbeat is written every minute
REPEAT_H = 6
BUILD_DUE = (5, 45)      # the build starts at 5:00 and takes about 6 minutes
BUILD_HANG_MIN = 30
APP_HEALTH = "https://bgv-scheduling-qvt9nhbqqbusvbcpm7kidq.streamlit.app/~/+/_stcore/health"
KEYS = ("hotsos_agent_heartbeat", "daily_build_status", "teams_webhooks", "gh_watchdog")
STATE_KEY = "gh_watchdog"

URL = os.environ["SUPABASE_URL"].strip().rstrip("/")
KEY = os.environ["SUPABASE_KEY"].strip()


def _rest(method, path, body=None, extra=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    h.update(extra or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode()
    return json.loads(text) if text.strip() else None


def load():
    q = ",".join(f'"{k}"' for k in KEYS)
    out = {}
    for row in _rest("GET", f"/rest/v1/app_settings?select=key,payload&key=in.({q})") or []:
        p = row.get("payload")
        try:
            out[row["key"]] = json.loads(p) if isinstance(p, str) else (p or {})
        except ValueError:
            out[row["key"]] = {}
    return out


def save_state(state):
    _rest("POST", "/rest/v1/app_settings?on_conflict=key",
          {"key": STATE_KEY, "payload": json.dumps(state)},
          {"Prefer": "resolution=merge-duplicates,return=minimal"})


def _t(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=MT)
    except (TypeError, ValueError):
        return None


def _hm(t):
    return t.astimezone(MT).strftime("%a %I:%M %p").replace(" 0", " ")


def app_answers():
    try:
        with urllib.request.urlopen(APP_HEALTH, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def problems(now, got, app_fails):
    """{key: sentence}. Keys stay the same while the problem does."""
    out = {}
    hb = got.get("hotsos_agent_heartbeat") or {}
    at, host = _t(hb.get("at")), str(hb.get("host") or "")
    age = (now - at).total_seconds() / 60 if at else None
    if age is None or age > QUIET_MIN:
        out["quiet"] = ("The office PC has gone quiet"
                        + (f" -- last heard from {_hm(at)}." if at else ".")
                        + " No build, no HotSOS updates and no alerts until it's back. If it "
                          "restarted, sign in on it (the agent starts with the sign-in); if "
                          "it's signed in, end and run 'BGV HotSOS Agent' in Task Scheduler.")
    elif host and host != OFFICE:
        out["backup"] = (f"The office PC is off; the backup PC ({host}) is standing in. "
                         "Preview and Push still work, but the 5 AM build, the forecast and "
                         "the staff schedule import wait for the office PC.")

    today = now.astimezone(MT).date()
    b = got.get("daily_build_status") or {}
    bk = f"build {today}"         # one day's build, so yesterday's never "clears" at midnight
    if (now.astimezone(MT).hour, now.astimezone(MT).minute) >= BUILD_DUE:
        started = _t(b.get("started_at"))
        if b.get("date") != str(today):
            out[bk] = "Today's 5 AM build hasn't run."
        elif b.get("status") == "error":
            out[bk] = f"Today's 5 AM build failed: {str(b.get('error') or '')[:160]}"
        elif b.get("status") == "running" and started and \
                (now - started).total_seconds() / 60 > BUILD_HANG_MIN:
            out[bk] = f"Today's build has been 'running' since {_hm(started)} -- it's stuck."

    if app_fails >= 2:
        out["app"] = "The app isn't answering (two checks in a row, 30 minutes apart)."
    return out


CLEARED = {
    "quiet": "The office PC is back.",
    "backup": "The office PC is back; the backup PC has stood down.",
    "app": "The app is answering again.",
}


def cleared_line(k, found, today):
    """The line for a problem that has gone, or None to drop it quietly."""
    if k.startswith("build "):
        return "Today's build is done." if k == f"build {today}" else None
    if k in ("quiet", "backup") and {"quiet", "backup"} & set(found):
        return None               # one became the other: the new line says what's up
    return CLEARED.get(k)


def post(url, lines):
    card = {"type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": [{"type": "TextBlock", "text": "BGV watchdog (GitHub)", "weight": "Bolder"}]
            + [{"type": "TextBlock", "text": f"• {x}", "wrap": True} for x in lines]}
    payload = {"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
        "content": card}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as ex:
        return ex.code
    except Exception:
        return 0


def main():
    now = dt.datetime.now(dt.timezone.utc)
    got = load()
    state = got.get(STATE_KEY) or {}
    alerted = dict(state.get("alerted") or {})
    app_fails = 0 if app_answers() else int(state.get("app_fails") or 0) + 1

    found = problems(now, got, app_fails)
    lines, sent_keys = [], []
    for k, msg in found.items():
        last = _t(alerted.get(k))
        if last is None or (now - last).total_seconds() > REPEAT_H * 3600:
            lines.append(msg)
            sent_keys.append(k)
    cleared = [k for k in alerted if k not in found]
    today = now.astimezone(MT).date()
    lines += [x for x in (cleared_line(k, found, today) for k in cleared) if x]
    if os.environ.get("WATCHDOG_TEST") == "true":       # "Run workflow" with test ticked
        lines.insert(0, "Test: the watchdog on GitHub can read the database and post here. "
                        f"Problems right now: {len(found)}.")

    ok = True
    if lines:
        url = ((got.get("teams_webhooks") or {}).get("test") or "").strip()
        code = post(url, lines) if url else 0
        ok = 200 <= code < 300
        print(f"posted {len(lines)} line(s): HTTP {code}")
    if ok:
        for k in sent_keys:
            alerted[k] = now.isoformat(timespec="seconds")
        for k in cleared:
            alerted.pop(k, None)
    new = {"alerted": alerted, "app_fails": app_fails}
    if new != {k: state.get(k) for k in new} or (lines and ok):
        new["at"] = now.isoformat(timespec="seconds")
        save_state(new)
    print(f"checked: {len(found)} problem(s), {len(sent_keys)} new, {len(cleared)} cleared")
    if not ok:
        sys.exit("could not post to Teams")      # a red run: GitHub e-mails the owner


if __name__ == "__main__":
    main()
