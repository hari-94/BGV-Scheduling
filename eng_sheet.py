"""
eng_sheet.py — the day's names for the "RQS-ENG-Runners" tab of
"Daily Tasks Ops Departments.xlsx" (GC8Team site), which the Engineering
team works from.

Four things on that tab are ours and were typed in by hand every morning:
the date at the top, the AM and the PM housepersons by HSP number, and each
RQS with the Full Clean rooms they inspect, under the building the rooms are
in. Everything else on it belongs to other departments and is never touched.

The workbook is open in Excel Online all day (the Front Desk keeps their tabs
in it), so the office PC does not edit the file. After a Push it drops the
day's values as a small text file into SharePoint ("App Outbox", beside the
GC8 Inspections workbook); a Power Automate flow sees the file and runs the
Office Script in office_scripts/eng_sheet.ts, which writes only those cells,
in place, while others have the workbook open.

Where the values come from:
  * RQS and rooms: the final GC8 Inspections tab, the same rows the Push just
    sent to HotSOS -- Full Clean only, grouped by building.
  * AM housepersons: Schedule.xlsx, "Houseperson AM" section. The number in a
    cell is the HSP route ("3", "6 + 7", "2 - Deep clean lobby bathroom",
    "Entrenamiento ... +5"); a building ("BLD 3") is not. The AM lead is
    whoever the "AM Lead" / "PM Leads" sections have on "Lead" that is not a
    PM lead.
  * PM housepersons: the "Houseperson PM" section, the same route numbers.
    The PM lead is whoever "PM Leads" has on a PM lead ("Lead - PM"); a PM
    lead's cell naming a route instead ("HSP 1", "HSP 1PM trining veronica")
    is that PM route -- on every such day to 28 Oct the AM route was already
    covered and the PM one was open.
"""
import datetime as _dt
import json
import re
from pathlib import Path

import clock

OUTBOX = "App Outbox"
HSP_ROUTES = range(1, 8)

_BLD = re.compile(r"\b(?:bld|bldg|building)\s*\d+", re.I)
# The route is the first number in the cell and any joined to it by "+"; what
# follows is the task, whose numbers are stairs, theaters and lockers. Reading
# every digit put "1 deep clean stair 6" on HSP 6 as well as 1, and on the PM
# side "4 + deep celan lookers 1-39" on HSP 1.
_ROUTE = re.compile(r"(?<![\d:.])[1-7](?![\d:])(?:\s*\+\s*[1-7](?![\d:]))*")


def hsp_numbers(raw) -> list:
    """The HSP routes a houseperson cell names: "6 + 7" -> [6, 7],
    "6 - Women bathroom/ BLD 3" -> [6], "Entrenamiento ... +5" -> [5],
    "6+7 + deep clean theather 5" -> [6, 7]."""
    s = _BLD.sub(" ", str(raw or ""))
    s = re.sub(r"\b\d{1,2}:\d{2}\b", " ", s)            # a time ("8:30 am") is not a route
    m = _ROUTE.search(s)
    return sorted({int(n) for n in re.findall(r"\d", m.group())}) if m else []


def _working(rec, iso) -> bool:
    import roster_import as ri
    kind, _ = ri.cell_kind(rec, iso)
    raw = str((rec.get("cells") or {}).get(iso, "") or "").strip()
    return bool(raw) and kind not in (ri.KIND_OFF, ri.KIND_VTO, ri.KIND_NOCALL)


def _short(name) -> str:
    """How the sheet writes a person: no trailing dots, no section suffix."""
    return re.sub(r"\.+$", "", str(name).split(" · ")[0].strip())


