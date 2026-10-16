"""
teams_notes.py — the morning's Arrival Report notes, posted to two Teams chats.

Once the day's sheet is set, the floor needs what the front desk sent the
night before, cut two ways:

  * "GC8 AM Houseperson 7am -3pm": what to carry up -- room moves, cribs,
    highchairs, rollaways, special requests, dogs -- room numbers only;
  * "GC8 - Housekeeping": what to clean or inspect differently -- VIPs, moves,
    stayovers, robes, celebrations, early ins, late arrivals, late checkouts --
    each room with the housekeeper and the RQS the sheet gives it today.

The desk's own lines are kept under their own headings (the heading names are
arrival_sections.py, shared with the Schedule page), so nothing the desk wrote
is reworded on the way.

Teams: each chat has a "Send webhook alerts to a chat" workflow (Teams >
Workflows); its URL takes an Adaptive Card and posts it as "Workflows". No
premium licence, no admin, and no office PC: anything that can make an HTTPS
request can post. The URLs are kept in app_settings (WEBHOOKS_KEY).

No Streamlit here, so the agent and the console can both use it.
"""
import argparse
import datetime as _dt
import json
import re
import sys
import urllib.request

import arrival_sections as secs

WEBHOOKS_KEY = "teams_webhooks"        # {"houseperson": url, "housekeeping": url, "test": url}
SENT_KEY = "teams_notes_sent"          # {date, at, by, host, results}

HOUSEPERSON = ["Room Move", "Pack n Play", "Highchair", "Rollaway", "Special Request",
               "Dog arriving"]
HOUSEKEEPING = ["VIP", "Room Move", "Stayover", "Robes", "Celebration", "Early In",
                "Late Arrival", "Late Checkout"]
TITLE = {"VIP": "VIP Inspections", "Room Move": "Room Moves", "Stayover": "Stayovers",
         "Robes": "Robes", "Pack n Play": "Pack n Play", "Highchair": "Highchairs",
         "Rollaway": "Rollaway", "Special Request": "Special Requests",
         "Dog arriving": "Dogs Arriving", "Celebration": "Celebrations",
         "Early In": "Early Ins", "Late Arrival": "Late Arrival",
         "Late Checkout": "Late Checkouts"}

_ROOM = re.compile(r'\b([1-9]\d{3}[A-Z]{1,4})\b')
_TIME = re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b', re.I)
_ARROW = r'(?:[>→⇒➡®à]|-{1,2}>|=>|–|—|\bto\b|-)'
_MOVE = re.compile(r'([1-9]\d{3}[A-Z]{1,4})\s*' + _ARROW + r'\s*([1-9]\d{3}[A-Z]{1,4})', re.I)
_BULLET = re.compile(r'^[\s\t]*(?:[*•◦‣⁃·\-–]+|\d+[.)])\s*')
_CELEB = re.compile(r'^(Birthday|Anniver\w*|Misc\.?|Other)$', re.I)
_EMPTY = {"", "n/a", "na", "none", "nil", "-", "--", "x"}


def expand(code):
    """'3240AB' is two doors, 3240A and 3240B -- the same rule, and the same
    check against the floor plans, as the Schedule page's expand_compound_room."""
    s = str(code).upper()
    m = re.match(r'^([1-9]\d{3})([A-Z]{2,4})$', s)
    if not m:
        return [s]
    parts = [m.group(1) + ch for ch in m.group(2)]
    try:
        import property_map as pmap
        if pmap.parse(s):
            return [s]
        if all(pmap.parse(p) for p in parts):
            return parts
    except Exception:
        pass
    return parts


def _rooms(text):
    return [r for c in _ROOM.findall(text.upper()) for r in expand(c)]


def parse(text):
    """{section: [item]} in the report's order. An item is a dict: `rooms`,
    `line` (what the desk wrote, tidied), and per section `move` (from, to),
    `time` (late checkout) or `kind` (celebration)."""
    out, section, kind, late = {}, None, None, None
    for raw in (text or "").splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue
        head, rest = (line.split(":", 1) + [""])[:2] if ":" in line else (line, "")
        key = secs.norm_heading(head)
        opened = None
        if key in secs.NOTE_SECTIONS:
            opened = secs.NOTE_SECTIONS[key]
        elif key in secs.LATE_SECTIONS:
            opened = "Late Checkout"
        elif key in secs.SKIP_SECTIONS:
            opened = ""
        elif line.endswith(":") and not _ROOM.search(line.upper()) and 0 < len(key.split()) <= 5:
            opened = ""                         # an unknown heading still closes the last one
        if opened is not None:
            section, kind, late = opened, None, None
            line = rest.strip()
            if not line:
                continue
        if not section or line.lower() in _EMPTY:
            continue
        bag = out.setdefault(section, [])
        if section == "Late Checkout":
            t = _TIME.search(line)
            if t:
                late = re.sub(r'\s+', ' ', t.group(1)).lower()
            rooms = _rooms(line)
            if rooms and late:                  # a time, or a signature: neither is a room
                bag.append({"rooms": rooms, "line": line, "time": late})
            continue
        if section == "Celebration":
            c = _CELEB.match(line)
            if c:
                k = c.group(1)
                kind = ("Anniversary" if k.lower().startswith("anniver") else
                        None if k.lower().startswith(("misc", "other")) else k.title())
                continue
        if section == "Room Move":
            for mv in _MOVE.finditer(line.upper()):
                bag.append({"rooms": [mv.group(1), mv.group(2)], "line": line,
                            "move": (mv.group(1), mv.group(2))})
            continue
        rooms = _rooms(line)
        # Whatever the desk wrote beside the room ("3140A 1pm", "2 cribs") rides along.
        extra = re.sub(r'\s+', ' ', re.sub(_ROOM.pattern, "", line, flags=re.I)).strip(" -,:;") \
            if rooms else ""
        bag.append({"rooms": rooms, "line": line, "extra": extra, "kind": kind})
    return {k: v for k, v in out.items() if v and k}