def housepersons(week, iso, shift="AM") -> dict:
    """{"HSP 1": [names], ..., "LEAD": [names]} for the day's AM or PM shift."""
    out = {f"HSP {n}": [] for n in HSP_ROUTES}
    out["LEAD"] = []
    for key, rec in (week.get("people") or {}).items():
        sec = str(rec.get("section") or "")
        if rec.get("group") != "other" or not _working(rec, iso):
            continue
        raw = str((rec.get("cells") or {}).get(iso, "") or "")
        name = _short(rec.get("name") or key)
        low = raw.lower()
        if sec == f"Houseperson {shift}":
            for n in hsp_numbers(raw):
                out[f"HSP {n}"].append(name)
        elif shift == "AM" and sec in ("AM Lead", "PM Leads"):
            if sec == "AM Lead" or ("lead" in low and "pm" not in low):
                out["LEAD"].append(name)
        elif shift == "PM" and sec == "PM Leads":
            if "lead" in low and "pm" in low:
                out["LEAD"].append(name)
            elif "lead" not in low:
                for n in hsp_numbers(raw):
                    out[f"HSP {n}"].append(name)
    return out


def _display_names(full_names, directory=()):
    """First name, plus the last initial where the first name is shared --
    "Edward", "Gustavo", but "Luis R" (Luis Rendon, Luis Urbina)."""
    firsts = {}
    for n in set(directory) | set(full_names):
        parts = str(n).split()
        if parts:
            firsts.setdefault(parts[0].lower(), set()).add(n)
    out = {}
    for n in full_names:
        parts = str(n).split()
        if not parts:
            continue
        shared = len(firsts.get(parts[0].lower(), ())) > 1
        out[n] = f"{parts[0]} {parts[1][0]}" if shared and len(parts) > 1 else parts[0]
    return out


def rqs_rooms(rows, directory=()) -> dict:
    """{"1": [[name, "1424E 1424F"], ...], "2": [...], "3": [...]}: each RQS's
    Full Clean rooms, by the building the rooms are in."""
    by = {}
    for r in rows:
        svc = str(r.get("service") or "").lower()
        who = " ".join(str(r.get("rqs") or "").split())
        room = str(r.get("room") or "").strip().upper()
        if "full" not in svc or not who or not re.fullmatch(r"\d{4}[A-I]", room):
            continue
        if re.match(r"^(inspector\s*\d+|rqs\s*[12]?|not assigned|-)$", who, re.I):
            continue
        by.setdefault(room[0], {}).setdefault(who, []).append(room)
    names = _display_names({w for b in by.values() for w in b}, directory)
    return {b: [[names.get(w, w), " ".join(sorted(set(rs)))]
                for w, rs in sorted(people.items(), key=lambda kv: kv[0])]
            for b, people in sorted(by.items())}


def payload(day: _dt.date, rows, week, now=None, directory=()) -> dict:
    now = now or clock.now()
    return {
        "date": f"{day:%m/%d/%Y}",
        "title": f"{day:%m/%d/%Y}   ·   Updated {now:%m/%d %I:%M %p}".replace(" 0", " "),
        "housepersons": housepersons(week, day.isoformat()),
        "housepersons_pm": housepersons(week, day.isoformat(), "PM"),
        "rqs": rqs_rooms(rows, directory),
        "made_at": clock.stamp(),
    }


def build(day: _dt.date, rows, now=None) -> dict:
    """The payload for `day` from the stored staff schedule."""
    import db
    import roster_import as ri
    try:
        import staff_names
        directory = [a.get("label", "") for a in (staff_names.attendants() or [])]
    except Exception:
        directory = []
    iso = day.isoformat()
    weeks, ov = db.load_staff_weeks(), db.load_staff_overrides()
    wk = ri.find_week_key(sorted(weeks), iso)
    week = ri.apply_overrides(weeks[wk], ov or {}, wk)[0] if wk else {"people": {}}
    return payload(day, rows, week, now, directory)


def publish(folder, day: _dt.date, rows, now=None) -> Path:
    """Drop the day's values into `folder`/App Outbox for the flow to apply.
    A .txt file, so the flow hands the script plain text."""
    p = build(day, rows, now)
    out = Path(folder) / OUTBOX
    out.mkdir(parents=True, exist_ok=True)
    cutoff = clock.now().timestamp() - 7 * 86400          # the flow has long since read these
    for old in out.glob("eng-sheet *.txt"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    f = out / f"eng-sheet {day.isoformat()} {clock.now():%H%M%S}.txt"
    # ASCII only: the flow is told the file is text/plain with no charset, and
    # a "·" or an accented name must not depend on how it guesses one.
    f.write_text(json.dumps(p, ensure_ascii=True), encoding="ascii")
    return f