# ── who has each room today ──────────────────────────────────────────────────
def assignments(rows):
    """{room: (housekeeper, rqs)} from the day's sheet rows (hotsos_sync)."""
    out = {}
    for r in rows or []:
        for room in expand(r.get("room", "")):
            out[room] = ((r.get("hskp") or "").strip(), (r.get("rqs") or "").strip())
    return out


def _who(room, assign):
    if room not in assign:
        return "not on today's sheet"
    h, r = assign[room]
    return f"HK {h or '—'} · RQS {r or '—'}"


# ── the two messages ─────────────────────────────────────────────────────────
def _houseperson_lines(section, items):
    # Rooms only: the housepersons know where every room is.
    out = []
    for it in items:
        if it.get("move"):
            a, b = it["move"]
            out.append(f"**{a} → {b}**")
            continue
        if not it["rooms"]:
            out.append(it["line"])
            continue
        for room in it["rooms"]:
            out.append(f"**{room}**" + (f" · {it['extra']}" if it.get("extra") else ""))
    return out


def _housekeeping_lines(section, items, assign):
    out = []
    for it in items:
        if it.get("move"):
            a, b = it["move"]
            out.append(f"**{a} → {b}** — from: {_who(a, assign)}; to: {_who(b, assign)}")
            continue
        if not it["rooms"]:
            out.append(it["line"])
            continue
        for room in it["rooms"]:
            detail = it.get("time") and f"out {it['time']}" or it.get("kind") or it.get("extra") or ""
            out.append(f"**{room}**" + (f" · {detail}" if detail else "") + f" — {_who(room, assign)}")
    return out


def build(day, report_text, rows):
    """{'houseperson': message, 'housekeeping': message}. A message is
    {title, subtitle, blocks: [(heading, [lines])], empty: [headings]}."""
    parsed = parse(report_text)
    assign = assignments(rows)
    when = f"{day:%a %b} {day.day}"
    msgs = {}
    for name, order, title, sub in (
            ("houseperson", HOUSEPERSON, f"Houseperson notes · {when}",
             "From the front desk's Arrival Report"),
            ("housekeeping", HOUSEKEEPING, f"Housekeeping notes · {when}",
             "From the front desk's Arrival Report, with who has each room on today's sheet")):
        blocks, empty = [], []
        for s in order:
            items = parsed.get(s, [])
            lines = (_houseperson_lines(s, items) if name == "houseperson"
                     else _housekeeping_lines(s, items, assign))
            (blocks.append((TITLE[s], lines)) if lines else empty.append(TITLE[s]))
        msgs[name] = {"title": title, "subtitle": sub, "blocks": blocks, "empty": empty}
    return msgs


def as_text(msg):
    out = [msg["title"], msg["subtitle"], ""]
    for head, lines in msg["blocks"]:
        out.append(head)
        out += [f"  • {l.replace('**', '')}" for l in lines]
    if msg["empty"]:
        out += ["", "Nothing today: " + ", ".join(msg["empty"])]
    return "\n".join(out)


def as_card(msg):
    """An Adaptive Card (1.4, which Teams renders on desktop and phone)."""
    body = [{"type": "TextBlock", "text": msg["title"], "weight": "Bolder", "size": "Large",
             "wrap": True},
            {"type": "TextBlock", "text": msg["subtitle"], "isSubtle": True, "spacing": "None",
             "wrap": True, "size": "Small"}]
    for head, lines in msg["blocks"]:
        body.append({"type": "TextBlock", "text": head, "weight": "Bolder", "color": "Accent",
                     "spacing": "Medium", "separator": True, "wrap": True})
        body += [{"type": "TextBlock", "text": f"• {l}", "wrap": True, "spacing": "Small"}
                 for l in lines]
    if msg["empty"]:
        body.append({"type": "TextBlock", "text": "Nothing today: " + ", ".join(msg["empty"]),
                     "isSubtle": True, "size": "Small", "wrap": True, "spacing": "Medium",
                     "separator": True})
    return {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard", "version": "1.4", "msteams": {"width": "Full"},
            "body": body}


def post(url, msg, timeout=30):
    """Send one message to a Teams workflow URL. Returns (HTTP status, body)."""
    payload = {"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
        "content": as_card(msg)}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")[:300]
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode(errors="replace")[:300]


# ── the morning send (hotsos_agent calls run_morning) ─────────────────────────
SEND_AT = (7, 30)            # property time; the 5 AM build and auto-push are long done
GIVE_UP_HOUR = 11            # no report or no tab by then: say so, send nothing


def arrival_text(day, arr_folder=None):
    """(text, file name) of the day's Arrival Report, or ("", why).

    The office PC has the folder synced; a PC without it reads the folder from
    SharePoint, dated as SharePoint dates it, so daily_build's own pick (a
    resend beats an earlier copy) chooses the same file either way."""
    import os
    import tempfile
    from pathlib import Path
    import daily_build
    if arr_folder and Path(arr_folder).exists():
        p = daily_build.find_arrival_report(arr_folder, day)
        return (daily_build.read_arrival_report(p), p.name) if p else ("", "not in the synced folder")
    import sharepoint
    files = [(n, m) for n, m in sharepoint.list_folder("Arrival Reports", top=15)
             if "arriv" in n.lower()]
    if not files:
        return "", "Arrival Reports folder not readable from SharePoint"
    tmp = Path(tempfile.mkdtemp(prefix="arrivals_"))
    for name, modified in files:
        data, _ = sharepoint.fetch(f"Arrival Reports/{name}")
        if data is None:
            continue
        (tmp / name).write_bytes(data)
        t = _dt.datetime.fromisoformat(modified.replace("Z", "+00:00")).timestamp()
        os.utime(tmp / name, (t, t))
    p = daily_build.find_arrival_report(tmp, day)
    return (daily_build.read_arrival_report(p), p.name) if p else ("", "no report for the day yet")


def run_morning(day, read_day, arr_folder=None, test=False, already=None, log=print):
    """Build both messages and post whichever has not gone yet. Returns the
    record kept under SENT_KEY. `read_day(day)` -> (tab, rows), live sheet."""
    import db
    hooks = db._load_key(WEBHOOKS_KEY) or {}
    rec = {"date": str(day), "test": test, "results": dict((already or {}).get("results") or {})}
    text, src = arrival_text(day, arr_folder)
    if not text:
        return dict(rec, status="waiting", why=f"Arrival Report: {src}")
    rec["report"] = src
    try:
        tab, rows = read_day(day)
    except LookupError as ex:
        return dict(rec, status="waiting", why=f"sheet: {ex}")
    rec["tab"] = tab
    msgs = build(day, text, rows)
    for name, group in (("houseperson", "GC8 AM Houseperson 7am -3pm"),
                        ("housekeeping", "GC8 - Housekeeping")):
        if str(rec["results"].get(name, "")).startswith("2"):
            continue                                    # went on an earlier pass
        url = hooks.get("test" if test else name)
        if not url:
            rec["results"][name] = "no workflow URL"
            continue
        m = msgs[name]
        if test:
            m = dict(m, title=f"TEST for {group} · {m['title']}")
        st, body = post(url, m)
        rec["results"][name] = f"{st}" if 200 <= st < 300 else f"{st} {body[:120]}"
        log(f"teams notes -> {group}{' (test)' if test else ''}: HTTP {st}")
    ok = all(str(rec["results"].get(n, "")).startswith("2") for n in ("houseperson", "housekeeping"))
    return dict(rec, status="sent" if ok else "failed")


def main():
    ap = argparse.ArgumentParser(description="Arrival Report notes for Teams")
    ap.add_argument("report", help="the Arrival Report (.txt or .htm)")
    ap.add_argument("--sheet", help="GC8 workbook (.xlsx) for who has each room")
    ap.add_argument("--date", default=None)
    ap.add_argument("--send", metavar="URL", help="post both messages to this workflow URL")
    a = ap.parse_args()
    import clock
    import daily_build
    day = _dt.date.fromisoformat(a.date) if a.date else clock.today()
    rows = []
    if a.sheet:
        import hotsos_sync as hs
        rows = hs.read_workbook(a.sheet, day)[1]
    msgs = build(day, daily_build.read_arrival_report(a.report), rows)
    sys.stdout.reconfigure(encoding="utf-8")
    for name, m in msgs.items():
        print(f"===== {name}\n{as_text(m)}\n")
        if a.send:
            print("  sent:", post(a.send, m))


if __name__ == "__main__":
    main()
